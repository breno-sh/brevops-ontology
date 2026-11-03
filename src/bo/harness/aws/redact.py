"""Redator do harness: roda ANTES de qualquer gravação (readback, desfechos, manifestos, notas de erro).

Duas camadas, sempre as duas:
  1. o redator do kit de segurança (SAFETY: $BO_REPO/deploy/safety/redactor.py, função redact(obj, context)),
     quando o kit existe; a execução real (CLI do Terraform) recusa rodar sem ele;
  2. o redator de base deste módulo, que cobre o mínimo do C00/C12: segredo, ambiente, script de boot, log,
     conteúdo de objeto e de mensagem viram 'withheld' sem valor nem hash; identificador real (ARN, conta de 12
     dígitos, id de recurso, e-mail, chave) nunca sai: vira referência simbólica ('ref:<nó>', 'sym:<SYM>') quando
     bate com o que o plano criou, ou 'withheld' (REDACT-IDENT-01) quando não bate.
Depois das duas, a gravação ainda passa pelo privacy_lint (bo.repo.privacy) e pelo validador do contrato.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

from . import pins

RULES = {
    "REDACT-SECRET-01": "atributo sensível ou write_only no schema, ou nome de segredo (senha, token, chave privada)",
    "REDACT-ENV-01": "variáveis de ambiente (bloco environment/variables)",
    "REDACT-BOOT-01": "script de inicialização (user data, custom data, startup script)",
    "REDACT-LOG-01": "conteúdo de log",
    "REDACT-OBJECT-01": "conteúdo de objeto (corpo de arquivo/objeto armazenado)",
    "REDACT-MESSAGE-01": "conteúdo de mensagem",
    "REDACT-IDENT-01": "identificador real (ARN, conta, id de recurso, nome criado) que não bate com o plano",
    "REDACT-TEXT-01": "texto livre (diagnóstico) com identificadores trocados por marcadores",
}

_SECRET = re.compile(r"(^|_)(password|passwd|secret|token|private_key|api_key|access_key|secret_key|"
                     r"master_password|auth_token|client_secret|sas|connection_string|passphrase)(_|$)", re.I)
_ENV = re.compile(r"(^|\.)(environment|env|environment_variables|variables)(\.|$)", re.I)
_BOOT = re.compile(r"(^|\.)(user_?data(_base64)?|custom_data|startup_script|metadata_startup_script|cloud_init)"
                   r"(\.|$)", re.I)
_LOG = re.compile(r"(^|\.)(log_events?|log_content|log_lines?)(\.|$)", re.I)
_OBJECT = re.compile(r"(^|\.)(content|content_base64|body|object_content|source_hash|etag)(\.|$)", re.I)
_MESSAGE = re.compile(r"(^|\.)(message_body|message_content|messages?)(\.|$)", re.I)

_TEXT_SUBS = [
    (re.compile(r"\barn:[A-Za-z0-9\-]+:[^\s\"',;)]*"), "<arn>"),
    (re.compile(r"(?<!\d)\d{12}(?!\d)"), "<conta>"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\b(AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b"), "<chave>"),
    (re.compile(r"\b(vpc|subnet|sg|sgr|igw|nat|eni|i|vol|snap|ami|rtb|acl|eipalloc|lt|db|kms|key|vpce|tgw|pcx|"
                r"fs|fsmp|cluster|bucket)-[0-9a-f]{6,32}\b"), "<id>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    (re.compile(r"\bocid1\.[a-z0-9_.-]+", re.I), "<ocid>"),
    (re.compile(r"/subscriptions/[^\s\"']+", re.I), "/subscriptions/<id>"),
    (re.compile(r"https?://[^\s\"']+"), "<url>"),
]


def content_rule(path: str) -> str | None:
    """Regra de conteúdo Withheld pelo caminho do campo (independe do valor)."""
    leaf = path.split(".")[-1]
    if _SECRET.search(leaf):
        return "REDACT-SECRET-01"
    if _BOOT.search(path):
        return "REDACT-BOOT-01"
    if _ENV.search(path):
        return "REDACT-ENV-01"
    if _LOG.search(path):
        return "REDACT-LOG-01"
    if _MESSAGE.search(path):
        return "REDACT-MESSAGE-01"
    if _OBJECT.search(path):
        return "REDACT-OBJECT-01"
    return None


def scrub_text(s: str) -> str:
    for rx, rep in _TEXT_SUBS:
        s = rx.sub(rep, s)
    return s


def looks_like_identifier(v) -> bool:
    if not isinstance(v, str):
        return False
    return scrub_text(v) != v


@dataclass
class FieldRedaction:
    state: str            # read | absent | not_read | withheld
    value: object = None
    rule_id: str | None = None


def redact_field(path: str, value, *, sensitive: bool = False, write_only: bool = False,
                 symbolic: dict | None = None, prefer=None) -> FieldRedaction:
    """Decide o que da leitura de um campo pode ser gravado. 'symbolic' mapeia valor real -> formas simbólicas
    (ids dos recursos criados no plano -> 'ref:<nó>', valores ligados a símbolos -> 'sym:<SYM>'). 'prefer' é o
    valor esperado pelo plano: um literal igual ao do plano é dado do plano (fica); quando o valor real tem mais
    de uma forma simbólica (id do bucket = nome ligado ao símbolo), a forma esperada é a escolhida."""
    if write_only:
        return FieldRedaction("not_read")
    rule = "REDACT-SECRET-01" if sensitive else content_rule(path)
    if rule:
        return FieldRedaction("withheld", rule_id=rule)
    if value is None:
        return FieldRedaction("absent")
    return FieldRedaction("read", _symbolize(value, symbolic or {}, prefer))


class _Ident(Exception):
    pass


def _symbolize(v, sym: dict, prefer=None):
    if isinstance(v, str) and isinstance(prefer, str):
        if v == prefer and not prefer.startswith(("ref:", "sym:")):
            return v
        if prefer in sym.get(v, ()):
            return prefer
    try:
        return _sym(v, sym)
    except _Ident:
        return _IDENT


_IDENT = object()


def _sym(v, sym):
    if isinstance(v, str):
        if v in sym:
            return sym[v][0]
        if looks_like_identifier(v):
            raise _Ident()
        return v
    if isinstance(v, list):
        return [_sym(x, sym) for x in v]
    if isinstance(v, dict):
        return {k: _sym(x, sym) for k, x in v.items()}
    return v


def finalize(fr: FieldRedaction) -> FieldRedaction:
    if fr.state == "read" and fr.value is _IDENT:
        return FieldRedaction("withheld", rule_id="REDACT-IDENT-01")
    return fr


# ------------------------------------------------------------------------------------------ kit de segurança
class KitRedactorMissing(RuntimeError):
    pass


def load_kit_redactor(path: Path | None = None):
    """Função redact(obj, context) do kit (SAFETY), ou None se o kit ainda não existe."""
    p = path or pins.repo_root() / "deploy" / "safety" / "redactor.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("bo_safety_redactor", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "redact", None)
    if not callable(fn):
        raise KitRedactorMissing(f"{p} não expõe redact(obj, context)")
    return fn


def deep_scrub(obj):
    """Camada final de base: todo texto livre passa pelo scrub_text."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, list):
        return [deep_scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: deep_scrub(v) for k, v in obj.items()}
    return obj


class Redactor:
    """Composição: kit (se houver) -> base. 'ids' registra quem redigiu, para o manifesto."""

    def __init__(self, kit_fn=None, require_kit: bool = False):
        if require_kit and kit_fn is None:
            raise KitRedactorMissing("execução real exige o redator do kit de segurança (deploy/safety/redactor.py)")
        self.kit_fn = kit_fn
        self.ids = (["kit:deploy/safety/redactor.py"] if kit_fn else []) + ["base:bo.harness.aws.redact"]

    def __call__(self, obj, context: str):
        if self.kit_fn is not None:
            obj = self.kit_fn(obj, context)
        return deep_scrub(obj)


def privacy_findings(text: str, name: str) -> list:
    from bo.repo import privacy
    lists, _ = privacy.load_lists()
    return privacy.scan_text(text, name, lists)
