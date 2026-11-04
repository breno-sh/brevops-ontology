"""Roda o piloto sto inteiro, grava o staging ($BO_DATA/PILOT-STO-E2E/.staging/) e o controls.json (C15).

Staging (trocado para $BO_DATA/PILOT-STO-E2E/ só dentro da trava de merge, por bo.pilot_sto_e2e.publish):
  owl/                       módulo OWL da fatia (3 níveis) e tabelas C14
  translation_trace.jsonl    C23, por valor, dos três controles
  graph_ir.jsonl             C26, um grafo por (controle, entrada) que desceu
  lowering_plan.jsonl        C26, um plano por (controle, entrada) que desceu
  targets.jsonl              configuração-alvo derivada do plano + mapa de contêineres (entrada do julgamento)
  render_status.json         estado de cada plano no renderizador do harness do provedor
  run_record.json            hashes das entradas, da política, do registro de transformações e do TBox
"""

from __future__ import annotations

import collections
import time
from pathlib import Path

from bo.contracts import validate as V

from . import canary as CN
from . import common as C
from . import evaluate as E
from . import pipeline as PL
from . import policy as P
from . import render as RD

CONTRACT_FILES = {"translation_trace.jsonl": "translation_trace", "graph_ir.jsonl": "graph_ir",
                  "lowering_plan.jsonl": "lowering_plan"}
OWL_FILES = {"classes.jsonl": "classes", "properties.jsonl": "properties", "realizations.jsonl": "realizations",
             "sto-c3_full.ttl": "ttl", "sto-c2_taxonomy.ttl": "ttl"}


def render_runs(res: dict, name: str) -> dict:
    """Renderiza todos os planos que desceram, por provedor; devolve {plan_id: status do harness}."""
    by = collections.defaultdict(lambda: ([], []))
    for runs in res["runs"].values():
        for r in runs:
            if r.plan:
                by[r.plan["target_provider"]][0].append(r.plan)
                by[r.plan["target_provider"]][1].append(r.graph_ir)
    status, renders = {}, {}
    for prov in sorted(by):
        rr = RD.render(prov, *by[prov], name)
        renders[prov] = rr
        status.update(rr["status"])
    return {"status": status, "renders": renders}


def apply_render(res: dict, rstatus: dict) -> None:
    for runs in res["runs"].values():
        for r in runs:
            if r.plan and rstatus.get(r.plan["plan_id"]) != "RENDERED":
                r.status = "BLOCKED"
                r.block = ("UNKNOWN_INPUT", "T-RENDER", f"harness: {rstatus.get(r.plan['plan_id'])}")


def run_all(controls=C.CONTROLS, write: bool = True, claims=None) -> dict:
    t0 = time.time()
    ctx = PL.prepare(claims=claims)
    res = PL.run_calib(ctx, controls)
    t1 = time.time()
    rend = render_runs(res, "calib")
    apply_render(res, rend["status"])
    t2 = time.time()
    ctx.timings.update({"render_s": round(t2 - t1, 3)})
    out = {"ctx": ctx, "res": res, "render": rend, "timings": dict(ctx.timings, total_s=round(t2 - t0, 3))}
    if write:
        write_stage(out)
    return out


def write_stage(out: dict) -> dict:
    sd = PL.stage_dir()
    res = out["res"]
    traces, girs, plans, targets = [], [], [], []
    for ctl, runs in res["runs"].items():
        for r in runs:
            traces += r.traces
            if r.plan:
                girs.append(r.graph_ir)
                plans.append(r.plan)
                targets.append({"entry_id": r.entry_id, "control": ctl, "plan_id": r.plan["plan_id"],
                                "status": r.status, "container_map": r.container_map,
                                "declared_losses": r.translation.effects, "target": r.target})
    C.write_jsonl(sd / "translation_trace.jsonl", traces)
    C.write_jsonl(sd / "graph_ir.jsonl", girs)
    C.write_jsonl(sd / "lowering_plan.jsonl", plans)
    C.write_jsonl(sd / "targets.jsonl", targets)
    C.write_json(sd / "render_status.json", {"plans": out["render"]["status"]})
    rec = run_record(out)
    C.write_json(sd / "run_record.json", rec)
    return rec


def run_record(out: dict) -> dict:
    ctx, res = out["ctx"], out["res"]
    sd = PL.stage_dir()
    per_control = {}
    for ctl, runs in res["runs"].items():
        per_control[ctl] = {"input_sha256": C.sha256_obj([r.input_sha256 for r in runs]),
                            "policy_sha256": ctx.inputs["policy"]["sha256"],
                            "transforms_sha256": ctx.inputs["transforms_registry"]["sha256"],
                            "claims_sha256": ctx.inputs["claims"]["mapping_sha256"],
                            "verdicts_sha256": ctx.inputs["claims"]["verdicts_sha256"],
                            "entries": len(runs)}
    files = {}
    for f in list(CONTRACT_FILES) + ["targets.jsonl", "render_status.json"]:
        files[f] = C.sha256_file(sd / f)
    for f in OWL_FILES:
        files["owl/" + f] = C.sha256_file(sd / "owl" / f)
    return {"schema": "bo.pilot.sto.run_record/1", "module": C.MODULE, "generated_at": C.now(),
            "pipeline_version": PL.PIPELINE_VERSION, "inputs": ctx.inputs, "per_control": per_control,
            "files": files, "timings": out["timings"]}


