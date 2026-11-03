"""ROBOT e o HermiT dele, na versão fixada (toolchain_pins.json); nada roda sem conferir a versão."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import common as c

PINS_FILE = "toolchain_pins.json"


def pins() -> dict:
    return c.read_json(c.patterns_dir() / PINS_FILE)


def jar() -> Path:
    return Path(pins()["robot"]["jar_path"].replace("$BO_DATA", str(c.data_dir())))


def java() -> str:
    return pins()["java"]["path"]


def env() -> dict:
    e = dict(os.environ)
    e.setdefault("TMPDIR", str(c.tmp_dir()))
    return e


def run(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    exe = shutil.which("robot")
    if not exe:
        raise RuntimeError("robot não está no PATH")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, env=env(), cwd=str(c.tmp_dir()))


def verify_jar() -> None:
    p = pins()["robot"]
    got = c.sha256_file(jar())
    if got != p["jar_sha256"]:
        raise RuntimeError(f"robot.jar diverge do pin: {got[:12]}… != {p['jar_sha256'][:12]}…")


def compile_harness() -> Path:
    """Compila o harness Java contra o robot.jar fixado, em $BO_TMP/classes (recompila se a fonte mudar)."""
    verify_jar()
    src = Path(__file__).resolve().parent / "java" / "TrialReasoner.java"
    out = c.tmp_dir() / "classes"
    stamp = out / ".src.sha256"
    sha = c.sha256_file(src)
    if stamp.exists() and stamp.read_text() == sha and (out / "TrialReasoner.class").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    javac = str(Path(java()).with_name("javac"))
    r = subprocess.run([javac, "-nowarn", "-cp", str(jar()), "-d", str(out), str(src)], capture_output=True, text=True,
                       env=env(), timeout=300)
    if r.returncode != 0:
        raise RuntimeError("javac falhou: " + r.stderr[-800:])
    stamp.write_text(sha)
    return out


def harness(jobs: Path, out: Path, timeout: int = 1800) -> list[str]:
    classes = compile_harness()
    r = subprocess.run([java(), "-Xmx4G", "-cp", f"{jar()}:{classes}", "TrialReasoner", str(jobs), str(out)],
                       capture_output=True, text=True, env=env(), timeout=timeout, cwd=str(c.tmp_dir()))
    if r.returncode != 0:
        raise RuntimeError("harness falhou: " + (r.stderr or r.stdout)[-1500:])
    return out.read_text(encoding="utf-8").splitlines()


def validate_profile(inputs: list[Path], tag: str) -> dict:
    """Junta os arquivos (com o fecho de imports) e valida o perfil OWL 2 DL; devolve o laudo."""
    tmp = c.tmp_dir()
    merged = tmp / f"closure_{tag}.ttl"
    args = ["merge"]
    for p in inputs:
        args += ["--input", str(p)]
    args += ["--collapse-import-closure", "true", "--output", str(merged)]
    r = run(args)
    if r.returncode != 0:
        return {"profile": "OWL 2 DL", "in_profile": False, "error": (r.stderr or r.stdout)[-600:]}
    rep = tmp / f"profile_{tag}.txt"
    r2 = run(["validate-profile", "--profile", "DL", "--input", str(merged), "--output", str(rep)])
    text = rep.read_text(encoding="utf-8") if rep.exists() else ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return {"profile": "OWL 2 DL", "in_profile": r2.returncode == 0, "violations": max(0, len(lines) - 1),
            "report_head": lines[:4]}


def tool_versions() -> dict:
    r = run(["--version"])
    return {"robot_version_output": (r.stdout or r.stderr).strip().splitlines()[:1]}


if __name__ == "__main__":
    print(json.dumps(tool_versions(), ensure_ascii=False))
