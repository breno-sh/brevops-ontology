#!/bin/bash
# Gate específico do SCHEMALIB (chamado por make gate ID=SCHEMALIB): testes, contratos C01/C02 dos stubs pela
# biblioteca, schemas extraídos conferidos por sha256, regeneração idêntica do relatório de reprodução,
# manifesto e proveniência. Nunca chama make gate (sem recursão); os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/SCHEMALIB}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
CAT=/Users/breno/doutorado/pesquisa-lanes/c1-37-icsa/superficie/data/catalogo4v2.jsonl
step() { echo "== $*"; }

step "testes (tests/schema, pytest)"
$py -I -B -m pytest tests/schema -q -p no:cacheprovider

step "stubs C01/C02 conferem no validador oficial"
$py -I -m bo.contracts.validate C01_atoms contracts/stubs/C01/atoms.jsonl
$py -I -m bo.contracts.validate C02_types contracts/stubs/C02/types.jsonl

step "schemas extraídos: sha256 da saída crua do terraform e recibo do extract"
for d in "$BO_DATA"/downloads/tfschema/{aws-5.83.1,azurerm-5.5.0,google-8.2.0,oci-9.1.0}; do
  test -f "$d/receipt.json" || { echo "falta $d/receipt.json"; exit 1; }
  want=$(cut -d' ' -f1 "$d/schema.json.sha256")
  got=$(gzip -dc "$d/schema.json.gz" | shasum -a 256 | cut -d' ' -f1)
  [ "$want" = "$got" ] || { echo "sha256 diverge em $d"; exit 1; }
  echo "  $(basename "$d"): $got"
done

step "regeneração idêntica do relatório de reprodução (menos generated_at)"
$py -I -B -m bo.schema.repro --catalog "$CAT" --check

step "build: dois builds do mesmo schema dão os mesmos bytes"
w="$BO_TMP/gate_build"; rm -rf "$w"; mkdir -p "$w"
for i in 1 2; do
  $py -I -B -m bo.schema.build --schema "$BO_DATA/downloads/tfschema/azurerm-5.5.0/schema.json.gz" --provider azurerm \
     --atoms "$w/a$i.jsonl" --types "$w/t$i.jsonl" >/dev/null
done
cmp "$w/a1.jsonl" "$w/a2.jsonl" && cmp "$w/t1.jsonl" "$w/t2.jsonl" && echo "  idêntico"

step "manifesto C17 (results/SCHEMALIB/MANIFEST.sha256)"
shasum -a 256 -c results/SCHEMALIB/MANIFEST.sha256 --quiet
echo "  confere"

step "summary.json C17 e proveniência do agente"
$py -I tools/provenance.py verify SCHEMALIB
echo "gates/SCHEMALIB.sh: OK"
