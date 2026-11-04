"""Redator do kit: roda sobre state e plan do Terraform ANTES da primeira serialização em disco persistente.

Regra do §10.2: state e plan contêm valores sensíveis. O runner os mantém no canal privado efêmero (ephemeral.py)
e tudo o que sai de lá passa por aqui, em memória, antes de qualquer gravação. A porta única de gravação
(write_redacted) só aceita objetos Redacted, isto é, devolvidos por este redator; um dict cru é recusado.

O que é retido (vira "WITHHELD", sem valor e sem hash):
  R-SENS    o que o próprio Terraform marca como sensível: after_sensitive/before_sensitive do plano,
            sensitive_values do show -json, sensitive_attributes do arquivo de state (v4), outputs sensitive
  R-VAR     valor de toda variável do plano (o nome fica)
  R-SECRET  chave com nome de segredo (senha, token, chave privada, connection string, chave de acesso)
  R-CONTENT conteúdo Withheld: user data / custom data / startup script, variáveis de ambiente, app settings,
            corpo de objeto e de mensagem, conteúdo de log
  R-IDENT   identificador real dentro de texto: ARN, OCID, caminho de subscription, conta de 12 dígitos, e-mail,
            chave de acesso, JWT, chave PEM, connection string. Vira o símbolo do contexto (symbols: real->símbolo)
            quando o runner o conhece, senão "WITHHELD:IDENT".
O selo (Redacted.meta) guarda só contagens por regra, nunca valores.

Interface para os harnesses: redact(obj, context) devolve o objeto redigido (context é o nome do fluxo, ex.
"readback", ou um dict {"kind": ..., "symbols": {...}}).
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .common import SafetyError, append_line, write_atomic

SCHEMA = "bo.safety.redaction/1"
WITHHELD = "WITHHELD"
IDENT = "WITHHELD:IDENT"

SECRET_KEY = re.compile(
    r"(?i)^(.*_)?(password|passwd|passphrase|secret|secret_string|secret_binary|token|auth_token|access_token|"
    r"api_key|apikey|private_key|private_key_pem|key_material|plaintext|ciphertext_blob|client_secret|"
    r"connection_string|primary_connection_string|secondary_connection_string|primary_access_key|"
    r"secondary_access_key|primary_key|secondary_key|access_key|secret_key|sas|sas_token|shared_key|"
    r"master_password|admin_password|administrator_login_password|root_password|credentials|"
    r"private_key_id|session_token|kube_config|kube_admin_config|certificate_password|pfx_blob)(_.*)?$")
CONTENT_KEY = re.compile(
    r"(?i)^(user_data|user_data_base64|custom_data|metadata_startup_script|startup-script|startup_script|"
    r"cloud_init|cloudinit|environment|environment_variables|env|app_settings|variables|content|"
    r"content_base64|source_code|body|message|message_body|log_events|log_content|zip_file|"
    r"sensitive_content)$")
# Em registro qualquer (kind=record, ex. readback dos harnesses) só valem as chaves de conteúdo inequívocas;
# "message", "body", "content", "variables" só são retidos dentro de state/plan, onde são atributo do recurso.
CONTENT_KEY_RECORD = re.compile(
    r"(?i)^(user_data|user_data_base64|custom_data|metadata_startup_script|startup-script|startup_script|"
    r"message_body|object_content|log_events|log_content|sensitive_content|zip_file|environment_variables)$")

IDENT_PATTERNS = [
    ("arn", re.compile(r"\barn:(?:aws|aws-cn|aws-us-gov|aws-iso[a-z-]*):[A-Za-z0-9\-]*:[A-Za-z0-9\-]*:\d*:[^\s\"',]+")),
    ("ocid", re.compile(r"\bocid1\.[a-z0-9_-]+\.[a-z0-9_-]*\.[a-z0-9_-]*\.[A-Za-z0-9_.-]+")),
    ("azure_sub", re.compile(r"/subscriptions/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                             r"[0-9a-fA-F]{12}[^\s\"',]*")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*")),
    ("pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)),
    ("connstr", re.compile(r"(?i)\b(?:AccountKey|SharedAccessKey|SharedAccessSignature|Password|Pwd)=[^;\s\"']+")),
    ("gcp_sa_key", re.compile(r"\"private_key\"\s*:\s*\"[^\"]+\"")),
    ("twelve", re.compile(r"(?<![0-9A-Za-z])\d{12}(?![0-9A-Za-z])")),
]
SAFE_EMAIL = re.compile(r"@(example\.(com|org|net)|[a-z0-9-]+\.(example|invalid|test))$", re.I)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class Redacted:
    """Objeto que passou pelo redator. Só ele atravessa a porta de gravação."""
    obj: object
    meta: dict = field(default_factory=dict)

    def text(self) -> str:
        return json.dumps(self.obj, ensure_ascii=False, sort_keys=True)


class RedactionRefused(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "REDACT")


class Counter(dict):
    def hit(self, rule: str, n: int = 1):
        self[rule] = self.get(rule, 0) + n


# --------------------------------------------------------------------------------------------- texto livre
def scrub_text(s: str, symbols: dict | None, cnt: Counter) -> str:
    if HEX64.match(s):
        return s  # hash sha256 (do kit ou do contrato), não identificador
    out = s
    if symbols:
        for real_v in sorted(symbols, key=len, reverse=True):
            if real_v and real_v in out:
                out = out.replace(real_v, symbols[real_v])
                cnt.hit("R-IDENT")
    for name, rx in IDENT_PATTERNS:
        def rep(m, name=name):
            v = m.group(0)
            if name == "email" and SAFE_EMAIL.search(v):
                return v
            cnt.hit("R-IDENT")
            return IDENT
        out = rx.sub(rep, out)
    return out


def _scrub_all(obj, symbols, cnt):
    if isinstance(obj, str):
        return scrub_text(obj, symbols, cnt)
    if isinstance(obj, list):
        return [_scrub_all(x, symbols, cnt) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_all(v, symbols, cnt) for k, v in obj.items()}
    return obj


def _withhold(v, rule, cnt):
    if v is None or v == "" or v == [] or v == {}:
        return v
    if isinstance(v, str) and v.startswith(WITHHELD):
        return v
    cnt.hit(rule)
    return WITHHELD


def _key_rules(obj, cnt, depth=0, tf=True):
    """Nomes de segredo e de conteúdo Withheld, em qualquer profundidade. tf=False: registro qualquer."""
    content = CONTENT_KEY if tf else CONTENT_KEY_RECORD
    if isinstance(obj, list):
        return [_key_rules(x, cnt, depth + 1, tf) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        ks = str(k)
        if tf and SECRET_KEY.match(ks) and not isinstance(v, bool) and not _is_meta_key(ks):
            out[k] = _withhold(v, "R-SECRET", cnt) if not isinstance(v, (dict, list)) else _withhold_tree(v, "R-SECRET", cnt)
        elif content.match(ks) and not isinstance(v, bool):
            out[k] = _withhold_tree(v, "R-CONTENT", cnt)
        else:
            out[k] = _key_rules(v, cnt, depth + 1, tf)
    return out


def _is_meta_key(k: str) -> bool:
    # nomes que descrevem a configuração do segredo, não o segredo (ex.: "password_length", "secret_arn" tem ARN
    # e é tratado pelo R-IDENT; "token_ttl" é número de configuração)
    return bool(re.search(r"(?i)(_length|_ttl|_version|_wo_version|_enabled|_rotation|_policy|_type|_name|_id)$", k))


def _withhold_tree(v, rule, cnt):
    """Retém folhas mantendo a forma (o leitor ainda vê quais chaves existiam)."""
    if isinstance(v, dict):
        return {k: _withhold_tree(x, rule, cnt) for k, x in v.items()}
    if isinstance(v, list):
        return [_withhold_tree(x, rule, cnt) for x in v]
    if isinstance(v, bool) or v is None:
        return v
    return _withhold(v, rule, cnt)


def _apply_mask(values, mask, cnt):
    """mask no formato do Terraform (after_sensitive / sensitive_values): true = sensível, dict/list paralelos."""
    if mask is True:
        return _withhold_tree(values, "R-SENS", cnt) if isinstance(values, (dict, list)) else _withhold(values, "R-SENS", cnt)
    if isinstance(mask, dict) and isinstance(values, dict):
        return {k: (_apply_mask(v, mask[k], cnt) if k in mask else v) for k, v in values.items()}
    if isinstance(mask, list) and isinstance(values, list):
        return [(_apply_mask(v, mask[i], cnt) if i < len(mask) else v) for i, v in enumerate(values)]
    return values


def _apply_paths(values, paths, cnt):
    """sensitive_attributes do state v4: lista de caminhos [{type: get_attr, value: x}, {type: index, value: ..}]."""
    for p in paths or []:
        steps = p if isinstance(p, list) else p.get("path", []) if isinstance(p, dict) else []
        _set_path(values, steps, cnt)
    return values


def _set_path(node, steps, cnt):
    if not steps:
        return
    st = steps[0]
    key = st.get("value") if isinstance(st, dict) else st
    if isinstance(st, dict) and isinstance(key, dict):
        key = key.get("value")
    container = node
    if isinstance(container, dict) and key in container:
        if len(steps) == 1:
            container[key] = _withhold_tree(container[key], "R-SENS", cnt)
        else:
            _set_path(container[key], steps[1:], cnt)
    elif isinstance(container, list) and isinstance(key, int) and 0 <= key < len(container):
        if len(steps) == 1:
            container[key] = _withhold_tree(container[key], "R-SENS", cnt)
        else:
            _set_path(container[key], steps[1:], cnt)


# --------------------------------------------------------------------------------------------- formatos
def looks_like_plan(o) -> bool:
    return isinstance(o, dict) and "format_version" in o and ("resource_changes" in o or "planned_values" in o)


def looks_like_state_show(o) -> bool:
    return isinstance(o, dict) and "format_version" in o and "values" in o and "resource_changes" not in o


def looks_like_state_file(o) -> bool:
    return isinstance(o, dict) and "lineage" in o and "resources" in o and "terraform_version" in o


def _module_resources(mod, cnt):
    if not isinstance(mod, dict):
        return mod
    mod = dict(mod)
    rs = []
    for r in mod.get("resources", []) or []:
        r = dict(r)
        if "values" in r:
            r["values"] = _apply_mask(r["values"], r.get("sensitive_values", {}), cnt)
        rs.append(r)
    if "resources" in mod:
        mod["resources"] = rs
    if "child_modules" in mod:
        mod["child_modules"] = [_module_resources(c, cnt) for c in mod["child_modules"]]
    return mod


def _plan(o, cnt):
    o = copy.deepcopy(o)
    for v in (o.get("variables") or {}).values():
        if isinstance(v, dict) and "value" in v:
            v["value"] = _withhold_tree(v["value"], "R-VAR", cnt) if v["value"] not in (None, "") else v["value"]
    for rc in o.get("resource_changes", []) or []:
        ch = rc.get("change") or {}
        if "after" in ch:
            ch["after"] = _apply_mask(ch["after"], ch.get("after_sensitive", {}), cnt)
        if "before" in ch:
            ch["before"] = _apply_mask(ch["before"], ch.get("before_sensitive", {}), cnt)
    for oc in (o.get("output_changes") or {}).values():
        for side in ("before", "after"):
            if side in oc and (oc.get(f"{side}_sensitive") or oc.get("sensitive")):
                oc[side] = _withhold_tree(oc[side], "R-SENS", cnt) if isinstance(oc[side], (dict, list)) else _withhold(oc[side], "R-SENS", cnt)
    for key in ("planned_values", "prior_state"):
        node = o.get(key)
        if isinstance(node, dict):
            vals = node.get("values", node)
            if isinstance(vals, dict) and "root_module" in vals:
                vals["root_module"] = _module_resources(vals["root_module"], cnt)
            elif "root_module" in node:
                node["root_module"] = _module_resources(node["root_module"], cnt)
            for out in (vals.get("outputs") or {}).values() if isinstance(vals, dict) else []:
                if isinstance(out, dict) and out.get("sensitive"):
                    out["value"] = _withhold_tree(out.get("value"), "R-SENS", cnt)
    cfg = o.get("configuration")
    if isinstance(cfg, dict):
        o["configuration"] = cfg  # expressões só têm referências e constantes; os nomes de segredo pegam abaixo
    return o


def _state_show(o, cnt):
    o = copy.deepcopy(o)
    vals = o.get("values") or {}
    if "root_module" in vals:
        vals["root_module"] = _module_resources(vals["root_module"], cnt)
    for out in (vals.get("outputs") or {}).values():
        if isinstance(out, dict) and out.get("sensitive"):
            out["value"] = _withhold_tree(out.get("value"), "R-SENS", cnt)
    return o


def _state_file(o, cnt):
    o = copy.deepcopy(o)
    for r in o.get("resources", []) or []:
        for inst in r.get("instances", []) or []:
            if "attributes" in inst:
                inst["attributes"] = _apply_paths(inst["attributes"], inst.get("sensitive_attributes"), cnt)
            if "private" in inst:
                inst["private"] = _withhold(inst["private"], "R-SENS", cnt)
    for out in (o.get("outputs") or {}).values():
        if isinstance(out, dict) and out.get("sensitive"):
            out["value"] = _withhold_tree(out.get("value"), "R-SENS", cnt)
    return o


def redact_tf(obj, kind: str = "auto", symbols: dict | None = None) -> Redacted:
    """Redige plano, state (show -json ou arquivo v4) ou registro qualquer. Devolve Redacted com selo."""
    if isinstance(obj, (bytes, bytearray)):
        raise RedactionRefused("binário (plano .tfplan) não é serializável: use terraform show -json no efêmero")
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError:
            pass
    cnt = Counter()
    if kind == "auto":
        kind = ("plan" if looks_like_plan(obj) else "state_file" if looks_like_state_file(obj)
                else "state" if looks_like_state_show(obj) else "record")
    if kind == "plan":
        o = _plan(obj, cnt)
    elif kind == "state":
        o = _state_show(obj, cnt)
    elif kind == "state_file":
        o = _state_file(obj, cnt)
    else:
        o = copy.deepcopy(obj)
    o = _key_rules(o, cnt, tf=(kind != "record"))
    o = _scrub_all(o, symbols, cnt)
    meta = {"schema": SCHEMA, "kind": kind, "counts": dict(sorted(cnt.items()))}
    if kind != "record" and isinstance(o, dict):
        o["bo_redaction"] = meta  # selo: o varredor de artefato cru distingue plano/state já redigido
    return Redacted(o, meta)


def redact(obj, context=None):
    """Interface dos harnesses (redact(obj, context) -> obj). context: str (nome do fluxo) ou
    {"kind": "plan|state|state_file|record|auto", "symbols": {real: símbolo}}."""
    kind, symbols = "auto", None
    if isinstance(context, dict):
        kind = context.get("kind", "auto")
        symbols = context.get("symbols")
    return redact_tf(obj, kind, symbols).obj


# --------------------------------------------------------------------------------------------- porta de gravação
RAW_STATE_MARK = re.compile(r"\"lineage\"\s*:|\"terraform_version\"\s*:\s*\"\d")


def _privacy_scan(text: str, name: str) -> list[str]:
    try:  # no repositório: o privacy_lint oficial (inclui as listas privadas)
        from bo.repo import privacy
        lists, _ = privacy.load_lists()
        return sorted({f.rule for f in privacy.scan_text(text, name, lists)})
    except ImportError:  # na VM do supervisor: os padrões do próprio redator
        hits = []
        for nm, rx in IDENT_PATTERNS:
            if rx.search(text):
                hits.append(nm)
        return hits


def serialize(red: Redacted, jsonl: bool = False) -> str:
    if not isinstance(red, Redacted):
        raise RedactionRefused("gravação recusada: objeto não passou pelo redator (state/plan sem redator)")
    if jsonl:
        recs = red.obj if isinstance(red.obj, list) else [red.obj]
        return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)
    return json.dumps(red.obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def write_redacted(path: Path, red: Redacted, append: bool = False, ephemeral_roots=()) -> None:
    """Única porta de gravação persistente do kit. Recusa: objeto cru, texto com achado do privacy_lint, e
    caminho dentro do canal efêmero (lá se grava só pela CLI do Terraform)."""
    text = serialize(red, jsonl=append)
    path = Path(path)
    for root in ephemeral_roots:
        r = Path(root).resolve()
        if path.resolve() == r or r in path.resolve().parents:
            raise RedactionRefused("gravação redigida dentro do canal efêmero não faz sentido: destino errado")
    finds = _privacy_scan(text, path.name)
    if finds:
        raise RedactionRefused("privacy_lint reprovou a gravação redigida: " + ", ".join(finds))
    if append:
        for ln in text.splitlines():
            append_line(path, ln)
    else:
        write_atomic(path, text)


def write_raw(path: Path, obj) -> None:
    """Existe só para ser recusada: gravar state/plan cru é proibido (o teste confere a recusa)."""
    raise RedactionRefused("gravação de state/plan cru recusada: passe pelo redator (redact_tf) primeiro")


def find_raw_tf_artifacts(roots) -> list[str]:
    """Varre diretórios persistentes atrás de state/plan cru (terraform.tfstate, *.tfplan, JSON de state sem
    selo, crash.log). Devolve caminhos relativos ao root achado; usado no preflight e no teste."""
    hits = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            n = p.name
            if n.endswith((".tfstate", ".tfstate.backup", ".tfplan")) or n in ("crash.log", "terraform.tfplan"):
                hits.append(str(p.relative_to(root)))
                continue
            if p.suffix in (".json", ".jsonl") and p.stat().st_size < 64 * 1024 * 1024:
                try:
                    head = p.read_text(encoding="utf-8", errors="replace")[:4096]
                except OSError:
                    continue
                if RAW_STATE_MARK.search(head) and SCHEMA not in head:
                    hits.append(str(p.relative_to(root)))
    return sorted(hits)
