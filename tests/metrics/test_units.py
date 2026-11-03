"""Denominadores: campo, decisão (documento de política por declaração normalizada), NAME/TAG, grafo."""
import copy
import json

import pytest

from bo.metrics import core, units as U
from bo.metrics.invariance import NotExplodable, policy_to_block_records, policy_variants
from conftest import STUBS, jsonl

BASE = {"family_id": "F-00a1b2c3d4e5", "file": "main.tf", "provider": "aws", "repo_id": "R-00a1b2c3d4e5",
        "resource_address": "aws_s3_bucket_policy.SYM-0a1b2c3d4e5f", "resource_type": "aws_s3_bucket_policy"}


def doc_record(tree, **kw):
    return {**BASE, **kw, "attr_path": "policy",
            "term": {"format": "policy_json", "kind": "document", "symbolized": [], "tree": tree}}


POLICY = {"Version": "2012-10-17", "Statement": [
    {"Sid": "Leitura", "Effect": "Allow", "Principal": {"AWS": ["SYM-0a", "SYM-0b"]},
     "Action": ["s3:GetObject", "s3:ListBucket"], "Resource": ["SYM-r1", {"$term": {
         "kind": "reference", "attribute": "arn", "target_address": "aws_s3_bucket.SYM-b", "target_type": "aws_s3_bucket"}}]},
    {"Effect": "Deny", "Principal": "*", "NotAction": ["s3:GetObject", "s3:PutObject"], "Resource": "*",
     "Condition": {"Bool": {"aws:SecureTransport": ["false"]}, "StringEquals": {"aws:x": ["b", "a"]}}}]}


def op_units_for(decisions, code_of):
    return [U.Unit(d.decision_id, d.family_id, d.repo_id, "aws", "google", codes=(code_of(d),)) for d in decisions]


def test_G1_exploding_a_policy_json_into_fields_changes_field_denominator_not_decision_reading():
    """Gate G1: somar campos de um JSON muda o denominador por campo; a leitura por decisão não muda."""
    inline = U.fields_from_symbolic([doc_record(POLICY)])
    blocks = U.fields_from_symbolic(policy_to_block_records(doc_record(POLICY)))
    f_in, f_bl = U.field_units(inline), U.field_units(blocks)
    assert len(f_in) == 1                       # documento = um campo
    assert len(f_bl) > len(f_in)                # explodido: um campo por atributo de bloco
    d_in, d_bl = U.decision_units(f_in), U.decision_units(f_bl)
    # 2 principais x 2 ações x 2 recursos + 1 (NotAction é conjunto, não se parte) = 9
    assert len(d_in) == len(d_bl) == 9
    assert [d.decision_id for d in d_in] == [d.decision_id for d in d_bl]

    def code(d):  # mesmo desfecho do tradutor por decisão, nas duas embalagens
        if "Deny" in d.statement[0]:
            return "INFRA_ERROR"
        return "carried" if "GetObject" in d.statement[2] else "NO_REALIZATION"
    r_in = core.reading("M-OPCOV-DEC", op_units_for(d_in, code))
    r_bl = core.reading("M-OPCOV-DEC", op_units_for(d_bl, code))
    assert r_in == r_bl
    assert r_in["aws->google"].n == 9 and r_in["aws->google"].lower == pytest.approx(4 / 9)
    assert r_in["aws->google"].upper == pytest.approx(5 / 9) and r_in["aws->google"].est == pytest.approx(0.5)
    # a leitura por campo muda com a embalagem (é o que a leitura por decisão corrige)
    fu_in = [U.Unit(f.field_id, f.family_id, f.repo_id, "aws", "google", codes=("carried",)) for f in f_in]
    fu_bl = [U.Unit(f.field_id, f.family_id, f.repo_id, "aws", "google", codes=("carried",)) for f in f_bl]
    assert core.reading("M-OPCOV-FIELD", fu_in)["aws->google"].n != core.reading("M-OPCOV-FIELD", fu_bl)["aws->google"].n


@pytest.mark.parametrize("name", ["reserialized", "keys_reordered", "lists_split", "statements_reversed"])
def test_policy_variants_keep_decisions(name):
    tree = policy_variants(POLICY, seed=3)[name]
    assert U.decisions_of_document(tree) == U.decisions_of_document(POLICY)


def test_single_statement_object_and_scalar_vs_list():
    a = {"Statement": {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}}
    b = {"Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": ["*"], "Sid": "x"}]}
    assert U.decisions_of_document(a) == U.decisions_of_document(b)


