"""Redator na origem do harness google (S16; C12-WITHHELD).

Recebe o state do Terraform ('terraform show -json', que traz valores sensíveis em claro) SÓ em memória e devolve
campos de leitura do C12: read (com valor), absent, not_read ou withheld (sem valor e sem hash, com rule_id e
at_source=true). Withheld quando: o atributo é sensitive/write_only no schema fixado, o state marca o caminho em
sensitive_values, ou uma regra de caminho de _templates/redaction_rules.json cobre o campo (boot script,
ambiente, conteúdo de objeto).

Canário: os segredos gerados na hora pelo runner ficam registrados aqui (só em memória); qualquer registro que
contenha um deles, inteiro ou como trecho, é recusado antes de ir para disco (assert_clean).
"""

from __future__ import annotations

import json

from . import common as C
from .render import load_rules, withheld_rule
from .schema import attr_at

WITHHELD, READ, ABSENT, NOT_READ = "withheld", "read", "absent", "not_read"


class RedactionError(RuntimeError):
    pass


def c12_path(path: str) -> str:
    """'lifecycle_rule.0.action.type' -> 'lifecycle_rule[0].action.type' (gramática de caminho do C12)."""
    out = []
    for s in path.split("."):
        if s.isdigit() and out:
            out[-1] += f"[{s}]"
        else:
            out.append(s)
    return ".".join(out)


def _walk(values, svals, segs):
    """Desce por valores e sensitive_values do state; devolve (estado, valor, sensível)."""
    cur, sens = values, svals
    for s in segs:
        if sens is True:
            return WITHHELD, None, True
        if isinstance(cur, list):
            if s.isdigit():
                i = int(s)
                if i >= len(cur):
                    return ABSENT, None, False
                cur = cur[i]
                sens = sens[i] if isinstance(sens, list) and i < len(sens) else None
                continue
            if len(cur) == 1:          # bloco de instância única aparece como lista de 1 no state
                cur = cur[0]
                sens = sens[0] if isinstance(sens, list) and sens else None
            elif not cur:
                return ABSENT, None, False
            else:
                return NOT_READ, None, False
        if not isinstance(cur, dict):
            return NOT_READ, None, False
        if s not in cur:
            return NOT_READ, None, False
        cur = cur[s]
        sens = sens.get(s) if isinstance(sens, dict) else None
    if sens is True:
        return WITHHELD, None, True
    if cur is None or cur == []:
        return ABSENT, None, False
    if isinstance(cur, list) and len(cur) == 1 and isinstance(cur[0], dict) and segs and not segs[-1].isdigit():
        return READ, cur[0], False
    return READ, cur, False


class GoogleRedactor:
    def __init__(self, schema, rules: dict | None = None):
        self.schema = schema
        self.rules = rules or load_rules()
        self._secrets: list[str] = []

    def register_secret(self, value: str) -> None:
        if len(value) < 8:
            raise RedactionError("segredo curto demais para o canário")
        self._secrets.append(value)

    def rule_for(self, kind: str, rtype: str, path: str) -> dict | None:
        block = self.schema.block(kind, rtype)
        attr, _ = attr_at(block, path.split(".")) if block else (None, [])
        return withheld_rule(self.rules, rtype, path, attr)

    def field(self, kind: str, rtype: str, path: str, resource: dict | None) -> dict:
        """Um campo do C12 a partir do recurso do state (ou None se o recurso não está no state)."""
        p = c12_path(path)
        rule = self.rule_for(kind, rtype, path)
        if rule is not None:
            return {"path": p, "state": WITHHELD, "redaction": {"rule_id": rule["rule_id"], "at_source": True}}
        if resource is None:
            return {"path": p, "state": NOT_READ}
        st, val, sens = _walk(resource.get("values") or {}, resource.get("sensitive_values") or {},
                              path.split("."))
        if sens:
            return {"path": p, "state": WITHHELD, "redaction": {"rule_id": "REDACT-SECRET-01", "at_source": True}}
        if st == READ:
            rec = {"path": p, "state": READ, "value": val}
            self.assert_clean(rec)
            return rec
        return {"path": p, "state": st}

    def assert_clean(self, obj) -> None:
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        for s in self._secrets:
            if s in text:
                raise RedactionError("registro contém um segredo gerado na hora; nada gravado")

    def forget(self) -> None:
        self._secrets.clear()


def resources_by_address(state: dict) -> dict:
    """Recursos do 'terraform show -json' por endereço (só o módulo raiz: o harness não renderiza módulos)."""
    root = ((state or {}).get("values") or {}).get("root_module") or {}
    return {r["address"]: r for r in root.get("resources", [])}


def now() -> str:
    return C.now()
