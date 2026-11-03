"""Verificadores que o DECOMPOSE chama (coverage, permutation, relations) pelo caminho real: átomos C01 +
evidência C25 em arquivo → decomposição → C19, e o caminho de fixtures com os controles quebrados."""

import json
import os
import subprocess
import sys

import pytest

from bo.grain import battery as B
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.evidence import C25Adapter

RS = R.load()
WORLDS = ("bucket", "nic", "firewall", "iam")


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    d = tmp_path_factory.mktemp("decompose_inputs")
    recs, units, atoms_c19 = [], [], []
    for name in WORLDS:
        w = B.all_worlds()[name]
        atoms = S.atoms_from_tf_schema(w["provider"], w["schema"])
        sd = d / f"SCHEMA-{name}"
        sd.mkdir()
        (sd / "atoms.jsonl").write_text("".join(json.dumps(a) + "\n" for a in atoms))
        r, extra = B.to_c25(w)
        assert not extra or name == "bucket"  # grupos de atributos só no contêiner
        recs += r
        res = S.decompose_schema(S.candidates_from_atoms(atoms), C25Adapter(r, extra), RS)
        u, a = S.to_c19(res)
        units += u
        atoms_c19 += a
    (d / "service_evidence.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    (d / "canonical_units.jsonl").write_text("".join(json.dumps(u) + "\n" for u in units))
    (d / "canonical_atoms.jsonl").write_text("".join(json.dumps(a) + "\n" for a in atoms_c19))
    return d


def _run(*args):
    return subprocess.run([sys.executable, "-I", "-m", *args], capture_output=True, text=True, env=dict(os.environ))


def test_inputs_validate_against_contracts(inputs):
    for kind, f in (("C25", "service_evidence.jsonl"), ("C19", "canonical_units.jsonl"),
                    ("C19", "canonical_atoms.jsonl")):
        r = _run("bo.contracts.validate", kind, str(inputs / f))
        assert r.returncode == 0, r.stdout + r.stderr
    r = _run("bo.contracts.validate", "C01", *[str(p) for p in sorted(inputs.glob("SCHEMA-*/atoms.jsonl"))])
    assert r.returncode == 0, r.stdout + r.stderr


def test_coverage_on_files(inputs):
    r = _run("bo.grain.coverage", "--schema-atoms", str(inputs / "SCHEMA-*" / "atoms.jsonl"),
             "--units", str(inputs / "canonical_units.jsonl"), "--atoms", str(inputs / "canonical_atoms.jsonl"))
    assert r.returncode == 0, r.stdout + r.stderr


def test_permutation_on_files(inputs):
    r = _run("bo.grain.permutation", "--rename", "--schema-atoms", str(inputs / "SCHEMA-*" / "atoms.jsonl"),
             "--evidence", str(inputs / "service_evidence.jsonl"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "28 execução(ões)" in r.stdout  # 24 ordens dos 4 provedores + 1 renomeação por provedor


def test_relations_on_files(inputs):
    r = _run("bo.grain.relations", "--schema-atoms", str(inputs / "SCHEMA-*" / "atoms.jsonl"),
             "--evidence", str(inputs / "service_evidence.jsonl"), "--units", str(inputs / "canonical_units.jsonl"),
             "--atoms", str(inputs / "canonical_atoms.jsonl"))
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("mod", ["bo.grain.coverage", "bo.grain.relations"])
def test_checkers_fixtures(mod):
    r = _run(mod, "--fixtures")
    assert r.returncode == 0, r.stdout + r.stderr


def test_permutation_fixtures_with_control():
    r = _run("bo.grain.permutation", "--fixtures", "--rename")
    assert r.returncode == 0, r.stdout + r.stderr


def test_missing_inputs_exit_2(tmp_path):
    r = _run("bo.grain.coverage", "--schema-atoms", str(tmp_path / "nada" / "atoms.jsonl"))
    assert r.returncode == 2