def test_notaction_is_not_split_and_duplicates_collapse():
    a = {"Statement": [{"Effect": "Deny", "NotAction": ["a", "b"], "Resource": "*"}]}
    b = {"Statement": [{"Effect": "Deny", "NotAction": ["a"], "Resource": "*"},
                       {"Effect": "Deny", "NotAction": ["b"], "Resource": "*"}]}
    assert len(U.decisions_of_document(a)) == 1 and len(U.decisions_of_document(b)) == 2
    c = {"Statement": [{"Effect": "Allow", "Action": ["x", "x"], "Resource": "*"}] * 2}
    assert len(U.decisions_of_document(c)) == 1


def test_condition_value_order_and_empty_statement():
    a = {"Statement": [{"Effect": "Allow", "Action": "x", "Condition": {"S": {"k": ["1", "2"]}}}, {"Sid": "vazia"}]}
    b = {"Statement": [{"Effect": "Allow", "Action": "x", "Condition": {"S": {"k": ["2", "1"]}}}]}
    assert U.decisions_of_document(a) == U.decisions_of_document(b)
    assert len(U.decisions_of_document(a)) == 1


def test_unresolved_key_kept_and_not_explodable():
    t = {"Statement": [{"Effect": "Allow", "Action": "x", "SYM-k": {"$term": {"kind": "symbol", "symbol_id": "SYM-1"}}}]}
    d = U.decisions_of_document(t)
    assert len(d) == 1 and "$unresolved" in d[0][4]
    with pytest.raises(NotExplodable):
        policy_to_block_records(doc_record(t))


def test_hcl_tuple_equals_list():
    lit = {"Statement": [{"Effect": "Allow", "Action": ["a", "b"]}]}
    tup = {"Statement": [{"Effect": "Allow", "Action": {"$term": {"kind": "expression", "op": "hcl_tuple", "args": [
        {"kind": "literal", "value": "a"}, {"kind": "literal", "value": "b"}]}}}]}
    assert U.decisions_of_document(lit) == U.decisions_of_document(tup)


def test_gcp_bindings_and_unsupported_format():
    g = {"bindings": [{"role": "roles/viewer", "members": ["SYM-u1", "SYM-u2"]}]}
    assert len(U.decisions_of_document(g)) == 2
    with pytest.raises(U.UnsupportedPolicyFormat):
        U.decisions_of_document({"if": {"field": "type"}, "then": {"effect": "deny"}})


def test_name_tag_out_of_field_and_decision_readings_tags_per_key():
    recs = [{**BASE, "attr_path": "bucket", "term": {"kind": "literal", "value": "SYM-n"}},
            {**BASE, "attr_path": "tags", "term": {"kind": "literal", "value": {"a": "1", "b": "2", "c": "3"}}},
            {**BASE, "attr_path": "versioning", "term": {"kind": "literal", "value": True}}]
    roles = {"aws:aws_s3_bucket_policy:bucket": "NAME", "aws:aws_s3_bucket_policy:tags": "TAG"}
    fs = U.fields_from_symbolic(recs, roles.get)
    assert [f.attr_path for f in U.field_units(fs)] == ["versioning"]
    assert len(U.field_units(fs, nametag=True)) == 1 + 3
    assert [d.concept for d in U.decision_units(U.field_units(fs))] == ["versioning"]


def test_stub_symbolic_config_and_graphs():
    recs = jsonl(STUBS / "C06" / "symbolic_config.jsonl")
    roles = {r["atom_id"]: r["role"] for r in jsonl(STUBS / "C04" / "roles.jsonl")}
    fs = U.fields_from_symbolic(recs, roles.get)
    assert len(U.field_units(fs)) == 5
    ds = U.decision_units(U.field_units(fs))
    assert sum(1 for d in ds if d.concept == "policy_statement") == 1
    g = U.config_graphs(recs)
    # aws_db_instance referencia aws_db_subnet_group, que não tem registro próprio: grafo do db sozinho
    assert len(set(g.values())) == 2


def test_graph_components_link_by_reference():
    def r(addr, ref=None):
        t = {"kind": "reference", "target_address": ref, "attribute": "id", "target_type": "x"} if ref else \
            {"kind": "literal", "value": 1}
        return {**BASE, "resource_address": addr, "attr_path": "a", "term": t}
    g = U.config_graphs([r("a.x"), r("b.y", "a.x"), r("c.z", "b.y"), r("d.w")])
    rid = lambda a: f"{BASE['repo_id']}|{BASE['file']}|{a}"
    assert g[rid("a.x")] == g[rid("b.y")] == g[rid("c.z")] != g[rid("d.w")]


