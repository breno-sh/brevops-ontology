#!/bin/bash
# Gate específico do ONTPAT (chamado por make gate ID=ONTPAT): testes, pins, regeneração idêntica, perfil sobre o
# fecho de imports, compromissos como casos de teste, contrato C14 (proposta), hashes e proveniência.
# Nunca chama make gate (sem recursão). O teste de topo completo (re-execução) é o gate do catálogo.
set -euo pipefail
: "${BO_REPO:?BO_REPO indefinido}"
cd "$BO_REPO"
py=python
step() { echo "== $*"; }

step "testes unitários (tests/ontpat): formas pegam as violações plantadas, punning, OntoClean, regeneração"
$py -I -B -m unittest discover -s tests/ontpat -q

step "cadeia de ferramentas na versão fixada (ROBOT, HermiT, ELK, OWLAPI, Java, rdflib, pyshacl, ontologias externas)"
$py -I -B -m bo.ontpat.pins --check

step "regeneração idêntica (example-abox.ttl, upper_trial/*/cases.ttl, ONTPAT.html, UPPER_DECISION.html)"
$py -I -B -m bo.ontpat.build --check
$py -I -B -m bo.ontpat.docs --check

step "perfil OWL 2 DL sobre o fecho de imports, HermiT consistente, laudo do PROV-O"
$py -I -B -m bo.ontpat.profile --check

step "nomes (higiene, não validade)"
$py -I -B -m bo.ontpat.naming

step "compromissos do REQUIREMENTS com o ONTPAT como consumidor, como casos de teste dos padrões"
$py -I -B -m bo.ontpat.suite --check

step "teste de topo: resultado gravado coerente com as entradas e com a regra (a re-execução é o gate do catálogo)"
$py -I -B -m bo.ontpat.upper_trial --check --no-rerun

step "contrato C14"
if $py -I -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("bo.contracts.validate") else 1)' 2>/dev/null; then
  echo "bo.contracts.validate existe: o C14 publicado manda; conferir results/ONTPAT/C14_proposta contra ele"
  $py -I -m bo.contracts.validate realizations results/ONTPAT/C14_proposta/realizations.example.jsonl
else
  echo "SKIP bo.contracts.validate: ainda não existe (CONTRACTS vem depois do ONTPAT na ordem do plano)"
fi
$py -I -B -m bo.ontpat.c14 --check

step "hashes (MANIFEST C17)"
shasum -a 256 -c results/ONTPAT/MANIFEST.sha256 --quiet
echo "hashes conferem"

step "summary.json C17 e proveniência do agente"
$py -I -B -c '
import json, sys
s = json.load(open("results/ONTPAT/summary.json", encoding="utf-8"))
ap = s.get("agent_provenance", {})
miss = [k for k in ("schema", "contract", "module", "generated_at", "agent_provenance", "sources") if k not in s]
miss += ["agent_provenance." + k for k in ("model_id", "brief_sha256", "params", "inputs") if k not in ap]
if s.get("contract") != "C17" or s.get("module") != "ONTPAT" or miss or ap.get("model_id") != "claude-opus-5-5":
    sys.exit("summary.json fora do formato C17: " + ", ".join(miss))
print("summary.json C17: campos obrigatórios presentes")
'
$py -I tools/provenance.py verify ONTPAT
echo "gates/ONTPAT.sh: OK"
