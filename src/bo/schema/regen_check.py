"""Emenda da biblioteca x saída publicada dos SCHEMA-*: nenhum átomo existente muda (id nem bytes).

  python -I -m bo.schema.regen_check [--providers aws,azurerm,google,oci] [--out ARQ]

Para cada SCHEMA-<X>: lê a versão do types.jsonl publicado ($BO_DATA/SCHEMA-<X>/), regenera átomos e tipos com
a biblioteca atual a partir do schema extraído e conferido ($BO_DATA/downloads/tfschema/<p>-<v>/schema.json.gz,
sha256 = schema.json.sha256) em $BO_TMP/regen/, e compara:
  * toda linha publicada do atoms.jsonl existe, com os MESMOS bytes, na regeneração (mesmo atom_id);
  * as linhas novas são todas átomos de elemento (block_path[].kind = nested_attribute);
  * o types.jsonl regenerado é byte a byte o publicado;
  * os átomos regenerados conferem no C01 publicado (bo.contracts.validate).
Sai 0 só se tudo confere nos provedores pedidos. Relatório: $BO_DATA/SCHEMALIB/regen_check.json.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

from . import LIBRARY_VERSION, core

PRODUCER = {"aws": "SCHEMA-AWS", "azurerm": "SCHEMA-AZURE", "google": "SCHEMA-GCP", "oci": "SCHEMA-OCI"}


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / "SCHEMALIB")


def _lines(p: Path) -> list[str]:
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def check(provider: str) -> dict:
    src = bo_data() / PRODUCER[provider]
    pub_types = _lines(src / "types.jsonl")
    version = json.loads(pub_types[0])["provider_version"]
    d = bo_data() / "downloads" / "tfschema" / f"{provider}-{version}"
    raw = gzip.open(d / "schema.json.gz", "rb").read()
    want = (d / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
    rep = {"modulo": PRODUCER[provider], "provider": provider, "provider_version": version,
           "schema_sha256": hashlib.sha256(raw).hexdigest()}
    if rep["schema_sha256"] != want:
        return {**rep, "ok": False, "erro": "sha256 do schema diverge do schema.json.sha256"}
    ps = core.providers(json.loads(raw))[provider]
    types = list(core.iter_types(ps, provider, version))
    out = bo_tmp() / "regen" / provider
    core.write_jsonl(out / "atoms.jsonl", (a for t in types for a in t.all_atoms()))
    core.write_jsonl(out / "types.jsonl", (core.type_record(t) for t in types))
    new = {json.loads(ln)["atom_id"]: ln for ln in _lines(out / "atoms.jsonl")}
    old = {json.loads(ln)["atom_id"]: ln for ln in _lines(src / "atoms.jsonl")}
    missing = sorted(set(old) - set(new))
    changed = sorted(i for i in set(old) & set(new) if old[i] != new[i])
    added = sorted(set(new) - set(old))
    not_element = [i for i in added if not core.is_element(json.loads(new[i]))]
    types_same = _lines(out / "types.jsonl") == pub_types
    from bo.contracts import validate as V
    r = V.validate("C01_atoms", out / "atoms.jsonl")
    collections = sorted({json.loads(new[i])["atom_id"].rsplit(".", 1)[0] for i in added})
    ok = not missing and not changed and not not_element and types_same and r.ok
    return {**rep, "ok": ok, "atomos_publicados": len(old), "atomos_regenerados": len(new),
            "atomos_existentes_ausentes": missing[:20], "n_ausentes": len(missing),
            "atomos_existentes_com_bytes_diferentes": changed[:20], "n_diferentes": len(changed),
            "atomos_novos": len(added), "novos_que_nao_sao_elemento": not_element[:20],
            "colecoes_expandidas": len(collections), "exemplos_colecoes": collections[:10],
            "types_identico": types_same, "c01_confere": r.ok, "c01_erros": r.errors[:5]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema.regen_check", description=__doc__.split("\n")[0])
    ap.add_argument("--providers", default="aws,azurerm,google,oci")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    from bo.repo.core import now
    res = [check(p) for p in a.providers.split(",")]
    rep = {"schema": "bo.schemalib.regen_check/1", "generated_at": now(), "library_version": LIBRARY_VERSION,
           "resultados": res, "veredito": "PASS" if all(r["ok"] for r in res) else "FAIL"}
    out = a.out or bo_data() / "SCHEMALIB" / "regen_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in res:
        print(f"{r['modulo']:13s} {r['provider_version']:8s} publicados {r.get('atomos_publicados')} regenerados "
              f"{r.get('atomos_regenerados')} | ausentes {r.get('n_ausentes')} bytes diferentes {r.get('n_diferentes')} "
              f"| novos {r.get('atomos_novos')} (elemento de {r.get('colecoes_expandidas')} coleções) | types "
              f"{'idêntico' if r.get('types_identico') else 'DIFERENTE'} | C01 {'ok' if r.get('c01_confere') else 'FALHA'}"
              f" -> {'OK' if r['ok'] else 'FAIL'}")
    print(f"RESULTADO: {rep['veredito']} ({out})")
    return 0 if rep["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
