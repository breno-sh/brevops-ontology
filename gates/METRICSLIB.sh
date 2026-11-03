#!/bin/bash
# Gate específico do METRICSLIB (chamado por make gate ID=METRICSLIB): testes, ligação spec x biblioteca,
# regeneração idêntica, contrato C15 da saída, hashes da biblioteca (metrics_lib.sha256, C17) e proveniência.
# Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/metrics, pytest)"
$py -I -B -m pytest tests/metrics -q -p no:cacheprovider

step "regeneração idêntica (results/METRICSLIB/* e prereg/metrics_lib.sha256 saem só de src/bo/metrics)"
$py -I -B -m bo.metrics.build --check

step "contrato C15 da leitura sobre os stubs"
$py -I -m bo.contracts.validate results results/METRICSLIB/stub_readings.json | tail -1

step "hashes da biblioteca e do manifesto (C17)"
shasum -a 256 -c prereg/metrics_lib.sha256 --quiet
shasum -a 256 -c results/METRICSLIB/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "comandos de consumo (bounds_present, denominator_invariance, recompute) no próprio módulo"
$py -I -B -m bo.metrics.bounds_present METRICSLIB | tail -1
$py -I -B -m bo.metrics.denominator_invariance METRICSLIB --stubs | tail -1
$py -I -B -m bo.metrics.recompute METRICSLIB | tail -1

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/METRICSLIB/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/METRICSLIB/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
if s.get("module") != "METRICSLIB" or ap.get("model_id") != "claude-opus-5-5" or not ap.get("brief_sha256"):
    sys.exit("summary.json não é do METRICSLIB, model_id diferente de claude-opus-5-5 ou sem sha do brief")
print("summary.json: módulo, model_id e sha do brief conferem")
'
$py -I tools/provenance.py verify METRICSLIB
echo "gates/METRICSLIB.sh: OK"
