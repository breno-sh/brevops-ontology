#!/bin/bash
# Gate específico do CORPUS-AZURE (chamado por make gate ID=CORPUS-AZURE): testes, saídas declaradas, validação
# C06 registrada para ESTE usage.jsonl, conferência contra o resources.parquet e o atoms.jsonl, totais, manifesto,
# regeneração idêntica de uma amostra, summary.json C17 e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo (validate usage inteiro, privacy_lint, consume_check,
# ownership, commit_lint, integration) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/CORPUS-AZURE}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
D="$BO_DATA/CORPUS-AZURE"
step() { echo "== [$(TZ=America/Recife date '+%Y-%m-%dT%H:%M:%S')] $*"; }

step "testes (tests/corpus_azure, pytest)"
$py -I -B -m pytest tests/corpus_azure -q -p no:cacheprovider

step "saídas declaradas existem e não estão vazias; staging não ficou para trás"
for f in usage.jsonl atom_totals.jsonl type_totals.jsonl build_report.json contract_report.json; do
  test -s "$D/$f" || { echo "falta $D/$f"; exit 1; }
done
test -s results/CORPUS-AZURE/summary.json || { echo "falta results/CORPUS-AZURE/summary.json"; exit 1; }
test ! -e "$D/.staging" || { echo "staging pendente em $D/.staging (troca não feita)"; exit 1; }
echo "saídas presentes"

step "contrato C06: validação do usage.jsonl inteiro registrada para ESTE arquivo (sha256)"
$py -I -B -c '
import json, sys
from bo.corpus_azure.swap import sha256_file
d = sys.argv[1]
r = json.load(open(d + "/contract_report.json"))
sha = sha256_file(d + "/usage.jsonl")
print(f"contract_report: {r["result"]}, sha confere: {r["sha256"] == sha}")
sys.exit(0 if r["result"] == "PASS" and r["sha256"] == sha else 1)
' "$D"

step "conferência: parquet, atoms, totais, resumo, manifesto, regeneração da amostra (1 em 50)"
$py -I -m bo.corpus_azure.check --sample-mod 50

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/CORPUS-AZURE/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources", "counts") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "CORPUS-AZURE" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
print("summary.json C17: campos obrigatórios presentes")
'
$py -I -m bo.contracts.validate C17_summary results/CORPUS-AZURE/summary.json
$py -I tools/provenance.py verify CORPUS-AZURE
echo "gates/CORPUS-AZURE.sh: OK"
