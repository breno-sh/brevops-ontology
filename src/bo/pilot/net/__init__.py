"""Piloto NET de ponta a ponta (PILOT-NET-E2E): OWL da fatia -> lifting -> 3 controles -> IR de grafo -> lowering.

Fatia: regras de segurança de rede (security group AWS inline e standalone, firewall GCP, NSG Azure, security list e
NSG OCI). Tudo offline. Módulos:

  vocab       realizações por provedor (padrão de descritor do ONTPAT): que construção Terraform realiza cada classe
              e propriedade neutra, com codec de valor e evidência citada (SERVICE-EVIDENCE ou C03)
  axioms      catálogo de axiomas do controle c3, cada um com evidência e nível; só published/derived entram
  claims      leitura do C09 (SSSOM) + C21 (vereditos): só alegações OK transportam; índice por par e direção
  synthetic   alegações SINTÉTICAS (marcadas SYNTH) para testar o caminho antes do mapeamento real
  lift        configuração da fixture -> indivíduos neutros (ABox) e decomposição em unidades
  owlgen      módulo OWL da fatia (TTL) e tabelas C14 a partir das alegações OK e do catálogo de axiomas
  reason      os três controles: c1_table (tabela, sem inferência), c2_taxonomy (taxonomia + realizações),
              c3_full (axiomatização completa, HermiT pelo ROBOT fixado)
  translate   indivíduos + consequências do controle -> IR de grafo (C26) e plano de lowering (C26) + traço C23
  render      plano -> HCL pelos renderizadores dos HARNESS-*; HCL relido (python-hcl2) -> configuração do oráculo
  tfval       terraform validate offline no provider fixado, sandbox sem credenciais (D1)
  oracle      ponte para o oráculo congelado (pilot/net/oracle/net_oracle), sem tocar no código dele
  pipeline    orquestra fixture x direção x controle, grava traço, plano, resultados e esforço

O mesmo código roda sobre as fixtures de calibração (este módulo) e sobre as retidas (PILOT-EXIT, --fixtures-dir).
"""

SLICE = "net"
MODULE = "PILOT-NET-E2E"
MODEL_ID = "claude-opus-5-5"
PROVIDERS = ("aws", "google", "azurerm", "oci")
DIRECTIONS = tuple(f"{a}->{b}" for a in PROVIDERS for b in PROVIDERS if a != b)
CONTROLS = ("c1_table", "c2_taxonomy", "c3_full")
CONTROL_CODE = {"c1_table": "c1", "c2_taxonomy": "c2", "c3_full": "c3"}
PAIR_CODE = {"aws": "AWS", "google": "GCP", "azurerm": "AZ", "oci": "OCI"}
