"""Harness do Azure (provider azurerm), offline: renderizador de HCL a partir de um plano de lowering (C26),
conferência de não inserção silenciosa, redator, leitura de volta (C12) e executor apply -> espera -> leitura
-> destroy com backend de respostas gravadas. Módulo HARNESS-AZURE.

Comandos (cada um com main(argv) -> int):
  python -I -m bo.harness.azurerm.render PLANO.jsonl --out DIR [--graph-ir G.jsonl] [--plan-id LP-x]
  python -I -m bo.harness.azurerm.no_silent_insert [PLANO.jsonl ...]
  python -I -m bo.harness.azurerm.build_templates [--schema ARQ] [--check]
  python -I -m bo.harness.azurerm.executor --replay GRAVACAO.json PLANO.jsonl --plan-id LP-x --work DIR

O renderizador nunca inventa valor: campo obrigatório que o plano não traz bloqueia o caso com
UNKNOWN_INPUT (código de bloqueio do C00); símbolo sem valor em posição de valor bloqueia com
UNKNOWN_SYMBOLIC_INPUT. Tudo o que entra no HCL e não é valor do plano está declarado no manifesto do render.
"""
