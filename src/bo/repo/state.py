"""Estado declarado dos módulos (modules/state.json): CURRENT, STALE ou ABANDONED.

"Mergeado" não é guardado aqui: é derivado do git (commit '[ID] ...' em bo/base).
O estado só muda por ferramenta (invalidate.py, freeze.py) e cada mudança vira evento.
"""

from __future__ import annotations

from pathlib import Path

from . import core
from .catalog import STATE_REL, Catalog

STATUSES = ("CURRENT", "STALE", "ABANDONED")


def path(repo: Path | None = None) -> Path:
    return Path(repo or core.bo_repo()) / STATE_REL


def initial(cat: Catalog) -> dict:
    return {
        "schema": "bo.state/1",
        "timezone": "America/Recife",
        "statuses": list(STATUSES),
        "note": "merged é derivado do git (commit '[ID] ...' em bo/base); aqui fica só o estado declarado.",
        "modules": {mid: {"status": "CURRENT"} for mid in cat.modules},
        "freezes": {},
        "events": [],
    }


def load(repo: Path | None = None, cat: Catalog | None = None) -> dict:
    st = core.read_json(path(repo))
    if st is None:
        if cat is None:
            return {"schema": "bo.state/1", "modules": {}, "freezes": {}, "events": []}
        st = initial(cat)
    st.setdefault("modules", {})
    st.setdefault("freezes", {})
    st.setdefault("events", [])
    return st


def save(st: dict, repo: Path | None = None) -> None:
    core.write_json(path(repo), st)


def status_of(st: dict, mid: str) -> str:
    return (st.get("modules", {}).get(mid) or {}).get("status", "CURRENT")


def mark(st: dict, mid: str, status: str, reason: str, source: str | None = None) -> bool:
    if status not in STATUSES:
        raise ValueError(status)
    cur = st["modules"].setdefault(mid, {"status": "CURRENT"})
    changed = cur.get("status") != status
    cur["status"] = status
    cur["since"] = core.now()
    cur["reason"] = reason
    if source:
        cur["source"] = source
    elif "source" in cur and status == "CURRENT":
        cur.pop("source")
    st["events"].append({"at": cur["since"], "module": mid, "status": status, "reason": reason,
                         **({"source": source} if source else {})})
    return changed
