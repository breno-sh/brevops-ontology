"""Lint de nomes do núcleo pelas regras de naming_rules.yaml. Higiene, não validade (N6).

  python -I -m bo.ontpat.naming
"""

from __future__ import annotations

import re
import sys

import rdflib
import yaml
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from . import common as c


def rules() -> dict:
    return yaml.safe_load((c.patterns_dir() / "naming_rules.yaml").read_text(encoding="utf-8"))


def lint(g: rdflib.Graph, r: dict) -> list[str]:
    ns = r["namespaces"]["terms"]
    bad = []
    toks = [t.lower() for k in ("providers", "provider_terms") for t in r["forbidden_tokens"][k]]
    tok_re = re.compile(r"(?<![a-z0-9])(" + "|".join(map(re.escape, toks)) + r")(?![a-z0-9])", re.I)
    suf = r["forbidden_tokens"]["legacy_suffixes"]
    cls_re, prop_re = re.compile(r["classes"]["local_name"]), re.compile(r["properties"]["local_name"])

    def local(x):
        return str(x)[len(ns):]

    def words(x):  # nome local em palavras (camelCase -> palavras) para o teste de token
        return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", local(x)).replace("_", " ")

    classes = {s for s in g.subjects(RDF.type, OWL.Class) if str(s).startswith(ns)}
    props = {s for t in (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty) for s in g.subjects(RDF.type, t)
             if str(s).startswith(ns)}
    for x in sorted(classes):
        if not cls_re.match(local(x)):
            bad.append(f"classe fora do padrão de nome: {local(x)}")
        if not any(getattr(l, "language", None) == "pt" for l in g.objects(x, RDFS.label)):
            bad.append(f"classe sem rdfs:label @pt: {local(x)}")
        if not list(g.objects(x, SKOS.definition)):
            bad.append(f"classe sem skos:definition: {local(x)}")
        if (x, c.BO.rigidity, None) not in g:
            bad.append(f"classe sem bo:rigidity: {local(x)}")
    for x in sorted(props):
        if not prop_re.match(local(x)):
            bad.append(f"propriedade fora do padrão de nome: {local(x)}")
        if not any(getattr(l, "language", None) == "pt" for l in g.objects(x, RDFS.label)):
            bad.append(f"propriedade sem rdfs:label @pt: {local(x)}")
        n = len(list(g.objects(x, RDFS.domain)))
        if n > 1:
            bad.append(f"propriedade com {n} rdfs:domain (use união): {local(x)}")
    for x in sorted(classes | props):
        texts = [words(x)] + [str(o) for p in (RDFS.label, SKOS.definition) for o in g.objects(x, p)]
        for t in texts:
            m = tok_re.search(t)
            if m:
                bad.append(f"token de provedor '{m.group(1)}' em {local(x)}")
                break
        for s in suf:
            if local(x).endswith(s):
                bad.append(f"sufixo legado '{s}' em {local(x)}")
    return bad


def main(argv=None) -> int:
    g, _ = c.load_closure(c.patterns_dir() / c.PATTERNS)
    bad = lint(g, rules())
    for b in bad:
        c.emit("NOME: " + b)
    if not bad:
        n = sum(1 for _ in g.subjects(RDF.type, OWL.Class))
        c.emit(f"naming ok (higiene): fecho de bo-patterns.ttl sem token de provedor, padrões de nome, rótulo @pt, definição e rigidez em toda classe ({n} classes)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
