"""bo.hist_azure: cadeia de confiança, átomos por versão, conferências do gate (lista, monotonia, cobertura,
binários) e as saídas publicadas do HIST-AZURE."""
import dataclasses
import gzip
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "HIST-AZURE"))
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

from bo.contracts import validate as V  # noqa: E402
from bo.schema import core  # noqa: E402
from bo.hist_azure import atoms, check, common, pipeline, signed  # noqa: E402

V5 = "5.12.0"


@pytest.fixture
def work():
    d = Path(os.environ["BO_TMP"]) / "pytest"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ SHA256SUMS e registro

def test_parse_shasums_e_zh():
    a, b = "a" * 64, "b" * 64
    s = signed.parse_shasums(f"{a}  terraform-provider-azurerm_1.0.0_linux_amd64.zip\n"
                             f"{b}  terraform-provider-azurerm_1.0.0_darwin_arm64.zip\n"
                             f"{a}  terraform-provider-azurerm_1.0.0_manifest.json\n")
    assert signed.zh_hashes(s, "1.0.0") == sorted([f"zh:{a}", f"zh:{b}"])
    with pytest.raises(signed.TrustError):
        signed.parse_shasums(f"{a}  x\n{a}  x\n")
    with pytest.raises(signed.TrustError):
        signed.parse_shasums("XYZ  arquivo\n")


def test_url_da_assinatura_so_a_oficial():
    base = common.sums_url("2.53.0")
    assert signed.sig_url_ok(base + ".sig", "2.53.0")
    assert signed.sig_url_ok(base + ".72D7468F.sig", "2.53.0")
    assert not signed.sig_url_ok(base.replace("releases.hashicorp.com", "evil.example.com") + ".sig", "2.53.0")
    assert not signed.sig_url_ok(common.sums_url("2.54.0") + ".sig", "2.53.0")
    assert not signed.sig_url_ok(base + ".72D7468F.sig?x=1", "2.53.0")


def _reg(v):
    return {"os": "darwin", "arch": "arm64", "filename": common.zip_name(v), "download_url": common.zip_url(v),
            "shasums_url": common.sums_url(v), "shasums_signature_url": common.sums_url(v) + ".72D7468F.sig",
            "shasum": "c" * 64}


def test_registro_com_url_estranha_reprova():
    signed.check_registry(_reg("3.0.0"), "3.0.0", "darwin_arm64")
    for k, bad in (("download_url", "https://evil.example.com/x.zip"), ("shasums_url", "https://x.test/S"),
                   ("arch", "amd64"), ("shasum", "nao-hex"), ("filename", "outro.zip")):
        r = _reg("3.0.0")
        r[k] = bad
        with pytest.raises(signed.TrustError):
            signed.check_registry(r, "3.0.0", "darwin_arm64")


def test_status_gpg_sem_uid():
    st = signed.parse_gpg_status(
        "[GNUPG:] NEWSIG\n[GNUPG:] EXPKEYSIG 34365D9472D7468F HashiCorp <x@example.com>\n"
        "[GNUPG:] VALIDSIG 374EC75B485913604A831CC7C820C6D5CD27AB87 2022-04-19 1650000000 0 4 0 1 10 00 "
        "C874011F0AB405110D02105534365D9472D7468F\n")
    assert st["validsig"] == "374EC75B485913604A831CC7C820C6D5CD27AB87"
    assert st["primary_fpr"] == common.HASHICORP_FPR and st["expkeysig"] and not st["badsig"]
    assert "example.com" not in json.dumps(st)


def test_gpg_confere_a_versao_mais_antiga_e_reprova_adulterado(work):
    """A assinatura guardada da primeira versão listada confere com a chave primária; um byte a mais reprova."""
    v = common.read_history().listed[0].version
    d = common.dl_dir(v)
    sums, sig = d / common.sums_name(v), d / (common.sums_name(v) + ".sig")
    reg = json.loads((d / "registry-download-darwin_arm64.json").read_text(encoding="utf-8"))
    keys = [k["ascii_armor"] for k in reg["signing_keys"]["gpg_public_keys"]]
    st = signed.gpg_verify(sums, sig, keys, work)
    assert st["primary_fpr"] == common.HASHICORP_FPR
    bad = work / "SUMS"
    bad.write_bytes(sums.read_bytes() + b"\n")
    with pytest.raises(signed.TrustError):
        signed.gpg_verify(bad, sig, keys, work)


