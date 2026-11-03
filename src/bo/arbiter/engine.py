"""Motor do árbitro: versões → obrigações por alegação → regras de conjunto → K4 → vereditos C21.

Ordem e precedência fixas (nada depende da ordem das linhas nem do nome dos provedores):
  1. versões (C09-IDS): só a corrente é julgada; bifurcação refuta.
  2. grupos: definição única por bo_group_id (ARB-G-CONSIST); campos em bloco repetido = C01 ∪ projeções scope=block.
  3. obrigações por alegação (claimcheck): OK | REFUTED_BY_RULE | UNPROVEN.
  4. conjunto (setcheck) sobre as não refutadas; K4 (k4) sobre as OK que nenhuma regra de conjunto refutou.
  5. veredito = maior precedência entre todas as falhas: REFUTED_BY_RULE > CONTESTED > UNPROVEN > AMBIGUOUS > OK.
Saídas: vereditos (C21, um por claim_version_id e ciclo, mais os compostos do K4), ciclos do K4 e relatório.
"""

from __future__ import annotations

from collections import Counter

from . import claimcheck as CC
from . import k4 as K4
from . import setcheck as SC
from .common import canon, now, sha256_bytes
from .freeze import arbiter_sha
from .inputs import repeated_fields, resolve_versions
from .rules import verdict_of


def _sortkey(it):
    r = it["rec"]
    return (str(r.get("claim_id")), str(r.get("claim_version_id")), canon(r))


def _group_defs(items):
    defs: dict[str, dict] = {}
    for it in items:
        r = it["rec"]
        g = r.get("group")
        if isinstance(g, dict) and g.get("bo_group_id"):
            defs.setdefault(g["bo_group_id"], {})[canon(g)] = g
    return defs


def _event_id(cycle: int, vid: str) -> str:
    return f"EV-ARB-{cycle}-{sha256_bytes(vid.encode('utf-8'))[:16]}"


def _detail(fails: list[dict], ok_text: str) -> str:
    if not fails:
        return ok_text
    seen, parts = set(), []
    for f in fails:
        k = (f["rule"], f["detail"])
        if k in seen:
            continue
        seen.add(k)
        parts.append(f"{f['rule']}: {f['detail']}")
    s = " | ".join(parts)
    return s if len(s) <= 900 else s[:897] + "..."


def arbitrate(items: list[dict], *, glossary=None, atoms: list[dict] | None = None, cycle: int = 1,
              decided_at: str | None = None, disabled=frozenset(), arbiter_sha256: str | None = None) -> dict:
    """items: [{rec, source, domain, line}] (inputs.load). -> {verdicts, cycles, report}."""
    dis = frozenset(disabled)
    decided_at = decided_at or now()
    sha = arbiter_sha256 or arbiter_sha()
    current, superseded, vfails = resolve_versions(items)
    current = sorted(current, key=_sortkey)

    defs = _group_defs(current)
    repeated = set(repeated_fields(atoms or []))
    for it in current:
        for p in it["rec"].get("projection") or []:
            if (p.get("occurrence") or {}).get("scope") == "block" and p.get("field"):
                repeated.add(p["field"])

    checked: list[CC.Checked] = []
    for it in current:
        r = it["rec"]
        gid = r.get("bo_group_id")
        gdef = None
        extra = []
        if gid and "ARB-G-CONSIST" not in dis:
            ds = defs.get(gid, {})
            if len(ds) > 1:
                extra.append(CC.F("ARB-G-CONSIST", "REFUTED_BY_RULE", f"{gid} tem {len(ds)} definições diferentes"))
            elif not ds and not r.get("group"):
                extra.append(CC.F("ARB-G-CONSIST", "REFUTED_BY_RULE", f"{gid} sem definição em nenhuma linha"))
            elif not r.get("group") and ds:
                gdef = next(iter(ds.values()))
        try:
            c = CC.check(it, glossary=glossary, repeated=repeated, group_def=gdef, disabled=dis)
        except Exception as e:      # noqa: BLE001 - entrada impossível não derruba o árbitro
            c = CC.Checked(it, [CC.F("ARB-MALFORMED", "REFUTED_BY_RULE", f"{type(e).__name__}: {e}")], form="invalid")
        c.failures = extra + vfails.get(c.cid, []) + c.failures if "ARB-VERSION" not in dis else extra + c.failures
        checked.append(c)

    set_conf, set_diag = SC.run(checked, dis)
    refuted_by_set = {cid for x in set_conf if x["outcome"] == "REFUTED_BY_RULE" for cid in x["claims"]}
    k4 = K4.run(checked, refuted_by_set, dis)

    extra_fails: dict[str, list] = {}
    comp_used: dict[str, list] = {}
    for x in set_conf + k4["conflicts"]:
        for cid in x["claims"]:
            extra_fails.setdefault(cid, []).append(CC.F(x["rule"], x["outcome"], x["detail"]))
            if x.get("composition_used"):
                comp_used.setdefault(cid, []).append(x["composition_used"])

    verdicts, seen_vid = [], set()
    for c in checked:
        if c.vid in seen_vid:
            continue
        seen_vid.add(c.vid)
        fails = c.failures + extra_fails.get(c.cid, [])
        v = verdict_of(f["outcome"] for f in fails)
        rules = sorted({f["rule"] for f in fails})
        used = sorted(comp_used.get(c.cid, []), key=lambda ch: (len(ch), ch))
        verdicts.append({
            "claim_id": c.cid, "claim_version_id": c.vid, "event_id": _event_id(cycle, c.vid),
            "verdict": v, "rules": rules, "cycle": cycle, "composition_used": used[0] if used else None,
            "arbiter_sha256": sha, "decided_at": decided_at,
            "detail": _detail(fails, f"obrigações de {c.relation} provadas; nenhuma regra de conjunto ou de ciclo falhou"),
        })
    for comp in sorted(k4["composites"], key=lambda x: x["claim_id"]):
        vid = f"{comp['claim_id']}@1"
        if vid in seen_vid:
            continue
        seen_vid.add(vid)
        verdicts.append({
            "claim_id": comp["claim_id"], "claim_version_id": vid, "event_id": _event_id(cycle, vid),
            "verdict": comp["verdict"], "rules": comp["rules"], "cycle": cycle, "composition_used": comp["chain"],
            "arbiter_sha256": sha, "decided_at": decided_at, "detail": comp["detail"][:900],
        })

    report = _report(checked, verdicts, superseded, set_conf, set_diag, k4, items)
    return {"verdicts": verdicts, "cycles": k4["cycles"], "report": report, "checked": checked}


