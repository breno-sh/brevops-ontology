"""Gera as saídas do DOCS-GCP a partir das páginas copiadas e do schema fixado.

  python -I -m bo.docs_gcp.build            grava tudo
  python -I -m bo.docs_gcp.build --check    regenera em $BO_TMP e compara com o gravado (sai 1 se diverge;
                                            coverage.json é comparado sem generated_at)

Saídas ($BO_DATA/DOCS-GCP/):
  docs_facts.jsonl       C03 3.0.0: um fato por (átomo, tipo de fato, item de origem); unknown explícito
  type_subcategory.jsonl C03 3.1.0 type_fact: um registro por tipo de recurso do schema, com os blocos subcategory
                         (front matter, com linha) e import (formatos aceitos, métodos, identidade, frase-chave)
  unresolved.jsonl       itens da documentação que não viram átomo (bloco, fora do schema, contexto ambíguo)
  redactions.jsonl       frases mascaradas pela regra de privacidade (só id do fato, campo e regra; nunca o valor)
Saída ($BO_REPO/results/DOCS-GCP/): coverage.json (C15 result; censo dos átomos do schema fixado).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bo.repo import core, privacy

from . import coverage as COV
from . import extract as X
from . import mdparse as MD
from . import resolve as R
from . import sources as S

MAX_SENTENCE = 600
MAX_DESCRIPTION = 2000
PAGE_GLOB = "r/*.html.markdown"


def _clip(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


class Sanitizer:
    """Mascara, em frase e valor, o que o privacy_lint reprovaria (exemplos da documentação pública: e-mails de
    exemplo fora de example.*, ARNs, 12 dígitos). O texto mascarado vira '[omitido:<regra>]'. Registro: só regra."""

    def __init__(self):
        self.lists, _ = privacy.load_lists()
        self.list_res = privacy._list_regexes(self.lists)
        self.log: list = []

    def _mask(self, s: str, hits: list) -> str:
        spans = []
        for m in re.finditer(r"(?<!\d)\d{12}(?!\d)", s):
            if not any(a <= m.start() and m.end() <= b for a, b in (x.span() for x in privacy.HEX_TOKEN.finditer(s))):
                spans.append((m.start(), m.end(), "doze_digitos"))
        for rule, rx in privacy.RULES + self.list_res:
            for m in rx.finditer(s):
                if rule == "email" and privacy.ALLOWED_EMAIL_DOMAINS.search(m.group(0)):
                    continue
                spans.append((m.start(), m.end(), rule))
        if not spans:
            return s
        out, pos = [], 0
        for a, b, rule in sorted(spans):
            if a < pos:
                continue
            out.append(s[pos:a])
            out.append(f"[omitido:{rule}]")
            hits.append(rule)
            pos = b
        out.append(s[pos:])
        return "".join(out)

    def _walk(self, v, hits):
        if isinstance(v, str):
            return self._mask(v, hits)
        if isinstance(v, list):
            return [self._walk(x, hits) for x in v]
        if isinstance(v, dict):
            return {k: self._walk(x, hits) for k, x in v.items()}
        return v

    def clean(self, rec: dict) -> dict | None:
        hits: list = []
        if "source" in rec:
            rec["source"]["sentence"] = self._mask(rec["source"]["sentence"], hits)
        if "value" in rec:
            rec["value"] = self._walk(rec["value"], hits)
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        if privacy.scan_text(line, "docs_facts.jsonl", self.lists):
            self.log.append({"fact_id": rec["fact_id"], "action": "dropped", "rules": sorted(set(hits)) or ["?"]})
            return None
        if hits:
            self.log.append({"fact_id": rec["fact_id"], "action": "masked", "rules": sorted(set(hits))})
        return rec


def _sentence(sent, item, bullet) -> tuple[str, int]:
    """(frase, linha). Frase curta demais (< 5 car., mínimo do C03) cai na descrição inteira e, por fim, na
    linha crua do item, com a linha correspondente."""
    t = _clip(sent.text, MAX_SENTENCE) if sent else ""
    if len(t) >= 5:
        return t, sent.line
    t = _clip(item.description, MAX_SENTENCE)
    if len(t) >= 5:
        return t, (item.sentences[0].line if item.sentences else bullet.line)
    return _clip(bullet.lines[0][1].strip(), MAX_SENTENCE), bullet.line


def build(out_dir: Path, res_dir: Path, at: str) -> dict:
    types = S.load_types()
    schema_types = set(types)
    version = S.version()
    commit, commit_date = S.tag_commit()
    tag = S.tag()
    root = S.docs_root()
    san = Sanitizer()
    facts: list = []
    ids: set = set()
    unresolved: list = []
    type_page: dict = {}
    stats = {"pages": 0, "pages_without_type": [], "bullets": 0, "bullet_resolution": {}, "context_methods": {},
             "pattern_hits": {}, "flag_required_vs_schema": {"agree": 0, "doc_required_schema_not": 0,
                                                             "schema_required_doc_not": 0}}

    def fid(atom_id: str, kind: str, line, extra: str = "") -> str:
        base = f"DF-{atom_id}:{kind}:" + (f"L{line}" if line else "none") + (f":{extra}" if extra else "")
        f, k = base, 2
        while f in ids:
            f, k = f"{base}:{k}", k + 1
        ids.add(f)
        return f

    def src(rel: str, line: int, sentence: str) -> dict:
        return {"repo": S.REPO, "tag": tag, "file": rel, "line": int(line), "sentence": sentence}

    def add(rec: dict):
        rec = san.clean(rec)
        if rec is not None:
            facts.append(rec)

    pages = sorted(root.glob(PAGE_GLOB))
    for path in pages:
        rel = f"{S.DOCS_PREFIX}/{path.relative_to(root)}"
        stem = path.name[: -len(".html.markdown")]
        pg = MD.parse_file(path, rel)
        stats["pages"] += 1
        ptypes = R.page_types(pg, stem, schema_types)
        if not ptypes:
            stats["pages_without_type"].append(rel)
            continue
        for t in ptypes:
            type_page.setdefault(t, []).append((rel, pg))
        items = [X.item_from_lines(b.lines) for b in pg.bullets]
        finds = [X.findings(it) for it in items]
        stats["bullets"] += len(pg.bullets)
        per_bullet_any: list = [[] for _ in pg.bullets]
        for t in ptypes:
            idx = R.TypeIndex.of(types[t])
            bpaths, how = R.bullet_paths(pg, idx)
            for m in how.values():
                stats["context_methods"][m] = stats["context_methods"].get(m, 0) + 1
            req = {a["path"]: a["required"] for a in types[t].atoms}
            for bi, (b, it, fs) in enumerate(zip(pg.bullets, items, finds)):
                per_bullet_any[bi] += [c for _, c in bpaths[bi]]
                for p, cls in bpaths[bi]:
                    if cls != "ATOM":
                        continue
                    atom_id = f"{S.PROVIDER}:{t}:{p}"
                    first = it.sentences[0] if it.sentences else None
                    if b.section == "args" and b.parent is None:
                        dreq = "required" in it.flags
                        if dreq == req[p]:
                            stats["flag_required_vs_schema"]["agree"] += 1
                        elif dreq:
                            stats["flag_required_vs_schema"]["doc_required_schema_not"] += 1
                        else:
                            stats["flag_required_vs_schema"]["schema_required_doc_not"] += 1
                    desc = _clip(it.description, MAX_DESCRIPTION)
                    if len(desc) >= 1:
                        add({"fact_id": fid(atom_id, "description", b.line), "atom_id": atom_id,
                             "provider_version": version, "fact_kind": "description", "status": "stated",
                             "value": desc, "source": src(rel, *_sentence(first, it, b)[::-1]),
                             "extraction_method": "parser", "evidence_level": "published"})
                    for f in fs:
                        stats["pattern_hits"][f.pattern] = stats["pattern_hits"].get(f.pattern, 0) + 1
                        rec = {"fact_id": fid(atom_id, f.kind, f.sentence.line, f.pattern), "atom_id": atom_id,
                               "provider_version": version, "fact_kind": f.kind,
                               "source": src(rel, *_sentence(f.sentence, it, b)[::-1]),
                               "extraction_method": f.method, "evidence_level": "published"}
                        if f.unknown_reason:
                            rec.update(status="unknown", unknown_reason=f.unknown_reason)
                        else:
                            rec.update(status="stated", value=f.value)
                            if f.kind == "default":
                                rec["as_of"] = commit_date
                        add(rec)
        for bi, b in enumerate(pg.bullets):
            cls = per_bullet_any[bi]
            if "ATOM" in cls:
                k = "ATOM"
            elif not cls:
                k = "SUBTEXT" if b.parent is not None else "NO_CONTEXT"
            elif "BLOCK" in cls:
                k = "BLOCK"
            elif "OBJECT_FIELD" in cls:
                k = "OBJECT_FIELD"
            else:
                k = "NOT_IN_SCHEMA"
            stats["bullet_resolution"][k] = stats["bullet_resolution"].get(k, 0) + 1
            if k in ("NO_CONTEXT", "NOT_IN_SCHEMA"):
                unresolved.append({"types": ptypes, "file": rel, "line": b.line, "name": b.name, "class": k,
                                   "section": b.section})

    # contradição: mais de um valor declarado para default (ou unidade) do mesmo átomo -> unknown contradictory
    contradictions = 0
    for kind in ("default", "unit"):
        groups: dict = {}
        for i, f in enumerate(facts):
            if f["fact_kind"] == kind and f["status"] == "stated":
                groups.setdefault(f["atom_id"], []).append(i)
        drop = set()
        for atom_id, ix in groups.items():
            vals = {json.dumps(facts[i]["value"], sort_keys=True) for i in ix}
            if len(vals) > 1:
                contradictions += 1
                drop.update(ix)
                f0 = facts[ix[0]]
                facts.append({"fact_id": fid(atom_id, kind, f0["source"]["line"], "CONTRADICTORY"),
                              "atom_id": atom_id, "provider_version": version, "fact_kind": kind,
                              "status": "unknown", "unknown_reason": "contradictory", "source": f0["source"],
                              "extraction_method": "regex", "evidence_level": "derived"})
                unresolved.append({"atom_id": atom_id, "class": f"CONTRADICTORY_{kind.upper()}",
                                   "lines": sorted({facts[i]["source"]["line"] for i in ix}),
                                   "file": f0["source"]["file"], "n_values": len(vals)})
        facts = [f for i, f in enumerate(facts) if i not in drop]

    # átomo sem descrição documentada -> unknown not_documented (nunca valor inventado)
    described = {f["atom_id"] for f in facts if f["fact_kind"] == "description" and f["status"] == "stated"}
    for t in sorted(types):
        for a in types[t].atoms:
            if a["atom_id"] not in described:
                facts.append({"fact_id": fid(a["atom_id"], "description", None, "NOT_DOCUMENTED"),
                              "atom_id": a["atom_id"], "provider_version": version, "fact_kind": "description",
                              "status": "unknown", "unknown_reason": "not_documented",
                              "extraction_method": "parser", "evidence_level": "derived"})

    # fatos do TIPO (C03 3.1.0, type_subcategory): subcategoria e ID de importação, em blocos
    subcats = [type_fact(t, type_page.get(t, []), version, src) for t in sorted(types)]

    facts.sort(key=lambda f: f["fact_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)
    core_write(out_dir / "docs_facts.jsonl", facts)
    core_write(out_dir / "type_subcategory.jsonl", subcats)
    core_write(out_dir / "unresolved.jsonl", sorted(unresolved, key=lambda u: json.dumps(u, sort_keys=True)))
    core_write(out_dir / "redactions.jsonl", sorted(san.log, key=lambda r: r["fact_id"]))
    stats["pages_without_type"] = sorted(stats["pages_without_type"])
    stats["contradictions"] = contradictions
    stats["redactions"] = {"masked": sum(r["action"] == "masked" for r in san.log),
                           "dropped": sum(r["action"] == "dropped" for r in san.log)}
    stats["source"] = {"repo": S.REPO, "tag": tag, "commit": commit, "commit_date": commit_date}
    (out_dir / "build_stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                                              encoding="utf-8")
    cov = COV.compute(out_dir, types, at)
    (res_dir / "coverage.json").write_text(json.dumps(cov, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"facts": len(facts), "types": len(types), "stats": stats, "coverage": cov}


PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")


def import_block(rel: str, pg, src) -> dict:
    """Bloco import (C03 3.1.0) da seção Import da página."""
    imp = pg.imports
    base = {"extraction_method": "parser", "evidence_level": "published"}
    if imp.formats:
        fmts = [f for _, f in imp.formats]
        ln0, f0 = imp.formats[0]
        blk = {**base, "status": "stated", "supported": True, "value": fmts,
               "source": src(rel, ln0, _clip(pg.lines[ln0 - 1].strip(), MAX_SENTENCE)),
               "statements": [{"line": ln, "sentence": _clip(pg.lines[ln - 1].strip(), MAX_SENTENCE)}
                              for ln, _ in imp.formats if len(pg.lines[ln - 1].strip()) >= 5],
               "placeholders": sorted({p for f in fmts for p in PLACEHOLDER.findall(f)})}
        if not blk["statements"]:
            del blk["statements"]
        if imp.line and len(imp.sentence or "") >= 5:
            blk["key_sentence"] = src(rel, imp.line, _clip(imp.sentence, MAX_SENTENCE))
        if imp.methods:
            blk["methods"] = sorted(imp.methods)
        if imp.identity["required"] or imp.identity["optional"]:
            blk["identity"] = {"required": list(imp.identity["required"]),
                               "optional": list(imp.identity["optional"])}
        return blk
    if imp.unsupported:
        ln, sent = imp.unsupported
        return {**base, "status": "unknown", "unknown_reason": "not_supported", "supported": False,
                "source": src(rel, ln, _clip(sent, MAX_SENTENCE))}
    return {**base, "status": "unknown", "unknown_reason": "not_documented"}


def type_fact(t: str, pages_t: list, version: str, src) -> dict:
    rec = {"type_id": f"{S.PROVIDER}:{t}", "provider": S.PROVIDER, "provider_version": version, "resource_type": t,
           "kind": "resource", "in_schema": True}
    undoc = {"status": "unknown", "unknown_reason": "not_documented", "extraction_method": "parser",
             "evidence_level": "derived"}
    if not pages_t:
        rec.update(doc_file=None, subcategory=dict(undoc), **{"import": dict(undoc)})
        return rec
    rel, pg = pages_t[0]
    rec["doc_file"] = rel
    rec["doc_pages"] = [r for r, _ in pages_t]
    heads = [ln for ty, ln in pg.types if ty == t]
    if heads:
        rec["title"] = {"text": t, "line": heads[0]}
    if pg.subcategory:
        rec["subcategory"] = {"status": "stated", "value": pg.subcategory, "extraction_method": "parser",
                              "evidence_level": "published",
                              "source": src(rel, pg.subcategory_line, f'subcategory: "{pg.subcategory}"')}
    else:
        rec["subcategory"] = dict(undoc)
    rec["import"] = import_block(rel, pg, src)
    return rec


def core_write(path: Path, recs) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


OUT_FILES = ("docs_facts.jsonl", "type_subcategory.jsonl", "unresolved.jsonl", "redactions.jsonl", "build_stats.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.docs_gcp.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    at = core.now()
    if a.check:
        tmp = S.bo_tmp() / "check"
        r = build(tmp / "data", tmp / "results", at)
        bad = []
        for n in OUT_FILES:
            if (tmp / "data" / n).read_bytes() != (S.out_dir() / n).read_bytes():
                bad.append(n)
        old = json.loads((S.results_dir() / "coverage.json").read_text(encoding="utf-8"))
        new = r["coverage"]
        old.pop("generated_at", None)
        new = {k: v for k, v in new.items() if k != "generated_at"}
        if old != new:
            bad.append("coverage.json")
        print(f"[{at}] regeneração: {'idêntica' if not bad else 'DIVERGE em ' + ', '.join(bad)} "
              f"({r['facts']} fatos, {r['types']} tipos)")
        return 1 if bad else 0
    r = build(S.out_dir(), S.results_dir(), at)
    st = r["stats"]
    print(f"[{at}] {st['pages']} páginas, {st['bullets']} itens, {r['facts']} fatos, {r['types']} tipos; "
          f"itens: {st['bullet_resolution']}; mascarados {st['redactions']}")
    for m in r["coverage"]["metrics"]:
        c = m["operational_coverage"]
        print(f"  {m['metric_id']}: {c['est']:.4f} (n={c['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
