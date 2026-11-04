"""Caminhos, hora (America/Recife), hashes e leitura do pacote do PILOT-STO-GLOSS (somente leitura)."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "PILOT-STO-MAP"
SLICE = "sto"
DOMAIN = "STO"
TZ = ZoneInfo("America/Recife")
MODEL_ID = "claude-opus-5-5"
MAPPING_SET_ID = f"https://w3id.org/brevops/mapping/{MODULE}/1"

# Orientação canônica de cada par (MAPPER_BRIEF M1): sujeito = primeiro provedor do ID do par.
PAIRS: tuple[tuple[str, str, str], ...] = (
    ("AWSGCP", "aws", "google"),
    ("AWSAZ", "aws", "azurerm"),
    ("AWSOCI", "aws", "oci"),
    ("GCPAZ", "google", "azurerm"),
    ("GCPOCI", "google", "oci"),
    ("AZOCI", "azurerm", "oci"),
)
PAIR_SIDES = {p: (a, b) for p, a, b in PAIRS}

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

BUNDLE_FILES = ("candidates.jsonl", "canonical_atoms.jsonl", "canonical_units.jsonl", "claims.jsonl",
                "decisions.jsonl", "glossary.jsonl", "value_space.jsonl")
OUTPUTS = ("mapping.sssom.tsv", "verdicts.jsonl")
STAGED = ("mapping.sssom.tsv", "build_record.json", "verdicts.jsonl", "cycles.jsonl", "arbiter_report.json",
          "run_record.json", "pipeline_report.json")


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def emit(msg: str) -> None:
    print(msg, flush=True)


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def out_dir() -> Path:
    return data_root() / MODULE


def staging_dir() -> Path:
    return out_dir() / ".staging"


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or data_root() / "tmp" / MODULE)
    p.mkdir(parents=True, exist_ok=True)
    return p


def bundle_dir() -> Path:
    return data_root() / "PILOT-STO-GLOSS" / "bundle"


def results_dir() -> Path:
    return repo() / "results" / MODULE


def mapper_brief() -> Path:
    return repo() / "briefs" / "MAPPER_BRIEF.txt"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def provider_of(atom_id: str) -> str:
    return atom_id.split(":", 1)[0]


class BundleError(RuntimeError):
    """Pacote ausente, incompleto ou com MANIFEST que não confere: nada é mapeado."""


@dataclass
class Bundle:
    """O pacote fechado do glossarista (MAPPER_BRIEF M11), lido e conferido pelo MANIFEST.sha256."""
    path: Path
    hashes: dict[str, str]
    atoms: dict[str, dict]
    value_space: dict[str, dict]
    anchors: dict[str, dict]            # átomo -> âncora corrente (C20 claims.jsonl)
    concepts: dict[str, dict]
    decisions: list[dict]
    candidates: list[dict]
    units: dict[str, dict]
    manifest_sha256: str = ""
    by_provider: dict[str, list[str]] = field(default_factory=dict)

    @property
    def sha256(self) -> str:
        """Identidade do pacote: sha256 do MANIFEST.sha256 (que lista o sha256 de cada arquivo)."""
        return self.manifest_sha256

    def concept_of(self, atom_id: str) -> str:
        a = self.anchors.get(atom_id)
        return a["concept_id"] if a else "bo:UNGLOSSED"


def load_bundle(path: Path | None = None) -> Bundle:
    d = Path(path or bundle_dir())
    man = d / "MANIFEST.sha256"
    if not man.is_file():
        raise BundleError(f"pacote sem MANIFEST.sha256: {d}")
    listed = {}
    for line in man.read_text(encoding="utf-8").splitlines():
        if line.strip():
            h, rel = line.split("  ", 1)
            listed[rel.strip()] = h
    missing = [f for f in BUNDLE_FILES if f not in listed]
    if missing:
        raise BundleError(f"MANIFEST do pacote não lista {missing}")
    bad = [f for f in BUNDLE_FILES if not (d / f).is_file() or sha256_file(d / f) != listed[f]]
    if bad:
        raise BundleError(f"arquivo(s) do pacote não conferem com o MANIFEST: {bad}")
    atoms = {a["atom_id"]: a for a in load_jsonl(d / "canonical_atoms.jsonl")}
    vs = {v["atom_id"]: v for v in load_jsonl(d / "value_space.jsonl")}
    claims = load_jsonl(d / "claims.jsonl")
    replaced = {c.get("supersedes") for c in claims if c.get("supersedes")}
    anchors = {}
    for c in sorted(claims, key=lambda c: c["claim_version_id"]):
        if c["claim_version_id"] in replaced or c.get("anchor_kind", "atom") != "atom":
            continue
        anchors[c["atom_id"]] = c
    by_p: dict[str, list[str]] = {}
    for a in sorted(atoms):
        by_p.setdefault(provider_of(a), []).append(a)
    return Bundle(path=d, hashes={f: listed[f] for f in BUNDLE_FILES}, atoms=atoms, value_space=vs,
                  anchors=anchors, concepts={c["concept_id"]: c for c in load_jsonl(d / "glossary.jsonl")},
                  decisions=load_jsonl(d / "decisions.jsonl"), candidates=load_jsonl(d / "candidates.jsonl"),
                  units={u["unit_id"]: u for u in load_jsonl(d / "canonical_units.jsonl")},
                  manifest_sha256=sha256_file(man), by_provider=by_p)


def run_main(fn) -> None:
    try:
        sys.exit(fn())
    except BundleError as e:
        emit(f"[{now()}] {MODULE}: {e}")
        sys.exit(2)
