"""Orquestração do piloto sto: módulo OWL -> lifting -> 3 controles -> IR de grafo -> plano -> configuração-alvo.

prepare()      lê as entradas (alegações OK, vereditos, evidência, átomos), gera o módulo OWL e indexa os TBox
run_entry()    traduz uma entrada de direção (fixture de calibração) por um controle
run_calib()    as 181 entradas de direção x 3 controles + as respostas do pipeline às alegações das fixtures
A avaliação pelo oráculo fica em bo.pilot.sto.evaluate (o pipeline não importa o oráculo).
"""

from __future__ import annotations

import glob
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from bo.transforms import registry as R

from . import abox as A
from . import atoms as ATM
from . import claims as CL
from . import common as C
from . import evidence as EV
from . import lift as L
from . import lower as LW
from . import owl as O
from . import policy as P
from . import tbox as T
from . import translate as TR

PIPELINE_VERSION = "1.0.0"


@dataclass
class Ctx:
    claims: object
    evidence: object
    glossary: dict
    owl_dir: Path
    owl_info: dict
    tbox: dict
    inputs: dict
    timings: dict = field(default_factory=dict)


def stage_dir() -> Path:
    p = C.data_dir() / ".staging"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_glossary() -> dict:
    p = C.data_root() / "PILOT-STO-GLOSS" / "glossary.jsonl"
    return {r["concept_id"]: r for r in C.iter_jsonl(p)} if p.exists() else {}


def prepare(claims=None, out_dir: Path | None = None) -> Ctx:
    t0 = time.time()
    claims = claims or CL.ClaimSet.load()
    ev = EV.Evidence.load()
    gl = load_glossary()
    t1 = time.time()
    owl_dir = out_dir or (stage_dir() / "owl")
    info = O.build_module(claims, gl, owl_dir)
    tb = {lv: A.load_tbox(str(owl_dir / f"sto-{lv}.ttl"), lv) for lv in ("c2_taxonomy", "c3_full")}
    ATM.load()
    t2 = time.time()
    inputs = {
        "claims": claims.source, "evidence": ev.source,
        "glossary_sha256": C.sha256_obj(gl), "atoms": ATM.sources(),
        "transforms_registry": {"version": R.REGISTRY_VERSION, "sha256": C.sha256_obj(R.document())},
        "policy": {"version": P.POLICY_VERSION, "sha256": P.sha256()},
        "tbox_module_sha256": C.sha256_obj({k: C.sha256_file(owl_dir / f"sto-{k}.ttl") for k in ("c2_taxonomy", "c3_full")}),
        "pipeline_version": PIPELINE_VERSION,
    }
    return Ctx(claims, ev, gl, owl_dir, info, tb, inputs, {"load_s": round(t1 - t0, 3), "owl_s": round(t2 - t1, 3)})


def direction_entries() -> list[dict]:
    out = []
    for p in sorted(glob.glob(str(C.fixtures_calib_dir() / "directions" / "*" / "*.json"))):
        e = C.read_json(Path(p))
        e["_file"] = C.portable(p)
        out.append(e)
    return out


def calib_fixtures() -> list[dict]:
    out = []
    for prov in C.PROVIDERS:
        for p in sorted(glob.glob(str(C.fixtures_calib_dir() / prov / "*.json"))):
            fx = C.read_json(Path(p))
            fx["_file"] = C.portable(p)
            out.append(fx)
    return out


def input_view(entry: dict) -> dict:
    """O que o tradutor lê de uma entrada: a origem, o provedor de destino e o contexto de implantação do destino.
    Nunca a configuração-alvo da entrada, a variante, a nota nem as perdas declaradas pelo oráculo."""
    return {"source": entry["source"], "dst": entry["direction"].split("->")[1],
            "env": (entry.get("target") or {}).get("context") or {}}


@dataclass
class EntryRun:
    entry_id: str
    control: str
    translation: object
    graph_ir: dict | None
    plan: dict | None
    target: dict | None
    container_map: dict
    status: str                 # LOWERED | BLOCKED
    block: tuple | None
    input_sha256: str
    traces: list


