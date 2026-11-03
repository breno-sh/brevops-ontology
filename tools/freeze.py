#!/usr/bin/env python3
"""Comprovante de congelamento (C17 freeze_receipt.json).

  freeze.py create NOME --paths P [P ...] [--owner coordenador] [--out ARQ] [--no-tag] [--no-ots] [--note T]
  freeze.py verify [NOME ...]          confere comprovantes (todos, sem nome)
  freeze.py stamp NOME                 tenta de novo o carimbo OpenTimestamps
  freeze.py --selftest                 adulterar entrada depois do comprovante faz o consume_check reprovar

O comprovante grava dono, hora, hashes do que foi congelado e hashes transitivos de todas
as entradas dos produtores (fecho de deps), a tag git bo-freeze-NOME e o carimbo OTS
(PENDING explícito quando o cliente ots não está instalado).
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import subprocess  # noqa: E402

from bo.repo import catalog, core, fixtures, receipts  # noqa: E402

TOOLS = Path(__file__).resolve().parent


def selftest() -> int:
    ck = fixtures.Checks("freeze.py --selftest")
    mods = [
        fixtures.module("A", outputs=["$BO_DATA/A/a.txt"]),
        fixtures.module("B", deps=["A"], inputs=["$BO_DATA/A/a.txt"], outputs=["$BO_DATA/B/b.txt"]),
        fixtures.module("C", deps=["B"], inputs=["$BO_DATA/B/b.txt"]),
    ]
    with fixtures.sandbox(mods) as root:
        repo, data = root / "repo", root / "data"
        (data / "A").mkdir()
        (data / "A" / "a.txt").write_text("conteúdo congelado\n", encoding="utf-8")
        (data / "B").mkdir()
        (data / "B" / "b.txt").write_text("derivado de a\n", encoding="utf-8")
        fixtures.commit_files(repo, "[A] produz a", {"src/bo/a/x.py": "X = 1\n"})
        fixtures.commit_files(repo, "[B] produz b", {"src/bo/b/x.py": "X = 2\n"})

        def consume(mid):
            r = subprocess.run([sys.executable, "-I", str(TOOLS / "consume_check.py"), mid],
                               capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr

        rc, out = subprocess.run([sys.executable, "-I", str(TOOLS / "freeze.py"), "create", "F0",
                                  "--paths", "$BO_DATA/A/a.txt", "--owner", "coordenador", "--no-ots"],
                                 capture_output=True, text=True).returncode, ""
        rec_p = repo / "freeze" / "F0" / "freeze_receipt.json"
        ck.expect("create sai 0 e grava o comprovante", rc == 0 and rec_p.exists())
        rec = core.read_json(rec_p) or {}
        ck.expect("comprovante tem dono, hora, tag, carimbo e digest",
                  all(k in rec for k in ("owner", "created_at", "git", "ots", "digest"))
                  and rec.get("git", {}).get("tag") == "bo-freeze-F0")
        ck.expect("tag git bo-freeze-F0 criada", core.ref_exists(repo, "refs/tags/bo-freeze-F0"))
        ck.expect("carimbo OTS desligado aparece explícito", rec.get("ots", {}).get("status") == "DISABLED")
        ck.expect("produtor do artefato identificado", rec.get("artifacts", [{}])[0].get("producers") == ["A"])
        ck.expect("congelamento do coordenador registrado em state.json",
                  (core.read_json(repo / "modules" / "state.json") or {}).get("freezes", {}).get("F0", {})
                  .get("status") == "VALID")
        r2 = subprocess.run([sys.executable, "-I", str(TOOLS / "freeze.py"), "create", "FB", "--paths",
                             "$BO_DATA/B/b.txt", "--owner", "B", "--no-ots", "--no-tag",
                             "--out", str(repo / "freeze" / "FB" / "freeze_receipt.json")], capture_output=True)
        ck.expect("comprovante de módulo (dono B) não toca modules/state.json", r2.returncode == 0 and
                  "FB" not in (core.read_json(repo / "modules" / "state.json") or {}).get("freezes", {}))
        rc, out = consume("B")
        ck.expect("consume_check B passa antes da adulteração", rc == 0, out[-300:])
        ck.expect("verify do comprovante íntegro não acha problema", receipts.verify(rec_p, repo) == [])
        ck.expect("create recusa sobrescrever comprovante",
                  subprocess.run([sys.executable, "-I", str(TOOLS / "freeze.py"), "create", "F0",
                                  "--paths", "$BO_DATA/A/a.txt", "--no-ots"],
                                 capture_output=True).returncode != 0)
        # adultera a entrada congelada
        (data / "A" / "a.txt").write_text("conteúdo ADULTERADO\n", encoding="utf-8")
        rc, out = consume("B")
        ck.expect("consume_check B reprova depois da adulteração", rc != 0)
        ck.expect("a reprovação cita o comprovante", "FAIL comprovantes" in out and "F0" in out, out[-300:])
        rc, out = consume("C")
        ck.expect("dependente transitivo C também reprova (comprovante no fecho)", rc != 0)
        rc = subprocess.run([sys.executable, "-I", str(TOOLS / "freeze.py"), "verify", "F0"],
                            capture_output=True).returncode
        ck.expect("freeze.py verify reprova", rc != 0)
        # restaura a entrada, mas adultera o próprio comprovante
        (data / "A" / "a.txt").write_text("conteúdo congelado\n", encoding="utf-8")
        rec["artifacts"][0]["sha256"] = "0" * 64
        core.write_json(rec_p, rec)
        probs = receipts.verify(rec_p, repo)
        ck.expect("editar o comprovante é detectado pelo digest",
                  any("comprovante editado" in p["problem"] for p in probs))
    return ck.report()


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    ap = argparse.ArgumentParser(prog="freeze.py", description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--paths", nargs="+", required=True)
    c.add_argument("--owner", default="coordenador")
    c.add_argument("--out")
    c.add_argument("--note", default="")
    c.add_argument("--no-tag", action="store_true")
    c.add_argument("--no-ots", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("names", nargs="*")
    s = sub.add_parser("stamp")
    s.add_argument("name")
    a = ap.parse_args()
    repo = core.bo_repo()
    cat = catalog.load(repo)
    if a.cmd == "create":
        out, rec = receipts.create(cat, a.name, a.paths, a.owner, repo, Path(a.out) if a.out else None,
                                   tag=not a.no_tag, ots=not a.no_ots, note=a.note)
        core.emit(f"[{core.now()}] comprovante {a.name}: {out}")
        core.emit(f"  {len(rec['artifacts'])} artefato(s), {len(rec['transitive_inputs'])} entrada(s) transitiva(s), "
                  f"módulos {', '.join(rec['modules']) or '-'}; tag {rec['git']['tag']}; OTS {rec['ots']['status']}")
        core.emit(f"  digest {rec['digest']}")
        return 0
    if a.cmd == "verify":
        recs = receipts.list_receipts(repo)
        if a.names:
            recs = [r for r in recs if r.parent.name in a.names]
            missing = set(a.names) - {r.parent.name for r in recs}
            if missing:
                raise core.BoError("comprovante não encontrado: " + ", ".join(sorted(missing)))
        bad = 0
        for r in recs:
            probs = receipts.verify(r, repo)
            bad += bool(probs)
            core.emit(f"{r.parent.name}: {'OK' if not probs else 'DIVERGE'}")
            for p in probs:
                core.emit(f"  - {p['path']}: {p['problem']}")
        core.emit(f"[{core.now()}] {len(recs)} comprovante(s), {bad} com divergência")
        return 1 if bad else 0
    if a.cmd == "stamp":
        rp = receipts.receipts_dir(repo) / a.name / "freeze_receipt.json"
        rec = core.read_json(rp)
        if rec is None:
            raise core.BoError(f"comprovante não encontrado: {rp}")
        rec["ots"] = receipts.stamp_ots(rec["digest"], rp.parent)
        core.write_json(rp, rec)
        core.emit(f"{a.name}: OTS {rec['ots']['status']} ({rec['ots'].get('reason', '')})")
        return 0 if rec["ots"]["status"] == "STAMPED" else 1
    return 2


if __name__ == "__main__":
    core.run_main(main)
