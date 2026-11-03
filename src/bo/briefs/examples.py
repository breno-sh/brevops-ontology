"""Exemplos SINTÉTICOS citados nos briefs, executados contra a implementação de referência do SEMANTICS.

Por que sintéticos e neutros: um exemplo com nomes reais (classe de armazenamento, faixa de portas de regra de
segurança, versionamento de bucket) seria a resposta de uma célula do estudo dentro do brief e contaminaria o
mapeador. Os provedores são pa, pb, pc (example.org); os recursos são 'widget', 'gadget', 'gizmo'; os valores são
rótulos sem significado de nuvem. A evidência é 'fixture:' (sintética) e não afirma nada sobre provedor real.

Cada exemplo declara o veredito que o brief diz que ele tem (OK, UNPROVEN, REFUTED_BY_RULE) e as regras que
o explicam; check() roda bo.semantics.obligations.assess, o transporte nas duas direções, a ida e volta pelo
TSV do C09 (bo.contracts.sssom) e pelo RDF com os axiomas SKOS do W3C, e o validador único do C09/C20.
"""

from __future__ import annotations

import copy
import json

from . import common

DOC = [{"source": "fixture:doc-sintetica", "sentence": "frase sintética de documentação que sustenta a alegação",
        "date": "2026-11-03"}]

# prefixos do C09: sintéticos (example.org) + os do núcleo + sssom (para sssom:NoTermFound)
PREFIXES = {
    "pa": "https://example.org/provider-a/", "pb": "https://example.org/provider-b/",
    "pc": "https://example.org/provider-c/",
    "skos": "http://www.w3.org/2004/02/skos/core#", "semapv": "https://w3id.org/semapv/vocab/",
    "bosx": "https://w3id.org/brevops/sssom-ext#", "bo": "https://w3id.org/brevops/ontology#",
    "concept": "https://w3id.org/brevops/glossary#", "sssom": "https://w3id.org/sssom/",
}
# o que um mapeador real acrescenta ao curie_map (mesma base do GOLD-XPLANE: um IRI por provedor)
PROVIDER_PREFIXES = {
    "aws": "https://w3id.org/brevops/atom/aws/", "google": "https://w3id.org/brevops/atom/google/",
    "azurerm": "https://w3id.org/brevops/atom/azurerm/", "oci": "https://w3id.org/brevops/atom/oci/",
}
MAPPING_SET_ID = "https://example.org/mapping-set/briefs-exemplos"


def T(datatype, **kw):
    d = {"datatype": datatype}
    d.update(kw)
    return d


def DAYS(lo, hi):
    return T("integer", quantity_kind="quantitykind:Time", unit="unit:DAY", range={"min": lo, "max": hi})


def ENUM(*v):
    return T("enum", enum=list(v), quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE")


PROOF_TYPE = {"exact": "normalization", "close": "declared_loss", "broad": "membership", "narrow": "membership",
              "related": "none"}
SKOS = {"exact": "skos:exactMatch", "close": "skos:closeMatch", "broad": "skos:broadMatch",
        "narrow": "skos:narrowMatch", "related": "skos:relatedMatch"}


def claim(cid, s, rel, o, st, ot, fn, vdr, fid, sc, oc, **kw):
    r = {"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
         "subject_id": s, "predicate_id": SKOS[rel], "object_id": o,
         "mapping_justification": "semapv:UnspecifiedMatching", "mapping_tool": common.MODEL_ID,
         "creator_id": "MAP-EXEMPLO", "semantic_relation": rel,
         "value_domain_relation": {"relation": vdr, "orientation": "subject_to_object"},
         "transport_fidelity": fid, "guard": {"all": []}, "translation_fn": fn, "loss_contract": [],
         "subject_value_type": st, "object_value_type": ot, "evidence_state": "DOC_SUPPORTED", "basis": "direct",
         "proof": {"type": PROOF_TYPE[rel], "evidence": copy.deepcopy(DOC), "tests": []},
         "subject_concept": sc, "object_concept": oc}
    tests = kw.pop("tests", None)
    if tests is not None:
        r["proof"]["tests"] = tests
    r.update(kw)
    return r


IDENT = {"name": "identity", "params": {}}


def EM(table):
    return {"name": "enum_map", "params": {"table": table}}


# --------------------------------------------------------------------------------------------- os exemplos
EXACT_SAT = claim(
    "CLM-BRF-EXACT-01", "pa:pa_widget:keep_days", "exact", "pb:pb_gadget:keep_days",
    DAYS(1, 3650), DAYS(1, 365), IDENT, "superset", "declared_loss",
    "concept:item_keep_period", "concept:item_keep_period",
    loss_contract=[{"kind": "saturation", "min": 1, "max": 365, "why": "o destino aceita no máximo 365 dias"}],
    tests=[{"input": 30, "expected": 30}])

BROAD = claim(
    "CLM-BRF-BROAD-01", "pa:pa_widget:grade", "broad", "pb:pb_gadget:level",
    ENUM("g_low", "g_top"), ENUM("l1", "l2", "l3", "l4"), EM({"g_low": "l3", "g_top": "l4"}), "subset", "lossless",
    "concept:item_grade", "concept:item_level",
    tests=[{"input": "g_top", "expected": "l4"}, {"input": "g_low", "expected": "l3"}],
    membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["l3", "l4"]},
                          "tests": {"members": ["l4"], "non_members": ["l1"]}})

