"""Testes do bo.hist_gcp: SHA256SUMS, lock, h1 do zip, átomos sobre a biblioteca, motivo de indisponível e o
check do G2 (completude, datas monótonas, pin) num mundo sintético com mutações que têm de reprovar."""
import copy
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from bo.schema import core, lockfile
from bo.hist_gcp import atoms as A
from bo.hist_gcp import check as K
from bo.hist_gcp import common as C
from bo.hist_gcp import extract as E
from bo.hist_gcp import pipeline as P
from bo.hist_gcp import signed as S

SUMS = (
    "aa" * 32 + "  terraform-provider-google_3.74.0_darwin_arm64.zip\n"
    + "bb" * 32 + "  terraform-provider-google_3.74.0_linux_amd64.zip\n"
    + "cc" * 32 + "  terraform-provider-google_3.74.0_manifest.json\n"
)


# ------------------------------------------------------------------ SHA256SUMS, lock, h1

def test_sha256sums_so_zips_do_release():
    assert S.parse_sha256sums(SUMS, "3.74.0") == {"darwin_arm64": "aa" * 32, "linux_amd64": "bb" * 32}


@pytest.mark.parametrize("bad", [
    "dd" * 32 + "  terraform-provider-google_3.73.0_darwin_arm64.zip\n",       # outro release
    "dd" * 32 + "  terraform-provider-google-beta_3.74.0_darwin_arm64.zip\n",  # outro provider
    "xyz  terraform-provider-google_3.74.0_darwin_arm64.zip\n",                 # fora do formato
    "dd" * 32 + "  terraform-provider-google_3.74.0_darwin_arm64.zip\n",       # plataforma repetida
])
def test_sha256sums_reprova_linha_estranha(bad):
    with pytest.raises(C.HistError):
        S.parse_sha256sums(SUMS + bad, "3.74.0")


def test_lock_zh_de_todas_as_plataformas_mais_h1_relido():
    lp = S.locked_provider("3.74.0", {"darwin_arm64": "aa" * 32, "linux_amd64": "bb" * 32}, "h1:abc=")
    assert lp.hashes == ("h1:abc=", "zh:" + "aa" * 32, "zh:" + "bb" * 32)
    again = lockfile.find(lockfile.parse(lockfile.render([lp])), C.SOURCE)
    assert again == lp and again.version == again.constraints == "3.74.0"


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    return buf.getvalue()


def test_h1_do_zip_e_o_dirhash_da_pasta_desempacotada(work):
    files = {"terraform-provider-google_v3.74.0_x5": b"binario", "LICENSE.txt": b"licenca"}
    zp = work / "p.zip"
    zp.write_bytes(_zip(files))
    d = work / "unpacked"
    d.mkdir()
    for n, b in files.items():
        (d / n).write_bytes(b)
    assert S.zip_h1(zp) == C.dirhash_h1(d)
    (d / "LICENSE.txt").write_bytes(b"outra")
    assert S.zip_h1(zp) != C.dirhash_h1(d)


def test_h1_do_zip_reprova_nome_que_escapa(work):
    zp = work / "p.zip"
    zp.write_bytes(_zip({"../fora": b"x"}))
    with pytest.raises(C.HistError):
        S.zip_h1(zp)


def test_so_hosts_permitidos():
    with pytest.raises(C.HistError):
        S._get("https://example.com/x")
    with pytest.raises(C.HistError):
        S._get("http://registry.terraform.io/v1/providers")


def test_metadado_de_download_fora_de_releases_reprova():
    meta = {"os": "darwin", "arch": "arm64", "filename": "terraform-provider-google_3.74.0_darwin_arm64.zip",
            "shasum": "aa" * 32, "download_url": "https://releases.hashicorp.com/x.zip",
            "shasums_url": "https://releases.hashicorp.com/s", "shasums_signature_url": "https://releases.hashicorp.com/g"}
    S.check_download_meta(meta, "3.74.0")
    for k in ("download_url", "shasums_url", "shasums_signature_url"):
        bad = dict(meta, **{k: "https://evil.example/x"})
        with pytest.raises(C.HistError):
            S.check_download_meta(bad, "3.74.0")
    with pytest.raises(C.HistError):
        S.check_download_meta(dict(meta, filename="terraform-provider-google_3.74.0_linux_amd64.zip"), "3.74.0")


def test_http_404_com_build_no_indice_nao_vira_indisponivel(monkeypatch, work):
    monkeypatch.setenv("BO_DATA", str(work))
    monkeypatch.setattr(S, "index_platforms", lambda h, v: {"platforms": ["darwin_arm64"], "protocols": ["5.0"],
                                                            "index": "x", "index_sha256": "0" * 64})
    monkeypatch.setattr(S, "_get", lambda url, timeout=120: (404, b'{"errors":["provider platform not found"]}'))
    with pytest.raises(C.HistError):
        S.fetch_and_verify("3.74.0", {}, {})