def run_entry(ctx: Ctx, entry: dict, control: str, carries_cache: dict | None = None) -> EntryRun:
    iv = input_view(entry)
    src = iv["source"]
    lf = L.lift(src, ctx.claims, ctx.evidence)
    key = (entry["entry_id"], iv["dst"])
    if carries_cache is not None and key in carries_cache:
        carries = [TR.Carry(**{**c.__dict__}) for c in carries_cache[key]]
    else:
        carries = [TR.transport(lf, v, iv["dst"], ctx.claims) for v in lf.values if v.role != "wiring"]
        if carries_cache is not None:
            carries_cache[key] = [TR.Carry(**{**c.__dict__}) for c in carries]
    tr = TR.translate(lf, iv["dst"], ctx.claims, control, ctx.tbox, env=iv["env"], carries=carries)
    case = entry["entry_id"].replace("DX-", "")
    gir, plan, tgt, cmap, block = None, None, None, {}, None
    if tr.complete and tr.nodes:
        gir, plan = LW.build(tr, case, lf.provider)
        if not plan["dependency_closure"]["closed"]:
            block = ("UNKNOWN_INPUT", "T-REQUIRED", "obrigatório sem valor: " + ", ".join(plan["dependency_closure"]["missing"]))
        else:
            tgt, cmap = LW.target_fixture(src, plan, tr, iv["env"], entry["entry_id"])
            if not cmap:
                block = ("NO_UNIT", "T-NO-CONTAINER", "nenhum contêiner de destino para o contêiner de origem")
    elif not tr.nodes:
        block = ("NO_UNIT", "T-EMPTY", "nada a traduzir")
    else:
        block = tr.blocked[0]
    status = "LOWERED" if block is None else "BLOCKED"
    traces = trace_rows(ctx, tr, case, control)
    return EntryRun(entry["entry_id"], control, tr, gir, plan if status == "LOWERED" else None, tgt, cmap, status,
                    block, C.sha256_obj(iv), traces)


