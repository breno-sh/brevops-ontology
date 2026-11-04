"""C00–C08: convenções e definições comuns, átomos, tipos, fatos de docs, papéis, espaço de valores,
configuração simbólica, universo e candidatos."""

from __future__ import annotations

from ._base import (arr, boolean, c00, const, contract_schema, enum, file_kind, header, integer, local, nullable,
                    number, obj, string, text)

# ------------------------------------------------------------------------------------------- vocabulário
PROVIDERS = ("aws", "google", "azurerm", "oci")
SYNTHETIC_PROVIDER = r"^provider_[a-z]$"
PAIRS = ("AWSGCP", "AWSAZ", "AWSOCI", "GCPAZ", "GCPOCI", "AZOCI")
PAIR_SIDE = {"AWS": "aws", "GCP": "google", "AZ": "azurerm", "OCI": "oci"}
DOMAINS = ("CMP", "NET", "STO", "DB", "SEC", "OPS")
EVIDENCE_LEVELS = ("published", "derived", "interpreted")
EVIDENCE_STATES = ("UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED")
MARKERS = ("NOT_APPLICABLE", "UNKNOWN")
PERSISTENCE_VALUES = ("PERSISTED", "ALTERED", "REJECTED_BY_API", "NOT_READABLE", "INFRA_ERROR", "UNKNOWN")
BEHAVIOR_VALUES = ("OBSERVATIONS_MATCH_UNDER_PROTOCOL", "OBSERVATIONS_DIFFER_UNDER_PROTOCOL", "NOT_OBSERVED_IN_WINDOW",
                   "PROTOCOL_UNSUPPORTED", "INFRA_ERROR", "UNKNOWN")
OUTCOME_AXES = {"persistence": PERSISTENCE_VALUES, "behavior": BEHAVIOR_VALUES}
VERDICTS = ("OK", "REFUTED_BY_RULE", "UNPROVEN", "CONTESTED", "AMBIGUOUS")
# C23: os 13 do plano + UNKNOWN_INPUT (T-ABSENCE do SEMANTICS) + REFUTED_BY_RULE (proposta do SEMANTICS)
BLOCK_CODES = ("OUT_OF_SUBSET", "UNKNOWN_SYMBOLIC_INPUT", "TRANSFORM_OUT_OF_DOMAIN", "NO_UNIT", "NO_REALIZATION",
               "SHACL_VIOLATION", "CONDITION_FALSE", "CONDITION_INDETERMINATE", "RELATED_ONLY", "REPAIR_EXCLUDED",
               "AMBIGUOUS_TARGET", "UNPROVEN", "INFRA_ERROR", "UNKNOWN_INPUT", "REFUTED_BY_RULE")
INDEX_SETS_FIXED = ("provider", "pair", "domain", "slice", "model", "candidate", "probe_type", "control", "lens")
VALUE_MARKS = ("configured", "inferred", "default", "observed")
UNKNOWN_MARKS = ("unknown", "absent", "not_read", "withheld")
WITHHELD_REASONS = ("secret", "environment", "boot_script", "log", "object_content", "message_content")

# ------------------------------------------------------------------------------------------- padrões
P_STABLE_ID = r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$"
P_DATETIME = (r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T([01]\d|2[0-3]):[0-5]\d(:[0-5]\d(\.\d{1,6})?)?"
              r"-03:00$")
P_DATE = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
P_SHA256 = r"^[0-9a-f]{64}$"
P_SEMVER = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$"
P_IRI = r"^[A-Za-z][A-Za-z0-9+.\-_]*:[^\s<>\"{}|\\^`]+$"
P_QK = r"^(quantitykind:|http://qudt\.org/vocab/quantitykind/)[A-Za-z0-9_\-]+$"
P_UNIT = r"^(unit:|http://qudt\.org/vocab/unit/)[A-Za-z0-9_\-]+$"
P_PORTABLE = r"^\$BO_(REPO|DATA|TMP)(/[^/\s]+)*/?$"
P_NO_TEMPLATE = r"(\.\.\.|…|<|>)"
P_DURATION = r"^P(?=\d|T\d)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+(\.\d+)?S)?)?$"
_CL = r"(?!EV-)[A-Za-z][A-Za-z0-9_.:\-]*(~inv)?"
P_CLAIM_ID = rf"^(?![0-9a-f]{{16,}}$){_CL}(∘{_CL})*$"
P_CLAIM_VERSION_ID = r"^[^@\s]+@[1-9][0-9]*(~inv)?$"
P_EVENT_ID = r"^EV-[A-Za-z0-9][A-Za-z0-9_.:~∘\-]*$"
P_ATOM_ID = r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"
P_RESOURCE_TYPE = r"^[a-z][a-z0-9_]*$"
P_UNIT_ID = r"^CU-[A-Za-z0-9][A-Za-z0-9_.:\-]*$"
P_CONCEPT = r"^(concept:[a-z][a-z0-9_]*|bo:UNGLOSSED)$"
P_SYMBOL = r"^SYM-[0-9a-f]{8,16}$"
P_REPO_ID = r"^R-[0-9a-f]{12}$"
P_FAMILY_ID = r"^F-[0-9a-f]{12}$"
P_MODEL_ID = r"^[a-z][a-z0-9.\-]*[a-z0-9]$"
P_RULE_ID = r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$"
P_GOLDISH = r"(?i)(gold|truth|^label$|is_match|^expected|^answer$|^correct)"


