"""Gate: python -I -m bo.briefs.lint [--dir DIR]   # higiene (lexical) + reexecução dos exemplos citados

Por brief: cita os três campos, a direção SKOS com exemplo (uma linha broadMatch que o código aceita e a volta
narrowMatch), UNPROVEN, a separação de papéis com a auditoria átomo→conceito, a escada de evidência, a lista de
proibidos, a lista de leitura IGUAL à de briefs/read_allowlists.json, os despachantes e o pacote próprio, o campo
de proveniência e as exigências do papel; não cita nenhum caminho de avaliação; os exemplos (linhas 'EX|') não
usam vocabulário real de nuvem; e cada exemplo C09 tem, na linha 'EX=' seguinte, o veredito que o
bo.semantics devolve hoje. A parte lexical é higiene (N6): passar não prova que o brief está certo.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

from . import common, content
from . import examples as E


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _has(pattern: str, raw: str, flat: str) -> bool:
    if pattern.startswith("^"):
        return re.search(pattern, raw, re.M) is not None
    return re.search(pattern, flat) is not None


def _vocab_hits(line: str) -> list[str]:
    low = line.lower()
    return [w for w in content.REAL_VOCAB if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low)]


def lint_brief(role: str, text: str, allow: dict) -> list[str]:
    probs = []
    flat = _norm(text)
    reqs = dict(content.COMMON_REQUIRED)
    reqs.update(content.ROLE_REQUIRED[role])
    for what, pats in reqs.items():
        miss = [p for p in pats if not _has(p, text, flat)]
        if miss:
            probs.append(f"falta '{what}': {miss}")
    for p in content.EVAL_PATH_PATTERNS:
        for m in re.finditer(p, text):
            ln = text.count("\n", 0, m.start()) + 1
            probs.append(f"caminho de avaliação citado na linha {ln}: '{m.group(0)}'")
    if re.search(r"\{\{[A-Z_]+(:[A-Z_0-9]+)?\}\}", text):
        probs.append("marcador de modelo não resolvido")
    if f"Versão {common.BRIEF_VERSION}" not in text:
        probs.append(f"cabeçalho sem a versão {common.BRIEF_VERSION}")
    # lista de leitura: exatamente a do read_allowlists.json, na mesma ordem
    m = re.search(r"^O QUE VOCÊ PODE LER[^\n]*\n((?:  \S[^\n]*\n)+)", text, re.M)
    listed = [ln.split()[0] for ln in m.group(1).splitlines()] if m else []
    want = (allow.get("roles", {}).get(role) or {}).get("read", [])
    if listed != want:
        probs.append(f"lista de leitura do texto difere de read_allowlists.json ({len(listed)} × {len(want)})")
    # proibidos: as duas partes, com itens
    pm = re.search(r"^PROIBIDO\n(.*?)\n\n", text, re.M | re.S)
    if not pm:
        probs.append("seção PROIBIDO ausente")
    else:
        block = pm.group(1)
        role_part = block.split("Do seu papel:", 1)
        n_common = len(re.findall(r"^- ", role_part[0], re.M))
        n_role = len(re.findall(r"^- ", role_part[1], re.M)) if len(role_part) == 2 else 0
        if n_common < 8 or n_role < 3:
            probs.append(f"lista de proibidos curta: {n_common} comuns, {n_role} do papel")
    # exemplos
    lines = text.splitlines()
    n_ex, broad_ok = 0, False
    for i, ln in enumerate(lines):
        if not ln.startswith("  EX| "):
            continue
        n_ex += 1
        try:
            rec = json.loads(ln[6:])
        except ValueError as e:
            probs.append(f"linha {i + 1}: exemplo não é JSON ({e})")
            continue
        hits = _vocab_hits(ln)
        if hits:
            probs.append(f"linha {i + 1}: exemplo usa vocabulário real de nuvem {hits}")
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if not nxt.startswith("  EX= "):
            probs.append(f"linha {i + 1}: exemplo sem a linha EX= do resultado")
            continue
        if "semantic_relation" in rec:
            if "group" in rec:
                got = E.group_check(rec)["verdict"]
                if f"grupo: veredito {got} " not in nxt:
                    probs.append(f"linha {i + 2}: veredito do grupo declarado difere do calculado ({got})")
                continue
            got = E.assess(rec)
            want_v = re.match(r"  EX= veredito (\S+)", nxt)
            if not want_v or want_v.group(1) != got["verdict"]:
                probs.append(f"linha {i + 2}: veredito declarado {want_v.group(1) if want_v else '?'} ≠ "
                             f"calculado {got['verdict']} {got['rules']}")
            for r in got["rules"]:
                if r not in nxt:
                    probs.append(f"linha {i + 2}: regra {r} que falha não está declarada")
            if rec.get("predicate_id") == "skos:broadMatch" and got["verdict"] == "OK":
                inv = E.inverse_of(copy.deepcopy(rec))
                if f"{inv['subject_id']} skos:narrowMatch {inv['object_id']}" in text:
                    broad_ok = True
    if n_ex == 0:
        probs.append("nenhum exemplo (EX|)")
    if not broad_ok:
        probs.append("direção SKOS sem exemplo: falta uma linha broadMatch aceita com a volta narrowMatch escrita")
    return probs


def lint_dir(d: Path) -> dict:
    out = {"briefs": {}, "problems": []}
    ap = d / "read_allowlists.json"
    try:
        allow = json.loads(ap.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        out["problems"].append(f"read_allowlists.json ilegível: {e}")
        allow = {}
    for role, fname in common.BRIEF_FILES.items():
        p = d / fname
        if not p.is_file():
            out["problems"].append(f"{fname}: ausente")
            continue
        probs = lint_brief(role, p.read_text(encoding="utf-8"), allow)
        out["briefs"][fname] = {"role": role, "problems": probs, "lines": p.read_text(encoding="utf-8").count("\n")}
        out["problems"] += [f"{fname}: {x}" for x in probs]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.briefs.lint")
    ap.add_argument("--dir", default=None, help="pasta dos briefs (padrão: $BO_REPO/briefs)")
    a = ap.parse_args(argv)
    d = Path(a.dir) if a.dir else common.briefs_dir()
    res = lint_dir(d)
    for f, r in res["briefs"].items():
        common.emit(f"  {'OK  ' if not r['problems'] else 'FAIL'} {f} ({r['role']}, {r['lines']} linhas)")
    for p in res["problems"]:
        common.emit(f"    - {p}")
    ok = not res["problems"] and len(res["briefs"]) == len(common.BRIEF_FILES)
    if a.dir is None:
        common.write_report("lint_report", {"gate": "bo.briefs.lint", "label": "higiene", "ok": ok, **res})
    common.emit(f"[{common.now()}] bo.briefs.lint (higiene): {len(res['briefs'])} brief(s), "
                f"{len(res['problems'])} problema(s) -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
