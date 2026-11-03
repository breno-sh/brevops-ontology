#!/bin/bash
# Gate específico do DOCS-AWS (chamado por make gate ID=DOCS-AWS): fonte fixada e conferida, testes, regeneração
# idêntica, C03 e C15 pelo validador único, proveniência de cada sentença citada (arquivo:linha), cobertura
# recalculada, hashes e proveniência do agente. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "fonte fixada: pin do PINS, sha256 do MANIFEST da pré-busca, git blob sha1 da tag (offline) e MANIFEST da cópia"
$py -I -B -m bo.docs_aws.source --verify

step "testes (tests/docs_aws, pytest)"
$py -I -B -m pytest tests/docs_aws -q -p no:cacheprovider

step "regeneração idêntica (\$BO_DATA/DOCS-AWS/* e results/DOCS-AWS/coverage.json saem só do código)"
$py -I -B -m bo.docs_aws.build --check

step "C03 docs_facts e C15 coverage pelo validador único"
$py -I -B -m bo.contracts.validate docs_facts "$BO_DATA/DOCS-AWS/docs_facts.jsonl" | tail -1
$py -I -B -m bo.contracts.validate result results/DOCS-AWS/coverage.json | tail -1

step "proveniência: toda sentença citada está no arquivo:linha da cópia conferida"
$py -I -B -m bo.docs_aws.audit provenance

step "cobertura recalculada confere com results/DOCS-AWS/coverage.json"
$py -I -B -m bo.docs_aws.coverage DOCS-AWS | tail -1

step "hashes (MANIFEST C17)"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
probs = receipts.verify_manifest(Path("results/DOCS-AWS/MANIFEST.sha256"))
if probs:
    sys.exit("MANIFEST não confere: " + "; ".join(p["problem"] for p in probs))
n = sum(1 for x in open("results/DOCS-AWS/MANIFEST.sha256") if x.strip())
print(f"hashes conferem ({n} arquivos)")
'

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/DOCS-AWS/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/DOCS-AWS/summary.json", encoding="utf-8"))
if s.get("module") != "DOCS-AWS" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do DOCS-AWS ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify DOCS-AWS
echo "gates/DOCS-AWS.sh: OK"
