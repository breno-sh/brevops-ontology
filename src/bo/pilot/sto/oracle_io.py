"""Carrega o oráculo do PILOT-STO-ORACLE (pilot/sto/oracle/sto_oracle.py) só para AVALIAR.

O pipeline (lift, owl, abox, translate, lower) nunca importa este módulo; o teste de independência confere.
O sha do oráculo carregado tem de bater com o de pilot/sto/ORACLE.sha256 (o arquivo congelado do oráculo)."""

from __future__ import annotations

import importlib.util
import sys

from . import common as C

_MOD = None


def oracle_path():
    return C.oracle_dir() / "sto_oracle.py"


def expected_sha() -> str:
    for line in (C.repo() / "pilot" / "sto" / "ORACLE.sha256").read_text(encoding="utf-8").splitlines():
        h, _, path = line.partition("  ")
        if path.strip() == "pilot/sto/oracle/sto_oracle.py":
            return h
    raise RuntimeError("ORACLE.sha256 sem a linha do sto_oracle.py")


def load():
    global _MOD
    if _MOD is not None:
        return _MOD
    p = oracle_path()
    got = C.sha256_file(p)
    if got != expected_sha():
        raise RuntimeError(f"oráculo alterado: sha {got[:12]} ≠ ORACLE.sha256")
    spec = importlib.util.spec_from_file_location("bo_pilot_sto_oracle_eval", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    _MOD = mod
    return mod
