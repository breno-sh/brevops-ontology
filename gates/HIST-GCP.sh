#!/bin/bash
# Gate específico do HIST-GCP (chamado por make gate ID=HIST-GCP): testes, contratos C13/C01, completude e datas
# (bo.hist.check, com gpgv reconferido), privacidade do conteúdo descomprimido dos átomos, regeneração idêntica,
# manifestos e proveniência C17. Offline: não baixa nada e não executa binário de provider. Nunca chama make gate.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/HIST-GCP}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/hist_gcp, pytest)"
$py -I -B -m pytest tests/hist_gcp -q -p no:cacheprovider

step "contrato C13 do versions.json no validador único"
$py -I -B -m bo.contracts.validate versions "$BO_DATA/HIST-GCP/versions.json" | tail -1

step "toda versão listada extraída ou com motivo; datas monótonas; pin; assinaturas reconferidas (gpgv)"
$py -I -B -m bo.hist_gcp.check --deep

step "contrato C01 de todos os arquivos de átomos (descomprimidos em \$BO_TMP)"
lint="$BO_TMP/gate-lint"
$py -I -B -m bo.hist_gcp.c01 --keep "$lint"

step "privacy_lint --strict sobre o conteúdo descomprimido dos átomos (o .gz sozinho não é varrível)"
$py -I tools/privacy_lint.py --strict "$lint" | tail -1
rm -rf "$lint"

step "regeneração offline: átomos 2x da saída crua; versions.json, extraction.json e contagens"
$py -I -B -m bo.hist_gcp.regen_check

step "manifesto da pasta do módulo (\$BO_DATA/HIST-GCP/MANIFEST.sha256, sem livros nem logs)"
(cd "$BO_DATA/HIST-GCP" && shasum -a 256 -c MANIFEST.sha256 --quiet)
want="$($py -I -B -c 'from bo.hist_gcp import common as C; import sys; sys.stdout.write(C.manifest_text(C.out_dir()))')"
[ "$want" == "$(cat "$BO_DATA/HIST-GCP/MANIFEST.sha256")" ] || { echo "MANIFEST.sha256 não cobre exatamente as saídas"; exit 1; }
echo "  confere"

step "manifesto dos resultados (results/HIST-GCP/MANIFEST.sha256)"
shasum -a 256 -c results/HIST-GCP/MANIFEST.sha256 --quiet
echo "  confere"

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/HIST-GCP/summary.json | tail -1
$py -I tools/provenance.py verify HIST-GCP
echo "gates/HIST-GCP.sh: OK"
