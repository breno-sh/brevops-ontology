"""Gera o ouro do GOLD-XPLANE a partir de $BO_DATA/downloads/crossplane/ (sem rede).

  python -I -m bo.gold_xplane.build            grava as saídas
  python -I -m bo.gold_xplane.build --check    regenera em $BO_TMP e confere byte a byte (fora o carimbo)

Saídas:
  $BO_DATA/GOLD-XPLANE/crossplane.sssom.tsv  C09 3.0.0: linhas P (patch: campo do XR <-> campo do MR) e D (derivadas:
                                             MR do provedor A <-> MR do provedor B pelo mesmo campo do XR)
  $BO_DATA/GOLD-XPLANE/patches.jsonl         todo ponto final extraído, com categoria, resolução e ponte Terraform
  $BO_DATA/GOLD-XPLANE/resolution.json       contagens de resolução (lidas pelo bo.gold_xplane.resolve)
  $BO_REPO/results/GOLD-XPLANE/stats.json    números do módulo (relatório, com carimbo)

Regras (declaradas antes de olhar os números):
  * nível DERIVADO em toda linha (proof.evidence[].level = derived; curation_rule); patch não prova exact;
  * close só quando a cadeia de transformações dos dois lados compõe numa função do núcleo (identity, scale,
    enum_map), com perda semântica declarada; senão related (sem função, fidelidade none);
  * evidence_state STRUCTURALLY_VALID quando os dois lados resolvem no schema fixado (XRD/CRD); senão UNRESOLVED;
  * linhas SSSOM só para os 4 provedores do projeto e para campos do provider (forProvider/initProvider,
    atProvider, external-name); referência/seletor, metadados e campos de controle do Crossplane ficam no
    patches.jsonl com a categoria, sem linha SSSOM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

from bo.contracts import sssom as CSSSOM

from . import sources
from .extract import Extractor
from .paths import data_dir, downloads_dir, now_iso, results_dir, tmp_dir

PROVIDERS = ("aws", "google", "azurerm", "oci")
SSSOM_CATS = ("param", "observed", "external_name")
MAPPING_SET_ID = "https://w3id.org/brevops/gold/crossplane"
LICENSE = "https://www.apache.org/licenses/LICENSE-2.0"
LICENSE_URI = {"Apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0", "MIT": "https://opensource.org/licenses/MIT"}
PREFIXES = {
    "aws": "https://w3id.org/brevops/atom/aws/", "google": "https://w3id.org/brevops/atom/google/",
    "azurerm": "https://w3id.org/brevops/atom/azurerm/", "oci": "https://w3id.org/brevops/atom/oci/",
    "xpxr": "https://w3id.org/brevops/crossplane/xr/", "xpmr": "https://w3id.org/brevops/crossplane/mr/",
    "skos": "http://www.w3.org/2004/02/skos/core#", "semapv": "https://w3id.org/semapv/vocab/",
    "bosx": "https://w3id.org/brevops/sssom-ext#", "bo": "https://w3id.org/brevops/ontology#",
    "concept": "https://w3id.org/brevops/glossary#",
}
LEVEL_RULE = "GOLD-XPLANE:nivel=DERIVADO"
SEMANTIC_LOSS = {"kind": "semantic",
                 "note": "patch de composição: o autor ligou os dois campos ao mesmo parâmetro do XR; isso não "
                         "prova o mesmo significado nem o mesmo domínio (nível DERIVADO)"}


# --------------------------------------------------------------------------------- transformações
def step_of(t: dict):
    """Transformação Crossplane -> passo do núcleo, ou None se não compõe (string, convert, match, ...)."""
    typ = (t.get("type") or "").lower()
    if typ == "map":
        table = {str(k): v for k, v in (t.get("map") or {}).items() if k != "__line__"}
        return ("enum_map", table) if table else None
    if typ == "math":
        m = t.get("math") or {}
        mt = (m.get("type") or "Multiply").lower()
        if mt == "multiply" and isinstance(m.get("multiply"), (int, float)):
            return ("scale", Fraction(str(m["multiply"])))
        return None
    return None


def _apply(steps, v):
    for name, p in steps:
        if name == "enum_map":
            k = "true" if v is True else "false" if v is False else str(v)
            if k not in p:
                raise KeyError(k)
            v = p[k]
        else:
            v = Fraction(str(v)) * p
            v = int(v) if v.denominator == 1 else v
    return v


def _num(x):
    if isinstance(x, Fraction):
        return int(x) if x.denominator == 1 else float(x)
    return x


def chain_steps(chain):
    out = []
    for t in chain:
        s = step_of(t)
        if s is None:
            return None
        out.append(s)
    return out


def single_fn(pairs: dict | None, factor: Fraction | None):
    """Função do núcleo de um passo: identity, scale ou enum_map (com testes tirados dos próprios dados)."""
    if pairs is not None:
        if not pairs:
            return None, []
        table = {k: _num(v) for k, v in sorted(pairs.items())}
        tests = [{"input": k, "expected": v} for k, v in table.items()]
        return {"name": "enum_map", "params": {"table": table}}, tests
    if factor == 1:
        return {"name": "identity", "params": {}}, []
    return {"name": "scale", "params": {"factor": _num(factor)}}, [{"input": 1, "expected": _num(factor)}]


def compose_forward(sa, sb):
    """to_mr: a = A(x), b = B(x). Devolve a função a -> b (uma só, do núcleo) ou None."""
    if sa is None or sb is None:
        return None
    maps = [p for n, p in sa + sb if n == "enum_map"]
    if not maps:
        fa = _prod(sa)
        fb = _prod(sb)
        return single_fn(None, fb / fa)
    dom = next(iter(p for n, p in sa if n == "enum_map"), None) or next(p for n, p in sb if n == "enum_map")
    pairs = {}
    for x in dom:
        try:
            a, b = _apply(sa, x), _apply(sb, x)
        except (KeyError, ValueError, TypeError, ArithmeticError):
            continue
        ka = "true" if a is True else "false" if a is False else str(_num(a))
        if ka in pairs and pairs[ka] != b:
            return None          # dois valores de x com o mesmo a e b diferentes: a -> b não é função
        pairs[ka] = b
    return single_fn(pairs, None)


def compose_backward(sa, sb):
    """to_xr: x = A(a), x = B(b). Devolve a -> b = B⁻¹(A(a)) ou None."""
    if sa is None or sb is None:
        return None
    if not any(n == "enum_map" for n, _ in sa + sb):
        return single_fn(None, _prod(sa) / _prod(sb))
    if not sb and len(sa) == 1:          # b = x = A(a)
        return single_fn({k: v for k, v in sa[0][1].items()}, None)
    if not sa and len(sb) == 1:          # a = x = B(b): b = B⁻¹(a), só se B é injetiva
        inv = {}
        for b, x in sb[0][1].items():
            if str(x) in inv:
                return None
            inv[str(x)] = b
        return single_fn(inv, None)
    mb = [p for n, p in sb if n == "enum_map"]
    ma = [p for n, p in sa if n == "enum_map"]
    if not ma or not mb or len(sa) != 1 or len(sb) != 1:
        return None
    inv = {}
    for b, x in mb[0].items():
        kx = str(x)
        if kx in inv and inv[kx] != b:
            return None
        inv[kx] = b
    pairs = {a: inv[str(x)] for a, x in ma[0].items() if str(x) in inv}
    return single_fn(pairs, None)


def _prod(steps):
    f = Fraction(1)
    for _, p in steps:
        f *= p
    return f


def fn_xr_to_mr(e):
    """Cadeia XR -> MR (to_mr) ou MR -> XR (to_xr) de um ponto final, na ordem do fluxo do valor."""
    hops = e["trail"] if e["direction"] == "to_mr" else list(reversed(e["trail"]))
    chain = [t for h in hops for t in h["transforms"]]
    return chain, chain_steps(chain)


# ------------------------------------------------------------------------------------------- ids e tipos
def mr_id(e):
    b = e["mr_resolution"].get("bridge") or {}
    if b.get("status") == "resolved":
        return f"{e['provider']}:{b['tf_type']}:{b['tf_path']}", "terraform_attribute"
    m = e["mr"]
    return f"xpmr:{m['group']}/{m['version']}/{m['kind']}/{e['mr_path']}", "crossplane_mr_field"


def xr_id(e, path):
    x = e["xr"]
    return f"xpxr:{x['group']}/{x['version']}/{x['kind']}/{path}"


def vt(res):
    v = (res or {}).get("value_type")
    if not v:
        return None
    v = dict(v)
    if v["datatype"] in ("string", "enum", "boolean"):
        v.update(quantity_kind="NOT_APPLICABLE", unit="NOT_APPLICABLE")
    return v


def short(s: str, n=10) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:n]


def evidence_item(h):
    src = sources.source_by_id(h["source"])
    frm = h["from"] if isinstance(h["from"], str) else ",".join(h["from"] or [])
    return {"level": "derived", "ref": f"github:{src['repo']}@{src['commit']}:{h['file']}#L{h['line']}",
            "note": f"{h['type']} {frm} -> {h['to']} (composição {h['composition']}, recurso {h['resource']})"}


def realization(e):
    return (e["top_source"], e["top_file"], e["composition"], e.get("top_condition") or "",
            tuple(h["composition"] for h in e["trail"][1:]))


def resolved_side(res, xr=False):
    if xr:
        return res["status"] in ("resolved", "runtime")
    return res["status"] == "resolved" or (res["status"] == "runtime" and res.get("category") == "external_name")


# ---------------------------------------------------------------------------------------------- linhas
def base_row(cid, subj, obj, rel, fn, tests, evidence, state, basis, just, extra):
    close = rel == "close"
    r = {"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
         "subject_id": subj, "object_id": obj, "predicate_id": "skos:closeMatch" if close else "skos:relatedMatch",
         "semantic_relation": rel, "mapping_justification": just,
         "value_domain_relation": {"orientation": "subject_to_object", "relation": "unknown"},
         "transport_fidelity": "declared_loss" if close else "none", "guard": {"all": []},
         "translation_fn": fn if close else None, "loss_contract": [SEMANTIC_LOSS] if close else [],
         "proof": {"type": "crossplane_patch_chain", "evidence": evidence, "tests": tests if close else []},
         "evidence_state": state, "basis": basis, "subject_concept": "bo:UNGLOSSED",
         "object_concept": "bo:UNGLOSSED", "curation_rule": LEVEL_RULE,
         "curation_rule_text": "patch de composição Crossplane; nível DERIVADO, nunca prova de equivalência",
         "mapping_tool": "bo.gold_xplane.build"}
    r.update({k: v for k, v in extra.items() if v is not None})
    return r


def patch_rows(eps):
    rows = {}
    for e in eps:
        if e["provider"] not in PROVIDERS or e["mr_resolution"]["category"] not in SSSOM_CATS:
            continue
        chain, steps = fn_xr_to_mr(e)
        mid, mcat = mr_id(e)
        for xp in e["xr_paths"]:
            xid = xr_id(e, xp)
            xres = e["xr_resolutions"][xp]
            if e["combine"] or steps is None:
                fn, tests, rel = None, [], "related"
            else:
                ident = []
                fn, tests = (compose_forward(ident, steps) if e["direction"] == "to_mr"
                             else compose_backward(steps, ident)) or (None, [])
                rel = "close" if fn else "related"
            subj, obj = (xid, mid) if e["direction"] == "to_mr" else (mid, xid)
            key = (subj, obj, rel, json.dumps(fn, sort_keys=True))
            cid = f"XPL-P-{e['provider']}-{short('|'.join(key))}"
            state = "STRUCTURALLY_VALID" if resolved_side(xres, xr=True) and resolved_side(e["mr_resolution"]) \
                else "UNRESOLVED"
            ev = [evidence_item(h) for h in e["trail"]]
            if key in rows:
                old = rows[key]
                old["proof"]["evidence"] = _merge_ev(old["proof"]["evidence"], ev)
                if state == "UNRESOLVED":
                    old["evidence_state"] = "UNRESOLVED"
                continue
            src = sources.source_by_id(e["top_source"])
            other = {"direction": e["direction"], "xr_category": xres.get("category"),
                     "mr_category": e["mr_resolution"]["category"], "mr_field": _mr_field(e),
                     "bridge": e["mr_resolution"].get("bridge"), "provider_pin": e["mr_resolution"].get("pin"),
                     "transforms": chain, "combine": e["combine"],
                     "condition": e.get("top_condition")}
            sv, ov = (vt(xres), vt(e["mr_resolution"])) if e["direction"] == "to_mr" else \
                (vt(e["mr_resolution"]), vt(xres))
            rows[key] = base_row(
                cid, subj, obj, rel, fn, tests, ev, state, "direct", "semapv:ManualMappingCuration",
                {"subject_category": "crossplane_xr_field" if e["direction"] == "to_mr" else mcat,
                 "object_category": mcat if e["direction"] == "to_mr" else "crossplane_xr_field",
                 "subject_value_type": sv, "object_value_type": ov,
                 "mapping_cardinality": "n:1" if e["combine"] else None,
                 "author_label": src["repo"], "license": LICENSE_URI[src["license"]],
                 "other": json.dumps(other, ensure_ascii=False, sort_keys=True),
                 "comment": f"patch {e['direction']} em {src['repo']}; derivado, não prova equivalência"})
    return list(rows.values())


def _mr_field(e):
    m = e["mr"]
    return f"{m['group']}/{m['version']}/{m['kind']}:{e['mr_path']}"


def _merge_ev(a, b):
    seen = {json.dumps(x, sort_keys=True) for x in a}
    return a + [x for x in b if json.dumps(x, sort_keys=True) not in seen]


def derived_rows(eps):
    """Pares entre provedores pelo mesmo campo do XR (pivô), por par de realizações (composições)."""
    piv: dict = {}
    for e in eps:
        if e["provider"] not in PROVIDERS or e["mr_resolution"]["category"] not in SSSOM_CATS or e["combine"]:
            continue
        x = e["xr"]
        k = (x["group"], x["version"], x["kind"], e["xr_paths"][0], e["direction"])
        piv.setdefault(k, {}).setdefault(realization(e), []).append(e)
    rows, stats = {}, {"pivots": len(piv), "realization_pairs": 0, "same_provider_pairs_skipped": 0,
                       "groups": 0, "pairwise_fallback": 0}
    for k, reals in sorted(piv.items()):
        rkeys = sorted(reals)
        for i, r1 in enumerate(rkeys):
            for r2 in rkeys[i + 1:]:
                e1, e2 = _dedupe(reals[r1]), _dedupe(reals[r2])
                p1, p2 = e1[0]["provider"], e2[0]["provider"]
                if p1 == p2:
                    stats["same_provider_pairs_skipped"] += 1
                    continue
                if PROVIDERS.index(p1) > PROVIDERS.index(p2):
                    e1, e2, p1, p2 = e2, e1, p2, p1
                stats["realization_pairs"] += 1
                _emit_pair(rows, k, e1, e2, p1, p2, stats)
    return list(rows.values()), stats


def _dedupe(es):
    out, seen = [], set()
    for e in sorted(es, key=lambda e: (mr_id(e)[0], json.dumps(fn_xr_to_mr(e)[0], sort_keys=True))):
        key = (mr_id(e)[0], json.dumps(fn_xr_to_mr(e)[0], sort_keys=True))
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def _pair_fn(a, b, direction):
    sa, sb = fn_xr_to_mr(a)[1], fn_xr_to_mr(b)[1]
    return compose_forward(sa, sb) if direction == "to_mr" else compose_backward(sa, sb)


def _emit_pair(rows, k, e1, e2, p1, p2, stats):
    direction = k[4]
    pivot = f"{k[0]}/{k[1]}/{k[2]}:{k[3]}"
    fns = {(i, j): _pair_fn(a, b, direction) for i, a in enumerate(e1) for j, b in enumerate(e2)}
    ev = []
    for e in e1 + e2:
        ev = _merge_ev(ev, [evidence_item(h) for h in e["trail"]])
    state = None   # calculado por linha em _add_derived, só com os pontos finais dela
    authors = sorted({sources.source_by_id(e["top_source"])["repo"] for e in e1 + e2})
    lic = sorted({sources.source_by_id(e["top_source"])["license"] for e in e1 + e2})
    common = {"author_label": ", ".join(authors), "license": LICENSE_URI[lic[0]] if len(lic) == 1 else LICENSE}
    if len(e1) == 1 and len(e2) == 1:
        _add_derived(rows, e1, e2, p1, p2, fns[(0, 0)], ev, state, pivot, direction, common, None)
        return
    if all(f is not None for f in fns.values()):
        stats["groups"] += 1
        _add_derived(rows, e1, e2, p1, p2, None, ev, state, pivot, direction, common, fns)
        return
    stats["pairwise_fallback"] += 1
    for (i, j), f in sorted(fns.items()):
        _add_derived(rows, [e1[i]], [e2[j]], p1, p2, f, ev, state, pivot, direction,
                     dict(common, mapping_cardinality=f"{_card(len(e1), len(e2))} (desdobrado em pares)"), None)


def _card(n, m):
    return "1:1" if n == m == 1 else "1:N" if n == 1 else "N:1" if m == 1 else "N:M"


def _pair_state(e1, e2, xr_path):
    ok = all(resolved_side(e["mr_resolution"]) for e in e1 + e2) and all(
        resolved_side(e["xr_resolutions"][xr_path], xr=True) for e in e1 + e2)
    return "STRUCTURALLY_VALID" if ok else "UNRESOLVED"


def _add_derived(rows, e1, e2, p1, p2, f, ev, state, pivot, direction, common, group_fns):
    state = _pair_state(e1, e2, pivot.split(":", 1)[1])
    ev = []
    for e in e1 + e2:
        ev = _merge_ev(ev, [evidence_item(h) for h in e["trail"]])
    sid, scat = mr_id(e1[0])
    oid, ocat = mr_id(e2[0])
    other = {"pivot_xr_field": pivot, "direction": direction,
             "subject_mr_fields": sorted({_mr_field(e) for e in e1}),
             "object_mr_fields": sorted({_mr_field(e) for e in e2}),
             "bridges": {mr_id(e)[0]: e["mr_resolution"].get("bridge") for e in e1 + e2},
             "realizations": sorted({"|".join(map(str, realization(e)[:4])) for e in e1 + e2})}
    extra = dict(common, subject_category=scat, object_category=ocat,
                 subject_value_type=vt(e1[0]["mr_resolution"]) if len(e1) == 1 else None,
                 object_value_type=vt(e2[0]["mr_resolution"]) if len(e2) == 1 else None,
                 comment=f"derivado: {p1} e {p2} recebem o mesmo campo do XR ({pivot}); não prova equivalência")
    if group_fns is None:
        fn, tests = f if f else (None, [])
        rel = "close" if fn else "related"
        key = ("D", sid, oid, rel, json.dumps(fn, sort_keys=True))
        cid = f"XPL-D-{p1}-{p2}-{short('|'.join(key))}"
    else:
        sids = sorted({mr_id(e)[0] for e in e1})
        oids = sorted({mr_id(e)[0] for e in e2})
        key = ("G", "+".join(sids), "+".join(oids), direction)
        cid = f"XPL-G-{p1}-{p2}-{short('|'.join(key))}"
        gid = f"GRP-XPL-{short('|'.join(key))}"
        svars = [{"name": f"?s{i + 1}", "side": "subject", "field": x, "occurrence": f"?rs{i + 1}"}
                 for i, x in enumerate(sids)]
        ovars = [{"name": f"?o{j + 1}", "side": "object", "field": x, "occurrence": f"?ro{j + 1}"}
                 for j, x in enumerate(oids)]
        steps, tests = [], []
        for (i, j), (gfn, gt) in sorted(group_fns.items()):
            si = sids.index(mr_id(e1[i])[0])
            oj = oids.index(mr_id(e2[j])[0])
            st = {"name": gfn["name"], "inputs": {"value": f"?s{si + 1}"}, "outputs": {"value": f"?o{oj + 1}"}}
            if gfn.get("params"):
                st["params"] = gfn["params"]
            if st not in steps:
                steps.append(st)
        group = {"bo_group_id": gid, "cardinality": _card(len(sids), len(oids)), "variables": svars + ovars,
                 "occurrence_vars": [v["occurrence"] for v in svars + ovars], "joins": [], "steps": steps}
        if group["cardinality"] == "1:1":
            # campos repetidos colapsaram num só por lado: vira linha 1:1 comum
            fn, tests = group_fns[sorted(group_fns)[0]]
            return _add_derived(rows, e1[:1], e2[:1], p1, p2, (fn, tests), ev, state, pivot, direction, common, None)
        rel, fn = "close", None
        extra.update(bo_group_id=gid, group=group, mapping_cardinality=group["cardinality"])
    if cid in rows:
        old = rows[cid]
        old["proof"]["evidence"] = _merge_ev(old["proof"]["evidence"], ev)
        o = json.loads(old["other"])
        o["realizations"] = sorted(set(o["realizations"]) | set(other["realizations"]))
        old["other"] = json.dumps(o, ensure_ascii=False, sort_keys=True)
        authors = sorted(set(old["author_label"].split(", ")) | set(extra["author_label"].split(", ")))
        old["author_label"] = ", ".join(authors)
        if state == "UNRESOLVED":
            old["evidence_state"] = "UNRESOLVED"
        return
    extra["other"] = json.dumps(other, ensure_ascii=False, sort_keys=True)
    rows[cid] = base_row(cid, sid, oid, rel, fn, tests, ev, state, "composition", "semapv:MappingChaining", extra)


# ---------------------------------------------------------------------------------------------- build
def compute(root: Path):
    ex = Extractor(root)
    eps = ex.endpoints()
    for e in eps:
        x = e["xr"]
        e["xr_resolutions"] = {p: ex.xr_resolve(x["group"], x["version"], x["kind"], p) for p in e["xr_paths"]}
        # campos intermediários (XR aninhado) também têm de resolver no XRD deles
        for h in e["trail"][1:]:
            nl = h.get("nested_link") or {}
            g, kd = nl.get("nested_xr", "/").split("/", 1) if nl else ("", "")
            xrd = ex.corpus["xrds"].get((g, kd))
            ver = next(iter(xrd["versions"])) if xrd else ""
            h["nested_resolution"] = ex.xr_resolve(g, ver, kd, nl["nested_field"]) if nl else None
    prow = patch_rows(eps)
    drow, dstats = derived_rows(eps)
    rows = sorted(prow, key=lambda r: r["claim_id"]) + sorted(drow, key=lambda r: r["claim_id"])
    return ex, eps, rows, dstats


def outputs(root: Path):
    ex, eps, rows, dstats = compute(root)
    tsv = CSSSOM.write_tsv(rows, MAPPING_SET_ID, PREFIXES)
    tsv = tsv.replace(f"# license: {CSSSOM.SIO.LICENSE}\n", f"# license: {LICENSE}\n")
    patches = "".join(json.dumps(_ep_record(e), ensure_ascii=False, sort_keys=True) + "\n" for e in eps)
    res = resolution_report(eps, rows)
    stats = stats_report(ex, eps, rows, dstats, res)
    return {"crossplane.sssom.tsv": tsv, "patches.jsonl": patches,
            "resolution.json": json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n"}, stats


def _ep_record(e):
    return {"top_source": e["top_source"], "top_file": e["top_file"], "composition": e["composition"],
            "xr": e["xr"], "direction": e["direction"], "xr_paths": e["xr_paths"],
            "xr_resolutions": e["xr_resolutions"], "provider": e["provider"], "api_family": e["family"],
            "mr": e["mr"], "mr_path": e["mr_path"], "mr_resolution": e["mr_resolution"], "combine": e["combine"],
            "condition": e.get("top_condition"), "nested_status": e["nested_status"],
            "trail": [{k: v for k, v in h.items() if k != "mr"} | {"mr": f"{h['mr']['group']}/{h['mr']['kind']}"}
                      for h in e["trail"]],
            "in_sssom": e["provider"] in PROVIDERS and e["mr_resolution"]["category"] in SSSOM_CATS}


def resolution_report(eps, rows):
    from collections import Counter
    fields = Counter()
    for e in eps:
        fields[("mr", e["mr_resolution"]["category"], e["mr_resolution"]["status"])] += 1
        for p, r in e["xr_resolutions"].items():
            fields[("xr", r.get("category"), r["status"])] += 1
        b = e["mr_resolution"].get("bridge") or {}
        if e["mr_resolution"]["category"] in ("param", "observed"):
            fields[("bridge", e["family"] or "none", b.get("status"))] += 1
    unresolved_rows = [r["claim_id"] for r in rows if r["evidence_state"] == "UNRESOLVED"]
    return {"schema": "bo.gold_xplane.resolution/1", "endpoints": len(eps),
            "counts": [{"side": a, "category": b, "status": c, "n": n} for (a, b, c), n in sorted(
                fields.items(), key=lambda x: tuple(str(y) for y in x[0]))],
            "sssom_rows": len(rows), "sssom_unresolved_rows": len(unresolved_rows),
            "rule": "todo campo resolve no XRD/CRD do provider fixado (status resolved | runtime) ou é marcado "
                    "unresolved com o motivo; linha SSSOM com um lado unresolved tem evidence_state UNRESOLVED"}


def stats_report(ex, eps, rows, dstats, res):
    from collections import Counter
    kinds = Counter(r["claim_id"].split("-")[1] for r in rows)
    rel = Counter((r["claim_id"].split("-")[1], r["semantic_relation"]) for r in rows)
    st = Counter(r["evidence_state"] for r in rows)
    pairs = Counter("-".join(r["claim_id"].split("-")[2:4]) for r in rows if r["claim_id"].split("-")[1] in "DG")
    xr_multi = {}
    for c in ex.corpus["compositions"]:
        if c["role"] == "top":
            xr_multi.setdefault(f"{c['xr']['group']}/{c['xr']['kind']}", set()).add(c["name"])
    tf_rows = sum(1 for r in rows if r["claim_id"].split("-")[1] in "DG" and
                  r["subject_category"] == r["object_category"] == "terraform_attribute")
    return {"schema": "bo.gold_xplane.stats/1", "module": "GOLD-XPLANE", "generated_at": now_iso(),
            "sources": [{"id": s["id"], "repo": s["repo"], "commit": s["commit"], "license": s["license"],
                         "role": s["role"], "family": s["family"]} for s in sources.COMPOSITION_SOURCES],
            "excluded_sources": sources.EXCLUDED_SOURCES,
            "top_xrs": {k: sorted(v) for k, v in sorted(xr_multi.items())},
            "compositions_read": len(ex.corpus["compositions"]),
            "unread_pipeline_steps": len(ex.corpus["unread_steps"]),
            "endpoints": len(eps), "endpoints_in_sssom": sum(1 for e in eps if e["provider"] in PROVIDERS and
                                                              e["mr_resolution"]["category"] in SSSOM_CATS),
            "rows": dict(sorted(kinds.items())), "rows_by_relation": {f"{a}:{b}": n for (a, b), n in sorted(rel.items())},
            "rows_by_evidence_state": dict(sorted(st.items())), "derived_by_provider_pair": dict(sorted(pairs.items())),
            "derived_both_sides_terraform": tf_rows, "derived_stats": dstats,
            "row_kinds": {"P": "patch: campo do XR <-> campo do MR", "D": "derivada 1:1 entre provedores",
                          "G": "derivada em grupo (1:N, N:1, N:M) entre provedores"},
            "level": "DERIVADO em todas as linhas", "resolution": {"sssom_unresolved_rows": res["sssom_unresolved_rows"]}}


def write_all(files: dict, stats: dict, ddir: Path, rdir: Path):
    ddir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)
    for n, t in files.items():
        (ddir / n).write_text(t, encoding="utf-8")
    (rdir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_manifest(ddir, rdir)


MANIFEST_DATA = ("crossplane.sssom.tsv", "patches.jsonl", "resolution.json")


def write_manifest(ddir: Path, rdir: Path):
    """results/GOLD-XPLANE/MANIFEST.sha256 (C17): saídas em $BO_DATA (caminho portátil), stats e o manifesto
    dos downloads."""
    lines = [(hashlib.sha256((ddir / n).read_bytes()).hexdigest(), f"$BO_DATA/GOLD-XPLANE/{n}")
             for n in MANIFEST_DATA]
    dm = downloads_dir() / "MANIFEST.sha256"
    lines.append((hashlib.sha256(dm.read_bytes()).hexdigest(), "$BO_DATA/downloads/crossplane/MANIFEST.sha256"))
    lines.append((hashlib.sha256((rdir / "stats.json").read_bytes()).hexdigest(), "results/GOLD-XPLANE/stats.json"))
    (rdir / "MANIFEST.sha256").write_text("".join(f"{h}  {p}\n" for h, p in lines), encoding="utf-8")


def _strip_ts(t: str) -> str:
    d = json.loads(t)
    d.pop("generated_at", None)
    return json.dumps(d, sort_keys=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.gold_xplane.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    files, stats = outputs(downloads_dir())
    if a.check:
        bad = []
        for n, t in files.items():
            p = data_dir() / n
            if not p.exists() or p.read_text(encoding="utf-8") != t:
                bad.append(str(p))
        p = results_dir() / "stats.json"
        if not p.exists() or _strip_ts(p.read_text(encoding="utf-8")) != _strip_ts(json.dumps(stats)):
            bad.append(str(p))
        if bad:
            print("regeneração diverge:", *bad, sep="\n  ")
            return 1
        print(f"[{now_iso()}] build --check: {len(files) + 1} arquivo(s) idênticos à regeneração")
        return 0
    write_all(files, stats, data_dir(), results_dir())
    print(f"[{now_iso()}] build: {stats['endpoints']} pontos finais, linhas {stats['rows']}, "
          f"estados {stats['rows_by_evidence_state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
