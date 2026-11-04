#!/bin/bash
# Gate específico do CORPUS-GCP (chamado por make gate ID=CORPUS-GCP): testes, saídas declaradas, invariantes do
# usage contra o parquet e o schema, recontagem independente numa amostra, regeneração idêntica, manifestos,
# summary.json C17 e proveniência. Nunca chama make gate (sem recursão). O validador C06 do usage.jsonl inteiro
# roda como gate do catálogo, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/CORPUS-GCP}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
D="$BO_DATA/CORPUS-GCP"
step() { echo "== [$(TZ=America/Recife date '+%Y-%m-%dT%H:%M:%S')] $*"; }

step "testes (tests/corpus_gcp, pytest)"
$py -I -B -m pytest tests/corpus_gcp -q -p no:cacheprovider

step "saídas declaradas existem e não estão vazias; nada sobrou na .staging"
for f in usage.jsonl atom_totals.jsonl type_totals.jsonl coverage.json build_report.json MANIFEST.sha256; do
  test -s "$D/$f" || { echo "falta $D/$f"; exit 1; }
done
test ! -e "$D/.staging" || { echo "sobrou $D/.staging (troca não concluída)"; exit 1; }
test -s results/CORPUS-GCP/summary.json || { echo "falta results/CORPUS-GCP/summary.json"; exit 1; }
echo "saídas presentes"

step "invariantes contra resources.parquet e atoms.jsonl, totais, recontagem independente (1 em 20 repositórios)"
$py -I -B -m bo.corpus_gcp.check --sample-mod 20

step "regeneração inteira em \$BO_TMP/regen: mesmos sha256 das saídas determinísticas"
$py -I -B -m bo.corpus_gcp.regen_check

step "manifesto da pasta do módulo (\$BO_DATA/CORPUS-GCP/MANIFEST.sha256)"
(cd "$D" && shasum -a 256 -c MANIFEST.sha256 --quiet)
echo "  confere"

step "manifesto dos resultados (results/CORPUS-GCP/MANIFEST.sha256, caminhos portáteis)"
$py -I -B -c '
import os, sys
from bo.corpus_gcp.common import sha256_file
env = {"$BO_DATA": os.environ["BO_DATA"], "$BO_REPO": os.environ["BO_REPO"]}
bad = n = 0
for ln in open("results/CORPUS-GCP/MANIFEST.sha256", encoding="utf-8"):
    if not ln.strip():
        continue
    sha, path = ln.rstrip("\n").split("  ", 1)
    for k, v in env.items():
        if path.startswith(k):
            path = v + path[len(k):]
    n += 1
    if sha256_file(path) != sha:
        bad += 1
        print("DIVERGE", ln.split("  ", 1)[1].strip())
print(f"  manifesto: {n} arquivo(s), {bad} divergência(s)")
sys.exit(1 if bad or not n else 0)
'

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate C17_summary results/CORPUS-GCP/summary.json | tail -1
$py -I tools/provenance.py verify CORPUS-GCP
echo "gates/CORPUS-GCP.sh: OK"
