"""CORPUS-GCP: uso real do provider google no TerraDS, por átomo e por repositório (C06 usage, sem split).

Lê a configuração simbólica do HCL ($BO_DATA/HCL/resources.parquet e symbolic_config.jsonl, pelo índice de
repositórios) e os átomos fixados do SCHEMA-GCP ($BO_DATA/SCHEMA-GCP/atoms.jsonl). Grava
$BO_DATA/CORPUS-GCP/usage.jsonl (C06 usage), os totais por átomo e o relatório de cobertura. Nada de split: a
partição é do SPLIT (C27).
"""
