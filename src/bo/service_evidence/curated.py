"""Fatos curados das fatias dos pilotos (rede: SG/firewall/NSG/security list; armazenamento: bucket/contêiner).

Cada entrada aponta uma frase da página FIXADA (arquivo + trecho para achar a linha). Dois níveis:
  published   (regra C-PILOT-LITERAL) o valor só repete o que a frase diz;
  interpreted (regra I-PILOT-READING, model_id claude-opus-5-5) leitura da frase; value.basis diz o que foi
              inferido além do texto. A frase citada é o apoio, não a prova.
Depois, para cada tipo das fatias e cada fato de regra de rede ou de alcance que a página não diz, um UNKNOWN
explícito (C-PILOT-GAP): a lacuna fica visível e não é preenchida com conhecimento de fora do pin.
"""

from __future__ import annotations

from . import common, extract

NET_TYPES = {
    "aws": ["aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule",
            "aws_vpc_security_group_egress_rule", "aws_network_acl_rule"],
    "google": ["google_compute_firewall"],
    "azurerm": ["azurerm_network_security_group", "azurerm_network_security_rule"],
    "oci": ["oci_core_security_list", "oci_core_network_security_group_security_rule"],
}
STO_TYPES = {
    "aws": ["aws_s3_bucket", "aws_s3_bucket_public_access_block", "aws_s3_account_public_access_block",
            "aws_s3_bucket_versioning"],
    "google": ["google_storage_bucket"],
    "azurerm": ["azurerm_storage_account", "azurerm_storage_container"],
    "oci": ["oci_objectstorage_bucket"],
}
NET_KINDS = ("connection_state", "effect", "precedence")
STO_KINDS = ("effective_scope", "precedence")

A, G, Z, O = "website/docs/r/", "website/docs/r/", "website/docs/r/", "website/docs/r/"

