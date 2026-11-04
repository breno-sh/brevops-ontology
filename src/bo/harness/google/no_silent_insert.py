"""Gate: HCL renderizado = plano + valores sintetizados declarados (nada inserido, nada perdido, nada trocado).

  python -I -m bo.harness.google.no_silent_insert [PLANO.jsonl ...]

Sem argumentos, confere o stub do C26 (contracts/stubs/C26/lowering_plan.jsonl) e toda fixture em
deploy/fixtures/google/_templates/plans/*/lowering_plan.jsonl. Para cada plano:
  1. renderiza em $BO_TMP/no_silent_insert/<nome>/ com bo.harness.google.render;
  2. lê o HCL com um parser INDEPENDENTE do emissor (python-hcl2, versão do requirements.lock) e achata cada
     recurso em folhas (endereço, caminho, valor);
  3. calcula, só a partir do plano e do grafo, as folhas esperadas: valores do passo, nome derivado, depends_on,
     variáveis de símbolo e de segredo, e a inserção declarada HI-GCP-01 (labels["bo-run"] = var.<plano>_bo_run,
     só nos tipos de run_label.json); e confere igualdade exata dos dois conjuntos, as perdas fora do HCL, as
     variáveis sem default e o andaime (versions.tf) igual ao fixado;
  4. plano reprovado (UNKNOWN_INPUT etc.) não pode ter .tf escrito.
Controles negativos (o gate só passa se TODOS forem pegos): atributo inserido, valor removido, valor trocado,
default em variável, rótulo bo-run removido, trocado ou posto em tipo fora da lista, campo obrigatório retirado do plano (tem de dar UNKNOWN_INPUT) e valor sintetizado sem marca
(o validador do C26 tem de recusar e nada pode ser escrito).
Relatório: $BO_DATA/HARNESS-GCP/no_silent_insert.json.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from pathlib import Path

import hcl2

from . import common as C
from . import render as R
from . import run_label as RL

_REF = re.compile(r"^(data\.)?([a-z][a-z0-9_]*)\.(SYM-[0-9a-f]{8,16})$")
_PH = re.compile(r"\{(t[0-9]+)\}")


# ------------------------------------------------------------------------------------------------ HCL -> folhas
def unquote(tok: str):
    """Token de string do hcl2 ('"..."') -> str, ou ('tmpl', partes) se houver interpolação."""
    s = tok[1:-1]
    parts, buf, i = [], [], 0
    esc = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "u":
                buf.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            buf.append(esc.get(n, n))
            i += 2
            continue
        if c in "$%" and s[i + 1:i + 3] == c + "{":
            buf.append(c + "{")
            i += 3
            continue
        if c == "$" and s[i + 1:i + 2] == "{":
            j = s.index("}", i)
            if buf:
                parts.append("".join(buf))
                buf = []
            parts.append(("expr", s[i + 2:j]))
            i = j + 1
            continue
        buf.append(c)
        i += 1
    if buf:
        parts.append("".join(buf))
    if any(isinstance(p, tuple) for p in parts):
        return ("tmpl", tuple(parts))
    return "".join(parts)


def decode(v):
    if isinstance(v, str):
        if v.startswith('"') and v.endswith('"') and len(v) >= 2:
            return unquote(v)
        if v.startswith("${") and v.endswith("}"):
            return ("expr", v[2:-1])
        return ("expr", v)
    if isinstance(v, list):
        return [decode(x) for x in v]
    if isinstance(v, dict):
        return {(k[1:-1] if k.startswith('"') else k): decode(x) for k, x in v.items() if k != "__is_block__"}
    return v


def single_block(block: dict, name: str) -> bool:
    bt = block["blocks"][name]
    return bt["nesting_mode"] in ("single", "group") or bt["max_items"] == 1


def flatten_hcl(body: dict, schema_block: dict, pre: str, out: dict, where: str, problems: list):
    for k, v in body.items():
        if k in ("__is_block__", "depends_on"):
            continue
        path = f"{pre}{k}"
        if isinstance(v, list) and v and all(isinstance(x, dict) and x.get("__is_block__") for x in v):
            if k not in schema_block["blocks"]:
                problems.append(f"{where}: bloco '{path}' fora do schema")
                continue
            sb = schema_block["blocks"][k]["block"]
            if single_block(schema_block, k):
                if len(v) != 1:
                    problems.append(f"{where}: bloco único '{path}' com {len(v)} instâncias")
                flatten_hcl(v[0], sb, path + ".", out, where, problems)
            else:
                for i, x in enumerate(v):
                    flatten_hcl(x, sb, f"{path}.{i}.", out, where, problems)
            continue
        dv = decode(v)
        if isinstance(dv, dict):
            for kk, x in dv.items():
                out[f"{path}.{kk}"] = x
        else:
            out[path] = dv


def parse_dir(d: Path) -> dict:
    """{'resource': {endereço: corpo}, 'variable': {nome: corpo}, 'terraform': [...], 'other': [...]}"""
    res = {"resource": {}, "variable": {}, "terraform": [], "other": []}
    for f in sorted(d.glob("*.tf")):
        doc = hcl2.loads(f.read_text(encoding="utf-8"))
        for top, items in doc.items():
            if top.startswith("__"):          # comentários e metadados do parser, não blocos
                continue
            for item in items:
                if top in ("resource", "data"):
                    for t, named in item.items():
                        for n, body in named.items():
                            addr = f"{t.strip(chr(34))}.{n.strip(chr(34))}"
                            res["resource"][("data." if top == "data" else "") + addr] = body
                elif top == "variable":
                    for n, body in item.items():
                        res["variable"][n.strip('"')] = body
                elif top == "terraform":
                    res["terraform"].append(item)
                else:
                    res["other"].append(top)
    return res


# ------------------------------------------------------------------------------------------------ plano -> folhas
class Expected:
    """Folhas esperadas calculadas só do plano, do grafo e das convenções de nome documentadas no render."""

    def __init__(self, plan: dict, graph: dict, schema):
        self.plan, self.graph, self.schema = plan, graph, schema
        self.slug = C.slug(plan["plan_id"])
        self.terms = {t["term_id"]: t["term"] for t in graph.get("terms", [])}
        self.comps = {c["node_id"]: c for c in graph.get("components", [])}
        self.by_order = {s["order"]: s for s in plan["steps"]}
        self.by_node = {s["node_id"]: s for s in plan["steps"] if s["action"] != "configure"}
        self.leaves: dict = {}
        self.deps: dict = {}
        self.vars: dict = {}
        self.losses: list = []

    def owner(self, st: dict) -> dict:
        if st["action"] == "configure" and st["node_id"] in self.comps:
            parent = self.by_node.get(self.comps[st["node_id"]]["of"])
            if parent is not None and parent["resource_type"] == st["resource_type"]:
                return parent
        return st

    def addr(self, st: dict) -> str:
        st = self.owner(st)
        a = f"{st['resource_type']}.{self.slug}_{st['node_id']}"
        return "data." + a if st["action"] == "reference" else a

    def block(self, st: dict) -> dict:
        st = self.owner(st)
        return self.schema.block("data" if st["action"] == "reference" else "resource", st["resource_type"])

    def term(self, t: dict, st: dict, fld: str):
        k = t["kind"]
        if k == "literal":
            return t["value"]
        if k == "symbol":
            name = f"{self.slug}_{C.slug(t['symbol_id'])}"
            self.vars[name] = False
            return ("expr", "var." + name)
        if k == "withheld":
            name = f"{self.slug}_{st['node_id']}_secret_{C.slug(fld)}"
            self.vars[name] = True
            return ("expr", "var." + name)
        if k == "reference":
            m = _REF.match(t["target_address"])
            hits = [s for s in self.plan["steps"] if s["resource_type"] == m.group(2)
                    and (s["action"] == "reference") == bool(m.group(1))
                    and any(self.terms.get(x, {}).get("symbol_id") == m.group(3)
                            for x in (s.get("derived_name") or {}).get("from_terms", []))]
            return ("expr", f"{self.addr(hits[0])}.{t['attribute']}")
        if k == "document":
            return json.dumps(t["tree"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        raise ValueError(k)

    def name(self, st: dict):
        dn = st["derived_name"]
        parts, pos = [], 0
        for m in _PH.finditer(dn["template"]):
            parts.append(dn["template"][pos:m.start()])
            t = self.terms[m.group(1)]
            parts.append(self.term(t, st, "name") if t["kind"] == "symbol" else str(t["value"]))
            pos = m.end()
        parts.append(dn["template"][pos:])
        merged = []
        for p in parts:
            if p == "":
                continue
            if isinstance(p, str) and merged and isinstance(merged[-1], str):
                merged[-1] += p
            else:
                merged.append(p)
        return ("tmpl", tuple(merged)) if any(isinstance(p, tuple) for p in merged) else "".join(merged)

    def flat(self, block: dict, path: str, v, out: dict):
        segs = [s for s in path.split(".")]
        node, i = block, 0
        while i < len(segs) and segs[i] in node["blocks"]:
            nm = segs[i]
            node_b = node["blocks"][nm]
            if i + 1 == len(segs) and isinstance(v, list) and not single_block(node, nm):
                for j, item in enumerate(v):
                    for k, x in item.items():
                        self.flat(node_b["block"], k, x, sub := {})
                        for kk, xx in sub.items():
                            out[f"{path}.{j}.{kk}"] = xx
                return
            node = node_b["block"]
            i += 1
            if i < len(segs) and segs[i].isdigit():
                i += 1
        if isinstance(v, dict):
            for k, x in v.items():
                self.flat(block, f"{path}.{k}", x, out)
            return
        out[path] = v

    def build(self):
        for st in sorted(self.plan["steps"], key=lambda s: s["order"]):
            a = self.addr(st)
            leaves = self.leaves.setdefault(a, {})
            blk = self.block(st)
            for v in st["values"]:
                self.flat(blk, v["field"], self.term(v["term"], st, v["field"]), leaves)
            if "derived_name" in st:
                leaves["name"] = self.name(st)
            deps = self.deps.setdefault(a, [])
            for d in st["depends_on"]:
                da = self.addr(self.by_order[d])
                if da != a and da not in deps:
                    deps.append(da)
            self.losses += [(a, x["field"]) for x in st["losses"]]
        # inserção declarada HI-GCP-01: rótulo da execução nos recursos dos tipos da lista (nunca em data source)
        for st in self.plan["steps"]:
            own = self.owner(st)
            if own["action"] != "reference" and own["resource_type"] in RL.types():
                name = RL.var_name(self.slug)
                self.leaves[self.addr(st)][f"{RL.ATTRIBUTE}.{RL.LABEL_KEY}"] = ("expr", "var." + name)
                self.vars[name] = False
        return self


# ------------------------------------------------------------------------------------------------ comparação
def norm(v):
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return ("n", float(v))
    if isinstance(v, list):
        return tuple(norm(x) for x in v)
    if isinstance(v, tuple):
        return tuple(norm(x) if not isinstance(x, str) else x for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, norm(x)) for k, x in v.items()))
    return v


def compare(rendered_dir: Path, plan: dict, graph: dict, schema) -> list[str]:
    """Lista de problemas (vazia = HCL é exatamente plano + declarados)."""
    probs: list[str] = []
    exp = Expected(plan, graph, schema).build()
    got = parse_dir(rendered_dir)
    if got["other"]:
        probs.append(f"blocos de topo fora do esperado: {sorted(set(got['other']))}")
    # andaime
    want_tf = {"required_version": "= " + C.pins()["terraform"]["version"],
               "google": {"source": "hashicorp/google", "version": "= " + schema.version}}
    tf = got["terraform"]
    if len(tf) != 1:
        probs.append(f"{len(tf)} bloco(s) terraform (esperado 1, o andaime)")
    else:
        t = decode(tf[0])
        rp = t.get("required_providers") or [{}]
        seen = {"required_version": t.get("required_version"), "google": (rp[0] if isinstance(rp, list) else {})
                .get("google")}
        if seen != want_tf or set(t) - {"required_version", "required_providers"} or \
                set(rp[0] if isinstance(rp, list) else {}) - {"google", "__is_block__"}:
            probs.append(f"andaime diferente do fixado: {seen}")
    # variáveis: exatamente as dos símbolos e segredos, sem default
    if set(got["variable"]) != set(exp.vars):
        probs.append(f"variáveis {sorted(got['variable'])} ≠ esperadas {sorted(exp.vars)}")
    for n, body in got["variable"].items():
        b = decode(body)
        if "default" in b:
            probs.append(f"variável {n} com default (valor inventado)")
        if bool(b.get("sensitive")) != exp.vars.get(n, False):
            probs.append(f"variável {n}: sensitive={b.get('sensitive')} ≠ esperado {exp.vars.get(n, False)}")
        if set(b) - {"type", "description", "sensitive"}:
            probs.append(f"variável {n} com argumentos extras {sorted(set(b) - {'type', 'description', 'sensitive'})}")
    # recursos
    if set(got["resource"]) != set(exp.leaves):
        probs.append(f"recursos {sorted(got['resource'])} ≠ esperados {sorted(exp.leaves)}")
    for a in sorted(set(got["resource"]) & set(exp.leaves)):
        body = got["resource"][a]
        rtype = a.removeprefix("data.").split(".")[0]
        blk = schema.block("data" if a.startswith("data.") else "resource", rtype)
        obs: dict = {}
        flatten_hcl(body, blk, "", obs, a, probs)
        want = exp.leaves[a]
        for p in sorted(set(obs) - set(want)):
            probs.append(f"{a}: '{p}' no HCL sem origem no plano (inserção silenciosa)")
        for p in sorted(set(want) - set(obs)):
            probs.append(f"{a}: '{p}' do plano ausente no HCL (valor perdido)")
        for p in sorted(set(obs) & set(want)):
            if norm(obs[p]) != norm(want[p]):
                probs.append(f"{a}: '{p}' = {obs[p]!r} no HCL, plano diz {want[p]!r}")
        deps = [d[1] for d in decode(body.get("depends_on", []))] if body.get("depends_on") else []
        if sorted(deps) != sorted(exp.deps.get(a, [])):
            probs.append(f"{a}: depends_on {deps} ≠ plano {exp.deps.get(a, [])}")
    for a, f in exp.losses:
        leaves = {}
        if a in got["resource"]:
            rtype = a.removeprefix("data.").split(".")[0]
            flatten_hcl(got["resource"][a], schema.block("data" if a.startswith("data.") else "resource", rtype),
                        "", leaves, a, [])
        if any(p == f or p.startswith(f + ".") for p in leaves):
            probs.append(f"{a}: perda declarada '{f}' aparece no HCL")
    return probs


def check_report(rep: dict, plan: dict) -> list[str]:
    """O render_report lista exatamente os valores sintetizados/default do plano, todos marcados."""
    want = sorted((s["order"], v["field"], v["origin"]) for s in plan["steps"] for v in s["values"]
                  if v["origin"] in ("synthesized", "default_declared"))
    got = sorted((x["order"], x["field"], x["origin"]) for x in rep["synthesized"])
    probs = [] if want == got else [f"sintetizados no relatório {got} ≠ plano {want}"]
    probs += [f"sintetizado sem marca: {x['field']}" for x in rep["synthesized"] if not x["marked"]]
    return probs


# ------------------------------------------------------------------------------------------------ execução
def default_plans() -> list[Path]:
    stub = C.repo() / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"
    return [stub] + sorted((C.templates() / "plans").glob("*/lowering_plan.jsonl"))


def run_plan(plan_path: Path, work: Path, schema) -> dict:
    out = work / C.slug(plan_path.parent.name if plan_path.parent.name != "C26" else "stub_c26")
    if out.exists():
        shutil.rmtree(out)
    rc, rep = R.render_file(plan_path, out)
    res = {"plan_file": str(plan_path), "render_rc": rc, "plans": []}
    if rc:
        res["problems"] = [f"render saiu {rc}: {rep.get('errors', [])[:3]}"]
        return res
    graphs = {g["graph_id"]: g for g in C.read_jsonl(plan_path.with_name("graph_ir.jsonl"))}
    plans = {p["plan_id"]: p for p in C.read_jsonl(plan_path)}
    for pr in rep["plans"]:
        plan = plans[pr["plan_id"]]
        item = {"plan_id": pr["plan_id"], "status": pr["status"], "problems": []}
        f = out / R.file_name(pr["plan_id"])
        if pr["status"] == R.RENDERED:
            one = out / ("_only_" + C.slug(pr["plan_id"]))
            one.mkdir()
            shutil.copy(f, one / f.name)
            shutil.copy(out / "versions.tf", one / "versions.tf")
            item["problems"] += compare(one, plan, graphs[plan["graph_id"]], schema)
            item["problems"] += check_report(pr, plan)
            item["leaves"] = sum(1 for x in pr["ledger"] if x["path"] != "depends_on")
            shutil.rmtree(one)
        else:
            if f.exists():
                item["problems"].append(f"plano reprovado ({pr['status']}) com HCL escrito")
            item["failures"] = [x["code"] for x in pr["failures"]]
        res["plans"].append(item)
    return res


def negative_controls(work: Path, schema) -> list[dict]:
    """Cada sabotagem tem de ser pega; devolve [{control, caught, detail}]."""
    fx = C.templates() / "plans" / "net_sql"
    plan = C.read_jsonl(fx / "lowering_plan.jsonl")[0]
    graph = C.read_jsonl(fx / "graph_ir.jsonl")[0]
    base = work / "neg_base"
    if base.exists():
        shutil.rmtree(base)
    rc, rep = R.render_file(fx / "lowering_plan.jsonl", base)
    tf = base / R.file_name(plan["plan_id"])
    text = tf.read_text(encoding="utf-8")
    out = []

    def sabotage(label: str, new_text: str, expect: str):
        """Pego = o texto mudou E o comparador acusa exatamente o defeito plantado (regex), não outro qualquer."""
        d = work / ("neg_" + C.slug(label))
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        (d / tf.name).write_text(new_text, encoding="utf-8")
        shutil.copy(base / "versions.tf", d / "versions.tf")
        probs = compare(d, plan, graph, schema)
        hit = new_text != text and any(re.search(expect, p) for p in probs)
        out.append({"control": label, "caught": hit, "expected": expect, "detail": probs[:2]})

    # controle do controle: a cópia sem sabotagem não pode ter problema nenhum
    ctl = work / "neg_controle"
    if ctl.exists():
        shutil.rmtree(ctl)
    ctl.mkdir()
    shutil.copy(tf, ctl / tf.name)
    shutil.copy(base / "versions.tf", ctl / "versions.tf")
    p0 = compare(ctl, plan, graph, schema)
    out.append({"control": "cópia sem sabotagem passa", "caught": not p0, "expected": "nenhum problema",
                "detail": p0[:2]})

    sabotage("atributo inserido", text.replace("  deletion_protection = false\n",
                                               "  deletion_protection = false\n  region = \"us-east1\"\n", 1),
             r"'region' no HCL sem origem")
    sabotage("bloco inserido", text.replace("    tier    = \"db-f1-micro\"\n",
                                            "    tier    = \"db-f1-micro\"\n    insights_config {\n"
                                            "      query_insights_enabled = true\n    }\n", 1),
             r"'settings\.insights_config\.query_insights_enabled' no HCL sem origem")
    sabotage("valor removido", text.replace("    edition = \"ENTERPRISE\"\n", "", 1),
             r"'settings\.edition' do plano ausente")
    sabotage("valor trocado", text.replace("retained_backups = 7", "retained_backups = 8", 1),
             r"retained_backups' = 8 no HCL, plano diz 7")
    sabotage("default em variável", text.replace("  sensitive   = true\n",
                                                 "  sensitive   = true\n  default     = \"x\"\n", 1),
             r"com default")
    sabotage("depends_on removido", re.sub(r"\n  depends_on += \[[^\]]*\]", "", text, count=1),
             r"depends_on \[\] ≠ plano")
    sabotage("variável extra", text + '\nvariable "x_extra" {\n  type = string\n}\n', r"variáveis .* ≠ esperadas")
    sabotage("rótulo bo-run em tipo fora da lista", text.replace("  deletion_protection = false\n",
                                                               "  deletion_protection = false\n  labels = {\n"
                                                               "    \"bo-run\" = \"x\"\n  }\n", 1),
             r"'labels' no HCL sem origem|'labels\.bo-run' no HCL sem origem")
    out += label_controls(work, schema)
    # campo obrigatório retirado do plano -> UNKNOWN_INPUT, nada escrito
    p2 = copy.deepcopy(plan)
    p2["steps"][1]["values"] = [v for v in p2["steps"][1]["values"] if v["field"] != "database_version"]
    r2 = R.render_plan(p2, graph, schema)
    out.append({"control": "obrigatório ausente vira UNKNOWN_INPUT", "caught": r2.status == "UNKNOWN_INPUT"
                and r2.hcl is None, "detail": [f["detail"] for f in r2.failures][:2]})
    # sintetizado sem marca: o validador do C26 recusa e o render não escreve nada
    d = work / "neg_unmarked"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()
    p3 = copy.deepcopy(plan)
    p3["steps"][0]["values"][0]["marked"] = False
    C.write_jsonl(d / "lowering_plan.jsonl", [p3])
    C.write_jsonl(d / "graph_ir.jsonl", [graph])
    rc3, rep3 = R.render_file(d / "lowering_plan.jsonl", d / "out")
    out.append({"control": "sintetizado sem marca recusado na entrada",
                "caught": rc3 == 1 and not (d / "out").exists(), "detail": rep3.get("errors", [])[:1]})
    return out


def label_controls(work: Path, schema) -> list[dict]:
    """Sabotagens do rótulo bo-run (HI-GCP-01) na fixture bucket: removido, trocado, variável com default."""
    fx = C.templates() / "plans" / "bucket"
    plan = C.read_jsonl(fx / "lowering_plan.jsonl")[0]
    graph = C.read_jsonl(fx / "graph_ir.jsonl")[0]
    base = work / "neg_label_base"
    if base.exists():
        shutil.rmtree(base)
    rc, rep = R.render_file(fx / "lowering_plan.jsonl", base)
    tf = base / R.file_name(plan["plan_id"])
    if rc or not tf.exists():
        # fixture fora do C26 ou não renderizada: os controles do rótulo não rodam, e isso conta como não pego
        return [{"control": "fixture bucket renderiza para os controles do rótulo", "caught": False,
                 "expected": "RENDERED", "detail": (rep.get("errors") or [p["status"] for p in rep.get("plans", [])])[:2]}]
    text = tf.read_text(encoding="utf-8")
    var = RL.var_name(C.slug(plan["plan_id"]))
    line = re.search(r'\n( *)"?bo-run"? += var\.' + var + r"\n", text)
    out = [{"control": "rótulo bo-run presente na fixture bucket", "caught": bool(line), "expected": "linha do rótulo",
            "detail": []}]
    if not line:
        return out

    def sabotage(label: str, new_text: str, expect: str):
        d = work / ("neg_" + C.slug(label))
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        (d / tf.name).write_text(new_text, encoding="utf-8")
        shutil.copy(base / "versions.tf", d / "versions.tf")
        probs = compare(d, plan, graph, schema)
        hit = new_text != text and any(re.search(expect, p) for p in probs)
        out.append({"control": label, "caught": hit, "expected": expect, "detail": probs[:2]})

    sabotage("rótulo bo-run removido", text.replace(line.group(0), "\n", 1), r"'labels\.bo-run' do plano ausente")
    sabotage("rótulo bo-run trocado", text.replace(line.group(0), f'\n{line.group(1)}"bo-run" = "fixo"\n', 1),
             r"'labels\.bo-run' = 'fixo' no HCL")
    sabotage("rótulo bo-run com default", re.sub(r'(variable "' + var + r'" \{\n)', r'\1  default = "x"\n', text,
                                                 count=1), r"variável " + var + " com default")
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = [a for a in argv if a != C.MODULE]
    plans = [Path(a) for a in argv] or default_plans()
    schema = R.Schema.load()
    work = C.tmp() / "no_silent_insert"
    work.mkdir(parents=True, exist_ok=True)
    results = [run_plan(p, work, schema) for p in plans]
    neg = negative_controls(work, schema)
    n_plans = sum(len(r["plans"]) for r in results)
    probs = [p for r in results for p in r.get("problems", [])] + \
            [f"{x['plan_id']}: {p}" for r in results for x in r["plans"] for p in x["problems"]]
    missed = [x["control"] for x in neg if not x["caught"]]
    rendered = sum(1 for r in results for x in r["plans"] if x["status"] == R.RENDERED)
    leaves = sum(x.get("leaves", 0) for r in results for x in r["plans"])
    rep = {"schema": "bo.harness_google.no_silent_insert/1", "module": C.MODULE, "generated_at": C.now(),
           "plans_checked": n_plans, "rendered": rendered, "leaves_checked": leaves,
           "problems": probs, "negative_controls": neg, "results": results,
           "verdict": "PASS" if not probs and not missed and n_plans else "FAIL"}
    (C.module_data() / "no_silent_insert.json").write_text(C.dump(rep), encoding="utf-8")
    print(f"[{C.now()}] no_silent_insert: {n_plans} plano(s), {rendered} renderizado(s), {leaves} folha(s) "
          f"conferidas; {len(probs)} problema(s); controles negativos pegos {len(neg) - len(missed)}/{len(neg)}")
    for r in results:
        for x in r["plans"]:
            extra = f" ({', '.join(x.get('failures', []))})" if x.get("failures") else ""
            print(f"  {x['plan_id']}: {x['status']}{extra} — {len(x['problems'])} problema(s)")
    for p in probs[:30]:
        print("  PROBLEMA " + p)
    for m in missed:
        print("  CONTROLE NÃO PEGO " + m)
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
