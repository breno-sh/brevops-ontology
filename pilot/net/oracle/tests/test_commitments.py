"""O avaliador reproduz as respostas congeladas dos compromissos FIREWALL do REQUIREMENTS (vocabulário independente)."""
import json

import pytest

import net_oracle as no
from conftest import REPO
from net_oracle import adapters, evaluate as ev
from net_oracle.model import Flow

CMT = {}
for line in (REPO / "requirements/commitments.jsonl").read_text(encoding="utf-8").splitlines():
    d = json.loads(line)
    if d["case"] == "FIREWALL" or d["commitment_id"] == "CMT-TAX-N03":
        CMT[d["commitment_id"]] = d


def run(fx):
    fx = dict(fx, provider="neutral")
    net, flows = adapters.build(fx)
    flows += [Flow(f.flow_id + "_ret", "t", "", "", "", state="return", of=f.flow_id) for f in list(flows)]
    adapters.resolve_return_direction(flows)
    return ev.evaluate(net, flows), no.validity_of(net)


def test_todos_os_compromissos_firewall_lidos():
    assert {"CMT-FW-P02", "CMT-FW-P03", "CMT-FW-P04", "CMT-FW-P06", "CMT-FW-N02", "CMT-FW-N03",
            "CMT-FW-U01", "CMT-FW-U02", "CMT-FW-U03"} <= set(CMT)


def test_p02_retorno_com_estado():
    r, _ = run(CMT["CMT-FW-P02"]["fixtures"][0])
    assert r["f1_ret"]["value"] == "ALLOW"


def test_p03_estado_por_regra():
    r, _ = run(CMT["CMT-FW-P03"]["fixtures"][0])
    assert (r["f1_ret"]["value"], r["f2_ret"]["value"]) == ("ALLOW", "DENY")


def test_p04_deny_de_precedencia_maior():
    r, _ = run(CMT["CMT-FW-P04"]["fixtures"][0])
    assert r["f1"]["value"] == "DENY"


def test_p06_ordem_textual_invariante():
    a, b = (run(fx)[0]["f1"]["value"] for fx in CMT["CMT-FW-P06"]["fixtures"])
    assert a == b == "DENY"


def test_p01_embalagem_mesma_decisao():
    fa, fb = CMT["CMT-FW-P01"]["fixtures"]
    flow = {"of": "f1", "attr": "direction", "value": "ingress"}
    extra = [{"id": "f1", "kind": "flow"}]
    attrs = [flow, {"of": "f1", "attr": "protocol", "value": "tcp"}, {"of": "f1", "attr": "port", "value": 443},
             {"of": "f1", "attr": "source_cidr", "value": "203.0.113.10/32"}]
    ra = run(dict(fa, entities=fa["entities"] + extra, attributes=fa["attributes"] + attrs))[0]
    rb = run(dict(fb, entities=fb["entities"] + extra, attributes=fb["attributes"] + attrs))[0]
    assert ra["f1"]["value"] == rb["f1"]["value"] == "ALLOW"


def test_p05_alvo_por_rotulo():
    assert adapters.applies_neutral(CMT["CMT-FW-P05"]["fixtures"][0])["rs1"] == {"vm1"}


@pytest.mark.parametrize("cid", ["CMT-FW-N02", "CMT-TAX-N03"])
def test_negativos_de_estado(cid):
    _, v = run(CMT[cid]["fixtures"][0])
    assert v["value"] == ("INVALID" if cid == "CMT-FW-N02" else "VALID")


def test_n03_saida_nao_autoriza_entrada():
    r, _ = run(CMT["CMT-FW-N03"]["fixtures"][0])
    assert r["f1"]["value"] != "ALLOW"


@pytest.mark.parametrize("cid", ["CMT-FW-U01", "CMT-FW-U02", "CMT-FW-U03"])
def test_desconhecidos(cid):
    d = CMT[cid]
    r, _ = run(d["fixtures"][0])
    key = "f1_ret" if "retorno" in d["check"]["assertion"] else "f1"
    assert r[key]["value"] == "UNKNOWN"
    assert r[key]["code"] == d["expected_answer"]["code"]
