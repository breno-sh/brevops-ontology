"""C15–C23: resultados, manifesto de execução, comprovantes, números, unidades canônicas, glossário, vereditos,
sondas e rastro de tradução."""

from __future__ import annotations

from ._base import (BASE_URI, arr, boolean, c00, const, contract_schema, enum, file_kind, header, integer, local,
                    nullable, number, obj, string, text)
from .spec_b import C10_GUARD, SEMANTIC_RELATIONS

READINGS = ("field", "decision", "graph", "complete_unit")
AXES = ("representability", "transportability", "operational", "persistence", "behavior")
QUANTIFIERS = ("existential", "universal", "observed_fraction")
P_OLDTERM = r"(?i)(ceiling|teto)"
METRIC_ID = string(r"^M-[A-Za-z0-9_\-]+$")


# ------------------------------------------------------------------------------------------------- C15
def c15() -> dict:
    cov = obj({"lower": number(minimum=0, maximum=1), "upper": number(minimum=0, maximum=1),
               "est": nullable(number(minimum=0, maximum=1)), "n": integer(0)}, ["lower", "upper", "est", "n"])
    metric = obj({
        "metric_id": METRIC_ID, "name": text(3), "reading": enum(*READINGS), "axis": enum(*AXES),
        "quantifier": enum(*QUANTIFIERS), "operational_coverage": cov,
        "frame": obj({"ref": c00("file_ref"), "description": text(5)}, ["description"]),
        "inclusion": obj({"rule_id": c00("rule_id"), "text": text(5)}, ["rule_id", "text"]),
        "weights": obj({"scheme": enum("uniform", "frame", "inverse_probability", "custom"), "ref": c00("file_ref")},
                       ["scheme"], allOf=[{"if": {"properties": {"scheme": const("custom")}},
                                           "then": {"required": ["ref"]}}]),
        "joint_uncertainty": obj({"method": enum("bootstrap", "delta", "bayesian", "exact", "wilson", "none"),
                                  "level": number(exclusiveMinimum=0, exclusiveMaximum=1),
                                  "correlated_with": arr(METRIC_ID, unique=True)}, ["method"])},
        ["metric_id", "name", "reading", "axis", "quantifier", "operational_coverage", "frame", "inclusion",
         "weights", "joint_uncertainty"], propertyNames={"not": {"pattern": P_OLDTERM}})
    audit = obj({"n_absences": integer(0), "n_audited": integer(0), "method": text(5), "ref": c00("file_ref")},
                ["n_absences", "n_audited", "method"],
                description="ausências como auditoria separada (não entram no numerador nem no denominador)")
    hp, hr = header("bo.result/1", "C15", "3.0.0", module=True)
    res = obj({**hp, "metrics": arr(local("metric"), 1), "absence_audit": audit, "notes": text(1),
               "data": obj({}, extra=True, propertyNames={"not": {"pattern": P_OLDTERM}})},
              hr + ["metrics"], propertyNames={"not": {"pattern": P_OLDTERM}})
    sp, sr = header("bo.metrics_spec/1", "C15", "3.0.0", module=True)
    spec_item = obj({"metric_id": METRIC_ID, "definition": text(10), "reading": enum(*READINGS),
                     "axis": enum(*AXES), "quantifier": enum(*QUANTIFIERS), "frame": text(5), "inclusion": text(5),
                     "weights": enum("uniform", "frame", "inverse_probability", "custom"),
                     "uncertainty": enum("bootstrap", "delta", "bayesian", "exact", "wilson", "none")},
                    ["metric_id", "definition", "reading", "axis", "quantifier", "frame", "inclusion", "weights",
                     "uncertainty"], propertyNames={"not": {"pattern": P_OLDTERM}})
    spec = obj({**sp, "metrics": arr(spec_item, 1)}, sr + ["metrics"])
    summ = {"allOf": [{"$ref": f"{BASE_URI}C17/manifest_receipt.schema.json#/$defs/summary"},
                      {"required": ["results"]}],
            "description": "summary.json (C17) que carrega métricas C15 no bloco results"}
    return contract_schema(
        "C15", "results", "3.0.0", "resultados e especificação de métricas", status="changed_v3",
        description="operational_coverage{lower, upper, est, n} por leitura (field | decision | graph | complete_unit) e "
                    "por eixo (representability | transportability | operational | persistence | behavior); quantifier "
                    "(existential | universal | observed_fraction); frame, inclusion, weights; incerteza conjunta; "
                    "ausências como auditoria separada; o campo da v2 com o termo antigo saiu (nenhuma chave com ele).",
        files=[file_kind("metrics_spec", "metrics_spec.yaml", "yaml", "metrics_spec", "document"),
               file_kind("summary_results", "summary.json", "json", "summary_results", "document",
                         "summary.json catalogado como C15: C17 + bloco results"),
               file_kind("result", "*.json", "json", "result", "document")],
        defs={"metric": metric, "result": res, "metrics_spec": spec, "summary_results": summ},
        producers=["(quase todos: results/<ID>/*.json)"], consumers=["STATS", "MATRIX", "METRICSLIB"],
        rules=["C15-BOUNDS: lower <= est <= upper (est nulo só com n = 0)",
               "C15-OLDTERM: nenhuma chave com o termo antigo da v2",
               "C15-CORR: correlated_with só cita metric_id do mesmo documento",
               "C15-UNIQ: metric_id único"])


