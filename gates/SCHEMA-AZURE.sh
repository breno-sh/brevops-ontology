#!/bin/bash
# Gate específico do SCHEMA-AZURE (chamado por make gate ID=SCHEMA-AZURE): testes, contratos C01/C02 das saídas,
# schema conferido contra o pins.json, manifesto C17 (inclui o binário assinado), regeneração idêntica com schema
# refeito sem rede e validate offline, cruzamento com o índice do Registry e proveniência.
# Nunca chama make gate (sem recursão); os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/SCHEMA-AZURE}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
OUT="$BO_DATA/SCHEMA-AZURE"
step() { echo "== $*"; }

step "testes (tests/schema_azure, pytest)"
$py -I -B -m pytest tests/schema_azure -q -p no:cacheprovider

step "saídas C01 (átomos) e C02 (tipos) no validador oficial"
$py -I -m bo.contracts.validate C01_atoms "$OUT/atoms.jsonl"
$py -I -m bo.contracts.validate C02_types "$OUT/types.jsonl"

step "schema: sha256 publicado = saída crua do terraform = pins.json"
want=$($py -I -c 'import json,sys; print(next(p["schema_sha256"] for p in json.load(open(sys.argv[1]))["providers"] if p["provider"]=="azurerm"))' universe/pins.json)
ver=$($py -I -c 'import json,sys; print(next(p["version"] for p in json.load(open(sys.argv[1]))["providers"] if p["provider"]=="azurerm"))' universe/pins.json)
pub=$(cut -d' ' -f1 "$OUT/schema.json.sha256")
got=$(gzip -dc "$BO_DATA/downloads/tfschema/azurerm-$ver/schema.json.gz" | shasum -a 256 | cut -d' ' -f1)
[ "$want" = "$pub" ] && [ "$pub" = "$got" ] || { echo "sha256 do schema diverge (pins $want, publicado $pub, gz $got)"; exit 1; }
echo "  azurerm $ver: $got"

step "manifesto C17 (MANIFEST.sha256, com o binário assinado do plugin_cache)"
m="$BO_TMP/MANIFEST.expandido"
sed "s|\\\$BO_DATA|$BO_DATA|g" "$OUT/MANIFEST.sha256" > "$m"
(cd "$OUT" && shasum -a 256 -c "$m" --quiet)
echo "  confere ($(wc -l < "$OUT/MANIFEST.sha256" | tr -d ' ') arquivos)"

step "regeneração idêntica (duas execuções) + schema refeito sem rede + validate offline"
$py -I -m bo.schema_azure.regen_check

step "tipos = índice do Registry da versão"
$py -I -m bo.schema.crosscheck --provider azurerm

step "summary.json C17 e proveniência do agente"
$py -I tools/provenance.py verify SCHEMA-AZURE
echo "gates/SCHEMA-AZURE.sh: OK"
