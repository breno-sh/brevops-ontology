#!/bin/bash
# Gate específico do GOLD-MODS (chamado por make gate ID=GOLD-MODS): testes, regeneração idêntica a partir do
# C06, contrato C09 do SSSOM, manifesto C17 dos resultados, resolução no HCL simbólico e C17 do summary.json.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes unitários (tests/gold_mods)"
$py -I -B -m unittest discover -s tests/gold_mods -q

step "regeneração idêntica a partir de \$BO_DATA/HCL (sem rede)"
$py -I -B -m bo.gold_mods.build --check

step "contrato C09 (mods.sssom.tsv)"
$py -I -m bo.contracts.validate correspondences "$BO_DATA/GOLD-MODS/mods.sssom.tsv"

step "manifesto C17 dos resultados confere"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
p = receipts.verify_manifest(Path("results/GOLD-MODS/MANIFEST.sha256"))
if p:
    sys.exit("manifesto: " + "; ".join(x["problem"] for x in p))
print("results/GOLD-MODS/MANIFEST.sha256: ok")
'

step "toda linha nasce de variável seguida até atributo no C06; estado de evidência pela regra"
$py -I -B -m bo.gold_mods.resolve GOLD-MODS

step "contrato C17 (summary.json) e proveniência"
$py -I -m bo.contracts.validate manifest_receipt results/GOLD-MODS/summary.json
$py -I tools/provenance.py verify GOLD-MODS
echo "gates/GOLD-MODS.sh: OK"
