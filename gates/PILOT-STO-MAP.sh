#!/bin/bash
# Gate específico do PILOT-STO-MAP (chamado por make gate ID=PILOT-STO-MAP). Nunca chama make gate.
# Os gates do catálogo (validate C09, skos_roundtrip, árbitro congelado, smoke, consumo, privacidade, posse,
# commits, integração) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:=/Users/breno/doutorado/brevops-data}"
cd "$BO_REPO"
py=python
d="$BO_DATA/PILOT-STO-MAP"
step() { echo "== $*"; }

step "testes (tests/pilot_sto_map): exaustividade, orientação, pacote e registro, evidência, rerodada"
$py -I -B -m pytest tests/pilot_sto_map -q -p no:cacheprovider

step "mapeamento regerado do pacote e das decisões idêntico ao definitivo"
$py -I -B -m bo.pilot_sto_map.build --check

step "saídas do módulo pelo validador oficial (C09, C21)"
for f in mapping.sssom.tsv verdicts.jsonl; do
  test -f "$d/$f" || { echo "saída ausente: $d/$f"; exit 1; }
done
$py -I -m bo.contracts.validate correspondences "$d/mapping.sssom.tsv"
$py -I -m bo.contracts.validate verdicts "$d/verdicts.jsonl"

step "vereditos gravados = árbitro de hoje sobre o mapeamento gravado; saídas = build_record e pipeline_report"
$py -I -B -m bo.pilot_sto_map.verify

step "manifesto dos resultados e proveniência C17"
shasum -a 256 -c "results/PILOT-STO-MAP/MANIFEST.sha256" --quiet && echo "MANIFEST dos resultados confere"
$py -I tools/provenance.py verify PILOT-STO-MAP
