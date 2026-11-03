"""Testes do bo.schema_gcp: cadeia do pin, lock, h1, write_only sobre a biblioteca, mirror offline e beta_check."""
import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from bo.schema import core, lockfile
from bo.schema_gcp import atoms as A
from bo.schema_gcp import beta_check as B
from bo.schema_gcp import common as C
from bo.schema_gcp import offline

SUMS = (
    "aa" * 32 + "  terraform-provider-google_8.9.0_darwin_arm64.zip\n"
    + "bb" * 32 + "  terraform-provider-google_8.9.0_linux_amd64.zip\n"
    + "cc" * 32 + "  terraform-provider-google_8.9.0_manifest.json\n"
)


# ------------------------------------------------------------------ SHA256SUMS, lock, h1

def test_sha256sums_so_zips_do_release():
    z = C.parse_sha256sums(SUMS, "8.9.0")
    assert z == {"darwin_arm64": "aa" * 32, "linux_amd64": "bb" * 32}


@pytest.mark.parametrize("bad", [
    "dd" * 32 + "  terraform-provider-google_8.8.0_darwin_arm64.zip\n",      # outro release
    "dd" * 32 + "  terraform-provider-google-beta_8.9.0_darwin_arm64.zip\n",  # outro provider
    "xyz  terraform-provider-google_8.9.0_darwin_arm64.zip\n",                 # fora do formato
])
def test_sha256sums_reprova_linha_estranha(bad):
    with pytest.raises(C.PinError):
        C.parse_sha256sums(SUMS + bad, "8.9.0")


def test_lock_h1_e_zh_ordenados_e_relidos():
    pin = {"version": "8.9.0"}
    sig = {"h1": "h1:abc=", "zips": {"darwin_arm64": "aa" * 32, "linux_amd64": "bb" * 32}}
    lp = C.locked_provider(pin, sig)
    assert lp.hashes == ("h1:abc=", "zh:" + "aa" * 32, "zh:" + "bb" * 32)
    again = lockfile.find(lockfile.parse(lockfile.render([lp])), C.SOURCE)
    assert again == lp and again.version == "8.9.0" and again.constraints == "8.9.0"


def test_h1_e_o_dirhash_do_terraform(work):
    d = work / "pkg"
    (d / "sub").mkdir(parents=True)
    (d / "terraform-provider-x").write_bytes(b"binario")
    (d / "sub" / "LICENSE.txt").write_bytes(b"licenca")
    lines = "".join(f"{hashlib.sha256((d / r).read_bytes()).hexdigest()}  {r}\n"
                    for r in sorted(["sub/LICENSE.txt", "terraform-provider-x"]))
    want = "h1:" + base64.b64encode(hashlib.sha256(lines.encode()).digest()).decode()
    assert C.dirhash_h1(d) == want
    (d / "terraform-provider-x").write_bytes(b"binarioX")
    assert C.dirhash_h1(d) != want


def test_signed_inputs_reprova_pin_com_outro_sha():
    pin = C.read_pin()
    if not C.prefetch_dir(pin["version"]).exists():
        pytest.skip("pré-busca ausente")
    assert C.signed_inputs(pin)["sha256sums_sha256"] == pin["shasums_sha256"]
    with pytest.raises(C.PinError):
        C.signed_inputs({**pin, "shasums_sha256": "0" * 64})


def test_pin_le_google_do_pins_json(work):
    pins = work / "pins.json"
    doc = {"terraform": {"version": "1.15.8"}, "providers": [
        {"provider": "google", "source": C.ADDRESS, "version": "8.9.0", "shasums_sha256": "a" * 64,
         "schema_sha256": "b" * 64}]}
    pins.write_text(json.dumps(doc), encoding="utf-8")
    assert C.read_pin(pins)["version"] == "8.9.0"
    doc["providers"][0]["source"] = "registry.terraform.io/hashicorp/google-beta"
    pins.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(C.PinError):
        C.read_pin(pins)


def test_plugin_cache_real_tem_o_h1_do_lock_da_pre_busca():
    pin = C.read_pin()
    pdir = C.provider_dir(C.plugin_cache(), pin["version"])
    if not pdir.exists():
        pytest.skip("plugin_cache ainda não gerado")
    pre = lockfile.find(lockfile.read(C.prefetch_dir(pin["version"]) / "terraform.lock.hcl"), C.SOURCE)
    assert C.dirhash_h1(pdir) in pre.hashes


# ------------------------------------------------------------------ átomos: biblioteca + write_only

