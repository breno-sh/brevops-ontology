#!/bin/bash
# Gate específico do DOCS-GCP (chamado por make gate ID=DOCS-GCP): testes, cópia da documentação contra SHA256SUMS,
# regeneração idêntica, contratos C03/C15/C17, cobertura recalculada, manifesto e proveniência.
# Nunca chama make gate (sem recursão). Os gates do catálogo rodam depois, pelo runner.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
: "${BO_DATA:?BO_DATA indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes (tests/docs_gcp, pytest)"
$py -I -B -m pytest tests/docs_gcp -q -p no:cacheprovider

step "fonte: SOURCE.txt presente e cópia da tag confere com SHA256SUMS (offline)"
test -s "$BO_DATA/downloads/docs-google/SOURCE.txt"
$py -I -B -m bo.docs_gcp.fetch --verify

step "regeneração idêntica (saídas em \$BO_DATA/DOCS-GCP e coverage.json saem só de src/bo/docs_gcp)"
$py -I -B -m bo.docs_gcp.build --check

step "contratos: C03 docs_facts, C15 coverage.json, C17 summary.json"
$py -I -m bo.contracts.validate docs_facts "$BO_DATA/DOCS-GCP/docs_facts.jsonl" | tail -1
$py -I -m bo.contracts.validate C15_result results/DOCS-GCP/coverage.json | tail -1
$py -I -m bo.contracts.validate C17_summary results/DOCS-GCP/summary.json | tail -1

step "type_subcategory.jsonl: C03 3.1.0 type_fact, um registro por tipo do schema fixado"
$py -I -m bo.contracts.validate type_subcategory "$BO_DATA/DOCS-GCP/type_subcategory.jsonl" | tail -1
$py -I -B -c '
import json, os, sys
from bo.docs_gcp import sources as S
recs = [json.loads(x) for x in open(os.environ["BO_DATA"] + "/DOCS-GCP/type_subcategory.jsonl", encoding="utf-8")]
ids = [r["type_id"] for r in recs]
ok = len(ids) == len(set(ids)) and set(ids) == {"google:" + t for t in S.load_types()}
print(f"{len(recs)} tipos (= schema fixado: {ok})")
sys.exit(0 if ok else 1)
'

step "cobertura recalculada confere com coverage.json (relatada, sem meta)"
$py -I -m bo.docs_gcp.coverage DOCS-GCP

step "privacidade estrita nas saídas"
$py -I tools/privacy_lint.py --strict results/DOCS-GCP "$BO_DATA/DOCS-GCP" | tail -1

step "manifesto C17 (results/DOCS-GCP/MANIFEST.sha256)"
$py -I -B -m bo.docs_gcp.manifest --check

step "proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/DOCS-GCP/summary.json", encoding="utf-8"))
if s.get("module") != "DOCS-GCP" or s["agent_provenance"].get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json não é do DOCS-GCP ou model_id diferente de claude-opus-5-5")
print("summary.json: módulo e model_id conferem")
'
$py -I tools/provenance.py verify DOCS-GCP
echo "gates/DOCS-GCP.sh: OK"
