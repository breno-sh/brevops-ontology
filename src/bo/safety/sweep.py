"""Varredura do provedor inteiro, em todas as regiões lidas da conta, só para RELATAR (§10.3).

  python -I -m bo.safety.sweep --provider P --dry-run
  python -I -m bo.safety.sweep --provider P --run MODULO --record-baseline           (antes do lote)
  python -I -m bo.safety.sweep --provider P --run MODULO [--batch B] [--expect-empty] [--project X] [--tenancy X]
  python -I -m bo.safety.sweep --provider P --fixture ARQ.json [--run MODULO ...]     (executor gravado, offline)

--dry-run não chama nenhuma CLI: imprime o comando que lê as regiões da conta, cada fonte por região e global, e
a cobertura (todo tipo da allowlist enxergado por alguma fonte); sai 1 se a cobertura tiver buraco.
Execução de verdade exige BO_CLOUD_GO=1 e a identidade conferida (identity.check); sem isso, recusa (saída 2).
Relatório público (results/<MODULO>/sweep_report.json): só contagens por classe, tipo e região, nunca id ou nome.
Detalhe com referências: no canal privado do manifesto (sweep_detail.json). Nada é apagado aqui.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import identity, residue, skus
from .common import PROVIDERS, SafetyError, bo_repo, now, tag_value, write_json
from .manifest import Manifest
from .ownership import owned
from .providers import REGION_CMD, SOURCES, CliAdapter, coverage

FAIL_CLASSES = ("residuo_inesperado", "investigar")


class FixtureRunner:
    """Executor gravado: {"comando com espaços": {"rc": 0, "out": <json>}}. Comando ausente = erro (rc 254)."""

    def __init__(self, path: Path):
        self.map = json.loads(Path(path).read_text(encoding="utf-8"))
        self.calls: list[str] = []

    def __call__(self, argv, env=None):
        k = " ".join(argv)
        self.calls.append(k)
        if k not in self.map:
            return 254, ""
        v = self.map[k]
        return v.get("rc", 0), json.dumps(v.get("out", {}))


def dry_run(provider: str, table: dict) -> tuple[int, list[str]]:
    lines = [f"[{provider}]"]
    lines.append("  regiões: lidas da conta em tempo de execução por: " + " ".join(REGION_CMD[provider])
                 + "   (dry-run: não executado; nenhuma lista fixa)")
    for name, argv, _, all_types in SOURCES[provider]["region"]:
        lines.append(f"  por região  {name:<18} {' '.join(argv)}" + ("   [todos os tipos]" if all_types else ""))
    for name, argv, _, all_types in SOURCES[provider]["region_best_effort"]:
        lines.append(f"  por região  {name:<18} {' '.join(argv)}   [todos os tipos, se o índice existir]")
    for name, argv, _, all_types in SOURCES[provider]["global"]:
        lines.append(f"  global      {name:<18} {' '.join(argv)}" + ("   [todos os tipos]" if all_types else ""))
    cov = coverage(table)[provider]
    holes = sorted(t for t, v in cov.items() if not v)
    lines.append(f"  cobertura: {len(cov) - len(holes)}/{len(cov)} tipos da allowlist enxergados por alguma fonte"
                 + (f"; SEM FONTE: {', '.join(holes)}" if holes else ""))
    return (1 if holes else 0), lines


def run_sweep(provider: str, adapter, table: dict, res: dict, run_tag: str | None = None,
              man: Manifest | None = None, baseline_refs: set | None = None) -> tuple[dict, list[dict]]:
    regions = adapter.regions()
    items = adapter.list_all()
    states = man.load() if man else {}
    rows, counts, by_type, by_region = [], {}, {}, {}
    for it in items:
        why = owned(it, run_tag, states) if run_tag else None
        cls = residue.classify(res, provider, it, why, baseline_refs or set())
        rows.append({**it, "class": cls, "owner_reason": why})
        counts[cls] = counts.get(cls, 0) + 1
        by_type.setdefault(it.get("type"), {}).setdefault(cls, 0)
        by_type[it.get("type")][cls] += 1
        by_region[it.get("region")] = by_region.get(it.get("region"), 0) + 1
    rep = {"schema": "bo.safety.sweep_report/1", "provider": provider, "at": now(),
           "regions_read_from_account": regions, "n_regions": len(regions),
           "sources": [s[0] for s in SOURCES[provider]["region"] + SOURCES[provider]["global"]],
           "best_effort_errors": len(getattr(adapter, "errors", [])),
           "counts": counts, "by_type": by_type, "by_region": by_region, "n_items": len(items),
           "run_tag": run_tag, "rule": "só relato; apagar exige tag ou linha de manifesto desta execução"}
    return rep, rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sweep")
    ap.add_argument("--provider", required=True, choices=PROVIDERS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run", help="módulo dono do manifesto (ex.: SMOKE-AWS)")
    ap.add_argument("--batch", help="lote (padrão: o do manifesto)")
    ap.add_argument("--expect-empty", action="store_true")
    ap.add_argument("--fixture")
    ap.add_argument("--project")
    ap.add_argument("--tenancy")
    ap.add_argument("--record-baseline", action="store_true",
                    help="grava as referências vistas agora como baseline privado do módulo (só relato)")
    ap.add_argument("--report", help="caminho do relatório público (padrão results/<run>/sweep_report.json)")
    a = ap.parse_args(argv)
    table = skus.load_table()
    if a.dry_run:
        rc, lines = dry_run(a.provider, table)
        print("\n".join(lines))
        return rc
    if a.fixture:
        runner = FixtureRunner(Path(a.fixture))
    else:
        if os.environ.get("BO_CLOUD_GO") != "1":
            print("sweep: recusado; sem GO do Breno (BO_CLOUD_GO=1) nenhuma CLI de nuvem roda", file=sys.stderr)
            return 2
        identity.check(a.provider)  # aborta se a sessão não é a sandbox da allowlist
        from .providers import subprocess_runner
        runner = subprocess_runner
    ctx = {k: v for k, v in (("project", a.project or os.environ.get("GOOGLE_PROJECT")),
                             ("tenancy", a.tenancy)) if v}
    adapter = CliAdapter(a.provider, runner, ctx)
    res = residue.load()
    man = Manifest(a.run) if a.run else None
    run_tag = None
    if man:
        st = man.load()
        batch = a.batch or (next(iter(st.values())).intent["batch_id"] if st else None)
        run_tag = tag_value(batch) if batch else None
    baseline = set()
    bpath = man.private / f"baseline_{a.provider}.json" if man else None
    if bpath and bpath.exists():
        baseline = set(json.loads(bpath.read_text(encoding="utf-8"))["refs"])
    elif a.expect_empty and not a.record_baseline:
        print(f"sweep {a.provider}: REPROVADO --expect-empty sem baseline gravado antes do lote (--record-baseline)")
        return 1
    try:
        rep, rows = run_sweep(a.provider, adapter, table, res, run_tag, man, baseline)
    except SafetyError as e:
        print(f"sweep {a.provider}: REPROVADO ({e}); sem leitura completa não existe 'zero'", file=sys.stderr)
        return 1
    if a.record_baseline and man:
        write_json(bpath, {"provider": a.provider, "at": rep["at"], "refs": sorted(r["ref"] for r in rows)}, 0o600)
        rep["baseline_recorded"] = len(rows)
    bad = {k: v for k, v in rep["counts"].items() if k in FAIL_CLASSES}
    rep["expect_empty"] = a.expect_empty
    rep["ok"] = not (a.expect_empty and bad)
    if a.run:
        write_json(Path(a.report) if a.report else bo_repo() / "results" / a.run / "sweep_report.json", rep)
        write_json(man.private / "sweep_detail.json", {"provider": a.provider, "at": rep["at"], "items": rows}, 0o600)
    print(f"sweep {a.provider}: {rep['n_items']} item(ns) em {rep['n_regions']} região(ões) lidas da conta; "
          + ", ".join(f"{k}={v}" for k, v in sorted(rep["counts"].items())))
    if not rep["ok"]:
        print(f"sweep {a.provider}: REPROVADO --expect-empty ({bad}); investigar, não apagar às cegas")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
