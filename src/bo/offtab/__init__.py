"""OFFTAB: tabelas oficiais de comparação de serviços (Google, Microsoft, Oracle) como alegações C09 só de auditoria.

As tabelas são afirmações dos fornecedores no nível de SERVIÇO (nunca de tipo Terraform nem de atributo). Elas não
definem universo nem classes: servem para auditar quanto um recorte ancorado na AWS deixa de fora. Cada linha do
fornecedor vira alegações skos:relatedMatch (sem transporte de valor) com URL, data de coleta e sha256 do HTML.

Módulos:
  sources     caminhos, URLs, datas e sha256 esperados de cada fonte
  htmltables  extrator de tabelas HTML (html.parser da biblioteca padrão; nada é executado)
  google      linhas da tabela do Google (223)
  microsoft   linhas das tabelas da Microsoft (205)
  oracle      linhas da tabela da Oracle (JSON embutido no pacote JavaScript da página, lido como texto)
  mentions    regra de separação das células em menções de serviço
  claims      alegações C09 e catálogo de serviços
  audit       métricas de centralidade da AWS (C15)
  build       grava as saídas (services.sssom.tsv, service_catalog.json, summary.json); --check confere
  repro       gate: 223 e 205 linhas reproduzidas a partir do HTML, sha256 do HTML confere
"""
