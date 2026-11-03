#!/bin/bash
# Gate específico do CONTRACTS (chamado por make gate ID=CONTRACTS): testes, regeneração idêntica dos schemas,
# stubs e CONTRACTS.html, stubs válidos, C09 complexo, união de desfechos, ids de alegação, arquivos já publicados
# pelos produtores (os gates adiados de REQUIREMENTS, ONTPAT, SEMANTICS, REPO e LIT), hashes e proveniência.
# Nunca chama make gate (sem recursão). O --mutation-test é gate do catálogo (G2).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/contracts, pytest)"
$py -I -B -m pytest tests/contracts -q -p no:cacheprovider

step "regeneração idêntica (contracts/*.schema.json, contracts/stubs/**, contracts/CONTRACTS.html)"
$py -I -B -m bo.contracts.build --check

step "todo stub confere e todo tipo de arquivo tem stub"
$py -I -B -m bo.contracts.validate --all-stubs | tail -1

step "C09 complexo: grupo sobre subgrafo, projeção por ocorrência, alternativas guardadas"
$py -I -B -m bo.contracts.validate correspondences contracts/stubs/complex.sssom.tsv

step "união discriminada de desfechos (C12 = C22) e ids de alegação"
$py -I -B -m bo.contracts.enum_union
$py -I -B -m bo.contracts.claim_ids

step "arquivos publicados pelos produtores no validador único (gates adiados)"
for k in requirements commitments cq_spec; do
  $py -I -B -m bo.contracts.validate "$k" "requirements/$k.jsonl" | tail -1
done
$py -I -B -m bo.contracts.validate realizations results/ONTPAT/C14_proposta/realizations.example.jsonl | tail -1
$py -I -B -m bo.contracts.validate C10_composition_table semantics/composition_table.json | tail -1
for m in REPO LIT ONTPAT REQUIREMENTS SEMANTICS; do
  $py -I -B -m bo.contracts.validate manifest_receipt "results/$m/summary.json" | tail -1
done

step "relatórios (adoção das propostas, produtores) e MANIFEST C17"
$py -I -B -m bo.contracts.report --check
shasum -a 256 -c results/CONTRACTS/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 (pelo próprio validador) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/CONTRACTS/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/CONTRACTS/summary.json", encoding="utf-8"))
if s.get("module") != "CONTRACTS" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do CONTRACTS ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify CONTRACTS
echo "gates/CONTRACTS.sh: OK"
