"""Fonte fixada: website/docs/ do oracle/terraform-provider-oci na tag do PINS, como dado não confiável.

Nada daqui é executado: os arquivos só são lidos como texto. A cópia vem da pré-busca do coordenador
($BO_DATA/downloads/prefetch/oci/<versão>/docs/) e é conferida de dois jeitos independentes:
  1. sha256 de cada arquivo == sha256 do MANIFEST.json da pré-busca;
  2. hash de blob do git (sha1 de "blob <n>\\0" + conteúdo) == o da árvore da tag no repositório oficial,
     lida com um clone sem blobs (--filter=blob:none), e a tag aponta para o commit registrado na pré-busca.

  python -I -m bo.docs_oci.source fetch    copia da pré-busca, lê a árvore da tag (rede) e grava SOURCE.txt
  python -I -m bo.docs_oci.source verify   confere tudo offline (sai 1 se algo diverge)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROVIDER = "oci"
SOURCE_ADDR = "registry.terraform.io/oracle/oci"
REPO = "oracle/terraform-provider-oci"
REPO_URL = f"https://github.com/{REPO}.git"
DOCS_PREFIX = "website/docs/"
LICENSE = "MPL-2.0"
TZ = ZoneInfo("America/Recife")


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def bo_tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / "DOCS-OCI")


def download_dir() -> Path:
    return bo_data() / "downloads" / "docs-oci"


def docs_root() -> Path:
    """Raiz cujos caminhos relativos são os do repositório (website/docs/r/x.html.markdown)."""
    return download_dir()


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def pin() -> dict:
    """A entrada do oci em universe/pins.json (C13)."""
    pins = json.loads((bo_repo() / "universe" / "pins.json").read_text(encoding="utf-8"))
    for p in pins["providers"]:
        if p["provider"] == PROVIDER:
            if p["source"] != SOURCE_ADDR:
                raise SystemExit(f"pins.json: oci com source inesperado {p['source']!r}")
            return p
    raise SystemExit("pins.json sem o provider oci")


def version() -> str:
    return pin()["version"]


def tag() -> str:
    return "v" + version()


def prefetch_dir(ver: str | None = None) -> Path:
    return bo_data() / "downloads" / "prefetch" / PROVIDER / (ver or version())


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(b: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def read_prefetch_manifest(ver: str) -> dict:
    m = json.loads((prefetch_dir(ver) / "MANIFEST.json").read_text(encoding="utf-8"))
    if m.get("provider") != SOURCE_ADDR or m.get("version") != ver:
        raise SystemExit(f"MANIFEST.json da pré-busca não é do {SOURCE_ADDR} {ver}")
    return m


def parse_ls_tree(text: str) -> dict[str, str]:
    """'<modo> blob <sha1>\\t<caminho>' -> {caminho: sha1} (só blobs)."""
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind == "blob":
            out[path] = sha
    return out


def local_files() -> dict[str, Path]:
    root = docs_root() / "website" / "docs"
    return {str(p.relative_to(docs_root())): p for p in sorted(root.rglob("*")) if p.is_file()}


def fetch() -> int:
    ver = version()
    man = read_prefetch_manifest(ver)
    commit = man["sources"]["docs"]["commit"]
    if man["sources"]["docs"]["tag"] != tag():
        raise SystemExit(f"pré-busca na tag {man['sources']['docs']['tag']}, PINS pede {tag()}")
    dd = download_dir()
    up = dd / "upstream"
    up.mkdir(parents=True, exist_ok=True)
    # 1. árvore da tag no repositório oficial (sem blobs: só o hash de cada arquivo)
    work = bo_tmp() / "tagtree.git"
    if work.exists():
        shutil.rmtree(work)
    env = {"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "HOME": str(bo_tmp()), "GIT_TERMINAL_PROMPT": "0",
           "GIT_CONFIG_NOSYSTEM": "1"}
    ls_remote = subprocess.run(["git", "ls-remote", REPO_URL, f"refs/tags/{tag()}", f"refs/tags/{tag()}^{{}}"],
                               check=True, capture_output=True, text=True, env=env).stdout
    subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none", "--depth", "1", "--branch", tag(),
                    REPO_URL, str(work)], check=True, env=env)
    head = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()
    cdate = subprocess.run(["git", "-C", str(work), "log", "-1", "--format=%cI", "HEAD"], check=True,
                           capture_output=True, text=True, env=env).stdout.strip()
    tree = subprocess.run(["git", "-C", str(work), "ls-tree", "-r", "HEAD", DOCS_PREFIX.rstrip("/")], check=True,
                          capture_output=True, text=True, env=env).stdout
    shutil.rmtree(work)
    if head != commit:
        raise SystemExit(f"tag {tag()} aponta para {head}, pré-busca registrou {commit}")
    (up / "ls-remote.txt").write_text(ls_remote, encoding="utf-8")
    (up / "ls-tree.txt").write_text(tree, encoding="utf-8")
    (up / "commit.json").write_text(json.dumps({"repo": REPO, "tag": tag(), "commit": head, "commit_date": cdate},
                                               indent=1) + "\n", encoding="utf-8")
    # 2. cópia da pré-busca para website/docs/ (caminhos iguais aos do repositório)
    dst = dd / "website" / "docs"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(prefetch_dir(ver) / "docs", dst)
    rep = verify_report()
    write_source_txt(rep)
    if rep["problems"]:
        print("\n".join(rep["problems"][:20]), file=sys.stderr)
        return 1
    print(f"docs-oci {tag()}: {rep['files']} arquivos conferidos (sha256 da pré-busca e blob do git da tag)")
    return 0


def verify_report() -> dict:
    ver = version()
    dd = download_dir()
    man = read_prefetch_manifest(ver)
    pre = {f["path"][len("docs/"):]: f["sha256"] for f in man["files"] if f["path"].startswith("docs/")}
    tree = parse_ls_tree((dd / "upstream" / "ls-tree.txt").read_text(encoding="utf-8"))
    commit = json.loads((dd / "upstream" / "commit.json").read_text(encoding="utf-8"))
    loc = local_files()
    problems = []
    if commit["commit"] != man["sources"]["docs"]["commit"] or commit["tag"] != tag():
        problems.append("commit/tag da árvore oficial diverge da pré-busca ou do PINS")
    want = set(tree)
    have = set(loc)
    for p in sorted(want - have):
        problems.append(f"falta localmente: {p}")
    for p in sorted(have - want):
        problems.append(f"sobra localmente (não está na tag): {p}")
    manifest_lines = []
    for rel, p in sorted(loc.items()):
        b = p.read_bytes()
        s256 = hashlib.sha256(b).hexdigest()
        manifest_lines.append(f"{s256}  {rel}")
        r2 = rel[len(DOCS_PREFIX):]
        if pre.get(r2) != s256:
            problems.append(f"sha256 diverge da pré-busca: {rel}")
        if rel in tree and tree[rel] != git_blob_sha1(b):
            problems.append(f"blob do git diverge da tag: {rel}")
    return {"files": len(loc), "tree_files": len(tree), "prefetch_files": len(pre), "commit": commit,
            "problems": problems, "manifest": "\n".join(manifest_lines) + "\n"}


def write_source_txt(rep: dict) -> None:
    dd = download_dir()
    p = pin()
    (dd / "MANIFEST.sha256").write_text(rep["manifest"], encoding="utf-8")
    c = rep["commit"]
    txt = f"""DOCS-OCI — fonte da documentação (dado não confiável, nunca executado)
