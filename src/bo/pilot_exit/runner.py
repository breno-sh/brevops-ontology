"""Executa o código congelado do E2E numa cópia isolada, com as retidas no leiaute da calibração.

Isolamento (o avaliador não pode estragar nada de ninguém nem deixar o código avaliado sair da caixa):
  BO_REPO  = cópia congelada (git archive do commit avaliado) em $BO_TMP/run/<fatia>/repo
  BO_DATA  = sobreposição em $BO_TMP/run/<fatia>/data: ligação simbólica para cada pasta de $BO_DATA (só
             leitura na prática, ver abaixo), menos a do próprio E2E (cópia, para a escrita dele ficar aqui),
             tmp/ (novo), PILOT-EXIT/ e SPLIT/ (fora)
  sandbox-exec: escrita negada em toda a HOME salvo $BO_TMP do PILOT-EXIT; rede de saída negada (offline),
             salvo localhost e soquete unix (o terraform fala com o provider por gRPC local)
Os comandos são os gates do próprio E2E no catálogo (bo.pilot.*, bo.lower.*), na ordem, com o mesmo texto.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from . import common as C

SKIP_TOP = {"tmp", "PILOT-EXIT", "SPLIT", ".DS_Store"}


def catalog_gates(mid: str) -> list[str]:
    import json
    p = os.environ.get("BO_MODULES") or "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json"
    mods = {m["stable_id"]: m for m in json.load(open(p, encoding="utf-8"))["modules"]}
    out = []
    for g in mods[mid]["gates"]:
        cmd = g.split("  #", 1)[0].strip()
        if cmd.startswith("python -I -m bo.pilot.") or cmd.startswith("python -I -m bo.lower."):
            out.append(cmd)
    return out


def overlay(real: Path, dest: Path, own: str) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for p in sorted(real.iterdir()):
        if p.name in SKIP_TOP:
            continue
        if p.name == own:
            shutil.copytree(p, dest / own, symlinks=True, ignore=shutil.ignore_patterns(".staging"))
        else:
            (dest / p.name).symlink_to(p)
    (dest / "tmp").mkdir()
    if not (dest / own).exists():
        (dest / own).mkdir()
    return dest


def profile(write_root: Path, home: Path) -> str:
    return "\n".join([
        "(version 1)", "(allow default)",
        "(deny network-outbound (remote ip))",
        '(allow network-outbound (remote ip "localhost:*"))',
        '(allow network-outbound (remote unix-socket))',
        f'(deny file-write* (subpath "{home}"))',
        f'(allow file-write* (subpath "{write_root}"))',
        '(allow file-write* (literal "/dev/null"))', ""])


def run_commands(cmds: list[str], frozen_repo: Path, data_root: Path, mid: str, logdir: Path,
                 timeout: int = 1500, sandbox: bool = True, tmp_root: Path | None = None) -> list[dict]:
    """Roda cada comando; grava stdout/stderr em logdir (fica em $BO_TMP, nunca em results/)."""
    # BO_TMP curto: o socket unix do provider Terraform não cabe nos 104 caracteres do macOS com caminho longo
    tmpd = tmp_root or C.tmp() / "t"
    if tmpd.exists() and not tmpd.is_symlink():
        shutil.rmtree(tmpd)
    tmpd.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "USER", "SHELL", "TERM")}
    env.update({"BO_REPO": str(frozen_repo), "BO_DATA": str(data_root), "BO_ID": mid, "BO_TMP": str(tmpd),
                "TMPDIR": str(tmpd), "BO_MODULES": os.environ.get("BO_MODULES") or
                "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/modulos.json",
                "BO_BASE": "bo/base", "PYTHONDONTWRITEBYTECODE": "1"})
    logdir.mkdir(parents=True, exist_ok=True)
    sb = None
    if sandbox:
        sb = logdir / "sandbox.sb"
        sb.write_text(profile(C.tmp(), Path.home()), encoding="utf-8")
    out = []
    for i, cmd in enumerate(cmds, 1):
        argv = shlex.split(cmd.replace("$BO_DATA", str(data_root)).replace("$BO_REPO", str(frozen_repo)))
        if sb:
            argv = ["sandbox-exec", "-f", str(sb)] + argv
        t0 = time.monotonic()
        try:
            r = subprocess.run(argv, cwd=str(frozen_repo), env=env, capture_output=True, timeout=timeout)
            rc, so, se = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            rc, so, se = 124, e.stdout or b"", (e.stderr or b"") + b"\nTIMEOUT"
        dt = time.monotonic() - t0
        (logdir / f"{i:02d}.out").write_bytes(so)
        (logdir / f"{i:02d}.err").write_bytes(se)
        out.append({"i": i, "cmd": cmd, "rc": rc, "seconds": round(dt, 1)})
    return out
