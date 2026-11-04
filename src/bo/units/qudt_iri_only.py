"""Gate: toda unidade e grandeza do value_space é IRI QUDT, NOT_APPLICABLE ou UNKNOWN; nada de texto livre.

  python -I -m bo.units.qudt_iri_only [value_space.jsonl]

Confere, registro a registro:
  - quantity_kind e unit_qudt são CURIE/IRI do QUDT ou um dos dois marcadores, na forma exata;
  - o IRI existe no QUDT fixado (3.5.3, sha256 conferido), não é obsoleto, e a unidade serve à grandeza segundo o
    próprio QUDT (hasQuantityKind | unitForQuantityKind | applicableUnit);
  - a unidade está no registro fechado do TRANSFORMS (bo.transforms.units), para que toda conversão seja definida;
  - NOT_APPLICABLE ≠ UNKNOWN: NOT_APPLICABLE só junto (grandeza e unidade), UNKNOWN de grandeza só com unidade UNKNOWN;
  - nenhum outro campo do registro carrega unidade em texto livre (formato e nota não são unidade: o formato vem de
    vocabulário fechado).
Sai 0 só com zero erro; imprime as contagens.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from bo.transforms import units as tu

from . import qudt
from .build import out_dir
from .rules import FORMATS

ALLOWED_FORMATS = set(FORMATS.values()) | {"go_duration", "protobuf_duration", "iso8601_duration", "unix_epoch"}


def check_record(r: dict) -> list[str]:
    errs = []
    qk, un = r.get("quantity_kind"), r.get("unit_qudt")
    if not isinstance(qk, str) or not isinstance(un, str):
        return ["grandeza ou unidade ausente ou não textual"]
    errs += qudt.check_pair(qk, un)
    if un not in qudt.MARKERS and un not in tu.UNITS:
        errs.append(f"unidade {un} fora do registro do TRANSFORMS (conversão indefinida)")
    if (qk == "NOT_APPLICABLE") != (un == "NOT_APPLICABLE"):
        errs.append("NOT_APPLICABLE só nas duas (grandeza e unidade) ou em nenhuma")
    f = r.get("format")
    if f is not None and f not in ALLOWED_FORMATS:
        errs.append(f"formato fora do vocabulário fechado: {f!r}")
    return errs


def run(path: Path) -> tuple[int, Counter, list[str]]:
    errs, c = [], Counter()
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            r = json.loads(line)
            c["records"] += 1
            e = check_record(r)
            for x in e:
                errs.append(f"{path.name}:{i} {r.get('atom_id')}: {x}")
            qk, un = r["quantity_kind"], r["unit_qudt"]
            c["unit_iri" if un not in qudt.MARKERS else f"unit_{un}"] += 1
            c["qk_iri" if qk not in qudt.MARKERS else f"qk_{qk}"] += 1
    return len(errs), c, errs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    path = Path(argv[0]) if argv else out_dir() / "value_space.jsonl"
    ferr = qudt.verify_files()
    if ferr:
        print("REPROVADO: " + "; ".join(ferr))
        return 1
    if not path.exists():
        print(f"REPROVADO: {path} não existe")
        return 1
    n, c, errs = run(path)
    for e in errs[:40]:
        print("  " + e)
    print(f"qudt_iri_only: {c['records']} registros; unidade IRI {c['unit_iri']}, UNKNOWN {c['unit_UNKNOWN']}, "
          f"NOT_APPLICABLE {c['unit_NOT_APPLICABLE']}; grandeza IRI {c['qk_iri']}, UNKNOWN {c['qk_UNKNOWN']}, "
          f"NOT_APPLICABLE {c['qk_NOT_APPLICABLE']}; QUDT {qudt.QUDT_VERSION}; {n} erro(s)")
    if c["records"] == 0:
        print("REPROVADO: value_space vazio")
        return 1
    return 0 if n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
