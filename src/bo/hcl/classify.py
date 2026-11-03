"""Classificação de cadeias e de chaves, sem perder estrutura.

Ordem para uma cadeia sem interpolação:
  1. ""                                   -> literal
  2. documento JSON (objeto ou lista)     -> documento (árvore; principais e identificadores viram símbolos)
  3. CIDR / IP                            -> expressão cidr/ip: endereço (literal, ou símbolo se público), prefixo, classe
  4. ARN                                  -> expressão arn: partição, serviço, região, conta (símbolo), recurso (segmentos)
  5. 12 dígitos                           -> símbolo (id de conta)
  6. número em texto                      -> literal
  7. vocabulário: valor comum (>= N famílias no mesmo contexto) num contexto de enumeração -> literal; senão símbolo

Retido (C06-WITHHELD): segredo, ambiente, script de boot, conteúdo de objeto, log, mensagem. Decidido pela chave
(atributo, bloco, chave de objeto ou de documento), antes de olhar o valor; o valor nunca é lido para o termo.
"""

from __future__ import annotations

import ipaddress
import re

# ------------------------------------------------------------------------------------------------ retidos
_SECRET = re.compile(
    r"((password|passwd|passphrase)(_wo)?$|^secret$|client_secret|_secret$|secret_(string|binary|key|value|data|access_key)$"
    r"|private_key(_pem|_openssh)?$|api_key$|^access_key$|^secret_key$|auth_token$|^token$|_token$|sas_token"
    r"|connection_string|^primary_key$|^secondary_key$|shared_key$|key_material|pre_shared_key|^psk$"
    r"|^admin_password$|^certificate_password$)")
_ENV_NAMES = {"environment", "environment_variables", "env", "app_settings", "env_vars", "environment_variable",
              "environmentvariables", "secrets"}
_BOOT = {"user_data", "user_data_base64", "custom_data", "metadata_startup_script", "startup_script",
         "startup-script", "user-data", "cloud_init", "cloud-init", "init_script", "inline", "script_content"}
_CONTENT = {"content", "content_base64", "sensitive_content", "source_content", "body", "file_content"}
_MESSAGE = {"message_body", "message_content", "messagebody"}
_LOG = {"log_events", "log_content", "logevents"}
WITHHELD_BLOCKS = {"provisioner": "boot_script", "connection": "secret"}


def withheld_reason(key: str, rtype: str = "", value_is_scalar: bool | None = None) -> str | None:
    """Motivo de retenção pela chave (nome de atributo, bloco ou chave de mapa/documento)."""
    k = key.strip().lower()
    if not k:
        return None
    if k in _BOOT:
        return "boot_script"
    if k in _MESSAGE:
        return "message_content"
    if k in _LOG:
        return "log"
    if k in _ENV_NAMES:
        # "Environment = \"prod\"" em tags é rótulo, não variável de ambiente: só coleção ou bloco é retido
        return None if value_is_scalar else "environment"
    if _SECRET.search(k):
        return "secret"
    if k in _CONTENT:
        return "object_content"
    if k == "value" and ("secret" in rtype or "ssm_parameter" in rtype or "key_vault" in rtype):
        return "secret"
    return None


# ------------------------------------------------------------------------------------------------ CIDR / IP
_V4 = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}"
_CIDR4 = re.compile(rf"^({_V4})/(\d{{1,2}})$")
_IP4 = re.compile(rf"^({_V4})$")
_CIDR6 = re.compile(r"^([0-9A-Fa-f:]*:[0-9A-Fa-f:.]*)/(\d{1,3})$")
_IP6 = re.compile(r"^([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})$")


_RFC1918 = [ipaddress.ip_network(x) for x in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
_ULA = ipaddress.ip_network("fc00::/7")
_DOC = [ipaddress.ip_network(x) for x in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")]
_SHARED = ipaddress.ip_network("100.64.0.0/10")


def ip_class(addr) -> str:
    """any | loopback | link_local | private (RFC 1918, ULA) | shared (100.64/10) | documentation |
    multicast | reserved (outros blocos especiais) | public. Só 'public' tem o endereço simbolizado."""
    if addr.is_unspecified:
        return "any"
    if addr.is_loopback:
        return "loopback"
    if addr.is_link_local:
        return "link_local"
    if addr.version == 4 and any(addr in n for n in _RFC1918) or addr.version == 6 and addr in _ULA:
        return "private"
    if addr.version == 4 and addr in _SHARED:
        return "shared"
    if any(addr.version == n.version and addr in n for n in _DOC):
        return "documentation"
    if addr.is_multicast:
        return "multicast"
    if addr.is_private or addr.is_reserved or not addr.is_global:
        return "reserved"
    return "public"


def parse_cidr(s: str):
    """-> (endereço como escrito, prefixo, classe) ou None."""
    m = _CIDR4.match(s) or _CIDR6.match(s)
    if not m:
        return None
    try:
        a = ipaddress.ip_address(m.group(1))
        p = int(m.group(2))
    except ValueError:
        return None
    if p > (32 if a.version == 4 else 128):
        return None
    cls = "any" if p == 0 else ip_class(a)
    return m.group(1), p, cls


def parse_ip(s: str):
    m = _IP4.match(s) or _IP6.match(s)
    if not m:
        return None
    try:
        a = ipaddress.ip_address(m.group(1))
    except ValueError:
        return None
    return m.group(1), ip_class(a)


# ------------------------------------------------------------------------------------------------ ARN
ARN_PREFIX = "arn" + ":"
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_REGION = re.compile(r"^([a-z]{2}(-gov|-iso[a-z]?)?-[a-z]+-\d|\*|)$")


def split_arn(s: str):
    """arn:partição:serviço:região:conta:recurso -> partes (o recurso pode ter ':' e '/')."""
    if not s.startswith(ARN_PREFIX):
        return None
    parts = s.split(":", 5)
    if len(parts) < 6:
        return None
    return parts[1:]


_SEG = re.compile(r"([/:])")


def arn_resource_segments(res: str) -> list:
    """Separa o recurso em segmentos e separadores, preservando a ordem: ['role', '/', 'nome']."""
    return [x for x in _SEG.split(res) if x != ""]


# ------------------------------------------------------------------------------------------------ números
_NUMSTR = re.compile(r"^-?\d+(\.\d+)?$")
ACCOUNT_LIKE = re.compile(r"^\d{12}$")


def is_numeric_text(s: str) -> bool:
    return bool(_NUMSTR.match(s))


def looks_json(s: str) -> bool:
    t = s.lstrip()
    return len(t) > 1 and t[0] in "{[" and t.rstrip()[-1:] in "}]"


def is_policy(tree) -> bool:
    return isinstance(tree, dict) and ("Statement" in tree or "statement" in tree)
