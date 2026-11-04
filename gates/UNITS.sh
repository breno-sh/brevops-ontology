#!/bin/bash
# Gate específico do UNITS (chamado por make gate ID=UNITS): QUDT fixado conferido, testes, regeneração idêntica do
# value_space a partir das entradas, C05 no validador único, os dois gates de unidade, hashes e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/UNITS}"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "QUDT 3.5.3 fixado (sha256 dos dois vocabulários e SOURCE.txt)"
$py -I -B -c 'import sys; from bo.units import qudt; e = qudt.verify_files(); print("; ".join(e) or "QUDT confere"); sys.exit(1 if e else 0)'

step "testes (tests/units, pytest)"
$py -I -B -m pytest tests/units -q -p no:cacheprovider

step "regeneração idêntica (value_space, contagens, coverage e iri_status saem só do código e das entradas)"
$py -I -B -m bo.units.build --check

step "C05 value_space pelo validador único"
$py -I -B -m bo.contracts.validate value_space "$BO_DATA/UNITS/value_space.jsonl" | tail -1

step "unidade e grandeza só por IRI QUDT ou marcador; taxa com janela"
$py -I -B -m bo.units.qudt_iri_only | tail -1
$py -I -B -m bo.units.rate_window | tail -1

step "decisão de grandeza única (UNITS-QK-01, STO-MAP CC-5): citação do QUDT conferida e arquivo regenerado igual"
$py -I -B -m bo.units.crosscheck --check
$py -I -B -m bo.units.crosscheck || echo "(divergência dos outros núcleos é relatada, não é gate do UNITS: dono SEMANTICS/TRANSFORMS)"

step "hashes (MANIFEST C17)"
$py -I -B -m bo.units.manifest --check

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/UNITS/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/UNITS/summary.json", encoding="utf-8"))
if s.get("module") != "UNITS" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do UNITS ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify UNITS
echo "gates/UNITS.sh: OK"