def test_trace_and_case_adapters_on_stubs():
    tr = jsonl(STUBS / "C23" / "translation_trace.jsonl")
    assert U.trace_codes(tr) == ["carried", "CONDITION_FALSE", "REFUTED_BY_RULE", "omitted"]
    cases = jsonl(STUBS / "C11" / "cases.jsonl")
    outs = jsonl(STUBS / "C12" / "outcomes.jsonl")
    cu = U.case_units(cases, outs)
    assert [u.unit_id for u in cu] == ["CASE-AWSGCP-DB-0001"]          # só origin = sample
    assert (cu[0].source, cu[0].target, cu[0].weight) == ("aws", "google", 12.5)
    assert cu[0].codes == ("INFRA_ERROR",)                               # empate de hora: vence o maior outcome_id
    later = copy.deepcopy(outs)
    later[0]["decided_at"] = "2026-11-03T12:00:00-03:00"
    assert U.case_units(cases, later)[0].codes == ("PERSISTED",)        # retentativa: vale a última
    assert U.case_units(cases, [])[0].codes == ("UNKNOWN",)             # sem desfecho: no intervalo
    pj = U.probe_units(jsonl(STUBS / "C22" / "pair_judgements.jsonl"), cases)
    assert (pj[0].source, pj[0].target, pj[0].codes) == ("aws", "google", ("OBSERVATIONS_MATCH_UNDER_PROTOCOL",))


def test_pair_direction():
    assert U.pair_direction("AZOCI", "inverse") == ("oci", "azurerm")
    assert U.pair_of("oci", "azurerm") == "AZOCI"
    with pytest.raises(U.UnitError):
        U.pair_direction("AWSGCP", "sideways")


@pytest.mark.parametrize("rec,q,code", [
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "broad", "satisfiable": "TRUE"}, "existential", "TRANSPORTS"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "narrow", "valid": "FALSE"}, "universal", "PREDICATE_FALSE"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "broad"}, "universal", "TRANSPORTS"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "exact", "valid": "INDETERMINATE"}, "universal", "CONDITION_INDETERMINATE"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "exact", "satisfiable": "TRUE", "guard": "INDETERMINATE"}, "existential", "CONDITION_INDETERMINATE"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "exact", "satisfiable": "TRUE", "guard": "FALSE"}, "existential", "CONDITION_FALSE"),
    ({"verdict": "OK", "evidence_state": "STRUCTURALLY_VALID", "relation": "exact", "satisfiable": "TRUE"}, "existential", "EVIDENCE_BELOW_DOC_SUPPORTED"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "exact", "kind_unknown": True, "satisfiable": "TRUE"}, "existential", "KIND_UNKNOWN"),
    ({"verdict": "UNPROVEN"}, "existential", "UNPROVEN"),
    ({"verdict": "OK", "repair_excluded": True}, "existential", "REPAIR_EXCLUDED"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "related", "satisfiable": "TRUE"}, "existential", "RELATED_ONLY"),
    ({"verdict": "OK", "evidence_state": "PERSISTENCE_VERIFIED", "relation": "close", "value_status": "SYMBOLIC"}, "observed_fraction", "UNKNOWN_SYMBOLIC_INPUT"),
    ({"verdict": "OK", "evidence_state": "DOC_SUPPORTED", "relation": "exact", "value_status": "FALSE"}, "observed_fraction", "FUNCTION_UNDEFINED"),
])
def test_transport_code(rec, q, code):
    assert U.transport_code(rec, q) == code


def test_complete_unit_codes():
    plan = {"dependency_closure": {"closed": True, "missing": []}}
    assert "COMPLETE" in U.complete_unit_codes({"plan": plan, "trace_codes": ["carried"], "validate": "ok"})
    assert "DEPENDENCY_OPEN" in U.complete_unit_codes({"plan": {"dependency_closure": {"closed": False}},
                                                      "validate": "ok"})
    c = U.complete_unit_codes({"plan": plan, "trace_codes": ["carried"], "required_missing": ["x"], "validate": "ok"})
    assert "UNKNOWN_INPUT" in c and "COMPLETE" not in c
    assert "INFRA_ERROR" in U.complete_unit_codes({"plan": plan, "trace_codes": ["carried"], "validate": "INFRA_ERROR"})
