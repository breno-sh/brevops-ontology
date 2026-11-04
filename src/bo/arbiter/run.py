"""Executa o árbitro sobre arquivos C09 e grava os vereditos C21.

Uso: python -I -m bo.arbiter.run --in ARQ|GLOB [--in ...] [--glossary DIR] [--atoms ARQ ...] [--out DIR]
                                 [--verdicts ARQ] [--cycles ARQ] [--report ARQ] [--frozen] [--check-unproven]
                                 [--cycle N | --previous verdicts.jsonl] [--decided-at ISO]

  --in            alegações C09 (*.sssom.tsv ou *.jsonl); aceita glob (ex. "$BO_DATA/MAP-*-*/mapping.sssom.tsv")
  --glossary      pasta C20 com claims.jsonl (+ glossary_audit.jsonl, glossary.jsonl): âncoras auditadas (F4)
  --atoms         C01 (*.jsonl): campos em bloco repetido
  --out           pasta de saída (padrão $BO_DATA/$BO_ID; com --check-unproven e sem --out, $BO_TMP/arbiter, para a
                  conferência de gate nunca regravar o dado publicado): verdicts.jsonl, cycles.jsonl, arbiter_report.json,
                  run_record.json (o que entrou, com sha256, para o bo.arbiter.determinism repetir)
  --frozen        confere arbiter/ARBITER.sha256 antes de julgar (saída 3 se o código não é o congelado)
  --check-unproven  segunda conferência, independente do motor: todo OK que transporta tem as provas mínimas do
                  seu tipo (evidência citada, tipos com grandeza conhecida, normalização com testes, perda no close,
                  predicado com testes no broad/narrow, data no fixo, âncoras auditadas no mesmo conceito); saída 1
                  se algum OK não tem. Muitos UNPROVEN é resultado, não falha.
  --cycle/--previous  ciclo do C21 (padrão 1; com --previous, 1 + o maior ciclo já gravado)
Os vereditos saem validados pelo validador oficial do C21 (bo.contracts.validate).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bo.contracts import catalog as CCAT
from bo.contracts import validate as CVAL

from . import engine
from .common import data_root, dump_json, dump_jsonl, emit, load_jsonl, now, sha256_file
from .freeze import arbiter_sha, verify
from .inputs import Glossary, expand, load

MEANING = ("DOC_SUPPORTED", "OBSERVATION_TESTED", "PERSISTENCE_VERIFIED")


def minimal_proof_gaps(rec: dict, glossary_given: bool) -> list[str]:
    """Conferência independente (não usa o assess): o que um OK que transporta tem de trazer."""
    rel = rec.get("semantic_relation")
    if rel not in ("exact", "close", "broad", "narrow"):
        return []
    gaps = []
    proof = rec.get("proof") or {}
    cited = [e for e in proof.get("evidence") or [] if isinstance(e, dict) and e.get("source")
             and (e.get("sentence") or e.get("observation"))]
    if rec.get("evidence_state") not in MEANING or not cited:
        gaps.append("evidência")
    for side in ("subject_value_type", "object_value_type"):
        t = rec.get(side)
        if not isinstance(t, dict) or "UNKNOWN" in (t.get("quantity_kind"), t.get("unit")):
            gaps.append(f"tipo {side}")
    if rec.get("translation_fn") is None and not rec.get("group") and not rec.get("bo_group_id") \
            and not rec.get("fixed_default"):
        gaps.append("normalização")
    if not proof.get("tests") and not rec.get("fixed_default"):
        gaps.append("testes")
    if rel == "close" and not rec.get("loss_contract"):
        gaps.append("perda declarada")
    if rel in ("broad", "narrow"):
        mp = rec.get("membership_predicate") or {}
        t = mp.get("tests") or {}
        if not mp.get("expr") or not t.get("members") or not t.get("non_members"):
            gaps.append("predicado de pertença")
    fd = rec.get("fixed_default")
    if fd and not (fd.get("evidence") or {}).get("date"):
        gaps.append("data do fixo")
    if rec.get("basis") == "shared_concept" and not glossary_given:
        gaps.append("âncoras auditadas")
    return gaps


def validate_c21(path: Path) -> list[str]:
    sch = CCAT.schemas()
    fk = next(f for f in CCAT.file_kinds(sch) if f.cid == "C21" and f.kind == "verdicts")
    return CVAL.validate_file(fk, path, sch).errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.arbiter.run")
    ap.add_argument("--in", dest="inputs", action="append", required=True)
    ap.add_argument("--glossary")
    ap.add_argument("--atoms", action="append", default=[])
    ap.add_argument("--out")
    ap.add_argument("--verdicts")
    ap.add_argument("--cycles")
    ap.add_argument("--report")
    ap.add_argument("--frozen", action="store_true")
    ap.add_argument("--check-unproven", action="store_true")
    ap.add_argument("--cycle", type=int)
    ap.add_argument("--previous")
    ap.add_argument("--decided-at")
    a = ap.parse_args(argv)

    if a.frozen:
        bad = verify()
        if bad:
            for b in bad[:20]:
                emit(f"  FALHA congelamento: {b}")
            emit(f"[{now()}] run: o código não é o congelado ({len(bad)} divergência(s)); nada julgado")
            return 3
    mid = os.environ.get("BO_ID") or "ARBITERLIB"
    if a.out:
        out = Path(a.out)
    elif a.check_unproven:
        # conferência (gate): nunca regrava o dado publicado em $BO_DATA (CC-MAP-NET-4 do PILOT-NET-MAP)
        out = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / mid)) / "arbiter"
    else:
        out = data_root() / mid
    out.mkdir(parents=True, exist_ok=True)
    vpath = Path(a.verdicts) if a.verdicts else out / "verdicts.jsonl"
    cpath = Path(a.cycles) if a.cycles else out / "cycles.jsonl"
    rpath = Path(a.report) if a.report else out / "arbiter_report.json"
    for p in (vpath, cpath, rpath):
        p.parent.mkdir(parents=True, exist_ok=True)
    cycle = a.cycle or 1
    if a.previous:
        prev = load_jsonl(Path(a.previous))
        cycle = 1 + max((v.get("cycle", 0) for v in prev), default=0)
    glossary = Glossary.from_dir(Path(a.glossary)) if a.glossary else None
    atoms = []
    for p in expand(a.atoms):
        atoms += load_jsonl(p)
    items = load(a.inputs)
    decided = a.decided_at or now()
    res = engine.arbitrate(items, glossary=glossary, atoms=atoms, cycle=cycle, decided_at=decided,
                           arbiter_sha256=arbiter_sha())
    vpath.write_text(dump_jsonl(res["verdicts"]), encoding="utf-8")
    cpath.write_text(dump_jsonl(res["cycles"]), encoding="utf-8")
    rep = dict(res["report"])
    rep.update(generated_at=now(), timezone="America/Recife", decided_at=decided, cycle=cycle,
               arbiter_sha256=arbiter_sha(), frozen_checked=a.frozen)
    rpath.write_text(dump_json(rep), encoding="utf-8")
    record = {"schema": "bo.arbiter_run/1", "recorded_at": now(), "decided_at": decided, "cycle": cycle,
              "inputs": [{"path": str(p), "sha256": sha256_file(p)} for p in expand(a.inputs)],
              "glossary": a.glossary, "atoms": [str(p) for p in expand(a.atoms)],
              "verdicts_sha256": sha256_file(vpath), "cycles_sha256": sha256_file(cpath)}
    (out / "run_record.json").write_text(dump_json(record), encoding="utf-8")
    errs = validate_c21(vpath)
    for e in errs[:10]:
        emit(f"  FALHA C21: {e}")
    rc = 1 if errs else 0
    if a.check_unproven:
        byv = {c.vid: c.rec for c in res["checked"]}
        gaps = []
        for v in res["verdicts"]:
            if v["verdict"] == "OK" and v["claim_version_id"] in byv:
                g = minimal_proof_gaps(byv[v["claim_version_id"]], glossary is not None)
                if g:
                    gaps.append((v["claim_id"], g))
        for cid, g in gaps[:20]:
            emit(f"  FALHA check-unproven: {cid} saiu OK sem {', '.join(g)}")
        emit(f"  check-unproven: {len(gaps)} OK sem prova mínima; UNPROVEN = {rep['verdicts'].get('UNPROVEN', 0)}")
        rc = rc or (1 if gaps else 0)
    emit(f"[{now()}] run: {rep['n_current']} alegação(ões) correntes de {len(rep['inputs'])} arquivo(s); "
         f"{json.dumps(rep['verdicts'], ensure_ascii=False, sort_keys=True)}; compostos "
         f"{json.dumps(rep['verdicts_composites'], ensure_ascii=False, sort_keys=True)}; -> {vpath}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
