"""Rodada v4-r2 (DIAG_T3 F1/F2; GRAIN 0.2.4, T03): alvo tipado do campo que aponta para o conjunto-pai em todo tipo
de regra ou configuração separada das fatias NET e STO (e das anexações e do contêiner separado, para a lista).

O ESCOPO (tipo, campo do pai) é a lista de auditoria: diz QUAL campo conferir, nunca o alvo. O alvo sai só de fonte
fixada, por uma destas regras declaradas (todas DERIVADAS sobre fatos publicados do pin):

  R-REF-SPEC-PARENT    a spec do provedor dá o tipo como faceta de um recurso-pai P, via este campo (R-LIFE-SPEC-
                       PARENT / R-OWN-SPEC com via = [campo]), e exatamente um tipo U do pin tem ponte da spec
                       (R-BRIDGE-SPEC) para o mesmo serviço e o recurso P: alvo = U
  R-REF-EXAMPLE-TARGET os exemplos da página oficial do tipo, nos blocos `resource "<tipo>"`, atribuem ao campo uma
                       referência `<U>.<nome>.<atributo>` com U tipo do pin, e todas nomeiam o mesmo U: alvo = U
                       (cada linha de exemplo é um fato PUBLICADO, R-REF-EXAMPLE, com o sha256 da página)
  R-REF-STEM           o nome do campo é <radical>[_id|_name], <provedor>_<radical> é tipo do pin e a descrição
                       publicada do campo nomeia o radical por extenso (R-REF-PHRASE-LEAD, PUBLICADO): alvo = esse tipo
Mais de uma regra: valem juntas só se dão o mesmo alvo (as outras vão em corroborated_by); se divergem, nada é
publicado e o campo fica UNKNOWN. Campo que já tinha alvo resolvido (R-REF-TARGET) não é tocado (R1 do PREREG: nada
sobrescrito). Sem regra que se aplique, o campo fica UNKNOWN com o motivo de cada regra. Nenhum fato de ciclo de vida
novo: as páginas fixadas não têm frase oficial nova sobre o ciclo de vida desses tipos (ver LIFECYCLE_NOTE).
"""

from __future__ import annotations

import re

from . import common, sources

# (provedor, tipo, campo do pai, papel na fatia)
SCOPE = [
    ("aws", "aws_security_group_rule", "security_group_id", "NET regra separada (id composto)"),
    ("aws", "aws_vpc_security_group_ingress_rule", "security_group_id", "NET regra separada (id de API)"),
    ("aws", "aws_vpc_security_group_egress_rule", "security_group_id", "NET regra separada (id de API)"),
    ("aws", "aws_network_interface_sg_attachment", "security_group_id", "NET anexação do conjunto"),
    ("google", "google_compute_firewall", "network", "NET regra separada (rede do conjunto)"),
    ("azurerm", "azurerm_network_security_rule", "network_security_group_name", "NET regra separada (pai por nome)"),
    ("azurerm", "azurerm_network_interface_security_group_association", "network_security_group_id",
     "NET anexação do conjunto"),
    ("azurerm", "azurerm_subnet_network_security_group_association", "network_security_group_id",
     "NET anexação do conjunto"),
    ("oci", "oci_core_network_security_group_security_rule", "network_security_group_id", "NET regra separada"),
    ("aws", "aws_s3_bucket_versioning", "bucket", "STO configuração separada"),
    ("aws", "aws_s3_bucket_lifecycle_configuration", "bucket", "STO configuração separada"),
    ("aws", "aws_s3_bucket_server_side_encryption_configuration", "bucket", "STO configuração separada"),
    ("aws", "aws_s3_bucket_public_access_block", "bucket", "STO configuração separada"),
    ("aws", "aws_s3_bucket_acl", "bucket", "STO política separada (ACL)"),
    ("aws", "aws_s3_bucket_policy", "bucket", "STO política separada"),
    ("aws", "aws_s3_bucket_ownership_controls", "bucket", "STO configuração separada"),
    ("aws", "aws_s3_account_public_access_block", "account_id", "STO configuração separada (nível da conta)"),
    ("google", "google_storage_bucket_acl", "bucket", "STO política separada (ACL)"),
    ("google", "google_storage_bucket_access_control", "bucket", "STO política separada (entrada de ACL)"),
    ("google", "google_storage_bucket_iam_policy", "bucket", "STO política separada (IAM)"),
    ("google", "google_storage_bucket_iam_binding", "bucket", "STO política separada (IAM)"),
    ("google", "google_storage_bucket_iam_member", "bucket", "STO política separada (IAM)"),
    ("azurerm", "azurerm_storage_container", "storage_account_id", "STO contêiner separado da conta"),
    ("azurerm", "azurerm_storage_management_policy", "storage_account_id", "STO política separada"),
    ("azurerm", "azurerm_storage_account_customer_managed_key", "storage_account_id", "STO configuração separada"),
    ("azurerm", "azurerm_storage_encryption_scope", "storage_account_id", "STO configuração separada"),
    ("oci", "oci_objectstorage_object_lifecycle_policy", "bucket", "STO política separada"),
    ("oci", "oci_objectstorage_namespace_metadata", "namespace", "STO configuração do namespace"),
]
LIFECYCLE_NOTE = ("nenhuma frase oficial nova de ciclo de vida nas páginas fixadas desses tipos (busca por destroy/"
                  "delete/remove/lifecycle/parent): nenhum lifecycle_controller publicado nesta rodada; os que já "
                  "existiam (R-LIFE-SPEC-PARENT, R-LIFE-DOC, R-OBS-*) ficam como estavam")