def test_http_404_sem_build_vira_indisponivel_com_evidencia(monkeypatch, work):
    monkeypatch.setenv("BO_DATA", str(work))
    monkeypatch.setattr(S, "index_platforms", lambda h, v: {"platforms": ["darwin_amd64", "linux_amd64"],
                                                            "protocols": ["5.0"], "index": "$BO_DATA/i.json",
                                                            "index_sha256": "ab" * 32})
    monkeypatch.setattr(S, "_get", lambda url, timeout=120: (404, b'{"errors":["provider platform not found"]}'))
    ch = S.fetch_and_verify("3.62.0", {}, {})
    assert ch["available"] is False and ch["http_status"] == 404
    why = P.unavailable_reason({"version": "3.62.0"}, ch)
    assert "darwin_amd64, linux_amd64" in why and "HTTP 404" in why and "provider platform not found" in why
    assert "nenhum schema foi produzido" in why


# ------------------------------------------------------------------ átomos

def test_atomos_iguais_a_biblioteca_mais_write_only(schema_file, work):
    raw, counts = A.build_bytes(schema_file, "6.0.0")
    mine = [json.loads(x) for x in raw.decode().splitlines()]
    ps = core.providers(core.load(schema_file))
    lib = [a for ts in core.iter_types(ps["google"], "google", "6.0.0") for a in ts.atoms]
    assert len(mine) == len(lib) == counts["atoms"] == 6
    wo = {a["atom_id"] for a in mine if a.get("write_only")}
    assert wo == {"google:google_widget:secret_wo", "google:google_widget:conf.key_wo"}
    for m, b in zip(mine, lib):
        m = dict(m)
        m.pop("write_only", None)
        assert m == b
    assert counts["write_only"] == 2 and counts["types"] == 2 and counts["data_sources"] == 1


def test_atomos_gzip_deterministico_e_valida_c01(schema_file, work):
    a1 = A.write(schema_file, "6.0.0", work / "a1" / "atoms_6.0.0.jsonl.gz")
    a2 = A.write(schema_file, "6.0.0", work / "a2" / "atoms_6.0.0.jsonl.gz")
    assert a1["gz_sha256"] == a2["gz_sha256"] and a1["jsonl_sha256"] == a2["jsonl_sha256"]
    assert (work / "a1" / "atoms_6.0.0.jsonl.gz").read_bytes() == (work / "a2" / "atoms_6.0.0.jsonl.gz").read_bytes()
    from bo.contracts import validate as V
    j = work / "atoms.jsonl"
    j.write_bytes(C.gunzip_bytes(work / "a1" / "atoms_6.0.0.jsonl.gz"))
    assert V.validate("C01_atoms", j).ok


def test_write_only_nao_duplica_se_a_biblioteca_ja_gravar(schema_file):
    ps = core.providers(core.load(schema_file))
    ts = next(t for t in core.iter_types(ps["google"], "google", "6.0.0") if t.resource_type == "google_widget")
    for a in ts.atoms:
        a["write_only"] = a["path"] == "secret_wo"
    assert A.annotate_write_only(ts) == 1
    assert [a["write_only"] for a in ts.atoms].count(True) == 1


