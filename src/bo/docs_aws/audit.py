"""Conferências do DOCS-AWS sobre o que foi gravado.

  python -I -m bo.docs_aws.audit provenance     toda sentença citada (docs_facts e type_subcategory) está no
                                                arquivo:linha da cópia conferida (espaços normalizados; trecho
                                                redigido conta como curinga); sai 1 se alguma não está
  python -I -m bo.docs_aws.audit sample N SEED  amostra estratificada por fact_kind de fatos stated, para a
                                                auditoria manual (imprime atom_id, valor, sentença, arquivo:linha)
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from functools import lru_cache

from bo.docs_aws import build, source

RED = re.compile(r"⟨redigido:[a-z_0-9]+⟩")


@lru_cache(maxsize=4096)
def _lines(rel: str) -> tuple:
    p = source.repo_root_copy() / rel
    return tuple(p.read_text(encoding="utf-8").splitlines())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def sentence_at(src: dict, span: int = 40) -> bool:
    lines = _lines(src["file"])
    i = src["line"] - 1
    if i < 0 or i >= len(lines):
        return False
    window = _norm(" ".join(x.strip() for x in lines[i:i + span]))
    sent = _norm(src["sentence"])
    if src["sentence"].startswith("(") and src["sentence"].endswith(")"):
        sent = sent   # parêntese de marcas: aparece literal no item
    parts = [re.escape(p) for p in RED.split(sent)]
    rx = re.compile(r".{1,400}?".join(parts)) if len(parts) > 1 else None
    if rx is None:
        return sent in window
    return bool(rx.search(window))


def provenance() -> int:
    from bo.repo import core
    bad, n = [], 0
    with open(build.out_dir() / "docs_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if "source" not in r:
                continue
            n += 1
            if not sentence_at(r["source"]):
                bad.append(f"{r['fact_id']} -> {r['source']['file']}:{r['source']['line']}")
    with open(build.out_dir() / "type_subcategory.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            for key in ("subcategory",):
                s = r.get(key, {}).get("source")
                if s:
                    n += 1
                    if not sentence_at(s):
                        bad.append(f"{r['type_id']}.{key} -> {s['file']}:{s['line']}")
            for st in r.get("import", {}).get("statements", []):
                n += 1
                if not sentence_at({"file": r["doc_file"], "line": st["line"], "sentence": st["sentence"]}):
                    bad.append(f"{r['type_id']}.import -> {r['doc_file']}:{st['line']}")
            al = r.get("alias_of")
            if al:
                n += 1
                if not sentence_at(al["source"]):
                    bad.append(f"{r['type_id']}.alias_of")
    core.emit(f"[{core.now()}] proveniência: {n} sentença(s) citada(s), {len(bad)} fora do arquivo:linha")
    for b in bad[:20]:
        core.emit(f"  FORA {b}")
    return 1 if bad else 0


def sample(n: int, seed: int) -> list[dict]:
    by = defaultdict(list)
    with open(build.out_dir() / "docs_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["status"] == "stated":
                by[r["fact_kind"]].append(r)
    rnd = random.Random(seed)
    kinds = sorted(by)
    out = []
    per = max(1, n // len(kinds))
    for k in kinds:
        out.extend(rnd.sample(by[k], min(per, len(by[k]))))
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "provenance":
        return provenance()
    if argv and argv[0] == "sample":
        n = int(argv[1]) if len(argv) > 1 else 60
        seed = int(argv[2]) if len(argv) > 2 else 20261103
        for r in sample(n, seed):
            print(json.dumps({"fact_id": r["fact_id"], "atom_id": r["atom_id"], "kind": r["fact_kind"],
                              "level": r["evidence_level"], "value": r["value"],
                              "at": f"{r['source']['file']}:{r['source']['line']}",
                              "sentence": r["source"]["sentence"]}, ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
