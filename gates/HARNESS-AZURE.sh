#!/bin/bash
# Gate específico do HARNESS-AZURE (chamado por make gate ID=HARNESS-AZURE). Offline: nenhuma credencial, nenhum
# apply; terraform só em fmt/validate num sandbox sem credenciais (D1). Nunca chama make gate (sem recursão).
# Os gates do catálogo (pytest, render + fmt -check, no_silent_insert, ...) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
BO_TMP="${BO_TMP:-$BO_DATA/tmp/HARNESS-AZURE}"
export BO_TMP TMPDIR="$BO_TMP"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
ref=deploy/fixtures/azurerm/_templates/reference
step() { echo "== $*"; }

step "testes (tests/harness/azurerm, pytest)"
$py -I -B -m pytest tests/harness/azurerm -q -p no:cacheprovider

step "regeneração idêntica dos templates (schema fixado do azurerm, versões do PINS)"
$py -I -B -m bo.harness.azurerm.build_templates --check

step "planos de referência no validador único (C26)"
$py -I -m bo.contracts.validate graph_ir $ref/graph_ir.jsonl | tail -1
$py -I -m bo.contracts.validate lowering_plan $ref/lowering_plan.jsonl | tail -1

step "render dos planos de referência + terraform fmt -check -recursive + validate offline no provider fixado"
rm -rf "$BO_TMP/gate_render"
$py -I -B -m bo.harness.azurerm.render $ref/lowering_plan.jsonl --out "$BO_TMP/gate_render"
terraform -chdir="$BO_TMP/gate_render" fmt -check -recursive
$py -I -B -c '
import json, os, sys
from pathlib import Path
from bo.harness.azurerm import tf
from bo.harness.azurerm._common import templates_dir
rep = json.load(open(os.environ["BO_TMP"] + "/gate_render/render_report.json"))
n = 0
for p in rep["plans"]:
    if p["status"] != "RENDERED":
        continue
    pid = p["plan_id"]
    ok, msg = tf.validate_offline(Path(os.environ["BO_TMP"]) / "gate_render" / pid,
                                  templates_dir() / "terraform.lock.hcl")
    print("  validate", pid, "OK" if ok else "REPROVADO")
    if not ok:
        sys.exit(msg)
    n += 1
if n < 2:
    sys.exit("menos de 2 módulos de referência validados")
'

step "sem inserção silenciosa (planos de referência e stub C26, com mutantes)"
$py -I -B -m bo.harness.azurerm.no_silent_insert

step "executor com resposta gravada: saídas no validador único (C16, C12)"
rm -rf "$BO_TMP/gate_exec"
mkdir -p "$BO_TMP/gate_exec"
printf '%s\n' '{"case_id":"CASE-AZREF-DB-0002","group_id":"G-AZREF-0002","claim_id":"CLM-EX-01"}' > "$BO_TMP/gate_exec/cases.jsonl"
$py -I -B -m bo.harness.azurerm.executor --replay tests/harness/azurerm/fixtures/recorded/ok_LP-AZREF-0002.json \
  --plan $ref/lowering_plan.jsonl --plan-id LP-AZREF-0002 --cases "$BO_TMP/gate_exec/cases.jsonl" \
  --out "$BO_TMP/gate_exec/out" --run-id RUN-AZGATE-01
for k in intent_manifest run_manifest readback; do
  $py -I -m bo.contracts.validate $k "$BO_TMP/gate_exec/out/$k.jsonl" | tail -1
done

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/HARNESS-AZURE/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 (validador) e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/HARNESS-AZURE/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/HARNESS-AZURE/summary.json", encoding="utf-8"))
if s.get("module") != "HARNESS-AZURE" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do HARNESS-AZURE ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify HARNESS-AZURE
echo "gates/HARNESS-AZURE.sh: OK"