# ------------------------------------------------------------------------------------------------- C16
STAGES = ("intent", "creating", "created", "confirmed", "removal_requested", "removal_pending", "purge_scheduled",
          "absent")


def c16() -> dict:
    idc = obj({"identity_sha256": c00("sha256"), "checked_at": c00("datetime"), "matches_allowlist": boolean()},
              ["identity_sha256", "checked_at", "matches_allowlist"],
              description="hash da identidade efetiva (nunca o id da conta)")
    cost = obj({"amount": number(minimum=0), "currency": const("USD")}, ["amount", "currency"])
    intent = obj({
        "intent_id": string(r"^INT-[A-Za-z0-9_\-]+$"), "module": c00("stable_id"), "provider": c00("provider"),
        "batch_id": string(r"^B-[A-Za-z0-9_\-]+$"), "case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"),
        "resource_type": c00("resource_type"), "logical_name": string(r"^bo-[a-z0-9\-]{3,40}$"),
        "recorded_at": c00("datetime"), "effective_identity_check": idc, "purge_deadline": c00("datetime"),
        "max_residual_cost": cost, "tag_supported": boolean(), "ttl_supported": boolean(),
        "tags": obj({}, extra=string(r"^[A-Za-z0-9_.:\-]{1,63}$"), propertyNames={"pattern": r"^bo-[a-z\-]+$"}),
        "ttl_hours": integer(1)},
        ["intent_id", "module", "provider", "batch_id", "resource_type", "logical_name", "recorded_at",
         "effective_identity_check", "purge_deadline", "max_residual_cost", "tag_supported", "ttl_supported"],
        allOf=[{"if": {"properties": {"tag_supported": const(True)}}, "then": {"required": ["tags"]}},
               {"if": {"properties": {"tag_supported": const(False)}}, "then": {"not": {"required": ["tags"]}}},
               {"if": {"properties": {"ttl_supported": const(True)}}, "then": {"required": ["ttl_hours"]}}])
    run = obj({"run_id": string(r"^RUN-[A-Za-z0-9_\-]+$"), "intent_id": string(r"^INT-[A-Za-z0-9_\-]+$"),
               "stage": enum(*STAGES), "at": c00("datetime"), "visibility": enum("private", "public"),
               "provider_resource_ref": text(1), "effective_identity_check": idc,
               "residual_cost": cost, "note": text(3)},
              ["run_id", "intent_id", "stage", "at", "visibility"],
              allOf=[{"if": {"properties": {"visibility": const("public")}},
                      "then": {"not": {"required": ["provider_resource_ref"]}}},
                     {"if": {"properties": {"stage": {"enum": ["created", "confirmed"]}}},
                      "then": {"required": ["effective_identity_check"]}}],
              description="cópia pública: sem provider_resource_ref (redigida)")
    return contract_schema(
        "C16", "run_manifest", "3.0.0", "manifesto de intenção e de execução", status="changed_v3",
        description="Manifesto privado intenção → criação → confirmação → remoção (pedido, pendente, expurgo agendado, "
                    "ausente), com prazo de expurgo e custo residual máximo; effective_identity_check (hash da "
                    "identidade, nunca o id); cópia pública redigida; suporte a tag/TTL do tipo.",
        files=[file_kind("intent_manifest", "intent_manifest.jsonl", "jsonl", "intent", "record"),
               file_kind("run_manifest", "run_manifest.jsonl", "jsonl", "run", "record")],
        defs={"intent": intent, "run": run}, producers=["DEP-{provider}-A", "DEP-{provider}-B", "PROBE-{provider}",
                                                        "SMOKE-{provider}"],
        rules=["C16-ORDER: por intent_id, os estágios do run_manifest seguem a ordem intent < creating < created < "
               "confirmed < removal_requested < removal_pending < purge_scheduled < absent, com tempo crescente",
               "C16-INTENT: todo run cita um intent_id do intent_manifest irmão (a intenção vem ANTES da criação)",
               "C16-PUBLIC: a cópia pública não tem provider_resource_ref",
               "C16-IDENTITY: identidade conferida (matches_allowlist) antes de created"])


