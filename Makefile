# BrevOps Ontology — alvos comuns (dono: REPO). Python sempre com -I; temporário em $BO_DATA/tmp/<ID>.
ROOT    := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
PY      ?= python
BO_REPO ?= $(ROOT)
BO_DATA ?= /Users/breno/doutorado/brevops-data
export BO_REPO BO_DATA
RUN = $(PY) -I -B -c 'import sys; sys.path.insert(0, sys.argv.pop(1) + "/src"); import importlib; sys.exit(importlib.import_module(sys.argv.pop(1)).main())' $(ROOT)

.PHONY: help bootstrap gate smoke integration selftest test owners manifest lanes

help:
	@echo "make bootstrap            prepara o ambiente (.pth, hooks, exclude, árvore BO_DATA)"
	@echo "make gate ID=<X>          roda os gates do módulo X (smoke antes; nada roda se algo não resolve)"
	@echo "make smoke ID=<X>         só o smoke offline dos gates de X"
	@echo "make integration          testes de integração cruzada (tests/integration/*), SKIP registrado"
	@echo "make selftest             selftests de todas as ferramentas do REPO"
	@echo "make test                 testes unitários do REPO (tests/repo)"
	@echo "make owners               regenera modules/owners.json a partir do modulos.json"
	@echo "make manifest             regenera results/REPO/MANIFEST.sha256"
	@echo "make lanes                lista as worktrees bo-*"

bootstrap:
	@$(RUN) bo.repo.bootstrap

gate:
	@test -n "$(ID)" || { echo "uso: make gate ID=<stable_id>" >&2; exit 2; }
	@$(RUN) bo.repo.gate_runner $(ID)

smoke:
	@test -n "$(ID)" || { echo "uso: make smoke ID=<stable_id>" >&2; exit 2; }
	@$(PY) -I $(ROOT)/tools/gate_smoke.py $(ID)

integration:
	@$(PY) -I $(ROOT)/tools/integration.py

selftest:
	@for t in privacy_lint commit_lint freeze invalidate gate_smoke ownership_check provenance; do \
	  $(PY) -I $(ROOT)/tools/$$t.py --selftest || exit 1; done
	@$(ROOT)/tools/lock.sh selftest

test:
	@$(PY) -I -B -m unittest discover -s $(ROOT)/tests/repo -q

owners:
	@$(RUN) bo.repo.regen owners

manifest:
	@$(RUN) bo.repo.regen manifest

lanes:
	@$(ROOT)/tools/bo-lane list
