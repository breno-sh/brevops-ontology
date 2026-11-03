#!/bin/bash
# Gate específico do DOCS-OCI (chamado por make gate ID=DOCS-OCI): fonte fixada conferida, testes, regeneração
# idêntica, C03 e C15 pelo validador único, formato proposto do type_subcategory, cobertura recontada, auditoria
# de precisão ainda válida, hashes e proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/DOCS-OCI}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "fonte: docs da tag do PINS == blobs da árvore oficial == pré-busca (sha256)"
$py -I -B -m bo.docs_oci.source verify
test -s "$BO_DATA/downloads/docs-oci/SOURCE.txt"

step "testes (tests/docs_oci, pytest)"
$py -I -B -m pytest tests/docs_oci -q -p no:cacheprovider

step "regeneração idêntica (docs_facts, type_subcategory e coverage saem só do código e da fonte)"
$py -I -B -m bo.docs_oci.build --check

step "C03 docs_facts e C15 coverage pelo validador único"
$py -I -B -m bo.contracts.validate docs_facts "$BO_DATA/DOCS-OCI/docs_facts.jsonl" | tail -1
$py -I -B -m bo.contracts.validate C15 results/DOCS-OCI/coverage.json | tail -1

step "type_subcategory no formato proposto (CONTRACT_CHANGE) e completo contra o schema fixado"
$py -I -B -m bo.docs_oci.typecheck

step "cobertura recontada (relatada, sem meta)"
$py -I -B -m bo.docs_oci.coverage DOCS-OCI

step "auditoria de precisão: todo fact_id auditado existe nos dados atuais"
$py -I -B -c '
import json, os, sys
a = json.load(open("results/DOCS-OCI/precision_audit.json", encoding="utf-8"))
ids = {f["fact_id"] for f in a["round_2_final"]["facts"]}
seen = set()
with open(os.environ["BO_DATA"] + "/DOCS-OCI/docs_facts.jsonl", encoding="utf-8") as f:
    for line in f:
        i = line.find("\"fact_id\":\"")
        fid = line[i + 11:line.index("\"", i + 11)]
        if fid in ids:
            seen.add(fid)
miss = ids - seen
if miss:
    sys.exit(f"auditoria velha: {len(miss)} fact_id(s) auditados não existem mais")
print(f"auditoria: {len(ids)} fatos auditados ainda presentes")
'

step "hashes (MANIFEST C17)"
$py -I -B -m bo.docs_oci.manifest --check

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/DOCS-OCI/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/DOCS-OCI/summary.json", encoding="utf-8"))
if s.get("module") != "DOCS-OCI" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do DOCS-OCI ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify DOCS-OCI
echo "gates/DOCS-OCI.sh: OK"
