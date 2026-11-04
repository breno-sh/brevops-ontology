"""Unidades do HIST-AWS sobre dados sintéticos (sem rede, sem terraform, sem binário)."""
import hashlib
import json
import zipfile

import pytest

from bo.hist_aws import atoms, check, common, fetch, pipeline, trust
from conftest import SCHEMA, write_schema_gz

SHA_A = "a" * 64
SHA_B = "b" * 64


# ------------------------------------------------------------------ SHA256SUMS

def test_parse_shasums_e_zh():
    sums = trust.parse_shasums(
        f"{SHA_A}  terraform-provider-aws_3.34.0_darwin_arm64.zip\n"
        f"{SHA_B}  terraform-provider-aws_3.34.0_linux_amd64.zip\n"
        f"{'c' * 64}  terraform-provider-aws_3.34.0_manifest.json\n")
    assert sums["terraform-provider-aws_3.34.0_darwin_arm64.zip"] == SHA_A
    assert trust.zh_hashes(sums, "3.34.0") == [f"zh:{SHA_A}", f"zh:{SHA_B}"]
    assert trust.zh_hashes(sums, "3.47.0") == []


@pytest.mark.parametrize("bad", [f"{SHA_A[:-1]}  x.zip\n", f"{SHA_A.upper()}  x.zip\n",
                                 f"{SHA_A}  x.zip\n{SHA_B}  x.zip\n", f"{SHA_A}\n"])
def test_parse_shasums_reprova_mal_formado(bad):
    with pytest.raises(trust.TrustError):
        trust.parse_shasums(bad)


# ------------------------------------------------------------------ GPG

def _status(primary, sub="374EC75B485913604A831CC7C820C6D5CD27AB87", extra=""):
    return (f"[GNUPG:] NEWSIG\n{extra}"
            f"[GNUPG:] VALIDSIG {sub} 2022-04-19 1650000000 0 4 0 1 8 00 {primary}\n")


def test_gpg_status_ancora_aceita_e_expkeysig_registrado():
    st = trust.parse_gpg_status(_status(common.HASHICORP_FPR, extra="[GNUPG:] EXPKEYSIG 34365D9472D7468F x\n"))
    trust.check_gpg_status(st)
    assert st["expkeysig"] and st["primary_fpr"] == common.HASHICORP_FPR


@pytest.mark.parametrize("status", [
    _status("0" * 40),                                            # outra chave primária
    "[GNUPG:] BADSIG 34365D9472D7468F x\n",                       # assinatura ruim
    _status(common.HASHICORP_FPR, extra="[GNUPG:] ERRSIG x\n"),   # erro
    "[GNUPG:] NEWSIG\n",                                          # sem VALIDSIG
])
def test_gpg_status_reprova(status):
    with pytest.raises(trust.TrustError):
        trust.check_gpg_status(trust.parse_gpg_status(status))


# ------------------------------------------------------------------ zip, h1 e desempacotamento

def _zip(p, members):
    with zipfile.ZipFile(p, "w") as zf:
        for name, data in members.items():
            zi = zipfile.ZipInfo(name)
            zi.external_attr = 0o755 << 16
            zf.writestr(zi, data)
    return p


def test_unpack_h1_igual_ao_do_zip_e_ao_dirhash(work):
    z = _zip(work / "p.zip", {"terraform-provider-aws_v9.9.9_x5": b"bin", "LICENSE.txt": b"MPL"})
    with zipfile.ZipFile(z) as zf:
        want = trust.zip_h1(zf)
    un = trust.unpack(z, work / "cache" / "darwin_arm64")
    assert un["h1"] == want == trust.dirhash_h1(work / "cache" / "darwin_arm64")
    assert un["files"]["terraform-provider-aws_v9.9.9_x5"]["sha256"] == hashlib.sha256(b"bin").hexdigest()
    # h1 do terraform: sha256 de '<sha>  <nome>\n' em ordem de nome
    lines = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in sorted(
        {"LICENSE.txt": b"MPL", "terraform-provider-aws_v9.9.9_x5": b"bin"}.items()))
    import base64
    assert want == "h1:" + base64.b64encode(hashlib.sha256(lines.encode()).digest()).decode()


@pytest.mark.parametrize("name", ["../fora", "/abs", "sub/dir"])
def test_unpack_reprova_membro_inesperado(work, name):
    z = _zip(work / "p.zip", {name: b"x"})
    with pytest.raises(trust.TrustError):
        trust.unpack(z, work / "cache" / "x")


