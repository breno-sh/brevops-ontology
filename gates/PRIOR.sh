#!/bin/bash
# Gate específico do PRIOR (chamado por make gate ID=PRIOR): testes, downloads íntegros, regeneração idêntica,
# contratos C09/C14/C15/C17, manifestos, G1 (bo.prior.check) e proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/prior, pytest)"
$py -I -B -m pytest tests/prior -q -p no:cacheprovider

step "downloads fixados conferem com o fetch_manifest.json (offline)"
$py -I -B -m bo.prior.fetch --check

step "regeneração idêntica ($BO_DATA/PRIOR/*, results/PRIOR/{inventory,metrics}.json, manifestos)"
$py -I -B -m bo.prior.build --check

step "contratos: C09 em todo provider_links, C14 nas projeções, C15/C17 no summary.json"
for f in "$BO_DATA"/PRIOR/*/provider_links.sssom.tsv; do
  $py -I -m bo.contracts.validate correspondences "$f" >/dev/null || { echo "C09 reprovado: $f"; exit 1; }
done
for f in "$BO_DATA"/PRIOR/*/classes.jsonl; do
  $py -I -m bo.contracts.validate C14_classes "$f" >/dev/null || { echo "C14 reprovado: $f"; exit 1; }
done
for f in "$BO_DATA"/PRIOR/*/properties.jsonl; do
  $py -I -m bo.contracts.validate C14_properties "$f" >/dev/null || { echo "C14 reprovado: $f"; exit 1; }
done
$py -I -m bo.contracts.validate summary_results results/PRIOR/summary.json
$py -I -m bo.contracts.validate manifest_receipt results/PRIOR/summary.json
$py -I -B -m bo.prior.summary --check
echo "contratos conferem"

step "manifestos C17 ($BO_DATA/PRIOR/MANIFEST.sha256 e results/PRIOR/MANIFEST.sha256)"
shasum -a 256 -c results/PRIOR/MANIFEST.sha256 --quiet
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import core, receipts
mf = core.bo_data() / "PRIOR" / "MANIFEST.sha256"
probs = receipts.verify_manifest(mf, core.bo_repo())
for p in probs:
    print("FAIL", p["path"], p["problem"])
n = sum(1 for l in mf.read_text(encoding="utf-8").splitlines() if l.strip())
print(f"{mf}: {n} arquivo(s)", "conferem" if not probs else "REPROVADO")
sys.exit(1 if probs else 0)
'

step "G1: todo modelo com SOURCE, licença e sha, ou 'só documental' com a referência"
$py -I -B -m bo.prior.check

step "proveniência do agente confere (brief e entradas)"
$py -I tools/provenance.py verify PRIOR
echo "gates/PRIOR.sh: OK"
