"""Fixtures comuns do UNITS: BO_TMP do módulo (nunca /tmp) e construtores de átomo e fato sintéticos."""
import os
from collections import Counter
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "UNITS"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)


@pytest.fixture
def tmpdir_units():
    d = Path(os.environ["BO_TMP"]) / "pytest"
    d.mkdir(parents=True, exist_ok=True)
    return d


def atom(path, tf="number", rtype="aws_x", block_path=None, sib=()):
    return {"atom_id": f"aws:{rtype}:{path}", "path": path, "resource_type": rtype, "tf_type": tf,
            "block_path": block_path or [], "_sib": frozenset(sib)}


def fact(kind, value, sentence="", status="stated", level="published", fid=None, ur=None):
    return {"k": kind, "id": fid or f"DF-test-{kind}-{abs(hash((kind, str(value), sentence))) % 10**8}",
            "st": status, "lv": level, "v": value, "s": sentence, "ur": ur}


def build_record(a, fs=()):
    from bo.units import build
    return build.record(a, list(fs), Counter(), lambda text: False)
