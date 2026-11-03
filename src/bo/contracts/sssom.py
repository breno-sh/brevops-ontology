"""I/O do C09 (*.sssom.tsv). Delega ao bo.semantics.sssom_io as colunas da teoria e preserva as colunas que o
C09 3.0.0 acrescenta (alternative_to, exclusivity, supersedes, inverse_of) e os slots padrão do SSSOM.

Por quê: o sssom-py 0.4.22 descarta slots de extensão em silêncio, e o bo.semantics.sssom_io.write_tsv só escreve
as colunas que a teoria conhece. Para registros só com essas colunas, write_tsv daqui produz os mesmos bytes que o
do SEMANTICS (teste em tests/contracts)."""

from __future__ import annotations

import csv
import io
import json

import yaml

from bo.semantics import claims as SC
from bo.semantics import sssom_io as SIO

from .spec_b import SSSOM_SLOTS

EXTRA = ("alternative_to", "exclusivity", "supersedes", "inverse_of", "absence", "disputes")
EXTRA_JSON = ("alternative_to", "absence", "disputes")
NUMERIC = ("confidence", "similarity_score", "reviewer_agreement")
CORE = SC.CORE
EXT = SC.EXT + EXTRA


def decode(row: dict) -> dict:
    out = SC.from_row({k: v for k, v in row.items() if k in SC.FIELDS})
    for k, v in row.items():
        if k in SC.FIELDS or v is None or v == "":
            continue
        if k in EXTRA_JSON:
            v = json.loads(v)
        elif k in NUMERIC:
            v = float(v)
        out[k] = v
    return out


def encode(rec: dict) -> dict:
    out = SC.to_row(rec)
    for k in EXTRA + SSSOM_SLOTS:
        if k in rec and rec[k] is not None:
            v = rec[k]
            out[k] = json.dumps(v, ensure_ascii=False, sort_keys=True) if k in EXTRA_JSON else str(v)
    return out


def read_tsv(text: str) -> tuple[dict, list[dict], list[str]]:
    meta_lines, body = [], []
    for line in text.splitlines(keepends=True):
        (meta_lines if line.startswith("#") else body).append(line)
    meta = yaml.safe_load("".join(l[2:] if l.startswith("# ") else l[1:] for l in meta_lines)) or {}
    if not isinstance(meta, dict):
        raise ValueError("cabeçalho YAML do SSSOM não é um mapa")
    rd = csv.DictReader(io.StringIO("".join(body)), delimiter="\t")
    rows = list(rd)
    cols = list(rd.fieldnames or [])
    return meta, [decode(dict(r)) for r in rows], cols


def write_tsv(records: list[dict], mapping_set_id: str, prefixes: dict | None = None) -> str:
    prefixes = dict(prefixes or SIO.PREFIXES)
    rows = [encode(r) for r in records]
    order = CORE + EXT + tuple(s for s in SSSOM_SLOTS)
    cols = [c for c in order if any(c in r for r in rows)]
    ext = [c for c in cols if c in EXT]
    meta = {"curie_map": prefixes, "mapping_set_id": mapping_set_id, "license": SIO.LICENSE,
            "extension_definitions": [{"slot_name": s, "property": SIO.slot_property(s), "type_hint": SIO.XSD_STRING}
                                      for s in ext]}
    head = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True, default_flow_style=False)
    buf = io.StringIO()
    buf.write("".join(f"# {line}\n" for line in head.splitlines()))
    w = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    return buf.getvalue()
