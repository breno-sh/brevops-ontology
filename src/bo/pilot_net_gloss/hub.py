"""Caminhos átomo→conceito←átomo entre provedores (achado F4): cada um é uma alegação composta pelo bo.semantics.

A âncora C20 (átomo→conceito) é levantada para a forma de alegação do bo.semantics: exact, identidade, tipo do
átomo vindo do value_space (UNITS) e tipo do conceito vindo da decisão value_type do glossário. O caminho é
compose(âncora_a, inversa(âncora_b)) pela bo.semantics.composition.hub_claim (K-HUB), e a mesma correspondência
vista como alegação de base shared_concept passa pelas obrigações (ANCHOR-NOT-PROOF). Nada aqui decide veredito:
o código congelado do bo.semantics decide; aqui só se monta a entrada.
"""

from __future__ import annotations

import copy
import itertools

from bo.semantics import obligations as OB
from bo.semantics.claims import Claim
from bo.semantics.composition import hub_claim
from bo.semantics.valuetypes import ValueType

NA = "NOT_APPLICABLE"


def atom_type(vs: dict | None) -> dict | None:
    """Tipo C05 do átomo → tipo do bo.semantics (só o que o value_space afirma)."""
    if not vs:
        return None
    dt = vs.get("datatype") or {}
    if dt.get("kind") != "scalar":
        return None
    t = {"datatype": dt.get("scalar"), "quantity_kind": vs.get("quantity_kind", NA), "unit": vs.get("unit_qudt", NA)}
    if vs.get("enum"):
        t["enum"] = list(vs["enum"])
    if vs.get("range"):
        t["range"] = dict(vs["range"])
    return t


def identity_tests(t: dict | None) -> list[dict]:
    """Teste da normalização identidade: um valor do domínio declarado do átomo volta igual. Só exercita a função
    (a prova de significado é a citação); sem domínio declarado, sem teste."""
    if not t:
        return []
    if t.get("enum"):
        v = sorted(t["enum"])[0]
    elif t.get("range") and t["range"].get("min") is not None:
        v = t["range"]["min"]
    elif t["datatype"] == "boolean":
        v = True
    elif t["datatype"] == "string":
        v = "valor-sintetico"      # amostra sintética: só exercita a identidade num domínio de texto livre
    else:
        return []
    return [{"input": v, "expected": v}]


def concept_type(concept: dict, decisions: list[dict]) -> dict | None:
    for d in decisions:
        if d["kind"] == "value_type" and d["concept_id"] == concept["concept_id"]:
            t = {"datatype": d["value"]["datatype"], "quantity_kind": concept["quantity_kind"],
                 "unit": concept.get("unit", "UNKNOWN")}
            return t
    return None


def ref_of(a: dict) -> str:
    return a.get("atom_id") or a.get("block_id") or a.get("type_id")


def lift(anchor: dict, concept: dict, decisions: list[dict], vs: dict | None, state: str | None = None) -> dict:
    """Âncora C20 → alegação átomo→conceito no formato do bo.semantics (sem inventar prova além da citação).
    Âncora de bloco ou tipo (C20 3.2.0): o lado sujeito é o bloco/tipo e o seu domínio é o valor implicado."""
    if anchor.get("implication"):
        st = {"datatype": "enum", "enum": [anchor["implication"]["value"]], "quantity_kind": NA, "unit": NA}
    else:
        st = atom_type(vs)
    ot = concept_type(concept, decisions)
    src = anchor.get("source") or {}
    er = anchor.get("evidence_ref") or {}
    if src:
        ev = [{"source": f"{src.get('repo')}/{src.get('file')}:{src.get('line')}@{src.get('tag')}",
               "sentence": anchor.get("sentence"), "date": anchor["recorded_at"][:10]}]
    elif er and anchor.get("sentence"):     # fato do guia oficial citado pelo C25 (sem repo/linha)
        ev = [{"source": f"{er['contract']}:{er['id']}", "sentence": anchor["sentence"],
               "date": anchor["recorded_at"][:10]}]
    else:
        ev = []
    c = {"claim_id": anchor["claim_id"], "claim_version_id": anchor["claim_version_id"],
         "event_id": anchor["event_id"], "subject_id": ref_of(anchor), "predicate_id": "skos:exactMatch",
         "object_id": anchor["concept_id"], "mapping_justification": "semapv:ManualMappingCuration",
         "semantic_relation": "exact", "guard": {"all": []}, "translation_fn": {"name": "identity", "params": {}},
         "loss_contract": [], "subject_value_type": st, "object_value_type": ot,
         "evidence_state": state or anchor["evidence_state"], "basis": "direct",
         "proof": {"type": "normalization", "evidence": ev, "tests": identity_tests(st)},
         "subject_concept": anchor["concept_id"], "object_concept": anchor["concept_id"]}
    vdr = "unknown"
    if st and ot:
        try:
            vdr = OB.computed_vdr(Claim(c), ValueType.from_dict(st), ValueType.from_dict(ot))
        except Exception:  # tipo mal formado: o árbitro reprova adiante (TYPE-WF); aqui fica unknown
            vdr = "unknown"
    c["value_domain_relation"] = {"relation": vdr, "orientation": "subject_to_object"}
    c["transport_fidelity"] = OB.derive_fidelity("exact", vdr, [], False, False)
    return c


