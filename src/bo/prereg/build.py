"""Materializa o pré-registro: python -I -m bo.prereg.build [--check]

Escreve, a partir de src/bo/prereg/content.py e de prereg/power.py (e só deles):
  $BO_REPO/prereg/{metrics_spec.yaml, probe_types.yaml, h2h_fairness.yaml, pilot_exit.yaml, SEEDS.txt,
                   power.json, PREREG.html}
  $BO_REPO/results/PREREG/{OSF_ID.txt, MANIFEST.sha256}
--check não grava nada: sai 1 se algum arquivo publicado difere do que o conteúdo produz (regeneração idêntica).
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

from . import common, content as C, render, seeds

OSF_TEXT = ("PENDING\n"
            "# Registro OSF do pré-registro v3 (D4): feito pelo Breno. Troque a primeira linha pelo ID do OSF.\n"
            "# prereg/OSF_ID.txt (o caminho do brief) está fora do owns do PREREG; por isso o estado fica aqui.\n")


def metrics_spec() -> dict:
    ms = []
    for m in C.METRICS:
        definition = common.SEP.join(f"{lab}: {m[key]}" for lab, key in zip(
            common.CLAUSES, ["definition", "population", "direction", "unit", "denominator", "unknown"]))
        ms.append({
            "metric_id": m["metric_id"], "definition": definition, "reading": m["reading"], "axis": m["axis"],
            "quantifier": m["quantifier"], "frame": m["frame"],
            "inclusion": f"{m['inclusion_id']}: {m['inclusion_text']}", "weights": m["weights"],
            "uncertainty": m["uncertainty"],
        })
    return {"schema": "bo.metrics_spec/1", "contract": "C15", "contract_version": "3.0.0", "module": "PREREG",
            "generated_at": C.AUTHORED_AT, "metrics": ms}


def probe_types() -> dict:
    pts = []
    for p in C.PROBE_TYPES:
        pts.append({
            "probe_type": p["probe_type"], "preconditions": p["preconditions"],
            "negative_control": p["negative_control"], "repetitions": p["repetitions"],
            "tolerance": p["tolerance"], "polling": p["polling"], "window": p["window"],
            "cost_limit": {"amount": p["cost_limit"], "currency": "USD"},
            "validated_support": [{"provider": pv, "status": "unknown", "evidence": []} for pv in C.PROVIDERS],
        })
    return {"schema": "bo.probe_types/1", "contract": "C22", "contract_version": "3.0.0", "module": "PREREG",
            "generated_at": C.AUTHORED_AT, "protocol_version": "1.0.0", "probe_types": pts}


def h2h_fairness(spec_text: str) -> dict:
    return {
        "schema": "bo.h2h_fairness/1", "contract": "C28", "contract_version": "1.0.0", "module": "PREREG",
        "generated_at": C.AUTHORED_AT,
        # o universo U ainda não existe: a referência é a definição pré-registrada do frame (metrics_spec.yaml);
        # o BENCH-CONTRACT publica a sua versão com $BO_REPO/universe/universe.json
        "universe_ref": {"path": "$BO_REPO/prereg/metrics_spec.yaml", "sha256": common.sha_bytes(spec_text.encode())},
        "cq_ref": {"path": common.portable(common.CQ_SPEC), "sha256": common.sha_file(common.CQ_SPEC)},
        "budget": {"unit": "agent_hours", "per_comparator": C.H2H["budget_per_comparator"]},
        "comparators": [{"comparator_id": c, "budget_hours": C.H2H["budget_per_comparator"], "same_universe": True,
                         "same_cqs": True} for c in C.H2H["comparators"]],
        "rules": C.H2H["rules"],
    }


def pilot_exit() -> dict:
    pe = dict(C.PILOT_EXIT)
    return {"schema": "bo.pilot_exit/1", "module": "PREREG", "generated_at": C.AUTHORED_AT, "version": C.VERSION,
            **pe, "reasoning_controls_rule": C.CONTROLS_RULE}


def seeds_txt() -> str:
    lines = [f"# SEEDS.txt — sementes pré-registradas do BrevOps v3 (PREREG, {C.AUTHORED_AT}, America/Recife)",
             f"# Regra: {C.SEED_RULE}",
             "# Formato: TSV, uma semente por linha: nome<TAB>semente<TAB>consumidor<TAB>para quê",
             "name\tseed\tconsumer\tpurpose"]
    for name, consumer, purpose in C.SEEDS:
        lines.append(f"{name}\t{seeds.derive(name)}\t{consumer}\t{purpose}")
    return "\n".join(lines) + "\n"


def content_sha() -> str:
    return common.sha_bytes(inspect.getsource(C).encode())


def produce() -> dict[Path, str]:
    """Todos os arquivos publicados, em memória, na ordem de dependência."""
    F = common.FILES
    out: dict[Path, str] = {}
    out[F["metrics_spec"]] = common.yaml_dump(metrics_spec())
    out[F["probe_types"]] = common.yaml_dump(probe_types())
    out[F["h2h_fairness"]] = common.yaml_dump(h2h_fairness(out[F["metrics_spec"]]))
    out[F["pilot_exit"]] = common.yaml_dump(pilot_exit())
    out[F["seeds"]] = seeds_txt()
    pw = common.power_module()
    power_doc = build_power(pw, out[F["metrics_spec"]])
    out[F["power_json"]] = pw["dumps"](power_doc)
    hashes = {
        "prereg/metrics_spec.yaml": ("C15 3.0.0", common.sha_bytes(out[F["metrics_spec"]].encode())),
        "prereg/probe_types.yaml": ("C22 3.0.0", common.sha_bytes(out[F["probe_types"]].encode())),
        "prereg/h2h_fairness.yaml": ("C28 1.0.0", common.sha_bytes(out[F["h2h_fairness"]].encode())),
        "prereg/power.py": ("código", common.sha_file(F["power_py"])),
        "prereg/power.json": ("C15 3.0.0", common.sha_bytes(out[F["power_json"]].encode())),
        "prereg/SEEDS.txt": ("texto", common.sha_bytes(out[F["seeds"]].encode())),
        "prereg/pilot_exit.yaml": ("bo.pilot_exit/1", common.sha_bytes(out[F["pilot_exit"]].encode())),
    }
    ctx = {
        "power": power_doc, "pilot_exit": pilot_exit(), "probe_types": probe_types(),
        "h2h": json.loads(json.dumps(h2h_fairness(out[F["metrics_spec"]]))),
        "seeds": [[n, str(seeds.derive(n)), c, p] for n, c, p in C.SEEDS],
        "hashes": hashes, "osf": "PENDING", "content_sha": content_sha(),
    }
    out[F["html"]] = render.render(ctx)
    out[common.OSF_FILE] = OSF_TEXT
    man = []
    for p in sorted(out, key=lambda x: x.as_posix()):
        man.append(f"{common.sha_bytes(out[p].encode())}  {p.resolve().relative_to(common.REPO.resolve()).as_posix()}")
    man.append(f"{common.sha_file(F['power_py'])}  prereg/power.py")
    man.sort(key=lambda s: s.split("  ", 1)[1])
    out[common.MANIFEST] = "\n".join(man) + "\n"
    return out


def build_power(pw: dict, spec_text: str) -> dict:
    """power.build lê o spec do disco; aqui ele recebe o texto em memória (via arquivo temporário em BO_TMP)."""
    import os
    import tempfile
    tmp_base = os.environ.get("BO_TMP") or str(common.DATA / "tmp" / "PREREG")
    Path(tmp_base).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_base) as td:
        sp = Path(td) / "metrics_spec.yaml"
        sp.write_text(spec_text, encoding="utf-8")
        return pw["build"](sp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="materializa o pré-registro v3")
    ap.add_argument("--check", action="store_true", help="não grava; sai 1 se algo difere")
    a = ap.parse_args(argv)
    out = produce()
    if a.check:
        bad = []
        for p, txt in out.items():
            if not p.exists() or p.read_text(encoding="utf-8") != txt:
                bad.append(p)
        for p in bad:
            print(f"DIFERE {p}")
        if bad:
            print(f"RESULTADO: REPROVADO ({len(bad)} arquivo(s) diferem do conteúdo)")
            return 1
        print(f"RESULTADO: OK (regeneração idêntica de {len(out)} arquivos)")
        return 0
    for p, txt in out.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
        print(f"gravado {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
