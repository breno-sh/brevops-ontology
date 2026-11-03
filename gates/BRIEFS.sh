#!/bin/bash
# Gate específico do BRIEFS (chamado por make gate ID=BRIEFS): testes, regeneração idêntica, exemplos nos
# validadores do C09 e do C20, lint e listas de leitura, hashes (C17) e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/briefs, pytest): exemplos, mutações que o lint tem de reprovar, listas, sandbox simulado"
$py -I -B -m pytest tests/briefs -q -p no:cacheprovider

step "regeneração idêntica (briefs/*, read_allowlists.json, manifestos, results/BRIEFS/examples*)"
$py -I -B -m bo.briefs.build --check

step "exemplos nos validadores únicos (C09 TSV e JSONL, C20 glossary, claims, glossary_audit)"
$py -I -m bo.contracts.validate correspondences results/BRIEFS/examples/mapper_examples.sssom.tsv | tail -1
$py -I -m bo.contracts.validate correspondences_jsonl results/BRIEFS/examples/nonehunt_examples.jsonl | tail -1
$py -I -m bo.contracts.validate glossary results/BRIEFS/examples/glossary.jsonl | tail -1
$py -I -m bo.contracts.validate claims results/BRIEFS/examples/claims.jsonl | tail -1
$py -I -m bo.contracts.validate glossary_audit results/BRIEFS/examples/glossary_audit.jsonl | tail -1

step "lint (higiene) e listas de leitura"
$py -I -B -m bo.briefs.lint | tail -1
$py -I -B -m bo.briefs.allowlists | tail -1

step "hashes (MANIFEST C17)"
shasum -a 256 -c briefs/MANIFEST.sha256 --quiet
shasum -a 256 -c results/BRIEFS/MANIFEST.sha256 --quiet
$py -I -m bo.contracts.validate manifest briefs/MANIFEST.sha256 | tail -1
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/BRIEFS/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/BRIEFS/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("module") != "BRIEFS" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17 ou model_id diferente: " + ", ".join(miss))
print("summary.json C17: módulo e model_id conferem")
'
$py -I tools/provenance.py verify BRIEFS
echo "gates/BRIEFS.sh: OK"