RES = re.compile(r'^\s*resource\s+"([a-z0-9_]+)"\s+"[^"]+"\s*\{\s*$')
ASSIGN = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*([a-z][a-z0-9_]*)\.([A-Za-z0-9_\-]+)\.([a-z][a-z0-9_]*)\s*$")
STEM = re.compile(r"^([a-z][a-z0-9_]*?)(?:_ids?|_names?)?$")
SPEC_PARENT_RULES = ("R-LIFE-SPEC-PARENT", "R-OWN-SPEC")


def _api(bridges: dict, T: str) -> dict:
    return bridges.get(T) or {"service": "UNKNOWN", "resource": "UNKNOWN"}


def _spec_parent(ctx, T: str, a: str):
    """(U, ids) pela spec, ou (None, motivo)."""
    facts = [r for r in ctx.recs if r["terraform_resource_type"] == T and not r.get("block_path")
             and r["status"] == "stated" and (r.get("value") or {}).get("rule") in SPEC_PARENT_RULES
             and r["value"].get("kind") == "parent"]
    if not facts:
        return None, "spec: o tipo não é faceta de um recurso-pai na spec"
    f = sorted(facts, key=lambda r: r["evidence_id"])[0]
    v = f["value"]
    if v.get("via") != [a]:
        return None, f"spec: o campo do pai da spec é {v.get('via')}, não [{a}]"
    svc = (v.get("spec_resource") or "").split(":", 1)[0]
    par = v.get("parent_resource")
    us = sorted((r["terraform_resource_type"], r["evidence_id"]) for r in ctx.recs
                if r["fact_kind"] == "api_bridge" and r["status"] == "stated" and not r.get("block_path")
                and (r.get("value") or {}).get("rule") == "R-BRIDGE-SPEC"
                and r["value"].get("aspect") == "api_resource_bridge" and not r["value"].get("inherited_from")
                and r["value"].get("service") == svc and r["value"].get("resource") == par)
    if len(us) != 1:
        return None, f"spec: {len(us)} tipo(s) com ponte para {svc}:{par}"
    return us[0][0], [f["evidence_id"], us[0][1]]


def examples(p: str, T: str, a: str, page: str | None) -> list[tuple[int, str, str]]:
    """[(linha 1-based, U, linha)] das atribuições `a = U.<nome>.<atributo>` nos blocos `resource "T"` da página."""
    if not page:
        return []
    types = set(sources.types(p))
    out, depth = [], 0
    for i, ln in enumerate(common.page_lines(p, page)):
        if depth <= 0:
            m = RES.match(ln)
            depth = 1 if (m and m.group(1) == T) else 0
            continue
        if depth == 1:
            m = ASSIGN.match(ln)
            if m and m.group(1) == a and m.group(2) in types:
                out.append((i + 1, m.group(2), ln.strip()))
        depth += ln.count("{") - ln.count("}")
    return out


def _examples(ctx, T: str, a: str, page: str | None, api: dict):
    ex = examples(ctx.p, T, a, page)
    if not ex:
        return None, "exemplo: nenhum bloco do tipo atribui referência a um recurso a este campo"
    us = sorted({u for _ln, u, _s in ex})
    sha = common.sha256_file(common.docs_root(ctx.p) / page)
    ids = []
    for ln, u, _s in ex:
        ids.append(ctx.add(T, "identity", f"refexample:{a}:{ln}", api, "stated", "published",
                           value={"aspect": "reference_example", "rule": "R-REF-EXAMPLE", "attribute": a,
                                  "example_type": u, "page_sha256": sha},
                           doc=common.doc_cite(ctx.p, page, ln)))
        ctx.st["R-REF-EXAMPLE"] += 1
    if len(us) != 1:
        return None, f"exemplo: os exemplos nomeiam tipos diferentes {us}"
    return us[0], ids