def test_write_only_so_onde_o_schema_marca(schema_file, work):
    r = A.build(schema_file, "8.9.0", work / "a.jsonl", work / "t.jsonl")
    at = [json.loads(x) for x in (work / "a.jsonl").read_text().splitlines()]
    wo = sorted(a["atom_id"] for a in at if "write_only" in a)
    assert wo == ["google:google_widget:conf.key_wo", "google:google_widget:secret_wo"]
    assert all(a["write_only"] is True for a in at if "write_only" in a)
    assert r == {**r, "types": 2, "atoms": 7, "write_only": 2}
    from bo.contracts import validate as V
    assert V.validate("C01_atoms", work / "a.jsonl").ok
    assert V.validate("C02_types", work / "t.jsonl").ok


def test_sem_write_only_e_byte_a_byte_a_biblioteca(schema_file, work):
    from bo.schema import build as LB
    A.build(schema_file, "8.9.0", work / "a.jsonl", work / "t.jsonl")
    LB.build(schema_file, "google", "8.9.0", work / "la.jsonl", work / "lt.jsonl")
    assert (work / "t.jsonl").read_bytes() == (work / "lt.jsonl").read_bytes()
    mine = (work / "a.jsonl").read_text().splitlines()
    lib = (work / "la.jsonl").read_text().splitlines()
    diff = [(m, b) for m, b in zip(mine, lib) if m != b]
    assert len(mine) == len(lib) and len(diff) == 2
    for m, b in diff:
        mm = json.loads(m)
        assert mm.pop("write_only") is True and mm == json.loads(b)


def test_write_only_reprova_percurso_fora_de_ordem(schema_file):
    ps = core.providers(core.load(schema_file))["google"]
    ts = next(t for t in core.iter_types(ps, "google", "8.9.0") if t.resource_type == "google_widget")
    ts.atoms.reverse()
    with pytest.raises(core.SchemaError):
        A.annotate_write_only(ts)


def test_regenerar_da_os_mesmos_bytes(schema_file, work):
    A.build(schema_file, "8.9.0", work / "a1.jsonl", work / "t1.jsonl")
    A.build(schema_file, "8.9.0", work / "a2.jsonl", work / "t2.jsonl")
    assert (work / "a1.jsonl").read_bytes() == (work / "a2.jsonl").read_bytes()
    assert (work / "t1.jsonl").read_bytes() == (work / "t2.jsonl").read_bytes()


# ------------------------------------------------------------------ offline e beta_check

def test_terraformrc_so_mirror_para_o_google(work):
    rc = offline.terraformrc(work)
    assert "filesystem_mirror" in rc and str(work.resolve()) in rc
    assert f'exclude = ["{C.ADDRESS}"]' in rc and f'include = ["{C.ADDRESS}"]' in rc


def test_beta_check_classifica_paginas(work, monkeypatch):
    monkeypatch.setattr(C, "prefetch_dir", lambda v: work / "pf")
    r = work / "pf" / "docs" / "r"
    r.mkdir(parents=True)
    (r / "x_beta.html.markdown").write_text("~> **Warning:** This resource is in beta, and should be used with "
                                            "the terraform-provider-google-beta provider.\n  provider = google-beta\n")
    (r / "y_iam.html.markdown").write_text("sem aviso\n")
    (r / "ga.html.markdown").write_text("These resources are in beta, and should be used with the "
                                        "terraform-provider-google-beta provider.\n")
    index = {"docs": [{"slug": s, "category": "resources", "language": "hcl"} for s in ("x_beta", "y_iam", "ga")]}
    xc = {"veredito": "FAIL", "paginas_sem_tipo": ["google_x_beta", "google_y_iam"], "tipos_sem_pagina": []}
    rep = B.analyse(xc, {"google_ga"}, {"google_ga", "google_x_beta", "google_y_iam_member"}, index, "8.9.0")
    by = {p["pagina"]: p for p in rep["paginas"]}
    assert by["google_x_beta"] == {"pagina": "google_x_beta", "em_google_beta": True,
                                   "tipos_google_beta": ["google_x_beta"], "aviso_beta": True, "exemplo_beta": True}
    assert by["google_y_iam"]["em_google_beta"] and not by["google_y_iam"]["aviso_beta"]
    assert rep["contagens"]["sem_aviso_beta"] == ["google_y_iam"]
    assert rep["controle_aviso_beta_com_tipo_no_google"] == [{"pagina": "google_ga", "tipos_google": ["google_ga"]}]
    assert rep["conclusao"].startswith("todas")
    rep2 = B.analyse(xc, {"google_ga"}, {"google_ga"}, index, "8.9.0")
    assert rep2["contagens"]["fora_do_google_beta"] == ["google_x_beta", "google_y_iam"]
    assert rep2["conclusao"].startswith("há página")


def test_portable_troca_prefixo():
    assert C.portable(C.bo_data() / "SCHEMA-GCP" / "x") == "$BO_DATA/SCHEMA-GCP/x"
    assert C.portable("/outro/lugar") == "/outro/lugar"
    assert os.environ["BO_TMP"].endswith("SCHEMA-GCP")
