"""Saídas publicadas do SCHEMA-OCI conferidas contra o PINS, o schema extraído e o pino do binário."""
import gzip
import hashlib
import json

import pytest

from bo.schema import core, lockfile
from bo.schema_oci import atoms, common, manifest

OUT = common.out_dir()


def _jsonl(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def pin():
    return common.read_pin()


@pytest.fixture(scope="module")
def ps(pin):
    return core.providers(core.load(common.tfschema_dir(pin.version) / "schema.json.gz"))["oci"]


def test_schema_extraido_e_o_do_pins_e_o_da_pre_busca(pin):
    gz = common.tfschema_dir(pin.version) / "schema.json.gz"
    with gzip.open(gz, "rb") as f:
        raw = hashlib.sha256(f.read()).hexdigest()
    assert raw == pin.schema_sha256
    assert (OUT / "schema.json.sha256").read_text(encoding="utf-8").split()[0] == raw
    assert common.sha256_file(common.prefetch_dir(pin.version) / "providers-schema.json") == raw


def test_atomos_e_tipos_cobrem_o_schema(pin, ps):
    at, ty = _jsonl(OUT / "atoms.jsonl"), _jsonl(OUT / "types.jsonl")
    assert len(ty) == len(ps["resource_schemas"])
    assert len(at) == atoms.count_schema_attributes(ps)
    assert {a["provider_version"] for a in at} == {t["provider_version"] for t in ty} == {pin.version}
    assert {t["resource_type"] for t in ty} == set(ps["resource_schemas"])
    per = {}
    for a in at:
        per[a["resource_type"]] = per.get(a["resource_type"], 0) + 1
    assert all(per.get(t["resource_type"], 0) == t["counts"]["attributes"] for t in ty)


def test_write_only_bate_com_o_schema(ps):
    def walk(b):
        n = sum(bool(a.get("write_only")) for a in (b.get("attributes") or {}).values())
        return n + sum(walk(bt.get("block") or {}) for bt in (b.get("block_types") or {}).values())
    want = sum(walk(s["block"]) for s in ps["resource_schemas"].values())
    assert sum(bool(a.get("write_only")) for a in _jsonl(OUT / "atoms.jsonl")) == want


def test_lock_e_pino_do_binario(pin):
    pc = common.plugin_cache_dir()
    lp = lockfile.find(lockfile.read(pc / "terraform.lock.hcl"), pin.source)
    pre = lockfile.find(lockfile.read(common.prefetch_dir(pin.version) / "terraform.lock.hcl"), pin.source)
    assert lp.version == pin.version
    assert {h for h in pre.hashes if h.startswith("h1:")} <= set(lp.hashes)
    pd = json.loads((pc / "provider.json").read_text(encoding="utf-8"))
    b = common.unportable(pd["binary"]["path"])
    assert b.is_file() and common.sha256_file(b) == pd["binary"]["sha256"]
    assert pd["lock_sha256"] == common.sha256_file(pc / "terraform.lock.hcl")
    assert pd["gpg"]["primary_fpr"] == common.ORACLE_FPR
    assert f"zh:{pd['zip']['sha256']}" in lp.hashes
    assert str(common.shared_cache()) in (pc / "terraformrc").read_text(encoding="utf-8")


def test_relatorio_registra_crosscheck_sem_afrouxar(pin):
    br = json.loads((OUT / "build_report.json").read_text(encoding="utf-8"))
    cx = json.loads((OUT / f"crosscheck_oci-{pin.version}.json").read_text(encoding="utf-8"))
    assert br["crosscheck"]["veredito_da_biblioteca"] == cx["veredito"]
    assert br["crosscheck"]["tipos_sem_pagina"] == len(cx["tipos_sem_pagina"])
    assert br["crosscheck"]["paginas_sem_tipo"] == len(cx["paginas_sem_tipo"])
    assert br["offline_validate"]["veredito"] == "PASS"


def test_manifestos_conferem():
    assert manifest.verify(common.bo_repo()) == []
