"""Orquestração do piloto NET: fixtures x 12 direções x 3 controles, com a mesma entrada, a mesma política de perda e
as mesmas transformações. Grava em $BO_DATA/PILOT-NET-E2E/.staging (o definitivo só troca dentro da trava).

Etapas (cada uma com o tempo medido para o effort.json):
  inputs   fixtures (calib do repositório ou --fixtures-dir), alegações (PILOT-NET-MAP ou sintéticas, marcado)
  lift     configuração -> indivíduos e unidades
  owl      módulo OWL da fatia + C14
  reason   c1 (nada), c2 (owlrl RDFS), c3 (HermiT pelo ROBOT + SHACL)
  translate  IR de grafo + plano de lowering + traço C23 por caso
  render   HCL pelos HARNESS-* + releitura (python-hcl2) para o formato do oráculo
  oracle   juiz do oráculo congelado com as perdas declaradas pela política
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import CONTROLS, DIRECTIONS, MODULE, MODEL_ID
from . import claims as CL
from . import lift as LF
from . import loss_policy as LP
from . import oracle as O
from . import owlgen
from . import reason as RS
from . import render as RD
from . import synthetic as SY
from . import translate as TR

TZ = ZoneInfo("America/Recife")
CODE = {"c1_table": "c1", "c2_taxonomy": "c2", "c3_full": "c3"}
PRIMARY = "c3_full"


def now() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()


def data_dir() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / MODULE


def staging() -> Path:
    return data_dir() / ".staging"


def tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "tmp" / MODULE)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jsonl(rows) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


class Timer:
    def __init__(self):
        self.steps = {}

    def __call__(self, name):
        t = self

        class _C:
            def __enter__(self_):
                self_.t0 = time.monotonic()

            def __exit__(self_, *a):
                t.steps[name] = round(t.steps.get(name, 0.0) + time.monotonic() - self_.t0, 3)
        return _C()


def load_claims(mode: str, decided_at: str):
    """mode: mapping (PILOT-NET-MAP em bo/base) | synthetic (teste do caminho). Devolve (ClaimSet, origem)."""
    if mode == "synthetic":
        d = tmp() / "synthetic_claims"
        m, v = SY.write(d, decided_at)
        return CL.load(m, v, "synthetic"), {"mode": "synthetic", "mapping": str(m), "verdicts": str(v)}
    base = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "PILOT-NET-MAP"
    m, v = base / "mapping.sssom.tsv", base / "verdicts.jsonl"
    if not m.exists() or not v.exists():
        raise SystemExit(f"alegações do PILOT-NET-MAP ausentes ({m}); sem mapeamento real não há execução "
                         "(use --claims synthetic só para testar o caminho)")
    return CL.load(m, v, "mapping"), {"mode": "mapping", "mapping": "$BO_DATA/PILOT-NET-MAP/mapping.sssom.tsv",
                                      "verdicts": "$BO_DATA/PILOT-NET-MAP/verdicts.jsonl"}


def run(*, claims_mode="mapping", fixtures_dir: Path | None = None, split="calib", controls=CONTROLS,
        out: Path | None = None, recorded_at: str | None = None, render=True) -> dict:
    T = Timer()
    out = out or staging()
    recorded_at = recorded_at or now()
    with T("inputs"):
        fxs = O.fixtures(fixtures_dir, split)
        cs, corigin = load_claims(claims_mode, recorded_at)
        fx_by = {fx["fixture_id"]: fx for fx in fxs}
    with T("lift"):
        lifted = [LF.lift(fx) for fx in fxs]
        Ls = {L.fixture_id: L for L in lifted}
    with T("owl"):
        tables = owlgen.c14_tables(cs, MODULE)
        ttl = {c: owlgen.tbox_ttl(c, cs) for c in ("c2_taxonomy", "c3_full")}
    abox_sha = RS.input_sha(lifted)
    knowledge, cases = {}, []
    for c in controls:
        with T(f"reason.{CODE[c]}"):
            knowledge[c] = RS.run(c, lifted, cs, tmp() / "reason_cache")
        with T(f"translate.{CODE[c]}"):
            for d in DIRECTIONS:
                src = d.split("->")[0]
                for L in lifted:
                    if L.provider != src:
                        continue
                    cid = f"CASE-{L.fixture_id}-{d.replace('->', '-')}-{CODE[c]}"
                    k = TR.Translator(L, knowledge[c][L.fixture_id], cs, d, c, cid).run()
                    k.n_flows = len(fx_by[L.fixture_id].get("flows", []))
                    cases.append(k)
    rendered = {}
    judged = {}
    if render:
        no = O.load()
        for c in controls:
            for prov in ("aws", "google", "azurerm", "oci"):
                sel = [k for k in cases if k.control == c and k.status == "TRANSLATED" and k.direction.endswith("->" + prov)]
                if not sel:
                    continue
                with T(f"render.{CODE[c]}"):
                    rr = RD.render_provider(prov, sel, tmp() / "render" / CODE[c] / prov)
                for k in sel:
                    r = rr.get(k.plan["plan_id"], {"status": "MISSING", "problems": [], "files": {}})
                    rendered[k.case_id] = r
                    if r["status"] != "RENDERED":
                        continue
                    with T(f"oracle.{CODE[c]}"):
                        tfx = RD.to_oracle(prov, k, RD.parse(r["files"]), fx_by[k.fixture_id])
                        dl = LP.declared(k.losses, fx_by[k.fixture_id]["flows"])
                        j = no.judge(fx_by[k.fixture_id], tfx, [{"loss_id": x["loss_id"], "flows": x["flows"]} for x in dl],
                                     k.direction)
                        judged[k.case_id] = {"verdict": j["verdict"], "per_flow": j["per_flow"],
                                             "negatives_carried": j["negatives_carried"],
                                             "silent_losses": j["silent_losses"], "undetermined": j["undetermined"],
                                             "covered": j["covered"], "undeclarable_losses": j["undeclarable_losses"],
                                             "target_validity": j["target_validity"], "declared_losses": dl,
                                             "target_config": tfx}
    with T("write"):
        rep = write_outputs(out, recorded_at, cs, corigin, fxs, lifted, tables, ttl, knowledge, cases, rendered,
                            judged, abox_sha, T)
    return rep


def case_row(k, rendered, judged) -> dict:
    r = rendered.get(k.case_id)
    j = judged.get(k.case_id)
    status = k.status
    if status == "TRANSLATED" and r is not None and r["status"] != "RENDERED":
        status = "RENDER_BLOCKED"
    return {"case_id": k.case_id, "fixture_id": k.fixture_id, "direction": k.direction, "control": k.control,
            "status": status, "translate_status": k.status, "reasons": k.reasons,
            "render_status": r["status"] if r else None,
            "render_problems": (r or {}).get("problems", [])[:5],
            "plan_id": k.plan["plan_id"] if k.plan else None, "losses": k.losses,
            "endpoints": k.endpoints, "consequences": k.consequences,
            "verdict": j["verdict"] if j else None,
            "judge": {x: j[x] for x in ("per_flow", "negatives_carried", "silent_losses", "undetermined", "covered",
                                        "undeclarable_losses", "target_validity", "declared_losses")} if j else None,
            "n_traces": len(k.traces), "n_flows": k.n_flows}


def write_outputs(out, recorded_at, cs, corigin, fxs, lifted, tables, ttl, knowledge, cases, rendered, judged,
                  abox_sha, T) -> dict:
    if out.exists():
        shutil.rmtree(out)
    (out / "ontology").mkdir(parents=True)
    (out / "hcl").mkdir()
    traces = [t for k in cases for t in k.traces]
    (out / "translation_trace.jsonl").write_text(jsonl(traces), encoding="utf-8")
    plans = [k.plan for k in cases if k.plan]
    graphs = [k.graph for k in cases if k.graph]
    (out / "lowering_plan.jsonl").write_text(jsonl(plans), encoding="utf-8")
    (out / "graph_ir.jsonl").write_text(jsonl(graphs), encoding="utf-8")
    rows = [case_row(k, rendered, judged) for k in cases]
    (out / "cases.jsonl").write_text(jsonl(rows), encoding="utf-8")
    (out / "judge_targets.jsonl").write_text(jsonl([{"case_id": cid, "target": j["target_config"]}
                                                    for cid, j in sorted(judged.items())]), encoding="utf-8")
    for cid, r in rendered.items():
        if r["status"] == "RENDERED":
            d = out / "hcl" / cid
            d.mkdir()
            for name, text in r["files"].items():
                (d / name).write_text(text, encoding="utf-8")
    for name, rows_ in tables.items():
        (out / "ontology" / f"{name}.jsonl").write_text(owlgen.jsonl(rows_), encoding="utf-8")
    for c, t in ttl.items():
        (out / "ontology" / f"net_slice_{CODE[c]}.ttl").write_text(t, encoding="utf-8")
    kn = {c: {fid: {"types": {k: sorted(v) for k, v in K.types.items()}, "values": K.values,
                    "violations": K.violations, "consistent": K.consistent} for fid, K in kc.items()}
          for c, kc in knowledge.items()}
    (out / "knowledge.json").write_text(json.dumps(kn, ensure_ascii=False, sort_keys=True, indent=0), encoding="utf-8")
    inv = invariants(cases, lifted, abox_sha, cs)
    rep = {"schema": "bo.pilot_net.run_report/1", "module": MODULE, "recorded_at": recorded_at,
           "claims": dict(corigin, sha256=cs.sha256, ok=cs.ok_count(), records=len(cs.records)),
           "fixtures": {"n": len(fxs), "split": sorted({fx["split"] for fx in fxs}),
                        "sha256": sha(json.dumps(fxs, sort_keys=True, ensure_ascii=False).encode())},
           "abox_sha256": abox_sha, "loss_policy": LP.document(),
           "transforms_registry": _registry_version(), "oracle": O.fingerprint(),
           "robot": RS.ROBOT_VERSION, "invariants": inv, "timing_s": T.steps,
           "counts": _counts(rows)}
    (out / "run_report.json").write_text(json.dumps(rep, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    return rep


def _registry_version() -> dict:
    from bo.transforms import registry as REG
    return {"version": REG.REGISTRY_VERSION, "generated_at": REG.GENERATED_AT}


def invariants(cases, lifted, abox_sha, cs) -> dict:
    """Mesma entrada, mesma política de perda, mesmas transformações nos 3 controles (gate G2)."""
    per = {}
    for k in cases:
        per.setdefault(k.control, set()).add((k.fixture_id, k.direction))
    same_cases = len({frozenset(v) for v in per.values()}) == 1
    fns = {}
    for k in cases:
        for t in k.traces:
            if t.get("claim_id") and t.get("transform"):
                fns.setdefault(t["claim_id"], set()).add(json.dumps(t["transform"], sort_keys=True))
    same_transforms = all(len(v) == 1 for v in fns.values())
    codes = {}
    for k in cases:
        codes.setdefault(k.control, set()).update(l["code"] for l in k.losses)
    return {"same_case_set": same_cases, "abox_sha256": abox_sha, "same_abox_for_c2_c3": True,
            "same_loss_policy": True, "loss_policy_codes_used": {c: sorted(v) for c, v in codes.items()},
            "same_transform_per_claim": same_transforms, "claims_sha256": cs.sha256,
            "ok": same_cases and same_transforms}


def _counts(rows) -> dict:
    out = {}
    for r in rows:
        c = out.setdefault(r["control"], {})
        c[r["status"]] = c.get(r["status"], 0) + 1
        if r["verdict"]:
            v = c.setdefault("verdicts", {})
            v[r["verdict"]] = v.get(r["verdict"], 0) + 1
    return out


def promote() -> None:
    """Troca o staging pelo definitivo (chamar só com a trava merge-base deste módulo)."""
    st, d = staging(), data_dir()
    if not st.exists():
        raise SystemExit("nada em .staging para promover")
    for p in st.iterdir():
        dst = d / p.name
        if dst.exists():
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        shutil.copytree(p, dst) if p.is_dir() else shutil.copy2(p, dst)
