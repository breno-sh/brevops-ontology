"""Entradas do árbitro: alegações C09 (TSV SSSOM ou JSONL), versões (C09-IDS), glossário auditado C20, átomos C01.

As alegações vêm com a origem (arquivo e domínio, quando o nome segue MAP-<par>-<domínio> ou PILOT-<fatia>-MAP).
Versões: só a versão CORRENTE de cada claim_id é julgada; as substituídas vão ao relatório. Bifurcação (duas
versões correntes do mesmo claim_id, inclusive em arquivos diferentes), versão que não é do claim_id, versão ou
evento repetido e supersedes para versão inexistente ou de outra alegação: ARB-VERSION (REFUTED).
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

from bo.contracts import sssom as CSSSOM

from .common import load_jsonl

_VID = re.compile(r"^(?P<base>[^@\s]+)@(?P<n>[1-9][0-9]*)$")
_DOM = re.compile(r"(?:^|/)MAP-[A-Z]+-(?P<dom>CMP|NET|STO|DB|SEC|OPS)(?:/|$)")


def domain_of(path: str) -> str | None:
    m = _DOM.search(str(path))
    return m["dom"] if m else None


def expand(paths: list[str]) -> list[Path]:
    out = []
    for p in paths:
        hits = sorted(glob.glob(p)) if any(ch in p for ch in "*?[") else [p]
        if not hits:
            raise SystemExit(f"entrada não encontrada: {p}")
        out.extend(Path(h) for h in hits)
    seen, uniq = set(), []
    for p in out:
        k = str(p.resolve())
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def read_claims(path: Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith(".tsv"):
        _meta, recs, _cols = CSSSOM.read_tsv(text)
        return recs
    return load_jsonl(Path(path))


def load(paths: list[str]) -> list[dict]:
    """[{rec, source, domain, line}] na ordem dos arquivos e das linhas."""
    out = []
    for p in expand(paths):
        for i, r in enumerate(read_claims(p), 1):
            out.append({"rec": r, "source": str(p), "domain": domain_of(str(p)), "line": i})
    return out


def _vparts(vid):
    m = _VID.match(str(vid or ""))
    return (m["base"], int(m["n"])) if m else (None, None)


def resolve_versions(items: list[dict]) -> tuple[list[dict], list[dict], dict[str, list[dict]]]:
    """-> (correntes, substituídas, falhas por claim_id). Correntes: versão que nenhuma outra substitui."""
    fails: dict[str, list[dict]] = {}

    def f(cid, detail):
        fails.setdefault(cid, []).append({"rule": "ARB-VERSION", "outcome": "REFUTED_BY_RULE", "detail": detail})

    by_cid: dict[str, list[dict]] = {}
    for it in items:
        r = it["rec"]
        by_cid.setdefault(str(r.get("claim_id")), []).append(it)
    vids, evs = {}, {}
    for it in items:
        r = it["rec"]
        vids.setdefault(r.get("claim_version_id"), []).append(it)
        evs.setdefault(r.get("event_id"), []).append(it)
    for vid, its in vids.items():
        if len(its) > 1:
            for it in its:
                f(str(it["rec"].get("claim_id")), f"claim_version_id {vid} repetido ({len(its)} linhas)")
    for ev, its in evs.items():
        if len(its) > 1:
            for it in its:
                f(str(it["rec"].get("claim_id")), f"event_id {ev} repetido ({len(its)} linhas)")
    current, superseded = [], []
    for cid in sorted(by_cid):
        its = by_cid[cid]
        mine = {it["rec"].get("claim_version_id"): it for it in its}
        for it in its:
            r = it["rec"]
            base, n = _vparts(r.get("claim_version_id"))
            if base != cid:
                f(cid, f"claim_version_id {r.get('claim_version_id')!r} não é versão de {cid!r}")
            sup = r.get("supersedes")
            if sup is not None:
                sb, sn = _vparts(sup)
                if sb != cid:
                    f(cid, f"supersedes {sup!r} é de outra alegação")
                elif sup not in mine:
                    f(cid, f"supersedes {sup!r}: versão inexistente")
                elif n is not None and sn is not None and sn >= n:
                    f(cid, f"supersedes {sup!r} não é anterior a {r.get('claim_version_id')}")
        replaced = {it["rec"].get("supersedes") for it in its if it["rec"].get("supersedes")}
        heads = [it for it in its if it["rec"].get("claim_version_id") not in replaced]
        if len(heads) > 1:
            srcs = sorted({h["source"] for h in heads})
            f(cid, f"{len(heads)} versões correntes de {cid} (bifurcação" +
               (f" entre arquivos: {len(srcs)}" if len(srcs) > 1 else "") + ")")
        heads.sort(key=lambda it: (_vparts(it["rec"].get("claim_version_id"))[1] or 0, it["source"], it["line"]))
        if heads:
            current.append(heads[-1])
            for h in heads[:-1]:
                h = dict(h)
                h["forked"] = True
                current.append(h)
        superseded.extend(it for it in its if it["rec"].get("claim_version_id") in replaced)
    return current, superseded, fails


# ------------------------------------------------------------------------------------------- glossário C20
class Glossary:
    """Âncoras auditadas: claims.jsonl (versões) + glossary_audit.jsonl (auditoria). Estado efetivo de uma âncora =
    o da versão corrente; com auditoria dessa versão, o evidence_state_after da última (por 'at'); resultado
    'fail' = UNRESOLVED."""

    def __init__(self, claims: list[dict], audits: list[dict] | None = None, concepts: list[dict] | None = None):
        self.by_vid = {c["claim_version_id"]: c for c in claims}
        replaced = {c.get("supersedes") for c in claims if c.get("supersedes")}
        self.current = {}
        for c in sorted(claims, key=lambda c: _vparts(c["claim_version_id"])[1] or 0):
            if c["claim_version_id"] not in replaced:
                self.current[c["claim_id"]] = c
        self.audits: dict[str, list[dict]] = {}
        for a in audits or []:
            self.audits.setdefault(a["claim_version_id"], []).append(a)
        self.concepts = {c["concept_id"]: c for c in concepts or []}

    @classmethod
    def from_dir(cls, d: Path) -> "Glossary":
        d = Path(d)
        cl = load_jsonl(d / "claims.jsonl")
        au = load_jsonl(d / "glossary_audit.jsonl") if (d / "glossary_audit.jsonl").exists() else []
        co = load_jsonl(d / "glossary.jsonl") if (d / "glossary.jsonl").exists() else []
        return cls(cl, au, co)

    def resolve(self, ref: dict) -> tuple[dict | None, str, str]:
        """ref: {claim_version_id | claim_id, ...} -> (âncora, estado efetivo, motivo)."""
        a = None
        if ref.get("claim_version_id"):
            a = self.by_vid.get(ref["claim_version_id"])
            if a is not None and self.current.get(a["claim_id"]) is not a:
                return a, "UNRESOLVED", f"{ref['claim_version_id']} foi substituída"
        elif ref.get("claim_id"):
            a = self.current.get(ref["claim_id"])
        if a is None:
            return None, "UNRESOLVED", "âncora não encontrada no glossário auditado"
        st = a.get("evidence_state", "UNRESOLVED")
        aus = sorted(self.audits.get(a["claim_version_id"], []), key=lambda x: (x.get("at", ""), x.get("audit_id", "")))
        if aus:
            last = aus[-1]
            st = "UNRESOLVED" if last.get("result") == "fail" else last.get("evidence_state_after", st)
        return a, st, "auditada" if aus else "sem auditoria registrada"


# ---------------------------------------------------------------------------------------------- átomos C01
def repeated_fields(atoms: list[dict]) -> set[str]:
    """Átomo em bloco repetido: algum bloco do caminho com nesting list/set/map e sem max_items = 1."""
    out = set()
    for a in atoms or []:
        for b in a.get("block_path") or []:
            if b.get("nesting_mode") in ("list", "set", "map") and b.get("max_items") != 1:
                out.add(a["atom_id"])
                break
    return out
