"""Caminhos, pins, fontes fixadas, redação, resolução de citação e ids do SERVICE-EVIDENCE.

Duas fontes PUBLICADAS, ambas fixadas no pin do provedor (universe/pins.json, C13):
  doc     website/docs/ do repositório do provedor na tag v<versão> (cópia conferida pelos DOCS-*), citada
          por doc_source (repo, tag, file, line, sentence). Resolver = a frase (depois da mesma redação) aparece
          no texto do arquivo começando na linha citada (quebras de linha do markdown viram espaço).
  schema  saída de `terraform providers schema -json` do binário assinado do pin (sha256 = schema_sha256 do
          pin), citada por web_citation: uri = pacote assinado publicado, section = "providers-schema sha256 <h>
          <op> <json-pointer>", sentence = JSON canônico do nó (op=node) ou da lista ordenada das chaves do nó
          (op=keys). Resolver = recalcular a partir do arquivo fixado.
Nenhuma outra fonte entra: nada de nuvem, nada de página web fora do pin.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from bo.repo import privacy

MODULE = "SERVICE-EVIDENCE"
MODEL_ID = "claude-opus-5-5"
TZ = ZoneInfo("America/Recife")
PROVIDERS = ("aws", "google", "azurerm", "oci")


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def real(p: str) -> Path:
    return Path(p.replace("$BO_DATA", str(bo_data())).replace("$BO_REPO", str(bo_repo())))


def out_dir() -> Path:
    return bo_data() / MODULE


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------- pins e fontes fixadas

# Por provedor: onde está a cópia conferida da documentação (dado não confiável, só lido como texto), qual
# módulo a conferiu, o commit da tag e a data do commit (copiados do SOURCE.txt de cada DOCS-*; o pinned.py
# confere que o commit e a data estão escritos lá), e o schema do binário assinado.
SRC = {
    "aws": {
        "repo": "hashicorp/terraform-provider-aws",
        "docs_root": "$BO_DATA/downloads/docs-aws/v6.71.0",
        "source_txt": "$BO_DATA/downloads/docs-aws/SOURCE.txt",
        "commit": "d5f4cd8a1d0a8ab528685adba1dfbd4595368e9d",
        "commit_date": "2026-10-28",
        "docs_module": "DOCS-AWS",
        "schema_module": "SCHEMA-AWS",
        "prefetch": "$BO_DATA/downloads/prefetch/aws/{v}",
    },
    "google": {
        "repo": "hashicorp/terraform-provider-google",
        "docs_root": "$BO_DATA/downloads/docs-google",
        "source_txt": "$BO_DATA/downloads/docs-google/SOURCE.txt",
        "commit": "ffc5d7f2c4af44558f1b6a7c66142fac3a7abd80",
        "commit_date": "2026-10-26",
        "docs_module": "DOCS-GCP",
        "schema_module": "SCHEMA-GCP",
        "prefetch": "$BO_DATA/downloads/prefetch/google/{v}",
    },
    "azurerm": {
        "repo": "hashicorp/terraform-provider-azurerm",
        "docs_root": "$BO_DATA/downloads/docs-azurerm/v5.12.0",
        "source_txt": "$BO_DATA/downloads/docs-azurerm/SOURCE.txt",
        "commit": "e4304e154034d27313432fa98dee2184fb6d8519",
        "commit_date": "2026-10-29",
        "docs_module": "DOCS-AZURE",
        "schema_module": "SCHEMA-AZURE",
        "prefetch": "$BO_DATA/downloads/prefetch/azurerm/{v}",
    },
    "oci": {
        "repo": "oracle/terraform-provider-oci",
        "docs_root": "$BO_DATA/downloads/docs-oci",
        "source_txt": "$BO_DATA/downloads/docs-oci/SOURCE.txt",
        "commit": "6015ea78c08f3f71d711d4262fdac8d01271cdaf",
        "commit_date": "2026-10-21",
        "docs_module": "DOCS-OCI",
        "schema_module": "SCHEMA-OCI",
        "prefetch": "$BO_DATA/downloads/prefetch/oci/{v}",
    },
}


@lru_cache(maxsize=1)
def pins() -> dict:
    d = json.loads((bo_repo() / "universe" / "pins.json").read_text(encoding="utf-8"))
    return {p["provider"]: p for p in d["providers"]}


def version(provider: str) -> str:
    return pins()[provider]["version"]


def tag(provider: str) -> str:
    return "v" + version(provider)


def docs_root(provider: str) -> Path:
    return real(SRC[provider]["docs_root"])


def prefetch(provider: str) -> Path:
    return real(SRC[provider]["prefetch"].format(v=version(provider)))


def schema_path(provider: str) -> Path:
    return prefetch(provider) / "providers-schema.json"


@lru_cache(maxsize=4)
def schema_meta(provider: str) -> dict:
    """uri do pacote assinado, data de extração do schema (pré-busca) e sha256 do pin."""
    pf = prefetch(provider)
    ver = json.loads((pf / "verification.json").read_text(encoding="utf-8"))
    man = json.loads((pf / "MANIFEST.json").read_text(encoding="utf-8"))
    return {
        "uri": ver["zip_url"],
        "retrieved_at": man["generated_at_america_recife"],
        "sha256": pins()[provider]["schema_sha256"],
        "source": pins()[provider]["source"],
    }


@lru_cache(maxsize=4)
def schema(provider: str) -> dict:
    p = schema_path(provider)
    got = sha256_file(p)
    want = pins()[provider]["schema_sha256"]
    if got != want:
        raise SystemExit(f"schema de {provider} não é o do pin: {got[:12]} != {want[:12]}")
    d = json.loads(p.read_text(encoding="utf-8"))
    return d["provider_schemas"][schema_meta(provider)["source"]]


def _ptr_escape(s: str) -> str:
    return s.replace("~", "~0").replace("/", "~1")


def schema_pointer(provider: str, *parts: str) -> str:
    return "/provider_schemas/" + _ptr_escape(schema_meta(provider)["source"]) + "".join(
        "/" + _ptr_escape(p) for p in parts)


def schema_node(provider: str, pointer: str):
    pre = "/provider_schemas/" + _ptr_escape(schema_meta(provider)["source"])
    if not pointer.startswith(pre):
        raise KeyError(pointer)
    node = schema(provider)
    for raw in pointer[len(pre):].split("/")[1:]:
        key = raw.replace("~1", "/").replace("~0", "~")
        node = node[key]
    return node


SECTION_RX = re.compile(r"^providers-schema sha256 (?P<sha>[0-9a-f]{64}) (?P<op>node|keys) (?P<ptr>/\S+)$")


def schema_cite(provider: str, pointer: str, op: str = "node") -> dict:
    node = schema_node(provider, pointer)
    sentence = canon(node) if op == "node" else canon(sorted(node.keys()))
    m = schema_meta(provider)
    return {"uri": m["uri"], "retrieved_at": m["retrieved_at"],
            "section": f"providers-schema sha256 {m['sha256']} {op} {pointer}", "sentence": sentence}


# ---------------------------------------------------------------- redação (antes da primeira serialização)

PRIVATE_LISTS = None


def _lists():
    global PRIVATE_LISTS
    if PRIVATE_LISTS is None:
        PRIVATE_LISTS = privacy.load_lists()[0]
    return PRIVATE_LISTS


_ZERO_GUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def redact(text: str) -> tuple[str, bool]:
    """Troca por marcador tudo o que o privacy_lint reprova (as mesmas regras, importadas dele).
    /subscriptions/<guid> vira /subscriptions/{subscriptionId} (convenção do C03-TS-REDACT)."""
    orig = text
    text = re.sub(r"/subscriptions/" + _ZERO_GUID, "/subscriptions/{subscriptionId}", text, flags=re.I)
    for hit in privacy.twelve_digit_hits(text):
        text = re.sub(r"(?<!\d)" + re.escape(hit) + r"(?!\d)", "{redacted:twelve_digits}", text)
    for rule, rx in privacy.RULES:
        if rule == "email":
            text = rx.sub(lambda m: m.group(0) if privacy.ALLOWED_EMAIL_DOMAINS.search(m.group(0))
                          else "{redacted:email}", text)
        elif rule == "money":
            continue  # nenhum valor monetário é citado; se aparecer, o privacy_lint da saída reprova
        else:
            text = rx.sub("{redacted:" + rule + "}", text)
    for rule, rx in privacy._list_regexes(_lists()):
        text = rx.sub("{redacted:" + rule + "}", text)
    return text, text != orig


# ---------------------------------------------------------------- páginas e resolução de frase

@lru_cache(maxsize=4096)
def page_lines(provider: str, rel: str) -> tuple[str, ...]:
    p = docs_root(provider) / rel
    if not p.is_file():
        return ()
    return tuple(p.read_text(encoding="utf-8", errors="replace").splitlines())


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


WINDOW = 80  # linhas seguintes que a frase pode atravessar (parágrafo com quebra manual)


def resolve_doc(provider: str, doc: dict) -> str | None:
    """None se a frase resolve; senão o motivo."""
    if doc.get("repo") != SRC[provider]["repo"]:
        return "repo fora do pin"
    if doc.get("tag") != tag(provider):
        return "tag fora do pin"
    lines = page_lines(provider, doc["file"])
    if not lines:
        return "arquivo ausente na cópia fixada"
    i = doc["line"] - 1
    if i < 0 or i >= len(lines):
        return "linha fora do arquivo"
    first = lines[i]
    window = " ".join(lines[i:i + WINDOW])
    sent = doc["sentence"]
    if doc.get("redacted"):
        first = redact(first)[0]
        window = redact(window)[0]
    nf, nw, ns = norm(first), norm(window), norm(sent)
    pos = nw.find(ns)
    if pos < 0:
        return "frase não está no texto a partir da linha"
    if pos > len(nf):
        return "frase começa depois da linha citada"
    return None


def resolve_schema(provider: str, cit: dict) -> str | None:
    m = SECTION_RX.match(cit.get("section", ""))
    if not m:
        return "section sem ponteiro do schema"
    meta = schema_meta(provider)
    if m["sha"] != meta["sha256"]:
        return "sha256 do schema fora do pin"
    if cit.get("uri") != meta["uri"]:
        return "uri não é o pacote assinado do pin"
    try:
        node = schema_node(provider, m["ptr"])
    except (KeyError, TypeError, IndexError):
        return "ponteiro não existe no schema fixado"
    want = canon(node) if m["op"] == "node" else canon(sorted(node.keys()))
    if want != cit.get("sentence"):
        return "nó do schema difere da frase"
    return None


def doc_cite(provider: str, rel: str, line: int, sentence: str | None = None) -> dict:
    """doc_source da linha (1-based) da página fixada; sem frase, a linha inteira (sem espaços nas pontas)."""
    lines = page_lines(provider, rel)
    raw = sentence if sentence is not None else lines[line - 1].strip()
    sent, red = redact(raw)
    d = {"repo": SRC[provider]["repo"], "tag": tag(provider), "file": rel, "line": line, "sentence": sent}
    if red:
        d["redacted"] = True
    return d


def cite_or_none(provider: str, doc: dict) -> dict | None:
    """Citação que resolve, nesta ordem: a frase como veio do DOCS-*; a mesma frase marcada como redigida
    (o DOCS-* já redigiu o ID); a linha inteira da página fixada com a redação daqui (o DOCS-* tirou markdown,
    juntou linhas ou usou outro marcador de redação). None se nada resolve (o fato não é publicado)."""
    d = dict(doc)
    if resolve_doc(provider, d) is None:
        return d
    d["redacted"] = True
    if resolve_doc(provider, d) is None:
        return d
    lines = page_lines(provider, doc.get("file", ""))
    ln = doc.get("line", 0)
    if doc.get("repo") == SRC[provider]["repo"] and doc.get("tag") == tag(provider) and 1 <= ln <= len(lines) \
            and len(lines[ln - 1].strip()) >= 5:
        d = doc_cite(provider, doc["file"], ln)
        if resolve_doc(provider, d) is None:
            return d
    return None


def find_line(provider: str, rel: str, needle: str, start: int = 0) -> int | None:
    """1-based da primeira linha (a partir de start, 0-based) que contém needle."""
    for i, ln in enumerate(page_lines(provider, rel)[start:], start):
        if needle in ln:
            return i + 1
    return None


def se_id(provider: str, *parts) -> str:
    """Base32 minúsculo (não hex): 12 dígitos seguidos num id hex parecem id de conta para o privacy_lint."""
    d = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return f"SE-{provider}-" + base64.b32encode(d).decode("ascii").lower().rstrip("=")[:16]
