#!/bin/bash
# Gate específico do PILOT-STO-ORACLE (chamado por make gate ID=PILOT-STO-ORACLE): testes do oráculo e do módulo,
# regeneração idêntica da calibração, schema fixado, cobertura com retidas seladas, hashes (C17) e proveniência.
# Offline: nunca decifra as retidas (a chave privada fica na VM, D15) e nunca toca nuvem.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/PILOT-STO-ORACLE}"
export TMPDIR="$BO_TMP"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes do oráculo (pilot/sto/oracle: exemplos documentados e calibração)"
$py -I -B -m pytest pilot/sto/oracle -q -p no:cacheprovider

step "testes do módulo (tests/pilot_sto_oracle: o gate de cobertura reprova o que promete)"
$py -I -B -m pytest tests/pilot_sto_oracle -q -p no:cacheprovider

step "regeneração idêntica (fixtures_calib, expected_answers.json, MANDATORY.json, RULES.json) e selo x índice"
$py -I -B -m bo.pilot_sto_oracle.build --check

step "contrato C24 1.1.0 (pilot_expected_answers) do gabarito"
$py -I -m bo.contracts.validate pilot_expected_answers pilot/sto/expected_answers.json | tail -1

step "configuração das fixtures de calibração contra o schema do provider fixado"
$py -I -B -m bo.pilot_sto_oracle.schema_check

step "cobertura: casos obrigatórios e direções com positivo, negativo e desconhecido; retidas >= 30% e só cifradas"
$py -I -B -m bo.pilot_sto_oracle.oracle_coverage --slice sto

step "hashes do oráculo (ORACLE.sha256) e dos resultados (MANIFEST C17)"
shasum -a 256 -c pilot/sto/ORACLE.sha256 --quiet
shasum -a 256 -c results/PILOT-STO-ORACLE/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "privacidade do que vai para o git (pilot/sto)"
$py -I tools/privacy_lint.py --strict pilot/sto | tail -1

step "summary.json C17 e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/PILOT-STO-ORACLE/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/PILOT-STO-ORACLE/summary.json", encoding="utf-8"))
if s.get("module") != "PILOT-STO-ORACLE" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do PILOT-STO-ORACLE ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify PILOT-STO-ORACLE
echo "gates/PILOT-STO-ORACLE.sh: OK"
