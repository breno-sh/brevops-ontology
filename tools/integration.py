#!/usr/bin/env python3
"""Runner dos testes de integração cruzada (make integration), a cada merge (§7.2, S10).

  integration.py [--only DIR]

Roda cada diretório tests/integration/*/ (core/ é do REPO; domains/ é do DOMAIN-CONTRACTS, com IAM em
NET/SEC e chaves em STO/SEC/OPS) com pytest (versão do requirements.lock) ou unittest se pytest faltar.
Teste que depende de domínio ainda não mergeado sai SKIP com motivo; todo SKIP é impresso e
registrado em $BO_DATA/REPO/integration/last_run.json (e no histórico history.jsonl), nunca silencioso.
Reprova se algum teste falhar, se nenhum teste for coletado ou se o runner não conseguir rodar.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

from bo.repo import core  # noqa: E402


def run_dir(d: Path, env: dict, tmp: Path) -> dict:
    junit = tmp / f"junit-{d.name}.xml"
    junit.unlink(missing_ok=True)
    if importlib.util.find_spec("pytest") is not None:
        cmd = [sys.executable, "-I", "-B", "-m", "pytest", str(d), "-q", "-rs", "-p", "no:cacheprovider",
               f"--junitxml={junit}", f"--rootdir={d}"]
        runner = "pytest"
    else:
        cmd = [sys.executable, "-I", "-B", "-m", "unittest", "discover", "-s", str(d), "-v"]
        runner = "unittest"
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(tmp), timeout=3600)
    res = {"dir": str(d.relative_to(core.bo_repo())), "runner": runner, "rc": r.returncode,
           "tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": [], "failures": []}
    if runner == "pytest" and junit.exists():
        root = ET.parse(junit).getroot()
        for tc in root.iter("testcase"):
            res["tests"] += 1
            name = f"{tc.get('classname', '')}::{tc.get('name', '')}"
            sk, fa, er = tc.find("skipped"), tc.find("failure"), tc.find("error")
            if sk is not None:
                res["skipped"].append({"test": name, "reason": (sk.get("message") or "").strip()})
            elif fa is not None or er is not None:
                res["failed" if fa is not None else "errors"] += 1
                el = fa if fa is not None else er
                res["failures"].append({"test": name, "message": (el.get("message") or "")[:300]})
            else:
                res["passed"] += 1
    else:
        out = r.stdout + r.stderr
        for line in out.splitlines():
            if " ... " in line:
                res["tests"] += 1
                name, _, st = line.rpartition(" ... ")
                if st.startswith("skipped"):
                    res["skipped"].append({"test": name.strip(), "reason": st[len("skipped"):].strip(" '")})
                elif st.startswith("ok"):
                    res["passed"] += 1
                else:
                    res["failed"] += 1
                    res["failures"].append({"test": name.strip(), "message": st[:300]})
    if r.returncode not in (0, 5) and not res["failures"]:
        res["errors"] += 1
        res["failures"].append({"test": "(runner)", "message": (r.stdout + r.stderr)[-600:]})
    res["output_tail"] = (r.stdout + r.stderr).splitlines()[-15:]
    return res


def main() -> int:
    ap = argparse.ArgumentParser(prog="integration.py")
    ap.add_argument("--only")
    a = ap.parse_args()
    repo = core.bo_repo()
    base = repo / "tests" / "integration"
    dirs = sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")) and
                  p.name != "__pycache__") if base.is_dir() else []
    if a.only:
        dirs = [d for d in dirs if d.name == a.only]
    if not dirs:
        raise core.BoError(f"nenhum diretório de teste em {base}")
    env = core.module_env("REPO", repo)
    tmp = core.bo_tmp("REPO") / "integration"
    tmp.mkdir(parents=True, exist_ok=True)
    report = {"at": core.now(), "repo": str(repo),
              "head": core.git(repo, "rev-parse", "--short", "HEAD", check=False).strip(), "dirs": []}
    core.emit(f"[{report['at']}] make integration em {repo} ({report['head']})")
    tot = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for d in dirs:
        res = run_dir(d, env, tmp)
        report["dirs"].append(res)
        for k in ("tests", "passed", "failed", "errors"):
            tot[k] += res[k]
        tot["skipped"] += len(res["skipped"])
        core.emit(f"  {res['dir']} ({res['runner']}): {res['passed']} passaram, {len(res['skipped'])} SKIP, "
                  f"{res['failed']} falharam, {res['errors']} erro(s)")
        for s in res["skipped"]:
            core.emit(f"    SKIP {s['test']}: {s['reason']}")
        for f in res["failures"]:
            core.emit(f"    FAIL {f['test']}: {f['message']}")
    report["totals"] = tot
    ok = tot["failed"] == 0 and tot["errors"] == 0 and tot["tests"] > 0 and tot["passed"] > 0
    report["ok"] = ok
    out = core.bo_data() / "REPO" / "integration"
    core.write_json(out / "last_run.json", report)
    with open(out / "history.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({k: report[k] for k in ("at", "head", "totals", "ok")}, ensure_ascii=False) + "\n")
    core.emit(f"  total: {tot['tests']} teste(s), {tot['passed']} passaram, {tot['skipped']} SKIP registrado(s), "
              f"{tot['failed'] + tot['errors']} falha(s); relatório {out / 'last_run.json'}")
    core.emit("RESULTADO: " + ("OK" if ok else "REPROVADO"))
    return 0 if ok else 1


if __name__ == "__main__":
    core.run_main(main)
