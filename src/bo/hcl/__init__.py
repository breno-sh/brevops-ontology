"""HCL: leitor do TerraDS para a configuração SIMBÓLICA do C06 (sem executar HCL).

Módulos:
  common      caminhos, ids sintéticos (R-, F-, SYM-), escrita canônica
  source      leitura do TerraDS (tar de tars e sqlite imutável), sem extrair nada em disco
  hclast      árvore Lark do python-hcl2 -> AST neutra (com timeout por arquivo)
  classify    cadeias: documento JSON, CIDR, IP, ARN, número, retido, vocabulário comum
  symbolize   AST neutra -> termos C06 (literal | símbolo | expressão | documento | referência | retido)
  render      termo -> HCL, com a tabela privada em memória (só para o roundtrip; nunca gravada)
  extract     as duas passadas (vocabulário, termos) e a escrita das saídas
  stats, symbolic_roundtrip, crosscheck   gates do catálogo
"""
