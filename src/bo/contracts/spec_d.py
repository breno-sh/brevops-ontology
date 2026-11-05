"""C24–C29 (novos na v3): requisitos e CQs, evidência de serviço, IR de grafo, split global, catálogo de
comparadores e contratos de domínio. O C24 é a proposta do REQUIREMENTS adotada sem mudança."""

from __future__ import annotations

from ._base import (arr, boolean, c00, const, contract_schema, enum, file_kind, header, integer, local, nullable,
                    number, obj, string, text)
from .spec_b import C10_GUARD, _strip, adopted

MODELS = ("cpg", "certgraph", "devops-infra", "fixinventory", "cartography", "steampipe", "cloudquery", "mosaic", "cso",
          "cocoon", "tosca-edmm", "kalinin")
AUTH_DIMS = ("principal", "permission", "effect", "binding", "scope", "inheritance", "context", "combination")
SUPPORT = ("SUPPORTED", "OUT_OF_PIN", "UNSUPPORTED_BY_TRANSLATOR", "UNRESOLVED", "ABSENCE_DEMONSTRATED")


# ------------------------------------------------------------------------------------------------- C24
def pilot_defs() -> dict:
    """Gabarito dos oráculos dos pilotos (expected_answers.json), emenda C24 1.1.0. O envelope e a semente de caso C11
    são comuns às duas fatias; o corpo de cada fatia segue o formato que o oráculo publicou (o da NET é o schema do
    PILOT-NET-ORACLE adotado; o da STO, o do PILOT-STO-ORACLE)."""
    from .spec_b import _strip as strip
    seed = obj({"case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"), "group_id": string(r"^(GRP|G)-[A-Za-z0-9_\-]+$"),
                "stratum_partial": obj({"pair": c00("pair"), "domain": c00("domain"),
                                        "cardinality": enum("1:1", "1:N", "N:1", "N:M"),
                                        "direction": enum("forward", "inverse"),
                                        "relation": enum("exact", "close", "broad", "narrow", "related")},
                                       ["pair", "domain", "cardinality", "direction"]),
                "side": enum("subject", "object", "both"),
                "comparator": obj({"name": enum("exact", "numeric_tolerance", "set_equal", "normalized_string",
                                                "duration_equal", "cidr_equal"), "tolerance": number(minimum=0)},
                                  ["name"]),
                "cost_class": enum("free", "low", "medium", "high"),
                "values": arr(obj({"var": string(r"^(\?[a-z][a-z0-9_]*|[a-z][a-z0-9_]*:\S+)$"), "term": c00("term")},
                                  ["var", "term"])),
                "pending": obj({}, extra=text(3), minProperties=1,
                               propertyNames={"enum": ["claim_id", "claim_version_id", "frame_ref", "lowering_plan",
                                                       "origin", "stratum.relation", "weight", "values"]})},
               ["case_id", "group_id", "stratum_partial", "side", "comparator", "cost_class", "pending"],
               description="semente de caso C11: o que o oráculo sabe, e em pending o motivo de cada campo que só o "
                           "E2E preenche (o oráculo não lê alegações)")
    net = strip(adopted("C24_pilot_net_expected_answers"))
    net["properties"]["contract_version"] = enum("1.0.0", "1.1.0")
    net["properties"]["translations"]["additionalProperties"]["properties"]["c11_case_seed"] = local("c11_case_seed")
    net.pop("description", None)
    hp = {"schema": const("bo.pilot.sto.expected_answers/1", description="como o PILOT-STO-ORACLE publicou"), "contract": const("C24"),
          "contract_version": enum("1.0.0", "1.1.0"), "module": const("PILOT-STO-ORACLE")}
    check = obj({"kind": enum("version_state", "public", "claim", "decomposition", "versioning", "timeline",
                              "apply_rejection", "key_unknown"),
                 "claim": {"type": "object"}, "version": text(1), "container": text(1), "axis": text(1),
                 "unit": text(1), "key": text(1),
                 "expect": {"description": "resposta do oráculo (estado, booleano, lista ou {verdict, code})"}},
                ["kind", "expect"],
                allOf=[{"if": {"properties": {"kind": const("claim")}},
                        "then": {"required": ["claim"], "properties": {"expect": obj(
                            {"verdict": enum("ACCEPT", "ACCEPT_WITH_DECLARED_LOSS", "REJECT", "UNKNOWN"),
                             "code": string(r"^[A-Z][A-Z_]+$")}, ["verdict"])}}}])
    sto_fx = obj({"case": string(r"^MC-[A-Z0-9-]+$"), "checks": arr(check, 1), "file": text(3),
                  "invariant_group": nullable(text(1)), "polarity": enum("positive", "negative", "unknown"),
                  "provider": enum("aws", "google", "azurerm", "oci"), "summary": text(5)},
                 ["case", "checks", "file", "invariant_group", "polarity", "provider", "summary"])
    sto_dx = obj({"c11_case_seed": local("c11_case_seed"), "declared_losses": arr(string(r"^[A-Z][A-Z_]+$")),
                  "direction": string(r"^(aws|google|azurerm|oci)->(aws|google|azurerm|oci)$"),
                  "expect": obj({"verdict": enum("ACCEPT", "ACCEPT_WITH_DECLARED_LOSS", "REJECT", "UNKNOWN"),
                                 "code": string(r"^[A-Z][A-Z_]+$")}, ["verdict"], extra=True),
                  "family": text(2), "file": text(3), "note": {"type": "string"},
                  "polarity": enum("positive", "negative", "unknown"), "variant": text(2)},
                 ["c11_case_seed", "declared_losses", "direction", "expect", "family", "file", "note", "polarity",
                  "variant"])
    sto = obj({**hp, "generated_at": c00("datetime"), "note": text(10), "oracle_sha256": c00("sha256"),
               "oracle_version": c00("semver"),
               "providers": obj({p: c00("semver") for p in ("aws", "google", "azurerm", "oci")},
                                ["aws", "google", "azurerm", "oci"]),
               "fixtures": obj({}, extra=sto_fx, minProperties=1, propertyNames={"pattern": r"^FX-STO-[A-Z0-9-]+$"}),
               "directions": obj({}, extra=sto_dx, minProperties=1, propertyNames={"pattern": r"^DX-[A-Za-z0-9_-]+$"}),
               "heldout": obj({"ciphertext_sha256": c00("sha256"), "plaintext_sha256": c00("sha256"),
                               "recipient_fingerprint_sha256": c00("sha256"), "sealed_at": c00("datetime"),
                               "sealed_file": string(r"^\$BO_DATA/PILOT-STO-ORACLE/sealed/\S+$"),
                               "counts": obj({}, extra=integer(0))},
                              ["ciphertext_sha256", "plaintext_sha256", "recipient_fingerprint_sha256", "sealed_at",
                               "sealed_file", "counts"], description="retidas só cifradas: hashes, nunca respostas")},
              ["schema", "contract", "contract_version", "module", "generated_at", "note", "oracle_sha256",
               "oracle_version", "providers", "fixtures", "directions", "heldout"])
    return {"c11_case_seed": seed, "pilot_net_expected_answers": net, "pilot_sto_expected_answers": sto,
            "pilot_expected_answers": {"oneOf": [local("pilot_net_expected_answers"), local("pilot_sto_expected_answers")],
                                       "description": "gabarito de oráculo de piloto (fatia net ou sto)"}}


