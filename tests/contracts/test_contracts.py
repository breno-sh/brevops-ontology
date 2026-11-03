"""Testes do CONTRACTS: schemas bem formados, referências que resolvem, regeneração idêntica, stubs, os gates de união
de desfechos e de ids pegando defeitos plantados, compatibilidade do I/O do C09 com o SEMANTICS e os arquivos já
publicados pelos produtores (REQUIREMENTS, ONTPAT, SEMANTICS, REPO, LIT) passando no validador único."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from bo.contracts import _base, build, catalog, claim_ids, enum_union, sssom, validate
from bo.semantics import sssom_io

ROOT = _base.repo()


def _walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)


@pytest.fixture(scope="module")
def sch():
    return catalog.schemas()


def test_trinta_contratos_publicados(sch):
    assert sorted(sch) == [f"C{i:02d}" for i in range(30)]
    for cid, s in sch.items():
        x = s["x-bo-contract"]
        assert x["id"] == cid and x["files"] and x["semantic_rules"], cid
        assert s["$id"] == _base.schema_uri(cid, catalog.NAMES[cid])


def test_versoes_do_plano(sch):
    cat = json.loads(Path(__import__("os").environ.get("BO_MODULES") or
                          "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json").read_text())
    for cid, c in cat["contracts"].items():
        assert sch[cid]["x-bo-contract"]["version"] == c["version"], cid
        assert sch[cid]["x-bo-contract"]["name"] == c["name"], cid


def test_metaschema(sch):
    for cid, s in sch.items():
        jsonschema.Draft202012Validator.check_schema(s)


def test_toda_referencia_resolve(sch):
    reg = catalog.registry(sch)
    for cid, s in sch.items():
        res = reg.resolver(base_uri=s["$id"])
        for node in _walk(s):
            if "$ref" in node:
                res.lookup(node["$ref"])          # levanta se não resolve


def test_regeneracao_identica():
    assert build.main(["--check"]) == 0


def test_todos_os_stubs():
    res, problems = validate.all_stubs()
    assert not problems
    assert all(r.ok for r in res), [(r.path, r.errors[:2]) for r in res if not r.ok]
    kinds = {r.kind for r in res}
    assert len(kinds) == len(catalog.file_kinds())


@pytest.mark.parametrize("alias,path,kind", [
    ("commitments", "requirements/commitments.jsonl", "C24:commitments"),
    ("requirements", "requirements/requirements.jsonl", "C24:requirements"),
    ("cq_spec", "requirements/cq_spec.jsonl", "C24:cq_spec"),
    ("manifest_receipt", "results/LIT/summary.json", "C17:summary"),
    ("manifest_receipt", "results/REPO/summary.json", "C17:summary"),
    ("realizations", "results/ONTPAT/C14_proposta/realizations.example.jsonl", "C14:realizations"),
    ("C10_composition_table", "semantics/composition_table.json", "C10:composition_table"),
    ("correspondences", "results/SEMANTICS/C09_proposta/examples.sssom.tsv", "C09:correspondences"),
    ("correspondences", "contracts/stubs/complex.sssom.tsv", "C09:correspondences"),
])
def test_arquivos_dos_produtores_e_aliases(alias, path, kind):
    p = ROOT / path
    r = validate.validate(alias, p)
    assert r.kind == kind
    assert r.ok, r.errors[:5]


def test_alias_desconhecido():
    with pytest.raises(KeyError):
        catalog.resolve("nao_existe", None)
    with pytest.raises(KeyError):
        catalog.resolve("C12", None)        # vários arquivos sem caminho


# --------------------------------------------------------------------------------- união de desfechos (G4)
def test_enum_union_limpo(sch):
    assert enum_union.check_schemas(sch)[0] == []
    assert enum_union.selftest(sch) == []


def test_enum_union_pega_enum_plano_no_c12(sch):
    s = copy.deepcopy(sch)
    s["C12"]["$defs"]["outcome_record"]["properties"]["outcome"] = {"enum": ["PERSISTED", "ALTERED"]}
    errs = enum_union.check_schemas(s)[0]
    assert any(e.startswith("U2 C12") for e in errs) and any(e.startswith("U3 C12") for e in errs)


def test_enum_union_pega_valor_solto_em_outro_contrato(sch):
    s = copy.deepcopy(sch)
    s["C23"]["$defs"]["trace"]["properties"]["result"]["enum"].append("PERSISTED")
    assert any(e.startswith("U3 C23") for e in enum_union.check_schemas(s)[0])


def test_enum_union_pega_valor_fora_do_plano(sch):
    s = copy.deepcopy(sch)
    s["C00"]["$defs"]["outcome_behavior"]["properties"]["value"]["enum"].append("SAME")
    assert any(e.startswith("U1") for e in enum_union.check_schemas(s)[0])


# ------------------------------------------------------------------------------------------- claim ids (G5)
def test_claim_ids_limpo(sch):
    assert claim_ids.check_schemas(sch)[0] == []
    assert claim_ids.check_patterns() == []
    assert claim_ids.selftest(sch) == []


def test_claim_ids_pega_padrao_proprio_e_id_mutavel(sch):
    s = copy.deepcopy(sch)
    s["C21"]["$defs"]["verdict"]["properties"]["claim_id"] = {"type": "string"}
    s["C11"]["$defs"]["case"]["properties"]["bo_row_id"] = {"type": "string"}
    s["C20"]["$defs"]["anchor_claim"]["required"].remove("event_id")
    errs = claim_ids.check_schemas(s)[0]
    assert any(e.startswith("I1 C21") for e in errs)
    assert any(e.startswith("I3 C11") for e in errs)
    assert any(e.startswith("I2 C20") for e in errs)


# --------------------------------------------------------------------------------------------- I/O do C09
def test_sssom_bytes_iguais_ao_semantics():
    text = (ROOT / "results/SEMANTICS/C09_proposta/examples.sssom.tsv").read_text(encoding="utf-8")
    meta, recs = sssom_io.read_tsv(text)
    ours = sssom.write_tsv(recs, meta["mapping_set_id"], meta["curie_map"])
    theirs = sssom_io.write_tsv(recs, meta["mapping_set_id"], meta["curie_map"])
    assert ours == theirs


def test_sssom_preserva_colunas_novas_que_o_semantics_descarta():
    text = (ROOT / "contracts/stubs/complex.sssom.tsv").read_text(encoding="utf-8")
    meta, recs, cols = sssom.read_tsv(text)
    assert "alternative_to" in cols and "exclusivity" in cols
    back = sssom.read_tsv(sssom.write_tsv(recs, meta["mapping_set_id"], meta["curie_map"]))[1]
    assert back == recs
    dropped = sssom_io.write_tsv(recs, meta["mapping_set_id"], meta["curie_map"])
    assert "alternative_to" not in dropped.splitlines()[-len(recs) - 1]   # achado: o writer do SEMANTICS descarta


def test_complexo_tem_os_tres_casos():
    recs = sssom.read_tsv((ROOT / "contracts/stubs/complex.sssom.tsv").read_text(encoding="utf-8"))[1]
    groups = [r["group"] for r in recs if "group" in r]
    assert groups and all(len(g["variables"]) >= 3 and g["steps"] for g in groups)
    assert any(g["joins"] for g in groups)                                   # ocorrências ligadas por junção
    projs = [p for r in recs for p in r.get("projection") or []]
    assert any(p["occurrence"]["scope"] == "block" and p["occurrence"]["key_fields"] for p in projs)
    alts = [r for r in recs if r.get("alternative_to")]
    assert len(alts) == 2 and {r["exclusivity"] for r in alts} == {"ProvenExclusive"}


def test_withheld_nunca_tem_valor(sch):
    reg = catalog.registry(sch)
    v = jsonschema.Draft202012Validator({"$ref": f"{_base.BASE_URI}C12/readback_outcomes.schema.json#/$defs/readback"},
                                        registry=reg)
    rb = json.loads((ROOT / "contracts/stubs/C12/readback.jsonl").read_text().splitlines()[0])
    assert v.is_valid(rb)
    rb["fields"][1]["value"] = "qualquer"
    assert not v.is_valid(rb)


def test_not_applicable_nao_e_unknown(sch):
    reg = catalog.registry(sch)
    v = jsonschema.Draft202012Validator({"$ref": f"{_base.BASE_URI}C05/value_space.schema.json#/$defs/value_space"},
                                        registry=reg)
    rec = json.loads((ROOT / "contracts/stubs/C05/value_space.jsonl").read_text().splitlines()[1])
    assert rec["quantity_kind"] == "NOT_APPLICABLE" and v.is_valid(rec)
    rec["unit_qudt"] = "UNKNOWN"
    assert not v.is_valid(rec)
