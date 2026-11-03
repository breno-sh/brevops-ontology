"""DOCS-AZURE: páginas r/ do azurerm na tag fixada -> docs_facts.jsonl (C03), type_subcategory.jsonl e coverage.

  python -I -m bo.docs_azure.build            gera $BO_DATA/DOCS-AZURE/{docs_facts,type_subcategory}.jsonl,
                                              build_report.json e results/DOCS-AZURE/coverage.json
  python -I -m bo.docs_azure.build --check    regenera em $BO_TMP e exige bytes idênticos (regeneração idêntica)
  python -I -m bo.docs_azure.build --manifest só regrava results/DOCS-AZURE/MANIFEST.sha256

Universo de átomos: o schema fixado (providers-schema.json, sha256 = pins.json) lido com a biblioteca única
bo.schema.core (a mesma do SCHEMA-AZURE), só resource_schemas. Cada página r/<x>.html.markdown é o tipo
azurerm_<x>. Seção de bloco -> caminho no schema: pelo nome; se o nome aparece em mais de um lugar, pela dica
'within `pai`' da abertura e depois pela árvore da própria página (o item que cita o bloco diz quem é o pai);
se ainda sobrar mais de um caminho sem a página distinguir, o fato vai para todos com evidence=derived.
Átomo sem item na página -> description unknown/not_documented; átomo numérico sem unidade -> unit
unknown/not_documented. Texto que o privacy_lint reprovaria é redigido ('[REDIGIDO:<regra>]') e contado.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bo.repo import privacy
from bo.schema import core as schema_core

from . import extract as X
from . import markdown as MD
from . import source as SRC

MODULE = "DOCS-AZURE"
KEEP_FROM_NOTES = {"forces_replacement", "deprecation", "conflicts_with", "required_when"}
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
SUB_GUID = re.compile(r"(/subscriptions/)" + GUID.pattern, re.I)
GUID_DIGITS = re.compile(r"\b[0-9a-fA-F]{4,8}(?:-[0-9a-fA-F]{4}){1,3}-\d{12}\b")   # inclui GUIDs malformados
NOTE_HEAD = re.compile(r"^\*\*\s*(?:Note|NOTE|Warning|WARNING|Important|IMPORTANT)\s*:?\s*\*\*\s*:?\s*")


def out_dir() -> Path:
    return SRC.bo_data() / MODULE


def results_dir() -> Path:
    return SRC.bo_repo() / "results" / MODULE


# ---------------------------------------------------------------------------------------- redação
class Redactor:
    def __init__(self):
        self.count = Counter()

    def text(self, s: str) -> str:
        if not isinstance(s, str):
            return s
        s2 = SUB_GUID.sub(r"\1{subscriptionId}", s)
        if s2 != s:
            self.count["guid_assinatura_normalizado"] += 1
        s = s2
        # GUID de exemplo cujo último grupo é só dígitos (o lint lê como 12 dígitos de conta) -> {guid}
        s2 = GUID_DIGITS.sub("{guid}", s)
        if s2 != s:
            self.count["guid_exemplo_normalizado"] += 1
        s = s2
        for _ in range(3):
            hits = privacy.scan_text(s, "x")
            if not hits:
                break
            for rule, rx in privacy.RULES:
                if rule == "email":
                    s, n = rx.subn(lambda m: m.group(0) if privacy.ALLOWED_EMAIL_DOMAINS.search(m.group(0))
                                   else f"[REDIGIDO:{rule}]", s)
                else:
                    s, n = rx.subn(f"[REDIGIDO:{rule}]", s)
                if n:
                    self.count[rule] += n
            for d in privacy.twelve_digit_hits(s):
                s = s.replace(d, "[REDIGIDO:doze_digitos]")
                self.count["doze_digitos"] += 1
        return s

    def value(self, v):
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, list):
            return [self.value(x) for x in v]
        if isinstance(v, dict):
            return {k: self.value(x) for k, x in v.items()}
        return v


# ------------------------------------------------------------------------------------------ schema
class TypeIndex:
    """Átomos e blocos de um tipo: caminho do bloco -> nomes de atributos e de blocos filhos."""

    def __init__(self, ts):
        self.ts = ts
        self.atoms = {tuple(a["path"].split(".")): a for a in ts.atoms}
        self.blocks = {b.path for b in ts.blocks}
        self.attrs = defaultdict(set)
        self.children = defaultdict(set)
        for p in self.atoms:
            self.attrs[p[:-1]].add(p[-1])
        for b in self.blocks:
            self.children[b[:-1]].add(b[-1])
        self.block_names = {b[-1] for b in self.blocks}

    def siblings(self, bpath: tuple) -> set:
        return self.attrs[bpath] | self.children[bpath]


def load_schema():
    doc = schema_core.load(SRC.schema_path())
    ps = schema_core.providers(doc)[SRC.PROVIDER]
    return {ts.resource_type: TypeIndex(ts) for ts in schema_core.iter_types(ps, SRC.PROVIDER, SRC.version())}


# ------------------------------------------------------------------------------------- resolução
def resolve_sections(pg: MD.Page, ti: TypeIndex, stats: Counter) -> dict:
    """id(seção) -> (conjunto de caminhos de bloco, derivado?)."""
    refs = defaultdict(list)
    for sec in pg.sections:
        for it in sec.items:
            if it.name in ti.block_names:
                refs[it.name].append(sec)
    memo: dict = {}

    def res(sec, stack=()):
        k = id(sec)
        if k in memo:
            return memo[k]
        if k in stack:
            return set(), False
        if sec.kind == "timeouts":
            r = ({("timeouts",)} if ("timeouts",) in ti.blocks else set(), False)
            memo[k] = r
            return r
        if not sec.blocks:
            memo[k] = ({()}, False)
            return memo[k]
        paths, derived = set(), False
        for b in sec.blocks:
            cands = [p for p in ti.blocks if p[-1] == b]
            if len(cands) > 1 and sec.hint:
                c2 = [p for p in cands if len(p) >= 2 and p[-2] == sec.hint]
                if c2:
                    cands = c2
            if len(cands) > 1:
                parents = set()
                for ps in refs.get(b, []):
                    if ps is not sec:
                        parents |= res(ps, stack + (k,))[0]
                c3 = [p for p in cands if p[:-1] in parents]
                if c3:
                    cands = c3
                    if len(c3) > 1:
                        stats["secoes_bloco_compartilhado_pela_pagina"] += 1
                else:
                    derived = True
                    stats["secoes_bloco_ambiguas_derived"] += 1
            if not cands:
                if any(b in ti.attrs[q] for q in ti.attrs):
                    stats["secoes_de_atributo_objeto_sem_atomo_filho"] += 1
                else:
                    stats["secoes_bloco_sem_schema"] += 1
            paths |= set(cands)
        memo[k] = (paths, derived)
        return memo[k]

    return {id(s): res(s) for s in pg.sections}


# -------------------------------------------------------------------------------------------- fatos
class Facts:
    def __init__(self, meta: dict, red: Redactor):
        self.meta = meta
        self.red = red
        self.rows = {}

    def add(self, atom_id: str, kind: str, status: str, *, value=None, reason=None, line=None, file=None,
            sentence=None, method="regex", level="published"):
        rec = {"atom_id": atom_id, "provider_version": self.meta["version"], "fact_kind": kind, "status": status,
               "extraction_method": method, "evidence_level": level}
        if status == "stated":
            rec["value"] = self.red.value(value)
            if kind == "default":
                rec["as_of"] = self.meta["as_of"]
        else:
            rec["unknown_reason"] = reason
        if line is not None:
            rec["source"] = {"repo": self.meta["repo"], "tag": self.meta["tag"], "file": file, "line": line,
                             "sentence": self.red.text(sentence)}
        key = json.dumps([atom_id, kind, status, rec.get("value"), reason, line], sort_keys=True, ensure_ascii=False)
        if key in self.rows:
            return
        rec["fact_id"] = "DF-azurerm-" + hashlib.sha256(key.encode()).hexdigest()[:32]
        self.rows[key] = rec

    def records(self):
        return sorted(self.rows.values(), key=lambda r: (r["atom_id"], r["fact_kind"], r["status"],
                                                         (r.get("source") or {}).get("line", 0), r["fact_id"]))


def _raw(pg: MD.Page, it: MD.Item) -> str:
    return " ".join(" ".join(pg.lines[ln - 1].split()) for ln, _ in it.parts)


def _clean_desc(it: MD.Item) -> str:
    t = " ".join(it.text.split())
    return MD.MARKER.sub("", t, count=1).strip()


def page_facts(pg: MD.Page, ti: TypeIndex, facts: Facts, stats: Counter, documented: set, unit_stated: set):
    rtype = ti.ts.resource_type
    resolved = resolve_sections(pg, ti, stats)
    for sec in pg.sections:
        paths, derived = resolved[id(sec)]
        level = "derived" if derived else "published"
        sec_atoms = {}
        for it in sec.items:
            stats["itens"] += 1
            bound = []
            for p in sorted(paths):
                if it.name in ti.attrs[p]:
                    bound.append(ti.atoms[p + (it.name,)])
                elif it.name in ti.children[p]:
                    stats["itens_que_sao_blocos"] += 1
            if not bound:
                if not any(it.name in ti.children[p] for p in paths):
                    stats["itens_sem_atomo_no_schema"] += 1
                    stats[f"itens_sem_atomo:{sec.kind}"] += 1
                continue
            sec_atoms.setdefault(it.name, []).extend(bound)
            raw = _raw(pg, it)
            desc = _clean_desc(it)
            for a in bound:
                documented.add(a["atom_id"])
                if len(desc) >= 1:
                    facts.add(a["atom_id"], "description", "stated", value=desc, line=it.line, file=pg.file,
                              sentence=raw, method="parser", level=level)
                if "deprecated" in it.marker.lower():
                    facts.add(a["atom_id"], "deprecation", "stated", value={"deprecated": True, "scope": "attribute"}, line=it.line,
                              file=pg.file, sentence=raw, method="parser", level=level)
                sib = ti.siblings(tuple(a["path"].split("."))[:-1])
                for f in X.extract(it.text, a, sib, timeouts=(sec.kind == "timeouts")):
                    lv = "derived" if derived else f["level"]
                    if f["status"] == "stated":
                        facts.add(a["atom_id"], f["kind"], "stated", value=f["value"], line=it.line_at(f["off"]),
                                  file=pg.file, sentence=f["s"], method=f["method"], level=lv)
                        if f["kind"] == "unit":
                            unit_stated.add(a["atom_id"])
                    else:
                        facts.add(a["atom_id"], f["kind"], "unknown", reason=f["reason"],
                                  line=it.line_at(f["off"]), file=pg.file, sentence=f["s"], method=f["method"],
                                  level=lv)
        # notas -------------------------------------------------------------------------------------
        for nt in sec.notes:
            text = NOTE_HEAD.sub("", nt.text).strip()
            if len(text) < 5:
                continue
            ticks = set(X.TICKS.findall(text))
            targets = []
            if nt.after_item is not None and nt.after_item.name in sec_atoms and (
                    nt.after_item.name in ticks or re.match(r"(?i)^(this|these|the value)\b", text)):
                targets = sec_atoms[nt.after_item.name]
                stats["notas_anexadas_ao_item"] += 1
            else:
                named = [n for n in ticks if n in sec_atoms]
                if len(named) == 1:
                    targets = sec_atoms[named[0]]
                    stats["notas_anexadas_por_nome"] += 1
                else:
                    stats["notas_sem_alvo_unico"] += 1
            raw = " ".join(nt.text.split())
            for a in targets:
                facts.add(a["atom_id"], "behavior", "stated", value=text, line=nt.line, file=pg.file,
                          sentence=raw, method="regex", level=level)
                sib = ti.siblings(tuple(a["path"].split("."))[:-1])
                for f in X.extract(text, a, sib):
                    if f["kind"] in KEEP_FROM_NOTES and f["status"] == "stated":
                        facts.add(a["atom_id"], f["kind"], "stated", value=f["value"], line=nt.line,
                                  file=pg.file, sentence=f["s"], method=f["method"], level=level)


def type_record(pg: MD.Page | None, rtype: str, meta: dict, red: Redactor, in_schema: bool) -> dict:
    rec = {"type_id": f"{SRC.PROVIDER}:{rtype}", "provider": SRC.PROVIDER, "provider_version": meta["version"],
           "resource_type": rtype, "in_schema": in_schema}
    src = lambda ln, s: {"repo": meta["repo"], "tag": meta["tag"], "file": pg.file, "line": ln,  # noqa: E731
                         "sentence": red.text(s)}
    if pg is None:
        rec["doc_file"] = None
        rec["subcategory"] = {"status": "unknown", "unknown_reason": "not_documented",
                              "extraction_method": "parser", "evidence_level": "published"}
        rec["import_id"] = dict(rec["subcategory"], extraction_method="regex")
        return rec
    rec["doc_file"] = pg.file
    if "page_title" in pg.front:
        rec["page_title"] = pg.front["page_title"][0]
    if "subcategory" in pg.front and pg.front["subcategory"][0].strip():
        v, ln = pg.front["subcategory"]
        rec["subcategory"] = {"status": "stated", "value": v, "source": src(ln, pg.lines[ln - 1].strip()),
                              "extraction_method": "parser", "evidence_level": "published"}
    else:
        rec["subcategory"] = {"status": "unknown", "unknown_reason": "not_documented",
                              "extraction_method": "parser", "evidence_level": "published"}
    cmds = [c for c in pg.imports if c.address.split(".", 1)[0] == rtype]
    if cmds:
        vals = []
        for c in cmds:
            v = red.text(c.id)
            if v not in vals:
                vals.append(v)
        rec["import_id"] = {"status": "stated", "value": vals,
                            "source": src(cmds[0].line, pg.lines[cmds[0].line - 1].strip()),
                            "extraction_method": "regex", "evidence_level": "published"}
        if len(cmds) > 1:
            rec["import_id"]["other_lines"] = [c.line for c in cmds[1:]]
        if pg.import_text:
            ln, s = pg.import_text[0]
            rec["import_id"]["key_sentence"] = src(ln, s)
    elif pg.has_import_section:
        ln, s = pg.import_text[0] if pg.import_text else (pg.import_line, "## Import")
        rec["import_id"] = {"status": "unknown", "unknown_reason": "ambiguous", "source": src(ln, s),
                            "extraction_method": "regex", "evidence_level": "published"}
    else:
        rec["import_id"] = {"status": "unknown", "unknown_reason": "not_documented",
                            "extraction_method": "regex", "evidence_level": "published"}
    return rec


def build(dest: Path) -> dict:
    meta = SRC.meta()
    red = Redactor()
    facts = Facts(meta, red)
    stats = Counter()
    types = load_schema()
    rdir = SRC.docs_root() / "website" / "docs" / "r"
    pages = {}
    for p in sorted(rdir.glob("*.html.markdown")):
        rtype = "azurerm_" + p.name[: -len(".html.markdown")]
        pages[rtype] = MD.parse(p, f"website/docs/r/{p.name}")
        h1 = pages[rtype].h1
        if not h1 or h1[0] != rtype:
            stats["paginas_h1_diferente_do_arquivo"] += 1
    documented, unit_stated = set(), set()
    trecs = []
    for rtype in sorted(set(types) | set(pages)):
        pg, ti = pages.get(rtype), types.get(rtype)
        trecs.append(type_record(pg, rtype, meta, red, ti is not None))
        if ti is None:
            stats["paginas_sem_tipo_no_schema"] += 1
            continue
        if pg is None:
            stats["tipos_sem_pagina"] += 1
        else:
            page_facts(pg, ti, facts, stats, documented, unit_stated)
        for a in ti.ts.atoms:
            if a["atom_id"] not in documented:
                facts.add(a["atom_id"], "description", "unknown", reason="not_documented", method="parser")
            if X.is_numeric(a["tf_type"]) and a["atom_id"] not in unit_stated:
                facts.add(a["atom_id"], "unit", "unknown", reason="not_documented", method="regex")
    recs = facts.records()
    ids = Counter(r["fact_id"] for r in recs)
    if any(n > 1 for n in ids.values()):
        raise SystemExit("fact_id repetido")
    dest.mkdir(parents=True, exist_ok=True)
    schema_core.write_jsonl(dest / "docs_facts.jsonl", recs)
    schema_core.write_jsonl(dest / "type_subcategory.jsonl", trecs)
    for name in ("docs_facts.jsonl", "type_subcategory.jsonl"):
        hits = privacy.scan_text((dest / name).read_text(encoding="utf-8"), name)
        if hits:
            raise SystemExit(f"{name}: {len(hits)} achado(s) do privacy_lint depois da redação: {hits[0]}")
    report = {
        "module": MODULE, "provider": SRC.PROVIDER, "provider_version": meta["version"], "tag": meta["tag"],
        "commit": meta["commit"], "as_of_defaults": meta["as_of"],
        "pages_r": len(pages), "types_schema": len(types),
        "atoms": sum(len(t.ts.atoms) for t in types.values()),
        "facts": len(recs),
        "facts_by_kind_status": dict(sorted(Counter(f"{r['fact_kind']}:{r['status']}" for r in recs).items())),
        "facts_by_level": dict(sorted(Counter(r["evidence_level"] for r in recs).items())),
        "parse_stats": dict(sorted(stats.items())),
        "redactions": dict(sorted(red.count.items())),
        "types_with_subcategory": sum(t["subcategory"]["status"] == "stated" for t in trecs),
        "types_with_import_id": sum(t["import_id"]["status"] == "stated" for t in trecs),
    }
    (dest / "build_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                                            encoding="utf-8")
    return report


def manifest_entries() -> list[tuple[str, Path]]:
    """Arquivos do MANIFEST C17 (caminhos portáveis); summary.json fica de fora (carimbo de hora)."""
    dl, d = "$BO_DATA/downloads/docs-azurerm/", f"$BO_DATA/{MODULE}/"
    out = [(dl + n, SRC.dest_dir() / n) for n in ("SOURCE.txt", "FILES.sha256", "providers-schema.json")]
    out += [(d + n, out_dir() / n) for n in ("docs_facts.jsonl", "type_subcategory.jsonl", "build_report.json")]
    out += [(f"$BO_REPO/results/{MODULE}/coverage.json", results_dir() / "coverage.json"),
            (f"$BO_REPO/gates/{MODULE}.sh", SRC.bo_repo() / "gates" / f"{MODULE}.sh")]
    return out


def write_manifest() -> Path:
    p = results_dir() / "MANIFEST.sha256"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(f"{SRC.sha256(f)}  {rel}\n" for rel, f in manifest_entries()), encoding="utf-8")
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--manifest" in argv:
        print(write_manifest())
        return 0
    SRC.verify()
    if "--check" in argv:
        tmp = Path(os.environ.get("BO_TMP") or SRC.bo_data() / "tmp" / MODULE) / "regen"
        build(tmp)
        bad = []
        for name in ("docs_facts.jsonl", "type_subcategory.jsonl", "build_report.json"):
            a, b = tmp / name, out_dir() / name
            if not b.exists() or a.read_bytes() != b.read_bytes():
                bad.append(name)
        if bad:
            print(f"regeneração difere: {bad}")
            return 1
        print("regeneração idêntica: docs_facts.jsonl, type_subcategory.jsonl, build_report.json")
        return 0
    rep = build(out_dir())
    from . import coverage
    coverage.main([MODULE])
    write_manifest()
    print(json.dumps({k: rep[k] for k in ("pages_r", "types_schema", "atoms", "facts")}, ensure_ascii=False))
    print(json.dumps(rep["facts_by_kind_status"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
