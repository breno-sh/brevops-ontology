#!/bin/bash
# Gate específico do HIST-OCI (chamado por make gate ID=HIST-OCI): testes, contratos C13 (versions.json) e C01
# (dentro de cada atoms_<versão>.jsonl.gz), cobertura da lista histórica com motivo para cada falta, datas
# monótonas, regeneração idêntica dos átomos, privacidade do conteúdo descomprimido, manifestos e proveniência
# C17. Offline: não baixa nada, não executa binário (já apagado), não toca nuvem.
# Nunca chama make gate (sem recursão); os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/HIST-OCI}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
OUT="$BO_DATA/HIST-OCI"
step() { echo "== $*"; }

step "testes (tests/hist_oci, pytest; nenhum SKIP aceito)"
log="$BO_TMP/pytest.log"
$py -I -B -m pytest tests/hist_oci -q -p no:cacheprovider -rs | tee "$log" | tail -3
if grep -q "skipped" "$log"; then echo "teste pulado: reprovado (nada passa por vacuidade)"; exit 1; fi

step "contrato C13 de versions.json no validador oficial"
$py -I -B -m bo.contracts.validate versions "$OUT/versions.json" | tail -1

step "toda versão listada extraída ou com motivo; datas monótonas; pin == lista histórica; binários apagados"
$py -I -B -m bo.hist_oci.check HIST-OCI | tail -1

step "C01 e privacidade dentro de cada atoms_<versão>.jsonl.gz"
$py -I -B -m bo.hist_oci.atoms_check | tail -1

step "regeneração idêntica dos átomos (duas execuções == publicado, por versão)"
$py -I -B -m bo.hist_oci.regen_check | tail -1

step "manifestos ($OUT/MANIFEST.sha256 sem log volátil, results/HIST-OCI/MANIFEST.sha256)"
$py -I -B -m bo.hist_oci.manifest

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/HIST-OCI/summary.json | tail -1
$py -I tools/provenance.py verify HIST-OCI
echo "gates/HIST-OCI.sh: OK"
