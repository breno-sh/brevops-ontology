"""Kit de sondas v3 (PROBEKIT): protocolo completo por tipo e provedor, suporte validado antes do sorteio e
observação local. O kit nunca compara os dois lados de um par: quem julga é o PROBE-JOIN.

Comandos (cada um com main(argv) -> int):
  python -I -m bo.probes.support_matrix [--write]     tipo × provedor × SKU; sem suporte validado, fora do sorteio
  python -I -m bo.probes.cost_cap [--write]           todo template abaixo do limite do tipo (armazenamento,
                                                      tráfego, requisições, horas, resíduo), pelo plan_guard
  python -I -m bo.probes.hashes [--write]             deploy/probes/PROBEKIT.sha256 e results/PROBEKIT/MANIFEST.sha256
  python -I -m bo.probes.selfcheck                    corrida simulada e gravada dos 10 casos validados (só local)
  python -I -m bo.probes.supervisor_heartbeat ID      (PROBE-*) nenhuma janela longa sem heartbeat contínuo
  python -I -m bo.probes.join_complete                (PROBE-JOIN) todo par tem os dois lados ou censura/infra
  python -I -m bo.probes.negative_controls            (PROBE-JOIN) controle negativo falho => par INFRA_ERROR

Módulos:
  common      caminhos, relógio de Recife, durações xsd, gravação atômica
  protocol    protocolo congelado do PREREG (C22 probe_types) + parâmetros do kit + coerência janela/TTL
  cells       os 24 pares tipo × provedor: tipo Terraform, atributos, TTL configurado, SKU
  kinds       efeito de cada tipo de sonda (o que conta como observado e o que é o efeito oposto)
  ops         operações de plano de dados por caso validado (CLI/REST) e os parsers das respostas
  backends    respostas gravadas, simulação determinística e CLI ao vivo (recusa sem GO e sem kit SAFETY)
  runner      pré-condições, repetição, polling, consistência eventual, censura, controle negativo
  templates   _templates/ (HCL), plano sintético para o plan_guard e conferência contra o schema fixado
  tfschema    schema do provider fixado (universe/pins.json), conferido por sha256
"""

MODULE_ID = "PROBEKIT"
KIT_VERSION = "1.0.0"
PROVIDERS = ("aws", "google", "azurerm", "oci")
PROBE_TYPES = ("object_versioning", "object_lifecycle", "item_ttl", "queue_retention", "rate_limit",
               "log_retention")