gravado em: {now()} (America/Recife)

provider: {SOURCE_ADDR} {p['version']} (universe/pins.json, C13; shasums_sha256 {p['shasums_sha256']})
repositório: https://github.com/{REPO}
tag: {c['tag']}   commit: {c['commit']}   data do commit: {c['commit_date']}
caminho no repositório: {DOCS_PREFIX}  ->  aqui: website/docs/ (mesmos caminhos relativos)
licença: {LICENSE}

como foi obtido
  - cópia de $BO_DATA/downloads/prefetch/oci/{p['version']}/docs/ (pré-busca do coordenador, 02/11/2026:
    git clone --depth 1 --filter=blob:none --no-checkout --branch {c['tag']} + sparse-checkout de {DOCS_PREFIX});
  - árvore da tag lida de novo no repositório oficial, sem blobs (git clone --bare --filter=blob:none --depth 1
    --branch {c['tag']}; git ls-tree -r HEAD website/docs) -> upstream/ls-tree.txt; git ls-remote -> upstream/ls-remote.txt.

conferência (python -I -m bo.docs_oci.source verify)
  - {rep['files']} arquivos locais; {rep['tree_files']} blobs na árvore da tag; {rep['prefetch_files']} na pré-busca;
  - sha256 de cada arquivo == MANIFEST.json da pré-busca; hash de blob do git de cada arquivo == ls-tree da tag;
  - commit da tag == commit registrado na pré-busca;
  - divergências: {len(rep['problems'])}.
  - MANIFEST.sha256: sha256 de cada arquivo copiado (formato shasum -a 256, caminho relativo a esta pasta).
"""
    (dd / "SOURCE.txt").write_text(txt, encoding="utf-8")
    (dd / "verification.json").write_text(json.dumps(
        {k: v for k, v in rep.items() if k != "manifest"}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def verify() -> int:
    rep = verify_report()
    on_disk = (download_dir() / "MANIFEST.sha256").read_text(encoding="utf-8")
    if on_disk != rep["manifest"]:
        rep["problems"].append("MANIFEST.sha256 gravado difere do recalculado")
    if not (download_dir() / "SOURCE.txt").stat().st_size:
        rep["problems"].append("SOURCE.txt vazio")
    if rep["problems"]:
        print("\n".join(rep["problems"][:20]), file=sys.stderr)
        print(f"source verify: {len(rep['problems'])} divergência(s)")
        return 1
    print(f"source verify: {rep['files']} arquivos == blobs da tag {rep['commit']['tag']} "
          f"({rep['commit']['commit'][:12]}) == pré-busca; 0 divergências")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "verify"
    if cmd == "fetch":
        return fetch()
    if cmd == "verify":
        return verify()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
