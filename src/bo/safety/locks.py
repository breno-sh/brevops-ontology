"""Travas mkdir no formato do tools/lock.sh ($BO_DATA/locks/<nome>/owner com owner, pid, host, at).

A limpeza (teardown, supervisor, varredura com remoção) só roda com a trava cleanup-global: duas limpezas em
paralelo nunca decidem sobre o mesmo inventário. Trava órfã é relatada, nunca quebrada sozinha.
"""

from __future__ import annotations

import os
import re
import socket
import time
from contextlib import contextmanager
from pathlib import Path

from .common import SafetyError, bo_data, now

CLEANUP = "cleanup-global"


class LockBusy(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "LOCK")


def locks_root() -> Path:
    return Path(os.environ.get("BO_LOCKS_DIR") or (bo_data() / "locks"))


def _owner_text(owner: str) -> str:
    return f"owner={owner}\npid={os.getpid()}\nhost={socket.gethostname().split('.')[0]}\nat={now()}\n"


def acquire(name: str, owner: str, wait_s: float = 0.0, root: Path | None = None, poll_s: float = 0.2) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise SafetyError(f"nome de trava inválido: {name}", "LOCK")
    root = Path(root or locks_root())
    root.mkdir(parents=True, exist_ok=True)
    d = root / name
    t0 = time.monotonic()
    while True:
        try:
            d.mkdir()
            (d / "owner").write_text(_owner_text(owner), encoding="utf-8")
            return d
        except FileExistsError:
            if time.monotonic() - t0 >= wait_s:
                raise LockBusy(f"trava {name} ocupada ({holder(name, root) or 'dono ilegível'})") from None
            time.sleep(poll_s)


def holder(name: str, root: Path | None = None) -> str | None:
    f = Path(root or locks_root()) / name / "owner"
    try:
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.startswith("owner="):
                return ln[6:]
    except OSError:
        return None
    return None


def release(name: str, owner: str, root: Path | None = None) -> None:
    d = Path(root or locks_root()) / name
    if not d.exists():
        return
    cur = holder(name, root)
    if cur != owner:
        raise LockBusy(f"trava {name} pertence a {cur!r}, não a {owner!r}")
    (d / "owner").unlink(missing_ok=True)
    d.rmdir()


def orphan(name: str, root: Path | None = None) -> bool:
    """True se a trava é deste host e o processo dono não existe mais (só relato)."""
    f = Path(root or locks_root()) / name / "owner"
    try:
        kv = dict(ln.split("=", 1) for ln in f.read_text(encoding="utf-8").splitlines() if "=" in ln)
    except OSError:
        return False
    if kv.get("host") != socket.gethostname().split(".")[0]:
        return False
    try:
        os.kill(int(kv.get("pid", "0")), 0)
        return False
    except (OSError, ValueError):
        return True


@contextmanager
def held(name: str, owner: str, wait_s: float = 0.0, root: Path | None = None):
    acquire(name, owner, wait_s, root)
    try:
        yield
    finally:
        release(name, owner, root)
