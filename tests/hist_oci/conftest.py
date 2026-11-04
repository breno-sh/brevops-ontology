"""Fixtures do HIST-OCI: temporário em $BO_TMP (nunca /tmp), lista histórica e saídas sintéticas."""
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "HIST-OCI"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

from bo.hist_oci import common  # noqa: E402

PIN_SHA = "c" * 64
LT = {"at": "2021-01-01T00:00:00-03:00", "version_in_force": None, "major_in_force": None,
      "index_first_version": "1.0.0", "index_first_published_at": "2022-01-01T00:00:00Z"}


@pytest.fixture
def work(request):
    d = Path(os.environ["BO_TMP"]) / "pytest" / request.node.name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def listed(v, date, pub, sha=None):
    return common.Listed(v, date, pub, ("quarter_end:2022Q1",), "d" * 64, ("5.0",), True, sha)


def hist3():
    """Três versões: 1.0.0 (sem release), 1.1.0 e o pin 2.0.0."""
    vs = (listed("1.0.0", "2022-01-01", "2022-01-01T00:00:00Z"),
          listed("1.1.0", "2022-03-01", "2022-03-01T00:00:00Z"),
          listed("2.0.0", "2022-06-01", "2022-06-01T00:00:00Z", PIN_SHA))
    return common.History(common.ADDRESS, "2.0.0", vs, dict(LT), {"start": "2021-01-01", "rule": "r" * 10},
                          {"date": "2026-11-02"}, "e" * 64, "$BO_REPO/universe/history_versions.json")


def _atom(v, name):
    return {"atom_id": f"oci:oci_x:{name}", "block_path": [], "computed": False, "configurable": True,
            "deprecated": False, "nesting": "none", "optional": False, "path": name, "provider": "oci",
            "provider_version": v, "required": True, "resource_type": "oci_x", "sensitive": False,
            "tf_type": "string"}


def write_outputs(out: Path, schemas: Path, hist, schema_shas=None):
    """Saídas coerentes: 1.0.0 not_extracted com motivo; as outras extraídas, com schema e átomos."""
    out.mkdir(parents=True, exist_ok=True)
    vers, recs = [], []
    for lv in hist.versions:
        e = {"version": lv.version, "released_at": lv.released_at}
        if lv.version == "1.0.0":
            recs.append({"version": lv.version, "status": "not_extracted",
                         "motivo": "pacote assinado indisponível: release apagado na fonte oficial"})
            vers.append(e)
            continue
        raw = json.dumps({"format_version": "1.0", "v": lv.version}).encode()
        sha = (schema_shas or {}).get(lv.version) or lv.schema_sha256 or hashlib.sha256(raw).hexdigest()
        sd = schemas / f"oci-{lv.version}"
        sd.mkdir(parents=True, exist_ok=True)
        if lv.schema_sha256 and sha == lv.schema_sha256:
            raw = b"pin"                       # o sha do pin é sintético: o gz é conferido via monkeypatch
        with gzip.open(sd / "schema.json.gz", "wb") as g:
            g.write(raw)
        lines = "".join(json.dumps(_atom(lv.version, n), sort_keys=True) + "\n" for n in ("a", "b"))
        jp = out / f"atoms_{lv.version}.jsonl"
        jp.write_text(lines, encoding="utf-8")
        common.write_gz(jp, out / f"atoms_{lv.version}.jsonl.gz", jp.name)
        jp.unlink()
        e["schema_sha256"] = sha
        vers.append(e)
        recs.append({"version": lv.version, "status": "extracted", "schema_sha256": sha,
                     "atoms_gz_sha256": common.sha256_file(out / f"atoms_{lv.version}.jsonl.gz"),
                     "atoms_jsonl_sha256": hashlib.sha256(lines.encode()).hexdigest(), "atoms": 2,
                     "gpg_primary_fpr": common.ORACLE_FPR, "binarios_apagados": True})
    (out / "versions.json").write_text(json.dumps(
        {"schema": "bo.versions/1", "contract": "C13", "contract_version": "3.1.0", "module": "HIST-OCI",
         "generated_at": "2026-11-03T21:00:00-03:00", "provider": "oci", "versions": vers}), encoding="utf-8")
    (out / "extraction.json").write_text(json.dumps(
        {"versions": recs, "left_truncation": {**hist.left_truncation, "declarado": "truncamento declarado"}}),
        encoding="utf-8")
