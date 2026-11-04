"""PILOT-NET-GLOSS: grão mecânico e glossário da fatia de regras de segurança de rede (piloto net).

Papel glossarista: define conceitos e âncoras átomo→conceito; nunca mapeia átomo↔átomo. O grão sai da
biblioteca bo.grain aplicada como está (adaptador C25 da própria biblioteca). Comandos:
  python -I -m bo.pilot_net_gloss.build [--check]     gera (ou confere por regeneração) todas as saídas
  python -I -m bo.pilot_net_gloss.anchor_claims       gate F4: todo caminho átomo→conceito←átomo entre provedores
"""
