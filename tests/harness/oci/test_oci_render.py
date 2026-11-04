"""Renderizador: nada inserido, campo obrigatório ausente = UNKNOWN_INPUT, outro provedor = NOT_APPLICABLE."""
import json

import pytest
from conftest import EX, REPO, load_jsonl, mutate, write_plan

from bo.harness.oci import render as R
from bo.harness.oci import sandbox as SB

COMP = "SYM-c0a1000000000001"


def statuses(res):
    return {p.plan_id: p.status for p in res.renders}


def codes(res, plan_id):
    return sorted({i.code for p in res.renders if p.plan_id == plan_id for i in p.issues})


def test_examples_render_and_are_fmt_canonical_and_valid(tmp_out):
    res = R.render(EX / "lowering_plan.jsonl", tmp_out / "out", bindings_path=EX / "bindings.json")
    assert statuses(res) == {"LP-OCI-NET-0001": "RENDERED", "LP-OCI-STO-0001": "RENDERED"}
    f = SB.fmt_check(tmp_out / "out")
    assert f.rc == 0, f.out + f.err
    init, val = SB.init_validate(tmp_out / "out")
    assert init.rc == 0, init.err[-500:]
    v = json.loads(val.out)
    assert v["valid"] is True and v["error_count"] == 0


def test_every_written_attribute_traces_to_a_plan_value(tmp_out, example_plans):
    res = R.render(EX / "lowering_plan.jsonl", tmp_out / "out", bindings_path=EX / "bindings.json")
    for p in res.renders:
        plan = example_plans[p.plan_id]
        planned = {(s["order"], v["field"]) for s in plan["steps"] for v in s["values"]}
        order = {lab: o for o, lab in p.labels.items()}
        written = {(order[w.label], w.field) for w in p.written}
        assert written == planned


def test_missing_required_field_is_unknown_input_and_writes_no_hcl(tmp_out, example_plans):
    plan = mutate(example_plans["LP-OCI-STO-0001"], 1,
                  lambda s: s.__setitem__("values", [v for v in s["values"] if v["field"] != "namespace"]))
    pf, bf = write_plan(tmp_out / "in", [plan])
    res = R.render(pf, tmp_out / "out", bindings_path=bf)
    assert statuses(res) == {"LP-OCI-STO-0001": "UNKNOWN_INPUT"}
    assert codes(res, "LP-OCI-STO-0001") == ["MISSING_REQUIRED_FIELD"]
    assert not (tmp_out / "out" / "lp_oci_sto_0001").exists()
    root = (tmp_out / "out" / "main.tf").read_text()
    assert "module \"" not in root and "provider \"oci\"" not in root


def test_missing_required_nested_field(tmp_out, example_plans):
    plan = mutate(example_plans["LP-OCI-STO-0001"], 2,
                  lambda s: s.__setitem__("values", [v for v in s["values"] if v["field"] != "rules.0.time_unit"]))
    pf, bf = write_plan(tmp_out / "in", [plan])
    res = R.render(pf, tmp_out / "out", bindings_path=bf)
    issues = res.renders[0].issues
    assert res.renders[0].status == "UNKNOWN_INPUT"
    assert [(i.code, i.field) for i in issues] == [("MISSING_REQUIRED_FIELD", "rules.0.time_unit")]


def test_unbound_symbol_is_unknown_symbolic_input(tmp_out, example_plans):
    pf, bf = write_plan(tmp_out / "in", [example_plans["LP-OCI-NET-0001"]], bindings={})
    res = R.render(pf, tmp_out / "out", bindings_path=bf)
    assert res.renders[0].status == "UNKNOWN_INPUT"
    assert codes(res, "LP-OCI-NET-0001") == ["UNKNOWN_SYMBOLIC_INPUT"]


