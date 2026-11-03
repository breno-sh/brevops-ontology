#!/bin/bash
# Gate específico do SCHEMA-AWS (chamado por make gate ID=SCHEMA-AWS): testes, contratos C01/C02 das saídas,
# schema extraído == pins.json, manifesto das saídas (inclui o binário assinado), validate offline pelo
# plugin_cache/, manifesto do repositório e proveniência. Nunca chama make gate (sem recursão); os gates do
# catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/SCHEMA-AWS}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
OUT="$BO_DATA/SCHEMA-AWS"
step() { echo "== $*"; }

step "testes (tests/schema_aws, pytest)"
$py -I -B -m pytest tests/schema_aws -q -p no:cacheprovider

step "contratos C01 (atoms) e C02 (types) no validador oficial"
$py -I -m bo.contracts.validate C01_atoms "$OUT/atoms.jsonl"
$py -I -m bo.contracts.validate C02_types "$OUT/types.jsonl"

step "schema extraído: gzip -> sha256 == schema.json.sha256 == universe/pins.json"
want=$(cut -d' ' -f1 "$OUT/schema.json.sha256")
pin=$($py -I -B -c 'from bo.schema_aws import common; print(common.read_pin().schema_sha256)')
ver=$($py -I -B -c 'from bo.schema_aws import common; print(common.read_pin().version)')
got=$(gzip -dc "$BO_DATA/downloads/tfschema/aws-$ver/schema.json.gz" | shasum -a 256 | cut -d' ' -f1)
[ "$want" = "$got" ] && [ "$got" = "$pin" ] || { echo "sha256 diverge: arquivo $want, gz $got, pins $pin"; exit 1; }
echo "  aws $ver: $got"

step "manifesto das saídas (\$BO_DATA/SCHEMA-AWS/MANIFEST.sha256, com o binário assinado)"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo.receipts import verify_manifest
from bo.schema_aws import common
p = verify_manifest(common.out_dir() / "MANIFEST.sha256", common.bo_repo())
for x in p:
    print("  ", x)
n = sum(1 for l in (common.out_dir() / "MANIFEST.sha256").read_text().splitlines() if l.strip())
print(f"  {n} arquivo(s), {len(p)} problema(s)")
sys.exit(1 if p else 0)'

step "terraform validate offline pelo plugin_cache/ (válida passa, inválida reprova, binário do pino)"
$py -I -B -m bo.schema_aws.offline

step "manifesto C17 do repositório (results/SCHEMA-AWS/MANIFEST.sha256)"
shasum -a 256 -c results/SCHEMA-AWS/MANIFEST.sha256 --quiet
echo "  confere"

step "summary.json C17 e proveniência do agente"
$py -I tools/provenance.py verify SCHEMA-AWS
echo "gates/SCHEMA-AWS.sh: OK"