# ------------------------------------------------------------------------------------------------- C17
def c17() -> dict:
    inp = obj({"path": text(1), "kind": enum("file", "dir", "missing"), "sha256": c00("sha256")},
              ["path", "kind", "sha256"])
    ap = obj({"model_id": c00("model_id"), "brief_path": text(1), "brief_sha256": c00("sha256"),
              "params": obj({}, extra={"type": ["string", "number", "boolean"]}), "inputs": arr(inp),
              "recorded_at": c00("datetime")}, ["model_id", "brief_sha256", "params", "inputs"])
    hp, hr = header("bo.summary/1", "C17", "3.0.0", module=True)
    summ = obj({**hp, "agent_provenance": ap, "sources": arr(c00("source_license")), "notes": text(1),
                "results": arr({"$ref": f"{BASE_URI}C15/results.schema.json#/$defs/metric"}, 1)},
               hr + ["agent_provenance", "sources"], extra=True)
    art = obj({"path": c00("portable_path"), "kind": enum("file", "dir"), "sha256": c00("sha256"),
               "files": obj({}, extra=c00("sha256")), "producers": arr(c00("stable_id")),
               "via": c00("stable_id")}, ["path", "kind", "sha256"])
    rp, rr = header("bo.freeze_receipt/1", "C17", "3.0.0", generated=False)
    rec = obj({**rp, "name": string(r"^[A-Z][A-Z0-9_\-]*$"), "owner": text(2), "created_at": c00("datetime"),
               "note": {"type": "string"},
               "git": obj({"commit": string(r"^[0-9a-f]{40}$"), "tag": string(r"^bo-freeze-[A-Z][A-Z0-9_\-]*$")},
                          ["commit", "tag"]),
               "modules": arr(c00("stable_id")), "artifacts": arr(art, 1), "transitive_inputs": arr(art),
               "digest": c00("sha256"),
               "ots": obj({"status": enum("STAMPED", "PENDING", "DISABLED"), "digest": c00("sha256"),
                           "file": text(1), "reason": text(1), "at": c00("datetime")}, ["status"],
                          allOf=[{"if": {"properties": {"status": const("STAMPED")}},
                                  "then": {"required": ["file", "digest"]}},
                                 {"if": {"properties": {"status": {"enum": ["PENDING", "DISABLED"]}}},
                                  "then": {"required": ["reason"]}}])},
              rr + ["name", "owner", "created_at", "git", "modules", "artifacts", "transitive_inputs", "digest", "ots"])
    return contract_schema(
        "C17", "manifest_receipt", "3.0.0", "MANIFEST.sha256, summary.json e freeze_receipt.json", status="changed_v3",
        description="Hashes transitivos das entradas; comprovante de congelamento (dono, hora, tag, carimbo); "
                    "sources[{uri, licença, transformação}]; agent_provenance{model_id, brief_sha256, params, inputs}. "
                    "Formato do REPO (CONVENTIONS.html §7), agora com schema.",
        files=[file_kind("manifest", "MANIFEST.sha256", "sha256_manifest", None, "line",
                         "linhas '<sha256>  <caminho>' (formato do shasum -a 256)"),
               file_kind("summary", "summary.json", "json", "summary", "document",
                         "blocos extras do módulo são permitidos; results, quando há, é C15"),
               file_kind("freeze_receipt", "freeze_receipt.json", "json", "freeze_receipt", "document")],
        defs={"summary": summ, "freeze_receipt": rec}, producers=["(todo módulo)"], consumers=["consume_check"],
        rules=["C17-MANIFEST: toda linha é '<sha256 minúsculo>  <caminho>', sem caminho repetido, sem reticências",
               "C17-DIGEST: digest do comprovante = sha256 do JSON canônico sem digest e ots (bo.repo.receipts)",
               "C17-MODEL: model_id do agente nunca é Fable (regra do projeto: Opus)",
               "C17-SOURCES: toda fonte tem uri, licença e transformação"])


