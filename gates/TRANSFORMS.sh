#!/bin/bash
# Gate específico do TRANSFORMS (chamado por make gate ID=TRANSFORMS): testes, regeneração idêntica, contratos
# C10 (transforms.yaml e conditions.grammar.json no validador único), hashes (C17) e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo (audit, scalar_kind, duration_context, guard_sat)
# rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/transforms, pytest)"
$py -I -B -m pytest tests/transforms -q -p no:cacheprovider

step "regeneração idêntica (transforms/*, results/TRANSFORMS/* saem só de src/bo/transforms)"
$py -I -B -m bo.transforms.build --check

step "contrato C10 no validador único"
$py -I -m bo.contracts.validate transforms transforms/transforms.yaml | tail -1
$py -I -m bo.contracts.validate conditions_grammar transforms/conditions.grammar.json | tail -1

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/TRANSFORMS/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 (validador) e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/TRANSFORMS/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/TRANSFORMS/summary.json", encoding="utf-8"))
if s.get("module") != "TRANSFORMS" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do TRANSFORMS ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify TRANSFORMS
echo "gates/TRANSFORMS.sh: OK"
