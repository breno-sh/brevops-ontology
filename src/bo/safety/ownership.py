"""Filtro de propriedade, reconciliação do manifesto com o inventário e limpeza sob a trava cleanup-global.

Regra (§10.2): só se apaga o que tem a tag desta execução (bo-run = run_tag) OU uma linha do manifesto próprio
(referência do provedor gravada, ou nome sintético de uma intenção desta execução). NUNCA se apaga algo só por ser
diferente do baseline: a limpeza não aceita lista de candidatos de fora; ela mesma lista o inventário e filtra.
Recurso sem prova de posse é só relatado ("alheio"), em qualquer região e de qualquer tipo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import locks
from .common import SafetyError, now_dt, parse_iso
from .manifest import RANK, Manifest

LIVE_STATES = {"active"}
PENDING_STATES = {"deleting"}
SCHEDULED_STATES = {"pending_deletion", "soft_deleted", "retained"}


class OwnershipRefused(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "OWNERSHIP")


def owned(item: dict, run_tag: str, states: dict, type_of=None) -> str | None:
    """Motivo da posse ('tag', 'manifesto:ref', 'manifesto:nome') ou None (alheio: só relatar)."""
    type_of = type_of or (lambda t: t)
    if (item.get("tags") or {}).get("bo-run") == run_tag:
        return "tag"
    for s in states.values():
        if s.ref and item.get("ref") == s.ref:
            return "manifesto:ref"
    for s in states.values():
        nm, ln = item.get("name") or "", s.intent["logical_name"]
        if type_of(item.get("type")) == s.intent["resource_type"] and (nm == ln or nm.endswith("/" + ln)):
            reg = (s.binding or {}).get("region")
            if reg and item.get("region") not in (reg, "global"):
                continue
            return "manifesto:nome"
    return None


def match_intent(item: dict, states: dict, type_of=None):
    type_of = type_of or (lambda t: t)
    for s in states.values():
        if s.ref and item.get("ref") == s.ref:
            return s
    for s in states.values():
        tags = item.get("tags") or {}
        if s.intent.get("tags") and tags.get("bo-intent") == s.intent["tags"].get("bo-intent"):
            return s
    for s in states.values():
        nm, ln = item.get("name") or "", s.intent["logical_name"]
        if type_of(item.get("type")) == s.intent["resource_type"] and (nm == ln or nm.endswith("/" + ln)):
            return s
    return None


@dataclass
class Report:
    run_tag: str
    owned_live: list = field(default_factory=list)
    owned_pending: list = field(default_factory=list)
    owned_scheduled: list = field(default_factory=list)
    untracked_owned: list = field(default_factory=list)   # tag da execução sem intenção: violação
    untracked_seen: list = field(default_factory=list)    # acumulado na limpeza (a violação não some ao apagar)
    foreign: int = 0
    foreign_by_type: dict = field(default_factory=dict)
    adopted: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    intents: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _short(item):
    return {"type": item.get("type"), "region": item.get("region"), "state": item.get("state"),
            "trace": item.get("_why")}


def reconcile(man: Manifest, inventory: list[dict], run_tag: str, identity_check: dict | None,
              type_of=None, write: bool = True, now=None, final: bool = True) -> Report:
    """Casa o manifesto com o inventário vivo e grava os estágios que faltam (adoção depois de morte do runner).
    Nunca apaga nada. Devolve o retrato da posse."""
    rep = Report(run_tag)
    rep.problems = man.problems()
    states = man.load()
    seen: set[str] = set()
    for it in inventory:
        if it.get("state") == "gone":
            continue  # listado como apagado (ex.: compartment DELETED da OCI): é ausência, não resíduo
        why = owned(it, run_tag, states, type_of)
        if why is None:
            rep.foreign += 1
            rep.foreign_by_type[it.get("type")] = rep.foreign_by_type.get(it.get("type"), 0) + 1
            continue
        it = dict(it, _why=why)
        s = match_intent(it, states, type_of)
        if s is None:
            rep.untracked_owned.append(_short(it))
            rep.owned_live.append(it) if it["state"] in LIVE_STATES else rep.owned_pending.append(it)
            continue
        seen.add(s.iid)
        it["_intent"] = s.iid
        if write:
            if RANK[s.last] < RANK["creating"]:
                rep.problems.append(f"{s.iid}: recurso existe sem 'creating' gravado (violação do protocolo)")
            if RANK[s.last] < RANK["created"]:
                man.stage(s.iid, "created", identity_check=identity_check, ref=it["ref"],
                          note="reconciliado: criado antes da morte do runner", now=now)
                rep.adopted.append(s.iid)
                states = man.load()
                s = states[s.iid]
            if it["state"] in PENDING_STATES and RANK[s.last] < RANK["removal_pending"]:
                man.stage(s.iid, "removal_pending", note="reconciliado: provedor removendo", now=now)
            elif it["state"] in SCHEDULED_STATES and RANK[s.last] < RANK["purge_scheduled"]:
                man.stage(s.iid, "purge_scheduled", note="reconciliado: remoção agendada", now=now)
            states = man.load()
        (rep.owned_live if it["state"] in LIVE_STATES else
         rep.owned_pending if it["state"] in PENDING_STATES else rep.owned_scheduled).append(it)
    # intenções sem nada vivo: ausentes (nunca criadas, ou já removidas)
    for iid, s in states.items():
        if iid in seen:
            continue
        if write and s.last == "creating" and (s.binding or {}).get("trace") == "ref" and not final:
            continue  # vínculo sem nome nem tag: só se conclui ausente depois de remover o pai
        if write and s.last != "absent":
            note = {"purge_scheduled": "expurgado: leitura direta não encontra mais",
                    "intent": "intenção sem criação: nada foi criado",
                    "creating": "criação interrompida antes de o provedor criar",
                    "created": "sumiu sem remoção pelo kit (investigar)",
                    "confirmed": "sumiu sem remoção pelo kit (investigar)"}.get(s.last, "leitura direta: não encontrado")
            if s.last in ("created", "confirmed"):
                rep.problems.append(f"{iid}: {note}")
            man.stage(iid, "absent", residual_usd=0.0, note=note, now=now)
    for iid, s in man.load().items():
        rep.intents[iid] = s.last
    return rep


def advance(man: Manifest, iid: str, stage: str, **kw) -> bool:
    """Grava o estágio só se ele sobe (retomada idempotente depois de morte entre gravação e chamada)."""
    st = man.load().get(iid)
    if st is None or RANK[stage] <= RANK[st.last]:
        return False
    man.stage(iid, stage, **kw)
    return True


def _delete_order(order_fn, it):
    return -(order_fn(it.get("type")) if order_fn else 0)


def _carry(old: Report, new: Report) -> Report:
    """O retrato novo herda o histórico da limpeza: ações, adoções e problemas (cauda cortada, violações)."""
    new.actions = old.actions
    new.adopted = old.adopted + [a for a in new.adopted if a not in old.adopted]
    new.problems = old.problems + [p for p in new.problems if p not in old.problems]
    return new


def cleanup(man: Manifest, adapter, run_tag: str, identity_check: dict, owner: str, *, order_fn=None,
            type_of=None, lock_root=None, wait_lock_s: float = 0.0, wait_fn=None, max_passes: int = 8,
            poll_s: float = 30.0, apply: bool = True, now_fn=None) -> Report:
    """Teardown com trava global e filtro de propriedade. A lista de candidatos é sempre derivada aqui."""
    if not identity_check or not identity_check.get("matches_allowlist"):
        raise OwnershipRefused("limpeza sem identidade conferida")
    wait_fn = wait_fn or time.sleep
    now_fn = now_fn or now_dt
    with locks.held(locks.CLEANUP, owner, wait_lock_s, lock_root):
        cut = man.repair()
        rep = reconcile(man, adapter.list_all(), run_tag, identity_check, type_of, write=apply, now=now_fn(),
                        final=False)
        untracked_seen = list(rep.untracked_owned)
        rep.problems += [f"{c}:cauda_cortada" for c in cut]
        if not apply:
            rep.untracked_seen = untracked_seen
            return rep
        for p in range(max_passes):
            live = sorted(rep.owned_live, key=lambda it: _delete_order(order_fn, it))
            for it in live:
                iid = it.get("_intent")
                if iid:
                    advance(man, iid, "removal_requested", identity_check=identity_check, now=now_fn())
                res = adapter.delete(it)
                rep.actions.append({"pass": p, "type": it.get("type"), "result": res, "trace": it.get("_why")})
                if iid and res in ("removal_pending", "purge_scheduled"):
                    advance(man, iid, res, now=now_fn())
            for it in rep.owned_scheduled:
                if hasattr(adapter, "purge") and it.get("state") == "soft_deleted":
                    res = adapter.purge(it)
                    rep.actions.append({"pass": p, "type": it.get("type"), "result": "purge:" + res,
                                        "trace": it.get("_why")})
            rep = _carry(rep, reconcile(man, adapter.list_all(), run_tag, identity_check, type_of, now=now_fn(),
                                        final=False))
            untracked_seen += [u for u in rep.untracked_owned if u not in untracked_seen]
            if not rep.owned_live and not rep.owned_pending:
                break
            wait_fn(poll_s)
        rep = _carry(rep, reconcile(man, adapter.list_all(), run_tag, identity_check, type_of, now=now_fn(),
                                    final=True))
        rep.untracked_seen = untracked_seen + [u for u in rep.untracked_owned if u not in untracked_seen]
        man.publish()
        return rep


def delete_candidates(*_a, **_k):
    """Recusa explícita: limpeza por lista de candidatos de fora (ex.: diferença contra o baseline) não existe."""
    raise OwnershipRefused("limpeza por lista externa (diferença de baseline) é proibida; use cleanup(), que "
                           "filtra por tag da execução ou linha do manifesto próprio")


def complete(rep: Report, man: Manifest, expected_residue_fn=None, now=None) -> tuple[bool, list[str]]:
    """Teardown completo: nada vivo nem removendo; agendados só se previstos no EXPECTED_RESIDUE com prazo;
    nenhuma intenção fora de estado terminal; nenhum recurso da execução sem intenção."""
    why = []
    if rep.owned_live:
        why.append(f"{len(rep.owned_live)} recurso(s) da execução ainda vivo(s)")
    if rep.owned_pending:
        why.append(f"{len(rep.owned_pending)} recurso(s) ainda em remoção")
    if rep.untracked_owned or rep.untracked_seen:
        n = len(rep.untracked_seen or rep.untracked_owned)
        why.append(f"{n} recurso(s) com a tag da execução sem intenção gravada (violação do protocolo)")
    now = now or now_dt()
    st = man.load()
    for iid, s in st.items():
        if s.last not in ("absent", "purge_scheduled"):
            why.append(f"{iid}: estágio final {s.last}")
        elif s.last == "purge_scheduled" and parse_iso(s.intent["purge_deadline"]) < now and \
                any(it.get("_intent") == iid for it in rep.owned_scheduled):
            why.append(f"{iid}: prazo de expurgo vencido e o recurso ainda aparece")
    for it in rep.owned_scheduled:
        if expected_residue_fn and not expected_residue_fn(it):
            why.append(f"agendado fora do EXPECTED_RESIDUE: {it.get('type')}")
    for p in rep.problems:
        if "cauda" in p or "linha_invalida" in p:
            continue  # cauda rasgada já foi cortada; vira nota
        if "investigar" in p or "violação" in p:
            why.append(p)
    return (not why), why
