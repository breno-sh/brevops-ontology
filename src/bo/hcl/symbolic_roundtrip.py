"""Gate: nomes, expressões, CIDRs e documentos voltam do termo simbólico com a mesma estrutura.

  python -I -m bo.hcl.symbolic_roundtrip [--repos N] [--report ARQ]

Amostra determinística de repositórios (os N menores hashes de repo_id entre os emitidos). Para cada um:
  1. regeneração: refaz o repositório do zero e as linhas têm de ser idênticas às de symbolic_config.jsonl;
  2. volta: cada termo (não retido) é renderizado em HCL com a tabela privada em memória, reparseado, e a
     forma normal da AST tem de ser igual à do original; o termo refeito da AST reparseada tem de ser igual;
  3. nomes: endereço, cadeia de módulos e caminho do arquivo revelados dão o texto original;
  4. CIDR: o texto volta igual, prefixo e classe conferem com ipaddress;
  5. documentos: todo SYM- na árvore está em symbolized e todo symbolized aponta para o símbolo;
  6. retido: o termo é só {kind, reason}.
Sai 0 só se não houver nenhuma divergência. A tabela privada nunca é gravada.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys

import numpy as np

from . import classify as C
from . import hclast, source
from .common import out_dir, now, write_json, dumps
from .extract import repo_core
from .render import NotText, Renderer, WithheldTerm


DEBUG = bool(__import__("os").environ.get("BO_HCL_DEBUG"))  # só depuração local em $BO_TMP; nunca no gate

# ------------------------------------------------------------------------------------------------ forma normal
PH = "\ue001I{}\ue001"


def _fold(parts):
    out = []
    for p in parts:
        if p[0] == "i" and p[1][0] == "str" and all(q[0] == "t" for q in p[1][1]):
            p = ("t", "".join(q[1] for q in p[1][1]))
        if p[0] == "t" and out and out[-1][0] == "t":
            out[-1] = ("t", out[-1][1] + p[1])
        elif p[0] != "t" or p[1]:
            out.append(p)
    return tuple(out)


def _nfj(x, ph):
    if isinstance(x, dict):
        return ("jd", tuple((_nfj(k, ph), _nfj(v, ph)) for k, v in x.items()))
    if isinstance(x, list):
        return ("jl", tuple(_nfj(v, ph) for v in x))
    if isinstance(x, str) and ph and any(m in x for m in ph):
        rx = re.compile("|".join(re.escape(m) for m in ph))
        parts, last = [], 0
        for m in rx.finditer(x):
            if m.start() > last:
                parts.append(("t", x[last:m.start()]))
            parts.append(ph[m.group(0)])
            last = m.end()
        if last < len(x):
            parts.append(("t", x[last:]))
        return ("jt", tuple(parts))
    if isinstance(x, bool) or x is None:
        return ("jv", x)
    if isinstance(x, (int, float)):
        return ("jn", x)
    return ("js", x)


def nf(a):
    """Forma normal: cadeias que são JSON viram a árvore JSON; interpolação de cadeia pura vira texto."""
    if not isinstance(a, tuple) or not a:
        return a
    if a[0] == "str":
        parts = _fold(a[1])
        if len(parts) == 1 and parts[0][0] == "i":
            return nf(parts[0][1])
        if all(p[0] == "t" for p in parts):
            s = "".join(p[1] for p in parts)
            if C.looks_json(s):
                try:
                    t = json.loads(s)
                    if isinstance(t, (dict, list)):
                        return ("json", _nfj(t, {}))
                except ValueError:
                    pass
            return ("str", (("t", s),) if s else ())
        if not any(p[0] == "d" for p in parts):
            ph = {PH.format(i): ("i", nf(p[1])) for i, p in enumerate(parts) if p[0] == "i"}
            text = "".join(p[1] if p[0] == "t" else PH.format(i) for i, p in enumerate(parts))
            if C.looks_json(text):
                try:
                    t = json.loads(text)
                    if isinstance(t, (dict, list)):
                        return ("json", _nfj(t, ph))
                except ValueError:
                    pass
        return ("str", tuple(nf_part(p) for p in parts))
    return tuple(nf(x) if isinstance(x, tuple) else x for x in a)


def nf_part(p):
    if p[0] == "t":
        return p
    if p[0] == "i":
        return ("i", nf(p[1]))
    return ("d", p[1], nf(p[2]) if p[2] is not None else None, p[3])


# ------------------------------------------------------------------------------------------------ verificações
def has_withheld(t) -> bool:
    if isinstance(t, dict):
        if t.get("kind") == "withheld":
            return True
        return any(has_withheld(v) for v in t.values())
    if isinstance(t, list):
        return any(has_withheld(v) for v in t)
    return False


def walk_terms(t):
    if isinstance(t, dict):
        if "kind" in t:
            yield t
        for v in t.values():
            yield from walk_terms(v)
    elif isinstance(t, list):
        for v in t:
            yield from walk_terms(v)


def check_doc(t, where, errs):
    multi: dict = {}
    for e in t["symbolized"]:
        multi.setdefault(e["path"], set()).add(e["symbol_id"])

    def get(path):
        x = t["tree"]
        for seg in path.split("/")[1:]:
            seg = seg.replace("~1", "/").replace("~0", "~")
            if isinstance(x, list):
                x = x[int(seg)]
            elif isinstance(x, dict):
                if seg in x:
                    x = x[seg]
                else:
                    return ("KEY", seg)
            else:
                return None
        return x

    for e in t["symbolized"]:
        p, sid = e["path"], e["symbol_id"]
        v = get(p)
        if isinstance(v, dict) and v.get("kind") == "symbol":
            v = v["symbol_id"]
        if isinstance(v, tuple) and v[0] == "KEY":
            v = v[1]
        # valor no caminho, ou chave simbolizada (o caminho termina no próprio símbolo)
        if v != sid and not p.endswith("/" + sid):
            errs.append(f"{where}: symbolized {p} não aponta para {sid}")

    def scan(x, path):
        if isinstance(x, dict):
            if set(x) == {"$term"}:
                return
            if set(x) == {"$key", "$value"}:
                scan(x["$value"], path + "/$value")
                return
            for k, v in x.items():
                kp = path + "/" + k.replace("~", "~0").replace("/", "~1")
                if re.fullmatch(r"SYM-[0-9a-f]{8,16}", k) and k not in multi.get(kp, ()):
                    errs.append(f"{where}: chave {k} sem symbolized")
                scan(v, kp)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                scan(v, f"{path}/{i}")
        elif isinstance(x, str) and re.fullmatch(r"SYM-[0-9a-f]{8,16}", x) and x not in multi.get(path, ()):
            errs.append(f"{where}: {path} = {x} sem symbolized")
    scan(t["tree"], "")


def check_repo(r, lines_file, keep, errs, cnt):
    rid = r["rid"]
    if r["lines"] != lines_file:
        n_diff = sum(1 for a, b in zip(r["lines"], lines_file) if a != b) + abs(len(r["lines"]) - len(lines_file))
        errs.append(f"{rid}: regeneração diverge em {n_diff} linha(s)")
    rev = r["reveal"]
    R = Renderer(rev)
    sz = r["sz"]
    for res in r["trace"]:
        # nomes: endereço, módulos, arquivo
        cnt["names"] += 1
        m = re.search(r"\.(SYM-[0-9a-f]+)$", res["addr"])
        if rev.get(m.group(1)) != ("res", res["label"]):
            errs.append(f"{rid}: endereço não revela o rótulo")
        mods = re.findall(r"module\.(SYM-[0-9a-f]+)\.", res["addr"])
        if [rev.get(x, ("?", "?"))[1] for x in mods] != res["chain"]:
            errs.append(f"{rid}: cadeia de módulos não revela")
        segs = res["frel"].split("/")
        back = []
        for i, sgm in enumerate(segs):
            last = i == len(segs) - 1
            stem, suf = (sgm[:-3], ".tf") if last and sgm.endswith(".tf") else (sgm, "")
            if re.fullmatch(r"SYM-[0-9a-f]+", stem):
                ns, txt = rev[stem]
                back.append(txt + suf)
            else:
                back.append(sgm)
        if "/".join(back) != res["rel"]:
            errs.append(f"{rid}: caminho do arquivo não revela")
        logs = res["log"]
        if len(logs) != len(res["recs"]):
            errs.append(f"{rid}: log de AST e registros com tamanhos diferentes")
            continue
        for (path, term), (lpath, ctx, mode, ast, scope) in zip(res["recs"], logs):
            if path != lpath:
                errs.append(f"{rid}: caminho {path} != {lpath}")
                continue
            if mode == "withheld" or has_withheld(term):
                cnt["withheld"] += 1
                for t in walk_terms(term):
                    if t.get("kind") == "withheld" and set(t) != {"kind", "reason"}:
                        errs.append(f"{rid}: termo retido com campo extra")
                continue
            if mode == "iterator":
                cnt["iterator"] += 1
                continue
            for t in walk_terms(term):
                if t.get("kind") == "document":
                    cnt["documents"] += 1
                    check_doc(t, f"{rid}:{path}", errs)
                if t.get("kind") == "expression" and t.get("op") == "cidr":
                    cnt["cidr"] += 1
                    try:
                        txt = R.to_text(t)
                        a, p = txt.rsplit("/", 1)
                        ad = ipaddress.ip_address(a)
                        want = "any" if int(p) == 0 else C.ip_class(ad)
                        if t["args"][2]["value"] != want or t["args"][1]["value"] != int(p):
                            errs.append(f"{rid}:{path}: classe/prefixo do CIDR não confere")
                    except (ValueError, NotText):
                        errs.append(f"{rid}:{path}: CIDR não volta a texto")
            try:
                text = R.expr(term)
            except (WithheldTerm, NotText, KeyError, ValueError) as e:
                errs.append(f"{rid}:{path}: termo não renderiza ({type(e).__name__})")
                if DEBUG:
                    print("DEBUG render:", type(e).__name__, e, dumps(term)[:400], file=sys.stderr)
                continue
            try:
                back_ast = hclast.parse_expr(text)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{rid}:{path}: HCL renderizado não reparseia ({type(e).__name__})")
                if DEBUG:
                    print("DEBUG reparse:", text[:400], file=sys.stderr)
                continue
            cnt["terms"] += 1
            if nf(back_ast) != nf(ast):
                errs.append(f"{rid}:{path}: estrutura diverge depois da volta")
                if DEBUG:
                    print("DEBUG texto:", text[:600], "\n  orig:", repr(nf(ast))[:600], "\n  volta:",
                          repr(nf(back_ast))[:600], file=sys.stderr)
                continue
            cnt["structure_ok"] += 1
            if mode == "term":
                sz.scope = [dict(fr) for fr in scope]
                t2 = sz.term(back_ast, ctx)
                sz.scope = []
                if t2 != term:
                    cnt["term_diff"] += 1
                    errs.append(f"{rid}:{path}: termo refeito diverge")
                    if DEBUG:
                        print("DEBUG termo:", dumps(term)[:500], "\n  refeito:", dumps(t2)[:500], file=sys.stderr)
                else:
                    cnt["term_ok"] += 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hcl.symbolic_roundtrip")
    ap.add_argument("--repos", type=int, default=400)
    ap.add_argument("--data", default=None)
    ap.add_argument("--report", default=None)
    a = ap.parse_args(argv)
    d = out_dir() if a.data is None else __import__("pathlib").Path(a.data)
    idx = json.load(open(d / "symbolic_config.index.json", encoding="utf-8"))["repos"]
    keep = set(int(x) for x in np.fromfile(d / "vocab_keep.u64", dtype=">u8"))
    lic = json.load(open(d / "licenses.json", encoding="utf-8"))
    emitted = [x["repo_id"] for x in lic["repos"] if x["repo_id"] in idx]
    chosen = set(sorted(emitted, key=lambda r: hashlib.sha256(r.encode()).hexdigest())[:a.repos])
    from .common import repo_id
    errs, cnt = [], {"repos": 0, "names": 0, "terms": 0, "structure_ok": 0, "term_ok": 0, "term_diff": 0,
                     "withheld": 0, "iterator": 0, "documents": 0, "cidr": 0}
    with open(d / "symbolic_config.jsonl", "rb") as fh:
        for tid, data in source.iter_repos():
            rid = repo_id(tid)
            if rid not in chosen:
                continue
            r = repo_core(tid, data, keep, reveal=True)
            s, e, _n = idx[rid]
            fh.seek(s)
            lines = fh.read(e - s).decode("utf-8").splitlines()
            check_repo(r, lines, keep, errs, cnt)
            cnt["repos"] += 1
            if cnt["repos"] >= len(chosen):
                break
    ok = not errs and cnt["repos"] == len(chosen) and cnt["terms"] > 0
    rep = {"at": now(), "sample_repos": len(chosen), "counts": cnt, "n_errors": len(errs),
           "errors": errs[:200], "result": "PASS" if ok else "FAIL"}
    write_json(d / "roundtrip_report.json" if a.report is None else __import__("pathlib").Path(a.report), rep)
    print(f"[{now()}] symbolic_roundtrip: {cnt['repos']} repos, {cnt['terms']} termos, "
          f"{cnt['structure_ok']} estrutura igual, {cnt['term_ok']} termo igual, {cnt['withheld']} retidos, "
          f"{cnt['documents']} documentos, {cnt['cidr']} CIDRs, {cnt['names']} recursos com nomes revelados; "
          f"{len(errs)} divergência(s) -> {'PASS' if ok else 'FAIL'}")
    for x in errs[:15]:
        print("  " + x)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
