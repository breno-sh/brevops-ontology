"""Conferência das saídas publicadas do SCHEMA-AWS contra o schema extraído (pula se ainda não foram geradas)."""
import json
from collections import Counter

import pytest

from bo.schema import core
from bo.schema_aws import common, signed

OUT = common.out_dir()
pytestmark = pytest.mark.skipif(not (OUT / "build_report.json").exists(), reason="pipeline ainda não rodou")


@pytest.fixture(scope="module")
def pin():
    return common.read_pin()


@pytest.fixture(scope="module")
def ps(pin):
    return core.providers(core.load(common.tfschema_dir(pin.version) / "schema.json.gz"))["aws"]


@pytest.fixture(scope="module")
def types():
    return [json.loads(x) for x in open(OUT / "types.jsonl", encoding="utf-8")]


@pytest.fixture(scope="module")
def atom_summary():
    per_type, wo, versions, ids = Counter(), [], set(), set()
    dup = 0
    with open(OUT / "atoms.jsonl", encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            per_type[a["resource_type"]] += 1
            versions.add(a["provider_version"])
            dup += a["atom_id"] in ids
            ids.add(a["atom_id"])
            if "write_only" in a:
                wo.append(a)
    return {"per_type": per_type, "wo": wo, "versions": versions, "dup": dup, "n": len(ids)}


def test_tipos_sao_os_do_schema(types, ps, pin):
    assert [t["resource_type"] for t in types] == sorted(ps["resource_schemas"])
    assert {t["provider_version"] for t in types} == {pin.version}


def test_atomos_batem_com_contagem_dos_tipos(types, atom_summary, pin):
    assert atom_summary["dup"] == 0
    assert atom_summary["versions"] == {pin.version}
    assert {t["resource_type"]: t["counts"]["attributes"] for t in types if t["counts"]["attributes"]} == \
        dict(atom_summary["per_type"])


def test_write_only_igual_ao_schema(ps, atom_summary):
    want = set()

    def walk(b, t, p=()):
        for n, a in (b.get("attributes") or {}).items():
            if a.get("write_only"):
                want.add(f"aws:{t}:{'.'.join(p + (n,))}")
        for n, bt in (b.get("block_types") or {}).items():
            walk(bt.get("block") or {}, t, p + (n,))
    for t, s in ps["resource_schemas"].items():
        walk(s.get("block") or {}, t)
    got = {a["atom_id"] for a in atom_summary["wo"]}
    assert got == want
    assert all(a["write_only"] is True and a["configurable"] and not a["computed"] for a in atom_summary["wo"])


def test_block_sha256_confere(types, ps):
    for t in types[:: max(1, len(types) // 200)]:
        assert t["block_sha256"] == core.canonical_sha256(ps["resource_schemas"][t["resource_type"]]["block"])


def test_cache_h1_igual_ao_lock_da_prefetch(pin):
    """Âncora externa do h1: o lock que o terraform init da pré-busca gravou."""
    from bo.schema import lockfile
    pre = lockfile.find(lockfile.read(common.prefetch_dir(pin.version) / "terraform.lock.hcl"), pin.source)
    prov = json.loads((OUT / "plugin_cache" / "provider.json").read_text(encoding="utf-8"))
    bdir = common.shared_cache() / "registry.terraform.io" / "hashicorp" / "aws" / pin.version / prov["os_arch"]
    assert signed.dirhash_h1(bdir) == prov["h1"]
    assert prov["h1"] in pre.hashes


def test_lock_do_modulo_cobre_todas_as_plataformas_assinadas(pin):
    from bo.schema import lockfile
    lp = lockfile.find(lockfile.read(OUT / "plugin_cache" / "terraform.lock.hcl"), pin.source)
    pf = common.prefetch_dir(pin.version)
    sums = signed.parse_shasums((pf / f"terraform-provider-aws_{pin.version}_SHA256SUMS").read_text())
    assert lp.version == pin.version
    assert sorted(h for h in lp.hashes if h.startswith("zh:")) == signed.zh_hashes(sums, "aws", pin.version)