def test_c26_stub_other_providers_not_applicable_oci_needs_binding(tmp_out):
    stub = REPO / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"
    res = R.render(stub, tmp_out / "out")
    st = statuses(res)
    oci = [p for p, s in st.items() if res.renders[[x.plan_id for x in res.renders].index(p)].target_provider == "oci"]
    assert all(s == "NOT_APPLICABLE" for p, s in st.items() if p not in oci)
    assert len(oci) == 1
    # sem binding de contexto, o compartment do stub é símbolo: UNKNOWN_INPUT, nunca um default
    assert st[oci[0]] == "UNKNOWN_INPUT" and codes(res, oci[0]) == ["UNKNOWN_SYMBOLIC_INPUT"]
    assert R.main([str(stub), "--out", str(tmp_out / "cli")]) == 0
    assert sorted(p.name for p in (tmp_out / "cli").iterdir()) == ["main.tf", "render_report.json"]
    assert SB.fmt_check(tmp_out / "cli").rc == 0
    # o mesmo stub com um bindings.json irmão (entrada explícita) renderiza e passa no fmt e no validate
    d = tmp_out / "stub_with_bindings"
    d.mkdir()
    for n in ("lowering_plan.jsonl", "graph_ir.jsonl"):
        (d / n).write_text((stub.parent / n).read_text())
    (d / "bindings.json").write_text((EX / "bindings.json").read_text())
    res2 = R.render(d / "lowering_plan.jsonl", tmp_out / "out2")
    assert statuses(res2)[oci[0]] == "RENDERED"
    assert SB.fmt_check(tmp_out / "out2").rc == 0
    i, v = SB.init_validate(tmp_out / "out2")
    assert i.rc == 0 and json.loads(v.out)["valid"]


def test_reference_by_target_node_and_transitive_dependency(tmp_out, example_plans):
    def by_node(s):
        for v in s["values"]:
            if v["field"] == "network_security_group_id":
                v["term"]["target_node"] = "r3"
                v["term"]["target_address"] = "oci_core_network_security_group.SYM-00000000deadbeef"
    pf, bf = write_plan(tmp_out / "a", [mutate(example_plans["LP-OCI-NET-0001"], 4, by_node)], graph=False)
    res = R.render(pf, tmp_out / "oa", bindings_path=bf)
    assert res.renders[0].status == "UNKNOWN_INPUT"       # sem graph_ir as outras referências não resolvem
    assert ("REFERENCE_UNRESOLVED", "network_security_group_id") not in \
        {(i.code, i.field) for i in res.renders[0].issues}

    def via_vcn(s):                     # passo 4 referencia o VCN (passo 1) dependendo só do passo 3
        s["values"].append({"field": "description", "term": {"kind": "reference", "target_type": "oci_core_vcn",
                            "target_address": "oci_core_vcn.SYM-0a1b2c3d4e5f0001", "attribute": "display_name"},
                            "origin": "carried", "marked": False})
    pf, bf = write_plan(tmp_out / "b", [mutate(example_plans["LP-OCI-NET-0001"], 4, via_vcn)])
    res = R.render(pf, tmp_out / "ob", bindings_path=bf)
    assert res.renders[0].status == "RENDERED"


def test_derived_name_with_field(tmp_out, example_plans):
    def lit_name(s):
        s["derived_name"]["field"] = "display_name"
        s["values"] = [v for v in s["values"] if v["field"] != "display_name"]
    plan = mutate(example_plans["LP-OCI-NET-0001"], 1, lit_name)
    for st in plan["steps"]:            # referências ao VCN pelo nó (C00 3.0.1), não pelo símbolo do nome
        for v in st["values"]:
            if v["term"]["kind"] == "reference" and v["term"]["target_type"] == "oci_core_vcn":
                v["term"]["target_node"] = "r1"
    d = tmp_out / "a"
    pf, bf = write_plan(d, [plan])
    # termo t1 do exemplo é símbolo: o nome derivado não pode ser montado
    res = R.render(pf, tmp_out / "oa", bindings_path=bf)
    assert codes(res, "LP-OCI-NET-0001") == ["UNKNOWN_SYMBOLIC_INPUT"]
    g = [json.loads(x) for x in (d / "graph_ir.jsonl").read_text().splitlines()]
    g[0]["terms"][0]["term"] = {"kind": "literal", "datatype": "string", "value": "net0001"}
    (d / "graph_ir.jsonl").write_text("".join(json.dumps(x) + "\n" for x in g))
    res = R.render(pf, tmp_out / "ob", bindings_path=bf)
    assert res.renders[0].status == "RENDERED"
    assert 'display_name   = "bo-net0001-vcn"' in (tmp_out / "ob" / "lp_oci_net_0001" / "main.tf").read_text()
    from bo.harness.oci import no_silent_insert as NSI
    rep = NSI.run_corpus([(pf, bf)], tmp_out / "w")
    assert rep["violations"] == [] and rep["rendered_checked"] == 1