def _report(checked, verdicts, superseded, set_conf, set_diag, k4, items) -> dict:
    base = {c.cid for c in checked}
    vb = [v for v in verdicts if v["claim_id"] in base]
    by_rule = Counter(r for v in vb for r in v["rules"])
    by_dom: dict[str, Counter] = {}
    unglossed: Counter = Counter()
    vmap = {v["claim_version_id"]: v["verdict"] for v in vb}
    for c in checked:
        d = c.item.get("domain") or "?"
        by_dom.setdefault(d, Counter())[vmap.get(c.vid, "?")] += 1
        if CC.UNGLOSSED in (c.rec.get("subject_concept"), c.rec.get("object_concept")):
            unglossed[d] += 1
    genuine = [x for x in set_conf + k4["conflicts"] if x["outcome"] == "CONTESTED"]
    structures = {
        "groups_by_cardinality": dict(Counter((c.rec.get("group") or {}).get("cardinality", "?")
                                              for c in checked if c.form == "group")),
        "groups_crossing_occurrences": sorted(c.cid for c in checked if c.form == "group"
                                              and (c.rec.get("group") or {}).get("joins")),
        "projected_claims": sorted(c.cid for c in checked if c.form == "projection"),
        "fields_with_several_concepts": _multi_concept(checked),
        "block_occurrence_fields": sorted({p.get("field") for c in checked for p in c.rec.get("projection") or []
                                           if (p.get("occurrence") or {}).get("scope") == "block"}),
        "alternatives_proven_exclusive": sorted(c.cid for c in checked if c.rec.get("alternative_to")
                                                and c.cid not in {cid for x in set_conf for cid in x["claims"]}),
        "compositions_consistent": sum(1 for x in k4["composites"] if x["verdict"] == "OK"),
    }
    return {
        "schema": "bo.arbiter_report/1", "module": "ARBITERLIB",
        "inputs": sorted({it["source"] for it in items}),
        "n_lines": len(items), "n_current": len(checked), "n_superseded": len(superseded),
        "verdicts": dict(Counter(v["verdict"] for v in vb)),
        "verdicts_composites": dict(Counter(v["verdict"] for v in verdicts if v["claim_id"] not in base)),
        "by_rule": dict(sorted(by_rule.items())),
        "by_domain": {d: dict(c) for d, c in sorted(by_dom.items())},
        "unglossed_by_domain": dict(sorted(unglossed.items())),
        "unproven_by_domain": {d: c.get("UNPROVEN", 0) for d, c in sorted(by_dom.items())},
        "genuine_conflicts": [{k: x[k] for k in ("rule", "claims", "detail") if k in x} |
                              ({"composition_used": x["composition_used"]} if x.get("composition_used") else {})
                              for x in genuine],
        "declaration_defects": [{k: x[k] for k in ("rule", "claims", "detail")} for x in set_conf
                                if x["outcome"] == "REFUTED_BY_RULE"],
        "ambiguous_realizations": [{k: x[k] for k in ("rule", "claims", "detail")} for x in set_conf
                                   if x["outcome"] == "AMBIGUOUS"],
        "valid_structure": structures,
        "undecided": set_diag["undecided"] + k4["undecided"],
        "duplicates": set_diag["duplicates"],
        "k4": {"legs": k4["n_legs"], "attempts": len(k4["cycles"]),
               "outcomes": dict(Counter(x["outcome"] for x in k4["cycles"]))},
    }


def _multi_concept(checked) -> list[dict]:
    m: dict[str, set] = {}
    for c in checked:
        for p in c.rec.get("projection") or []:
            if p.get("concept") and p.get("concept") != CC.UNGLOSSED:
                m.setdefault(p.get("field"), set()).add(p["concept"])
    return [{"field": f, "concepts": sorted(cs)} for f, cs in sorted(m.items()) if len(cs) > 1]


def verdict_map(verdicts: list[dict]) -> dict[str, tuple]:
    """claim_version_id -> (veredito, regras, composição usada): a parte do C21 que não depende de hora, sha nem
    texto."""
    return {v["claim_version_id"]: (v["verdict"], tuple(v["rules"]), tuple(v["composition_used"] or ())) for v in verdicts}