def c24() -> dict:
    defs = {"requirement": _strip(adopted("C24_requirements")), "commitment": _strip(adopted("C24_commitments")),
            "cq_spec": _strip(adopted("C24_cq_spec")), **pilot_defs()}
    return contract_schema(
        "C24", "requirements", "1.1.0", "requisitos, compromissos, CQs e gabaritos dos pilotos", status="amended",
        description="Requisito; compromisso {positive | negative | unknown, fixture, resposta esperada}; CQ em "
                    "vocabulário independente com família (CIS, identidade e ciclo de vida, composição, efeito de "
                    "autorização, caminho de rede, configuração × observação, perda, provedor novo) e fixtures "
                    "conforme, não conforme e incompleta. Os três schemas são a proposta do REQUIREMENTS, sem mudança; "
                    "as regras que o schema não exprime são as de bo.requirements.model, chamadas pelo validador.",
        files=[file_kind("requirements", "requirements.jsonl", "jsonl", "requirement", "record"),
               file_kind("commitments", "commitments.jsonl", "jsonl", "commitment", "record"),
               file_kind("cq_spec", "cq_spec.jsonl", "jsonl", "cq_spec", "record"),
               file_kind("pilot_expected_answers", "expected_answers.json", "json", "pilot_expected_answers",
                         "document", "gabarito dos oráculos PILOT-NET-ORACLE e PILOT-STO-ORACLE (emenda 1.1.0)")],
        defs=defs, producers=["REQUIREMENTS", "SEMANTICS", "CQ", "CQFIX", "PILOT-{slice}-ORACLE"],
        adopted=["results/REQUIREMENTS/C24_proposta/requirements.schema.json",
                 "results/REQUIREMENTS/C24_proposta/commitments.schema.json",
                 "results/REQUIREMENTS/C24_proposta/cq_spec.schema.json"],
        rules=["C24-MODEL: regras de bo.requirements.model (polaridade × checagem, leitura completa para resposta "
               "definida, UNKNOWN com leitura parcial e o que falta, vocabulário de fixture, ids únicos)",
               "C24-XREF: requirement_ids e commitment_ids existem nos arquivos irmãos quando presentes",
               "C24-PILOT-SEED: case_id único; um campo não está ao mesmo tempo na semente e em pending; semente + "
               "pending cobrem os obrigatórios do C11",
               "C24-PILOT-DIR: a direção liga dois provedores distintos e o par do estrato é o da direção",
               "C24-PILOT-SEAL: retidas só por hash/arquivo cifrado (nenhuma resposta retida em claro)",
               "C24-PILOT-CMT: commitment_ids citados têm o formato do C24 (e existem, com commitments.jsonl irmão)"])


# ------------------------------------------------------------------------------------------------- C25
FACTS = ("identity", "import_key", "lifecycle_controller", "owner", "effective_scope", "connection_state", "effect",
         "precedence", "tag_support", "ttl_support", "api_bridge", "default")


