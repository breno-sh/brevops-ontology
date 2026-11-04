"""Caminhos, hora, pares e prefixos do PILOT-NET-MAP."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "PILOT-NET-MAP"
GLOSS = "PILOT-NET-GLOSS"
TZ = ZoneInfo("America/Recife")
MODEL_ID = "claude-opus-5-5"
MAPPING_SET_ID = "https://w3id.org/brevops/mapping/PILOT-NET-MAP/1"

PROVIDERS = ("aws", "google", "azurerm", "oci")
# orientação canônica (MAPPER_BRIEF M1): sujeito = primeiro provedor do ID do par
PAIRS = {
    "AWSGCP": ("aws", "google"),
    "AWSAZ": ("aws", "azurerm"),
    "AWSOCI": ("aws", "oci"),
    "GCPAZ": ("google", "azurerm"),
    "GCPOCI": ("google", "oci"),
    "AZOCI": ("azurerm", "oci"),
}
PREFIXES = {
    "aws": "https://w3id.org/brevops/atom/aws/",
    "google": "https://w3id.org/brevops/atom/google/",
    "azurerm": "https://w3id.org/brevops/atom/azurerm/",
    "oci": "https://w3id.org/brevops/atom/oci/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "semapv": "https://w3id.org/semapv/vocab/",
    "bosx": "https://w3id.org/brevops/sssom-ext#",
    "bo": "https://w3id.org/brevops/ontology#",
    "concept": "https://w3id.org/brevops/glossary#",
    "sssom": "https://w3id.org/sssom/",
}
UNGLOSSED = "bo:UNGLOSSED"
NO_TERM = "sssom:NoTermFound"
PRED = {"exact": "skos:exactMatch", "close": "skos:closeMatch", "broad": "skos:broadMatch",
        "narrow": "skos:narrowMatch", "related": "skos:relatedMatch"}
TRANSPORTING = ("exact", "close", "broad", "narrow")
OUTPUTS = ("mapping.sssom.tsv", "verdicts.jsonl")


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    return Path(env) if env else Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def data_dir() -> Path:
    return data_root() / MODULE


def staging_dir() -> Path:
    return data_dir() / ".staging"


def tmp_dir() -> Path:
    d = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / MODULE))
    d.mkdir(parents=True, exist_ok=True)
    return d


def results_dir() -> Path:
    return repo() / "results" / MODULE


def default_bundle() -> Path:
    return data_root() / GLOSS / "bundle"


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def dump_jsonl(rows) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def emit(msg: str) -> None:
    print(msg, flush=True)


def provider_of(atom_or_type: str) -> str:
    return atom_or_type.split(":", 1)[0]


def type_of(atom_id: str) -> str:
    return atom_id.split(":")[1]


def path_of(atom_id: str) -> str:
    return atom_id.split(":", 2)[2]