def test_unresolved_choice_and_open_closure(tmp_out, example_plans):
    p1 = mutate(example_plans["LP-OCI-NET-0001"], 4, lambda s: s["typed_choices"][0].__setitem__("selected", None))
    p2 = dict(example_plans["LP-OCI-STO-0001"], dependency_closure={"closed": False, "missing": ["r9"]})
    pf, bf = write_plan(tmp_out / "in", [p1, p2])
    res = R.render(pf, tmp_out / "out", bindings_path=bf)
    assert statuses(res) == {"LP-OCI-NET-0001": "UNKNOWN_INPUT", "LP-OCI-STO-0001": "UNKNOWN_INPUT"}
    assert codes(res, "LP-OCI-NET-0001") == ["UNRESOLVED_CHOICE"]
    assert codes(res, "LP-OCI-STO-0001") == ["OPEN_DEPENDENCY_CLOSURE"]


def test_type_mismatch_is_invalid_not_coerced(tmp_out, example_plans):
    def f(s):
        for v in s["values"]:
            if v["field"] == "rules.0.time_amount":
                v["term"] = {"kind": "literal", "datatype": "number", "value": 30}
    plan = mutate(example_plans["LP-OCI-STO-0001"], 2, f)
    pf, bf = write_plan(tmp_out / "in", [plan])
    res = R.render(pf, tmp_out / "out", bindings_path=bf)
    assert res.renders[0].status == "INVALID_PLAN"
    assert codes(res, "LP-OCI-STO-0001") == ["TYPE_MISMATCH"]


def test_field_not_in_schema_and_computed_only(tmp_out, example_plans):
    def f(s):
        s["values"].append({"field": "state", "term": {"kind": "literal", "datatype": "string", "value": "X"},
                            "origin": "carried", "marked": False})
        s["values"].append({"field": "nao_existe", "term": {"kind": "literal", "datatype": "string", "value": "X"},
                            "origin": "carried", "marked": False})
    plan = mutate(example_plans["LP-OCI-NET-0001"], 1, f)
    pf, bf = write_plan(tmp_out / "in", [plan])
    res = R.render(pf, tmp_out / "out", bindings_path=bf)
    assert codes(res, "LP-OCI-NET-0001") == ["FIELD_NOT_CONFIGURABLE", "FIELD_NOT_IN_SCHEMA"]


def test_reference_rules(tmp_out, example_plans):
    no_dep = mutate(example_plans["LP-OCI-NET-0001"], 2, lambda s: s.__setitem__("depends_on", []))
    pf, bf = write_plan(tmp_out / "a", [no_dep])
    assert codes(R.render(pf, tmp_out / "oa", bindings_path=bf), "LP-OCI-NET-0001") == ["REFERENCE_NOT_IN_DEPENDS_ON"]

    def other_target(s):
        for v in s["values"]:
            if v["field"] == "vcn_id":
                v["term"]["target_address"] = "oci_core_vcn.SYM-00000000deadbeef"
    outside = mutate(example_plans["LP-OCI-NET-0001"], 2, other_target)
    pf, bf = write_plan(tmp_out / "b", [outside])
    assert codes(R.render(pf, tmp_out / "ob", bindings_path=bf), "LP-OCI-NET-0001") == ["REFERENCE_UNRESOLVED"]

    def no_attr(s):
        for v in s["values"]:
            if v["field"] == "vcn_id":
                del v["term"]["attribute"]
    pf, bf = write_plan(tmp_out / "c", [mutate(example_plans["LP-OCI-NET-0001"], 2, no_attr)])
    assert codes(R.render(pf, tmp_out / "oc", bindings_path=bf), "LP-OCI-NET-0001") == ["REFERENCE_UNRESOLVED"]

    pf, bf = write_plan(tmp_out / "d", [example_plans["LP-OCI-NET-0001"]], graph=False)
    assert "NO_GRAPH_IR" in codes(R.render(pf, tmp_out / "od", bindings_path=bf), "LP-OCI-NET-0001")


