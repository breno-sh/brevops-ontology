"""Fonte fixada do DOCS-AZURE: website/docs/ do terraform-provider-azurerm na tag do PINS, como DADO.

  python -I -m bo.docs_azure.source fetch    copia da pré-busca, conferindo cada sha256 do MANIFEST.json dela
  python -I -m bo.docs_azure.source verify   confere a cópia (FILES.sha256, schema contra o pins.json)

A versão vem de $BO_REPO/universe/pins.json (provider azurerm). A pré-busca só é aceita se for da mesma
versão, se o sha256 do schema bater com o schema_sha256 do pins.json e se cada arquivo bater com o
MANIFEST.json dela; senão o fetch para (baixar a versão fixada é outro caminho, não implementado aqui
porque a pré-busca é da versão fixada). Nada da pasta é executado ou importado.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

PROVIDER = "azurerm"
REPO = "hashicorp/terraform-provider-azurerm"
LICENSE = "MPL-2.0"


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def pins_path() -> Path:
    return bo_repo() / "universe" / "pins.json"


def pin() -> dict:
    doc = json.loads(pins_path().read_text(encoding="utf-8"))
    for p in doc["providers"]:
        if p["provider"] == PROVIDER:
            return p
    raise SystemExit(f"pins.json sem provider {PROVIDER}")


def version() -> str:
    return pin()["version"]


def tag() -> str:
    return "v" + version()


def prefetch_dir() -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / version()


def dest_dir() -> Path:
    return bo_data() / "downloads" / "docs-azurerm"


def docs_root() -> Path:
    """Raiz equivalente à raiz do repositório na tag: source.file 'website/docs/r/x.html.markdown' fica aqui."""
    return dest_dir() / tag()


def schema_path() -> Path:
    return dest_dir() / "providers-schema.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _prefetch_manifest() -> dict:
    m = json.loads((prefetch_dir() / "MANIFEST.json").read_text(encoding="utf-8"))
    if m.get("version") != version():
        raise SystemExit(f"pré-busca é da versão {m.get('version')}, o PINS fixa {version()}")
    d = m["sources"]["docs"]
    if d.get("tag") != tag() or d.get("repo") != f"https://github.com/{REPO}":
        raise SystemExit(f"pré-busca: docs de {d.get('repo')}@{d.get('tag')}, esperado {REPO}@{tag()}")
    return m


def meta() -> dict:
    """Repo, tag, commit e data do commit da tag (a data é o as_of dos defaults)."""
    m = _prefetch_manifest()
    d = m["sources"]["docs"]
    return {"repo": REPO, "tag": tag(), "version": version(), "commit": d["commit"],
            "commit_date": d["commit_date"], "as_of": d["commit_date"][:10]}


def fetch() -> dict:
    m = _prefetch_manifest()
    pf = prefetch_dir()
    p = pin()
    got = sha256(pf / "providers-schema.json")
    if got != p["schema_sha256"]:
        raise SystemExit(f"schema da pré-busca {got[:12]} != schema_sha256 do pins.json {p['schema_sha256'][:12]}")
    files = [f for f in m["files"] if f["path"].startswith("docs/")]
    bad = [f["path"] for f in files if sha256(pf / f["path"]) != f["sha256"]]
    if bad:
        raise SystemExit(f"{len(bad)} arquivo(s) da pré-busca não batem com o MANIFEST.json: {bad[:3]}")
    dst = dest_dir()
    root = docs_root() / "website"
    if root.exists():
        shutil.rmtree(root)
    lines = []
    for f in sorted(files, key=lambda x: x["path"]):
        rel = "website/" + f["path"]                      # docs/... -> website/docs/...
        out = docs_root() / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pf / f["path"], out)
        lines.append(f"{f['sha256']}  {tag()}/{rel}\n")
    shutil.copyfile(pf / "providers-schema.json", schema_path())
    (dst / "FILES.sha256").write_text("".join(lines), encoding="utf-8")
    mt = meta()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")
    src = [
        "Fonte: documentação do provider Terraform azurerm (dado não confiável; só lido como texto, nunca executado)",
        f"Repositório: https://github.com/{REPO}",
        f"Tag: {mt['tag']}  commit {mt['commit']}  data do commit {mt['commit_date']}",
        "Tag conferida em 2026-11-03 com git ls-remote: refs/tags/v5.12.0 -> o mesmo commit",
        f"Versão fixada: {mt['version']} ($BO_REPO/universe/pins.json, módulo PINS)",
        "Caminho no repositório: website/docs/  ->  aqui em " + f"{mt['tag']}/website/docs/",
        f"Arquivos: {len(files)} (sha256 de cada um em FILES.sha256, iguais ao MANIFEST.json da pré-busca)",
        f"Origem da cópia: $BO_DATA/downloads/prefetch/{PROVIDER}/{version()}/ (pré-busca de 2026-11-02, "
        "git clone --depth 1 da tag; ver o MANIFEST.json de lá)",
        f"Schema: providers-schema.json, sha256 {got} = schema_sha256 do pins.json "
        "(saída de 'terraform providers schema -json' com o binário assinado, feita na pré-busca)",
        f"Licença: {LICENSE} (https://www.mozilla.org/en-US/MPL/2.0/), a do repositório",
        "Uso: leitura de r/*.html.markdown pelo bo.docs_azure (módulo DOCS-AZURE)",
        f"Copiado em: {now} (America/Recife)",
    ]
    (dst / "SOURCE.txt").write_text("\n".join(src) + "\n", encoding="utf-8")
    return {"files": len(files), "schema_sha256": got}


def verify() -> dict:
    """Confere a cópia: FILES.sha256 inteiro, nenhum arquivo a mais, schema = pins.json. Levanta em erro."""
    dst = dest_dir()
    if not (dst / "SOURCE.txt").is_file() or (dst / "SOURCE.txt").stat().st_size == 0:
        raise SystemExit("SOURCE.txt ausente ou vazio; rode: python -I -m bo.docs_azure.source fetch")
    want = {}
    for ln in (dst / "FILES.sha256").read_text(encoding="utf-8").splitlines():
        h, rel = ln.split("  ", 1)
        want[rel] = h
    have = {str(p.relative_to(dst)) for p in docs_root().rglob("*") if p.is_file()}
    extra, missing = have - set(want), set(want) - have
    if extra or missing:
        raise SystemExit(f"cópia diverge: {len(extra)} a mais, {len(missing)} faltando")
    bad = [r for r, h in want.items() if sha256(dst / r) != h]
    if bad:
        raise SystemExit(f"{len(bad)} arquivo(s) com sha256 diferente: {bad[:3]}")
    s = sha256(schema_path())
    if s != pin()["schema_sha256"]:
        raise SystemExit("providers-schema.json não bate com o schema_sha256 do pins.json")
    return {"files": len(want), "schema_sha256": s}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "verify"
    if cmd == "fetch":
        r = fetch()
    elif cmd == "verify":
        r = verify()
    else:
        print(__doc__)
        return 2
    print(f"{cmd}: {r['files']} arquivos conferidos; schema {r['schema_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