def trace_rows(ctx: Ctx, tr, case: str, control: str) -> list[dict]:
    rows = []
    code = C.CONTROL_CODE[control]
    for i, c in enumerate(tr.carries, 1):
        v = c.value
        row = {"trace_id": f"TR-PSTO-{code.upper()}-{case}-{i:03d}", "case_id": f"CASE-PSTO-{case}",
               "input": {"atom_id": v.atom_id, "term": v.term}, "control": code,
               "justifying_axioms": [], "consulted_metadata": [], "result": c.result}
        if c.view is not None:
            row["claim_id"] = c.view.claim_ref
            row["consulted_metadata"].append(f"sssom {c.view.claim.claim_id} {c.view.claim.predicate_id} veredito {c.view.claim.verdict}")
        if control != "c1_table" and v.unit_id and v.unit_id in tr.individuals:
            row["individual"] = tr.individuals[v.unit_id]
            row["inferred_classes"] = tr.inferred.get(v.unit_id, [])
        if c.transform:
            row["transform"] = {"name": c.transform["name"], "params": c.transform.get("params") or {}}
        if c.guard and c.guard["guard"].get("all"):
            row["guard_evaluated"] = c.guard
        if c.result == "carried":
            row["output"] = {"atom_id": c.out_atom, "term": c.out_term}
            row["property"] = "sto:" + T.prop_local(v.concept) if T.concept_class(v.concept) else "bo:UNGLOSSED"
            prov, rtype, path = c.out_atom.split(":", 2)
            row["realization_id"] = f"r_{prov}_{rtype}_{path}".replace(".", "_")
            if control != "c1_table":
                row["justifying_axioms"] = sorted(set(tr.justifying.get(id(v), [])))
                if T.concept_class(v.concept):
                    row["justifying_axioms"].append(f"sto:{T.prop_local(v.concept)} descritor stod:desc_{T.prop_local(v.concept)}")
            row["consulted_metadata"].append(f"realização {row['realization_id']}")
            if c.losses:
                row["detail"] = "perda declarada: " + "; ".join(sorted({(x.get('kind') or 'semantic') for x in c.losses}))
        elif c.result == "blocked":
            row["block_code"] = c.code
            row["rule"] = c.rule or "T-BLOCK"
            row["detail"] = (c.detail or "bloqueado")[:300]
            if c.code in ("CONDITION_FALSE", "CONDITION_INDETERMINATE") and not c.guard:
                row["guard_evaluated"] = {"guard": {"all": []}, "result": "INDETERMINATE"}
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------------------------------------
# respostas do pipeline às alegações das fixtures (contraexemplos) — por controle
# ----------------------------------------------------------------------------------------------------------
def pipeline_answer(ctx: Ctx, fx: dict, claim: dict, control: str) -> dict:
    """ACCEPT | REJECT | ABSTAIN do pipeline para uma alegação. O pipeline não calcula estado efetivo (versão
    corrente, acesso público efetivo): isso é do oráculo, e o pipeline se abstém."""
    about = claim["about"]
    if control == "c1_table":
        return {"answer": "ABSTAIN", "why": "c1 não tem unidades nem axiomas"}
    lf = L.lift(fx, ctx.claims, ctx.evidence)
    ix = ctx.tbox[control]
    if about == "decomposition":
        dec = L.decomposition(lf)
        if control == "c2_taxonomy":
            tr, iri = A.abox_of(lf)
            cl = A.reason(tr, ix)
            es = A.effective_scope(lf, cl, iri)
            for uid, d in dec.items():
                if "effective_scope" in d and isinstance(d["effective_scope"], (list, dict)):
                    d["effective_scope"] = es.get(uid) or "UNKNOWN"
        u = dec.get(claim["unit"])
        if u is None:
            return {"answer": "REJECT", "code": "NO_SUCH_UNIT"}
        got = {k: u.get(k) for k in claim["value"]}
        return {"answer": "ACCEPT"} if got == claim["value"] else {"answer": "REJECT", "code": "CONTRADICTS_MODEL",
                                                                     "model": got}
    if about == "disjoint_kinds":
        names = {"storage_namespace": "StorageNamespace", "object_container": "ObjectContainer"}
        x = A.IND + "probe"
        tr = {(x, A.TYPE, A.S(names[k])) for k in claim["kinds"] if k in names}
        cl = A.reason(tr, ix)
        if cl.clashes:
            return {"answer": "REJECT", "code": "INCONSISTENT", "axioms": [c["classes"] for c in cl.clashes]}
        return {"answer": "ACCEPT", "why": "nenhum axioma de disjunção no TBox do controle"}
    return {"answer": "ABSTAIN", "why": f"estado efetivo ({about}) é do oráculo"}


def verify_candidate(ctx: Ctx, run: EntryRun, candidate: dict) -> dict:
    """O pipeline confere uma configuração-alvo candidata (a do oráculo) contra a própria tradução: ACCEPT só se
    os valores da fatia do candidato são exatamente os transportados (mesmo átomo, mesmo valor)."""
    if run.status != "LOWERED":
        return {"answer": "ABSTAIN", "why": "tradução bloqueada: " + (run.block[0] if run.block else "?")}
    lc = L.lift(candidate, ctx.claims, ctx.evidence)
    cand = sorted(C.canon([v.atom_id, v.raw]) for v in lc.values if v.role == "config")
    ours = []
    for s in run.plan["steps"]:
        for v in s["values"]:
            if v["origin"] == "carried" and v["term"]["kind"] != "reference":
                atom = P.atom_of_field(run.plan["target_provider"], s["resource_type"], v["field"])
                if T.concept_class(ctx.claims.concept(atom)):
                    ours.append(C.canon([atom, v["term"].get("value", v["term"])]))
    ours.sort()
    if cand == ours:
        return {"answer": "ACCEPT"}
    return {"answer": "REJECT", "missing": sorted(set(ours) - set(cand))[:5], "extra": sorted(set(cand) - set(ours))[:5]}


def run_calib(ctx: Ctx, controls=C.CONTROLS) -> dict:
    t0 = time.time()
    entries = direction_entries()
    cache: dict = {}
    runs = {ctl: [] for ctl in controls}
    for e in entries:
        for ctl in controls:
            runs[ctl].append(run_entry(ctx, e, ctl, cache))
    ctx.timings["translate_s"] = round(time.time() - t0, 3)
    return {"entries": entries, "runs": runs}
