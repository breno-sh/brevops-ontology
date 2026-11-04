#!/bin/bash
# Gate específico do SAFETY (chamado por make gate ID=SAFETY): testes, regeração idêntica, C16 pelo validador
# único sobre manifestos gerados agora pelo runner simulado nos 4 provedores, dry-runs de varredura e teardown,
# pacote do supervisor só com biblioteca padrão, hashes (C17) e proveniência. Nunca chama make gate, nunca nuvem.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_ID=SAFETY
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/SAFETY}"
mkdir -p "$BO_TMP"
unset BO_CLOUD_GO
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/safety, pytest)"
$py -I -B -m pytest tests/safety -q -p no:cacheprovider

step "regeração idêntica (allowlist_skus.yaml, EXPECTED_RESIDUE.json, resumos saem do código e do SERVICE-EVIDENCE)"
$py -I -B -m bo.safety.build --check

step "C16: manifestos de um lote simulado completo nos 4 provedores, pelo validador único"
ex="$BO_TMP/gate_c16"
rm -rf "$ex"
$py -I -B -c '
import sys
from pathlib import Path
from bo.safety import skus
from bo.safety.sim_runner import run_batch, setup
base = Path(sys.argv[1])
for p in ("aws", "google", "azurerm", "oci"):
    setup(base / p, p, skus.load_table())
    run_batch(base / p, p)
' "$ex"
for p in aws google azurerm oci; do
  for side in public private; do
    $py -I -B -m bo.contracts.validate C16 "$ex/$p/$side/intent_manifest.jsonl" "$ex/$p/$side/run_manifest.jsonl" | tail -2
  done
done
$py -I -B -m bo.contracts.validate C16 contracts/stubs/C16/intent_manifest.jsonl contracts/stubs/C16/run_manifest.jsonl | tail -1
rm -rf "$ex"

step "dry-run: varredura dos 4 provedores (sem CLI de nuvem) e teardown por tipo"
bash deploy/safety/sweep_all.sh --dry-run | grep -E "^\[|cobertura|sweep_all"
for p in aws google azurerm oci; do bash "deploy/safety/teardown_$p.sh" --dry-run | head -1; done

step "pacote do supervisor (VM): monta e importa sem PyYAML"
bash deploy/safety/supervisor/bundle.sh "$BO_TMP/bundle" >/dev/null
$py -I -B -c '
import sys
sys.modules["yaml"] = None
sys.path.insert(0, sys.argv[1] + "/pkg/src")
import bo.safety.supervisor, bo.safety.ownership, bo.safety.providers, bo.safety.identity, bo.safety.residue
from bo.safety import skus
t = skus.load_table(sys.argv[1] + "/pkg/deploy/safety/allowlist_skus.json")
assert len(t["providers"]) == 4
print("supervisor: pacote importa só com a biblioteca padrão; tabela JSON com", sum(len(p["types"]) for p in t["providers"].values()), "tipos")
' "$BO_TMP/bundle"
rm -rf "$BO_TMP/bundle"

step "hashes (MANIFEST C17)"
$py -I -B -m bo.safety.hashes --check

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/SAFETY/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/SAFETY/summary.json", encoding="utf-8"))
if s.get("module") != "SAFETY" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do SAFETY ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify SAFETY
echo "gates/SAFETY.sh: OK"
