"""Gate G1 do PRIOR: todo modelo tem SOURCE com licença e sha, ou a marca 'só documental' com a referência.

  python -I -m bo.prior.check

Para cada modelo do índice {model} do modulos.json confere: as quatro saídas existem (e METHOD_NOTES.html no
kalinin); o SOURCE.txt de artefato tem licença (não NOASSERTION), commit de 40 hex e linhas 'sha256  caminho' cujos
arquivos existem com aquele sha256 hoje; o de 'só documental' tem a marca, a referência e as buscas feitas; o
status e a licença batem com sources.MODELS; o provider_links.sssom.tsv passa no C09 3.0.0 (bo.contracts.validate);
modelo documental só tem vínculo afirmado em texto ou ausência declarada; os cabeçalhos dos CSV são os do build.
Sai 0 só se tudo confere.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path

from bo.contracts import validate as V

from . import sources as S
from .build import CLASS_COLS, PROP_COLS
from .common import bo_data, sha256_file

SHA_LINE = re.compile(r"^([0-9a-f]{64})  (\S.*)$")
COMMIT = re.compile(r"\b[0-9a-f]{40}\b")
NOTES_MUST = ("6 passos", "4 camadas", "5 perguntas de competência", "CloudQuery", "CSPM", "HermiT", "owlready2",
              "SWRL", "só documental", "artefato ontológico não está disponível")


def catalog_models() -> list[str]:
    p = Path(os.environ.get("BO_MODULES") or
             "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json")
    try:
        return list(json.loads(p.read_text(encoding="utf-8"))["index_sets"]["model"])
    except (OSError, KeyError, ValueError):
        return list(S.ORDER)


def _expand(path: str) -> Path:
    return Path(path.replace("$BO_DATA", str(bo_data()), 1)) if path.startswith("$BO_DATA") else Path(path)


def check_model(model: str, root: Path) -> list[str]:
    errs = []
    m = S.MODELS.get(model)
    if m is None:
        return [f"modelo {model} do catálogo não está em sources.MODELS"]
    d = root / model
    need = ["classes.csv", "properties.csv", "provider_links.sssom.tsv", "SOURCE.txt"]
    if model == "kalinin":
        need.append("METHOD_NOTES.html")
    for f in need:
        if not (d / f).is_file() or (d / f).stat().st_size == 0:
            errs.append(f"{f} ausente ou vazio")
    if errs:
        return errs
    src = (d / "SOURCE.txt").read_text(encoding="utf-8").splitlines()
    kv = {}
    for ln in src:
        k, sep, v = ln.partition(": ")
        if sep and k in ("status", "referência", "licença", "repositório", "commit"):
            kv.setdefault(k, v.strip())
    status = kv.get("status", "")
    lic = kv.get("licença", "").split(" ", 1)[0]
    if lic != m["license"]:
        errs.append(f"licença do SOURCE ({lic!r}) != sources.MODELS ({m['license']!r})")
    shas = [SHA_LINE.match(ln) for ln in src]
    shas = [x for x in shas if x]
    for x in shas:
        p = _expand(x.group(2))
        if not p.is_file():
            errs.append(f"arquivo listado não existe: {x.group(2)}")
        elif sha256_file(p) != x.group(1):
            errs.append(f"sha256 não confere: {x.group(2)}")
    if m["status"] == "documental":
        if status != S.DOCUMENTAL or S.DOCUMENTAL not in "\n".join(src):
            errs.append(f"modelo sem artefato sem a marca '{S.DOCUMENTAL}'")
        if len(kv.get("referência", "")) < 20:
            errs.append("'só documental' sem referência")
        if not any(ln.startswith("busca: ") for ln in src):
            errs.append("'só documental' sem registro das buscas pelo artefato")
    else:
        if status != "artefato":
            errs.append(f"status {status!r} != 'artefato'")
        if lic in ("", "NOASSERTION"):
            errs.append("artefato sem licença declarada")
        if not COMMIT.search(kv.get("commit", "")):
            errs.append("artefato sem commit de 40 hex")
        if not shas:
            errs.append("artefato sem nenhuma linha 'sha256  caminho'")
        if m["fetch"]:
            dl_line = next((ln for ln in src if ln.startswith("download: ")), "")
            mm = re.search(r"download: (\S+) sha256 ([0-9a-f]{64})", dl_line)
            if not mm:
                errs.append("artefato baixado sem a linha 'download:' do fetch_manifest")
            else:
                fm = _expand(mm.group(1))
                if not fm.is_file() or sha256_file(fm) != mm.group(2):
                    errs.append("fetch_manifest.json ausente ou mudou")
                else:
                    man = json.loads(fm.read_text(encoding="utf-8"))
                    for f in man["files"]:
                        if f.get("archive"):
                            continue
                        p = fm.parent / f["path"]
                        if not p.is_file() or sha256_file(p) != f["sha256"]:
                            errs.append(f"download mudou ou sumiu: {f['path']}")
                            break
    r = V.validate("correspondences", d / "provider_links.sssom.tsv")
    if not r.ok:
        errs += [f"C09: {e}" for e in r.errors[:5]]
    links = [ln for ln in (d / "provider_links.sssom.tsv").read_text(encoding="utf-8").splitlines()
             if ln and not ln.startswith("#")]
    head = links[0].split("\t")
    ci = head.index("curation_rule")
    rules = [ln.split("\t")[ci] for ln in links[1:]]
    if m["status"] == "documental":
        bad = [x for x in rules if not (x.startswith("bo:prior/text:") or x.startswith("bo:prior/sssom:NoTermFound"))]
        if bad:
            errs.append(f"modelo só documental com vínculo que não é de texto nem ausência: {bad[0]}")
    else:
        if any(x.startswith("bo:prior/text:") for x in rules):
            errs.append("modelo com artefato tem vínculo marcado como só de texto")
    for f, cols in (("classes.csv", CLASS_COLS), ("properties.csv", PROP_COLS)):
        with open(d / f, encoding="utf-8", newline="") as fh:
            h = next(csv.reader(fh), [])
        if h != cols:
            errs.append(f"{f}: cabeçalho fora do formato do build")
    if model == "kalinin":
        t = (d / "METHOD_NOTES.html").read_text(encoding="utf-8")
        miss = [k for k in NOTES_MUST if k not in t]
        if miss:
            errs.append(f"METHOD_NOTES.html sem: {', '.join(miss)}")
    return errs


def main(argv=None) -> int:
    root = bo_data() / "PRIOR"
    models = catalog_models()
    bad = 0
    extra = sorted(set(S.MODELS) - set(models))
    if extra:
        print(f"FAIL modelos fora do índice {{model}} do catálogo: {extra}")
        bad += 1
    for model in models:
        errs = check_model(model, root)
        m = S.MODELS.get(model, {})
        tag = S.DOCUMENTAL if m.get("status") == "documental" else f"artefato {m.get('license', '?')}"
        if errs:
            bad += 1
            print(f"FAIL {model:13s} {tag}")
            for e in errs:
                print(f"       {e}")
        else:
            print(f"OK   {model:13s} {tag}")
    print("RESULTADO: " + ("OK" if not bad else f"REPROVADO ({bad})") + f" — {len(models)} modelo(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