def shared_concept_claim(a: dict, b: dict, la: dict, lb: dict) -> dict:
    """A correspondência implícita a↔b vista como alegação de base shared_concept (ANCHOR-NOT-PROOF)."""
    c = copy.deepcopy(la)
    cid = f"HUB-{a['claim_id']}-{b['claim_id']}"
    c.update({"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
              "object_id": ref_of(b), "object_value_type": lb["subject_value_type"], "basis": "shared_concept",
              "anchors": [{"claim_id": a["claim_id"], "evidence_state": a["evidence_state"]},
                          {"claim_id": b["claim_id"], "evidence_state": b["evidence_state"]}],
              "evidence_state": min((a["evidence_state"], b["evidence_state"]), key=OB_RANK.get)})
    vdr = "unknown"
    if c["subject_value_type"] and c["object_value_type"]:
        try:
            vdr = OB.computed_vdr(Claim(c), ValueType.from_dict(c["subject_value_type"]),
                                  ValueType.from_dict(c["object_value_type"]))
        except Exception:
            vdr = "unknown"
    c["value_domain_relation"] = {"relation": vdr, "orientation": "subject_to_object"}
    c["transport_fidelity"] = OB.derive_fidelity("exact", vdr, [], False, False)
    return c


OB_RANK = {"UNRESOLVED": 0, "STRUCTURALLY_VALID": 1, "DOC_SUPPORTED": 2, "PERSISTENCE_VERIFIED": 3,
           "OBSERVATION_TESTED": 4}


def provider_of(atom_id: str) -> str:
    return atom_id.split(":", 1)[0]


def paths(claims: list[dict]) -> list[tuple[dict, dict]]:
    """Todo par de âncoras de provedores diferentes no mesmo conceito, em ordem estável (sujeito antes no
    catálogo de provedores)."""
    order = {"aws": 0, "google": 1, "azurerm": 2, "oci": 3}
    by: dict[str, list[dict]] = {}
    for c in claims:
        by.setdefault(c["concept_id"], []).append(c)
    out = []
    for cid in sorted(by):
        xs = sorted(by[cid], key=lambda x: (order.get(provider_of(ref_of(x)), 9), x["claim_id"]))
        for a, b in itertools.combinations(xs, 2):
            if provider_of(ref_of(a)) != provider_of(ref_of(b)):
                out.append((a, b))
    return out


def evaluate(claims, concepts, decisions, value_space, promote: str | None = None) -> list[dict]:
    """Uma linha por caminho: desfecho da composição (hub_claim) e veredito da alegação shared_concept.
    promote: só para o controle positivo em memória (nunca gravado): trata as âncoras como se tivessem esse estado."""
    cmap = {c["concept_id"]: c for c in concepts}
    rows = []
    for a, b in paths(claims):
        if promote:
            a, b = dict(a, evidence_state=promote), dict(b, evidence_state=promote)
        la = lift(a, cmap[a["concept_id"]], decisions, value_space.get(ref_of(a)))
        lb = lift(b, cmap[b["concept_id"]], decisions, value_space.get(ref_of(b)))
        r = hub_claim(la, lb)
        sc = shared_concept_claim(a, b, la, lb)
        asmt = OB.assess(sc)
        rows.append({
            "path_id": f"HUB-{a['claim_id']}-{b['claim_id']}", "concept_id": a["concept_id"],
            "subject_atom": ref_of(a), "object_atom": ref_of(b),
            "subject_kind": a.get("anchor_kind", "atom"), "object_kind": b.get("anchor_kind", "atom"),
            "types_known": bool(la["subject_value_type"] and lb["subject_value_type"]),
            "subject_anchor": a["claim_version_id"], "object_anchor": b["claim_version_id"],
            "subject_anchor_state": a["evidence_state"], "object_anchor_state": b["evidence_state"],
            "hub_outcome": r["outcome"], "hub_rule": r.get("rule"),
            "hub_relation": (r.get("claim") or {}).get("semantic_relation") if r["outcome"] == "COMPOSED" else None,
            "shared_concept_verdict": asmt.verdict,
            "shared_concept_failed_rules": asmt.rules,
            "status": "hipótese de alinhamento (não é correspondência; não transporta sem DOC_SUPPORTED nas duas âncoras)",
        })
    return rows

