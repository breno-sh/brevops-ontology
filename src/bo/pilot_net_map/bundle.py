"""Leitura e conferência do pacote fechado do mapeador (saída PILOT-NET-GLOSS/bundle).

Aceita as duas formas que o glossarista produz:
  oficial     MANIFEST.sha256 + candidates, canonical_atoms, canonical_units, claims, decisions, glossary,
              value_space (MAPPER_BRIEF M11)
  diagnóstico bundle.json (mapa de sha256) + atoms.jsonl (tipo e papel do C01) e service_evidence.jsonl (C25)
Confere o hash de cada arquivo antes de ler e recusa arquivo fora da lista (o mapeador não procura nada fora
do pacote). Tipos de valor vêm de value_space.jsonl (C05) ou, sem ele, de atoms.jsonl; árvore (lista, mapa) não
tem datatype no C05/C09 e fica sem tipo (o árbitro devolve KIND-UNKNOWN). Evidência por átomo: só sentença com
nível published e fonte na tag fixada (âncoras do glossário, fatos do C25 ou do C05); interpreted nunca entra.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .common import UNGLOSSED, load_jsonl, path_of, provider_of, sha256_file, type_of

OFFICIAL = ("candidates.jsonl", "canonical_atoms.jsonl", "canonical_units.jsonl", "claims.jsonl",
            "decisions.jsonl", "glossary.jsonl", "value_space.jsonl")
DIAGNOSTIC_EXTRA = ("anchor_paths.jsonl", "atoms.jsonl", "service_evidence.jsonl", "slice_notes.jsonl")
EVIDENCE_DATE = "2026-11-04"


class BundleError(ValueError):
    pass


def _manifest(root: Path) -> tuple[str, dict[str, str]]:
    m = root / "MANIFEST.sha256"
    if m.exists():
        want = {}
        for line in m.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            sha, rel = line.split(None, 1)
            want[Path(rel.strip()).name] = sha
        return "MANIFEST.sha256", want
    b = root / "bundle.json"
    if b.exists():
        return "bundle.json", dict(json.loads(b.read_text(encoding="utf-8"))["files"])
    raise BundleError(f"{root}: pacote sem MANIFEST.sha256 nem bundle.json")


def verify(root: Path) -> dict:
    """Confere os hashes; devolve {form, files: {nome: sha}, manifest_sha256}."""
    root = Path(root)
    if not root.is_dir():
        raise BundleError(f"pacote ausente: {root}")
    form, want = _manifest(root)
    bad = []
    for name, sha in sorted(want.items()):
        p = root / name
        if not p.exists():
            bad.append(f"{name}: ausente")
        elif sha256_file(p) != sha:
            bad.append(f"{name}: sha256 não confere")
    allowed = set(OFFICIAL) | set(DIAGNOSTIC_EXTRA) | {"MANIFEST.sha256", "bundle.json"}
    extra = sorted(p.name for p in root.iterdir() if p.name not in allowed and not p.name.startswith("."))
    if extra:
        bad.append(f"arquivos fora do pacote declarado: {extra}")
    if bad:
        raise BundleError("; ".join(bad))
    return {"form": "official" if form == "MANIFEST.sha256" else "diagnostic", "files": want,
            "manifest_sha256": sha256_file(root / form)}


def value_type(rec: dict) -> dict | None:
    """Registro do C05 (ou do C01 com tipo) -> tipo de valor do C09; árvore -> None (sem datatype no C05)."""
    dt = rec.get("datatype") or {}
    if dt.get("kind") != "scalar":
        return None
    t = {"datatype": dt["scalar"], "quantity_kind": rec.get("quantity_kind", "UNKNOWN"),
         "unit": rec.get("unit_qudt", rec.get("unit", "UNKNOWN"))}
    if rec.get("enum") is not None:
        t["enum"] = list(rec["enum"])
    if rec.get("range") is not None:
        t["range"] = {k: v for k, v in rec["range"].items() if k in ("min", "max", "step")}
    for k in ("byte_convention", "rate_window"):
        if rec.get(k) not in (None, "NOT_APPLICABLE"):
            t[k] = rec[k]
    return t


def _src(doc: dict) -> str:
    return f"{doc['repo']}/{doc['file']}:{doc['line']}@{doc['tag']}"


@dataclass
class Bundle:
    root: Path
    info: dict
    domain: str
    types_by_provider: dict[str, list[str]]
    canonical: dict[str, dict]                     # atom_id -> registro C19 (papel, unidade)
    types: dict[str, dict | None]                  # atom_id -> tipo de valor do C09 (ou None)
    concept_of: dict[str, str]                     # atom_id -> conceito da âncora
    anchor_of: dict[str, dict]                     # atom_id -> âncora (C20)
    evidence: dict[str, list[dict]]                # atom_id -> [{source, sentence, date}] (published)
    ref_target: dict[str, str]                     # atom_id -> tipo de recurso que a referência alcança
    candidates: list[dict]
    concepts: dict[str, dict]
    se_by_type: dict[str, list[dict]] = field(default_factory=dict)

    def provider_atoms(self, prov: str) -> list[str]:
        return sorted(a for a in self.canonical if provider_of(a) == prov)

    def concept(self, atom: str) -> str:
        return self.concept_of.get(atom, UNGLOSSED)

    def has_atom(self, atom: str) -> bool:
        return atom in self.canonical or atom in self.types

    def has_type(self, rtype_ref: str) -> bool:
        prov, rt = rtype_ref.split(":", 1)
        return rt in self.types_by_provider.get(prov, [])


def load(root: Path) -> Bundle:
    root = Path(root)
    info = verify(root)
    rd = lambda n: load_jsonl(root / n) if (root / n).exists() else []
    canonical = {r["atom_id"]: r for r in rd("canonical_atoms.jsonl")}
    if not canonical:
        raise BundleError("pacote sem canonical_atoms.jsonl")
    types: dict[str, dict | None] = {}
    evidence: dict[str, list[dict]] = {}

    def add_ev(atom, doc, level, note=""):
        if level != "published" or not doc or not doc.get("sentence"):
            return
        e = {"source": _src(doc), "sentence": doc["sentence"], "date": EVIDENCE_DATE}
        if note:
            e["note"] = note
        lst = evidence.setdefault(atom, [])
        if all(x["source"] != e["source"] or x["sentence"] != e["sentence"] for x in lst):
            lst.append(e)

    for r in rd("value_space.jsonl"):
        types[r["atom_id"]] = value_type(r)
        for ev in r.get("evidence") or []:
            add_ev(r["atom_id"], ev.get("doc"), ev.get("level"), "C05")
    for r in rd("atoms.jsonl"):
        if r["atom_id"] not in types:
            d = dict(r)
            if "datatype" in d and isinstance(d["datatype"], dict):
                types[r["atom_id"]] = value_type(d)
    concept_of, anchor_of = {}, {}
    for c in rd("claims.jsonl"):
        a = c.get("atom_id")
        if not a:
            continue
        concept_of[a] = c["concept_id"]
        anchor_of[a] = c
        if c.get("evidence_level") == "published" and c.get("extraction_method") != "model":
            add_ev(a, c.get("source"), "published", c["claim_id"])
    ref_target: dict[str, str] = {}
    se_by_type: dict[str, list[dict]] = {}
    for s in rd("service_evidence.jsonl"):
        rt = s.get("terraform_resource_type")
        se_by_type.setdefault(f"{s['provider']}:{rt}", []).append(s)
        v = s.get("value") or {}
        attr = v.get("attribute")
        if not attr:
            continue
        atom = f"{s['provider']}:{rt}:{attr}"
        if v.get("aspect") == "reference_target" and v.get("resolved"):
            ref_target[atom] = v["resolved"]
        if s.get("status") == "stated":
            add_ev(atom, s.get("doc"), s.get("level"), s["evidence_id"])
    meta = json.loads((root / "bundle.json").read_text(encoding="utf-8")) if (root / "bundle.json").exists() else {}
    tbp: dict[str, list[str]] = {}
    for a in canonical:
        tbp.setdefault(provider_of(a), [])
        if type_of(a) not in tbp[provider_of(a)]:
            tbp[provider_of(a)].append(type_of(a))
    for prov, lst in (meta.get("types") or {}).items():
        for t in lst:
            if t not in tbp.setdefault(prov, []):
                tbp[prov].append(t)
    return Bundle(root=root, info=info, domain=meta.get("domain", "NET"),
                  types_by_provider={k: sorted(v) for k, v in tbp.items()}, canonical=canonical, types=types,
                  concept_of=concept_of, anchor_of=anchor_of, evidence=evidence, ref_target=ref_target,
                  candidates=rd("candidates.jsonl"), concepts={g["concept_id"]: g for g in rd("glossary.jsonl")},
                  se_by_type=se_by_type)


__all__ = ["Bundle", "BundleError", "load", "verify", "value_type", "path_of"]
