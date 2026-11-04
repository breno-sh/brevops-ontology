"""Os 24 casos tipo × provedor e o que o kit implementa em cada um.

A linha do SERVICE-EVIDENCE (C25 protocol_support) diz QUAL tipo Terraform e QUAIS atributos realizam a sonda e o
suporte documentado; aqui fica o que o kit acrescenta para os casos em que há template:
  ttl_s        TTL que o template configura no lado caso (0 quando o tipo não tem TTL), conferido no plano
  ttl_from     como ler esse TTL do plano sintético do lado caso (tipo, atributo, conversão)
  data_types   tipos que recebem as requisições e o armazenamento da sonda (uso no custo)
  per_rep      os alvos são um por repetição (filas)
  runner_inputs  variáveis que o runner do PROBE-* entrega pelo ambiente (TF_VAR_*), nunca gravadas
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import PROBE_TYPES, PROVIDERS


@dataclass(frozen=True)
class CellImpl:
    ttl_s: float
    ttl_from: tuple = ()          # (tipo, caminho no after, fator para segundos | "duration_s")
    data_types: tuple = ()
    per_rep: bool = False
    runner_inputs: tuple = ()
    targets: tuple = ()           # marcadores de alvo que o PROBE-* tira do state e passa ao backend


AWS_IN = ("bo_allowed_account_ids",)
OCI_IN = ("bo_compartment_id",)

IMPL: dict[str, CellImpl] = {
    "object_versioning/aws": CellImpl(0, (), ("aws_s3_bucket",), runner_inputs=AWS_IN, targets=("bucket",)),
    "object_versioning/google": CellImpl(0, (), ("google_storage_bucket",), targets=("bucket",)),
    "object_versioning/azurerm": CellImpl(0, (), ("azurerm_storage_account",), targets=("account", "container")),
    "object_versioning/oci": CellImpl(0, (), ("oci_objectstorage_bucket",), runner_inputs=OCI_IN,
                                      targets=("bucket",)),
    "object_lifecycle/aws": CellImpl(86400, ("aws_s3_bucket_lifecycle_configuration", "rule.0.expiration.0.days",
                                             86400), ("aws_s3_bucket",), runner_inputs=AWS_IN, targets=("bucket",)),
    "object_lifecycle/google": CellImpl(86400, ("google_storage_bucket", "lifecycle_rule.0.condition.0.age", 86400),
                                        ("google_storage_bucket",), targets=("bucket",)),
    "item_ttl/aws": CellImpl(3600, (), ("aws_dynamodb_table",), runner_inputs=AWS_IN, targets=("table",)),
    "item_ttl/google": CellImpl(3600, (), ("google_firestore_database",), targets=("project", "database")),
    "queue_retention/aws": CellImpl(60, ("aws_sqs_queue", "message_retention_seconds", 1), ("aws_sqs_queue",),
                                    per_rep=True, runner_inputs=AWS_IN, targets=("queue_url",)),
    "queue_retention/google": CellImpl(600, ("google_pubsub_subscription", "message_retention_duration",
                                             "duration_s"), ("google_pubsub_topic", "google_pubsub_subscription"),
                                       per_rep=True, targets=("project", "topic", "subscription")),
}

# TTL do item (não é atributo do recurso): o runner grava a expiração = gravação + ttl_s no atributo declarado
ITEM_TTL_ATTRIBUTE = {"item_ttl/aws": ("aws_dynamodb_table", "ttl.0.attribute_name", "bo_expire_at"),
                      "item_ttl/google": ("google_firestore_field", "field", "bo_expire_at")}


def all_cells() -> list[str]:
    return [f"{t}/{p}" for t in PROBE_TYPES for p in PROVIDERS]


def split(cell: str) -> tuple[str, str]:
    t, p = cell.split("/")
    return t, p
