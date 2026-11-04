"""CQs da família cis (C24): uma por conceito CIS presente nos 4 benchmarks do CQSRC.

O CQSRC achou 8 conceitos com controle CIS nos 4 provedores (o plano estimava ~10); este módulo trabalha
com os 8 e registra a diferença. Cada conceito vira uma CQ em vocabulário independente
(bo.requirements.terms), com fixture conforme, não conforme e incompleta e a resposta esperada escrita a
partir do texto do controle CIS, não do mapeador. Os controles por provedor ficam em CIS_CONTROLS (lidos
do cis_cross_provider.csv no build e conferidos contra ele no fixture_check).
"""
from __future__ import annotations

import csv
from collections import OrderedDict

from bo.requirements.model import cq, fx

from . import repo_root

ANSWERS = ["S4", "R1-M8"]
OBS_AT = "2026-11-02T10:00:00-03:00"
DOC_SRC = "203.0.113.0/24"

# conceito CIS -> cq_id (ordem estável; os 8 com concept_in_all_four = true no CQSRC)
CONCEPT_CQ = OrderedDict([
    ("SEC-MFA-ALL-USERS", "CQ-CIS-01"),
    ("SEC-CREDENTIAL-ROTATION", "CQ-CIS-02"),
    ("SEC-KMS-KEY-ROTATION", "CQ-CIS-03"),
    ("NET-SSH-FROM-ANYWHERE", "CQ-CIS-04"),
    ("NET-RDP-FROM-ANYWHERE", "CQ-CIS-05"),
    ("NET-FLOW-LOGS", "CQ-CIS-06"),
    ("OPS-ALERT-NETFILTER-CHANGE", "CQ-CIS-07"),
    ("STO-BUCKET-NOT-PUBLIC", "CQ-CIS-08"),
])
PLAN_ESTIMATE = 10


def _f(qid, role, summary, ents, rels=(), attrs=(), **kw):
    return fx(f"FX-{qid[3:]}-{role}", summary, ents, rels, attrs, **kw)


def _ports(qid, port, label):
    return cq(
        qid, "cis",
        f"Nenhuma regra de entrada do conjunto C abre a porta {port} ({label}) para qualquer origem?",
        f"conforme = sob leitura completa, nenhuma regra de entrada que permite tcp/{port} tem origem 0.0.0.0/0",
        "boolean",
        (_f(qid, "C", f"regra de entrada {port} restrita a faixa de documentação", "rs1:rule_set r1:filter_rule",
            ["r1 rule_in rs1"],
            ["r1.direction=ingress", "r1.protocol=tcp", f"r1.port={port}", f"r1.source_cidr={DOC_SRC}",
             "r1.effect=allow"]),
         True, "a única regra que permite a porta tem origem restrita"),
        (_f(qid, "N", f"regra de entrada {port} aberta a qualquer origem", "rs1:rule_set r1:filter_rule",
            ["r1 rule_in rs1"],
            ["r1.direction=ingress", "r1.protocol=tcp", f"r1.port={port}", "r1.source_cidr=0.0.0.0/0",
             "r1.effect=allow"]),
         False, "regra permite a porta a partir de 0.0.0.0/0"),
        (_f(qid, "I", f"origem da regra {port} vem de entrada não resolvida", "rs1:rule_set r1:filter_rule",
            ["r1 rule_in rs1"],
            ["r1.direction=ingress", "r1.protocol=tcp", f"r1.port={port}", "r1.effect=allow",
             "r1.value_symbolic=true"], complete=False, not_read=["r1.value"]),
         "a origem simbólica pode ser 0.0.0.0/0", "UNKNOWN_SYMBOLIC_INPUT"),
        ["REQ-NET-01", "REQ-ABS-01"], ["CMT-FW-U01"], ["FIREWALL"], ANSWERS,
        "filtragem por direção, protocolo, porta e origem; negação sob leitura completa", negation=True)


