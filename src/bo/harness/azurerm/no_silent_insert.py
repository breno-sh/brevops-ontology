"""Gate: HCL renderizado = plano + valores sintetizados declarados (nada inserido em silêncio, nada perdido).

  python -I -m bo.harness.azurerm.no_silent_insert [PLANO.jsonl ...] [--out DIR]

Sem argumentos, usa os planos de referência (deploy/fixtures/azurerm/_templates/reference/) e o stub do C26.
Para cada arquivo: renderiza em $BO_TMP/no_silent_insert/<n>/ e confere cada módulo gerado com um leitor
INDEPENDENTE do escritor (python-hcl2 lê o HCL; o esperado sai do plano e do schema, não do manifesto):
  - blocos de topo: só terraform, provider, variable, resource, data; um resource/data por passo do plano,
    no endereço esperado; terraform/provider idênticos ao declarado em TEMPLATES.json;
  - variáveis: só as entradas que o próprio plano exige (símbolo de nome derivado, segredo withheld), com
    type = string e sensitive só no segredo;
  - folhas de cada recurso: cada folha vem de um valor do plano, do nome derivado, do depends_on do plano ou
    de uma tag de propriedade declarada; e cada valor do plano aparece (nada some);
  - meta-argumentos proibidos (count, for_each, lifecycle, provisioner, connection, dynamic, provider);
  - plano bloqueado ou inválido não gera nenhum .tf.
Antes de aceitar, roda o próprio verificador contra mutantes (atributo extra, valor trocado, valor removido,
recurso extra, atributo extra no provider, variável extra, tag não declarada): todo mutante tem de ser pego,
senão o gate reprova (o verificador não passa por vacuidade). Exige ao menos um módulo renderizado.
Relatório: $BO_DATA/HARNESS-AZURE/no_silent_insert.json. Saída 0 = tudo confere.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import hcl2

from . import render as R
from . import schema as S
from ._common import HarnessError, data_dir, dumps, now, portable, read_jsonl, repo, templates_dir, tmp_dir

FORBIDDEN_META = {"count", "for_each", "lifecycle", "provisioner", "connection", "dynamic", "provider"}
TOP_ALLOWED = {"terraform", "provider", "variable", "resource", "data"}


# ------------------------------------------------------------------------------------------------ leitura (hcl2)
def _unq(s: str) -> str:
    return s[1:-1] if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else s


def _unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            m = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
            if n in m:
                out.append(m[n])
                i += 2
                continue
            if n == "u":
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
        if c in "$%" and s[i + 1:i + 3] == c + "{":
            out.append(c + "{")
            i += 3
            continue
        out.append(c)
        i += 1
    return "".join(out)


def norm_actual(v):
    """Valor do python-hcl2 -> forma normal: ('lit', valor) | ('ref', travessia) | ('tmpl', partes) | ('expr', texto)."""
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return ("lit", v)
    if isinstance(v, list):
        return ("list", tuple(norm_actual(x) for x in v))
    if isinstance(v, dict):
        return ("map", tuple(sorted((_unq(k), norm_actual(x)) for k, x in v.items() if k != "__is_block__")))
    if isinstance(v, str):
        if v.startswith("${") and v.endswith("}") and v.count("${") == 1:
            inner = v[2:-1]
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*(\.[A-Za-z_][A-Za-z0-9_\-]*)+", inner):
                return ("ref", inner)
            return ("expr", re.sub(r"\s+", "", inner))
        if v.startswith('"') and v.endswith('"'):
            body = v[1:-1]
            parts, i = [], 0
            for m in re.finditer(r"(?<![$])\$\{([^}]*)\}", body):
                if m.start() > i:
                    parts.append(_unescape(body[i:m.start()]))
                parts.append(("ref", m.group(1)))
                i = m.end()
            if not any(isinstance(p, tuple) for p in parts):
                return ("lit", _unescape(body))
            if i < len(body):
                parts.append(_unescape(body[i:]))
            return ("tmpl", tuple(parts))
        if v in ("true", "false", "null"):
            return ("lit", {"true": True, "false": False, "null": None}[v])
        return ("expr", re.sub(r"\s+", "", v))
    return ("expr", repr(v))


def norm_value(v):
    """Literal JSON do plano -> mesma forma normal."""
    if isinstance(v, list):
        return ("list", tuple(norm_value(x) for x in v))
    if isinstance(v, dict):
        return ("map", tuple(sorted((k, norm_value(x)) for k, x in v.items())))
    if isinstance(v, float) and v.is_integer():
        return ("lit", int(v))
    return ("lit", v)


def leaves(body: dict, prefix: str, out: dict, meta: list):
    for k, v in body.items():
        if k == "__is_block__":
            continue
        if k in FORBIDDEN_META:
            meta.append(prefix + k)
        if isinstance(v, list) and v and all(isinstance(x, dict) and x.get("__is_block__") for x in v):
            for i, inst in enumerate(v):
                leaves(inst, f"{prefix}{k}[{i}].", out, meta)
        else:
            out[prefix + k] = norm_actual(v)


# ------------------------------------------------------------------------------------------------ esperado (plano)
class Expect:
    def __init__(self, plan: dict, graph: dict | None, sch: S.Schema, tmpl: dict, tags: dict):
        self.plan, self.sch, self.tmpl, self.tags = plan, sch, tmpl, tags
        self.terms = {t["term_id"]: t["term"] for t in (graph or {}).get("terms", [])}
        self.by_order = {s["order"]: s for s in plan["steps"]}
        self.labels = R._labels(plan["steps"])  # rótulo = node_id (desambiguado pela ordem): convenção do C26
        self.vars: dict[str, bool] = {}

    def addr(self, s):
        a = f"{s['resource_type']}.{self.labels[s['order']]}"
        return "data." + a if s["action"] == "reference" else a

    def term(self, s, t):
        k = t["kind"]
        if k == "literal":
            return norm_value(t["value"])
        if k == "reference":
            want_data = t["target_address"].startswith("data.")
            c = [self.by_order[d] for d in s["depends_on"] if self.by_order[d]["resource_type"] == t["target_type"]
                 and (self.by_order[d]["action"] == "reference") == want_data]
            return ("ref", self.addr(c[0]) + ("." + t["attribute"] if t.get("attribute") else ""))
        if k == "withheld":
            return ("withheld", None)
        if k == "expression":
            return ("expression", t["op"])
        if k == "document":
            return ("document", "yamlencode" if t["format"] == "yaml" else "jsonencode")
        raise HarnessError(f"termo {k} não esperado num plano renderizado")

    def path(self, kind, s, field):
        """Caminho de folha no HCL para um campo pontuado do plano (blocos ganham [0])."""
        node = self.sch.node(kind, s["resource_type"])
        segs, out = field.split("."), []
        for i, seg in enumerate(segs):
            b = S.blocks(node)
            if seg in b and i < len(segs) - 1:
                out.append(f"{seg}[0]")
                node = b[seg].node
            elif seg in b:
                return ".".join(out + [seg]), "block"
            else:
                return ".".join(out + [seg]), ("attr" if i == len(segs) - 1 else "objattr")
        raise HarnessError(f"campo vazio: {field!r}")

    def step_leaves(self, s) -> dict:
        kind = "data" if s["action"] == "reference" else "resource"
        exp: dict = {}
        if s.get("derived_name"):
            parts, toks = [], re.split(r"(\{t[0-9]+\})", s["derived_name"]["template"])
            for tk in toks:
                m = re.fullmatch(r"\{(t[0-9]+)\}", tk)
                if not tk:
                    continue
                if not m:
                    parts.append(tk)
                    continue
                t = self.terms[m.group(1)]
                if t["kind"] == "symbol":
                    v = "sym_" + t["symbol_id"].split("-", 1)[1].lower()
                    self.vars[v] = False
                    parts.append(("ref", "var." + v))
                else:
                    parts.append(str(t["value"]))
            merged = []
            for p in parts:
                if merged and isinstance(p, str) and isinstance(merged[-1], str):
                    merged[-1] += p
                else:
                    merged.append(p)
            exp["name"] = ("lit", merged[0]) if len(merged) == 1 and isinstance(merged[0], str) else ("tmpl", tuple(merged))
        for v in s["values"]:
            p, where = self.path(kind, s, v["field"])
            t = self.term(s, v["term"])
            if t[0] == "withheld":
                var = f"secret_{self.labels[s['order']]}_{v['field'].replace('.', '_')}"
                self.vars[var] = True
                t = ("ref", "var." + var)
            if where == "block":
                raw = v["term"]["value"]
                for i, inst in enumerate(raw if isinstance(raw, list) else [raw]):
                    self._block_leaves(f"{p}[{i}].", inst, kind, s, exp)
            elif where == "objattr":
                n_before = p.count(".") + 1  # segmentos do campo até o atributo-objeto (inclusive)
                sub = v["field"].split(".")[n_before:]
                exp.setdefault(("__obj__", p), []).append((sub, t))
            else:
                exp[p] = t
        if self.tags and kind == "resource":
            a = S.attrs(self.sch.node(kind, s["resource_type"]))
            if "tags" in a and a["tags"].configurable:
                base = dict(exp.get("tags", ("map", ()))[1]) if exp.get("tags", ("", None))[0] == "map" else None
                if "tags" not in exp:
                    exp["tags"] = norm_value(dict(self.tags))
                elif base is not None:
                    for k2, v2 in self.tags.items():
                        base.setdefault(k2, ("lit", v2))
                    exp["tags"] = ("map", tuple(sorted(base.items())))
        if s["depends_on"]:
            exp["depends_on"] = ("list", tuple(("ref", self.addr(self.by_order[d])) for d in s["depends_on"]))
        return exp

    def _block_leaves(self, prefix, inst, kind, s, exp):
        for k, v in inst.items():
            if isinstance(v, dict) or (isinstance(v, list) and v and all(isinstance(x, dict) for x in v)):
                # bloco aninhado só se o schema disser; atributo-mapa fica inteiro
                exp_is_block = True
                try:
                    node = self.sch.node(kind, s["resource_type"])
                    for seg in re.sub(r"\[[0-9]+\]", "", prefix.rstrip(".")).split(".") + [k]:
                        b = S.blocks(node)
                        if seg in b:
                            node = b[seg].node
                        else:
                            exp_is_block = False
                            break
                except KeyError:
                    exp_is_block = False
                if exp_is_block:
                    for i, x in enumerate(v if isinstance(v, list) else [v]):
                        self._block_leaves(f"{prefix}{k}[{i}].", x, kind, s, exp)
                    continue
            exp[prefix + k] = norm_value(v)


def _obj_leaves(v, prefix="") -> dict:
    """Objeto normalizado ('map', ((chave, valor), ...)) -> {caminho pontuado: folha}."""
    out = {}
    if v[0] == "map":
        for k, x in v[1]:
            if x[0] == "map":
                out.update(_obj_leaves(x, f"{prefix}{k}."))
            else:
                out[prefix + k] = x
    return out


def _match(actual, expected) -> bool:
    if expected[0] in ("expression", "document"):
        return actual[0] == "expr" and expected[1] in actual[1]
    return actual == expected


def check_module(d: Path, plan: dict, graph: dict | None, sch: S.Schema, tmpl: dict, tags: dict) -> list[str]:
    errs: list[str] = []
    tfs = sorted(p.name for p in d.glob("*.tf"))
    if tfs != ["main.tf", "versions.tf"]:
        errs.append(f"arquivos .tf inesperados: {tfs}")
    if (d / "versions.tf").read_bytes() != (templates_dir() / "versions.tf").read_bytes():
        errs.append("versions.tf difere do template declarado")
    doc: dict = {}
    for f in tfs:
        try:
            parsed = hcl2.loads((d / f).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001  (qualquer falha do leitor reprova)
            return [f"{f}: python-hcl2 não leu: {type(e).__name__}: {str(e)[:200]}"]
        for k, v in parsed.items():
            doc.setdefault(k, []).extend(v)
    for k in doc:
        if k not in TOP_ALLOWED:
            errs.append(f"bloco de topo não permitido: {k}")
    # terraform/provider = boilerplate declarado
    decl = {b["path"]: b["value"] for b in tmpl["declared_boilerplate"]}
    got: dict = {}
    meta: list = []
    for blk in doc.get("terraform", []):
        leaves(blk, "terraform.", got, meta)
    for blk in doc.get("provider", []):
        for name, body in blk.items():
            leaves(body, f"provider.{_unq(name)}.", got, meta)
    want = {}
    for p, v in decl.items():
        if p.startswith("terraform.required_providers."):
            continue
        want[p if not p.endswith(".features") else p + "[0]"] = norm_value(v) if v != {} else None
    rp = {}
    for p, v in decl.items():
        if p.startswith("terraform.required_providers."):
            _, _, prov, key = p.split(".")
            rp.setdefault(prov, {})[key] = v
    for prov, kv in rp.items():
        want[f"terraform.required_providers[0].{prov}"] = norm_value(kv)
    for p in sorted(set(got) | set(want)):
        if p.endswith(".features[0]") or p.endswith(".features"):
            continue
        if p not in want:
            errs.append(f"terraform/provider: folha não declarada {p}")
        elif p not in got:
            errs.append(f"terraform/provider: folha declarada ausente {p}")
        elif want[p] is not None and got[p] != want[p]:
            errs.append(f"terraform/provider: {p} = {got[p]} ≠ declarado {want[p]}")
    prov_blocks = [_unq(n) for blk in doc.get("provider", []) for n in blk]
    if prov_blocks != ["azurerm"]:
        errs.append(f"blocos provider {prov_blocks} ≠ ['azurerm']")
    feats = [body for blk in doc.get("provider", []) for body in blk.values()]
    if not feats or "features" not in feats[0]:
        errs.append("provider azurerm sem o bloco features declarado")
    # recursos
    ex = Expect(plan, graph, sch, tmpl, tags)
    seen = set()
    want_addr = {ex.addr(s): s for s in plan["steps"]}
    for top in ("resource", "data"):
        for blk in doc.get(top, []):
            for rtype, named in blk.items():
                for label, body in named.items():
                    a = ("data." if top == "data" else "") + f"{_unq(rtype)}.{_unq(label)}"
                    if a in seen:
                        errs.append(f"endereço repetido {a}")
                    seen.add(a)
                    s = want_addr.get(a)
                    if s is None:
                        errs.append(f"{top} sem passo no plano: {a}")
                        continue
                    act: dict = {}
                    meta = []
                    leaves(body, "", act, meta)
                    for m in meta:
                        errs.append(f"{a}: meta-argumento proibido {m}")
                    exp = ex.step_leaves(s)
                    objs = {k[1]: v for k, v in exp.items() if isinstance(k, tuple)}
                    exp = {k: v for k, v in exp.items() if not isinstance(k, tuple)}
                    for p in sorted(set(act) | set(exp)):
                        if p in objs:
                            continue
                        if p not in exp:
                            errs.append(f"{a}: folha inserida sem origem no plano: {p} = {act[p]}")
                        elif p not in act:
                            errs.append(f"{a}: valor do plano sumiu do HCL: {p}")
                        elif not _match(act[p], exp[p]):
                            errs.append(f"{a}: {p} = {act[p]} ≠ plano {exp[p]}")
                    for p, subs in objs.items():
                        if p not in act:
                            errs.append(f"{a}: valor do plano sumiu do HCL: {p}")
                            continue
                        got_obj = _obj_leaves(act[p])
                        want_obj = {".".join(k): t for k, t in subs}
                        for k in sorted(set(got_obj) | set(want_obj)):
                            if k not in want_obj:
                                errs.append(f"{a}: folha inserida sem origem no plano: {p}.{k}")
                            elif k not in got_obj:
                                errs.append(f"{a}: valor do plano sumiu do HCL: {p}.{k}")
                            elif not _match(got_obj[k], want_obj[k]):
                                errs.append(f"{a}: {p}.{k} = {got_obj[k]} ≠ plano {want_obj[k]}")
    for a in sorted(set(want_addr) - seen):
        errs.append(f"passo do plano sem bloco no HCL: {a}")
    # variáveis
    got_vars = {}
    for blk in doc.get("variable", []):
        for name, body in blk.items():
            got_vars[_unq(name)] = {k: v for k, v in body.items() if k != "__is_block__"}
    for v in sorted(set(got_vars) | set(ex.vars)):
        if v not in ex.vars:
            errs.append(f"variável sem entrada declarada pelo plano: {v}")
        elif v not in got_vars:
            errs.append(f"entrada exigida pelo plano sem variável: {v}")
        else:
            want_v = {"type": "${string}"} if not ex.vars[v] else {"type": "${string}", "sensitive": True}
            gv = dict(got_vars[v])
            if gv.get("type") in ("string", "${string}"):
                gv["type"] = "${string}"
            if gv != want_v:
                errs.append(f"variável {v}: {gv} ≠ declarado {want_v}")
    return errs


# ------------------------------------------------------------------------------------------------ mutantes
def mutants(main_tf: str) -> list[tuple[str, str]]:
    out = []
    m = re.search(r'(resource "[^"]+" "[^"]+" \{\n)', main_tf)
    if m:
        out.append(("atributo extra", main_tf[:m.end()] + '  public_network_access_enabled = false\n' + main_tf[m.end():]))
        out.append(("tag não declarada", main_tf[:m.end()] + '  tags = {\n    bo-x = "y"\n  }\n' + main_tf[m.end():]))
    m2 = re.search(r'= "([^"$]+)"\n', main_tf)
    if m2:
        out.append(("valor trocado", main_tf[:m2.start()] + '= "' + m2.group(1) + 'x"\n' + main_tf[m2.end():]))
    lines = main_tf.split("\n")
    idx = [i for i, ln in enumerate(lines) if re.match(r'^  [a-z_]+ += "', ln)]
    if idx:
        out.append(("valor removido", "\n".join(lines[:idx[0]] + lines[idx[0] + 1:])))
    out.append(("recurso extra", main_tf + '\nresource "azurerm_resource_group" "zz" {\n  location = "x"\n  name     = "y"\n}\n'))
    out.append(("variável extra", main_tf + '\nvariable "extra" {\n  type = string\n}\n'))
    out.append(("meta-argumento", main_tf.replace("\n}\n", "\n\n  lifecycle {\n    prevent_destroy = true\n  }\n}\n", 1)))
    return out


def provider_mutant(versions_tf: str) -> str:
    return versions_tf.replace("  features {}\n", "  features {}\n  resource_provider_registrations = \"none\"\n")


# ------------------------------------------------------------------------------------------------ execução
def run(plan_files: list[Path], work: Path) -> dict:
    sch, tmpl = S.load(), S.templates_manifest()
    rep = {"schema": "bo.harness_azurerm.no_silent_insert/1", "module": "HARNESS-AZURE", "started_at": now(),
           "files": [], "modules_checked": 0, "mutants": 0, "mutants_caught": 0, "errors": []}
    if work.exists():
        shutil.rmtree(work)
    for n, pf in enumerate(plan_files, 1):
        out = work / f"in{n}"
        frec = {"plan_file": portable(pf), "plans": []}
        try:
            r = R.render_file(pf, out)
        except HarnessError as e:
            rep["errors"].append(f"{portable(pf)}: {e}")
            rep["files"].append(frec)
            continue
        graphs = R.load_graphs(pf, None)
        plans = {p["plan_id"]: p for p in read_jsonl(pf)}
        for row in r["plans"]:
            pr = {"plan_id": row["plan_id"], "status": row["status"], "errors": []}
            if row["status"] != "RENDERED":
                stray = [p for p in out.rglob("*.tf") if row["plan_id"] in str(p)] if r["layout"] == "per_plan" \
                    else [p for p in out.glob("*.tf")] if not any(x["status"] == "RENDERED" for x in r["plans"]) \
                    else []
                if stray:
                    pr["errors"].append(f"plano {row['status']} gerou HCL: {[portable(p) for p in stray]}")
                frec["plans"].append(pr)
                continue
            d = out if r["layout"] == "single" else out / row["plan_id"]
            plan = plans[row["plan_id"]]
            g = graphs.get(plan["graph_id"])
            pr["errors"] = check_module(d, plan, g, sch, tmpl, {})
            rep["modules_checked"] += 1
            # mutantes: cada um tem de ser pego
            main_tf = (d / "main.tf").read_text(encoding="utf-8")
            mdir = work / "mut"
            for name, text in mutants(main_tf) + [("provider extra", None)]:
                if mdir.exists():
                    shutil.rmtree(mdir)
                shutil.copytree(d, mdir)
                if text is None:
                    (mdir / "versions.tf").write_text(provider_mutant((d / "versions.tf").read_text()), "utf-8")
                else:
                    (mdir / "main.tf").write_text(text, encoding="utf-8")
                rep["mutants"] += 1
                if check_module(mdir, plan, g, sch, tmpl, {}):
                    rep["mutants_caught"] += 1
                else:
                    pr["errors"].append(f"mutante não pego: {name}")
            shutil.rmtree(mdir, ignore_errors=True)
            frec["plans"].append(pr)
        for p in frec["plans"]:
            rep["errors"] += [f"{p['plan_id']}: {e}" for e in p["errors"]]
        rep["files"].append(frec)
    if rep["modules_checked"] == 0:
        rep["errors"].append("nenhum módulo renderizado para conferir (o gate não passa por vacuidade)")
    rep["finished_at"] = now()
    rep["ok"] = not rep["errors"]
    return rep


def default_inputs() -> list[Path]:
    return [templates_dir() / "reference" / "lowering_plan.jsonl",
            repo() / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.azurerm.no_silent_insert")
    ap.add_argument("plans", nargs="*")
    ap.add_argument("--report", default=None)
    a = ap.parse_args([x for x in (argv if argv is not None else sys.argv[1:]) if x != "HARNESS-AZURE"])
    files = [Path(p) for p in a.plans] or default_inputs()
    rep = run(files, tmp_dir() / "no_silent_insert")
    rp = Path(a.report) if a.report else data_dir() / "no_silent_insert.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(dumps(rep), encoding="utf-8")
    st = {}
    for f in rep["files"]:
        for p in f["plans"]:
            st[p["status"]] = st.get(p["status"], 0) + 1
    print(f"[{rep['finished_at']}] no_silent_insert: {rep['modules_checked']} módulo(s) conferido(s); planos "
          + ", ".join(f"{k}={v}" for k, v in sorted(st.items()))
          + f"; mutantes pegos {rep['mutants_caught']}/{rep['mutants']}; relatório {portable(rp)}")
    for e in rep["errors"]:
        print("  ERRO " + e)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
