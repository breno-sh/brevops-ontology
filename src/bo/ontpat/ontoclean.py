"""Verificador OntoClean de rigidez, com a regra CORRIGIDA.

Erro: classe rígida (ou semirrígida) subsumida por classe antirrígida (Pessoa ⊑ Estudante; Instância ⊑
MembroDePool). Válido: classe antirrígida subsumida por rígida (Estudante ⊑ Pessoa; papel sob tipo).
A versão com semirrígida segue a formulação do UFO (tipos rígidos e semirrígidos não especializam
antirrígidos); Guarino & Welty enunciam o caso rígido, que é o que os testes do REQUIREMENTS pedem.

A rigidez vem da anotação bo:rigidity (bo:Rigid, bo:AntiRigid, bo:SemiRigid). A hierarquia pode ser a
asserida (fecho transitivo de rdfs:subClassOf, owl:equivalentClass e interseções nomeadas) ou a inferida
pelo HermiT (pares passados pelo chamador). Classes sem anotação não geram erro, mas são listadas.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from . import common as c

RANK = {c.RIGID: "rigid", c.SEMI: "semi", c.ANTI: "anti"}


@dataclass
class Report:
    violations: list = field(default_factory=list)   # (sub, sup, rig_sub, rig_sup)
    unannotated: list = field(default_factory=list)
    pairs: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations


def rigidity_map(g: rdflib.Graph) -> dict:
    out = {}
    for s, o in g.subject_objects(c.PRED_RIGID):
        if isinstance(s, rdflib.URIRef) and o in RANK:
            out[s] = o
    return out


def asserted_pairs(g: rdflib.Graph) -> set[tuple]:
    edges = defaultdict(set)

    def named(x):
        return isinstance(x, rdflib.URIRef)

    for s, o in g.subject_objects(RDFS.subClassOf):
        if named(s) and named(o):
            edges[s].add(o)
    for s, o in g.subject_objects(OWL.equivalentClass):
        if named(s) and named(o):
            edges[s].add(o)
            edges[o].add(s)
        elif named(s) and isinstance(o, rdflib.BNode):
            lst = g.value(o, OWL.intersectionOf)
            if lst is not None:
                for m in rdflib.collection.Collection(g, lst):
                    if named(m):
                        edges[s].add(m)  # C ≡ A ⊓ ... implica C ⊑ A
    pairs = set()
    for a in list(edges):
        seen, todo = set(), list(edges[a])
        while todo:
            b = todo.pop()
            if b in seen:
                continue
            seen.add(b)
            todo.extend(edges.get(b, ()))
        for b in seen:
            if b != a:
                pairs.add((a, b))
    return pairs


def check(rig: dict, pairs: set[tuple]) -> Report:
    r = Report(pairs=len(pairs))
    seen_unann = set()
    for a, b in sorted(pairs):
        ra, rb = rig.get(a), rig.get(b)
        if ra in (c.RIGID, c.SEMI) and rb == c.ANTI:
            r.violations.append((str(a), str(b), RANK[ra], RANK[rb]))
        for x in (a, b):
            if x not in rig and x not in seen_unann and str(x).startswith(str(c.BO)):
                seen_unann.add(x)
    r.unannotated = sorted(str(x) for x in seen_unann)
    return r


def check_graph(g: rdflib.Graph, extra_pairs: set[tuple] | None = None) -> Report:
    pairs = asserted_pairs(g)
    if extra_pairs:
        pairs |= set(extra_pairs)
    return check(rigidity_map(g), pairs)
