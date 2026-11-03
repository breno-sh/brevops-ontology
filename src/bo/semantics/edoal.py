"""EDOAL: exportar o subconjunto suportado e reimportar (F3).

Subconjunto suportado (o resto é relatado como não exportado, com motivo):
  relação    exact -> '=', broad -> '<' (entity1 ⊑ entity2: o sujeito é o mais estreito), narrow -> '>'.
             close e related não têm relação EDOAL equivalente: não são exportados (não viram '=').
  entidades  edoal:Property; grupo 1:N/N:1 como edoal:PropertyConstruction com edoal:and.
  tradução   edoal:Transformation (direção 'o-') com edoal:Apply: operador = função do núcleo, argumento = parâmetros.
  O que o EDOAL não exprime (guarda, contrato de perda, predicado de pertença, tipos, evidência, ids) vai como
  anotação bosx:* na célula, para a reimportação devolver a mesma alegação.
"""

from __future__ import annotations

import json

import rdflib
from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import RDF, XSD

from .sssom_io import PREFIXES, expand, slot_property
from .claims import EXT, JSON_FIELDS
from .vocab import SKOS_PREDICATE

ALIGN = Namespace("http://knowledgeweb.semanticweb.org/heterogeneity/alignment#")
EDOAL = Namespace("http://ns.inria.org/edoal/1.0/#")
FN = Namespace("https://w3id.org/brevops/transform#")
REL_OUT = {"exact": "=", "broad": "<", "narrow": ">"}
REL_IN = {v: k for k, v in REL_OUT.items()}
ANNOT = [k for k in EXT if k not in ("semantic_relation",)]


def supported(rec: dict) -> tuple[bool, str]:
    if rec.get("semantic_relation") not in REL_OUT:
        return False, f"{rec.get('semantic_relation')}: sem relação EDOAL equivalente"
    fn = rec.get("translation_fn")
    if isinstance(fn, list) and len(fn) > 1:
        return False, "cadeia de funções: só uma Apply por célula no subconjunto"
    return True, ""


def export(records: list[dict], groups: dict | None = None, uri: str = "https://example.org/alignment/x"):
    """groups: {claim_id: {"object_ids": [...]} } para 1:N (entity2 = construção 'and')."""
    groups = groups or {}
    g = rdflib.Graph()
    g.bind("align", ALIGN)
    g.bind("edoal", EDOAL)
    g.bind("bofn", FN)
    for k, v in PREFIXES.items():
        g.bind(k, v)
    al = URIRef(uri)
    g.add((al, RDF.type, ALIGN.Alignment))
    g.add((al, ALIGN.level, Literal("2EDOAL")))
    skipped = []
    for i, r in enumerate(sorted(records, key=lambda x: x["claim_id"])):
        ok, why = supported(r)
        if not ok:
            skipped.append({"claim_id": r["claim_id"], "why": why})
            continue
        cell = BNode(f"cell{i}")
        g.add((al, ALIGN.map, cell))
        g.add((cell, RDF.type, ALIGN.Cell))
        e1 = expand(r["subject_id"], PREFIXES)
        g.add((e1, RDF.type, EDOAL.Property))
        g.add((cell, ALIGN.entity1, e1))
        objs = groups.get(r["claim_id"], {}).get("object_ids")
        if objs:
            pc = BNode(f"pc{i}")
            g.add((pc, RDF.type, EDOAL.PropertyConstruction))
            items = [expand(o, PREFIXES) for o in objs]
            for it in items:
                g.add((it, RDF.type, EDOAL.Property))
            lst = BNode(f"pcl{i}")
            Collection(g, lst, items)
            g.add((pc, EDOAL["and"], lst))
            g.add((cell, ALIGN.entity2, pc))
        else:
            e2 = expand(r["object_id"], PREFIXES)
            g.add((e2, RDF.type, EDOAL.Property))
            g.add((cell, ALIGN.entity2, e2))
        g.add((cell, ALIGN.relation, Literal(REL_OUT[r["semantic_relation"]])))
        g.add((cell, ALIGN.measure, Literal("1.0", datatype=XSD.float)))
        fn = r.get("translation_fn")
        fn = fn[0] if isinstance(fn, list) and fn else fn
        if fn:
            tr = BNode(f"tr{i}")
            ap = BNode(f"ap{i}")
            g.add((cell, EDOAL.transformation, tr))
            g.add((tr, RDF.type, EDOAL.Transformation))
            g.add((tr, EDOAL.direction, Literal("o-")))
            g.add((tr, EDOAL.entity1, e1))
            g.add((tr, EDOAL.entity2, ap))
            g.add((ap, RDF.type, EDOAL.Apply))
            g.add((ap, EDOAL.operator, FN[fn["name"]]))
            args = BNode(f"args{i}")
            Collection(g, args, [Literal(json.dumps(fn.get("params") or {}, sort_keys=True))])
            g.add((ap, EDOAL.arguments, args))
        for k in ANNOT:
            if k in r and k != "translation_fn" and r[k] is not None:
                v = json.dumps(r[k], sort_keys=True, ensure_ascii=False) if k in JSON_FIELDS else str(r[k])
                g.add((cell, expand(slot_property(k), PREFIXES), Literal(v)))
        if objs:
            g.add((cell, URIRef(str(FN) + "groupObjects"), Literal(json.dumps(objs))))
    return g, skipped


