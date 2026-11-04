"""bo.hist_oci.check em saídas sintéticas: o caso coerente passa e cada defeito plantado reprova."""
import dataclasses
import gzip
import json

import pytest

from bo.hist_oci import check, common

from .conftest import hist3, write_outputs


@pytest.fixture
def setup(work, monkeypatch):
    hist = hist3()
    out, schemas = work / "out", work / "schemas"
    write_outputs(out, schemas, hist)
    real = common.gz_sha256
    monkeypatch.setattr(common, "gz_sha256", lambda p: "c" * 64 if gzip.open(p).read() == b"pin" else real(p))
    run = lambda h=hist: check.check(h, out, schema_dir=lambda v: schemas / f"oci-{v}",  # noqa: E731
                                     binary_dirs=lambda h: [work / "bin"], validate=True)
    return hist, out, schemas, run, work


def test_coerente_passa(setup):
    hist, out, schemas, run, work = setup
    probs, counts = run()
    assert probs == []
    assert counts == {"extracted": 2, "not_extracted": 1, "listed": 3}


def _edit(p, fn):
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d), encoding="utf-8")


def test_versao_sem_registro_reprova(setup):
    hist, out, schemas, run, work = setup
    _edit(out / "extraction.json", lambda d: d["versions"].pop(1))
    assert any("1.1.0: sem registro" in p for p in run()[0])


def test_versao_faltando_no_versions_json_reprova(setup):
    hist, out, schemas, run, work = setup
    _edit(out / "versions.json", lambda d: d["versions"].pop(0))
    assert any("versions.json != lista histórica" in p for p in run()[0])


def test_not_extracted_sem_motivo_reprova(setup):
    hist, out, schemas, run, work = setup
    _edit(out / "extraction.json", lambda d: d["versions"][0].update(motivo=" "))
    assert any("1.0.0: not_extracted sem motivo" in p for p in run()[0])


def test_estado_pendente_reprova(setup):
    hist, out, schemas, run, work = setup
    _edit(out / "extraction.json", lambda d: d["versions"][0].update(status="pending"))
    assert any("estado 'pending'" in p for p in run()[0])


def test_datas_nao_monotonas_reprovam(setup):
    hist, out, schemas, run, work = setup
    vs = list(hist.versions)
    vs[1] = dataclasses.replace(vs[1], released_at="2021-12-31")
    bad = dataclasses.replace(hist, versions=tuple(vs))
    _edit(out / "versions.json", lambda d: d["versions"][1].update(released_at="2021-12-31"))
    assert any("released_at decresce" in p for p in run(bad)[0])


def test_atomos_adulterados_reprovam(setup):
    hist, out, schemas, run, work = setup
    ap = out / "atoms_1.1.0.jsonl.gz"
    with gzip.open(ap, "wb") as g:
        g.write(b'{"provider": "oci", "provider_version": "9.9.9"}\n')
    probs = run()[0]
    assert any("não bate com atoms_gz_sha256" in p for p in probs)
    assert any("outra versão ou provedor" in p for p in probs)


def test_schema_ausente_reprova(setup):
    hist, out, schemas, run, work = setup
    (schemas / "oci-1.1.0" / "schema.json.gz").unlink()
    assert any("1.1.0: schema extraído ausente" in p for p in run()[0])


def test_pin_nao_extraido_reprova(setup):
    hist, out, schemas, run, work = setup
    _edit(out / "extraction.json", lambda d: d["versions"][2].update(status="not_extracted", motivo="x" * 30))
    assert any("pin 2.0.0 não extraído" in p for p in run()[0])


def test_pin_com_schema_diferente_reprova(work, monkeypatch):
    hist = hist3()
    out, schemas = work / "out", work / "schemas"
    write_outputs(out, schemas, hist, schema_shas={"2.0.0": "f" * 64})
    probs, _ = check.check(hist, out, schema_dir=lambda v: schemas / f"oci-{v}", binary_dirs=lambda h: [],
                           validate=False)
    assert any("pin 2.0.0: schema_sha256 != lista histórica" in p for p in probs)


def test_truncamento_divergente_reprova(setup):
    hist, out, schemas, run, work = setup
    _edit(out / "extraction.json", lambda d: d["left_truncation"].update(index_first_version="0.9.0"))
    assert any("left_truncation registrado" in p for p in run()[0])


def test_binario_que_sobrou_reprova(setup):
    hist, out, schemas, run, work = setup
    (work / "bin").mkdir()
    (work / "bin" / "terraform-provider-oci_v1.1.0").write_bytes(b"\x00")
    assert any("binário não apagado" in p for p in run()[0])


def test_not_extracted_com_atomos_reprova(setup):
    hist, out, schemas, run, work = setup
    common.write_gz(out / "versions.json", out / "atoms_1.0.0.jsonl.gz", "x")
    assert any("not_extracted mas atoms_1.0.0.jsonl.gz existe" in p for p in run()[0])
