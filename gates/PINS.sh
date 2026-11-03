#!/bin/bash
# Gate específico do PINS (chamado por make gate ID=PINS): testes, regeneração idêntica, conferência do corte,
# contrato C13 do pins.json e dos versions_doc, manifestos, privacidade das saídas, C17 e proveniência.
# Offline: só lê o instantâneo $BO_DATA/PINS/registry_index/ e a pré-busca. Nunca chama make gate.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/pins), incluindo mutações plantadas no pins.json e no history_versions.json"
$py -I -B -m pytest tests/pins -q -p no:cacheprovider

step "regeneração idêntica (universe/pins.json, universe/history_versions.json, results/PINS/selection.json)"
$py -I -B -m bo.pins.build --check

step "4 providers, mesma data de corte, toda versão com data e sha do índice"
$py -I -B -m bo.pins.check | tail -1

step "contrato C13: pins.json e history_versions.json no validador único"
$py -I -B -m bo.contracts.validate versions universe/pins.json | tail -1
$py -I -B -m bo.contracts.validate history_versions universe/history_versions.json | tail -1

step "manifestos: results/PINS e registry_index"
shasum -a 256 -c results/PINS/MANIFEST.sha256 --quiet
(cd "$BO_DATA/PINS/registry_index" && shasum -a 256 -c MANIFEST.sha256 --quiet)
echo "hashes conferem"

step "privacidade das saídas versionadas"
$py -I tools/privacy_lint.py --strict universe/pins.json universe/history_versions.json | tail -1

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/PINS/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/PINS/summary.json", encoding="utf-8"))
if s.get("module") != "PINS" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do PINS ou model_id diferente de claude-opus-5-5")
if not s.get("sources"):
    sys.exit("summary.json sem sources")
print("summary.json: módulo, model_id e", len(s["sources"]), "fontes conferem")
'
$py -I tools/provenance.py verify PINS
echo "gates/PINS.sh: OK"
