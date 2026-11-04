"""Catálogo de CQs que o CQFIX instancia: as 29 do REQUIREMENTS (cq_spec.jsonl) mais as 8 CIS (cis_spec)."""
from __future__ import annotations

import json
from functools import lru_cache

from . import VARIANTS, repo_root
from . import cis_spec


@lru_cache(maxsize=1)
def beyond_cis() -> tuple:
    p = repo_root() / "requirements" / "cq_spec.jsonl"
    with open(p, encoding="utf-8") as f:
        return tuple(json.loads(ln) for ln in f if ln.strip())


@lru_cache(maxsize=1)
def catalog() -> tuple:
    """Todas as CQs (registros C24), CIS primeiro, depois as do REQUIREMENTS na ordem do arquivo."""
    return tuple(cis_spec.records()) + beyond_cis()


def by_id() -> dict:
    return {q["cq_id"]: q for q in catalog()}


def source_of(q: dict) -> str:
    return "results/CQFIX/cq_spec_cis.jsonl" if q["family"] == "cis" else "requirements/cq_spec.jsonl"


def fixture(q: dict, variant: str) -> dict:
    return q["fixtures"][variant]["fixture"]


def expected(q: dict, variant: str) -> dict:
    return q["fixtures"][variant]["expected"]


def entity_ids(q: dict, variant: str) -> list[str]:
    return [e["id"] for e in fixture(q, variant)["entities"]]


def attrs(q: dict, variant: str) -> dict:
    """{(of, attr): value} da fixture abstrata."""
    return {(a["of"], a["attr"]): a["value"] for a in fixture(q, variant)["attributes"]}


assert VARIANTS == ("conforming", "nonconforming", "incomplete")
