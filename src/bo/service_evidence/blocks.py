"""Fatos por bloco aninhado (value.block_path), pedidos pelo GRAIN para decidir facetas embutidas (CC-1 do
PILOT-STO-GLOSS). O formato por aspecto não muda; só se acrescentam aspectos com block_path.

Candidato = tipo + "." + block_path (blocos separados por ponto, sem o tipo), a convenção do GRAIN.
Cobertura: todo bloco aninhado (menos timeouts) até a profundidade MAX_DEPTH; abaixo dela, só os blocos cujo
caminho tem palavra de faceta (FACET_RX: versionamento, ciclo de vida, criptografia, acesso público, regras de
rede, retenção). O corte é declarado em evidence_levels.json (inputs.blocks).

Por bloco:
  identity/block_schema           PUBLICADO: forma do bloco no schema fixado (citação op=shape)
  identity/block_identity         DERIVADO (R-BLOCK-ID): o schema expõe ou não atributo de identidade no bloco;
                                  candidatos a chave de nome (atributos obrigatórios name/key); no máximo um
                                  por pai quando nesting single ou max_items 1. "absent" quer dizer só que o
                                  schema não expõe; nada sobre a API.
  owner/block_config_owner        DERIVADO (R-BLOCK-OWNER): a configuração do bloco é gravada pelo recurso
                                  Terraform do pai (camada terraform)
  lifecycle_controller/block_lifecycle  DERIVADO (R-BLOCK-LIFE): o bloco não tem recurso próprio; nasce e some
                                  com o pai no Terraform (camada terraform; o ciclo na API não é dito)
Alcance efetivo do bloco: só por frase (effective_scope/attribute_scope com block_path, do extract). Sem frase
não há registro: o C25 proíbe value em status=unknown, então um UNKNOWN por bloco não tem onde levar o
block_path (registrado no CONTRACT_CHANGE); para o GRAIN, campo sem alegação já é UNKNOWN.
Tipos separados de faceta: identity/shared_identity_key (DERIVADO, R-ID-SHARED) liga tipos cujo
resource_identity_schema tem os mesmos campos obrigatórios não genéricos (ex.: aws_s3_bucket e
aws_s3_bucket_versioning, ambos por bucket), para a invariância embutido × separado (E2).
"""

from __future__ import annotations

import collections
import re

from . import common

MAX_DEPTH = 4
FACET_RX = re.compile(r"version|lifecycle|encrypt|kms|cmek|sse|server_side|public_access|access_block|acl|cors|"
                      r"ingress|egress|security_rule|firewall|retention|expiration|object_lock|immutab")
ID_ATTRS = ("id", "arn", "self_link", "ocid")
NAME_KEYS = ("name", "key")
GENERIC_ID = {"id", "name", "arn", "region", "account_id", "project", "location", "zone", "subscription_id",
              "resource_group_name", "compartment_id"}


def walk(block: dict, prefix: str, ptr_parts: list, depth: int):
    for name, bt in sorted((block.get("block_types") or {}).items()):
        if name == "timeouts":
            continue
        path = f"{prefix}.{name}" if prefix else name
        parts = ptr_parts + ["block_types", name]
        yield path, parts, bt, depth
        yield from walk(bt.get("block") or {}, path, parts + ["block"], depth + 1)


def run(ctx, T: str, api: dict, st: collections.Counter) -> None:
    p = ctx.p
    root = common.schema(p)["resource_schemas"][T]["block"]
    for path, parts, bt, depth in walk(root, "", [], 1):
        facet = bool(FACET_RX.search(path))
        if depth > MAX_DEPTH and not facet:
            st["blocos_abaixo_do_corte"] += 1
            continue
        st["blocos"] += 1
        if facet:
            st["blocos_de_faceta"] += 1
        ptr = common.schema_pointer(p, "resource_schemas", T, "block", *parts)
        shape = common.block_shape(bt)
        parent = T + ("." + path.rsplit(".", 1)[0] if "." in path else "")
        sid = ctx.add(T, "identity", f"block:{path}:schema", api, "stated", "published",
                      value={"aspect": "block_schema", "rule": "R-BLOCK-SCHEMA", "block_path": path,
                             "depth": depth, "facet_word": facet, **shape},
                      cit=common.schema_cite(p, ptr, "shape"))
        attrs = shape["attributes"]
        idl = sorted(a for a in ID_ATTRS if a in attrs and "c" in attrs[a])
        names = sorted(a for a in NAME_KEYS if a in attrs and "r" in attrs[a])
        one = shape["nesting_mode"] == "single" or shape.get("max_items") == 1
        v = {"aspect": "block_identity", "rule": "R-BLOCK-ID", "block_path": path,
             "schema_identity": "present" if idl else "absent", "key_fields": idl,
             "element_name_candidates": names, "max_per_parent": 1 if one else None,
             "nesting_mode": shape["nesting_mode"]}
        ctx.add(T, "identity", f"block:{path}:id", api, "stated", "derived", value=v, derived=[sid])
        ctx.add(T, "owner", f"block:{path}", api, "stated", "derived",
                value={"aspect": "block_config_owner", "rule": "R-BLOCK-OWNER", "block_path": path,
                       "kind": "parent", "via": parent, "layer": "terraform"}, derived=[sid])
        ctx.add(T, "lifecycle_controller", f"block:{path}", api, "stated", "derived",
                value={"aspect": "block_lifecycle", "rule": "R-BLOCK-LIFE", "block_path": path,
                       "kind": "parent", "via": parent, "layer": "terraform"}, derived=[sid])


def shared_identity(ctx, bridges: dict, st: collections.Counter) -> None:
    """Agrupa tipos pelo conjunto de campos obrigatórios da identidade do schema (sem os genéricos)."""
    p = ctx.p
    ri = common.schema(p).get("resource_identity_schemas", {})
    by_rec = {}
    for r in ctx.recs:
        if (r.get("value") or {}).get("aspect") == "resource_identity_schema":
            by_rec[r["terraform_resource_type"]] = r
    groups = collections.defaultdict(list)
    for T, r in by_rec.items():
        req = tuple(r["value"]["required"])
        if req and not set(req) <= GENERIC_ID:
            groups[req].append(T)
    for req, ts in groups.items():
        if len(ts) < 2:
            continue
        for T in sorted(ts):
            r = by_rec[T]
            ctx.add(T, "identity", "shared_identity", r["api_resource"], "stated", "derived",
                    value={"aspect": "shared_identity_key", "rule": "R-ID-SHARED", "fields": list(req),
                           "peers": sorted(t for t in ts if t != T)},
                    derived=[by_rec[t]["evidence_id"] for t in ts])
            st["tipos_com_identidade_compartilhada"] += 1
    _ = ri, bridges
