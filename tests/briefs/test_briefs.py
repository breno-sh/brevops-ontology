"""Testes do BRIEFS: exemplos executados, lint (com mutações que têm de reprovar), listas de leitura e regeneração."""
import copy
import json
import re
import shutil
from pathlib import Path

import pytest

from bo.briefs import allowlists as AL
from bo.briefs import common, content, lint
from bo.briefs import examples as E

BDIR = common.briefs_dir()


def _copy(tmp_name):
    d = common.tmp_dir() / "tests" / tmp_name
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(BDIR, d)
    return d


# ---------------------------------------------------------------- exemplos
def test_examples_behave_as_stated():
    rep = E.check()
    assert rep["problems"] == []
    assert {c["key"]: c["got"]["verdict"] for c in rep["cases"]}["REFUTED_V2"] == "REFUTED_BY_RULE"
    assert rep["broad_inverse"]["predicate_id"] == "skos:narrowMatch"
    assert rep["broad_roundtrip_values"]["A_B_A"] == ["g_low", "g_top"]


def test_example_files_pass_contract_validator():
    rep = E.validate_files(common.tmp_dir() / "tests" / "ex")
    assert all(v["rc"] == 0 for v in rep.values()), rep


def test_examples_are_synthetic():
    for rec in E.GOOD_ROWS + [r for _, r, *_ in E.CASES]:
        assert not lint._vocab_hits(json.dumps(rec)), rec["claim_id"]


# ---------------------------------------------------------------- lint
def test_lint_passes_on_frozen_briefs():
    assert lint.lint_dir(BDIR)["problems"] == []


