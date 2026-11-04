"""Inserção declarada HI-GCP-01: rótulo bo-run da execução nos tipos que o SAFETY rastreia por rótulo.

  python -I -m bo.harness.google.run_label --check     a lista gravada bate com a tabela de SKUs do SAFETY
  python -I -m bo.harness.google.run_label --write     regrava a lista a partir da tabela

O plan_guard do SAFETY (PG-TAG) exige labels["bo-run"] = run_tag em todo tipo com trace = tag, e o C16 só aceita
chaves ^bo-[a-z-]+$. O plano de lowering não traz esse rótulo (é da execução, não do caso), então o renderizador
o põe como inserção DECLARADA: só nos tipos de deploy/fixtures/google/_templates/run_label.json (tirados da
tabela deploy/safety/allowlist_skus.yaml, providers.google.types[*].trace == "tag", tag_attribute "labels"), só
em recurso (nunca em data source), sempre como variável '<plano>_bo_run' SEM default, ligada pelo executor.
Tipo da tabela sem 'labels' configurável no schema fixado é defeito da lista: o renderizador reprova o caso.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path

from . import common as C

INSERTION_ID = "HI-GCP-01"
LABEL_KEY = "bo-run"
ATTRIBUTE = "labels"
VAR_SUFFIX = "bo_run"
SAFETY_TABLE = Path("deploy") / "safety" / "allowlist_skus.yaml"


def path() -> Path:
    return C.templates() / "run_label.json"


@functools.lru_cache(maxsize=4)
def _load(p: str) -> dict:
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    if (d.get("insertion_id"), d.get("label_key"), d.get("attribute")) != (INSERTION_ID, LABEL_KEY, ATTRIBUTE):
        raise SystemExit(f"{p}: inserção declarada diferente de {INSERTION_ID} {ATTRIBUTE}[{LABEL_KEY!r}]")
    return d


def declared() -> dict:
    return _load(str(path()))


def types() -> frozenset:
    return frozenset(declared()["types"])


def var_name(plan_slug: str) -> str:
    return f"{plan_slug}_{VAR_SUFFIX}"


def from_safety_table(table: Path | None = None) -> list[str]:
    import yaml
    t = table or C.repo() / SAFETY_TABLE
    g = yaml.safe_load(t.read_text(encoding="utf-8"))["providers"][C.PROVIDER]
    if g.get("tag_attribute") != ATTRIBUTE:
        raise SystemExit(f"{t}: tag_attribute do google = {g.get('tag_attribute')!r}, esperado {ATTRIBUTE!r}")
    return sorted(n for n, e in g["types"].items() if e.get("trace") == "tag")


def document(types_: list[str], table: Path) -> dict:
    return {"schema": "bo.harness_google.run_label/1", "module": C.MODULE, "insertion_id": INSERTION_ID,
            "attribute": ATTRIBUTE, "label_key": LABEL_KEY,
            "value": "variável '<plano>_bo_run' sem default; o executor liga o run_tag da execução "
                     "(tag_value(batch_id) do SAFETY)",
            "source": {"path": str(SAFETY_TABLE), "sha256_at_write": C.sha256_file(table),
                       "rule": "providers.google.types[*].trace == 'tag' (tag_attribute 'labels')"},
            "types": types_}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.google.run_label", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    table = C.repo() / SAFETY_TABLE
    want = from_safety_table(table)
    if a.write:
        path().write_text(C.dump(document(want, table)), encoding="utf-8")
        print(f"[{C.now()}] run_label: {len(want)} tipo(s) gravados em {path()}")
        return 0
    got = sorted(declared()["types"])
    if got != want:
        print(f"[{C.now()}] run_label: lista gravada difere da tabela do SAFETY; "
              f"só na lista {sorted(set(got) - set(want))}, só na tabela {sorted(set(want) - set(got))}")
        return 1
    print(f"[{C.now()}] run_label: {len(got)} tipo(s), iguais à tabela do SAFETY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
