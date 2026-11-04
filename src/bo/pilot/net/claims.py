"""Alegações do C09 (mapping.sssom.tsv) com os vereditos do C21 (verdicts.jsonl): o que pode transportar valor.

Só transporta a alegação cujo veredito MAIS RECENTE do árbitro (maior ciclo) é OK; o resto fica no índice para o
traço dizer por que não transportou (UNPROVEN, REFUTED_BY_RULE, AMBIGUOUS, CONTESTED). A transformação por valor é
sempre a de bo.semantics.transport (tabela SKOS da §1.5 com a direção corrigida), igual nos três controles.

Índice: por átomo de origem e provedor de destino, nos dois sentidos da alegação (sujeito->objeto = forward;
objeto->sujeito = inverse). Alegação de grupo (C09 group: variáveis e passos executáveis) entra pelo campo de cada
variável do lado de origem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from bo.contracts import sssom as SS

TRANSPORTING = ("exact", "close", "broad", "narrow")


def provider_of(atom: str) -> str:
    return atom.split(":", 1)[0]


def strip_index(path: str) -> str:
    """'ingress[0].from_port' -> 'ingress.from_port' (o C01 não tem índice)."""
    import re
    return re.sub(r"\[[^\]]*\]", "", path)


@dataclass
class ClaimRef:
    claim: dict
    direction: str            # forward | inverse
    verdict: str
    source_atom: str
    target_atom: str
    group: dict | None = None

    @property
    def claim_id(self) -> str:
        return self.claim["claim_id"]

    @property
    def ok(self) -> bool:
        return self.verdict == "OK"


@dataclass
class ClaimSet:
    records: list
    verdicts: dict
    origin: str               # "mapping" (PILOT-NET-MAP) | "synthetic"
    sha256: dict = field(default_factory=dict)
    by_source: dict = field(default_factory=dict)   # (atom de origem, provedor de destino) -> [ClaimRef]
    groups: list = field(default_factory=list)      # [ClaimRef] de grupo

    def build(self):
        self.by_source.clear()
        self.groups.clear()
        for rec in self.records:
            v = self.verdicts.get(rec["claim_id"], "UNPROVEN")
            g = rec.get("group")
            if isinstance(g, str) and g:
                g = json.loads(g)
            if g:
                for side, direction in (("subject", "forward"), ("object", "inverse")):
                    other = "object" if side == "subject" else "subject"
                    src = sorted({x["field"] for x in g["variables"] if x["side"] == side})
                    dst = sorted({x["field"] for x in g["variables"] if x["side"] == other})
                    if src and dst:
                        self.groups.append(ClaimRef(rec, direction, v, src[0], dst[0], g))
                continue
            s, o = rec["subject_id"], rec["object_id"]
            self.by_source.setdefault((s, provider_of(o)), []).append(ClaimRef(rec, "forward", v, s, o))
            self.by_source.setdefault((o, provider_of(s)), []).append(ClaimRef(rec, "inverse", v, o, s))
        return self

    def scalar(self, source_atom: str, target_atom: str) -> list:
        return [c for c in self.by_source.get((source_atom, provider_of(target_atom)), []) if c.target_atom == target_atom]

    def from_source(self, source_atom: str, target_provider: str) -> list:
        return list(self.by_source.get((source_atom, target_provider), []))

    def groups_to(self, target_atom: str, source_provider: str) -> list:
        out = []
        for g in self.groups:
            tgt = [x["field"] for x in g.group["variables"]
                   if x["side"] == ("object" if g.direction == "forward" else "subject")]
            src = [x["field"] for x in g.group["variables"]
                   if x["side"] == ("subject" if g.direction == "forward" else "object")]
            if target_atom in tgt and src and provider_of(src[0]) == source_provider:
                out.append(g)
        return out

    def ok_count(self) -> int:
        return sum(1 for r in self.records if self.verdicts.get(r["claim_id"]) == "OK")

    def concepts_by_atom(self) -> dict:
        """átomo -> conceito do glossário, lido das alegações OK (subject_concept/object_concept)."""
        out = {}
        for r in self.records:
            if self.verdicts.get(r["claim_id"]) != "OK":
                continue
            for a, c in ((r["subject_id"], r.get("subject_concept")), (r["object_id"], r.get("object_concept"))):
                if c and c != "bo:UNGLOSSED":
                    out.setdefault(a, set()).add(c)
        return out


def latest_verdicts(lines) -> dict:
    best = {}
    for line in lines:
        if not line.strip():
            continue
        v = json.loads(line)
        cid = v["claim_id"]
        if cid not in best or v.get("cycle", 0) >= best[cid].get("cycle", 0):
            best[cid] = v
    return {k: v["verdict"] for k, v in best.items()}


def latest_records(records: list) -> list:
    """Última versão de cada claim_id (claim_version_id @n maior)."""
    best = {}
    for r in records:
        n = int(str(r.get("claim_version_id", "@0")).rsplit("@", 1)[-1] or 0)
        if r["claim_id"] not in best or n >= best[r["claim_id"]][0]:
            best[r["claim_id"]] = (n, r)
    return [v[1] for v in best.values()]


def load(mapping: Path, verdicts: Path, origin: str = "mapping") -> ClaimSet:
    import hashlib
    text = mapping.read_text(encoding="utf-8")
    _, recs, _ = SS.read_tsv(text)
    vlines = verdicts.read_text(encoding="utf-8").splitlines()
    cs = ClaimSet(latest_records(recs), latest_verdicts(vlines), origin,
                  {"mapping": hashlib.sha256(text.encode()).hexdigest(),
                   "verdicts": hashlib.sha256(verdicts.read_bytes()).hexdigest()})
    return cs.build()
