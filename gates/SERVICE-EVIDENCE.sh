#!/bin/bash
# Gate específico do SERVICE-EVIDENCE (chamado por make gate ID=SERVICE-EVIDENCE): testes, regeneração idêntica,
# C25 pelo validador único, níveis e pins (os mesmos comandos do catálogo), formato do protocol_support, hashes e
# proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_ID=SERVICE-EVIDENCE
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/SERVICE-EVIDENCE}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/service_evidence, pytest)"
$py -I -B -m pytest tests/service_evidence -q -p no:cacheprovider

step "regeneração idêntica (service_evidence, protocol_support e relatórios saem só do código e das entradas)"
$py -I -B -m bo.service_evidence.build --check

step "C25 service_evidence pelo validador único"
$py -I -B -m bo.contracts.validate service_evidence "$BO_DATA/SERVICE-EVIDENCE/service_evidence.jsonl" | tail -1

step "níveis: publicado resolve na fonte fixada, derivado aponta fatos, interpretado tem model_id"
$py -I -B -m bo.evidence.levels | tail -1

step "pins: toda fonte ligada a um pin e datada"
$py -I -B -m bo.evidence.pinned | tail -1

step "protocol_support no formato do módulo (results/SERVICE-EVIDENCE/protocol_support.schema.json)"
$py -I -B -c '
import json, os, sys
import jsonschema
s = json.load(open("results/SERVICE-EVIDENCE/protocol_support.schema.json", encoding="utf-8"))
v = jsonschema.Draft202012Validator(s)
n = bad = 0
for line in open(os.environ["BO_DATA"] + "/SERVICE-EVIDENCE/protocol_support.jsonl", encoding="utf-8"):
    n += 1
    bad += sum(1 for _ in v.iter_errors(json.loads(line)))
if bad or not n:
    sys.exit(f"protocol_support: {bad} erro(s) em {n} linha(s)")
print(f"protocol_support: {n} linhas conferem")
'

step "hashes (MANIFEST C17)"
$py -I -B -m bo.service_evidence.manifest --check

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/SERVICE-EVIDENCE/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/SERVICE-EVIDENCE/summary.json", encoding="utf-8"))
if s.get("module") != "SERVICE-EVIDENCE" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do SERVICE-EVIDENCE ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify SERVICE-EVIDENCE
echo "gates/SERVICE-EVIDENCE.sh: OK"