def protocol_support() -> dict:
    """protocol_support.jsonl do SERVICE-EVIDENCE (bo.protocol_support/1), adotado com as evidências tipadas."""
    ev = obj({"level": c00("evidence_level"), "ref": text(1), "doc": c00("doc_source"), "citation": c00("web_citation"),
              "schema": c00("schema_source"), "model_id": c00("model_id"), "note": text(3)}, ["level"],
             allOf=[{"if": {"properties": {"level": const("interpreted")}}, "then": {"required": ["model_id", "note"]}},
                    {"if": {"properties": {"level": const("published")}},
                     "then": {"anyOf": [{"required": ["doc"]}, {"required": ["citation"]}, {"required": ["schema"]}],
                              "not": {"required": ["model_id"]}}},
                    {"if": {"properties": {"level": const("derived")}},
                     "then": {"anyOf": [{"required": ["ref"]}, {"required": ["doc"]}, {"required": ["note"]}],
                              "not": {"required": ["model_id"]}}}])
    return obj({
        "schema": const("bo.protocol_support/1"),
        "probe_type": enum("item_ttl", "log_retention", "object_lifecycle", "object_versioning", "queue_retention",
                           "rate_limit"),
        "provider": enum("aws", "google", "azurerm", "oci"), "pin": obj({"provider_version": c00("semver")},
                                                                       ["provider_version"]),
        "terraform_resource_type": c00("resource_type"), "attributes": arr(string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")),
        "status": enum("documented_supported", "documented_unsupported", "unknown"),
        "requirement": obj({"text": text(3), "max_seconds": nullable(integer(0))}, ["text", "max_seconds"]),
        "documented": {"type": "object"}, "reason": text(3), "evidence": arr(ev, 1),
        "validated": const(False, description="suporte só documentado; validar é do PROBEKIT")},
        ["schema", "probe_type", "provider", "pin", "terraform_resource_type", "attributes", "status", "requirement",
         "documented", "evidence", "validated"],
        allOf=[{"if": {"properties": {"status": const("unknown")}}, "then": {"required": ["reason"]}},
               {"if": {"properties": {"status": const("documented_supported")}},
                "then": {"properties": {"attributes": {"minItems": 1}}}}])


def c25() -> dict:
    se = obj({
        "evidence_id": string(r"^SE-[A-Za-z0-9_\-]+$"), "provider": c00("provider"),
        "pin": obj({"provider_version": c00("semver"), "api_version": text(1)}, ["provider_version"]),
        "api_resource": obj({"service": text(1), "resource": text(1)}, ["service", "resource"]),
        "terraform_resource_type": c00("resource_type"),
        "block_path": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$", description="bloco do tipo a que o fato se refere "
                                                                              "(emenda 1.1.0)"),
        "as_of": c00("date"), "schema": c00("schema_source"),
        "rule_id": string(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$",
                                                        description="regra do SERVICE-EVIDENCE que gerou o fato "
                                                                    "(emenda 1.3.0)"),
        "consulted": {"anyOf": [c00("doc_source"), c00("web_citation"), c00("schema_source")],
                      "description": "publicação consultada para um fato unknown (a busca pode ser refeita)"},
        "fact_kind": enum(*FACTS),
        "status": enum("stated", "unknown"), "value": {},
        "unknown_reason": enum("not_documented", "ambiguous", "contradictory", "out_of_pin"),
        "level": enum("published", "derived", "interpreted", "observed",
                      description="observed (emenda 1.4.0): experimento reprodutível na API real; acima de interpreted "
                                  "e distinto de published"),
        "model_id": c00("model_id"), "citation": c00("web_citation"),
        "doc": c00("doc_source"), "derived_from": arr(string(r"^SE-[A-Za-z0-9_\-]+$"), 1),
        "observation_ref": obj({"path": string(r"^\$BO_DATA/OBS-GAPS(-AZ)?/\S+$"), "record_id": text(1)},
                               ["path", "record_id"], description="registro do experimento em $BO_DATA/OBS-GAPS"),
        "run_id": string(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{2,63}$", description="rótulo sintético da execução"),
        "repetitions": integer(2), "observed_at": c00("datetime"),
        "control": obj({"description": text(5), "result": text(2)}, ["description", "result"]),
        "disputes": arr(string(r"^SE-[A-Za-z0-9_\-]+$"), 1, unique=True,
                        description="fatos publicados ou derivados que este contradiz: a divergência vira disputa, "
                                    "nunca sobrescreve (R2 corrigida do PREREG, b95403a)")},
        ["evidence_id", "provider", "pin", "api_resource", "fact_kind", "status"],
        allOf=[{"if": {"properties": {"status": const("stated")}}, "then": {"required": ["value", "level"]}},
               {"if": {"properties": {"status": const("unknown")}},
                "then": {"required": ["unknown_reason"], "not": {"required": ["value"]},
                         "anyOf": [{"required": [k]} for k in ("consulted", "citation", "doc", "schema")]}},
               {"if": {"properties": {"fact_kind": const("default"), "status": const("stated")}},
                "then": {"required": ["as_of"]}},
               {"if": {"properties": {"level": const("published"), "status": const("stated")}, "required": ["level"]},
                "then": {"anyOf": [{"required": ["citation"], "properties": {"citation": {"required": ["sentence"]}}},
                                   {"required": ["doc"]}, {"required": ["schema"]}]}},
               {"if": {"properties": {"level": const("derived")}, "required": ["level"]},
                "then": {"required": ["derived_from"]}},
               {"if": {"properties": {"level": const("interpreted")}, "required": ["level"]},
                "then": {"required": ["model_id"]}},
               {"if": {"properties": {"level": {"enum": ["published", "derived", "observed"]}}, "required": ["level"]},
                "then": {"not": {"required": ["model_id"]}}},
               {"if": {"properties": {"level": const("observed")}, "required": ["level"]},
                "then": {"required": ["observation_ref", "run_id", "repetitions", "control", "observed_at"]},
                "else": {"not": {"anyOf": [{"required": [k]} for k in ("observation_ref", "run_id", "repetitions",
                                                                       "control", "observed_at")]}}},
               # aspectos que o GRAIN 0.1.11 consome (emenda 1.5.0)
               {"if": {"properties": {"status": const("stated"),
                                      "value": {"type": "object", "properties": {"aspect": const("item_identity")}, "required": ["aspect"]}},
                       "required": ["value"]},
                "then": {"properties": {"value": local("item_identity")}}},
               {"if": {"properties": {"status": const("stated"),
                                      "value": {"type": "object", "properties": {"aspect": const("namespace_cascade")},
                                                "required": ["aspect"]}},
                       "required": ["value"]},
                "then": {"properties": {"value": obj({"aspect": const("namespace_cascade"), "cascade": boolean()},
                                                     ["aspect", "cascade"], extra=True)}}}])
    item_identity = obj({"aspect": const("item_identity"), "has_id": boolean(), "requires_parent": boolean(),
                         "parent_attribute": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"),
                         "parent_type": c00("resource_type")}, ["aspect", "has_id"], extra=True,
                        allOf=[{"if": {"properties": {"has_id": const(True)}}, "then": {"required": ["requires_parent"]},
                                "else": {"not": {"anyOf": [{"required": [k]} for k in
                                                           ("requires_parent", "parent_attribute", "parent_type")]}}},
                               {"if": {"properties": {"requires_parent": const(True)}, "required": ["requires_parent"]},
                                "then": {"required": ["parent_attribute", "parent_type"]}}],
                        description="identidade do item de bloco/coleção (GRAIN T64): com id, diz se exige o pai")
    side = {"type": "object", "description": "o que cada lado afirma (kind/rule, ou service/resource)"}
    dispute = obj({"provider": c00("provider"), "terraform_resource_type": c00("resource_type"),
                   "block_path": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"), "fact": enum(*FACTS),
                   "doc": side, "spec": side, "evidence": arr(string(r"^SE-[A-Za-z0-9_\-]+$"), 1, unique=True),
                   "kind": string(r"^[a-z]+_x_[a-z]+$", description="natureza da disputa (ex.: observed_x_derived)"),
                   "status": enum("aberta", "resolvida-por-observação", "resolvida-por-publicação",
                                  description="ausente = aberta (registros anteriores à emenda 1.5.0); "
                                              "resolvida-por-publicação = R6 do PREREG (emenda 1.6.0)"),
                   "sides": arr(string(r"^SE-[A-Za-z0-9_\-]+$"), 2, unique=True, maxItems=2,
                                description="ids dos dois lados (PUBLISHED ou DERIVED, R2 corrigida)"),
                   "resolved_to": string(r"^(spec|doc|SE-[A-Za-z0-9_\-]+)$"),
                   "observation_id": string(r"^SE-[A-Za-z0-9_\-]+$"),
                   "publication_id": string(r"^SE-[A-Za-z0-9_\-]+$",
                                            description="fato PUBLISHED literal de fonte fixada que resolveu (R6)"),
                   "resolved_at": c00("datetime")},
                  ["provider", "terraform_resource_type", "fact", "evidence"],
                  allOf=[{"if": {"properties": {"status": const("resolvida-por-observação")}, "required": ["status"]},
                          "then": {"required": ["sides", "resolved_to", "observation_id"]}},
                         {"if": {"properties": {"status": const("resolvida-por-publicação")}, "required": ["status"]},
                          "then": {"required": ["sides", "resolved_to", "publication_id"]}},
                         {"if": {"properties": {"status": enum("resolvida-por-observação", "resolvida-por-publicação")},
                                 "required": ["status"]},
                          "else": {"not": {"anyOf": [{"required": [k]} for k in
                                                     ("resolved_to", "observation_id", "publication_id")]}}}])
    dp, dr = header("bo.spec_disputes/1", "C25", "1.6.0", module=False, generated=False)
    dp.pop("contract_version"); dp.pop("contract")
    disputes_doc = obj({**dp, "module": c00("stable_id"), "note": text(3), "contract": const("C25"),
                        "contract_version": enum("1.5.0", "1.6.0"), "generated_at": c00("datetime"),
                        "disputes": arr(local("spec_dispute"))}, ["schema", "module", "disputes"])
    return contract_schema(
        "C25", "service_evidence", "1.6.0", "evidência de API e docs ligada ao pin", status="amended",
        description="Fato de API/docs ligado ao pin: recurso de API, identidade, chave de importação, controlador de "
                    "ciclo de vida, dono, alcance, estado de conexão, efeito, precedência, suporte a tag/TTL; nível "
                    "(publicado | derivado | interpretado) e citação. Citação publicada separada de inferência; "
                    "desconhecido explícito.",
        files=[file_kind("service_evidence", "service_evidence.jsonl", "jsonl", "service_evidence", "record"),
               file_kind("protocol_support", "protocol_support.jsonl", "jsonl", "protocol_support", "record",
                         "suporte documentado de cada tipo de sonda por provedor (emenda 1.2.0; consumido pelo PROBEKIT)"),
               file_kind("spec_disputes", "spec_disputes.json", "json", "spec_disputes", "document",
                         "disputas spec x doc e a resolução por observação (1.5.0) ou por publicação literal (R6, 1.6.0)")],
        defs={"service_evidence": se, "protocol_support": protocol_support(), "item_identity": item_identity,
              "spec_dispute": dispute, "spec_disputes": disputes_doc}, producers=["SERVICE-EVIDENCE"],
        rules=["C25-LEVEL: publicado cita a sentença (citation, doc ou schema do binário assinado); derivado aponta "
               "de quais fatos; interpretado tem model_id",
               "C25-OBSERVED: observed (experimento reprodutível na API real) tem observation_ref em $BO_DATA/OBS-GAPS, "
               "run_id, repetitions >= 2, control e observed_at; fica acima de interpreted e é distinto de published "
               "(emenda 1.4.0, adendo de 04/11 §2)",
               "C25-DISPUTE: observed e published do mesmo fato com valores diferentes viram disputa (o observed cita o "
               "publicado em disputes; os dois ficam no arquivo, nada é sobrescrito)",
               "C25-SYNTH: fato observado só com rótulos sintéticos (nenhum ocid1., arn, conta de 12 dígitos, GUID de "
               "assinatura nem e-mail no valor, no controle ou na referência)",
               "C25-DISPUTE-REG: spec_disputes.json registra cada disputa; resolvida-por-observação exige os dois "
               "lados (sides), resolved_to (spec, doc ou o id do lado) e observation_id; o lado vencedor é um dos lados "
               "e a observação não é um deles; uma disputa por (fato, natureza) (emenda 1.5.0)",
               "C25-DISPUTE-PUB: resolvida-por-publicação (R6 do PREREG) só em disputa derived_x_derived; exige sides, "
               "resolved_to e publication_id (fato PUBLISHED literal de fonte fixada), não exige observation_id; o "
               "fato publicado não é um dos lados e o vencedor é um dos lados (emenda 1.6.0)",
               "C25-ITEM: item_identity tem has_id; com id, requires_parent; exigindo o pai, parent_attribute e "
               "parent_type; namespace_cascade tem cascade booleano (GRAIN 0.1.11)",
               "C25-UNKNOWN: unknown cita a publicação consultada (consulted, citation, doc ou schema); level é opcional",
               "C25-DEFAULT: default afirmado tem as_of (como o C03-DEFAULT); api_bridge liga api_resource ao tipo",
               "C25-API: api_resource.resource aceita o marcador UNKNOWN quando a página não nomeia o recurso",
               "C25-BLOCK: block_path, quando há, é caminho de bloco do tipo e terraform_resource_type está presente",
               "C25-DERIVED: derived_from cita evidence_id do mesmo arquivo",
               "C25-PS-UNIQ: (probe_type, provider, terraform_resource_type) único em protocol_support.jsonl",
               "C25-PS-PUB: documented_* tem ao menos uma evidência published; validated é sempre false",
               "C25-UNIQ: evidence_id único"])


# ------------------------------------------------------------------------------------------------- C26
def c26() -> dict:
    node = string(r"^[rc][0-9]+$")
    gir = obj({
        "graph_id": string(r"^GIR-[A-Za-z0-9_\-]+$"), "case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"),
        "source_provider": c00("provider"),
        "terms": arr(obj({"term_id": string(r"^t[0-9]+$"), "term": c00("term")}, ["term_id", "term"])),
        "resources": arr(obj({"node_id": string(r"^r[0-9]+$"), "class_iri": c00("iri"),
                              "unit_id": c00("unit_id")}, ["node_id", "class_iri"]), 1),
        "components": arr(obj({"node_id": string(r"^c[0-9]+$"), "of": string(r"^r[0-9]+$"), "class_iri": c00("iri"),
                               "occurrence_key": arr(text(1), 1)}, ["node_id", "of", "class_iri", "occurrence_key"])),
        "references": arr(obj({"from": node, "to": node, "property_iri": c00("iri"),
                               "kind": enum("reference", "attachment", "facet_of")}, ["from", "to", "property_iri",
                                                                                       "kind"])),
        "preconditions": arr(obj({"precondition_id": string(r"^PRE-[A-Za-z0-9_\-]+$"), "guard": C10_GUARD,
                                  "applies_to": arr(node, 1)}, ["precondition_id", "guard", "applies_to"])),
        "contexts": arr(obj({"key": enum("region", "edition", "provider_version", "synthetic_account"),
                             "value": {"type": ["string", "null"]},
                             "state": enum("known", "symbolic", "unknown")}, ["key", "state"]))},
        ["graph_id", "source_provider", "terms", "resources", "components", "references", "preconditions", "contexts"])
    step = obj({
        "order": integer(1), "action": enum("create", "configure", "attach", "reference"),
        "node_id": node, "resource_type": c00("resource_type"),
        "derived_name": obj({"template": string(r"^[a-z0-9\-_{}]+$"), "from_terms": arr(string(r"^t[0-9]+$")),
                             "field": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$",
                                             description="campo do recurso que recebe o nome derivado; sem ele o "
                                                         "nome não vai para o HCL (emenda 1.1.0)")},
                            ["template", "from_terms"]),
        "typed_choices": arr(obj({"choice_id": string(r"^CH-[A-Za-z0-9_\-]+$"),
                                  "options": arr(string(r"^[A-Za-z0-9_.:\-]+$"), 2, unique=True),
                                  "selected": nullable(string(r"^[A-Za-z0-9_.:\-]+$")), "guard": C10_GUARD,
                                  "reason": text(3)}, ["choice_id", "options", "selected", "reason"])),
        "values": arr(obj({"field": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"), "term": c00("term"),
                           "origin": enum("carried", "synthesized", "default_declared"), "marked": boolean()},
                          ["field", "term", "origin", "marked"],
                          allOf=[{"if": {"properties": {"origin": {"enum": ["synthesized", "default_declared"]}}},
                                  "then": {"properties": {"marked": const(True)}}}])),
        "losses": arr(obj({"code": string(r"^[A-Z][A-Z_]+$"), "field": text(1), "detail": text(3)}, ["code", "field"])),
        "symbolic_unknowns": arr(obj({"term_id": string(r"^t[0-9]+$"), "reason": text(3)}, ["term_id", "reason"])),
        "depends_on": arr(integer(1), unique=True)},
        ["order", "action", "node_id", "resource_type", "typed_choices", "values", "losses", "symbolic_unknowns",
         "depends_on"])
    lp = obj({"plan_id": string(r"^LP-[A-Za-z0-9_\-]+$"), "graph_id": string(r"^GIR-[A-Za-z0-9_\-]+$"),
              "target_provider": c00("provider"), "steps": arr(local("lowering_step"), 1),
              "dependency_closure": obj({"closed": boolean(), "missing": arr(text(1))}, ["closed", "missing"],
                                        allOf=[{"if": {"properties": {"closed": const(True)}},
                                                "then": {"properties": {"missing": {"maxItems": 0}}},
                                                "else": {"properties": {"missing": {"minItems": 1}}}}])},
             ["plan_id", "graph_id", "target_provider", "steps", "dependency_closure"])
    return contract_schema(
        "C26", "graph_ir", "1.3.0", "IR de grafo e plano de lowering", status="amended",
        description="IR de grafo: termos simbólicos, recursos, componentes, referências, pré-condições, contextos; plano "
                    "de criação com ordem, nomes derivados, escolhas tipadas, valores sintetizados (marcados), perdas, "
                    "desconhecidos simbólicos; fechamento de dependências. O plano é neutro: tags de execução (bo_run, "
                    "bo_case…) são do harness e nunca vêm no plano.",
        files=[file_kind("graph_ir", "graph_ir.jsonl", "jsonl", "graph_ir", "record"),
               file_kind("lowering_plan", "lowering_plan.jsonl", "jsonl", "lowering_plan", "record")],
        defs={"graph_ir": gir, "lowering_step": step, "lowering_plan": lp},
        producers=["GRAPH-LOWERING", "PILOT-{slice}-E2E"],
        rules=["C26-NODES: referências, componentes e pré-condições citam nós do mesmo grafo",
               "C26-ORDER: ordens 1..n sem repetição; depends_on só aponta para passos anteriores",
               "C26-SYNTH: valor sintetizado ou default é marcado",
               "C26-TERMS: from_terms e symbolic_unknowns citam termos do graph_ir irmão",
               "C26-CHOICE: selected é uma das opções (ou nulo com motivo)",
               "C26-TARGET: reference.target_node (C00 3.0.1), quando há, é nó do grafo criado por passo anterior "
               "(de que o passo depende, direta ou indiretamente)",
               "C26-LIST: atributo-lista de referências vai como termo list do C00 (security_list_ids = [ref, …]), "
               "não como campo indexado .0, .1 (aceito, com nota, para os planos já gravados); cada referência da lista obedece ao C26-TARGET (emenda 1.3.0, "
               "CC-NET-E2E-1)",
               "C26-NOTAG: nenhum valor do plano é tag de execução (campo tags/labels/freeform_tags.bo_*); quem marca "
               "a execução é o harness (emenda 1.2.0, decisão do coordenador sobre o ACHADO 4 do HARNESS-OCI)",
               "C26-STUB: o stub tem exatamente um plano por target_provider (aws, google, azurerm, oci), cada um "
               "renderizável no pin do PINS (gate de render dos HARNESS-*)"])


