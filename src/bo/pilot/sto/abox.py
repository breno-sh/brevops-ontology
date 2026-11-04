"""ABox da fatia e o raciocinador RL usado pelos controles c2 e c3.

O ABox de uma configuração levantada (bo.pilot.sto.lift) tem indivíduos para contêineres, namespaces, facetas e
regras, as arestas de dono e de contenção e os valores dos conceitos. O raciocinador aplica, sobre o TBox do
controle (o TTL gerado por bo.pilot.sto.owl), as regras OWL 2 RL dos construtores que o módulo usa:
  cax-sco (subClassOf), prp-spo1 (subPropertyOf), prp-inv (inverseOf), prp-spo2 (cadeia de 2), prp-dom/prp-rng,
  cax-dw/cax-adc (disjunção -> conflito), prp-fp em literal (dois valores distintos -> conflito).
É um subconjunto fiel do OWL 2 RL (o teste confere contra o owlrl no mesmo grafo) e roda em milissegundos; o
HermiT do ROBOT fixado confere o módulo e um ABox agregado (bo.pilot.sto.robot).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

from . import common as C
from . import tbox as T

TYPE = str(RDF.type)
IND = "https://w3id.org/brevops/ontology/sto/ind/"


def S(local: str) -> str:
    return T.STO + local


@dataclass
class TBoxIndex:
    level: str
    sub: dict = field(default_factory=dict)        # classe -> {superclasses diretas}
    subprop: dict = field(default_factory=dict)
    domain: dict = field(default_factory=dict)
    range: dict = field(default_factory=dict)
    inverse: dict = field(default_factory=dict)
    chains: list = field(default_factory=list)     # (sup, p1, p2)
    disjoint: set = field(default_factory=set)     # frozenset({a, b})
    functional: set = field(default_factory=set)
    axioms: dict = field(default_factory=dict)     # chave legível -> texto do axioma (justifying_axioms)

    def supers(self, c: str) -> set:
        out, todo = set(), [c]
        while todo:
            x = todo.pop()
            for y in self.sub.get(x, ()):
                if y not in out:
                    out.add(y)
                    todo.append(y)
        return out


def _short(u) -> str:
    s = str(u)
    for pfx, ns in (("sto:", T.STO), ("bo:", T.BO), ("owl:", str(OWL)), ("rdfs:", str(RDFS))):
        if s.startswith(ns):
            return pfx + s[len(ns):]
    return s


def index_tbox(g: Graph, level: str) -> TBoxIndex:
    ix = TBoxIndex(level)
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
        if isinstance(o, URIRef):
            ix.sub.setdefault(str(s), set()).add(str(o))
            ix.axioms[f"sco:{_short(s)}"] = f"{_short(s)} ⊑ {_short(o)}"
    for s, _, o in g.triples((None, RDFS.subPropertyOf, None)):
        ix.subprop.setdefault(str(s), set()).add(str(o))
        ix.axioms[f"spo:{_short(s)}:{_short(o)}"] = f"{_short(s)} ⊑ {_short(o)}"
    for s, _, o in g.triples((None, RDFS.domain, None)):
        ix.domain.setdefault(str(s), set()).add(str(o))
    for s, _, o in g.triples((None, RDFS.range, None)):
        ix.range.setdefault(str(s), set()).add(str(o))
    for s, _, o in g.triples((None, OWL.inverseOf, None)):
        ix.inverse.setdefault(str(s), set()).add(str(o))
        ix.inverse.setdefault(str(o), set()).add(str(s))
        ix.axioms[f"inv:{_short(s)}"] = f"{_short(s)} ≡ {_short(o)}⁻"
    for s, _, lst in g.triples((None, OWL.propertyChainAxiom, None)):
        items = [str(x) for x in Collection(g, lst)]
        if len(items) == 2:
            ix.chains.append((str(s), items[0], items[1]))
            ix.axioms[f"chain:{_short(items[0])}:{_short(items[1])}"] = (
                f"{_short(items[0])} ∘ {_short(items[1])} ⊑ {_short(s)}")
    for s, _, o in g.triples((None, OWL.disjointWith, None)):
        ix.disjoint.add(frozenset((str(s), str(o))))
    for n in g.subjects(RDF.type, OWL.AllDisjointClasses):
        for lst in g.objects(n, OWL.members):
            items = [str(x) for x in Collection(g, lst)]
            for i, a in enumerate(items):
                for b in items[i + 1:]:
                    ix.disjoint.add(frozenset((a, b)))
            ix.axioms["adc:" + "|".join(sorted(_short(x) for x in items))] = (
                "AllDisjoint(" + ", ".join(sorted(_short(x) for x in items)) + ")")
    for s in g.subjects(RDF.type, OWL.FunctionalProperty):
        ix.functional.add(str(s))
    return ix


@lru_cache(maxsize=8)
def load_tbox(path: str, level: str) -> TBoxIndex:
    g = Graph()
    g.parse(path, format="turtle")
    return index_tbox(g, level)


@dataclass
class Closure:
    triples: set
    clashes: list
    used: set            # chaves de axioma que produziram alguma tripla nova

    def objects(self, s: str, p: str) -> list[str]:
        return sorted(o for (a, b, o) in self.triples if a == s and b == p)

    def types(self, s: str) -> set:
        return {o for (a, b, o) in self.triples if a == s and b == TYPE}


def reason(triples: set, ix: TBoxIndex | None) -> Closure:
    """Fecho RL das triplas sob o TBox do controle (None = sem raciocínio, c1)."""
    tr = set(triples)
    used: set = set()
    if ix is None:
        return Closure(tr, [], used)
    changed = True
    while changed:
        changed = False
        new = set()
        by_p: dict[str, list] = {}
        for (s, p, o) in tr:
            by_p.setdefault(p, []).append((s, o))
        for s, o in by_p.get(TYPE, []):
            for sup in ix.supers(o):
                new.add((s, TYPE, sup))
                used.add(f"sco:{_short(o)}")
        for p, pairs in by_p.items():
            if p == TYPE:
                continue
            for sup in ix.subprop.get(p, ()):
                for s, o in pairs:
                    new.add((s, sup, o))
                used.add(f"spo:{_short(p)}:{_short(sup)}")
            for q in ix.inverse.get(p, ()):
                for s, o in pairs:
                    if not o.startswith("L:"):
                        new.add((o, q, s))
                used.add(f"inv:{_short(p)}" if f"inv:{_short(p)}" in ix.axioms else f"inv:{_short(q)}")
            for d in ix.domain.get(p, ()):
                for s, _ in pairs:
                    new.add((s, TYPE, d))
            for r in ix.range.get(p, ()):
                for _, o in pairs:
                    if not o.startswith("L:"):
                        new.add((o, TYPE, r))
        for sup, p1, p2 in ix.chains:
            first = by_p.get(p1, [])
            second: dict[str, list] = {}
            for y, z in by_p.get(p2, []):
                second.setdefault(y, []).append(z)
            for x, y in first:
                for z in second.get(y, ()):
                    if (x, sup, z) not in tr:
                        used.add(f"chain:{_short(p1)}:{_short(p2)}")
                    new.add((x, sup, z))
        if not new <= tr:
            tr |= new
            changed = True
    clashes = []
    types: dict[str, set] = {}
    vals: dict[tuple, set] = {}
    for (s, p, o) in tr:
        if p == TYPE:
            types.setdefault(s, set()).add(o)
        elif p in ix.functional and o.startswith("L:"):
            vals.setdefault((s, p), set()).add(o)
    for s, ts in types.items():
        for pair in ix.disjoint:
            if pair <= ts:
                a, b = sorted(pair)
                clashes.append({"individual": s, "kind": "disjoint", "classes": [_short(a), _short(b)]})
    for (s, p), vs in vals.items():
        if len(vs) > 1:
            clashes.append({"individual": s, "kind": "functional", "property": _short(p), "values": sorted(vs)})
    return Closure(tr, sorted(clashes, key=C.canon), used)


# ----------------------------------------------------------------------------------------------------------
# ABox de uma configuração levantada
# ----------------------------------------------------------------------------------------------------------
def ind(fid: str, key: str) -> str:
    return IND + C.short_id(fid, key)


def lit(v) -> str:
    return "L:" + C.canon(v)


def abox_of(lf, env: dict | None = None) -> tuple[set, dict]:
    """(triplas, mapa unit_id/endereço -> IRI). env: contexto de implantação (vizinhos no namespace)."""
    fid = lf.fixture_id
    tr: set = set()
    iri: dict[str, str] = {}

    def node(key):
        if key not in iri:
            iri[key] = ind(fid, key)
        return iri[key]

    for uid, u in lf.units.items():
        if u.cls:
            tr.add((node(uid), TYPE, S(u.cls)))
        if u.kind == "FACET" or (u.cls in T.SETTING_CLASSES and isinstance(u.owner, str)):
            ow = u.owner if isinstance(u.owner, str) else ""
            if ow.startswith("container:"):
                tr.add((node(uid), S("facetOfContainer"), node(ow)))
            elif ow.startswith("namespace:"):
                tr.add((node(uid), S("facetOfNamespace"), node(ow)))
                if "C3-SCOPE-PREFIX" not in u.rules:
                    tr.add((node(uid), S("scopeAnchor"), node(ow)))
            elif ow == "account:context":
                tr.add((node(uid), S("facetOfAccount"), node(ow)))
                tr.add((node(uid), S("scopeAnchor"), node(ow)))
        if u.cls == "ObjectContainer":
            ns = u.namespace
            if isinstance(ns, str) and ns.startswith("namespace:"):
                tr.add((node(uid), S("inScope"), node(ns)))
            if lf.provider == "aws":
                tr.add((node(uid), S("inScope"), node("account:context")))
    # seleção por prefixo (regra de modelagem do ciclo de vida de nível de namespace)
    for uid, u in lf.units.items():
        if "C3-SCOPE-PREFIX" in u.rules and isinstance(u.effective_scope, list):
            rnode = node(uid + "#prefix-selection")
            tr.add((node(uid), S("hasRule"), rnode))
            tr.add((rnode, TYPE, S("LifecycleRule")))
            for c in u.effective_scope:
                tr.add((rnode, S("selectsContainer"), node(c)))
    for comp, d in lf.components.items():
        tr.add((node(comp), TYPE, S("LifecycleRule")))
        tr.add((node(d["setting"]), S("hasRule"), node(comp)))
    for v in lf.values:
        if v.role not in ("config", "context"):
            continue
        cls = T.concept_class(v.concept)
        if not cls:
            continue
        subj = v.component if (cls == "LifecycleRule" and v.component) else v.unit_id
        if not subj:
            continue
        if cls == "ObjectContainer" and subj.startswith("namespace:"):
            # conceito do contêiner realizado pelo namespace (ex.: localização da conta Azure): vale para cada
            # contêiner do namespace (projeção por ocorrência), nunca tipa o namespace como contêiner
            for cu, cuu in lf.units.items():
                if cuu.cls == "ObjectContainer" and cuu.namespace == subj:
                    tr.add((node(cu), S(T.prop_local(v.concept)), lit(v.raw)))
            continue
        tr.add((node(subj), S(T.prop_local(v.concept)), lit(v.raw)))
    for b in (env or {}).get("bystanders", []):
        ns = b.get("namespace")
        if ns:
            tr.add((node("container:" + b["container"]), TYPE, S("ObjectContainer")))
            tr.add((node("container:" + b["container"]), S("inScope"), node(ns)))
    return tr, iri


def effective_scope(lf, closure: Closure, iri: dict) -> dict:
    """unit_id da faceta -> contêineres que ela alcança no fecho (appliesTo)."""
    back = {v: k for k, v in iri.items()}
    out = {}
    for uid in lf.units:
        if uid in iri:
            objs = closure.objects(iri[uid], S("appliesTo"))
            out[uid] = sorted(back.get(o, o) for o in objs)
    return out


def tbox_path(level: str) -> Path:
    return C.data_dir() / ".staging" / "owl" / f"sto-{level}.ttl"
