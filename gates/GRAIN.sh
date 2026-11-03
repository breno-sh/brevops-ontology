#!/bin/bash
# Gate específico do GRAIN (chamado por make gate ID=GRAIN): testes, regeneração idêntica, contrato C19 nos
# exemplos, verificadores do DECOMPOSE nos mundos sintéticos, hashes e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo (unknown_exit, priority, lint, RULES.sha256) rodam
# depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:=/Users/breno/doutorado/brevops-data}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/grain, pytest): embalagens, reordenação, compromissos, regras, adaptador C25, verificadores"
$py -I -B -m pytest tests/grain -q -p no:cacheprovider

step "regeneração idêntica (grain/GRAIN.html, grain/RULES.sha256, results/GRAIN/*, exemplos C19 em \$BO_DATA/GRAIN)"
$py -I -B -m bo.grain.build --check

step "contrato C19 nos exemplos gerados (validador oficial)"
shopt -s nullglob
ex=("$BO_DATA"/GRAIN/c19_examples/*/canonical_units.jsonl "$BO_DATA"/GRAIN/c19_examples/*/canonical_atoms.jsonl)
if [ ${#ex[@]} -lt 2 ]; then echo "exemplos C19 ausentes em $BO_DATA/GRAIN/c19_examples"; exit 1; fi
$py -I -m bo.contracts.validate C19 "${ex[@]}"

step "verificadores que o DECOMPOSE chama, nos mundos sintéticos (com controles quebrados)"
$py -I -B -m bo.grain.coverage --fixtures
$py -I -B -m bo.grain.permutation --fixtures --rename
$py -I -B -m bo.grain.relations --fixtures

step "hashes (RULES.sha256 e MANIFEST C17)"
shasum -a 256 -c grain/RULES.sha256 --quiet
shasum -a 256 -c results/GRAIN/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/GRAIN/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "GRAIN" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
print("summary.json C17: campos obrigatórios presentes")
'
$py -I tools/provenance.py verify GRAIN
echo "gates/GRAIN.sh: OK"