# ------------------------------------------------------------------------------------------------- C18
CATEGORY_PREFIX = {"persistence": "Pers", "observation": "Obs", "coverage": "Cov", "other": "Num"}


def c18() -> dict:
    macro = obj({"value": {"type": ["number", "string"]}, "display": text(1), "file": c00("portable_path"),
                 "sha256": c00("sha256"), "pointer": string(r"^(/[^/]*)+$"),
                 "category": enum(*CATEGORY_PREFIX)}, ["value", "display", "file", "sha256", "pointer", "category"])
    hp, hr = header("bo.numbers/1", "C18", "2.0.0", module=True)
    doc = obj({**hp, "macros": obj({}, extra=local("macro"),
                                   propertyNames={"pattern": r"^(Pers|Obs|Cov|Num)[A-Z][A-Za-z]*$"}, minProperties=1)},
              hr + ["macros"])
    return contract_schema(
        "C18", "numbers", "2.0.0", "números do artigo", status="unchanged_v3",
        description="Macro → {valor, arquivo, sha, ponteiro}; prefixos distintos para persistência (Pers), observação "
                    "(Obs) e cobertura (Cov); numbers.tex é gerado de numbers.json e tem de bater com ele.",
        files=[file_kind("numbers", "numbers.json", "json", "numbers", "document"),
               file_kind("numbers_tex", "numbers.tex", "tex_macros", None, "line",
                         "uma linha \\newcommand{\\Nome}{exibição} por macro; comentários com %")],
        defs={"macro": macro, "numbers": doc}, producers=["STATS"], consumers=["PAPER-RESULTS", "ARTIFACT"],
        rules=["C18-PREFIX: o prefixo do nome é o da categoria (Pers, Obs, Cov, Num)",
               "C18-TEX: numbers.tex tem exatamente as macros de numbers.json, com a mesma exibição",
               "C18-NOLETTERS: nome de macro só com letras (LaTeX)"])