NARROW = claim(
    "CLM-BRF-NARROW-01", "pa:pa_widget:min_level", "narrow", "pb:pb_gadget:level_policy",
    ENUM("v1", "v2", "v3", "v4"), ENUM("q3", "q4"), EM({"v3": "q3", "v4": "q4"}), "superset", "partial",
    "concept:item_min_level", "concept:item_min_level_strict",
    tests=[{"input": "v3", "expected": "q3"}],
    membership_predicate={"subset": "object", "expr": {"op": "in", "values": ["v3", "v4"]},
                          "tests": {"members": ["v3"], "non_members": ["v1"]}})

CLOSE = claim(
    "CLM-BRF-CLOSE-01", "pa:pa_widget:speed", "close", "pb:pb_gadget:pace",
    ENUM("fast", "medium", "slow"), ENUM("quick", "calm"), EM({"fast": "quick", "medium": "calm", "slow": "calm"}),
    "equal", "declared_loss", "concept:item_speed", "concept:item_speed",
    loss_contract=[{"kind": "semantic", "values": ["medium", "slow"], "what": "médio e lento caem no mesmo valor"}],
    tests=[{"input": "fast", "expected": "quick"}, {"input": "slow", "expected": "calm"}])

RELATED = claim(
    "CLM-BRF-RELATED-01", "pa:pa_widget:note", "related", "pb:pb_gadget:label",
    T("string", quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE"),
    T("string", quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE"), None, "unknown", "none",
    "concept:item_note", "concept:item_label")
RELATED["proof"] = {"type": "none", "evidence": copy.deepcopy(DOC), "tests": []}

# ausência tipada (NONE): nem um termo relacionado no outro lado; o tipo vai em curation_rule (C09 3.0.1) até a
# emenda proposta em results/BRIEFS/CONTRACT_CHANGE.txt
NONE_ROW = claim(
    "CLM-BRF-NONE-01", "pa:pa_widget:spin_rate", "related", "sssom:NoTermFound",
    T("integer", quantity_kind="quantitykind:Frequency", unit="unit:HZ"), None, None, "unknown", "none",
    "concept:item_spin_rate", "bo:UNGLOSSED",
    curation_rule="bo:NONE_ABSENCE_DEMONSTRATED", evidence_state="STRUCTURALLY_VALID",
    comment="procurados no pacote: atributos do tipo pb_gadget e vizinhos por referência; nenhum realiza a decisão")
del NONE_ROW["object_value_type"]
NONE_ROW["proof"] = {"type": "absence", "tests": [],
                     "evidence": [{"source": "fixture:pacote-sintetico#pb_gadget", "date": "2026-11-03",
                                   "sentence": "nenhum atributo nem subgrafo do pacote realiza a decisão"}]}

# alternativas guardadas do mesmo sujeito: exclusivas porque a interseção das guardas é UNSAT
ALT_STD = claim(
    "CLM-BRF-ALT-STD", "pa:pa_widget:mode", "exact", "pb:pb_gadget:mode",
    ENUM("on", "off"), ENUM("on", "off"), IDENT, "equal", "lossless", "concept:item_mode", "concept:item_mode",
    guard={"all": [{"term": "object.edition", "op": "edition_in", "value": ["standard"]}]},
    alternative_to=["CLM-BRF-ALT-PREM"], exclusivity="ProvenExclusive",
    tests=[{"input": "on", "expected": "on"}])
ALT_PREM = claim(
    "CLM-BRF-ALT-PREM", "pa:pa_widget:mode", "exact", "pb:pb_gizmo:mode",
    ENUM("on", "off"), ENUM("on", "off"), IDENT, "equal", "lossless", "concept:item_mode", "concept:item_mode",
    guard={"all": [{"term": "object.edition", "op": "edition_in", "value": ["premium"]}]},
    alternative_to=["CLM-BRF-ALT-STD"], exclusivity="ProvenExclusive",
    tests=[{"input": "off", "expected": "off"}])

# grupo N:M como regra sobre subgrafo: dois atributos em facetas diferentes do lado a (ligadas por junção)
# para dois atributos de um bloco do lado b; só passos do registro (identity), variáveis nomeadas
def STR():
    return T("string", quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE")


LOOK = T("tuple", components=[{"name": "color", "type": STR()}, {"name": "shade", "type": STR()}],
         quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE")
GROUP = claim(
    "CLM-BRF-GROUP-01", "pa:pa_widget", "exact", "pb:pb_gadget", copy.deepcopy(LOOK), copy.deepcopy(LOOK), None,
    "equal", "lossless", "bo:UNGLOSSED", "bo:UNGLOSSED", bo_group_id="GRP-BRF-01",
    group={"bo_group_id": "GRP-BRF-01", "cardinality": "N:M",
           "variables": [
               {"name": "?color", "side": "subject", "field": "pa:pa_widget.color", "occurrence": "?w"},
               {"name": "?shade", "side": "subject", "field": "pa:pa_widget.finish.shade", "occurrence": "?f"},
               {"name": "?color_b", "side": "object", "field": "pb:pb_gadget.look.color", "occurrence": "?g"},
               {"name": "?shade_b", "side": "object", "field": "pb:pb_gadget.look.shade", "occurrence": "?g"}],
           "occurrence_vars": ["?w", "?f", "?g"],
           "joins": [{"left": "?f", "right": "?w", "via": "facet_of"}],
           "steps": [{"name": "identity", "inputs": {"value": "?color"}, "outputs": {"value": "?color_b"}},
                     {"name": "identity", "inputs": {"value": "?shade"}, "outputs": {"value": "?shade_b"}}]})
GROUP["proof"] = {"type": "group_execution", "evidence": copy.deepcopy(DOC),
                  "tests": [{"input": {"?color": "c1", "?shade": "s2"}, "expected": {"?color_b": "c1", "?shade_b": "s2"}}]}

# projeção por ocorrência: um campo em bloco repetido (chave de ocorrência por identidade, nunca posição) e um
# documento JSON que alimenta duas decisões (duas projeções do mesmo campo, sem sobreposição)
SETTINGS_DOC = '{"alpha": "x1", "beta": 5}'
PROJECTION = claim(
    "CLM-BRF-PROJ-01", "pa:pa_widget:settings_doc", "exact", "pb:pb_gadget:alpha",
    T("tuple", components=[{"name": "alpha", "type": STR()},
                           {"name": "beta", "type": T("integer", quantity_kind="quantitykind:Count", unit="unit:NUM",
                                                      range={"min": 1, "max": 100})}],
      quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE"),
    STR(), {"name": "json_get", "params": {"key": "alpha"}},
    "unknown", "partial", "concept:item_alpha", "concept:item_alpha",
    tests=[{"input": {"alpha": "x1", "beta": 5}, "expected": "x1"}],
    projection=[
        {"projection_id": "PRJ-BRF-alpha", "field": "pa:pa_widget.settings_doc", "occurrence": {"scope": "resource"},
         "extractor": {"name": "json_get", "params": {"key": "alpha"}}, "concept": "concept:item_alpha",
         "type": T("string"), "tests": [{"input": SETTINGS_DOC, "expected": "x1"}]},
        {"projection_id": "PRJ-BRF-beta", "field": "pa:pa_widget.settings_doc", "occurrence": {"scope": "resource"},
         "extractor": {"name": "json_get", "params": {"key": "beta"}}, "concept": "concept:item_beta",
         "type": T("integer", quantity_kind="quantitykind:Count", unit="unit:NUM", range={"min": 1, "max": 100}),
         "tests": [{"input": SETTINGS_DOC, "expected": 5}]},
        {"projection_id": "PRJ-BRF-part", "field": "pa:pa_widget.part.size",
         "occurrence": {"scope": "block", "key_fields": ["name"]},
         "extractor": {"name": "identity"}, "concept": "concept:part_size",
         "type": T("integer", quantity_kind="quantitykind:Count", unit="unit:NUM", range={"min": 1, "max": 64}),
         "tests": [{"input": 4, "expected": 4}]}])

# ------------------------------------------------------------------------- exemplos que TÊM de ser recusados
UNPROVEN_NO_PRED = copy.deepcopy(BROAD)
UNPROVEN_NO_PRED.update(claim_id="CLM-BRF-BAD-01", claim_version_id="CLM-BRF-BAD-01@1", event_id="EV-CLM-BRF-BAD-01-1")
del UNPROVEN_NO_PRED["membership_predicate"]

REFUTED_V2 = copy.deepcopy(BROAD)        # leitura invertida da v2: broad com o objeto como subconjunto
REFUTED_V2.update(claim_id="CLM-BRF-BAD-02", claim_version_id="CLM-BRF-BAD-02@1", event_id="EV-CLM-BRF-BAD-02-1")
REFUTED_V2["membership_predicate"]["subset"] = "object"

UNPROVEN_ANCHOR = copy.deepcopy(EXACT_SAT)   # "mesmo conceito no glossário" como prova: não é
UNPROVEN_ANCHOR.update(claim_id="CLM-BRF-BAD-03", claim_version_id="CLM-BRF-BAD-03@1",
                       event_id="EV-CLM-BRF-BAD-03-1", basis="shared_concept",
                       anchors=[{"claim_id": "ANC-BRF-pa-01", "evidence_state": "STRUCTURALLY_VALID"},
                                {"claim_id": "ANC-BRF-pb-01", "evidence_state": "STRUCTURALLY_VALID"}])

UNPROVEN_READBACK = copy.deepcopy(EXACT_SAT)  # leitura de volta não prova significado
UNPROVEN_READBACK.update(claim_id="CLM-BRF-BAD-04", claim_version_id="CLM-BRF-BAD-04@1",
                         event_id="EV-CLM-BRF-BAD-04-1", evidence_state="PERSISTENCE_VERIFIED")
UNPROVEN_READBACK["proof"]["evidence"] = []

# (chave, registro, veredito esperado, regras esperadas, frase do brief)
CASES = [
    ("EXACT_SAT", EXACT_SAT, "OK", [], "exact de significado, domínio superset, perda declarada (saturação)"),
    ("BROAD", BROAD, "OK", [], "broad: b é o mais amplo; predicado de pertença ao lado a (sujeito)"),
    ("NARROW", NARROW, "OK", [], "narrow: b é o mais estreito; predicado de pertença ao lado b (objeto)"),
    ("CLOSE", CLOSE, "OK", [], "close: perda semântica declarada; sem inversa parcial"),
    ("RELATED", RELATED, "OK", [], "related: não transporta"),
    ("NONE_ROW", NONE_ROW, "OK", [], "ausência tipada: nem termo relacionado; não transporta"),
    ("ALT_STD", ALT_STD, "OK", [], "alternativa guardada (edição standard)"),
    ("ALT_PREM", ALT_PREM, "OK", [], "alternativa guardada (edição premium)"),
    ("PROJECTION", PROJECTION, "OK", [], "projeções por ocorrência sobre um documento e um bloco repetido"),
    ("UNPROVEN_NO_PRED", UNPROVEN_NO_PRED, "UNPROVEN", ["BN-PRED"], "broad sem predicado de pertença"),
    ("REFUTED_V2", REFUTED_V2, "REFUTED_BY_RULE", ["SKOS-ORIENT"], "leitura invertida da v2"),
    ("UNPROVEN_ANCHOR", UNPROVEN_ANCHOR, "UNPROVEN", ["ANCHOR-NOT-PROOF"], "mesmo conceito sem âncoras DOC_SUPPORTED"),
    ("UNPROVEN_READBACK", UNPROVEN_READBACK, "UNPROVEN", ["EVIDENCE"], "leitura de volta sem citação"),
]
GOOD_ROWS = [EXACT_SAT, BROAD, NARROW, CLOSE, RELATED, NONE_ROW, ALT_STD, ALT_PREM, GROUP, PROJECTION]

# ------------------------------------------------------------------------------------------- C20 (glossário)
GLOSSARY_CONCEPT = {
    "concept_id": "concept:item_keep_period", "label": "período de guarda do item",
    "definition": "intervalo de tempo durante o qual um item é mantido antes de ser descartado",
    "domain": "OPS", "quantity_kind": "quantitykind:Time", "unit": "unit:DAY", "status": "active",
    "evidence_state": "STRUCTURALLY_VALID"}
GLOSSARY_CONCEPT_NA = {
    "concept_id": "concept:item_grade", "label": "grau do item",
    "definition": "classificação ordinal de um item por nível de serviço",
    "domain": "OPS", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE", "status": "active",
    "evidence_state": "UNRESOLVED"}


def anchor(cid, atom, n, state="STRUCTURALLY_VALID", method="parser", level="published", **kw):
    r = {"claim_id": cid, "claim_version_id": f"{cid}@{n}", "event_id": f"EV-{cid}-{n}",
         "concept_id": "concept:item_keep_period", "atom_id": atom,
         "sentence": "frase sintética: dias durante os quais o item é mantido",
         "context": "seção de argumentos do tipo sintético",
         "counterexample_search": {"query": "keep days retain hold period", "found": False,
                                   "result": "nenhum uso com outro significado no pacote"},
         "extraction_method": method, "evidence_level": level, "evidence_state": state,
         "recorded_at": "2026-11-03T08:00:00-03:00",
         "source": {"repo": "example-org/provider-a-docs", "tag": "v1.0.0", "file": "docs/widget.md", "line": 12,
                    "sentence": "frase sintética de documentação que sustenta o fato"}}
    r.update(kw)
    return r


ANCHOR_PA = anchor("ANC-BRF-pa-01", "pa:pa_widget:keep_days", 1)
ANCHOR_PB = anchor("ANC-BRF-pb-01", "pb:pb_gadget:keep_days", 1, method="model", level="interpreted",
                   model_id=common.MODEL_ID,
                   source={"repo": "example-org/provider-b-docs", "tag": "v2.0.0", "file": "docs/gadget.md",
                           "line": 40, "sentence": "frase sintética de documentação que sustenta o fato"})
ANCHOR_PA_AUDITED = anchor("ANC-BRF-pa-01", "pa:pa_widget:keep_days", 2, state="DOC_SUPPORTED",
                           event_id="EV-AUDIT-BRF-0001", supersedes="ANC-BRF-pa-01@1",
                           recorded_at="2026-11-03T09:00:00-03:00")
AUDIT_PASS = {"audit_id": "GA-BRF-0001", "claim_id": "ANC-BRF-pa-01", "claim_version_id": "ANC-BRF-pa-01@1",
              "event_id": "EV-AUDIT-BRF-0001", "check": "evidence_support", "result": "pass",
              "evidence_state_before": "STRUCTURALLY_VALID", "evidence_state_after": "DOC_SUPPORTED",
              "auditor": "GLOSSARY-AUDIT", "at": "2026-11-03T09:00:00-03:00",
              "note": "sentença publicada na tag fixada sustenta o conceito; contraexemplo procurado e não achado"}
AUDIT_INDIRECT = {"audit_id": "GA-BRF-0002", "claim_id": "ANC-BRF-pb-01", "claim_version_id": "ANC-BRF-pb-01@1",
                  "event_id": "EV-ANC-BRF-pb-01-1", "check": "indirect_anchor", "result": "unresolved",
                  "evidence_state_before": "STRUCTURALLY_VALID", "evidence_state_after": "UNRESOLVED",
                  "auditor": "GLOSSARY-AUDIT", "at": "2026-11-03T09:05:00-03:00",
                  "note": "âncora interpretada por modelo: a alegação pa_widget:keep_days ↔ pb_gadget:keep_days "
                          "que ela implica fica como hipótese de alinhamento até haver sentença publicada"}

# registro de decisão do glossário (decisions.jsonl): formato provisório até a emenda do C20 (CONTRACT_CHANGE)
DECISION_BROADER = {"schema": "bo.glossary_decision/1", "decision_id": "GD-BRF-0001", "kind": "broader",
                    "concept_id": "concept:item_min_level_strict", "related_concept": "concept:item_min_level",
                    "reason": "todo nível mínimo estrito é um nível mínimo (extensão contida)",
                    "evidence": [{"source": "fixture:doc-sintetica", "sentence": "frase sintética", "date": "2026-11-03"}],
                    "author": "GLOSSARY-EXEMPLO", "recorded_at": "2026-11-03T08:00:00-03:00"}
DECISION_SAME_KIND = {"schema": "bo.glossary_decision/1", "decision_id": "GD-BRF-0002",
                      "kind": "same_kind_distinct", "concept_id": "concept:item_keep_period",
                      "related_concept": "concept:item_wait_before_check",
                      "reason": "mesma grandeza (tempo), significados distintos: guardar depois de criar × esperar "
                                "antes de medir",
                      "evidence": [], "author": "GLOSSARY-EXEMPLO", "recorded_at": "2026-11-03T08:00:00-03:00"}
DECISION_VALUE_TYPE = {"schema": "bo.glossary_decision/1", "decision_id": "GD-BRF-0003", "kind": "value_type",
                       "concept_id": "concept:item_grade",
                       "value": {"datatype": "enum", "enum_semantics": "ordinal: g_low < g_top"},
                       "reason": "tipo de valor e semântica do enum do conceito", "evidence": [],
                       "author": "GLOSSARY-EXEMPLO", "recorded_at": "2026-11-03T08:00:00-03:00"}
DECISIONS = [DECISION_BROADER, DECISION_SAME_KIND, DECISION_VALUE_TYPE]


# -------------------------------------------------------------------------------------------- execução
def assess(rec: dict) -> dict:
    from bo.semantics.obligations import assess as _assess
    a = _assess(copy.deepcopy(rec))
    return {"verdict": a.verdict, "rules": a.rules}


def transports(rec: dict, values_fwd, values_bwd) -> dict:
    from bo.semantics.transport import transport
    out = {"forward": [], "inverse": []}
    for v in values_fwd:
        o = transport(copy.deepcopy(rec), v)
        out["forward"].append({"in": v, "result": o["result"], "out": o.get("value"), "code": o.get("code")})
    for v in values_bwd:
        o = transport(copy.deepcopy(rec), v, direction="inverse")
        out["inverse"].append({"in": v, "result": o["result"], "out": o.get("value"), "code": o.get("code")})
    return out


def inverse_of(rec: dict) -> dict:
    from bo.semantics.claims import Claim, invert
    return invert(Claim(copy.deepcopy(rec)))


def skos_closure_check() -> dict:
    """RDF com os axiomas SKOS do W3C (fecho OWL 2 RL): em 'a broadMatch b', b é o mais amplo."""
    from bo.semantics import owl_theory as O
    a, b = BROAD["subject_id"], BROAD["object_id"]
    g = O.closure([BROAD])
    return {"a_broader_b": O.has(g, a, "skos:broader", b),
            "b_narrowMatch_a": O.has(g, b, "skos:narrowMatch", a),
            "not_b_broadMatch_a": not O.has(g, b, "skos:broadMatch", a),
            "not_a_narrowMatch_b": not O.has(g, a, "skos:narrowMatch", b)}


def tsv_roundtrip() -> dict:
    """Escreve os exemplos bons pelo bo.contracts.sssom (o caminho oficial do C09) e lê de volta."""
    from bo.contracts import sssom as CS
    text = CS.write_tsv(copy.deepcopy(GOOD_ROWS), MAPPING_SET_ID, PREFIXES)
    meta, back, cols = CS.read_tsv(text)

    def norm(r):   # null e ausente são a mesma coisa no TSV (célula vazia)
        return json.loads(json.dumps({k: v for k, v in r.items() if v is not None}, sort_keys=True))
    same = [norm(x) for x in back] == [norm(x) for x in GOOD_ROWS]
    lost = sorted({k for r in GOOD_ROWS for k in r} - set(cols))
    return {"text": text, "equal": same, "columns": cols, "lost_columns": lost,
            "prefixes_declared": sorted(meta.get("curie_map", {}))}


def hub_check() -> dict:
    """átomo→conceito←átomo (F4): a correspondência implícita das duas âncoras passa pela tabela de composição."""
    from bo.semantics.composition import hub_claim
    anc_a = claim("ANC-BRF-pa-01", "pa:pa_widget:keep_days", "exact", "concept:item_keep_period",
                  DAYS(1, 3650), DAYS(0, 3650), IDENT, "subset", "lossless", "concept:item_keep_period",
                  "concept:item_keep_period", tests=[{"input": 7, "expected": 7}])
    anc_b = claim("ANC-BRF-pb-01", "pb:pb_gadget:keep_days", "exact", "concept:item_keep_period",
                  DAYS(1, 365), DAYS(0, 3650), IDENT, "subset", "lossless", "concept:item_keep_period",
                  "concept:item_keep_period", tests=[{"input": 7, "expected": 7}])
    weak_a = copy.deepcopy(anc_a)
    weak_a["evidence_state"] = "STRUCTURALLY_VALID"
    weak_a["proof"]["evidence"] = []
    ok = hub_claim(anc_a, anc_b)
    weak = hub_claim(weak_a, anc_b)
    return {"supported": {"outcome": ok.get("outcome"), "relation": (ok.get("claim") or {}).get("semantic_relation")},
            "weak": {"outcome": weak.get("outcome"), "verdict": weak.get("verdict"),
                     "relation": (weak.get("claim") or {}).get("semantic_relation")}}


def group_check(rec: dict) -> dict:
    """O grupo é julgado como regra sobre subgrafo (G-VARS, G-ARITY, G-OCC) e executado nos testes da prova."""
    from bo.semantics import projections as P
    g = P.check_group(copy.deepcopy(rec["group"]))
    runs = []
    for t in rec["proof"]["tests"]:
        inst = {}
        for v in rec["group"]["variables"]:
            if v["side"] == "subject" and v["name"] in t["input"]:
                inst.setdefault(v["occurrence"], {})[v["field"]] = t["input"][v["name"]]
        got = P.apply_group(copy.deepcopy(rec["group"]), inst)
        runs.append({"input": t["input"], "expected": t["expected"], "got": got, "ok": got == t["expected"]})
    return {"verdict": g["verdict"], "rules": sorted({f.get("rule") for f in g["failures"]}), "runs": runs}


def projection_check(rec: dict) -> dict:
    from bo.semantics import projections as P
    r = P.check_projections(copy.deepcopy(rec["projection"]))
    return {"verdict": r["verdict"], "n": r.get("n"), "rules": sorted({f.get("rule") for f in r["failures"]})}


def check() -> dict:
    """Roda todos os exemplos e devolve o relatório (sem efeito colateral)."""
    res = {"cases": [], "problems": []}
    res["group"] = group_check(GROUP)
    if res["group"]["verdict"] != "OK" or not all(x["ok"] for x in res["group"]["runs"]):
        res["problems"].append(f"grupo fora do esperado: {res['group']}")
    res["projections"] = projection_check(PROJECTION)
    if res["projections"]["verdict"] != "OK":
        res["problems"].append(f"projeções fora do esperado: {res['projections']}")
    for key, rec, want, rules, _ in CASES:
        got = assess(rec)
        ok = got["verdict"] == want and all(r in got["rules"] for r in rules)
        res["cases"].append({"key": key, "claim_id": rec["claim_id"], "expected": want, "got": got, "ok": ok})
        if not ok:
            res["problems"].append(f"{key}: esperado {want} {rules}, obtido {got}")
    res["broad_transport"] = transports(BROAD, ["g_low", "g_top"], ["l1", "l2", "l3", "l4"])
    fw, bw = res["broad_transport"]["forward"], res["broad_transport"]["inverse"]
    if not (all(x["result"] == "carried" for x in fw)
            and [x["result"] for x in bw] == ["blocked", "blocked", "carried", "carried"]
            and all(x["code"] == "OUT_OF_SUBSET" for x in bw if x["result"] != "carried")):
        res["problems"].append(f"transporte do broad fora do esperado: {res['broad_transport']}")
    rt = [transports(BROAD, [], [x["out"]])["inverse"][0]["out"] for x in fw]
    res["broad_roundtrip_values"] = {"A": ["g_low", "g_top"], "A_B_A": rt}
    if rt != ["g_low", "g_top"]:
        res["problems"].append(f"ida e volta A→B→A não devolveu os valores: {rt}")
    res["narrow_transport"] = transports(NARROW, ["v1", "v3", "v4"], ["q3", "q4"])
    if [x["result"] for x in res["narrow_transport"]["forward"]] != ["blocked", "carried", "carried"]:
        res["problems"].append(f"transporte do narrow fora do esperado: {res['narrow_transport']}")
    res["exact_transport"] = transports(EXACT_SAT, [30, 400], [200])
    if [x["out"] for x in res["exact_transport"]["forward"]] != [30, 365]:
        res["problems"].append(f"saturação do exact fora do esperado: {res['exact_transport']}")
    res["close_inverse"] = transports(CLOSE, ["medium"], ["calm"])
    if res["close_inverse"]["inverse"][0]["code"] != "UNPROVEN":
        res["problems"].append(f"close sem inversa parcial transportou na volta: {res['close_inverse']}")
    res["related_transport"] = transports(RELATED, ["x"], [])
    if res["related_transport"]["forward"][0]["code"] != "RELATED_ONLY":
        res["problems"].append("related transportou")
    inv = inverse_of(BROAD)
    res["broad_inverse"] = {"subject_id": inv["subject_id"], "predicate_id": inv["predicate_id"],
                            "object_id": inv["object_id"], "semantic_relation": inv["semantic_relation"]}
    if (inv["predicate_id"], inv["subject_id"]) != ("skos:narrowMatch", BROAD["object_id"]):
        res["problems"].append(f"inversa do broad não é narrowMatch: {res['broad_inverse']}")
    res["skos_closure"] = skos_closure_check()
    if not all(res["skos_closure"].values()):
        res["problems"].append(f"fecho SKOS fora do esperado: {res['skos_closure']}")
    rt = tsv_roundtrip()
    res["tsv_roundtrip"] = {k: v for k, v in rt.items() if k != "text"}
    if not rt["equal"] or rt["lost_columns"]:
        res["problems"].append(f"ida e volta pelo TSV do C09 perdeu algo: {res['tsv_roundtrip']}")
    res["hub"] = hub_check()
    if res["hub"]["supported"]["relation"] != "exact" or res["hub"]["weak"]["outcome"] == "COMPOSED" \
            and res["hub"]["weak"].get("verdict") not in (None, "UNPROVEN"):
        res["problems"].append(f"composição pelo conceito fora do esperado: {res['hub']}")
    return res


def validate_files(out_dir) -> dict:
    """Grava os exemplos nos formatos dos contratos e passa cada arquivo no validador único."""
    import subprocess
    import sys
    from pathlib import Path
    from bo.contracts import sssom as CS
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "correspondences": out / "mapper_examples.sssom.tsv",
        "correspondences_jsonl": out / "nonehunt_examples.jsonl",
        "glossary": out / "glossary.jsonl",
        "claims": out / "claims.jsonl",
        "glossary_audit": out / "glossary_audit.jsonl",
    }
    files["correspondences"].write_text(CS.write_tsv(copy.deepcopy(GOOD_ROWS), MAPPING_SET_ID, PREFIXES),
                                        encoding="utf-8")
    dispute = dispute_example()
    files["correspondences_jsonl"].write_text(common.canon(dispute) + "\n", encoding="utf-8")
    files["glossary"].write_text("".join(common.canon(x) + "\n" for x in (GLOSSARY_CONCEPT, GLOSSARY_CONCEPT_NA)),
                                 encoding="utf-8")
    files["claims"].write_text("".join(common.canon(x) + "\n" for x in (ANCHOR_PA, ANCHOR_PB, ANCHOR_PA_AUDITED)),
                               encoding="utf-8")
    files["glossary_audit"].write_text("".join(common.canon(x) + "\n" for x in (AUDIT_PASS, AUDIT_INDIRECT)),
                                       encoding="utf-8")
    (out / "decisions.jsonl").write_text("".join(common.canon(x) + "\n" for x in DECISIONS), encoding="utf-8")
    report = {}
    for kind, p in files.items():
        cp = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", kind, str(p)],
                            capture_output=True, text=True)
        report[p.name] = {"kind": kind, "rc": cp.returncode,
                          "last": (cp.stdout.strip().splitlines() or [""])[-1][-200:]}
    return report


def dispute_example() -> dict:
    """Descoberta do caçador: contesta a ausência CLM-BRF-NONE-01 com um alvo que existe no schema fixado."""
    d = claim("DSP-BRF-pb-0001", "pa:pa_widget:spin_rate", "exact", "pb:pb_gadget:turn_rate",
              T("integer", quantity_kind="quantitykind:Frequency", unit="unit:HZ", range={"min": 1, "max": 100}),
              T("integer", quantity_kind="quantitykind:Frequency", unit="unit:HZ", range={"min": 1, "max": 1000}),
              IDENT, "subset", "lossless", "concept:item_spin_rate", "concept:item_spin_rate",
              tests=[{"input": 10, "expected": 10}], creator_id="NONEHUNT-EXEMPLO",
              see_also="CLM-BRF-NONE-01",
              comment="descoberta adversarial: contesta a ausência CLM-BRF-NONE-01; alvo existe no schema fixado")
    return d
