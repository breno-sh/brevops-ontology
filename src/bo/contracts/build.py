"""Gera os artefatos publicados do CONTRACTS a partir do código:

  contracts/Cnn_<nome>.schema.json   (30 schemas)
  contracts/stubs/**                 (stubs + INDEX.json)
  contracts/CONTRACTS.html           (documento dos contratos)

  python -I -m bo.contracts.build            grava
  python -I -m bo.contracts.build --check    regeneração idêntica: sai 1 se algo publicado difere do gerado
"""

from __future__ import annotations

import json
import sys

from . import _base, catalog, stubs


def outputs() -> dict:
    """{caminho relativo a $BO_REPO: bytes}"""
    out = {}
    gen = catalog.generated()
    for cid, s in gen.items():
        out[f"contracts/{catalog.schema_filename(cid)}"] = _base.dumps(s).encode()
    st = stubs.all_stubs()
    missing = sorted(set(st) - set(stubs.KIND_OF)) + sorted(set(stubs.KIND_OF) - set(st))
    if missing:
        raise SystemExit(f"stubs sem tipo ou tipo sem stub: {missing}")
    for rel, data in st.items():
        out[f"contracts/stubs/{rel}"] = data if isinstance(data, bytes) else data.encode()
    idx = {"schema": "bo.stub_index/1", "contract": "C00", "note": "tipo de arquivo (Cnn:tipo) de cada stub",
           "stubs": dict(sorted(stubs.KIND_OF.items()))}
    out["contracts/stubs/INDEX.json"] = _base.dumps(idx).encode()
    from . import render
    out["contracts/CONTRACTS.html"] = render.html(gen).encode()
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = _base.repo()
    outs = outputs()
    if "--check" in argv:
        diff = []
        for rel, data in sorted(outs.items()):
            p = root / rel
            if not p.is_file() or p.read_bytes() != data:
                diff.append(rel)
        stub_dir = root / "contracts" / "stubs"
        extra = sorted(str(p.relative_to(root)) for p in stub_dir.rglob("*") if p.is_file()
                       and str(p.relative_to(root)) not in outs) if stub_dir.is_dir() else []
        for rel in diff:
            print(f"  DIFERE {rel}")
        for rel in extra:
            print(f"  SOBRA  {rel}")
        print(f"[{_base.now()}] build --check: {len(outs)} artefato(s), {len(diff)} diferente(s), {len(extra)} sobra(s)")
        return 1 if diff or extra else 0
    for rel, data in outs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.is_file() or p.read_bytes() != data:
            p.write_bytes(data)
    print(f"[{_base.now()}] build: {len(outs)} artefato(s) em {root / 'contracts'}")
    catalog.published.cache_clear()
    return 0


if __name__ == "__main__":
    sys.exit(main())
