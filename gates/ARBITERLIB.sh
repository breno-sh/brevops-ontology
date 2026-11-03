#!/bin/bash
# Gate específico do ARBITERLIB (chamado por make gate ID=ARBITERLIB): testes, regeneração idêntica, congelamento,
# contrato C21 nos vereditos da bateria, determinismo, hashes e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo (pytest, unproven, no_llm, permutation, shasum)
# rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:=/Users/breno/doutorado/brevops-data}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/arbiter, pytest)"
$py -I -B -m pytest tests/arbiter -q -p no:cacheprovider

step "regeneração idêntica (arbiter/RULES.html, arbiter/ARBITER.sha256, results/ARBITERLIB/*)"
$py -I -B -m bo.arbiter.build --check

step "árbitro congelado: todo arquivo do fecho de importação no ARBITER.sha256 e conferindo"
$py -I -B -m bo.arbiter.freeze

step "contrato C21 nos vereditos da bateria (validador oficial)"
$py -I -m bo.contracts.validate C21 results/ARBITERLIB/battery_verdicts.jsonl

step "determinismo (duas execuções e ordem inversa, mesmo sha)"
$py -I -B -m bo.arbiter.determinism

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/ARBITERLIB/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/ARBITERLIB/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "ARBITERLIB" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
print("summary.json C17: campos obrigatórios presentes")
'
$py -I tools/provenance.py verify ARBITERLIB
echo "gates/ARBITERLIB.sh: OK"
