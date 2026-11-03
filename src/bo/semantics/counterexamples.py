"""Gate G4: python -I -m bo.semantics.counterexamples

Cada regra do catálogo (rules.RULES) tem contraexemplo em semantics/counterexamples.jsonl que o verificador
REJEITA pela própria regra; o controle (par mínimo) é ACEITO; e o teste de mutação mostra que é a regra que
rejeita: desligada, o contraexemplo passa ('strict') ou ao menos a falha dela some ('rule_only', com o motivo).
Relatório com hora em $BO_DATA/SEMANTICS/counterexamples_report.json. Sai 0 só se tudo vale.
"""

from __future__ import annotations

import sys

from . import common
from . import projections as PJ
from .composition import compose, hub_claim
from .obligations import assess, check_set
from .rules import RULES
from .transport import check_trace


def _cmp_compose(res: dict, asserted: dict):
    """(diverge?, regra que explica a divergência)."""
    if res.get("outcome") != asserted.get("outcome"):
        return True, res.get("rule")
    claim = res.get("claim") or {}
    if "relation" in asserted and claim.get("semantic_relation") != asserted["relation"]:
        return True, "K-TABLE"
    if "fidelity" in asserted and claim.get("transport_fidelity") != asserted["fidelity"]:
        return True, "K-FIDELITY"
    return False, None


def run(ce: dict, which: str, disabled=frozenset()) -> dict:
    """which ∈ {input, control}. Devolve {rejected, rules}."""
    x = ce[which]
    k = ce["kind"]
    if k == "claim":
        a = assess(x, disabled)
        return {"rejected": a.verdict != "OK", "rules": a.rules, "verdict": a.verdict}
    if k == "set":
        out = check_set(x, disabled)
        return {"rejected": bool(out), "rules": sorted({o["rule"] for o in out})}
    if k == "trace":
        r = check_trace(x, disabled)
        return {"rejected": not r["accepted"], "rules": [r["rule"]] if not r["accepted"] and r["rule"] else [],
                "recomputed": {kk: r["recomputed"].get(kk) for kk in ("result", "code", "value", "fidelity")}}
    if k == "compose":
        res = compose(x["m1"], x["m2"], disabled)
        bad, rule = _cmp_compose(res, x["asserted"])
        return {"rejected": bad, "rules": [rule] if bad and rule else [], "outcome": res.get("outcome")}
    if k == "hub":
        if "K-HUB" in disabled:   # o atalho da v2 que a regra substitui: mesmo conceito => exact
            res = {"outcome": "COMPOSED", "claim": {"semantic_relation": "exact"}}
        else:
            res = hub_claim(x["a"], x["b"])
        bad, rule = _cmp_compose(res, x["asserted"])
        return {"rejected": bad, "rules": ["K-HUB"] if bad else [], "outcome": res.get("outcome"),
                "via": res.get("rule")}
    if k == "projections":
        r = PJ.check_projections(x["projections"], x.get("fields"), disabled)
        return {"rejected": r["verdict"] != "OK", "rules": sorted({f["rule"] for f in r["failures"]})}
    if k == "alternatives":
        r = PJ.check_alternatives(x["realizations"], disabled)
        return {"rejected": bool(r["failures"]), "rules": sorted({f["rule"] for f in r["failures"]}),
                "exclusivity": r["exclusivity"]}
    if k == "group":
        r = PJ.check_group(x["group"], disabled)
        return {"rejected": r["verdict"] != "OK", "rules": sorted({f["rule"] for f in r["failures"]})}
    raise ValueError(f"kind desconhecido: {k}")


def verify(ce: dict) -> dict:
    rule = ce["rule_id"]
    inp = run(ce, "input")
    ctl = run(ce, "control")
    off = run(ce, "input", frozenset({rule}))
    rejected_by_rule = inp["rejected"] and rule in inp["rules"]
    control_ok = not ctl["rejected"]
    if ce["mutation"] == "strict":
        mutation_ok = not off["rejected"]
    else:
        mutation_ok = rule not in off["rules"]
    return {"ce_id": ce["ce_id"], "rule_id": rule, "kind": ce["kind"], "rejected_by_rule": rejected_by_rule,
            "control_accepted": control_ok, "mutation": ce["mutation"], "mutation_ok": mutation_ok,
            "ok": rejected_by_rule and control_ok and mutation_ok,
            "input": inp, "control": ctl, "rule_disabled": off}


def main(argv=None) -> int:
    path = common.semantics_dir() / "counterexamples.jsonl"
    if not path.is_file():
        common.emit(f"FAIL: {path} ausente (rode python -I -m bo.semantics.build)")
        return 1
    ces = common.load_jsonl(path)
    results = [verify(c) for c in ces]
    by_rule = {r: [x for x in results if x["rule_id"] == r] for r in RULES}
    missing = sorted(r for r, xs in by_rule.items() if not xs)
    unknown = sorted({c["rule_id"] for c in ces} - set(RULES))
    bad = [x for x in results if not x["ok"]]
    for x in results:
        common.emit(f"  {'OK  ' if x['ok'] else 'FAIL'} {x['ce_id']:<26} {x['rule_id']:<16} rejeitado={x['rejected_by_rule']} "
                    f"controle={x['control_accepted']} mutação({x['mutation']})={x['mutation_ok']}")
    rep = {"module": "SEMANTICS", "gate": "counterexamples", "file": "semantics/counterexamples.jsonl",
           "file_sha256": common.sha256_file(path), "n_rules": len(RULES), "n_counterexamples": len(ces),
           "rules_without_counterexample": missing, "unknown_rules": unknown,
           "n_ok": len(results) - len(bad), "n_strict": sum(1 for x in results if x["mutation"] == "strict"),
           "n_rule_only": sum(1 for x in results if x["mutation"] == "rule_only"),
           "failures": [x["ce_id"] for x in bad], "results": results}
    p = common.write_report("counterexamples_report", rep)
    ok = not missing and not unknown and not bad
    common.emit(f"[{common.now()}] contraexemplos: {len(ces)} para {len(RULES)} regras; "
                f"{rep['n_ok']}/{len(ces)} ok (strict {rep['n_strict']}, rule_only {rep['n_rule_only']}); "
                f"regras sem contraexemplo: {missing or 'nenhuma'} -> {'PASS' if ok else 'FAIL'}  ({p})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
