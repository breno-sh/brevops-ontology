#!/usr/bin/env python3
"""Checador de plano (SAFETY). Implementação: src/bo/safety/plan_check.py.

  terraform show -json plano.tfplan | plan_guard.py --context ctx.json [--intents vinculos.json] [--tf-dir D]
                                                    [--live-prices precos.json] [--report relatorio.json]
O plano entra pela entrada padrão (do canal efêmero, sem ir ao disco). Sai 0 se aprovado, 1 se recusado.
O relatório leva endereços, códigos e custo estimado; nunca valor de atributo.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if (_SRC / "bo" / "safety").is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bo.safety.plan_check import PlanRefused, check_plan, enforce  # noqa: E402,F401


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="plan_guard")
    ap.add_argument("--plan", default="-")
    ap.add_argument("--context", required=True)
    ap.add_argument("--intents")
    ap.add_argument("--tf-dir")
    ap.add_argument("--live-prices")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    plan = json.load(sys.stdin) if a.plan == "-" else json.loads(Path(a.plan).read_text(encoding="utf-8"))
    ctx = json.loads(Path(a.context).read_text(encoding="utf-8"))
    intents = json.loads(Path(a.intents).read_text(encoding="utf-8")) if a.intents else None
    lp = json.loads(Path(a.live_prices).read_text(encoding="utf-8")) if a.live_prices else None
    rep = check_plan(plan, ctx, intents=intents, tf_dir=Path(a.tf_dir) if a.tf_dir else None, live_prices=lp)
    if a.report:
        Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    for f in rep["findings"]:
        print(f"  {f['code']:<15} {f['address']}: {f['detail']}")
    print(f"plan_guard: {'APROVADO' if rep['ok'] else 'RECUSADO'}; {len(rep['findings'])} achado(s); "
          f"custo estimado {rep['cost']['total']:.4f} (teto do provedor {rep['cost']['caps']['provider']})")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
