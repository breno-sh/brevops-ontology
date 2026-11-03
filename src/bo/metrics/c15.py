"""Documentos C15 3.0.0 (result) a partir das leituras.

Uma entrada de métrica por célula: metric_id = <métrica>__<origem>__<destino> (ou __<provedor> nas não
direcionais, __mean12 para a média das direções). O nome antigo da v2 não aparece em nenhuma chave.

Lacuna do contrato (results/METRICSLIB/CONTRACT_CHANGE.txt): o C15 só aceita est nulo com n = 0, mas uma célula
com n > 0 e todas as unidades desconhecidas não tem est (0/0). A biblioteca não inventa número: essa célula
não vira entrada de métrica; vai inteira para data.est_undefined (lower, upper, n) e a nota do documento diz
isso.
"""
from __future__ import annotations

from .core import Bounds
from .spec import BINDINGS, LEVEL, inclusion_rule


class ContractGap(ValueError):
    pass


def cell_metric_id(metric_id: str, cell: str) -> str:
    return metric_id if cell in ("", None) else f"{metric_id}__{cell.replace('->', '__')}"


def metric_entry(metric_id: str, cell: str, bd: Bounds, spec_metric: dict, frame_ref: dict | None = None,
                 correlated_with=(), method: str | None = None, level: float = LEVEL) -> dict:
    if bd.est is None and bd.n != 0:
        raise ContractGap(f"{metric_id} {cell}: n = {bd.n} sem est (todas desconhecidas)")
    b = BINDINGS[metric_id]
    rid, text = inclusion_rule(spec_metric["inclusion"])
    frame = {"description": spec_metric["frame"]}
    if frame_ref:
        frame["ref"] = frame_ref
    ju = {"method": method or b.uncertainty}
    if ju["method"] != "none":
        ju["level"] = level
    if correlated_with:
        ju["correlated_with"] = sorted(set(correlated_with))
    label = "" if not cell else f" ({cell})"
    return {"metric_id": cell_metric_id(metric_id, cell), "name": b.name + label, "reading": b.reading,
            "axis": b.axis, "quantifier": b.quantifier,
            "operational_coverage": {"lower": bd.lower, "upper": bd.upper, "est": bd.est, "n": bd.n},
            "frame": frame, "inclusion": {"rule_id": rid, "text": text}, "weights": {"scheme": b.weights},
            "joint_uncertainty": ju}


def result_document(module: str, generated_at: str, entries: list[dict], undefined: list[dict] | None = None,
                    notes: str | None = None, data: dict | None = None, absence_audit: dict | None = None) -> dict:
    ids = {e["metric_id"] for e in entries}
    for e in entries:
        cw = e["joint_uncertainty"].get("correlated_with")
        if cw:
            e["joint_uncertainty"]["correlated_with"] = [x for x in cw if x in ids] or None
            if e["joint_uncertainty"]["correlated_with"] is None:
                del e["joint_uncertainty"]["correlated_with"]
    doc = {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.0.0", "module": module,
           "generated_at": generated_at, "metrics": sorted(entries, key=lambda e: e["metric_id"])}
    d = dict(data or {})
    if undefined:
        d["est_undefined"] = sorted(undefined, key=lambda x: x["metric_id"])
    if d:
        doc["data"] = d
    if absence_audit:
        doc["absence_audit"] = absence_audit
    if notes:
        doc["notes"] = notes
    return doc


def entries_for(metric_id: str, cells: dict[str, Bounds], spec_metric: dict, frame_ref=None,
                correlated=None) -> tuple[list[dict], list[dict]]:
    """Entradas C15 de todas as células de uma métrica; as sem est vão para a lista de indefinidas."""
    ok, undef = [], []
    for cell, bd in sorted(cells.items()):
        cw = [cell_metric_id(m, cell) for m in (correlated or [])]
        try:
            ok.append(metric_entry(metric_id, cell, bd, spec_metric, frame_ref, cw))
        except ContractGap:
            undef.append({"metric_id": cell_metric_id(metric_id, cell), "lower": bd.lower, "upper": bd.upper,
                          "n": bd.n, "reason": "n > 0 e est indefinido: nenhuma unidade com desfecho conhecido na célula (ou num fator da leitura combinada)"})
    return ok, undef