def test_withheld_carried_fails_and_synthesized_becomes_sensitive_variable(tmp_out, example_plans):
    def carried(s):
        s["values"].append({"field": "kms_key_id", "term": {"kind": "withheld", "reason": "secret"},
                            "origin": "carried", "marked": False})
    pf, bf = write_plan(tmp_out / "a", [mutate(example_plans["LP-OCI-STO-0001"], 1, carried)])
    assert codes(R.render(pf, tmp_out / "oa", bindings_path=bf), "LP-OCI-STO-0001") == ["WITHHELD_NOT_AVAILABLE"]

    def synth(s):
        s["values"].append({"field": "kms_key_id", "term": {"kind": "withheld", "reason": "secret"},
                            "origin": "synthesized", "marked": True})
    pf, bf = write_plan(tmp_out / "b", [mutate(example_plans["LP-OCI-STO-0001"], 1, synth)])
    res = R.render(pf, tmp_out / "ob", bindings_path=bf)
    assert res.renders[0].status == "RENDERED"
    tf = (tmp_out / "ob" / "lp_oci_sto_0001" / "main.tf").read_text()
    assert 'variable "bo_withheld_r1_kms_key_id"' in tf and "sensitive = true" in tf and "default" not in tf
    assert SB.fmt_check(tmp_out / "ob").rc == 0


def test_list_block_index_rules(tmp_out, example_plans):
    def gap(s):
        for v in s["values"]:
            if v["field"].startswith("ingress_security_rules.1."):
                v["field"] = v["field"].replace("ingress_security_rules.1.", "ingress_security_rules.2.")
    pf, bf = write_plan(tmp_out / "a", [mutate(example_plans["LP-OCI-NET-0001"], 2, gap)])
    assert codes(R.render(pf, tmp_out / "oa", bindings_path=bf), "LP-OCI-NET-0001") == ["INDEX_GAP"]

    def mixed(s):
        s["values"].append({"field": "egress_security_rules.1.protocol",
                            "term": {"kind": "literal", "datatype": "string", "value": "6"},
                            "origin": "carried", "marked": False})
        s["values"].append({"field": "egress_security_rules.1.destination",
                            "term": {"kind": "literal", "datatype": "string", "value": "10.9.0.0/16"},
                            "origin": "carried", "marked": False})
    pf, bf = write_plan(tmp_out / "b", [mutate(example_plans["LP-OCI-NET-0001"], 2, mixed)])
    assert codes(R.render(pf, tmp_out / "ob", bindings_path=bf), "LP-OCI-NET-0001") == ["MIXED_INDEXING"]

    def too_many(s):
        s["values"].append({"field": "tcp_options.1.destination_port_range.min",
                            "term": {"kind": "literal", "datatype": "number", "value": 1},
                            "origin": "carried", "marked": False})
        s["values"].append({"field": "tcp_options.1.destination_port_range.max",
                            "term": {"kind": "literal", "datatype": "number", "value": 1},
                            "origin": "carried", "marked": False})
    pf, bf = write_plan(tmp_out / "c", [mutate(example_plans["LP-OCI-NET-0001"], 4, too_many)])
    assert "MAX_ITEMS_EXCEEDED" in codes(R.render(pf, tmp_out / "oc", bindings_path=bf), "LP-OCI-NET-0001")


def test_duplicate_field_is_invalid(tmp_out, example_plans):
    def dup(s):
        s["values"].append(dict(s["values"][-1]))
    pf, bf = write_plan(tmp_out / "a", [mutate(example_plans["LP-OCI-STO-0001"], 1, dup)])
    assert codes(R.render(pf, tmp_out / "oa", bindings_path=bf), "LP-OCI-STO-0001") == ["DUPLICATE_FIELD"]


def test_contract_invalid_input_refused(tmp_out, example_plans):
    bad = dict(example_plans["LP-OCI-STO-0001"])
    del bad["dependency_closure"]
    pf, bf = write_plan(tmp_out / "a", [bad])
    with pytest.raises(ValueError, match="C26"):
        R.render(pf, tmp_out / "oa", bindings_path=bf)
    assert R.main([str(pf), "--out", str(tmp_out / "ob")]) == 2
    assert R.main([str(tmp_out / "nao_existe.jsonl"), "--out", str(tmp_out / "oc")]) == 2


def test_out_dir_confined_and_foreign_dir_not_wiped(tmp_out):
    with pytest.raises(ValueError, match="fora de"):
        R.render(EX / "lowering_plan.jsonl", __import__("pathlib").Path("/tmp/bo-harness-oci-out"),
                 bindings_path=EX / "bindings.json")
    foreign = tmp_out / "alheio"
    foreign.mkdir()
    (foreign / "nao_apagar.txt").write_text("x")
    with pytest.raises(SystemExit):
        R.render(EX / "lowering_plan.jsonl", foreign, bindings_path=EX / "bindings.json")
    assert (foreign / "nao_apagar.txt").exists()


