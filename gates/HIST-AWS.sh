#!/bin/bash
# Gate específico do HIST-AWS (chamado por make gate ID=HIST-AWS): testes, contrato C13 do versions.json,
# cobertura da lista do PINS (bo.hist.check --deep), regeneração idêntica dos átomos a partir dos schemas
# guardados (com C01 validado em cada versão), binários apagados, manifestos e proveniência.
# Offline: não baixa nada e não executa binário. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/HIST-AWS}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
OUT="$BO_DATA/HIST-AWS"
step() { echo "== $*"; }

step "testes (tests/hist_aws, pytest)"
$py -I -B -m pytest tests/hist_aws -q -p no:cacheprovider

step "contrato C13 (versions) no validador oficial"
$py -I -B -m bo.contracts.validate versions "$OUT/versions.json" | tail -1

step "toda versão listada extraída ou com motivo, datas monótonas, átomos contados (--deep)"
$py -I -B -m bo.hist.check HIST-AWS --deep | tail -1

step "regeneração idêntica: átomos (C01 validado) refeitos dos schemas guardados; versions.json e report.json"
$py -I -B -m bo.hist_aws.regen_check

step "binários apagados: nenhum zip nem pasta desempacotada do provider ficou"
n=$(find "$BO_DATA/downloads/hist-aws" "$OUT" "$BO_TMP" \( -name '*.zip' -o -name 'terraform-provider-aws_v*' \) | wc -l | tr -d ' ')
[ "$n" = "0" ] || { echo "  $n binário(s) do provider ainda no disco"; exit 1; }
echo "  0 binário(s)"

step "manifesto das saídas (\$BO_DATA/HIST-AWS/MANIFEST.sha256 com os schemas em downloads/hist-aws, sem logs voláteis)"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo.receipts import verify_manifest
from bo.hist_aws import common, pipeline
mf = common.out_dir() / "MANIFEST.sha256"
p = verify_manifest(mf, common.bo_repo())
listed = {l.split(None, 1)[1] for l in mf.read_text().splitlines() if l.strip()}
want = {lab for _, lab in pipeline.manifest_entries(common.out_dir(), pipeline.load_extraction())}
for x in p:
    print("  ", x)
if listed != want:
    print("   manifesto não cobre exatamente as saídas: faltam", sorted(want - listed)[:5], "sobram", sorted(listed - want)[:5])
if any(x.startswith("integration/") for x in listed):
    print("   manifesto com log volátil integration/")
    p.append(1)
print(f"  {len(listed)} arquivo(s), {len(p)} problema(s)")
sys.exit(1 if p or listed != want else 0)'

step "manifesto C17 do repositório (results/HIST-AWS/MANIFEST.sha256)"
shasum -a 256 -c results/HIST-AWS/MANIFEST.sha256 --quiet
echo "  confere"

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/HIST-AWS/summary.json | tail -1
$py -I tools/provenance.py verify HIST-AWS
echo "gates/HIST-AWS.sh: OK"
