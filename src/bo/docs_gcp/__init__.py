"""DOCS-GCP: documentação do provider google (tag fixada) -> fatos por atributo (C03).

A documentação é dado não confiável: lida como texto, nunca executada. Cada fato traz a sentença de origem
(arquivo:linha no repositório oficial, na tag do pin), o método de extração e o nível de evidência.

Módulos:
  sources   pin, caminhos, repositório, tag, commit e data da tag; leitura do schema fixado (átomos C01)
  fetch     reaproveita a pré-busca: confere sha256 de cada página, copia para downloads/docs-google/, confere a tag
            e uma amostra das páginas contra o GitHub, grava SOURCE.txt e SHA256SUMS
  mdparse   página markdown -> front matter, tipos, seções, blocos aninhados, itens de atributo, formatos de import
  extract   padrões declarados (regex) sobre o texto de um item: default, valores válidos, faixa, unidade, formato,
            ForceNew, depreciação, conflitos
  resolve   item da página -> caminho de átomo do schema (links #nested_, nome do bloco, seção Timeouts)
  build     grava docs_facts.jsonl, type_subcategory.jsonl, unresolved.jsonl, redactions.jsonl e
            results/DOCS-GCP/coverage.json; --check regenera e compara
  coverage  gate G2: recalcula a cobertura a partir de docs_facts.jsonl e confere com coverage.json (relatado, sem meta)
"""
