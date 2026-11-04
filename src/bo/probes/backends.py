"""Backends do runner. Todos expõem a mesma interface:

  act(role, rep, ctx)                 ação da repetição (role = case | control)
  observe(role, rep) -> {contagens}   leitura que não consome nada
  burst(role, rep, n, window_s)       limite de taxa: N pedidos numa janela -> {accepted, throttled, other}

  RecordedBackend  respostas gravadas (formato de saída de cada CLI/API, valores sintéticos) passadas pelos MESMOS
                   parsers do ops.py; confere que o runner lê nos instantes gravados (at_s)
  SimBackend       simulação determinística (semente) da semântica de cada família, com atraso, oscilação e erro
  LiveBackend      CLI/REST de verdade; RECUSA sem as pré-condições de nuvem do SAFETY (GO do Breno, módulo de
                   nuvem, trava cloud-<provedor>, ambiente limpo). Nesta fase não roda.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .common import TZ, ProbeError
from .ops import ParseError, ops_for, runner_ctx


class BackendError(RuntimeError):
    def __init__(self, msg: str, code: str = "BACKEND"):
        super().__init__(msg)
        self.code = code


# ------------------------------------------------------------------------------------------------ relógio
class Clock:
    def monotonic(self) -> float:
        raise NotImplementedError

    def sleep(self, s: float) -> None:
        raise NotImplementedError

    def wall_epoch(self) -> float:
        raise NotImplementedError

    def wall(self) -> datetime:
        return datetime.fromtimestamp(int(self.wall_epoch()), TZ)


class RealClock(Clock):
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, s: float) -> None:
        time.sleep(max(0.0, s))

    def wall_epoch(self) -> float:
        return time.time()


class FakeClock(Clock):
    """Relógio simulado: dormir só avança o tempo (72 h de janela rodam em milissegundos)."""

    def __init__(self, start_epoch: float = 1793800800.0):  # 2026-11-04T09:00:00-03:00
        self.t = 0.0
        self.start = start_epoch
        self.slept = 0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += max(0.0, s)
        self.slept += 1

    def wall_epoch(self) -> float:
        return self.start + self.t


# ------------------------------------------------------------------------------------------------ gravado
class RecordedBackend:
    """recording = {"schema": "bo.probe_recording/1", "cell": "<tipo>/<provedor>", "synthetic": true,
    "calls": {"<role>/<rep>": {"act": [raw, ...], "observe": [{"at_s": t, "raw": raw}, ...],
                                "burst": [{"accepted": a, "throttled": t, "other": o}]}}}
    raw de CLI = {"rc": 0, "stdout": "<json>"}; raw de REST = {"status": 200, "body": {...}}; observe por item =
    lista de raws. Falha gravada = {"rc": 255} ou {"status": 503}. Resposta a mais ou a menos é erro do teste."""

    def __init__(self, recording: dict, clock: Clock | None = None, base_ctx: dict | None = None):
        if recording.get("schema") != "bo.probe_recording/1" or recording.get("synthetic") is not True:
            raise ProbeError("gravação sem schema bo.probe_recording/1 ou não marcada como sintética", "RECORDING")
        self.cell = recording["cell"]
        self.calls = recording["calls"]
        self.clock = clock
        self.base = base_ctx or {}
        self.pos: dict = {}
        self.t0: float | None = None
        self.ops = ops_for(self.cell) if self.cell in _cells_with_ops() else None

    def _next(self, role, rep, op):
        k = (role, rep, op)
        i = self.pos.get(k, 0)
        seq = (self.calls.get(f"{role}/{rep}") or {}).get(op) or []
        if i >= len(seq):
            raise AssertionError(f"gravação sem resposta {i + 1} de {op} para {role}/{rep}")
        self.pos[k] = i + 1
        return seq[i]

    def act(self, role, rep, ctx):
        if self.t0 is None and self.clock is not None:
            self.t0 = self.clock.monotonic()
        raw = self._next(role, rep, "act")
        items = raw if isinstance(raw, list) else [raw]
        for r in items:
            if not (r.get("rc") == 0 or r.get("status") in (200, 201)):
                raise BackendError("ação gravada falhou", "ACT")

    def observe(self, role, rep):
        rec = self._next(role, rep, "observe")
        if self.clock is not None and self.t0 is not None and "at_s" in rec:
            t = self.clock.monotonic() - self.t0
            if abs(t - float(rec["at_s"])) > 1e-6:
                raise AssertionError(f"leitura em t={t:.0f}s, gravada em {rec['at_s']}s ({role}/{rep})")
        if self.ops is None:
            return rec["sample"]
        ctx = runner_ctx(self.cell, role, rep, {**self.base, "n": rec.get("n", self.base.get("n", 0))})
        try:
            return self.ops["observe"].parse(rec["raw"], ctx)
        except ParseError as e:
            raise BackendError(str(e), "PARSE") from None

    def burst(self, role, rep, n, window_s):
        rec = self._next(role, rep, "burst")
        if rec.get("failed"):
            raise BackendError("rajada gravada falhou", "BURST")
        return rec


def _cells_with_ops() -> set:
    from .ops import OPS
    return set(OPS)


# ------------------------------------------------------------------------------------------------ simulado
class SimBackend:
    """Semântica simulada por família (determinística com a semente):
      versions  ligado: a listagem mostra W versões depois de list_lag_s (antes, 1); desligado: 1 versão
      expiry    ligado: cada item some em ttl + atraso (uniforme em [0, expiry_lag_s]); desligado: nunca some;
                resurrect_s > 0 faz um item reaparecer por uma leitura depois de sumir (oscilação)
      throttle  ligado: balde de fichas (rajada + taxa × janela); desligado: tudo aceito
    on = {"case": True, "control": False} por padrão (controle negativo = configuração desligada);
    fail = {(role, rep, op): k} faz as k primeiras chamadas falharem; error_rate sorteia falhas de leitura."""

    def __init__(self, family: str, clock: Clock, *, ttl_s=0.0, n=3, seed=0, on=None, list_lag_s=0.0,
                 expiry_lag_s=0.0, resurrect_s=0.0, error_rate=0.0, fail=None, rate=None, burst_cap=None):
        self.family, self.clock, self.ttl_s, self.n = family, clock, float(ttl_s), n
        self.rng = random.Random(seed)
        self.on = on or {"case": True, "control": False}
        self.list_lag_s, self.expiry_lag_s, self.resurrect_s = list_lag_s, expiry_lag_s, resurrect_s
        self.error_rate, self.fail = error_rate, dict(fail or {})
        self.rate, self.burst_cap = rate, burst_cap
        self.state: dict = {}
        self.calls: dict = {}

    def _maybe_fail(self, role, rep, op):
        k = (role, rep, op)
        if self.fail.get(k, 0) > 0:
            self.fail[k] -= 1
            raise BackendError("falha simulada", op.upper())
        if op == "observe" and self.error_rate and self.rng.random() < self.error_rate:
            raise BackendError("falha simulada", "OBSERVE")

    def act(self, role, rep, ctx):
        self._maybe_fail(role, rep, "act")
        t = self.clock.monotonic()
        if self.family == "versions":
            self.state[(role, rep)] = {"t": t, "writes": self.n}
        elif self.family == "expiry":
            exp = [t + self.ttl_s + self.rng.uniform(0, self.expiry_lag_s) for _ in range(self.n)]
            self.state[(role, rep)] = {"t": t, "expire_at": exp, "shown_again": set()}

    def observe(self, role, rep):
        self._maybe_fail(role, rep, "observe")
        st = self.state[(role, rep)]
        now = self.clock.monotonic()
        if self.family == "versions":
            if not self.on[role]:
                return {"versions": 1}
            return {"versions": st["writes"] if now - st["t"] >= self.list_lag_s else 1}
        if not self.on[role]:
            return {"present": self.n}
        present = 0
        for i, e in enumerate(st["expire_at"]):
            if now < e:
                present += 1
            elif self.resurrect_s and now < e + self.resurrect_s and i not in st["shown_again"]:
                st["shown_again"].add(i)  # leitura eventual devolve o item uma vez depois de sumir
                present += 1
        return {"present": present}

    def burst(self, role, rep, n, window_s):
        self._maybe_fail(role, rep, "burst")
        if not self.on[role]:
            return {"accepted": n, "throttled": 0, "other": 0}
        cap = int(self.burst_cap + self.rate * window_s)
        acc = min(n, cap)
        return {"accepted": acc, "throttled": n - acc, "other": 0}


# ------------------------------------------------------------------------------------------------ ao vivo
def _utc(t: datetime) -> str:
    """Instante em UTC com Z (vai em query string de REST sem precisar de escape)."""
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LiveBackend:
    """CLI/REST de verdade. Só nasce com as pré-condições de nuvem do SAFETY satisfeitas para o módulo PROBE-* que
    o chama (bo.safety.runner.cloud_preconditions) e com alvos em memória. Não grava resposta nenhuma: só a
    contagem do parser volta ao runner. A carga sintética é um arquivo de zeros em $BO_TMP, apagado no fim."""

    def __init__(self, module: str, cell: str, targets: dict, *, env: dict | None = None, token_fn=None,
                 exec_fn=None, http_fn=None, timeout_s: float = 120.0):
        from bo.safety.runner import cloud_preconditions
        provider = cell.split("/")[1]
        probs = cloud_preconditions(module, provider, env)
        if probs:
            raise ProbeError("backend ao vivo recusado: " + "; ".join(probs), "NO_GO")
        self.cell, self.ops, self.targets = cell, ops_for(cell), targets
        self.env = dict(os.environ if env is None else env)
        self.token_fn, self.exec_fn, self.http_fn = token_fn, exec_fn or self._exec, http_fn or self._http
        self.timeout_s = timeout_s
        self.started_utc: str | None = None
        from .common import tmp
        from .protocol import KIT_PARAMS
        self.payload = Path(tmp()) / f"payload-{os.getpid()}.bin"
        self.payload.write_bytes(b"\0" * KIT_PARAMS["object_size_bytes"])

    def close(self):
        self.payload.unlink(missing_ok=True)

    def _exec(self, argv):
        try:
            p = subprocess.run(argv, env=self.env, capture_output=True, text=True, timeout=self.timeout_s)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise BackendError(f"{argv[0]} não rodou ({type(e).__name__})", "EXEC") from None
        # só a cauda do stderr (mensagem de erro da CLI, ex. "matched no objects"), em memória; nunca gravada
        return {"rc": p.returncode, "stdout": p.stdout, "stderr_tail": (p.stderr or "")[-300:]}

    def _http(self, method, url, body):
        if self.token_fn is None:
            raise BackendError("REST sem fonte de token", "AUTH")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None)
        req.add_header("Authorization", "Bearer " + self.token_fn())
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return {"status": r.status, "body": json.loads(r.read() or b"null")}
        except urllib.error.HTTPError as e:
            return {"status": e.code, "body": None}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise BackendError(f"REST falhou ({type(e).__name__})", "HTTP") from None

    def _call(self, op, ctx):
        r = op.render(ctx)
        if r["kind"] == "cli":
            return self.exec_fn(r["argv"])
        return self.http_fn(r["method"], r["url"], r["body"])

    def _ctx(self, role, rep, extra):
        now = _utc(datetime.now(timezone.utc))
        base = {**self.targets, **extra, "payload_file": str(self.payload), "now_utc": now,
                "since_utc": self.started_utc or now}
        return runner_ctx(self.cell, role, rep, base)

    def act(self, role, rep, ctx):
        self.started_utc = self.started_utc or _utc(datetime.now(timezone.utc))
        op = self.ops["act"]
        exp = float(ctx["now_epoch"]) + float(ctx["ttl_s"])
        extra = {"n": ctx["n"], "expire_epoch": str(int(exp)),
                 "expire_iso": datetime.fromtimestamp(int(exp), TZ).isoformat()}
        c = self._ctx(role, rep, extra)
        times = ctx["n"] if (op.per_item or op.repeat) else 1
        for i in range(1, times + 1):
            raw = self._call(op, {**c, "i": i})
            if not (raw.get("rc") == 0 or raw.get("status") in (200, 201)):
                raise BackendError("ação falhou", "ACT")

    def observe(self, role, rep):
        op = self.ops["observe"]
        c = self._ctx(role, rep, {"n": self._n(role)})
        try:
            if op.per_item:
                raws = [self._call(op, {**c, "i": i}) for i in range(1, c["n"] + 1)]
                return op.parse(raws, c)
            return op.parse(self._call(op, c), c)
        except ParseError as e:
            raise BackendError(str(e), "PARSE") from None

    def _n(self, role):
        from .protocol import KIT_PARAMS
        return KIT_PARAMS["writes_per_key"] if self.cell.startswith("object_versioning") else \
            KIT_PARAMS["items_per_repetition"]

    def burst(self, role, rep, n, window_s):
        raise ProbeError(f"{self.cell}: o kit não tem operação ao vivo de limite de taxa (nenhum caso validado)",
                         "PROTOCOL_UNSUPPORTED")
