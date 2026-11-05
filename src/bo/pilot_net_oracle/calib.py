"""Fixtures de CALIBRAÇÃO da fatia NET, com as respostas escritas à mão.

Estas ficam no repositório (pilot/net/fixtures_calib/). As RETIDAS não estão aqui: foram escritas fora do
repositório e só existem cifradas em $BO_DATA/PILOT-NET-ORACLE/sealed/ (só o PILOT-EXIT abre).
Endereços: 203.0.113.0/24 e 198.51.100.0/24 (RFC 5737, documentação); alvo 10.0.1.10.
"""
from __future__ import annotations

import copy

from .authoring import E, F, R, RET, aws, azure, fixture, gcp, oci, translation

NET = "203.0.113.0/24"
IN_IP, IN_IP5, OUT_IP = "203.0.113.10", "203.0.113.5", "198.51.100.7"
ANY = "0.0.0.0/0"
S = "calib"

ALLOW, DENY, UNK = "ALLOW", "DENY", "UNKNOWN"
ME, IR, USI = "MISSING_EVIDENCE", "INCOMPLETE_READ", "UNKNOWN_SYMBOLIC_INPUT"


def gcp_catch(tags=None):
    return [R("ingress", "all", None, ANY, "deny", 65534, name="deny-in", tags=tags),
            R("egress", "all", None, ANY, "deny", 65534, name="deny-out", tags=tags)]


def az_catch():
    return [R("ingress", "all", None, ANY, "deny", 4095, name="deny-in"),
            R("egress", "all", None, ANY, "deny", 4096, name="deny-out")]


# ---------------------------------------------------------------- cenário S1 (web 443 a partir de uma /24)

S1_FLOWS = [F("f1", "ingress", "tcp", 443, IN_IP), F("f2", "ingress", "tcp", 22, IN_IP),
            F("f3", "ingress", "tcp", 443, OUT_IP), F("f4", "egress", "tcp", 443, OUT_IP), RET("f1r", "f1")]


def s1(provider, catch=True, sym_cidr=False, open_egress=False, wide=False):
    cidr = "sym:var.allowed_cidr" if sym_cidr else (ANY if wide else NET)
    if provider == "aws":
        rules = [R("ingress", "tcp", (443, 443), cidr)]
        if open_egress:
            rules.append(R("egress", "all", None, ANY))
        return aws(rules)
    if provider == "google":
        rules = [R("ingress", "tcp", (443, 443), cidr, "allow", 1000, name="allow-web")]
        if open_egress:
            rules.append(R("egress", "all", None, ANY, "allow", 1000, name="allow-out"))
        return gcp(rules + (gcp_catch() if catch else []))
    if provider == "azurerm":
        rules = [R("ingress", "tcp", (443, 443), cidr, "allow", 100, name="allow-web")]
        if open_egress:
            rules.append(R("egress", "all", None, ANY, "allow", 200, name="allow-out"))
        return azure(rules + (az_catch() if catch else []))
    rules = [R("ingress", "tcp", (443, 443), cidr)]
    if open_egress:
        rules.append(R("egress", "all", None, ANY))
    return oci(rules)


RET_WHY = {"oci": "security list: regra com estado por padrão ('Defaults to false, which means the rule is stateful')",
           "aws": "'Security groups are stateful.' (guia oficial, SE CC-14)",
           "google": "'VPC firewall rules are stateful' (guia oficial, SE CC-14)"}


def _s1_expected(provider):
    ret = E(ALLOW, RET_WHY[provider]) if provider in RET_WHY \
        else E(UNK, "estado de conexão do NSG Azure sem evidência: com estado permite, sem estado nega", ME)
    return {"f1": E(ALLOW, "regra 443 cobre a origem"), "f2": E(DENY, "nenhuma regra permite 22"),
            "f3": E(DENY, "origem fora da /24"), "f4": E(DENY, "nenhuma permissão de saída"), "f1r": ret}


# ---------------------------------------------------------------- cenário S2 (negação de precedência maior)

S2_FLOWS = [F("f1", "ingress", "tcp", 22, IN_IP5), F("f2", "ingress", "tcp", 443, OUT_IP),
            F("f3", "ingress", "tcp", 80, IN_IP5), F("f4", "egress", "tcp", 443, OUT_IP), RET("f2r", "f2")]


def s2(provider, swap=False):
    if provider == "google":
        rules = [R("ingress", "tcp", (22, 22), ANY, "deny", 100, name="deny-ssh"),
                 R("ingress", "tcp", (22, 22), NET, "allow", 200, name="allow-ssh"),
                 R("ingress", "tcp", (443, 443), ANY, "allow", 300, name="allow-web")] + gcp_catch()
    else:
        rules = [R("ingress", "tcp", (22, 22), ANY, "deny", 100, name="deny-ssh"),
                 R("ingress", "tcp", (22, 22), NET, "allow", 200, name="allow-ssh"),
                 R("ingress", "tcp", (443, 443), ANY, "allow", 300, name="allow-web")] + az_catch()
    if swap:
        rules = list(reversed(rules))
    return gcp(rules) if provider == "google" else azure(rules)