# ------------------------------------------------------------------------------------------------- C27
def c27() -> dict:
    part = obj({"n_families": integer(0), "ids_sha256": c00("sha256")}, ["n_families", "ids_sha256"])
    sealed = obj({"n_families": integer(0),
                  "encrypted": obj({"path": string(r"^\$BO_DATA/SPLIT/sealed/\S+\.age$"), "sha256": c00("sha256"),
                                    "cipher": const("age"),
                                    "recipient_fingerprint": string(r"^age1[0-9a-z]{20,}$|^SHA256:[A-Za-z0-9+/=]{20,}$")},
                                   ["path", "sha256", "cipher", "recipient_fingerprint"])},
                 ["n_families", "encrypted"], description="o teste nunca lista ids em claro")
    hp, hr = header("bo.split/1", "C27", "1.0.0", module=True)
    split = obj({**hp, "seed": integer(0), "method": text(5),
                 "dedup": obj({"method": enum("exact_hash", "near_dup_minhash", "fork_graph", "manual"),
                               "threshold": number(minimum=0, maximum=1)}, ["method"]),
                 "partitions": obj({"train": part, "dev": part, "test": sealed}, ["train", "dev", "test"]),
                 "role_projections": obj({}, extra=obj({"partitions": arr(enum("train", "dev"), 1, unique=True)},
                                                       ["partitions"]),
                                         propertyNames={"enum": ["mapper", "glossarist", "hunter", "auditor",
                                                                 "evaluator", "extractor", "builder"]}),
                 "opening_receipt": nullable(obj({"opened_at": c00("datetime"), "by": c00("stable_id"),
                                                  "freeze_name": string(r"^[A-Z][A-Z0-9_\-]*$"),
                                                  "receipt_sha256": c00("sha256")},
                                                 ["opened_at", "by", "freeze_name", "receipt_sha256"]))},
                hr + ["seed", "method", "dedup", "partitions", "role_projections", "opening_receipt"])
    fam = obj({"family_id": c00("family_id"), "members": arr(c00("repo_id"), 1, unique=True),
               "dedup_method": enum("exact_hash", "near_dup_minhash", "fork_graph", "manual"),
               "signature_sha256": c00("sha256"), "partition": enum("train", "dev")},
              ["family_id", "members", "dedup_method", "signature_sha256", "partition"],
              description="famílias de desenvolvimento; as de teste só no arquivo cifrado")
    return contract_schema(
        "C27", "split", "1.0.0", "split global por família", status="new_v3",
        description="Famílias deduplicadas, split global, projeções de treino por papel, sha do arquivo cifrado, recibo "
                    "de abertura. O teste nunca aparece em claro nem é projetado para papel algum.",
        files=[file_kind("split", "split.json", "json", "split", "document"),
               file_kind("families", "families.jsonl", "jsonl", "family", "record")],
        defs={"split": split, "family": fam}, producers=["SPLIT"],
        rules=["C27-DISJOINT: um repositório em uma família só; family_id único",
               "C27-COUNTS: com families.jsonl irmão, as contagens de train e dev batem",
               "C27-SEALED: nenhum papel vê o teste; o teste só como sha256 + caminho .age"])


