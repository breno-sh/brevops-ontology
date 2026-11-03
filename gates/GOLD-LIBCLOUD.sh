#!/bin/bash
# Gate específico do GOLD-LIBCLOUD (chamado por make gate ID=GOLD-LIBCLOUD): fonte fixada, testes, regeneração
# idêntica, C09 pelo validador único, resolução (todo campo resolve num campo de API registrado ou é UNRESOLVED),
# hashes e proveniência. Nunca chama make gate (sem recursão).
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "fonte fixada (sha256 do tar.gz do PyPI e árvore extraída igual ao tar.gz)"
$py -I -B -c 'from bo.gold_libcloud import source as S; v = S.verify(); print(v["sha256"][:16], v["py_files"], "arquivos .py")'

step "testes (tests/gold_libcloud, pytest)"
$py -I -B -m pytest tests/gold_libcloud -q -p no:cacheprovider

step "regeneração idêntica (\$BO_DATA/GOLD-LIBCLOUD/* e results/GOLD-LIBCLOUD/stats.json saem só do código)"
$py -I -B -m bo.gold_libcloud.build --check

step "C09 pelo validador único"
$py -I -B -m bo.contracts.validate correspondences "$BO_DATA/GOLD-LIBCLOUD/libcloud.sssom.tsv" | tail -1

step "resolução: campo de API registrado ou UNRESOLVED (S1-S5)"
$py -I -B -m bo.gold_libcloud.resolve GOLD-LIBCLOUD

step "hashes (MANIFEST C17)"
$py -I -B -c '
import sys
from pathlib import Path
from bo.repo import receipts
probs = receipts.verify_manifest(Path("results/GOLD-LIBCLOUD/MANIFEST.sha256"))
if probs:
    sys.exit("MANIFEST não confere: " + "; ".join(p["problem"] for p in probs))
n = sum(1 for x in open("results/GOLD-LIBCLOUD/MANIFEST.sha256") if x.strip())
print(f"hashes conferem ({n} arquivos)")
'

step "summary.json C17 (validador único) e proveniência do agente"
$py -I -B -m bo.contracts.validate manifest_receipt results/GOLD-LIBCLOUD/summary.json | tail -1
$py -I -B -c '
import json, sys
s = json.load(open("results/GOLD-LIBCLOUD/summary.json", encoding="utf-8"))
if s.get("module") != "GOLD-LIBCLOUD" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do GOLD-LIBCLOUD ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify GOLD-LIBCLOUD
echo "gates/GOLD-LIBCLOUD.sh: OK"
