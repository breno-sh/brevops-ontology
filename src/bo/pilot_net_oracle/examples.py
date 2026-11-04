"""Exemplos documentados de cada provedor: a frase da doc fixada (via SERVICE-EVIDENCE) vira configuração e fluxo,
e a resposta esperada é a que a frase diz. O G1 (pytest em pilot/net/oracle) exige que o avaliador reproduza todos."""
from __future__ import annotations

from .authoring import E, F, R, RET, aws, azure, gcp, oci, targets

NET, ANY = "203.0.113.0/24", "0.0.0.0/0"


def _ex(eid, provider, evidence, quote, config, flows, decisions, validity="VALID"):
    return {"example_id": eid, "provider": provider, "evidence_id": evidence, "quote": quote,
            "fixture": {"fixture_id": eid, "provider": provider, "config": config, "targets": targets(provider),
                        "read": {"completeness": "complete", "not_read": [], "withheld": []}, "flows": flows},
            "expected": {"decisions": decisions, "validity": {"value": validity}}}


def examples() -> list:
    f22 = [F("x1", "ingress", "tcp", 22, "203.0.113.5")]
    return [
        _ex("DOC-GCP-01", "google", "SE-google-n2ccqgtmt4jm72sp",
            "a rule with priority 0 has higher precedence than a rule with priority 1",
            gcp([R("ingress", "tcp", (22, 22), ANY, "allow", 0, name="p0"), R("ingress", "tcp", (22, 22), ANY, "deny", 1, name="p1")]),
            f22, {"x1": E("ALLOW", "prioridade 0 vence 1")}),
        _ex("DOC-GCP-02", "google", "SE-google-t45d32hahm5ikdc3",
            "DENY rules take precedence over ALLOW rules having equal priority",
            gcp([R("ingress", "tcp", (22, 22), ANY, "allow", 700, name="a"), R("ingress", "tcp", (22, 22), ANY, "deny", 700, name="d")]),
            f22, {"x1": E("DENY", "empate: deny")}),
        _ex("DOC-GCP-03", "google", "SE-google-dcmc4qigsgr3wxue", "When not specified, the value assumed is 1000",
            gcp([R("ingress", "tcp", (22, 22), ANY, "allow", None, name="a"), R("ingress", "tcp", (22, 22), ANY, "deny", 1001, name="d")]),
            f22, {"x1": E("ALLOW", "allow sem prioridade = 1000 < 1001")}),
        _ex("DOC-GCP-04", "google", "SE-google-dcmc4qigsgr3wxue", "When not specified, the value assumed is 1000",
            gcp([R("ingress", "tcp", (22, 22), ANY, "allow", None, name="a"), R("ingress", "tcp", (22, 22), ANY, "deny", 999, name="d")]),
            f22, {"x1": E("DENY", "deny 999 < 1000")}),
        _ex("DOC-GCP-05", "google", "SE-google-n2ccqgtmt4jm72sp", "This is an integer between 0 and 65535, both inclusive",
            gcp([R("ingress", "tcp", (22, 22), ANY, "allow", 70000, name="a")]),
            f22, {"x1": E("ALLOW", "única regra casa (a validade é que reprova)")}, validity="INVALID"),
        _ex("DOC-AZ-01", "azurerm", "SE-azurerm-hfppj5whireqkdcl",
            "The lower the priority number, the higher the priority of the rule",
            azure([R("ingress", "tcp", (22, 22), ANY, "deny", 100, name="d"), R("ingress", "tcp", (22, 22), NET, "allow", 200, name="a")]),
            f22, {"x1": E("DENY", "100 antes de 200")}),
        _ex("DOC-AZ-02", "azurerm", "SE-azurerm-hfppj5whireqkdcl", "The value can be between 100 and 4096",
            azure([R("ingress", "tcp", (22, 22), ANY, "allow", 50, name="a")]),
            f22, {"x1": E("ALLOW", "única regra casa (a validade é que reprova)")}, validity="INVALID"),
        _ex("DOC-AZ-03", "azurerm", "SE-azurerm-hfppj5whireqkdcl",
            "The priority number must be unique for each rule in the collection",
            azure([R("ingress", "tcp", (22, 22), ANY, "allow", 300, name="a"), R("ingress", "tcp", (443, 443), ANY, "allow", 300, name="b")]),
            f22, {"x1": E("ALLOW", "só a regra 22 casa")}, validity="INVALID"),
        _ex("DOC-AZ-04", "azurerm", "SE-azurerm-x42gvfavlctlsm6r", "Possible values are `Allow` and `Deny`",
            azure([R("ingress", "tcp", (22, 22), ANY, "deny", 100, name="d")]),
            f22, {"x1": E("DENY", "access = Deny")}),
        _ex("DOC-OCI-01", "oci", "SE-oci-bp7mulbmn76camow",
            "if ingress traffic allows TCP destination port 80, there should be an egress rule to allow TCP source port 80",
            oci([R("ingress", "tcp", (80, 80), NET, stateless=True), R("egress", "tcp", None, NET, stateless=True, src_ports=(80, 80))]),
            [F("x1", "ingress", "tcp", 80, "203.0.113.5"), RET("x1r", "x1")],
            {"x1": E("ALLOW", "entrada 80"), "x1r": E("ALLOW", "a regra de saída com porta de origem 80 deixa o retorno passar")}),
        _ex("DOC-OCI-02", "oci", "SE-oci-bp7mulbmn76camow",
            "A stateless rule allows traffic in one direction",
            oci([R("ingress", "tcp", (80, 80), NET, stateless=True)]),
            [F("x1", "ingress", "tcp", 80, "203.0.113.5"), RET("x1r", "x1")],
            {"x1": E("ALLOW", "entrada 80"), "x1r": E("DENY", "sem a regra inversa, o retorno não passa")}),
        _ex("DOC-OCI-03", "oci", "SE-oci-3ihxku562hxrgq4b",
            "Defaults to false, which means the rule is stateful and a corresponding rule is not necessary",
            oci([R("egress", "tcp", (80, 80), ANY)]),
            [F("x1", "egress", "tcp", 80, "198.51.100.7"), RET("x1r", "x1")],
            {"x1": E("ALLOW", "saída 80"), "x1r": E("ALLOW", "regra com estado: não precisa da regra inversa")}),
        _ex("DOC-AWS-01", "aws", "SE-aws-jcsq5zrpnuvxzaxv", "If nothing is specified, traffic will be blocked",
            aws([R("ingress", "tcp", (22, 22), None)]), f22, {"x1": E("DENY", "bloco sem cidr_blocks bloqueia")}),
        _ex("DOC-AWS-02", "aws", "SE-aws-jcsq5zrpnuvxzaxv", "Terraform removes this default rule",
            aws([R("ingress", "tcp", (22, 22), NET)]),
            [F("x1", "egress", "tcp", 443, "198.51.100.7")], {"x1": E("DENY", "sem bloco egress, a saída padrão foi removida")}),
    ]
