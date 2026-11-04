#!/bin/bash
# Gate específico do PROBEKIT (chamado por make gate ID=PROBEKIT): testes sobre respostas gravadas e simuladas,
# suporte validado antes do sorteio, teto de custo pelo plan_guard, corrida simulada, C22 pelo validador oficial,
# manifestos (C17) e proveniência. Nunca chama make gate, nunca nuvem, nunca credencial.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_ID=PROBEKIT
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/PROBEKIT}"
mkdir -p "$BO_TMP"
unset BO_CLOUD_GO
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/probes: controle negativo, repetição, censura, consistência eventual em respostas gravadas)"
$py -I -B -m pytest tests/probes -q -p no:cacheprovider

step "suporte validado antes do sorteio (regenera e compara; invariantes do sorteio)"
$py -I -B -m bo.probes.support_matrix | tail -3

step "C22: protocol_support.json pelo validador oficial"
$py -I -B -m bo.contracts.validate C22_probe_types deploy/probes/protocol_support.json | tail -1

step "teto de custo de cada template (plan_guard do SAFETY; armazenamento, tráfego, requisições)"
$py -I -B -m bo.probes.cost_cap | tail -2

step "corrida simulada dos casos sorteáveis (só local) e C22 das observações"
$py -I -B -m bo.probes.selfcheck | tail -1
$py -I -B -m bo.contracts.validate C22_observations "$BO_TMP/selfcheck/observations.jsonl" | tail -1
$py -I -B -m bo.probes.supervisor_heartbeat PROBEKIT --dir "$BO_TMP/selfcheck" | tail -1

step "manifestos (C17): PROBEKIT.sha256 e MANIFEST.sha256 regenerados idênticos; shasum -c"
$py -I -B -m bo.probes.hashes | tail -1
shasum -a 256 -c deploy/probes/PROBEKIT.sha256 | tail -1

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/PROBEKIT/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/PROBEKIT/summary.json", encoding="utf-8"))
if s.get("module") != "PROBEKIT" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do PROBEKIT ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify PROBEKIT
echo "gates/PROBEKIT.sh: OK"
