#!/bin/bash
# Gate específico do PILOT-NET-E2E (chamado por make gate ID=PILOT-NET-E2E): testes do pacote, contratos dos
# resultados e das saídas, regeneração idêntica dos resultados, manifesto (C17) e proveniência.
# Nunca chama make gate, nunca lê as fixtures retidas e nunca toca nuvem.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
R=results/PILOT-NET-E2E
D="$BO_DATA/PILOT-NET-E2E"
step() { echo "== $*"; }

step "testes do pacote (tests/pilot/net, alegações sintéticas)"
$py -I -B -m pytest tests/pilot/net -q -p no:cacheprovider

step "resultados C15 (controls, oracle_calib, effort)"
for f in controls oracle_calib effort; do
  $py -I -m bo.contracts.validate result "$R/$f.json" | tail -1
done

step "saídas no BO_DATA: traço C23, plano e IR C26, tabelas C14"
$py -I -m bo.contracts.validate translation_trace "$D/translation_trace.jsonl" | tail -1
$py -I -m bo.contracts.validate lowering_plan "$D/lowering_plan.jsonl" | tail -1
$py -I -m bo.contracts.validate graph_ir "$D/graph_ir.jsonl" | tail -1
for t in classes properties realizations; do
  $py -I -m bo.contracts.validate "$t" "$D/ontology/$t.jsonl" | tail -1
done

step "regeneração idêntica dos resultados (mapeamento real, carimbo fixo)"
$py -I -B -m bo.pilot_net_e2e.publish --check

step "hashes (MANIFEST C17) e proveniência do agente"
shasum -a 256 -c "$R/MANIFEST.sha256" --quiet
echo "hashes conferem"
$py -I -m bo.contracts.validate manifest_receipt "$R/summary.json" | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/PILOT-NET-E2E/summary.json", encoding="utf-8"))
if s.get("module") != "PILOT-NET-E2E" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do PILOT-NET-E2E ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify PILOT-NET-E2E
echo "gates/PILOT-NET-E2E.sh: OK"
