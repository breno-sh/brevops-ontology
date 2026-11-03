#!/bin/bash
# Gate específico do REQUIREMENTS (chamado por make gate ID=REQUIREMENTS): testes, regeneração idêntica,
# contrato C24, hashes, proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes unitários (tests/requirements)"
$py -I -B -m unittest discover -s tests/requirements -q

step "regeneração idêntica (requirements/* e results/REQUIREMENTS/* saem só de src/bo/requirements/content)"
$py -I -B -m bo.requirements.build --check

step "contrato C24"
if $py -I -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("bo.contracts.validate") else 1)' 2>/dev/null; then
  for k in requirements commitments cq_spec; do
    $py -I -m bo.contracts.validate "$k" "requirements/$k.jsonl"
  done
else
  echo "SKIP bo.contracts.validate: ainda não existe (CONTRACTS depende de SEMANTICS, que depende deste módulo)"
fi
for k in requirements commitments cq_spec; do
  $py -I -B -m bo.requirements.validate "$k" "requirements/$k.jsonl"
done

step "hashes (REQUIREMENTS.sha256 e MANIFEST C17)"
shasum -a 256 -c requirements/REQUIREMENTS.sha256 --quiet
shasum -a 256 -c results/REQUIREMENTS/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/REQUIREMENTS/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "REQUIREMENTS" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
print("summary.json C17: campos obrigatórios presentes")
'
$py -I tools/provenance.py verify REQUIREMENTS
echo "gates/REQUIREMENTS.sh: OK"