# ------------------------------------------------------------------ check (G2) num mundo sintético

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def world(monkeypatch, work, schema_file):
    """BO_REPO/BO_DATA sintéticos: 1.0.0 sem darwin_arm64 (indisponível) e 1.1.0 extraída (pin)."""
    real_repo = Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))
    repo, data = work / "repo", work / "data"
    (repo / "universe").mkdir(parents=True)
    (repo / "contracts").symlink_to(real_repo / "contracts")
    monkeypatch.setenv("BO_REPO", str(repo))
    monkeypatch.setenv("BO_DATA", str(data))
    monkeypatch.setenv("BO_TMP", str(work / "tmp"))
    idx = data / "PINS" / "registry_index"
    (idx / "providers" / "google").mkdir(parents=True)
    v1 = {"versions": [{"version": "1.0.0", "protocols": ["5.0"], "platforms": [{"os": "linux", "arch": "amd64"}]},
                       {"version": "1.1.0", "protocols": ["5.0"], "platforms": [{"os": "darwin", "arch": "arm64"},
                                                                                {"os": "linux", "arch": "amd64"}]}]}
    v1p = idx / "providers" / "google" / "registry-v1-versions.json"
    v1p.write_text(json.dumps(v1), encoding="utf-8")
    fpr = "C874011F0AB405110D02105534365D9472D7468F"
    (idx / "verification.json").write_text(json.dumps({"terraform": {"signature": {"primary_fingerprint": fpr,
                                                                                   "good": True}}}))
    raw = schema_file.read_bytes()
    raw_sha = _sha(raw)
    ref = {"path": "$BO_DATA/PINS/registry_index/providers/google/registry-v1-versions.json", "sha256": _sha(v1p.read_bytes())}
    sel = [{"version": "1.0.0", "published_at": "2021-03-29T20:53:13Z", "released_at": "2021-03-29",
            "reasons": ["quarter_end:2021Q1"], "index_sha256": "0" * 64, "protocols": ["5.0"],
            "darwin_arm64": False, "linux_amd64": True},
           {"version": "1.1.0", "published_at": "2021-06-28T16:47:55Z", "released_at": "2021-06-28",
            "reasons": ["cutoff:2021-06-30"], "index_sha256": "0" * 64, "protocols": ["5.0"],
            "darwin_arm64": True, "linux_amd64": True}]
    hist = {"schema": "bo.history_versions/1", "contract": "C13", "contract_version": "3.1.0", "module": "PINS",
            "generated_at": "2026-11-03T01:37:14-03:00",
            "cutoff": {"date": "2021-06-30", "timezone": "America/Recife", "end_exclusive": "2021-07-01T00:00:00-03:00",
                       "rule": "regra sintética de teste"},
            "window": {"start": "2021-01-01", "rule": "regra sintética de teste"},
            "index": {"path": "$BO_DATA/PINS/registry_index/snapshot.json", "sha256": "0" * 64,
                      "fetched_at": "2026-11-03T01:37:14-03:00"},
            "providers": [{"provider": "google", "source": C.ADDRESS, "pin": "1.1.0",
                           "index_files": {"registry_v1": ref, "registry_v2": ref},
                           "versions_doc": {"schema": "bo.versions/1", "contract": "C13", "contract_version": "3.1.0",
                                            "module": "PINS", "generated_at": "2026-11-03T01:37:14-03:00",
                                            "provider": "google",
                                            "versions": [{"version": s["version"], "released_at": s["released_at"]}
                                                         for s in sel]},
                           "selection": sel,
                           "left_truncation": {"at": "2021-01-01T00:00:00-03:00", "version_in_force": "0.9.0",
                                               "major_in_force": 0, "index_first_version": "0.1.0",
                                               "index_first_published_at": "2017-07-12T17:45:07Z"}}]}
    (repo / "universe" / "history_versions.json").write_text(json.dumps(hist), encoding="utf-8")
    pins = {"terraform": {"version": "1.15.8", "sha256": "f" * 64},
            "providers": [{"provider": "google", "source": C.ADDRESS, "version": "1.1.0", "schema_sha256": raw_sha}]}
    (repo / "universe" / "pins.json").write_text(json.dumps(pins), encoding="utf-8")

    # 1.1.0 extraída
    rd = C.raw_schema_dir("1.1.0")
    rd.mkdir(parents=True)
    (rd / "schema.json.gz").write_bytes(C.gzip_bytes(raw, "schema.json"))
    sums = C.download_dir("1.1.0") / "terraform-provider-google_1.1.0_SHA256SUMS"
    sums.write_text("aa" * 32 + "  terraform-provider-google_1.1.0_darwin_arm64.zip\n")
    at = A.write(rd / "schema.json.gz", "1.1.0", C.atoms_path("1.1.0"))
    lk = S.write_lock(S.locked_provider("1.1.0", {"darwin_arm64": "aa" * 32}, "h1:x="), C.lock_path("1.1.0"))
    rec = {"schema_json": {"sha256": raw_sha},
           "atoms": {**at, "C01_validate": {"ok": True, "records": at["atoms"]}},
           "signed": {"sha256sums": C.portable(sums), "sha256sums_sha256": _sha(sums.read_bytes()),
                      "gpg": {"good": True, "primary_fingerprint": fpr}},
           "lock": {"path": C.portable(lk), "sha256": _sha(lk.read_bytes()), "h1_from_signed_zip": "h1:x="},
           "provider_binary": {"h1": "h1:x=", "sha256": "e" * 64, "deleted_after_extract": True}}
    C.write_json(C.receipt_path("1.1.0"), rec)
    h = C.history()
    results = {"1.0.0": {"status": "unavailable", "reason": "sem build darwin_arm64 publicado: índice sintético " * 2,
                         "evidence": {"index_platforms": ["linux_amd64"]}},
               "1.1.0": {"status": "extracted", "receipt": rec}}
    gen = "2026-11-03T21:00:00-03:00"
    C.write_json(C.out_dir() / "versions.json", P.versions_doc(h, results, gen))
    tf = {"version": "1.15.8", "binary_sha256": "e" * 64, "zip_sha256": "f" * 64}
    key = {"path": idx / "k.txt", "sha256": "d" * 64, "primary_fingerprint": fpr}
    C.write_json(C.out_dir() / "extraction.json", P.extraction_doc(h, C.pins(), tf, key, results, gen))
    return {"repo": repo, "data": data, "hist": hist}