def _stem(ctx, T: str, a: str, api: dict):
    from .extract import fdoc
    p = ctx.p
    m = STEM.match(a)
    U = f"{p}_{m.group(1)}" if m else None
    if not U or U == T or U not in set(sources.types(p)):
        return None, "radical: <provedor>_<radical do campo> não é tipo do pin"
    facts, _can = sources.facts_for(p, f"{p}:{T}:{a}", ctx.st)
    desc = next((f for f in facts if f["fact_kind"] == "description"), None)
    doc = fdoc(desc, p) if desc else None
    if not doc:
        return None, "radical: campo sem descrição publicada que resolva"
    words = m.group(1).replace("_", " ")
    hit = re.search(r"\b" + re.escape(words) + r"\b", doc["sentence"], re.I)
    if not hit:
        return None, f"radical: a descrição não nomeia '{words}'"
    pid = ctx.add(T, "identity", f"refphrase:{a}", api, "stated", "published",
                  value={"aspect": "reference_phrase", "rule": "R-REF-PHRASE-LEAD", "attribute": a,
                         "phrase": hit.group(0), "c03_fact_id": desc["fact_id"]}, doc=doc)
    return U, [pid]


def run(ctx, bridges: dict) -> list[dict]:
    """Confere o ESCOPO do provedor; publica os alvos que as regras dão; devolve as linhas do relatório."""
    p = ctx.p
    types = set(sources.types(p))
    have = {}
    for r in ctx.recs:
        v = r.get("value") or {}
        if r["status"] == "stated" and not r.get("block_path") and v.get("aspect") == "reference_target":
            k = (r["terraform_resource_type"], v.get("attribute"))
            if v.get("resolved") or k not in have:
                have[k] = r
    rows = []
    for prov, T, a, role in SCOPE:
        if prov != p:
            continue
        row = {"provider": p, "terraform_resource_type": T, "attribute": a, "role": role}
        rows.append(row)
        if T not in types:
            row.update(status="UNKNOWN", reason="tipo fora do schema fixado")
            continue
        ex = have.get((T, a))
        if ex is not None:
            v = ex["value"]
            if v.get("resolved"):
                row.update(status="já tinha", target=v["resolved"], level=ex["level"], rule=v.get("rule"),
                           evidence_id=ex["evidence_id"])
            else:
                row.update(status="UNKNOWN", reason=f"alvo já publicado e ambíguo {v.get('target_types')}",
                           evidence_id=ex["evidence_id"])
            continue
        tsr = sources.typesub(p)[0].get(T)
        page = tsr["doc_file"] if tsr else None
        api = _api(bridges, T)
        support, why = [], []
        for rule, (u, x) in (("R-REF-SPEC-PARENT", _spec_parent(ctx, T, a)),
                             ("R-REF-EXAMPLE-TARGET", _examples(ctx, T, a, page, api)),
                             ("R-REF-STEM", _stem(ctx, T, a, api))):
            if u:
                support.append((rule, u, x))
            else:
                why.append(x)
        targets = sorted({u for _r, u, _x in support})
        if not support:
            row.update(status="UNKNOWN", reason="; ".join(why))
            ctx.st["R-REF-PARENT_unknown"] += 1
            continue
        if len(targets) > 1:
            row.update(status="UNKNOWN", reason=f"as regras divergem: {[(r, u) for r, u, _x in support]}")
            ctx.st["R-REF-PARENT_divergente"] += 1
            continue
        U = targets[0]
        rule = support[0][0]
        derived = sorted({i for _r, _u, x in support for i in x})
        eid = ctx.add(T, "identity", f"reftarget:{a}", api, "stated", "derived",
                      value={"aspect": "reference_target", "rule": rule, "attribute": a, "target_types": [U],
                             "resolved": U, "references": {a: U}, "parent_field": True,
                             "corroborated_by": [r for r, _u, _x in support[1:]]},
                      derived=derived)
        ctx.st[rule] += 1
        row.update(status="publicado", target=U, level="derived", rule=rule,
                   corroborated_by=[r for r, _u, _x in support[1:]], evidence_id=eid)
    return rows


def report(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda x: (x["provider"], x["terraform_resource_type"], x["attribute"]))
    by_level, by_rule = {}, {}
    for x in rows:
        if x["status"] == "publicado":
            by_level[x["level"]] = by_level.get(x["level"], 0) + 1
            by_rule[x["rule"]] = by_rule.get(x["rule"], 0) + 1
    return {"schema": "bo.service_evidence.parent_refs/1", "module": common.MODULE,
            "motivo": "results/PILOT-EXIT/DIAG_T3.json F1/F2; GRAIN 0.2.4 (R-GRAIN-T03): sem reference_target no "
                      "campo do pai, a unidade C19 de esquema da regra separada fica UNKNOWN",
            "rules": __doc__.split("\n\n")[1], "lifecycle": LIFECYCLE_NOTE,
            "totals": {"checked": len(rows), "already": sum(1 for x in rows if x["status"] == "já tinha"),
                       "published": sum(1 for x in rows if x["status"] == "publicado"),
                       "published_by_level": dict(sorted(by_level.items())),
                       "published_by_rule": dict(sorted(by_rule.items())),
                       "unknown": sum(1 for x in rows if x["status"] == "UNKNOWN")},
            "checked": rows}
