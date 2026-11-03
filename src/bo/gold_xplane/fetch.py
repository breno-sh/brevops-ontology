"""Baixa (como dado, nunca executado) as fontes fixadas do GOLD-XPLANE para $BO_DATA/downloads/crossplane/.

  python -I -m bo.gold_xplane.fetch [--clones DIR]

1. composições: clone parcial (--filter=blob:none) de cada repositório em $BO_TMP/clones, conferência do commit
   fixado e exportação de cada arquivo listado (mais o LICENSE) com `git show <commit>:<arquivo>`;
2. providers: lê as composições exportadas, junta os (grupo, versão, kind) de MR por (repositório, tag) fixado e,
   num clone raso e parcial da tag, exporta o CRD de cada kind (package/crds/<grupo>_*.yaml, conferido por
   spec.names.kind) e, nos providers gerados do Terraform (upjet/jet), o arquivo de tipos Go (zz_*_types.go) e o
   zz_generated*terraformed.go do mesmo grupo/versão, que trazem as tags tf:"..." e o tipo de recurso Terraform;
3. SOURCE.txt por fonte e MANIFEST.sha256 da árvore inteira.
Nenhum arquivo baixado é executado; o YAML é lido com yaml.SafeLoader e o Go como texto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import compose, sources
from .paths import downloads_dir, now_iso, tmp_dir


def _git(args, cwd=None, binary=False):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"),
           "HOME": str(tmp_dir()), "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"}
    r = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "advice.detachedHead=false", *args],
                       cwd=cwd, env=env, capture_output=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace')[-400:]}")
    return r.stdout if binary else r.stdout.decode()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _clone(repo: str, clones: Path, tag: str | None = None) -> Path:
    name = repo.replace("/", "__") + (f"@{tag}" if tag else "")
    d = clones / name
    if not d.exists():
        args = ["clone", "-q", "--filter=blob:none", "--no-checkout"]
        if tag:
            args += ["--depth", "1", "--branch", tag]
        _git(args + [f"https://github.com/{repo}", str(d)])
    return d


def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def fetch_compositions(clones: Path, out: Path) -> list[dict]:
    recs = []
    for s in sources.COMPOSITION_SOURCES:
        d = _clone(s["repo"], clones)
        commit = _git(["rev-parse", f"{s['commit']}^{{commit}}"], cwd=d).strip()
        if commit != s["commit"]:
            raise RuntimeError(f"{s['id']}: commit {commit} != fixado {s['commit']}")
        if s["ref"].startswith("v"):
            tagc = _git(["rev-parse", f"{s['ref']}^{{commit}}"], cwd=d).strip()
            if tagc != commit:
                raise RuntimeError(f"{s['id']}: tag {s['ref']} aponta para {tagc}, não {commit}")
        files = {}
        tree = set(_git(["ls-tree", "-r", "--name-only", commit], cwd=d).split())
        lic = sorted(f for f in tree if re.match(r"^(LICENSE|LICENSE\.md|COPYING)$", f))
        for f in list(s["files"]) + lic:
            data = _git(["show", f"{commit}:{f}"], cwd=d, binary=True)
            _write(out / "compositions" / s["id"] / f, data)
            files[f] = _sha(data)
        src = (f"fonte: https://github.com/{s['repo']}\nref: {s['ref']}\ncommit: {commit}\n"
               f"licença: {s['license']} (arquivo {', '.join(lic) or 'ausente'} exportado junto)\n"
               f"papel: {s['role']}\nfamília de autoria: {s['family']}\nregra de pin de provider: {s['pin_rule']}\n"
               f"obtido em: {now_iso()}\nmétodo: git clone --filter=blob:none; git show <commit>:<arquivo>\n"
               "dado não confiável: lido com yaml.SafeLoader, nunca executado\n"
               + "".join(f"{v}  {k}\n" for k, v in sorted(files.items())))
        _write(out / "compositions" / s["id"] / "SOURCE.txt", src.encode())
        recs.append({"id": s["id"], "repo": s["repo"], "commit": commit, "files": files})
    return recs


def needed_kinds(out: Path) -> dict:
    """{(repo, tag): {(group, version, kind)}} a partir das composições exportadas."""
    need: dict = {}
    for s in sources.COMPOSITION_SOURCES:
        for f in s["files"]:
            p = out / "compositions" / s["id"] / f
            for c in compose.parse_file(p.read_text(encoding="utf-8"))["compositions"]:
                for r in c["resources"]:
                    prov, fam = sources.api_family(r["mr"]["group"])
                    if fam is None or fam not in s["provider_pins"]:
                        continue
                    key = s["provider_pins"][fam]
                    need.setdefault(key, set()).add((r["mr"]["group"], r["mr"]["version"], r["mr"]["kind"]))
    return need


_GROUP_RE = re.compile(r'Group\s*=\s*"([^"]+)"')
_VER_RE = re.compile(r'Version\s*=\s*"([^"]+)"')


def fetch_providers(clones: Path, out: Path, need: dict) -> list[dict]:
    recs = []
    for (repo, tag), kinds in sorted(need.items()):
        meta = sources.PROVIDER_REPOS[(repo, tag)]
        d = _clone(repo, clones, tag)
        commit = _git(["rev-parse", "HEAD^{commit}"], cwd=d).strip()
        tree = _git(["ls-tree", "-r", "--name-only", commit], cwd=d).split()
        crds = [f for f in tree if f.startswith("package/crds/") and f.endswith(".yaml")]
        base = out / "providers" / f"{repo.replace('/', '__')}@{tag}"
        files, found = {}, {}
        for group, version, kind in sorted(kinds):
            hit = None
            for f in crds:
                if not os.path.basename(f).startswith(group + "_"):
                    continue
                data = _git(["show", f"{commit}:{f}"], cwd=d, binary=True)
                doc = yaml_first(data)
                names = ((doc or {}).get("spec") or {}).get("names") or {}
                if names.get("kind") == kind:
                    hit = (f, data)
                    break
            entry = {"group": group, "version": version, "kind": kind, "crd": None, "go_types": None,
                     "terraformed": None}
            if hit:
                _write(base / hit[0], hit[1])
                files[hit[0]] = _sha(hit[1])
                entry["crd"] = hit[0]
            if meta["kind"] == "upjet":
                gv = [f for f in tree if f.startswith("apis/") and f.endswith("zz_groupversion_info.go")]
                guess = f"apis/{group.split('.')[0]}/{version}/zz_groupversion_info.go"
                gv = ([guess] if guess in gv else []) + [f for f in gv if f != guess]
                for f in gv:
                    txt = _git(["show", f"{commit}:{f}"], cwd=d)
                    g, v = _GROUP_RE.search(txt), _VER_RE.search(txt)
                    if not (g and v and g.group(1) == group and v.group(1) == version):
                        continue
                    ddir = os.path.dirname(f)
                    _write(base / f, txt.encode())
                    files[f] = _sha(txt.encode())
                    for g2 in [x for x in tree if os.path.dirname(x) == ddir and x.endswith(".go")]:
                        b2 = os.path.basename(g2)
                        low = kind.lower()
                        if not (b2 == f"zz_{low}_types.go" or b2 in ("zz_generated_terraformed.go",
                                                                     "zz_generated.terraformed.go",
                                                                     f"zz_{low}_terraformed.go")):
                            continue
                        t2 = _git(["show", f"{commit}:{g2}"], cwd=d)
                        if "terraformed" in b2 and f"func (mg *{kind}) GetTerraformResourceType()" in t2:
                            entry["terraformed"] = g2
                        elif b2.endswith("_types.go") and re.search(rf"^type {re.escape(kind)} struct", t2, re.M):
                            entry["go_types"] = g2
                        else:
                            continue
                        _write(base / g2, t2.encode())
                        files[g2] = _sha(t2.encode())
                    break
            found[f"{group}/{version}/{kind}"] = entry
        lic = [f for f in tree if f in ("LICENSE", "LICENSE.md")]
        for f in lic:
            data = _git(["show", f"{commit}:{f}"], cwd=d, binary=True)
            _write(base / f, data)
            files[f] = _sha(data)
        index = {"repo": repo, "tag": tag, "commit": commit, "kind": meta["kind"], "license": meta["license"],
                 "kinds": found}
        _write(base / "index.json", (json.dumps(index, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode())
        src = (f"fonte: https://github.com/{repo}\ntag: {tag}\ncommit: {commit}\nlicença: {meta['license']}\n"
               f"tipo: {meta['kind']}\nobtido em: {now_iso()}\n"
               "método: git clone --depth 1 --filter=blob:none --branch <tag>; git show <commit>:<arquivo>\n"
               "dado não confiável: CRD lido com yaml.SafeLoader; Go lido como texto (regex de struct/tag), nunca compilado\n"
               + "".join(f"{v}  {k}\n" for k, v in sorted(files.items())))
        _write(base / "SOURCE.txt", src.encode())
        recs.append(index)
    return recs


def yaml_first(data: bytes):
    import yaml
    for d in yaml.safe_load_all(data.decode("utf-8")):
        if isinstance(d, dict):
            return d
    return None


def write_manifest(out: Path):
    lines = []
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.sha256":
            lines.append(f"{_sha(p.read_bytes())}  {p.relative_to(out).as_posix()}\n")
    (out / "MANIFEST.sha256").write_text("".join(lines), encoding="utf-8")
    return len(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.gold_xplane.fetch")
    ap.add_argument("--clones", default=None)
    a = ap.parse_args(argv)
    clones = Path(a.clones) if a.clones else tmp_dir() / "clones"
    clones.mkdir(parents=True, exist_ok=True)
    out = downloads_dir()
    out.mkdir(parents=True, exist_ok=True)
    comps = fetch_compositions(clones, out)
    need = needed_kinds(out)
    provs = fetch_providers(clones, out, need)
    n = write_manifest(out)
    miss = [(p["repo"], p["tag"], k) for p in provs for k, e in p["kinds"].items() if not e["crd"]]
    print(f"[{now_iso()}] fetch: {len(comps)} fonte(s) de composição, {len(provs)} provider(s), "
          f"{sum(len(p['kinds']) for p in provs)} kind(s) de MR, {len(miss)} sem CRD; MANIFEST com {n} arquivo(s)")
    for m in miss:
        print("  sem CRD:", *m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