# (provider, tipo, fact_kind, chave, arquivo, trecho que acha a linha, frase exata ou None = linha inteira,
#  nível, value)
ENTRIES = [
    # ---------------- rede
    ("aws", "aws_security_group", "effect", "default_egress", A + "security_group.html.markdown",
     "NOTE on Egress rules", None, "published",
     {"aspect": "provider_default_rule", "rule": "C-PILOT-LITERAL", "direction": "egress",
      "provider_default": "ALLOW ALL egress rule created by AWS for a new security group in a VPC",
      "terraform_behavior": "Terraform removes this default rule"}),
    ("google", "google_compute_firewall", "precedence", "tie_break", G + "compute_firewall.html.markdown",
     "DENY rules take", "DENY rules take precedence over ALLOW rules having equal priority.", "published",
     {"aspect": "tie_break", "rule": "C-PILOT-LITERAL", "attribute": "priority",
      "equal_priority": "deny_over_allow"}),
    ("google", "google_compute_firewall", "precedence", "default_priority", G + "compute_firewall.html.markdown",
     "When not specified, the value assumed is 1000", "When not specified, the value assumed is 1000.",
     "published",
     {"aspect": "default_priority", "rule": "C-PILOT-LITERAL", "attribute": "priority", "value": 1000,
      "range": [0, 65535], "as_of": "2026-10-26"}),
    ("google", "google_compute_firewall", "effect", "allow_block", G + "compute_firewall.html.markdown",
     "The list of ALLOW rules specified by this firewall", "The list of ALLOW rules specified by this firewall.",
     "published", {"aspect": "effect_block", "rule": "C-PILOT-LITERAL", "attribute": "allow", "block_path": "allow", "effect": "allow"}),
    ("google", "google_compute_firewall", "effect", "deny_block", G + "compute_firewall.html.markdown",
     "The list of DENY rules specified by this firewall", "The list of DENY rules specified by this firewall.",
     "published", {"aspect": "effect_block", "rule": "C-PILOT-LITERAL", "attribute": "deny", "block_path": "deny", "effect": "deny"}),
    ("google", "google_compute_firewall", "effect", "implied_rules", G + "compute_firewall.html.markdown",
     "No manually created network has",
     "No manually created network has automatically created firewall rules except for a default \"allow\" rule "
     "for outgoing traffic and a default \"deny\" for incoming traffic.", "interpreted",
     {"aspect": "implied_rules", "rule": "I-PILOT-READING", "ingress": "deny", "egress": "allow",
      "applies_to": "networks other than the default network",
      "basis": "a frase fala de regras 'default' de redes criadas à mão; ler isso como regras implícitas de "
               "menor prioridade (deny de entrada, allow de saída) é interpretação: a frase não diz a prioridade"}),
    ("oci", "oci_core_security_list", "connection_state", "ingress_per_rule", O + "core_security_list.html.markdown",
     "* `stateless` - (Optional) (Updatable) A stateless rule allows traffic in one direction. Remember to add a "
     "corresponding stateless rule in the other direction if you need to support bidirectional traffic. For "
     "example, if ingress", None, "interpreted",
     {"aspect": "rule_connection_state", "rule": "I-PILOT-READING", "attribute": "ingress_security_rules.stateless",
      "block_path": "ingress_security_rules",
      "granularity": "per_rule", "default": "stateful", "as_of": "2026-10-21",
      "stateless_needs_reverse_rule": True,
      "basis": "a frase diz o default (false = stateful) e que regra stateless pede a regra inversa; a "
               "granularidade por regra vem de o atributo estar dentro de cada ingress_security_rules"}),
    ("oci", "oci_core_security_list", "connection_state", "egress_per_rule", O + "core_security_list.html.markdown",
     "* `stateless` - (Optional) (Updatable) A stateless rule allows traffic in one direction. Remember to add a "
     "corresponding stateless rule in the other direction if you need to support bidirectional traffic. For "
     "example, if egress", None, "interpreted",
     {"aspect": "rule_connection_state", "rule": "I-PILOT-READING", "attribute": "egress_security_rules.stateless",
      "block_path": "egress_security_rules",
      "granularity": "per_rule", "default": "stateful", "as_of": "2026-10-21",
      "stateless_needs_reverse_rule": True,
      "basis": "a frase diz o default (false = stateful) e que regra stateless pede a regra inversa; a "
               "granularidade por regra vem de o atributo estar dentro de cada egress_security_rules"}),
    ("oci", "oci_core_network_security_group_security_rule", "connection_state", "per_rule",
     O + "core_network_security_group_security_rule.html.markdown",
     "* `stateless` - (Optional) A stateless rule allows traffic", None, "interpreted",
     {"aspect": "rule_connection_state", "rule": "I-PILOT-READING", "attribute": "stateless",
      "granularity": "per_rule", "default": "stateful", "as_of": "2026-10-21",
      "stateless_needs_reverse_rule": True,
      "basis": "a frase diz o default (false = stateful); cada instância deste tipo é uma regra"}),
    # ---------------- armazenamento
    ("aws", "aws_s3_account_public_access_block", "identity", "one_per_account",
     A + "s3_account_public_access_block.html.markdown", "Each AWS account may only have one", None, "published",
     {"aspect": "cardinality", "rule": "C-PILOT-LITERAL", "per": "account", "max": 1}),
    ("aws", "aws_s3_bucket_public_access_block", "lifecycle_controller", "skip_destroy",
     A + "s3_bucket_public_access_block.html.markdown", "Setting `skip_destroy` to `true`", None, "published",
     {"aspect": "destroy_effect", "rule": "C-PILOT-LITERAL", "attribute": "skip_destroy", "when": True,
      "effect": "not_deleted"}),
    ("azurerm", "azurerm_storage_account", "effective_scope", "nested_public", Z + "storage_account.html.markdown",
     "* `allow_nested_items_to_be_public` -", None, "published",
     {"aspect": "attribute_scope", "rule": "C-PILOT-LITERAL", "attribute": "allow_nested_items_to_be_public",
      "scope": "account", "governs": "nested items within this account opting into being public",
      "default": False, "as_of": "2026-10-29"}),
    ("azurerm", "azurerm_storage_container", "effective_scope", "gated_by_account",
     Z + "storage_container.html.markdown", "* `container_access_type` -", None, "interpreted",
     {"aspect": "effective_public_access", "rule": "I-PILOT-READING", "attribute": "container_access_type",
      "gated_by": "azurerm_storage_account.allow_nested_items_to_be_public",
      "effective_public_when": "container_access_type in (blob, container) and the account allows nested items "
                               "to be public",
      "basis": "a frase do contêiner só lista os níveis; a dependência do nível da conta vem da frase de "
               "allow_nested_items_to_be_public na página da conta ('nested items ... opt into being public')"}),
    ("google", "google_storage_bucket", "effective_scope", "pap_inherited", G + "storage_bucket.html.markdown",
     "* `public_access_prevention` -", None, "interpreted",
     {"aspect": "effective_public_access_prevention", "rule": "I-PILOT-READING",
      "attribute": "public_access_prevention", "outer_scope": "organization_policy",
      "effective_enforced_when": "value = enforced, or value = inherited and the bucket is subject to the "
                                 "organization policy constraint",
      "default": "inherited", "as_of": "2026-10-26",
      "basis": "a frase diz que 'inherited' só aplica a prevenção se a política da organização a impõe; ler "
               "isso como regra de alcance efetivo (bucket ou organização) é interpretação"}),
    ("oci", "oci_objectstorage_bucket", "effect", "access_type", O + "objectstorage_bucket.html.markdown",
     "* `access_type` - (Optional)", None, "published",
     {"aspect": "bucket_public_access", "rule": "C-PILOT-LITERAL", "attribute": "access_type",
      "default": "NoPublicAccess", "as_of": "2026-10-21",
      "values_described": ["NoPublicAccess", "ObjectRead", "ObjectReadWithoutList"]}),
]


