"""Gate: alegação sem prova sai UNPROVEN; mesmo conceito sem evidência das âncoras não vira exact.

Uso: python -I -m bo.arbiter.unproven

Cada caso da bateria (bo.arbiter.battery.unproven_cases) é julgado SOZINHO (átomos próprios) e tem de sair com o
veredito esperado (UNPROVEN, com a regra que falta) — e o CONTROLE, a mesma alegação com a prova que faltava,
tem de sair OK (o teste não é vazio: é a falta de prova, e não outra coisa, que derruba). Para os casos de mesmo
conceito, além de não sair OK, nenhum composto do K4 pode usá-los como perna (não transportam por fecho).
Relatório: $BO_DATA/ARBITERLIB/unproven.json.
"""

from __future__ import annotations

import sys

from . import battery as B
from . import engine
from .common import emit, now, write_report
from .inputs import Glossary


def _gloss(g):
    return None if g is None else Glossary(g["claims"], g["audits"])


def judge(rec: dict, glossary=None) -> dict:
    res = engine.arbitrate(B.items_of([rec], "battery:unproven"), glossary=_gloss(glossary),
                           decided_at=now(), arbiter_sha256="0" * 64)
    v = next(x for x in res["verdicts"] if x["claim_id"] == rec["claim_id"])
    used = [x for x in res["verdicts"] if x["composition_used"] and rec["claim_id"] in "∘".join(x["composition_used"])]
    return {"verdict": v["verdict"], "rules": v["rules"], "detail": v["detail"], "composites": len(used)}


def run_cases() -> list[dict]:
    rows = []
    for c in B.unproven_cases():
        case_g = c.get("glossary_case")
        got = judge(c["claim"], case_g)
        ctl = judge(c["control"], c.get("glossary")) if c.get("control") is not None else None
        ok = got["verdict"] == c["verdict"] and c["rule"] in got["rules"]
        if c["same_concept"]:
            ok = ok and got["verdict"] != "OK" and got["composites"] == 0
        ctl_ok = ctl is None or ctl["verdict"] == "OK"
        rows.append({"case": c["case"], "claim_id": c["claim"]["claim_id"], "expected": [c["verdict"], c["rule"]],
                     "got": [got["verdict"], got["rules"]], "control": None if ctl is None else [ctl["verdict"], ctl["rules"]],
                     "same_concept": c["same_concept"], "pass": bool(ok and ctl_ok),
                     "detail": got["detail"][:300], "control_detail": None if ctl is None else ctl["detail"][:300]})
    return rows


def main(argv=None) -> int:
    rows = run_cases()
    bad = [r for r in rows if not r["pass"]]
    for r in rows:
        emit(f"  {'ok  ' if r['pass'] else 'FALHA'} {r['case']:<52} {r['got'][0]:<16} {','.join(r['got'][1])[:60]}"
             f"   controle: {r['control'][0] if r['control'] else '-'}")
        if not r["pass"]:
            emit(f"        esperado {r['expected']}; {r['detail']}; controle: {r['control_detail']}")
    n_same = sum(1 for r in rows if r["same_concept"])
    p = write_report("unproven", {"cases": rows, "n": len(rows), "n_same_concept": n_same, "failures": len(bad)})
    emit(f"[{now()}] unproven: {len(rows) - len(bad)}/{len(rows)} casos com o veredito esperado e controle OK "
         f"({n_same} de mesmo conceito); relatório {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
