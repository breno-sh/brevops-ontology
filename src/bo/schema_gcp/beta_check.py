"""Causa das páginas do índice do Registry sem tipo no schema do google: são recursos só do google-beta?

  python -I -m bo.schema_gcp.beta_check [--extract]

O bo.schema.crosscheck (SCHEMALIB) não conhece a causa "página de recurso só do google-beta" e reprova: a
documentação do google e do google-beta é uma só (Magic Modules) e o índice do hashicorp/google lista as páginas
beta. Este comando NÃO muda o veredito do crosscheck; ele só mede a causa, com três provas independentes por
página sem tipo:
  em_google_beta     o tipo existe no schema do google-beta da MESMA versão (binário assinado, extraído pela
                     biblioteca, bo.schema.extract, no mesmo sandbox sem credenciais); página *_iam = algum dos
                     tipos _iam_member/_binding/_policy no google-beta;
  aviso_beta         a página (docs do repositório na tag da versão, pré-busca) traz o aviso "in beta, and should
                     be used with the terraform-provider-google-beta provider";
  exemplo_beta       a página tem exemplo com 'provider = google-beta'.
E o controle: tipos do google que TÊM página com aviso beta (aviso que não corresponde ao schema).
Saída: $BO_DATA/SCHEMA-GCP/crosscheck_beta_google-<versão>.json (sem data de geração: regenerar dá os mesmos bytes).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bo.schema import core, lockfile
from bo.schema import extract as X

from . import common as C

BETA_ADDRESS = "registry.terraform.io/hashicorp/google-beta"
WARNING = re.compile(r"(is|are) in beta,? and should be used with the terraform-provider-google-beta provider", re.I)
EXAMPLE = re.compile(r"^\s*provider\s*=\s*google-beta\s*$", re.M)
IAM_SUFFIXES = ("_iam_member", "_iam_binding", "_iam_policy")


def beta_dir(version: str) -> Path:
    return C.bo_data() / "downloads" / f"google-beta-{version}"


def beta_lock(version: str, cache: Path | None = None) -> Path:
    """Lock do google-beta: zh: do SHA256SUMS baixado (o init confere a assinatura do release) e, se o pacote já
    estiver desempacotado no cache (depois de um init que o conferiu contra os zh:), o h1 da pasta dele."""
    d = beta_dir(version)
    sums = d / f"terraform-provider-google-beta_{version}_SHA256SUMS"
    pref = f"terraform-provider-google-beta_{version}_"
    zh = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        sha, fname = line.split("  ")
        if not fname.startswith(pref):
            raise C.PinError(f"SHA256SUMS do google-beta com arquivo de outro release: {fname}")
        if fname.endswith(".zip"):
            zh.append(f"zh:{sha}")
    reg = json.loads((d / "registry-download-darwin_arm64.json").read_text(encoding="utf-8"))
    if f"zh:{reg['shasum']}" not in zh:
        raise C.PinError("shasum do registro do google-beta fora do SHA256SUMS")
    hashes = list(zh)
    pdir = (cache or X.default_cache()) / BETA_ADDRESS / version / C.OS_ARCH
    if pdir.is_dir():
        hashes.append(C.dirhash_h1(pdir))
    lp = lockfile.LockedProvider(BETA_ADDRESS, version, version, tuple(sorted(hashes)))
    return C.write_lock(lp, C.bo_tmp() / "beta" / "terraform.lock.hcl")


def prime_cache(version: str) -> None:
    """terraform init (rede só para o registro) com o lock só de zh:: baixa, confere e desempacota no cache."""
    lp = lockfile.find(lockfile.read(beta_lock(version)), "hashicorp/google-beta")
    tf = Path(X.shutil.which("terraform") or "").resolve()
    work = C.bo_tmp() / "beta" / "prime"
    if work.exists():
        X.shutil.rmtree(work)
    cache = X.default_cache()
    for d in (work / "home", work / "tmp", cache):
        d.mkdir(parents=True, exist_ok=True)
    (work / "home" / "terraformrc").write_text("", encoding="utf-8")
    (work / "versions.tf").write_text(X.versions_tf(lp), encoding="utf-8")
    (work / ".terraform.lock.hcl").write_text(lockfile.render([lp]), encoding="utf-8")
    r = X.run_sandboxed([str(tf), "init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"],
                        work, cache, tf, network=True, capture=True)
    if r.returncode:
        raise SystemExit(f"beta_check: init do google-beta falhou: {(r.stderr or b'').decode()[-800:]}")


def beta_schema_path(version: str) -> Path:
    return C.bo_data() / "downloads" / "tfschema" / f"google-beta-{version}" / "schema.json.gz"


def doc_file(version: str, slug: str) -> Path:
    return C.prefetch_dir(version) / "docs" / "r" / f"{slug}.html.markdown"


def analyse(xc: dict, ga_types: set[str], beta_types: set[str], index: dict, version: str) -> dict:
    pages = []
    slugs = {}
    for d in index.get("docs") or []:
        if d.get("category") == "resources" and d.get("language") == "hcl":
            s = d["slug"]
            slugs[s if s.startswith("google_") else "google_" + s] = s
    for p in xc["paginas_sem_tipo"]:
        text = doc_file(version, slugs[p]).read_text(encoding="utf-8")
        cands = [p + s[len("_iam"):] for s in IAM_SUFFIXES] if p.endswith("_iam") else [p]
        in_beta = sorted(t for t in cands if t in beta_types)
        pages.append({"pagina": p, "em_google_beta": bool(in_beta), "tipos_google_beta": in_beta,
                      "aviso_beta": bool(WARNING.search(text)), "exemplo_beta": bool(EXAMPLE.search(text))})
    warned_ga = []
    for name, slug in sorted(slugs.items()):
        f = doc_file(version, slug)
        if name in xc["paginas_sem_tipo"] or not f.exists():
            continue
        if WARNING.search(f.read_text(encoding="utf-8")):
            cands = [name + s[len("_iam"):] for s in IAM_SUFFIXES] if name.endswith("_iam") else [name]
            warned_ga.append({"pagina": name, "tipos_google": sorted(t for t in cands if t in ga_types)})
    n = len(pages)
    return {
        "schema": "bo.schema_gcp.beta_check/1", "module": C.ID, "provider_version": version,
        "crosscheck_veredito": xc["veredito"], "paginas_sem_tipo": n, "tipos_sem_pagina": len(xc["tipos_sem_pagina"]),
        "google_tipos": len(ga_types), "google_beta_tipos": len(beta_types),
        "google_tipos_fora_do_beta": sorted(ga_types - beta_types),
        "contagens": {"em_google_beta": sum(x["em_google_beta"] for x in pages),
                      "aviso_beta": sum(x["aviso_beta"] for x in pages),
                      "exemplo_beta": sum(x["exemplo_beta"] for x in pages),
                      "sem_aviso_beta": [x["pagina"] for x in pages if not x["aviso_beta"]],
                      "fora_do_google_beta": [x["pagina"] for x in pages if not x["em_google_beta"]]},
        "controle_aviso_beta_com_tipo_no_google": warned_ga,
        "conclusao": ("todas as páginas sem tipo são tipos do google-beta da mesma versão"
                      if n and all(x["em_google_beta"] for x in pages) else
                      "há página sem tipo que também não está no google-beta"),
        "paginas": pages,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema_gcp.beta_check", description=__doc__.split("\n")[0])
    ap.add_argument("--extract", action="store_true", help="extrai o schema do google-beta (rede só no init)")
    a = ap.parse_args(argv)
    pin = C.read_pin()
    v = pin["version"]
    bschema = beta_schema_path(v)
    if a.extract or not bschema.exists():
        prime_cache(v)
        X.extract("hashicorp/google-beta", beta_lock(v), out=bschema.parent, version=v)
    xc = json.loads((C.out_dir() / f"crosscheck_{C.PROVIDER}-{v}.json").read_text(encoding="utf-8"))
    index = json.loads(Path(xc["index"]).read_text(encoding="utf-8"))
    ga = {json.loads(l)["resource_type"] for l in open(C.out_dir() / "types.jsonl", encoding="utf-8") if l.strip()}
    beta = set((core.providers(core.load(bschema))["google-beta"].get("resource_schemas") or {}))
    rep = analyse(xc, ga, beta, index, v)
    rep["fontes"] = {"google_beta_schema_sha256": C.read_sha_file(bschema.parent / "schema.json.sha256"),
                     "google_beta_schema": C.portable(bschema), "indice": C.portable(xc["index"]),
                     "docs": C.portable(C.prefetch_dir(v) / "docs" / "r")}
    out = C.out_dir() / f"crosscheck_beta_{C.PROVIDER}-{v}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = rep["contagens"]
    print(f"beta_check {v}: {rep['paginas_sem_tipo']} páginas sem tipo; no google-beta {c['em_google_beta']}, "
          f"aviso beta {c['aviso_beta']}, exemplo beta {c['exemplo_beta']}; aviso beta em página com tipo GA "
          f"{len(rep['controle_aviso_beta_com_tipo_no_google'])}; {rep['conclusao']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