def s2_expected(provider):
    return {"f1": E(DENY, "negação de prioridade 100 vence a permissão de 200 (menor número, maior precedência)"),
            "f2": E(ALLOW, "443 permitido de qualquer origem"), "f3": E(DENY, "negação explícita de menor precedência"),
            "f4": E(DENY, "negação explícita de saída"),
            "f2r": E(ALLOW, RET_WHY["google"]) if provider == "google" else E(UNK, "estado de conexão do NSG Azure sem evidência", ME)}


def fixtures() -> list:
    out = []
    add = out.append
    # ======================== NET-C01 embalagem
    r01 = [R("ingress", "tcp", (443, 443), NET), R("ingress", "tcp", (8000, 8080), "198.51.100.0/24")]
    fl01 = [F("f1", "ingress", "tcp", 443, IN_IP), F("f2", "ingress", "tcp", 8080, OUT_IP), F("f3", "ingress", "tcp", 22, IN_IP)]
    ex01 = {"f1": E(ALLOW, "regra 443"), "f2": E(ALLOW, "faixa 8000-8080 da 198.51.100.0/24"), "f3": E(DENY, "nada permite 22")}
    chk_inv = {"kind": "invariant", "assertion": "unidades(embutida) == unidades(separada) e decisões iguais"}
    add(fixture("NETC-C01-AWS-INLINE", S, "NET-C01", "positive", "aws", aws(r01), fl01, ex01,
                summary="duas regras embutidas no grupo de segurança", commitments=["CMT-FW-P01"], check=chk_inv,
                invariant_with="NETC-C01-AWS-SEP"))
    add(fixture("NETC-C01-AWS-SEP", S, "NET-C01", "positive", "aws", aws(r01, separate=True), fl01, ex01,
                summary="as mesmas regras como aws_vpc_security_group_ingress_rule", commitments=["CMT-FW-P01"],
                check=chk_inv, invariant_with="NETC-C01-AWS-INLINE"))
    raz = [R("ingress", "tcp", (443, 443), NET, "allow", 100, name="allow-web")] + az_catch()
    flaz = [F("f1", "ingress", "tcp", 443, IN_IP), F("f2", "ingress", "tcp", 22, IN_IP)]
    exaz = {"f1": E(ALLOW, "permissão de prioridade 100"), "f2": E(DENY, "negação explícita 4095")}
    add(fixture("NETC-C01-AZ-INLINE", S, "NET-C01", "positive", "azurerm", azure(raz), flaz, exaz,
                summary="security_rule embutido no NSG", commitments=["CMT-FW-P01"], check=chk_inv,
                invariant_with="NETC-C01-AZ-SEP"))
    add(fixture("NETC-C01-AZ-SEP", S, "NET-C01", "positive", "azurerm", azure(raz, separate=True), flaz, exaz,
                summary="as mesmas regras como azurerm_network_security_rule", commitments=["CMT-FW-P01"],
                check=chk_inv, invariant_with="NETC-C01-AZ-INLINE"))
    ro = R("ingress", "tcp", (443, 443), NET)
    ro["sg"] = "other"
    add(fixture("NETC-C01-AWS-OTHER", S, "NET-C01", "negative", "aws",
                aws([ro], separate=True, extra_sgs=("other",), attach=("web",)),
                [F("f1", "ingress", "tcp", 443, IN_IP)],
                {"f1": E(DENY, "a regra separada é do grupo 'other', que não está anexado a vm1")},
                summary="regra separada ligada a outro grupo: não é a mesma decomposição",
                commitments=["CMT-FW-P01"],
                check={"kind": "not_entails", "assertion": "NOT decision(f1) = allow AND parent(regra) != web"}))
    add(fixture("NETC-C01-AWS-SYM", S, "NET-C01", "unknown", "aws",
                aws([R("ingress", "tcp", (443, 443), NET)], separate=True, sym_parent=True),
                [F("f1", "ingress", "tcp", 443, IN_IP), F("f2", "ingress", "tcp", 22, IN_IP)],
                {"f1": E(UNK, "a pertença da regra 443 ao grupo não se resolve", USI),
                 "f2": E(DENY, "nenhuma regra, lida ou não resolvida, cobre 22")},
                summary="regra separada com security_group_id não resolvido", commitments=["CMT-FW-P01", "CMT-NIC-U02"],
                check={"kind": "unknown", "assertion": "decision(f1) = UNKNOWN; parent(regra) = UNKNOWN"}))
    # ======================== NET-C02 estado do conjunto e retorno
    for prov, fid, pol, chk in (
            ("oci", "NETC-C02-OCI-STATEFUL", "positive", {"kind": "entails", "assertion": "decision(retorno de f1) = allow"}),
            ("aws", "NETC-C02-AWS-RET", "positive", {"kind": "entails", "assertion": "decision(retorno de f1) = allow (SG com estado, publicado)"}),
            ("google", "NETC-C02-GCP-RET", "positive", {"kind": "entails", "assertion": "decision(retorno de f1) = allow (firewall com estado, publicado)"}),
            ("azurerm", "NETC-C02-AZ-RET", "unknown", {"kind": "unknown", "assertion": "decision(retorno de f1) = UNKNOWN"})):
        add(fixture(fid, S, "NET-C02", pol, prov, s1(prov), S1_FLOWS, _s1_expected(prov),
                    summary=f"cenário S1 em {prov}: só regra de entrada 443; retorno de f1",
                    commitments=["CMT-FW-P02", "CMT-FW-U03"], check=chk))
    add(fixture("NETC-C02-OCI-STATELESS", S, "NET-C02", "negative", "oci",
                oci([R("ingress", "tcp", (443, 443), NET, stateless=True)]),
                [F("f1", "ingress", "tcp", 443, IN_IP), RET("f1r", "f1")],
                {"f1": E(ALLOW, "regra 443 sem estado"),
                 "f1r": E(DENY, "'A stateless rule allows traffic in one direction': sem regra de saída, o retorno não passa")},
                summary="regra sem estado, sem regra de saída", commitments=["CMT-FW-P03"],
                check={"kind": "not_entails", "assertion": "NOT decision(retorno de f1) = allow"}))
    # ======================== NET-C03 estado por regra (OCI)
    mixed = [R("ingress", "tcp", (443, 443), NET), R("ingress", "tcp", (8080, 8080), NET, stateless=True)]
    fl03 = [F("f1", "ingress", "tcp", 443, IN_IP), F("f2", "ingress", "tcp", 8080, IN_IP), RET("f1r", "f1"), RET("f2r", "f2")]
    add(fixture("NETC-C03-OCI-MIXED-REV", S, "NET-C03", "positive", "oci",
                oci(mixed + [R("egress", "tcp", None, NET, stateless=True, src_ports=(8080, 8080))]), fl03,
                {"f1": E(ALLOW, "regra 443"), "f2": E(ALLOW, "regra 8080"),
                 "f1r": E(ALLOW, "regra 443 com estado (padrão)"),
                 "f2r": E(ALLOW, "regra de saída sem estado com porta de origem 8080, como a doc pede")},
                summary="regra com estado e regra sem estado com a regra inversa", commitments=["CMT-FW-P03"],
                check={"kind": "entails", "assertion": "decision(retorno de f1) = allow AND decision(retorno de f2) = allow"}))
    add(fixture("NETC-C03-OCI-MIXED", S, "NET-C03", "negative", "oci", oci(mixed), fl03,
                {"f1": E(ALLOW, "regra 443"), "f2": E(ALLOW, "regra 8080"),
                 "f1r": E(ALLOW, "regra com estado"), "f2r": E(DENY, "regra sem estado e nenhuma regra de saída")},
                summary="CMT-FW-P03 em security list: o retorno da regra sem estado não é automático",
                commitments=["CMT-FW-P03"],
                check={"kind": "not_entails", "assertion": "NOT decision(retorno de f2) = allow"}))
    add(fixture("NETC-C03-OCI-OVERLAP", S, "NET-C03", "unknown", "oci",
                oci([R("ingress", "tcp", (443, 443), NET), R("ingress", "tcp", (443, 443), ANY, stateless=True)]),
                [F("f1", "ingress", "tcp", 443, IN_IP), RET("f1r", "f1")],
                {"f1": E(ALLOW, "as duas regras permitem"),
                 "f1r": E(UNK, "o pacote casa regra com estado e regra sem estado: o rastreio não tem evidência", ME)},
                summary="sobreposição de regra com estado e sem estado", commitments=["CMT-FW-P03"],
                check={"kind": "unknown", "assertion": "decision(retorno de f1) = UNKNOWN"}))
    add(fixture("NETC-C03-OCI-NSG-SYM", S, "NET-C03", "unknown", "oci",
                oci([R("ingress", "tcp", (22, 22), NET, stateless="sym:var.stateless")], kind="nsg"),
                [F("f1", "ingress", "tcp", 22, IN_IP), RET("f1r", "f1")],
                {"f1": E(ALLOW, "regra 22 do NSG"), "f1r": E(UNK, "stateless vem de variável", USI)},
                summary="regra de NSG com estado simbólico", commitments=["CMT-FW-P03", "CMT-CFG-U01"],
                check={"kind": "unknown", "assertion": "decision(retorno de f1) = UNKNOWN"}))
    add(fixture("NETC-C03-OCI-NSG-REV", S, "NET-C03", "positive", "oci",
                oci([R("ingress", "tcp", (22, 22), NET, stateless=True),
                     R("egress", "tcp", None, NET, stateless=True, src_ports=(22, 22))], kind="nsg"),
                [F("f1", "ingress", "tcp", 22, IN_IP), RET("f1r", "f1"), F("f5", "egress", "tcp", 443, IN_IP)],
                {"f1": E(ALLOW, "regra 22 sem estado"), "f1r": E(ALLOW, "regra inversa com porta de origem 22"),
                 "f5": E(DENY, "a regra de saída exige porta de origem 22; o fluxo novo sai da 49152")},
                summary="NSG: regra sem estado e a regra inversa", commitments=["CMT-FW-P03"],
                check={"kind": "entails", "assertion": "decision(retorno de f1) = allow"}))
    # ======================== NET-C04 precedência
    add(fixture("NETC-C04-GCP-DENY-WINS", S, "NET-C04", "positive", "google", s2("google"), S2_FLOWS, s2_expected("google"),
                summary="deny 22 prioridade 100 sobre allow 22 prioridade 200", commitments=["CMT-FW-P04", "CMT-FW-P06"],
                check={"kind": "entails", "assertion": "decision(f1) = deny"}, invariant_with="NETC-C04-GCP-DENY-WINS-SWAP"))
    add(fixture("NETC-C04-GCP-DENY-WINS-SWAP", S, "NET-C04", "positive", "google", s2("google", swap=True), S2_FLOWS,
                s2_expected("google"), summary="as mesmas regras em ordem textual inversa", commitments=["CMT-FW-P06"],
                check={"kind": "invariant", "assertion": "decision(f1, base) == decision(f1, invertida) == deny"},
                invariant_with="NETC-C04-GCP-DENY-WINS"))
    add(fixture("NETC-C04-AZ-DENY-WINS", S, "NET-C04", "positive", "azurerm", s2("azurerm"), S2_FLOWS, s2_expected("azurerm"),
                summary="NSG: Deny 100 sobre Allow 200", commitments=["CMT-FW-P04"],
                check={"kind": "entails", "assertion": "decision(f1) = deny"}))
    add(fixture("NETC-C04-GCP-ALLOW-FIRST", S, "NET-C04", "negative", "google",
                gcp([R("ingress", "tcp", (22, 22), NET, "allow", 100, name="allow-ssh"),
                     R("ingress", "tcp", (22, 22), ANY, "deny", 200, name="deny-ssh")] + gcp_catch()),
                [F("f1", "ingress", "tcp", 22, IN_IP5), F("f2", "ingress", "tcp", 22, OUT_IP)],
                {"f1": E(ALLOW, "allow de prioridade 100 vence deny de 200"), "f2": E(DENY, "fora da /24 só a negação casa")},
                summary="permissão com precedência maior que a negação", commitments=["CMT-FW-P04"],
                check={"kind": "not_entails", "assertion": "NOT decision(f1) = deny (negação não vence sempre)"}))
    add(fixture("NETC-C04-AZ-NOCATCH", S, "NET-C04", "unknown", "azurerm",
                azure([R("ingress", "tcp", (443, 443), NET, "allow", 100, name="allow-web")]),
                [F("f1", "ingress", "tcp", 443, IN_IP), F("f2", "ingress", "tcp", 22, IN_IP), F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f1": E(ALLOW, "permissão 100"), "f2": E(UNK, "sem regra que case; regras padrão do NSG sem evidência", ME),
                 "f4": E(UNK, "sem regra de saída; padrão sem evidência", ME)},
                summary="NSG sem negação explícita", commitments=["CMT-FW-U01"],
                check={"kind": "unknown", "assertion": "decision(f2) = UNKNOWN"}))
    # ======================== NET-C05 desempate e prioridade repetida
    add(fixture("NETC-C05-GCP-TIE", S, "NET-C05", "positive", "google",
                gcp([R("ingress", "tcp", (22, 22), NET, "allow", 500, name="allow-ssh"),
                     R("ingress", "tcp", (22, 22), ANY, "deny", 500, name="deny-ssh")] + gcp_catch()),
                [F("f1", "ingress", "tcp", 22, IN_IP5)],
                {"f1": E(DENY, "'DENY rules take precedence over ALLOW rules having equal priority'")},
                summary="allow e deny com a mesma prioridade", commitments=["CMT-FW-U02"],
                check={"kind": "entails", "assertion": "decision(f1) = deny"}))
    add(fixture("NETC-C05-AZ-DUP", S, "NET-C05", "negative", "azurerm",
                azure([R("ingress", "tcp", (22, 22), NET, "allow", 200, name="allow-ssh"),
                       R("ingress", "tcp", (22, 22), ANY, "deny", 200, name="deny-ssh")] + az_catch()),
                [F("f1", "ingress", "tcp", 22, IN_IP5)],
                {"f1": E(UNK, "configuração recusada pela doc; desempate também sem evidência", ME)},
                validity={"value": "INVALID", "code": "INCONSISTENT"},
                summary="duas regras de entrada com a mesma prioridade", commitments=["CMT-FW-U02"],
                check={"kind": "rejects", "assertion": "configuração com prioridade repetida na mesma direção é inválida"}))
    add(fixture("NETC-C05-AZ-DUP-DIRS", S, "NET-C05", "positive", "azurerm",
                azure([R("ingress", "tcp", (443, 443), NET, "allow", 300, name="allow-web"),
                       R("egress", "tcp", (443, 443), ANY, "allow", 300, name="allow-out")] + az_catch()),
                [F("f1", "ingress", "tcp", 443, IN_IP), F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f1": E(ALLOW, "permissão 300 de entrada"), "f4": E(ALLOW, "permissão 300 de saída")},
                summary="mesma prioridade em direções diferentes", commitments=["CMT-FW-U02"],
                check={"kind": "entails", "assertion": "validade = VALID ('same priority and direction' é o que a guia proíbe)"}))
    add(fixture("NETC-C05-AZ-SYM-PRIO", S, "NET-C05", "unknown", "azurerm",
                azure([R("ingress", "tcp", (22, 22), NET, "allow", 200, name="allow-ssh"),
                       R("ingress", "tcp", (22, 22), ANY, "deny", "sym:var.deny_priority", name="deny-ssh")] + az_catch()),
                [F("f1", "ingress", "tcp", 22, IN_IP5)],
                {"f1": E(UNK, "a prioridade da negação vem de variável: pode vir antes ou depois de 200", USI)},
                summary="prioridade simbólica no NSG", commitments=["CMT-FW-U02", "CMT-CFG-U01"],
                check={"kind": "unknown", "assertion": "decision(f1) = UNKNOWN"}))
    # ======================== NET-C06 direção
    eg = [R("egress", "tcp", (443, 443), ANY)]
    add(fixture("NETC-C06-AWS-EGRESS", S, "NET-C06", "positive", "aws", aws(eg), [F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f4": E(ALLOW, "regra de saída 443")}, summary="regra de saída permite saída",
                commitments=["CMT-FW-N03"], check={"kind": "entails", "assertion": "decision(f4) = allow"}))
    add(fixture("NETC-C06-AWS-INGRESS-NEW", S, "NET-C06", "negative", "aws", aws(eg),
                [F("f1", "ingress", "tcp", 443, OUT_IP)], {"f1": E(DENY, "a regra é de saída")},
                summary="só regra de saída; conexão nova de entrada", commitments=["CMT-FW-N03"],
                check={"kind": "not_entails", "assertion": "NOT decision(f1) = allow"}))
    add(fixture("NETC-C06-OCI-INGRESS-NEW", S, "NET-C06", "negative", "oci", oci(eg),
                [F("f1", "ingress", "tcp", 443, OUT_IP), F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f1": E(DENY, "a regra é de saída"), "f4": E(ALLOW, "regra de saída")},
                summary="security list só com saída", commitments=["CMT-FW-N03"],
                check={"kind": "not_entails", "assertion": "NOT decision(f1) = allow"}))
    add(fixture("NETC-C06-GCP-INGRESS-NOMATCH", S, "NET-C06", "negative", "google",
                gcp([R("egress", "tcp", (443, 443), ANY, "allow", 1000, name="allow-out")]),
                [F("f1", "ingress", "tcp", 443, OUT_IP), F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f1": E(DENY, "nenhuma regra de entrada; vale a regra implícita de entrada que nega (guia oficial, SE CC-14)"),
                 "f4": E(ALLOW, "regra de saída 443")},
                summary="firewall só de saída", commitments=["CMT-FW-N03"],
                check={"kind": "not_entails", "assertion": "NOT decision(f1) = allow"}))
    add(fixture("NETC-C06-AZ-OUT-ONLY", S, "NET-C06", "unknown", "azurerm",
                azure([R("egress", "tcp", (443, 443), ANY, "allow", 100, name="allow-out")]),
                [F("f1", "ingress", "tcp", 443, OUT_IP), F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f1": E(UNK, "nenhuma regra de entrada; regras padrão do NSG sem evidência", ME), "f4": E(ALLOW, "saída 443")},
                summary="NSG só de saída, sem negação explícita", commitments=["CMT-FW-N03", "CMT-FW-U01"],
                check={"kind": "unknown", "assertion": "decision(f1) = UNKNOWN (não ALLOW)"}))
    # ======================== NET-C07 leitura parcial
    pr = {"completeness": "partial", "not_read": [{"of": "aws_security_group.web", "what": "rules"}], "withheld": []}
    add(fixture("NETC-C07-AWS-PARTIAL-ALLOW", S, "NET-C07", "positive", "aws", s1("aws"),
                [F("f1", "ingress", "tcp", 443, IN_IP)],
                {"f1": E(ALLOW, "só permissão: regra não lida não tira a permissão lida")},
                read=pr, summary="grupo lido pela metade; fluxo coberto por regra lida", commitments=["CMT-FW-U01"],
                check={"kind": "entails", "assertion": "decision(f1) = allow"}))
    add(fixture("NETC-C07-AWS-PARTIAL-22", S, "NET-C07", "unknown", "aws", s1("aws"),
                [F("f2", "ingress", "tcp", 22, IN_IP)],
                {"f2": E(UNK, "negação implícita só vale sob leitura completa", IR)},
                read=pr, summary="grupo lido pela metade; fluxo sem regra lida", commitments=["CMT-FW-U01"],
                check={"kind": "unknown", "assertion": "decision(f2) = UNKNOWN"}))
    prg = {"completeness": "partial", "not_read": [{"of": "google_compute_network.net", "what": "rules"}], "withheld": []}
    add(fixture("NETC-C07-GCP-PARTIAL", S, "NET-C07", "negative", "google", s1("google"),
                [F("f1", "ingress", "tcp", 443, IN_IP)],
                {"f1": E(UNK, "regra não lida de prioridade maior pode negar", IR)},
                read=prg, summary="firewall lido pela metade; permissão lida de prioridade 1000",
                commitments=["CMT-FW-U01"],
                check={"kind": "not_entails", "assertion": "NOT decision(f1) = allow"}))
    add(fixture("NETC-C07-GCP-PARTIAL-DENY0", S, "NET-C07", "positive", "google",
                gcp([R("ingress", "tcp", (22, 22), ANY, "deny", 0, name="deny-ssh"),
                     R("ingress", "tcp", (443, 443), NET, "allow", 1000, name="allow-web")]),
                [F("f1", "ingress", "tcp", 22, IN_IP5), F("f2", "ingress", "tcp", 443, IN_IP)],
                {"f1": E(DENY, "negação na prioridade 0: regra não lida no máximo empata, e no empate deny vence"),
                 "f2": E(UNK, "regra não lida de prioridade maior que 1000 pode negar", IR)},
                read=prg, summary="negação na prioridade máxima sob leitura parcial", commitments=["CMT-FW-U01", "CMT-FW-U02"],
                check={"kind": "entails", "assertion": "decision(f1) = deny"}))
    # ======================== NET-C08 alvo
    gtag = gcp([R("ingress", "tcp", (443, 443), NET, "allow", 1000, name="allow-web", tags=["web"])] + gcp_catch(["web", "app"]),
               extra_vms=(("vm2", ["app"]),))
    add(fixture("NETC-C08-GCP-TAG", S, "NET-C08", "positive", "google", gtag,
                [F("f1", "ingress", "tcp", 443, IN_IP, "vm1")], {"f1": E(ALLOW, "vm1 tem o rótulo web")},
                vms=("vm1", "vm2"), summary="seleção por rótulo: instância com o rótulo", commitments=["CMT-FW-P05"],
                check={"kind": "entails", "assertion": "applies(allow-web) = {vm1}; decision(f1) = allow"}))
    add(fixture("NETC-C08-GCP-UNTAGGED", S, "NET-C08", "negative", "google", copy.deepcopy(gtag),
                [F("f2", "ingress", "tcp", 443, IN_IP, "vm2")],
                {"f2": E(DENY, "vm2 não tem o rótulo web; só a negação (rótulo app) se aplica")},
                vms=("vm1", "vm2"), summary="seleção por rótulo: instância sem o rótulo", commitments=["CMT-FW-P05"],
                check={"kind": "not_entails", "assertion": "NOT decision(f2) = allow"}))
    add(fixture("NETC-C08-AWS-ATTACH", S, "NET-C08", "positive", "aws", s1("aws"),
                [F("f1", "ingress", "tcp", 443, IN_IP)], {"f1": E(ALLOW, "grupo anexado a vm1")},
                summary="anexação do grupo à instância", commitments=["CMT-FW-P05"],
                check={"kind": "entails", "assertion": "applies(web) = {vm1}"}))
    cfg = aws([R("ingress", "tcp", (443, 443), NET)], extra_sgs=("base",), attach=("base",))
    cfg["resources"].append({"type": "aws_instance", "name": "vm2",
                             "values": {"vpc_security_group_ids": ["ref:aws_security_group.web"]}})
    add(fixture("NETC-C08-AWS-OTHER-VM", S, "NET-C08", "negative", "aws", cfg,
                [F("f1", "ingress", "tcp", 443, IN_IP, "vm1"), F("f2", "ingress", "tcp", 443, IN_IP, "vm2")],
                {"f1": E(DENY, "vm1 só tem o grupo base, sem regras"), "f2": E(ALLOW, "vm2 tem o grupo web")},
                vms=("vm1", "vm2"), summary="grupo anexado à outra instância", commitments=["CMT-FW-P05"],
                check={"kind": "not_entails", "assertion": "NOT decision(f1) = allow"}))
    cfg = s1("aws")
    cfg["resources"][-1]["values"]["vpc_security_group_ids"] = ["sym:var.sg_id"]
    add(fixture("NETC-C08-AWS-ATTACH-SYM", S, "NET-C08", "unknown", "aws", cfg,
                [F("f1", "ingress", "tcp", 443, IN_IP)],
                {"f1": E(UNK, "o grupo da instância vem de variável", USI)},
                summary="anexação por variável", commitments=["CMT-FW-P05", "CMT-NIC-U02"],
                check={"kind": "unknown", "assertion": "applies(web) = UNKNOWN"}))
    sub = [R("ingress", "all", None, ANY, "deny", 4095, name="deny-in")]
    for r in sub:
        r["nsg"] = "sub"
    add(fixture("NETC-C08-AZ-NIC-SUBNET", S, "NET-C08", "unknown", "azurerm",
                azure([R("ingress", "tcp", (443, 443), NET, "allow", 100, name="allow-web")] + az_catch() + sub,
                      extra_nsgs=("sub",), assoc=("nic:web", "subnet:sub")),
                [F("f1", "ingress", "tcp", 443, IN_IP)],
                {"f1": E(UNK, "NSG da NIC permite e o da sub-rede nega: combinação sem evidência", ME)},
                summary="NSG na NIC e na sub-rede", commitments=["CMT-FW-P05"],
                check={"kind": "unknown", "assertion": "decision(f1) = UNKNOWN"}))
    # ======================== NET-C09 sem regra que case
    add(fixture("NETC-C09-AWS-NOMATCH", S, "NET-C09", "positive", "aws", s1("aws"),
                [F("f2", "ingress", "tcp", 22, IN_IP)],
                {"f2": E(DENY, "'If nothing is specified, traffic will be blocked'")},
                summary="grupo de segurança: fluxo sem regra", commitments=["CMT-FW-N03"],
                check={"kind": "entails", "assertion": "decision(f2) = deny"}))
    add(fixture("NETC-C09-AWS-NO-EGRESS", S, "NET-C09", "negative", "aws", s1("aws"),
                [F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f4": E(DENY, "'Terraform removes this default rule': sem bloco egress não há saída")},
                summary="grupo sem bloco egress: a regra padrão de saída foi removida pelo Terraform",
                commitments=["CMT-FW-N03"], check={"kind": "not_entails", "assertion": "NOT decision(f4) = allow"}))
    add(fixture("NETC-C09-GCP-NOMATCH", S, "NET-C09", "positive", "google", s1("google", catch=False),
                [F("f2", "ingress", "tcp", 22, IN_IP), F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f2": E(DENY, "regra implícita de entrada nega (guia oficial, SE-google-q7fxffs3brh35x6f)"),
                 "f4": E(ALLOW, "regra implícita de saída permite (guia oficial, SE-google-lczae72rfhtxc6ad)")},
                summary="firewall sem negação explícita: regras implícitas", commitments=["CMT-FW-U01"],
                check={"kind": "entails", "assertion": "decision(f2) = deny AND decision(f4) = allow"}))
    add(fixture("NETC-C09-AZ-NOMATCH", S, "NET-C09", "unknown", "azurerm",
                azure([R("ingress", "tcp", (443, 443), NET, "allow", 100, name="allow-web")]),
                [F("f2", "ingress", "tcp", 22, IN_IP), F("f4", "egress", "tcp", 443, OUT_IP)],
                {"f2": E(UNK, "sem regra que case; regras padrão do NSG sem evidência", ME),
                 "f4": E(UNK, "sem regra de saída; padrão sem evidência", ME)},
                summary="NSG sem negação explícita", commitments=["CMT-FW-U01"],
                check={"kind": "unknown", "assertion": "decision(f2) = UNKNOWN AND decision(f4) = UNKNOWN"}))
    add(fixture("NETC-C09-OCI-NOMATCH", S, "NET-C09", "positive", "oci", s1("oci"),
                [F("f2", "ingress", "tcp", 22, IN_IP)],
                {"f2": E(DENY, "sem regra, o tráfego não passa (derivado da frase do atributo stateless)")},
                summary="security list: fluxo sem regra", commitments=["CMT-FW-N03"],
                check={"kind": "entails", "assertion": "decision(f2) = deny"}))
    return out


# ---------------------------------------------------------------- traduções (12 direções)

S1_SOURCE = {"aws": "NETC-C02-AWS-RET", "google": "NETC-C02-GCP-RET", "azurerm": "NETC-C02-AZ-RET", "oci": "NETC-C02-OCI-STATEFUL"}
S2_SOURCE = {"google": "NETC-C04-GCP-DENY-WINS", "azurerm": "NETC-C04-AZ-DENY-WINS"}
PROVS = ("aws", "google", "azurerm", "oci")


def _deny_dropped(b):
    """Contraexemplo do CMT-FW-N01: a negação some e a permissão sombreada vira permissão."""
    rules = [R("ingress", "tcp", (22, 22), NET), R("ingress", "tcp", (443, 443), ANY)]
    return aws(rules) if b == "aws" else oci(rules)


def _effective(b):
    rules = [R("ingress", "tcp", (443, 443), ANY)]
    return aws(rules) if b == "aws" else oci(rules)


STATEFUL = ("aws", "google", "oci")   # retorno de conexão definido (publicado); Azure: sem evidência


def translations() -> list:
    """Vereditos escritos à mão pelas regras do juiz e pela semântica publicada de cada lado (SE f44b9a6)."""
    out = []
    for a in PROVS:
        for b in PROVS:
            if a == b:
                continue
            d = f"{a}->{b}"
            tag = f"{a[:3].upper()}-{b[:3].upper()}"
            # ---- positivo
            if a in S2_SOURCE and b in ("aws", "oci"):
                src, tgt = S2_SOURCE[a], _effective(b)
                losses = [{"loss_id": "LOSS-NET-EFFECT-DENY", "flows": []}]
                verdict, why = "ACCEPT", "conjunto efetivo (443 de qualquer origem) sem a negação: decisões iguais"
                if a == "azurerm":
                    losses.append({"loss_id": "LOSS-NET-UNKNOWN-INPUT", "flows": ["f2r"]})
                    verdict, why = "ACCEPT_WITH_DECLARED_LOSS", why + "; retorno UNKNOWN no Azure declarado"
            else:
                src, tgt = S1_SOURCE[a], s1(b)
                losses, verdict, why = [], "ACCEPT", "decisões iguais em todos os fluxos (retorno com estado dos dois lados)"
                if a in STATEFUL and b == "azurerm":
                    losses = [{"loss_id": "LOSS-NET-STATE", "flows": ["f1r"]}]
                    verdict, why = "ACCEPT_WITH_DECLARED_LOSS", "retorno permitido na origem fica UNKNOWN no NSG Azure: declarado"
                if a == "azurerm" and b in STATEFUL:
                    losses = [{"loss_id": "LOSS-NET-UNKNOWN-INPUT", "flows": ["f1r"]}]
                    verdict, why = "ACCEPT_WITH_DECLARED_LOSS", "retorno UNKNOWN no Azure vira com estado no destino: declarado"
            out.append(translation(f"NETC-T-{tag}-P", S, d, "positive", src, tgt, losses, verdict, why=why))
            # ---- negativo
            if a in S2_SOURCE and b in ("aws", "oci"):
                out.append(translation(f"NETC-T-{tag}-N", S, d, "negative", S2_SOURCE[a], _deny_dropped(b),
                                       [{"loss_id": "LOSS-NET-EFFECT-DENY", "flows": ["f1"]}], "REJECT",
                                       why="a negação de 22 sumiu e a permissão da /24 passou: deny virou allow (CMT-FW-N01)",
                                       counts={"negatives_carried": ["f1"]}))
            else:
                out.append(translation(f"NETC-T-{tag}-N", S, d, "negative", S1_SOURCE[a], s1(b, wide=True), [],
                                       "REJECT", why="443 aberto para qualquer origem: f3 era negado",
                                       counts={"negatives_carried": ["f3"]}))
            # ---- desconhecido
            if b == "azurerm":
                ls = [{"loss_id": "LOSS-NET-DEFAULT", "flows": ["f2", "f3", "f4"]}]
                if a in STATEFUL:
                    ls.append({"loss_id": "LOSS-NET-STATE", "flows": ["f1r"]})
                out.append(translation(f"NETC-T-{tag}-U", S, d, "unknown", S1_SOURCE[a], s1(b, catch=False), ls,
                                       "ACCEPT_WITH_DECLARED_LOSS",
                                       why="sem negação explícita o NSG fica UNKNOWN em f2, f3 e f4; a perda está declarada",
                                       counts={"covered": ["f2", "f3", "f4"] + (["f1r"] if a in STATEFUL else [])}))
            else:
                silent = ["f1", "f3"] + (["f1r"] if a in STATEFUL else [])
                out.append(translation(f"NETC-T-{tag}-U", S, d, "unknown", S1_SOURCE[a], s1(b, sym_cidr=True), [],
                                       "REJECT", why="CIDR simbólico inventado no destino: decisões definidas viram UNKNOWN sem perda declarável",
                                       counts={"silent_losses": silent}))
    return out
