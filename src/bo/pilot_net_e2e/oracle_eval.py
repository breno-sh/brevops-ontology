"""Juiz do oráculo sobre a saída do piloto (gate: toda divergência coberta por perda declarada; zero transporte em
caso negativo).

  python -I -m bo.pilot.oracle_eval --slice net --set calib [--claims mapping|synthetic] [--out DIR] [--write-results]

Roda o pipeline (mesmas entradas do bo.pilot.run) e aplica, no controle principal (c3_full, o pipeline com a
ontologia completa), os critérios do E4 sobre a calibração:
  (a) nenhum caso julgado com perda silenciosa (divergência não coberta pela perda declarada pela política);
  (b) nenhum DENY da origem vira ALLOW no destino (negativo transportado);
  (c) nenhum destino inválido para o oráculo;
  (d) toda fixture negativa do tipo 'rejects' é recusada (REFUSED) ou não atravessa; nenhuma 'not_entails' é
      transportada com DENY -> ALLOW (já coberto por b);
  (e) a ponte com o oráculo confere: nos casos de tradução de referência do PILOT-NET-ORACLE, o juiz devolve o
      veredito esperado (os negativos são REJECT).
Os controles c1 e c2 são julgados e relatados (oracle_calib.json, controls.json), mas não decidem o gate: o que
eles transportam errado é resultado do controle, não defeito do pipeline.
--write-results grava results/PILOT-NET-E2E/oracle_calib.json (C15). Sai 0 só se (a)-(e) valem.
"""

from __future__ import annotations

import json

from bo.pilot.net import oracle as O
from bo.pilot.net import results as RS

from .common import dump, fixtures_args, out_dir, parser, results_dir, run_pipeline, say, validate


def evaluate(out, rep, fixtures_dir=None) -> dict:
    rows = [json.loads(l) for l in (out / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    prim = [r for r in rows if r["control"] == "c3_full"]
    fails = []
    for r in prim:
        j = r.get("judge")
        if not j:
            continue
        if j["silent_losses"]:
            fails.append({"criterion": "a", "case_id": r["case_id"], "flows": j["silent_losses"]})
        if j["negatives_carried"]:
            fails.append({"criterion": "b", "case_id": r["case_id"], "flows": j["negatives_carried"]})
        if j["target_validity"] == "INVALID":
            fails.append({"criterion": "c", "case_id": r["case_id"]})
    fxs = {fx["fixture_id"]: fx for fx in O.fixtures(fixtures_dir, None if fixtures_dir else "calib")}
    negatives = []
    for fid, fx in sorted(fxs.items()):
        if fx.get("polarity") != "negative":
            continue
        outs = {r["direction"]: (r["status"], r["verdict"]) for r in prim if r["fixture_id"] == fid}
        kind = fx["check"]["kind"]
        bad = []
        if kind == "rejects":
            bad = [d for d, (st, v) in outs.items() if st not in ("REFUSED", "UNSUPPORTED", "RENDER_BLOCKED")]
        negatives.append({"fixture_id": fid, "check": kind, "outcomes": {d: st if not v else v for d, (st, v) in outs.items()},
                          "transported_when_must_reject": bad})
        for d in bad:
            fails.append({"criterion": "d", "case_id": f"{fid} {d}"})
    no = O.load()
    reference = []
    for tc in O.translation_cases(fixtures_dir):
        src = fxs.get(tc["source_fixture"])
        if src is None:
            continue
        j = no.judge(src, tc["target"], tc["declared_losses"] and [
            {"loss_id": x, "flows": [f["flow_id"] for f in src["flows"]]} if isinstance(x, str) else x
            for x in tc["declared_losses"]], tc["direction"])
        ok = j["verdict"] == tc["expected"]["verdict"]
        reference.append({"case_id": tc["case_id"], "polarity": tc["polarity"], "expected": tc["expected"]["verdict"],
                          "judge": j["verdict"], "ok": ok})
        if not ok or (tc["polarity"] == "negative" and j["verdict"] != "REJECT"):
            fails.append({"criterion": "e", "case_id": tc["case_id"], "judge": j["verdict"]})
    return {"criteria": {"a": "zero perda silenciosa (c3_full)", "b": "zero DENY -> ALLOW (c3_full)",
                         "c": "zero destino inválido (c3_full)", "d": "negativos 'rejects' recusados (c3_full)",
                         "e": "ponte com o oráculo: casos de referência com o veredito esperado"},
            "failures": fails, "negatives": negatives, "reference": reference,
            "judged": {c: sum(1 for r in rows if r["control"] == c and r["verdict"]) for c in
                       ("c1_table", "c2_taxonomy", "c3_full")}}


def main(argv=None) -> int:
    ap = parser("bo.pilot.oracle_eval", __doc__)
    ap.add_argument("--set", default="calib", choices=["calib"])
    ap.add_argument("--write-results", action="store_true")
    a = ap.parse_args(argv)
    rep = run_pipeline(a)
    out = out_dir(a)
    d, _ = fixtures_args(a)
    ev = evaluate(out, rep, d)
    dump(out / "oracle_eval.json", ev)
    if a.write_results:
        doc = RS.oracle_calib(out, rep, ev)
        dump(results_dir() / "oracle_calib.json", doc)
        rc, last = validate("result", results_dir() / "oracle_calib.json")
        if rc != 0:
            ev["failures"].append({"criterion": "C15", "detail": last})
    for f in ev["failures"][:30]:
        say(f"FALHA ({f['criterion']}) {f.get('case_id', '')} {f.get('flows', f.get('judge', f.get('detail', '')))}")
    say(f"oracle_eval: julgados {ev['judged']}; referência {sum(r['ok'] for r in ev['reference'])}/"
        f"{len(ev['reference'])}; negativos {len(ev['negatives'])}; falhas {len(ev['failures'])} -> "
        f"{'OK' if not ev['failures'] else 'REPROVADO'}")
    return 0 if not ev["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
