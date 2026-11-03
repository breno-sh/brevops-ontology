#!/bin/bash
# Gate específico do OFFTAB (chamado por make gate ID=OFFTAB): testes, regeneração idêntica, reprodução das
# tabelas a partir do HTML, contratos C09/C15/C17, manifesto e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/offtab, pytest)"
$py -I -B -m pytest tests/offtab -q -p no:cacheprovider

step "regeneração idêntica (saídas em \$BO_DATA/OFFTAB e results/OFFTAB saem só de src/bo/offtab)"
$py -I -B -m bo.offtab.build --check

step "reprodução: 223 Google e 205 Microsoft a partir do HTML, sha256 do HTML confere; Oracle 160"
$py -I -B -m bo.offtab.repro

step "contratos C09 (tsv e jsonl), C15 e C17 do summary.json"
$py -I -m bo.contracts.validate correspondences "$BO_DATA/OFFTAB/services.sssom.tsv"
$py -I -m bo.contracts.validate correspondences_jsonl "$BO_DATA/OFFTAB/correspondences.jsonl"
$py -I -m bo.contracts.validate summary_results results/OFFTAB/summary.json
$py -I -m bo.contracts.validate C17_summary results/OFFTAB/summary.json

step "obrigações do SEMANTICS: toda alegação relatedMatch sai OK (sem transporte) e nenhum par CONTESTED"
$py -I -B -c '
import json, os, sys
from bo.semantics.obligations import assess, check_set
recs = [json.loads(l) for l in open(os.environ["BO_DATA"] + "/OFFTAB/correspondences.jsonl", encoding="utf-8")]
bad = [a.claim_id for a in map(assess, recs) if a.verdict != "OK"]
cont = check_set(recs)
print(f"{len(recs)} alegações; {len(bad)} fora de OK; {len(cont)} conjunto(s) CONTESTED")
sys.exit(1 if bad or cont else 0)
'

step "manifesto C17 (results/OFFTAB/MANIFEST.sha256)"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
probs = receipts.verify_manifest(Path("results/OFFTAB/MANIFEST.sha256"))
for p in probs:
    print("  FAIL", p["path"], p["problem"])
sys.exit(1 if probs else print("manifesto confere") or 0)
'

step "proveniência do agente"
$py -I tools/provenance.py verify OFFTAB
echo "gates/OFFTAB.sh: OK"
