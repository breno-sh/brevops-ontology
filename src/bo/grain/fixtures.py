"""Mundos sintéticos (provedores provider_a, provider_b, ...) para os testes e gates do GRAIN.

Nada aqui é dado real: nomes de tipo, serviços e valores são inventados. Cada mundo tem
  * o schema da camada Terraform (formato de `terraform providers schema -json`, só o que importa);
  * a evidência da camada de API por candidato (o que um adaptador de provedor entregaria);
  * configurações de instância nas várias embalagens.
"""

from __future__ import annotations

import copy
import random

SRC = "FX-GRAIN"


def src(tag: str) -> dict:
    return {"level": "derived", "ref": f"{SRC}-{tag}", "note": "fixture sintética do GRAIN"}


def c(**kw):
    """Alegação com fonte sintética."""
    tag = kw.pop("tag", "x")
    kw["source"] = src(tag)
    return kw


def blk(attrs=(), blocks=None, nesting="single"):
    return {"nesting_mode": nesting, "block": {"attributes": {a: {"type": "string"} for a in attrs},
                                               "block_types": blocks or {}}}


def res(attrs=(), blocks=None):
    return {"block": {"attributes": {a: {"type": "string"} for a in attrs}, "block_types": blocks or {}}}


# ---------------------------------------------------------------------------------------------------------
# Evidência neutra reutilizável (camada de API)

def ev_entity(label, key_field, path, service="svc", resource=None, tag="ent", import_key=True, extra_fm=None):
    fm = {key_field: {"path": path, "norm": "str"}}
    fm.update(extra_fm or {})
    out = {
        "identity": [c(status="present", scope="independent", key_fields=[key_field], tag=tag)],
        "lifecycle_controller": [c(kind="self", tag=tag)],
        "owner": [c(kind="self", tag=tag)],
        "effective_scope": [c(kind="self", tag=tag)],
        "api_resource": [c(status="resource", label=label, service=service, resource=resource or label.title()
                           .replace(" ", ""), tag=tag)],
        "field_map": fm,
    }
    if import_key:
        out["import_key"] = [c(status="present", fields=[key_field], tag=tag)]
    return out


def ev_aspect(label, config: dict, via=None, ref_field=None, ref_target=None, tag="asp"):
    """Faceta: sem identidade própria; dono, alcance e ciclo de vida = o pai (estrutural ou referenciado)."""
    v = [via] if via else None
    out = {
        "identity": [c(status="absent", tag=tag)],
        "lifecycle_controller": [c(kind="parent", via=v, tag=tag)],
        "owner": [c(kind="parent", via=v, tag=tag)],
        "effective_scope": [c(kind="parent", via=v, tag=tag)],
        "api_resource": [c(status="aspect", label=label, tag=tag)],
        "field_map": {k: {"path": p, "norm": n, "config": True} for k, (p, n) in config.items()},
    }
    if ref_field:
        out["import_key"] = [c(status="present", fields=[ref_field], tag=tag)]
        out["field_map"][ref_field] = {"path": ref_field, "ref": True}
        out["references"] = {ref_field: ref_target}
    return out


def ev_payload(config: dict | None = None, ref_field=None, ref_target=None, tag="pay"):
    """Carga útil da API do pai (T0): transparente."""
    out = {
        "identity": [c(status="absent", tag=tag)],
        "api_resource": [c(status="payload", label="payload", tag=tag)],
        "field_map": {k: {"path": p, "norm": n, "config": True} for k, (p, n) in (config or {}).items()},
    }
    if ref_field:
        out["import_key"] = [c(status="present", fields=[ref_field], tag=tag)]
        out["field_map"][ref_field] = {"path": ref_field, "ref": True}
        out["references"] = {ref_field: ref_target}
    return out


def ev_element(label, name_field, name_path, config: dict, via=None, ref_field=None, ref_target=None,
               anonymous_fields=None, tag="elm"):
    """Elemento de coleção com identidade dentro do pai (nomeado ou anônimo por conteúdo)."""
    v = [via] if via else None
    fm = {k: {"path": p, "norm": n, "config": True} for k, (p, n) in config.items()}
    if anonymous_fields:
        ident = c(status="present", scope="within_parent", key_fields=sorted(anonymous_fields), anonymous=True,
                  tag=tag)
        for k in anonymous_fields:
            fm[k] = dict(fm.get(k, {"path": k, "norm": "str"}))
        nk = c(status="absent", tag=tag)
    else:
        ident = c(status="present", scope="within_parent", key_fields=[name_field], tag=tag)
        fm[name_field] = {"path": name_path, "norm": "str"}
        nk = c(status="present", fields=[name_field], tag=tag)
    out = {
        "identity": [ident], "element_name_key": [nk],
        "lifecycle_controller": [c(kind="parent", via=v, tag=tag)],
        "owner": [c(kind="parent", via=v, tag=tag)],
        "effective_scope": [c(kind="parent", via=v, tag=tag)],
        "api_resource": [c(status="payload", label=label, tag=tag)],
        "field_map": fm,
    }
    if ref_field:
        keyf = sorted(anonymous_fields) if anonymous_fields else [name_field]
        out["import_key"] = [c(status="present", fields=[ref_field] + keyf, tag=tag)]
        out["field_map"][ref_field] = {"path": ref_field, "ref": True}
        out["references"] = {ref_field: ref_target}
    return out


