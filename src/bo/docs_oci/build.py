"""DOCS-OCI: páginas r/ e d/ da documentação oficial do oci (tag do PINS) -> três saídas.

  $BO_DATA/DOCS-OCI/docs_facts.jsonl        C03 docs_facts: fatos por átomo (descrição, default, valores
                                            válidos, faixa, unidade, formato, depreciação, required_when,
                                            conflicts_with, ForceNew, exemplo, behavior), com sentença de origem
  $BO_DATA/DOCS-OCI/type_subcategory.jsonl  por tipo (recurso e data source): subcategoria do front matter,
                                            aliases e ID de importação, com a linha de origem
  $BO_REPO/results/DOCS-OCI/coverage.json   C15 result: % de átomos com descrição, valores válidos e unidade

  python -I -m bo.docs_oci.build            gera as três
  python -I -m bo.docs_oci.build --check    gera em $BO_TMP e compara byte a byte (coverage.json sem generated_at)

Átomos = os do C01 (bo.schema.core) sobre o schema do 'terraform providers schema -json' do oci na versão do
PINS, conferido pelo schema_sha256 do pins.json. Um item da doc casa com um átomo só por caminho exato
(tipo + nomes de bloco + nome); o resto é contado por motivo (bloco, filho de atributo objeto, fora do schema).
Trechos que o privacy_lint reprovaria (ocid1., e-mail, 12 dígitos, dinheiro, ...) são trocados por
'[redigido]' na sentença e no valor, e contados.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from bo.repo import privacy
from bo.schema import core as schema_core

from . import extract, parse, source

MODULE = "DOCS-OCI"
REDACTED = "[redigido]"
COV_KINDS = ("description", "allowed_values", "unit")


def out_dir() -> Path:
    return source.bo_data() / MODULE


def results_dir() -> Path:
    return source.bo_repo() / "results" / MODULE


def schema_path(ver: str) -> Path:
    return source.prefetch_dir(ver) / "providers-schema.json"


def load_schema(ver: str) -> dict:
    p = schema_path(ver)
    got = source.sha256_file(p)
    want = source.pin()["schema_sha256"]
    if got != want:
        raise SystemExit(f"schema do oci {ver}: sha256 {got} != schema_sha256 do pins.json {want}")
    doc = schema_core.load(p)
    return schema_core.providers(doc)["oci"]


# ------------------------------------------------------------------ privacidade
def redact(s: str, counter: Counter) -> str:
    if not isinstance(s, str) or not s:
        return s
    out = s
    for hit in privacy.twelve_digit_hits(out):
        out = out.replace(hit, REDACTED)
        counter["doze_digitos"] += 1
    for rule, rx in privacy.RULES:
        def sub(m, rule=rule):
            if rule == "email" and privacy.ALLOWED_EMAIL_DOMAINS.search(m.group(0)):
                return m.group(0)
            counter[rule] += 1
            return REDACTED
        out = rx.sub(sub, out)
    return out


def redact_value(v, counter: Counter):
    if isinstance(v, str):
        return redact(v, counter)
    if isinstance(v, list):
        return [redact_value(x, counter) for x in v]
    if isinstance(v, dict):
        return {k: redact_value(x, counter) for k, x in v.items()}
    if isinstance(v, (int, float)) and not isinstance(v, bool) and privacy.twelve_digit_hits(json.dumps(v)):
        # número de 12 dígitos seguidos (ex.: um limite 99...9) reprova no privacy_lint mesmo sendo da doc
        counter["doze_digitos"] += 1
        return REDACTED
    return v


# ------------------------------------------------------------------ páginas
def load_pages(kind: str) -> list:
    root = source.docs_root()
    pages = []
    for p in sorted((root / "website" / "docs" / kind).glob("*.markdown")):
        rel = str(p.relative_to(root))
        pages.append(parse.parse(p.read_text(encoding="utf-8"), rel))
    return pages


def classify_unmatched(path: tuple, atom_paths: set, block_paths: set) -> str:
    p = ".".join(path)
    if p in block_paths:
        return "bloco_do_schema"
    for i in range(1, len(path)):
        if ".".join(path[:i]) in atom_paths:
            return "filho_de_atributo_objeto"
    return "fora_do_schema"


def build(dest_facts: Path, dest_types: Path, dest_cov: Path) -> dict:
    ver = source.version()
    tag = source.tag()
    commit = json.loads((source.download_dir() / "upstream" / "commit.json").read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(commit["commit_date"]).astimezone(source.TZ).date().isoformat()
    ps = load_schema(ver)
    types = {ts.resource_type: ts for ts in schema_core.iter_types(ps, "oci", ver)}
    ds_names = set((ps.get("data_source_schemas") or {}).keys())

    r_pages = load_pages("r")
    d_pages = load_pages("d")
    stats: dict = {"unmatched": Counter(), "unmatched_by_section": Counter(), "items": Counter(),
                   "required_flag_disagree": 0, "optional_flag_disagree": 0, "redacted": Counter(),
                   "pages_without_type": [], "duplicate_pages": [], "alias_applied": [], "title_mismatch": []}

    # página -> tipo; tipos com página própria
    page_of: dict = {}
    for pg in r_pages:
        if parse.title_mismatch(pg):
            stats["title_mismatch"].append(pg.file)
        rt = parse.resource_type_of(pg, set(types))
        if rt not in types:
            stats["pages_without_type"].append(pg.file)
            continue
        if rt in page_of:
            stats["duplicate_pages"].append(pg.file)
            continue
        page_of[rt] = pg
    alias_of: dict = {}
    for rt, pg in sorted(page_of.items()):
        for al, _ in pg.aliases:
            if al in types and al not in page_of:
                alias_of[al] = rt
                stats["alias_applied"].append(f"{al} <- {rt}")

    facts_by_atom: dict = defaultdict(list)
    for rt in sorted(types):
        doc_rt = rt if rt in page_of else alias_of.get(rt)
        if not doc_rt:
            continue
        pg = page_of[doc_rt]
        ts = types[rt]
        atoms = {a["path"]: a for a in ts.atoms}
        blocks = {".".join(b.path) for b in ts.blocks}
        top_names = {a["path"].split(".")[-1] for a in ts.atoms}
        for it in pg.items:
            if rt == doc_rt:
                stats["items"][it.section] += 1
            p = ".".join(it.path)
            a = atoms.get(p)
            if a is None:
                if rt == doc_rt:
                    why = classify_unmatched(it.path, set(atoms), blocks)
                    stats["unmatched"][why] += 1
                    stats["unmatched_by_section"][f"{it.section}:{why}"] += 1
                continue
            if rt == doc_rt and it.section == "arguments":
                if "Required" in it.markers and not a["required"]:
                    stats["required_flag_disagree"] += 1
                if "Optional" in it.markers and a["required"]:
                    stats["optional_flag_disagree"] += 1
            fs = extract.extract_item(it, a, pg, top_names)
            for f in fs:
                f["file"] = pg.file
                if rt != doc_rt:
                    f["evidence_level"] = "derived"
            facts_by_atom[a["atom_id"]].extend(fs)

    records = []
    n_atoms = 0
    atom_has: dict = {k: set() for k in COV_KINDS}
    atom_has_pub_unit = set()
    configurable = set()
    for rt in sorted(types):
        for a in sorted(types[rt].atoms, key=lambda x: x["path"]):
            n_atoms += 1
            aid = a["atom_id"]
            if a["configurable"]:
                configurable.add(aid)
            fs = extract.reconcile(facts_by_atom.get(aid, []))
            if not any(f["fact_kind"] == "description" and f["status"] == "stated" for f in fs):
                if not any(f["fact_kind"] == "description" for f in fs):
                    fs.insert(0, {"fact_kind": "description", "status": "unknown", "unknown_reason": "not_documented",
                                  "extraction_method": "parser", "evidence_level": "published"})
            seq = Counter()
            for f in fs:
                k = f["fact_kind"]
                seq[k] += 1
                rec = {
                    "fact_id": f"DF-oci:{rt}:{a['path']}:{k}:{seq[k]}",
                    "atom_id": aid,
                    "provider_version": ver,
                    "fact_kind": k,
                    "status": f["status"],
                    "extraction_method": f["extraction_method"],
                    "evidence_level": f["evidence_level"],
                }
                if f["status"] == "stated":
                    rec["value"] = redact_value(f["value"], stats["redacted"])
                    if k in atom_has:
                        atom_has[k].add(aid)
                    if k == "unit" and f["evidence_level"] == "published":
                        atom_has_pub_unit.add(aid)
                else:
                    rec["unknown_reason"] = f["unknown_reason"]
                if k == "default" and f["status"] == "stated":
                    rec["as_of"] = as_of
                if "line" in f:
                    sent = redact(f["sentence"], stats["redacted"])
                    rec["source"] = {"repo": source.REPO, "tag": tag, "file": f["file"], "line": f["line"],
                                     "sentence": sent}
                records.append(rec)

    dest_facts.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_facts, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    # ---------------------------------------------------------- subcategoria e importação por tipo
    trecs = type_records(types, ds_names, page_of, alias_of, d_pages, ver, tag, stats)
    dest_types.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_types, "w", encoding="utf-8") as fh:
        for r in trecs:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    cov = coverage_doc(records, n_atoms, configurable, atom_has, atom_has_pub_unit, trecs, stats, ver,
                       r_pages, d_pages, types, page_of)
    dest_cov.parent.mkdir(parents=True, exist_ok=True)
    dest_cov.write_text(json.dumps(cov, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return cov


def _src(pg, line: int, sentence: str, tag: str, red: Counter) -> dict:
    return {"repo": source.REPO, "tag": tag, "file": pg.file, "line": line, "sentence": redact(sentence, red)}


def import_info(pg, tag: str, red: Counter) -> dict:
    if not pg.import_cmds:
        if pg.import_text:
            n, t = pg.import_text[0]
            return {"status": "unknown", "unknown_reason": "ambiguous", "source": _src(pg, n, t, tag, red),
                    "extraction_method": "parser", "evidence_level": "published"}
        return {"status": "unknown", "unknown_reason": "not_documented", "extraction_method": "parser",
                "evidence_level": "published"}
    n, addr, raw = pg.import_cmds[0]
    idf = raw.strip()
    if len(idf) >= 2 and idf[0] == idf[-1] and idf[0] in "\"'":
        idf = idf[1:-1]
    sent = pg.import_text[0][1] if pg.import_text else f"terraform import {addr} {raw}"
    out = {"status": "stated", "id_format": redact(idf, red), "id_is_plain_id": idf == "id",
           "placeholders": re.findall(r"\{([A-Za-z0-9_]+)\}", idf),
           "source": _src(pg, n, f"terraform import {addr} {raw}", tag, red),
           "extraction_method": "parser", "evidence_level": "published"}
    if pg.import_text:
        out["statement"] = _src(pg, pg.import_text[0][0], sent, tag, red)
    return out


def type_records(types, ds_names, page_of, alias_of, d_pages, ver, tag, stats) -> list:
    red = stats["redacted"]
    out = []
    for rt in sorted(types):
        doc_rt = rt if rt in page_of else alias_of.get(rt)
        rec = {"type_id": f"oci:{rt}", "provider": "oci", "provider_version": ver, "resource_type": rt,
               "kind": "resource"}
        if not doc_rt:
            rec["subcategory"] = {"status": "unknown", "unknown_reason": "not_documented",
                                  "extraction_method": "parser", "evidence_level": "published"}
            rec["import"] = {"status": "unknown", "unknown_reason": "not_documented",
                             "extraction_method": "parser", "evidence_level": "published"}
            out.append(rec)
            continue
        pg = page_of[doc_rt]
        ev = "published" if doc_rt == rt else "derived"
        if doc_rt != rt:
            rec["documented_as_alias_of"] = doc_rt
        rec["doc_file"] = pg.file
        rec["aliases"] = [a for a, _ in pg.aliases] if doc_rt == rt else []
        sc = pg.front.get("subcategory")
        if sc and sc[0]:
            rec["subcategory"] = {"status": "stated", "value": sc[0],
                                  "source": _src(pg, sc[1], f'subcategory: "{sc[0]}"', tag, red),
                                  "extraction_method": "parser", "evidence_level": ev}
        else:
            rec["subcategory"] = {"status": "unknown", "unknown_reason": "not_documented",
                                  "extraction_method": "parser", "evidence_level": ev}
        imp = import_info(pg, tag, red)
        if doc_rt != rt:
            imp["evidence_level"] = "derived"
        rec["import"] = imp
        out.append(rec)
    # data sources: só subcategoria (não têm importação nem átomos no C01)
    dpage = {}
    for pg in d_pages:
        rt = parse.resource_type_of(pg, ds_names)
        if rt in ds_names and rt not in dpage:
            dpage[rt] = pg
    for rt in sorted(ds_names):
        rec = {"type_id": f"oci:{rt}", "provider": "oci", "provider_version": ver, "resource_type": rt,
               "kind": "data_source"}
        pg = dpage.get(rt)
        if pg is None:
            rec["subcategory"] = {"status": "unknown", "unknown_reason": "not_documented",
                                  "extraction_method": "parser", "evidence_level": "published"}
        else:
            rec["doc_file"] = pg.file
            sc = pg.front.get("subcategory")
            if sc and sc[0]:
                rec["subcategory"] = {"status": "stated", "value": sc[0],
                                      "source": _src(pg, sc[1], f'subcategory: "{sc[0]}"', tag, red),
                                      "extraction_method": "parser", "evidence_level": "published"}
            else:
                rec["subcategory"] = {"status": "unknown", "unknown_reason": "not_documented",
                                      "extraction_method": "parser", "evidence_level": "published"}
        out.append(rec)
    stats["data_pages_without_type"] = sorted(pg.file for pg in d_pages
                                              if parse.resource_type_of(pg, ds_names) not in ds_names)
    return out


# ------------------------------------------------------------------ cobertura (C15)
def _frac(k: int, n: int) -> float:
    return round(k / n, 6) if n else 0.0


def coverage_doc(records, n_atoms, configurable, atom_has, atom_has_pub_unit, trecs, stats, ver, r_pages, d_pages,
                 types, page_of) -> dict:
    sp = schema_path(ver)
    frame_ref = {"path": f"$BO_DATA/downloads/prefetch/oci/{ver}/providers-schema.json",
                 "sha256": source.sha256_file(sp)}
    names = {"description": "átomos do oci com descrição na documentação",
             "allowed_values": "átomos do oci com valores válidos (enum) na documentação",
             "unit": "átomos do oci com unidade na documentação (publicada ou derivada do nome)"}
    ids = {"description": "M-DOCS-OCI-DESC", "allowed_values": "M-DOCS-OCI-ENUM", "unit": "M-DOCS-OCI-UNIT"}
    metrics = []
    for k in COV_KINDS:
        f = _frac(len(atom_has[k]), n_atoms)
        metrics.append({
            "metric_id": ids[k], "name": names[k], "reading": "field", "axis": "representability",
            "quantifier": "observed_fraction",
            "operational_coverage": {"lower": f, "upper": f, "est": f, "n": n_atoms},
            "frame": {"ref": frame_ref, "description": f"todos os átomos C01 dos {len(types)} tipos de recurso do oci {ver}"},
            "inclusion": {"rule_id": "INC-DOCS-OCI-01",
                          "text": f"átomo com ao menos um fato C03 {k} com status stated"},
            "weights": {"scheme": "uniform"},
            "joint_uncertainty": {"method": "exact"},
        })
    by = Counter((r["fact_kind"], r["status"], r.get("unknown_reason") or r["evidence_level"]) for r in records)
    per_kind = defaultdict(dict)
    for (k, st, x), n in sorted(by.items()):
        per_kind[k][f"{st}:{x}"] = n
    cfg_n = len(configurable)
    data = {
        "provider": "oci", "provider_version": ver, "tag": source.tag(),
        "atoms": n_atoms, "atoms_configurable": cfg_n,
        "atoms_with": {k: len(v) for k, v in atom_has.items()},
        "atoms_with_unit_published_only": len(atom_has_pub_unit),
        "pct_atoms_with": {k: round(100 * _frac(len(v), n_atoms), 2) for k, v in atom_has.items()},
        "pct_configurable_atoms_with": {k: round(100 * _frac(len(v & configurable), cfg_n), 2)
                                        for k, v in atom_has.items()},
        "pct_atoms_with_unit_published_only": round(100 * _frac(len(atom_has_pub_unit), n_atoms), 2),
        "facts": len(records),
        "facts_by_kind": {k: dict(v) for k, v in sorted(per_kind.items())},
        "pages": {"r": len(r_pages), "d": len(d_pages)},
        "resource_types": len(types), "resource_types_with_page": len(page_of),
        "resource_types_documented_via_alias": len(stats["alias_applied"]),
        "resource_types_without_page": sum(1 for r in trecs if r["kind"] == "resource" and "doc_file" not in r),
        "r_pages_without_schema_type": stats["pages_without_type"],
        "r_pages_duplicate_type": stats["duplicate_pages"],
        "r_pages_title_differs_from_file": stats["title_mismatch"],
        "d_pages_without_schema_type": len(stats.get("data_pages_without_type", [])),
        "doc_items": dict(stats["items"]),
        "doc_items_unmatched": dict(stats["unmatched"]),
        "doc_items_unmatched_by_section": dict(stats["unmatched_by_section"]),
        "doc_required_but_schema_not_required": stats["required_flag_disagree"],
        "doc_optional_but_schema_required": stats["optional_flag_disagree"],
        "types_import_stated": sum(1 for r in trecs if r["kind"] == "resource" and r["import"]["status"] == "stated"),
        "types_import_plain_id": sum(1 for r in trecs if r["kind"] == "resource"
                                     and r["import"].get("id_is_plain_id")),
        "types_subcategory_stated": {kd: sum(1 for r in trecs if r["kind"] == kd and r["subcategory"]["status"] == "stated")
                                     for kd in ("resource", "data_source")},
        "subcategories": len({r["subcategory"]["value"] for r in trecs if r["subcategory"]["status"] == "stated"}),
        "redacted_spans": dict(stats["redacted"]),
    }
    return {
        "schema": "bo.result/1", "contract": "C15", "contract_version": "3.0.0", "module": MODULE,
        "generated_at": source.now(),
        "metrics": metrics,
        "notes": ("Relatado, sem meta. Censo dos átomos (sem amostragem): lower=upper=est. Fatos casados só por "
                  "caminho exato. 'unit' inclui unidade derivada do sufixo do nome (_in_gbs, ...); a fração só "
                  "publicada está em data. ForceNew do oci: '(Updatable)' -> forces_replacement=false (published); "
                  "sem '(Updatable)' e com a nota da página sobre destruição e recriação -> true (derived)."),
        "data": data,
    }


def comparable_cov(text: str) -> dict:
    d = json.loads(text)
    d.pop("generated_at", None)
    return d


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        tmp = source.bo_tmp() / "regen"
        tmp.mkdir(parents=True, exist_ok=True)
        cov = build(tmp / "docs_facts.jsonl", tmp / "type_subcategory.jsonl", tmp / "coverage.json")
        bad = []
        for name, real in (("docs_facts.jsonl", out_dir() / "docs_facts.jsonl"),
                           ("type_subcategory.jsonl", out_dir() / "type_subcategory.jsonl")):
            if not real.exists() or real.read_bytes() != (tmp / name).read_bytes():
                bad.append(str(real))
        realc = results_dir() / "coverage.json"
        if not realc.exists() or comparable_cov(realc.read_text(encoding="utf-8")) != comparable_cov(
                (tmp / "coverage.json").read_text(encoding="utf-8")):
            bad.append(str(realc))
        if bad:
            print("regeneração difere: " + ", ".join(bad), file=sys.stderr)
            return 1
        print(f"regeneração idêntica: {cov['data']['facts']} fatos, {cov['data']['atoms']} átomos")
        return 0
    cov = build(out_dir() / "docs_facts.jsonl", out_dir() / "type_subcategory.jsonl", results_dir() / "coverage.json")
    d = cov["data"]
    print(f"docs_facts: {d['facts']} fatos para {d['atoms']} átomos; % com descrição/enum/unidade: "
          f"{d['pct_atoms_with']['description']}/{d['pct_atoms_with']['allowed_values']}/{d['pct_atoms_with']['unit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
