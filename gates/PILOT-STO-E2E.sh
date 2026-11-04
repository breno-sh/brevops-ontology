#!/bin/bash
# Gate específico do PILOT-STO-E2E (chamado por make gate ID=PILOT-STO-E2E antes dos gates do catálogo): testes da
# biblioteca do piloto, conferência do módulo OWL pelo ROBOT/HermiT fixado, contratos (C14, C15, C23, C26),
# hashes dos resultados (C17) e proveniência. Offline: nada de nuvem, nada de credencial, retidas nunca lidas.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_ID=PILOT-STO-E2E
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/PILOT-STO-E2E}"
export TMPDIR="$BO_TMP"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes da biblioteca do piloto (tests/pilot/sto: alegações sintéticas, canário de 12 direções, raciocinador)"
$py -I -B -m pytest tests/pilot/sto -q -p no:cacheprovider

step "módulo OWL da fatia: perfil OWL 2 DL do fecho, HermiT = raciocinador RL nas fixtures, conflito detectado"
$py -I -B -m bo.pilot.sto.robot

step "contratos dos resultados (C15) e do staging (C14, C23, C26)"
for f in controls oracle_calib effort; do
  $py -I -m bo.contracts.validate result "results/PILOT-STO-E2E/$f.json" | tail -1
done
$py -I -B -c '
import sys
from bo.pilot.sto import stage as ST
errs = ST.validate_contracts()
if errs:
    sys.exit("staging fora do contrato: " + "; ".join(errs[:5]))
print("staging: C14, C23 e C26 conferem")
'

step "hashes dos resultados (MANIFEST C17)"
shasum -a 256 -c results/PILOT-STO-E2E/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "privacidade do que vai para o git"
$py -I tools/privacy_lint.py --strict src/bo/pilot/sto src/bo/pilot_sto_e2e tests/pilot/sto results/PILOT-STO-E2E | tail -1

step "summary.json C17 e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/PILOT-STO-E2E/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/PILOT-STO-E2E/summary.json", encoding="utf-8"))
if s.get("module") != "PILOT-STO-E2E" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do PILOT-STO-E2E ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify PILOT-STO-E2E
echo "gates/PILOT-STO-E2E.sh: OK"
