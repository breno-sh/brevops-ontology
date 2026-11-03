"""python -I -m bo.gold_libcloud.resolve [GOLD-LIBCLOUD] [--sssom ARQ] [--registry ARQ] [--coverage ARQ]

Gate G2 do GOLD-LIBCLOUD (no catálogo: python -I -m bo.gold_libcloud.resolve GOLD-LIBCLOUD): todo campo
resolve num campo de API registrado ou é marcado UNRESOLVED. Confere de novo, contra a fonte baixada
(sem reaproveitar o interpretador da extração):
  S1 a fonte é a fixada (sha256 do tar.gz e árvore extraída igual ao tar.gz);
  S2 todo object_id é campo normalizado de libcloud/<domínio>/base.py (relido com ast);
  S3 toda linha resolvida tem sujeito no registro api_fields.jsonl, o registro liga o sujeito ao mesmo
     object_id, e em algum sítio arquivo:linha do registro o último segmento do caminho aparece num literal
     de string do código (até 3 linhas em volta);
  S4 linha UNRESOLVED: sujeito '<driver>:<função>/?', related, transport none, sem função de tradução;
  S5 cobertura: toda alimentação 'api' tem linha resolvida com o mesmo object_id no mesmo driver/função, e
     toda alimentação 'opaque' tem linha UNRESOLVED; as demais (input, constant, context, absent) não são
     campo de API e ficam contadas.
Relatório com carimbo em $BO_DATA/GOLD-LIBCLOUD/resolve_report.json. Sai 0 só se tudo confere.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import source as S

MODULE = "GOLD-LIBCLOUD"
WINDOW = 3


def now() -> str:
    return datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def base_fields(pkg: Path) -> dict[str, set]:
    out = {}
    for d in ("compute", "storage", "dns", "loadbalancer"):
        if not (pkg / d / "base.py").is_file():
            raise ValueError(f"{pkg / d / 'base.py'} ausente na fonte")
        t = ast.parse((pkg / d / "base.py").read_text(encoding="utf-8"))
        for n in t.body:
            if isinstance(n, ast.ClassDef):
                init = next((m for m in n.body if isinstance(m, ast.FunctionDef) and m.name == "__init__"), None)
                if init is None:
                    continue
                ps = [a.arg for a in init.args.args][1:]
                if "extra" in ps:
                    out[f"{d}.{n.name}"] = set(ps) - {"driver"}
    return out


class Literals:
    """Literais de string por linha de cada arquivo (todas as linhas que o nó Constant cobre)."""

    def __init__(self, root: Path):
        self.root, self.cache = root, {}

    def lines(self, rel: str) -> dict[int, list[str]]:
        if rel not in self.cache:
            p = self.root / rel
            by = defaultdict(list)
            if p.is_file():
                for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                    if isinstance(n, ast.Constant) and isinstance(n.value, str):
                        for ln in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                            by[ln].append(n.value)
            self.cache[rel] = by if p.is_file() else None
        return self.cache[rel]

    def has_segment(self, rel: str, line: int, seg: str) -> bool:
        by = self.lines(rel)
        if by is None:
            return False
        for ln in range(line - WINDOW, line + WINDOW + 1):
            for s in by.get(ln, []):
                s2 = re.sub(r"\{[^}]*\}", "", s)
                parts = [p.split(":", 1)[-1] for p in s2.strip("/").split("/")]
                if seg == s2 or seg in parts:
                    return True
        return False


def last_segment(path: list) -> str | None:
    for p in reversed(path):
        if p != "*":
            return str(p)
    return None


def check(sssom: Path, registry: Path, coverage: Path) -> dict:
    from bo.contracts import sssom as CS
    fails: list[str] = []
    src = S.verify()                                                   # S1
    pkg = S.pkg_root()
    fields = base_fields(pkg)
    meta, recs, _ = CS.read_tsv(sssom.read_text(encoding="utf-8"))
    reg = {r["subject_id"]: r for r in load_jsonl(registry)}
    cov = load_jsonl(coverage)
    lit = Literals(S.tree_root())
    resolved_by = defaultdict(set)     # (prefixo, classe.função, object_id) com linha resolvida
    unresolved_by = set()
    states = Counter()
    for r in recs:
        cid, subj, obj = r["claim_id"], r["subject_id"], r["object_id"]
        states[r["evidence_state"]] += 1
        o = obj.split(":", 1)[1] if obj.startswith("lcm:") else None    # S2
        tgt, _, fld = (o or "").rpartition(".")
        if o is None or tgt not in fields or fld not in fields[tgt]:
            fails.append(f"S2 {cid}: {obj} não é campo normalizado de base.py")
        prefix, local = subj.split(":", 1)
        func = local.split("/", 1)[0]
        if r["evidence_state"] == "UNRESOLVED":                          # S4
            ok = (local.endswith("/?") and r["semantic_relation"] == "related"
                  and r["transport_fidelity"] == "none" and not r.get("translation_fn"))
            if not ok:
                fails.append(f"S4 {cid}: linha UNRESOLVED mal marcada")
            unresolved_by.add((prefix, func, obj))
            continue
        g = reg.get(subj)                                                # S3
        if g is None:
            fails.append(f"S3 {cid}: sujeito fora do registro de campos de API")
            continue
        if obj not in g["feeds"]:
            fails.append(f"S3 {cid}: registro não liga o sujeito a {obj}")
        seg = last_segment(g["path"])
        if seg is None or not any(lit.has_segment(s["file"], s["line"], seg) for s in g["sites"]):
            fails.append(f"S3 {cid}: segmento {seg!r} não aparece em literal nos sítios do registro")
        resolved_by[(prefix, func)].add(obj)
    counts = Counter(c["feed"] for c in cov)                            # S5
    for c in cov:
        rel, line = c["site"].rsplit(":", 1)
        parts = Path(rel).parts   # libcloud/<domínio>/drivers/<stem>.py
        prefix = f"lcapi.{parts[1]}.{Path(rel).stem}"
        obj = f"lcm:{c['target']}.{c['field']}"
        if c["field"] == "extra":
            continue
        if c["feed"] == "api":
            if not any(obj in objs for (p, _f), objs in resolved_by.items() if p == prefix):
                fails.append(f"S5 {c['site']} {obj}: alimentação de API sem linha resolvida")
        elif c["feed"] == "opaque":
            if not any(p == prefix and o == obj for p, _f, o in unresolved_by):
                fails.append(f"S5 {c['site']} {obj}: alimentação não resolvida sem linha UNRESOLVED")
    return {"module": MODULE, "at": now(), "sssom": str(sssom), "registry": str(registry),
            "coverage": str(coverage), "source_sha256": src["sha256"], "rows": len(recs),
            "rows_by_evidence_state": dict(sorted(states.items())), "registry_fields": len(reg),
            "coverage_by_feed": dict(sorted(counts.items())), "failures": fails, "ok": not fails,
            "checks": ["S1 fonte fixada", "S2 objeto normalizado", "S3 sujeito registrado e literal no sítio",
                       "S4 UNRESOLVED marcado", "S5 cobertura api/opaque"]}


def main(argv=None) -> int:
    d = S.bo_data() / MODULE
    ap = argparse.ArgumentParser(prog="bo.gold_libcloud.resolve")
    ap.add_argument("module", nargs="?", default=MODULE, help="stable_id (só GOLD-LIBCLOUD)")
    ap.add_argument("--sssom", default=str(d / "libcloud.sssom.tsv"))
    ap.add_argument("--registry", default=str(d / "api_fields.jsonl"))
    ap.add_argument("--coverage", default=str(d / "coverage.jsonl"))
    ap.add_argument("--report", default=str(d / "resolve_report.json"))
    a = ap.parse_args(argv)
    if a.module != MODULE:
        print(f"bo.gold_libcloud.resolve: módulo {a.module!r} não é {MODULE}", file=sys.stderr)
        return 2
    try:
        rep = check(Path(a.sssom), Path(a.registry), Path(a.coverage))
    except (S.SourceError, OSError, ValueError) as e:
        print(f"[{now()}] resolve {MODULE}: ERRO {e}", file=sys.stderr)
        return 2
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                  encoding="utf-8")
    for f in rep["failures"][:40]:
        print("  FAIL " + f)
    print(f"[{rep['at']}] resolve {MODULE}: {rep['rows']} linhas ({rep['rows_by_evidence_state']}), "
          f"{rep['registry_fields']} campos de API, cobertura {rep['coverage_by_feed']}, "
          f"{len(rep['failures'])} falha(s) -> {'OK' if rep['ok'] else 'REPROVADO'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