# ------------------------------------------------------------------ download: hosts

@pytest.mark.parametrize("url", ["http://releases.hashicorp.com/x", "https://example.com/x",
                                 "https://releases.hashicorp.com.evil.test/x"])
def test_url_fora_dos_hosts_reprova(url):
    with pytest.raises(trust.TrustError):
        fetch._check_url(url)


def test_url_do_release_aceita():
    assert fetch._check_url("https://releases.hashicorp.com/terraform-provider-aws/3.34.0/x.zip",
                            "releases.hashicorp.com")


# ------------------------------------------------------------------ átomos

def test_atoms_write_only_e_determinismo(work, schema_gz):
    r1 = atoms.make(schema_gz, "1.0.0", work / "b1", work / "a1.jsonl.gz")
    r2 = atoms.make(schema_gz, "1.0.0", work / "b2", work / "a2.jsonl.gz")
    assert r1["atoms_gz_sha256"] == r2["atoms_gz_sha256"]
    got = {a["atom_id"]: a for a in atoms.read_atoms(work / "a1.jsonl.gz")}
    assert r1["atoms"] == len(got) == 8 and r1["types"] == 2 and r1["write_only"] == 2
    assert got["aws:aws_exemplo_segredo:value_wo"]["write_only"] is True
    assert got["aws:aws_exemplo_segredo:config.token_wo"]["write_only"] is True
    assert "write_only" not in got["aws:aws_exemplo_segredo:name"]
    assert {a["provider_version"] for a in got.values()} == {"1.0.0"}


def test_atoms_write_only_computed_reprova(work, schema_doc):
    schema_doc["provider_schemas"]["registry.terraform.io/hashicorp/aws"]["resource_schemas"][
        "aws_exemplo_segredo"]["block"]["attributes"]["value_wo"]["computed"] = True
    p = work / "s.json.gz"
    write_schema_gz(p, schema_doc)
    with pytest.raises(Exception, match="WRITEONLY"):
        atoms.make(p, "1.0.0", work / "b", work / "a.jsonl.gz")


# ------------------------------------------------------------------ check (mutações plantadas)

def _hist(versions, pin):
    items = tuple(common.Listed(v, d, d + "T00:00:00Z", ("quarter_end:2021Q1",), ("5.0",), True)
                  for v, d in versions)
    return common.History(pin, None, items, {}, {})


def _out(work, schema_gz):
    """out/ sintético: 1.0.0 EXTRACTED (pin), 1.1.0 FAILED com motivo."""
    out = work / "out"
    sdir = out / "schemas" / "aws-1.0.0"
    raw = write_schema_gz(sdir / "schema.json.gz", SCHEMA)
    sha = hashlib.sha256(raw).hexdigest()
    (sdir / "schema.json.sha256").write_text(f"{sha}  schema.json\n")
    br = atoms.make(sdir / "schema.json.gz", "1.0.0", work / "b", out / "atoms_1.0.0.jsonl.gz")
    (sdir / "trust.json").write_text(json.dumps({
        "gpg": {"primary_fpr": common.HASHICORP_FPR, "validsig_subkey": "X"},
        "binary": {"file": "b", "sha256": SHA_A, "igual_ao_membro_do_zip": True},
        "unpacked": {"files": {"b": {"sha256": SHA_A}}, "apagado": True},
        "zip": {"reaproveitado_de": None, "apagado": True}, "schema_json_sha256": sha}))
    ext = {"versions": {
        "1.0.0": {"status": "EXTRACTED", "schema_sha256": sha, "atoms_gz_sha256": br["atoms_gz_sha256"],
                  "atoms": br["atoms"]},
        "1.1.0": {"status": "FAILED", "motivo": "TrustError: assinatura não confere"}}}
    (out / "extraction.json").write_text(json.dumps(ext))
    vd = {"module": "HIST-AWS", "provider": "aws", "versions": [
        {"version": "1.0.0", "released_at": "2021-03-25", "schema_sha256": sha},
        {"version": "1.1.0", "released_at": "2021-06-24"}]}
    (out / "versions.json").write_text(json.dumps(vd))
    pins = common.Pins("1.15.8", SHA_B, "1.0.0", SHA_B, sha)
    return out, ext, vd, pins


H = [("1.0.0", "2021-03-25"), ("1.1.0", "2021-06-24")]


def test_check_controle_passa(work, schema_gz):
    out, _, _, pins = _out(work, schema_gz)
    assert check.check(out, deep=True, hist=_hist(H, "1.0.0"), pins=pins) == []


