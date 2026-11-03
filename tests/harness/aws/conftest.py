"""Fixtures comuns do HARNESS-AWS: BO_TMP do módulo (nunca /tmp), render dos planos de fixture e o schema fixado."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "HARNESS-AWS"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
os.environ.setdefault("BO_REPO", str(Path(__file__).resolve().parents[3]))
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

FX = Path(__file__).resolve().parent / "fixtures"
PLANS = FX / "plans" / "lowering_plan.jsonl"


@pytest.fixture
def work(request):
    """Diretório de trabalho exclusivo sob $BO_TMP (o tmp_path do pytest cairia em /private/var ou /tmp)."""
    import re
    import shutil
    d = Path(os.environ["BO_TMP"]) / "pytest" / re.sub(r"[^A-Za-z0-9_]+", "_", request.node.name)[:80]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="session")
def schema():
    from bo.harness.aws import schema as sch
    return sch.load_pinned()


@pytest.fixture(scope="session")
def rendered():
    """Render dos planos de fixture, uma vez por sessão (somente leitura nos testes)."""
    from bo.harness.aws import render
    out = Path(os.environ["BO_TMP"]) / "pytest-session-render"
    man = render.render_file(PLANS, out)
    return out, man
