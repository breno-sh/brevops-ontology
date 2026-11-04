"""Gate: todo template estimado abaixo do limite do tipo, contando armazenamento, tráfego e requisições.

  python -I -m bo.probes.cost_cap            confere (e compara com results/PROBEKIT/cost_estimate.json)
  python -I -m bo.probes.cost_cap --write    regrava results/PROBEKIT/cost_estimate.json

Cada _templates/ com main.tf vira plano sintético dos dois lados; o plan_guard do SAFETY (bo.safety.plan_check)
dá achados e custo (horas, armazenamento, tráfego, requisições, custo único e resíduo) com o uso que o protocolo
implica (bo.probes.cost). Reprova se: algum template não puder ser estimado (tipo fora da tabela, caso sem
implementação no kit), o plan_guard achar algo, ou caso + controle passar do cost_limit do tipo no PREREG.
"""

from __future__ import annotations

import sys

from . import KIT_VERSION, MODULE_ID
from . import cells as C
from . import cost as K
from . import protocol as PR
from . import templates as T
from .common import ProbeError, compare_or_write, deploy_dir, now, portable, results_dir


def template_cells() -> list[str]:
    out = []
    for main in sorted(deploy_dir().glob("*/*/_templates/main.tf")):
        out.append(f"{main.parents[2].name}/{main.parents[1].name}")
    return out


def build() -> tuple[dict, list[str]]:
    from bo.safety import skus
    protos = PR.load()
    table = skus.load_table()
    rows, probs = [], []
    for cell in template_cells():
        t, _ = C.split(cell)
        if cell not in C.IMPL or t not in protos:
            probs.append(f"{cell}: template sem implementação no kit (custo não estimável)")
            continue
        if not T.has_template(cell):
            probs.append(f"{cell}: template incompleto ({', '.join(T.TEMPLATE_FILES)})")
            continue
        try:
            e = K.estimate(cell, protos[t], table)
        except (ProbeError, ValueError, KeyError) as ex:
            probs.append(f"{cell}: não estimável ({type(ex).__name__}: {str(ex)[:160]})")
            continue
        e.pop("_insts")
        rows.append(e)
        if not e["plan_guard_ok"]:
            codes = sorted({f["code"] for s in e["sides"].values() for f in s["findings"]})
            probs.append(f"{cell}: plan_guard recusou ({', '.join(codes)})")
        if not e["within_limit"]:
            probs.append(f"{cell}: estimativa acima do limite do tipo")
        missing = [k for k in ("storage", "traffic", "requests") if k not in e["by_category"]]
        if missing:
            probs.append(f"{cell}: estimativa sem {', '.join(missing)}")
    doc = {"schema": "bo.probekit.cost_estimate/1", "module": MODULE_ID, "kit_version": KIT_VERSION,
           "generated_at": now(), "currency": "USD",
           "method": "plan_guard do SAFETY sobre o plano sintético de cada lado; uso por endereço derivado do "
                     "protocolo (requisições com novas tentativas, 1 KiB por objeto, resposta <= "
                     f"{K.RESPONSE_BYTES_BOUND} bytes); horas = janela arredondada para cima",
           "templates": rows, "n_templates": len(rows)}
    return doc, probs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        doc, probs = build()
    except ProbeError as e:
        print(f"cost_cap: RECUSA ({e.code}): {e}")
        return 1
    probs += compare_or_write(results_dir() / "cost_estimate.json", doc, "--write" in argv)
    for r in doc["templates"]:
        ok = "ok" if r["within_limit"] and r["plan_guard_ok"] else "ACIMA/RECUSADO"
        print(f"  {r['cell']:<26} {ok:<15} {r['total'] / r['limit'] * 100:6.2f}% do limite do tipo")
    print(f"cost_cap: {doc['n_templates']} template(s) em {portable(deploy_dir())}")
    for p in probs:
        print("  PROBLEMA:", p)
    print("cost_cap:", "OK" if not probs else "REPROVADO")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
