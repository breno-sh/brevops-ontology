"""HCL de exemplo dos moldes (deploy/fixtures/oci/_templates/rendered_example/), para quem escreve fixtures (CQFIX).

  python -I -m bo.harness.oci.example           regrava rendered_example/ a partir de examples/
  python -I -m bo.harness.oci.example --check   renderiza de novo em $BO_TMP e compara (o carimbo de hora do
                                                relatório não conta)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import templates_dir, tmp_root
from . import render as R


def _render(out: Path) -> None:
    ex = templates_dir() / "examples"
    R.render(ex / "lowering_plan.jsonl", out, bindings_path=ex / "bindings.json")


def _snapshot(d: Path) -> dict:
    snap = {}
    for p in sorted(d.rglob("*")):
        if not p.is_file() or ".terraform" in p.parts or p.name == ".terraform.lock.hcl":
            continue
        rel = str(p.relative_to(d))
        if p.name == R.REPORT_NAME:
            rep = json.loads(p.read_text(encoding="utf-8"))
            rep.pop("generated_at", None)
            snap[rel] = json.dumps(rep, sort_keys=True)
        else:
            snap[rel] = p.read_text(encoding="utf-8")
    return snap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dest = templates_dir() / "rendered_example"
    if "--check" in argv:
        tmp = tmp_root() / "example_check"
        _render(tmp)
        a, b = _snapshot(dest), _snapshot(tmp)
        if a != b:
            diff = sorted(set(a) ^ set(b)) + sorted(k for k in set(a) & set(b) if a[k] != b[k])
            print(f"example --check: rendered_example difere da regeneração em {diff}", file=sys.stderr)
            return 1
        print(f"example --check: rendered_example idêntico à regeneração ({len(a)} arquivo(s))")
        return 0
    _render(dest)
    print(f"example: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
