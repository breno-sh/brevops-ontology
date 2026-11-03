#!/bin/bash
# Gate específico do REPO (chamado por make gate ID=REPO): testes, regeneração idêntica, manifesto,
# contratos C00/C17 (quando o validador existir), proveniência e estado.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes unitários (tests/repo)"
$py -I -B -m unittest discover -s tests/repo -q

step "regeneração idêntica (modules/owners.json e results/REPO/MANIFEST.sha256)"
$py -I -B -c 'import sys; sys.path.insert(0, "src"); from bo.repo import regen; sys.exit(regen.main(["check"]))'

step "manifesto C17 confere"
shasum -a 256 -c results/REPO/MANIFEST.sha256 --quiet

step "contratos C00/C17"
if $py -I -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("bo.contracts.validate") else 1)' 2>/dev/null; then
  $py -I -m bo.contracts.validate manifest_receipt results/REPO/summary.json
else
  echo "SKIP contratos: bo.contracts.validate ainda não existe (CONTRACTS não mergeado); conferência estrutural abaixo"
fi
$py -I -B -c '
import json, sys
s = json.load(open("results/REPO/summary.json", encoding="utf-8"))
need = {"schema", "contract", "module", "generated_at", "agent_provenance", "sources"}
miss = need - set(s)
ap = s.get("agent_provenance", {})
miss |= {"agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap}
if s.get("contract") != "C17" or s.get("module") != "REPO" or miss:
    sys.exit("summary.json fora do formato C17: " + ", ".join(sorted(miss)))
print("summary.json C17: campos obrigatórios presentes")
'

step "proveniência do agente confere (brief e entradas)"
$py -I tools/provenance.py verify REPO

step "estado declarado cobre o catálogo"
$py -I -B -c '
import sys; sys.path.insert(0, "src")
from bo.repo import catalog, state
cat = catalog.load(); st = state.load()
falta = sorted(set(cat.modules) - set(st["modules"]))
if falta: sys.exit("state.json sem: " + ", ".join(falta))
mods = st["modules"]
fora = sum(v["status"] != "CURRENT" for v in mods.values())
print("state.json:", len(mods), "módulos,", fora, "fora de CURRENT")
'

step "trava (lock.sh selftest)"
tools/lock.sh selftest >/dev/null && echo "lock.sh: ok"

step "posses do catálogo disjuntas"
$py -I tools/ownership_check.py --all | tail -1
echo "gates/REPO.sh: OK"
