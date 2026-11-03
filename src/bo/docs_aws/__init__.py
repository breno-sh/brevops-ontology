"""DOCS-AWS: documentação do provider aws na versão fixada pelo PINS -> fatos por atributo (C03) e por tipo.

Módulos:
  source    pré-busca conferida (sha256 do MANIFEST, git blob sha1 da árvore da tag no GitHub) e cópia para
            $BO_DATA/downloads/docs-aws/ com SOURCE.txt; nada da documentação é executado
  mdparse   leitura linha a linha do markdown (frontmatter, seções, blocos, itens de lista, cercas de código)
  cues      sinais textuais por item (parêntese de flags, default, valores válidos, faixa, unidade, formato...)
  resolve   item da documentação -> átomo do schema (C01) na mesma versão
  build     fatos (docs_facts.jsonl), subcategoria e importação por tipo (type_subcategory.jsonl), cobertura
  coverage  gate: recalcula a cobertura a partir dos arquivos gravados e confere com results/DOCS-AWS/coverage.json
"""
