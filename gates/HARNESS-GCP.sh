#!/bin/bash
# Gate específico do HARNESS-GCP (chamado por make gate ID=HARNESS-GCP): testes offline, índice do schema fixado,
# contrato C26 das fixtures, render + fmt das fixtures, no_silent_insert, rodada offline com respostas gravadas
# (saída C12 validada), manifesto C17 e proveniência. Nunca chama make gate; nunca toca nuvem.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
BO_DATA="${BO_DATA:-/Users/breno/doutorado/brevops-data}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/HARNESS-GCP}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/harness/google, pytest; respostas gravadas, sem nuvem)"
$py -I -B -m pytest tests/harness/google -q -p no:cacheprovider

step "índice do schema google regenera idêntico a partir do schema fixado (universe/pins.json)"
$py -I -B -m bo.harness.google.schema_index --check

step "fixtures C26 no validador único"
for d in deploy/fixtures/google/_templates/plans/*/; do
  $py -I -m bo.contracts.validate C26 "$d/graph_ir.jsonl" "$d/lowering_plan.jsonl" | tail -2
done

step "render das fixtures + terraform fmt -check"
for d in deploy/fixtures/google/_templates/plans/*/; do
  n=$(basename "$d")
  $py -I -B -m bo.harness.google.render "$d/lowering_plan.jsonl" --out "$BO_TMP/gate_render/$n" | head -2
  terraform -chdir="$BO_TMP/gate_render/$n" fmt -check
  $py -I -B -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r["counts"]["failed"]==0 else 1)' \
      "$BO_TMP/gate_render/$n/render_report.json"
done

step "terraform validate offline das fixtures renderizadas (sandbox sem credenciais, provider do SCHEMA-GCP)"
$py -I -B -m bo.harness.google.tf_validate "$BO_TMP"/gate_render/*/

step "HCL = plano + valores sintetizados declarados"
$py -I -B -m bo.harness.google.no_silent_insert

step "rodada offline (executor completo com respostas gravadas; C12 validado)"
$py -I -B -m bo.harness.google.offline_run

step "manifesto C17 confere"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
probs = receipts.verify_manifest(Path("results/HARNESS-GCP/MANIFEST.sha256"))
for p in probs:
    print("FAIL", p["path"], p["problem"])
sys.exit(1 if probs else 0)
'
echo "hashes conferem"

step "contrato C17 (summary.json) e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/HARNESS-GCP/summary.json | tail -1
$py -I tools/provenance.py verify HARNESS-GCP
echo "gates/HARNESS-GCP.sh: OK"
