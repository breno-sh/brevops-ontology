#!/bin/bash
# Gate específico do CORPUS-OCI (chamado por make gate ID=CORPUS-OCI): testes, contrato C06 do usage,
# conferência independente contra o parquet do HCL e o atoms.jsonl do SCHEMA-OCI, regeneração idêntica,
# manifesto, privacidade e summary.json C17 com proveniência. Não toca nuvem, não baixa nada.
# Nunca chama make gate (sem recursão); os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/CORPUS-OCI}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
D="$BO_DATA/CORPUS-OCI"
step() { echo "== [$(TZ=America/Recife date '+%Y-%m-%dT%H:%M:%S')] $*"; }

step "testes (tests/corpus_oci, pytest; nenhum SKIP aceito)"
log="$BO_TMP/pytest.log"
$py -I -B -m pytest tests/corpus_oci -q -p no:cacheprovider -rs | tee "$log" | tail -3
if grep -q "skipped" "$log"; then echo "teste pulado: reprovado (nada passa por vacuidade)"; exit 1; fi

step "saídas publicadas existem e não estão vazias (staging já trocado)"
for f in usage.jsonl atom_totals.jsonl type_totals.jsonl build_report.json; do
  test -s "$D/$f" || { echo "falta $D/$f"; exit 1; }
done
test ! -e "$D/.staging" || { echo "staging não trocado em $D/.staging"; exit 1; }
test -s results/CORPUS-OCI/summary.json || { echo "falta results/CORPUS-OCI/summary.json"; exit 1; }

step "contrato C06 usage (validador oficial, arquivo inteiro)"
$py -I -B -m bo.contracts.validate usage "$D/usage.jsonl" | tail -1

step "conferência independente contra resources.parquet, atoms.jsonl e sha das entradas"
$py -I -B -m bo.corpus_oci.check

step "regeneração idêntica (reconstrói em \$BO_TMP e compara byte a byte)"
$py -I -B -m bo.corpus_oci.regen_check

step "manifesto results/CORPUS-OCI/MANIFEST.sha256"
$py -I -B -m bo.corpus_oci.manifest verify

step "privacidade (--strict) dos resultados e dos dados"
$py -I tools/privacy_lint.py --strict results/CORPUS-OCI "$D" | tail -1

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate C17_summary results/CORPUS-OCI/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/CORPUS-OCI/summary.json", encoding="utf-8"))
ap = s["agent_provenance"]
if s.get("module") != "CORPUS-OCI" or ap.get("model_id") != "claude-opus-5-5" or not s.get("notes"):
    sys.exit("summary.json sem módulo, modelo ou notas")
print("summary.json: módulo, modelo e notas presentes")
'
$py -I tools/provenance.py verify CORPUS-OCI | tail -1
echo "gates/CORPUS-OCI.sh: OK"
