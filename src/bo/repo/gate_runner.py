"""make gate ID=<X>: roda os gates do módulo X lidos do modulos.json.

Ordem: ambiente pronto (bootstrap) -> gate_smoke (nada roda se algum comando não resolve)
-> gates/<X>.sh (contratos, manifesto, regeneração idêntica) -> cada gate do catálogo, em ordem.
A linha 'make -C $BO_REPO gate ID=<X>' do próprio módulo é pulada (auto-referência) e registrada
como SKIP. Cada comando roda com BO_REPO, BO_DATA, BO_ID e BO_TMP=$BO_DATA/tmp/<X> (TMPDIR também),
com tempo-limite (BO_GATE_TIMEOUT, padrão 1800 s). Relatório em $BO_DATA/<X>/gate_report.json.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from . import bootstrap, catalog, core, privacy, smoke
from .core import BoError


def scrub(text: str, keep: int = 30) -> list[str]:
    out = []
    for ln in text.splitlines()[-keep:]:
        f = privacy.scan_text(ln, "saida")
        out.append(f"[linha omitida pelo privacy_lint: {f[0].rule}]" if f else ln[:300])
    return out


def run_cmd(cmd: str, env: dict, cwd: Path, timeout: int) -> tuple[int, str, float]:
    t0 = time.monotonic()
    try:
        r = subprocess.run(["bash", "-c", cmd], env=env, cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        rc, out = 124, f"TEMPO ESGOTADO depois de {timeout} s\n" + partial
    return rc, out, time.monotonic() - t0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not argv[0] or argv[0].startswith("-"):
        raise BoError("uso: make gate ID=<stable_id>", code=2)
    mid = argv[0]
    repo = core.bo_repo()
    cat = catalog.load(repo)
    mod = cat.get(mid)
    stack = [x for x in os.environ.get("BO_GATE_STACK", "").split(",") if x]
    if mid in stack:
        raise BoError(f"recursão de gates: {' -> '.join(stack + [mid])}", code=4)
    env = core.module_env(mid, repo)
    env["BO_GATE_STACK"] = ",".join(stack + [mid])
    timeout = int(os.environ.get("BO_GATE_TIMEOUT", "1800"))
    head = core.git(repo, "rev-parse", "--short", "HEAD", check=False).strip() or "?"
    core.emit(f"[{core.now()}] make gate ID={mid} em {repo} ({head}); catálogo {cat.source}")
    report = {"module": mid, "at": core.now(), "repo": str(repo), "head": head, "catalog": str(cat.source),
              "catalog_sha256": core.sha256_file(cat.source), "results": []}

    def finish(code: int) -> int:
        report["finished_at"] = core.now()
        report["exit"] = code
        n = {s: sum(r["status"] == s for r in report["results"]) for s in ("PASS", "FAIL", "SKIP")}
        report["summary"] = n
        core.write_json(core.bo_data() / mid / "gate_report.json", report)
        core.emit(f"[{core.now()}] gate {mid}: {n['PASS']} PASS, {n['FAIL']} FAIL, {n['SKIP']} SKIP -> "
                  + ("OK" if code == 0 else "REPROVADO"))
        return code

    # 1. ambiente
    env_probs = bootstrap.check()
    if env_probs:
        for p in env_probs:
            core.emit(f"  FAIL ambiente: {p}")
            report["results"].append({"gate": "ambiente", "status": "FAIL", "detail": p})
        return finish(3)
    # 2. smoke (nada roda se algo não resolve)
    rep = smoke.Smoker(cat, repo, env).smoke_module(mid)
    bad = [i for i in rep.items if not i.ok]
    report["results"].append({"gate": "gate_smoke", "status": "PASS" if not bad else "FAIL",
                              "detail": f"{len(rep.items)} verificações, {len(bad)} não resolvem"})
    if bad:
        core.emit("  FAIL gate_smoke: nenhum gate foi executado")
        for i in bad:
            core.emit(i.line())
        return finish(3)
    core.emit(f"  PASS gate_smoke ({len(rep.items)} verificações)")
    # 3. gates/<ID>.sh e 4. gates do catálogo
    lines = [("gates/%s.sh" % mid, f"bash {repo}/gates/{mid}.sh")] + [(g, catalog.strip_comment(g)[0]) for g in mod.gates]
    code = 0
    for label, cmd in lines:
        if catalog.is_self_gate(label, mid):
            core.emit(f"  SKIP {label}  (auto-referência: é este runner)")
            report["results"].append({"gate": label, "status": "SKIP", "detail": "auto-referência"})
            continue
        rc, out, dt = run_cmd(cmd, env, repo, timeout)
        st = "PASS" if rc == 0 else "FAIL"
        core.emit(f"  {st} [{dt:6.1f}s] {label}")
        res = {"gate": label, "status": st, "rc": rc, "seconds": round(dt, 1)}
        if rc != 0:
            code = 1
            res["tail"] = scrub(out)
            for ln in res["tail"]:
                core.emit(f"       | {ln}")
        report["results"].append(res)
    return finish(code)


if __name__ == "__main__":
    core.run_main(main)
