#!/bin/bash
# Gate específico do PILOT-NET-MAP (chamado por make gate ID=PILOT-NET-MAP). Nunca chama make gate.
# Os gates do catálogo (C09, SKOS ida e volta, árbitro congelado, smoke, consumo, privacidade, posse, commits,
# integração) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:=/Users/breno/doutorado/brevops-data}"
cd "$BO_REPO"
py=python
d="$BO_DATA/PILOT-NET-MAP"
step() { echo "== $*"; }

step "testes (tests/pilot_net_map): guardas, pulos sem valor documentado, grupos, exaustividade, ida e volta"
$py -I -B -m pytest tests/pilot_net_map -q -p no:cacheprovider

step "saídas presentes"
for f in mapping.sssom.tsv verdicts.jsonl build_report.json decisions_log.jsonl; do
  test -f "$d/$f" || { echo "saída ausente: $d/$f (ver results/PILOT-NET-MAP/CONTRACT_CHANGE.txt)"; exit 1; }
done

step "pacote oficial, regeneração idêntica, exaustividade, só pacote, só registro, orientação, vereditos"
$py -I -B -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r["bundle"]["official"] else "mapeamento feito sobre pacote não oficial")' "$d/build_report.json"
$py -I -B -m bo.pilot_net_map.verify --dir "$d"

step "vereditos pelo validador oficial (C21)"
$py -I -m bo.contracts.validate verdicts "$d/verdicts.jsonl"

step "manifesto dos resultados"
(cd "$BO_REPO" && shasum -a 256 -c results/PILOT-NET-MAP/MANIFEST.sha256 --quiet) && echo "MANIFEST confere"

step "proveniência C17"
$py -I tools/provenance.py verify PILOT-NET-MAP
