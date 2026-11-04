"""Juiz de tradução: compara a decisão da configuração de origem com a da configuração-alvo, fluxo a fluxo.

Regras (E4 do pilot_exit.yaml):
  origem DENY e alvo ALLOW              -> negative_carried (REJECT sempre; perda declarada não cobre)
  origem UNKNOWN e alvo ALLOW           -> undetermined (permissão sem prova; só a perda LOSS-NET-UNKNOWN-INPUT cobre)
  origem definida e alvo diferente      -> divergência; coberta só por perda declarada do catálogo da direção
                                           que cubra aquele tipo de divergência; senão silent_loss (REJECT)
  origem UNKNOWN e alvo DENY            -> divergência conservadora; idem
  alvo inválido (validade INVALID)      -> REJECT (o provedor recusa a configuração)
Veredito: REJECT > UNDETERMINED > ACCEPT_WITH_DECLARED_LOSS > ACCEPT.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import evaluate_fixture
from .model import ALLOW, DENY, UNKNOWN

DIRECTIONS_PATH = Path(__file__).resolve().parent.parent / "directions.json"


def catalog() -> dict:
    return json.loads(DIRECTIONS_PATH.read_text(encoding="utf-8"))


def _losses_for(direction: str, cat: dict) -> dict:
    d = cat["directions"].get(direction)
    if d is None:  # mesmo provedor nos dois lados: nenhuma perda é declarável
        return {}
    return {lid: cat["loss_catalog"][lid] for lid in d["expected_losses"]}


def judge(source_fx: dict, target_fx: dict, declared_losses: list, direction: str | None = None,
          reading: str = "default", source_decisions: dict | None = None) -> dict:
    cat = catalog()
    direction = direction or f"{source_fx['provider']}->{target_fx['provider']}"
    allowed = _losses_for(direction, cat)
    src = source_decisions or evaluate_fixture(source_fx, reading)["decisions"]
    tev = evaluate_fixture(target_fx, reading)
    tgt = tev["decisions"]
    out = {"direction": direction, "per_flow": {}, "negatives_carried": [], "silent_losses": [],
           "undetermined": [], "covered": [], "undeclarable_losses": [], "target_validity": tev["validity"]["value"]}
    cover = {}
    for dl in declared_losses or []:
        if dl["loss_id"] not in allowed:
            out["undeclarable_losses"].append(dl["loss_id"])
            continue
        for f in dl.get("flows", []):
            cover.setdefault(f, set()).update(allowed[dl["loss_id"]]["covers"])
    missing = sorted(set(src) - set(tgt))
    if missing:
        raise ValueError(f"fluxos da origem ausentes no alvo: {missing}")
    for fid, s in src.items():
        sv, tv = s["value"], tgt[fid]["value"]
        kind = f"{sv}->{tv}"
        if sv == tv:
            res = "equal"
        elif sv == DENY and tv == ALLOW:
            res = "negative_carried"
        elif kind in cover.get(fid, set()):
            res = "covered"
        elif sv == UNKNOWN and tv == ALLOW:
            res = "undetermined"
        else:
            res = "silent_loss"
        out["per_flow"][fid] = {"source": sv, "target": tv, "result": res}
        if res != "equal":
            out[{"negative_carried": "negatives_carried", "covered": "covered", "undetermined": "undetermined",
                 "silent_loss": "silent_losses"}[res]].append(fid)
    if out["negatives_carried"] or out["silent_losses"] or out["target_validity"] == "INVALID":
        v = "REJECT"
    elif out["undetermined"]:
        v = "UNDETERMINED"
    elif out["covered"]:
        v = "ACCEPT_WITH_DECLARED_LOSS"
    else:
        v = "ACCEPT"
    out["verdict"] = v
    return out
