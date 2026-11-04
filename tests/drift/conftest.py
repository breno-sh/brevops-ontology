"""Fixtures do DRIFT: temporário em $BO_TMP (nunca /tmp) e um BO_DATA sintético com HIST-* e guias plantados."""
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "DRIFT"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)


def atom(provider, rt, path, tf_type="string", required=False, optional=True, computed=False, sensitive=False,
         deprecated=False, nesting="none", block_path=None, **extra):
    a = {"atom_id": f"{provider}:{rt}:{path}", "provider": provider, "resource_type": rt, "path": path,
         "tf_type": tf_type, "required": required, "optional": optional, "computed": computed,
         "configurable": required or optional, "sensitive": sensitive, "deprecated": deprecated,
         "nesting": nesting, "block_path": block_path or []}
    a.update(extra)
    return a


def write_hist(data: Path, module: str, provider: str, versions: dict, missing=()):
    """versions: {versão: [átomos]} em ordem; `missing`: versões listadas sem átomos (lacuna)."""
    d = data / module
    d.mkdir(parents=True, exist_ok=True)
    allv = list(versions) + list(missing)
    allv.sort(key=lambda v: tuple(int(x) for x in v.split(".")))
    doc = {"schema": "bo.versions/1", "contract": "C13", "contract_version": "3.1.0", "module": module,
           "generated_at": "2026-11-04T08:00:00-03:00", "provider": provider,
           "versions": [{"version": v, "released_at": f"2024-{i + 1:02d}-15"} for i, v in enumerate(allv)]}
    (d / "versions.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    lines = []
    for v, atoms in versions.items():
        raw = "".join(json.dumps(dict(a, provider_version=v), sort_keys=True) + "\n" for a in atoms).encode()
        gz = gzip.compress(raw, mtime=0)
        (d / f"atoms_{v}.jsonl.gz").write_bytes(gz)
        lines.append(f"{hashlib.sha256(gz).hexdigest()}  atoms_{v}.jsonl.gz")
    (d / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if missing:
        ext = {"versions": [{"version": v, "status": "unavailable", "reason": "sem build: HTTP 404"}
                            for v in missing]}
        (d / "extraction.json").write_text(json.dumps(ext), encoding="utf-8")


def write_guide(data: Path, rel_dir: str, name: str, text: str):
    d = data / rel_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


@pytest.fixture
def work(request):
    d = Path(os.environ["BO_TMP"]) / "pytest" / request.node.name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
