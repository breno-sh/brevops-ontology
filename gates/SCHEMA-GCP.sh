#!/bin/bash
# Gate específico do SCHEMA-GCP (chamado por make gate ID=SCHEMA-GCP): testes, contratos C01/C02, cadeia do pin
# (SHA256SUMS assinado -> lock -> h1 do plugin_cache), paridade com a biblioteca, regeneração offline idêntica,
# manifesto e proveniência C17. Offline: não baixa nada. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/SCHEMA-GCP}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/schema_gcp, pytest)"
$py -I -B -m pytest tests/schema_gcp -q -p no:cacheprovider

step "contratos C01 (2.1.0, com write_only) e C02 no validador único"
$py -I -B -m bo.contracts.validate C01_atoms "$BO_DATA/SCHEMA-GCP/atoms.jsonl" | tail -1
$py -I -B -m bo.contracts.validate C02_types "$BO_DATA/SCHEMA-GCP/types.jsonl" | tail -1

step "pin, paridade com bo.schema.build (só write_only a mais) e análise de causa do crosscheck"
$py -I -B -m bo.schema_gcp.check | tail -2

step "regeneração offline pelo plugin_cache, duas vezes, mesmos sha256"
$py -I -B -m bo.schema_gcp.regen_check

step "manifesto da pasta do módulo (\$BO_DATA/SCHEMA-GCP/MANIFEST.sha256)"
(cd "$BO_DATA/SCHEMA-GCP" && shasum -a 256 -c MANIFEST.sha256 --quiet)
echo "  confere"

step "manifesto dos resultados (results/SCHEMA-GCP/MANIFEST.sha256)"
shasum -a 256 -c results/SCHEMA-GCP/MANIFEST.sha256 --quiet
echo "  confere"

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/SCHEMA-GCP/summary.json | tail -1
$py -I tools/provenance.py verify SCHEMA-GCP
echo "gates/SCHEMA-GCP.sh: OK"
