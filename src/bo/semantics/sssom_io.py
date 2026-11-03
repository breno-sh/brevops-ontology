"""SSSOM do C09: TSV com as colunas próprias declaradas em extension_definitions, e RDF.

Achado (2026-11-02): o sssom-py 0.4.22 (versão do requirements.lock) DESCARTA os slots de extensão declarados
ao ler o TSV ('No attr for ...'); portanto as colunas próprias do C09 não sobrevivem ao conversor oficial. O
C09 é lido e escrito por este módulo; o sssom-py é usado como referência independente das colunas padrão
(sujeito, predicado, objeto, justificativa) e do RDF delas, que tem de sair isomorfo ao nosso.
"""

from __future__ import annotations

import csv
import io
import json

import rdflib
import yaml
from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF

from .claims import CORE, EXT, JSON_FIELDS, from_row, to_row
from .vocab import BOSX, SEMAPV, SKOS

SSSOM = Namespace("https://w3id.org/sssom/")
DCT = Namespace("http://purl.org/dc/terms/")
BOSXN = Namespace(BOSX)
XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"

PREFIXES = {
    "pa": "https://example.org/provider-a/", "pb": "https://example.org/provider-b/",
    "pc": "https://example.org/provider-c/", "pd": "https://example.org/provider-d/",
    "pz": "https://example.org/provider-z/",
    "skos": SKOS, "semapv": SEMAPV, "bosx": BOSX, "bo": "https://w3id.org/brevops/ontology#",
    "concept": "https://w3id.org/brevops/glossary#",
}
LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"


def slot_property(slot: str) -> str:
    parts = slot.split("_")
    return "bosx:" + parts[0] + "".join(p.capitalize() for p in parts[1:])


def write_tsv(records: list[dict], mapping_set_id: str, prefixes: dict | None = None) -> str:
    prefixes = dict(prefixes or PREFIXES)
    rows = [to_row(r) for r in records]
    cols = [c for c in CORE + EXT if any(c in r for r in rows)]
    ext = [c for c in cols if c in EXT]
    meta = {"curie_map": prefixes, "mapping_set_id": mapping_set_id, "license": LICENSE,
            "extension_definitions": [{"slot_name": s, "property": slot_property(s), "type_hint": XSD_STRING}
                                      for s in ext]}
    head = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True, default_flow_style=False)
    buf = io.StringIO()
    buf.write("".join(f"# {line}\n" for line in head.splitlines()))
    w = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return buf.getvalue()


def read_tsv(text: str) -> tuple[dict, list[dict]]:
    meta_lines, body = [], []
    for line in text.splitlines(keepends=True):
        (meta_lines if line.startswith("#") else body).append(line)
    meta = yaml.safe_load("".join(l[2:] if l.startswith("# ") else l[1:] for l in meta_lines)) or {}
    rd = csv.DictReader(io.StringIO("".join(body)), delimiter="\t")
    recs = [from_row(dict(r)) for r in rd]
    return meta, recs


def expand(curie: str, prefixes: dict) -> URIRef:
    if curie.startswith("http://") or curie.startswith("https://"):
        return URIRef(curie)
    p, _, local = curie.partition(":")
    if p not in prefixes:
        raise ValueError(f"prefixo desconhecido: {curie}")
    return URIRef(prefixes[p] + local)


