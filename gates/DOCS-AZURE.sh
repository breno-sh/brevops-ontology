#!/bin/bash
# Gate específico do DOCS-AZURE (chamado por make gate ID=DOCS-AZURE): fonte fixada, testes, regeneração
# idêntica, C03/C15/C17 pelo validador único, cobertura, hashes e proveniência. Nunca chama make gate.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "fonte fixada (cópia da doc na tag do PINS, sha256 de cada arquivo, schema = pins.json)"
$py -I -B -m bo.docs_azure.source verify

step "testes (tests/docs_azure, pytest)"
$py -I -B -m pytest tests/docs_azure -q -p no:cacheprovider

step "regeneração idêntica (docs_facts, type_subcategory e build_report saem só do código)"
$py -I -B -m bo.docs_azure.build --check

step "C03 docs_facts e C15 coverage pelo validador único"
$py -I -B -m bo.contracts.validate docs_facts "$BO_DATA/DOCS-AZURE/docs_facts.jsonl" | tail -1
$py -I -B -m bo.contracts.validate C15 "results/DOCS-AZURE/coverage.json" | tail -1

step "cobertura (relatada, sem meta)"
$py -I -B -m bo.docs_azure.coverage DOCS-AZURE

step "hashes (MANIFEST C17)"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
probs = receipts.verify_manifest(Path("results/DOCS-AZURE/MANIFEST.sha256"))
if probs:
    sys.exit("MANIFEST não confere: " + "; ".join(p["problem"] for p in probs))
n = sum(1 for x in open("results/DOCS-AZURE/MANIFEST.sha256") if x.strip())
print(f"hashes conferem ({n} arquivos)")
'

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/DOCS-AZURE/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/DOCS-AZURE/summary.json", encoding="utf-8"))
if s.get("module") != "DOCS-AZURE" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do DOCS-AZURE ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify DOCS-AZURE
echo "gates/DOCS-AZURE.sh: OK"
