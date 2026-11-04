"""Testes do PILOT-STO-GLOSS: o gate anchor_claims (com controles que têm de reprovar) e o diagnóstico.

Fixtures sintéticas: provedores provider_a/provider_b, documentação fixture em example-org; nada de provedor real.
"""

import copy
import json

import pytest

from bo.pilot_sto_gloss import anchor_claims as A
from bo.pilot_sto_gloss import common as C
from bo.pilot_sto_gloss import diagnose as D

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


def test_multi_provider_path_without_evidence_fails(pkg):
    files, write = pkg
    f = copy.deepcopy(files)
    f["claims.jsonl"][1] = _claim(1, "pb", "pb:pb_store:history_on", state="UNRESOLVED", with_source=False)
    f["glossary.jsonl"][0]["evidence_state"] = "UNRESOLVED"
    errs, st = A.check(write(f), validate=False)
    assert st["paths_without_evidence"] == 1
    assert any("sem evidência" in e for e in errs)


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


def test_atoms_from_roles_rebuilds_blocks_and_counts_collisions():
    roles = {"provider_a:a_bucket:name": {}, "provider_a:a_bucket:versioning.enabled": {},
             "provider_a:a_bucket:rule": {}, "provider_a:a_bucket:rule.days": {}}
    atoms = {a["atom_id"]: a for a in D.atoms_from_roles(roles)}
    assert [b["block"] for b in atoms["provider_a:a_bucket:versioning.enabled"]["block_path"]] == ["versioning"]
    assert atoms["provider_a:a_bucket:name"]["block_path"] == []
    assert D.prefix_collisions(roles) == 1  # rule é átomo e prefixo de rule.days


def test_shape_counts_grain_convention_vs_aspect():
    recs = [{"fact_kind": "owner", "status": "stated", "value": "parent"},
            {"fact_kind": "identity", "status": "stated", "value": {"status": "present", "key_fields": ["n"]}},
            {"fact_kind": "identity", "status": "stated", "value": {"aspect": "id_template", "template": "x"}},
            {"fact_kind": "owner", "status": "unknown", "value": None},
            {"fact_kind": "tag_support", "status": "stated", "value": {"aspect": "terraform_attribute"}}]
    s = D.shape(recs)
    assert (s["grain_fact_records"], s["stated"], s["stated_in_grain_convention"]) == (4, 3, 2)
    assert s["stated_by_aspect"] == {"identity/None": 1, "identity/id_template": 1}


def test_grain_library_as_is_on_aspect_form_raises_and_is_recorded():
    """Controle: o mesmo fato na forma por aspecto (a do SERVICE-EVIDENCE) faz a biblioteca levantar erro, e o
    diagnóstico registra o erro em vez de decidir unidade (nada de conserto local)."""
    roles = {"aws:a_bucket:name": {"role": "NAME"}}
    ev = [{"provider": "aws", "terraform_resource_type": "a_bucket", "fact_kind": "identity", "status": "stated",
           "level": "derived", "evidence_id": "SE-fixture-1", "value": {"aspect": "id_template", "template": "{name}"}}]
    old = C.SLICE
    try:
        C.SLICE = {"aws": {"a_bucket": "fixture"}}
        out = D.grain_as_is(roles, ev)
    finally:
        C.SLICE = old
    assert out["providers"]["aws"]["outcome"] == "EVIDENCE_ERROR"
    assert out["providers"]["aws"]["candidates_with_evidence_error"] == 1


def test_grain_library_as_is_on_grain_convention_decides():
    """Controle positivo: a mesma entidade na convenção do GRAIN.html é decidida (ENTITY) pela biblioteca."""
    roles = {"aws:a_bucket:name": {"role": "NAME"}}
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
    old = C.SLICE
    try:
        C.SLICE = {"aws": {"a_bucket": "fixture"}}
        out = D.grain_as_is(roles, ev)
    finally:
        C.SLICE = old
    p = out["providers"]["aws"]
    assert p["outcome"] == "DECIDED" and p["kinds"] == {"ENTITY": 1}


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