def reimport(g: rdflib.Graph) -> tuple[list[dict], dict]:
    inv = sorted(((v, k) for k, v in PREFIXES.items()), key=lambda kv: -len(kv[0]))

    def curie(u):
        s = str(u)
        for ns, p in inv:
            if s.startswith(ns):
                return f"{p}:{s[len(ns):]}"
        return s
    slot = {str(expand(slot_property(k), PREFIXES)): k for k in ANNOT}
    recs, groups = [], {}
    for cell in g.subjects(RDF.type, ALIGN.Cell):
        r = {"subject_id": curie(g.value(cell, ALIGN.entity1))}
        e2 = g.value(cell, ALIGN.entity2)
        if (e2, RDF.type, EDOAL.PropertyConstruction) in g:
            items = [curie(x) for x in Collection(g, g.value(e2, EDOAL["and"]))]
            r["object_id"] = None
            grp = {"object_ids": items}
        else:
            r["object_id"] = curie(e2)
            grp = None
        r["semantic_relation"] = REL_IN[str(g.value(cell, ALIGN.relation))]
        r["predicate_id"] = SKOS_PREDICATE[r["semantic_relation"]]
        tr = g.value(cell, EDOAL.transformation)
        if tr is not None:
            ap = g.value(tr, EDOAL.entity2)
            op = str(g.value(ap, EDOAL.operator))
            args = [str(x) for x in Collection(g, g.value(ap, EDOAL.arguments))]
            r["translation_fn"] = {"name": op[len(str(FN)):], "params": json.loads(args[0])}
        for p, o in g.predicate_objects(cell):
            if str(p) in slot:
                k = slot[str(p)]
                r[k] = json.loads(str(o)) if k in JSON_FIELDS else str(o)
        if grp is not None:
            r["object_id"] = r.get("object_id") or None
            groups[r.get("claim_id")] = grp
        recs.append(r)
    return sorted(recs, key=lambda x: x.get("claim_id", "")), groups


def roundtrip(records: list[dict], groups: dict | None = None) -> dict:
    """Exporta, serializa em Turtle, relê e reimporta: o que foi exportado volta igual (campo a campo)."""
    g, skipped = export(records, groups)
    ttl = g.serialize(format="turtle")
    g2 = rdflib.Graph()
    g2.parse(data=ttl, format="turtle")
    back, bgroups = reimport(g2)
    exported = [r for r in sorted(records, key=lambda x: x["claim_id"]) if supported(r)[0]]
    diffs = []
    for a, b in zip(exported, back):
        for k in set(a) | set(b):
            if k in ("object_id",) and a["claim_id"] in (groups or {}):
                continue
            if k not in EXT + ("subject_id", "object_id", "predicate_id"):
                continue
            va, vb = a.get(k), b.get(k)
            if k == "translation_fn" and isinstance(va, list) and len(va) == 1:
                va = va[0]
            if va != vb:
                diffs.append({"claim_id": a["claim_id"], "field": k, "out": va, "back": vb})
    if len(exported) != len(back):
        diffs.append({"count": [len(exported), len(back)]})
    gd = [{"claim_id": k, "out": (groups or {}).get(k), "back": v} for k, v in bgroups.items()
          if (groups or {}).get(k, {}).get("object_ids") != v.get("object_ids")]
    return {"exported": len(exported), "skipped": skipped, "reimported": len(back), "diffs": diffs + gd,
            "same": not diffs and not gd, "turtle_bytes": len(ttl.encode())}
