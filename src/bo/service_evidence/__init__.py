"""SERVICE-EVIDENCE: fatos de API e de docs ligados aos pins (C25), com citação separada de inferência.

Módulos:
  common    caminhos, pins, fontes fixadas, redação, resolução de citação, ids
  sources   leitura tolerante das entradas (type_subcategory nas 4 variantes, docs_facts, shared_block_map, schema)
  extract   fatos mecânicos por tipo e por atributo (publicado / derivado / desconhecido)
  curated   fatos interpretados das fatias dos pilotos (rede e armazenamento), cada um ancorado numa frase literal
  protocol  tabela de suporte de protocolo por tipo de sonda e provedor (protocol_support.jsonl)
  build     gera tudo; --check regera em memória e compara byte a byte
  levels    gate: todo fato tem nível; publicado resolve na fonte fixada; interpretado tem model_id
  pinned    gate: toda fonte ligada a um pin e com data
  manifest  MANIFEST.sha256 (C17)
"""
