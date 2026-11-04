"""Custo estimado de cada template pelo plan_guard do SAFETY (bo.safety.plan_check), sobre o plano sintético dos
dois lados (caso e controle negativo), com o uso que o protocolo implica declarado por endereço:

  requisições  repetições × (ações + leituras × chamadas por leitura) × (1 + novas tentativas), no recurso de dados
  armazenamento  objetos/versões/itens/mensagens × 1 KiB, pelo tempo da janela
  tráfego      cada chamada devolve no máximo RESPONSE_BYTES_BOUND (saída da nuvem para o runner)
  horas        TTL do runner = janela do protocolo arredondada para cima (o supervisor destrói no prazo)
  resíduo      o max_residual_usd da tabela do SAFETY

O total do caso tipo × provedor (caso + controle) tem de ficar abaixo do cost_limit do tipo no PREREG.
"""

from __future__ import annotations

import math

from .cells import IMPL
from .protocol import KIT_PARAMS, Protocol
from . import templates as T

RESPONSE_BYTES_BOUND = 16 * 1024
GIB = float(1 << 30)
BATCH_ID = "b-probekit-offline"
CATEGORIES = ("compute", "storage", "traffic", "requests", "one_time", "residual")


def regions(table: dict) -> dict:
    return {p: table["providers"][p]["regions_allowed"][0] for p in table["providers"]}


