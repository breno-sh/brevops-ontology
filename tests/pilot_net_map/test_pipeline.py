"""Testes do PILOT-NET-MAP: pacote sintético mínimo (provedores reais só como nomes de tipo, valores sintéticos)
e, quando presente, o pacote oficial do PILOT-NET-GLOSS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bo.contracts import sssom as CS
from bo.pilot_net_map import bundle as BU
from bo.pilot_net_map import generate as GN
from bo.pilot_net_map import verify as VF
from bo.pilot_net_map.common import MAPPING_SET_ID, NO_TERM, PAIRS, PREFIXES, default_bundle, sha256_file

NA = "NOT_APPLICABLE"


def _atom(aid, role, scalar=None, tree=False, enum=None, rng=None, qk=NA):
    p, t, path = aid.split(":", 2)
    dt = {"kind": "tree", "format": "list"} if tree else {"kind": "scalar", "scalar": scalar}
    r = {"atom_id": aid, "datatype": dt, "path": path, "provider": p, "quantity_kind": qk,
         "resource_type": t, "role": role, "unit": qk if qk in (NA, "UNKNOWN") else "unit:NUM", "unit_id": f"CU-{p}-{t}"}
    if enum:
        r["enum"] = enum
    if rng:
        r["range"] = rng
    return r


ATOMS = [
    _atom("aws:aws_vpc_security_group_ingress_rule:ip_protocol", "CONFIG", "string"),
    _atom("aws:aws_vpc_security_group_ingress_rule:cidr_ipv4", "CONFIG", "string"),
    _atom("aws:aws_vpc_security_group_ingress_rule:from_port", "CONFIG", "decimal"),
    _atom("aws:aws_vpc_security_group_ingress_rule:to_port", "CONFIG", "decimal"),
    _atom("aws:aws_vpc_security_group_ingress_rule:id", "IDENTIFIER", "string"),
    _atom("azurerm:azurerm_network_security_rule:protocol", "CONFIG", "enum", enum=["Tcp", "Udp", "*"]),
    _atom("azurerm:azurerm_network_security_rule:direction", "CONFIG", "enum", enum=["Inbound", "Outbound"]),
    _atom("azurerm:azurerm_network_security_rule:access", "CONFIG", "enum", enum=["Allow", "Deny"]),
    _atom("azurerm:azurerm_network_security_rule:source_address_prefix", "CONFIG", "string"),
    _atom("azurerm:azurerm_network_security_rule:destination_port_range", "CONFIG", "string"),
    _atom("azurerm:azurerm_network_security_rule:priority", "CONFIG", "decimal", rng={"min": 100, "max": 4096}),
    _atom("azurerm:azurerm_network_security_rule:id", "IDENTIFIER", "string"),
    _atom("google:google_compute_firewall:priority", "CONFIG", "decimal", rng={"min": 0, "max": 65535}),
    _atom("google:google_compute_firewall:direction", "CONFIG", "enum", enum=["INGRESS", "EGRESS"]),
    _atom("google:google_compute_firewall:source_ranges", "CONFIG", tree=True),
    _atom("google:google_compute_firewall:allow.protocol", "CONFIG", "string"),
    _atom("google:google_compute_firewall:deny.protocol", "CONFIG", "string"),
    _atom("oci:oci_core_network_security_group_security_rule:protocol", "CONFIG", "string"),
    _atom("oci:oci_core_network_security_group_security_rule:direction", "CONFIG", "string"),
]


def _anchor(i, atom, concept, sentence="frase sintética publicada"):
    return {"atom_id": atom, "claim_id": f"ANC-t-{i:04d}", "concept_id": concept, "evidence_level": "published",
            "evidence_state": "STRUCTURALLY_VALID", "extraction_method": "parser",
            "source": {"repo": "example/repo", "file": "doc.md", "line": i, "tag": "v1.0.0", "sentence": sentence},
            "sentence": sentence}


ANCHORS = [
    _anchor(1, "aws:aws_vpc_security_group_ingress_rule:ip_protocol", "concept:rule_protocol"),
    _anchor(2, "azurerm:azurerm_network_security_rule:protocol", "concept:rule_protocol"),
    _anchor(3, "google:google_compute_firewall:priority", "concept:rule_priority"),
    _anchor(4, "azurerm:azurerm_network_security_rule:priority", "concept:rule_priority"),
]


def _write_bundle(root: Path, atoms=ATOMS, anchors=ANCHORS) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "atoms.jsonl": atoms,
        "canonical_atoms.jsonl": [{"atom_id": a["atom_id"], "path_in_unit": a["path"], "role": a["role"],
                                   "unit_id": a["unit_id"]} for a in atoms],
        "claims.jsonl": anchors, "candidates.jsonl": [], "glossary.jsonl": [], "decisions.jsonl": [],
        "canonical_units.jsonl": [], "service_evidence.jsonl": [], "slice_notes.jsonl": [],
    }
    shas = {}
    for name, rows in files.items():
        (root / name).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        shas[name] = sha256_file(root / name)
    (root / "bundle.json").write_text(json.dumps({"files": shas, "domain": "NET"}), encoding="utf-8")
    return root


@pytest.fixture()
def synth(tmp_path):
    return BU.load(_write_bundle(tmp_path / "bundle"))


def _by(recs, s, o):
    return [r for r in recs if r["subject_id"] == s and r["object_id"] == o]


def test_manifest_tamper_refused(tmp_path):
    root = _write_bundle(tmp_path / "b")
    (root / "atoms.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(BU.BundleError):
        BU.load(root)


def test_extra_file_refused(tmp_path):
    root = _write_bundle(tmp_path / "b")
    (root / "gold.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(BU.BundleError):
        BU.load(root)


def test_list_has_no_type(synth):
    assert synth.types["google:google_compute_firewall:source_ranges"] is None
    assert synth.types["azurerm:azurerm_network_security_rule:priority"]["range"] == {"min": 100, "max": 4096}


def test_fixed_direction_guards_attribute_side(synth):
    recs, _ = GN.generate(synth)
    rows = _by(recs, "aws:aws_vpc_security_group_ingress_rule:ip_protocol", "azurerm:azurerm_network_security_rule:protocol")
    assert len(rows) == 1
    g = rows[0]["guard"]["all"]
    assert {"term": "object.direction", "op": "eq", "value": "Inbound"} in g
    assert {"term": "object.access", "op": "eq", "value": "Allow"} in g      # aws só permite: guarda no efeito
    assert rows[0]["evidence_state"] == "DOC_SUPPORTED"
    assert rows[0]["proof"]["tests"][0]["input"] in ("Tcp", "Udp", "*")      # teste admitido pelo enum do objeto


def test_undocumented_direction_is_skipped_not_invented(synth):
    recs, st = GN.generate(synth)
    assert not _by(recs, "aws:aws_vpc_security_group_ingress_rule:ip_protocol",
                   "oci:oci_core_network_security_group_security_rule:protocol")
    absent = [r for r in recs if r["subject_id"] == "oci:oci_core_network_security_group_security_rule:direction"]
    assert absent and all(r["absence"]["kind"] == "UNRESOLVED" for r in absent)
    assert st["skipped_pairings"] > 0


def test_priority_is_close_with_saturation(synth):
    recs, _ = GN.generate(synth)
    rows = _by(recs, "google:google_compute_firewall:priority", "azurerm:azurerm_network_security_rule:priority")
    assert len(rows) == 2                     # bloco usado (allow/deny) x access: duas guardas exclusivas
    for r in rows:
        assert r["semantic_relation"] == "close" and r["predicate_id"] == "skos:closeMatch"
        assert {x["kind"] for x in r["loss_contract"]} == {"saturation", "semantic"}
        assert r["value_domain_relation"]["relation"] == "superset"
        assert 100 <= r["proof"]["tests"][0]["input"] <= 4096


def test_direction_enum_map(synth):
    recs, _ = GN.generate(synth)
    rows = _by(recs, "google:google_compute_firewall:direction", "azurerm:azurerm_network_security_rule:direction")
    assert rows and rows[0]["translation_fn"] == {"name": "enum_map", "params": {"table": {"EGRESS": "Outbound",
                                                                                         "INGRESS": "Inbound"}}}
    assert rows[0]["transport_fidelity"] == "lossless"


def test_port_group_join(synth):
    recs, _ = GN.generate(synth)
    gs = [r for r in recs if r.get("group")]
    assert gs, "grupo N:1 de portas esperado no AWSAZ"
    g = gs[0]
    assert g["group"]["cardinality"] == "N:1" and g["group"]["steps"][0]["name"] == "join_port_range"
    assert g["bo_group_id"] == g["group"]["bo_group_id"]


def test_struct_effect_needs_block_in_bundle(tmp_path):
    atoms = [a for a in ATOMS if not a["atom_id"].endswith("deny.protocol")]
    b = BU.load(_write_bundle(tmp_path / "nodeny", atoms=atoms))
    recs, _ = GN.generate(b)
    rows = _by(recs, "google:google_compute_firewall:priority", "azurerm:azurerm_network_security_rule:priority")
    assert len(rows) == 1 and {"term": "subject.allow", "op": "present", "value": True} in rows[0]["guard"]["all"]
    assert VF.check_bundle_only(recs, b) == []


def test_exhaustive_orientation_and_roundtrip(synth):
    recs, _ = GN.generate(synth)
    assert VF.check_exhaustive(recs, synth) == []
    assert VF.check_orientation(recs) == []
    assert VF.check_bundle_only(recs, synth) == []
    assert VF.check_registry(recs) == []
    text = CS.write_tsv(recs, MAPPING_SET_ID, PREFIXES)
    _, back, _ = CS.read_tsv(text)
    assert back == recs
    for r in recs:
        if r["object_id"] == NO_TERM:
            assert r["semantic_relation"] == "related" and r["transport_fidelity"] == "none"
            assert "translation_fn" not in r and r["absence"]["searched"]


def test_deterministic(synth):
    a, _ = GN.generate(synth)
    b, _ = GN.generate(synth)
    assert CS.write_tsv(a, MAPPING_SET_ID, PREFIXES) == CS.write_tsv(b, MAPPING_SET_ID, PREFIXES)


def test_validator_accepts(synth, tmp_path):
    from bo.contracts import catalog as CCAT
    from bo.contracts import validate as CVAL
    recs, _ = GN.generate(synth)
    f = tmp_path / "m.sssom.tsv"
    f.write_text(CS.write_tsv(recs, MAPPING_SET_ID, PREFIXES), encoding="utf-8")
    sch = CCAT.schemas()
    fk = next(x for x in CCAT.file_kinds(sch) if x.cid == "C09" and x.kind == "correspondences")
    assert CVAL.validate_file(fk, f, sch).errors == []


def test_no_inflation_without_sentence(synth):
    recs, _ = GN.generate(synth)
    for r in recs:
        if r["evidence_state"] == "DOC_SUPPORTED":
            assert r["proof"]["evidence"], r["claim_id"]
        assert r["evidence_state"] in ("DOC_SUPPORTED", "STRUCTURALLY_VALID")


@pytest.mark.skipif(not (default_bundle() / "bundle.json").exists() and not (default_bundle() / "MANIFEST.sha256").exists(),
                    reason="pacote oficial do PILOT-NET-GLOSS ausente")
def test_official_bundle_exhaustive():
    b = BU.load(default_bundle())
    recs, _ = GN.generate(b)
    assert VF.check_exhaustive(recs, b) == []
    assert VF.check_orientation(recs) == []
    assert VF.check_bundle_only(recs, b) == []
    assert {r["claim_id"].split("-")[1] for r in recs} == set(PAIRS)
