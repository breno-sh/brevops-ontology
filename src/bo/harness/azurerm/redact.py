"""Redator do harness: roda sobre o state em memória ANTES de qualquer gravação (S16, §10.2).

Entrada: o JSON de `terraform show -json` (só em memória, vindo do canal efêmero). Saída: cópia em que todo
valor Withheld virou o marcador {"$withheld": REGRA}; o valor original não sobra em lugar nenhum, nem como hash.
Regras (rule_id no formato do C00):
  REDACT-SECRET-01   atributo marcado sensitive no state (sensitive_values) ou no schema fixado; write_only
  REDACT-SECRET-02   string com cara de credencial (chave de conta, connection string, SAS, PEM, token)
  REDACT-IDENT-01    identificador de conta/assinatura/locatário: /subscriptions/<guid>, GUID solto, e-mail
  REDACT-CONTENT-01  conteúdo Withheld por natureza: dados de boot, variáveis de ambiente, app settings, corpo
O redator do kit SAFETY (quando mergeado) entra como redator extra, depois deste; nenhum é opcional.
Fail closed: estrutura que o redator não entende levanta RedactionError e nada é gravado.
"""

from __future__ import annotations

import copy
import re

from . import schema as S

W = "$withheld"
GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
IDENT = [re.compile(r"/subscriptions/" + GUID, re.I), re.compile(r"^" + GUID + r"$"),
         re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")]
SECRET = [re.compile(p, re.I) for p in (
    r"AccountKey=", r"SharedAccessKey=", r"SharedAccessSignature", r"[?&]sig=", r"-----BEGIN [A-Z ]*PRIVATE KEY",
    r"Password=", r"\bpwd=", r"^eyJ[A-Za-z0-9_-]{10,}\.", r"DefaultEndpointsProtocol=")]
CONTENT_ATTRS = {"custom_data", "user_data", "app_settings", "environment_variables", "connection_string",
                 "source_content", "content", "content_base64", "message", "body", "script", "secure_environment_variables",
                 "settings_json", "protected_settings", "value"}
SECRET_NAME = re.compile(r"(password|secret|_key$|^key$|token|connection_string|sas|private_key|credential)", re.I)


class RedactionError(Exception):
    pass


def _mark(rule: str) -> dict:
    return {W: rule}


def is_withheld(v) -> bool:
    return isinstance(v, dict) and set(v) == {W}


def _scan_str(s: str):
    for p in SECRET:
        if p.search(s):
            return "REDACT-SECRET-02"
    for p in IDENT:
        if p.search(s):
            return "REDACT-IDENT-01"
    return None


def _walk(v, sens, node: dict | None, name: str | None):
    """sens: espelho de sensitive_values (True / dict / list / None). node: nó do schema do bloco atual."""
    if sens is True:
        return _mark("REDACT-SECRET-01")
    if name is not None and name in CONTENT_ATTRS:
        return _mark("REDACT-CONTENT-01") if v not in (None, "", [], {}) else v
    if isinstance(v, dict):
        out = {}
        a = S.attrs(node) if node else {}
        b = S.blocks(node) if node else {}
        for k, x in v.items():
            if not isinstance(k, str):
                raise RedactionError("chave não textual no state")
            ai = a.get(k)
            if ai is not None and (ai.sensitive or ai.write_only) and x not in (None, "", [], {}):
                out[k] = _mark("REDACT-SECRET-01")
                continue
            if ai is None and k not in b and SECRET_NAME.search(k) and x not in (None, "", [], {}, False, 0):
                out[k] = _mark("REDACT-SECRET-01")
                continue
            sub = sens.get(k) if isinstance(sens, dict) else None
            out[k] = _walk(x, sub, b[k].node if k in b else None, k)
        return out
    if isinstance(v, list):
        return [_walk(x, sens[i] if isinstance(sens, list) and i < len(sens) else None, node, None)
                for i, x in enumerate(v)]
    if isinstance(v, str):
        rule = _scan_str(v)
        return _mark(rule) if rule else v
    if v is None or isinstance(v, (bool, int, float)):
        return v
    raise RedactionError(f"tipo inesperado no state: {type(v).__name__}")


def redact_state(show_json: dict, sch: S.Schema | None = None) -> dict:
    """Redige o `terraform show -json` inteiro. Devolve só values.root_module.resources redigidos."""
    if not isinstance(show_json, dict):
        raise RedactionError("state não é objeto JSON")
    sch = sch or S.load()
    root = ((show_json.get("values") or {}).get("root_module") or {})
    if "child_modules" in root and root["child_modules"]:
        raise RedactionError("state com módulos filhos: o harness não gera módulo filho")
    out = []
    for r in root.get("resources") or []:
        for key in ("address", "mode", "type", "name"):
            if not isinstance(r.get(key), str):
                raise RedactionError(f"recurso do state sem {key}")
        node = sch.node("data" if r["mode"] == "data" else "resource", r["type"])
        vals = _walk(copy.deepcopy(r.get("values") or {}), r.get("sensitive_values") or {}, node, None)
        out.append({"address": r["address"], "mode": r["mode"], "type": r["type"], "name": r["name"],
                    "values": vals})
    return {"resources": out}


def assert_clean(obj, raw_secrets: list[str]) -> None:
    """Prova negativa usada antes de gravar: nenhum segredo conhecido sobrou no objeto redigido."""
    import json
    s = json.dumps(obj, ensure_ascii=False)
    for sec in raw_secrets:
        if sec and sec in s:
            raise RedactionError("valor sensível sobreviveu ao redator")
    for p in IDENT[:1] + SECRET:
        if p.search(s):
            raise RedactionError(f"padrão sensível sobreviveu ao redator ({p.pattern[:20]}…)")
