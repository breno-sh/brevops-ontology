"""Leitura de volta (C12 readback) a partir do state JÁ REDIGIDO, e desfecho de infraestrutura (C12 outcome).

Um campo por valor do plano (e pelo nome derivado), no caminho `<rótulo do passo>.<caminho HCL>` com blocos
indexados (ex.: r2.blob_properties[0].delete_retention_policy[0].days). Estados:
  read      valor lido do state redigido
  absent    o recurso foi lido e o atributo está nulo ou ausente
  not_read  o recurso não está no state, ou o atributo é write_only (nunca volta por construção)
  withheld  o redator marcou: sem valor e sem hash; leva a regra do redator (redação na origem)
A leitura só confirma persistência; quem decide PERSISTED/ALTERED é o JUDGE (C12-READ). O harness só grava
desfecho de infraestrutura (REJECTED_BY_API, INFRA_ERROR), que não sobe a escada de evidência.
"""

from __future__ import annotations

import json

from . import render as R
from . import schema as S
from .redact import W, is_withheld

PROTOCOL_VERSION = "1.0.0"


def _contains_withheld(v):
    if is_withheld(v):
        return v[W]
    if isinstance(v, dict):
        for x in v.values():
            r = _contains_withheld(x)
            if r:
                return r
    if isinstance(v, list):
        for x in v:
            r = _contains_withheld(x)
            if r:
                return r
    return None


def _hcl_path(sch: S.Schema, kind: str, rtype: str, field: str):
    """Segmentos [(nome, é_bloco)], e se o atributo final é write_only."""
    node = sch.node(kind, rtype)
    segs, out, wo = field.split("."), [], False
    for i, seg in enumerate(segs):
        b, a = S.blocks(node), S.attrs(node)
        if seg in b:
            out.append((seg, True))
            node = b[seg].node
        else:
            out.append((seg, False))
            if seg in a and a[seg].write_only:
                wo = True
            node = {}
    return out, wo


def _get(values: dict, segs):
    cur = values
    for i, (name, is_block) in enumerate(segs):
        if not isinstance(cur, dict) or name not in cur:
            return False, None
        cur = cur[name]
        if is_withheld(cur):
            return True, cur
        if is_block:
            if not isinstance(cur, list) or not cur:
                return False, None
            if i == len(segs) - 1:
                return True, cur
            cur = cur[0]
    return True, cur


def build_readback(plan: dict, redacted: dict, *, readback_id: str, case_id: str, group_id: str, claim_id: str,
                   side: str, read_at: str, sch: S.Schema | None = None, harness_tags: dict | None = None) -> dict:
    """`harness_tags`: {rótulo do passo: [chaves]} das tags de propriedade que o harness pôs (declaradas no
    manifesto do render). Elas saem do valor lido de `tags`, para a leitura refletir só o que o plano pediu."""
    sch = sch or S.load()
    harness_tags = harness_tags or {}
    labels = R._labels(plan["steps"])
    state = {r["address"]: r for r in redacted["resources"]}
    fields = []
    for s in sorted(plan["steps"], key=lambda s: s["order"]):
        if s["action"] == "reference":
            continue
        addr = f"{s['resource_type']}.{labels[s['order']]}"
        res = state.get(addr)
        wanted = (["name"] if s.get("derived_name") else []) + [v["field"] for v in s["values"]]
        for fld in wanted:
            segs, wo = _hcl_path(sch, "resource", s["resource_type"], fld)
            path = labels[s["order"]] + "." + ".".join(n + ("[0]" if blk and k < len(segs) - 1 else "")
                                                         for k, (n, blk) in enumerate(segs))
            if res is None or wo:
                fields.append({"path": path, "state": "not_read"})
                continue
            found, v = _get(res["values"], segs)
            rule = _contains_withheld(v) if found else None
            if rule:
                fields.append({"path": path, "state": "withheld", "redaction": {"rule_id": rule, "at_source": True}})
            elif not found or v is None:
                fields.append({"path": path, "state": "absent"})
            else:
                drop = harness_tags.get(labels[s["order"]], []) if fld == "tags" and isinstance(v, dict) else []
                if drop:
                    v = {k: x for k, x in v.items() if k not in drop}
                fields.append({"path": path, "state": "read", "value": v})
    return {"readback_id": readback_id, "case_id": case_id, "group_id": group_id, "claim_id": claim_id,
            "side": side, "provider": "azurerm", "read_at": read_at, "protocol_version": PROTOCOL_VERSION,
            "fields": fields}


def infra_outcome(*, outcome_id: str, case_id: str, group_id: str, claim_id: str, side: str, value: str,
                  detail: str, evidence_before: str, decided_at: str) -> dict:
    if value not in ("REJECTED_BY_API", "INFRA_ERROR", "UNKNOWN"):
        raise ValueError("o harness só decide desfecho de infraestrutura")
    return {"outcome_id": outcome_id, "case_id": case_id, "group_id": group_id, "claim_id": claim_id, "side": side,
            "outcome": {"axis": "persistence", "value": value, "detail": detail},
            "evidence_state_before": evidence_before, "evidence_state_after": evidence_before,
            "rule_id": "HARNESS-APPLY-01", "decided_at": decided_at}


def dumps_line(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n"
