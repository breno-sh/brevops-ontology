"""bo.schema_oci.signed: elos da cadeia de confiança, com dados sintéticos e com o SHA256SUMS real da pré-busca."""
import zipfile

import pytest

from bo.schema_oci import common, signed

SHA = "a" * 64


def test_parse_shasums_e_zh():
    sums = signed.parse_shasums(f"{SHA}  terraform-provider-oci_1.0.0_darwin_arm64.zip\n"
                                f"{'b' * 64}  terraform-provider-oci_1.0.0_manifest.json\n")
    assert signed.zh_hashes(sums, "oci", "1.0.0") == [f"zh:{SHA}"]       # o manifest.json não é zip


@pytest.mark.parametrize("text", ["xyz  arquivo\n", f"{SHA}  a\n{SHA}  a\n", f"{SHA}\n"])
def test_parse_shasums_reprova_mal_formado(text):
    with pytest.raises(signed.TrustError):
        signed.parse_shasums(text)


def test_parse_gpg_status():
    st = signed.parse_gpg_status(
        "[GNUPG:] GOODSIG 1533A49284137CEB nome\n"
        f"[GNUPG:] VALIDSIG {common.ORACLE_FPR} 2026-10-21 1 0 4 0 1 8 00 {common.ORACLE_FPR}\n")
    assert st["goodsig"] and st["validsig"] == common.ORACLE_FPR and st["primary_fpr"] == common.ORACLE_FPR
    assert st["sig_created"] == "2026-10-21" and not st["badsig"]


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for n, b in members.items():
            z.writestr(n, b)
    return path


def test_h1_do_zip_igual_ao_da_pasta_e_unpack_idempotente(work):
    zp = _zip(work / "p.zip", {"terraform-provider-oci_v1.0.0": b"\x00bin", "LICENSE": b"texto"})
    dest = work / "cache" / "darwin_arm64"
    dest.parent.mkdir()
    r1 = signed.unpack(zp, dest)
    with zipfile.ZipFile(zp) as z:
        assert r1["h1"] == signed.zip_h1(z) == signed.dirhash_h1(dest)
    assert signed.unpack(zp, dest)["h1"] == r1["h1"]                    # já existe com o mesmo h1: não toca
    (dest / "LICENSE").write_bytes(b"adulterado")
    with pytest.raises(signed.TrustError, match="já existe"):
        signed.unpack(zp, dest)


def test_unpack_reprova_membro_com_caminho(work):
    zp = _zip(work / "p.zip", {"../fora": b"x"})
    with pytest.raises(signed.TrustError, match="membro inesperado"):
        signed.unpack(zp, work / "d")


def test_fetch_zip_reprova_url_fora_do_release(work):
    with pytest.raises(signed.TrustError, match="fora do release"):
        signed.fetch_zip("https://example.com/terraform-provider-oci_9.11.0_darwin_arm64.zip",
                         work / "z.zip", SHA, "9.11.0")


def _prefetch():
    pin = common.read_pin()
    pf = common.prefetch_dir(pin.version)
    return pin, pf / f"terraform-provider-oci_{pin.version}_SHA256SUMS", \
        pf / f"terraform-provider-oci_{pin.version}_SHA256SUMS.sig", pf / "registry-download-darwin_arm64.json"


def _keys(reg):
    import json
    d = json.loads(reg.read_text(encoding="utf-8"))
    return [k["ascii_armor"] for k in d["signing_keys"]["gpg_public_keys"]]


def test_gpg_real_confere_com_a_ancora_e_reprova_outra(work):
    _, sums, sig, reg = _prefetch()
    st = signed.gpg_verify(sums, sig, _keys(reg), work)
    assert st["primary_fpr"] == common.ORACLE_FPR
    with pytest.raises(signed.TrustError, match="chave primária"):
        signed.gpg_verify(sums, sig, _keys(reg), work, anchor="0" * 40)


def test_gpg_real_reprova_shasums_adulterado(work):
    _, sums, sig, reg = _prefetch()
    bad = work / "SHA256SUMS"
    bad.write_bytes(sums.read_bytes().replace(b"darwin_arm64", b"darwin_arm65"))
    with pytest.raises(signed.TrustError, match="não confere"):
        signed.gpg_verify(bad, sig, _keys(reg), work)


def test_shasums_da_pre_busca_e_o_do_pins():
    pin, sums, _, _ = _prefetch()
    assert common.sha256_file(sums) == pin.shasums_sha256