def test_render_is_deterministic(tmp_out):
    a = R.render(EX / "lowering_plan.jsonl", tmp_out / "a", bindings_path=EX / "bindings.json")
    b = R.render(EX / "lowering_plan.jsonl", tmp_out / "b", bindings_path=EX / "bindings.json")
    assert a.report["files"] == b.report["files"]


def test_expression_and_document_terms(tmp_out, example_plans):
    def f(s):
        for v in s["values"]:
            if v["field"] == "display_name":
                v["term"] = {"kind": "expression", "op": "format",
                             "args": [{"kind": "literal", "datatype": "string", "value": "bo-%s"},
                                      {"kind": "literal", "datatype": "string", "value": "net"}]}
    pf, bf = write_plan(tmp_out / "a", [mutate(example_plans["LP-OCI-NET-0001"], 1, f)])
    res = R.render(pf, tmp_out / "oa", bindings_path=bf)
    assert res.renders[0].status == "RENDERED"
    assert 'display_name   = format("bo-%s", "net")' in (tmp_out / "oa" / "lp_oci_net_0001" / "main.tf").read_text()

    def g(s):
        for v in s["values"]:
            if v["field"] == "display_name":
                v["term"] = {"kind": "expression", "op": "file",
                             "args": [{"kind": "literal", "datatype": "string", "value": "x"}]}
    pf, bf = write_plan(tmp_out / "b", [mutate(example_plans["LP-OCI-NET-0001"], 1, g)])
    assert codes(R.render(pf, tmp_out / "ob", bindings_path=bf), "LP-OCI-NET-0001") == ["UNSUPPORTED_TERM"]


def test_report_lists_losses_and_derived_name_note(tmp_out):
    res = R.render(EX / "lowering_plan.jsonl", tmp_out / "o", bindings_path=EX / "bindings.json")
    rep = json.loads((tmp_out / "o" / R.REPORT_NAME).read_text())
    net = next(p for p in rep["plans"] if p["plan_id"] == "LP-OCI-NET-0001")
    assert [x["code"] for x in net["losses"]] == ["DENY_NOT_EXPRESSIBLE"]
    assert any("derived_name" in n for n in net["notes"])
    assert rep["counts"]["RENDERED"] == 2 and len(load_jsonl(EX / "lowering_plan.jsonl")) == 2


def test_null_on_required_is_missing(tmp_out, example_plans):
    def f(s):
        for v in s["values"]:
            if v["field"] == "name":
                v["term"] = {"kind": "literal", "datatype": "null", "value": None}
    pf, bf = write_plan(tmp_out / "a", [mutate(example_plans["LP-OCI-STO-0001"], 1, f)])
    res = R.render(pf, tmp_out / "oa", bindings_path=bf)
    assert res.renders[0].status == "UNKNOWN_INPUT"
    assert [(i.code, i.field) for i in res.renders[0].issues] == [("MISSING_REQUIRED_FIELD", "name")]


def test_catalog_g2_with_synthetic_bindings(tmp_out):
    """G2 do catálogo: stub C26 + bindings.synthetic.json -> o plano oci renderiza; origem registrada."""
    stub = REPO / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"
    b = EX.parent / "bindings.synthetic.json"
    assert R.main([str(stub), "--bindings", str(b), "--out", str(tmp_out / "g2")]) == 0
    rep = json.loads((tmp_out / "g2" / R.REPORT_NAME).read_text())
    oci = [p for p in rep["plans"] if p["target_provider"] == "oci"]
    assert [p["status"] for p in oci] == ["RENDERED"]
    assert rep["bindings"]["synthetic"] is True and rep["bindings"]["values_written"] is False
    srcs = {w["field"]: w["source"] for w in oci[0]["written"] if w["source"].startswith("binding:")}
    assert srcs and set(srcs.values()) <= {"binding:compartment_id", "binding:run_tag"}
    tf = (tmp_out / "g2" / oci[0]["module"] / "main.tf").read_text()
    assert "var.bo_ctx_compartment_id" in tf and "oc" + "id1." not in tf and "default" not in tf
    assert SB.fmt_check(tmp_out / "g2").rc == 0
    i, v = SB.init_validate(tmp_out / "g2")
    assert i.rc == 0 and json.loads(v.out)["valid"]


