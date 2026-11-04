"""O que cada controle SABE sobre os indivíduos levantados (a saída de reason.py, num formato que o translate lê).

  c1_table     só o valor dos átomos (e a estrutura de agrupamento da configuração); nenhuma classe
  c2_taxonomy  + tipos das realizações e fecho de rdfs:subClassOf (owlrl, semântica RDFS) + fatos estruturais
               (sentido pelo bloco/tipo, efeito pelo bloco, efeito pelo valor do átomo de efeito)
  c3_full      + o que o HermiT entaila do catálogo de axiomas (efeito da lista de permissão, decisão sem regra,
               ordem de precedência, desempate, estado padrão) e as violações das formas SHACL

O translate nunca consulta o controle por nome: pergunta ao Knowledge. Assim a mesma entrada, a mesma política de
perda e as mesmas transformações valem nos três; só muda o que o controle consegue saber.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Knowledge:
    control: str
    types: dict = field(default_factory=dict)        # indivíduo -> set(IRIs de classe)
    values: dict = field(default_factory=dict)       # indivíduo -> {propriedade: valor neutro}
    why: dict = field(default_factory=dict)          # (indivíduo, propriedade) -> [axiom_id | realização]
    violations: dict = field(default_factory=dict)   # indivíduo -> [mensagem SHACL]
    structural: bool = False                         # c2+: lê fatos estruturais e codecs de realização
    consistent: bool = True
    infra_error: str | None = None

    def value(self, ind: str, prop: str):
        return self.values.get(ind, {}).get(prop)

    def has_type(self, ind: str, iri: str) -> bool:
        return iri in self.types.get(ind, set())

    def justification(self, ind: str, prop: str) -> list:
        return list(self.why.get((ind, prop), []))