MUTATIONS = {
    "sem value_domain_relation": ("MAPPER_BRIEF.txt", lambda t: t.replace("value_domain_relation", "vdr")),
    "direção SKOS invertida": ("GLOSSARY_BRIEF.txt", lambda t: t.replace("b é o mais amplo", "a é o mais amplo")),
    "caminho de avaliação": ("AUDITOR_BRIEF.txt", lambda t: t + "\nleia $BO_DATA/SPLIT/sealed/x\n"),
    "veredito digitado errado": ("MAPPER_BRIEF.txt",
                                 lambda t: t.replace("veredito REFUTED_BY_RULE", "veredito OK", 1)),
    "vocabulário real no exemplo": ("NONEHUNT_BRIEF.txt",
                                    lambda t: t.replace("pa:pa_widget:spin_rate", "pa:aws_s3_bucket:spin_rate", 1)),
    "sem proibidos do papel": ("VALIDATOR_BRIEF.txt",
                               lambda t: re.sub(r"(Do seu papel:\n)(?:- [^\n]*\n(?:  [^\n]*\n)*)+", r"\1(nada)\n", t)),
    "lista de leitura divergente": ("MAPPER_BRIEF.txt", lambda t: t.replace("  $WT/transforms/ ", "  $WT/outra/ ", 1)),
    "sem UNPROVEN": ("AUDITOR_BRIEF.txt", lambda t: t.replace("UNPROVEN", "não provado")),
    "sem alegação auditada": ("GLOSSARY_BRIEF.txt", lambda t: t.replace("ALEGAÇÃO", "afirmação")),
    "sem bo.contracts.sssom": ("MAPPER_BRIEF.txt", lambda t: t.replace("bo.contracts.sssom", "bo.x.sssom")),
    "sem despachante": ("NONEHUNT_BRIEF.txt", lambda t: t.replace("despachante", "roteador")),
    "sem proibição de nuvem": ("VALIDATOR_BRIEF.txt", lambda t: t.replace("Nuvem", "N.").replace("nuvem", "n.")),
    "sem exemplo broad aceito": ("AUDITOR_BRIEF.txt",
                                 lambda t: t.replace("pb:pb_gadget:level skos:narrowMatch pa:pa_widget:grade", "x")),
    "marcador solto": ("GLOSSARY_BRIEF.txt", lambda t: t + "\n{{HUB}}\n"),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_lint_rejects_mutation(name):
    fname, fn = MUTATIONS[name]
    d = _copy("lint_" + str(abs(hash(name))))
    p = d / fname
    t = p.read_text(encoding="utf-8")
    t2 = fn(t)
    assert t2 != t, f"mutação nula: {name}"
    p.write_text(t2, encoding="utf-8")
    probs = lint.lint_dir(d)["problems"]
    assert any(x.startswith(fname) for x in probs), name


# ---------------------------------------------------------------- listas de leitura
def test_allowlists_literal_ok():
    doc = json.loads((BDIR / "read_allowlists.json").read_text(encoding="utf-8"))
    assert AL.literal_checks(doc) == []


@pytest.mark.parametrize("bad", ["$BO_DATA/SPLIT/", "$BO_DATA/", "$BO_DATA/SPLIT/sealed/a.jsonl",
                                 "$BO_DATA/UNSEAL/test_partition/", "$BO_DATA/SPL*/sealed", "$WT"])
def test_allowlists_reject_test_partition(bad):
    doc = json.loads((BDIR / "read_allowlists.json").read_text(encoding="utf-8"))
    doc["roles"]["mapper"]["read"].append(bad)
    assert AL.literal_checks(doc), bad


def test_allowlists_require_every_role():
    doc = json.loads((BDIR / "read_allowlists.json").read_text(encoding="utf-8"))
    del doc["roles"]["hunter"]
    assert any("hunter" in p for p in AL.literal_checks(doc))


def test_covers():
    assert AL.covers("$BO_DATA/SPLIT/", "$BO_DATA/SPLIT/sealed/")
    assert AL.covers("$BO_DATA/SPLIT/sealed/x", "$BO_DATA/SPLIT/sealed/")
    assert not AL.covers("$BO_DATA/SPLIT/training_projection/", "$BO_DATA/SPLIT/sealed/")
    assert not AL.covers("$BO_DATA/DOCS-*/docs_facts.jsonl", "$BO_DATA/SPLIT/sealed/")


def test_expansion_by_the_lane_itself():
    from bo.repo import catalog
    probs, seen = AL.expansion_checks(catalog.load())
    assert probs == []
    assert {v["role"] for v in seen.values()} == set(common.ROLES)


def test_lane_sandbox_denies_test_partition_for_mapper():
    """O mesmo cálculo que o bo-lane grava em .claude/settings.json nega a partição de teste a um mapeador."""
    from bo.repo import catalog, core, lane
    cat = catalog.load()
    mod = cat.get("MAP-AWSAZ-NET")
    wt = Path(mod.worktree)
    allowed, src = lane.allowlist(cat, mod, "mapper", wt)
    assert src == "briefs/read_allowlists.json"
    settings = lane.settings_for(allowed, lane.complement(allowed), [], wt)
    sealed = core.bo_data() / "SPLIT" / "sealed" / "x.jsonl"
    assert not lane.simulate(settings, sealed, wt)
    assert lane.simulate(settings, wt / "briefs" / "MAPPER_BRIEF.txt", wt)
    assert not lane.simulate(settings, core.bo_data() / "MAP-AWSGCP-NET" / "mapping.sssom.tsv", wt)


def test_read_lists_in_json_match_content():
    doc = json.loads((BDIR / "read_allowlists.json").read_text(encoding="utf-8"))
    for role in common.ROLES:
        assert doc["roles"][role]["read"] == content.ROLE_READ[role]


# ---------------------------------------------------------------- regeneração
def test_regeneration_identical():
    from bo.briefs import build
    assert build.check() == []


def test_decisions_reference_rule_rejects_unknown_concept():
    """C20-DEC-REF: decisão que cita conceito fora do glossary.jsonl irmão reprova (o exemplo completo passa)."""
    import subprocess, sys
    d = common.tmp_dir() / "tests" / "decref"
    E.validate_files(d)
    bad = copy.deepcopy(E.DECISION_BROADER)
    bad["related_concept"] = "concept:nao_existe"
    (d / "decisions.jsonl").write_text(common.canon(bad) + "\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "decisions", str(d / "decisions.jsonl")],
                        capture_output=True, text=True)
    assert cp.returncode != 0


def test_none_row_uses_absence_and_dispute_uses_disputes():
    assert E.NONE_ROW["absence"]["kind"] == "ABSENCE_DEMONSTRATED" and "curation_rule" not in E.NONE_ROW
    assert E.dispute_example()["disputes"] == [E.NONE_ROW["claim_id"]] and "see_also" not in E.dispute_example()


def test_unresolved_anchor_without_sentence_c20_330():
    """C20 3.3.0 (C20-UNRESOLVED): UNRESOLVED sem sentence passa com motivo no context; estado maior sem sentence reprova."""
    import subprocess, sys
    d = common.tmp_dir() / "tests" / "unres"
    E.validate_files(d)

    def run(rec):
        (d / "claims.jsonl").write_text(common.canon(rec) + "\n", encoding="utf-8")
        return subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "claims", str(d / "claims.jsonl")],
                              capture_output=True, text=True).returncode
    assert "sentence" not in E.ANCHOR_UNRESOLVED and len(E.ANCHOR_UNRESOLVED["context"]) >= 15
    assert run(E.ANCHOR_UNRESOLVED) == 0
    bad = copy.deepcopy(E.ANCHOR_UNRESOLVED)
    bad["evidence_state"] = "STRUCTURALLY_VALID"
    assert run(bad) != 0
