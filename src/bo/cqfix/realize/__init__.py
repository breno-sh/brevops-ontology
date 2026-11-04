"""Realizadores por provedor. Interface de cada módulo realize/<provider>.py:

  PROVIDER        "aws" | "google" | "azurerm" | "oci"
  REALIZERS       {cq_id: f(v, c) -> Fx | NA} para as 37 CQs (8 CIS + 29 do REQUIREMENTS)
  header()        -> str: bloco terraform com required_providers fixado (universe/pins.json), blocos provider
                  sem credencial e as variáveis de contexto de implantação (CONTEXT_VARS)
  CONTEXT_VARS    {nome: descrição}: contexto de implantação (run_id, localizações, projeto/compartimento);
                  não são entradas de CQ; o runner do DEP liga os valores, nunca gravados aqui
  ALLOWED_TYPES   {tipo (recurso ou data): {"category": categoria do §10.1 do plano, "cost_class": ...}}
  SKU_RULES       {(tipo, caminho do atributo): [valores literais permitidos]}

Convenções de Fx (ver model.py): entity_map com valores "<endereço>", "<endereço>#<atributo|bloco>",
"probe:<chave>" (chave existe em probe["inputs"]), "implicit:<texto>", "external:<var.x|data.x>: <texto>",
"absent:<texto>". probe = {"kind": static|readback|two_phase|translation, "inputs": {...}}.
"""