# ------------------------------------------------------------------------------------------------- C19
def c19() -> dict:
    ctl = obj({"kind": enum("self", "parent", "provider", "external", "UNKNOWN"), "ref": text(1)}, ["kind"])
    unit = obj({
        "unit_id": c00("unit_id"), "provider": c00("provider"),
        "kind": enum("ENTITY", "COMPONENT", "FACET", "BINDING", "UNKNOWN"),
        "layers": obj({"api_resource": obj({"service": text(1), "resource": text(1)}, ["service", "resource"]),
                       "terraform": obj({"resource_type": c00("resource_type"),
                                         "block_path": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")},
                                        ["resource_type"]),
                       "domain_unit": text(2)}, ["terraform", "domain_unit"]),
        "identity": obj({"evidence": arr(c00("evidence_item")), "key_fields": arr(text(1), unique=True),
                         "anonymous": boolean(), "occurrence_key": arr(text(1), unique=True)},
                        ["evidence", "key_fields", "anonymous", "occurrence_key"]),
        "lifecycle_controller": ctl, "owner": ctl,
        "effective_scope": obj({"kind": enum("self", "parent", "container", "global", "UNKNOWN"), "ref": text(1)},
                               ["kind"]),
        "evidence": arr(c00("evidence_item")), "rule_applied": c00("rule_id"),
        "missing_evidence": arr(enum("identity", "lifecycle_controller", "owner", "effective_scope", "api_resource"),
                                unique=True)},
        ["unit_id", "provider", "kind", "layers", "identity", "lifecycle_controller", "owner", "effective_scope",
         "evidence", "rule_applied", "missing_evidence"],
        allOf=[{"if": {"properties": {"kind": const("UNKNOWN")}},
                "then": {"properties": {"missing_evidence": {"minItems": 1}}},
                "else": {"properties": {"missing_evidence": {"maxItems": 0}, "evidence": {"minItems": 1}}}},
               {"if": {"properties": {"identity": {"properties": {"anonymous": const(True)}}}},
                "then": {"properties": {"identity": {"properties": {"occurrence_key": {"minItems": 1}}}}}}])
    atom = obj({"atom_id": c00("atom_id"), "unit_id": c00("unit_id"),
                "path_in_unit": string(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$"),
                "role": enum("CONFIG", "IDENTIFIER", "NAME", "TAG", "REFERENCE", "TIMESTAMP", "SECRET")},
               ["atom_id", "unit_id", "path_in_unit"])
    return contract_schema(
        "C19", "canonical_units", "3.0.0", "unidades e átomos canônicos", status="changed_v3",
        description="Unidade: kind (ENTITY | COMPONENT | FACET | BINDING | UNKNOWN), identity{evidência, campos-chave, "
                    "anonymous, occurrence_key}, lifecycle_controller, owner, effective_scope, evidence[], rule_applied, "
                    "missing_evidence[]; ligação unidade canônica ↔ recurso/bloco Terraform ↔ recurso de API. Sem "
                    "evidência, UNKNOWN (nunca 'entidade' por omissão); nada depende de quantos elementos o bloco aceita.",
        files=[file_kind("canonical_units", "canonical_units.jsonl", "jsonl", "canonical_unit", "record"),
               file_kind("canonical_atoms", "canonical_atoms.jsonl", "jsonl", "canonical_atom", "record")],
        defs={"canonical_unit": unit, "canonical_atom": atom},
        producers=["DECOMPOSE", "GRAIN-REPRO", "PILOT-{slice}-GLOSS"],
        rules=["C19-UNKNOWN: kind = UNKNOWN ⇔ missing_evidence não vazio",
               "C19-ANON: componente anônimo (bloco sem identidade) tem occurrence_key",
               "C19-LINK: canonical_atoms citam unit_id do canonical_units irmão",
               "C19-UNIQ: unit_id único; atom_id em uma unidade só"])


# ------------------------------------------------------------------------------------------------- C20
def c20() -> dict:
    concept = obj({"concept_id": c00("concept_id"), "label": text(2), "definition": text(10), "domain": c00("domain"),
                   "quantity_kind": c00("quantity_kind"), "unit": c00("unit_qudt"),
                   "status": enum("active", "deprecated", "merged", "split"),
                   "replaced_by": arr(c00("concept_id"), 1), "evidence_state": c00("evidence_state")},
                  ["concept_id", "label", "definition", "domain", "quantity_kind", "status", "evidence_state"],
                  allOf=[{"if": {"properties": {"status": {"enum": ["merged", "split", "deprecated"]}}},
                          "then": {"required": ["replaced_by"]}},
                         {"if": {"properties": {"quantity_kind": const("NOT_APPLICABLE")}},
                          "then": {"properties": {"unit": const("NOT_APPLICABLE")}}}])
    claim = obj({
        "claim_id": c00("claim_id"), "claim_version_id": c00("claim_version_id"), "event_id": c00("event_id"),
        "supersedes": c00("claim_version_id"), "concept_id": c00("concept_id"), "atom_id": c00("atom_id"),
        "sentence": text(10), "context": text(5),
        "counterexample_search": obj({"query": text(3), "found": boolean(), "result": text(3)},
                                     ["query", "found", "result"]),
        "extraction_method": enum("parser", "regex", "table", "manual", "model"),
        "evidence_level": c00("evidence_level"), "model_id": c00("model_id"), "source": c00("doc_source"),
        "evidence_state": c00("evidence_state"), "recorded_at": c00("datetime")},
        ["claim_id", "claim_version_id", "event_id", "concept_id", "atom_id", "sentence", "context",
         "counterexample_search", "extraction_method", "evidence_level", "evidence_state", "recorded_at"],
        allOf=[{"if": {"properties": {"evidence_level": const("interpreted")}}, "then": {"required": ["model_id"]}},
               {"if": {"properties": {"extraction_method": const("model")}},
                "then": {"properties": {"evidence_level": const("interpreted")}}},
               {"if": {"properties": {"evidence_state": {"enum": ["DOC_SUPPORTED"]}}}, "then": {"required": ["source"]}}],
        description="âncora como alegação: claim_id imutável; cada versão tem claim_version_id e event_id próprios")
    audit = obj({"audit_id": string(r"^GA-[A-Za-z0-9_\-]+$"), "claim_id": c00("claim_id"),
                 "claim_version_id": c00("claim_version_id"), "event_id": c00("event_id"),
                 "check": enum("evidence_support", "same_quantity_distinction", "indirect_anchor", "no_test_in_train",
                               "counterexample"),
                 "result": enum("pass", "fail", "unresolved"), "evidence_state_before": c00("evidence_state"),
                 "evidence_state_after": c00("evidence_state"), "auditor": c00("stable_id"), "at": c00("datetime"),
                 "note": text(3)},
                ["audit_id", "claim_id", "claim_version_id", "event_id", "check", "result", "evidence_state_before",
                 "evidence_state_after", "auditor", "at"])
    return contract_schema(
        "C20", "glossary", "3.0.0", "glossário, âncoras como alegações e auditoria", status="changed_v3",
        description="Conceito com grandeza (IRI | NOT_APPLICABLE | UNKNOWN); âncora como alegação com sentença, contexto, "
                    "contraexemplo procurado, método de extração e evidence_state (STRUCTURALLY_VALID | DOC_SUPPORTED | "
                    "PERSISTENCE_VERIFIED | OBSERVATION_TESTED | UNRESOLVED).",
        files=[file_kind("glossary", "glossary.jsonl", "jsonl", "concept", "record"),
               file_kind("claims", "claims.jsonl", "jsonl", "anchor_claim", "record"),
               file_kind("glossary_audit", "glossary_audit.jsonl", "jsonl", "audit", "record")],
        defs={"concept": concept, "anchor_claim": claim, "audit": audit},
        producers=["GLOSSARY-{domain}", "GLOSSARY-AUDIT", "GLOSSARY-FREEZE", "PILOT-{slice}-GLOSS"],
        rules=["C20-IDS: claim_version_id = <claim_id>@n, únicos; event_id único por versão; supersedes = versão "
               "anterior da mesma alegação (claim_id nunca muda entre versões)",
               "C20-NA: grandeza NOT_APPLICABLE não tem unidade; UNKNOWN ≠ NOT_APPLICABLE",
               "C20-AUDIT: a auditoria cita uma versão existente quando claims.jsonl é irmão",
               "C20-UNIQ: concept_id único"])


# ------------------------------------------------------------------------------------------------- C21
def c21() -> dict:
    v = obj({"claim_id": c00("claim_id"), "claim_version_id": c00("claim_version_id"), "event_id": c00("event_id"),
             "verdict": c00("verdict"), "rules": arr(c00("rule_id"), unique=True), "cycle": integer(1),
             "composition_used": nullable(arr(c00("claim_id"), 2)), "arbiter_sha256": c00("sha256"),
             "decided_at": c00("datetime"), "detail": text(3)},
            ["claim_id", "claim_version_id", "event_id", "verdict", "rules", "cycle", "composition_used",
             "arbiter_sha256", "decided_at"],
            allOf=[{"if": {"properties": {"verdict": {"enum": ["REFUTED_BY_RULE", "UNPROVEN", "CONTESTED",
                                                                 "AMBIGUOUS"]}}},
                    "then": {"properties": {"rules": {"minItems": 1}}}}])
    return contract_schema(
        "C21", "verdicts", "3.0.0", "vereditos do árbitro", status="changed_v3",
        description="Por claim_id: OK | REFUTED_BY_RULE | UNPROVEN | CONTESTED | AMBIGUOUS, regra, ciclo, composição "
                    "usada, sha do árbitro.",
        files=[file_kind("verdicts", "verdicts.jsonl", "jsonl", "verdict", "record")], defs={"verdict": v},
        producers=["ARBITER", "PILOT-{slice}-MAP"],
        rules=["C21-RULES: veredito diferente de OK cita a(s) regra(s)",
               "C21-VER: claim_version_id é versão do claim_id",
               "C21-UNIQ: um veredito por (claim_version_id, cycle)"])


# ------------------------------------------------------------------------------------------------- C22
def c22() -> dict:
    pt = obj({
        "probe_type": enum("object_versioning", "object_lifecycle", "item_ttl", "queue_retention", "rate_limit",
                           "log_retention"),
        "preconditions": arr(text(5), 1), "negative_control": obj({"description": text(5), "expected": text(3)},
                                                                   ["description", "expected"]),
        "repetitions": integer(1), "tolerance": obj({"kind": enum("absolute", "relative", "exact"),
                                                     "value": number(minimum=0)}, ["kind", "value"]),
        "polling": obj({"interval": c00("xsd_duration"), "max_wait": c00("xsd_duration")}, ["interval", "max_wait"]),
        "window": obj({"duration": c00("xsd_duration"), "margin_over_ttl": c00("xsd_duration")},
                      ["duration", "margin_over_ttl"]),
        "cost_limit": obj({"amount": number(minimum=0), "currency": const("USD")}, ["amount", "currency"]),
        "validated_support": arr(obj({"provider": c00("provider"), "status": enum("validated", "unsupported", "unknown"),
                                      "evidence": arr(c00("evidence_item"))}, ["provider", "status", "evidence"]), 1)},
        ["probe_type", "preconditions", "negative_control", "repetitions", "tolerance", "polling", "window",
         "cost_limit", "validated_support"])
    hp, hr = header("bo.probe_types/1", "C22", "3.0.0", module=True)
    pdoc = obj({**hp, "protocol_version": c00("semver"), "probe_types": arr(local("probe_type"), 1)},
               hr + ["protocol_version", "probe_types"])
    obs = obj({"observation_id": string(r"^OBS-[A-Za-z0-9_\-]+$"), "pair_case_id": string(r"^PC-[A-Za-z0-9_\-]+$"),
               "side": enum("A", "B"), "provider": c00("provider"), "probe_type": text(3), "timestamp": c00("datetime"),
               "protocol_version": c00("semver"),
               "counts": obj({"attempts": integer(0), "observed": integer(0), "not_observed": integer(0),
                              "errors": integer(0)}, ["attempts", "observed", "not_observed", "errors"]),
               "negative_control_ok": boolean()},
              ["observation_id", "pair_case_id", "side", "provider", "probe_type", "timestamp", "protocol_version",
               "counts", "negative_control_ok"],
              description="observação local de um lado: nunca traz julgamento de comportamento (isso é do PROBE-JOIN)")
    behavior = {"allOf": [c00("outcome"), {"properties": {"axis": const("behavior")}}]}
    pj = obj({"judgement_id": string(r"^PJ-[A-Za-z0-9_\-]+$"), "pair_case_id": string(r"^PC-[A-Za-z0-9_\-]+$"),
              "case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"), "group_id": string(r"^(GRP|G)-[A-Za-z0-9_\-]+$"),
              "observations": obj({"A": string(r"^OBS-[A-Za-z0-9_\-]+$"), "B": string(r"^OBS-[A-Za-z0-9_\-]+$")},
                                  ["A", "B"]),
              "outcome": behavior, "protocol_version": c00("semver"), "judged_by": const("PROBE-JOIN"),
              "judged_at": c00("datetime")},
             ["judgement_id", "pair_case_id", "case_id", "group_id", "observations", "outcome", "protocol_version",
              "judged_by", "judged_at"])
    return contract_schema(
        "C22", "probes", "3.0.0", "tipos de sonda, observações e julgamentos pareados", status="changed_v3",
        description="Tipo: pré-condições, controle negativo, repetição, tolerância, polling, janela e margem sobre o TTL, "
                    "limite de custo, suporte validado. Observação local: pair_case_id, side, timestamp, "
                    "protocol_version, contagens. Julgamento pareado (só o PROBE-JOIN): união discriminada do C00 com "
                    "axis = behavior.",
        files=[file_kind("probe_types", "probe_types.yaml", "yaml", "probe_types", "document"),
               file_kind("observations", "observations.jsonl", "jsonl", "observation", "record"),
               file_kind("pair_judgements", "pair_judgements.jsonl", "jsonl", "pair_judgement", "record")],
        defs={"probe_type": pt, "probe_types": pdoc, "observation": obs, "pair_judgement": pj},
        producers=["PROBEKIT", "PREREG", "PROBE-{provider}", "PROBE-JOIN"],
        rules=["C22-UNION: outcome do julgamento é a união do C00 com axis = behavior",
               "C22-COUNTS: observed + not_observed + errors = attempts",
               "C22-PAIR: as duas observações citadas são do mesmo pair_case_id, lados A e B, mesmo protocolo",
               "C22-JOIN: só o PROBE-JOIN julga (judged_by)"])


# ------------------------------------------------------------------------------------------------- C23
def c23() -> dict:
    tr = obj({
        "trace_id": string(r"^TR-[A-Za-z0-9_\-]+$"), "case_id": string(r"^CASE-[A-Za-z0-9_\-]+$"),
        "claim_id": c00("claim_id"),
        "input": obj({"atom_id": c00("atom_id"), "term": c00("term")}, ["atom_id", "term"]),
        "individual": c00("iri"), "inferred_classes": arr(c00("iri")), "property": c00("iri"),
        "realization_id": string(r"^[A-Za-z0-9_.:\-]+$"),
        "transform": obj({"name": string(r"^[a-z][a-z0-9_]*$"), "params": {"type": "object"}}, ["name"]),
        "guard_evaluated": obj({"guard": C10_GUARD, "result": enum("TRUE", "FALSE", "INDETERMINATE")},
                               ["guard", "result"]),
        "justifying_axioms": arr(text(3)), "consulted_metadata": arr(text(3)), "control": enum("c1", "c2", "c3"),
        "output": obj({"atom_id": c00("atom_id"), "term": c00("term")}, ["atom_id", "term"]),
        "result": enum("carried", "omitted", "blocked"), "block_code": c00("block_code"), "rule": text(2),
        "detail": text(3)},
        ["trace_id", "input", "justifying_axioms", "consulted_metadata", "control", "result"],
        allOf=[{"if": {"properties": {"result": const("carried")}},
                "then": {"required": ["output", "property"], "not": {"required": ["block_code"]}}},
               {"if": {"properties": {"result": const("blocked")}},
                "then": {"required": ["block_code"], "not": {"required": ["output"]}}},
               {"if": {"properties": {"result": const("omitted")}},
                "then": {"not": {"anyOf": [{"required": ["output"]}, {"required": ["block_code"]}]}}},
               {"if": {"properties": {"block_code": {"enum": ["CONDITION_FALSE", "CONDITION_INDETERMINATE"]}},
                       "required": ["block_code"]},
                "then": {"required": ["guard_evaluated"]}}])
    return contract_schema(
        "C23", "translation_trace", "3.0.0", "rastro de tradução por valor", status="changed_v3",
        description="Por valor: entrada, indivíduo, classes inferidas, propriedade, realização, transformação, guarda "
                    "avaliada, justifying_axioms separados de consulted_metadata, controle (c1 | c2 | c3 = c1_table | "
                    "c2_taxonomy | c3_full), saída e resultado: carried, omitted (opcional sem valor) ou blocked com "
                    "código — os 13 do plano, UNKNOWN_INPUT (obrigatório no destino sem valor na origem, T-ABSENCE) e "
                    "REFUTED_BY_RULE (alegação refutada, proposta do SEMANTICS).",
        files=[file_kind("translation_trace", "translation_trace.jsonl", "jsonl", "trace", "record")],
        defs={"trace": tr}, producers=["TRANSLATOR", "PAIRWISE", "PILOT-{slice}-E2E"],
        rules=["C23-RESULT: carried tem saída e nenhum código; blocked tem código e nenhuma saída",
               "C23-GUARD: CONDITION_FALSE/INDETERMINATE vêm com a guarda avaliada e o resultado coerente",
               "C23-SEP: justifying_axioms e consulted_metadata não se sobrepõem",
               "C23-UNIQ: trace_id único"])


SPECS = {"C15": c15, "C16": c16, "C17": c17, "C18": c18, "C19": c19, "C20": c20, "C21": c21, "C22": c22, "C23": c23}
