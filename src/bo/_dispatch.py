"""Despachante do coordenador para pacotes de família sem dono (bo.docs, bo.pilot, bo.map, ...).

Resolve o módulo-alvo (argumento que seja stable_id do catálogo, senão BO_ID, senão a pasta de $BO_TMP)
e executa bo.<pacote do módulo>.<comando>: chama main(argv) se existir; senão roda o módulo como __main__.
O pacote do módulo é o primeiro `$BO_REPO/src/bo/<pkg>/` do seu `owns` no catálogo
(fallback: stable_id em minúsculas com '-' trocado por '_').
"""
import importlib
import json
import os
import runpy
import sys
from pathlib import Path


def _catalog():
    p = os.environ.get("BO_MODULES") or "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json"
    return {m["stable_id"]: m for m in json.load(open(p))["modules"]}


def _target(argv, cat):
    for a in argv:
        if a in cat:
            return a
    if os.environ.get("BO_ID") in cat:
        return os.environ["BO_ID"]
    tmp = os.environ.get("BO_TMP")
    if tmp and Path(tmp).name in cat:
        return Path(tmp).name
    raise SystemExit("despachante: não sei o módulo-alvo (passe o ID, ou defina BO_ID ou BO_TMP)")


def _pkg(mid, cat):
    for o in cat[mid].get("owns", []):
        if o.startswith("$BO_REPO/src/bo/") and o.endswith("/"):
            rel = o[len("$BO_REPO/src/bo/"):-1]
            if "/" not in rel:
                return rel
    return mid.lower().replace("-", "_")


def run(cmd, argv):
    cat = _catalog()
    mid = _target(argv, cat)
    name = f"bo.{_pkg(mid, cat)}.{cmd}"
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name and name.startswith(e.name):
            sys.stderr.write(f"despachante: {mid} ainda não implementa {name}\n")
            return 3
        raise
    if hasattr(mod, "main"):
        rc = mod.main(list(argv))
        return int(rc or 0)
    sys.argv = [name] + list(argv)
    runpy.run_module(name, run_name="__main__", alter_sys=True)
    return 0
