"""CC-14: guias oficiais dos provedores como fonte PUBLICADA (páginas HTML baixadas como dado não confiável).

Lote: $BO_DATA/downloads/guides-cc14/ (SOURCE.txt com URL oficial, data e sha256; promovido dentro da trava).
O HTML só é lido como texto: text_lines() tira script/style, troca tags por quebra de linha, desfaz entidades e
junta espaços; a linha N desse texto é o ponteiro. Citação (web_citation): uri = URL oficial; section =
"guide <arquivo> sha256 <h> L<n>"; sentence = trecho literal da linha N. resolve() recalcula.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from functools import lru_cache

from . import common

DIR = "guides-cc14"
SECTION_RX = re.compile(r"^guide (?P<file>\S+) sha256 (?P<sha>[0-9a-f]{64}) L(?P<line>\d+)$")


def ddir():
    d = common.bo_data() / "downloads" / DIR
    return d if d.exists() else common.bo_data() / "downloads" / (DIR + ".staging")


@lru_cache(maxsize=1)
def meta() -> dict:
    p = ddir() / "FILES.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"files": {}}


@lru_cache(maxsize=16)
def sha(f: str) -> str:
    return hashlib.sha256((ddir() / f).read_bytes()).hexdigest()


@lru_cache(maxsize=16)
def text_lines(f: str) -> tuple[str, ...]:
    t = (ddir() / f).read_text(encoding="utf-8", errors="replace")
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?i)<(br|/p|/li|/h[1-6]|/div|/td|/tr|/dt|/dd|p|li|h[1-6]|div|tr)\b[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    out = []
    for ln in t.split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            out.append(ln)
    return tuple(out)


def find(f: str, needle: str) -> int | None:
    for i, ln in enumerate(text_lines(f)):
        if needle in ln:
            return i + 1
    return None


def cite(f: str, line: int, sentence: str) -> dict:
    m = meta()["files"][f]
    return {"uri": m["url"], "retrieved_at": m["retrieved_at"], "section": f"guide {f} sha256 {sha(f)} L{line}",
            "sentence": sentence}


def resolve(cit: dict) -> str | None:
    m = SECTION_RX.match(cit.get("section", ""))
    if not m or m["file"] not in meta()["files"]:
        return "guia fora do lote fixado"
    if m["sha"] != sha(m["file"]) or meta()["files"][m["file"]]["sha256"] != m["sha"]:
        return "sha256 do guia não confere"
    if cit.get("uri") != meta()["files"][m["file"]]["url"]:
        return "uri não é a do guia fixado"
    lines = text_lines(m["file"])
    n = int(m["line"])
    if not 1 <= n <= len(lines):
        return "linha fora do guia"
    window = " ".join(lines[n - 1:n + 5])
    pos = window.find(cit.get("sentence", "\0"))
    if pos < 0 or pos > len(lines[n - 1]):
        return "frase não começa na linha citada do guia"
    return None


# (provedor, tipos, fact_kind, chave, arquivo, frase literal curta, value) — rodada CC-14
ENTRIES = [
    ("aws", ["aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule",
             "aws_vpc_security_group_egress_rule"], "connection_state", "aws_sg_stateful",
     "aws-vpc-security-groups.html", "Security groups are stateful.",
     {"aspect": "stateful", "stateful": True}),
    ("aws", ["aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule",
             "aws_vpc_security_group_egress_rule"], "effect", "aws_sg_allow_only",
     "aws-vpc-security-group-rules.html", "You can specify allow rules, but not deny rules.",
     {"aspect": "allow_only", "allow_only": True}),
    ("aws", ["aws_network_acl", "aws_network_acl_rule"], "connection_state", "aws_nacl_stateless",
     "aws-vpc-network-acls.html", "NACLs are stateless", {"aspect": "stateful", "stateful": False}),
    ("aws", ["aws_network_acl", "aws_network_acl_rule"], "effect", "aws_nacl_allow_deny",
     "aws-vpc-network-acls.html", "rule can either allow or deny traffic",
     {"aspect": "allow_only", "allow_only": False, "actions": ["allow", "deny"]}),
    ("google", ["google_compute_firewall"], "connection_state", "gcp_fw_stateful", "gcp-firewalls.html",
     "VPC firewall rules are stateful", {"aspect": "stateful", "stateful": True}),
    ("google", ["google_compute_firewall"], "effect", "gcp_fw_implied_deny_ingress", "gcp-firewalls.html",
     "the allow ingress firewall rules override the implied deny ingress rule",
     {"aspect": "implied_rule", "direction": "ingress", "action": "deny"}),
    ("google", ["google_compute_firewall"], "effect", "gcp_fw_implied_allow_egress", "gcp-firewalls.html",
     "the deny egress firewall rules override the implied allow egress rule",
     {"aspect": "implied_rule", "direction": "egress", "action": "allow"}),
    ("azurerm", ["azurerm_network_security_group", "azurerm_network_security_rule"], "precedence",
     "az_nsg_priority_unique", "azure-nsg-overview.html",
     "You can't create two security rules with the same priority and direction.",
     {"aspect": "priority_unique_scope", "unique_within": ["network_security_group", "direction"]}),
    ("azurerm", ["azurerm_network_security_group", "azurerm_network_security_rule"], "precedence",
     "az_nsg_evaluation", "azure-nsg-overview.html",
     "Rules are processed in priority order, with lower numbers processed before higher numbers because lower "
     "numbers have higher priority. Once traffic matches a rule, processing stops.",
     {"aspect": "evaluation", "order": "lower_value_first", "first_match_stops": True}),
    ("oci", ["oci_core_security_list", "oci_core_network_security_group_security_rule"], "connection_state",
     "oci_rule_stateful_default", "oci-securityrules.html",
     "When you create a security rule, you select whether it's stateful or stateless . The difference is "
     "described in the next sections. The default is stateful.",
     {"aspect": "stateful_option", "options": ["stateful", "stateless"], "default": "stateful",
      "as_of": "2026-11-04"}),
    ("oci", ["oci_core_security_list", "oci_core_network_security_group_security_rule"], "effect",
     "oci_rule_allows", "oci-securityrules.html",
     "A security rule allows a particular type of traffic in or out of a VNIC.",
     {"aspect": "rule_allows", "rule_action": "allow"}),
    ("oci", ["oci_core_security_list", "oci_core_network_security_group_security_rule"], "effect",
     "oci_no_rules_no_traffic", "oci-securityrules.html",
     "Without security rules, no traffic is allowed in and out of VNICs in the VCN.",
     {"aspect": "default_without_rules", "traffic": "none allowed"}),
    ("oci", ["oci_core_network_security_group_security_rule"], "effective_scope", "oci_nsg_rules_apply_vnics",
     "oci-nsg.html", "security rules that apply only to a set of VNICs in a single VCN",
     {"aspect": "rule_applies_to", "applies_to": "set of VNICs in the NSG"}),
    ("oci", ["oci_core_network_security_group_security_rule"], "effective_scope", "oci_nsg_rules_define_vnics",
     "oci-nsg.html", "The NSG's Security rules define the types of traffic allowed in and out of the VNICs in the "
     "group.", {"aspect": "rule_applies_to", "applies_to": "VNICs in the group"}),
]


def records(ctxs: dict, bridges: dict) -> dict:
    from . import sources
    st = {"published": 0, "missing": [], "list": []}
    if not meta()["files"]:
        st["missing"].append("lote de guias ausente")
        return st
    for p, types_, kind, key, f, sentence, value in ENTRIES:
        ln = None
        lines = text_lines(f)
        for i in range(len(lines)):
            w = " ".join(lines[i:i + 6])
            pos = w.find(sentence)
            if 0 <= pos <= len(lines[i]):
                ln = i + 1
                break
        if ln is None:
            st["missing"].append(f"{key}: frase não achada")
            continue
        cit = cite(f, ln, sentence)
        for T in types_:
            if T not in set(sources.types(p)):
                st["missing"].append(f"{key}: {T} fora do schema")
                continue
            api = bridges[p].get(T) or {"service": "UNKNOWN", "resource": "UNKNOWN"}
            ctxs[p].add(T, kind, f"guide:{key}", api, "stated", "published",
                        value=dict(value, rule="C-GUIDE-LITERAL", guide=f), cit=cit)
            st["published"] += 1
        st["list"].append({"key": key, "file": f, "line": ln, "sentence": sentence, "types": types_,
                           "fact_kind": kind})
    return st
