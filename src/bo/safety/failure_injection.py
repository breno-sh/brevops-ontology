"""Gate: matar o runner em cada etapa deixa o manifesto reconciliável e o teardown completo.

  python -I -m bo.safety.failure_injection [--provider P ...] [--quick]

Para cada provedor (4) e cada passo do runner simulado (sim_runner), o runner roda num processo próprio e é morto
com SIGKILL: antes do passo (before); e, nos passos que gravam o manifesto, no meio da linha (torn) e entre a
cópia privada e a pública (split). Depois de cada morte, a recuperação (a mesma do supervisor e do teardown:
ownership.cleanup, sob a trava cleanup-global e com identidade conferida) tem de deixar:
  R1  o processo morreu mesmo por SIGKILL (senão a injeção não testou nada)
  R2  manifesto legível: só caudas rasgadas, que a recuperação corta; nenhuma linha inválida no meio
  R3  toda intenção em estado terminal (absent ou purge_scheduled) e teardown completo (ownership.complete)
  R4  nada da execução vivo nem removendo; agendado só se previsto no EXPECTED_RESIDUE
  R5  nenhum recurso de terceiro apagado (todos os alheios, em todas as regiões, continuam lá)
  R6  cópia pública = projeção da privada, e as duas validam no C16 (bo.contracts.validate, regras C16-*)
  R7  created/confirmed só depois de intent e creating, salvo adoção marcada como reconciliada
Relatórios: $BO_REPO/results/SAFETY/failure_injection.json (resumo) e $BO_DATA/SAFETY/failure_injection_runs.jsonl.
"""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from . import residue, skus
from .common import PROVIDERS, bo_tmp, data_dir, now, results_dir, tag_value, write_json
from .fakecloud import FakeCloud
from .manifest import RANK, Manifest
from .ownership import cleanup, complete
from .sim_runner import SCENARIOS, paths, setup, sim_check


def _validate_c16(d: Path) -> list[str]:
    from bo.contracts import validate as V
    errs = []
    for side in ("public", "private"):
        for f in ("intent_manifest.jsonl", "run_manifest.jsonl"):
            p = d / side / f
            if not p.exists():
                continue
            r = V.validate("C16", p)
            errs += [f"{side}/{f}: {e}" for e in r.errors[:3]]
    return errs


def _order_check(man: Manifest) -> list[str]:
    errs = []
    for iid, s in man.load().items():
        stages = [r["stage"] for r in s.runs]
        for st in ("created", "confirmed"):
            if st in stages:
                i = stages.index(st)
                rec = s.runs[i]
                if "creating" not in stages[:i] and "reconciliado" not in (rec.get("note") or ""):
                    errs.append(f"{iid}: {st} sem creating antes")
        ranks = [RANK[x] for x in stages]
        if ranks != sorted(ranks) or len(set(ranks)) != len(ranks):
            errs.append(f"{iid}: estágios fora de ordem")
    return errs


def recover_and_check(d: Path, provider: str, table: dict, res: dict) -> dict:
    p = paths(d)
    fc = FakeCloud(p["cloud"])
    man = Manifest(f"SIM-{provider.upper()}", p["public"], p["private"])
    run_tag = tag_value(f"B-SIM-{provider.upper()}-01")
    order = {t: e["delete_order"] for t, e in table["providers"][provider]["types"].items()}
    rep = cleanup(man, fc, run_tag, sim_check(d, provider), owner="SAFETY-failure-injection",
                  order_fn=lambda t: order.get(t, 0), lock_root=p["locks"], wait_fn=lambda s: fc.advance(3600),
                  poll_s=3600)
    fails = []
    bad_lines = [x for x in man.problems() if "linha_invalida" in x or "cauda" in x]
    if bad_lines:
        fails.append("R2 manifesto ilegível depois da recuperação: " + ", ".join(bad_lines))
    ok, why = complete(rep, man, lambda it: residue.owned_expected(res, provider, it))
    if not ok:
        fails.append("R3 teardown incompleto: " + "; ".join(why))
    items = fc.items()
    mine = [i for i in items.values() if i.get("owner") == "bo"]
    for it in mine:
        if not residue.owned_expected(res, provider, it):
            fails.append(f"R4 sobrou {it['type']} em {it['state']}")
    foreign_before = sum(1 for _ in SCENARIOS[provider]) + 1
    foreign_now = sum(1 for i in items.values() if i.get("owner") == "terceiro")
    if foreign_now != foreign_before or fc.foreign_deletes():
        fails.append(f"R5 recurso de terceiro apagado ({foreign_before - foreign_now})")
    if not man.public_consistent():
        fails.append("R6 cópia pública diferente da projeção da privada")
    fails += ["R6 " + e for e in _validate_c16(d)]
    fails += ["R7 " + e for e in _order_check(man)]
    return {"fails": fails, "intents": {k: v.last for k, v in man.load().items()},
            "residue": sorted({f"{i['type']}:{i['state']}" for i in mine}), "adopted": len(rep.adopted),
            "cut_tails": [x for x in rep.problems if "cauda_cortada" in x]}


