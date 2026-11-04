"""Testes do CORPUS-GCP: caminho C06 -> átomo, regras de contagem e contrato C06 usage (dados sintéticos)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from bo.corpus_gcp import build
from bo.corpus_gcp.check import _cls, _norm
from bo.corpus_gcp.count import count_repo, load_atoms, resolve, term_class
from bo.corpus_gcp.paths import classify_path

R, F = "R-0123456789ab", "F-0123456789ab"


@pytest.mark.parametrize("p,want", [
    ("name", ("path", "name")),
    ("network_interface[0].network", ("path", "network_interface.network")),
    ("boot_disk[0].initialize_params[0].image", ("path", "boot_disk.initialize_params.image")),
    ('dynamic["binding"][0].content.members', ("path", "binding.members")),
    ('config[0].dynamic["software_config"][0].content.image_version', ("path", "config.software_config.image_version")),
    ('dynamic["a"][0].content.dynamic["b"][1].content.c', ("path", "a.b.c")),
    ('dynamic["a"][0].content.b[0].count', ("path", "a.b.count")),
    ("quantity_based_retention[0].count", ("path", "quantity_based_retention.count")),
    ('dynamic["binding"][0].for_each', ("meta", None)),
    ('dynamic["binding"][0].iterator', ("meta", None)),
    ('a[0].dynamic["b"][0].labels', ("meta", None)),
    ("count", ("meta", None)),
    ("for_each", ("meta", None)),
    ("provider", ("meta", None)),
    ("depends_on", ("meta", None)),
    ("lifecycle[0].ignore_changes", ("meta", None)),
    ("provisioner[0]", ("meta", None)),
    ("connection[0]", ("meta", None)),
    ("template[0].containers[0].env[0]", ("block", "template.containers.env")),
    ('dynamic["env"][0].content', ("block", "env")),
    ("content", ("path", "content")),
    ('dynamic["x"][0].value', ("malformed", None)),
    (".name", ("malformed", None)),
    ("a b", ("malformed", None)),
    ("[0].x", ("malformed", None)),
])
def test_classify_path(p, want):
    assert classify_path(p) == want


@pytest.mark.parametrize("p", [
    "name", "network_interface[0].network", 'dynamic["binding"][0].content.members',
    'dynamic["a"][0].content.dynamic["b"][1].content.c', "quantity_based_retention[0].count",
    "template[0].containers[0].env[0]", 'dynamic["env"][0].content', "x[0].content", "content",
    'dynamic["a"][0].content.b[0].count', 'dynamic["binding"][0].for_each', "lifecycle[0].ignore_changes",
])
def test_recount_normalizer_agrees(p):
    """A recontagem independente (check._norm, por regex) e o paths.classify_path dão o mesmo caminho."""
    cat, path = classify_path(p)
    q, whole = _norm(p)
    if cat == "meta":
        assert q is None
    else:
        assert (q, whole) == (path, cat == "block")


ATOM_LINES = [json.dumps({"atom_id": f"google:{t}:{p}", "provider": "google", "resource_type": t, "path": p})
              for t, p in [("google_compute_firewall", "name"), ("google_compute_firewall", "network"),
                           ("google_compute_firewall", "allow.protocol"), ("google_compute_firewall", "allow.ports"),
                           ("google_compute_instance", "name"), ("google_compute_instance", "metadata"),
                           ("google_compute_instance", "network_interface.access_config.nat_ip"),
                           ("google_cloud_run_v2_service", "template.containers.env.name"),
                           ("google_cloud_run_v2_service", "template.containers.env.value")]] + \
    [json.dumps({"atom_id": "aws:aws_vpc:cidr_block", "provider": "aws", "resource_type": "aws_vpc",
                 "path": "cidr_block"})]


@pytest.fixture()
def atoms():
    return load_atoms(ATOM_LINES)


def test_load_atoms_only_google(atoms):
    assert "aws_vpc" not in atoms
    paths, blocks = atoms["google_compute_instance"]
    assert "network_interface.access_config.nat_ip" in paths
    assert {"network_interface", "network_interface.access_config"} <= blocks


def test_resolve(atoms):
    assert resolve(atoms, "google_compute_firewall", "allow[1].ports", "expression") == ("atom", "allow.ports")
    assert resolve(atoms, "google_compute_instance", "metadata", "withheld") == ("atom", "metadata")
    assert resolve(atoms, "google_compute_instance", "metadata.foo", "literal") == ("atom_object", "metadata")
    assert resolve(atoms, "google_compute_instance", "network_interface[0].access_config", "expression") == \
        ("block_as_attribute", None)
    assert resolve(atoms, "google_cloud_run_v2_service", "template[0].containers[0].env[0]", "withheld") == \
        ("withheld_block", None)
    assert resolve(atoms, "google_compute_instance", "zonee", "literal") == ("unmatched_path", None)
    assert resolve(atoms, "google_beta_only_thing", "name", "literal") == ("unmatched_type", None)
    assert resolve(atoms, "google_compute_instance", "count", "literal") == ("meta", None)


VAR = {"kind": "symbol", "symbol_id": "SYM-0123456789ab", "name_class": "variable", "scope": "repo"}
LIT = {"kind": "literal", "datatype": "string", "value": "x"}
WH = {"kind": "withheld", "reason": "secret"}
REF = {"kind": "reference", "target_type": "google_compute_network",
       "target_address": "google_compute_network.SYM-0123456789ab", "attribute": "id"}


@pytest.mark.parametrize("term,want", [
    (LIT, "literal"),
    ({"kind": "symbol", "symbol_id": "SYM-0123456789ac", "name_class": "unknown", "scope": "repo"}, "literal"),
    ({"kind": "expression", "op": "cidr", "args": [{"kind": "symbol", "symbol_id": "SYM-0123456789ac",
      "name_class": "unknown", "scope": "repo"}, {"kind": "literal", "datatype": "number", "value": 24}]}, "literal"),
    (VAR, "symbolic"),
    (REF, "symbolic"),
    ({"kind": "expression", "op": "hcl_template", "args": [LIT, VAR]}, "symbolic"),
    ({"kind": "expression", "op": "file", "args": [LIT]}, "symbolic"),
    ({"kind": "expression", "op": "lower", "args": [LIT]}, "literal"),
    ({"kind": "expression", "op": "hcl_object", "args": [LIT, WH]}, "withheld"),
    (WH, "withheld"),
    ({"kind": "document", "format": "policy_json", "tree": {"a": "b"}, "symbolized": []}, "literal"),
    ({"kind": "document", "format": "json", "tree": {"a": {"$term": REF}}, "symbolized": []}, "symbolic"),
    ({"kind": "document", "format": "json", "tree": [{"$key": VAR, "$value": "x"}], "symbolized": []}, "symbolic"),
    ({"kind": "document", "format": "json", "tree": {"k": [{"$term": WH}]}, "symbolized": []}, "withheld"),
])
def test_term_class_and_recount_agree(term, want):
    assert term_class(term) == want
    assert _cls(term) == want  # a recontagem independente classifica pelo JSON serializado


def rec(file, addr, rtype, path, kind):
    term = {"literal": {"kind": "literal", "datatype": "string", "value": "x"},
            "symbol": VAR,
            "expression": {"kind": "expression", "op": "hcl_tuple", "args": [VAR]},
            "privacy": {"kind": "symbol", "symbol_id": "SYM-0123456789ac", "name_class": "unknown", "scope": "repo"},
            "null": {"kind": "literal", "datatype": "null", "value": None},
            "reference": REF, "withheld": WH}[kind]
    return {"repo_id": R, "family_id": F, "file": file, "resource_address": addr, "resource_type": rtype,
            "provider": "google", "attr_path": path, "term": term}


FW1 = ("net/main.tf", "google_compute_firewall.SYM-000000000a01")
FW2 = ("net/main.tf", "google_compute_firewall.SYM-000000000a02")
FW3 = ("mods/fw/main.tf", "module.SYM-000000000b01.google_compute_firewall.SYM-000000000a03")
VM1 = ("main.tf", "google_compute_instance.SYM-000000000a04")
DATA = ("main.tf", "data.google_compute_network.SYM-000000000a05")
UNK = ("main.tf", "google_beta_only_thing.SYM-000000000a06")


def synthetic():
    resources = [(*FW1, "google_compute_firewall", 4), (*FW2, "google_compute_firewall", 2),
                 (*FW3, "google_compute_firewall", 2), (*VM1, "google_compute_instance", 3),
                 (*DATA, "google_compute_network", 1), (*UNK, "google_beta_only_thing", 1)]
    records = [
        rec(*FW1, "google_compute_firewall", "name", "literal"),
        rec(*FW1, "google_compute_firewall", "allow[0].ports", "literal"),
        rec(*FW1, "google_compute_firewall", "allow[1].ports", "symbol"),  # mesma átomo, 2 blocos: simbólico vence
        rec(*FW1, "google_compute_firewall", "count", "symbol"),           # meta
        rec(*FW2, "google_compute_firewall", "name", "symbol"),
        rec(*FW2, "google_compute_firewall", 'dynamic["allow"][0].content.ports', "expression"),
        rec(*VM1, "google_compute_instance", "name", "literal"),
        rec(*VM1, "google_compute_instance", "metadata", "withheld"),
        rec(*VM1, "google_compute_instance", "zonee", "literal"),          # sem átomo
        rec(*FW3, "google_compute_firewall", "name", "null"),              # attr = null: não configura
        rec(*FW3, "google_compute_firewall", "network", "privacy"),        # cadeia simbolizada: literal
        rec(*DATA, "google_compute_network", "name", "literal"),           # data: fora
        rec(*UNK, "google_beta_only_thing", "name", "literal"),            # tipo fora do schema
    ]
    return resources, records


def test_count_repo_rules(atoms):
    resources, records = synthetic()
    out = count_repo(R, F, resources, records, atoms)
    rows = {(r["resource_type"], r.get("atom_id")): r for r in out["rows"]}
    fw = rows[("google_compute_firewall", None)]
    assert (fw["n_resources"], fw["n_set"], fw["n_literal"], fw["n_symbolic"], fw["n_withheld"]) == (3, 3, 1, 2, 0)
    name = rows[("google_compute_firewall", "google:google_compute_firewall:name")]
    assert (name["n_resources"], name["n_set"], name["n_literal"], name["n_symbolic"]) == (3, 2, 1, 1)
    ports = rows[("google_compute_firewall", "google:google_compute_firewall:allow.ports")]
    assert (ports["n_set"], ports["n_literal"], ports["n_symbolic"]) == (2, 0, 2)
    net = rows[("google_compute_firewall", "google:google_compute_firewall:network")]
    assert (net["n_set"], net["n_literal"]) == (1, 1)
    assert ("google_compute_firewall", "google:google_compute_firewall:allow.protocol") not in rows  # implícito
    assert out["cov"]["records:explicit_null"] == 1
    vm = rows[("google_compute_instance", None)]
    assert (vm["n_resources"], vm["n_set"], vm["n_withheld"]) == (1, 1, 1)
    md = rows[("google_compute_instance", "google:google_compute_instance:metadata")]
    assert (md["n_set"], md["n_withheld"]) == (1, 1)
    assert ("google_compute_network", None) not in rows                 # data source fora do uso
    unk = rows[("google_beta_only_thing", None)]
    assert (unk["n_resources"], unk["n_set"]) == (1, 0)
    assert out["cov"]["records:meta"] == 1 and out["cov"]["records:unmatched_path"] == 1
    assert out["cov"]["records:unmatched_type"] == 1 and out["cov"]["data_source_records"] == 1
    assert out["cov"]["data_source_blocks"] == 1 and out["cov"]["resources_managed"] == 5
    assert out["cov"]["modules_managed"] == 3
    assert dict(out["check"]) == {}
    assert out["unmatched"] == [("google_compute_instance", "zonee")]
    # n_set, n_lit, n_sym, n_wh, n_mod, registros por tipo de termo
    assert out["atoms"]["google:google_compute_firewall:name"][:5] == [2, 1, 1, 0, 1]
    assert out["types"]["google_compute_firewall"][:4] == [3, 2, 3, 2]  # 3 blocos em 2 módulos, todos com átomo
    for r in out["rows"]:
        assert r["n_literal"] + r["n_symbolic"] + r["n_withheld"] == r["n_set"] <= r["n_resources"]


def test_count_repo_detects_inconsistency(atoms):
    resources, records = synthetic()
    resources[0] = (*FW1, "google_compute_firewall", 99)
    records.append(rec("outro.tf", "google_compute_firewall.SYM-000000000a99", "google_compute_firewall", "name",
                       "literal"))
    out = count_repo(R, F, resources, records, atoms)
    assert out["check"]["resources_n_attrs_mismatch"] == 1
    assert out["check"]["records_without_resource_row"] == 1


def test_read_repo_records_checks_span(tmp_path):
    p = tmp_path / "s.jsonl"
    a = json.dumps({"repo_id": R, "provider": "google"}, separators=(",", ":")) + "\n"
    b = json.dumps({"repo_id": R, "provider": "aws"}, separators=(",", ":")) + "\n"
    c = json.dumps({"repo_id": "R-ffffffffffff", "provider": "google"}, separators=(",", ":")) + "\n"
    p.write_text(a + b + c)
    with open(p, "rb") as fh:
        assert len(build.read_repo_records(fh, (0, len(a + b), 2), R)) == 1
        with pytest.raises(ValueError):
            build.read_repo_records(fh, (0, len(a + b + c), 3), R)
        with pytest.raises(ValueError):
            build.read_repo_records(fh, (0, len(a + b), 3), R)


def test_rows_pass_official_c06_usage(atoms, tmp_path):
    resources, records = synthetic()
    out = count_repo(R, F, resources, records, atoms)
    p = tmp_path / "usage.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in out["rows"]))
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_no_split_field(atoms):
    resources, records = synthetic()
    for r in count_repo(R, F, resources, records, atoms)["rows"]:
        assert not {"split", "partition", "fold"} & set(r)


def test_promote_only_inside_lock(atoms, tmp_path, monkeypatch):
    from bo.corpus_gcp import common as C
    from bo.corpus_gcp import promote
    monkeypatch.setenv("BO_DATA", str(tmp_path))
    st = C.staging_dir()
    st.mkdir(parents=True)
    resources, records = synthetic()
    (st / "usage.jsonl").write_text("".join(C.dumps(r) + "\n" for r in count_repo(R, F, resources, records,
                                                                                    atoms)["rows"]))
    (st / "coverage.json").write_text("{}\n")
    (st / "MANIFEST.sha256").write_text("".join(f"{C.sha256_file(st / n)}  {n}\n"
                                                for n in ("coverage.json", "usage.jsonl")))
    assert promote.main(["--lock", "merge-base"]) == 2           # sem trava: nada trocado
    assert (st / "usage.jsonl").is_file() and not (C.out_dir() / "usage.jsonl").exists()
    lock = tmp_path / "locks" / "merge-base"
    lock.mkdir(parents=True)
    (lock / "owner").write_text("owner=OUTRO@1\n")
    assert promote.main(["--lock", "merge-base"]) == 2           # trava de outro módulo
    (lock / "owner").write_text("owner=CORPUS-GCP@1\n")
    (st / "coverage.json").write_text("{\"mexido\": 1}\n")
    assert promote.main(["--lock", "merge-base"]) == 1           # staging diverge do manifesto
    (st / "coverage.json").write_text("{}\n")
    assert promote.main(["--lock", "merge-base"]) == 0
    assert not st.exists()
    assert (C.out_dir() / "usage.jsonl").is_file() and (C.out_dir() / "MANIFEST.sha256").is_file()


def test_validated_record_must_match_sha(tmp_path):
    from bo.corpus_gcp import promote
    (tmp_path / "usage.jsonl").write_text("x\n")
    assert not promote.validated(tmp_path)
    from bo.corpus_gcp.common import sha256_file
    (tmp_path / promote.VALIDATED).write_text(json.dumps({"result": "PASS", "sha256": sha256_file(tmp_path / "usage.jsonl")}))
    assert promote.validated(tmp_path)
    (tmp_path / "usage.jsonl").write_text("y\n")
    assert not promote.validated(tmp_path)
