"""Efeito de cada tipo de sonda: o que a leitura conta, quando o efeito configurado foi observado e qual é o efeito
oposto que o controle negativo tem de dar (a mesma sonda com a configuração desligada).

Três famílias:
  versions   object_versioning: a mesma chave gravada W vezes; efeito = W versões listadas; oposto = 1 versão
  expiry     object_lifecycle, item_ttl, queue_retention, log_retention: N objetos/itens/mensagens/eventos
             sintéticos; efeito = nenhum presente (expirou); oposto = os N presentes no fim da janela
  throttle   rate_limit: N pedidos numa janela de renovação; efeito = houve limitação (429) e os aceitos batem com
             o esperado dentro da tolerância; oposto = nenhuma limitação

Estado de uma leitura: "effect", "opposite" ou "partial" (nem um nem outro, ex. 2 de 3 expirados). A leitura é só
contagem; conteúdo nunca entra.
"""

from __future__ import annotations

from dataclasses import dataclass

FAMILY = {"object_versioning": "versions", "object_lifecycle": "expiry", "item_ttl": "expiry",
          "queue_retention": "expiry", "log_retention": "expiry", "rate_limit": "throttle"}
EFFECT, OPPOSITE, PARTIAL = "effect", "opposite", "partial"


def within(observed: float, expected: float, kind: str, value: float) -> bool:
    if kind == "exact":
        return observed == expected
    if kind == "absolute":
        return abs(observed - expected) <= value
    if kind == "relative":
        return abs(observed - expected) <= value * abs(expected)
    raise ValueError(f"tolerância desconhecida: {kind}")


@dataclass(frozen=True)
class Kind:
    probe_type: str
    tolerance_kind: str
    tolerance_value: float
    n: int  # gravações por chave (versions), itens (expiry) ou pedidos (throttle)

    @property
    def family(self) -> str:
        return FAMILY[self.probe_type]

    def sample_keys(self) -> tuple:
        return {"versions": ("versions",), "expiry": ("present",),
                "throttle": ("accepted", "throttled")}[self.family]

    def check_sample(self, s: dict) -> dict:
        """Amostra só com contagens inteiras não negativas (nada de conteúdo)."""
        out = {}
        for k in self.sample_keys():
            v = s.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"amostra sem contagem {k} válida")
            out[k] = v
        extra = set(s) - set(self.sample_keys()) - {"other"}
        if extra:
            raise ValueError(f"amostra com campos fora do contrato do kit: {sorted(extra)}")
        if "other" in s:
            out["other"] = int(s["other"])
        return out

    def state(self, s: dict, expected_accepted: float | None = None) -> str:
        s = self.check_sample(s)
        if self.family == "versions":
            if within(s["versions"], self.n, self.tolerance_kind, self.tolerance_value):
                return EFFECT
            return OPPOSITE if s["versions"] == 1 else PARTIAL
        if self.family == "expiry":
            if s["present"] > self.n:
                return PARTIAL  # mais do que gravado: leitura incoerente, nunca conta como efeito
            if within(self.n - s["present"], self.n, self.tolerance_kind, self.tolerance_value):
                return EFFECT
            return OPPOSITE if s["present"] == self.n else PARTIAL
        # throttle
        if expected_accepted is None:
            raise ValueError("limite de taxa sem aceitos esperados")
        if s["throttled"] == 0:
            return OPPOSITE
        if within(s["accepted"], expected_accepted, self.tolerance_kind, self.tolerance_value):
            return EFFECT
        return PARTIAL
