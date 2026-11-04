#!/bin/bash
# Gate específico do PILOT-EXIT (chamado por make gate ID=PILOT-EXIT): testes do avaliador com dados sintéticos,
# contratos C15/C17 das saídas, execução registrada conferida SEM decifrar de novo, nada em claro das retidas fora
# da caixa temporária, hashes (C17) e proveniência. Nunca toca nuvem; nunca roda tentativa nova.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
export BO_TMP="${BO_TMP:-$BO_DATA/tmp/PILOT-EXIT}"
export TMPDIR="$BO_TMP"
mkdir -p "$BO_TMP"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }
R=results/PILOT-EXIT

step "testes do avaliador (tests/pilot_exit: só dados sintéticos e a calibração pública)"
$py -I -B -m pytest tests/pilot_exit -q -p no:cacheprovider

step "execução registrada: código congelado = código do E2E, selo = índice (sem decifrar, sem tentativa nova)"
$py -I -m bo.pilot_exit.heldout_run --slices sto,net --verify-only

step "nenhum texto claro das retidas ficou na caixa temporária"
for d in run t d; do
  if [ -d "$BO_TMP/$d" ]; then echo "sobrou $BO_TMP/$d (árvore com retidas materializadas)"; exit 1; fi
done
$py -I -B -c '
import json, os, sys
from pathlib import Path
d = Path(os.environ["BO_DATA"]) / "PILOT-EXIT"
bad = []
for p in d.rglob("*.json"):
    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("source", "target", "flows", "rules", "timeline", "fixture", "bundle"):
                    bad.append(f"{p.name}:{path}/{k}")
                walk(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o[:50]):
                walk(v, f"{path}[{i}]")
    walk(json.loads(p.read_text(encoding="utf-8")), "")
if bad:
    sys.exit("evidência com campo de configuração (conteúdo retido?): " + ", ".join(bad[:5]))
print("evidência só com ids, códigos e contagens")
'

step "contratos C15 (exit_report, effort_calibration) e C17 (summary.json, FREEZE-P quando existe)"
$py -I -m bo.contracts.validate C15_result $R/exit_report.json $R/effort_calibration.json | tail -1
$py -I -m bo.contracts.validate manifest_receipt $R/summary.json | tail -1
if [ -f freeze/FREEZE-P/freeze_receipt.json ]; then
  $py -I -m bo.contracts.validate manifest_receipt freeze/FREEZE-P/freeze_receipt.json | tail -1
  $py -I tools/freeze.py verify FREEZE-P
fi

step "regeneração idêntica do cálculo do esforço (E7)"
$py -I -B -c '
import json, sys
from pathlib import Path
from bo.pilot_exit import reestimate as R
import os; root = Path(os.environ["BO_REPO"])
new = R.c15(R.build(root / "results", root))
old = json.loads(Path("results/PILOT-EXIT/effort_calibration.json").read_text(encoding="utf-8"))
if new != old:
    sys.exit("effort_calibration.json não é o que o código regenera agora")
print("effort_calibration.json regenera igual")
'

step "hashes dos resultados (MANIFEST C17)"
shasum -a 256 -c $R/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente (avaliador)"
$py -I -B -c '
import json, sys
s = json.load(open("results/PILOT-EXIT/summary.json", encoding="utf-8"))
p = s["agent_provenance"]
if s.get("module") != "PILOT-EXIT" or p.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do PILOT-EXIT ou model_id diferente de claude-opus-5-5")
need = {"role", "role_brief", "role_brief_version", "role_brief_sha256", "evaluated_code_sha256", "criteria_sha256", "attempt"}
miss = need - set(p.get("params", {}))
if miss:
    sys.exit("summary.json sem os parâmetros do avaliador: " + ", ".join(sorted(miss)))
print("summary.json: módulo, model_id e parâmetros do avaliador conferem")
'
$py -I tools/provenance.py verify PILOT-EXIT
echo "gates/PILOT-EXIT.sh: OK"
