"""Regeneração idêntica do SCHEMA-OCI: duas execuções, mesmo sha256 (gate 'python -I -m bo.tools.regen_check').

  python -I -m bo.tools.regen_check SCHEMA-OCI      (despachante do coordenador -> este módulo)
  python -I -m bo.schema_oci.regen_check [SCHEMA-OCI]

Gera DUAS vezes, em pastas separadas de $BO_TMP/regen/, a partir do schema extraído (conferido contra o
schema.json.sha256 e o pins.json): atoms.jsonl e types.jsonl (bo.schema.build + passada write_only) e a
classificação do crosscheck. Sai 0 só se as duas execuções dão os mesmos sha256 E eles são os dos arquivos
publicados em $BO_DATA/SCHEMA-OCI. O relatório da biblioteca (crosscheck_oci-<v>.json) entra sem o
generated_at, único campo que muda entre execuções.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import atoms, common, crossdiff, pipeline


def _lib_report_sha(p: Path) -> str:
    import hashlib
    d = json.loads(p.read_text(encoding="utf-8"))
    d.pop("generated_at", None)
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def one(run_dir: Path, gz: Path, version: str) -> dict[str, str]:
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    atoms.make(gz, version, run_dir / "atoms.jsonl", run_dir / "types.jsonl")
    crossdiff.run(run_dir)                       # lê o types.jsonl desta execução
    return {"atoms.jsonl": common.sha256_file(run_dir / "atoms.jsonl"),
            "types.jsonl": common.sha256_file(run_dir / "types.jsonl"),
            "crosscheck_classificacao.json": common.sha256_file(run_dir / "crosscheck_classificacao.json"),
            f"crosscheck_oci-{version}.json(sem generated_at)": _lib_report_sha(run_dir / f"crosscheck_oci-{version}.json")}


def published(out: Path, version: str) -> dict[str, str]:
    return {"atoms.jsonl": common.sha256_file(out / "atoms.jsonl"),
            "types.jsonl": common.sha256_file(out / "types.jsonl"),
            "crosscheck_classificacao.json": common.sha256_file(out / "crosscheck_classificacao.json"),
            f"crosscheck_oci-{version}.json(sem generated_at)": _lib_report_sha(out / f"crosscheck_oci-{version}.json")}


def main(argv=None) -> int:
    argv = [a for a in (argv or []) if a != common.MODULE]
    if argv:
        print(f"regen_check: argumentos inesperados {argv}", file=sys.stderr)
        return 2
    pin = common.read_pin()
    sdir = common.tfschema_dir(pin.version)
    gz = sdir / "schema.json.gz"
    raw = (sdir / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
    if pipeline.gz_sha256(gz) != raw or raw != pin.schema_sha256:
        print("regen_check: schema extraído não confere com schema.json.sha256/pins.json", file=sys.stderr)
        return 1
    out = common.out_dir()
    pub = published(out, pin.version)
    root = common.bo_tmp() / "regen"
    runs = [one(root / f"run{i}", gz, pin.version) for i in (1, 2)]
    ok = True
    for k in pub:
        same = runs[0][k] == runs[1][k] == pub[k]
        ok &= same
        print(f"  {'OK  ' if same else 'DIFF'} {k}: run1 {runs[0][k][:16]} run2 {runs[1][k][:16]} publicado {pub[k][:16]}")
    shutil.rmtree(root, ignore_errors=True)
    print(f"regen_check SCHEMA-OCI ({pin.version}): {'idêntico' if ok else 'DIVERGE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