# ---------------------------------------------------------------------------------------------------------
# Mundo BUCKET: um contêiner de objetos com versionamento, regras de ciclo de vida, criptografia e bloqueio de
# acesso público, em quatro embalagens de um mesmo provedor sintético.

P = "provider_a"


def bucket_schema() -> dict:
    rule_inline = blk(["id", "prefix", "expiration_days"], nesting="list")
    return {
        "a_bucket": res(["name"], {
            "versioning": blk(["status"]),
            "lifecycle_rule": rule_inline,
            "encryption": blk(["algorithm"]),
            "public_access": blk(["block_public"]),
        }),
        "a_bucket_versioning": res(["bucket", "status"]),
        "a_bucket_lifecycle": res(["bucket"], {
            "rule": blk(["id"], {"filter": blk(["prefix"]), "expiration": blk(["days"])}, nesting="list")}),
        "a_bucket_encryption": res(["bucket"], {"rule": blk(["algorithm"])}),
        "a_bucket_public_access": res(["bucket", "block_public"]),
        "a_bucket_lifecycle_rule": res(["bucket", "id", "prefix", "days"]),
        "a_store": res(["name", "encryption_algorithm", "public_block"], {
            "settings": blk([], {"versioning": blk(["status"]),
                                 "lifecycle_rule": blk(["id", "prefix", "expiration_days"], nesting="list")})}),
    }


def bucket_evidence() -> dict:
    ent = ev_entity("object container", "bucket_name", "name", service="objstore", resource="Bucket", tag="bkt")
    rule_cfg = {"prefix": ("prefix", "str"), "expiration_days": ("expiration_days", "int")}
    ver = {"versioning": ("status", "bool")}
    enc = {"algorithm": ("algorithm", "lower")}
    pub = {"block_public": ("block_public", "bool")}
    ev = {
        "a_bucket": ent,
        "a_bucket.versioning": ev_aspect("versioning", ver, tag="ver"),
        "a_bucket.lifecycle_rule": ev_element("lifecycle rule", "rule_name", "id", rule_cfg, tag="lcr"),
        "a_bucket.encryption": ev_aspect("encryption", enc, tag="enc"),
        "a_bucket.public_access": ev_aspect("public access block", pub, tag="pub"),
        "a_bucket_versioning": ev_aspect("versioning", ver, via="bucket", ref_field="bucket", ref_target="a_bucket",
                                         tag="ver"),
        "a_bucket_lifecycle": ev_payload(ref_field="bucket", ref_target="a_bucket", tag="lcp"),
        "a_bucket_lifecycle.rule": ev_element("lifecycle rule", "rule_name", "id", {}, tag="lcr"),
        "a_bucket_lifecycle.rule.filter": ev_payload({"prefix": ("prefix", "str")}, tag="lcf"),
        "a_bucket_lifecycle.rule.expiration": ev_payload({"expiration_days": ("days", "int")}, tag="lce"),
        "a_bucket_encryption": ev_aspect("encryption", {}, via="bucket", ref_field="bucket", ref_target="a_bucket",
                                         tag="enc"),
        "a_bucket_encryption.rule": ev_payload(enc, tag="encr"),
        "a_bucket_public_access": ev_aspect("public access block", pub, via="bucket", ref_field="bucket",
                                            ref_target="a_bucket", tag="pub"),
        "a_bucket_lifecycle_rule": ev_element("lifecycle rule", "rule_name", "id",
                                              {"prefix": ("prefix", "str"), "expiration_days": ("days", "int")},
                                              via="bucket", ref_field="bucket", ref_target="a_bucket", tag="lcr"),
        "a_store": dict(copy.deepcopy(ent), groups={
            "encryption": {"paths": ["encryption_algorithm"],
                           "evidence": ev_aspect("encryption", {"algorithm": ("encryption_algorithm", "lower")},
                                                 tag="enc")},
            "public_access": {"paths": ["public_block"],
                              "evidence": ev_aspect("public access block",
                                                    {"block_public": ("public_block", "bool")}, tag="pub")}}),
        "a_store.settings": ev_payload(tag="set"),
        "a_store.settings.versioning": ev_aspect("versioning", ver, tag="ver"),
        "a_store.settings.lifecycle_rule": ev_element("lifecycle rule", "rule_name", "id", rule_cfg, tag="lcr"),
    }
    return ev