def n_ticks(p: Protocol) -> int:
    n = int(p.max_wait_s // p.poll_interval_s)
    return n + (0 if n * p.poll_interval_s >= p.max_wait_s - 1e-9 else 1)


def per_rep_calls(cell: str, p: Protocol) -> dict:
    """Chamadas e bytes de UMA repetição de UM lado (limite superior: todas as leituras até max_wait)."""
    from .ops import OPS
    t = cell.split("/")[0]
    n = KIT_PARAMS["writes_per_key"] if t == "object_versioning" else KIT_PARAMS["items_per_repetition"]
    obs = OPS[cell]["observe"]
    reads = n_ticks(p) * (n if obs.per_item else 1)
    retry = 1 + KIT_PARAMS["op_retries"]
    return {"acts": n * retry, "reads": reads * retry, "stored_bytes": n * KIT_PARAMS["object_size_bytes"]}


def usage_for(cell: str, p: Protocol, insts: list) -> dict:
    impl = IMPL[cell]
    c = per_rep_calls(cell, p)
    data_addrs = [i.address for i in insts if i.type in impl.data_types]
    if not data_addrs:
        raise ValueError(f"{cell}: plano sem recurso de dados ({impl.data_types})")
    reps = p.repetitions
    usage = {}
    if impl.per_rep:
        # um alvo por repetição: ação no primeiro tipo de dados, leitura no último (tópico -> assinatura)
        by_type = {t: [i.address for i in insts if i.type == t] for t in impl.data_types}
        act_t, read_t = impl.data_types[0], impl.data_types[-1]
        for t, addrs in by_type.items():
            if len(addrs) != reps:
                raise ValueError(f"{cell}: {len(addrs)} recursos {t} para {reps} repetições")
        for t, addrs in by_type.items():
            for a in addrs:
                req = (c["acts"] if t == act_t else 0) + (c["reads"] if t == read_t else 0)
                usage[a] = {"requests_millions": req / 1e6,
                            "storage_gb": (c["stored_bytes"] if t == act_t else 0) / GIB,
                            "egress_gb": req * RESPONSE_BYTES_BOUND / GIB}
        return usage
    req = reps * (c["acts"] + c["reads"])
    share = 1.0 / len(data_addrs)
    for a in data_addrs:
        usage[a] = {"requests_millions": req * share / 1e6, "storage_gb": reps * c["stored_bytes"] * share / GIB,
                    "egress_gb": req * share * RESPONSE_BYTES_BOUND / GIB}
    return usage


def names_for(insts: list) -> dict:
    from bo.safety.common import synthetic_name
    return {it.address: synthetic_name(BATCH_ID, n) for n, it in enumerate(insts, 1)}


def check_side(cell: str, side: str, p: Protocol, table: dict, now=None) -> dict:
    """plan_guard sobre o plano sintético de um lado: achados (códigos) e custo por categoria."""
    from bo.safety import plan_check
    from bo.safety.common import iso, now_dt, tag_value
    provider = cell.split("/")[1]
    impl = IMPL[cell]
    region = regions(table)[provider]
    run_tag = tag_value(BATCH_ID)
    v0 = T.synthetic_vars(cell, run_tag, {}, region, impl.runner_inputs)
    _, insts0 = T.synthetic_plan(cell, side, v0)
    names = names_for(insts0)  # plano 2 do SafeRun: com os nomes sintéticos do manifesto de intenção
    plan, insts = T.synthetic_plan(cell, side, T.synthetic_vars(cell, run_tag, names, region, impl.runner_inputs))
    now = now or now_dt()
    ttl_h = int(math.ceil(p.window_s / 3600.0))
    ctx = {"module": "PROBEKIT", "provider": provider, "batch_id": BATCH_ID, "run_tag": run_tag,
           "ttl_hours": ttl_h, "window_hours": p.window_s / 3600.0, "region": region,
           "usage": usage_for(cell, p, insts), "spent_usd": {}}
    if ttl_h > table["budget"]["short_window_hours"]:
        # janela longa: o plan_guard exige ack fresco do supervisor (D16); aqui o ack é sintético e só deixa ver
        # o resto do plano; na execução real a pré-condição é do PROBE-* (runner.preflight)
        ctx["supervisor"] = {"last_ack_at": iso(now), "run_tag": run_tag}
    rep = plan_check.check_plan(plan, ctx, table, now=now)
    cats = {k: round(sum(i[k] for i in rep["cost"]["items"]), 6) for k in CATEGORIES}
    return {"side": side, "ok": rep["ok"], "findings": rep["findings"], "ttl_hours": ttl_h,
            "cost": {"currency": "USD", "total": rep["cost"]["total"], "by_category": cats,
                     "items": [{"address": i["address"], "type": i["type"], "total": i["total"]}
                               for i in rep["cost"]["items"]],
                     "includes": rep["cost"]["includes"]},
            "insts": insts}


def estimate(cell: str, p: Protocol, table: dict, now=None) -> dict:
    sides = {s: check_side(cell, s, p, table, now) for s in T.SIDES}
    total = round(sum(sides[s]["cost"]["total"] for s in T.SIDES), 6)
    cats = {k: round(sum(sides[s]["cost"]["by_category"][k] for s in T.SIDES), 6) for k in CATEGORIES}
    return {"cell": cell, "total": total, "by_category": cats, "limit": p.cost_limit_usd,
            "within_limit": total <= p.cost_limit_usd + 1e-12,
            "plan_guard_ok": all(sides[s]["ok"] for s in T.SIDES),
            "sides": {s: {k: v for k, v in sides[s].items() if k != "insts"} for s in T.SIDES},
            "_insts": {s: sides[s]["insts"] for s in T.SIDES}}


def run_context(cell: str, p: Protocol, table: dict, side: str) -> dict:
    """Peças do contexto do SafeRun (SAFETY) para um lado de um caso sorteado: TTL do runner >= janela (o supervisor
    destrói no prazo), janela, região permitida, uso por endereço (o mesmo da estimativa) e se a janela é longa
    (supervisor obrigatório, D16). O PROBE-* junta identidade, canal efêmero, manifesto e supervisor."""
    if side not in T.SIDES:
        raise ValueError(f"lado inválido: {side}")
    impl = IMPL[cell]
    provider = cell.split("/")[1]
    region = regions(table)[provider]
    _, insts = T.synthetic_plan(cell, side, T.synthetic_vars(cell, "b-ctx", {}, region, impl.runner_inputs))
    ttl_h = int(math.ceil(p.window_s / 3600.0))
    return {"ttl_hours": ttl_h, "window_hours": p.window_s / 3600.0, "region": region,
            "usage": usage_for(cell, p, insts), "needs_supervisor": ttl_h > table["budget"]["short_window_hours"]
            or p.needs_supervisor, "runner_inputs": list(impl.runner_inputs), "targets": list(impl.targets)}
