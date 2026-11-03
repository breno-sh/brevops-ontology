"""bo.schema_azure: cadeia de confiança, passada write_only, pino e as saídas publicadas do SCHEMA-AZURE."""
import gzip
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "SCHEMA-AZURE"))
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

from bo.contracts import validate as V  # noqa: E402
from bo.schema import build as libbuild  # noqa: E402
from bo.schema import core  # noqa: E402
from bo.schema_azure import atoms, common, signed  # noqa: E402

ADDR = "registry.terraform.io/hashicorp/azurerm"


@pytest.fixture
def work():
    d = Path(os.environ["BO_TMP"]) / "pytest"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ SHA256SUMS e GPG

def test_parse_shasums_and_zh():
    a, b, m = "a" * 64, "b" * 64, "c" * 64
    text = (f"{a}  terraform-provider-azurerm_1.0.0_linux_amd64.zip\n"
            f"{b}  terraform-provider-azurerm_1.0.0_darwin_arm64.zip\n"
            f"{m}  terraform-provider-azurerm_1.0.0_manifest.json\n")
    sums = signed.parse_shasums(text)
    assert len(sums) == 3
    # o manifest.json não é pacote: fica fora dos zh
    assert signed.zh_hashes(sums, "azurerm", "1.0.0") == [f"zh:{a}", f"zh:{b}"]


@pytest.mark.parametrize("bad", ["xyz  arquivo.zip\n", f"{'a' * 64}\n",
                                 f"{'a' * 64}  x.zip\n{'b' * 64}  x.zip\n", f"{'A' * 64}  x.zip\n"])
def test_parse_shasums_rejects(bad):
    with pytest.raises(signed.TrustError):
        signed.parse_shasums(bad)


def test_parse_gpg_status_reads_validsig_without_uid():
    fpr = common.HASHICORP_FPR
    status = ("[GNUPG:] NEWSIG\n[GNUPG:] EXPKEYSIG C820C6D5CD27AB87 Nome <x@example.com>\n"
              f"[GNUPG:] VALIDSIG 374EC75B485913604A831CC7C820C6D5CD27AB87 2026-10-29 1793285331 0 4 0 1 8 00 {fpr}\n")
    st = signed.parse_gpg_status(status)
    assert st["validsig"] == "374EC75B485913604A831CC7C820C6D5CD27AB87"
    assert st["primary_fpr"] == fpr and st["expkeysig"] and not st["badsig"]
    assert "example.com" not in json.dumps(st)


def test_parse_gpg_status_badsig():
    st = signed.parse_gpg_status("[GNUPG:] BADSIG ABCDEF Nome\n")
    assert st["badsig"] and st["validsig"] is None


# ------------------------------------------------------------------ h1 e desempacotamento

def _zip(path: Path, members: dict) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zi = zipfile.ZipInfo(name)
            zi.external_attr = 0o755 << 16
            zf.writestr(zi, data)
    return path


def test_h1_zip_equals_dir_and_known_value(work):
    zp = _zip(work / "p.zip", {"terraform-provider-x_v1": b"bin", "LICENSE.txt": b"lic"})
    dest = work / "cache" / "x"
    dest.parent.mkdir()
    un = signed.unpack(zp, dest)
    with zipfile.ZipFile(zp) as zf:
        assert signed.zip_h1(zf) == un["h1"] == signed.dirhash_h1(dest)
    # h1 = base64(sha256("<sha>  LICENSE.txt\n<sha>  terraform-provider-x_v1\n")), conta feita à mão
    lines = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in
                    sorted({"LICENSE.txt": b"lic", "terraform-provider-x_v1": b"bin"}.items()))
    import base64
    assert un["h1"] == "h1:" + base64.b64encode(hashlib.sha256(lines.encode()).digest()).decode()
    assert un["files"]["terraform-provider-x_v1"]["mode"] == "0o755"
    # segunda vez: pasta já existe com o mesmo h1, não reprova
    assert signed.unpack(zp, dest)["h1"] == un["h1"]


def test_unpack_rejects_traversal_and_tampered_dest(work):
    bad = _zip(work / "bad.zip", {"../fora": b"x"})
    with pytest.raises(signed.TrustError):
        signed.unpack(bad, work / "d1")
    ok = _zip(work / "ok.zip", {"a": b"1"})
    d2 = work / "d2"
    d2.mkdir()
    (d2 / "a").write_bytes(b"adulterado")
    with pytest.raises(signed.TrustError):
        signed.unpack(ok, d2)


# ------------------------------------------------------------------ write_only (C01 2.1.0)

def _schema(wo_flags: dict) -> dict:
    blk = {"attributes": {"name": {"type": "string", "required": True},
                          "value_wo": {"type": "string", "optional": True, **wo_flags},
                          "id": {"type": "string", "computed": True}},
           "block_types": {"conn": {"nesting_mode": "list", "max_items": 1,
                                    "block": {"attributes": {"secret_wo": {"type": "string", "optional": True,
                                                                           "write_only": True}}}}}}
    return {"format_version": "1.0", "provider_schemas": {ADDR: {"resource_schemas": {
        "azurerm_exemplo": {"version": 0, "block": blk}}, "data_source_schemas": {}}}}


def _write_gz(path: Path, doc: dict) -> Path:
    with gzip.open(path, "wb") as f:
        f.write(json.dumps(doc).encode())
    return path


