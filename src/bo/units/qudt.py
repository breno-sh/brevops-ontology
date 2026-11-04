"""QUDT fixado (v3.5.3) e a conferência de IRI: existe, não é obsoleto, e a unidade serve à grandeza.

Fonte: $BO_DATA/downloads/qudt-3.5.3/ (SOURCE.txt; dado não confiável, só lido como RDF pelo rdflib).
A unidade serve à grandeza quando o QUDT afirma (unidade qudt:hasQuantityKind | qudt:unitForQuantityKind grandeza)
ou (grandeza qudt:applicableUnit unidade).
"""

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path

QUDT_VERSION = "3.5.3"
FILES = {
    "VOCAB_QUDT-UNITS-ALL.ttl": "5e84f3e10ae6a3c535e2e7616dc2affee09dd52bea5229822188730493fd4418",
    "VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl": "b246c2f851e3c9353cafddf9640b18b696c410e176b29735218f7a266bcb9888",
}
UNIT_NS = "http://qudt.org/vocab/unit/"
QK_NS = "http://qudt.org/vocab/quantitykind/"
SCHEMA_NS = "http://qudt.org/schema/qudt/"
MARKERS = ("NOT_APPLICABLE", "UNKNOWN")
CURIE_UNIT = re.compile(r"^(?:unit:|http://qudt\.org/vocab/unit/)([A-Za-z0-9_\-]+)$")
CURIE_QK = re.compile(r"^(?:quantitykind:|http://qudt\.org/vocab/quantitykind/)([A-Za-z0-9_\-]+)$")


def qudt_dir() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "downloads" / f"qudt-{QUDT_VERSION}"


def verify_files() -> list[str]:
    errs = []
    for name, want in FILES.items():
        p = qudt_dir() / name
        if not p.exists():
            errs.append(f"QUDT ausente: {p}")
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want:
            errs.append(f"QUDT {name}: sha256 {got[:12]} != fixado {want[:12]}")
    if not (qudt_dir() / "SOURCE.txt").exists():
        errs.append(f"QUDT sem SOURCE.txt em {qudt_dir()}")
    return errs


@lru_cache(maxsize=1)
def index() -> dict:
    """{'units': {local: {'deprecated': bool, 'kinds': set}}, 'kinds': {local: {'deprecated': bool, 'units': set}}}"""
    import rdflib
    from rdflib.namespace import RDF
    errs = verify_files()
    if errs:
        raise RuntimeError("; ".join(errs))
    Q = rdflib.Namespace(SCHEMA_NS)
    g = rdflib.Graph()
    for name in FILES:
        g.parse(str(qudt_dir() / name), format="turtle")
    units, kinds = {}, {}
    for s in set(g.subjects(RDF.type, Q.Unit)):
        s = str(s)
        if s.startswith(UNIT_NS):
            units[s[len(UNIT_NS):]] = {"deprecated": False, "kinds": set()}
    for s in set(g.subjects(RDF.type, Q.QuantityKind)):
        s = str(s)
        if s.startswith(QK_NS):
            kinds[s[len(QK_NS):]] = {"deprecated": False, "units": set()}
    for s, o in g.subject_objects(Q.deprecated):
        loc = str(s)
        if str(o).lower() in ("true", "1"):
            if loc.startswith(UNIT_NS) and loc[len(UNIT_NS):] in units:
                units[loc[len(UNIT_NS):]]["deprecated"] = True
            if loc.startswith(QK_NS) and loc[len(QK_NS):] in kinds:
                kinds[loc[len(QK_NS):]]["deprecated"] = True
    for p in (Q.hasQuantityKind, Q.unitForQuantityKind):
        for s, o in g.subject_objects(p):
            s, o = str(s), str(o)
            if s.startswith(UNIT_NS) and o.startswith(QK_NS) and s[len(UNIT_NS):] in units:
                units[s[len(UNIT_NS):]]["kinds"].add(o[len(QK_NS):])
    for s, o in g.subject_objects(Q.applicableUnit):
        s, o = str(s), str(o)
        if s.startswith(QK_NS) and o.startswith(UNIT_NS) and o[len(UNIT_NS):] in units:
            units[o[len(UNIT_NS):]]["kinds"].add(s[len(QK_NS):])
    return {"units": units, "kinds": kinds}


def unit_local(x: str) -> str | None:
    m = CURIE_UNIT.match(x or "")
    return m.group(1) if m else None


def qk_local(x: str) -> str | None:
    m = CURIE_QK.match(x or "")
    return m.group(1) if m else None


def check_pair(qk: str, unit: str) -> list[str]:
    """Erros da dupla (grandeza, unidade) contra o QUDT fixado. Marcadores são aceitos só na forma exata."""
    errs = []
    idx = index()
    if qk in MARKERS and unit in MARKERS:
        return errs
    if qk not in MARKERS:
        q = qk_local(qk)
        if q is None:
            return [f"grandeza não é IRI QUDT nem marcador: {qk!r}"]
        if q not in idx["kinds"]:
            errs.append(f"grandeza {qk} não existe no QUDT {QUDT_VERSION}")
        elif idx["kinds"][q]["deprecated"]:
            errs.append(f"grandeza {qk} obsoleta no QUDT {QUDT_VERSION}")
    if unit not in MARKERS:
        u = unit_local(unit)
        if u is None:
            return errs + [f"unidade não é IRI QUDT nem marcador: {unit!r}"]
        if u not in idx["units"]:
            errs.append(f"unidade {unit} não existe no QUDT {QUDT_VERSION}")
        elif idx["units"][u]["deprecated"]:
            errs.append(f"unidade {unit} obsoleta no QUDT {QUDT_VERSION}")
        elif qk not in MARKERS and qk_local(qk) not in idx["units"][u]["kinds"]:
            errs.append(f"o QUDT {QUDT_VERSION} não liga {unit} a {qk} (liga a: "
                        f"{', '.join(sorted(idx['units'][u]['kinds'])[:6])})")
    elif unit == "NOT_APPLICABLE" and qk != "NOT_APPLICABLE":
        errs.append(f"unidade NOT_APPLICABLE com grandeza {qk}")
    if qk == "UNKNOWN" and unit not in MARKERS:
        errs.append(f"grandeza UNKNOWN com unidade {unit}")
    return errs


def iri_status(pairs: dict[tuple[str, str], int]) -> dict:
    """Estado de cada IRI e dupla usada (para results/UNITS/iri_status.json)."""
    idx = index()
    units, kinds, out_pairs = {}, {}, []
    for (qk, unit), n in sorted(pairs.items()):
        if unit not in MARKERS:
            u = unit_local(unit)
            units[unit] = {"exists": u in idx["units"], "deprecated": bool(u in idx["units"] and
                                                                             idx["units"][u]["deprecated"]),
                           "qudt_kinds": sorted(idx["units"].get(u, {}).get("kinds", set()))}
        if qk not in MARKERS:
            q = qk_local(qk)
            kinds[qk] = {"exists": q in idx["kinds"], "deprecated": bool(q in idx["kinds"] and
                                                                         idx["kinds"][q]["deprecated"])}
        out_pairs.append({"quantity_kind": qk, "unit_qudt": unit, "records": n, "errors": check_pair(qk, unit)})
    return {"qudt_version": QUDT_VERSION, "files": FILES, "units": units, "quantity_kinds": kinds,
            "pairs": out_pairs}