# ------------------------------------------------------------------------------------------------- C28
def c28() -> dict:
    val = {"oneOf": [number(), c00("marker")], "description": "número | NOT_APPLICABLE | UNKNOWN (NOT_APPLICABLE ≠ 0)"}
    metric = obj({"axis": enum("native", "representation", "translation"), "name": text(2), "value": val,
                  "reason": text(5)}, ["axis", "name", "value"],
                 allOf=[{"if": {"properties": {"value": const("NOT_APPLICABLE")}}, "then": {"required": ["reason"]}}])
    comp = obj({"comparator_id": enum(*MODELS), "version": text(1),
                "source": obj({"uri": string(r"^https://\S+$"), "kind": enum("paper", "repo", "both")},
                              ["uri", "kind"]),
                "native_scope": text(5), "artifact": enum("yes", "no", "doc_only"), "native_task": text(5),
                "decision": enum("include", "exclude", "adapt"), "decision_reason": text(10),
                "axes": arr(enum("native", "representation", "translation"), 1, unique=True),
                "adaptation_budget": obj({"hours": number(minimum=0), "unit": const("agent_hours")}, ["hours", "unit"]),
                "kalinin_family": boolean(), "metrics": arr(metric)},
               ["comparator_id", "version", "source", "native_scope", "artifact", "native_task", "decision",
                "decision_reason", "axes", "adaptation_budget", "kalinin_family", "metrics"])
    hp, hr = header("bo.comparators/1", "C28", "1.0.0", module=True)
    cdoc = obj({**hp, "comparators": arr(local("comparator"), 1)}, hr + ["comparators"])
    fp, fr = header("bo.h2h_fairness/1", "C28", "1.0.0", module=True)
    fair = obj({**fp, "universe_ref": c00("file_ref"), "cq_ref": c00("file_ref"),
                "budget": obj({"unit": const("agent_hours"), "per_comparator": number(minimum=0)},
                              ["unit", "per_comparator"]),
                "comparators": arr(obj({"comparator_id": enum(*MODELS), "budget_hours": number(minimum=0),
                                        "same_universe": boolean(), "same_cqs": boolean()},
                                       ["comparator_id", "budget_hours", "same_universe", "same_cqs"]), 1),
                "rules": arr(text(10), 1)},
               fr + ["universe_ref", "cq_ref", "budget", "comparators", "rules"])
    return contract_schema(
        "C28", "comparators", "1.0.0", "catálogo de comparadores e justiça do head-to-head", status="new_v3",
        description="Comparador: versão, fonte, escopo nativo, artefato (sim | não | só documental), tarefa nativa, "
                    "decisão; eixo (nativo | representação | tradução); orçamento de adaptação; família Kalinin; "
                    "NOT_APPLICABLE ≠ 0.",
        files=[file_kind("comparators", "comparators.yaml", "yaml", "comparators", "document"),
               file_kind("h2h_fairness", "h2h_fairness.yaml", "yaml", "h2h_fairness", "document")],
        defs={"metric": metric, "comparator": comp, "comparators": cdoc, "h2h_fairness": fair},
        producers=["BENCH-CONTRACT", "PREREG"], consumers=["BASELINE-ADAPT", "HEAD2HEAD"],
        rules=["C28-NA: eixo fora de 'axes' só tem valor NOT_APPLICABLE (nunca 0); NOT_APPLICABLE diz o porquê",
               "C28-ARTIFACT: sem artefato (no/doc_only), nenhum número no eixo de tradução",
               "C28-BUDGET: orçamento igual para todos (budget_hours = per_comparator), mesmo universo e mesmas CQs",
               "C28-UNIQ: comparator_id único"])


