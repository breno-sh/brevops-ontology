"""Alegação de correspondência (linha C09): relação tipada entre configurações, e a sua inversa.

Campos (proposta em results/SEMANTICS/C09_proposta/): colunas SSSOM (subject_id, predicate_id, object_id,
mapping_justification) + claim_id, claim_version_id, event_id, semantic_relation, value_domain_relation
{relation, orientation}, transport_fidelity, guard, translation_fn, loss_contract, membership_predicate,
fixed_default, projection, bo_group_id, group, proof, evidence_state, basis, anchors, subject_concept,
object_concept, subject_value_type, object_value_type, preserved_observations.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from . import guards as G
from . import transforms as T
from .valuetypes import ValueType
from .vocab import (INVERSE_RELATION, INVERSE_VDR, PREDICATE_RELATION, SKOS_PREDICATE, SUBSET_SIDE)

JSON_FIELDS = ("value_domain_relation", "guard", "translation_fn", "loss_contract", "membership_predicate",
               "fixed_default", "projection", "group", "proof", "anchors", "subject_value_type", "object_value_type",
               "preserved_observations")
CORE = ("subject_id", "predicate_id", "object_id", "mapping_justification")
EXT = ("claim_id", "claim_version_id", "event_id", "semantic_relation", "value_domain_relation",
       "transport_fidelity", "guard", "translation_fn", "loss_contract", "membership_predicate", "fixed_default",
       "projection", "bo_group_id", "group", "proof", "evidence_state", "basis", "anchors", "subject_concept",
       "object_concept", "subject_value_type", "object_value_type", "preserved_observations")
FIELDS = CORE + EXT


def from_row(row: dict) -> dict:
    """Linha SSSOM (valores texto, JSON nas colunas estruturadas) -> registro."""
    out = {}
    for k, v in row.items():
        if v is None or (isinstance(v, str) and v == ""):
            continue
        if k in JSON_FIELDS and isinstance(v, str):
            v = json.loads(v)
        out[k] = v
    return out


def to_row(rec: dict) -> dict:
    out = {}
    for k in FIELDS:
        if k in rec and rec[k] is not None:
            v = rec[k]
            out[k] = json.dumps(v, ensure_ascii=False, sort_keys=True) if k in JSON_FIELDS else str(v)
    return out


@dataclass
class Claim:
    rec: dict

    def __getitem__(self, k):
        return self.rec.get(k)

    @property
    def id(self) -> str:
        return self.rec.get("claim_id", "?")

    @property
    def relation(self) -> str:
        return self.rec.get("semantic_relation")

    @property
    def guard(self) -> dict:
        return self.rec.get("guard") or G.empty()

    @property
    def subject_value_type(self) -> ValueType | None:
        t = self.rec.get("subject_value_type")
        return ValueType.from_dict(t) if t else None

    @property
    def object_value_type(self) -> ValueType | None:
        t = self.rec.get("object_value_type")
        return ValueType.from_dict(t) if t else None

    @property
    def fn(self) -> list[dict]:
        return T.chain_of(self.rec.get("translation_fn"))

    @property
    def losses(self) -> list[dict]:
        return list(self.rec.get("loss_contract") or [])

    def loss(self, kind: str) -> list[dict]:
        return [x for x in self.losses if x.get("kind") == kind]

    @property
    def vdr(self) -> str:
        v = self.rec.get("value_domain_relation")
        return v.get("relation") if isinstance(v, dict) else v

    @property
    def vdr_orientation(self) -> str | None:
        v = self.rec.get("value_domain_relation")
        return v.get("orientation") if isinstance(v, dict) else None


def predicate_for(rel: str) -> str:
    return SKOS_PREDICATE[rel]


def invert(c: Claim) -> Claim:
    """Alegação na direção contrária (objeto -> sujeito). A fidelidade NÃO é copiada: é recalculada pelas regras
    a partir do domínio e da inversa parcial; sem inversa parcial, a direção inversa não transporta."""
    r = copy.deepcopy(c.rec)
    rel = r.get("semantic_relation")
    inv = {
        "claim_id": f"{c.id}~inv",
        "claim_version_id": f"{r.get('claim_version_id', c.id)}~inv",
        "subject_id": r["object_id"], "object_id": r["subject_id"],
        "semantic_relation": INVERSE_RELATION.get(rel, rel),
        "predicate_id": SKOS_PREDICATE.get(INVERSE_RELATION.get(rel, rel), r.get("predicate_id")),
        "mapping_justification": r.get("mapping_justification"),
        "subject_value_type": r.get("object_value_type"), "object_value_type": r.get("subject_value_type"),
        "subject_concept": r.get("object_concept"), "object_concept": r.get("subject_concept"),
        "guard": G.flip(r["guard"]) if r.get("guard") else G.empty(),
        "evidence_state": r.get("evidence_state"),
        "basis": "inverse",
        "inverse_of": c.id,
    }
    for k in ("event_id", "bo_group_id", "anchors"):
        if k in r:
            inv[k] = r[k]
    v = r.get("value_domain_relation")
    if any(x.get("kind") in ("rounding", "saturation") for x in r.get("loss_contract") or []):
        # a relação da ida foi medida contra o envoltório ou a faixa saturada do destino: na volta é recalculada
        v = {"relation": "unknown", "orientation": "subject_to_object"}
    if isinstance(v, dict):
        inv["value_domain_relation"] = {"relation": INVERSE_VDR[v["relation"]], "orientation": v.get("orientation")}
    elif v:
        inv["value_domain_relation"] = {"relation": INVERSE_VDR[v], "orientation": "subject_to_object"}
    mp = r.get("membership_predicate")
    if mp:
        mp = dict(mp)
        mp["subset"] = "object" if mp.get("subset") == "subject" else "subject"
        inv["membership_predicate"] = mp
    ich = T.inverse_chain_safe(r.get("translation_fn")) if r.get("translation_fn") is not None else []
    if r.get("translation_fn") is not None and ich is None:
        inv["translation_fn"] = None
        inv["inverse_missing"] = True
    else:
        inv["translation_fn"] = ich if len(ich) != 1 else ich[0]
    # perdas da ida não valem na volta; sentinelas e contexto sim (mesmo par de tipos, papéis trocados)
    keep = []
    for x in r.get("loss_contract") or []:
        if x.get("kind") == "sentinel":
            keep.append({"kind": "sentinel", "map": {str(b): a for a, b in (x.get("map") or {}).items()
                                                     if b is not None}})
        elif x.get("kind") == "context_dependence":
            keep.append({"kind": "context_dependence",
                         "terms": [G.flip({"all": [{"term": t, "op": "present", "value": True}]})["all"][0]["term"]
                                   for t in x.get("terms", [])]})
        elif x.get("kind") == "semantic":
            y = dict(x)
            if "values" in x:
                vals = []
                for v in x["values"]:
                    try:
                        vals.append(T.apply_chain(T.chain_of(r.get("translation_fn")), v))
                    except Exception:
                        pass
                y["values"] = vals
            keep.append(y)
        elif x.get("kind") == "absence":
            keep.append(dict(x))
    inv["loss_contract"] = keep
    proof = dict(r.get("proof") or {})
    proof = {"type": "inverse_of", "of": c.id, "evidence": proof.get("evidence", []),
             "tests": _inverse_tests(proof.get("tests"), r.get("object_value_type"))}
    inv["proof"] = proof
    if r.get("preserved_observations"):
        inv["preserved_observations"] = r["preserved_observations"]
    inv["transport_fidelity"] = None   # calculada (obligations.derive_fidelity)
    return Claim(inv)


def _inverse_tests(tests, new_subject_value_type):
    """Testes da volta = testes da ida invertidos, só quando a saída da ida é valor admitido do tipo de origem da
    volta (uma saída intermediária antes de arredondar não é valor do destino)."""
    if not tests:
        return []
    try:
        t_in = ValueType.from_dict(new_subject_value_type) if new_subject_value_type else None
    except ValueError:
        t_in = None
    out = []
    for t in tests:
        if "input" in t and "expected" in t and not t.get("lossy") and (t_in is None or t_in.admits(t["expected"])):
            out.append({"input": t["expected"], "expected": t["input"]})
    return out


def check_predicate(c: Claim) -> list[str]:
    """Erros de SKOS-PRED: semantic_relation e predicate_id têm de dizer a mesma coisa."""
    errs = []
    rel, pred = c.relation, c["predicate_id"]
    if rel not in SKOS_PREDICATE:
        errs.append(f"semantic_relation inválida: {rel!r}")
    elif PREDICATE_RELATION.get(pred) != rel:
        errs.append(f"predicate_id {pred} não é {SKOS_PREDICATE[rel]} (semantic_relation={rel})")
    return errs


def expected_subset_side(rel: str) -> str | None:
    return SUBSET_SIDE.get(rel)