# as quatro embalagens: quais candidatos de schema cada uma usa
BUCKET_PACKAGINGS = {
    "inline": ["a_bucket", "a_bucket.versioning", "a_bucket.lifecycle_rule", "a_bucket.encryption",
               "a_bucket.public_access"],
    "separate": ["a_bucket", "a_bucket_versioning", "a_bucket_lifecycle.rule", "a_bucket_encryption",
                 "a_bucket_public_access"],
    "wrapped": ["a_store", "a_store.settings.versioning", "a_store.settings.lifecycle_rule", "a_store:encryption",
                "a_store:public_access"],
    "mixed": ["a_bucket", "a_bucket.encryption", "a_bucket_lifecycle_rule", "a_bucket_versioning",
              "a_bucket_public_access"],
}

RULES_V = [("r-old", "tmp/", 30), ("r-arch", "arch/", 365)]


def bucket_configs(name="logs-example", rules=RULES_V, versioning="Enabled", algorithm="AES256",
                   block_public=True) -> dict:
    """Mesma configuração de contêiner nas quatro embalagens."""
    bref = {"$ref": "a_bucket.main"}
    inline = {"provider": P, "resources": [{"type": "a_bucket", "name": "main", "values": {
        "name": name, "versioning": {"status": versioning},
        "lifecycle_rule": [{"id": i, "prefix": p, "expiration_days": d} for i, p, d in rules],
        "encryption": {"algorithm": algorithm}, "public_access": {"block_public": block_public}}}]}
    separate = {"provider": P, "resources": [
        {"type": "a_bucket", "name": "main", "values": {"name": name}},
        {"type": "a_bucket_versioning", "name": "v", "values": {"bucket": bref, "status": versioning}},
        {"type": "a_bucket_lifecycle", "name": "lc", "values": {"bucket": bref, "rule": [
            {"id": i, "filter": {"prefix": p}, "expiration": {"days": d}} for i, p, d in rules]}},
        {"type": "a_bucket_encryption", "name": "e", "values": {"bucket": bref, "rule": {"algorithm":
                                                                                           algorithm.lower()}}},
        {"type": "a_bucket_public_access", "name": "pa", "values": {"bucket": bref, "block_public":
                                                                    "true" if block_public else "false"}},
    ]}
    wrapped = {"provider": P, "resources": [{"type": "a_store", "name": "main", "values": {
        "name": name, "encryption_algorithm": algorithm, "public_block": block_public,
        "settings": {"versioning": {"status": versioning == "Enabled"},
                     "lifecycle_rule": [{"id": i, "prefix": p, "expiration_days": str(d)} for i, p, d in rules]}}}]}
    mixed = {"provider": P, "resources": [
        {"type": "a_bucket", "name": "main", "values": {"name": name, "encryption": {"algorithm": algorithm}}},
        *[{"type": "a_bucket_lifecycle_rule", "name": f"r{k}", "values": {"bucket": bref, "id": i, "prefix": p,
                                                                          "days": d}}
          for k, (i, p, d) in enumerate(rules)],
        {"type": "a_bucket_versioning", "name": "v", "values": {"bucket": bref, "status": versioning}},
        {"type": "a_bucket_public_access", "name": "pa", "values": {"bucket": bref, "block_public": block_public}},
    ]}
    return {"inline": inline, "separate": separate, "wrapped": wrapped, "mixed": mixed}


def shuffled(config: dict, seed: int) -> dict:
    """Mesma configuração com recursos, blocos de lista e chaves em outra ordem (o conteúdo não muda)."""
    rnd = random.Random(seed)

    def sh(v):
        if isinstance(v, dict):
            items = list(v.items())
            rnd.shuffle(items)
            return {k: sh(x) for k, x in items}
        if isinstance(v, list):
            xs = [sh(x) for x in v]
            rnd.shuffle(xs)
            return xs
        return v

    out = copy.deepcopy(config)
    rs = [dict(r, values=sh(r.get("values", {}))) for r in out["resources"]]
    rnd.shuffle(rs)
    out["resources"] = rs
    return out


def schema_blocks(resource_schemas: dict) -> dict:
    """cid -> nomes dos blocos filhos (para a camada de instância)."""
    out = {}

    from .schema import collection_fields

    def walk_obj(cid, fields):
        out[cid] = set()
        for f, ty in fields.items():
            cf = collection_fields(ty)
            if cf:
                out[cid].add(f)
                walk_obj(f"{cid}.{f}", cf[1])

    def walk(cid, block):
        bt = block.get("block_types") or {}
        out[cid] = set(bt)
        for a, spec in (block.get("attributes") or {}).items():
            cf = collection_fields(spec.get("type"))
            if cf:
                out[cid].add(a)
                walk_obj(f"{cid}.{a}", cf[1])
        for b, spec in bt.items():
            walk(f"{cid}.{b}", spec.get("block") or {})

    for rt, sch in resource_schemas.items():
        walk(rt, sch.get("block") or {})
    return out
