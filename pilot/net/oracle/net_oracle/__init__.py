"""Oráculo offline da fatia NET (regras de segurança de rede), PILOT-NET-ORACLE.

API:
  evaluate_fixture(fx, reading="default") -> {"decisions": {flow_id: {...}}, "validity": {...}}
  judge(source_fx, target_fx, declared_losses, direction) -> veredito da tradução (ver judging.py)
  compare_decomposition(expected, actual) -> diferenças (ver decomposing.py)

Só biblioteca padrão. Não lê mapeamento, glossário nem saída de pipeline: a semântica vem de
semantics_profile.json (evidência do SERVICE-EVIDENCE e compromissos do REQUIREMENTS).
"""
from __future__ import annotations

from . import adapters, evaluate as _ev
from .model import ALLOW, DENY, UNKNOWN

__all__ = ["evaluate_fixture", "validity_of", "ALLOW", "DENY", "UNKNOWN", "judge", "compare_decomposition"]
ORACLE_VERSION = "1.0.0"


def validity_of(net) -> dict:
    vals = [v for v, _, _ in net.validity]
    if "INVALID" in vals:
        value, code = "INVALID", "INCONSISTENT"
    elif "UNKNOWN" in vals:
        value, code = "UNKNOWN", "MISSING_EVIDENCE"
    else:
        value, code = "VALID", None
    return {"value": value, "code": code, "reasons": [w for _, _, w in net.validity]}


def evaluate_fixture(fx: dict, reading: str = "default") -> dict:
    net, flows = adapters.build(fx)
    adapters.resolve_return_direction(flows)
    return {"decisions": _ev.evaluate(net, flows, reading), "validity": validity_of(net), "notes": net.notes}


def judge(*a, **k):
    from .judging import judge as _j
    return _j(*a, **k)


def compare_decomposition(*a, **k):
    from .decomposing import compare as _c
    return _c(*a, **k)
