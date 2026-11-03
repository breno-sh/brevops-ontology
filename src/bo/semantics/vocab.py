"""Vocabulários fechados do SEMANTICS e alinhamento com o ONTPAT (P7) e com os códigos do C23."""

from __future__ import annotations

SKOS = "http://www.w3.org/2004/02/skos/core#"
SEMAPV = "https://w3id.org/semapv/vocab/"
BOSX = "https://w3id.org/brevops/sssom-ext#"     # slots de extensão do C09 (não é termo da ontologia)
BO = "https://w3id.org/brevops/ontology#"         # termos do ONTPAT (só citados, nunca criados aqui)

# --- relação semântica (significado), com o predicado SKOS na direção correta -------------------------
SEMANTIC_RELATIONS = ("exact", "close", "broad", "narrow", "related")
SKOS_PREDICATE = {
    "exact": "skos:exactMatch",
    "close": "skos:closeMatch",
    "broad": "skos:broadMatch",    # a broadMatch b: b é o MAIS AMPLO (a ⊂ b)
    "narrow": "skos:narrowMatch",  # a narrowMatch b: b é o MAIS ESTREITO (b ⊂ a)
    "related": "skos:relatedMatch",
}
PREDICATE_RELATION = {v: k for k, v in SKOS_PREDICATE.items()}
INVERSE_RELATION = {"exact": "exact", "close": "close", "broad": "narrow", "narrow": "broad", "related": "related"}
# lado que é o subconjunto, por relação (o predicado de pertença testa a pertença a ESTE lado)
SUBSET_SIDE = {"broad": "subject", "narrow": "object"}
TRANSPORTING = ("exact", "close", "broad", "narrow")

# --- relação entre domínios de valores (orientação: domínio do sujeito R domínio do objeto) -------------
# Cinco relações conjuntamente exaustivas e disjuntas duas a duas (as do RCC5), mais 'unknown' (= disjunção das cinco).
VDR_JEPD = ("equal", "subset", "superset", "overlap", "disjoint")
VALUE_DOMAIN_RELATIONS = VDR_JEPD + ("unknown",)
INVERSE_VDR = {"equal": "equal", "subset": "superset", "superset": "subset", "overlap": "overlap",
               "disjoint": "disjoint", "unknown": "unknown"}
VDR_ORIENTATION = "subject_to_object"

# --- fidelidade de transporte (na direção sujeito -> objeto) ------------------------------------------
FIDELITIES = ("lossless", "declared_loss", "partial", "none")
FIDELITY_RANK = {f: i for i, f in enumerate(FIDELITIES)}   # maior = pior
ONTPAT_FIDELITY = {"lossless": "bo:Lossless", "declared_loss": "bo:DeclaredLoss",
                   "partial": "bo:PartialTransport", "none": "bo:NoTransport"}

# --- escada de evidência (PLANO §9.2; C20) -------------------------------------------------------------
EVIDENCE_STATES = ("UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED")
EVIDENCE_RANK = {s: i for i, s in enumerate(EVIDENCE_STATES)}
MEANING_SUPPORT = ("DOC_SUPPORTED", "OBSERVATION_TESTED", "PERSISTENCE_VERIFIED")
ONTPAT_EVIDENCE = {"STRUCTURALLY_VALID": "bo:StructurallyValid", "DOC_SUPPORTED": "bo:DocSupported",
                   "PERSISTENCE_VERIFIED": "bo:PersistenceVerified", "OBSERVATION_TESTED": "bo:ObservationTested",
                   "UNRESOLVED": "bo:Unresolved"}

# --- vereditos (C21) e resultado de composição -----------------------------------------------------------
VERDICTS = ("OK", "REFUTED_BY_RULE", "UNPROVEN", "CONTESTED", "AMBIGUOUS")
COMPOSITION_OUTCOMES = ("COMPOSED", "EMPTY", "UNPROVEN", "NOT_COMPOSABLE")

# --- códigos de bloqueio de transporte (C23) + proposta REFUTED_BY_RULE (ver C10_proposta/LEIA.txt) ------
BLOCK_CODES = ("OUT_OF_SUBSET", "UNKNOWN_SYMBOLIC_INPUT", "TRANSFORM_OUT_OF_DOMAIN", "NO_UNIT", "NO_REALIZATION",
               "SHACL_VIOLATION", "CONDITION_FALSE", "CONDITION_INDETERMINATE", "RELATED_ONLY", "REPAIR_EXCLUDED",
               "AMBIGUOUS_TARGET", "UNPROVEN", "INFRA_ERROR", "UNKNOWN_INPUT", "REFUTED_BY_RULE")
LOSS_KINDS = ("rounding", "saturation", "absence", "sentinel", "context_dependence", "not_expressible", "semantic")

# --- marcadores de grandeza (N4): NOT_APPLICABLE != UNKNOWN ---------------------------------------------
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"

# --- marcadores de valor na entrada de um transporte --------------------------------------------------------
ABSENT = {"$absent": True}          # sabidamente sem valor (leitura completa)
NOT_READ = {"$not_read": True}      # fora do que a leitura cobriu
SYMBOLIC = {"$symbolic": True}      # termo simbólico ainda não resolvido (conhecido só depois da criação)


def is_marker(v, m) -> bool:
    return isinstance(v, dict) and next(iter(m)) in v


# --- basis da alegação ------------------------------------------------------------------------------------
BASES = ("direct", "shared_concept", "composition")
FIXED_DEFAULT = ("fixed", "default")
