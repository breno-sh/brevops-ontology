"""Peças do HIST-OCI: lista histórica real, gzip determinístico, fontes de download, motivo de release ausente."""
import urllib.error

import pytest

from bo.hist_oci import atoms, chain, common, pipeline


def test_lista_historica_real_do_pins():
    h = common.read_history()
    vs = [lv.version for lv in h.versions]
    assert len(vs) == 25 and vs[0] == "4.67.3" and vs[-1] == h.pin == "9.11.0"
    assert h.left_truncation["index_first_version"] == "4.67.3"
    assert h.left_truncation["version_in_force"] is None
    assert h.versions[-1].schema_sha256 and not any(lv.schema_sha256 for lv in h.versions[:-1])
    assert [common.semver_key(v) for v in vs] == sorted(common.semver_key(v) for v in vs)


def test_gzip_deterministico(work):
    src = work / "a.jsonl"
    src.write_text('{"x": 1}\n' * 1000, encoding="utf-8")
    common.write_gz(src, work / "1.gz", "a.jsonl")
    common.write_gz(src, work / "2.gz", "a.jsonl")
    assert common.sha256_file(work / "1.gz") == common.sha256_file(work / "2.gz")
    assert common.gz_sha256(work / "1.gz") == common.sha256_file(src)


@pytest.mark.parametrize("url", ["https://example.org/x", "http://registry.terraform.io/v1/providers/oracle/oci/1",
                                 "https://github.com/outro/repo/releases/download/v1/x"])
def test_url_fora_das_fontes_reprova(url):
    with pytest.raises(chain.TrustError):
        chain._get(url, (common.REGISTRY_PREFIX, common.RELEASE_PREFIX))


def test_fetch_zip_reprova_url_de_outra_versao(work):
    with pytest.raises(chain.TrustError):
        chain.fetch_zip(common.RELEASE_PREFIX + "v1.0.0/x.zip", work / "x.zip", "a" * 64, "2.0.0")


def test_release_ausente_nao_e_repetido(monkeypatch):
    calls = []

    def boom():
        calls.append(1)
        raise chain.Unavailable("release apagado")
    with pytest.raises(chain.Unavailable):
        pipeline._with_retries(boom, "x")
    assert calls == [1]


def test_erro_de_rede_e_repetido(monkeypatch):
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.URLError("rede")
        return "ok"
    assert pipeline._with_retries(flaky, "x") == "ok" and len(calls) == 3


def test_motivo_de_release_ausente_cita_url_e_codigo(monkeypatch):
    def fake(url, allowed, timeout=60):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(chain, "_get", fake)
    m = chain.release_gone("4.67.3", "https://github.com/oracle/terraform-provider-oci/releases/download/v4.67.3/S", 404)
    assert "HTTP 404" in m and "v4.67.3" in m and "responde 404" in m


def _attr(t, **f):
    return {"type": t, "description_kind": "plain", **f}


def _schema(wo=False):
    return {"format_version": "1.0", "provider_schemas": {common.ADDRESS: {
        "provider": {"version": 0, "block": {}},
        "resource_schemas": {"oci_x": {"version": 0, "block": {
            "attributes": {"id": _attr("string", optional=True, computed=True),
                           "senha": _attr("string", optional=True, sensitive=True,
                                          **({"write_only": True} if wo else {}))},
            "block_types": {"r": {"nesting_mode": "list", "block": {"attributes": {"d": _attr("number", optional=True)}}}}}}},
        "data_source_schemas": {"oci_xs": {"version": 0, "block": {}}}}}}


@pytest.mark.parametrize("wo", [False, True])
def test_atomos_e_write_only(work, wo):
    import gzip
    import json
    gz = work / "schema.json.gz"
    with gzip.open(gz, "wb") as g:
        g.write(json.dumps(_schema(wo)).encode())
    r = atoms.make(gz, "1.2.3", work / "atoms.jsonl", work / "types.jsonl")
    assert (r["types"], r["atoms"], r["data_sources"], r["write_only"]) == (1, 3, 1, int(wo))
    rows = [json.loads(x) for x in (work / "atoms.jsonl").read_text().splitlines()]
    assert {a["provider_version"] for a in rows} == {"1.2.3"}
    assert sum(bool(a.get("write_only")) for a in rows) == int(wo)
