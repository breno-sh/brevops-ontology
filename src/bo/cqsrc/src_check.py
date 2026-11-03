"""Gate do CQSRC: cada controle tem provedor, seção, título e fonte; o alinhamento só cita controles que existem.

  python -I -m bo.cqsrc.src_check [--controls CSV] [--cross CSV]

Confere cq/cis_controls.csv (cabeçalho, campos obrigatórios, provedor do index_set, número do item dentro da
seção, fonte = URL do arquivo no commit fixado com linha, unicidade, uma versão mais nova por provedor) e
cq/cis_cross_provider.csv (controles citados existem na versão mais nova com o mesmo número e título, par
coerente com os provedores e na ordem do index_set, predicado SKOS válido, proof_status UNPROVEN), além do
SOURCE.txt e do sha256 de cada tarball. Sai 0 só se nada reprova; imprime cada problema.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from . import build, concepts, extract, fetch, sources

PREDICATES = {"skos:closeMatch", "skos:broadMatch", "skos:narrowMatch", "skos:relatedMatch", "skos:exactMatch"}
REQUIRED = ("provider", "mod", "benchmark_id", "cis_version", "control_id", "cis_item_id", "section_id",
            "section_title", "title", "source_repo", "source_commit", "source_file", "source_line", "source_uri")


def check_controls(path: Path) -> tuple[list[str], dict]:
    probs: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        header = next(r, None)
        rows = [dict(zip(header or [], x)) | {"_n": len(x)} for x in r]
    if header != build.CONTROL_COLS:
        probs.append(f"{path.name}: cabeçalho difere do esperado")
        return probs, {}
    seen = set()
    latest: dict[str, set[str]] = {}
    index = {}
    for i, row in enumerate(rows, start=2):
        where = f"{path.name}:{i}"
        if row["_n"] != len(header):
            probs.append(f"{where}: {row['_n']} colunas, esperado {len(header)}")
            continue
        for k in REQUIRED:
            if not row[k].strip():
                probs.append(f"{where}: campo obrigatório vazio: {k}")
        p = row["provider"]
        if p not in concepts.PROVIDERS:
            probs.append(f"{where}: provedor fora do index_set: {p!r}")
            continue
        if concepts.MOD_OF[p] != row["mod"]:
            probs.append(f"{where}: mod {row['mod']!r} não é o do provedor {p}")
            continue
        repo, tag, commit = sources.MODS[row["mod"]][:3]
        if (row["source_repo"], row["source_tag"], row["source_commit"]) != (repo, tag, commit):
            probs.append(f"{where}: fonte não é o commit fixado")
        if not row["source_line"].isdigit() or int(row["source_line"]) < 1:
            probs.append(f"{where}: source_line inválida")
        else:
            want = sources.blob_url(row["mod"], row["source_file"], int(row["source_line"]))
            if row["source_uri"] != want:
                probs.append(f"{where}: source_uri não aponta para arquivo e linha no commit fixado")
        if not re.fullmatch(r"cis_v\d{3}/[^/]+\.(pp|sp)", row["source_file"]):
            probs.append(f"{where}: source_file fora de cis_vNNN/")
        item, sec = row["cis_item_id"].strip("."), row["section_id"]
        if sec and item and not (item == sec or item.startswith(sec + ".")):
            probs.append(f"{where}: item {item} fora da seção {sec}")
        if row["is_latest"] not in ("true", "false"):
            probs.append(f"{where}: is_latest inválido")
        key = (p, row["control_id"])
        if key in seen:
            probs.append(f"{where}: controle repetido {key}")
        seen.add(key)
        if row["is_latest"] == "true":
            latest.setdefault(p, set()).add(row["benchmark_id"])
            index[(p, row["control_id"])] = row
    for p in concepts.PROVIDERS:
        if len(latest.get(p, ())) != 1:
            probs.append(f"{path.name}: provedor {p} precisa de exatamente uma versão mais nova, achadas "
                         f"{sorted(latest.get(p, ()))}")
    return probs, {"rows": len(rows), "latest": index}


def check_cross(path: Path, latest: dict) -> tuple[list[str], int]:
    probs: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        header = next(r, None)
        rows = list(r)
    if header != build.CROSS_COLS:
        return [f"{path.name}: cabeçalho difere do esperado"], 0
    order = {p: i for i, p in enumerate(concepts.PROVIDERS)}
    seen = set()
    for i, x in enumerate(rows, start=2):
        where = f"{path.name}:{i}"
        if len(x) != len(header):
            probs.append(f"{where}: {len(x)} colunas")
            continue
        row = dict(zip(header, x))
        sp, op = row["subject_provider"], row["object_provider"]
        if sp not in order or op not in order or order[sp] >= order[op]:
            probs.append(f"{where}: par de provedores fora da ordem do index_set ({sp}, {op})")
            continue
        if concepts.PAIR_CODE[(sp, op)] != row["pair"]:
            probs.append(f"{where}: código de par {row['pair']} não bate com {sp}/{op}")
        for side, prov in (("subject", sp), ("object", op)):
            c = latest.get((prov, row[f"{side}_control_id"]))
            if c is None:
                probs.append(f"{where}: {side} {prov} {row[f'{side}_control_id']} não está na versão mais nova")
                continue
            if (c["cis_item_id"], c["title"], c["cis_version"]) != (row[f"{side}_cis_item_id"], row[f"{side}_title"],
                                                                     row[f"{side}_cis_version"]):
                probs.append(f"{where}: {side} difere do controle extraído (número, título ou versão)")
        if row["predicate"] not in PREDICATES:
            probs.append(f"{where}: predicado inválido {row['predicate']!r}")
        if row["proof_status"] != "UNPROVEN":
            probs.append(f"{where}: proof_status {row['proof_status']!r} sem prova registrada (só UNPROVEN)")
        if row["predicate"] == "skos:exactMatch":
            probs.append(f"{where}: exactMatch exige prova que este módulo não tem")
        if row["domain"] not in ("CMP", "NET", "STO", "DB", "SEC", "OPS"):
            probs.append(f"{where}: domínio fora do index_set")
        if not row["concept_id"] or not row["concept_label"]:
            probs.append(f"{where}: conceito sem id ou rótulo")
        k = (row["concept_id"], row["subject_control_id"], row["object_control_id"])
        if k in seen:
            probs.append(f"{where}: linha repetida {k}")
        seen.add(k)
    return probs, len(rows)


def check_sources() -> list[str]:
    probs = []
    for mod, (_, _, _, _, pin) in sources.MODS.items():
        arc = sources.archive_path(mod)
        st = arc.parent / "SOURCE.txt"
        if not arc.exists():
            probs.append(f"fonte ausente: {arc}")
            continue
        if fetch.sha256(arc) != pin:
            probs.append(f"sha256 do tarball de {mod} difere do fixado")
        if not st.exists() or st.read_text(encoding="utf-8") != sources.source_txt(mod):
            probs.append(f"SOURCE.txt de {mod} ausente ou diferente")
    return probs


def check_source_lines(path: Path) -> list[str]:
    """A linha citada em cada controle abre, no tarball fixado, o bloco com aquele nome."""
    probs = []
    texts = {}
    for mod in sources.MODS:
        dirs, _ = extract.read_mod(sources.archive_path(mod))
        texts[mod] = {rel: t.splitlines() for d in dirs.values() for rel, t in d.items()}
    with open(path, encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            lines = texts.get(row.get("mod", ""), {}).get(row.get("source_file", ""))
            n = row.get("source_line", "")
            if lines is None or not n.isdigit() or not 1 <= int(n) <= len(lines):
                probs.append(f"{path.name}:{i}: arquivo ou linha de origem não existe no tarball")
                continue
            if not re.match(r'\s*(control|benchmark)\s+"' + re.escape(row["control_id"]) + '"', lines[int(n) - 1]):
                probs.append(f"{path.name}:{i}: a linha {n} de {row['source_file']} não abre {row['control_id']}")
    return probs


def main(argv=None) -> int:
    root = build.repo_root()
    ap = argparse.ArgumentParser(prog="bo.cqsrc.src_check")
    ap.add_argument("--controls", default=str(root / "cq" / "cis_controls.csv"))
    ap.add_argument("--cross", default=str(root / "cq" / "cis_cross_provider.csv"))
    ap.add_argument("--no-sources", action="store_true", help="não confere os tarballs (só nos testes)")
    a = ap.parse_args(argv)
    probs = []
    cpath, xpath = Path(a.controls), Path(a.cross)
    for p in (cpath, xpath):
        if not p.is_file():
            probs.append(f"arquivo ausente: {p}")
    if probs:
        for p in probs:
            print("FALHA", p)
        return 1
    pc, info = check_controls(cpath)
    px, nx = check_cross(xpath, info.get("latest", {}))
    ps = [] if a.no_sources else check_sources()
    if not a.no_sources and not ps:
        ps = check_source_lines(cpath)
    probs = pc + px + ps
    for p in probs[:200]:
        print("FALHA", p)
    if len(probs) > 200:
        print(f"... e mais {len(probs) - 200}")
    print(f"src_check: {info.get('rows', 0)} controle(s), {nx} linha(s) de alinhamento, "
          f"{len(sources.MODS)} fonte(s); {len(probs)} problema(s)")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
