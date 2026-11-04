"""bo.corpus_oci.build/check sobre o corpus sintético: contagens esperadas, contrato C06, determinismo."""
import json
import subprocess
import sys

import pytest
from conftest import F1, F2, R1, R2, R3, rec, write_data, corpus, LIT

from bo.corpus_oci import build, check, counting


def _usage(out):
    return [json.loads(x) for x in (out / "usage.jsonl").read_text().splitlines()]


def _key(u):
    return (u["repo_id"], u["resource_type"], u.get("atom_id"))


@pytest.fixture
def built(data_root):
    out = data_root / "out"
    rep = build.run("oci", out)
    return out, rep


def test_expected_usage(built):
    out, rep = built
    u = {_key(x): x for x in _usage(out)}
    cnt = lambda x: (x["n_resources"], x["n_set"], x["n_literal"], x["n_symbolic"], x["n_withheld"])  # noqa: E731
    inst = "oci_core_instance"
    assert cnt(u[(R1, inst, None)]) == (2, 2, 0, 1, 1)
    assert cnt(u[(R1, inst, "oci:oci_core_instance:shape")]) == (2, 2, 1, 1, 0)
    assert cnt(u[(R1, inst, "oci:oci_core_instance:metadata")]) == (2, 1, 0, 0, 1)
    assert cnt(u[(R1, inst, "oci:oci_core_instance:shape_config.ocpus")]) == (2, 2, 2, 0, 0)
    sl = "oci_core_security_list"
    # protocol em dois blocos: literal + referência -> symbolic, um recurso só
    assert cnt(u[(R1, sl, "oci:oci_core_security_list:ingress_security_rules.protocol")]) == (1, 1, 0, 1, 0)
    assert cnt(u[(R1, sl, "oci:oci_core_security_list:ingress_security_rules.tcp_options.min")]) == (1, 1, 1, 0, 0)
    assert cnt(u[(R1, "oci_tag", None)]) == (1, 0, 0, 0, 0)
    assert cnt(u[(R2, inst, "oci:oci_core_instance:metadata")]) == (1, 1, 0, 0, 1)
    assert cnt(u[(R2, sl, None)]) == (1, 0, 0, 0, 0)
    assert cnt(u[(R3, sl, None)]) == (1, 0, 0, 0, 0)
    assert u[(R1, inst, None)]["family_id"] == F1 and u[(R3, sl, None)]["family_id"] == F2
    # data source e outro provedor fora; nenhum átomo não configurável aparece; nenhum n_set 0 em átomo
    assert not any(k[1] in ("oci_core_images", "aws_s3_bucket") for k in u)
    assert all(x["n_set"] > 0 for x in u.values() if "atom_id" in x)
    assert len(u) == len(_usage(out))  # sem chave repetida
    c = rep["counts"]
    assert (c["managed_blocks"], c["data_blocks"], c["data_records"], c["repos_without_records"]) == (7, 1, 1, 1)
    assert c["managed_records"] == c["managed_attrs_declared"] == 16
    assert rep["unattributed_records"] == {"meta_argument": 1, "dynamic_meta": 1, "block_as_attribute": 1,
                                           "attr_not_in_schema": 1, "type_not_in_schema": 1}
    assert c["modules_with_managed"] == 4 and c["repos_with_managed"] == 3 and c["families_with_managed"] == 2


def test_atom_totals(built):
    out, _ = built
    t = {x["atom_id"]: x for x in map(json.loads, (out / "atom_totals.jsonl").read_text().splitlines())}
    assert len(t) == 8  # todo átomo do schema, inclusive os nunca configurados
    s = t["oci:oci_core_instance:shape"]
    assert (s["n_repos"], s["n_families"], s["n_modules"], s["n_set"]) == (1, 1, 2, 2)
    m = t["oci:oci_core_instance:metadata"]
    assert (m["n_repos"], m["n_families"], m["n_modules"], m["n_withheld"]) == (2, 2, 2, 2)
    st = t["oci:oci_core_instance:state"]
    assert st["configurable"] is False and st["n_set"] == 0
    assert (st["type_n_resources"], st["type_n_repos"], st["type_n_modules"]) == (3, 2, 3)
    tt = {x["resource_type"]: x for x in map(json.loads, (out / "type_totals.jsonl").read_text().splitlines())}
    assert tt["oci_tag"]["in_schema"] is False and tt["oci_core_security_list"]["n_resources"] == 3


def test_contract_and_check(built, data_root):
    out, _ = built
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(out / "usage.jsonl")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert check.check(out, "oci") == []


def test_check_catches_tampering(built):
    out, _ = built
    lines = (out / "usage.jsonl").read_text().splitlines()
    u = json.loads(lines[0])
    u["n_resources"] += 1
    u["n_set"] = min(u["n_set"], u["n_resources"])
    (out / "usage.jsonl").write_text("\n".join([counting.dumps(u)] + lines[1:]) + "\n")
    assert check.check(out, "oci", verify_input_sha=False)


def test_check_catches_dropped_record(built):
    out, _ = built
    lines = (out / "usage.jsonl").read_text().splitlines()
    (out / "usage.jsonl").write_text("\n".join(lines[1:]) + "\n")
    assert check.check(out, "oci", verify_input_sha=False)


def test_deterministic(built, data_root):
    out, _ = built
    out2 = data_root / "out2"
    build.run("oci", out2)
    for f in ("usage.jsonl", "atom_totals.jsonl", "type_totals.jsonl", "build_report.json"):
        assert (out / f).read_bytes() == (out2 / f).read_bytes(), f


def test_orphan_record_fails(data_root, monkeypatch):
    rows, recs = corpus()
    recs.append(rec(R1, F1, "zz.tf", "oci_core_vcn.SYM-0000000000zz", "oci_core_vcn", "cidr_block", LIT))
    root = data_root / "orphan"
    write_data(root, rows, recs)
    monkeypatch.setenv("BO_DATA", str(root))
    with pytest.raises(ValueError):
        build.run("oci", root / "out")


def test_no_names_in_output(built):
    out, _ = built
    for f in ("usage.jsonl", "atom_totals.jsonl", "type_totals.jsonl", "build_report.json"):
        txt = (out / f).read_text()
        assert ".tf" not in txt and "SYM-" not in txt  # nem arquivo nem endereço de recurso
