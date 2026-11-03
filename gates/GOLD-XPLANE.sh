#!/bin/bash
# Gate específico do GOLD-XPLANE (chamado por make gate ID=GOLD-XPLANE): testes, regeneração idêntica,
# contrato C09 do SSSOM, manifestos (downloads e resultados), resolução de campos e C17 do summary.json.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes unitários (tests/gold_xplane)"
$py -I -B -m unittest discover -s tests/gold_xplane -q

step "regeneração idêntica a partir dos downloads (sem rede)"
$py -I -B -m bo.gold_xplane.build --check

step "contrato C09 (crossplane.sssom.tsv)"
$py -I -m bo.contracts.validate correspondences "$BO_DATA/GOLD-XPLANE/crossplane.sssom.tsv"

step "manifesto dos downloads confere"
(cd "$BO_DATA/downloads/crossplane" && shasum -a 256 -c MANIFEST.sha256 --quiet)

step "manifesto C17 dos resultados confere"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
p = receipts.verify_manifest(Path("results/GOLD-XPLANE/MANIFEST.sha256"))
if p:
    sys.exit("manifesto: " + "; ".join(x["problem"] for x in p))
print("results/GOLD-XPLANE/MANIFEST.sha256: ok")
'

step "todo campo resolve no schema fixado ou é unresolved"
$py -I -B -m bo.gold_xplane.resolve GOLD-XPLANE

step "contrato C17 (summary.json) e proveniência"
$py -I -m bo.contracts.validate manifest_receipt results/GOLD-XPLANE/summary.json
$py -I tools/provenance.py verify GOLD-XPLANE
echo "gates/GOLD-XPLANE.sh: OK"
