"""Unidades do SCHEMA-AWS sobre dados sintéticos (sem rede, sem terraform)."""
import json
import os
import zipfile

import pytest

from bo.schema import core, lockfile
from bo.schema_aws import atoms, common, offline, pipeline, signed

SHA_A = "a" * 64
SHA_B = "b" * 64


# ------------------------------------------------------------------ SHA256SUMS e lock

def test_parse_shasums_e_zh():
    sums = signed.parse_shasums(
        f"{SHA_A}  terraform-provider-aws_6.71.0_darwin_arm64.zip\n"
        f"{SHA_B}  terraform-provider-aws_6.71.0_linux_amd64.zip\n"
        f"{'c' * 64}  terraform-provider-aws_6.71.0_manifest.json\n")
    assert sums["terraform-provider-aws_6.71.0_darwin_arm64.zip"] == SHA_A
    assert signed.zh_hashes(sums, "aws", "6.71.0") == [f"zh:{SHA_A}", f"zh:{SHA_B}"]
    assert signed.zh_hashes(sums, "aws", "6.70.0") == []


@pytest.mark.parametrize("bad", [f"{SHA_A[:-1]}  x.zip\n", f"{SHA_A.upper()}  x.zip\n",
                                 f"{SHA_A}  x.zip\n{SHA_B}  x.zip\n", f"{SHA_A}\n"])
def test_parse_shasums_reprova_mal_formado(bad):
    with pytest.raises(signed.TrustError):
        signed.parse_shasums(bad)


def test_lock_do_modulo_relido_pela_biblioteca():
    lp = lockfile.LockedProvider(common.ADDRESS, "6.71.0", "6.71.0", ("h1:abc=", f"zh:{SHA_A}"))
    back = lockfile.find(lockfile.parse(lockfile.render([lp])), "hashicorp/aws")
    assert back == lp


# ------------------------------------------------------------------ GPG

def test_parse_gpg_status_validsig_com_subchave_vencida():
    st = signed.parse_gpg_status(
        "[GNUPG:] NEWSIG\n[GNUPG:] KEYEXPIRED 1776549017\n"
        "[GNUPG:] EXPKEYSIG C820C6D5CD27AB87 Fulano\n"
        "[GNUPG:] VALIDSIG 374EC75B485913604A831CC7C820C6D5CD27AB87 2026-10-28 1793217807 0 4 0 1 8 00 "
        f"{common.HASHICORP_FPR}\n")
    assert st["validsig"].endswith("C820C6D5CD27AB87")
    assert st["primary_fpr"] == common.HASHICORP_FPR
    assert st["expkeysig"] and not st["badsig"] and st["sig_created"] == "2026-10-28"


def test_parse_gpg_status_badsig():
    st = signed.parse_gpg_status("[GNUPG:] BADSIG C820C6D5CD27AB87 Fulano\n")
    assert st["badsig"] and st["validsig"] is None


# ------------------------------------------------------------------ zip, h1, desempacotar

def _zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, (data, mode) in members.items():
            zi = zipfile.ZipInfo(name)
            zi.external_attr = (0o100000 | mode) << 16
            z.writestr(zi, data)
    return path


def test_unpack_h1_igual_ao_do_zip_e_idempotente(work):
    zp = _zip(work / "p.zip", {"LICENSE.txt": (b"lic", 0o644), "terraform-provider-x_v1": (b"\x7fELFbin", 0o755)})
    dest = work / "cache" / "darwin_arm64"
    r1 = signed.unpack(zp, dest)
    with zipfile.ZipFile(zp) as z:
        assert r1["h1"] == signed.zip_h1(z) == signed.dirhash_h1(dest)
    assert oct(os.stat(dest / "terraform-provider-x_v1").st_mode & 0o777) == "0o755"
    r2 = signed.unpack(zp, dest)                      # já existe com o mesmo h1: não toca
    assert r2 == r1


def test_unpack_reprova_pasta_adulterada(work):
    zp = _zip(work / "p.zip", {"LICENSE.txt": (b"lic", 0o644)})
    dest = work / "cache" / "x"
    signed.unpack(zp, dest)
    (dest / "LICENSE.txt").write_bytes(b"outro")
    with pytest.raises(signed.TrustError):
        signed.unpack(zp, dest)


@pytest.mark.parametrize("name", ["../fora", "sub/arquivo", "/abs"])
def test_unpack_reprova_membro_com_caminho(work, name):
    zp = _zip(work / "p.zip", {name: (b"x", 0o644)})
    with pytest.raises(signed.TrustError):
        signed.unpack(zp, work / "cache" / "y")


