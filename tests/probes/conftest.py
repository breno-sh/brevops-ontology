"""Fixtures do PROBEKIT: temporário em $BO_TMP/pytest (nunca /tmp), relógio simulado, supervisor de mentira."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from bo.probes import common, protocol
from probes_helpers import RECORDED  # noqa: F401

@pytest.fixture
def work(request) -> Path:
    base = common.tmp() / "pytest" / (request.node.name[:60].replace("[", "_").replace("]", "_") + "-"
                                      + uuid.uuid4().hex[:6])
    base.mkdir(parents=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture(scope="session")
def protos():
    return protocol.load()


@pytest.fixture
def recording():
    def load(name):
        return json.loads((RECORDED / name).read_text(encoding="utf-8"))
    return load


