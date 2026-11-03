"""Traz a documentação da tag fixada para $BO_DATA/downloads/docs-google/ (dado não confiável, nunca executado).

  python -I -m bo.docs_gcp.fetch            confere e copia; grava SOURCE.txt, SHA256SUMS e fetch_verification.json
  python -I -m bo.docs_gcp.fetch --verify   só confere a cópia contra SHA256SUMS (offline; usado no gate)

Reaproveita a pré-busca ($BO_DATA/downloads/prefetch/google/<versão>/docs = website/docs/ do repositório na tag):
  1. cada página tem o sha256 do MANIFEST.json da pré-busca (nenhuma a mais, nenhuma a menos);
  2. a tag v<versão> aponta, na API do GitHub, para o commit que a pré-busca registrou;
  3. uma amostra determinística (1 a cada 100 páginas, em ordem de caminho) baixada de raw.githubusercontent.com
     no commit da tag tem o mesmo sha256 da cópia.
Sem rede, (2) e (3) ficam registrados como NAO_CONFERIDO (nunca como conferido).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

from bo.repo import core

from . import sources as S

SAMPLE_STEP = 100
UA = {"User-Agent": "bo-docs-gcp/1 (leitura de documentação pública)"}


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL fixa, https)
        return r.read()


def manifest_docs() -> dict[str, dict]:
    """{caminho relativo a docs/: {bytes, sha256}} das páginas da pré-busca."""
    out = {}
    for f in S.prefetch_manifest()["files"]:
        if f["path"].startswith("docs/"):
            out[f["path"][len("docs/"):]] = f
    return out


def check_prefetch(files: dict[str, dict]) -> list[str]:
    src = S.prefetch_dir() / "docs"
    probs = []
    on_disk = {str(p.relative_to(src)) for p in src.rglob("*") if p.is_file()}
    for rel in sorted(set(files) - on_disk):
        probs.append(f"falta na pré-busca: {rel}")
    for rel in sorted(on_disk - set(files)):
        probs.append(f"arquivo fora do MANIFEST da pré-busca: {rel}")
    for rel in sorted(set(files) & on_disk):
        if S.sha256_file(src / rel) != files[rel]["sha256"]:
            probs.append(f"sha256 diverge do MANIFEST: {rel}")
    return probs


def check_remote(files: dict[str, dict], commit: str) -> dict:
    res = {"tag_ref": {"status": "NAO_CONFERIDO"}, "sample": {"status": "NAO_CONFERIDO", "files": []}}
    url = f"https://api.github.com/repos/{S.REPO}/git/ref/tags/{S.tag()}"
    try:
        ref = json.loads(_get(url))
        got = ref["object"]["sha"]
        res["tag_ref"] = {"url": url, "object_type": ref["object"]["type"], "commit": got,
                          "status": "CONFERE" if got == commit and ref["object"]["type"] == "commit" else "DIVERGE"}
    except Exception as e:  # rede ausente: registrado, nunca tratado como conferido
        res["tag_ref"]["error"] = type(e).__name__
    rels = sorted(files)[::SAMPLE_STEP]
    tmp = S.bo_tmp() / "fetch_sample"
    tmp.mkdir(parents=True, exist_ok=True)
    ok = bad = err = 0
    for rel in rels:
        url = f"https://raw.githubusercontent.com/{S.REPO}/{commit}/{S.DOCS_PREFIX}/{rel}"
        item = {"path": f"{S.DOCS_PREFIX}/{rel}", "url": url}
        try:
            b = _get(url)
            (tmp / rel.replace("/", "__")).write_bytes(b)
            h = hashlib.sha256(b).hexdigest()
            item["status"] = "CONFERE" if h == files[rel]["sha256"] else "DIVERGE"
        except Exception as e:
            item["status"] = "NAO_CONFERIDO"
            item["error"] = type(e).__name__
        ok += item["status"] == "CONFERE"
        bad += item["status"] == "DIVERGE"
        err += item["status"] == "NAO_CONFERIDO"
        res["sample"]["files"].append(item)
    res["sample"].update(n=len(rels), confere=ok, diverge=bad, nao_conferido=err, step=SAMPLE_STEP,
                         status="CONFERE" if ok == len(rels) else ("DIVERGE" if bad else "NAO_CONFERIDO"))
    return res


def copy(files: dict[str, dict]) -> None:
    src = S.prefetch_dir() / "docs"
    dst = S.docs_root()
    if dst.exists():
        shutil.rmtree(dst)
    for rel in sorted(files):
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, t)


def write_sums(files: dict[str, dict]) -> Path:
    p = S.download_dir() / "SHA256SUMS"
    lines = [f"{files[rel]['sha256']}  {S.DOCS_PREFIX}/{rel}\n" for rel in sorted(files)]
    p.write_text("".join(lines), encoding="utf-8")
    return p


def verify_copy() -> list[str]:
    """Confere a cópia contra SHA256SUMS (offline). Lista de problemas; vazia = confere."""
    d = S.download_dir()
    sums = d / "SHA256SUMS"
    if not sums.exists():
        return [f"falta {sums}"]
    want = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        h, rel = line.split("  ", 1)
        want[rel] = h
    probs = []
    have = {str(p.relative_to(d)) for p in (d / S.DOCS_PREFIX).rglob("*") if p.is_file()}
    for rel in sorted(set(want) - have):
        probs.append(f"falta: {rel}")
    for rel in sorted(have - set(want)):
        probs.append(f"arquivo a mais: {rel}")
    for rel in sorted(set(want) & have):
        if S.sha256_file(d / rel) != want[rel]:
            probs.append(f"sha256 diverge: {rel}")
    return probs


def source_txt(files: dict[str, dict], commit: str, commit_date: str, remote: dict, at: str) -> str:
    man = S.prefetch_dir() / "MANIFEST.json"
    by_dir: dict[str, int] = {}
    for rel in files:
        k = rel.split("/", 1)[0] if "/" in rel else rel
        by_dir[k] = by_dir.get(k, 0) + 1
    s = remote["sample"]
    return "\n".join([
        f"DOCS-GCP: documentação do provider google na tag fixada (gravado em {at}, America/Recife)",
        "",
        f"repositório: {S.REPO_URL}",
        f"tag: {S.tag()}  commit: {commit}  data do commit: {commit_date}",
        f"caminho no repositório: {S.DOCS_PREFIX}/  ->  copiado para {S.DOCS_PREFIX}/ nesta pasta",
        f"licença: {S.LICENSE}",
        f"pin: $BO_REPO/universe/pins.json provider google versão {S.version()} (sha256 do pins.json "
        f"{S.sha256_file(S.pins_path())})",
        "",
        "origem dos bytes: pré-busca $BO_DATA/downloads/prefetch/google/" + S.version() + "/docs "
        f"(MANIFEST.json sha256 {S.sha256_file(man)})",
        f"páginas: {len(files)} ({', '.join(f'{k}={v}' for k, v in sorted(by_dir.items()))})",
        "conferências:",
        "  1. sha256 de cada página igual ao do MANIFEST.json da pré-busca, sem página a mais ou a menos: CONFERE",
        f"  2. tag na API do GitHub aponta para o commit acima: {remote['tag_ref']['status']}",
        f"  3. amostra de {s['n']} páginas (1 a cada {s['step']}, ordem de caminho) baixada de raw.githubusercontent.com "
        f"no commit: {s['confere']} confere, {s['diverge']} diverge, {s['nao_conferido']} não conferida(s) -> {s['status']}",
        "  detalhe: fetch_verification.json; hashes da cópia: SHA256SUMS (formato shasum -a 256, relativo a esta pasta)",
        "",
        "segurança: as páginas são texto não confiável; nada delas foi executado. Nenhuma credencial, nenhuma nuvem.",
        "",
    ])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.docs_gcp.fetch")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    if a.verify:
        probs = verify_copy()
        for p in probs[:20]:
            print("  FAIL", p)
        print(f"cópia da documentação: {'confere' if not probs else f'{len(probs)} problema(s)'}")
        return 1 if probs else 0
    files = manifest_docs()
    commit, commit_date = S.tag_commit()
    probs = check_prefetch(files)
    if probs:
        for p in probs[:20]:
            print("  FAIL", p)
        print(f"pré-busca não confere ({len(probs)} problema(s)); nada copiado")
        return 1
    remote = check_remote(files, commit)
    if remote["tag_ref"]["status"] == "DIVERGE" or remote["sample"]["status"] == "DIVERGE":
        print("tag ou amostra DIVERGE do GitHub; nada copiado")
        print(json.dumps(remote["tag_ref"]))
        return 1
    S.download_dir().mkdir(parents=True, exist_ok=True)
    copy(files)
    write_sums(files)
    at = core.now()
    ver = {"module": S.MODULE, "generated_at": at, "repo": S.REPO, "tag": S.tag(), "commit": commit,
           "commit_date": commit_date, "n_files": len(files), "prefetch_manifest_ok": True, **remote}
    (S.download_dir() / "fetch_verification.json").write_text(
        json.dumps(ver, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (S.download_dir() / "SOURCE.txt").write_text(source_txt(files, commit, commit_date, remote, at), encoding="utf-8")
    probs = verify_copy()
    print(f"[{at}] {len(files)} páginas copiadas para {S.download_dir()}; tag {remote['tag_ref']['status']}; "
          f"amostra {remote['sample']['confere']}/{remote['sample']['n']} {remote['sample']['status']}; "
          f"cópia {'confere' if not probs else 'NÃO confere'}")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
