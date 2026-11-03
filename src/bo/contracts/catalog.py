"""Catálogo dos contratos C00–C29: gera os schemas (Python → JSON), resolve aliases e monta o registro de
referências para o jsonschema (todo $ref entre contratos resolve localmente, sem rede)."""

from __future__ import annotations

import fnmatch
import functools
import json
from dataclasses import dataclass
from pathlib import Path

from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from . import _base, spec_a, spec_b, spec_c, spec_d

SPECS = {**spec_a.SPECS, **spec_b.SPECS, **spec_c.SPECS, **spec_d.SPECS}
NAMES = {"C00": "conventions", "C01": "atoms", "C02": "types", "C03": "docs_facts", "C04": "roles",
         "C05": "value_space", "C06": "symbolic_config", "C07": "universe", "C08": "candidates",
         "C09": "correspondences", "C10": "transforms", "C11": "cases", "C12": "readback_outcomes",
         "C13": "versions", "C14": "ontology_tables", "C15": "results", "C16": "run_manifest",
         "C17": "manifest_receipt", "C18": "numbers", "C19": "canonical_units", "C20": "glossary",
         "C21": "verdicts", "C22": "probes", "C23": "translation_trace", "C24": "requirements",
         "C25": "service_evidence", "C26": "graph_ir", "C27": "split", "C28": "comparators",
         "C29": "domain_contracts"}
assert set(SPECS) == set(NAMES) == {f"C{i:02d}" for i in range(30)}


def schema_filename(cid: str) -> str:
    return f"{cid}_{NAMES[cid]}.schema.json"


@functools.lru_cache(maxsize=None)
def generated() -> dict:
    """{cid: schema} gerados do código (o que build grava)."""
    out = {}
    for cid in sorted(SPECS):
        s = SPECS[cid]()
        assert s["x-bo-contract"]["id"] == cid and s["x-bo-contract"]["name"] == NAMES[cid], cid
        out[cid] = json.loads(json.dumps(s))   # cópia limpa, só tipos JSON
    return out


@functools.lru_cache(maxsize=None)
def published(root: str | None = None) -> dict:
    """{cid: schema} lidos de $BO_REPO/contracts/ (o que o validador usa)."""
    d = Path(root) if root else _base.contracts_dir()
    out = {}
    for cid in NAMES:
        p = d / schema_filename(cid)
        if not p.is_file():
            raise FileNotFoundError(f"schema publicado ausente: {p} (rode python -I -m bo.contracts.build)")
        out[cid] = json.loads(p.read_text(encoding="utf-8"))
    return out


def schemas(source: str = "published") -> dict:
    return published() if source == "published" else generated()


def registry(sch: dict) -> Registry:
    return Registry().with_resources([(s["$id"], Resource.from_contents(s, default_specification=DRAFT202012))
                                      for s in sch.values()])


@dataclass(frozen=True)
class FileKind:
    cid: str
    kind: str
    file: str
    format: str
    record: str | None
    unit: str

    @property
    def ref(self) -> str | None:
        if not self.record:
            return None
        return f"{_base.schema_uri(self.cid, NAMES[self.cid])}#/$defs/{self.record}"


def file_kinds(sch: dict | None = None) -> list[FileKind]:
    sch = sch or schemas()
    out = []
    for cid, s in sorted(sch.items()):
        for f in s["x-bo-contract"]["files"]:
            out.append(FileKind(cid, f["kind"], f["file"], f["format"], f["record"], f["unit"]))
    return out


def _norm(s: str) -> str:
    return s.strip().lower().replace("-", "_")


def _by_filename(cands: list[FileKind], path: Path) -> FileKind | None:
    """Primeiro tipo (na ordem declarada) cujo padrão casa com o nome do arquivo ou com pasta/nome."""
    name, rel = path.name, "/".join(path.parts[-2:])
    for k in cands:
        if fnmatch.fnmatchcase(name, k.file) or fnmatch.fnmatchcase(rel, k.file):
            return k
    return None


def resolve(alias: str, path: Path | None = None, sch: dict | None = None) -> FileKind:
    """alias: Cnn | Cnn_<nome> | <nome do contrato> | <tipo de arquivo> | Cnn_<tipo de arquivo>. Contrato com vários
    arquivos: escolhe pelo nome do arquivo (padrão do x-bo-contract), na ordem declarada."""
    kinds = file_kinds(sch)
    a = _norm(alias)
    by_kind = [k for k in kinds if _norm(k.kind) == a or _norm(f"{k.cid}_{k.kind}") == a]
    named = [c for c, n in NAMES.items() if a == _norm(n)]
    if by_kind and named and path is not None:
        # alias = nome do contrato E tipo homônimo (ex.: versions, glossary): escolhe pelo nome do arquivo entre os
        # tipos do contrato; o tipo homônimo só vale quando nenhum padrão de arquivo do contrato casa (emenda 3.1.0)
        hit = _by_filename([k for k in kinds if k.cid == named[0]], path)
        if hit is not None:
            return hit
    if by_kind:
        if len(by_kind) == 1:
            return by_kind[0]
        cands = by_kind
    else:
        cid = None
        for c, n in NAMES.items():
            if a in (_norm(c), _norm(n), _norm(f"{c}_{n}")):
                cid = c
        if cid is None:
            raise KeyError(f"contrato ou tipo de arquivo desconhecido: {alias!r}")
        cands = [k for k in kinds if k.cid == cid]
    if len(cands) == 1:
        return cands[0]
    if path is None:
        raise KeyError(f"{alias}: contrato com vários arquivos ({', '.join(k.kind for k in cands)}); diga o tipo")
    hit = _by_filename(cands, path)
    if hit is not None:
        return hit
    raise KeyError(f"{alias}: {name} não casa com nenhum arquivo do contrato ({', '.join(k.file for k in cands)})")