# ------------------------------------------------------------------ h1, zip e gzip

def test_h1_da_pasta_igual_ao_do_zip_e_unpack_recusa_caminho(work):
    zp = work / "p.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("terraform-provider-azurerm_v9.9.9_x5", b"\x7fELF binario")
        zf.writestr("LICENSE.txt", b"MPL")
    un = signed.unpack(zp, work / "un")
    with zipfile.ZipFile(zp) as zf:
        assert un["h1"] == signed.zip_h1(zf) == signed.dirhash_h1(work / "un")
    evil = work / "e.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../fora", b"x")
    with pytest.raises(signed.TrustError):
        signed.unpack(evil, work / "un2")


def test_gzip_deterministico(work):
    src = work / "a.jsonl"
    src.write_text('{"a": 1}\n', encoding="utf-8")
    common.write_gz(src, work / "1.gz", "a.jsonl")
    common.write_gz(src, work / "2.gz", "a.jsonl")
    assert (work / "1.gz").read_bytes() == (work / "2.gz").read_bytes()
    assert common.gz_sha256(work / "1.gz") == hashlib.sha256(src.read_bytes()).hexdigest()


# ------------------------------------------------------------------ átomos

def _schema(write_only_attr: dict) -> dict:
    return {"format_version": "1.0", "provider_schemas": {common.ADDRESS: {"resource_schemas": {
        "azurerm_x": {"version": 0, "block": {
            "attributes": {"id": {"type": "string", "computed": True, "optional": True},
                           "pw": write_only_attr},
            "block_types": {"b": {"nesting_mode": "list", "max_items": 1,
                                  "block": {"attributes": {"n": {"type": "number", "required": True}}}}}}}}}}}


def test_atoms_make_write_only_e_contrato(work):
    sg = work / "schema.json.gz"
    with gzip.open(sg, "wt", encoding="utf-8") as f:
        json.dump(_schema({"type": "string", "optional": True, "write_only": True}), f)
    r = atoms.make(sg, "9.9.9", work / "b", work / "atoms.gz", work / "types.gz")
    assert r["atoms"] == 3 and r["types"] == 1 and r["write_only"] == 1
    with gzip.open(work / "atoms.gz", "rt", encoding="utf-8") as f:
        at = [json.loads(x) for x in f]
    assert [a["path"] for a in at] == ["id", "pw", "b.n"]
    assert [a.get("write_only") for a in at] == [None, True, None]
    assert all(a["provider_version"] == "9.9.9" for a in at)
    # mesmos bytes numa segunda geração
    r2 = atoms.make(sg, "9.9.9", work / "b2", work / "atoms2.gz", work / "types2.gz")
    assert r2["atoms_gz_sha256"] == r["atoms_gz_sha256"] and r2["types_gz_sha256"] == r["types_gz_sha256"]


def test_write_only_computado_reprova(work):
    sg = work / "schema.json.gz"
    with gzip.open(sg, "wt", encoding="utf-8") as f:
        json.dump(_schema({"type": "string", "optional": True, "computed": True, "write_only": True}), f)
    with pytest.raises(core.SchemaError):
        atoms.make(sg, "9.9.9", work / "b", work / "atoms.gz", work / "types.gz")


# ------------------------------------------------------------------ conferências do gate

def _hist(n=3):
    h = common.read_history()
    return h, list(h.listed[:n])


