"""Gate: HCL renderizado = plano C26 + inserções declaradas do harness. Nada a mais, nada a menos, nada mudado.

  python -I -m bo.harness.aws.no_silent_insert [--plans PLANO.jsonl ...] [--report ARQ]

Sem argumentos, confere os planos de fixture do módulo (tests/harness/aws/fixtures/plans/) e os stubs C26 do
CONTRACTS que tiverem plano aws. O HCL é relido por um parser independente do renderizador (python-hcl2, versão
do requirements.lock) e comparado com o PLANO (não com o manifesto do renderizador):
  INSERTED  atributo, bloco, recurso, variável ou default que nem o plano nem DECLARED_INSERTIONS.json trazem;
  DROPPED   valor do plano ausente do HCL sem motivo tipado de UNKNOWN_INPUT;
  ALTERED   valor do HCL diferente do valor do plano (literal, símbolo, segredo, referência ou documento).
Também confere os modelos (versions/providers/variables) contra a lista declarada e que campo obrigatório
ausente (UNKNOWN_INPUT) não aparece no HCL. Por fim, roda mutações (atributo plantado, valor trocado, valor
removido, tag nova no provider, default em variável, recurso extra, obrigatório inventado, locals) e exige que
TODAS reprovem. Sai 0 só se os renders limpos passam, há ao menos um RENDERED e um UNKNOWN_INPUT conferidos,
e toda mutação é pega.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import hcl2

from . import pins, render

TZ = ZoneInfo("America/Recife")
REF_RX = re.compile(r"^([a-z][a-z0-9_]*)\.([a-z0-9_]+)(?:\.([A-Za-z0-9_.]+))?$")
VAR_RX = re.compile(r"^var\.([A-Za-z0-9_]+)$")
CALL_RX = re.compile(r"^(jsonencode|yamlencode)\((.*)\)$", re.S)
SKIP_KEYS = ("__is_block__", "__comments__", "__inline_comments__")


# ------------------------------------------------------------------------------------------ normalização
def unquote(s: str):
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return json.loads(s.replace("$${", "${").replace("%%{", "%{"))
    if s.startswith("${") and s.endswith("}"):
        s = s[2:-1]
    return ("expr", s)


def norm(v):
    if isinstance(v, str):
        return unquote(v)
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {(unquote(k) if k.startswith('"') else k): norm(x) for k, x in v.items() if k not in SKIP_KEYS}
    return v


def is_block(v) -> bool:
    return isinstance(v, list) and v and all(isinstance(x, dict) and x.get("__is_block__") for x in v)


def parse(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return hcl2.load(f)


def _label(k: str) -> str:
    return k[1:-1] if k.startswith('"') and k.endswith('"') else k


# ------------------------------------------------------------------------------------------ modelos
def leaves(obj, prefix: str) -> dict:
    """Folhas de um corpo parseado: caminho -> valor normalizado (blocos viram segmentos do caminho)."""
    out = {}
    for k, v in obj.items():
        if k in SKIP_KEYS:
            continue
        name = _label(k)
        p = f"{prefix}.{name}" if prefix else name
        if is_block(v):
            for b in v:
                out.update(leaves(b, p))
        elif isinstance(v, dict) and not v.get("__is_block__") and prefix.count(".") < 6 and \
                all(not isinstance(x, (dict, list)) for x in v.values()):
            for kk, vv in v.items():
                out[f"{p}.{_label(kk)}"] = norm(vv)
        elif isinstance(v, dict):
            out.update(leaves(v, p))
        else:
            out[p] = norm(v)
    return out


def check_templates(render_dir: Path, declared: dict) -> list[dict]:
    finds = []
    for fname, items in declared["templates"].items():
        got = {}
        for k, v in parse(render_dir / fname).items():
            if k in SKIP_KEYS:
                continue
            for blk in v:
                got.update(leaves(blk, k))
        want = {}
        for it in items:
            if "value" in it:
                want[it["path"]] = it["value"]
            elif "expr" in it:
                want[it["path"]] = ("expr", it["expr"])
            else:
                for ak, av in it["attrs"].items():
                    want[f"{it['path']}.{ak}"] = ("expr", av) if ak == "type" else av
        for p in sorted(set(got) | set(want)):
            if p not in want:
                finds.append({"kind": "INSERTED", "where": fname, "path": p, "detail": "fora da lista declarada"})
            elif p not in got:
                finds.append({"kind": "DROPPED", "where": fname, "path": p, "detail": "inserção declarada ausente"})
            elif got[p] != want[p]:
                finds.append({"kind": "ALTERED", "where": fname, "path": p, "detail": f"{got[p]!r} != {want[p]!r}"})
    return finds


# ------------------------------------------------------------------------------------------ planos
class _Expect:
    def __init__(self, plan: dict):
        self.plan = plan
        self.slug = render.slug(plan["plan_id"])
        self.steps = sorted(plan["steps"], key=lambda s: s["order"])
        self.secret_n = 0
        self.sym_vars: set[str] = set()
        self.secret_vars: set[str] = set()
        self.values: dict[str, dict] = {}   # address -> {field: esperado}
        self.deps: dict[str, list] = {}
        self.order: dict[str, int] = {}
        for s in self.steps:
            if s["action"] == "reference":
                continue
            addr = f"{s['resource_type']}.{render.label(plan['plan_id'], s['node_id'])}"
            self.order[addr] = s["order"]
            self.values[addr] = {v["field"]: self.expect(v["term"]) for v in s["values"]}
            by_order = {x["order"]: x for x in self.steps}
            self.deps[addr] = [f"{by_order[d]['resource_type']}.{render.label(plan['plan_id'], by_order[d]['node_id'])}"
                               for d in s["depends_on"] if d in by_order and by_order[d]["action"] != "reference"]

    def expect(self, t: dict):
        k = t["kind"]
        if k == "literal":
            return ("lit", t["value"])
        if k == "symbol":
            name = f"{self.slug}_sym_{t['symbol_id'][4:]}"
            self.sym_vars.add(name)
            return ("var", name)
        if k == "withheld":
            if t["reason"] != "secret":
                return ("unrenderable", t["reason"])
            self.secret_n += 1
            name = f"{self.slug}_secret_{self.secret_n}"
            self.secret_vars.add(name)
            return ("var", name)
        if k == "reference":
            return ("ref", t["target_type"], t.get("attribute") or "id")
        if k == "document":
            if t["symbolized"]:
                return ("unrenderable", "documento simbolizado")
            return ("doc", "yamlencode" if t["format"] == "yaml" else "jsonencode", t["tree"])
        return ("unrenderable", k)


def _match(exp, got, ex: _Expect, addr: str) -> str | None:
    kind = exp[0]
    if kind == "lit":
        same = got == exp[1] and isinstance(got, bool) == isinstance(exp[1], bool)
        return None if same else f"{got!r} != {exp[1]!r}"
    if kind == "var":
        m = VAR_RX.match(got[1]) if isinstance(got, tuple) else None
        return None if m and m.group(1) == exp[1] else f"{got!r} != var.{exp[1]}"
    if kind == "ref":
        m = REF_RX.match(got[1]) if isinstance(got, tuple) else None
        if not m:
            return f"{got!r} não é referência"
        tgt = f"{m.group(1)}.{m.group(2)}"
        if m.group(1) != exp[1] or (m.group(3) or "") != exp[2]:
            return f"referência {got[1]} não é {exp[1]}.<passo>.{exp[2]}"
        if tgt not in ex.order or ex.order[tgt] >= ex.order[addr]:
            return f"referência {tgt} não é passo anterior deste plano"
        return None
    if kind == "doc":
        m = CALL_RX.match(got[1]) if isinstance(got, tuple) else None
        if not m or m.group(1) != exp[1]:
            return f"{got!r} não é {exp[1]}(...)"
        inner = norm(hcl2.loads("x = " + m.group(2) + "\n")["x"])
        return None if inner == exp[2] else "documento difere da árvore do plano"
    return f"valor que não devia ser renderizado ({exp[1]})"


def _resource_leaves(body: dict, exp_fields: dict) -> dict:
    """Folhas do recurso no formato dos campos do plano (bloco -> segmento; objeto só quando o plano o abre)."""
    out = {}

    def walk(obj, prefix):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            p = f"{prefix}.{_label(k)}" if prefix else _label(k)
            if is_block(v):
                for b in v:
                    walk(b, p)
            elif isinstance(v, dict) and p not in exp_fields and any(f.startswith(p + ".") for f in exp_fields):
                walk(v, p)
            else:
                out[p] = norm(v)
    walk(body, "")
    return out


def check_plan(render_dir: Path, plan: dict, entry: dict) -> list[dict]:
    finds = []
    pid = plan["plan_id"]
    f = render_dir / f"{pid}.tf"
    if entry["status"] == "INVALID_PLAN":
        if f.exists():
            finds.append({"kind": "INSERTED", "where": f.name, "path": "(arquivo)", "detail": "plano inválido com HCL"})
        return finds
    if not f.exists():
        return [{"kind": "DROPPED", "where": f.name, "path": "(arquivo)", "detail": "plano sem HCL"}]
    ex = _Expect(plan)
    doc = parse(f)
    unrendered = {(u["address"], u["field"]) for u in entry["unrendered"]}
    seen_vars = set()
    for top, items in doc.items():
        if top in SKIP_KEYS:
            continue
        if top == "variable":
            for blk in items:
                for name, body in blk.items():
                    name = _label(name)
                    seen_vars.add(name)
                    attrs = {k: norm(v) for k, v in body.items() if k not in SKIP_KEYS}
                    if name in ex.sym_vars:
                        want = {"type": ("expr", "any"), "nullable": False}
                    elif name in ex.secret_vars:
                        want = {"type": ("expr", "string"), "nullable": False, "sensitive": True}
                    else:
                        finds.append({"kind": "INSERTED", "where": f.name, "path": f"variable.{name}",
                                      "detail": "variável sem termo correspondente no plano"})
                        continue
                    if attrs != want:
                        finds.append({"kind": "INSERTED" if set(attrs) - set(want) else "ALTERED", "where": f.name,
                                      "path": f"variable.{name}", "detail": f"{sorted(attrs)} != {sorted(want)}"})
        elif top == "resource":
            for blk in items:
                for rtype, labeled in blk.items():
                    for lab, body in labeled.items():
                        addr = f"{_label(rtype)}.{_label(lab)}"
                        if addr not in ex.values:
                            finds.append({"kind": "INSERTED", "where": f.name, "path": addr,
                                          "detail": "recurso sem passo no plano"})
                            continue
                        want = ex.values[addr]
                        got = _resource_leaves(body, want)
                        dep = got.pop("depends_on", None)
                        want_dep = list(ex.deps[addr])
                        if (dep or []) != [("expr", d) for d in want_dep]:
                            finds.append({"kind": "ALTERED" if dep else "DROPPED", "where": f.name,
                                          "path": f"{addr}.depends_on", "detail": f"{dep!r} != {want_dep!r}"})
                        for p in sorted(set(got) | set(want)):
                            if p not in want:
                                finds.append({"kind": "INSERTED", "where": f.name, "path": f"{addr}.{p}",
                                              "detail": "campo fora do plano"})
                            elif p not in got:
                                if want[p][0] == "unrenderable" or (addr, p) in unrendered and \
                                        entry["status"] == "UNKNOWN_INPUT":
                                    continue
                                finds.append({"kind": "DROPPED", "where": f.name, "path": f"{addr}.{p}",
                                              "detail": "valor do plano ausente"})
                            else:
                                why = _match(want[p], got[p], ex, addr)
                                if why:
                                    finds.append({"kind": "ALTERED", "where": f.name, "path": f"{addr}.{p}",
                                                  "detail": why})
                        for m in entry["missing"]:
                            if m["address"] == addr and m["field"] and m["field"] in got:
                                finds.append({"kind": "INSERTED", "where": f.name, "path": f"{addr}.{m['field']}",
                                              "detail": "campo dado como UNKNOWN_INPUT aparece no HCL"})
        else:
            finds.append({"kind": "INSERTED", "where": f.name, "path": top, "detail": "bloco de topo não declarado"})
    for v in sorted((ex.sym_vars | ex.secret_vars) - seen_vars):
        finds.append({"kind": "DROPPED", "where": f.name, "path": f"variable.{v}", "detail": "variável ausente"})
    want_res = set(ex.values)
    got_res = {f"{_label(t)}.{_label(lab)}" for blk in doc.get("resource", []) for t, ls in blk.items() for lab in ls}
    for a in sorted(want_res - got_res):
        finds.append({"kind": "DROPPED", "where": f.name, "path": a, "detail": "passo do plano sem recurso"})
    return finds


def check_render(render_dir: Path) -> dict:
    render_dir = Path(render_dir)
    man = json.loads((render_dir / "render_manifest.json").read_text(encoding="utf-8"))
    declared = json.loads((render.templates_dir() / "DECLARED_INSERTIONS.json").read_text(encoding="utf-8"))
    plans = {p["plan_id"]: p for p in render.read_jsonl(Path(man["input"]["plan"]))}
    finds = check_templates(render_dir, declared)
    expected_files = set(render.TEMPLATE_FILES) | {"render_manifest.json"}
    for e in man["plans"]:
        finds += check_plan(render_dir, plans[e["plan_id"]], e)
        if e["status"] != "INVALID_PLAN":
            expected_files.add(f"{e['plan_id']}.tf")
    for extra in sorted({p.name for p in render_dir.iterdir()} - expected_files):
        finds.append({"kind": "INSERTED", "where": extra, "path": "(arquivo)", "detail": "arquivo não esperado"})
    counts = {s: sum(1 for e in man["plans"] if e["status"] == s) for s in render.STATUSES}
    return {"render_dir": str(render_dir), "plan": man["input"]["plan"], "counts": counts, "findings": finds}


# ------------------------------------------------------------------------------------------ mutações
def _edit(path: Path, old: str, new: str):
    t = path.read_text(encoding="utf-8")
    if old not in t:
        raise AssertionError(f"mutação não aplicável em {path.name}: trecho ausente")
    path.write_text(t.replace(old, new, 1), encoding="utf-8")


MUTATIONS = [
    ("M1 atributo plantado (default silencioso)", "LP-AWS-NET-01.tf",
     '  cidr_block           = "10.42.0.0/16"\n', '  cidr_block           = "10.42.0.0/16"\n  instance_tenancy     = "default"\n'),
    ("M2 valor trocado", "LP-AWS-NET-01.tf", '"10.42.0.0/16"', '"10.0.0.0/16"'),
    ("M3 valor removido", "LP-AWS-NET-01.tf", "  enable_dns_hostnames = true\n", ""),
    ("M4 tag nova no provider", "providers.tf", '      "bo-case" = var.bo_case_id\n',
     '      "bo-case" = var.bo_case_id\n      "bo-x"    = "y"\n'),
    ("M5 default em variável simbólica", "LP-AWS-STO-01.tf", "  type     = any\n", '  type     = any\n  default  = "x"\n'),
    ("M6 recurso extra", "LP-AWS-NET-01.tf", "resource \"aws_subnet\"",
     "resource \"aws_internet_gateway\" \"lp_aws_net_01_r9\" {\n}\n\nresource \"aws_subnet\""),
    ("M7 obrigatório inventado no UNKNOWN_INPUT", "LP-AWS-DB-01.tf", '  engine                  = "postgres"\n',
     '  engine                  = "postgres"\n  instance_class          = "db.t4g.micro"\n'),
    ("M8 bloco locals", "LP-AWS-SEC-02.tf", 'resource "aws_iam_role"', 'locals {\n  a = 1\n}\n\nresource "aws_iam_role"'),
    ("M9 referência trocada de atributo", "LP-AWS-NET-01.tf", "aws_vpc.lp_aws_net_01_r1.id\n",
     "aws_vpc.lp_aws_net_01_r1.arn\n"),
    ("M10 documento alterado", "LP-AWS-SEC-02.tf", 'Service = "ec2.amazonaws.com"', 'Service = "lambda.amazonaws.com"'),
    ("M11 segredo virou literal", "LP-AWS-DB-02.tf", "var.lp_aws_db_02_secret_1", '"fixo-no-codigo"'),
    ("M12 depends_on removido", "LP-AWS-STO-01.tf", "  depends_on = [aws_s3_bucket.lp_aws_sto_01_r1]\n", ""),
]


def run_mutations(clean_dir: Path, work: Path) -> list[dict]:
    out = []
    baseline = check_render(clean_dir)["findings"]
    for name, fname, old, new in MUTATIONS:
        d = work / re.sub(r"[^A-Za-z0-9]+", "_", name.split()[0])
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(clean_dir, d)
        try:
            _edit(d / fname, old, new)
            rep = check_render(d)
            new = [f for f in rep["findings"] if f not in baseline]
            caught = bool(new)
            kinds = sorted({f"{f['kind']} {f['path']}" for f in new})
        except AssertionError as e:
            caught, kinds = False, [f"não aplicada: {e}"]
        except Exception as e:  # parser recusando o arquivo também é detecção, mas registramos o motivo
            caught, kinds = True, [f"parser recusou: {type(e).__name__}"]
        out.append({"mutation": name, "file": fname, "caught": caught, "kinds": kinds})
        shutil.rmtree(d, ignore_errors=True)
    return out


def default_plans() -> list[Path]:
    root = pins.repo_root()
    cands = [root / "tests" / "harness" / "aws" / "fixtures" / "plans" / "lowering_plan.jsonl",
             root / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl",
             root / "contracts" / "stubs" / "lowering_plan.jsonl"]
    return [p for p in cands if p.exists()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.aws.no_silent_insert")
    ap.add_argument("--plans", nargs="*")
    ap.add_argument("--report")
    ap.add_argument("ids", nargs="*", help="ignorado (ID repassado pelo despachante)")
    a = ap.parse_args(argv)
    work = pins.tmp_root() / "no_silent_insert"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    plans = [Path(p) for p in a.plans] if a.plans else default_plans()
    reports, notes, fixture_dir = [], [], None
    for i, p in enumerate(plans):
        out = work / f"render_{i}"
        man = render.render_file(p, out)
        if not man["plans"]:
            notes.append(f"{p}: nenhum plano aws ({man['counts']['OTHER_PROVIDER']} de outro provedor); nada a conferir")
            continue
        rep = check_render(out)
        reports.append(rep)
        if fixture_dir is None and all((out / m[1]).exists() for m in MUTATIONS):
            fixture_dir = out
    muts = run_mutations(fixture_dir, work / "mut") if fixture_dir else []
    n_rendered = sum(r["counts"]["RENDERED"] for r in reports)
    n_unknown = sum(r["counts"]["UNKNOWN_INPUT"] for r in reports)
    n_find = sum(len(r["findings"]) for r in reports)
    ok = bool(reports) and n_find == 0 and n_rendered >= 1 and n_unknown >= 1 and bool(muts) and \
        all(m["caught"] for m in muts)
    rep = {"schema": "bo.harness_no_silent_insert/1", "module": "HARNESS-AWS",
           "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
           "renders": reports, "notes": notes, "mutations": muts,
           "totals": {"rendered": n_rendered, "unknown_input": n_unknown, "findings": n_find,
                      "mutations": len(muts), "mutations_caught": sum(m["caught"] for m in muts)},
           "verdict": "PASS" if ok else "FAIL"}
    for r in reports:
        print(f"  {r['plan']}: {r['counts']} achados={len(r['findings'])}")
        for f in r["findings"]:
            print(f"    {f['kind']} {f['where']} {f['path']}: {f['detail']}")
    for n in notes:
        print(f"  nota: {n}")
    for m in muts:
        print(f"  {'pega ' if m['caught'] else 'PASSOU'} {m['mutation']} {m['kinds']}")
    t = rep["totals"]
    print(f"no_silent_insert: {t['rendered']} RENDERED e {t['unknown_input']} UNKNOWN_INPUT conferidos, "
          f"{t['findings']} achado(s); mutações pegas {t['mutations_caught']}/{t['mutations']} -> {rep['verdict']}")
    dest = Path(a.report) if a.report else pins.data_root() / "HARNESS-AWS" / "no_silent_insert.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
