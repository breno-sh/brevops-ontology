"""Cenário plantado (BO_DATA sintético): renomes publicados e por ponte de depreciação são achados, mudanças de
contrato saem por campo com antes/depois, a data sai como intervalo (after, until] que atravessa a lacuna, e o
que não tem prova fica como remoção + adição com candidato UNPROVEN."""
import json
from pathlib import Path

import pytest

from bo.contracts import validate as V
from bo.drift import build, common
from conftest import atom, write_guide, write_hist

P, RT = "aws", "aws_widget"
GUIDE_DIR = common.PROVIDERS["aws"][3]
GUIDE = """---
subcategory: ""
---
# Version 2 Upgrade Guide

## Provider Arguments

`old_size` has been renamed to `size_gb` (fora de seção de tipo: não conta).

## resource/aws_widget

`old_size` has been renamed to `size_gb`.

`legacy_flag` has been removed in favor of `flag_mode`.

```hcl
# `tier` has been renamed to `tier2` (bloco de código: não conta)
```

## data-source/aws_widget

`color` has been renamed to `colour` (data source: não conta).
"""


def a(path, **kw):
    return atom(P, RT, path, **kw)


def scenario():
    base = [a("name", required=True, optional=False), a("tier", required=True, optional=False),
            a("mode"), a("endpoint"), a("secret"), a("retention", tf_type="number"), a("zone"),
            a("color"), a("legacy_flag", tf_type="bool"),
            a("config.level", nesting="list", block_path=[{"block": "config", "nesting_mode": "list"}])]
    v100 = base + [a("old_size", tf_type="number"), a("subnet"), a("beta")]
    v150 = base + [a("old_size", tf_type="number"), a("subnet", deprecated=True), a("subnet_id")]
    common_2 = [x for x in base if x["path"] not in ("color", "legacy_flag")] + [
        a("size_gb", tf_type="number"), a("subnet_id"), a("beta"), a("colour"), a("flag_mode")]
    v200 = common_2
    v230 = [x for x in common_2 if x["path"] not in ("mode", "tier", "endpoint", "secret", "retention", "zone",
                                                     "config.level")] + [
        a("mode", tf_type="number"), a("tier"), a("endpoint", computed=True), a("secret", sensitive=True),
        a("retention_days", tf_type="number"), a("zone_a"), a("zone_b"),
        a("config.level", nesting="set", block_path=[{"block": "config", "nesting_mode": "set"}])]
    return {"1.0.0": v100, "1.5.0": v150, "2.0.0": v200, "2.3.0": v230}


@pytest.fixture
def out(work, monkeypatch):
    data = work / "data"
    write_hist(data, "HIST-AWS", P, scenario(), missing=("1.8.0",))
    write_guide(data, GUIDE_DIR, "version-2-upgrade.html.markdown", GUIDE)
    monkeypatch.setenv("BO_DATA", str(data))
    o = work / "out"
    build.build(o, ["aws"], jobs=1)
    return o


def _events(o):
    return [json.loads(l) for l in (o / "events.jsonl").read_text().splitlines()]


def _ev(evs, etype, atom_id=None, **kw):
    out = []
    for e in evs:
        if e["event_type"] != etype:
            continue
        if atom_id and e.get("atom_id") != f"{P}:{RT}:{atom_id}":
            continue
        if all(e.get(k) == f"{P}:{RT}:{v}" for k, v in kw.items()):
            out.append(e)
    return out


def _iv(e):
    return (e["version_interval"]["after"], e["version_interval"]["until"])


def test_saidas_conferem_c13_e_c15(out):
    for kind, f in (("events", "events.jsonl"), ("atom_history", "atom_history.jsonl")):
        res = V.validate("versions", out / f)
        assert res.ok, (f, res.errors[:5])
    assert V.validate("results", out / "churn.json").ok


def test_renome_publicado_achado_e_intervalo_atravessa_a_lacuna(out):
    evs = _events(out)
    r = _ev(evs, "rename", from_atom="old_size", to_atom="size_gb")
    assert len(r) == 1
    assert _iv(r[0]) == ("1.5.0", "2.0.0")          # 1.8.0 é lacuna: o intervalo a abrange
    doc = r[0]["evidence"][0]
    assert doc["level"] == "published"
    assert doc["doc"]["file"] == "website/docs/guides/version-2-upgrade.html.markdown"
    line = GUIDE.splitlines().index("`old_size` has been renamed to `size_gb`.") + 1
    assert doc["doc"]["line"] == line and "renamed" in doc["doc"]["sentence"]
    # o renome substitui a remoção e a adição do mesmo intervalo
    assert not _ev(evs, "removal", "old_size") and not _ev(evs, "addition", "size_gb")


