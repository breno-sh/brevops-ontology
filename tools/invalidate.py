#!/usr/bin/env python3
"""Invalidação automática: artefato congelado que mudou deixa STALE todo dependente transitivo.

  invalidate.py check [--apply]          confere todos os comprovantes; --apply grava modules/state.json
  invalidate.py mark CAMINHO [--apply]   marca os dependentes de um artefato mudado (sem comprovante)
  invalidate.py clear ID --reason T      volta um módulo refeito para CURRENT
  invalidate.py status                   lista STALE/ABANDONED e congelamentos BROKEN
  invalidate.py --selftest               mudar artefato congelado marca STALE todo dependente transitivo

Dependentes de um artefato X = módulos cujas entradas cobrem X (e os consumidores do catálogo),
mais o fecho reverso das deps deles. O produtor não vira STALE (é a causa); o congelamento
vira BROKEN. Saída 3 quando há divergência.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import subprocess  # noqa: E402

from bo.repo import catalog, core, fixtures, receipts, state  # noqa: E402

TOOLS = Path(__file__).resolve().parent


def run_tool(name, *args):
    r = subprocess.run([sys.executable, "-I", str(TOOLS / name), *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def selftest() -> int:
    ck = fixtures.Checks("invalidate.py --selftest")
    mods = [
        fixtures.module("A", outputs=["$BO_DATA/A/a.txt", "$BO_DATA/A/a2.txt"]),
        fixtures.module("B", deps=["A"], inputs=["$BO_DATA/A/a.txt"], outputs=["$BO_DATA/B/b.txt"]),
        fixtures.module("C", deps=["B"], inputs=["$BO_DATA/B/b.txt"], outputs=["$BO_DATA/C/c.txt"]),
        fixtures.module("G", deps=["C"], inputs=["$BO_DATA/C/c.txt"]),
        fixtures.module("D", deps=["A"], inputs=["$BO_DATA/A/"]),
        fixtures.module("E", deps=["A"], inputs=["$BO_DATA/A/a2.txt"]),
        fixtures.module("F"),
    ]
    with fixtures.sandbox(mods) as root:
        repo, data = root / "repo", root / "data"
        for mid, f, txt in (("A", "a.txt", "a"), ("A", "a2.txt", "a2"), ("B", "b.txt", "b"), ("C", "c.txt", "c")):
            (data / mid).mkdir(exist_ok=True)
            (data / mid / f).write_text(txt + "\n", encoding="utf-8")
        for mid in "ABCDEFG":
            fixtures.commit_files(repo, f"[{mid}] entrega {mid.lower()}", {})
        rc, _ = run_tool("freeze.py", "create", "F0", "--paths", "$BO_DATA/A/a.txt", "--no-ots", "--no-tag")
        ck.expect("congelamento F0 criado", rc == 0)
        rc, out = run_tool("invalidate.py", "check")
        ck.expect("sem mudança, check sai 0", rc == 0, out[-200:])
        rc, out = run_tool("consume_check.py", "G")
        ck.expect("antes da mudança o consume_check de G passa", rc == 0, out[-300:])
        (data / "A" / "a.txt").write_text("a mudado depois do congelamento\n", encoding="utf-8")
        rc, out = run_tool("invalidate.py", "check")
        ck.expect("check sem --apply acusa (saída 3) e não grava", rc == 3 and
                  state.status_of(state.load(repo), "B") == "CURRENT", out[-200:])
        rc, out = run_tool("invalidate.py", "check", "--apply")
        st = state.load(repo)
        stat = {m: state.status_of(st, m) for m in "ABCDEFG"}
        ck.expect("check --apply sai 3", rc == 3)
        ck.expect("consumidor direto B fica STALE", stat["B"] == "STALE", str(stat))
        ck.expect("consumidor por diretório D fica STALE", stat["D"] == "STALE", str(stat))
        ck.expect("dependentes transitivos C e G ficam STALE", stat["C"] == "STALE" and stat["G"] == "STALE",
                  str(stat))
        ck.expect("E (consome outro arquivo de A) continua CURRENT", stat["E"] == "CURRENT", str(stat))
        ck.expect("F (sem relação) continua CURRENT", stat["F"] == "CURRENT", str(stat))
        ck.expect("produtor A não vira STALE", stat["A"] == "CURRENT", str(stat))
        ck.expect("congelamento F0 marcado BROKEN", st["freezes"].get("F0", {}).get("status") == "BROKEN")
        ck.expect("cada STALE guarda a origem", "F0:$BO_DATA/A/a.txt" in (st["modules"]["G"].get("source") or ""))
        rc, out = run_tool("consume_check.py", "G")
        ck.expect("consume_check de G reprova por STALE", rc != 0 and "FAIL estado: STALE" in out, out[-300:])
        rc, _ = run_tool("invalidate.py", "clear", "B", "--reason", "refeito no teste")
        ck.expect("clear volta B para CURRENT", rc == 0 and state.status_of(state.load(repo), "B") == "CURRENT")
        rc, out = run_tool("invalidate.py", "mark", "$BO_DATA/A/a2.txt", "--apply")
        ck.expect("mark manual de a2 deixa E STALE", state.status_of(state.load(repo), "E") == "STALE", out[-200:])
    return ck.report()


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    ap = argparse.ArgumentParser(prog="invalidate.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--apply", action="store_true")
    m = sub.add_parser("mark")
    m.add_argument("path")
    m.add_argument("--apply", action="store_true")
    m.add_argument("--reason", default="artefato mudou")
    cl = sub.add_parser("clear")
    cl.add_argument("module")
    cl.add_argument("--reason", required=True)
    sub.add_parser("status")
    a = ap.parse_args()
    repo = core.bo_repo()
    cat = catalog.load(repo)
    if a.cmd == "check":
        scan = receipts.invalidate_scan(cat, repo)
        broken = [r["name"] for r in scan["receipts"] if r["problems"]]
        core.emit(f"[{scan['at']}] {len(scan['receipts'])} comprovante(s); {len(broken)} com divergência")
        for r in scan["receipts"]:
            for p in r["problems"]:
                core.emit(f"  {r['name']}: {p['path']} ({p['problem']})")
        for mid, srcs in sorted(scan["stale"].items()):
            core.emit(f"  STALE {mid} <- {', '.join(sorted(set(srcs)))}")
        if broken and a.apply:
            ch = receipts.apply_stale(cat, repo, scan["stale"], broken, "artefato congelado mudou")
            core.emit(f"  gravado em {state.path(repo)}: {len(ch)} módulo(s) passaram a STALE")
        elif broken:
            core.emit("  (simulação; use --apply para gravar)")
        return 3 if broken else 0
    if a.cmd == "mark":
        p = str(receipts.resolve(a.path, repo)) if a.path.startswith("$BO_") else str(Path(a.path).resolve())
        deps = receipts.dependents_of(cat, p)
        src = receipts.portable(p, repo)
        for d in sorted(deps):
            core.emit(f"  STALE {d} <- {src}")
        if a.apply:
            ch = receipts.apply_stale(cat, repo, {d: [src] for d in deps}, [], a.reason)
            core.emit(f"  gravado: {len(ch)} módulo(s) passaram a STALE")
        return 3 if deps else 0
    if a.cmd == "clear":
        cat.get(a.module, allow_synthetic=False)
        s = state.load(repo, cat)
        state.mark(s, a.module, "CURRENT", a.reason)
        state.save(s, repo)
        core.emit(f"{a.module}: CURRENT ({a.reason})")
        return 0
    if a.cmd == "status":
        s = state.load(repo, cat)
        n = 0
        for mid, v in sorted(s["modules"].items()):
            if v.get("status") != "CURRENT":
                n += 1
                core.emit(f"  {v['status']:<9} {mid}: {v.get('reason', '')} {v.get('source', '')}")
        for f, v in sorted(s["freezes"].items()):
            core.emit(f"  freeze {f}: {v.get('status')}")
        core.emit(f"{n} módulo(s) fora de CURRENT")
        return 0
    return 2


if __name__ == "__main__":
    core.run_main(main)
