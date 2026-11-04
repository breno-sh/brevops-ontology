"""CORPUS-AWS: uso real dos átomos do provider aws no TerraDS, por repositório e família (C06 usage).

Lê a configuração simbólica do HCL (sem executar HCL) e os átomos do SCHEMA-AWS; conta, por átomo, em quantos
recursos, módulos, repositórios e famílias ele é configurado, e como (literal, simbólico ou retido). Sem split:
a divisão é do SPLIT (C27).

  python -I -m bo.corpus_aws.build [--workers N] [--out DIR]   conta e grava em $BO_DATA/CORPUS-AWS/.staging
  python -I -m bo.corpus_aws.promote                          troca .staging pelas saídas (dentro da trava)
  python -I -m bo.corpus_aws.check [DIR]                      invariantes das saídas contra as entradas
  python -I -m bo.corpus_aws.regen_check                      refaz em $BO_TMP e compara sha256

A biblioteca de contagem (bo.corpus_aws.core) não depende do provedor: o provedor entra como parâmetro.
"""
