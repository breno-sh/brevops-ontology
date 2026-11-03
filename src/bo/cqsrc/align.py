"""Alinhamento entre provedores a partir do catálogo curado (concepts.py).

Para cada conceito e cada par de provedores (ordem do index_set: aws, google, azurerm, oci), cada membro do
primeiro provedor é comparado com cada membro do segundo. A relação SKOS sai SÓ dos parâmetros declarados:

  todos os parâmetros iguais (ou nenhum)          skos:closeMatch
  sujeito mais estreito em ao menos um, resto =    skos:broadMatch   ("a skos:broadMatch b" = b mais amplo)
  sujeito mais largo em ao menos um, resto =       skos:narrowMatch  (b mais estreito)
  incomparável, categoria diferente ou misto       skos:relatedMatch

Extensão = conjunto de configurações conformes ao controle. Toda linha é UNPROVEN: a pertença ao conceito é
curadoria sobre títulos, e o título não prova o que a consulta do mod realmente confere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import concepts as C
from .extract import Control

STOP = set("""a an the and or to of for in on at by with is are be been that this these those all any
every each no not only than ensure ensures use used using set setting enabled enable disabled
is' 'on' 'off' it its from as""".split())

PROVIDER_WORDS = set("""aws amazon gcp google cloud azure microsoft oci oracle iam entra""".split())


class AlignError(ValueError):
    pass


@dataclass(frozen=True)
class Row:
    concept_id: str
    concept_label: str
    domain: str
    concept_providers: str
    concept_in_all_four: bool
    pair: str
    subject: Control
    predicate: str
    obj: Control
    direction_basis: str
    subject_params: str
    object_params: str
    lexical_jaccard: float


def _cmp_key(op: str, a, b) -> str:
    """'eq' | 'narrower' (a mais estreito) | 'broader' | 'inc'"""
    if op == "eq":
        return "eq" if (a is not None and b is not None and a == b) else "inc"
    if op == "max":
        a = float("inf") if a is None else a
        b = float("inf") if b is None else b
        return "eq" if a == b else ("narrower" if a < b else "broader")
    if op == "min":
        a = float("-inf") if a is None else a
        b = float("-inf") if b is None else b
        return "eq" if a == b else ("narrower" if a > b else "broader")
    if op in ("forbid", "require", "allow"):
        sa, sb = set(a or ()), set(b or ())
        if sa == sb:
            return "eq"
        if sa > sb:
            return "narrower" if op != "allow" else "broader"
        if sa < sb:
            return "broader" if op != "allow" else "narrower"
        return "inc"
    raise AlignError(f"operador desconhecido {op}")


def compare(pa: dict, pb: dict) -> tuple[str, str]:
    keys = sorted(set(pa) | set(pb))
    res = {}
    for k in keys:
        opa = pa.get(k, (None, None))[0]
        opb = pb.get(k, (None, None))[0]
        op = opa or opb
        if opa and opb and opa != opb:
            raise AlignError(f"parâmetro {k} com operadores diferentes ({opa} x {opb})")
        res[k] = _cmp_key(op, pa.get(k, (None, None))[1], pb.get(k, (None, None))[1])
    vals = set(res.values())
    if "inc" in vals or {"narrower", "broader"} <= vals:
        pred = "skos:relatedMatch"
        basis = [k for k, v in res.items() if v != "eq"]
    elif "narrower" in vals:
        pred = "skos:broadMatch"
        basis = [k for k, v in res.items() if v == "narrower"]
    elif "broader" in vals:
        pred = "skos:narrowMatch"
        basis = [k for k, v in res.items() if v == "broader"]
    else:
        pred = "skos:closeMatch"
        basis = []
    detail = ";".join(f"{k}={res[k]}" for k in keys)
    return pred, f"{','.join(basis) or '-'} | {detail or 'sem parâmetros'}"


def fmt_params(p: dict) -> str:
    out = []
    for k in sorted(p):
        op, v = p[k]
        if isinstance(v, tuple):
            v = "{" + ",".join(str(x) for x in v) + "}"
        out.append(f"{k}:{op}:{v}")
    return ";".join(out)


