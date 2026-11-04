"""E1–E8 da §3b: medidas calculadas da evidência e julgadas pelo pass_rule do prereg/pilot_exit.yaml, sem mudar
a regra. Critério por fatia (E1–E5) passa só se passar nas duas fatias; medida ausente reprova (nunca passa por
omissão). A fração de acerto do E4 é relatada e nunca entra em regra.
"""
from __future__ import annotations

from . import rules

PER_SLICE = ("E1", "E2", "E3", "E4")


def measures_e1(s: dict) -> dict:
    d = s.get("directions") or {}
    covered = sum(1 for v in d.values() if v in ("OUTPUT", "UNSUPPORTED"))
    return {"directions_covered": covered if d else None,
            "values_without_trace": s.get("values_without_trace"),
            "silent_insertions": s.get("silent_insertions")}


def measures_e2(s: dict) -> dict:
    g = s.get("grain") or {}
    return {"grain_mismatches": g.get("mismatches"), "invariance_failures": g.get("invariance_failures")}


def measures_e3(s: dict) -> dict:
    c = s.get("claims") or {}
    return {"claims_incomplete": c.get("incomplete"), "unproven_misjudged": c.get("unproven_misjudged"),
            "off_table_compositions": c.get("off_table_compositions"), "skos_roundtrip_ok": c.get("skos_roundtrip_ok")}


def measures_e4(s: dict) -> dict:
    o = s.get("oracle") or {}
    return {"silent_losses": o.get("silent_losses"), "negatives_carried": o.get("negatives_carried")}


def measures_e5(ev: dict) -> dict:
    sl = ev.get("slices", {})
    same = [((s.get("controls") or {}).get("same_input")) for s in sl.values()]
    counted = [((s.get("controls") or {}).get("consequences_counted")) for s in sl.values()]
    return {"controls_same_input": None if not sl or None in same else all(same),
            "consequences_counted": None if not sl or None in counted else all(counted),
            "addendum_written_before_scale": (ev.get("addendum") or {}).get("written_before_scale")}


def measures_e6(ev: dict) -> dict:
    a = ev.get("amendments") or {}
    return {"unversioned_changes": a.get("unversioned_changes"), "stale_not_marked": a.get("stale_not_marked"),
            "catalog_ok": a.get("catalog_ok")}


def measures_e7(ev: dict) -> dict:
    e = ev.get("effort") or {}
    return {"steps_without_effort": e.get("steps_without_effort"), "schedule_recomputed": e.get("schedule_recomputed")}


def measures_e8(ev: dict) -> dict:
    t = ev.get("attempts") or {}
    return {"attempts": t.get("attempts"), "expansion_blocked": t.get("expansion_blocked"),
            "plan_returned_v4": t.get("plan_returned_v4"), "breno_notified": t.get("breno_notified")}


FN = {"E1": measures_e1, "E2": measures_e2, "E3": measures_e3, "E4": measures_e4}
GLOBAL_FN = {"E5": measures_e5, "E6": measures_e6, "E7": measures_e7, "E8": measures_e8}


def judge(rule: str, m: dict) -> dict:
    try:
        ok = rules.evaluate(rule, m)
        return {"pass": ok, "measures": m}
    except rules.MissingMeasure as e:
        return {"pass": False, "measures": m, "error": f"MISSING_MEASURE: {e}"}


def evaluate(criteria: list[dict], ev: dict, only=None) -> dict:
    out = {}
    for c in criteria:
        cid = c["id"]
        if only and cid not in only:
            continue
        if cid in FN:
            per = {sl: judge(c["pass_rule"], FN[cid](s)) for sl, s in sorted(ev.get("slices", {}).items())}
            ok = bool(per) and all(v["pass"] for v in per.values())
            out[cid] = {"name": c["name"], "pass_rule": c["pass_rule"], "pass": ok, "per_slice": per}
        elif cid in GLOBAL_FN:
            r = judge(c["pass_rule"], GLOBAL_FN[cid](ev))
            out[cid] = {"name": c["name"], "pass_rule": c["pass_rule"], **r}
        else:
            out[cid] = {"name": c.get("name"), "pass_rule": c.get("pass_rule"), "pass": False,
                        "error": "critério sem implementação de medida"}
    return out
