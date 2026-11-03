#!/bin/bash
# Gate específico do GOLD-CARTO (chamado por make gate ID=GOLD-CARTO): download fixado, testes, regeneração
# idêntica, contrato C09, resolução de campos, manifesto C17, summary.json C17 e proveniência.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
BO_DATA="${BO_DATA:-/Users/breno/doutorado/brevops-data}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "download fixado (tarball do commit, sha256 do SOURCE.txt)"
$py -I -B -c '
import hashlib, sys
from bo.gold_carto import TARBALL, TARBALL_SHA256
from bo.gold_carto.build import download_dir
d = download_dir()
src = (d / "SOURCE.txt").read_text(encoding="utf-8")
got = hashlib.sha256((d / TARBALL).read_bytes()).hexdigest()
if got != TARBALL_SHA256 or ("sha256: " + TARBALL_SHA256) not in src:
    sys.exit("tarball ou SOURCE.txt não conferem com o sha256 fixado")
print("tarball", TARBALL, "confere")
'

step "testes unitários (tests/gold_carto)"
$py -I -B -m unittest discover -s tests/gold_carto -q

step "regeneração idêntica"
$py -I -B -m bo.gold_carto.build --check

step "contrato C09 (cartography.sssom.tsv)"
$py -I -m bo.contracts.validate correspondences "$BO_DATA/GOLD-CARTO/cartography.sssom.tsv"

step "resolução de campos (todo campo resolve ou está marcado UNRESOLVED)"
$py -I -B -m bo.gold_carto.resolve GOLD-CARTO

step "manifesto C17 confere"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
probs = receipts.verify_manifest(Path("results/GOLD-CARTO/MANIFEST.sha256"))
for p in probs:
    print("FAIL", p["path"], p["problem"])
sys.exit(1 if probs else 0)
'

step "contrato C17 (summary.json)"
$py -I -m bo.contracts.validate manifest_receipt results/GOLD-CARTO/summary.json

step "proveniência do agente confere (brief e entradas)"
$py -I tools/provenance.py verify GOLD-CARTO
echo "gates/GOLD-CARTO.sh: OK"