def test_h1_formula_do_dirhash(work):
    """h1 = base64(sha256('<sha256 hex>  <nome>\\n' em ordem)), como o golang.org/x/mod/sumdb/dirhash."""
    import base64
    import hashlib
    d = work / "d"
    d.mkdir()
    (d / "b").write_bytes(b"2")
    (d / "a").write_bytes(b"1")
    lines = "".join(f"{hashlib.sha256(x).hexdigest()}  {n}\n" for n, x in (("a", b"1"), ("b", b"2")))
    assert signed.dirhash_h1(d) == "h1:" + base64.b64encode(hashlib.sha256(lines.encode()).digest()).decode()


# ------------------------------------------------------------------ átomos e write_only

def test_make_write_only_so_onde_o_schema_marca(work, schema_gz):
    r = atoms.make(schema_gz, "6.71.0", work / "a.jsonl", work / "t.jsonl")
    at = {a["atom_id"]: a for a in map(json.loads, open(work / "a.jsonl"))}
    wo = sorted(k for k, a in at.items() if "write_only" in a)
    assert wo == ["aws:aws_exemplo_segredo:config.token_wo", "aws:aws_exemplo_segredo:value_wo"]
    assert all(at[k]["write_only"] is True and at[k]["configurable"] and not at[k]["computed"] for k in wo)
    assert r["write_only"] == 2 and r["types"] == 2 and r["atoms"] == len(at) == 9 and r["data_sources"] == 1
    assert at["aws:aws_exemplo_segredo:config.inner.n"]["nesting"] == "single"


def test_make_mesmos_bytes_e_contratos(work, schema_gz):
    from bo.contracts import validate as V
    for i in (1, 2):
        atoms.make(schema_gz, "6.71.0", work / f"a{i}.jsonl", work / f"t{i}.jsonl")
    assert (work / "a1.jsonl").read_bytes() == (work / "a2.jsonl").read_bytes()
    assert (work / "t1.jsonl").read_bytes() == (work / "t2.jsonl").read_bytes()
    assert V.validate("C01_atoms", work / "a1.jsonl").ok
    assert V.validate("C02_types", work / "t1.jsonl").ok


def test_saida_e_a_da_biblioteca_byte_a_byte(work, schema_gz):
    """O módulo não acrescenta nem muda nada: átomos e tipos são os bytes da bo.schema.build."""
    from bo.schema import build
    build.build(schema_gz, "aws", "6.71.0", work / "lib.jsonl", work / "t.jsonl")
    atoms.make(schema_gz, "6.71.0", work / "mod.jsonl", work / "t2.jsonl")
    assert (work / "lib.jsonl").read_bytes() == (work / "mod.jsonl").read_bytes()
    assert (work / "t.jsonl").read_bytes() == (work / "t2.jsonl").read_bytes()
    assert sum('"write_only": true' in x for x in open(work / "lib.jsonl")) == 2


def test_write_only_computed_reprova_na_biblioteca(work, schema_doc, schema_gz):
    """C01-WRITEONLY é conferida pela biblioteca: write_only + computed reprova no build."""
    import gzip
    blk = schema_doc["provider_schemas"][common.ADDRESS]["resource_schemas"]["aws_exemplo_simples"]["block"]
    blk["attributes"]["arn"]["write_only"] = True
    with open(schema_gz, "wb") as f, gzip.GzipFile(filename="schema.json", mode="wb", fileobj=f, mtime=0) as g:
        g.write(json.dumps(schema_doc).encode())
    with pytest.raises(core.SchemaError):
        atoms.make(schema_gz, "6.71.0", work / "a.jsonl", work / "t.jsonl")


# ------------------------------------------------------------------ plugin_cache

def test_terraformrc_so_o_provider_fixado_e_sem_instalacao_direta(work):
    rc = pipeline.terraformrc(work / "cache")
    assert f'include = ["{common.ADDRESS}"]' in rc
    assert 'exclude = ["registry.terraform.io/*/*"]' in rc
    assert f'path    = "{work / "cache"}"' in rc


def test_versions_tf_fixa_versao_exata():
    assert 'version = "= 6.71.0"' in offline.versions_tf("6.71.0")


def test_pin_vem_do_pins_json(work):
    p = work / "pins.json"
    p.write_text(json.dumps({"terraform": {"version": "1.15.8"}, "providers": [
        {"provider": "aws", "source": common.ADDRESS, "version": "9.9.9", "shasums_sha256": SHA_A,
         "schema_sha256": SHA_B}]}))
    pin = common.read_pin(p)
    assert (pin.version, pin.shasums_sha256, pin.schema_sha256, pin.terraform_version) == \
        ("9.9.9", SHA_A, SHA_B, "1.15.8")
    p.write_text(json.dumps({"terraform": {"version": "1"}, "providers": []}))
    with pytest.raises(SystemExit):
        common.read_pin(p)


def test_portable():
    assert common.portable(common.bo_data() / "SCHEMA-AWS" / "x") == "$BO_DATA/SCHEMA-AWS/x"
    assert common.portable("/outro/lugar") == "/outro/lugar"
