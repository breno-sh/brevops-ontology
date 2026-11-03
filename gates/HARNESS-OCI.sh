#!/bin/bash
# Gate específico do HARNESS-OCI (chamado por make gate ID=HARNESS-OCI): testes, regenerações idênticas,
# contratos (exemplos C26 no validador único), HCL de exemplo no fmt e no validate offline, hashes (C17) e
# proveniência. Nunca chama make gate (sem recursão) e nunca toca nuvem: terraform só em fmt/init -backend=false/
# validate, no sandbox sem credenciais (bo.harness.oci.sandbox).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/harness/oci, pytest)"
$py -I -B -m pytest tests/harness/oci -q -p no:cacheprovider

step "regeneração idêntica: tabela do schema oci 9.11.0, gravações sintéticas, HCL de exemplo"
$py -I -B -m bo.harness.oci.build_table --check
$py -I -B tests/harness/oci/make_recordings.py --check
$py -I -B -m bo.harness.oci.example --check

step "contratos C26 dos exemplos no validador único"
$py -I -m bo.contracts.validate lowering_plan deploy/fixtures/oci/_templates/examples/lowering_plan.jsonl | tail -1
$py -I -m bo.contracts.validate graph_ir deploy/fixtures/oci/_templates/examples/graph_ir.jsonl | tail -1

step "HCL de exemplo: fmt -check e validate offline (sandbox sem credenciais)"
$py -I -B -c '
import json, shutil, sys
from bo.harness.oci import sandbox as SB, templates_dir, tmp_root
src = templates_dir() / "rendered_example"
dst = tmp_root() / "gate_validate"
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)
f = SB.fmt_check(dst)
if f.rc:
    sys.exit("fmt -check reprovou: " + f.out[:400])
i, v = SB.init_validate(dst)
if i.rc or v is None or not json.loads(v.out)["valid"]:
    sys.exit("validate reprovou")
print("fmt -check e validate: OK")
'

step "no_silent_insert (o gate do catálogo roda de novo depois, pelo runner)"
$py -I -B -m bo.harness.oci.no_silent_insert

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/HARNESS-OCI/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 (validador) e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/HARNESS-OCI/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/HARNESS-OCI/summary.json", encoding="utf-8"))
if s.get("module") != "HARNESS-OCI" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do HARNESS-OCI ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify HARNESS-OCI
echo "gates/HARNESS-OCI.sh: OK"