def c00_defs() -> dict:
    """Definições comuns. Todo contrato referencia estas pelo $id do C00."""
    pers = obj({"axis": const("persistence"), "value": enum(*PERSISTENCE_VALUES), "detail": text(3),
                "block_code": local("block_code")},
               ["axis", "value"],
               allOf=[{"if": {"required": ["block_code"]}, "then": {"properties": {"value": const("UNKNOWN")}}}],
               description="block_code (C23) só com UNKNOWN: o caso foi barrado antes de implantar (emenda C00 3.2.0)")
    beh = obj({"axis": const("behavior"), "value": enum(*BEHAVIOR_VALUES), "detail": text(3)}, ["axis", "value"])
    lit = obj({"kind": const("literal"), "datatype": enum("string", "number", "bool", "null", "list", "map"),
               "value": {}}, ["kind", "datatype", "value"])
    sym = obj({"kind": const("symbol"), "symbol_id": string(P_SYMBOL),
               "name_class": enum("variable", "local", "module_output", "data_source", "resource_attribute",
                                  "count_index", "each_key", "path", "workspace", "unknown"),
               "scope": const("repo")}, ["kind", "symbol_id", "name_class", "scope"])
    expr = obj({"kind": const("expression"), "op": string(r"^[A-Za-z_][A-Za-z0-9_]*$|^[-+*/%<>=!&|?:]{1,3}$"),
                "args": arr(local("term"))}, ["kind", "op", "args"])
    doc = obj({"kind": const("document"), "format": enum("json", "yaml", "policy_json"), "tree": {},
               "symbolized": arr(obj({"path": string(r"^(/[^/]*)*$", min_len=0), "symbol_id": string(P_SYMBOL),
                                      "role": enum("principal", "identifier", "account", "resource_name")},
                                     ["path", "symbol_id", "role"]))},
              ["kind", "format", "tree", "symbolized"])
    ref = obj({"kind": const("reference"), "target_type": string(P_RESOURCE_TYPE),
               "target_address": string(r"^(data\.)?[a-z][a-z0-9_]*\.SYM-[0-9a-f]{8,16}(\[[^\]]+\])?$"),
               "attribute": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"),
               "target_node": string(r"^[rc][0-9]+$", description="nó do graph_ir (C26) que a referência aponta; "
                                                                     "opcional (emenda C00 3.0.1)")},
              ["kind", "target_type", "target_address"])
    wh = obj({"kind": const("withheld"), "reason": enum(*WITHHELD_REASONS)}, ["kind", "reason"])
    lst = obj({"kind": const("list"), "items": arr(local("term"))}, ["kind", "items"],
              description="lista de termos (literais, símbolos ou referências), ex.: security_list_ids = [ref, ref] "
                          "(emenda C00 3.1.0, CC-NET-E2E-1)")
    return {
        "stable_id": string(P_STABLE_ID, description="ID do módulo = stable_id (não depende da onda)"),
        "contract_id": string(r"^C([01]\d|2[0-9])$"),
        "semver": string(P_SEMVER),
        "datetime": string(P_DATETIME, description="ISO-8601 com fuso America/Recife (-03:00)"),
        "date": string(P_DATE),
        "sha256": string(P_SHA256),
        "portable_path": {"type": "string", "pattern": P_PORTABLE, "not": {"pattern": P_NO_TEMPLATE},
                          "description": "caminho portátil concreto ($BO_REPO/..., $BO_DATA/..., $BO_TMP/...)"},
        "path_template": {"type": "string", "minLength": 1,
                          "pattern": r"^(\$BO_(REPO|DATA|TMP)(/[^/\s]+)*/?|/(?!tmp/|private/tmp/)\S+|ext:\S.*)$",
                          "not": {"pattern": P_NO_TEMPLATE},
                          "description": "caminho com índices {x} declarados em index_sets; sem reticências nem <modelo>; "
                                         "absoluto só para entrada externa (nunca /tmp); ext:... é referência sem arquivo"},
        "iri": string(P_IRI, description="IRI absoluto ou CURIE"),
        "marker": enum(*MARKERS, description="NOT_APPLICABLE (não há grandeza) ≠ UNKNOWN (há, mas não se sabe)"),
        "quantity_kind": {"anyOf": [string(P_QK), enum(*MARKERS)]},
        "unit_qudt": {"anyOf": [string(P_UNIT), enum(*MARKERS)]},
        "iri_or_marker": {"anyOf": [string(P_IRI, not_={}), enum(*MARKERS)]},
        "xsd_duration": string(P_DURATION),
        "provider": {"anyOf": [enum(*PROVIDERS), string(SYNTHETIC_PROVIDER, description="sintético, só em fixture")]},
        "pair": enum(*PAIRS),
        "domain": enum(*DOMAINS),
        "model_id": string(P_MODEL_ID),
        "rule_id": string(P_RULE_ID),
        "atom_id": string(P_ATOM_ID, description="provider:resource_type:caminho.de.blocos"),
        "resource_type": string(P_RESOURCE_TYPE),
        "unit_id": string(P_UNIT_ID),
        "concept_id": string(P_CONCEPT),
        "repo_id": string(P_REPO_ID, description="id sintético por repositório (nunca o nome)"),
        "family_id": string(P_FAMILY_ID),
        "claim_id": string(P_CLAIM_ID, description="ID imutável da alegação; nunca carrega versão (@n) nem evento "
                                                   "(EV-) nem é hash da linha"),
        "claim_version_id": string(P_CLAIM_VERSION_ID, description="<claim_id>@<n>: uma versão da alegação"),
        "event_id": string(P_EVENT_ID, description="EV-...: o evento que criou esta versão"),
        "evidence_level": enum(*EVIDENCE_LEVELS),
        "evidence_state": enum(*EVIDENCE_STATES),
        "verdict": enum(*VERDICTS),
        "block_code": enum(*BLOCK_CODES),
        "absence_kind": enum("ABSENCE_DEMONSTRATED", "OUT_OF_PIN", "UNSUPPORTED_BY_TRANSLATOR", "UNRESOLVED",
                             description="tipo de ausência (C29); C09 3.1.0 grava a ausência tipada com ele"),
        "value_mark": enum(*VALUE_MARKS),
        "unknown_mark": enum(*UNKNOWN_MARKS),
        "side": enum("subject", "object"),
        "outcome_persistence": pers,
        "outcome_behavior": beh,
        "outcome": {"oneOf": [local("outcome_persistence"), local("outcome_behavior")],
                    "description": "união discriminada de desfechos {axis, value}; C12 (persistence) e C22 (behavior)",
                    "x-bo-discriminator": "axis"},
        "doc_source": obj({"repo": string(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$"), "tag": text(1),
                           "file": text(1), "line": integer(1), "sentence": text(5),
                           "redacted": boolean(description="a frase passou pela redação do privacy_lint antes de ser "
                                                           "gravada; file:line continua exato (emenda C00 3.0.1)")},
                          ["repo", "tag", "file", "line", "sentence"]),
        "web_citation": obj({"uri": string(r"^https://\S+$"), "retrieved_at": local("datetime"),
                             "section": text(1), "sentence": text(5)}, ["uri", "retrieved_at"]),
        "schema_source": obj({"provider_source": string(r"^registry\.terraform\.io/[a-z0-9-]+/[a-z0-9-]+$"),
                              "schema_sha256": local("sha256"), "op": enum("node", "keys", "shape"),
                              "pointer": string(r"^(/[^/]*)+$"), "sentence": text(2),
                              "retrieved_at": local("datetime")},
                             ["provider_source", "schema_sha256", "op", "pointer", "sentence", "retrieved_at"],
                             description="fonte publicada = saída de 'terraform providers schema -json' do binário "
                                         "assinado do pin; sentence = JSON canônico do nó (node) ou das chaves (keys) "
                                         "(emenda C00 3.0.3)"),
        "source_license": obj({"uri": text(1), "license": text(2), "transformation": text(3)},
                              ["uri", "license", "transformation"]),
        "evidence_item": {
            **obj({"level": local("evidence_level"), "ref": text(1), "doc": local("doc_source"),
                   "citation": local("web_citation"), "model_id": local("model_id"), "note": text(3)}, ["level"]),
            "anyOf": [{"required": ["ref"]}, {"required": ["doc"]}, {"required": ["citation"]}],
            "allOf": [{"if": {"properties": {"level": const("interpreted")}}, "then": {"required": ["model_id"]}},
                      {"if": {"properties": {"level": {"enum": ["published", "derived"]}}},
                       "then": {"not": {"required": ["model_id"]}}}]},
        "file_ref": obj({"path": local("portable_path"), "sha256": local("sha256")}, ["path", "sha256"]),
        "term": {"oneOf": [lit, sym, expr, doc, ref, wh, lst],
                 "description": "termo tipado da configuração simbólica (C06), sem executar HCL"},
    }


def _fix_not(d):
    """string(..., not_={}) é açúcar: troca 'not_' por um 'not' que exclui os marcadores."""
    if isinstance(d, dict):
        if "not_" in d:
            d.pop("not_")
            d["not"] = {"enum": list(MARKERS)}
        for v in d.values():
            _fix_not(v)
    elif isinstance(d, list):
        for v in d:
            _fix_not(v)
    return d


# ------------------------------------------------------------------------------------------------- C00
MODULE_KEYS = ("id", "stable_id", "v2_id", "v1_id", "title", "wave", "phase", "deps", "inputs", "outputs", "gates",
               "needs_cloud", "lock", "effort_h", "wall_h", "priority", "goal", "contracts", "answers",
               "answers_gemini", "answers_gpt6", "needs_breno", "group", "on_critical_path", "sched_start_h",
               "sched_end_h", "worktree", "branch", "owns", "tmp_dir", "model")


def c00_spec() -> dict:
    defs = _fix_not(c00_defs())
    paths = arr(local("path_template"))
    defs["module"] = obj({
        "id": local("stable_id"), "stable_id": local("stable_id"), "v2_id": {"type": ["string", "null"]},
        "v1_id": {"type": ["string", "null"]}, "title": text(3), "wave": integer(0), "phase": text(1),
        "deps": arr(local("stable_id"), unique=True), "inputs": paths, "outputs": paths,
        "gates": arr(text(3)), "needs_cloud": boolean(), "lock": {"type": ["string", "null"]},
        "effort_h": number(minimum=0), "wall_h": number(minimum=0), "priority": enum("P0", "P1", "P2"),
        "goal": text(3), "contracts": arr(local("contract_id"), unique=True), "answers": arr(text(1)),
        "answers_gemini": arr(text(1)), "answers_gpt6": arr(text(1)), "needs_breno": {"type": "string"},
        "group": text(1), "on_critical_path": boolean(), "sched_start_h": number(minimum=0),
        "sched_end_h": number(minimum=0), "worktree": string(r"^/\S+/bo-[a-z0-9-]+$"),
        "branch": string(r"^bo/[a-z0-9-]+$"), "owns": paths, "tmp_dir": string(r"^\$BO_DATA/tmp/[A-Z0-9-]+$"),
        "model": text(1)}, ["id", "stable_id", "wave", "deps", "inputs", "outputs", "gates", "contracts",
                             "worktree", "branch", "owns", "tmp_dir"])
    defs["module_catalog"] = obj({
        "project": text(3), "generated_at": local("datetime"), "timezone": const("America/Recife"),
        "plan_version": integer(1), "env": obj({}, extra=True, required=["BO_REPO", "BO_DATA", "BO_TMP"]),
        "index_sets": obj({k: arr(string(r"^[A-Za-z0-9_\-]+$"), 1) for k in INDEX_SETS_FIXED},
                          list(INDEX_SETS_FIXED), extra={"type": ["array", "string"]}),
        "contracts": obj({}, extra=obj({"name": string(r"^[a-z][a-z0-9_]*$"), "version": local("semver")},
                                       ["name", "version"]),
                         propertyNames={"pattern": r"^C([01]\d|2[0-9])$"}),
        "modules": arr(local("module"), 1)},
        ["timezone", "env", "index_sets", "contracts", "modules"], extra=True)
    return contract_schema(
        "C00", "conventions", "3.2.0", "convenções e definições comuns", status="amended",
        description="ID = stable_id; onda calculada do DAG; código em $BO_REPO/src/bo/<pacote>/; dados em "
                    "$BO_DATA/<ID>/; temporário em $BO_TMP=$BO_DATA/tmp/<ID> (nunca /tmp); caminhos só com índices "
                    "declarados em index_sets; datas ISO-8601 com fuso America/Recife. $defs comuns a todos os contratos.",
        files=[file_kind("module_catalog", "modulos.json", "json", "module_catalog", "document"),
               file_kind("module", "module.json", "json", "module", "document",
                         "uma entrada do catálogo (stub e testes)")],
        defs=defs, producers=["COORD"], consumers=["REPO"],
        rules=["C00-ID: id = stable_id; branch = bo/<id minúsculo>; worktree = .../bo-<id minúsculo>; "
               "tmp_dir = $BO_DATA/tmp/<ID>",
               "C00-WAVE: wave = 0 sem deps, senão 1 + max(wave das deps) (onda calculada do DAG)",
               "C00-DEPS: toda dep existe no catálogo; sem ciclo",
               "C00-INDEX: todo {x} num caminho é um index_set declarado",
               "C00-CONTRACTS: versões do catálogo = versões publicadas em contracts/"])


# ------------------------------------------------------------------------------------------------- C01
def c01() -> dict:
    atom = obj({
        "atom_id": c00("atom_id"), "provider": c00("provider"), "provider_version": c00("semver"),
        "resource_type": c00("resource_type"), "path": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"),
        "block_path": arr(obj({"block": string(r"^[A-Za-z0-9_]+$"),
                               "nesting_mode": enum("single", "list", "set", "map", "group"),
                               "min_items": integer(0), "max_items": integer(0),
                               "kind": enum("block", "nested_attribute",
                                            description="nested_attribute: atributo de coleção de objetos (nested_type "
                                                        "ou list/set de object) exposto como elemento; ausente = block "
                                                        "(emenda 2.2.0, CC-NET-1)")},
                              ["block", "nesting_mode"])),
        "tf_type": {"type": ["string", "array"], "description": "tipo cty do schema do provider"},
        "nesting": enum("none", "single", "list", "set", "map", "group"),
        "required": boolean(), "optional": boolean(), "computed": boolean(), "sensitive": boolean(),
        "deprecated": boolean(), "configurable": boolean(),
        "write_only": boolean(description="aceito na configuração e nunca gravado no state: sem readback por "
                                          "construção (ausente = false; emenda 2.1.0)")},
        ["atom_id", "provider", "provider_version", "resource_type", "path", "block_path", "tf_type", "nesting",
         "required", "optional", "computed", "sensitive", "deprecated", "configurable"])
    return contract_schema(
        "C01", "atoms", "2.2.0", "átomos de atributo", status="amended",
        description="Um atributo configurável de um tipo, com o caminho dos blocos aninhados.",
        files=[file_kind("atoms", "atoms.jsonl", "jsonl", "atom", "record")], defs={"atom": atom},
        producers=["SCHEMA-{provider}", "HIST-{provider}", "SCHEMA-POST"],
        rules=["C01-ID: atom_id = provider:resource_type:path",
               "C01-FLAGS: required e optional se excluem; required não é computed; configurable = required ou optional",
               "C01-BLOCKS: os blocos de block_path são o prefixo de path; nesting = modo do último bloco (none no topo)",
               "C01-UNIQ: atom_id único por (provider_version)",
               "C01-WRITEONLY: write_only implica configurable e não computed (emenda 2.1.0)",
               "C01-NESTED: atributo nested_type (protocolo 6) é UM átomo com tf_type cty equivalente "
               "(['object', {...}] ou [modo, objeto, opcionais]); os filhos não viram átomos"])


# ------------------------------------------------------------------------------------------------- C02
def c02() -> dict:
    counts = obj({k: integer(0) for k in ("attributes", "blocks", "required", "optional", "computed",
                                         "configurable", "sensitive", "deprecated")},
                 ["attributes", "blocks", "required", "optional", "computed", "configurable", "sensitive",
                  "deprecated"])
    typ = obj({"type_id": string(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$"), "provider": c00("provider"),
               "provider_version": c00("semver"), "resource_type": c00("resource_type"), "counts": counts,
               "max_depth": integer(0), "block_sha256": c00("sha256")},
              ["type_id", "provider", "provider_version", "resource_type", "counts", "block_sha256"])
    return contract_schema(
        "C02", "types", "2.0.0", "tipos de recurso", status="unchanged_v3",
        description="Um tipo de recurso por linha, com contagens e o sha256 canônico do bloco do schema.",
        files=[file_kind("types", "types.jsonl", "jsonl", "type", "record")], defs={"type": typ},
        producers=["SCHEMA-{provider}"],
        rules=["C02-ID: type_id = provider:resource_type",
               "C02-COUNTS: configurable = required + optional <= attributes"])


# ------------------------------------------------------------------------------------------------- C03
FACT_KINDS = ("description", "default", "allowed_values", "range", "unit", "format", "deprecation", "required_when",
              "conflicts_with", "forces_replacement", "example", "behavior", "applicable_when")


def c03() -> dict:
    fact = obj({
        "fact_id": string(r"^DF-[A-Za-z0-9][A-Za-z0-9_.:\-]*$"), "atom_id": c00("atom_id"),
        "provider_version": c00("semver"), "fact_kind": enum(*FACT_KINDS), "status": enum("stated", "unknown"),
        "value": {}, "unknown_reason": enum("not_documented", "ambiguous", "contradictory", "out_of_pin"),
        "as_of": c00("date"), "source": c00("doc_source"),
        "extraction_method": enum("parser", "regex", "table", "manual", "model"),
        "evidence_level": c00("evidence_level"), "model_id": c00("model_id"),
        "applies_to": arr(c00("atom_id"), 1, unique=True,
                          description="outras ocorrências (bloco repetido do schema) a que o mesmo fato se aplica; "
                                      "só em fato derived (emenda 3.1.0)")},
        ["fact_id", "atom_id", "provider_version", "fact_kind", "status", "extraction_method", "evidence_level"],
        allOf=[
            {"if": {"required": ["applies_to"]}, "then": {"properties": {"evidence_level": const("derived")}}},
            {"if": {"properties": {"status": const("stated")}}, "then": {"required": ["value", "source"],
                                                                        "not": {"required": ["unknown_reason"]}}},
            {"if": {"properties": {"status": const("unknown")}}, "then": {"required": ["unknown_reason"],
                                                                         "not": {"required": ["value"]}}},
            {"if": {"properties": {"fact_kind": const("default"), "status": const("stated")}},
             "then": {"required": ["as_of"]}},
            {"if": {"properties": {"evidence_level": const("interpreted")}}, "then": {"required": ["model_id"]}},
            {"if": {"properties": {"evidence_level": {"enum": ["published", "derived"]}}},
             "then": {"not": {"required": ["model_id"]}}},
            {"if": {"properties": {"extraction_method": const("model")}},
             "then": {"properties": {"evidence_level": const("interpreted")}}}])
    return contract_schema(
        "C03", "docs_facts", "3.1.0", "fatos de documentação por atributo e por tipo", status="amended",
        description="Fato por atributo com source{repo, tag, file, line, sentence}, extraction_method e evidence_level "
                    "(published | derived | interpreted, com model_id quando interpretado); default com data; unknown "
                    "explícito (status=unknown com motivo, nunca valor inventado).",
        files=[file_kind("docs_facts", "docs_facts.jsonl", "jsonl", "fact", "record"),
               file_kind("type_subcategory", "type_subcategory.jsonl", "jsonl", "type_fact", "record",
                         "fatos do TIPO (subcategoria, ID de importação, título, apelido): um registro por tipo")],
        defs={"fact": fact, "type_fact": type_fact(), "type_status": type_status()},
        producers=["DOCS-{provider}"],
        rules=["C03-UNK: status=unknown não tem value; stated tem value e source",
               "C03-DEFAULT: default declarado tem as_of (data)",
               "C03-MODEL: interpreted exige model_id; extraction_method=model só com interpreted",
               "C03-UNIQ: fact_id único",
               "C03-APPLIES: applies_to só em fato derived, átomos do mesmo provider:tipo e sem repetir atom_id",
               "C03-TS-UNIQ: type_id único (por kind) e = provider:resource_type",
               "C03-TS-UNK: bloco unknown sem valor nem formato de ID; stated com fonte (source ou statements)",
               "C03-TS-IMPORT: import só em recurso (kind resource ou ausente); data source não tem import",
               "C03-TS-REDACT: nenhum texto gravado com GUID depois de /subscriptions/ (use {subscriptionId})"])


def type_status() -> dict:
    """Bloco stated|unknown de um fato do tipo (subcategoria ou importação). Superconjunto dos campos que os quatro
    DOCS-* extraem; o que cada um não extrai fica ausente."""
    stmt = obj({"line": integer(1), "sentence": text(5)}, ["line", "sentence"])
    return obj({
        "status": enum("stated", "unknown"), "value": {"anyOf": [text(1), arr(text(1), 1)]},
        "unknown_reason": enum("not_documented", "ambiguous", "contradictory", "out_of_pin", "not_supported"),
        "source": c00("doc_source"), "statement": c00("doc_source"), "key_sentence": c00("doc_source"),
        "statements": arr(stmt, 1), "other_lines": arr(c00("doc_source")),
        "supported": boolean(), "id_format": text(1), "id_is_plain_id": boolean(),
        "id_attributes": arr(text(1)), "id_text": arr(text(1)), "separators": arr({"type": "string"}),
        "placeholders": arr(text(1)), "identity": obj({"required": arr(text(1)), "optional": arr(text(1))},
                                                       ["required", "optional"]),
        "methods": arr(enum("import_block_identity", "import_block_id", "terraform_import_cli"), unique=True),
        "extraction_method": enum("parser", "regex", "table", "manual", "model"),
        "evidence_level": c00("evidence_level"), "model_id": c00("model_id")},
        ["status", "extraction_method", "evidence_level"],
        allOf=[{"if": {"properties": {"status": const("stated")}},
                "then": {"anyOf": [{"required": ["source"]}, {"required": ["statements"]}],
                         "not": {"required": ["unknown_reason"]}}},
               {"if": {"properties": {"status": const("unknown")}},
                "then": {"required": ["unknown_reason"],
                         "not": {"anyOf": [{"required": ["value"]}, {"required": ["id_format"]}]}}},
               {"if": {"properties": {"evidence_level": const("interpreted")}}, "then": {"required": ["model_id"]}},
               {"if": {"properties": {"evidence_level": {"enum": ["published", "derived"]}}},
                "then": {"not": {"required": ["model_id"]}}}])


def type_fact() -> dict:
    return obj({
        "type_id": string(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$"), "provider": c00("provider"),
        "provider_version": c00("semver"), "resource_type": c00("resource_type"),
        "kind": enum("resource", "data_source", description="ausente = resource"), "in_schema": boolean(),
        "doc_file": nullable(text(1)), "doc_pages": arr(text(1)),
        "title": obj({"text": text(1), "line": integer(1)}, ["text", "line"]), "page_title": text(1),
        "aliases": arr(c00("resource_type"), unique=True), "documented_as_alias_of": c00("resource_type"),
        "alias_of": obj({"type_id": string(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$"), "evidence_level": c00("evidence_level"),
                         "source": c00("doc_source")}, ["type_id", "evidence_level"]),
        "subcategory": local("type_status"), "import": local("type_status")},
        ["type_id", "provider", "provider_version", "resource_type", "subcategory"],
        allOf=[{"if": {"properties": {"kind": const("data_source")}, "required": ["kind"]},
                "then": {"not": {"required": ["import"]}}}],
        description="fato do TIPO (não do átomo): subcategoria e ID de importação (emenda C03 3.1.0)")


# ------------------------------------------------------------------------------------------------- C04
ROLES = ("CONFIG", "IDENTIFIER", "NAME", "TAG", "REFERENCE", "TIMESTAMP", "SECRET")


def c04() -> dict:
    role = obj({"atom_id": c00("atom_id"), "role": enum(*ROLES), "rule_id": string(r"^ROLE-[A-Z0-9][A-Z0-9\-]*$"),
                "evidence": arr(c00("evidence_item"))}, ["atom_id", "role", "rule_id"])
    return contract_schema(
        "C04", "roles", "2.0.0", "papel de cada átomo", status="unchanged_v3",
        description="atom_id, role ∈ {CONFIG, IDENTIFIER, NAME, TAG, REFERENCE, TIMESTAMP, SECRET}, rule_id.",
        files=[file_kind("roles", "roles.jsonl", "jsonl", "role", "record")], defs={"role": role},
        producers=["ROLES"], rules=["C04-UNIQ: um papel por atom_id"])


# ------------------------------------------------------------------------------------------------- C05
SCALARS = ("integer", "decimal", "boolean", "string", "enum", "duration")


def c05() -> dict:
    datatype = {"oneOf": [
        obj({"kind": const("scalar"), "scalar": enum(*SCALARS)}, ["kind", "scalar"]),
        obj({"kind": const("tuple"), "components": arr(obj({"name": string(r"^[a-z][a-z0-9_]*$"),
                                                             "scalar": enum(*SCALARS)}, ["name", "scalar"]), 2)},
            ["kind", "components"]),
        obj({"kind": const("tree"), "format": enum("json_document", "yaml_document", "policy_document", "map",
                                                   "list"),
             "key_scalar": enum(*SCALARS), "value_scalar": enum(*SCALARS)}, ["kind", "format"]),
        obj({"kind": const("reference"), "target_kind": enum("resource", "data_source", "component", "external"),
             "target_types": arr(c00("resource_type"))}, ["kind", "target_kind"])]}
    vs = obj({
        "atom_id": c00("atom_id"), "datatype": datatype, "quantity_kind": c00("quantity_kind"),
        "unit_qudt": c00("unit_qudt"), "rate_window": nullable(c00("xsd_duration")),
        "byte_convention": enum("SI", "IEC", "NOT_APPLICABLE"), "enum": arr({}, 1, unique=True),
        "range": obj({"min": number(), "max": number(), "min_exclusive": boolean(), "max_exclusive": boolean(),
                      "step": number(exclusiveMinimum=0)}),
        "format": text(1), "sentinels": obj({}, extra=text(2)), "evidence": arr(c00("evidence_item"), 1),
        "unit_candidates": arr(string(r"^(unit:|http://qudt\.org/vocab/unit/)[A-Za-z0-9_\-]+$"), 2, unique=True,
                               description="unidades possíveis quando a convenção é aberta (ex.: GigaBYTE x GibiBYTE); "
                                           "só com unit_qudt UNKNOWN (emenda 3.1.0)"),
        "allowed_values": arr(number(), 1, unique=True, description="valores válidos numéricos (escalar numérico ou "
                                                                   "elemento numérico de árvore)"),
        "counted": enum("vcpu", "ocpu", "ecpu", "cpu", description="coisa contada quando a grandeza é Count")},
        ["atom_id", "datatype", "quantity_kind", "unit_qudt", "rate_window", "byte_convention", "evidence"],
        allOf=[{"if": {"properties": {"quantity_kind": const("NOT_APPLICABLE")}},
                "then": {"properties": {"unit_qudt": const("NOT_APPLICABLE"), "byte_convention": const("NOT_APPLICABLE"),
                                        "rate_window": {"type": "null"}}}},
               {"if": {"properties": {"unit_qudt": const("NOT_APPLICABLE"),
                                      "datatype": {"not": {"properties": {"kind": const("scalar"),
                                                                          "scalar": const("duration")}}}}},
                "then": {"properties": {"quantity_kind": const("NOT_APPLICABLE")}}},
               {"if": {"required": ["unit_candidates"]}, "then": {"properties": {"unit_qudt": const("UNKNOWN")}}},
               {"if": {"properties": {"quantity_kind": const("UNKNOWN")}},
                "then": {"properties": {"unit_qudt": const("UNKNOWN")}}}])
    return contract_schema(
        "C05", "value_space", "3.1.0", "espaço de valores por átomo", status="amended",
        description="datatype estruturado (escalar, tupla, árvore, referência); quantity_kind e unit_qudt = IRI | "
                    "NOT_APPLICABLE | UNKNOWN; rate_window; byte_convention (SI | IEC); enum, faixa, formato, evidência.",
        files=[file_kind("value_space", "value_space.jsonl", "jsonl", "value_space", "record")], defs={"value_space": vs},
        producers=["UNITS"],
        rules=["C05-NA: quantity_kind NOT_APPLICABLE ⇔ unit_qudt NOT_APPLICABLE, exceto duração (xsd:duration carrega a "
               "própria unidade: grandeza Time com unidade NOT_APPLICABLE); UNKNOWN de grandeza ⇒ unidade UNKNOWN "
               "(NOT_APPLICABLE ≠ UNKNOWN)",
               "C05-KIND: string, booleano, enum e referência não têm grandeza (NOT_APPLICABLE); árvore só tem a do "
               "elemento quando value_scalar é numérico ou duração",
               "C05-BYTES: unidade de informação com prefixo exige byte_convention SI ou IEC; unit:BYTE e unit:BIT sem "
               "prefixo aceitam NOT_APPLICABLE (convenção vácua)",
               "C05-CAND: unit_candidates só com unidade UNKNOWN; allowed_values só em numérico; counted só em Count",
               "C05-RATE: grandeza de taxa (…Rate, Frequency ou unidade -PER-) exige rate_window",
               "C05-ENUM: enum só com escalar enum (e obrigatório nele); range só com numérico ou duração",
               "C05-UNIQ: atom_id único"])


# ------------------------------------------------------------------------------------------------- C06
P_ADDR = r"^(module\.SYM-[0-9a-f]{8,16}\.)*(data\.)?[a-z][a-z0-9_]*\.SYM-[0-9a-f]{8,16}(\[[^\]]+\])?$"


def c06() -> dict:
    sc = obj({"repo_id": c00("repo_id"), "family_id": c00("family_id"),
              "file": string(r"^(?!/)(?!.*\.\.)[^\s]+\.tf(\.json)?$"), "resource_address": string(P_ADDR),
              "resource_type": c00("resource_type"), "provider": c00("provider"),
              "attr_path": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+|\[[0-9]+\]|\[\"[^\"]+\"\])*$"),
              "term": c00("term")},
             ["repo_id", "family_id", "file", "resource_address", "resource_type", "provider", "attr_path", "term"])
    res = obj({"repo_id": c00("repo_id"), "family_id": c00("family_id"),
               "file": string(r"^(?!/)(?!.*\.\.)[^\s]+\.tf(\.json)?$"), "resource_address": string(P_ADDR),
               "resource_type": c00("resource_type"), "provider": c00("provider"), "n_attrs": integer(0),
               "has_count": boolean(), "has_for_each": boolean(), "module_depth": integer(0)},
              ["repo_id", "family_id", "file", "resource_address", "resource_type", "provider", "n_attrs",
               "has_count", "has_for_each", "module_depth"])
    usage = obj({"repo_id": c00("repo_id"), "family_id": c00("family_id"), "provider": c00("provider"),
                 "resource_type": c00("resource_type"), "atom_id": c00("atom_id"), "n_resources": integer(0),
                 "n_set": integer(0), "n_literal": integer(0), "n_symbolic": integer(0), "n_withheld": integer(0)},
                ["repo_id", "family_id", "provider", "resource_type", "n_resources", "n_set", "n_literal",
                 "n_symbolic", "n_withheld"])
    return contract_schema(
        "C06", "symbolic_config", "3.0.0", "configuração simbólica, recursos e uso", status="changed_v3",
        description="Configuração simbólica sem executar HCL: por valor, termo tipado (literal | símbolo de nome por "
                    "repositório | árvore de expressão | documento parseado com principais e identificadores "
                    "simbolizados | referência com tipo e endereço | retido); usage por repositório e família, sem "
                    "split (o split é C27). Nomes de recurso, de repositório e de módulo nunca em claro.",
        files=[file_kind("symbolic_config", "symbolic_config.jsonl", "jsonl", "symbolic_config", "record"),
               file_kind("resources", "resources.parquet", "parquet", "resource_row", "row",
                         "colunas: string, int64 e bool; nada além das declaradas"),
               file_kind("usage", "usage.jsonl", "jsonl", "usage", "record")],
        defs={"symbolic_config": sc, "resource_row": res, "usage": usage},
        producers=["CORPUS-{provider}", "HCL"],
        rules=["C06-SYM: endereços e referências só com símbolos SYM-… (nome por repositório), nunca o nome real",
               "C06-DOC: documento parseado simboliza todo principal e identificador (symbolized não vazio quando há)",
               "C06-WITHHELD: termo retido não tem valor nem hash",
               "C06-USAGE: n_literal + n_symbolic + n_withheld = n_set <= n_resources",
               "C06-NOSPLIT: nenhum campo de partição (o split é do C27)"])


# ------------------------------------------------------------------------------------------------- C07
def c07() -> dict:
    hp, hr = header("bo.universe/1", "C07", "3.0.0", module=True)
    uni = obj({**hp,
               "rule": obj({"rule_id": c00("rule_id"), "text": text(10)}, ["rule_id", "text"]),
               "closure": obj({"rule": text(10), "iterations": integer(0), "fixed_point": boolean()},
                              ["rule", "iterations", "fixed_point"]),
               "seed": integer(0), "split_ref": c00("file_ref"),
               "units": arr(obj({"unit_id": c00("unit_id"), "provider": c00("provider"), "domain": c00("domain"),
                                 "rule_id": c00("rule_id"), "in_universe": boolean(), "reason": text(3)},
                                ["unit_id", "provider", "domain", "rule_id", "in_universe"]), 1),
               "pilot_exposed": obj({}, extra=boolean(), propertyNames={"pattern": r"^CU-"}),
               "holdout": obj({"encrypted_sha256": c00("sha256"),
                               "path": string(r"^\$BO_DATA/SPLIT/sealed/\S+\.age$"), "cipher": const("age"),
                               "recipient_fingerprint": string(r"^age1[0-9a-z]{20,}$|^SHA256:[A-Za-z0-9+/=]{20,}$")},
                              ["encrypted_sha256", "path", "cipher", "recipient_fingerprint"])},
              hr + ["rule", "closure", "seed", "split_ref", "units", "pilot_exposed", "holdout"])
    return contract_schema(
        "C07", "universe", "3.0.0", "universo U de unidades", status="changed_v3",
        description="Unidades por provedor, domínio, regra, fecho, semente, split_ref (C27), pilot_exposed[unit] e o "
                    "sha do hold-out cifrado.",
        files=[file_kind("universe", "universe.json", "json", "universe", "document")], defs={"universe": uni},
        producers=["UNIVERSE", "SPLIT"],
        rules=["C07-UNITS: unit_id único", "C07-PILOT: pilot_exposed tem exatamente as unidades do universo",
               "C07-HOLDOUT: o hold-out só aparece cifrado (sha256 + caminho .age); nenhum id de teste em claro"])


# ------------------------------------------------------------------------------------------------- C08
def c08() -> dict:
    sub = obj({"nodes": arr(obj({"node_id": string(r"^n[0-9]+$"), "kind": enum("atom", "unit"),
                                 "ref": text(3), "role": text(2)}, ["node_id", "kind", "ref"]), 1),
               "edges": arr(obj({"from": string(r"^n[0-9]+$"), "to": string(r"^n[0-9]+$"),
                                 "kind": enum("reference", "attachment", "facet_of", "component_of")},
                                ["from", "to", "kind"])),
               "cross_facets": arr(string(r"^n[0-9]+$"))}, ["nodes", "edges", "cross_facets"])
    feats = obj({}, extra={"type": ["number", "string", "boolean"]}, propertyNames={"not": {"pattern": P_GOLDISH}})
    cand = obj({"candidate_id": string(r"^CAND-[A-Z]+-[A-Z]+-[0-9]{4,}$"), "pair": c00("pair"), "domain": c00("domain"),
                "subject_provider": c00("provider"), "object_provider": c00("provider"), "subject": sub, "object": sub,
                "concept": c00("concept_id"), "features": feats, "generated_by": c00("stable_id")},
               ["candidate_id", "pair", "domain", "subject_provider", "object_provider", "subject", "object",
                "concept", "features", "generated_by"],
               propertyNames={"not": {"pattern": P_GOLDISH}})
    return contract_schema(
        "C08", "candidates", "3.0.0", "candidatos como subgrafos", status="changed_v3",
        description="Candidato como subgrafo (nós, arestas de referência/anexação, facetas cruzadas), conceito do "
                    "glossário, features; sem campo de ouro.",
        files=[file_kind("candidates", "candidates.jsonl", "jsonl", "candidate", "record")], defs={"candidate": cand},
        producers=["CAND", "PILOT-{slice}-GLOSS"],
        rules=["C08-EDGES: arestas e facetas cruzadas apontam para nós do mesmo subgrafo",
               "C08-PAIR: os provedores dos lados são os do par (AWS=aws, GCP=google, AZ=azurerm, OCI=oci)",
               "C08-NOGOLD: nenhum campo de ouro (gold, truth, label, is_match, expected…), nem em features",
               "C08-UNIQ: candidate_id único"])


SPECS = {"C00": c00_spec, "C01": c01, "C02": c02, "C03": c03, "C04": c04, "C05": c05, "C06": c06, "C07": c07, "C08": c08}
