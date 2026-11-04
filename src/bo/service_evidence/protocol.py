"""Tabela de suporte de protocolo por tipo de sonda e provedor ($BO_DATA/SERVICE-EVIDENCE/protocol_support.jsonl).

Consumida pelo PROBEKIT ("validar que o protocolo e o SKU são suportados antes do sorteio") e pelo SAFETY.
Não há contrato C* para este arquivo; o formato está em SCHEMA abaixo e é conferido pelo gate do módulo.

Por linha (probe_type × provedor):
  status       documented_supported | documented_unsupported | unknown (só pela documentação fixada; nada aqui
               foi lido de volta de nuvem: validated = false sempre)
  requirement  o que o probe_types.yaml (PREREG) pede para o tipo de sonda, e o limiar numérico quando há
  documented   o que a frase citada diz (mínimo com unidade, ou os quatro campos de limite de taxa)
  evidence     itens C00 evidence_item: frases PUBLICADAS da página fixada (doc_source), mais um item
               INTERPRETADO com a escolha do tipo/atributo (essa escolha é do modelo, não da documentação)
Regra de status: com limiar e mínimo documentado, supported se mínimo <= limiar, senão unsupported; sem limiar,
supported se as frases resolvem; rate_limit exige janela, chave, rajada e mecanismo documentados; faltou algo,
unknown com o motivo.
"""

from __future__ import annotations

import jsonschema

from . import common

R = "website/docs/r/"
DAY = 86400

# limiar em segundos tirado das pré-condições do probe_types.yaml (PREREG, C22)
REQUIREMENTS = {
    "object_versioning": ("atributo que liga o versionamento do contêiner", None),
    "object_lifecycle": ("regra de ciclo de vida com idade mínima de 1 dia onde a unidade é dia", DAY),
    "item_ttl": ("TTL habilitável num atributo declarado da tabela ou coleção", None),
    "queue_retention": ("retenção mínima da fila <= 24 h (senão PROTOCOL_UNSUPPORTED)", DAY),
    "rate_limit": ("limite de taxa com JANELA, CHAVE, RAJADA e MECANISMO declarados", None),
    "log_retention": ("retenção mínima de log <= 3 dias (senão PROTOCOL_UNSUPPORTED)", 3 * DAY),
}

