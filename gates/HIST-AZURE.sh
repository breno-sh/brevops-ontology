#!/bin/bash
# Gate específico do HIST-AZURE (chamado por make gate ID=HIST-AZURE): testes, contratos C13/C01/C02 das saídas,
# cobertura e monotonia contra a lista do PINS, manifesto C17, regeneração idêntica sem rede e sem binário,
# privacy_lint no conteúdo descomprimido e proveniência.
# Nunca chama make gate (sem recursão); os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/HIST-AZURE}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
OUT="$BO_DATA/HIST-AZURE"
step() { echo "== $*"; }

step "testes (tests/hist_azure, pytest)"
$py -I -B -m pytest tests/hist_azure -q -p no:cacheprovider

step "saídas no validador oficial: versions.json (C13), atoms_<v> (C01) e types_<v> (C02) descomprimidos"
$py -I -m bo.contracts.validate versions "$OUT/versions.json"
$py -I -m bo.hist_azure.validate_outputs --keep

step "conteúdo descomprimido dos átomos e tipos no privacy_lint --strict"
$py -I tools/privacy_lint.py --strict "$BO_TMP/validate"
rm -rf "$BO_TMP/validate"

step "toda versão listada extraída ou com motivo; datas monótonas; pin; binários apagados; manifesto"
$py -I -m bo.hist_azure.check

step "manifesto C17 (MANIFEST.sha256, sem log volátil)"
$py -I -m bo.contracts.validate manifest "$OUT/MANIFEST.sha256"
if grep -Eq '(^|/| )integration/|gate_report\.json|consume_ledger\.json' "$OUT/MANIFEST.sha256"; then
  echo "MANIFEST.sha256 lista log volátil"; exit 1
fi
m="$BO_TMP/MANIFEST.expandido"
sed "s|\\\$BO_DATA|$BO_DATA|g" "$OUT/MANIFEST.sha256" > "$m"
(cd "$OUT" && shasum -a 256 -c "$m" --quiet)
echo "  confere ($(wc -l < "$OUT/MANIFEST.sha256" | tr -d ' ') arquivos)"

step "regeneração idêntica (duas execuções por versão, do schema guardado, sem rede e sem binário)"
$py -I -m bo.hist_azure.regen_check

step "summary.json C17 e proveniência do agente"
$py -I -m bo.contracts.validate summary results/HIST-AZURE/summary.json
$py -I tools/provenance.py verify HIST-AZURE
echo "gates/HIST-AZURE.sh: OK"
