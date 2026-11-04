#!/bin/bash
# Gate específico do CQFIX (chamado por make gate ID=CQFIX): testes, regeneração idêntica, contrato C24 da
# especificação CIS, terraform fmt/validate offline das 4 fixtures (sandbox sem credenciais; nunca plan/apply),
# fixture_check, guarda de SKU, hashes (C17) e proveniência. Nunca chama make gate e nunca toca nuvem.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/cqfix, pytest)"
$py -I -B -m pytest tests/cqfix -q -p no:cacheprovider

step "regeneração idêntica (main.tf x4, expected_answers.json, probes.yaml, cq_spec_cis.jsonl, build_report)"
$py -I -B -m bo.cqfix.build --check

step "contrato C24 da especificação CIS no validador único"
$py -I -m bo.contracts.validate cq_spec results/CQFIX/cq_spec_cis.jsonl | tail -1

step "terraform fmt -check e validate offline nos providers fixados"
$py -I -B -m bo.cqfix.tfcheck

step "fixture_check e guarda de SKU"
$py -I -B -m bo.cqfix.fixture_check
$py -I -B -m bo.cqfix.plan_guard_offline "$BO_REPO/cq/fixtures"

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/CQFIX/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/CQFIX/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/CQFIX/summary.json", encoding="utf-8"))
if s.get("module") != "CQFIX" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do CQFIX ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify CQFIX
echo "gates/CQFIX.sh: OK"
