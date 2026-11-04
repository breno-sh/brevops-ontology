"""E3: alegações da fatia (as que o E2E consome: $BO_DATA/PILOT-<fatia>-MAP/mapping.sssom.tsv e verdicts.jsonl).

  claims_incomplete       alegação (não ausência) sem semantic_relation, value_domain_relation, transport_fidelity,
                          guard ou proof
  unproven_misjudged      alegação sem prova (proof ausente, ou sem evidência e sem testes) com veredito ≠ UNPROVEN;
                          mais: veredito gravado ≠ o que o árbitro congelado (bo.semantics.obligations.assess) devolve
                          quando ele devolve UNPROVEN (o árbitro diz que falta prova e o gravado diz outra coisa)
  off_table_compositions  veredito de composição (composition_used com 2+ pernas) cuja relação não sai da tabela
                          formal (bo.semantics.composition.semantic_table) e mesmo assim foi aceita, ou cuja linha
                          composta declara relação diferente da tabela
  skos_roundtrip_ok       bo.semantics.skos_roundtrip.file_checks no arquivo do mapeador: todas as conferências verdes
"""
from __future__ import annotations

from pathlib import Path

from . import common as C

FIELDS = ("semantic_relation", "value_domain_relation", "transport_fidelity", "guard", "proof")


def _absence(r: dict) -> bool:
    return r.get("object_id") == "sssom:NoTermFound" or bool(r.get("absence"))


def _no_proof(r: dict) -> bool:
    p = r.get("proof")
    if not isinstance(p, dict) or not p:
        return True
    return not (p.get("evidence") or p.get("tests"))


def check(sssom: Path, verdicts: Path) -> dict:
    from bo.contracts import sssom as CS
    from bo.semantics import skos_roundtrip
    from bo.semantics.composition import semantic_table
    from bo.semantics.obligations import assess
    out = {"sssom": C.portable(sssom), "verdicts": C.portable(verdicts)}
    if not sssom.is_file() or not verdicts.is_file():
        out["error"] = "arquivo do mapeador ausente"
        return out
    _, recs, _ = CS.read_tsv(sssom.read_text(encoding="utf-8"))
    vds = {}
    for v in C.read_jsonl(verdicts):
        vds.setdefault(v.get("claim_id"), []).append(v)
    last = {k: sorted(v, key=lambda x: (x.get("cycle") or 0, x.get("decided_at") or ""))[-1] for k, v in vds.items()}
    claims = [r for r in recs if not _absence(r)]
    incomplete = [r.get("claim_id") for r in claims if any(r.get(f) in (None, "", {}) for f in FIELDS
                                                         if f != "guard") or r.get("guard") is None]
    misjudged, arbiter_diff = [], []
    for r in claims:
        v = (last.get(r.get("claim_id")) or {}).get("verdict")
        if _no_proof(r) and v != "UNPROVEN":
            misjudged.append(r.get("claim_id"))
            continue
        try:
            a = assess(r).verdict
        except Exception:      # noqa: BLE001 (alegação malformada: o árbitro não decide; conta como divergência)
            a = "ERROR"
        if a == "UNPROVEN" and v != "UNPROVEN":
            arbiter_diff.append(r.get("claim_id"))
    table = semantic_table()
    rel = {r.get("claim_id"): r.get("semantic_relation") for r in recs}
    off = []
    for cid, v in last.items():
        legs = v.get("composition_used") or []
        if len(legs) < 2:
            continue
        cur = rel.get(legs[0])
        for leg in legs[1:]:
            cur = (table.get((cur, rel.get(leg))) or {}).get("result") if cur else None
        declared = rel.get(cid)
        if (cur is None and v.get("verdict") == "OK") or (declared is not None and cur is not None and declared != cur):
            off.append(cid)
    try:
        rt = skos_roundtrip.file_checks(sssom)
        rt_ok = all(c["ok"] for c in rt)
        rt_failed = [c["check"] for c in rt if not c["ok"]]
    except Exception as e:     # noqa: BLE001
        rt_ok, rt_failed = False, [f"{type(e).__name__}: {str(e)[:120]}"]
    out.update({"total": len(claims), "absences": len(recs) - len(claims), "n_verdicts": len(last),
                "incomplete": len(incomplete), "unproven_misjudged": len(misjudged) + len(arbiter_diff),
                "no_proof_not_unproven": sorted(x for x in misjudged if x), "arbiter_unproven_but_recorded_other":
                sorted(x for x in arbiter_diff if x), "off_table_compositions": len(off), "off_table": sorted(off),
                "skos_roundtrip_ok": rt_ok, "skos_roundtrip_failed": rt_failed,
                "incomplete_ids": sorted(x for x in incomplete if x)})
    return out
