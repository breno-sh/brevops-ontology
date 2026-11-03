#!/bin/bash
# Gate específico do HARNESS-AWS (chamado por make gate ID=HARNESS-AWS). Tudo offline: nada de credencial,
# plan ou apply; o Terraform só roda em fmt e validate, num sandbox sem credenciais (decisão D1).
# Nunca chama make gate (sem recursão). Os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
BO_TMP="${BO_TMP:-$BO_DATA/tmp/HARNESS-AWS}"
export BO_TMP TMPDIR="$BO_TMP"
mkdir -p "$BO_TMP" "$BO_DATA/HARNESS-AWS"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/harness/aws, pytest)"
$py -I -B -m pytest tests/harness/aws -q -p no:cacheprovider

step "planos de fixture no contrato C26 (validador único)"
$py -I -m bo.contracts.validate lowering_plan tests/harness/aws/fixtures/plans/lowering_plan.jsonl | tail -1
$py -I -m bo.contracts.validate graph_ir tests/harness/aws/fixtures/plans/graph_ir.jsonl | tail -1

step "render dos planos de fixture + terraform fmt -check"
$py -I -m bo.harness.aws.render tests/harness/aws/fixtures/plans/lowering_plan.jsonl --out "$BO_TMP/gate_render"
terraform -chdir="$BO_TMP/gate_render" fmt -check
echo "fmt: canônico"

step "terraform validate offline (sandbox sem credenciais) concorda com cada estado do renderizador"
$py -I -m bo.harness.aws.tf_validate "$BO_TMP/gate_render" --json "$BO_DATA/HARNESS-AWS/tf_validate.json"

step "sem inserção silenciosa (HCL = plano + inserções declaradas; mutações pegas)"
$py -I -m bo.harness.aws.no_silent_insert --report "$BO_DATA/HARNESS-AWS/no_silent_insert.json"

step "executor com respostas gravadas: C12 e C16 válidos, redator antes de gravar"
$py -I -m bo.harness.aws.executor --offline-demo --out "$BO_DATA/HARNESS-AWS/offline_run"
for k in readback outcomes intent_manifest run_manifest; do
  $py -I -m bo.contracts.validate "$k" "$BO_DATA/HARNESS-AWS/offline_run/$k.jsonl" | tail -1
done

step "privacidade das saídas"
$py -I tools/privacy_lint.py --strict results/HARNESS-AWS "$BO_DATA/HARNESS-AWS" | tail -1

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/HARNESS-AWS/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 (validador) e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/HARNESS-AWS/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/HARNESS-AWS/summary.json", encoding="utf-8"))
if s.get("module") != "HARNESS-AWS" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do HARNESS-AWS ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify HARNESS-AWS
rm -rf "$BO_TMP/gate_render" "$BO_TMP/sk"
echo "gates/HARNESS-AWS.sh: OK"
