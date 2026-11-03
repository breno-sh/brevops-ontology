"""Fonte fixada da documentação do provider aws: dado não confiável, conferido e copiado, nunca executado.

Origem: a pré-busca do coordenador ($BO_DATA/downloads/prefetch/aws/<versão>/), que copiou website/docs/ do
repositório hashicorp/terraform-provider-aws na tag v<versão>. Conferências, todas obrigatórias:
  1. a versão é a do universe/pins.json (PINS) e o sha256 do providers-schema.json é o schema_sha256 do pin;
  2. cada arquivo de docs/ confere com o sha256 do MANIFEST.json da pré-busca (nenhum a mais, nenhum a menos);
  3. a tag aponta para o commit registrado no MANIFEST e o git blob sha1 de cada arquivo confere com a árvore
     website/docs/ desse commit na API do GitHub (respostas brutas guardadas em github/; conferência offline
     depois do primeiro download).
Depois disso a árvore é copiada para $BO_DATA/downloads/docs-aws/v<versão>/website/docs/ e o SOURCE.txt é gravado.

  python -I -m bo.docs_aws.source            baixa o que falta, confere tudo e (re)grava a cópia
  python -I -m bo.docs_aws.source --verify   só confere a cópia gravada (offline); sai 1 se algo diverge
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

PROVIDER = "aws"
REPO = "hashicorp/terraform-provider-aws"
LICENSE = "MPL-2.0"
LICENSE_URI = "https://github.com/hashicorp/terraform-provider-aws/blob/main/LICENSE"
DOCS_IN_REPO = "website/docs"
API = "https://api.github.com/repos/" + REPO


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def pin() -> dict:
    pins = json.loads((bo_repo() / "universe" / "pins.json").read_text(encoding="utf-8"))
    for p in pins["providers"]:
        if p["provider"] == PROVIDER:
            return p
    raise SystemExit("pins.json sem o provider aws")


def version() -> str:
    return pin()["version"]


def tag() -> str:
    return "v" + version()


def prefetch_dir() -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / version()


def download_dir() -> Path:
    return bo_data() / "downloads" / "docs-aws"


def docs_root() -> Path:
    """Raiz copiada: .../v<versão>/website/docs (os caminhos 'file' do C03 são relativos à raiz do repositório)."""
    return download_dir() / tag() / DOCS_IN_REPO


def repo_root_copy() -> Path:
    return download_dir() / tag()


def schema_copy() -> Path:
    return download_dir() / "providers-schema.json"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(p: Path) -> str:
    b = p.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "brevops-ontology-docs-aws"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _cached(name: str, url: str) -> dict:
    """Resposta bruta da API do GitHub guardada em github/<name>.json (baixada uma vez; dado, não código)."""
    d = download_dir() / "github"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    if not p.exists():
        p.write_bytes(_get(url))
    return json.loads(p.read_text(encoding="utf-8"))


def github_tree() -> tuple[str, dict[str, str]]:
    """(commit da tag, {caminho relativo a website/docs: blob sha1}) a partir das respostas guardadas."""
    ref = _cached("ref-tag", f"{API}/git/ref/tags/{tag()}")
    obj = ref["object"]
    if obj["type"] == "tag":   # tag anotada: segue até o commit
        t = _cached("tag-object", obj["url"])
        obj = t["object"]
    commit = obj["sha"]
    c = _cached("commit", f"{API}/git/commits/{commit}")
    root = _cached("tree-root", f"{API}/git/trees/{c['tree']['sha']}")
    web = next(e for e in root["tree"] if e["path"] == "website" and e["type"] == "tree")
    wt = _cached("tree-website", f"{API}/git/trees/{web['sha']}")
    docs = next(e for e in wt["tree"] if e["path"] == "docs" and e["type"] == "tree")
    dt = _cached("tree-website-docs", f"{API}/git/trees/{docs['sha']}?recursive=1")
    if dt.get("truncated"):
        raise SystemExit("árvore website/docs truncada pela API do GitHub; conferência impossível")
    return commit, {e["path"]: e["sha"] for e in dt["tree"] if e["type"] == "blob"}


def _files(root: Path) -> dict[str, Path]:
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*")) if p.is_file()}


def check_tree(root: Path, manifest: dict, gh: dict[str, str]) -> list[str]:
    """Problemas da árvore root (website/docs) contra o MANIFEST da pré-busca e a árvore do GitHub."""
    probs = []
    want = {f["path"][len("docs/"):]: f["sha256"] for f in manifest["files"] if f["path"].startswith("docs/")}
    have = _files(root)
    for rel in sorted(set(want) - set(have)):
        probs.append(f"falta {rel}")
    for rel in sorted(set(have) - set(want)):
        probs.append(f"arquivo a mais {rel}")
    for rel in sorted(set(gh) ^ set(want)):
        probs.append(f"conjunto difere do GitHub: {rel}")
    for rel, p in have.items():
        if rel in want and sha256_file(p) != want[rel]:
            probs.append(f"sha256 difere do MANIFEST: {rel}")
        if rel in gh and git_blob_sha1(p) != gh[rel]:
            probs.append(f"git blob sha1 difere da tag: {rel}")
    return probs


def manifest_prefetch() -> dict:
    return json.loads((prefetch_dir() / "MANIFEST.json").read_text(encoding="utf-8"))


def verify(copy: bool = True) -> dict:
    """Confere a pré-busca (copy=True) ou a cópia gravada (copy=False). Sai com erro se algo diverge."""
    p = pin()
    man = manifest_prefetch()
    if man["version"] != p["version"]:
        raise SystemExit(f"pré-busca na versão {man['version']}, pin em {p['version']}")
    commit, gh = github_tree()
    if commit != man["sources"]["docs"]["commit"]:
        raise SystemExit("a tag no GitHub aponta para outro commit que o da pré-busca")
    if man["sources"]["docs"]["tag"] != tag():
        raise SystemExit("tag da pré-busca diferente da tag do pin")
    src_schema = prefetch_dir() / "providers-schema.json" if copy else schema_copy()
    sch = sha256_file(src_schema)
    if sch != p["schema_sha256"]:
        raise SystemExit("providers-schema.json não confere com o schema_sha256 do pin")
    root = prefetch_dir() / "docs" if copy else docs_root()
    probs = check_tree(root, man, gh)
    if probs:
        raise SystemExit("documentação não confere: " + "; ".join(probs[:10]) + f" ({len(probs)} problema(s))")
    return {"commit": commit, "commit_date": man["sources"]["docs"]["commit_date"], "n_files": len(gh),
            "schema_sha256": sch, "manifest_sha256": sha256_file(prefetch_dir() / "MANIFEST.json")}


def release_date() -> str:
    """Data (UTC, AAAA-MM-DD) de publicação da versão fixada no registry (versions.json da pré-busca)."""
    vs = json.loads((prefetch_dir() / "versions" / "versions.json").read_text(encoding="utf-8"))
    for v in vs:
        if v["version"] == version():
            return v["published_at"][:10]
    raise SystemExit("versão fixada ausente de versions.json")


def source_text(info: dict, when: str) -> str:
    v = version()
    return "\n".join([
        f"DOCS-AWS — fonte da documentação do provider aws {v}",
        f"gravado em: {when} (America/Recife)",
        "",
        f"repositório: https://github.com/{REPO}",
        f"tag: {tag()}  commit: {info['commit']}  data do commit: {info['commit_date']}",
        f"publicação da versão no registry: {release_date()}",
        f"caminho no repositório: {DOCS_IN_REPO}/  ->  cópia em {tag()}/{DOCS_IN_REPO}/ ({info['n_files']} arquivos)",
        f"licença: {LICENSE} ({LICENSE_URI})",
        "",
        "obtenção: cópia da pré-busca do coordenador ($BO_DATA/downloads/prefetch/aws/" + v + "/docs/)",
        "conferência 1: sha256 de cada arquivo = MANIFEST.json da pré-busca (sha256 " + info["manifest_sha256"] + ")",
        "conferência 2: git blob sha1 de cada arquivo = árvore website/docs do commit da tag na API do GitHub",
        "               (respostas brutas em github/; nenhum arquivo a mais nem a menos)",
        "conferência 3: providers-schema.json (cópia) sha256 " + info["schema_sha256"] + " = schema_sha256 do pin",
        "",
        "uso: dado não confiável. Lido só como texto pelo bo.docs_aws (python -I); nada daqui é executado.",
        "",
    ])


def write_manifest() -> int:
    d = download_dir()
    lines = []
    for rel, p in _files(d).items():
        if rel == "MANIFEST.sha256":
            continue
        lines.append(f"{sha256_file(p)}  {rel}")
    (d / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def fetch() -> dict:
    from bo.repo import core
    info = verify(copy=True)
    d = download_dir()
    d.mkdir(parents=True, exist_ok=True)
    if repo_root_copy().exists():
        shutil.rmtree(repo_root_copy())
    shutil.copytree(prefetch_dir() / "docs", docs_root())
    shutil.copyfile(prefetch_dir() / "providers-schema.json", schema_copy())
    verify(copy=False)
    (d / "SOURCE.txt").write_text(source_text(info, core.now()), encoding="utf-8")
    info["manifest_lines"] = write_manifest()
    return info


def verify_copy() -> dict:
    info = verify(copy=False)
    d = download_dir()
    bad = []
    for line in (d / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        sha, rel = line.split("  ", 1)
        if sha256_file(d / rel) != sha:
            bad.append(rel)
    if bad:
        raise SystemExit(f"MANIFEST.sha256 de downloads/docs-aws não confere: {bad[:5]}")
    if not (d / "SOURCE.txt").stat().st_size:
        raise SystemExit("SOURCE.txt vazio")
    return info


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--verify" in argv:
        info = verify_copy()
        print(f"downloads/docs-aws confere: {info['n_files']} arquivos na tag {tag()} (commit {info['commit'][:12]})")
        return 0
    info = fetch()
    print(f"docs-aws gravado: {info['n_files']} arquivos, commit {info['commit'][:12]}, "
          f"{info['manifest_lines']} linhas no MANIFEST.sha256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
