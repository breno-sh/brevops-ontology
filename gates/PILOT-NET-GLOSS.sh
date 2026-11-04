#!/bin/bash
# Gate específico do PILOT-NET-GLOSS (chamado por make gate ID=PILOT-NET-GLOSS): testes, regeneração idêntica
# (grão, glossário, âncoras, decisões e pacote saem só do código e das entradas), contratos C19/C20/C08/C05 no
# validador único, gate F4 das âncoras, MANIFEST e proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/PILOT-NET-GLOSS}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
D="$BO_DATA/PILOT-NET-GLOSS"
step() { echo "== $*"; }

step "testes (tests/pilot_net_gloss, pytest)"
$py -I -B -m pytest tests/pilot_net_gloss -q -p no:cacheprovider

step "regeneração idêntica e MANIFEST (bo.pilot_net_gloss.build --check)"
$py -I -B -m bo.pilot_net_gloss.build --check

step "contratos pelo validador único"
for kf in "glossary:glossary.jsonl" "claims:claims.jsonl" "decisions:decisions.jsonl" \
          "canonical_units:canonical_units.jsonl" "canonical_atoms:canonical_atoms.jsonl" \
          "candidates:bundle/candidates.jsonl" "value_space:bundle/value_space.jsonl"; do
  $py -I -B -m bo.contracts.validate "${kf%%:*}" "$D/${kf#*:}" | tail -1
done

step "pacote do mapeador: exatamente os arquivos do GLOSSARY_BRIEF (G1) e MANIFEST confere"
want="MANIFEST.sha256 candidates.jsonl canonical_atoms.jsonl canonical_units.jsonl claims.jsonl decisions.jsonl glossary.jsonl value_space.jsonl"
got=$(ls "$D/bundle" | sort | tr '\n' ' ' | sed 's/ $//')
[ "$got" = "$want" ] || { echo "pacote com arquivos fora do declarado: $got"; exit 1; }
(cd "$D/bundle" && shasum -a 256 -c MANIFEST.sha256 >/dev/null) && echo "bundle/MANIFEST.sha256 confere"

step "F4: toda âncora multi-provedor é alegação com evidência"
$py -I -B -m bo.pilot_net_gloss.anchor_claims

step "summary.json C17 e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/PILOT-NET-GLOSS/summary.json | tail -1
$py -I tools/provenance.py verify PILOT-NET-GLOSS
echo "gates/PILOT-NET-GLOSS.sh: OK"