def run_one(base: Path, provider: str, table: dict, res: dict, kill_at, mode) -> dict:
    d = base / provider / (f"k{kill_at:03d}-{mode}" if kill_at else "sem-falha")
    shutil.rmtree(d, ignore_errors=True)
    setup(d, provider, table)
    argv = [sys.executable, "-I", "-m", "bo.safety.sim_runner", "--dir", str(d), "--provider", provider]
    if kill_at:
        argv += ["--kill-at", str(kill_at), "--mode", mode]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    out = {"provider": provider, "kill_at": kill_at, "mode": mode, "returncode": r.returncode}
    fails = []
    if kill_at and r.returncode != -signal.SIGKILL:
        fails.append(f"R1 o runner não morreu por SIGKILL (código {r.returncode}): {r.stderr[-300:]}")
    if not kill_at and r.returncode != 0:
        fails.append(f"runner sem falha saiu {r.returncode}: {r.stderr[-300:]}")
    chk = recover_and_check(d, provider, table, res)
    out.update(chk)
    out["fails"] = fails + chk["fails"]
    if not out["fails"]:
        shutil.rmtree(d, ignore_errors=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", action="append", choices=PROVIDERS)
    ap.add_argument("--quick", action="store_true", help="só os modos before (testes)")
    a = ap.parse_args(argv)
    table = skus.load_table()
    res = residue.load()
    base = bo_tmp() / "failure_injection"
    runs_path = data_dir() / "failure_injection_runs.jsonl"
    data_dir().mkdir(parents=True, exist_ok=True)
    summary = {"schema": "bo.safety.failure_injection/1", "generated_at": now(), "providers": {}}
    all_runs = []
    total_fail = 0
    for p in a.provider or PROVIDERS:
        clean = run_one(base, p, table, res, None, "before")
        steps = _steps(base, p, table)
        runs = [clean]
        for k in range(1, steps["n"] + 1):
            runs.append(run_one(base, p, table, res, k, "before"))
            if not a.quick and k in steps["writes"]:
                runs.append(run_one(base, p, table, res, k, "torn"))
                runs.append(run_one(base, p, table, res, k, "split"))
        nf = sum(1 for r in runs if r["fails"])
        total_fail += nf
        summary["providers"][p] = {
            "steps": steps["n"], "write_steps": len(steps["writes"]), "runs": len(runs), "failed": nf,
            "kill_modes": sorted({r["mode"] for r in runs if r["kill_at"]}),
            "adoptions": sum(r["adopted"] for r in runs), "cut_tails": sum(len(r["cut_tails"]) for r in runs),
            "residue_kinds": sorted({x for r in runs for x in r["residue"]}),
            "resource_types": [t for t, _ in SCENARIOS[p]],
        }
        all_runs += runs
        print(f"{p}: {len(runs)} execuções ({steps['n']} passos, {len(steps['writes'])} com gravação), {nf} falha(s)")
    runs_path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in all_runs),
                         encoding="utf-8")
    summary["total_runs"] = len(all_runs)
    summary["total_failed"] = total_fail
    summary["checks"] = ["R1 SIGKILL real", "R2 manifesto legível", "R3 intenções terminais e teardown completo",
                         "R4 só resíduo esperado", "R5 nenhum alheio apagado", "R6 pública = projeção, C16 válido",
                         "R7 ordem do protocolo"]
    if not a.provider and not a.quick:
        write_json(results_dir() / "failure_injection.json", summary)
    for r in all_runs:
        if r["fails"]:
            print(f"  FALHA {r['provider']} k={r['kill_at']} {r['mode']}: {r['fails'][:3]}")
    print(f"failure_injection: {len(all_runs)} execuções, {total_fail} falha(s) -> {'OK' if not total_fail else 'REPROVADO'}")
    return 0 if total_fail == 0 else 1


def _steps(base: Path, provider: str, table: dict) -> dict:
    d = base / provider / "contagem"
    shutil.rmtree(d, ignore_errors=True)
    setup(d, provider, table)
    r = subprocess.run([sys.executable, "-I", "-m", "bo.safety.sim_runner", "--dir", str(d), "--provider", provider],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise SystemExit(f"contagem de passos falhou: {r.stderr[-400:]}")
    shutil.rmtree(d, ignore_errors=True)
    j = json.loads(r.stdout.strip().splitlines()[-1])
    return {"n": j["steps"], "writes": set(j["writes"])}


if __name__ == "__main__":
    sys.exit(main())
