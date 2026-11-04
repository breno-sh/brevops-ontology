"""Testes do oráculo NET: rodam só com a biblioteca padrão e os arquivos públicos do piloto."""
import json
import os
import sys
from pathlib import Path

import pytest

ORACLE = Path(__file__).resolve().parents[1]
NETDIR = ORACLE.parent
REPO = Path(os.environ.get("BO_REPO") or ORACLE.parents[2])
DATA = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))
sys.path.insert(0, str(ORACLE))


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def calib():
    fx = {d["fixture_id"]: d for d in (load(p) for p in sorted((NETDIR / "fixtures_calib").glob("*.json")))}
    tr = [load(p) for p in sorted((NETDIR / "fixtures_calib/translations").glob("*.json"))]
    return fx, tr
