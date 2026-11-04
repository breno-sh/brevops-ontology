"""Fixtures do SAFETY: tudo em $BO_TMP/pytest (nunca /tmp), canal privado e travas isolados por teste."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from bo.safety import common, identity

SUB_ID = "00000000-0000-4000-8000-" + "0" * 11 + "1"  # GUID sintético (montado: sem 12 dígitos literais)


@pytest.fixture
def work(request, monkeypatch) -> Path:
    base = common.bo_tmp() / "pytest" / (request.node.name[:60].replace("[", "_").replace("]", "_")
                                         + "-" + uuid.uuid4().hex[:6])
    base.mkdir(parents=True)
    monkeypatch.setenv("BO_PRIVATE_DIR", str(base / "private"))
    monkeypatch.setenv("BO_LOCKS_DIR", str(base / "locks"))
    monkeypatch.delenv("BO_CLOUD_GO", raising=False)
    yield base
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def allowlist(work, monkeypatch):
    """Allowlist privada sintética (600) com uma identidade por provedor."""
    p = work / "cfg" / "allowlist"
    p.parent.mkdir()
    ids = {"aws": "aws|account=" + "1" * 6 + "2" * 6, "google": "google|project=bo-sandbox|account=dev@example.com",
           "azurerm": "azurerm|subscription=" + SUB_ID + "|tenant=t-sintetico",
           "oci": "oci|tenancy=ten-sintetico|user=usr-sintetico"}
    p.write_text("# allowlist sintética de teste\n" + "".join(
        f"{k} sha256:{identity.identity_hash(v)} sandbox\n" for k, v in ids.items()))
    os.chmod(p, 0o600)
    monkeypatch.setenv("BO_ALLOWLIST", str(p))
    return {"path": p, "ids": ids}
