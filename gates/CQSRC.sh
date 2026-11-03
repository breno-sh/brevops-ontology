#!/bin/bash
# Gate específico do CQSRC (chamado por make gate ID=CQSRC): fontes fixadas, testes, regeneração idêntica,
# conferência dos controles e do alinhamento, hashes, proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "fontes: tarballs fixados e SOURCE.txt (sem rede)"
$py -I -B -m bo.cqsrc.fetch --verify

step "testes unitários (tests/cqsrc)"
$py -I -B -m unittest discover -s tests/cqsrc -q

step "regeneração idêntica (cq/cis_*.csv, results/CQSRC/*, \$BO_DATA/CQSRC/* saem só dos tarballs e do catálogo)"
$py -I -B -m bo.cqsrc.build --check

step "controles e alinhamento (provedor, seção, título, fonte; linha de origem conferida no tarball)"
$py -I -B -m bo.cqsrc.src_check

step "hashes (MANIFEST C17)"
$py -I -B -c '
import hashlib, os, sys
from pathlib import Path
repo, data = Path(os.environ["BO_REPO"]), Path(os.environ["BO_DATA"])
bad = 0
for ln in (repo / "results/CQSRC/MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
    h, _, rel = ln.partition("  ")
    p = Path(rel.replace("$BO_DATA", str(data))) if rel.startswith("$BO_DATA") else repo / rel
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
        print("MANIFEST diverge:", rel); bad += 1
sys.exit(1 if bad else 0)
'
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/CQSRC/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "CQSRC" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
if len(s.get("sources", [])) < 4:
    sys.exit("summary.json: as 4 fontes (mods) têm de estar registradas")
print("summary.json C17: campos obrigatórios presentes")
'
$py -I tools/provenance.py verify CQSRC
echo "gates/CQSRC.sh: OK"
