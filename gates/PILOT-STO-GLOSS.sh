#!/bin/bash
# Gate específico do PILOT-STO-GLOSS (chamado por make gate ID=PILOT-STO-GLOSS). Nunca chama make gate.
# Os gates do catálogo (validate glossary, anchor_claims, smoke, consume, privacidade, posse, commits,
# integração) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:=/Users/breno/doutorado/brevops-data}"
cd "$BO_REPO"
py=python
d="$BO_DATA/PILOT-STO-GLOSS"
step() { echo "== $*"; }

step "testes (tests/pilot_sto_gloss): gate anchor_claims com controles, diagnóstico do grão como está"
$py -I -B -m pytest tests/pilot_sto_gloss -q -p no:cacheprovider

step "diagnóstico regenerado idêntico das entradas (results/PILOT-STO-GLOSS/pilot_findings.json)"
$py -I -B -m bo.pilot_sto_gloss.diagnose --check

step "saídas do módulo pelo validador oficial (C19, C20, C08)"
for f in canonical_units canonical_atoms glossary claims decisions; do
  test -f "$d/$f.jsonl" || { echo "saída ausente: $d/$f.jsonl (ver results/PILOT-STO-GLOSS/CONTRACT_CHANGE.txt)"; exit 1; }
done
$py -I -m bo.contracts.validate canonical_units "$d/canonical_units.jsonl"
$py -I -m bo.contracts.validate canonical_atoms "$d/canonical_atoms.jsonl"
$py -I -m bo.contracts.validate glossary "$d/glossary.jsonl"
$py -I -m bo.contracts.validate claims "$d/claims.jsonl"
$py -I -m bo.contracts.validate decisions "$d/decisions.jsonl"
test -f "$d/bundle/candidates.jsonl" || { echo "pacote ausente: $d/bundle/candidates.jsonl"; exit 1; }
$py -I -m bo.contracts.validate candidates "$d/bundle/candidates.jsonl"

step "proveniência C17"
$py -I tools/provenance.py verify PILOT-STO-GLOSS
