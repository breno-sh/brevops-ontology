"""Regeneração idêntica do SCHEMA-AWS (alvo do despachante bo.tools.regen_check SCHEMA-AWS).

  python -I -m bo.tools.regen_check SCHEMA-AWS [--extract]

Passa (sai 0) só se:
  * MANIFEST.sha256 de $BO_DATA/SCHEMA-AWS confere (inclui o binário do provider e o schema no cache);
  * schema.json.gz descomprime no sha256 de schema.json.sha256, que é o schema_sha256 do pins.json;
  * duas execuções independentes de átomos+tipos (bo.schema.build) em $BO_TMP/regen/run1 e run2
    dão o mesmo sha256 entre si e o mesmo dos atoms.jsonl e types.jsonl publicados;
  * com --extract: o terraform é executado de novo (bo.schema.extract, mesmo lock e sandbox) e a saída crua
    tem o mesmo sha256 (a primeira execução é a publicada; init com rede só para o registro).
Relatório em $BO_DATA/SCHEMA-AWS/regen_check.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from . import atoms, common
from .pipeline import gz_sha256


def run(do_extract: bool = False) -> dict:
    from bo.repo.core import now
    from bo.repo.receipts import verify_manifest
    pin = common.read_pin()
    out = common.out_dir()
    sdir = common.tfschema_dir(pin.version)
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    probs = verify_manifest(out / "MANIFEST.sha256", common.bo_repo())
    add("manifesto", not probs, probs[:5] or "MANIFEST.sha256 confere")
    want = (out / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
    got = gz_sha256(sdir / "schema.json.gz")
    add("schema_sha256", want == got == pin.schema_sha256,
        {"schema.json.sha256": want, "gz": got, "pins": pin.schema_sha256})

    root = common.bo_tmp() / "regen"
    if root.exists():
        shutil.rmtree(root)
    runs = []
    for i in (1, 2):
        d = root / f"run{i}"
        atoms.make(sdir / "schema.json.gz", pin.version, d / "atoms.jsonl", d / "types.jsonl")
        runs.append({"atoms": common.sha256_file(d / "atoms.jsonl"), "types": common.sha256_file(d / "types.jsonl")})
    pub = {"atoms": common.sha256_file(out / "atoms.jsonl"), "types": common.sha256_file(out / "types.jsonl")}
    add("duas_execucoes", runs[0] == runs[1], {"run1": runs[0], "run2": runs[1]})
    add("igual_ao_publicado", runs[0] == pub, {"publicado": pub})

    if do_extract:
        from bo.schema import extract
        eo = root / "extract"
        rc = extract.extract("hashicorp/aws", common.plugin_cache_dir() / "terraform.lock.hcl", out=eo,
                             cache=common.shared_cache(), version=pin.version)
        add("reextracao", rc["schema_json"]["sha256"] == want,
            {"reextraido": rc["schema_json"]["sha256"], "publicado": want,
             "binario": rc["provider_binary"]["sha256"]})
    shutil.rmtree(root, ignore_errors=True)
    ok = all(c["ok"] for c in checks)
    return {"module": common.MODULE, "at": now(), "provider_version": pin.version, "checks": checks,
            "veredito": "PASS" if ok else "FAIL"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_aws.regen_check", description=__doc__.split("\n")[0])
    ap.add_argument("module", nargs="?", default=common.MODULE)
    ap.add_argument("--extract", action="store_true", help="reexecuta também o terraform providers schema")
    a = ap.parse_args(argv)
    if a.module != common.MODULE:
        print(f"regen_check: este é o {common.MODULE}, não {a.module}", file=sys.stderr)
        return 2
    rep = run(a.extract)
    (common.out_dir() / "regen_check.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for c in rep["checks"]:
        print(f"  {'OK  ' if c['ok'] else 'FAIL'} {c['check']}: {json.dumps(c['detail'], ensure_ascii=False)[:200]}")
    print(f"regen_check {common.MODULE}: {rep['veredito']}")
    return 0 if rep["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
