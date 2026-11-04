"""Testes do PILOT-STO-GLOSS: o gate anchor_claims (com controles que têm de reprovar) e o diagnóstico.

Fixtures sintéticas: provedores provider_a/provider_b, documentação fixture em example-org; nada de provedor real.
"""

import copy
import json

import pytest

from bo.pilot_sto_gloss import anchor_claims as A
from bo.pilot_sto_gloss import common as C
from bo.pilot_sto_gloss import build as B
from bo.pilot_sto_gloss import decompose as DEC
from bo.pilot_sto_gloss import diagnose as D
from bo.pilot_sto_gloss import spec as SP

T = "2026-11-04T02:00:00-03:00"


def _src(f):
    return {"repo": "example-org/provider-docs", "tag": "v1.0.0", "file": f, "line": 3,
            "sentence": "frase sintética de documentação que sustenta o fato"}


def _unit(prov, rt):
    ev = [{"level": "published", "doc": _src(f"docs/{rt}.md")}]
    return {"unit_id": f"CU-{prov}-{rt}", "provider": "aws" if prov == "pa" else "google", "kind": "ENTITY",
            "layers": {"terraform": {"resource_type": rt}, "domain_unit": "contêiner sintético"},
            "identity": {"evidence": ev, "key_fields": ["name"], "anonymous": False, "occurrence_key": []},
            "lifecycle_controller": {"kind": "self"}, "owner": {"kind": "self"}, "effective_scope": {"kind": "self"},
            "evidence": ev, "rule_applied": "GRAIN-G4-ENTITY", "missing_evidence": []}


def _claim(n, prov, atom, concept="concept:item_history_kept", state="STRUCTURALLY_VALID", with_source=True):
    c = {"claim_id": f"ANC-{prov}-{n}", "claim_version_id": f"ANC-{prov}-{n}@1", "event_id": f"EV-ANC-{prov}-{n}-1",
         "concept_id": concept, "atom_id": atom, "sentence": "frase sintética: guarda versões anteriores dos itens",
         "context": "seção de argumentos do tipo sintético",
         "counterexample_search": {"query": "history keep versions", "found": False, "result": "nenhum outro uso"},
         "extraction_method": "parser", "evidence_level": "published", "evidence_state": state, "recorded_at": T}
    if with_source:
        c["source"] = _src(f"docs/{prov}.md")
        c["evidence_ref"] = {"contract": "C03", "id": f"DF-fixture-{prov}-{n}"}
    else:
        del c["sentence"]
        c["context"] = "procurado nos fatos de documentação do tipo: o atributo não tem descrição própria"
        c["extraction_method"], c["evidence_level"] = "manual", "derived"
    return c


