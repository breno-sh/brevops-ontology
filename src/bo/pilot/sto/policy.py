"""Política de perda do piloto sto: UMA política, a mesma nos três controles (o sha dela vai para controls.json).

  P1  unidade completa: um caso só desce (lowering) se todo valor de configuração da fatia foi transportado; valor
      bloqueado bloqueia a unidade (código do primeiro bloqueio). Nada de unidade parcial: perda não declarada de
      valor da fatia seria perda silenciosa.
  P2  fora da fatia: átomo sem conceito (bo:UNGLOSSED) fica no rastro como NO_REALIZATION e não bloqueia.
  P3  contexto: conceito de posicionamento (localização) não transportado vira contexto declarado no plano.
  P4  perda de campo: cada item do loss_contract da alegação vira perda tipada no passo do plano
      (LOSS_<TIPO>), no campo de destino.
  P5  perda de efeito (vocabulário do oráculo, MANDATORY.json loss_codes): perda de campo cobre o efeito da classe
      de configuração do conceito do campo; alcance maior que o traduzido (inferido) é SCOPE_WIDENED.
      EARLY_DELETION, EARLY_EXPIRATION e PUBLIC_WIDENED nunca são cobríveis: a política não os declara.
  P6  inconsistência do ABox de origem sob o TBox do controle bloqueia a unidade.
"""

from __future__ import annotations

from . import common as C
from . import tbox as T

POLICY_VERSION = "1.0.0"
VERDICT_BLOCK = {"UNPROVEN": "UNPROVEN", "CONTESTED": "UNPROVEN", "REFUTED_BY_RULE": "REFUTED_BY_RULE",
                 "AMBIGUOUS": "AMBIGUOUS_TARGET"}
EFFECTS_BY_CLASS = {
    "VersioningSetting": ("VERSIONING_STATE_DIFFERS",),
    "LifecycleRule": ("RETAINED_LONGER", "EXPIRED_LATER"),
    "LifecycleSetting": ("RETAINED_LONGER", "EXPIRED_LATER"),
    "AccessGrantSetting": ("ACCESS_NARROWED",),
    "PublicAccessBlockSetting": ("ACCESS_NARROWED",),
    "AclModeSetting": ("ACCESS_NARROWED",),
}
NEVER_DECLARED = ("EARLY_DELETION", "EARLY_EXPIRATION", "PUBLIC_WIDENED")


def describe() -> dict:
    return {"version": POLICY_VERSION, "rules": ["P1", "P2", "P3", "P4", "P5", "P6"],
            "effects_by_class": {k: list(v) for k, v in EFFECTS_BY_CLASS.items()},
            "never_declared": list(NEVER_DECLARED), "verdict_block": VERDICT_BLOCK}


def sha256() -> str:
    return C.sha256_obj(describe())


def field_loss_code(loss: dict) -> str:
    kind = (loss.get("kind") or "semantic").upper()
    return "LOSS_" + "".join(ch if ch.isalnum() else "_" for ch in kind)


def atom_of_field(provider: str, rtype: str, fld: str) -> str:
    return f"{provider}:{rtype}:" + ".".join(p for p in fld.split(".") if not p.isdigit())


def field_class(provider: str, rtype: str, fld: str, concept_of) -> str | None:
    """Classe do conceito do campo; campo com ':' já é um átomo (perda declarada no átomo de origem)."""
    atom = fld if fld.count(":") >= 2 else atom_of_field(provider, rtype, fld)
    return T.concept_class(concept_of(atom))


def effects_of(code: str, provider: str, rtype: str, fld: str, concept_of) -> set:
    if code == "SCOPE_WIDENED":
        return {"SCOPE_WIDENED"}
    if not code.startswith("LOSS_"):
        return set()
    cls = field_class(provider, rtype, fld, concept_of)
    return set(EFFECTS_BY_CLASS.get(cls or "", ()))