def records() -> list[dict]:
    Q = []
    Q.append(cq(
        "CQ-CIS-01", "cis",
        "O principal humano com acesso de console tem segundo fator exigido pela configuração?",
        "conforme = a configuração lida exige segundo fator para o principal humano", "boolean",
        (_f("CQ-CIS-01", "C", "segundo fator exigido para o usuário", "u1:principal d1:config_description",
            ["d1 describes u1"], ["u1.principal_type=user", "d1.value=second_factor_required"]),
         True, "a configuração exige o segundo fator"),
        (_f("CQ-CIS-01", "N", "usuário de console sem exigência de segundo fator",
            "u1:principal d1:config_description", ["d1 describes u1"],
            ["u1.principal_type=user", "d1.value=second_factor_not_required"]),
         False, "nada na configuração lida exige o segundo fator"),
        (_f("CQ-CIS-01", "I", "exigência de segundo fator vem de entrada não resolvida",
            "u1:principal d1:config_description", ["d1 describes u1"],
            ["u1.principal_type=user", "d1.value_symbolic=true"], complete=False, not_read=["d1.value"]),
         "o valor simbólico decide a exigência", "UNKNOWN_SYMBOLIC_INPUT"),
        ["REQ-AUTH-01", "REQ-CFG-02"], [], ["IAM"], ANSWERS,
        "principal humano x identidade de serviço; configuração de autenticação ligada ao principal"))
    Q.append(cq(
        "CQ-CIS-02", "cis",
        "A credencial programática de longa duração K tem, na observação mais recente, idade de até 90 dias?",
        "conforme = a observação datada mostra a credencial criada ou rotacionada há no máximo 90 dias",
        "boolean",
        (_f("CQ-CIS-02", "C", "credencial observada com 10 dias",
            "p1:principal k1:secret_value_holder o1:observed_state ob1:observation",
            ["k1 secret_of p1", "o1 observed_state_of k1", "o1 produced_by ob1"],
            ["k1.secret_present=true", "o1.value=age_10_day", f"ob1.observed_at={OBS_AT}"],
            withheld=["k1.value"]),
         True, "idade observada dentro do prazo"),
        (_f("CQ-CIS-02", "N", "credencial observada com 120 dias",
            "p1:principal k1:secret_value_holder o1:observed_state ob1:observation",
            ["k1 secret_of p1", "o1 observed_state_of k1", "o1 produced_by ob1"],
            ["k1.secret_present=true", "o1.value=age_120_day", f"ob1.observed_at={OBS_AT}"],
            withheld=["k1.value"]),
         False, "idade observada acima de 90 dias"),
        (_f("CQ-CIS-02", "I", "credencial sem observação", "p1:principal k1:secret_value_holder",
            ["k1 secret_of p1"], ["k1.secret_present=true"], complete=False, not_read=["k1.observation"],
            withheld=["k1.value"]),
         "a idade só existe na observação", "INCOMPLETE_READ"),
        ["REQ-CFG-01", "REQ-ABS-01"], ["CMT-CFG-N01", "CMT-ABS-N01"], [], ANSWERS,
        "configuração x observação datada; segredo com valor retido"))
    Q.append(cq(
        "CQ-CIS-03", "cis",
        "A chave de cifra gerida pelo cliente tem rotação automática ligada na configuração?",
        "conforme = a configuração lida liga a rotação automática da chave", "boolean",
        (_f("CQ-CIS-03", "C", "chave com rotação automática", "k1:secret_value_holder d1:config_description",
            ["d1 describes k1"], ["d1.value=rotation_enabled", "d1.value_origin=configured"],
            withheld=["k1.value"]),
         True, "rotação ligada explicitamente"),
        (_f("CQ-CIS-03", "N", "chave sem rotação automática", "k1:secret_value_holder d1:config_description",
            ["d1 describes k1"], ["d1.value=rotation_disabled", "d1.value_origin=configured"],
            withheld=["k1.value"]),
         False, "rotação desligada"),
        (_f("CQ-CIS-03", "I", "rotação vem de entrada não resolvida", "k1:secret_value_holder d1:config_description",
            ["d1 describes k1"], ["d1.value_symbolic=true"], complete=False, not_read=["d1.value"],
            withheld=["k1.value"]),
         "o valor simbólico decide a rotação", "UNKNOWN_SYMBOLIC_INPUT"),
        ["REQ-CFG-02"], ["CMT-ABS-N01"], [], ANSWERS,
        "configuração de ciclo de vida de material secreto sem ler o material"))
    Q.append(_ports("CQ-CIS-04", 22, "SSH"))
    Q.append(_ports("CQ-CIS-05", 3389, "RDP"))
    Q.append(cq(
        "CQ-CIS-06", "cis",
        "A sub-rede S tem registro de fluxo de rede ligado (declarado nela ou na rede que a contém)?",
        "conforme = existe configuração lida que liga o registro de fluxo para S", "boolean",
        (_f("CQ-CIS-06", "C", "registro de fluxo ligado na sub-rede",
            "vn1:virtual_network sa:subnet d1:config_description", ["sa subnet_of vn1", "d1 describes sa"],
            ["d1.value=flow_log_enabled"]),
         True, "registro de fluxo configurado"),
        (_f("CQ-CIS-06", "N", "nenhum registro de fluxo sob leitura completa do escopo",
            "vn1:virtual_network sa:subnet s1:scope_node", ["sa subnet_of vn1", "vn1 in_scope s1"],
            ["s1.read_complete=true"]),
         False, "ausência sob leitura completa declarada"),
        (_f("CQ-CIS-06", "I", "registro de fluxo ligado por entrada não resolvida",
            "vn1:virtual_network sa:subnet d1:config_description", ["sa subnet_of vn1", "d1 describes sa"],
            ["d1.value_symbolic=true"], complete=False, not_read=["d1.value"]),
         "o valor simbólico decide se o registro existe", "UNKNOWN_SYMBOLIC_INPUT"),
        ["REQ-ABS-01", "REQ-NET-01"], ["CMT-ABS-P01"], [], ANSWERS,
        "configuração ligada à sub-rede ou à rede; ausência sob leitura completa", negation=False))
    Q.append(cq(
        "CQ-CIS-07", "cis",
        "Existe alarme no escopo S que notifica mudança em conjunto de regras de filtragem de tráfego?",
        "conforme = há alarme cujo evento é a mudança em conjunto de regras e que notifica um tópico",
        "boolean",
        (_f("CQ-CIS-07", "C", "alarme de mudança em conjunto de regras",
            "s1:scope_node al1:alarm t1:notification_topic", ["al1 alarm_on s1", "al1 notifies t1"],
            ["al1.value=event_rule_set_change"]),
         True, "alarme presente para o evento certo"),
        (_f("CQ-CIS-07", "N", "só há alarme de outro evento, leitura completa",
            "s1:scope_node al1:alarm t1:notification_topic", ["al1 alarm_on s1", "al1 notifies t1"],
            ["al1.value=event_route_change", "s1.read_complete=true"]),
         False, "o único alarme lido observa outro evento"),
        (_f("CQ-CIS-07", "I", "evento do alarme vem de entrada não resolvida",
            "s1:scope_node al1:alarm t1:notification_topic", ["al1 alarm_on s1", "al1 notifies t1"],
            ["al1.value_symbolic=true"], complete=False, not_read=["al1.value"]),
         "o filtro simbólico pode ou não casar o evento", "UNKNOWN_SYMBOLIC_INPUT"),
        ["REQ-ABS-01"], ["CMT-ABS-P01", "CMT-ABS-U01"], [], ANSWERS,
        "alarme sobre evento de controle; negação sob leitura completa", negation=True))
    Q.append(cq(
        "CQ-CIS-08", "cis",
        "O contêiner de objetos C não é acessível ao público?",
        "conforme = o alcance efetivo da configuração de acesso público de C é bloqueado", "boolean",
        (_f("CQ-CIS-08", "C", "acesso público bloqueado no contêiner",
            "c1:object_container k1:storage_setting",
            ["k1 setting_declared_on c1", "k1 setting_owned_by c1", "k1 setting_applies_to c1"],
            ["k1.setting_kind=public_access", "k1.public_access=blocked"]),
         True, "bloqueio vale para o contêiner"),
        (_f("CQ-CIS-08", "N", "leitura pública concedida ao contêiner",
            "c1:object_container k1:storage_setting",
            ["k1 setting_declared_on c1", "k1 setting_owned_by c1", "k1 setting_applies_to c1"],
            ["k1.setting_kind=public_access", "k1.public_access=allowed"]),
         False, "qualquer origem lê o contêiner"),
        (_f("CQ-CIS-08", "I", "acesso público vem de entrada não resolvida",
            "c1:object_container k1:storage_setting", ["k1 setting_declared_on c1", "k1 setting_applies_to c1"],
            ["k1.setting_kind=public_access", "k1.value_symbolic=true"], complete=False, not_read=["k1.value"]),
         "o valor simbólico decide o acesso", "UNKNOWN_SYMBOLIC_INPUT"),
        ["REQ-STO-01", "REQ-REL-01"], ["CMT-BKT-P01"], ["BUCKET"], ANSWERS,
        "dono x alcance efetivo da configuração de acesso público", negation=True))
    return Q


def cis_controls() -> dict:
    """{conceito: {provider: [(control_id, cis_item_id, título)]}} lido do cis_cross_provider.csv (CQSRC)."""
    out: dict = {}
    with open(repo_root() / "cq" / "cis_cross_provider.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["concept_in_all_four"] != "true":
                continue
            d = out.setdefault(r["concept_id"], {"label": r["concept_label"], "domain": r["domain"],
                                                  "providers": {}})
            for side in ("subject", "object"):
                p = r[f"{side}_provider"]
                item = (r[f"{side}_control_id"], r[f"{side}_cis_item_id"], r[f"{side}_title"],
                        r[f"{side}_cis_version"])
                lst = d["providers"].setdefault(p, [])
                if item not in lst:
                    lst.append(item)
    for d in out.values():
        for p in d["providers"]:
            d["providers"][p].sort()
    return out