def validate_contracts(sd: Path | None = None) -> list[str]:
    sd = sd or PL.stage_dir()
    errs = []
    for f, kind in CONTRACT_FILES.items():
        p = sd / f
        if p.stat().st_size == 0:
            continue                     # nenhum plano desceu: arquivo vazio não é registro inválido
        r = V.validate(kind, p)
        errs += [f"{f}: {e}" for e in r.errors[:5]]
    for f, kind in OWL_FILES.items():
        r = V.validate(kind, sd / "owl" / f)
        errs += [f"owl/{f}: {e}" for e in r.errors[:5]]
    return errs


# ----------------------------------------------------------------------------------------------------------
# controls.json (C15)
# ----------------------------------------------------------------------------------------------------------
def controls_doc(out: dict) -> dict:
    res, ctx = out["res"], out["ctx"]
    rec = run_record(out)
    metrics, data = [], {"controls": {}, "same_input": {}, "consequences": [], "directions": {}}
    same = {k: len({rec["per_control"][c][k] for c in rec["per_control"]}) == 1
            for k in ("input_sha256", "policy_sha256", "transforms_sha256", "claims_sha256", "verdicts_sha256")}
    data["same_input"] = {"checks": same, "per_control": rec["per_control"], "policy": P.describe()}
    for ctl, runs in res["runs"].items():
        code = C.CONTROL_CODE[ctl].upper()
        vals = [c for r in runs for c in r.translation.carries if c.value.role == "config"]
        carried = sum(1 for c in vals if c.result == "carried")
        lowered = sum(1 for r in runs if r.status == "LOWERED")
        blocks = collections.Counter(f"{r.block[0]}:{r.block[1]}" for r in runs if r.block)
        vblocks = collections.Counter(c.code for c in vals if c.result == "blocked")
        data["controls"][ctl] = {"entries": len(runs), "config_values": len(vals), "carried_values": carried,
                                 "lowered_units": lowered, "unit_blocks": dict(blocks.most_common()),
                                 "value_blocks": dict(vblocks.most_common()),
                                 "scope_losses_declared": sum(1 for r in runs if "SCOPE_WIDENED" in r.translation.effects),
                                 "inconsistent_sources": sum(1 for r in runs if r.translation.clashes)}
        for d in C.DIRECTIONS:
            rs = [r for r, e in zip(runs, res["entries"]) if e["direction"] == d]
            data["directions"].setdefault(d, {})[ctl] = {"entries": len(rs),
                                                         "lowered": sum(1 for r in rs if r.status == "LOWERED")}
        for name, k, n, reading in (("valores de configuração da fatia transportados", carried, len(vals), "field"),
                                    ("unidades completas descidas (lowering + render)", lowered, len(runs), "complete_unit")):
            metrics.append({"metric_id": f"M-PSTO-{code}-{reading.upper().replace('_', '-')}", "name": f"{ctl}: {name}",
                            "reading": reading, "axis": "transportability", "quantifier": "observed_fraction",
                            "operational_coverage": E.wilson(k, n),
                            "frame": {"description": "fixtures de calibração do PILOT-STO-ORACLE, 181 entradas de direção"},
                            "inclusion": {"rule_id": "INC-PSTO-CALIB", "text": "entrada de direção de calibração; valor de configuração da fatia"},
                            "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "none"}})
    # consequências: onde os controles divergem, com o motivo
    for i, e in enumerate(res["entries"]):
        outs = {ctl: res["runs"][ctl][i] for ctl in res["runs"]}
        sig = {ctl: (r.status, r.block[0] if r.block else None, tuple(r.translation.effects)) for ctl, r in outs.items()}
        if len(set(sig.values())) > 1:
            data["consequences"].append({"entry_id": e["entry_id"], "direction": e["direction"],
                                         "by_control": {ctl: {"status": s[0], "block": s[1], "declared": list(s[2])}
                                                        for ctl, s in sig.items()}})
    data["harness_findings"] = [
        {"finding": "HARNESS-GCP só aceitava $BO_TMP com o nome HARNESS-GCP", "status": "corrigido no harness (9082eda); contorno retirado"},
        {"finding": "HARNESS-GCP recusava perda (C26 losses) em campo que também é valor (CONFLICTING_VALUES)",
         "status": "corrigido no harness (9082eda); a perda voltou ao campo de destino"},
        {"finding": "HARNESS-GCP resolvia referência só pelo símbolo do nome derivado",
         "status": "corrigido no harness (9082eda): resolve por target_node, que o plano já traz"}]
    return {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": C.MODULE,
            "generated_at": C.now(), "metrics": metrics,
            "notes": "Três controles com a mesma entrada, a mesma política de perda e o mesmo registro de transformações "
                     "(data.same_input). Calibração apenas; as retidas são do PILOT-EXIT.", "data": data}


def canary(name: str = "canary") -> dict:
    """Roda o canário (12 direções, alegações sintéticas) por c3 e renderiza; não entra em resultado do estudo."""
    ctx = PL.prepare(claims=CN.claimset(), out_dir=C.tmp_dir() / "canary_owl")
    entries = CN.entries()
    runs = {"c3_full": [PL.run_entry(ctx, e, "c3_full") for e in entries]}
    res = {"entries": entries, "runs": runs}
    rend = render_runs(res, name)
    apply_render(res, rend["status"])
    return {"ctx": ctx, "res": res, "render": rend}