@pytest.fixture
def pkg(tmp_path):
    atoms = [{"atom_id": "pa:pa_box:keep_history", "unit_id": "CU-pa-pa_box", "path_in_unit": "keep_history"},
             {"atom_id": "pb:pb_store:history_on", "unit_id": "CU-pb-pb_store", "path_in_unit": "history_on"}]
    files = {
        "glossary.jsonl": [{"concept_id": "concept:item_history_kept", "label": "histórico de itens mantido",
                            "definition": "configuração booleana de um contêiner que mantém as versões anteriores",
                            "domain": "STO", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE",
                            "status": "active", "evidence_state": "STRUCTURALLY_VALID"}],
        "claims.jsonl": [_claim(1, "pa", atoms[0]["atom_id"]), _claim(1, "pb", atoms[1]["atom_id"])],
        "decisions.jsonl": [{"schema": "bo.glossary_decision/1", "decision_id": "GD-STO-0001", "kind": "value_type",
                             "concept_id": "concept:item_history_kept", "value": {"datatype": "boolean"},
                             "reason": "tipo de valor booleano do conceito", "evidence": [],
                             "author": C.MODULE, "recorded_at": T}],
        "canonical_atoms.jsonl": atoms,
        "canonical_units.jsonl": [_unit("pa", "pa_box"), _unit("pb", "pb_store")],
    }

    def write(fs):
        for name, recs in fs.items():
            (tmp_path / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
        return tmp_path

    return files, write


def test_valid_package_passes_and_counts_paths(pkg):
    files, write = pkg
    errs, st = A.check(write(files), validate=False)
    assert errs == []
    assert st["multi_provider_paths"] == 1 and st["paths_without_evidence"] == 0


def test_unresolved_anchor_without_sentence_is_hypothesis_not_error(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    f["claims.jsonl"][1] = _claim(1, "pb", "pb:pb_store:history_on", state="UNRESOLVED", with_source=False)
    f["glossary.jsonl"][0]["evidence_state"] = "UNRESOLVED"
    errs, st = A.check(write(f), validate=True)
    assert errs == [] and st["paths_without_evidence"] == 1 and st["paths_with_unresolved_anchor"] == 1


def test_anchor_without_sentence_above_unresolved_fails(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    bad = _claim(1, "pb", "pb:pb_store:history_on", state="UNRESOLVED", with_source=False)
    bad["evidence_state"] = "STRUCTURALLY_VALID"
    f["claims.jsonl"][1] = bad
    errs, _ = A.check(write(f), validate=False)
    assert any("sem sentença e fonte" in e for e in errs)
    assert any("acima de UNRESOLVED" in e for e in errs)


def test_sentence_without_evidence_ref_fails(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    del f["claims.jsonl"][0]["evidence_ref"]
    errs, _ = A.check(write(f), validate=False)
    assert any("C20-EVREF" in e for e in errs)


def test_doc_supported_written_by_glossarist_fails(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    f["claims.jsonl"][0]["evidence_state"] = "DOC_SUPPORTED"
    errs, _ = A.check(write(f), validate=False)
    assert any("não é do glossarista" in e for e in errs)


def test_concept_state_must_be_minimum_of_anchors(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    f["glossary.jsonl"][0]["evidence_state"] = "UNRESOLVED"
    errs, _ = A.check(write(f), validate=False)
    assert any("menor das âncoras" in e for e in errs)


def test_atom_outside_slice_and_model_extraction_fail(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    f["claims.jsonl"][0]["atom_id"] = "pa:pa_box:not_in_slice"
    f["claims.jsonl"][1]["extraction_method"] = "model"
    errs, _ = A.check(write(f), validate=False)
    assert any("fora da fatia" in e for e in errs)
    assert any("extração por modelo" in e for e in errs)


def test_missing_input_returns_2(tmp_path, capsys):
    assert A.main(["--dir", str(tmp_path)]) == 2
    assert "ENTRADA AUSENTE" in capsys.readouterr().out


def test_latest_version_wins():
    a = _claim(1, "pa", "pa:pa_box:keep_history", state="UNRESOLVED")
    b = dict(a, claim_version_id="ANC-pa-1@2", event_id="EV-ANC-pa-1-2", evidence_state="STRUCTURALLY_VALID")
    assert A.latest([b, a]) == [b]


def test_slice_is_provider_neutral_in_shape():
    st = C.slice_types()
    assert set(C.SLICE) == {"aws", "google", "azurerm", "oci"}
    assert all(st[t] == p for p, ts in C.SLICE.items() for t in ts)
    assert not set(st) & set(C.EXCLUDED)


def test_facet_rule_and_shape():
    assert D.facet_of("aws:aws_s3_bucket_versioning:versioning_configuration.status") == "versioning"
    assert D.facet_of("google:google_storage_bucket:encryption.default_kms_key_name") == "encryption"
    recs = [{"fact_kind": "owner", "status": "stated", "value": {"aspect": "parent"}},
            {"fact_kind": "identity", "status": "stated", "value": {"aspect": "id_template"}, "block_path": "x"},
            {"fact_kind": "owner", "status": "unknown", "value": None},
            {"fact_kind": "tag_support", "status": "stated", "value": {"aspect": "terraform_attribute"}}]
    s = D.shape(recs)
    assert (s["grain_fact_records"], s["stated"], s["with_block_path"]) == (3, 2, 1)
    assert s["stated_by_aspect"] == {"identity/id_template": 1, "owner/parent": 1}


def _with_slice(fn):
    old = C.SLICE
    try:
        C.SLICE = {"aws": {"a_bucket": "fixture"}}
        return fn()
    finally:
        C.SLICE = old


def _atom(path, blocks=()):
    return {"atom_id": f"aws:a_bucket:{path}", "provider": "aws", "resource_type": "a_bucket", "path": path,
            "block_path": [{"block": b, "nesting_mode": "single"} for b in blocks]}


def test_decompose_uses_library_and_decides_with_full_evidence():
    """Controle positivo: evidência completa na forma neutra do GRAIN dá ENTITY pela biblioteca."""
    ev = [
        {"provider": "aws", "terraform_resource_type": "a_bucket", "fact_kind": "identity", "status": "stated",
         "level": "published", "evidence_id": "SE-f-1", "api_resource": {"service": "s", "resource": "Bucket"},
         "value": {"status": "present", "scope": "independent", "key_fields": ["name"], "api_status": "resource",
                   "label": "contêiner"}},
        {"provider": "aws", "terraform_resource_type": "a_bucket", "fact_kind": "import_key", "status": "stated",
         "level": "published", "evidence_id": "SE-f-2", "value": {"status": "present", "fields": ["name"]}},
    ] + [{"provider": "aws", "terraform_resource_type": "a_bucket", "fact_kind": k, "status": "stated",
          "level": "published", "evidence_id": f"SE-f-{i}", "value": "self"}
         for i, k in enumerate(("lifecycle_controller", "owner", "effective_scope"), start=3)]
    roles = {"aws:a_bucket:name": {"role": "NAME"}}
    out = _with_slice(lambda: DEC.run(roles, ev, {"aws": [_atom("name")]}))
    assert out["report"]["aws"]["grains"] == {"ENTITY": 1}
    assert out["units"][0]["kind"] == "ENTITY" and out["atoms"][0]["unit_id"] == out["units"][0]["unit_id"]


def test_decompose_keeps_unknown_when_scope_missing():
    """Controle negativo: sem o alcance efetivo, a biblioteca devolve UNKNOWN e o piloto não muda isso."""
    ev = [
        {"provider": "aws", "terraform_resource_type": "a_bucket", "fact_kind": "identity", "status": "stated",
         "level": "published", "evidence_id": "SE-f-1", "api_resource": {"service": "s", "resource": "Bucket"},
         "value": {"status": "present", "scope": "independent", "key_fields": ["name"], "api_status": "resource",
                   "label": "contêiner"}},
        {"provider": "aws", "terraform_resource_type": "a_bucket", "fact_kind": "import_key", "status": "stated",
         "level": "published", "evidence_id": "SE-f-2", "value": {"status": "present", "fields": ["name"]}},
    ] + [{"provider": "aws", "terraform_resource_type": "a_bucket", "fact_kind": k, "status": "stated",
          "level": "published", "evidence_id": f"SE-f-{i}", "value": "self"}
         for i, k in enumerate(("lifecycle_controller", "owner"), start=3)]
    roles = {"aws:a_bucket:name": {"role": "NAME"}, "aws:a_bucket:versioning.enabled": {"role": "CONFIG"}}
    atoms = [_atom("name"), _atom("versioning.enabled", ["versioning"])]
    out = _with_slice(lambda: DEC.run(roles, ev, {"aws": atoms}))
    r = out["report"]["aws"]
    top = r["top_level"]["a_bucket"]
    assert top["grain"] == "UNKNOWN" and "effective_scope" in top["missing"]
    assert set(r["grains"]) == {"UNKNOWN"}


def test_spec_is_provider_neutral_and_consistent():
    import re

    toks = ["aws", "amazon", "gcp", "google", "azure", "azurerm", "microsoft", "oci", "oracle", "ec2", "s3", "vpc",
            "vnet", "vcn", "arn", "ocid", "gke", "eks", "aks", "lambda", "dynamodb", "cosmosdb", "bigquery",
            "cloudwatch", "stackdriver", "nsg", "elb", "alb"]
    ids = [c[0] for c in SP.CONCEPTS]
    assert len(ids) == len(set(ids))
    for c in SP.CONCEPTS:
        for text in (c[0], c[1], c[2]):
            words = set(re.split(r"[^a-z0-9]+", text.lower()))
            assert not words & set(toks), (c[0], words & set(toks))
        assert all(m in ("SV", "UR", "UX") for _, m, _ in c[8])
        assert all(len(n) >= 15 for _, m, n in c[8] if m == "UX")
        assert c[2].count(" ") >= 6  # definição com gênero e diferença, não um rótulo
    atoms = [a for c in SP.CONCEPTS for a, _, _ in c[8]]
    assert len(atoms) == len(set(atoms))
    for a, b, _ in SP.HIERARCHY + SP.DISTINCT:
        assert a in ids and b in ids and a != b


def test_counterexample_search_is_recorded_even_without_hits():
    concept = SP.CONCEPTS[0]
    descs = {"aws:x_type:other": [{"source": {"sentence": "nothing related here"}}]}
    r = B.counterexample(concept, {}, descs)
    assert r["found"] is False and r["query"]
    descs2 = {"aws:x_type:other": [{"source": {"sentence": "the name of the bucket owner"}}]}
    r2 = B.counterexample(concept, {}, descs2)
    assert r2["found"] is True and "aws:x_type:other" in r2["result"]


def test_decisions_mark_single_provider_concepts_exclusive():
    claims = [{"concept_id": SP.CONCEPTS[0][0], "atom_id": "aws:t:a"},
              {"concept_id": SP.CONCEPTS[1][0], "atom_id": "aws:t:b"},
              {"concept_id": SP.CONCEPTS[1][0], "atom_id": "google:t:c"}]
    dec = B.build_decisions(claims)
    excl = {d["concept_id"] for d in dec if d["kind"] == "exclusive"}
    assert SP.CONCEPTS[0][0] in excl and SP.CONCEPTS[1][0] not in excl
    assert sum(d["kind"] == "value_type" for d in dec) == len(SP.CONCEPTS)
    assert len({d["decision_id"] for d in dec}) == len(dec)


def test_valid_package_passes_official_validator(pkg):
    files, write = pkg
    errs, _ = A.check(write(files), validate=True)
    assert errs == []


def test_official_validator_rejects_broken_glossary(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    f["glossary.jsonl"][0]["quantity_kind"] = "Time"  # não é IRI QUDT nem NOT_APPLICABLE/UNKNOWN
    errs, _ = A.check(write(f), validate=True)
    assert any("validador oficial" in e for e in errs)


def test_packaging_invariance_counts_only_decided_equal_grains():
    u = lambda uid, k: {"unit_id": uid, "kind": k, "rule_applied": "R-X"}  # noqa: E731
    units = [u("CU-aws-aws_s3_bucket.versioning", "FACET"), u("CU-aws-aws_s3_bucket_versioning", "FACET"),
             u("CU-aws-aws_s3_bucket.lifecycle_rule", "COMPONENT"),
             u("CU-aws-aws_s3_bucket_lifecycle_configuration.rule", "UNKNOWN"),
             u("CU-aws-aws_s3_bucket.grant", "UNKNOWN"), u("CU-aws-aws_s3_bucket_acl.access_control_policy.grant", "UNKNOWN")]
    r = D.packaging(units)
    got = {x["inline"]: x["invariant"] for x in r["rows"]}
    assert got["aws_s3_bucket.versioning"] is True
    assert got["aws_s3_bucket.lifecycle_rule"] is False
    assert got["aws_s3_bucket.grant"] is False  # UNKNOWN == UNKNOWN não é invariância


def test_promote_refuses_without_own_lock(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BO_DATA", str(tmp_path))
    (tmp_path / "locks" / "merge-base").mkdir(parents=True)
    (tmp_path / "locks" / "merge-base" / "owner").write_text("owner=OUTRO\npid=1\n")
    assert B.promote() == 2
    assert "RECUSADO" in capsys.readouterr().out


def test_target_dir_prefers_pending_staging(tmp_path, monkeypatch):
    monkeypatch.setenv("BO_DATA", str(tmp_path))
    assert B.target_dir() == tmp_path / C.MODULE
    (tmp_path / C.MODULE / ".staging").mkdir(parents=True)
    (tmp_path / C.MODULE / ".staging" / "glossary.jsonl").write_text("")
    assert B.target_dir() == tmp_path / C.MODULE / ".staging"
