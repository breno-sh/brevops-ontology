#!/bin/bash
# Gate específico do HCL (chamado por make gate ID=HCL): testes, saídas declaradas, contrato C06, manifesto,
# privacidade do conteúdo inteiro em fluxo, summary.json C17 e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo (stats, privacy_lint, symbolic_roundtrip com a
# regeneração da amostra, crosscheck) rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
D="$BO_DATA/HCL"
T="${BO_TMP:-$BO_DATA/tmp/HCL}"
step() { echo "== [$(TZ=America/Recife date '+%Y-%m-%dT%H:%M:%S')] $*"; }

step "testes (tests/hcl, pytest)"
$py -I -B -m pytest tests/hcl -q -p no:cacheprovider

step "saídas declaradas existem e não estão vazias"
for f in resources.parquet symbolic_config.jsonl parse_stats.json licenses.json symbolic_config.index.json vocab_keep.u64 unit_counts.json; do
  test -s "$D/$f" || { echo "falta $D/$f"; exit 1; }
done
test -s results/HCL/summary.json || { echo "falta results/HCL/summary.json"; exit 1; }
echo "saídas presentes"

step "contrato C06: resources.parquet inteiro (validador oficial)"
$py -I -m bo.contracts.validate C06 "$D/resources.parquet"

step "contrato C06: symbolic_config.jsonl, amostra determinística (1 em 50 repositórios, pelo índice)"
mkdir -p "$T/c06_sample"
$py -I -B -c '
import hashlib, json, sys
d, out = sys.argv[1], sys.argv[2]
idx = json.load(open(d + "/symbolic_config.index.json"))["repos"]
pick = sorted(r for r in idx if int(hashlib.sha256(r.encode()).hexdigest(), 16) % 50 == 0)
with open(d + "/symbolic_config.jsonl", "rb") as f, open(out, "wb") as o:
    for r in pick:
        s, e, _ = idx[r]; f.seek(s); o.write(f.read(e - s))
print(f"amostra: {len(pick)} repositórios")
' "$D" "$T/c06_sample/symbolic_config.jsonl"
$py -I -m bo.contracts.validate C06 "$T/c06_sample/symbolic_config.jsonl"

step "contrato C06: validação do jsonl inteiro registrada para ESTE arquivo (bo.hcl.validate_full)"
$py -I -B -c '
import json, sys
from bo.hcl.common import sha256_file
d = sys.argv[1]
r = json.load(open(d + "/contract_report.json"))
sha = sha256_file(d + "/symbolic_config.jsonl")
ok = r["result"] == "PASS" and r["errors"] == 0 and r["sha256"] == sha and r["items"] > 0
print(f"contract_report: {r["items"]} registros, {r["errors"]} erros, sha confere: {r["sha256"] == sha}")
sys.exit(0 if ok else 1)
' "$D"

step "manifesto results/HCL/MANIFEST.sha256 (caminhos portáteis)"
$py -I -B -c '
import os, sys
from bo.hcl.common import sha256_file
env = {"$BO_DATA": os.environ["BO_DATA"], "$BO_REPO": os.environ["BO_REPO"]}
bad = n = 0
for ln in open("results/HCL/MANIFEST.sha256", encoding="utf-8"):
    if not ln.strip():
        continue
    sha, path = ln.rstrip("\n").split("  ", 1)
    for k, v in env.items():
        path = path.replace(k, v, 1) if path.startswith(k) else path
    n += 1
    if sha256_file(path) != sha:
        bad += 1; print("DIVERGE", ln.split("  ", 1)[1].strip())
print(f"manifesto: {n} arquivo(s), {bad} divergência(s)")
sys.exit(1 if bad or not n else 0)
'

step "privacidade do conteúdo inteiro em fluxo (mesmas regras do privacy_lint, inclusive o jsonl > 50 MB)"
$py -I -m bo.hcl.privacy_stream "$D" results/HCL

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/HCL/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "HCL" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
print("summary.json C17: campos obrigatórios presentes")
'
$py -I -m bo.contracts.validate C17_summary results/HCL/summary.json
$py -I tools/provenance.py verify HCL
echo "gates/HCL.sh: OK"
