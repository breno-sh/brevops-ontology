"""Regras do juiz que o E4 exige: perda declarada nunca cobre negado->permitido; alvo inválido reprova."""
import copy

import net_oracle as no
from conftest import NETDIR, load

SRC = load(NETDIR / "fixtures_calib/NETC-C04-GCP-DENY-WINS.json")


def _aws(rules):
    return {"provider": "aws", "targets": {"vm1": {"ref": "aws_instance.vm1", "ip": "10.0.1.10"}}, "flows": SRC["flows"],
            "read": {"completeness": "complete", "not_read": [], "withheld": []},
            "config": {"resources": [{"type": "aws_security_group", "name": "web", "values": {"ingress": rules}},
                                     {"type": "aws_instance", "name": "vm1", "values": {"vpc_security_group_ids": ["ref:aws_security_group.web"]}}]}}


def test_deny_virou_allow_reprova_mesmo_com_todas_as_perdas():
    tgt = _aws([{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["203.0.113.0/24"]},
                {"from_port": 443, "to_port": 443, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}])
    all_losses = [{"loss_id": k, "flows": ["f1", "f2", "f3", "f4", "f2r"]} for k in no.judging.catalog()["loss_catalog"]]
    j = no.judge(SRC, tgt, all_losses, "google->aws")
    assert j["verdict"] == "REJECT" and j["negatives_carried"] == ["f1"]


def test_bloqueio_conservador_coberto_so_por_perda_declarada():
    tgt = _aws([])
    j = no.judge(SRC, tgt, [], "google->aws")
    # f2 (443 permitido) vira negado; f2r (retorno permitido: firewall com estado) vira negado por não haver conexão
    assert j["verdict"] == "REJECT" and j["silent_losses"] == ["f2", "f2r"]
    j = no.judge(SRC, tgt, [{"loss_id": "LOSS-NET-EFFECT-DENY", "flows": ["f2", "f2r"]}], "google->aws")
    assert j["verdict"] == "ACCEPT_WITH_DECLARED_LOSS" and j["covered"] == ["f2", "f2r"]


def test_perda_fora_do_catalogo_da_direcao_nao_cobre():
    tgt = _aws([])
    j = no.judge(SRC, tgt, [{"loss_id": "LOSS-NET-DEFAULT", "flows": ["f2"]}], "google->aws")
    assert j["verdict"] == "REJECT" and j["undeclarable_losses"] == ["LOSS-NET-DEFAULT"]


def test_alvo_invalido_reprova():
    src = load(NETDIR / "fixtures_calib/NETC-C01-AZ-INLINE.json")
    tgt = copy.deepcopy(src)
    for r in tgt["config"]["resources"]:
        if r["type"] == "azurerm_network_security_group":
            r["values"]["security_rule"][1]["priority"] = 100
    assert no.evaluate_fixture(tgt)["validity"]["value"] == "INVALID"
    j = no.judge(src, tgt, [], "azurerm->azurerm")  # mesma origem: nenhuma perda declarável
    assert j["target_validity"] == "INVALID" and j["verdict"] == "REJECT"


def test_porta_simbolica_em_gcp_e_azure_vira_unknown():
    for p in ("google", "azurerm"):
        f = load(NETDIR / ("fixtures_calib/NETC-C09-GCP-NOMATCH.json" if p == "google" else "fixtures_calib/NETC-C01-AZ-INLINE.json"))
        f = copy.deepcopy(f)
        for r in f["config"]["resources"]:
            if r["type"] == "google_compute_firewall" and "allow" in r["values"]:
                r["values"]["allow"][0]["ports"] = ["sym:var.port"]
            if r["type"] == "azurerm_network_security_group":
                r["values"]["security_rule"][0]["destination_port_range"] = "sym:var.port"
        flows = [x for x in f["flows"] if x.get("port") == 443 and x.get("direction") == "ingress"] or f["flows"][:1]
        f["flows"] = flows
        d = no.evaluate_fixture(f)["decisions"]
        assert any(v["value"] == "UNKNOWN" and v["code"] == "UNKNOWN_SYMBOLIC_INPUT" for v in d.values()), p