def records(ctx_by_provider: dict, bridges: dict) -> tuple[list[dict], dict]:
    out, st = [], {"published": 0, "interpreted": 0, "gap_unknown": 0, "missing": []}
    for (p, T, kind, key, rel, needle, sentence, level, value) in ENTRIES:
        ctx = ctx_by_provider[p]
        if T not in set(extract.sources.types(p)):
            st["missing"].append(f"{p}:{T} fora do schema fixado")
            continue
        ln = common.find_line(p, rel, needle)
        if ln is None:
            st["missing"].append(f"{p}:{T}:{key} frase não achada")
            continue
        doc = common.doc_cite(p, rel, ln, sentence)
        if common.resolve_doc(p, doc) is not None:
            st["missing"].append(f"{p}:{T}:{key} frase não resolve")
            continue
        api = bridges[p].get(T) or {"service": "UNKNOWN", "resource": "UNKNOWN"}
        ctx.add(T, kind, f"curated:{key}", api, "stated", level, value=value, doc=doc,
                model=common.MODEL_ID if level == "interpreted" else None)
        st[level] += 1
    for slice_types, kinds in ((NET_TYPES, NET_KINDS), (STO_TYPES, STO_KINDS)):
        for p, ts in slice_types.items():
            ctx = ctx_by_provider[p]
            have = {(r["terraform_resource_type"], r["fact_kind"]) for r in ctx.recs if r["status"] == "stated"}
            for T in ts:
                if T not in set(extract.sources.types(p)):
                    st["missing"].append(f"{p}:{T} fora do schema fixado")
                    continue
                tsr = extract.sources.typesub(p)[0].get(T)
                page = tsr["doc_file"] if tsr else None
                api = bridges[p].get(T) or {"service": "UNKNOWN", "resource": "UNKNOWN"}
                for kind in kinds:
                    if (T, kind) in have:
                        continue
                    doc, cit = extract.absent_cite(ctx, T, page)
                    ctx.add(T, kind, "unknown", api, "unknown", "published", reason="not_documented", doc=doc,
                            cit=cit)
                    st["gap_unknown"] += 1
    return out, st