def tokens(title: str) -> set[str]:
    t = re.sub(r"[^a-z0-9/:.]+", " ", title.lower())
    return {w.strip(".") for w in t.split() if w.strip(".") and w.strip(".") not in STOP
            and w.strip(".") not in PROVIDER_WORDS}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return round(len(ta & tb) / len(ta | tb), 4) if ta | tb else 0.0


def resolve_members(latest: dict[str, list[Control]]) -> dict[str, list[tuple[Control, dict]]]:
    """Liga cada membro do catálogo ao controle extraído; reprova número ausente ou guarda que não casa."""
    by_item = {p: {c.cis_item_id: c for c in cs} for p, cs in latest.items()}
    out = {}
    seen_ids = set()
    for con in C.CONCEPTS:
        if con["id"] in seen_ids:
            raise AlignError(f"conceito repetido {con['id']}")
        seen_ids.add(con["id"])
        if con["domain"] not in ("CMP", "NET", "STO", "DB", "SEC", "OPS"):
            raise AlignError(f"{con['id']}: domínio fora do index_set")
        res = []
        for m in con["members"]:
            p = m["provider"]
            if p not in by_item:
                raise AlignError(f"{con['id']}: provedor {p} desconhecido")
            c = by_item[p].get(m["item"])
            if c is None:
                raise AlignError(f"{con['id']}: {p} {m['item']} não existe na versão mais nova")
            if not re.search(m["guard"], c.title.lower()):
                raise AlignError(f"{con['id']}: guarda de {p} {m['item']} não casa com o título {c.title!r}")
            res.append((c, m["params"]))
        provs = {c.provider for c, _ in res}
        if len(provs) < 2:
            raise AlignError(f"{con['id']}: conceito com um só provedor não alinha nada")
        out[con["id"]] = res
    return out


def align(latest: dict[str, list[Control]]) -> list[Row]:
    members = resolve_members(latest)
    rows: list[Row] = []
    for con in C.CONCEPTS:
        ms = members[con["id"]]
        provs = [p for p in C.PROVIDERS if any(c.provider == p for c, _ in ms)]
        for i, pa in enumerate(C.PROVIDERS):
            for pb in C.PROVIDERS[i + 1:]:
                for a, ppa in [x for x in ms if x[0].provider == pa]:
                    for b, ppb in [x for x in ms if x[0].provider == pb]:
                        pred, basis = compare(ppa, ppb)
                        rows.append(Row(con["id"], con["label"], con["domain"], ";".join(provs), len(provs) == 4,
                                        C.PAIR_CODE[(pa, pb)], a, pred, b, basis, fmt_params(ppa),
                                        fmt_params(ppb), jaccard(a.title, b.title)))
    return rows


def lexical_audit(latest: dict[str, list[Control]], rows: list[Row], threshold: float = 0.5) -> dict:
    """Pares entre provedores com títulos parecidos que a curadoria NÃO alinhou (possíveis faltas)."""
    curated = {(r.subject.control_id, r.obj.control_id) for r in rows}
    curated |= {(b, a) for a, b in curated}
    cand = []
    for i, pa in enumerate(C.PROVIDERS):
        for pb in C.PROVIDERS[i + 1:]:
            for a in latest[pa]:
                for b in latest[pb]:
                    j = jaccard(a.title, b.title)
                    if j >= threshold and (a.control_id, b.control_id) not in curated:
                        why = C.REVIEWED_NON_MATCHES.get((pa, a.cis_item_id, pb, b.cis_item_id), "")
                        cand.append({"pair": C.PAIR_CODE[(pa, pb)], "subject": f"{pa} {a.cis_item_id}",
                                     "subject_title": a.title, "object": f"{pb} {b.cis_item_id}",
                                     "object_title": b.title, "jaccard": j,
                                     "review": why or "NÃO REVISADO"})
    cand.sort(key=lambda d: (-d["jaccard"], d["pair"], d["subject"], d["object"]))
    jc = sorted(r.lexical_jaccard for r in rows)
    return {"threshold": threshold, "uncurated_similar_pairs": cand,
            "unreviewed": sum(1 for d in cand if d["review"] == "NÃO REVISADO"),
            "curated_pairs": len(rows),
            "curated_jaccard_median": jc[len(jc) // 2] if jc else None,
            "curated_jaccard_zero": sum(1 for x in jc if x == 0.0)}
