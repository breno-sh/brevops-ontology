"""bo.briefs: briefs congelados dos papéis restritos (módulo BRIEFS, contratos C09 e C20).

Cinco briefs (glossarista, mapeador, caçador de NONE, auditor e avaliador) e a lista de leitura por papel
(briefs/read_allowlists.json) que o bo-lane transforma no sandbox de cada worktree. Os briefs são gerados a partir
de modelos (templates/) e de exemplos sintéticos executados contra a implementação de referência do SEMANTICS
(examples), para que toda alegação-exemplo citada no texto tenha o veredito que o texto diz que ela tem.

Comandos (main(argv) -> int):
  python -I -m bo.briefs.build [--check]   gera (ou confere, byte a byte) briefs/, read_allowlists.json e o manifesto
  python -I -m bo.briefs.lint              higiene dos briefs (3 campos, direção SKOS com exemplo, proibidos,
                                           nenhum caminho de avaliação) mais a execução dos exemplos citados
  python -I -m bo.briefs.allowlists        todo papel tem lista de leitura; nenhuma lista alcança a partição de teste
"""
