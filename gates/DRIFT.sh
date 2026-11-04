#!/bin/bash
# Gate específico do DRIFT (chamado por make gate ID=DRIFT): contrato C13 dos eventos, C15 do churn.json,
# C17 do summary.json, regeneração idêntica a partir dos HIST-*, manifestos e proveniência.
# O atom_history.jsonl é validado pelo gate do catálogo (validate versions); aqui não repete (tempo).
# Offline: não baixa nada e não executa binário. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/DRIFT}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
OUT="$BO_DATA/DRIFT"
step() { echo "== $*"; }

step "saídas presentes e sem staging esquecido"
for f in events.jsonl atom_history.jsonl rename_candidates.jsonl MANIFEST.sha256; do
  [ -s "$OUT/$f" ] || { echo "  falta $OUT/$f"; exit 1; }
done
[ ! -e "$OUT/.staging" ] || { echo "  $OUT/.staging ainda existe"; exit 1; }
echo "  ok"

step "contrato C13 (events) no validador oficial, em paralelo com a regeneração (resultado mais abaixo)"
ev_log="$BO_TMP/gate_events_validate.log"
( $py -I -B -m bo.contracts.validate versions "$OUT/events.jsonl" > "$ev_log" 2>&1 ) &
ev_pid=$!

step "contrato C15 (churn.json) e C17 (summary.json)"
$py -I -B -m bo.contracts.validate results results/DRIFT/churn.json | tail -1
$py -I -B -m bo.contracts.validate manifest_receipt results/DRIFT/summary.json | tail -1

step "manifesto dos dados (\$BO_DATA/DRIFT/MANIFEST.sha256)"
(cd "$OUT" && shasum -a 256 -c MANIFEST.sha256 --quiet)
echo "  confere"

step "regeneração idêntica a partir dos HIST-* e dos guias"
$py -I -B -m bo.drift.regen_check

step "resultado do contrato C13 (events)"
if wait "$ev_pid"; then tail -1 "$ev_log"; else tail -5 "$ev_log"; exit 1; fi

step "manifesto C17 do repositório (results/DRIFT/MANIFEST.sha256)"
shasum -a 256 -c results/DRIFT/MANIFEST.sha256 --quiet
echo "  confere"

step "proveniência do agente"
$py -I tools/provenance.py verify DRIFT
echo "gates/DRIFT.sh: OK"
