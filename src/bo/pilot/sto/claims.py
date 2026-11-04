"""Alegações do PILOT-STO-MAP (C09 3.0.0 SSSOM + C21 vereditos) vistas por direção.

Só alegação com veredito OK (na versão vigente da alegação) pode transportar valor. As demais ficam visíveis para
o rastro (C23) com o código de bloqueio do veredito: UNPROVEN/CONTESTED -> UNPROVEN, REFUTED_BY_RULE ->
REFUTED_BY_RULE, AMBIGUOUS -> AMBIGUOUS_TARGET. Linha de ausência (object_id = sssom:NoTermFound) não é
correspondência: só registra o conceito do átomo e a ausência demonstrada ou não.

Direção: a alegação é sujeito -> objeto num par não ordenado; na direção inversa a relação SKOS é espelhada
(broad <-> narrow; exact, close e related são simétricas), a orientação do domínio de valores é trocada e a
transformação vira a inversa parcial do registro do C10 (sem inversa: não transporta, TRANSFORM_OUT_OF_DOMAIN).
Direção SKOS (corrigida na v3): "a skos:broadMatch b" = b mais amplo.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import common as C

JSON_COLS = ("value_domain_relation", "guard", "translation_fn", "loss_contract", "projection", "proof",
             "subject_value_type", "object_value_type", "absence", "membership_predicate")
NO_TERM = "sssom:NoTermFound"
UNGLOSSED = "bo:UNGLOSSED"
VERDICT_BLOCK = {"UNPROVEN": "UNPROVEN", "CONTESTED": "UNPROVEN", "REFUTED_BY_RULE": "REFUTED_BY_RULE",
                 "AMBIGUOUS": "AMBIGUOUS_TARGET"}
MIRROR = {"exact": "exact", "close": "close", "related": "related", "broad": "narrow", "narrow": "broad"}
DOMAIN_MIRROR = {"equal": "equal", "subset": "superset", "superset": "subset", "overlap": "overlap",
                 "disjoint": "disjoint", "unknown": "unknown"}


def _json(v):
    if v is None or v == "":
        return None
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v


@dataclass
class Claim:
    row: dict
    claim_id: str
    claim_version_id: str
    subject_id: str
    object_id: str
    predicate_id: str
    semantic_relation: str
    transport_fidelity: str
    verdict: str
    verdict_rec: dict = field(default_factory=dict)

    @property
    def is_absence(self) -> bool:
        return self.object_id == NO_TERM

    def col(self, name):
        return self.row.get(name)


@dataclass
class View:
    """A alegação lida numa direção: de (src_atom) para (dst_atom)."""
    claim: Claim
    inverse: bool
    src_atom: str
    dst_atom: str
    relation: str
    domain_relation: str
    translation_fn: dict | None
    loss_contract: list
    guard: dict
    membership_predicate: object

    @property
    def claim_ref(self) -> str:
        return self.claim.claim_id + ("~inv" if self.inverse else "")


def read_sssom(p: Path) -> tuple[dict, list[dict]]:
    meta_lines, body = [], []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            (meta_lines if line.startswith("#") else body).append(line)
    rows = list(csv.DictReader(io.StringIO("".join(body)), delimiter="\t"))
    for r in rows:
        for c in JSON_COLS:
            if c in r:
                r[c] = _json(r[c])
    return {"header_lines": len(meta_lines)}, rows


def read_verdicts(p: Path) -> dict[str, dict]:
    """Veredito vigente por claim_id: o de maior ciclo (empate: o último do arquivo)."""
    out: dict[str, dict] = {}
    for rec in C.iter_jsonl(p):
        cid = rec.get("claim_id")
        prev = out.get(cid)
        if prev is None or int(rec.get("cycle") or 0) >= int(prev.get("cycle") or 0):
            out[cid] = rec
    return out


class ClaimSet:
    def __init__(self, rows: list[dict], verdicts: dict[str, dict], source: dict | None = None):
        self.source = source or {}
        self.claims: list[Claim] = []
        self.concept_of: dict[str, str] = {}
        self.absence_of: dict[tuple[str, str], dict] = {}   # (átomo, provedor do outro lado) -> ausência
        for r in rows:
            cid = r["claim_id"]
            v = verdicts.get(cid) or {}
            verdict = v.get("verdict") or "UNPROVEN"
            if v and v.get("claim_version_id") not in (None, r.get("claim_version_id")):
                verdict = "UNPROVEN"     # veredito de outra versão não vale para esta linha
            cl = Claim(row=r, claim_id=cid, claim_version_id=r.get("claim_version_id", ""),
                       subject_id=r["subject_id"], object_id=r["object_id"], predicate_id=r["predicate_id"],
                       semantic_relation=r.get("semantic_relation") or "", transport_fidelity=r.get("transport_fidelity") or "",
                       verdict=verdict, verdict_rec=v)
            self.claims.append(cl)
            for side, atom in (("subject_concept", cl.subject_id), ("object_concept", cl.object_id)):
                if atom and atom != NO_TERM and r.get(side):
                    cur = self.concept_of.get(atom)
                    if cur is None or cur == UNGLOSSED:
                        self.concept_of[atom] = r[side]
            if cl.is_absence:
                other = cid.split("-")[1] if cid.count("-") >= 2 else ""
                self.absence_of[(cl.subject_id, other)] = r.get("absence") or {}
        self.by_atom: dict[str, list[Claim]] = {}
        for cl in self.claims:
            if cl.is_absence:
                continue
            self.by_atom.setdefault(cl.subject_id, []).append(cl)
            self.by_atom.setdefault(cl.object_id, []).append(cl)

    @classmethod
    def load(cls, mdir: Path | None = None) -> "ClaimSet":
        mdir = mdir or C.map_dir()
        mp, vp = mdir / "mapping.sssom.tsv", mdir / "verdicts.jsonl"
        _, rows = read_sssom(mp)
        ver = read_verdicts(vp)
        return cls(rows, ver, source={"mapping": C.portable(mp), "mapping_sha256": C.sha256_file(mp),
                                      "verdicts": C.portable(vp), "verdicts_sha256": C.sha256_file(vp)})

    def concept(self, atom_id: str) -> str:
        return self.concept_of.get(atom_id, UNGLOSSED)

    def ok_claims(self) -> list[Claim]:
        return [c for c in self.claims if not c.is_absence and c.verdict == "OK"]

    def views(self, atom_id: str, src_provider: str, dst_provider: str) -> list[View]:
        """Toda alegação que liga o átomo de origem a um átomo do provedor de destino, já orientada."""
        out = []
        for cl in self.by_atom.get(atom_id, []):
            if cl.subject_id == atom_id and C.provider_of_atom(cl.object_id) == dst_provider:
                out.append(_view(cl, False))
            elif cl.object_id == atom_id and C.provider_of_atom(cl.subject_id) == dst_provider:
                out.append(_view(cl, True))
        return out


def _view(cl: Claim, inverse: bool) -> View:
    r = cl.row
    vdr = r.get("value_domain_relation") or {}
    rel = vdr.get("relation", "unknown") if isinstance(vdr, dict) else "unknown"
    fn = r.get("translation_fn") or None
    if isinstance(fn, str):
        fn = None
    loss = r.get("loss_contract") or []
    guard = r.get("guard") or {"all": []}
    if not inverse:
        return View(cl, False, cl.subject_id, cl.object_id, cl.semantic_relation, rel, fn, loss, guard,
                    r.get("membership_predicate"))
    return View(cl, True, cl.object_id, cl.subject_id, MIRROR.get(cl.semantic_relation, cl.semantic_relation),
                DOMAIN_MIRROR.get(rel, "unknown"), fn, loss, guard, r.get("membership_predicate"))


def synthetic(rows: list[dict], verdicts: list[dict], concepts: dict | None = None) -> ClaimSet:
    """ClaimSet a partir de linhas já decodificadas (testes com alegações sintéticas); concepts completa o conceito
    dos átomos que as linhas não citam (ex.: âncoras do glossário)."""
    ver = {}
    for v in verdicts:
        ver[v["claim_id"]] = v
    cs = ClaimSet(rows, ver, source={"mapping": "synthetic", "mapping_sha256": C.sha256_obj(rows),
                                     "verdicts": "synthetic", "verdicts_sha256": C.sha256_obj(verdicts)})
    for a, c in (concepts or {}).items():
        cs.concept_of.setdefault(a, c)
    return cs


def glossary_anchors() -> dict:
    """Âncoras átomo -> conceito do glossário da fatia (PILOT-STO-GLOSS claims.jsonl), para testes."""
    p = C.data_root() / "PILOT-STO-GLOSS" / "claims.jsonl"
    return {r["atom_id"]: r["concept_id"] for r in C.iter_jsonl(p)} if p.exists() else {}
