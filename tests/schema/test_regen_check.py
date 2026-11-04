"""bo.schema.regen_check: a emenda só acrescenta átomos de elemento; átomo publicado que muda reprova."""
import gzip
import hashlib
import json

from bo.schema import core, regen_check

from conftest import schema_doc


def publish(work, monkeypatch, tamper=None):
    monkeypatch.setenv("BO_DATA", str(work))
    monkeypatch.setenv("BO_TMP", str(work / "tmp"))
    monkeypatch.setitem(regen_check.PRODUCER, "provider_a", "SCHEMA-A")
    doc = schema_doc()
    raw = json.dumps(doc).encode()
    d = work / "downloads" / "tfschema" / "provider_a-1.0.0"
    d.mkdir(parents=True)
    with gzip.open(d / "schema.json.gz", "wb") as f:
        f.write(raw)
    (d / "schema.json.sha256").write_text(f"{hashlib.sha256(raw).hexdigest()}  schema.json\n")
    types = list(core.iter_types(core.providers(doc)["provider_a"], "provider_a", "1.0.0"))
    pub = work / "SCHEMA-A"
    atoms = [a for t in types for a in t.atoms]                  # saída de antes da emenda: sem elementos
    if tamper:
        atoms = tamper(atoms)
    core.write_jsonl(pub / "atoms.jsonl", atoms)
    core.write_jsonl(pub / "types.jsonl", (core.type_record(t) for t in types))


def test_only_element_atoms_are_added(work, monkeypatch):
    publish(work, monkeypatch)
    r = regen_check.check("provider_a")
    assert r["ok"], r
    assert (r["n_ausentes"], r["n_diferentes"], r["atomos_novos"], r["types_identico"]) == (0, 0, 1, True)


def test_changed_published_atom_fails(work, monkeypatch):
    def tamper(atoms):
        atoms[0] = dict(atoms[0], sensitive=not atoms[0]["sensitive"])
        return atoms
    publish(work, monkeypatch, tamper)
    r = regen_check.check("provider_a")
    assert not r["ok"] and r["n_diferentes"] == 1


def test_published_atom_missing_fails(work, monkeypatch):
    publish(work, monkeypatch, lambda atoms: atoms + [dict(atoms[0], atom_id="provider_a:provider_a_gadget:ghost",
                                                           path="ghost")])
    r = regen_check.check("provider_a")
    assert not r["ok"] and r["n_ausentes"] == 1
