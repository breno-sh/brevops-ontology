#!/bin/bash
# Gate específico do SCHEMA-OCI (chamado por make gate ID=SCHEMA-OCI): testes, contratos C01/C02 das saídas,
# schema extraído == pins.json, regeneração idêntica, terraform validate offline com o plugin_cache/,
# manifestos (binário assinado incluído) e proveniência C17. Offline: não baixa nada, não toca nuvem.
# Nunca chama make gate (sem recursão); os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/SCHEMA-OCI}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
OUT="$BO_DATA/SCHEMA-OCI"
step() { echo "== $*"; }

step "testes (tests/schema_oci, pytest; nenhum SKIP aceito)"
log="$BO_TMP/pytest.log"
$py -I -B -m pytest tests/schema_oci -q -p no:cacheprovider -rs | tee "$log" | tail -3
if grep -q "skipped" "$log"; then echo "teste pulado: reprovado (nada passa por vacuidade)"; exit 1; fi

step "contratos C01 (atoms) e C02 (types) no validador oficial"
$py -I -B -m bo.contracts.validate atoms "$OUT/atoms.jsonl" | tail -1
$py -I -B -m bo.contracts.validate types "$OUT/types.jsonl" | tail -1

step "schema extraído == schema.json.sha256 == pins.json"
$py -I -B -c '
import gzip, hashlib, sys
from bo.schema_oci import common
pin = common.read_pin()
d = common.tfschema_dir(pin.version)
raw = hashlib.sha256(gzip.open(d / "schema.json.gz").read()).hexdigest()
pub = (common.out_dir() / "schema.json.sha256").read_text().split()[0]
if not (raw == pub == pin.schema_sha256):
    sys.exit(f"sha256 diverge: gz {raw} publicado {pub} pins {pin.schema_sha256}")
print(f"  oci {pin.version}: {raw}")
'

step "regeneração idêntica (duas execuções == publicado)"
$py -I -B -m bo.schema_oci.regen_check SCHEMA-OCI | tail -1

step "terraform validate offline com o plugin_cache/ (sem rede, sem credenciais)"
$py -I -B -m bo.schema_oci.offline | tail -1

step "manifestos ($OUT/MANIFEST.sha256 com o binário, results/SCHEMA-OCI/MANIFEST.sha256)"
$py -I -B -m bo.schema_oci.manifest

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/SCHEMA-OCI/summary.json | tail -1
$py -I tools/provenance.py verify SCHEMA-OCI
echo "gates/SCHEMA-OCI.sh: OK"
