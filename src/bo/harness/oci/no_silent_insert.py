"""Gate: HCL renderizado = plano + valores sintetizados declarados (nada inserido, nada perdido).

  python -I -m bo.harness.oci.no_silent_insert [PLANO.jsonl ...] [--bindings B.json]

Sem argumentos, o corpus é: o stub do C26 (contracts/stubs/C26/lowering_plan.jsonl, e contracts/stubs/
lowering_plan.jsonl se existir), os planos de exemplo dos moldes (deploy/fixtures/oci/_templates/examples) e as
mutações geradas deles. Três checagens:

  1. Independente do renderizador: o HCL de cada plano RENDERED é lido de volta pelo python-hcl2 (outro parser) e
     achatado em caminhos; cada folha de recurso tem de casar com exatamente um valor do plano (mesmo caminho e mesmo
     valor), e cada valor do plano com exatamente uma folha. Folha sem valor = INSERÇÃO; valor sem folha = PERDA.
     Fora dos recursos, só o encanamento do molde (root_template.json): bloco terraform com as versões fixadas,
     provider com os atributos do molde, variáveis usadas por algum valor e módulos com source + variáveis.
  2. Mutações: tirar um campo obrigatório (pelo schema do oci fixado) de um plano RENDERED tem de dar UNKNOWN_INPUT e
     nenhum HCL do plano; idem para escolha sem seleção, símbolo sem binding e fecho de dependências aberto; campo fora
     do schema tem de dar INVALID_PLAN.
  3. Vacuidade: o gate reprova se nenhum plano foi renderizado e conferido.

Relatório (só contagens e códigos) em $BO_DATA/HARNESS-OCI/no_silent_insert.json.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path

from . import MODULE_ID, module_data, repo_root, templates_dir, tmp_root
from . import render as R
from . import schema as S

EXPR = re.compile(r"^\$\{(.*)\}$", re.S)


# ------------------------------------------------------------------------------------------- leitura independente
def _unquote(s: str):
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        body = s[1:-1].replace("$${", "${").replace("%%{", "%{")
        return json.loads('"' + body + '"')
    m = EXPR.match(s)
    if m:
        return ("expr", m.group(1))
    return ("raw", s)


def norm(v):
    if isinstance(v, str):
        return _unquote(v)
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {(_unquote(k) if isinstance(k, str) and k.startswith('"') else k): norm(x)
                for k, x in v.items() if k != "__is_block__"}
    return v


def flatten(body: dict, prefix: tuple = ()) -> dict:
    """Corpo de bloco do hcl2 -> {caminho (tupla de segmentos, índices como int): valor normalizado}."""
    out = {}
    for k, v in body.items():
        if k == "__is_block__":
            continue
        if isinstance(v, list) and v and all(isinstance(x, dict) and x.get("__is_block__") for x in v):
            for i, b in enumerate(v):
                out.update(flatten(b, prefix + (k, i)))
        elif isinstance(v, dict) and not v.get("__is_block__"):
            nv = norm(v)
            if not nv:
                out[prefix + (k,)] = {}
            for kk, vv in _flat_map(nv, prefix + (k,)):
                out[kk] = vv
        else:
            out[prefix + (k,)] = norm(v)
    return out


def _flat_map(d, prefix):
    for k, v in d.items():
        if isinstance(v, dict) and v:
            yield from _flat_map(v, prefix + (k,))
        else:
            yield prefix + (k,), v


def _strip_idx(path: tuple) -> tuple:
    return tuple(p for p in path if not isinstance(p, int))


def _match(field: str, hpath: tuple) -> bool:
    """O caminho do plano casa com o caminho do HCL? Índice implícito = 0; explícito tem de bater."""
    segs = field.split(".")
    plan_names = [s for s in segs if not s.isdigit()]
    if list(_strip_idx(hpath)) != plan_names:
        return False
    # índices do HCL logo depois de cada nome; índices do plano idem (implícito 0)
    h_idx, i = {}, 0
    for j, p in enumerate(hpath):
        if isinstance(p, int):
            h_idx[i - 1] = p
        else:
            i += 1
    p_idx, i = {}, 0
    for s in segs:
        if s.isdigit():
            p_idx[i - 1] = int(s)
        else:
            i += 1
    for pos in h_idx:
        if h_idx[pos] != p_idx.get(pos, 0):
            return False
    return all(pos in h_idx for pos in p_idx)


def _expected(value: dict, plan: dict, bindings: dict, tpl: R.Templates, labels_by_type: dict):
    t = value["term"]
    k = t["kind"]
    if k == "literal":
        return ("eq", t["value"])
    if k == "symbol":
        key = bindings.get(t["symbol_id"])
        return ("eq", ("expr", f"var.{tpl.binding_var(key)}")) if key else ("never", None)
    if k == "reference":
        labs = labels_by_type.get(t["target_type"], [])
        pats = [f"{'data.' if t['target_address'].startswith('data.') else ''}{t['target_type']}.{lab}."
                f"{t.get('attribute')}" for lab in labs]
        return ("one_of", [("expr", p) for p in pats])
    if k == "withheld":
        return ("prefix", ("expr", "var." + tpl.root["variable_prefixes"]["withheld"]))
    if k == "document":
        fn = "yamlencode(" if t["format"] == "yaml" else "jsonencode("
        return ("prefix", ("expr", fn))
    return ("any_expr", None)


def _value_ok(exp, got) -> bool:
    kind, e = exp
    if kind == "eq":
        return got == e or (isinstance(e, (int, float)) and not isinstance(e, bool) and isinstance(got, (int, float))
                            and not isinstance(got, bool) and float(got) == float(e))
    if kind == "one_of":
        return got in e
    if kind == "prefix":
        return isinstance(got, tuple) and got[0] == "expr" and got[1].startswith(e[1])
    if kind == "any_expr":
        return isinstance(got, tuple) and got[0] == "expr"
    return False


def check_rendered(out: Path, plan: dict, pr_report: dict, bindings: dict, tpl: R.Templates) -> list[str]:
    import hcl2
    v: list[str] = []
    mod = pr_report["module"]
    d = hcl2.load(open(out / mod / "main.tf", encoding="utf-8"))
    allowed_top = {"terraform", "variable", "resource", "data", "__comments__"}
    for k in d:
        if k not in allowed_top:
            v.append(f"{plan['plan_id']}: bloco de topo fora do molde: {k}")
    # labels independentes: node_id, ou node_id_s<ordem> se o nó aparece em mais de um passo
    cnt = {}
    for s in plan["steps"]:
        cnt[s["node_id"]] = cnt.get(s["node_id"], 0) + 1
    label = {s["order"]: (s["node_id"] if cnt[s["node_id"]] == 1 else f"{s['node_id']}_s{s['order']}")
             for s in plan["steps"]}
    labels_by_type: dict = {}
    for s in plan["steps"]:
        labels_by_type.setdefault(s["resource_type"], []).append(label[s["order"]])
    want_blocks = {("data" if s["action"] == "reference" else "resource", s["resource_type"], label[s["order"]]): s
                   for s in plan["steps"]}
    got_blocks = {}
    for kind in ("resource", "data"):
        for item in d.get(kind, []):
            for rtype, inner in item.items():
                for lab, body in inner.items():
                    got_blocks[(kind, _unquote(rtype), _unquote(lab))] = body
    for key in sorted(set(got_blocks) - set(want_blocks)):
        v.append(f"{plan['plan_id']}: bloco {key} sem passo no plano (INSERÇÃO)")
    for key in sorted(set(want_blocks) - set(got_blocks)):
        v.append(f"{plan['plan_id']}: passo {key} sem bloco no HCL (PERDA)")
    used_vars = set()
    for key, step in want_blocks.items():
        if key not in got_blocks:
            continue
        flat = flatten(got_blocks[key])
        claimed = {}
        for val in step["values"]:
            hits = [h for h in flat if _match(val["field"], h)]
            if len(hits) != 1:
                v.append(f"{plan['plan_id']} passo {step['order']}: {val['field']} casa com {len(hits)} folha(s) "
                         f"do HCL ({'PERDA' if not hits else 'AMBÍGUO'})")
                continue
            h = hits[0]
            if h in claimed:
                v.append(f"{plan['plan_id']} passo {step['order']}: folha {h} reclamada por dois valores")
            claimed[h] = val["field"]
            exp = _expected(val, plan, bindings, tpl, labels_by_type)
            if not _value_ok(exp, flat[h]):
                v.append(f"{plan['plan_id']} passo {step['order']}: {val['field']} no HCL difere do plano")
            got = flat[h]
            if isinstance(got, tuple) and got[0] == "expr":
                used_vars |= set(re.findall(r"\bvar\.([A-Za-z0-9_]+)", got[1]))
        for h in sorted(set(flat) - set(claimed), key=str):
            v.append(f"{plan['plan_id']} passo {step['order']}: folha {'.'.join(map(str, h))} sem valor no plano "
                     f"(INSERÇÃO)")
    declared = set()
    for item in d.get("variable", []):
        for name, body in item.items():
            declared.add(_unquote(name))
            extra = set(body) - {"type", "sensitive", "__is_block__"}
            if extra:
                v.append(f"{plan['plan_id']}: variável {name} com campos fora do molde {sorted(extra)}")
            if "default" in body:
                v.append(f"{plan['plan_id']}: variável {name} com default (valor inventado)")
    if declared != used_vars:
        v.append(f"{plan['plan_id']}: variáveis declaradas {sorted(declared)} ≠ usadas {sorted(used_vars)}")
    v += _check_terraform_block(d, tpl, root=False, where=plan["plan_id"])
    return v


def _check_terraform_block(d: dict, tpl: R.Templates, root: bool, where: str) -> list[str]:
    v = []
    tfs = d.get("terraform", [])
    if len(tfs) != 1:
        return [f"{where}: {len(tfs)} bloco(s) terraform"]
    tf = tfs[0]
    keys = set(tf) - {"__is_block__"}
    want = {"required_providers"} | ({"required_version"} if root else set())
    if keys != want:
        v.append(f"{where}: bloco terraform com {sorted(keys)}, molde {sorted(want)}")
    if root and norm(tf.get("required_version")) != tpl.root["terraform"]["required_version"]:
        v.append(f"{where}: required_version fora do molde")
    rp = tf.get("required_providers", [{}])[0]
    provs = {k: norm(x) for k, x in rp.items() if k != "__is_block__"}
    if provs != tpl.root["required_providers"]:
        v.append(f"{where}: required_providers {provs} fora do molde")
    return v


def check_root(out: Path, renders: list, tpl: R.Templates) -> list[str]:
    import hcl2
    d = hcl2.load(open(out / "main.tf", encoding="utf-8"))
    v = _check_terraform_block(d, tpl, root=True, where="raiz")
    done = [p for p in renders if p["status"] == "RENDERED"]
    allowed = {"terraform", "__comments__"} | ({"provider", "variable", "module"} if done else set())
    for k in d:
        if k not in allowed:
            v.append(f"raiz: bloco de topo fora do molde: {k}")
    if done:
        provs = d.get("provider", [])
        want = {"oci": {k: ("expr", f"var.{x}") for k, x in tpl.root["provider"]["attributes"].items()}}
        got = {_unquote(n): {k: norm(x) for k, x in b.items() if k != "__is_block__"} for p in provs for n, b in p.items()}
        if got != want:
            v.append("raiz: provider fora do molde")
        mods = {}
        for item in d.get("module", []):
            for n, b in item.items():
                mods[_unquote(n)] = {k: norm(x) for k, x in b.items() if k != "__is_block__"}
        want_mods = {p["module"]: p for p in done}
        if set(mods) != set(want_mods):
            v.append(f"raiz: módulos {sorted(mods)} ≠ planos renderizados {sorted(want_mods)}")
        for n, body in mods.items():
            if n not in want_mods:
                continue
            want_vars = {x["name"] for x in want_mods[n]["variables"]}
            exp = {"source": f"./{n}", **{x: ("expr", f"var.{x}") for x in want_vars}}
            if body != exp:
                v.append(f"raiz: módulo {n} passa {sorted(body)}, esperado {sorted(exp)}")
        root_vars = {x["name"] for x in tpl.root["root_variables"]} | {x["name"] for p in done for x in p["variables"]}
        declared = {_unquote(n) for item in d.get("variable", []) for n in item}
        if declared != root_vars:
            v.append(f"raiz: variáveis {sorted(declared)} ≠ {sorted(root_vars)}")
    return v


# ------------------------------------------------------------------------------------------- mutações
def mutations(plan: dict, bindings: dict) -> list[tuple[str, dict, dict, str]]:
    """(nome, plano mutado, bindings, situação esperada)."""
    table = S.table()
    out = []
    for s in plan["steps"]:
        kind = "data" if s["action"] == "reference" else "resource"
        blk = table.block(kind, s["resource_type"])
        for i, val in enumerate(s["values"]):
            try:
                toks, attr = S.resolve(blk, val["field"])
            except S.PathError:
                continue
            if attr.required and all(t.kind != "key" for t in toks):
                m = copy.deepcopy(plan)
                ms = next(x for x in m["steps"] if x["order"] == s["order"])
                del ms["values"][i]
                out.append((f"sem_{s['node_id']}_{val['field']}", m, bindings, "UNKNOWN_INPUT"))
            if val["term"]["kind"] == "symbol" and val["term"]["symbol_id"] in bindings:
                nb = {k: x for k, x in bindings.items() if k != val["term"]["symbol_id"]}
                out.append((f"sem_binding_{s['node_id']}_{val['field']}", plan, nb, "UNKNOWN_INPUT"))
        m = copy.deepcopy(plan)
        ms = next(x for x in m["steps"] if x["order"] == s["order"])
        ms["values"].append({"field": "campo_que_nao_existe", "term": {"kind": "literal", "datatype": "string",
                                                                      "value": "x"}, "origin": "carried",
                             "marked": False})
        out.append((f"campo_fora_{s['node_id']}", m, bindings, "INVALID_PLAN"))
        if s["typed_choices"]:
            m = copy.deepcopy(plan)
            ms = next(x for x in m["steps"] if x["order"] == s["order"])
            ms["typed_choices"][0]["selected"] = None
            out.append((f"escolha_aberta_{s['node_id']}", m, bindings, "UNKNOWN_INPUT"))
    m = copy.deepcopy(plan)
    m["dependency_closure"] = {"closed": False, "missing": ["r_fora_do_plano"]}
    out.append(("fecho_aberto", m, bindings, "UNKNOWN_INPUT"))
    return out


def _write_bindings(path: Path, bindings: dict) -> None:
    path.write_text(json.dumps({"schema": "bo.harness.oci.bindings/1",
                                "bindings": [{"symbol_id": k, "key": v} for k, v in sorted(bindings.items())]}),
                    encoding="utf-8")


def run_corpus(plan_files: list[tuple[Path, Path | None]], work: Path) -> dict:
    tpl = R.Templates.load()
    rep = {"files": [], "rendered_checked": 0, "status_counts": {s: 0 for s in R.STATUS}, "violations": [],
           "mutations": {"total": 0, "as_expected": 0, "failed": []}}
    for k, (pf, bf) in enumerate(plan_files):
        out = work / f"corpus_{k}"
        rr = R.render(pf, out, bindings_path=bf)
        bindings = R.load_bindings(bf)
        plans = {p["plan_id"]: p for p in R.load_jsonl(pf)}
        rep["files"].append({"file": _portable(pf), "plans": len(plans)})
        rep["violations"] += check_root(out, rr.report["plans"], tpl)
        for pr in rr.report["plans"]:
            rep["status_counts"][pr["status"]] += 1
            if pr["status"] != "RENDERED":
                if (out / R.module_name(pr["plan_id"])).exists():
                    rep["violations"].append(f"{pr['plan_id']}: {pr['status']} com HCL escrito")
                continue
            rep["violations"] += check_rendered(out, plans[pr["plan_id"]], pr, bindings, tpl)
            rep["rendered_checked"] += 1
            # mutações deste plano
            graph = pf.parent / "graph_ir.jsonl"
            for name, mplan, mb, want in mutations(plans[pr["plan_id"]], bindings):
                rep["mutations"]["total"] += 1
                mdir = work / f"mut_{k}_{len(rep['mutations']['failed'])}_{rep['mutations']['total']}"
                mdir.mkdir(parents=True, exist_ok=True)
                (mdir / "lowering_plan.jsonl").write_text(json.dumps(mplan) + "\n", encoding="utf-8")
                if graph.exists():
                    shutil.copy(graph, mdir / "graph_ir.jsonl")
                mbf = mdir / "bindings.json"
                _write_bindings(mbf, mb)
                mr = R.render(mdir / "lowering_plan.jsonl", mdir / "out", bindings_path=mbf)
                got = mr.report["plans"][0]["status"]
                wrote = (mdir / "out" / R.module_name(pr["plan_id"])).exists()
                if got == want and not wrote:
                    rep["mutations"]["as_expected"] += 1
                else:
                    rep["mutations"]["failed"].append(f"{pr['plan_id']} {name}: {got} (esperado {want}), "
                                                      f"HCL escrito={wrote}")
    return rep


def _portable(p: Path) -> str:
    p = p.resolve()
    for root, tag in ((repo_root().resolve(), "$BO_REPO"), (tmp_root().resolve(), "$BO_TMP")):
        if root == p or root in p.parents:
            return tag + "/" + str(p.relative_to(root))
    return p.name


def default_corpus() -> list[tuple[Path, Path | None]]:
    stubs = repo_root() / "contracts" / "stubs"
    out = []
    for p in (stubs / "lowering_plan.jsonl", stubs / "C26" / "lowering_plan.jsonl"):
        if p.exists():
            b = p.parent / "bindings.json"
            out.append((p, b if b.exists() else None))
    ex = templates_dir() / "examples"
    out.append((ex / "lowering_plan.jsonl", ex / "bindings.json"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.oci.no_silent_insert")
    ap.add_argument("plans", nargs="*", type=Path)
    ap.add_argument("--bindings", type=Path)
    ap.add_argument("--report", type=Path, default=None)
    a = ap.parse_args(argv)
    files = [(p, a.bindings) for p in a.plans] if a.plans else default_corpus()
    work = tmp_root() / "no_silent_insert"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    rep = run_corpus(files, work)
    ok = not rep["violations"] and not rep["mutations"]["failed"] and rep["rendered_checked"] > 0 \
        and rep["mutations"]["total"] > 0
    rep.update({"schema": "bo.harness.oci.no_silent_insert/1", "module": MODULE_ID, "generated_at": R.now_iso(),
                "result": "OK" if ok else "REPROVADO",
                "vacuous": rep["rendered_checked"] == 0})
    dest = a.report or module_data() / "no_silent_insert.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    m = rep["mutations"]
    print(f"[{rep['generated_at']}] no_silent_insert: {len(files)} arquivo(s), situação {rep['status_counts']}, "
          f"{rep['rendered_checked']} plano(s) conferido(s) contra o HCL, {len(rep['violations'])} violação(ões); "
          f"mutações {m['as_expected']}/{m['total']} como esperado -> {rep['result']}")
    for x in rep["violations"][:20] + m["failed"][:20]:
        print("  " + x)
    if rep["rendered_checked"] == 0:
        print("  nenhum plano renderizado: o gate não passa por vacuidade")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
