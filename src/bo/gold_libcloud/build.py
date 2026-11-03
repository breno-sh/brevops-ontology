"""python -I -m bo.gold_libcloud.build [--fetch] [--check]

Gera, a partir do código-fonte fixado do Apache Libcloud (lido só com ast):
  $BO_DATA/GOLD-LIBCLOUD/libcloud.sssom.tsv   C09: campo da API do provedor -> campo normalizado do Libcloud
  $BO_DATA/GOLD-LIBCLOUD/api_fields.jsonl     registro dos campos de API (sujeitos), com sítios arquivo:linha
  $BO_DATA/GOLD-LIBCLOUD/extra_fields.jsonl   chaves de 'extra' (do driver, não normalizadas) e suas origens
  $BO_DATA/GOLD-LIBCLOUD/coverage.jsonl       cada (construção, campo normalizado) com o tipo de alimentação
  $BO_REPO/results/GOLD-LIBCLOUD/stats.json   contagens por provedor, domínio, tipo e relação
--fetch baixa e extrai a fonte (se faltar); --check regenera em memória e compara byte a byte.

Regras de relação (fixas, escritas antes de ver os números; R1-R6):
  R1 direto, fonte única            exact   equal    lossless       identity
  R2 conversão de tipo, fonte única exact   equal    lossless       sem função do núcleo (prova: cast)
  R3 tabela de estados (enum)       exact/equal/lossless/enum_map se a tabela é injetiva e não há valor
                                    padrão; senão close/overlap/declared_loss/enum_map com a perda declarada
  R4 uma de várias fontes           close   subset   partial        como R1-R3; perda 'semantic'
  R5 derivado (chamada, expressão, formatação, só em parte dos ramos)  related unknown none, sem função
  R6 sem campo de API resolvido (chamada não seguida, constantes por ramo)   related, evidence UNRESOLVED
'direto' admite: embrulhar em lista, iterar itens, valor na ausência (None, [], ''), seguir um helper do
mesmo arquivo. Linha resolvida = STRUCTURALLY_VALID (bem formada no C09); o nível (publicado, derivado,
interpretado) é do GOLD-AUDIT. O silêncio do Libcloud (campo que nenhum driver lê) não é negativo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import extract as X
from . import source as S
from .flow import NEUTRAL_OPS, Sym

MODULE = "GOLD-LIBCLOUD"
TOOL = "bo.gold_libcloud"
TOOL_VERSION = "1.0.0"
MAPPING_SET_ID = f"https://w3id.org/brevops/gold/libcloud/{S.VERSION}"
NS_API = f"https://w3id.org/brevops/gold/libcloud/{S.VERSION}/api/"
NS_MODEL = f"https://w3id.org/brevops/gold/libcloud/{S.VERSION}/model/"
GITHUB = f"https://github.com/apache/libcloud/blob/v{S.VERSION}/"
RELEASE_DATE = S.UPLOADED[:10]
CONST_ABSENCE = {"None", "[]", "''", "{}", "0", "False", '""'}


def bo_repo() -> Path:
    import os
    return Path(os.environ.get("BO_REPO", Path(__file__).resolve().parents[3]))


def out_dir() -> Path:
    return S.bo_data() / MODULE


# --------------------------------------------------------------------------------------------- classificação
def op_kind(ops: tuple) -> str:
    core = [op for op in ops if op not in NEUTRAL_OPS and not op.startswith("via:")]
    if not core:
        return "direct"
    if all(op.startswith("cast:") for op in core):
        return "cast"
    if all(op.startswith(("cast:", "enum:")) for op in core) and sum(op.startswith("enum:") for op in core) == 1:
        return "enum"
    return "derived"


def merge_kinds(kinds: set) -> str:
    if len(kinds) == 1:
        return next(iter(kinds))
    if "derived" in kinds:
        return "conditional"
    if "enum" in kinds:
        return "enum" if kinds <= {"enum", "direct", "cast"} else "conditional"
    return "cast"


def is_api(o, cls: str, func: str, api: set) -> bool:
    return o.kind == "field" and (o.root.startswith("response") or (cls, func, o.root) in api)


def root_label(o) -> str:
    if o.root.startswith("response"):
        vias = [op[4:] for op in o.ops if op.startswith("via:")]
        return o.root + ("@" + vias[-1] if vias else "")
    return o.root


def feed_class(f: X.Feed, api: set) -> tuple[str, list]:
    """(tipo de alimentação, origens de API com caminho)."""
    o = f.value.o
    apis = [x for x in o if is_api(x, f.cls, f.func, api) and any(k != "*" for k in x.path) and "?" not in x.path]
    if apis:
        return "api", apis
    if any(x.kind == "opaque" for x in o) or any(is_api(x, f.cls, f.func, api) for x in o):
        return "opaque", []
    if any(x.kind == "field" for x in o):
        return "input", []
    if any(x.kind == "ctx" for x in o):
        return "context", []
    notes = {x.note for x in o if x.kind == "const"}
    if len(notes) > 1:
        return "opaque", []      # constantes diferentes escolhidas por ramo: depende de algo não resolvido
    return "constant", []


def subject_local(f: X.Feed, o) -> str:
    path = "/".join(str(p).replace(" ", "_").replace("\t", "_") for p in o.path)
    return f"{f.cls}.{f.func}/{root_label(o)}/{path}"


def prefix_of(f: X.Feed) -> str:
    return f"lcapi.{f.domain}.{f.stem}"


def object_id(f: X.Feed) -> str:
    return f"lcm:{f.target}.{f.field}"


def enum_class_values(tbl, syms: dict) -> list | None:
    """Todos os valores da classe de estados usada na tabela (NodeState.* em types.py), se é uma só."""
    if not isinstance(tbl, dict):
        return None
    classes = {str(v).rsplit(".", 1)[0] for v in tbl.values() if isinstance(v, Sym) and "." in v}
    if len(classes) != 1:
        return None
    c = classes.pop()
    vals = sorted({str(v) for k, v in syms.items() if k.rsplit(".", 1)[0] == c})
    return vals or None


def resolve_table(tbl, syms: dict):
    """Tabela do código -> {str(chave): str(valor)}; valores simbólicos resolvidos em types.py."""
    if not isinstance(tbl, dict):
        return None
    out = {}
    for k, v in tbl.items():
        if isinstance(v, Sym):
            if str(v) not in syms:
                return None
            v = syms[str(v)]
        elif not isinstance(v, (str, int, float, bool)) or v is None:
            return None
        out["true" if k is True else "false" if k is False else str(k)] = v if isinstance(v, str) else str(v)
    return out


def claim_id(subject: str, obj: str) -> str:
    return "LC-" + hashlib.sha256(f"{subject}\0{obj}".encode()).hexdigest()[:10]


def build(pkg: Path) -> dict:
    ex, norm = X.extract(pkg)
    syms = X.sym_values(pkg)
    rows: dict[tuple, dict] = {}
    registry: dict[str, dict] = {}
    extras: dict[tuple, dict] = {}
    coverage = []
    for f in ex.feeds:
        api = ex.api_params.get(f.module, set())
        kind, apis = feed_class(f, api)
        if f.field.startswith("extra.") or f.field == "extra":
            if f.field == "extra":
                coverage.append({"site": f.site, "target": f.target, "field": f.field, "feed": kind})
                continue
            key = (f.site, f.field)
            extras[key] = {"site": f.site, "provider": f.stem, "project_provider": f.provider, "domain": f.domain,
                           "target": f.target, "extra_key": f.field[6:], "feed": kind,
                           "api_fields": sorted({f"{prefix_of(f)}:{subject_local(f, o)}" for o in apis}),
                           "kinds": sorted({op_kind(o.ops) for o in apis})}
            continue
        coverage.append({"site": f.site, "target": f.target, "field": f.field, "feed": kind})
        if kind == "opaque":
            subj = f"{prefix_of(f)}:{f.cls}.{f.func}/?"
            r = rows.setdefault((subj, object_id(f)), {"f": f, "kinds": set(), "sites": set(), "multi": False,
                                                      "fallback": set(), "tables": set(), "unresolved": True,
                                                      "origins": []})
            r["sites"].add((f.module, f.line))
            continue
        if kind != "api":
            continue
        paths = {(o.root, o.path) for o in apis}
        others = [o for o in f.value.o if o not in apis]
        nonconst_other = [o for o in others if o.kind != "const"]
        consts = {o.note for o in others if o.kind == "const"}
        for o in apis:
            subj = f"{prefix_of(f)}:{subject_local(f, o)}"
            r = rows.setdefault((subj, object_id(f)), {"f": f, "kinds": set(), "sites": set(), "multi": False,
                                                      "fallback": set(), "tables": set(), "unresolved": False,
                                                      "origins": []})
            r["kinds"].add(op_kind(o.ops))
            r["sites"].add((f.module, o.line or f.line))
            r["origins"].append(o)
            if len(paths) > 1 or nonconst_other:
                r["multi"] = True
            r["fallback"] |= consts
            for op in o.ops:
                if op.startswith("enum:"):
                    r["tables"].add((f.module, op[5:]))
            reg = registry.setdefault(subj, {
                "subject_id": subj, "provider": f.stem, "project_provider": f.provider, "domain": f.domain,
                "module": f.module, "class": f.cls, "function": f.func, "root": root_label(o),
                "path": list(o.path), "sites": set(), "feeds": set()})
            reg["sites"].add((f.module, o.line or f.line))
            reg["feeds"].add(object_id(f))
    records = []
    for (subj, obj), r in sorted(rows.items()):
        records.append(make_record(subj, obj, r, ex, syms))
    ids = [x["claim_id"] for x in records]
    if len(ids) != len(set(ids)):
        raise SystemExit("colisão de claim_id: aumente o sufixo")
    reg_list = []
    for s in sorted(registry):
        g = registry[s]
        g["sites"] = [{"file": m, "line": ln} for m, ln in sorted(g["sites"])]
        g["feeds"] = sorted(g["feeds"])
        reg_list.append(g)
    cov = sorted(coverage, key=lambda c: (c["site"].split(":")[0], int(c["site"].split(":")[1]), c["field"]))
    for site, tgt, fld in ex.absent:
        cov.append({"site": site, "target": tgt, "field": fld, "feed": "absent"})
    cov.sort(key=lambda c: (c["site"].split(":")[0], int(c["site"].split(":")[1]), c["field"], c["feed"]))
    return {"records": records, "registry": reg_list, "extras": [extras[k] for k in sorted(extras)],
            "coverage": cov, "ex": ex, "norm": norm}


def make_record(subj: str, obj: str, r: dict, ex, syms) -> dict:
    f = r["f"]
    cid = claim_id(subj, obj)
    sites = sorted(r["sites"])
    ev = [{"source": f"libcloud@{S.VERSION}:{m}#L{ln}", "date": RELEASE_DATE,
           "sentence": (f"o driver {f.stem} do Libcloud {S.VERSION} preenche {obj.split(':', 1)[1]} "
                        f"a partir deste campo ({m}:{ln})" if not r["unresolved"] else
                        f"o driver {f.stem} do Libcloud {S.VERSION} preenche {obj.split(':', 1)[1]} por uma "
                        f"chamada que a leitura por ast não resolve até um campo da API ({m}:{ln})")}
          for m, ln in sites[:5]]
    rec = {"subject_id": subj, "object_id": obj, "claim_id": cid, "claim_version_id": f"{cid}@1",
           "event_id": f"EV-{cid}-1", "guard": {"all": []}, "subject_concept": "bo:UNGLOSSED",
           "object_concept": "bo:UNGLOSSED", "basis": "direct",
           "subject_label": subj.split(":", 1)[1], "object_label": obj.split(":", 1)[1],
           "subject_source": f"{GITHUB}{f.module}", "subject_source_version": S.VERSION,
           "object_source": f"{GITHUB}libcloud/{f.target.split('.')[0]}/base.py",
           "object_source_version": S.VERSION, "author_label": "Apache Libcloud contributors",
           "mapping_provider": "https://libcloud.apache.org", "mapping_tool": TOOL,
           "mapping_tool_version": TOOL_VERSION, "publication_date": RELEASE_DATE, "license": S.LICENSE_URI,
           "see_also": f"{GITHUB}{sites[0][0]}#L{sites[0][1]}", "subject_category": f.provider,
           "object_category": f.domain}
    if r["unresolved"]:
        rec.update(predicate_id="skos:relatedMatch", semantic_relation="related",
                   mapping_justification="semapv:UnspecifiedMatching",
                   value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
                   transport_fidelity="none", translation_fn=None,
                   loss_contract=[{"kind": "not_expressible", "detail": "origem não resolvida"}],
                   evidence_state="UNRESOLVED", curation_rule="R6",
                   proof={"type": "none", "evidence": ev, "tests": [], "sites": len(sites)})
        return rec
    kind = merge_kinds(r["kinds"])
    casts = sorted({op[5:] for o in r["origins"] for op in o.ops if op.startswith("cast:")})
    absence = sorted(x for x in r["fallback"] if x in CONST_ABSENCE)
    proof = {"evidence": ev, "tests": [], "sites": len(sites), "extraction": kind}
    if absence:
        proof["absence"] = absence
    rec.update(mapping_justification="semapv:ManualMappingCuration", evidence_state="STRUCTURALLY_VALID")
    if kind in ("derived", "conditional"):
        rec.update(predicate_id="skos:relatedMatch", semantic_relation="related",
                   value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
                   transport_fidelity="none", translation_fn=None, curation_rule="R5",
                   loss_contract=[{"kind": "not_expressible",
                                   "detail": "transformação no código (chamada, expressão ou só em parte dos ramos)"}],
                   proof=dict(proof, type="none",
                              ops=sorted({op for o in r["origins"] for op in o.ops
                                          if op not in NEUTRAL_OPS and not op.startswith("via:")})))
        return rec
    fn, losses, vdr, fid, rel, rule = None, [], "equal", "lossless", "exact", "R1"
    if kind == "direct":
        fn = {"name": "identity", "params": {}}
        proof["type"] = "normalization"
        proof["normalization"] = {"op": "identity"}
    elif kind == "cast":
        rule = "R2"
        proof["type"] = "normalization"
        proof["normalization"] = {"op": "cast", "to": casts}
    else:   # enum
        rule = "R3"
        (mod, name), = sorted(r["tables"])[:1] or [(None, None)]
        table = resolve_table(ex.tables.get((mod, name)), syms)
        proof["type"] = "normalization"
        proof["normalization"] = {"op": "enum_map", "table_name": name}
        if table:
            fn = {"name": "enum_map", "params": {"table": table}}
            proof["tests"] = [{"input": k, "expected": v} for k, v in sorted(table.items())[:5]]
            rec["subject_value_type"] = {"datatype": "enum", "enum": sorted(table),
                                         "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}
            image = sorted(set(table.values()))
            codomain = enum_class_values(ex.tables.get((mod, name)), syms) or image
            rec["object_value_type"] = {"datatype": "enum", "enum": codomain,
                                        "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}
            injective = len(image) == len(table)
            sentinels = sorted(x for x in r["fallback"] if x not in CONST_ABSENCE)
            if set(image) < set(codomain):
                vdr = "subset"
            if not injective:
                losses.append({"kind": "semantic", "detail": f"{len(table)} valores do provedor em "
                                                               f"{len(set(table.values()))} estados normalizados"})
            if sentinels:
                sv = [syms.get(s, s) for s in sentinels]
                losses.append({"kind": "not_expressible", "detail": "valor fora da tabela vira o padrão",
                               "default": sv})
                losses.append({"kind": "sentinel", "map": {"*": sv[0]}})
            if losses:
                rel, fid = "close", "declared_loss"
        else:
            rel, vdr, fid = "close", "unknown", "declared_loss"
            losses.append({"kind": "not_expressible", "detail": f"tabela {name} não é constante legível"})
    if r["multi"]:
        rule = "R4"
        rel, vdr, fid = "close", "subset", "partial"
        losses.append({"kind": "semantic", "detail": "o campo normalizado também vem de outra fonte "
                                                      "(fallback ou ramo); este campo é uma das fontes"})
    pred = {"exact": "skos:exactMatch", "close": "skos:closeMatch"}[rel]
    rec.update(predicate_id=pred, semantic_relation=rel, curation_rule=rule,
               value_domain_relation={"relation": vdr, "orientation": "subject_to_object"},
               transport_fidelity=fid, translation_fn=fn, loss_contract=losses, proof=proof)
    return rec


# --------------------------------------------------------------------------------------------- escrita
def prefixes(records: list) -> dict:
    from bo.semantics import sssom_io as SIO
    pm = {k: v for k, v in SIO.PREFIXES.items() if k in ("skos", "semapv", "bosx", "bo", "concept")}
    for r in records:
        p = r["subject_id"].split(":", 1)[0]
        _, dom, stem = p.split(".", 2)
        pm[p] = f"{NS_API}{dom}/{stem}/"
    pm["lcm"] = NS_MODEL
    return dict(sorted(pm.items()))


def render(res: dict) -> dict[str, str]:
    from bo.contracts import sssom as CS
    recs = res["records"]
    tsv = CS.write_tsv(recs, MAPPING_SET_ID, prefixes(recs))
    # licença do conjunto: a da fonte (Apache-2.0), não a CC0 padrão do escritor
    from bo.semantics import sssom_io as SIO
    tsv = tsv.replace(f"# license: {SIO.LICENSE}\n", f"# license: {S.LICENSE_URI}\n", 1)
    jl = lambda xs: "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in xs)  # noqa: E731
    return {"libcloud.sssom.tsv": tsv, "api_fields.jsonl": jl(res["registry"]),
            "extra_fields.jsonl": jl(res["extras"]), "coverage.jsonl": jl(res["coverage"])}


def stats(res: dict, src: dict) -> dict:
    recs, ex = res["records"], res["ex"]
    by = lambda key: dict(sorted(Counter(key(r) for r in recs).items()))  # noqa: E731
    cov = Counter(c["feed"] for c in res["coverage"])
    from bo.semantics.obligations import assess
    verdicts = Counter()
    rules = Counter()
    for r in recs:
        a = assess(r)
        verdicts[a.verdict] += 1
        for f in a.failures:
            rules[f"{f['rule']}:{f['outcome']}"] += 1
    proj = defaultdict(Counter)
    for r in recs:
        proj[r["subject_category"]][r["semantic_relation"] + ("/UNRESOLVED" if r["evidence_state"] == "UNRESOLVED"
                                                              else "")] += 1
    providers_present = sorted({r["subject_category"] for r in recs})
    return {
        "source": {"version": S.VERSION, "sdist_sha256": src["sha256"], "py_files": src["py_files"],
                   "tree_digest": src["tree_digest"]},
        "driver_modules": len(ex.modules), "functions_read": ex.functions, "construction_sites": ex.sites,
        "interpreter_failures": len(ex.failures),
        "normalized_classes": sorted(res["norm"]),
        "rows": len(recs), "api_fields": len(res["registry"]), "extra_keys": len(res["extras"]),
        "rows_by_relation": by(lambda r: r["semantic_relation"]),
        "rows_by_rule": by(lambda r: r["curation_rule"]),
        "rows_by_evidence_state": by(lambda r: r["evidence_state"]),
        "rows_by_domain": by(lambda r: r["object_category"]),
        "rows_by_project_provider": by(lambda r: r["subject_category"]),
        "rows_by_project_provider_and_relation": {k: dict(sorted(v.items())) for k, v in sorted(proj.items())},
        "rows_by_target": by(lambda r: r["object_id"].split(":", 1)[1].rsplit(".", 1)[0]),
        "feeds_core_fields": dict(sorted(cov.items())),
        "extra_feeds": dict(sorted(Counter(e["feed"] for e in res["extras"]).items())),
        "project_providers_without_driver": [p for p in ("aws", "gcp", "azure", "oci") if p not in providers_present],
        "semantics_assess_verdicts": dict(sorted(verdicts.items())),
        "semantics_assess_failures": dict(sorted(rules.items())),
    }


def write_all(res: dict, src: dict) -> list[Path]:
    od = out_dir()
    od.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in render(res).items():
        p = od / name
        p.write_text(text, encoding="utf-8")
        written.append(p)
    rd = bo_repo() / "results" / MODULE
    rd.mkdir(parents=True, exist_ok=True)
    p = rd / "stats.json"
    p.write_text(json.dumps(stats(res, src), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    written.append(p)
    return written


def manifest_entries() -> list[tuple[str, Path]]:
    """Arquivos do MANIFEST C17 (caminhos portáveis); summary.json e resolve_report.json ficam de fora
    (carimbo de hora)."""
    d = "$BO_DATA/GOLD-LIBCLOUD/"
    out = [(f"$BO_DATA/downloads/libcloud/{S.SDIST}", S.sdist_path()),
           ("$BO_DATA/downloads/libcloud/SOURCE.txt", S.download_dir() / "SOURCE.txt")]
    out += [(d + n, out_dir() / n) for n in ("libcloud.sssom.tsv", "api_fields.jsonl", "extra_fields.jsonl",
                                             "coverage.jsonl")]
    out += [(f"$BO_REPO/results/{MODULE}/stats.json", bo_repo() / "results" / MODULE / "stats.json"),
            (f"$BO_REPO/gates/{MODULE}.sh", bo_repo() / "gates" / f"{MODULE}.sh")]
    return out


def write_manifest() -> Path:
    p = bo_repo() / "results" / MODULE / "MANIFEST.sha256"
    p.write_text("".join(f"{S.sha256_file(f)}  {rel}\n" for rel, f in manifest_entries()), encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.gold_libcloud.build")
    ap.add_argument("--fetch", action="store_true", help="baixa e extrai a fonte fixada se faltar")
    ap.add_argument("--manifest", action="store_true", help="só regrava results/GOLD-LIBCLOUD/MANIFEST.sha256")
    ap.add_argument("--check", action="store_true", help="regenera em memória e compara com o que está gravado")
    a = ap.parse_args(argv)
    if a.manifest:
        print(f"gravado {write_manifest()}")
        return 0
    src = S.fetch() if a.fetch else S.verify()
    res = build(S.pkg_root())
    if a.check:
        bad = []
        for name, text in render(res).items():
            p = out_dir() / name
            if not p.is_file() or p.read_text(encoding="utf-8") != text:
                bad.append(str(p))
        st = json.dumps(stats(res, src), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        p = bo_repo() / "results" / MODULE / "stats.json"
        if not p.is_file() or p.read_text(encoding="utf-8") != st:
            bad.append(str(p))
        if bad:
            print("regeneração diverge: " + ", ".join(bad), file=sys.stderr)
            return 1
        print(f"regeneração idêntica: {len(res['records'])} linhas, {len(res['registry'])} campos de API")
        return 0
    for p in write_all(res, src):
        print(f"gravado {p}")
    print(f"gravado {write_manifest()}")
    print(f"{len(res['records'])} linhas SSSOM, {len(res['registry'])} campos de API, "
          f"{len(res['extras'])} chaves de extra")
    return 0


if __name__ == "__main__":
    sys.exit(main())