# ------------------------------------------------------------------------------------------------- C29
def c29() -> dict:
    dim = obj({"status": enum(*SUPPORT), "note": text(3), "evidence": arr(c00("evidence_item"))}, ["status"],
              allOf=[{"if": {"properties": {"status": const("ABSENCE_DEMONSTRATED")}},
                      "then": {"required": ["evidence"], "properties": {"evidence": {"minItems": 1}}}}])
    frag_ref = string(r"^FRG-[A-Za-z0-9_\-]+$")
    dom = obj({
        "domain": c00("domain"),
        "identity": obj({"key_fields": arr(text(1), 1), "composite": boolean()}, ["key_fields", "composite"]),
        "owner": obj({"rule": text(5)}, ["rule"]), "scope": obj({"rule": text(5)}, ["rule"]),
        "authorization": obj({d: dim for d in AUTH_DIMS}, list(AUTH_DIMS)),
        "network_fragment": frag_ref, "graphs": obj({"lb": frag_ref, "db": frag_ref}),
        "decision_units": arr(obj({"name": string(r"^[a-z][a-z0-9_]*$"), "decision": text(5),
                                   "units": arr(c00("unit_id"))}, ["name", "decision"]), 1),
        "observability": obj({"signals": arr(text(2)), "status": enum(*SUPPORT)}, ["signals", "status"]),
        "out_of_support": arr(obj({"item": text(2), "status": enum(*SUPPORT[1:]), "evidence": arr(c00("evidence_item"))},
                                  ["item", "status"]))},
        ["domain", "identity", "owner", "scope", "authorization", "decision_units", "observability", "out_of_support"])
    hp, hr = header("bo.domain_contracts/1", "C29", "1.0.0", module=True)
    doc = obj({**hp, "domains": arr(local("domain_contract"), 1)}, hr + ["domains"])
    frag = obj({"fragment_id": frag_ref, "domain": c00("domain"),
                "kind": enum("authorization", "network", "lb_graph", "db_graph"),
                "nodes": arr(obj({"node_id": string(r"^n[0-9]+$"), "kind": string(r"^[a-z][a-z0-9_]*$"),
                                  "unit_id": c00("unit_id")}, ["node_id", "kind"]), 1),
                "edges": arr(obj({"from": string(r"^n[0-9]+$"), "to": string(r"^n[0-9]+$"),
                                  "kind": string(r"^[a-z][a-z0-9_]*$")}, ["from", "to", "kind"])),
                "status": enum(*SUPPORT)}, ["fragment_id", "domain", "kind", "nodes", "edges", "status"])
    return contract_schema(
        "C29", "domain_contracts", "1.0.0", "contratos de domínio e fragmentos", status="new_v3",
        description="Por domínio: identidade, dono e alcance; extensão de autorização (principal, permissão, efeito, "
                    "binding, escopo, herança, contexto, combinação); fragmento de rede; grafos de LB e banco; unidades "
                    "de decisão; observabilidade; OUT_OF_PIN | UNSUPPORTED_BY_TRANSLATOR | UNRESOLVED | ausência "
                    "demonstrada (ABSENCE_DEMONSTRATED, com evidência).",
        files=[file_kind("domain_contracts", "domain_contracts.yaml", "yaml", "domain_contracts", "document"),
               file_kind("fragment", "fragments/*.json", "json", "fragment", "document")],
        defs={"domain_contract": dom, "domain_contracts": doc, "fragment": frag}, producers=["DOMAIN-CONTRACTS"],
        rules=["C29-FRAG: todo fragmento citado existe em fragments/ irmão e é do mesmo domínio e do tipo certo",
               "C29-EDGES: arestas do fragmento citam nós dele",
               "C29-UNIQ: um contrato por domínio"])


SPECS = {"C24": c24, "C25": c25, "C26": c26, "C27": c27, "C28": c28, "C29": c29}
