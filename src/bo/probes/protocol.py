"""Protocolo congelado de cada tipo de sonda.

Fonte única: $BO_REPO/prereg/probe_types.yaml (PREREG, C22 probe_types 3.0.0), validado pelo validador oficial antes
de qualquer uso. O kit acrescenta só o que o pré-registro deixa para a implementação e declara tudo aqui, com versão
(KIT_PARAMS entra no PROBEKIT.sha256 e no protocol_kit.json): quantas leituras seguidas confirmam um efeito
(consistência eventual), quantas vezes uma operação falha antes de virar erro de infraestrutura e quanto de polling
perdido ainda deixa a repetição valer.

Regras de coerência (por tipo e por caso, antes do sorteio):
  P1  polling.interval <= polling.max_wait <= window.duration
  P2  janela separada do TTL: polling.max_wait >= TTL configurado + window.margin_over_ttl
  P3  repetições >= 1 e tolerância coerente com o tipo (exact => 0)
  P4  limite de taxa: janela, chave, rajada e mecanismo declarados (sem os quatro, PROTOCOL_UNSUPPORTED)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import KIT_VERSION, PROBE_TYPES
from .common import ProbeError, duration_s, prereg_path, sha256_file

# parâmetros do kit (não estão no pré-registro; congelados com a versão do kit)
KIT_PARAMS = {
    "kit_version": KIT_VERSION,
    "confirmations": 2,             # leituras seguidas iguais para aceitar um efeito (consistência eventual)
    "op_retries": 2,                # novas tentativas de uma ação ou leitura antes de contar erro
    "max_lost_poll_fraction": 0.5,  # mais leituras perdidas que isso numa repetição => erro de infraestrutura
    "heartbeat_every_s": 60,        # batida do supervisor durante a espera (D16)
    "object_size_bytes": 1024,      # objeto sintético de 1 KiB, sem conteúdo real
    "items_per_repetition": 3,      # objetos, itens, mensagens ou eventos por repetição (tipos de expiração)
    "writes_per_key": 3,            # versionamento: gravações da mesma chave
    "rate_limit_factor": 3,         # N = 3 × (rajada + taxa × janela)
}


@dataclass(frozen=True)
class Protocol:
    probe_type: str
    protocol_version: str
    preconditions: tuple
    negative_control: dict
    repetitions: int
    tolerance_kind: str
    tolerance_value: float
    poll_interval_s: float
    max_wait_s: float
    window_s: float
    margin_over_ttl_s: float
    cost_limit_usd: float
    raw: dict = field(compare=False, repr=False, default_factory=dict)

    @property
    def needs_supervisor(self) -> bool:
        return any("supervisor" in p for p in self.preconditions)

    def coherence(self, ttl_s: float) -> list[str]:
        """Problemas P1–P3 para um TTL configurado (0 quando o tipo não tem TTL)."""
        out = []
        if not (0 < self.poll_interval_s <= self.max_wait_s <= self.window_s):
            out.append("P1: exige 0 < polling.interval <= polling.max_wait <= window.duration")
        if self.max_wait_s < ttl_s + self.margin_over_ttl_s:
            out.append(f"P2: polling.max_wait ({self.max_wait_s:.0f} s) < TTL configurado ({ttl_s:.0f} s) + "
                       f"margem ({self.margin_over_ttl_s:.0f} s)")
        if self.repetitions < 1:
            out.append("P3: repetições < 1")
        if self.tolerance_kind == "exact" and self.tolerance_value != 0:
            out.append("P3: tolerância exact com valor diferente de 0")
        return out


def validate_contract(path: Path) -> list[str]:
    """Validador oficial do C22 (schema + regras)."""
    from bo.contracts import validate as V
    r = V.validate("C22_probe_types", Path(path))
    return list(r.errors)


def load(path: Path | None = None, check_contract: bool = True) -> dict[str, Protocol]:
    p = Path(path or prereg_path())
    if check_contract:
        errs = validate_contract(p)
        if errs:
            raise ProbeError(f"probe_types.yaml não confere com o C22: {errs[:3]}", "CONTRACT")
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    out = {}
    for t in doc["probe_types"]:
        out[t["probe_type"]] = Protocol(
            probe_type=t["probe_type"], protocol_version=doc["protocol_version"],
            preconditions=tuple(t["preconditions"]), negative_control=dict(t["negative_control"]),
            repetitions=int(t["repetitions"]), tolerance_kind=t["tolerance"]["kind"],
            tolerance_value=float(t["tolerance"]["value"]), poll_interval_s=duration_s(t["polling"]["interval"]),
            max_wait_s=duration_s(t["polling"]["max_wait"]), window_s=duration_s(t["window"]["duration"]),
            margin_over_ttl_s=duration_s(t["window"]["margin_over_ttl"]),
            cost_limit_usd=float(t["cost_limit"]["amount"]), raw=t)
    missing = [t for t in PROBE_TYPES if t not in out]
    if missing:
        raise ProbeError(f"probe_types.yaml sem os tipos {missing}", "PROTOCOL")
    return out


def source_info(path: Path | None = None) -> dict:
    p = Path(path or prereg_path())
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    return {"path": "$BO_REPO/prereg/probe_types.yaml", "sha256": sha256_file(p),
            "protocol_version": doc["protocol_version"], "module": doc["module"]}


# ------------------------------------------------------------------------------------- limite de taxa (P4)
RATE_LIMIT_FIELDS = ("window", "key", "burst", "mechanism")
MECHANISMS = ("token_bucket", "fixed_window")


@dataclass(frozen=True)
class RateLimitSpec:
    window_s: float      # período de renovação
    key: str             # por chave de assinatura, por IP de origem ou total
    burst: int           # capacidade do balde (0 em janela fixa)
    mechanism: str       # token_bucket | fixed_window
    rate_per_s: float    # taxa sustentada

    def expected_accepted(self) -> float:
        """Pedidos aceitos esperados quando N chega todo dentro de uma janela de renovação."""
        if self.mechanism == "token_bucket":
            return self.burst + self.rate_per_s * self.window_s
        return self.rate_per_s * self.window_s

    def n_requests(self) -> int:
        return int(KIT_PARAMS["rate_limit_factor"] * (self.burst + self.rate_per_s * self.window_s))


def rate_limit_declared(documented: dict) -> list[str]:
    """P4: campos do SERVICE-EVIDENCE (documented) que faltam para o limite de taxa."""
    return [f for f in RATE_LIMIT_FIELDS if not documented.get(f)]


def rate_limit_spec(d: dict) -> RateLimitSpec:
    miss = [f for f in (*RATE_LIMIT_FIELDS, "rate_per_s") if d.get(f) in (None, "")]
    if miss:
        raise ProbeError(f"limite de taxa sem {', '.join(miss)} declarado(s) (P4)", "PROTOCOL_UNSUPPORTED")
    mech = str(d["mechanism"]).replace(" ", "_").lower()
    if mech not in MECHANISMS:
        raise ProbeError(f"mecanismo de limite de taxa desconhecido: {d['mechanism']!r}", "PROTOCOL_UNSUPPORTED")
    spec = RateLimitSpec(window_s=duration_s(str(d["window"])), key=str(d["key"]), burst=int(d["burst"]), mechanism=mech, rate_per_s=float(d["rate_per_s"]))
    if spec.window_s <= 0 or spec.rate_per_s <= 0 or spec.burst < 0:
        raise ProbeError("limite de taxa com janela, taxa ou rajada fora do domínio", "PROTOCOL_UNSUPPORTED")
    return spec
