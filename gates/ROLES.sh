#!/bin/bash
# Gate específico do ROLES (chamado por make gate ID=ROLES): testes, regeneração idêntica, C04 e C15 pelo
# validador único, auditoria ainda válida, hashes e proveniência. A simetria (bo.roles.symmetry) é gate próprio
# do catálogo e não é repetida aqui. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/ROLES}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/roles, pytest)"
$py -I -B -m pytest tests/roles -q -p no:cacheprovider

step "regeneração idêntica (roles.jsonl e by_provider saem só de rules.yaml, do código e das entradas)"
$py -I -B -m bo.roles.build --check

step "C04 roles e C15 by_provider pelo validador único"
$py -I -B -m bo.contracts.validate roles "$BO_DATA/ROLES/roles.jsonl" | tail -1
$py -I -B -m bo.contracts.validate C15 results/ROLES/by_provider.json | tail -1

step "auditoria: todo átomo auditado ainda tem o papel e a regra que foram auditados"
$py -I -B -c '
import json, os, sys
a = json.load(open("results/ROLES/audit.json", encoding="utf-8"))
want = {i["atom_id"]: (i["role"], i["rule_id"]) for i in a["items"]}
seen = {}
with open(os.environ["BO_DATA"] + "/ROLES/roles.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r["atom_id"] in want:
            seen[r["atom_id"]] = (r["role"], r["rule_id"])
stale = [k for k, v in want.items() if seen.get(k) != v]
if stale:
    sys.exit(f"auditoria velha: {len(stale)} átomo(s) auditados mudaram de papel ou sumiram")
print(f"auditoria: {len(want)} átomos auditados conferem")
'

step "hashes (MANIFEST C17)"
$py -I -B -m bo.roles.manifest --check

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/ROLES/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/ROLES/summary.json", encoding="utf-8"))
if s.get("module") != "ROLES" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do ROLES ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify ROLES
echo "gates/ROLES.sh: OK"
