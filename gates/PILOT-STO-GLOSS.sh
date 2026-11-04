#!/bin/bash
# Gate específico do PILOT-STO-GLOSS (chamado por make gate ID=PILOT-STO-GLOSS). Nunca chama make gate.
# Os gates do catálogo (validate glossary, anchor_claims, smoke, consume, privacidade, posse, commits,
# integração) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:=/Users/breno/doutorado/brevops-data}"
cd "$BO_REPO"
py=python
d="$BO_DATA/PILOT-STO-GLOSS"
step() { echo "== $*"; }

step "testes (tests/pilot_sto_gloss): gate anchor_claims com controles, diagnóstico do grão como está"
$py -I -B -m pytest tests/pilot_sto_gloss -q -p no:cacheprovider

step "saídas regeneradas idênticas das entradas (grão pela biblioteca, glossário, âncoras, pacote)"
$py -I -B -m bo.pilot_sto_gloss.build --check
$py -I -B -m bo.pilot_sto_gloss.diagnose --check

step "saídas do módulo pelo validador oficial (C19, C20, C08)"
for f in canonical_units canonical_atoms glossary claims decisions; do
  test -f "$d/$f.jsonl" || { echo "saída ausente: $d/$f.jsonl (ver results/PILOT-STO-GLOSS/CONTRACT_CHANGE.txt)"; exit 1; }
done
$py -I -m bo.contracts.validate canonical_units "$d/canonical_units.jsonl"
$py -I -m bo.contracts.validate canonical_atoms "$d/canonical_atoms.jsonl"
$py -I -m bo.contracts.validate glossary "$d/glossary.jsonl"
$py -I -m bo.contracts.validate claims "$d/claims.jsonl"
$py -I -m bo.contracts.validate decisions "$d/decisions.jsonl"
test -f "$d/bundle/candidates.jsonl" || { echo "pacote ausente: $d/bundle/candidates.jsonl"; exit 1; }
$py -I -m bo.contracts.validate candidates "$d/bundle/candidates.jsonl"

step "pacote do mapeador: exatamente os arquivos declarados (GLOSSARY_BRIEF 1.2.0) e hashes"
want="MANIFEST.sha256 candidates.jsonl canonical_atoms.jsonl canonical_units.jsonl claims.jsonl decisions.jsonl glossary.jsonl value_space.jsonl"
have=$(cd "$d/bundle" && ls | sort | tr '\n' ' ' | sed 's/ $//')
[ "$have" = "$want" ] || { echo "pacote com arquivos diferentes do declarado: $have"; exit 1; }
(cd "$d/bundle" && shasum -a 256 -c MANIFEST.sha256 --quiet) && echo "MANIFEST do pacote confere"
for f in glossary decisions claims canonical_units canonical_atoms; do
  cmp -s "$d/$f.jsonl" "$d/bundle/$f.jsonl" || { echo "bundle/$f.jsonl difere da saída do módulo"; exit 1; }
done

step "proveniência C17"
$py -I tools/provenance.py verify PILOT-STO-GLOSS
