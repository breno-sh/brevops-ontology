"""Os módulos de gate rodam com 'python -I -m' e saem 0; a regeneração é idêntica e o manifesto cobre as saídas."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("mod", ["audit", "scalar_kind", "duration_context", "guard_sat"])
def test_gate_module(mod):
    env = dict(os.environ, BO_REPO=str(ROOT))
    r = subprocess.run([sys.executable, "-I", "-B", "-m", f"bo.transforms.{mod}"], capture_output=True, text=True,
                       env=env, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_build_check():
    env = dict(os.environ, BO_REPO=str(ROOT))
    r = subprocess.run([sys.executable, "-I", "-B", "-m", "bo.transforms.build", "--check"], capture_output=True,
                       text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


def test_contract_validator_accepts_outputs():
    env = dict(os.environ, BO_REPO=str(ROOT))
    for kind, path in (("transforms", "transforms/transforms.yaml"),
                       ("conditions_grammar", "transforms/conditions.grammar.json")):
        r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", kind, path], capture_output=True,
                           text=True, env=env, cwd=ROOT)
        assert r.returncode == 0, r.stdout + r.stderr


def test_manifest_covers_outputs():
    lines = (ROOT / "results/TRANSFORMS/MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    paths = {ln.split("  ", 1)[1] for ln in lines}
    for need in ("transforms/transforms.yaml", "transforms/conditions.grammar.json", "gates/TRANSFORMS.sh",
                 "src/bo/transforms/registry.py", "src/bo/transforms/guards.py"):
        assert need in paths