def to_rdf(records: list[dict], mapping_set_id: str, prefixes: dict | None = None,
           extensions: bool = True) -> rdflib.Graph:
    """Mesma forma do sssom-py (owl:Axiom anotado), mais os slots de extensão como literais no nó do axioma."""
    prefixes = dict(prefixes or PREFIXES)
    g = rdflib.Graph()
    for k, v in prefixes.items():
        g.bind(k, v)
    g.bind("sssom", str(SSSOM))
    ms = URIRef(mapping_set_id)
    g.add((ms, RDF.type, SSSOM.MappingSet))
    g.add((ms, DCT.license, URIRef(LICENSE)))
    rows = [to_row(r) for r in records]
    if extensions:
        ext = [c for c in EXT if any(c in r for r in rows)]
        for s in ext:
            d = BNode(f"ext_{s}")
            g.add((ms, SSSOM.extension_definitions, d))
            g.add((d, RDF.type, SSSOM.ExtensionDefinition))
            g.add((d, SSSOM.slot_name, Literal(s)))
            g.add((d, SSSOM.property, expand(slot_property(s), prefixes)))
            g.add((d, SSSOM.type_hint, URIRef(XSD_STRING)))
    for i, r in enumerate(rows):
        ax = BNode(f"m{i}")
        g.add((ms, SSSOM.mappings, ax))
        g.add((ax, RDF.type, OWL.Axiom))
        g.add((ax, OWL.annotatedSource, expand(r["subject_id"], prefixes)))
        g.add((ax, OWL.annotatedProperty, expand(r["predicate_id"], prefixes)))
        g.add((ax, OWL.annotatedTarget, expand(r["object_id"], prefixes)))
        g.add((ax, SSSOM.mapping_justification, expand(r["mapping_justification"], prefixes)))
        if extensions:
            for k in EXT:
                if k in r:
                    g.add((ax, expand(slot_property(k), prefixes), Literal(r[k])))
    return g


def from_rdf(g: rdflib.Graph, prefixes: dict | None = None) -> list[dict]:
    prefixes = dict(prefixes or PREFIXES)
    inv = sorted(((v, k) for k, v in prefixes.items()), key=lambda kv: -len(kv[0]))

    def curie(u):
        s = str(u)
        for ns, p in inv:
            if s.startswith(ns):
                return f"{p}:{s[len(ns):]}"
        return s
    prop_slot = {str(expand(slot_property(s), prefixes)): s for s in EXT}
    recs = []
    for ax in g.subjects(RDF.type, OWL.Axiom):
        row = {"subject_id": curie(g.value(ax, OWL.annotatedSource)),
               "predicate_id": curie(g.value(ax, OWL.annotatedProperty)),
               "object_id": curie(g.value(ax, OWL.annotatedTarget)),
               "mapping_justification": curie(g.value(ax, SSSOM.mapping_justification))}
        for p, o in g.predicate_objects(ax):
            if str(p) in prop_slot:
                row[prop_slot[str(p)]] = str(o)
        recs.append(from_row(row))
    return sorted(recs, key=lambda r: r.get("claim_id", ""))


def hydrate(g: rdflib.Graph) -> rdflib.Graph:
    """Do axioma anotado à tripla direta (s p o), que é o que o raciocinador vê."""
    for ax in list(g.subjects(RDF.type, OWL.Axiom)):
        s, p, o = g.value(ax, OWL.annotatedSource), g.value(ax, OWL.annotatedProperty), g.value(ax, OWL.annotatedTarget)
        if s is not None and p is not None and o is not None:
            g.add((s, p, o))
    return g


def core_subgraph(g: rdflib.Graph) -> rdflib.Graph:
    """Só os mapeamentos e suas 4 colunas padrão (para comparar com o sssom-py)."""
    out = rdflib.Graph()
    keep = {OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget, SSSOM.mapping_justification, RDF.type}
    for ax in g.subjects(RDF.type, OWL.Axiom):
        for p, o in g.predicate_objects(ax):
            if p in keep:
                out.add((ax, p, o))
    return out


def sssom_py_view(tsv_text: str, tmpdir) -> dict:
    """Lê o TSV com o sssom-py (referência independente): colunas que sobrevivem e o RDF das colunas padrão."""
    import logging
    import os
    from pathlib import Path
    logging.disable(logging.WARNING)
    try:
        from sssom.parsers import parse_sssom_table
        from sssom.writers import to_rdf_graph
        p = Path(tmpdir) / "sssom_py_input.sssom.tsv"
        p.write_text(tsv_text, encoding="utf-8")
        msdf = parse_sssom_table(str(p))
        cols = list(msdf.df.columns)
        rows = msdf.df.to_dict(orient="records")
        g = to_rdf_graph(msdf)
        os.remove(p)
    finally:
        logging.disable(logging.NOTSET)
    return {"columns": cols, "rows": rows, "graph": g}
