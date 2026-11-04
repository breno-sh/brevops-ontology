"""Testes do CONTRACTS: schemas bem formados, referências que resolvem, regeneração idêntica, stubs, os gates de união
de desfechos e de ids pegando defeitos plantados, compatibilidade do I/O do C09 com o SEMANTICS e os arquivos já
publicados pelos produtores (REQUIREMENTS, ONTPAT, SEMANTICS, REPO, LIT) passando no validador único."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from bo.contracts import _base, amendments, build, catalog, claim_ids, enum_union, sssom, sweep, validate
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
    from bo.contracts.amendments import accepted
    for cid, c in cat["contracts"].items():
        assert c["version"] in accepted(cid, sch[cid]["x-bo-contract"]["version"]), cid
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


# ------------------------------------------------------------------------------- emenda 2026-11-03 (PINS, DRIFT…)
@pytest.mark.parametrize("name,kind", [("pins.json", "C13:pins"), ("versions.json", "C13:versions"),
                                       ("events.jsonl", "C13:events")])
def test_alias_nome_do_contrato_escolhe_pelo_arquivo(name, kind):
    """'versions' é o nome do C13 E um tipo dele: escolhe pelo nome do arquivo (mudança A do PINS)."""
    fk = catalog.resolve("versions", ROOT / "contracts/stubs/C13" / name)
    assert f"{fk.cid}:{fk.kind}" == kind
    assert validate.validate("versions", ROOT / "contracts/stubs/C13" / name).ok


@pytest.mark.parametrize("alias,path,kind", [
    ("versions", "$BO_REPO/universe/history_versions.json", "C13:history_versions"),
    ("versions", "$BO_DATA/DRIFT/atom_history.jsonl", "C13:atom_history"),
    ("versions", "$BO_DATA/HIST-AWS/versions.json", "C13:versions"),
    ("glossary", "$BO_DATA/GLOSSARY-AUDIT/glossary_audit.jsonl", "C20:glossary_audit"),
    ("correspondences", "$BO_DATA/NONEHUNT-AWS/disputes.jsonl", "C09:correspondences_jsonl"),
    ("correspondences", "$BO_DATA/MAP-AWSGCP-NET/mappings.sssom.tsv", "C09:correspondences"),
    ("cases", "$BO_DATA/DEPSAMPLE/cases_aws.jsonl", "C11:cases"),
    ("numbers", "$BO_REPO/paper/numbers_supp.json", "C18:numbers"),
])
def test_resolucao_dos_gates_do_catalogo(alias, path, kind):
    fk = catalog.resolve(alias, Path(path))
    assert f"{fk.cid}:{fk.kind}" == kind


def test_varredura_de_todos_os_gates():
    rep = sweep.sweep()
    assert rep["gates"] >= 100
    assert rep["ok"] == rep["gates"], rep["failed"][:3]


def test_emendas_aditivas_aceitam_documento_antigo(sch):
    """Cabeçalho 3.0.0 continua válido no C13 3.1.0 (o PINS gravou 3.0.0); átomo sem write_only continua válido."""
    for a in amendments.AMENDMENTS:
        assert sch[a["contract"]]["x-bo-contract"]["version"] == amendments.chain(a["contract"])[-1]
    reg = catalog.registry(sch)
    v = jsonschema.Draft202012Validator({"$ref": f"{_base.BASE_URI}C13/versions.schema.json#/$defs/pins"}, registry=reg)
    doc = json.loads((ROOT / "contracts/stubs/C13/pins.json").read_text())
    assert doc["contract_version"] == "3.0.0" and v.is_valid(doc)
    doc["contract_version"] = "3.1.0"
    assert v.is_valid(doc)
    doc["contract_version"] = "9.9.9"
    assert not v.is_valid(doc)
    atoms = [json.loads(l) for l in (ROOT / "contracts/stubs/C01/atoms.jsonl").read_text().splitlines()]
    assert "write_only" not in atoms[0] and atoms[2]["write_only"] is True
    assert validate.validate("atoms", ROOT / "contracts/stubs/C01/atoms.jsonl").ok


def test_history_versions_do_pins_se_presente():
    lane = Path("/Users/breno/doutorado/pesquisa-lanes/bo-pins/universe")
    for base in (ROOT / "universe", lane):
        if (base / "history_versions.json").is_file():
            r = validate.validate("versions", base / "history_versions.json")
            assert r.kind == "C13:history_versions" and r.ok, r.errors[:5]
            assert validate.validate("versions", base / "pins.json").ok
            return
    pytest.skip("history_versions.json do PINS ainda não publicado")


# ----------------------------------------------------------------------------------- emenda 2 (2026-11-03)
def test_stub_c26_um_plano_por_provedor():
    """Gate de render dos HARNESS-*: exatamente UM plano por target_provider, cada um com o graph_ir irmão."""
    lp = [json.loads(l) for l in (ROOT / "contracts/stubs/C26/lowering_plan.jsonl").read_text().splitlines()]
    gi = {json.loads(l)["graph_id"] for l in (ROOT / "contracts/stubs/C26/graph_ir.jsonl").read_text().splitlines()}
    provs = sorted(p["target_provider"] for p in lp)
    assert provs == sorted(["aws", "google", "azurerm", "oci"])
    assert all(p["graph_id"] in gi for p in lp)
    assert validate.validate("lowering_plan", ROOT / "contracts/stubs/C26/lowering_plan.jsonl").ok


@pytest.mark.parametrize("alias,path,kind", [
    ("C03", "$BO_DATA/DOCS-OCI/type_subcategory.jsonl", "C03:type_subcategory"),
    ("docs_facts", "$BO_DATA/DOCS-OCI/type_subcategory.jsonl", "C03:type_subcategory"),
    ("docs_facts", "$BO_DATA/DOCS-OCI/docs_facts.jsonl", "C03:docs_facts"),
])
def test_c03_tipo_por_arquivo(alias, path, kind):
    fk = catalog.resolve(alias, Path(path))
    assert f"{fk.cid}:{fk.kind}" == kind


def test_emenda2_versoes():
    pub = catalog.schemas()
    for cid, v in {"C03": "3.1.0", "C19": "3.1.0"}.items():
        assert pub[cid]["x-bo-contract"]["version"] == v
        assert "3.0.0" in amendments.chain(cid) or "1.0.0" in amendments.chain(cid)


# ----------------------------------------------------------------------------------- emenda 3 (BRIEFS)
def test_ausencia_tipada_e_forma_provisoria():
    recs = sssom.read_tsv((ROOT / "contracts/stubs/C09/correspondences.sssom.tsv").read_text(encoding="utf-8"))[1]
    nones = [r for r in recs if r["object_id"] == "sssom:NoTermFound"]
    assert {bool(r.get("absence")) for r in nones} == {True, False}          # nova e provisória (curation_rule)
    assert validate.validate("correspondences", ROOT / "contracts/stubs/C09/correspondences.sssom.tsv").ok


def test_decisoes_do_glossario_formato_do_brief():
    r = validate.validate("decisions", ROOT / "contracts/stubs/C20/decisions.jsonl")
    assert r.kind == "C20:decisions" and r.ok, r.errors[:3]
    ex = ROOT / "results/BRIEFS/examples/decisions.jsonl"
    if ex.is_file():   # formato do GLOSSARY_BRIEF adotado: o schema aceita os exemplos (só a regra de referência
        reg = catalog.registry(catalog.schemas())   # ao glossary.jsonl irmão pode reprovar)
        v = jsonschema.Draft202012Validator({"$ref": f"{_base.BASE_URI}C20/glossary.schema.json#/$defs/decision"},
                                            registry=reg)
        for line in ex.read_text(encoding="utf-8").splitlines():
            assert v.is_valid(json.loads(line))


# ----------------------------------------------------------------------------------- emenda 4
def test_ancora_em_bloco_e_tipo():
    recs = [json.loads(l) for l in (ROOT / "contracts/stubs/C20/claims.jsonl").read_text().splitlines()]
    kinds = {r.get("anchor_kind", "atom") for r in recs}
    assert kinds == {"atom", "block", "type"}
    assert all("implication" in r for r in recs if r.get("anchor_kind") in ("block", "type"))
    assert validate.validate("claims", ROOT / "contracts/stubs/C20/claims.jsonl").ok


def test_c25_emenda_aceita_fatos_novos_e_antigos():
    r = validate.validate("service_evidence", ROOT / "contracts/stubs/C25/service_evidence.jsonl")
    assert r.ok, r.errors[:3]
    recs = [json.loads(l) for l in (ROOT / "contracts/stubs/C25/service_evidence.jsonl").read_text().splitlines()]
    assert {"api_bridge", "default"} <= {x["fact_kind"] for x in recs}
    assert any("schema" in x for x in recs) and any("block_path" in x for x in recs)
    assert any(x["status"] == "unknown" and "level" not in x for x in recs)


# ----------------------------------------------------------------------------------- emenda 5
@pytest.mark.parametrize("fatia", ["net", "sto"])
def test_gabaritos_dos_oraculos(fatia):
    p = ROOT / "pilot" / fatia / "expected_answers.json"
    if not p.is_file():
        pytest.skip("oráculo ainda não publicado")
    for alias in ("C24", "requirements", "pilot_expected_answers"):
        r = validate.validate(alias, p)
        assert r.kind == "C24:pilot_expected_answers" and r.ok, r.errors[:3]


def test_protocol_support_e_origem_pilot(sch):
    assert validate.validate("C25", ROOT / "contracts/stubs/C25/protocol_support.jsonl").ok
    assert "pilot" in sch["C11"]["$defs"]["case"]["properties"]["origin"]["enum"]
    assert sch["C24"]["x-bo-contract"]["version"] == "1.1.0"


def test_plano_sem_tag_de_execucao():
    lp = [json.loads(l) for l in (ROOT / "contracts/stubs/C26/lowering_plan.jsonl").read_text().splitlines()]
    fields = [v["field"] for p in lp for st in p["steps"] for v in st["values"]]
    assert not [f for f in fields if ".bo_" in f]


# ----------------------------------------------------------------------------------- emenda 7 (E6 do PILOT-EXIT)
def test_emenda7_tabela_cobre_os_27():
    from bo.contracts import report
    rep = report.emenda7()
    assert rep["n"] == 27 and len({(r["module"], r["item"]) for r in rep["items"]}) == 27
    lst = (ROOT / "results/PILOT-EXIT/CONTRACT_CHANGE.txt")
    if lst.is_file():
        import re as _re
        pedidos = set(_re.findall(r"- (PILOT-[A-Z0-9-]+) item ([A-Za-z0-9-]+):", lst.read_text(encoding="utf-8")))
        assert pedidos == {(r["module"], r["item"]) for r in rep["items"]}


def test_termo_lista_e_ausencia_do_lado_objeto(sch):
    reg = catalog.registry(sch)
    v = jsonschema.Draft202012Validator({"$ref": f"{_base.BASE_URI}C00/conventions.schema.json#/$defs/term"}, registry=reg)
    assert v.is_valid({"kind": "list", "items": [{"kind": "reference", "target_type": "oci_core_security_list",
                                                  "target_address": "oci_core_security_list.SYM-0a1b2c3d4e5f",
                                                  "target_node": "r2"}]})
    recs = sssom.read_tsv((ROOT / "contracts/stubs/C09/correspondences.sssom.tsv").read_text(encoding="utf-8"))[1]
    assert any(r["subject_id"] == "sssom:NoTermFound" and r["absence"]["side"] == "object" for r in recs)


# ----------------------------------------------------------------------------------- emenda 9 e livro de pedidos
def test_livro_de_pedidos():
    from bo.contracts import ledger
    rep = ledger.ledger("2026-11-04T14:00:00-03:00")
    keys = [(r["module"], r["item"]) for r in rep["items"]]
    assert len(keys) == len(set(keys))
    assert {"ACEITO", "RECUSADO", "ADIADO_FASE_2", "DE_OUTRO_DONO"} >= set(rep["by_decision"])
    e7 = {(r["module"], r["item"]) for r in __import__("bo.contracts.report", fromlist=["x"]).emenda7()["items"]}
    assert e7 <= set(keys)
    for k in [("PILOT-STO-MAP", "CC-13"), ("PILOT-STO-MAP", "CC-8"), ("PILOT-NET-E2E", "CC-NET-E2E-2"),
              ("PILOT-NET-E2E", "CC-NET-E2E-3"), ("TRANSFORMS", "2"), ("BRIEFS", "5")]:
        assert k in keys
    for r in rep["items"]:
        assert r["decision"] != "ACEITO" or r["closes"] not in ("-", "")


def test_emenda9_c05_unidades(sch):
    r = validate.validate("value_space", ROOT / "contracts/stubs/C05/value_space.jsonl")
    assert r.ok, r.errors[:3]
    recs = [json.loads(l) for l in (ROOT / "contracts/stubs/C05/value_space.jsonl").read_text().splitlines()]
    assert not [x for x in recs if x["quantity_kind"] == "quantitykind:InformationEntropy"]


# ----------------------------------------------------------------------------------- emenda 10 (nível observed)
def test_c25_observado_e_disputa(sch):
    assert sch["C25"]["x-bo-contract"]["version"] == "1.4.0"
    recs = [json.loads(l) for l in (ROOT / "contracts/stubs/C25/service_evidence.jsonl").read_text().splitlines()]
    obs = [r for r in recs if r.get("level") == "observed"]
    assert obs and all(r["repetitions"] >= 2 and r["observation_ref"]["path"].startswith("$BO_DATA/OBS-GAPS/")
                       for r in obs)
    assert all(r.get("disputes") for r in obs)          # diverge do publicado: disputa, os dois ficam
    assert validate.validate("service_evidence", ROOT / "contracts/stubs/C25/service_evidence.jsonl").ok