def test_monotonia_pega_data_fora_de_ordem():
    h, L = _hist()
    assert check.check_monotonic(dataclasses.replace(h, listed=tuple(L))) == []
    L2 = [L[0], dataclasses.replace(L[1], released_at="2020-01-01"), L[2]]
    assert any("released_at" in e for e in check.check_monotonic(dataclasses.replace(h, listed=tuple(L2))))
    L3 = [L[0], dataclasses.replace(L[1], published_at=L[0].published_at), L[2]]
    assert any("published_at" in e for e in check.check_monotonic(dataclasses.replace(h, listed=tuple(L3))))
    L4 = [L[1], L[0], L[2]]
    assert any("SemVer" in e for e in check.check_monotonic(dataclasses.replace(h, listed=tuple(L4))))


def test_cobertura_exige_motivo_e_proibe_sha_sem_extracao():
    h, L = _hist(1)
    h1 = dataclasses.replace(h, listed=tuple(L))
    v = L[0].version
    vdoc = {"versions": [{"version": v, "released_at": L[0].released_at}]}
    sem = {"versions": [{"version": v, "status": "NOT_EXTRACTED", "reason": "  "}]}
    com = {"versions": [{"version": v, "status": "NOT_EXTRACTED", "reason": "pacote ausente"}]}
    assert any("sem motivo" in e for e in check.check_coverage(h1, vdoc, sem)[0])
    assert check.check_coverage(h1, vdoc, com)[0] == []
    vdoc_sha = {"versions": [{"version": v, "released_at": L[0].released_at, "schema_sha256": "d" * 64}]}
    assert any("com schema_sha256" in e for e in check.check_coverage(h1, vdoc_sha, com)[0])
    assert any("status" in e for e in check.check_coverage(h1, vdoc, {"versions": [{"version": v}]})[0])


def test_lista_diferente_do_pins_reprova():
    h, L = _hist(2)
    h2 = dataclasses.replace(h, listed=tuple(L))
    vdoc = {"provider": "azurerm", "module": "HIST-AZURE",
            "versions": [{"version": L[0].version, "released_at": L[0].released_at}]}
    rep = {"versions": [{"version": x.version, "released_at": x.released_at, "published_at": x.published_at}
                        for x in L]}
    errs = check.check_lists(h2, vdoc, rep)
    assert len(errs) == 1 and "versions.json" in errs[0]


def test_binario_restante_e_detectado(work, monkeypatch):
    monkeypatch.setenv("BO_DATA", str(work / "data"))
    monkeypatch.setenv("BO_TMP", str(work / "tmp"))
    d = common.dl_dir("1.0.0")
    d.mkdir(parents=True)
    (d / common.sums_name("1.0.0")).write_text("x")
    (d / (common.sums_name("1.0.0") + ".sig")).write_bytes(b"x")
    assert pipeline.leftover_binaries() == []
    b = common.unpacked_dir("1.0.0")
    b.mkdir(parents=True)
    (b / "terraform-provider-azurerm_v1.0.0_x5").write_bytes(b"\x7fELF")
    (d / common.zip_name("1.0.0")).write_bytes(b"PK")
    assert len(pipeline.leftover_binaries()) == 2
    pipeline.cleanup("1.0.0", d / common.zip_name("1.0.0"))
    assert pipeline.leftover_binaries() == []


# ------------------------------------------------------------------ saídas publicadas

def test_lista_historica_do_pins():
    h = common.read_history()
    assert h.contract_version == "3.1.0" and h.listed[-1].version == h.pin == V5
    assert len(h.listed) == 27 and h.listed[-1].schema_sha256
    assert all(it.darwin_arm64 for it in h.listed)


def test_saidas_publicadas_conferem():
    rc, lines = check.run()
    assert rc == 0, lines
    assert V.validate("versions", common.versions_path()).ok
    rep = json.loads(common.report_path().read_text(encoding="utf-8"))
    pin = next(r for r in rep["versions"] if r["version"] == V5)
    assert pin["schema"]["sha256"] == common.read_history().listed[-1].schema_sha256
    for r in rep["versions"]:
        if r["status"] == "EXTRACTED":
            assert r["provider_binary"]["apagado"] and r["limpeza"]["binarios_restantes"] == []
            assert r["chain"]["gpg"]["primary_fpr"] == common.HASHICORP_FPR
            assert r["chain"]["zip"]["igual_ao_shasums"]
