#!/bin/bash
# Gate específico do SEMANTICS (chamado por make gate ID=SEMANTICS): testes, regeneração idêntica, validação do
# C09/C10 (proposta), contraexemplos, compromissos do REQUIREMENTS, hashes e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo (skos_roundtrip, composition_check, counterexamples)
# rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "schema SKOS do W3C presente e com o sha256 fixado (dado baixado, só lido)"
$py -I -B -c 'from bo.semantics import owl_theory as O; O.skos_graph(); print("core.rdf confere")'

step "testes (tests/semantics, pytest)"
$py -I -B -m pytest tests/semantics -q -p no:cacheprovider

step "regeneração idêntica (semantics/*, results/SEMANTICS/* saem só de src/bo/semantics)"
$py -I -B -m bo.semantics.build --check

step "contratos C09 e C10"
if $py -I -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("bo.contracts.validate") else 1)' 2>/dev/null; then
  echo "bo.contracts.validate existe: o C09/C10 publicado manda; conferir as propostas contra ele"
  $py -I -m bo.contracts.validate C10_composition_table semantics/composition_table.json
else
  echo "SKIP bo.contracts.validate: ainda não existe (CONTRACTS depende do SEMANTICS na ordem do plano)"
fi
$py -I -B -m bo.semantics.validate c09 results/SEMANTICS/C09_proposta/examples.sssom.tsv
$py -I -B -m bo.semantics.validate composition_table semantics/composition_table.json
$py -I -B -m bo.semantics.validate counterexamples semantics/counterexamples.jsonl

step "hashes (SEMANTICS.sha256 e MANIFEST C17)"
shasum -a 256 -c semantics/SEMANTICS.sha256 --quiet
shasum -a 256 -c results/SEMANTICS/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/SEMANTICS/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "SEMANTICS" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
print("summary.json C17: campos obrigatórios presentes")
'
$py -I tools/provenance.py verify SEMANTICS
echo "gates/SEMANTICS.sh: OK"
