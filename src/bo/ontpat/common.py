"""Caminhos, espaços de nome e leitura do fecho de imports (sem rede, sem catálogo)."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import rdflib
from rdflib.namespace import OWL, RDF, RDFS
from urllib.parse import unquote, urlparse

TZ = ZoneInfo("America/Recife")
BO = rdflib.Namespace("https://w3id.org/brevops/ontology#")
PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
UNIT = rdflib.Namespace("http://qudt.org/vocab/unit/")
EXV = rdflib.Namespace("https://example.org/bo-example/vocab#")
EX = rdflib.Namespace("https://example.org/bo-example/abox#")

PRED_RIGID = BO.rigidity
RIGID, ANTI, SEMI = BO.Rigid, BO.AntiRigid, BO.SemiRigid


def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or data_dir() / "tmp" / "ONTPAT")
    p.mkdir(parents=True, exist_ok=True)
    return p


def patterns_dir() -> Path:
    return repo() / "ontology" / "patterns"


def results_dir() -> Path:
    p = repo() / "results" / "ONTPAT"
    p.mkdir(parents=True, exist_ok=True)
    return p


def content_dir() -> Path:
    return Path(__file__).resolve().parent / "content"


PATTERNS = "bo-patterns.ttl"
DESCRIPTOR = "descriptor-pattern.ttl"
EXAMPLE = "example-abox.ttl"
CANDIDATES = ("bfo", "dul", "gufo", "none")


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def read_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def parse(path: Path, g: rdflib.Graph | None = None) -> rdflib.Graph:
    g = g if g is not None else rdflib.Graph()
    g.parse(str(path), format="turtle", publicID=Path(path).resolve().as_uri())
    return g


def load_closure(path: Path, follow_external: bool = False) -> tuple[rdflib.Graph, list[Path]]:
    """Carrega o arquivo e o fecho dos owl:imports que resolvem para arquivo local (file:).

    Import para IRI http(s) não é buscado (sem rede): é devolvido como erro, para o chamador decidir.
    """
    g = rdflib.Graph()
    seen: list[Path] = []
    todo = [Path(path).resolve()]
    missing = []
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        if not p.exists():
            missing.append(str(p))
            continue
        seen.append(p)
        sub = parse(p)
        for o in sub.objects(None, OWL.imports):
            s = str(o)
            if s.startswith("file:"):
                todo.append(Path(unquote(urlparse(s).path)))
            elif not follow_external:
                missing.append(s)
        g += sub
    if missing:
        raise FileNotFoundError("imports não resolvidos localmente: " + ", ".join(missing))
    return g, seen


def named_classes(g: rdflib.Graph) -> set:
    return {c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, rdflib.URIRef)}


def emit(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr, flush=True)
    sys.exit(code)
