#!/bin/bash
# Gate específico do PREREG (chamado por make gate ID=PREREG): testes, regeneração idêntica, contratos C15/C22/C28,
# estimandos, termo antigo, pilotos, sementes, poder, hashes e proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/prereg, pytest)"
$py -I -B -m pytest tests/prereg -q -p no:cacheprovider

step "regeneração idêntica (prereg/* e results/PREREG/* saem só de src/bo/prereg/content.py e prereg/power.py)"
$py -I -B -m bo.prereg.build --check

step "contratos: C15 (metrics_spec, power.json), C22 (probe_types), C28 (h2h_fairness)"
$py -I -m bo.contracts.validate results prereg/metrics_spec.yaml | tail -1
$py -I -m bo.contracts.validate results prereg/power.json | tail -1
$py -I -m bo.contracts.validate probes prereg/probe_types.yaml | tail -1
$py -I -m bo.contracts.validate C28 prereg/h2h_fairness.yaml | tail -1

step "estimandos, termo antigo, critérios dos pilotos, sementes"
$py -I -B -m bo.prereg.estimands | tail -1
$py -I -B -m bo.prereg.no_oldterm | tail -1
$py -I -B -m bo.prereg.pilot_exit | tail -1
$py -I -B -m bo.prereg.seeds | tail -1

step "poder por contraste reivindicado"
$py -I prereg/power.py --check prereg/power.json | tail -1

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/PREREG/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/PREREG/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/PREREG/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
if s.get("module") != "PREREG" or ap.get("model_id") != "claude-opus-5-5" or not ap.get("brief_sha256"):
    sys.exit("summary.json não é do PREREG, model_id diferente de claude-opus-5-5 ou sem sha do brief")
print("summary.json: módulo, model_id e sha do brief conferem")
'
$py -I tools/provenance.py verify PREREG
echo "gates/PREREG.sh: OK"
