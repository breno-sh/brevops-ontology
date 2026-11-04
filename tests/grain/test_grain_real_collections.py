"""CC-NET-1 com DADO REAL: regra embutida como atributo lista/conjunto de objetos (aws_security_group.ingress,
azurerm_network_security_group.security_rule) vira bloco repetido (T2), com sub-átomos virtuais derivados do
tipo cty, e tem de dar a mesma decomposição e as mesmas relações que a regra separada
(aws_vpc_security_group_ingress_rule, azurerm_network_security_rule).

Dois níveis: (1) só o dado real: o elemento embutido existe como candidato, os sub-átomos saem do tipo cty, e
nenhum lado ganha um grão que o outro não tem; (2) controle: dando às duas embalagens a MESMA evidência da
camada de API (o que o SERVICE-EVIDENCE ainda não emite para elementos de coleção), a decomposição e as
relações saem iguais. Sem os arquivos reais, o teste reprova (não pula).
"""

import json

import pytest

from bo.grain import realdata as RD
from bo.grain import relations as REL
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.common import data_root
from bo.grain.evidence import C25Adapter

PAIRS = {
    "aws": ("aws_security_group", "aws_security_group.ingress", "aws_vpc_security_group_ingress_rule",
            "security_group_id", {"protocol": ("protocol", "ip_protocol"), "from_port": ("from_port", "from_port"),
                                  "to_port": ("to_port", "to_port"), "source": ("cidr_blocks", "cidr_ipv4")}),
    "azurerm": ("azurerm_network_security_group", "azurerm_network_security_group.security_rule",
                "azurerm_network_security_rule", "network_security_group_name",
                {"rule_name": ("name", "name")}),
}
RS = R.load()


@pytest.fixture(scope="module")
def records():
    p = data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    assert p.is_file(), f"dado real ausente: {p}"
    return RD.load_evidence(p)


def _decompose(prov, records, extra=(), drop=()):
    top, _, standalone, _, _ = PAIRS[prov]
    atoms = RD.load_atoms(prov, {top, standalone})
    assert atoms, f"átomos reais ausentes para {prov}"
    cands = S.candidates_from_atoms(atoms)
    recs = [r for r in records if r.get("provider") == prov and not (
        r.get("terraform_resource_type") in drop and r.get("fact_kind") in ("identity", "import_key", "api_bridge",
                                                                    "lifecycle_controller", "owner",
                                                                    "effective_scope"))]
    return atoms, S.decompose_schema(cands, C25Adapter(recs + list(extra), candidates={c.cid for c in cands}), RS)


@pytest.mark.parametrize("prov", sorted(PAIRS))
def test_collection_attribute_becomes_repeated_block_with_virtual_atoms(prov, records):
    top, inline, standalone, _, _ = PAIRS[prov]
    atoms, res = _decompose(prov, records)
    coll = next(a for a in atoms if a["atom_id"] == f"{prov}:{top}:{inline.split('.')[1]}")
    mode, fields = S.collection_fields(coll["tf_type"])
    c = res.candidates[inline]
    assert c.virtual and c.nesting == mode and c.parent == top and sorted(c.attrs) == sorted(fields)
    virt = {f"{prov}:{top}:{inline.split('.')[1]}.{f}" for f in fields}
    assert virt <= res.virtual_atoms
    assert all(res.atom_owner[v][0] == inline for v in virt)
    assert res.atom_owner[coll["atom_id"]][0] == top        # o átomo da coleção fica com o contêiner
    d_in, d_sep = res.decisions[inline], res.decisions[standalone]
    assert d_in.grain == d_sep.grain                          # nenhum lado ganha um grão que o outro não tem


def _ctl(prov):
    top, inline, standalone, ref, keys = PAIRS[prov]
    blk = inline.split(".")[1]

    def f(eid, rt, kind, value):
        return {"evidence_id": eid, "provider": prov, "pin": {"provider_version": "0.0.1"},
                "api_resource": {"service": "x", "resource": "x"}, "terraform_resource_type": rt, "fact_kind": kind,
                "status": "stated", "level": "derived", "derived_from": ["SE-controle"], "value": value}
    kf = sorted(keys)
    anon = prov == "aws"
    fm_in = {k: {"path": p, "norm": "str"} for k, (p, _) in keys.items()}
    fm_sep = {k: {"path": p, "norm": "str"} for k, (_, p) in keys.items()}
    fm_sep["container"] = {"path": ref, "ref": True}
    return [
        f("SE-c1", top, "identity", {"aspect": "api_resource_bridge", "resource": "RuleSet", "service": "net"}),
        f("SE-c2", top, "lifecycle_controller", "self"), f("SE-c3", top, "owner", "self"),
        f("SE-c4", top, "effective_scope", "self"),
        f("SE-c5", top, "identity", {"status": "present", "scope": "independent", "key_fields": ["id"]}),
        f("SE-c6", top, "identity", {"block_path": blk, "status": "present", "scope": "within_parent",
                                     "key_fields": kf, "anonymous": anon, "field_map": fm_in}),
        f("SE-c7", top, "lifecycle_controller", {"block_path": blk, "kind": "parent"}),
        f("SE-c8", top, "owner", {"block_path": blk, "kind": "parent"}),
        f("SE-c9", top, "effective_scope", {"block_path": blk, "kind": "parent"}),
        f("SE-c10", standalone, "identity", {"status": "present", "scope": "within_parent",
                                             "key_fields": kf + ["container"], "anonymous": anon,
                                             "field_map": fm_sep, "references": {"container": top}}),
        f("SE-c11", standalone, "import_key", {"status": "present", "fields": ["container"] + kf}),
        f("SE-c12", standalone, "lifecycle_controller", {"kind": "parent", "via": "container"}),
        f("SE-c13", standalone, "owner", {"kind": "parent", "via": "container"}),
        f("SE-c14", standalone, "effective_scope", {"kind": "parent", "via": "container"}),
        f("SE-c15", top, "identity", {"aspect": "api_resource_bridge", "block_path": blk, "resource": "SecurityRule",
                                      "service": "net"}),
        f("SE-c16", standalone, "identity", {"aspect": "api_resource_bridge", "resource": "SecurityRule",
                                             "service": "net"}),
    ]


@pytest.mark.parametrize("prov", sorted(PAIRS))
def test_inline_and_standalone_same_decomposition_and_relations_with_same_api_evidence(prov, records):
    top, inline, standalone, _, _ = PAIRS[prov]
    _, res = _decompose(prov, records, extra=_ctl(prov), drop=(top, standalone))
    d_in, d_sep = res.decisions[inline], res.decisions[standalone]
    assert d_in.grain == d_sep.grain == "COMPONENT", (d_in.grain, d_in.missing, d_sep.grain, d_sep.missing)
    assert d_in.parent == d_sep.parent == top
    assert S.signature(res, [top, inline]) == S.signature(res, [top, standalone])
    r_in = REL.relations(res, [top, inline])
    r_sep = REL.relations(res, [top, standalone])
    assert not r_in[1] and not r_sep[1]
    assert [(a, h) for a, h, b in r_in[0] if a[-1] == d_in.label] == \
        [(a, h) for a, h, b in r_sep[0] if a[-1] == d_sep.label] == [((res.decisions[top].label, d_in.label), "parent")]
    units, _ = S.to_c19(res)
    json.dumps(units)