# ------------------------------------------------------------------ HI-OCI-01: tag bo-run declarada pelo harness
def test_lista_da_tag_bate_com_a_tabela_do_safety():
    from bo.harness.oci import run_tag as RT
    from bo.harness.oci import schema as S
    assert (REPO / RT.SAFETY_TABLE).is_file(), "tabela de SKUs do SAFETY ausente"
    assert sorted(RT.types()) == RT.from_safety_table()
    t = S.table()
    for rtype in sorted(RT.types()):
        a = t.block("resource", rtype).attrs.get(RT.ATTRIBUTE)
        assert a is not None and a.type == ["map", "string"] and a.configurable, rtype


def test_tag_bo_run_so_nos_recursos_dos_tipos_da_lista(tmp_out, example_plans):
    from bo.harness.oci import run_tag as RT
    res = R.render(EX / "lowering_plan.jsonl", tmp_out / "out", bindings_path=EX / "bindings.json")
    for p in res.renders:
        plan = example_plans[p.plan_id]
        want = sorted(p.labels[s["order"]] for s in plan["steps"]
                      if s["action"] != "reference" and s["resource_type"] in RT.types())
        assert want, p.plan_id
        assert sorted(x["label"] for x in p.insertions) == want
        assert all(x["insertion_id"] == "HI-OCI-01" and x["expr"] == "var.bo_ctx_run_tag"
                   and x["source"] == "binding:run_tag" for x in p.insertions)
        # nunca no 'written' (que é só do plano) e a variável vem da chave de contexto run_tag, sem default
        assert not any(w.field.startswith("freeform_tags") for w in p.written)
        assert p.variables["bo_ctx_run_tag"].source == "binding:run_tag"
        tf = (tmp_out / "out" / p.module / "main.tf").read_text()
        assert tf.count('"bo-run" = var.bo_ctx_run_tag') == len(want) and "bo_run" not in tf


def test_plano_com_freeform_tags_e_conflito(tmp_out, example_plans):
    plan = mutate(example_plans["LP-OCI-STO-0001"], 1, lambda s: s["values"].append(
        {"field": "freeform_tags", "origin": "carried", "marked": False,
         "term": {"kind": "literal", "datatype": "map", "value": {"bo-run": "fixo"}}}))
    pf, bf = write_plan(tmp_out / "in", [plan])
    res = R.render(pf, tmp_out / "out", bindings_path=bf)
    assert statuses(res) == {"LP-OCI-STO-0001": "INVALID_PLAN"}
    assert codes(res, "LP-OCI-STO-0001") == ["CONFLICTING_VALUES"]
    assert not (tmp_out / "out" / "lp_oci_sto_0001").exists()


def test_chave_bo_run_vinda_do_plano_e_conflito(example_plans):
    # o C26 já recusa '-' no caminho; o renderizador recusa de novo se a chave chegar por outra via
    from bo.harness.oci import schema as S
    plan = mutate(example_plans["LP-OCI-STO-0001"], 1, lambda s: s["values"].append(
        {"field": "freeform_tags.bo-run", "origin": "carried", "marked": False,
         "term": {"kind": "literal", "datatype": "string", "value": "fixo"}}))
    graph = {g["graph_id"]: g for g in load_jsonl(EX / "graph_ir.jsonl")}[plan["graph_id"]]
    pr = R.render_plan(plan, graph, R.load_bindings(EX / "bindings.json"), R.Templates.load(), S.table())
    assert pr.status == "INVALID_PLAN" and "CONFLICTING_VALUES" in {i.code for i in pr.issues}
    assert pr.blocks == [] and pr.insertions == []


def test_plano_com_tag_de_execucao_e_recusado_pelo_c26(tmp_out, example_plans):
    plan = mutate(example_plans["LP-OCI-STO-0001"], 1, lambda s: s["values"].append(
        {"field": "freeform_tags.bo_run", "origin": "carried", "marked": False,
         "term": {"kind": "literal", "datatype": "string", "value": "fixo"}}))
    pf, bf = write_plan(tmp_out / "in", [plan])
    with pytest.raises(ValueError, match="C26-NOTAG|tag de execução"):
        R.render(pf, tmp_out / "out", bindings_path=bf)
