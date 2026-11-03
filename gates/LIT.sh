#!/bin/bash
# Gate específico do LIT (chamado por make gate ID=LIT): testes, regeneração idêntica, manifesto,
# livro de resolução do .bib atual, contrato C17 do summary.json e proveniência.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes unitários (tests/lit)"
$py -I -B -m unittest discover -s tests/lit -q

step "regeneração idêntica (lit/*, results/LIT/cocoon_disambiguation.json, MANIFEST)"
$py -I -B -m bo.lit.build --check

step "manifesto C17 confere"
shasum -a 256 -c results/LIT/MANIFEST.sha256 --quiet

step "livro de resolução é do .bib atual"
$py -I -B -c '
import json, sys
from bo.lit import bib
led = json.load(open("results/LIT/id_resolution.json", encoding="utf-8"))
sha = bib.content_sha256(open("lit/related.bib", encoding="utf-8").read())
bad = [k for k, r in led["records"].items() if r.get("status") != "ok"]
if led.get("bib_content_sha256") != sha:
    sys.exit("id_resolution.json é de outra versão do related.bib")
if bad:
    sys.exit("identificadores sem verificação: " + ", ".join(bad))
print("id_resolution.json:", len(led["records"]), "identificadores ok, resolvidos em", led["resolved_at"])
'

step "contrato C17 (summary.json)"
if $py -I -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("bo.contracts.validate") else 1)' 2>/dev/null; then
  $py -I -m bo.contracts.validate manifest_receipt results/LIT/summary.json
else
  echo "SKIP contratos: bo.contracts.validate ainda não existe (CONTRACTS não mergeado); conferência estrutural abaixo"
fi
$py -I -B -c '
import json, sys
s = json.load(open("results/LIT/summary.json", encoding="utf-8"))
need = {"schema", "contract", "module", "generated_at", "agent_provenance", "sources"}
miss = need - set(s)
ap = s.get("agent_provenance", {})
miss |= {"agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap}
if s.get("contract") != "C17" or s.get("module") != "LIT" or miss:
    sys.exit("summary.json fora do formato C17: " + ", ".join(sorted(miss)))
if not s.get("sources"):
    sys.exit("summary.json sem sources (N9: fonte, licença e transformação)")
print("summary.json C17: campos obrigatórios presentes,", len(s["sources"]), "fontes")
'

step "proveniência do agente confere (brief e entradas)"
$py -I tools/provenance.py verify LIT
echo "gates/LIT.sh: OK"
