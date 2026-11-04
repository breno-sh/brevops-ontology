"""Ajudantes dos testes do PROBEKIT (importados pelos testes; o pytest põe esta pasta no sys.path)."""

from __future__ import annotations

import json
from pathlib import Path

from bo.probes.backends import FakeClock, RecordedBackend, SimBackend
from bo.probes.cells import IMPL
from bo.probes.kinds import FAMILY
from bo.probes.runner import ProbeCase, Runner

RECORDED = Path(__file__).resolve().parent / "recorded"


class FakeSupervisor:
    """beat() aceita, a não ser que down_from/down_until (instantes do relógio) digam que caiu."""

    def __init__(self, clock=None, down_from=None, down_until=None):
        self.clock, self.down_from, self.down_until = clock, down_from, down_until
        self.n = 0

    def beat(self):
        t = self.clock.monotonic() if self.clock else 0
        if self.down_from is not None and t >= self.down_from and (self.down_until is None or t < self.down_until):
            raise ConnectionError("supervisor fora")
        self.n += 1
        return {"status": "watching"}


ALL_VALIDATED = {f"{t}/{p}": "validated" for t in ("object_versioning", "object_lifecycle", "item_ttl",
                                                    "queue_retention", "rate_limit", "log_retention")
                 for p in ("aws", "google", "azurerm", "oci")}


def load_recording(name: str) -> dict:
    return json.loads((RECORDED / name).read_text(encoding="utf-8"))


def recorded_run(protos, name: str, *, side="A", support=None, readback=None, supervisor="ok"):
    rec = load_recording(name)
    cell = rec["cell"]
    t, p = cell.split("/")
    clock = FakeClock()
    sup = FakeSupervisor(clock) if supervisor == "ok" else supervisor
    case = ProbeCase(f"PC-REC-{t}-{p}", side, t, p, ttl_s=IMPL[cell].ttl_s)
    rb = RecordedBackend(rec, clock=clock, base_ctx={"n": 3})
    run = Runner(case, protos[t], rb, clock=clock, support=support or ALL_VALIDATED, supervisor=sup,
                 readback=readback or {"case": "PERSISTED", "control": "PERSISTED"})
    obs, trace = run.run()
    return obs, trace, run, rb


def sim_run(protos, cell: str, *, side="A", seed=0, sim=None, support=None, readback=None, supervisor="ok",
            rate_limit=None, ttl_s=None):
    t, p = cell.split("/")
    clock = FakeClock()
    sup = FakeSupervisor(clock) if supervisor == "ok" else supervisor
    ttl = IMPL[cell].ttl_s if ttl_s is None and cell in IMPL else (ttl_s or 0.0)
    kw = dict(sim or {})
    be = SimBackend(FAMILY[t], clock, ttl_s=ttl, seed=seed, **kw)
    case = ProbeCase(f"PC-SIM-{t}-{p}", side, t, p, ttl_s=ttl, rate_limit=rate_limit)
    run = Runner(case, protos[t], be, clock=clock, support=support or ALL_VALIDATED, supervisor=sup,
                 readback=readback or {"case": "PERSISTED", "control": "PERSISTED"})
    if be.family != "throttle":
        be.n = run.kind.n
    obs, trace = run.run()
    return obs, trace, run, be