# (probe_type, provedor, tipo, atributos, citações [(arquivo, trecho, frase|None)], documented, motivo se unknown)
ENTRIES = [
    ("object_versioning", "aws", "aws_s3_bucket_versioning", ["versioning_configuration.status"],
     [(R + "s3_bucket_versioning.html.markdown", "Versioning state of the bucket", None)], {}, None),
    ("object_versioning", "google", "google_storage_bucket", ["versioning.enabled"],
     [(R + "storage_bucket.html.markdown", "versioning is fully enabled for this bucket", None)], {}, None),
    ("object_versioning", "azurerm", "azurerm_storage_account", ["blob_properties.versioning_enabled"],
     [(R + "storage_account.html.markdown", "Is versioning enabled?", None)], {}, None),
    ("object_versioning", "oci", "oci_objectstorage_bucket", ["versioning"],
     [(R + "objectstorage_bucket.html.markdown", "Set the versioning status on the bucket.", None)], {}, None),

    ("object_lifecycle", "aws", "aws_s3_bucket_lifecycle_configuration", ["rule.expiration.days"],
     [(R + "s3_bucket_lifecycle_configuration.html.markdown", "Lifetime, in days, of the objects", None)],
     {"min": {"value": 1, "unit": "day", "seconds": DAY, "reading": "non-zero positive integer"}}, None),
    ("object_lifecycle", "google", "google_storage_bucket", ["lifecycle_rule.condition.age",
                                                             "lifecycle_rule.action.type"],
     [(R + "storage_bucket.html.markdown", "Minimum age of an object in days to satisfy this condition", None)],
     {"min": {"value": 0, "unit": "day", "seconds": 0, "reading": "0 is settable with send_age_if_zero"}}, None),
    ("object_lifecycle", "azurerm", "azurerm_storage_management_policy",
     ["rule.actions.base_blob.delete_after_days_since_creation_greater_than"],
     [(R + "storage_management_policy.html.markdown", "The age in days after creation to delete the blob", None)],
     {"min": {"value": 0, "unit": "day", "seconds": 0, "reading": "Must be between `0` and `99999`"}}, None),
    ("object_lifecycle", "oci", "oci_objectstorage_object_lifecycle_policy",
     ["rules.time_amount", "rules.time_unit", "rules.action"],
     [(R + "objectstorage_object_lifecycle_policy.html.markdown", "Specifies the age of objects to apply the rule",
       None)], {}, "a frase não diz o valor mínimo de time_amount"),

    ("item_ttl", "aws", "aws_dynamodb_table", ["ttl.enabled", "ttl.attribute_name"],
     [(R + "dynamodb_table.html.markdown", "Name of the table attribute to store the TTL timestamp in", None)],
     {}, None),
    ("item_ttl", "google", "google_firestore_field", ["ttl_config"],
     [(R + "firestore_field.html.markdown", "The state of TTL (time-to-live) configuration", None)], {}, None),
    ("item_ttl", "azurerm", "azurerm_cosmosdb_sql_container", ["default_ttl"],
     [(R + "cosmosdb_sql_container.html.markdown", "The default time to live of SQL container", None)], {}, None),
    ("item_ttl", "oci", "oci_nosql_table", [],
     [], {}, "nenhum atributo de TTL no schema fixado do tipo; a página não descreve TTL por atributo"),

    ("queue_retention", "aws", "aws_sqs_queue", ["message_retention_seconds"],
     [(R + "sqs_queue.html.markdown", "Number of seconds Amazon SQS retains a message", None)],
     {"min": {"value": 60, "unit": "s", "seconds": 60, "reading": "from 60 (1 minute) to 1209600 (14 days)"}}, None),
    ("queue_retention", "google", "google_pubsub_subscription", ["message_retention_duration"],
     [(R + "pubsub_subscription.html.markdown", "subscriptions.seek can be done. Defaults to 7 days. Cannot be more",
       "Cannot be more than 31 days (`\"2678400s\"`) or less than 10 minutes (`\"600s\"`).")],
     {"min": {"value": 600, "unit": "s", "seconds": 600, "reading": "less than 10 minutes is not allowed"}}, None),
    ("queue_retention", "azurerm", "azurerm_servicebus_queue", ["default_message_ttl"],
     [(R + "servicebus_queue.html.markdown", "The ISO 8601 timespan duration of the TTL of messages", None)], {},
     "a frase não diz o mínimo; TTL de mensagem não é a retenção da fila"),
    ("queue_retention", "oci", "oci_queue_queue", ["retention_in_seconds"],
     [(R + "queue_queue.html.markdown", "* `retention_in_seconds` - (Optional)", None)], {},
     "a frase não diz o mínimo"),

    ("rate_limit", "aws", "aws_api_gateway_usage_plan", ["throttle_settings.rate_limit",
                                                         "throttle_settings.burst_limit"],
     [(R + "api_gateway_usage_plan.html.markdown", "API request steady-state rate limit", None),
      (R + "api_gateway_usage_plan.html.markdown", "API request burst limit", None)],
     {"window": None, "key": None, "burst": "throttle_settings.burst_limit", "mechanism": "token bucket"},
     "janela (unidade do rate_limit) e chave não estão nas frases"),
    ("rate_limit", "google", "google_compute_security_policy",
     ["rule.rate_limit_options.rate_limit_threshold.count", "rule.rate_limit_options.rate_limit_threshold.interval_sec",
      "rule.rate_limit_options.enforce_on_key_type"],
     [(R + "compute_security_policy.html.markdown", "Interval over which the threshold is computed", None),
      (R + "compute_security_policy.html.markdown", "Determines the key to enforce the `rate_limit_threshold` on",
       None)],
     {"window": "rate_limit_threshold.interval_sec", "key": "enforce_on_key_type", "burst": None,
      "mechanism": None}, "rajada e mecanismo não estão nas frases"),
    ("rate_limit", "azurerm", "azurerm_api_management_api_policy", ["xml_content"],
     [], {"window": None, "key": None, "burst": None, "mechanism": None},
     "o limite fica num XML de política livre; o schema e a página não o estruturam"),
    ("rate_limit", "oci", "oci_apigateway_deployment",
     ["specification.request_policies.rate_limiting.rate_in_requests_per_second",
      "specification.request_policies.rate_limiting.rate_key"],
     [(R + "apigateway_deployment.html.markdown", "The maximum number of requests per second to allow", None),
      (R + "apigateway_deployment.html.markdown", "The key used to group requests together", None)],
     {"window": "per second", "key": "rate_key", "burst": None, "mechanism": None},
     "rajada e mecanismo não estão nas frases"),

    ("log_retention", "aws", "aws_cloudwatch_log_group", ["retention_in_days"],
     [(R + "cloudwatch_log_group.html.markdown", "* `retention_in_days` - (Optional) Specifies the number of days",
       "Specifies the number of days you want to retain log events in the specified log group. Possible values "
       "are: 1, 3, 5, 7, 14, 30")],
     {"min": {"value": 1, "unit": "day", "seconds": DAY, "reading": "Possible values are: 1, 3, 5, ..."}}, None),
    ("log_retention", "google", "google_logging_project_bucket_config", ["retention_days"],
     [(R + "logging_project_bucket_config.html.markdown", "The minimum retention period is 1 day", None)],
     {"min": {"value": 1, "unit": "day", "seconds": DAY, "reading": "The minimum retention period is 1 day"}}, None),
    ("log_retention", "azurerm", "azurerm_log_analytics_workspace", ["retention_in_days"],
     [(R + "log_analytics_workspace.html.markdown", "The workspace data retention in days", None)],
     {"min": {"value": 30, "unit": "day", "seconds": 30 * DAY, "reading": "between `30` and `730`"}}, None),
    ("log_retention", "oci", "oci_logging_log", ["retention_duration"],
     [(R + "logging_log.html.markdown", "Log retention duration in 30-day increments", None)],
     {"min": {"value": 30, "unit": "day", "seconds": 30 * DAY, "reading": "30-day increments (30, 60, ...)"}}, None),
]

