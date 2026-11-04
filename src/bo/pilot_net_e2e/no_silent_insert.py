"""Gate: HCL renderizado = plano de lowering + inserções declaradas. Nada a mais, nada a menos, nada mudado.

  python -I -m bo.lower.no_silent_insert --slice net [--out DIR]

Lê o HCL que o bo.pilot.run deixou no staging (hcl/<case_id>/) e o plano (lowering_plan.jsonl) e relê o HCL pelo
python-hcl2 (parser independente dos renderizadores). Para cada passo do plano exige um recurso do mesmo tipo com o
rótulo do nó, e para cada recurso:
  INSERTED  atributo ou bloco de topo que o plano não traz (nem é o campo do nome derivado, nem depends_on do
            plano, nem inserção declarada do harness: HI-GCP-01 labels.bo-run, HI-OCI-01 freeform_tags.bo-run);
  DROPPED   valor do plano ausente do HCL;
  ALTERED   literal do plano diferente do literal do HCL (escalar ou lista); referência que vira outra coisa;
  EXTRA_RESOURCE recurso sem passo; VAR_DEFAULT variável com default (o harness não pode inventar valor).
Mutações (atributo plantado, literal trocado, valor removido, recurso extra, default em variável) têm de reprovar
todas, e há de haver ao menos um plano conferido de cada provedor renderizado. Sai 0 só assim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import hcl2

from .common import dump, out_dir, parser, say

DECLARED = {"google": {"labels"}, "oci": {"freeform_tags"}, "aws": set(), "azurerm": set()}
SKIP = ("__is_block__", "__comments__", "__inline_comments__")


def _unq(s):
    return s[1:-1] if isinstance(s, str) and len(s) >= 2 and s[0] == s[-1] == '"' else s


def _norm(v):
    if isinstance(v, dict):
        return {_unq(k): _norm(x) for k, x in v.items() if k not in SKIP}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    return _unq(v) if isinstance(v, str) else v


def parse(text: str) -> dict:
    doc = hcl2.loads(text)
    res, var = {}, {}
    for blk in doc.get("resource", []):
        for rtype, inner in blk.items():
            for label, body in inner.items():
                res[(_unq(rtype), _unq(label))] = _norm(body)
    for blk in doc.get("variable", []):
        for name, body in blk.items():
            var[_unq(name)] = _norm(body)
    return {"resources": res, "variables": var}


def _get(body, path):
    cur = body
    for seg in path.split("."):
        if isinstance(cur, list):
            if seg.isdigit():
                if int(seg) >= len(cur):
                    return KeyError
                cur = cur[int(seg)]
                continue
            if len(cur) == 1:
                cur = cur[0]
            else:
                return KeyError
        if not isinstance(cur, dict) or seg not in cur:
            return KeyError
        cur = cur[seg]
    if isinstance(cur, list) and len(cur) == 1 and isinstance(cur[0], dict):
        return cur
    return cur


def check_case(plan: dict, files: dict, provider: str) -> list:
    issues = []
    parsed = {"resources": {}, "variables": {}}
    for name, text in files.items():
        p = parse(text)
        parsed["resources"].update(p["resources"])
        parsed["variables"].update(p["variables"])
    for v, body in parsed["variables"].items():
        if "default" in body:
            issues.append({"kind": "VAR_DEFAULT", "where": v})
    by_node = {}
    for (rtype, label), body in parsed["resources"].items():
        node = re.search(r"([rc][0-9]+)$", label)
        by_node.setdefault((rtype, node.group(1) if node else label), []).append((label, body))
    seen = set()
    for st in plan["steps"]:
        key = (st["resource_type"], st["node_id"])
        hits = by_node.get(key, [])
        if len(hits) != 1:
            issues.append({"kind": "DROPPED", "where": f"{key}", "detail": f"{len(hits)} recurso(s) no HCL"})
            continue
        label, body = hits[0]
        seen.add((st["resource_type"], label))
        allowed = {v["field"].split(".")[0] for v in st["values"]} | {"depends_on"} | DECLARED[provider]
        dn = st.get("derived_name") or {}
        if dn.get("field"):
            allowed.add(dn["field"].split(".")[0])
        for k in body:
            if k not in allowed:
                issues.append({"kind": "INSERTED", "where": f"{label}.{k}"})
        for v in st["values"]:
            got = _get(body, v["field"])
            if got is KeyError:
                issues.append({"kind": "DROPPED", "where": f"{label}.{v['field']}"})
                continue
            t = v["term"]
            if t["kind"] == "literal":
                if _norm_lit(got) != _norm_lit(t["value"]):
                    issues.append({"kind": "ALTERED", "where": f"{label}.{v['field']}",
                                   "detail": f"plano {t['value']!r} x HCL {got!r}"})
            elif t["kind"] == "reference":
                if not (isinstance(got, str) and got.startswith("${") and t["target_type"] in got):
                    issues.append({"kind": "ALTERED", "where": f"{label}.{v['field']}", "detail": "referência"})
            elif t["kind"] == "symbol":
                if not (isinstance(got, str) and "var." in got):
                    issues.append({"kind": "ALTERED", "where": f"{label}.{v['field']}", "detail": "símbolo"})
    for (rtype, label) in parsed["resources"]:
        if (rtype, label) not in seen:
            issues.append({"kind": "EXTRA_RESOURCE", "where": f"{rtype}.{label}"})
    return issues


def _norm_lit(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v) if re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", v) else v
        except ValueError:
            return v
    if isinstance(v, list):
        return [_norm_lit(x) for x in v]
    return v


def mutations(plan, files, provider) -> list:
    """Cada mutação tem de reprovar."""
    name = next(iter(files))
    text = files[name]
    m = re.search(r'resource "([a-z0-9_]+)" "([A-Za-z0-9_\-]+)" \{\n', text)
    out = []
    if not m:
        return [{"mutation": "sem recurso", "caught": False}]
    pos = m.end()
    cases = {
        "atributo plantado": text[:pos] + '  bo_planted = "x"\n' + text[pos:],
        "recurso extra": text + '\nresource "%s" "zz_extra" {\n}\n' % m.group(1),
        "default em variável": re.sub(r'(variable "[^"]+" \{\n)', r'\1  default = "x"\n', text, count=1)
        if "variable " in text else None,
    }
    lit = re.search(r'\n(\s+)([a-z_]+)\s+=\s+"([^"$]+)"\n', text[pos:])
    if lit:
        a = pos + lit.start()
        b = pos + lit.end()
        cases["literal trocado"] = text[:a] + f'\n{lit.group(1)}{lit.group(2)} = "zz-mutado"\n' + text[b:]
        cases["valor removido"] = text[:a] + "\n" + text[b:]
    for k, t in cases.items():
        if t is None:
            continue
        iss = check_case(plan, dict(files, **{name: t}), provider)
        out.append({"mutation": k, "caught": bool(iss)})
    return out


def main(argv=None) -> int:
    ap = parser("bo.lower.no_silent_insert", __doc__)
    a = ap.parse_args(argv)
    out = out_dir(a)
    if not (out / "cases.jsonl").exists():
        from .common import run_pipeline
        run_pipeline(a)
    rows = [json.loads(l) for l in (out / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    plans = {p["plan_id"]: p for p in (json.loads(l) for l in (out / "lowering_plan.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip())}
    checked, bad, per_prov, muts = 0, [], {}, []
    for r in rows:
        if r["render_status"] != "RENDERED":
            continue
        d = out / "hcl" / r["case_id"]
        files = {p.name: p.read_text(encoding="utf-8") for p in sorted(d.glob("*.tf"))}
        prov = r["direction"].split("->")[1]
        iss = check_case(plans[r["plan_id"]], files, prov)
        checked += 1
        per_prov[prov] = per_prov.get(prov, 0) + 1
        if iss:
            bad.append({"case_id": r["case_id"], "issues": iss[:10]})
        if per_prov[prov] == 1:
            muts += [dict(m, provider=prov, case_id=r["case_id"]) for m in mutations(plans[r["plan_id"]], files, prov)]
    uncaught = [m for m in muts if not m["caught"]]
    rep = {"schema": "bo.pilot_net.no_silent_insert/1", "checked": checked, "per_provider": per_prov,
           "failures": bad, "mutations": muts, "uncaught_mutations": uncaught}
    dump(out / "no_silent_insert.json", rep)
    ok = checked > 0 and not bad and not uncaught
    say(f"no_silent_insert: {checked} plano(s) conferido(s) {per_prov}; com problema {len(bad)}; mutações "
        f"{len(muts) - len(uncaught)}/{len(muts)} pegas -> {'OK' if ok else 'REPROVADO'}")
    for b in bad[:8]:
        say(f"  {b['case_id']}: {b['issues'][:3]}")
    for m in uncaught:
        say(f"  mutação não pega: {m}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