def _mut(out, name, fn):
    p = out / name
    d = json.loads(p.read_text())
    fn(d)
    p.write_text(json.dumps(d))


@pytest.mark.parametrize("mut, msg", [
    (lambda o: _mut(o, "versions.json", lambda d: d["versions"].pop()), "lista do PINS"),
    (lambda o: _mut(o, "extraction.json", lambda d: d["versions"].pop("1.1.0")), "nem extraída nem com motivo"),
    (lambda o: _mut(o, "extraction.json", lambda d: d["versions"]["1.1.0"].update(motivo=" ")), "sem motivo"),
    (lambda o: _mut(o, "versions.json", lambda d: d["versions"][1].update(schema_sha256=SHA_A)),
     "não extraída mas com schema_sha256"),
    (lambda o: _mut(o, "versions.json", lambda d: d["versions"][0].update(schema_sha256=SHA_A)),
     "schema_sha256 diverge"),
    (lambda o: _mut(o, "extraction.json", lambda d: d["versions"]["1.0.0"].update(atoms=1)), "átomos, registrado"),
    (lambda o: (o / "atoms_1.0.0.jsonl.gz").write_bytes(b"x"), "sha256 de atoms_1.0.0"),
    (lambda o: _mut(o, "schemas/aws-1.0.0/trust.json", lambda d: d["unpacked"].update(apagado=False)),
     "não apagado"),
    (lambda o: _mut(o, "schemas/aws-1.0.0/trust.json", lambda d: d["gpg"].update(primary_fpr="0" * 40)),
     "VALIDSIG"),
])
def test_check_mutacao_reprova(work, schema_gz, mut, msg):
    out, _, _, pins = _out(work, schema_gz)
    mut(out)
    errs = check.check(out, deep=True, hist=_hist(H, "1.0.0"), pins=pins)
    assert any(msg in e for e in errs), errs


def test_check_datas_nao_monotonas_reprova(work, schema_gz):
    out, _, _, pins = _out(work, schema_gz)
    bad = [("1.0.0", "2021-07-01"), ("1.1.0", "2021-06-24")]
    _mut(out, "versions.json", lambda d: (d["versions"][0].update(released_at="2021-07-01")))
    errs = check.check(out, hist=_hist(bad, "1.0.0"), pins=pins)
    assert any("datas não monótonas" in e for e in errs), errs


def test_check_pin_nao_extraido_reprova(work, schema_gz):
    out, _, _, pins = _out(work, schema_gz)
    errs = check.check(out, hist=_hist(H, "1.1.0"), pins=pins)
    assert any("pin 1.1.0 não extraído" in e for e in errs), errs


def test_check_pin_sha_diverge_reprova(work, schema_gz):
    out, _, _, pins = _out(work, schema_gz)
    pins = common.Pins(pins.terraform_version, SHA_B, "1.0.0", SHA_B, SHA_A)
    errs = check.check(out, hist=_hist(H, "1.0.0"), pins=pins)
    assert any("pins.json" in e for e in errs), errs


# ------------------------------------------------------------------ versions.json e manifesto

def test_versions_doc_so_extraidas_tem_schema_sha():
    hist = _hist(H, "1.0.0")
    vd = pipeline.versions_doc(hist, {"versions": {"1.0.0": {"status": "EXTRACTED", "schema_sha256": SHA_A},
                                                   "1.1.0": {"status": "FAILED", "motivo": "x"}}})
    assert vd["versions"] == [{"version": "1.0.0", "released_at": "2021-03-25", "schema_sha256": SHA_A},
                              {"version": "1.1.0", "released_at": "2021-06-24"}]
    assert vd["module"] == "HIST-AWS" and vd["contract_version"] == "3.1.0"


def test_manifesto_ignora_logs_volateis(work):
    root = work / "m"
    (root / "integration").mkdir(parents=True)
    (root / "integration" / "last_run.json").write_text("{}")
    for n in ("gate_report.json", "consume_ledger.json", "versions.json", "x.part"):
        (root / n).write_text("{}")
    names = [p.relative_to(root).as_posix() for p in pipeline.manifest_files(root)]
    assert names == ["versions.json"]


def test_semver_key_ordena_numericamente():
    vs = ["5.6.2", "5.19.0", "5.0.0", "4.61.0", "10.0.0"]
    assert sorted(vs, key=common.semver_key) == ["4.61.0", "5.0.0", "5.6.2", "5.19.0", "10.0.0"]
