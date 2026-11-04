#!/bin/bash
# Gate específico do PILOT-NET-ORACLE (chamado por make gate ID=PILOT-NET-ORACLE): testes do pacote, regeneração
# idêntica do gabarito, schema do expected_answers, envelope selado, hashes (C17) e proveniência.
# Nunca chama make gate, nunca decifra as retidas e nunca toca nuvem.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes do pacote (tests/pilot_net_oracle)"
$py -I -B -m pytest tests/pilot_net_oracle -q -p no:cacheprovider

step "regeneração idêntica (fixtures_calib, directions, exemplos, expected_answers, ORACLE.sha256, build_report)"
$py -I -B -m bo.pilot_net_oracle.build --check

step "schema do expected_answers.json (pilot/net/oracle/expected_answers.schema.json)"
$py -I -B -c '
import json, jsonschema
s = json.load(open("pilot/net/oracle/expected_answers.schema.json", encoding="utf-8"))
d = json.load(open("pilot/net/expected_answers.json", encoding="utf-8"))
jsonschema.Draft202012Validator(s).validate(d)
print("expected_answers.json confere com o schema")
'
$py -I -m bo.contracts.validate pilot_expected_answers pilot/net/expected_answers.json | tail -1

step "envelope selado das retidas (sem decifrar)"
$py -I -B -m bo.pilot_net_oracle.seal verify

step "hashes (ORACLE.sha256 e MANIFEST C17)"
shasum -a 256 -c pilot/net/ORACLE.sha256 --quiet
shasum -a 256 -c results/PILOT-NET-ORACLE/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -m bo.contracts.validate manifest_receipt results/PILOT-NET-ORACLE/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/PILOT-NET-ORACLE/summary.json", encoding="utf-8"))
if s.get("module") != "PILOT-NET-ORACLE" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do PILOT-NET-ORACLE ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify PILOT-NET-ORACLE
echo "gates/PILOT-NET-ORACLE.sh: OK"
