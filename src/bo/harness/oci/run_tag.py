"""Inserção declarada HI-OCI-01: freeform_tags["bo-run"] = var.bo_ctx_run_tag nos tipos que o SAFETY rastreia por tag.

  python -I -m bo.harness.oci.run_tag --check     a lista gravada bate com a tabela de SKUs do SAFETY
  python -I -m bo.harness.oci.run_tag --write     regrava a lista a partir da tabela

Desde a emenda 1.2.0 do C26 (C26-NOTAG) o plano de lowering não traz tag de execução: quem marca a execução é o
harness, como o AWS (default_tags) e o Google (HI-GCP-01). O plan_guard do SAFETY (PG-TAG) exige
freeform_tags["bo-run"] = run_tag em todo tipo com trace = tag, e o C16 só aceita chaves ^bo-[a-z-]+$.
O renderizador põe a chave só nos recursos (nunca em data source) dos tipos de
deploy/fixtures/oci/_templates/run_tag.json, tirados de deploy/safety/allowlist_skus.yaml
(providers.oci.types[*].trace == "tag", tag_attribute "freeform_tags"), sempre como var.bo_ctx_run_tag (chave de
contexto run_tag, sem default; o valor vem do contexto da execução). Plano que já traga freeform_tags com a chave
bo-run, ou freeform_tags inteiro (sem espaço para a chave declarada), reprova como CONFLICTING_VALUES.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import MODULE_ID, PROVIDER, repo_root, templates_dir

INSERTION_ID = "HI-OCI-01"
ATTRIBUTE = "freeform_tags"
TAG_KEY = "bo-run"
BINDING_KEY = "run_tag"
SAFETY_TABLE = Path("deploy") / "safety" / "allowlist_skus.yaml"


def path() -> Path:
    return templates_dir() / "run_tag.json"


@functools.lru_cache(maxsize=4)
def _load(p: str) -> dict:
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    want = (INSERTION_ID, ATTRIBUTE, TAG_KEY, BINDING_KEY)
    if (d.get("insertion_id"), d.get("attribute"), d.get("tag_key"), d.get("binding_key")) != want:
        raise SystemExit(f"{p}: inserção declarada diferente de {INSERTION_ID} {ATTRIBUTE}[{TAG_KEY!r}]")
    return d


def declared() -> dict:
    return _load(str(path()))


def types() -> frozenset:
    return frozenset(declared()["types"])


def from_safety_table(table: Path | None = None) -> list[str]:
    import yaml
    t = table or repo_root() / SAFETY_TABLE
    g = yaml.safe_load(t.read_text(encoding="utf-8"))["providers"][PROVIDER]
    if g.get("tag_attribute") != ATTRIBUTE:
        raise SystemExit(f"{t}: tag_attribute do oci = {g.get('tag_attribute')!r}, esperado {ATTRIBUTE!r}")
    return sorted(n for n, e in g["types"].items() if e.get("trace") == "tag")


def document(types_: list[str], table: Path) -> dict:
    return {"schema": "bo.harness.oci.run_tag/1", "module": MODULE_ID, "insertion_id": INSERTION_ID,
            "attribute": ATTRIBUTE, "tag_key": TAG_KEY, "binding_key": BINDING_KEY,
            "value": "var.bo_ctx_run_tag (chave de contexto run_tag, sem default; valor do contexto da execução)",
            "source": {"path": str(SAFETY_TABLE), "sha256_at_write": hashlib.sha256(table.read_bytes()).hexdigest(),
                       "rule": "providers.oci.types[*].trace == 'tag' (tag_attribute 'freeform_tags')"},
            "types": types_}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.oci.run_tag", description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(timezone(timedelta(hours=-3))).replace(microsecond=0).isoformat()
    table = repo_root() / SAFETY_TABLE
    want = from_safety_table(table)
    if a.write:
        path().write_text(json.dumps(document(want, table), ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")
        print(f"[{now}] run_tag: {len(want)} tipo(s) gravados em {path()}")
        return 0
    got = sorted(declared()["types"])
    if got != want:
        print(f"[{now}] run_tag: lista gravada difere da tabela do SAFETY; só na lista {sorted(set(got) - set(want))}, "
              f"só na tabela {sorted(set(want) - set(got))}")
        return 1
    print(f"[{now}] run_tag: {len(got)} tipo(s), iguais à tabela do SAFETY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