def test_write_only_only_where_marked_and_rest_untouched(work):
    gz = _write_gz(work / "schema.json.gz", _schema({"write_only": True, "sensitive": True}))
    r = atoms.make(gz, "9.9.9", work / "atoms.jsonl", work / "types.jsonl")
    got = {json.loads(x)["path"]: json.loads(x) for x in (work / "atoms.jsonl").read_text().splitlines()}
    assert r["write_only"] == 2
    assert sorted(p for p, a in got.items() if a.get("write_only")) == ["conn.secret_wo", "value_wo"]
    assert all("write_only" not in a for p, a in got.items() if p not in ("value_wo", "conn.secret_wo"))
    # tirando write_only, cada átomo é byte a byte o da biblioteca
    libbuild.build(gz, "azurerm", "9.9.9", work / "lib_a.jsonl", work / "lib_t.jsonl")
    lib = [json.loads(x) for x in (work / "lib_a.jsonl").read_text().splitlines()]
    ours = [json.loads(x) for x in (work / "atoms.jsonl").read_text().splitlines()]
    assert [{k: v for k, v in a.items() if k != "write_only"} for a in ours] == lib
    assert (work / "types.jsonl").read_bytes() == (work / "lib_t.jsonl").read_bytes()
    assert V.validate("C01_atoms", work / "atoms.jsonl").ok
    assert V.validate("C02_types", work / "types.jsonl").ok


def test_write_only_rule_violation_raises(work):
    gz = _write_gz(work / "schema.json.gz", _schema({"write_only": True, "computed": True}))
    with pytest.raises(core.SchemaError, match="C01-WRITEONLY"):
        atoms.make(gz, "9.9.9", work / "atoms.jsonl", work / "types.jsonl")


# ------------------------------------------------------------------ pino

def test_read_pin_from_pins(work):
    p = work / "pins.json"
    p.write_text(json.dumps({"terraform": {"version": "1.2.3"}, "providers": [
        {"provider": "azurerm", "source": ADDR, "version": "5.0.0", "shasums_sha256": "s", "schema_sha256": "t"}]}))
    pin = common.read_pin(p)
    assert (pin.version, pin.terraform_version, pin.shasums_sha256) == ("5.0.0", "1.2.3", "s")
    p.write_text(json.dumps({"terraform": {"version": "1"}, "providers": [
        {"provider": "azurerm", "source": "registry.terraform.io/outro/azurerm", "version": "5.0.0",
         "shasums_sha256": "s", "schema_sha256": "t"}]}))
    with pytest.raises(SystemExit):
        common.read_pin(p)


def test_zip_url_is_official_host():
    assert common.zip_url("5.12.0", "darwin_arm64") == (
        "https://releases.hashicorp.com/terraform-provider-azurerm/5.12.0/"
        "terraform-provider-azurerm_5.12.0_darwin_arm64.zip")


# ------------------------------------------------------------------ saídas publicadas

OUT = common.out_dir()
need_out = pytest.mark.skipif(not (OUT / "build_report.json").exists(), reason="pipeline ainda não rodou")


@need_out
def test_published_counts_match_schema():
    pin = common.read_pin()
    gz = common.tfschema_dir(pin.version) / "schema.json.gz"
    ps = core.providers(core.load(gz))["azurerm"]
    types = [json.loads(x) for x in (OUT / "types.jsonl").read_text().splitlines()]
    assert len(types) == len(ps["resource_schemas"])
    assert {t["provider_version"] for t in types} == {pin.version}
    n_atoms = sum(1 for _ in open(OUT / "atoms.jsonl"))
    assert n_atoms == sum(t["counts"]["attributes"] for t in types)


@need_out
def test_published_write_only_equals_raw_schema():
    pin = common.read_pin()
    gz = common.tfschema_dir(pin.version) / "schema.json.gz"
    ps = core.providers(core.load(gz))["azurerm"]
    raw = set()

    def walk(rt, b, p):
        for n, a in (b.get("attributes") or {}).items():
            if a.get("write_only"):
                raw.add(f"azurerm:{rt}:{p}{n}")
        for n, bt in (b.get("block_types") or {}).items():
            walk(rt, bt.get("block") or {}, f"{p}{n}.")
    for rt, s in ps["resource_schemas"].items():
        walk(rt, s["block"], "")
    pub = {a["atom_id"] for a in map(json.loads, open(OUT / "atoms.jsonl")) if a.get("write_only")}
    assert pub == raw and raw


@need_out
def test_manifest_and_pin_consistent():
    pin = common.read_pin()
    assert (OUT / "schema.json.sha256").read_text().split()[0] == pin.schema_sha256
    pd = json.loads((common.plugin_cache_dir() / "provider.json").read_text())
    assert pd["version"] == pin.version and pd["schema_json_sha256"] == pin.schema_sha256
    assert pd["shasums"]["sha256"] == pin.shasums_sha256
    assert pd["gpg"]["primary_fpr"] == common.HASHICORP_FPR
    lock = (common.plugin_cache_dir() / "terraform.lock.hcl").read_text()
    assert pd["h1"] in lock and f'version     = "{pin.version}"' in lock
    rows = [ln.split("  ", 1) for ln in (OUT / "MANIFEST.sha256").read_text().splitlines()]
    assert {"atoms.jsonl", "types.jsonl", "plugin_cache/provider.json"} <= {r[1] for r in rows}
    for sha, rel in rows:
        p = Path(rel.replace("$BO_DATA", str(common.bo_data()))) if rel.startswith("$") else OUT / rel
        if p.stat().st_size < 50_000_000:       # o binário (~200 MB) é conferido pelo gate com shasum -c
            assert common.sha256_file(p) == sha, rel