EVID = {"type": "object", "properties": {
    "level": {"enum": ["published", "derived", "interpreted"]}, "ref": {"type": "string"},
    "doc": {"type": "object"}, "citation": {"type": "object"}, "model_id": {"type": "string"},
    "note": {"type": "string", "minLength": 3}},
    "required": ["level"], "additionalProperties": False}

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SERVICE-EVIDENCE protocol_support 1.0.0 (sem contrato C*; formato do módulo)",
    "type": "object",
    "properties": {
        "schema": {"const": "bo.protocol_support/1"},
        "probe_type": {"enum": sorted(REQUIREMENTS)},
        "provider": {"enum": list(common.PROVIDERS)},
        "pin": {"type": "object", "properties": {"provider_version": {"type": "string"}},
                "required": ["provider_version"], "additionalProperties": False},
        "terraform_resource_type": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "attributes": {"type": "array", "items": {"type": "string"}},
        "status": {"enum": ["documented_supported", "documented_unsupported", "unknown"]},
        "requirement": {"type": "object", "properties": {"text": {"type": "string"},
                                                         "max_seconds": {"type": ["integer", "null"]}},
                        "required": ["text", "max_seconds"], "additionalProperties": False},
        "documented": {"type": "object"},
        "reason": {"type": "string", "minLength": 3},
        "evidence": {"type": "array", "items": EVID, "minItems": 1},
        "validated": {"const": False},
    },
    "required": ["schema", "probe_type", "provider", "pin", "terraform_resource_type", "attributes", "status",
                 "requirement", "documented", "evidence", "validated"],
    "additionalProperties": False,
}

SELECTION_NOTE = ("escolha do tipo e dos atributos que realizam a sonda feita pelo modelo; o valor documentado é "
                  "lido das frases publicadas citadas")


def rows() -> tuple[list[dict], list[str]]:
    from . import sources
    out, missing = [], []
    for probe, p, T, attrs, cites, documented, reason in ENTRIES:
        req_text, limit = REQUIREMENTS[probe]
        ev, ok = [], True
        if T not in set(sources.types(p)):
            missing.append(f"{probe}:{p}:{T} fora do schema fixado")
            ok = False
        for rel, needle, sentence in cites:
            ln = common.find_line(p, rel, needle)
            if ln is None:
                missing.append(f"{probe}:{p}:{T} frase não achada: {needle[:40]}")
                ok = False
                continue
            d = common.doc_cite(p, rel, ln, sentence)
            if common.resolve_doc(p, d) is not None:
                missing.append(f"{probe}:{p}:{T} frase não resolve: {needle[:40]}")
                ok = False
                continue
            ev.append({"level": "published", "doc": d})
        if not cites:
            tsr = sources.typesub(p)[0].get(T)
            page = tsr["doc_file"] if tsr else None
            from . import extract
            ctx = extract.Ctx(p)
            doc, cit = extract.absent_cite(ctx, T, page)
            ev.append({"level": "published", **({"doc": doc} if doc else {"citation": cit}),
                       "note": "publicação consultada; o fato não está nela"})
        ev.append({"level": "interpreted", "model_id": common.MODEL_ID, "note": SELECTION_NOTE})
        if not ok:
            status, why = "unknown", "citação não resolveu na fonte fixada"
        elif reason:
            status, why = "unknown", reason
        elif probe == "rate_limit":
            status = "documented_supported" if all(documented.get(k) for k in
                                                   ("window", "key", "burst", "mechanism")) else "unknown"
            why = None if status != "unknown" else "falta campo de limite de taxa"
        elif limit is not None and "min" in documented:
            status = "documented_supported" if documented["min"]["seconds"] <= limit else "documented_unsupported"
            why = None if status == "documented_supported" else (
                f"mínimo documentado ({documented['min']['value']} {documented['min']['unit']}) passa do limiar")
        elif limit is not None:
            status, why = "unknown", "limiar exigido e mínimo não documentado"
        else:
            status, why = "documented_supported", None
        row = {"schema": "bo.protocol_support/1", "probe_type": probe, "provider": p,
               "pin": {"provider_version": common.version(p)}, "terraform_resource_type": T,
               "attributes": attrs, "status": status,
               "requirement": {"text": req_text, "max_seconds": limit}, "documented": documented,
               "evidence": ev, "validated": False}
        if why:
            row["reason"] = why
        out.append(row)
    return out, missing


def validate(rows_: list[dict]) -> list[str]:
    v = jsonschema.Draft202012Validator(SCHEMA)
    errs = []
    for i, r in enumerate(rows_, 1):
        for e in v.iter_errors(r):
            errs.append(f"linha {i}: {e.message[:200]}")
    return errs
