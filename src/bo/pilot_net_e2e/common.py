"""Argumentos e utilidades comuns dos comandos do PILOT-NET-E2E."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from bo.pilot.net import pipeline as P

MODULE = "PILOT-NET-E2E"


def parser(prog: str, doc: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description=doc.split("\n")[0])
    ap.add_argument("ID", nargs="?", help="stable_id (para o despachante); ignorado aqui")
    ap.add_argument("--slice", default="net", choices=["net"])
    ap.add_argument("--claims", default="mapping", choices=["mapping", "synthetic"],
                    help="mapping = $BO_DATA/PILOT-NET-MAP (padrão); synthetic = só teste do caminho")
    ap.add_argument("--fixtures", default="calib", help="calib (repositório) ou pasta de fixtures (PILOT-EXIT)")
    ap.add_argument("--out", default=None, help="pasta de saída (padrão: $BO_DATA/PILOT-NET-E2E/.staging)")
    return ap


def fixtures_args(a):
    if a.fixtures in ("calib", None):
        return None, "calib"
    d = Path(a.fixtures)
    if not d.is_dir():
        raise SystemExit(f"--fixtures: {d} não é pasta")
    return d, None


def repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def results_dir() -> Path:
    return repo() / "results" / MODULE


def out_dir(a) -> Path:
    return Path(a.out) if a.out else P.staging()


def run_pipeline(a) -> dict:
    d, split = fixtures_args(a)
    return P.run(claims_mode=a.claims, fixtures_dir=d, split=split, out=out_dir(a))


def load_report(out: Path) -> dict:
    p = out / "run_report.json"
    if not p.exists():
        raise SystemExit(f"{p} ausente: rode bo.pilot.run primeiro")
    return json.loads(p.read_text(encoding="utf-8"))


def validate(contract: str, *paths) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", contract, *map(str, paths)],
                       capture_output=True, text=True, timeout=900, env=dict(os.environ))
    return r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:] and (r.stdout + r.stderr).strip().splitlines()[-1]


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")


def say(msg: str) -> None:
    print(f"[{P.now()}] {msg}")
