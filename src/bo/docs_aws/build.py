"""Monta os fatos de documentação do aws (C03), a subcategoria e a importação por tipo, e a cobertura (C15).

  python -I -m bo.docs_aws.build            grava $BO_DATA/DOCS-AWS/{docs_facts,type_subcategory,unresolved}.jsonl
                                            e $BO_REPO/results/DOCS-AWS/coverage.json
  python -I -m bo.docs_aws.build --check    regera em memória e compara com o gravado (regeneração idêntica;
                                            só generated_at do coverage.json pode diferir)

Universo de átomos: resource_schemas do providers-schema.json da versão fixada (cópia conferida em
downloads/docs-aws/), atomizado por bo.schema.core (a mesma régua do C01). Documentação: website/docs/r/ (recursos,
fonte dos fatos por atributo) e website/docs/d/ (fontes de dados: só subcategoria e tipo).

Consolidação por átomo e tipo de fato:
  * description: um fato por item que descreve o átomo (texto depois do parêntese); sem item -> unknown
    not_documented (um por átomo);
  * default, allowed_values, range (por 'of'), unit: valores diferentes para o mesmo átomo viram UM fato unknown
    (ambiguous quando vêm do mesmo item; contradictory quando vêm de itens diferentes);
  * forces_replacement, deprecation, format, conflicts_with, required_when: um fato por valor distinto;
  * candidato unknown/ambiguous (cláusula sem valor legível) só fica quando não há valor declarado do mesmo tipo.
Nível de evidência: published quando o item resolve no átomo por nome e contexto (R1-R3, R2, R4-top); derived quando
o item vale para o átomo por regra declarada (bloco descrito uma vez e repetido no schema; sufixo único).
Privacidade: trechos que o privacy_lint reprovaria (ARN de exemplo, 12 dígitos, e-mail, dinheiro, segredos de
exemplo) são trocados por ⟨redigido:regra⟩ na sentença e no valor; o arquivo:linha continua apontando o original.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bo.docs_aws import cues as C
from bo.docs_aws import mdparse, source
from bo.docs_aws.resolve import TypeIndex, resolve
from bo.repo import privacy
from bo.schema import core as schema_core

MODULE = "DOCS-AWS"
KINDS_SINGLE = ("default", "allowed_values", "range", "unit")
KINDS_MULTI = ("forces_replacement", "deprecation", "format", "conflicts_with", "required_when")
COVERAGE_KINDS = ("description", "allowed_values", "unit", "default", "range", "forces_replacement", "format",
                  "deprecation", "conflicts_with", "required_when")


def out_dir() -> Path:
    return source.bo_data() / MODULE


def results_dir() -> Path:
    return source.bo_repo() / "results" / MODULE


# ---------------------------------------------------------------- privacidade

def redact(s: str, counter: Counter) -> str:
    if not isinstance(s, str):
        return s
    spans = []
    for hit in privacy.twelve_digit_hits(s):
        for m in re.finditer(re.escape(hit), s):
            spans.append((m.start(), m.end(), "doze_digitos"))
    for rule, rx in privacy.RULES:
        for m in rx.finditer(s):
            if rule == "email" and privacy.ALLOWED_EMAIL_DOMAINS.search(m.group(0)):
                continue
            a, b = m.start(), m.end()
            if rule == "arn":   # o ARN inteiro (até espaço, crase, aspas ou fecha-parêntese)
                e = re.match(r"[^\s`\"')\]]*", s[b:])
                b += e.end() if e else 0
            spans.append((a, b, rule))
    if not spans:
        return s
    spans.sort()
    out, pos = [], 0
    for a, b, rule in spans:
        if a < pos:
            continue
        out.append(s[pos:a])
        out.append(f"⟨redigido:{rule}⟩")
        counter[rule] += 1
        pos = b
    out.append(s[pos:])
    return "".join(out)


def redact_value(v, counter: Counter):
    if isinstance(v, str):
        return redact(v, counter)
    if isinstance(v, list):
        return [redact_value(x, counter) for x in v]
    if isinstance(v, dict):
        return {k: redact_value(x, counter) for k, x in v.items()}
    return v


# ---------------------------------------------------------------- entradas

def load_types() -> tuple[dict, dict, set]:
    doc = schema_core.load(source.schema_copy())
    ps = schema_core.providers(doc)[source.PROVIDER]
    ver = source.version()
    types = {}
    for ts in schema_core.iter_types(ps, source.PROVIDER, ver):
        types[ts.resource_type] = (ts, TypeIndex.build(ts.atoms, ts.blocks))
    return types, ps, set((ps.get("data_source_schemas") or {}).keys())


def page_type(page: mdparse.Page, stem: str) -> str:
    if page.title:
        m = re.search(r"\b(aws_[a-z0-9_]+)\b", page.title[0])
        if m:
            return m.group(1)
    return "aws_" + stem


def doc_pages(kind_dir: str) -> list[tuple[str, mdparse.Page]]:
    root = source.docs_root() / kind_dir
    out = []
    for p in sorted(root.glob("*.markdown")):
        rel = f"{source.DOCS_IN_REPO}/{kind_dir}/{p.name}"
        page = mdparse.parse(p.read_text(encoding="utf-8"), rel)
        out.append((page_type(page, p.name.split(".", 1)[0]), page))
    return out


# ---------------------------------------------------------------- fatos

def src(file: str, line: int, sentence: str) -> dict:
    return {"repo": source.REPO, "tag": source.tag(), "file": file, "line": line, "sentence": sentence}


def sentence_line(item: mdparse.Item, sentence: str) -> int:
    key = re.sub(r"\s+", " ", sentence.strip())[:40]
    for n, raw in item.lines:
        if key[:25] and key[:25] in re.sub(r"\s+", " ", raw):
            return n
    return item.line


def item_candidates(item: mdparse.Item, tf_type) -> tuple[list[dict], list[str]]:
    """Candidatos a fato de um item: [{kind, value, sentence, line, method, unknown}] e marcas não usadas."""
    paren, rest = C.split_paren(item.text)
    cands = []
    unused = []
    if paren is not None:
        fc, unused = C.flag_cues(paren, tf_type)
        for c in fc:
            cands.append({"kind": c.kind, "value": c.value, "sentence": f"({paren})", "line": item.line,
                          "method": c.method, "unknown": c.unknown})
    body = rest.strip()
    if len(body) >= 5:
        sents = C.sentences(body)
        first = sents[0] if sents else body
        if len(first) < 5:
            first = body
        cands.append({"kind": "description", "value": body, "sentence": first,
                      "line": sentence_line(item, first), "method": "parser", "unknown": None})
        for c in C.text_cues(body, tf_type):
            cands.append({"kind": c.kind, "value": c.value, "sentence": c.sentence,
                          "line": sentence_line(item, c.sentence), "method": c.method, "unknown": c.unknown})
    return cands, unused


def fact_key(atom_id: str) -> str:
    """10 caracteres base32 (a-z, 2-7) do sha1 do atom_id: curto e sem sequência de 12 dígitos."""
    return base64.b32encode(hashlib.sha1(atom_id.encode()).digest()).decode().lower()[:10]


def _ranges_compatible(vals: list[dict]) -> bool:
    """Faixas parciais do mesmo eixo ('of') que não se contradizem: {min: 50} e {max: 29000} somam-se."""
    for key in ("min", "max"):
        if len({json.dumps(v[key]) for v in vals if key in v}) > 1:
            return False
    return True


def _canon(v) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def consolidate(order: list, version: str, as_of: str, red: Counter, shared: set) -> list[dict]:
    """order = [(atom_id, [(cand, file, item_line, level)])] -> fatos C03, em ordem estável.
    shared: átomos cobertos só pelo mapa de blocos repetidos (sem unknown not_documented aqui)."""
    facts = []
    for atom_id, cl in order:
        groups = defaultdict(list)
        for cand, file, iline, level in cl:
            key = cand["kind"]
            if key == "range" and isinstance(cand["value"], dict):
                key = "range:" + cand["value"].get("of", "value")
            groups[key].append((cand, file, iline, level))
        seq = Counter()

        def emit(kind, status, value=None, reason=None, cand=None, file=None, level="published"):
            seq[kind] += 1
            f = {"fact_id": f"DF-aws-{fact_key(atom_id)}-{kind}-{seq[kind]}", "atom_id": atom_id, "provider_version": version,
                 "fact_kind": kind, "status": status,
                 "extraction_method": cand["method"] if cand else "parser", "evidence_level": level}
            if status == "stated":
                f["value"] = redact_value(value, red)
                if kind == "default":
                    f["as_of"] = as_of
            else:
                f["unknown_reason"] = reason
            if cand is not None:
                f["source"] = src(file, cand["line"], redact(cand["sentence"], red))
            facts.append(f)

        if not groups.get("description") and atom_id not in shared:
            emit("description", "unknown", reason="not_documented", level="derived")
        for key in sorted(groups, key=lambda k: (COVERAGE_KINDS.index(k.split(":")[0]), k)):
            kind = key.split(":")[0]
            items = groups[key]
            stated = [x for x in items if x[0]["unknown"] is None and x[0]["value"] is not None]
            unk = [x for x in items if x not in stated]
            if kind == "description":
                seen = set()
                for cand, file, iline, level in stated:
                    k = (file, cand["line"], cand["value"])
                    if k in seen:
                        continue
                    seen.add(k)
                    emit(kind, "stated", cand["value"], cand=cand, file=file, level=level)
                continue
            if kind in KINDS_SINGLE:
                vals = {}
                for x in stated:
                    vals.setdefault(_canon(x[0]["value"]), []).append(x)
                if len(vals) > 1 and not (kind == "range" and _ranges_compatible([x[0]["value"] for x in stated])):
                    same_item = len({(x[1], x[2]) for x in stated}) == 1
                    first = stated[0]
                    lvl = "derived" if any(x[3] == "derived" for x in stated) else "published"
                    emit(kind, "unknown", reason="ambiguous" if same_item else "contradictory", cand=first[0],
                         file=first[1], level=lvl)
                    continue
                if vals:
                    seen = set()
                    for cand, file, iline, level in stated:
                        k = (file, cand["line"], _canon(cand["value"]))
                        if k in seen:
                            continue
                        seen.add(k)
                        emit(kind, "stated", cand["value"], cand=cand, file=file, level=level)
                    continue
            else:
                seen = set()
                for cand, file, iline, level in stated:
                    k = (file, cand["line"], _canon(cand["value"]))
                    if k in seen:
                        continue
                    seen.add(k)
                    emit(kind, "stated", cand["value"], cand=cand, file=file, level=level)
                if stated:
                    continue
            if unk:
                cand, file, iline, level = unk[0]
                emit(kind, "unknown", reason=cand["unknown"] or "ambiguous", cand=cand, file=file, level=level)
    return facts


# ---------------------------------------------------------------- importação e subcategoria

SEP = re.compile(r"separated\s+by\s+(?:an?\s+|the\s+)?(?:`([^`]+)`|(comma|colon|slash|forward\s+slash|underscore|"
                 r"pipe|hyphen|dash|semicolon|period|double\s+slash))", re.I)
SEP_WORDS = {"comma": ",", "colon": ":", "slash": "/", "forward slash": "/", "underscore": "_", "pipe": "|",
             "hyphen": "-", "dash": "-", "semicolon": ";", "period": ".", "double slash": "//"}
NO_IMPORT = re.compile(r"\b(?:cannot|can\s*not|can't)\s+be\s+imported\b|\bdoes\s+not\s+support\s+import|"
                       r"\bimport\s+is\s+not\s+supported\b", re.I)


def _sentence_tail(tail: str) -> str:
    """O que a sentença diz depois do último 'using' (ex.: 'their ARN', 'the `bucket`'), literal e sem ':' final."""
    t = re.sub(r"\.\s*For example:?$|:\s*$|\.$", "", tail.strip()).strip()
    return t[:200]


def import_record(page: mdparse.Page, red: Counter) -> dict:
    if not any(t.strip().lower().startswith("import") for _, t in page.sections):
        return {"status": "unknown", "unknown_reason": "not_documented"}
    text = [(n, s) for n, s in page.import_text if s.strip() and not s.lstrip().startswith(("#", "*", "-"))]
    code = "\n".join(s for _, s in page.import_code)
    sents = []
    id_attrs, seps, supported, id_texts = [], [], True, []
    for n, s in text:
        for sent in C.sentences(s.strip()):
            low = sent.lower()
            if NO_IMPORT.search(sent):
                supported = False
                sents.append({"line": n, "sentence": redact(sent, red)})
                continue
            if "import" not in low or " using " not in f" {low} ":
                continue
            sents.append({"line": n, "sentence": redact(sent, red)})
            tail = re.split(r"\busing\b", sent, maxsplit=1, flags=re.I)[-1]
            if "`terraform import`" in sent or "`import` block" in sent:
                tail = re.split(r"\busing\b", sent, flags=re.I)[-1]
            txt = redact(_sentence_tail(tail), red)
            if txt and txt not in id_texts:
                id_texts.append(txt)
            for t in C.TICK.findall(tail):
                t = t.strip()
                if not t or "import" in t:
                    continue
                if re.fullmatch(r"[A-Za-z0-9_.\[\]]+", t):
                    parts = [t]
                else:
                    # composto: 'analyzer_name/rule_name', 'a,b', 'a:b', 'a|b' -> partes e separador
                    m = re.fullmatch(r"([A-Za-z0-9_.\[\]-]+)((?:[/,:|_]{1,2}|--)[A-Za-z0-9_.\[\]-]+)+", t)
                    if not m:
                        continue
                    sep = re.findall(r"(?<=[A-Za-z0-9\]])([/,:|]{1,2}|--)(?=[A-Za-z0-9\[])", t)
                    if not sep:
                        continue
                    parts = [x for x in re.split(r"[/,:|]{1,2}|--", t) if x]
                    for x in sep:
                        if x not in seps:
                            seps.append(x)
                for x in parts:
                    x = redact(x, red)
                    if x not in id_attrs:
                        id_attrs.append(x)
            for m in SEP.finditer(sent):
                v = m.group(1) or SEP_WORDS.get(re.sub(r"\s+", " ", (m.group(2) or "").lower()))
                v = redact(v, red) if v else v
                if v and v not in seps:
                    seps.append(v)
    identity = {"required": [], "optional": []}
    for it in page.items:
        if it.section != "identity":
            continue
        hdr = "required"
        # o cabeçalho #### Required/Optional mais próximo antes do item decide
        lines_before = [s for n, s in page.import_text if n < it.line and s.startswith("####")]
        if lines_before and "optional" in lines_before[-1].lower():
            hdr = "optional"
        identity[hdr].append(redact(it.name, red))
    methods = []
    if re.search(r"^\s*identity\s*=\s*\{", code, re.M):
        methods.append("import_block_identity")
    if re.search(r"^\s*id\s*=", code, re.M):
        methods.append("import_block_id")
    if re.search(r"terraform\s+import\s", code):
        methods.append("terraform_import_cli")
    if not supported and not methods:
        return {"status": "stated", "supported": False, "statements": sents, "extraction_method": "regex",
                "evidence_level": "published"}
    if not sents and not methods and not identity["required"]:
        return {"status": "unknown", "unknown_reason": "ambiguous", "statements": []}
    return {"status": "stated", "supported": True, "id_attributes": id_attrs, "id_text": id_texts,
            "separators": seps,
            "identity": identity, "methods": methods, "statements": sents, "extraction_method": "regex",
            "evidence_level": "published"}


def subcategory_record(page: mdparse.Page, red: Counter) -> dict:
    sc = page.frontmatter.get("subcategory")
    if not sc or not sc[0].strip():
        return {"status": "unknown", "unknown_reason": "not_documented"}
    return {"status": "stated", "value": redact(sc[0], red), "extraction_method": "parser",
            "evidence_level": "published",
            "source": src(page.file, sc[1], f'subcategory: "{redact(sc[0], red)}"')}


# ---------------------------------------------------------------- montagem

def build() -> dict:
    ver = source.version()
    as_of = source.release_date()
    red: Counter = Counter()
    types, ps, ds_schema = load_types()
    pages_r = doc_pages("r")
    pages_d = doc_pages("d")
    per_type_atoms: dict[str, dict] = {t: defaultdict(list) for t in types}
    unresolved = []
    shared_rows, shared_atoms = [], set()
    res_rules = Counter()
    unused_flags = Counter()
    value_list_children = 0
    doc_only_r = []
    type_rows = []
    documented_r = set()
    def process(rtype, page, alias_of=None):
        nonlocal value_list_children
        tname = rtype
        ts, ix = types[rtype]
        res = []
        for i, it in enumerate(page.items):
            if it.section == "identity":
                res.append(None)
                continue
            pb = pa = None
            parent_vals = False
            if it.parent is not None and res[it.parent] is not None:
                pr = res[it.parent]
                if pr.block:
                    pb = pr.block
                elif pr.paths:
                    p0 = pr.paths[0]
                    if p0 in ix.nested_attrs:
                        pa = p0
                    else:
                        parent_vals = True
            if parent_vals:
                r = resolve(ix, it.name, it.hint, it.hint_kind, None, None)
                if not r.paths and not r.block:
                    res.append(r)
                    value_list_children += 1
                    _attach_value_list(page, i, res, ix, per_type_atoms[rtype], ts, alias_of)
                    res_rules["value_list_child"] += 1
                    continue
            else:
                r = resolve(ix, it.name, it.hint, it.hint_kind, pb, pa)
            res.append(r)
            res_rules[r.rule] += 1
            if not r.paths:
                if r.rule != "block":
                    unresolved.append({"type_id": f"aws:{rtype}", "file": page.file, "line": it.line,
                                       "name": redact(it.name, red), "section": it.section, "reason": r.rule,
                                       "context": redact(it.hint, red) if it.hint else None})
                continue
            targets = r.paths
            shared_row = None
            if r.rule == "R3-shared":
                # bloco descrito uma vez e repetido no schema: os fatos vão para as ocorrências de menor
                # profundidade; as repetições mais fundas vão para o mapa (shared_block_map.jsonl)
                depth = min(p.count(".") for p in r.paths)
                targets = [p for p in r.paths if p.count(".") == depth]
                repeats = [p for p in r.paths if p.count(".") > depth]
                if repeats:
                    shared_rows.append({"type_id": f"aws:{rtype}", "file": page.file, "line": it.line,
                                        "alias_of": alias_of,
                                        "name": redact(it.name, red),
                                        "context": redact(it.hint, red) if it.hint else None,
                                        "rule": "R3-shared", "evidence_level": "derived",
                                        "canonical": [f"aws:{rtype}:{p}" for p in targets],
                                        "repeats": [f"aws:{rtype}:{p}" for p in repeats]})
                    shared_row = shared_rows[-1]
                    shared_atoms.update(f"aws:{rtype}:{p}" for p in repeats)
            item_kinds = set()
            for p in targets:
                cands, unused = item_candidates(it, ix.atoms[p]["tf_type"])
                item_kinds.update(c["kind"] for c in cands if c["unknown"] is None and c["value"] is not None)
                for u in unused:
                    unused_flags[re.sub(r"`[^`]*`", "`x`", u)[:60]] += 1
                for c in cands:
                    per_type_atoms[rtype][p].append((c, page.file, it.line, "derived" if alias_of else r.level))
            if shared_row is not None:
                shared_row["kinds"] = sorted(item_kinds)

    for rtype, page in pages_r:
        if rtype not in types:
            doc_only_r.append(rtype)
            type_rows.append(_type_row(rtype, "resource", False, page, red))
            continue
        documented_r.add(rtype)
        type_rows.append(_type_row(rtype, "resource", True, page, red))
        process(rtype, page)
    # apelidos: '`aws_alb_listener` is known as `aws_lb_listener`' na página do nome canônico
    alias_rows = 0
    for rtype, page in pages_r:
        for line, sent, alias, canon in page.aliases:
            if canon == rtype and alias in types and alias not in documented_r:
                documented_r.add(alias)
                row = _type_row(alias, "resource", True, page, red)
                row["alias_of"] = {"type_id": f"aws:{canon}", "evidence_level": "derived",
                                   "source": src(page.file, line, redact(sent, red))}
                type_rows.append(row)
                process(alias, page, alias_of=canon)
                alias_rows += 1
    for rtype in sorted(set(types) - documented_r):
        type_rows.append(_type_row(rtype, "resource", True, None, red))
    data_docs = set()
    for dtype, page in pages_d:
        data_docs.add(dtype)
        type_rows.append(_type_row(dtype, "data_source", dtype in ds_schema, page, red))
    for dtype in sorted(ds_schema - data_docs):
        type_rows.append(_type_row(dtype, "data_source", True, None, red))
    type_rows.sort(key=lambda r: (r["kind"], r["resource_type"], r["doc_file"] or ""))
    facts = []
    for rtype in sorted(types):
        ts, ix = types[rtype]
        order = [(a["atom_id"], per_type_atoms[rtype].get(a["path"], [])) for a in ts.atoms]
        facts.extend(consolidate(order, ver, as_of, red, shared_atoms))
    atoms_meta = {a["atom_id"]: a["configurable"] for t in types.values() for a in t[0].atoms}
    stats = {"pages_r": len(pages_r), "pages_d": len(pages_d), "schema_resources": len(types),
             "schema_data_sources": len(ds_schema), "resources_without_doc": len(set(types) - documented_r),
             "doc_pages_not_in_schema_r": sorted(doc_only_r),
             "data_source_docs_not_in_schema": sorted(data_docs - ds_schema),
             "items_total_r": sum(len(p.items) for _, p in pages_r),
             "resolution_rules": dict(sorted(res_rules.items())), "value_list_children": value_list_children,
             "unresolved_by_reason": dict(sorted(Counter(u["reason"] for u in unresolved).items())),
             "redactions": dict(sorted(red.items())),
             "unused_flag_tokens_top": dict(unused_flags.most_common(25))}
    stats["alias_types"] = alias_rows
    stats["shared_map"] = {"items": len(shared_rows), "repeat_atoms": len(shared_atoms)}
    return {"facts": facts, "types": type_rows, "unresolved": unresolved, "atoms": atoms_meta, "stats": stats,
            "shared": shared_rows, "shared_atoms": shared_atoms}


def _attach_value_list(page, i, res, ix, store, ts, alias_of=None):
    """Sublista de valores sob um item que é atributo simples: allowed_values do pai (método parser)."""
    it = page.items[i]
    parent = page.items[it.parent]
    pr = res[it.parent]
    sibs = [x for x in page.items if x.parent == it.parent]
    if sibs[0] is not it:
        return   # a lista inteira entra uma vez, no primeiro filho
    names = [x.name for x in sibs]
    sents = C.sentences(C.split_paren(parent.text)[1])
    intro = next((s for s in sents if C.VALID_TEXT.search(s) or C.ONEOF_TEXT.search(s)
                  or re.search(r"\b(?:following|values?)\b.*:\s*$", s)), None)
    if intro is None:
        return
    for p in pr.paths:
        cand = {"kind": "allowed_values", "value": [C.typed(n, ix.atoms[p]["tf_type"]) for n in names],
                "sentence": intro, "line": sentence_line(parent, intro), "method": "parser", "unknown": None}
        store[p].append((cand, page.file, parent.line, "derived" if alias_of else pr.level))
        # a cláusula sem valor do próprio pai deixa de ser 'ambiguous'
        store[p][:] = [x for x in store[p] if not (x[0]["kind"] == "allowed_values" and x[0]["unknown"])]


def _type_row(rtype: str, kind: str, in_schema: bool, page, red: Counter) -> dict:
    row = {"type_id": f"aws:{rtype}", "provider": "aws", "provider_version": source.version(), "kind": kind,
           "resource_type": rtype, "in_schema": in_schema, "doc_file": page.file if page else None}
    if page is None:
        row["subcategory"] = {"status": "unknown", "unknown_reason": "not_documented"}
        row["import"] = {"status": "unknown", "unknown_reason": "not_documented"}
        return row
    row["subcategory"] = subcategory_record(page, red)
    if kind == "resource":
        row["import"] = import_record(page, red)
    if page.title:
        row["title"] = {"text": redact(page.title[0], red), "line": page.title[1]}
    return row


# ---------------------------------------------------------------- cobertura (C15)

def coverage_doc(facts: list[dict], types: list[dict], atoms: dict, stats: dict, generated_at: str,
                 shared: list[dict]) -> dict:
    direct = defaultdict(set)
    published = defaultdict(set)
    for f in facts:
        if f["status"] == "stated":
            direct[f["fact_kind"]].add(f["atom_id"])
            if f["evidence_level"] == "published":
                published[f["fact_kind"]].add(f["atom_id"])
    # expansão pelo mapa de blocos repetidos: a repetição herda os tipos de fato declarados pelo item
    stated = defaultdict(set, {k: set(v) for k, v in direct.items()})
    for row in shared:
        for k in row.get("kinds", []):
            stated[k].update(row["repeats"])
    undoc = Counter(a.split(":")[1] for a in atoms if a not in stated["description"])
    all_ids = set(atoms)
    cfg = {a for a, c in atoms.items() if c}
    frame_ref = {"path": "$BO_DATA/downloads/docs-aws/providers-schema.json",
                 "sha256": source.pin()["schema_sha256"]}
    metrics = []
    for kind in COVERAGE_KINDS:
        for fname, pop in (("ALL", all_ids), ("CFG", cfg)):
            hit = len(stated[kind] & pop)
            n = len(pop)
            est = hit / n if n else None
            metrics.append({
                "metric_id": f"M-DOCS-AWS-{kind.upper().replace('_', '')}-{fname}",
                "name": f"fração de átomos com fato '{kind}' declarado na documentação"
                        + (" (só configuráveis)" if fname == "CFG" else ""),
                "reading": "field", "axis": "representability", "quantifier": "observed_fraction",
                "operational_coverage": {"lower": est if est is not None else 0.0,
                                         "upper": est if est is not None else 1.0, "est": est, "n": n},
                "frame": {"ref": frame_ref,
                          "description": "átomos C01 de resource_schemas do aws " + source.version()
                                         + (" com required ou optional" if fname == "CFG" else "")},
                "inclusion": {"rule_id": f"INC-DOCS-AWS-{kind.upper().replace('_', '')}",
                              "text": f"átomo com pelo menos um fato '{kind}' de status stated "
                                      "(published ou derived) em docs_facts.jsonl, ou repetição de bloco "
                                      "cujo item declara esse tipo de fato (shared_block_map.jsonl)"},
                "weights": {"scheme": "uniform"},
                "joint_uncertainty": {"method": "none"},
            })
    t_res = [t for t in types if t["kind"] == "resource" and t["in_schema"]]
    for key, label in (("subcategory", "subcategoria"), ("import", "importação")):
        hit = sum(1 for t in t_res if t.get(key, {}).get("status") == "stated")
        n = len(t_res)
        metrics.append({
            "metric_id": f"M-DOCS-AWS-TYPE-{key.upper()}", "name": f"fração de tipos de recurso com {label} declarada",
            "reading": "complete_unit", "axis": "representability", "quantifier": "observed_fraction",
            "operational_coverage": {"lower": hit / n, "upper": hit / n, "est": hit / n, "n": n},
            "frame": {"ref": frame_ref, "description": "tipos de resource_schemas do aws " + source.version()},
            "inclusion": {"rule_id": f"INC-DOCS-AWS-TYPE-{key.upper()}",
                          "text": f"tipo com {label} de status stated em type_subcategory.jsonl"},
            "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "none"}})
    by_level = Counter((f["fact_kind"], f["status"], f["evidence_level"]) for f in facts)
    data = {
        "provider": "aws", "provider_version": source.version(), "tag": source.tag(),
        "atoms_total": len(all_ids), "atoms_configurable": len(cfg),
        "facts_total": len(facts),
        "facts_by_kind_status_level": {f"{k}|{s}|{l}": n for (k, s, l), n in sorted(by_level.items())},
        "atoms_with_stated": {k: len(stated[k]) for k in COVERAGE_KINDS},
        "atoms_with_stated_direct": {k: len(direct[k]) for k in COVERAGE_KINDS},
        "atoms_only_via_shared_map": len({a for r in shared for a in r["repeats"]}),
        "types_most_atoms_without_description": dict(undoc.most_common(12)),
        "atoms_with_published": {k: len(published[k]) for k in COVERAGE_KINDS},
        "parse": stats,
    }
    return {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.0.0", "module": MODULE,
            "generated_at": generated_at, "metrics": metrics,
            "notes": "Censo do que o extrator determinístico achou nas páginas da tag fixada; sem meta e sem "
                     "intervalo (método none): a incerteza é de recall do extrator, medida à parte pela "
                     "auditoria manual registrada no summary.json. Ausência de fato não é 'falso'.",
            "data": data}


# ---------------------------------------------------------------- gravação

def _jsonl(rows) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                   for r in rows).encode("utf-8")


def outputs(b: dict, generated_at: str) -> dict[Path, bytes]:
    cov = coverage_doc(b["facts"], b["types"], b["atoms"], b["stats"], generated_at, b["shared"])
    return {
        out_dir() / "docs_facts.jsonl": _jsonl(b["facts"]),
        out_dir() / "type_subcategory.jsonl": _jsonl(b["types"]),
        out_dir() / "unresolved.jsonl": _jsonl(b["unresolved"]),
        out_dir() / "shared_block_map.jsonl": _jsonl(b["shared"]),
        results_dir() / "coverage.json": (json.dumps(cov, ensure_ascii=False, indent=1, sort_keys=True)
                                          + "\n").encode("utf-8"),
    }


def _strip_gen(b: bytes) -> bytes:
    return re.sub(rb'"generated_at": "[^"]*"', b'"generated_at": ""', b)


MANIFEST_ITEMS = (
    "$BO_DATA/downloads/docs-aws/SOURCE.txt",
    "$BO_DATA/downloads/docs-aws/MANIFEST.sha256",
    "$BO_DATA/downloads/docs-aws/providers-schema.json",
    "$BO_DATA/DOCS-AWS/docs_facts.jsonl",
    "$BO_DATA/DOCS-AWS/type_subcategory.jsonl",
    "$BO_DATA/DOCS-AWS/shared_block_map.jsonl",
    "$BO_DATA/DOCS-AWS/unresolved.jsonl",
    "$BO_REPO/results/DOCS-AWS/coverage.json",
    "$BO_REPO/results/DOCS-AWS/audit_manual.json",
    "$BO_REPO/results/DOCS-AWS/CONTRACT_CHANGE.txt",
)


def write_manifest() -> int:
    """results/DOCS-AWS/MANIFEST.sha256 (C17) com caminhos portáteis."""
    lines = []
    for item in MANIFEST_ITEMS:
        real = Path(item.replace("$BO_DATA", str(source.bo_data())).replace("$BO_REPO", str(source.bo_repo())))
        if real.exists():
            lines.append(f"{source.sha256_file(real)}  {item}")
    (results_dir() / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def main(argv=None) -> int:
    from bo.repo import core
    argv = list(sys.argv[1:] if argv is None else argv)
    b = build()
    outs = outputs(b, core.now())
    if "--check" in argv:
        bad = []
        for p, data in outs.items():
            if not p.exists():
                bad.append(f"{p.name} ausente")
            elif _strip_gen(p.read_bytes()) != _strip_gen(data):
                bad.append(f"{p.name} difere da regeneração")
        if bad:
            print("regeneração NÃO idêntica: " + "; ".join(bad))
            return 1
        print(f"regeneração idêntica: {len(outs)} arquivos ({len(b['facts'])} fatos, {len(b['types'])} tipos)")
        return 0
    for p, data in outs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    n = write_manifest()
    print(f"[{core.now()}] DOCS-AWS: {len(b['facts'])} fatos, {len(b['types'])} tipos, "
          f"{len(b['unresolved'])} itens não resolvidos; MANIFEST com {n} arquivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
