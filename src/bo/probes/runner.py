"""Runner de um lado de um par de sonda: só grava a observação LOCAL (C22 observation) e o rastro de contagens.
Nunca compara com o outro lado (isso é do PROBE-JOIN).

Sequência:
  1. suporte: o tipo × provedor tem de estar validado em deploy/probes/protocol_support.json (senão a sonda nem
     foi sorteada: recusa com PROTOCOL_UNSUPPORTED, sem ação nenhuma);
  2. protocolo coerente com o TTL configurado (P1–P4 de protocol.py);
  3. pré-condições de execução: leitura de volta PERSISTED nas duas implantações (caso e controle negativo) e,
     para janela longa, supervisor com heartbeat (D16). Falhou aqui: observação com errors = attempts e
     negative_control_ok = false (o PROBE-JOIN vê INFRA_ERROR), e o motivo vai para o rastro;
  4. repetições: cada uma com a configuração ligada (caso) e desligada (controle negativo), agidas no mesmo t0;
  5. polling no intervalo do protocolo até max_wait, com leitura final no fim da janela; batida do supervisor
     durante a espera;
  6. consistência eventual: efeito só conta depois de KIT_PARAMS.confirmations leituras seguidas; leitura que volta
     atrás é registrada como oscilação e zera a contagem;
  7. censura: efeito ainda não confirmado no fim da janela => not_observed (NOT_OBSERVED_IN_WINDOW no join), nunca
     "igual";
  8. erro de infraestrutura: ação que falha depois das novas tentativas, mais leituras perdidas que o limite, leitura
     final perdida ou supervisor perdido => errors;
  9. controle negativo: ok só se nunca houve KIT_PARAMS.confirmations leituras seguidas fora do efeito oposto e a
     leitura final deu o efeito oposto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import KIT_VERSION
from .backends import BackendError, Clock
from .common import TZ, ProbeError, canon, iso
from .kinds import EFFECT, OPPOSITE, Kind
from .protocol import KIT_PARAMS, Protocol, RateLimitSpec

ROLES = ("case", "control")
SHORT_WINDOW_S = 2 * 3600  # acima disso, janela longa: supervisor obrigatório (budget.short_window_hours do SAFETY)


class SupervisorLost(ProbeError):
    def __init__(self, msg):
        super().__init__(msg, "SUPERVISOR")


@dataclass(frozen=True)
class ProbeCase:
    pair_case_id: str
    side: str
    probe_type: str
    provider: str
    ttl_s: float = 0.0
    rate_limit: RateLimitSpec | None = None

    def check(self):
        if not self.pair_case_id.startswith("PC-") or self.side not in ("A", "B"):
            raise ProbeError("caso de sonda sem pair_case_id PC-* ou lado A/B", "CASE")


@dataclass
class Rep:
    role: str
    rep: int
    open: bool = True
    result: str | None = None  # case: observed | not_observed | error ; control: ok | fail | error
    polls: list = field(default_factory=list)
    lost: int = 0
    run_effect: int = 0      # leituras seguidas no efeito (caso)
    run_bad: int = 0         # leituras seguidas fora do oposto (controle)
    flaps: int = 0
    first_effect_s: float | None = None
    reason: str = ""

    def trace(self) -> dict:
        return {"role": self.role, "rep": self.rep, "result": self.result, "reason": self.reason,
                "lost_polls": self.lost, "flaps": self.flaps, "effect_at_s": self.first_effect_s,
                "polls": self.polls}


class Runner:
    def __init__(self, case: ProbeCase, protocol: Protocol, backend, *, clock: Clock, support: dict,
                 supervisor=None, readback: dict | None = None, grace_s: float = 600.0):
        case.check()
        if protocol.probe_type != case.probe_type:
            raise ProbeError("protocolo de outro tipo de sonda", "PROTOCOL")
        self.case, self.p, self.b, self.clock = case, protocol, backend, clock
        self.support, self.sup, self.readback = support, supervisor, readback or {}
        self.grace_s = grace_s
        self.k = KIT_PARAMS["confirmations"]
        n = KIT_PARAMS["writes_per_key"] if case.probe_type == "object_versioning" else \
            KIT_PARAMS["items_per_repetition"]
        if case.probe_type == "rate_limit":
            if case.rate_limit is None:
                raise ProbeError("limite de taxa sem janela, chave, rajada e mecanismo (P4)", "PROTOCOL_UNSUPPORTED")
            n = case.rate_limit.n_requests()
        self.kind = Kind(case.probe_type, protocol.tolerance_kind, protocol.tolerance_value, n)
        self.reps = [Rep(r, i) for i in range(1, protocol.repetitions + 1) for r in ROLES]
        self.events: list[dict] = []
        self.beats: list[float] = []  # instantes (monotônicos) das batidas aceitas
        self.t0 = self.t_obs = 0.0

    # ----------------------------------------------------------------------------------- pré-condições
    def preflight(self) -> list[str]:
        key = f"{self.case.probe_type}/{self.case.provider}"
        st = self.support.get(key)
        if st != "validated":
            raise ProbeError(f"{key}: suporte {st or 'ausente'} em protocol_support.json; fora do sorteio",
                             "PROTOCOL_UNSUPPORTED")
        coh = self.p.coherence(self.case.ttl_s)
        if coh:
            raise ProbeError(f"{key}: protocolo incoerente: {'; '.join(coh)}", "PROTOCOL")
        probs = []
        for role in ROLES:
            if self.readback.get(role) != "PERSISTED":
                probs.append(f"leitura de volta do {role} não é PERSISTED")
        if self.long_window():
            if self.sup is None:
                probs.append("janela longa sem supervisor (D16)")
            else:
                try:
                    self.sup.beat()
                    self.beats.append(self.clock.monotonic())
                except Exception as e:  # noqa: BLE001 - qualquer falha do transporte é supervisor ausente
                    probs.append(f"supervisor não respondeu ({type(e).__name__})")
        return probs

    def long_window(self) -> bool:
        return self.p.needs_supervisor or self.p.window_s > SHORT_WINDOW_S

    # ----------------------------------------------------------------------------------- espera e batida
    def _beat(self):
        if self.sup is None:
            return
        try:
            self.sup.beat()
            self.beats.append(self.clock.monotonic())
        except Exception as e:  # noqa: BLE001
            now = self.clock.monotonic()
            self.events.append({"t_s": round(now - self.t0, 3), "event": "heartbeat_failed",
                                "error": type(e).__name__})
            last_ok = self.beats[-1] if self.beats else self.t0
            if now - last_ok >= self.grace_s:  # mesma régua do supervisor_heartbeat: intervalo < carência
                raise SupervisorLost("supervisor sem heartbeat aceito durante a carência") from None

    def wait_until(self, t: float):
        every = float(KIT_PARAMS["heartbeat_every_s"])
        while True:
            now = self.clock.monotonic()
            if now >= t:
                return
            self.clock.sleep(min(every, t - now))
            if self.long_window():
                self._beat()

    # ----------------------------------------------------------------------------------- operações
    def _retry(self, fn, *a):
        last = None
        for _ in range(1 + KIT_PARAMS["op_retries"]):
            try:
                return fn(*a)
            except BackendError as e:
                last = e
        raise last

    # ----------------------------------------------------------------------------------- execução
    def run(self) -> tuple[dict, list[dict]]:
        self.t0 = self.clock.monotonic()
        self.started_at = self.clock.wall()
        probs = self.preflight()
        if probs:
            for r in self.reps:
                r.open, r.result, r.reason = False, "error", "; ".join(probs)
            self.events.append({"t_s": 0.0, "event": "precondition_failed", "detail": "; ".join(probs)})
        else:
            try:
                if self.kind.family == "throttle":
                    self._run_throttle()
                else:
                    self._run_polling()
            except SupervisorLost as e:
                for r in self.reps:
                    if r.open:
                        r.open, r.result, r.reason = False, "error", str(e)
        return self.observation(), self.trace()

    def _act_all(self):
        ctx = {"ttl_s": self.case.ttl_s, "now_epoch": self.clock.wall_epoch(), "n": self.kind.n}
        for r in self.reps:
            try:
                # sem nova tentativa da ação inteira (repetir gravações já feitas mudaria a contagem); o backend
                # tenta de novo só a operação atômica que falhou
                self.b.act(r.role, r.rep, ctx, retries=KIT_PARAMS["op_retries"])
            except BackendError as e:
                r.open, r.result, r.reason = False, "error", f"ação falhou: {e.code}"
            if self.long_window():
                self._beat()

    def _ticks(self) -> list[float]:
        n = int(self.p.max_wait_s // self.p.poll_interval_s)
        ticks = [self.t_obs + i * self.p.poll_interval_s for i in range(1, n + 1)]
        end = self.t_obs + self.p.max_wait_s
        if not ticks or ticks[-1] < end - 1e-9:
            ticks.append(end)
        return ticks

    def _run_polling(self):
        if self.long_window():
            self._beat()
        self._act_all()
        self.t_obs = self.clock.monotonic()  # o polling conta a partir do fim das ações
        ticks = self._ticks()
        for i, t in enumerate(ticks):
            if not any(r.open for r in self.reps):
                break
            final = i == len(ticks) - 1
            if not final and self.clock.monotonic() > t + self.p.poll_interval_s / 2:
                # leitura anterior atrasou: pular o tick vencido em vez de ler duas vezes colado
                self.events.append({"t_s": round(self.clock.monotonic() - self.t_obs, 3), "event": "tick_skipped",
                                    "tick_s": round(t - self.t_obs, 3)})
                continue
            self.wait_until(t)
            for r in self.reps:
                if r.open:
                    self._poll(r, self.clock.monotonic() - self.t_obs, final)
                    if self.long_window():
                        self._beat()
        for r in self.reps:
            if r.open:  # janela fechada sem decisão: não acontece com a leitura final, mas fica explícito
                self._close_at_deadline(r, final_lost=True)

    def _poll(self, r: Rep, t_s: float, final: bool):
        try:
            s = self.kind.check_sample(self._retry(self.b.observe, r.role, r.rep))
        except (BackendError, ValueError) as e:
            r.lost += 1
            r.polls.append({"t_s": round(t_s, 3), "lost": True, "code": getattr(e, "code", "PARSE")})
            if r.role == "case" and r.run_effect:
                r.run_effect, r.first_effect_s = 0, None  # leitura perdida quebra "leituras seguidas"
            if final:
                self._close_at_deadline(r, final_lost=True)
            return
        st = self.kind.state(s)
        r.polls.append({"t_s": round(t_s, 3), "state": st, **s})
        if r.role == "case":
            if st == EFFECT:
                if r.run_effect == 0:
                    r.first_effect_s = round(t_s, 3)
                r.run_effect += 1
                if r.run_effect >= self.k:
                    r.open, r.result = False, "observed"
                    r.reason = f"efeito confirmado por {self.k} leituras seguidas"
                    return
            else:
                if r.run_effect:
                    r.flaps += 1
                r.run_effect, r.first_effect_s = 0, None
        else:
            if st != OPPOSITE:
                r.run_bad += 1
                if r.run_bad >= self.k:
                    r.open, r.result = False, "fail"
                    r.reason = f"controle negativo fora do efeito oposto em {self.k} leituras seguidas ({st})"
                    return
            else:
                if r.run_bad:
                    r.flaps += 1
                r.run_bad = 0
        if final:
            self._close_at_deadline(r, final_lost=False, last_state=st)

    def _close_at_deadline(self, r: Rep, final_lost: bool, last_state: str | None = None):
        r.open = False
        n_polls = len(r.polls)
        too_lost = n_polls and r.lost / n_polls > KIT_PARAMS["max_lost_poll_fraction"]
        if final_lost or too_lost:
            r.result = "error"
            r.reason = "leitura final perdida" if final_lost else f"{r.lost} de {n_polls} leituras perdidas"
            return
        if r.role == "case":
            r.result = "not_observed"
            r.reason = "censura: efeito não confirmado até o fim da janela"
        else:
            r.result = "ok" if last_state == OPPOSITE else "fail"
            r.reason = "efeito oposto na leitura final" if r.result == "ok" else \
                f"leitura final fora do efeito oposto ({last_state})"

    def _run_throttle(self):
        spec: RateLimitSpec = self.case.rate_limit
        expected = spec.expected_accepted()
        deadline = self.t0 + self.p.max_wait_s
        refill = max(2 * spec.window_s, self.p.poll_interval_s)
        by_rep: dict[int, list[Rep]] = {}
        for r in self.reps:
            by_rep.setdefault(r.rep, []).append(r)
        for rep in sorted(by_rep):
            for r in by_rep[rep]:
                now = self.clock.monotonic()
                if now + spec.window_s > deadline:
                    r.open = False
                    r.result = "not_observed" if r.role == "case" else "error"
                    r.reason = "censura: repetição não coube na janela" if r.role == "case" else \
                        "controle não coube na janela"
                    continue
                try:
                    # sem nova tentativa: repetir a rajada mudaria o estado do balde
                    s = self.kind.check_sample(self.b.burst(r.role, r.rep, self.kind.n, spec.window_s))
                except (BackendError, ValueError) as e:
                    r.open, r.result, r.reason = False, "error", f"rajada falhou: {getattr(e, 'code', 'PARSE')}"
                    continue
                if s["accepted"] + s["throttled"] + s.get("other", 0) != self.kind.n:
                    r.open, r.result = False, "error"
                    r.reason = "rajada com contagens que não somam N"
                    r.polls.append({"t_s": round(self.clock.monotonic() - self.t0, 3), "lost": True,
                                    "code": "COUNT"})
                    continue
                st = self.kind.state(s, expected_accepted=expected)
                r.polls.append({"t_s": round(self.clock.monotonic() - self.t0, 3), "state": st,
                                "expected_accepted": round(expected, 3), **s})
                r.open = False
                if s.get("other", 0) / max(1, self.kind.n) > KIT_PARAMS["max_lost_poll_fraction"]:
                    r.result, r.reason = "error", "respostas fora de 2xx/429 acima do limite"
                elif r.role == "case":
                    r.result = "observed" if st == EFFECT else "not_observed"
                    r.reason = {EFFECT: "limitação com aceitos dentro da tolerância",
                                OPPOSITE: "nenhuma limitação na janela"}.get(st, "limitação com aceitos fora da tolerância")
                else:
                    r.result = "ok" if st == OPPOSITE else "fail"
                    r.reason = "nenhuma limitação" if st == OPPOSITE else "controle limitado"
            self.wait_until(min(deadline, self.clock.monotonic() + refill))

    # ----------------------------------------------------------------------------------- saída
    def observation(self) -> dict:
        case = [r for r in self.reps if r.role == "case"]
        ctl = [r for r in self.reps if r.role == "control"]
        c = {"attempts": len(case), "observed": sum(r.result == "observed" for r in case),
             "not_observed": sum(r.result == "not_observed" for r in case),
             "errors": sum(r.result == "error" for r in case)}
        assert c["observed"] + c["not_observed"] + c["errors"] == c["attempts"], "C22-COUNTS"
        return {"observation_id": f"OBS-{self.case.pair_case_id[3:]}-{self.case.side}",
                "pair_case_id": self.case.pair_case_id, "side": self.case.side, "provider": self.case.provider,
                "probe_type": self.case.probe_type, "timestamp": iso(self.clock.wall()),
                "protocol_version": self.p.protocol_version, "counts": c,
                "negative_control_ok": all(r.result == "ok" for r in ctl)}

    def heartbeat_summary(self) -> dict:
        """Continuidade do heartbeat (D16): maior intervalo sem batida aceita, do início ao fim da execução."""
        end = self.clock.monotonic()
        pts = [self.t0, *self.beats, end]
        gap = max((b - a for a, b in zip(pts, pts[1:])), default=0.0)
        return {"required": self.long_window(), "beats": len(self.beats), "max_gap_s": round(gap, 3),
                "grace_s": self.grace_s, "duration_s": round(end - self.t0, 3)}

    def trace(self) -> list[dict]:
        head = {"pair_case_id": self.case.pair_case_id, "side": self.case.side, "provider": self.case.provider,
                "probe_type": self.case.probe_type, "protocol_version": self.p.protocol_version,
                "kit_version": KIT_VERSION, "started_at": iso(self.started_at), "ended_at": iso(self.clock.wall()),
                "ttl_s": self.case.ttl_s, "n": self.kind.n, "confirmations": self.k, "events": self.events,
                "heartbeat": self.heartbeat_summary()}
        return [{**head, **r.trace()} for r in self.reps]


def write_local(out_dir: Path, observation: dict, trace: list[dict]) -> None:
    """Grava só no diretório do módulo PROBE-*: observations.jsonl (C22, conferido pelo validador oficial) e
    probe_trace.jsonl (contagens e tempos). Nada de conteúdo, nome de recurso ou identificador de conta."""
    from bo.contracts import validate as V
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    obs_path = out_dir / "observations.jsonl"
    prev = obs_path.read_text(encoding="utf-8") if obs_path.exists() else ""
    if any(json.loads(x).get("observation_id") == observation["observation_id"]
           for x in prev.splitlines() if x.strip()):
        raise ProbeError(f"observação {observation['observation_id']} já gravada", "DUPLICATE")
    tmp = out_dir / ".observations.check.jsonl"
    tmp.write_text(prev + canon(observation) + "\n", encoding="utf-8")
    res = V.validate("C22_observations", tmp)
    if not res.ok:
        tmp.unlink()
        raise ProbeError(f"observação não confere com o C22: {res.errors[:2]}", "CONTRACT")
    tmp.replace(obs_path)
    with open(out_dir / "probe_trace.jsonl", "a", encoding="utf-8") as f:
        for t in trace:
            f.write(canon(t) + "\n")


def wall_from_epoch(x: float) -> datetime:
    return datetime.fromtimestamp(x, TZ).replace(microsecond=0)