def test_renome_por_ponte_de_depreciacao(out):
    evs = _events(out)
    r = _ev(evs, "rename", from_atom="subnet", to_atom="subnet_id")
    assert len(r) == 1 and _iv(r[0]) == ("1.5.0", "2.0.0")
    assert r[0]["evidence"][0]["level"] == "derived" and "R2" in r[0]["evidence"][0]["ref"]
    add = _ev(evs, "addition", "subnet_id")
    assert len(add) == 1 and _iv(add[0]) == ("1.0.0", "1.5.0")
    dep = [e for e in _ev(evs, "contract_change", "subnet") if e["change"]["field"] == "deprecated"]
    assert len(dep) == 1 and dep[0]["change"] == {"field": "deprecated", "before": False, "after": True}
    assert _iv(dep[0]) == ("1.0.0", "1.5.0")


@pytest.mark.parametrize("path,fld,before,after", [
    ("mode", "tf_type", "string", "number"),
    ("tier", "required", True, False),
    ("tier", "optional", False, True),
    ("endpoint", "computed", False, True),
    ("secret", "sensitive", False, True),
    ("config.level", "nesting", "list", "set"),
    ("config.level", "block_path", [{"block": "config", "nesting_mode": "list"}],
     [{"block": "config", "nesting_mode": "set"}]),
])
def test_mudancas_de_contrato_plantadas(out, path, fld, before, after):
    cc = [e for e in _ev(_events(out), "contract_change", path) if e["change"]["field"] == fld]
    assert len(cc) == 1
    assert cc[0]["change"] == {"field": fld, "before": before, "after": after}
    assert _iv(cc[0]) == ("2.0.0", "2.3.0")


def test_sem_prova_fica_remocao_e_adicao_com_candidato(out):
    evs = _events(out)
    assert _ev(evs, "removal", "retention") and _ev(evs, "addition", "retention_days")
    assert not _ev(evs, "rename", from_atom="retention")
    cands = [json.loads(l) for l in (out / "rename_candidates.jsonl").read_text().splitlines()]
    st = {(c["from_atom"].split(":")[-1], c["to_atom"].split(":")[-1]): c["status"] for c in cands}
    assert st[("retention", "retention_days")] == "UNPROVEN"
    assert st[("zone", "zone_a")] == st[("zone", "zone_b")] == "AMBIGUOUS"
    assert st[("legacy_flag", "flag_mode")] == "REPLACEMENT_TYPE_CHANGED"
    assert not _ev(evs, "rename", from_atom="zone") and not _ev(evs, "rename", from_atom="legacy_flag")


def test_frases_fora_de_secao_codigo_e_data_source_nao_contam(out):
    evs = _events(out)
    assert not _ev(evs, "rename", from_atom="color")
    assert _ev(evs, "removal", "color") and _ev(evs, "addition", "colour")


def test_truncamento_a_esquerda_e_reaparecimento(out):
    evs = _events(out)
    assert not _ev(evs, "addition", "name")          # já estava na 1ª versão observada
    rm, ad = _ev(evs, "removal", "beta"), _ev(evs, "addition", "beta")
    assert [_iv(e) for e in rm] == [("1.0.0", "1.5.0")] and [_iv(e) for e in ad] == [("1.5.0", "2.0.0")]
    hist = {json.loads(l)["atom_id"]: json.loads(l) for l in (out / "atom_history.jsonl").read_text().splitlines()}
    b = hist[f"{P}:{RT}:beta"]
    assert [h["state"] for h in b["history"]] == ["present", "absent", "present", "present"]
    assert b["first_seen"] == "1.0.0" and b["last_seen"] == "2.3.0"
    assert all(h["version"] != "1.8.0" for r in hist.values() for h in r["history"])   # lacuna não vira estado
    sid = {e["event_id"] for e in evs if f"{P}:{RT}:subnet_id" in (e.get("atom_id"), e.get("to_atom"))}
    assert set(hist[f"{P}:{RT}:subnet_id"]["events"]) == sid and len(sid) == 2


def test_churn_declara_lacuna_truncamento_e_campos_inobservaveis(out):
    c = json.loads((out / "churn.json").read_text())
    p = c["data"]["providers"]["aws"]
    assert [g["version"] for g in p["gaps"]] == ["1.8.0"] and "unavailable" in p["gaps"][0]["reason"]
    iv = {(i["after"], i["until"]): i for i in p["intervals"]}
    assert iv[("1.5.0", "2.0.0")]["spans_gap"] == ["1.8.0"]
    assert iv[("1.5.0", "2.0.0")]["days"] > 0
    assert p["left_truncation"]["first_observed"] == "1.0.0"
    assert set(c["data"]["unobservable_fields"]) == {"force_new", "default"}
    assert p["renames_by_rule"] == {"R1_published": 1, "R2_derived": 1}
    assert c["data"]["totals"]["events"] == len(_events(out))


def test_regeneracao_identica(out, work):
    o2 = work / "out2"
    build.build(o2, ["aws"], jobs=1)
    for f in ("events.jsonl", "atom_history.jsonl", "rename_candidates.jsonl"):
        assert (out / f).read_bytes() == (o2 / f).read_bytes(), f
    ev = _events(out)
    assert len({e["event_id"] for e in ev}) == len(ev)
