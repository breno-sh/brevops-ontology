#!/bin/bash
# Gate específico do CORPUS-AWS (chamado por make gate ID=CORPUS-AWS): testes, saídas declaradas, invariantes
# contra as entradas com uma segunda implementação numa amostra, sha256 das entradas consumidas == manifestos das
# deps, regeneração idêntica (refaz a contagem inteira, varre o symbolic_config.jsonl de 4,9 GB), manifestos e
# summary.json C17. Nunca chama make gate (sem recursão); os gates do catálogo (validador oficial do C06 usage,
# privacy_lint, consume_check...) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/CORPUS-AWS}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
D="$BO_DATA/CORPUS-AWS"
R="results/CORPUS-AWS"
step() { echo "== [$(TZ=America/Recife date '+%Y-%m-%dT%H:%M:%S')] $*"; }

step "testes (tests/corpus_aws, pytest)"
$py -I -B -m pytest tests/corpus_aws -q -p no:cacheprovider

step "saídas declaradas existem e não estão vazias"
for f in "$D/usage.jsonl" "$D/atom_totals.jsonl" "$D/build_report.json" "$D/counts.json" "$D/MANIFEST.sha256" \
         "$R/summary.json" "$R/counts.json" "$R/MANIFEST.sha256"; do
  test -s "$f" || { echo "falta $f"; exit 1; }
done
echo "  saídas presentes"

step "invariantes contra as entradas, 2ª implementação na amostra e sha das entradas == manifestos das deps"
$py -I -B -m bo.corpus_aws.check "$D" --deps

step "regeneração idêntica (contagem inteira refeita em \$BO_TMP/regen)"
$py -I -B -m bo.corpus_aws.regen_check

step "manifestos (\$BO_DATA/CORPUS-AWS/MANIFEST.sha256 e results/CORPUS-AWS/MANIFEST.sha256)"
$py -I -B -c '
import sys
from bo.repo.receipts import verify_manifest
from bo.corpus_aws import common as K
bad = 0
for mf in (K.out_dir() / "MANIFEST.sha256", K.results_dir() / "MANIFEST.sha256"):
    p = verify_manifest(mf, K.bo_repo())
    n = sum(1 for l in mf.read_text().splitlines() if l.strip())
    for x in p:
        print("  ", x)
    print(f"  {K.portable(mf)}: {n} arquivo(s), {len(p)} problema(s)")
    bad += len(p) + (n == 0)
sys.exit(1 if bad else 0)'
cmp -s "$D/counts.json" "$R/counts.json" || { echo "results/CORPUS-AWS/counts.json != \$BO_DATA/CORPUS-AWS/counts.json"; exit 1; }

step "summary.json C17 e proveniência do agente"
$py -I -m bo.contracts.validate C17_summary "$R/summary.json"
$py -I tools/provenance.py verify CORPUS-AWS
echo "gates/CORPUS-AWS.sh: OK"