def _fails(**kw):
    r = K.run(**kw)
    return r.fails


def test_check_passa_no_mundo_sintetico(world):
    assert _fails() == []
    xd = json.loads((C.out_dir() / "extraction.json").read_text())
    assert xd["totals"] == {"listed": 2, "extracted": 1, "unavailable": 1} and xd["first_extracted"] == "1.1.0"
    vd = json.loads((C.out_dir() / "versions.json").read_text())
    assert "schema_sha256" not in vd["versions"][0] and vd["versions"][1]["schema_sha256"]


def _edit(p: Path, fn):
    d = json.loads(p.read_text())
    fn(d)
    p.write_text(json.dumps(d))


def test_check_reprova_indisponivel_sem_motivo(world):
    _edit(C.out_dir() / "extraction.json", lambda d: d["versions"][0].update(reason=""))
    assert any("sem motivo" in f for f in _fails())


def test_check_reprova_situacao_desconhecida(world):
    _edit(C.out_dir() / "extraction.json", lambda d: d["versions"][0].update(status="skipped"))
    assert any("nem extraída nem com motivo" in f for f in _fails())


def test_check_reprova_datas_que_voltam(world):
    def back(d):
        p = d["providers"][0]
        p["selection"][1]["released_at"] = "2021-03-01"
        p["selection"][1]["published_at"] = "2021-03-01T12:00:00Z"
        p["versions_doc"]["versions"][1]["released_at"] = "2021-03-01"
    _edit(world["repo"] / "universe" / "history_versions.json", back)
    fails = _fails()
    assert any("released_at decresce" in f for f in fails) and any("published_at não cresce" in f for f in fails)


def test_check_reprova_versao_faltando_no_versions(world):
    _edit(C.out_dir() / "versions.json", lambda d: d["versions"].pop(0))
    assert any("difere da lista do PINS" in f for f in _fails())


def test_check_reprova_atomo_adulterado(world):
    p = C.atoms_path("1.1.0")
    lines = C.gunzip_bytes(p).decode().splitlines()
    a = json.loads(lines[0])
    a["required"] = not a["required"]
    lines[0] = json.dumps(a, sort_keys=True)
    p.write_bytes(C.gzip_bytes(("\n".join(lines) + "\n").encode(), "atoms_1.1.0.jsonl"))
    assert any("gzip dos átomos diverge" in f for f in _fails())


def test_check_reprova_indisponivel_com_atomos(world):
    p = C.atoms_path("1.0.0")
    p.write_bytes(C.atoms_path("1.1.0").read_bytes())
    assert any("unavailable com arquivo de átomos" in f for f in _fails())


def test_check_reprova_indisponivel_que_o_indice_diz_ter_build(world):
    def plat(d):
        d["versions"][0]["platforms"].append({"os": "darwin", "arch": "arm64"})
    p = C.pins_index_dir() / "providers" / "google" / "registry-v1-versions.json"
    _edit(p, plat)
    _edit(world["repo"] / "universe" / "history_versions.json",
          lambda d: d["providers"][0]["index_files"]["registry_v1"].update(sha256=_sha(p.read_bytes())))
    assert any("dizem que há darwin_arm64" in f for f in _fails())


def test_check_reprova_pin_com_outro_schema(world):
    _edit(world["repo"] / "universe" / "pins.json", lambda d: d["providers"][0].update(schema_sha256="0" * 64))
    assert any("!= pins.json" in f for f in _fails())


def test_check_reprova_binario_esquecido(world):
    d = E.provider_dir("1.1.0")
    d.mkdir(parents=True)
    (d / "terraform-provider-google_v1.1.0_x5").write_bytes(b"x")
    assert any("ainda no disco" in f for f in _fails())


def test_check_reprova_lock_alterado(world):
    p = C.lock_path("1.1.0")
    p.write_text(p.read_text().replace("h1:x=", "h1:y="))
    assert any("lock ausente, alterado" in f for f in _fails())


def test_check_reprova_schema_cru_trocado(world):
    rd = C.raw_schema_dir("1.1.0") / "schema.json.gz"
    doc = json.loads(C.gunzip_bytes(rd))
    doc2 = copy.deepcopy(doc)
    doc2["format_version"] = "1.1"
    rd.write_bytes(C.gzip_bytes(json.dumps(doc2).encode(), "schema.json"))
    assert any("saída crua não tem o sha" in f for f in _fails())


def test_data_recife():
    assert K.recife_date("2021-10-01T01:01:31Z") == "2021-09-30"
    assert K.recife_date("2021-06-28T16:47:55Z") == "2021-06-28"
