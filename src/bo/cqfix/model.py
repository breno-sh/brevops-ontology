"""Registro de realização de uma fixture abstrata num provedor.

Cada (CQ, provedor, variante) vira um Fx (realizada) ou um NA (não se aplica, com evidência). Regras:
- entity_map cobre todo indivíduo da fixture abstrata. Valor: endereço Terraform do main.tf
  ("aws_s3_bucket.fx_..."), "probe:<chave>" (entrada da pergunta em probes.yaml: fluxo, pedido, observação,
  mudança, destino de tradução), "implicit:<o quê>" (contexto do provedor: conta, projeto, região),
  "external:<var|data>" (fora da leitura) ou "absent:<porquê>" (a fixture diz que não existe).
- incompleteness (só na incompleta) cobre cada not_read da fixture com um mecanismo:
  SYMBOLIC_INPUT (variável sem valor), EXTERNAL_REFERENCE (referência para fora da leitura),
  READ_MASK (existe na configuração mas a leitura declarada a exclui) ou EVIDENCE_GAP (falta o fato de
  serviço que decidiria; nada a ler no HCL).
- synthesized lista todo recurso do slice que não é indivíduo da fixture (exigido pelo schema ou pelo
  deploy), com o motivo: nada entra em silêncio.
- deviations registra toda diferença entre a situação abstrata e a instanciação (tipo substituto, valor de
  atributo que o provedor fixa) e por que a resposta esperada continua a mesma.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hcl import Res, VarDecl

MECHANISMS = ("SYMBOLIC_INPUT", "EXTERNAL_REFERENCE", "READ_MASK", "EVIDENCE_GAP")
EVIDENCE_LEVELS = ("STRUCTURAL", "INTERPRETED")
EVIDENCE_KINDS = ("schema_type_absent", "schema_attr_absent", "schema_attr_present", "doc_citation")
COST_CLASSES = ("free", "low", "medium", "high")


def fx_slug(fixture_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fixture_id.lower()).strip("_")


@dataclass
class Fx:
    resources: list[Res]
    entity_map: dict[str, str]
    variables: list[VarDecl] = field(default_factory=list)
    incompleteness: list[dict] = field(default_factory=list)
    probe: dict = field(default_factory=dict)
    synthesized: dict[str, str] = field(default_factory=dict)
    deviations: list[str] = field(default_factory=list)
    evidence_level: str = "STRUCTURAL"
    evidence: list[dict] = field(default_factory=list)
    deployable: bool = True
    deploy_note: str = ""
    cost_class: str = "free"


@dataclass
class NA:
    reason: str
    evidence: list[dict]


def schema_type_absent(provider: str, pattern: str, why: str) -> dict:
    return {"kind": "schema_type_absent", "provider": provider, "pattern": pattern, "why": why}


def schema_attr_absent(provider: str, resource_type: str, pattern: str, why: str) -> dict:
    return {"kind": "schema_attr_absent", "provider": provider, "resource_type": resource_type,
            "pattern": pattern, "why": why}


def schema_attr_present(provider: str, resource_type: str, path: str, why: str) -> dict:
    return {"kind": "schema_attr_present", "provider": provider, "resource_type": resource_type,
            "path": path, "why": why}


def doc_citation(url: str, claim: str) -> dict:
    return {"kind": "doc_citation", "url": url, "claim": claim, "evidence_state": "INTERPRETED"}
