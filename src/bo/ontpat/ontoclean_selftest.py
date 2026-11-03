"""Selftest do OntoClean corrigido, nas duas direções, e sobre os artefatos reais.

  python -I -m bo.ontpat.ontoclean_selftest

  aceito    Estudante ⊑ Pessoa (papel sob tipo rígido)
  reprovado Pessoa ⊑ Estudante (rígida sob antirrígida)
  reprovado Instância ⊑ MembroDePool (CMT-LB-N01)
  reprovado Pessoa ⊑ X ⊑ Estudante (indireto) e Pessoa ≡ Estudante (equivalência)
  aceito    MembroDePool ⊑ RecursoEndereçável (CMT-TAX-P01)
  reprovado Tópico ⊑ DestinoDeNotificação (CMT-TAX-N04)
  aceito    o fecho de bo-patterns.ttl, o ABox de exemplo e o vocabulário do teste de topo (zero violações)
  reprovado a mutação exv:ComputeInstance ⊑ exv:BackendMember aplicada ao exemplo real
As respostas esperadas dos três compromissos vêm de requirements/commitments.jsonl.
"""

from __future__ import annotations

import json
import sys

import rdflib

from . import common as c
from . import ontoclean
from . import trial_spec as S

HEAD = """@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix bo: <https://w3id.org/brevops/ontology#> . @prefix x: <https://example.org/oc#> .
x:Pessoa bo:rigidity bo:Rigid . x:Estudante bo:rigidity bo:AntiRigid . x:X bo:rigidity bo:SemiRigid .
x:Instancia bo:rigidity bo:Rigid . x:MembroDePool bo:rigidity bo:AntiRigid . x:RecursoEnderecavel bo:rigidity bo:Rigid .
x:Topico bo:rigidity bo:Rigid . x:DestinoDeNotificacao bo:rigidity bo:AntiRigid .
"""

CASES = [
    ("Estudante ⊑ Pessoa", "x:Estudante rdfs:subClassOf x:Pessoa .", "ACCEPTED", None),
    ("Pessoa ⊑ Estudante", "x:Pessoa rdfs:subClassOf x:Estudante .", "REJECTED", None),
    ("Instância ⊑ MembroDePool", "x:Instancia rdfs:subClassOf x:MembroDePool .", "REJECTED", "CMT-LB-N01"),
    ("Pessoa ⊑ X ⊑ Estudante (indireto, X semirrígida)", "x:Pessoa rdfs:subClassOf x:X . x:X rdfs:subClassOf x:Estudante .", "REJECTED", None),
    ("Pessoa ≡ Estudante", "x:Pessoa owl:equivalentClass x:Estudante .", "REJECTED", None),
    ("MembroDePool ≡ RecursoEndereçável ⊓ ∃membroDe (papel definido sob tipo)",
     "x:MembroDePool owl:equivalentClass [ owl:intersectionOf ( x:RecursoEnderecavel [ a owl:Restriction ; owl:onProperty x:membroDe ; owl:someValuesFrom x:Pool ] ) ] .",
     "ACCEPTED", "CMT-TAX-P01"),
    ("Tópico ⊑ DestinoDeNotificação", "x:Topico rdfs:subClassOf x:DestinoDeNotificacao .", "REJECTED", "CMT-TAX-N04"),
]


def verdict(rep: ontoclean.Report) -> str:
    return "REJECTED" if rep.violations else "ACCEPTED"


def main(argv=None) -> int:
    cm = {}
    for line in (c.repo() / "requirements" / "commitments.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            cm[d["commitment_id"]] = d
    ok_all = True
    for label, ttl, want, cid in CASES:
        if cid:  # a resposta esperada vem do REQUIREMENTS, não daqui
            exp = cm[cid]["expected_answer"]["value"]
            want_req = "REJECTED" if exp == "REJECTED" else "ACCEPTED"
            if want_req != want:
                c.emit(f"FALHA {label}: esperado no teste {want} difere do REQUIREMENTS ({cid}: {exp})")
                ok_all = False
                continue
        g = rdflib.Graph().parse(data=HEAD + ttl, format="turtle")
        rep = ontoclean.check_graph(g)
        got = verdict(rep)
        ok = got == want
        ok_all &= ok
        c.emit(f"{'ok  ' if ok else 'FALHA'} {label}: {got}" + (f" ({cid})" if cid else "")
               + (f"; violação: {rep.violations[0][0].split('#')[-1]} ⊑ {rep.violations[0][1].split('#')[-1]}" if rep.violations else ""))

    pdir = c.patterns_dir()
    closure, _ = c.load_closure(pdir / c.PATTERNS)
    ex = rdflib.Graph()
    ex += closure
    c.parse(pdir / c.EXAMPLE, ex)
    tv = rdflib.Graph()
    tv += closure
    tv.parse(data=S.PREFIXES + S.TRIAL_TBOX, format="turtle")
    for label, g in (("fecho de bo-patterns.ttl", closure), ("ABox de exemplo + fecho", ex), ("vocabulário do teste de topo + fecho", tv)):
        rep = ontoclean.check_graph(g)
        ok = rep.ok and not rep.unannotated
        ok_all &= ok
        c.emit(f"{'ok  ' if ok else 'FALHA'} {label}: {len(rep.violations)} violações em {rep.pairs} pares de subsunção; "
               f"classes bo: sem rigidez = {len(rep.unannotated)}" + (f" {rep.unannotated[:5]}" if rep.unannotated else ""))
    mut = rdflib.Graph()
    mut += ex
    mut.add((c.EXV.ComputeInstance, rdflib.RDFS.subClassOf, c.EXV.BackendMember))
    rep = ontoclean.check_graph(mut)
    ok = not rep.ok
    ok_all &= ok
    c.emit(f"{'ok  ' if ok else 'FALHA'} mutação no exemplo real (instância ⊑ membro de pool): {verdict(rep)}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
