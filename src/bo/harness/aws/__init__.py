"""Harness AWS do BrevOps (HARNESS-AWS): renderiza HCL a partir de um plano de lowering (C26) sem inserção
silenciosa e executa apply -> espera -> leitura -> destroy com o redator antes de qualquer gravação.

Módulos:
  pins        versão fixada do provider aws (universe/pins.json) e o schema conferido por sha256
  schema      leitura estrutural do schema do provider (atributos, blocos, obrigatórios, sensíveis, write_only)
  hcl         escrita de HCL canônica (igual à saída de terraform fmt)
  render      plano C26 -> HCL + render_manifest.json; campo obrigatório ausente = UNKNOWN_INPUT
  no_silent_insert  gate: HCL renderizado = plano + inserções declaradas do harness (com mutações)
  redact      redator de base (C00 withheld, C12) composto com o redator do kit de segurança
  backends    respostas gravadas (offline) e a CLI do Terraform (bloqueada sem GO e identidade)
  executor    apply -> espera -> leitura -> destroy, manifestos C16 e desfechos C12
  tf_validate terraform init/validate offline num sandbox sem credenciais

Nesta fase nada toca nuvem: a CLI real só roda com um GoToken explícito e um kit de segurança completo.
"""

PROVIDER = "aws"
PROVIDER_SOURCE = "registry.terraform.io/hashicorp/aws"
MODULE_ID = "HARNESS-AWS"
