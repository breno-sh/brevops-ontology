"""Leitura dos formatos de troca. Cada leitor devolve (registros, contexto): registros = [(onde, objeto)] para
validar no schema; contexto = o que as regras semânticas precisam (metadados SSSOM, grafo RDF, linhas…).
Nada é executado: YAML com safe_load, XML/RDF com rdflib, Parquet com pyarrow."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


class FormatError(Exception):
    pass


def _jsonl(path: Path):
    recs = []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise FormatError("arquivo vazio")
    if not text.endswith("\n"):
        raise FormatError("JSONL sem quebra de linha final")
    for n, line in enumerate(text.split("\n")[:-1], 1):
        if not line.strip():
            raise FormatError(f"linha {n} em branco")
        try:
            recs.append((f"linha {n}", json.loads(line)))
        except json.JSONDecodeError as e:
            raise FormatError(f"linha {n}: JSON inválido: {e.msg}") from None
    return recs, {}


def _json(path: Path):
    try:
        return [("documento", json.loads(path.read_text(encoding="utf-8")))], {}
    except json.JSONDecodeError as e:
        raise FormatError(f"JSON inválido: {e.msg} (linha {e.lineno})") from None


def _yaml(path: Path):
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise FormatError(f"YAML inválido: {str(e)[:200]}") from None
    if doc is None:
        raise FormatError("YAML vazio")
    return [("documento", json.loads(json.dumps(doc, default=str)))], {}


def _sssom(path: Path):
    from .sssom import read_tsv
    try:
        meta, recs, cols = read_tsv(path.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError, yaml.YAMLError) as e:
        raise FormatError(f"SSSOM TSV ilegível: {str(e)[:200]}") from None
    if not recs:
        raise FormatError("SSSOM TSV sem linhas")
    return [(f"linha {i + 1} ({r.get('claim_id', '?')})", r) for i, r in enumerate(recs)], {"meta": meta, "columns": cols}


def _parquet(path: Path):
    import pyarrow.parquet as pq
    try:
        t = pq.read_table(path)
    except Exception as e:  # pyarrow levanta tipos variados para arquivo corrompido
        raise FormatError(f"Parquet ilegível: {str(e)[:200]}") from None
    rows = t.to_pylist()
    if not rows:
        raise FormatError("Parquet sem linhas")
    types = {f.name: str(f.type) for f in t.schema}
    return [(f"linha {i + 1}", r) for i, r in enumerate(rows)], {"arrow_types": types}


def _turtle(path: Path):
    """Turtle com o fecho dos owl:imports locais (o que se confere é o fecho, como no ONTPAT)."""
    import rdflib
    from rdflib.namespace import OWL
    g = rdflib.Graph()
    try:
        g.parse(path, format="turtle")
    except Exception as e:  # rdflib levanta BadSyntax e afins
        raise FormatError(f"Turtle inválido: {str(e)[:200]}") from None
    notes = []
    if any(True for _ in g.objects(None, OWL.imports)):
        from bo.ontpat import common as OC
        try:
            g, seen = OC.load_closure(path)
            notes.append(f"conferido no fecho de imports ({len(seen)} arquivo(s))")
        except FileNotFoundError as e:
            notes.append(f"fecho incompleto, conferido só o arquivo: {str(e)[:160]}")
        except Exception as e:  # import local com sintaxe inválida
            raise FormatError(f"import do fecho inválido: {str(e)[:200]}") from None
    return [], {"graph": g, "notes": notes}


def _edoal(path: Path):
    ctx = _turtle(path)[1]
    from bo.semantics import edoal
    try:
        recs, groups = edoal.reimport(ctx["graph"])
    except Exception as e:  # reimport falha com KeyError/TypeError em célula malformada
        raise FormatError(f"EDOAL fora do subconjunto: {type(e).__name__}: {str(e)[:150]}") from None
    if not recs:
        raise FormatError("EDOAL sem células")
    ctx.update({"records": recs, "groups": groups})
    return [], ctx


SHA_LINE = re.compile(r"^([0-9a-f]{64})  (\S.*)$")


def _manifest(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise FormatError("manifesto vazio")
    return [], {"lines": lines}


MACRO = re.compile(r"^\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}$")


def _tex(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not any(l.strip() and not l.lstrip().startswith("%") for l in lines):
        raise FormatError("numbers.tex sem macros")
    return [], {"lines": lines}


READERS = {"jsonl": _jsonl, "json": _json, "yaml": _yaml, "sssom_tsv": _sssom, "parquet": _parquet,
           "turtle": _turtle, "edoal_ttl": _edoal, "sha256_manifest": _manifest, "tex_macros": _tex}


def read(fmt: str, path: Path):
    if fmt not in READERS:
        raise FormatError(f"formato sem leitor: {fmt}")
    if not path.is_file():
        raise FormatError(f"arquivo não existe: {path}")
    return READERS[fmt](path)
