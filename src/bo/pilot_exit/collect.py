"""Evidência dos critérios a partir do que o código congelado gravou na caixa (sem copiar valor de configuração).

Cada fatia tem um adaptador para os arquivos do SEU E2E (formatos lidos do código congelado em bo/base, não
inventados): onde ficam casos, traço C23, plano C26, julgamento do oráculo, grão e controles. As medidas são
calculadas aqui, pelo avaliador, com regras fixas declaradas em RULES (não pelo veredito que o E2E dá a si mesmo):

  E1 direções   por direção, no controle principal c3_full: coberta se TODO caso dela terminou com saída
                renderizada, UNSUPPORTED declarado ou REFUSED tipado; RENDER_BLOCKED, MISSING ou sem caso = não coberta
     traço      valor do plano C26 com origin=carried sem traço C23 'carried' do mesmo caso cuja saída é
                <provedor>:<tipo>:<campo> (índices de lista ignorados); synthesized marcado é inserção declarada
     inserção   atributo do HCL fora do plano e das inserções declaradas: o relatório do no_silent_insert do E2E
                (python-hcl2) e caso RENDERED sem conferência conta como inserção não conferida
  E2            casos obrigatórios das retidas sem linha de comparação contam como divergência (nunca vácuo)
  E4            no c3_full: casos com silent_losses; casos com negatives_carried + negativos 'rejects' transportados
                + traduções de referência negativas que o juiz não rejeita
  E5            mesma entrada pelos invariantes do próprio run (casos, ABox, perda, transformações) e contagem
                por controle e polaridade feita aqui
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import claims_check, common as C, controls as K

RULES = __doc__.split("\n\n", 1)[1]
OK_STATES = ("UNSUPPORTED", "REFUSED")
GOOD = ("ACCEPT", "ACCEPT_WITH_DECLARED_LOSS")


class CollectError(RuntimeError):
    pass


def _jsonl(p: Path) -> list:
    return C.read_jsonl(p) if p.is_file() else []


def _field(f: str) -> str:
    return re.sub(r"\.\d+(?=\.|$)", "", f)


# ------------------------------------------------------------------------------------------------- comandos
def net_commands(cmds: list[str], frozen_repo: Path, out: Path) -> list[str]:
    """Os gates do E2E com a interface que o próprio E2E declarou para o PILOT-EXIT (--fixtures PASTA, --out).
    O grain_check grava numa pasta própria: o bo.pilot.run apaga a pasta de saída inteira antes de gravar."""
    fx = frozen_repo / "pilot" / "net" / "fixtures_calib"
    res = []
    for c in cmds:
        c = c.replace("--fixtures calib", f"--fixtures {fx}")
        if "--fixtures" not in c:
            c += f" --fixtures {fx}"
        o = out.parent / "out_grain" if ".grain_check" in c else out
        res.append(c + f" --out {o}")
    return res


# Sonda STO: chama a API do próprio código congelado (a mesma corrida determinística que o oracle_eval dele refaz)
# e grava, por controle e entrada, só estado, códigos e veredito; nenhum valor de configuração.
STO_PROBE = r'''
import json, sys
from bo.pilot.sto import evaluate as E, pipeline as PL, stage as ST
out = ST.run_all(write=False)
res = out["res"]
j = E.judge_runs(res)
neg = E.negatives(out["ctx"], res)
rows = []
for ctl, runs in res["runs"].items():
    for r, e, jj in zip(runs, res["entries"], j[ctl]):
        rows.append({"control": ctl, "entry_id": e["entry_id"], "direction": e["direction"], "family": e["family"],
                     "variant": e["variant"], "status": r.status, "block_code": (r.block or [None])[0],
                     "plan_id": (r.plan or {}).get("plan_id"), "verdict": jj.get("verdict"), "code": jj.get("code"),
                     "n_spurious_declared": len(jj.get("spurious_declared") or [])})
negs = {ctl: {"fixture_claims": [{k: x.get(k) for k in ("fixture_id", "case", "about", "answer", "code")}
                                 for x in v["fixture_claims"]],
              "candidates": [{k: x.get(k) for k in ("entry_id", "variant", "answer")} for x in v["candidates"]]}
        for ctl, v in neg.items()}
json.dump({"rows": rows, "negatives": negs}, open(sys.argv[1], "w"), ensure_ascii=False, sort_keys=True)
'''


def commands(slice_: str, cmds: list[str], frozen_repo: Path, out: Path) -> list[str]:
    if slice_ == "net":
        return net_commands(cmds, frozen_repo, out)
    out.mkdir(parents=True, exist_ok=True)
    probe = out / "sto_probe.py"
    probe.write_text(STO_PROBE, encoding="utf-8")
    return list(cmds) + [f"python -I {probe} {out / 'sto_probe.json'}"]


# ------------------------------------------------------------------------------------------------- comum
def directions_from(rows: list[dict]) -> tuple[dict, dict]:
    per = defaultdict(Counter)
    for r in rows:
        per[r["direction"]][r["state"]] += 1
    out = {}
    for d in C.DIRECTIONS:
        st = per.get(d)
        if not st:
            out[d] = "MISSING"
        elif all(k in ("OUTPUT",) + OK_STATES for k in st):
            out[d] = "OUTPUT" if st.get("OUTPUT") else "UNSUPPORTED"
        else:
            out[d] = "INCOMPLETE"
    return out, {d: dict(v) for d, v in sorted(per.items())}


def trace_gaps(rows: list[dict], plans: dict, traces: list[dict]) -> dict:
    carried = defaultdict(set)
    for t in traces:
        if t.get("result") == "carried" and isinstance(t.get("output"), dict) and t.get("case_id"):
            carried[t["case_id"]].add(t["output"].get("atom_id"))
    total, missing, kinds = 0, 0, Counter()
    for r in rows:
        p = plans.get(r.get("plan_id"))
        if not p:
            continue
        for s in p["steps"]:
            for v in s.get("values", []):
                if v.get("origin") != "carried":
                    continue
                total += 1
                atom = f"{p['target_provider']}:{s['resource_type']}:{_field(v['field'])}"
                if atom not in carried[r["case_id"]]:
                    missing += 1
                    kinds[(v.get("term") or {}).get("kind", "?")] += 1
    return {"carried_values": total, "without_trace": missing, "without_trace_by_term_kind": dict(kinds)}


# ------------------------------------------------------------------------------------------------- NET
def net(bundle: dict, frozen_repo: Path, data_root: Path, out: Path, cmd_results: list[dict]) -> dict:
    rows = _jsonl(out / "cases.jsonl")
    if not rows:
        raise CollectError("NET: cases.jsonl ausente na saída do código congelado")
    rep = C.read_json(out / "run_report.json") or {}
    plans = {p["plan_id"]: p for p in _jsonl(out / "lowering_plan.jsonl")}
    traces = _jsonl(out / "translation_trace.jsonl")
    fx = {f["fixture_id"]: f for f in bundle["fixtures"]}
    prim = [r for r in rows if r["control"] == "c3_full"]

    def state(r):
        if r["status"] == "TRANSLATED" and r.get("render_status") == "RENDERED":
            return "OUTPUT"
        return r["status"] if r["status"] in OK_STATES else (r["status"] or "MISSING")
    srows = [dict(r, state=state(r)) for r in prim]
    dirs, dir_states = directions_from(srows)
    tg = trace_gaps(prim, plans, [t for t in traces if t.get("control") == "c3"])
    nsi = C.read_json(out / "no_silent_insert.json") or {}
    rendered = sum(1 for r in prim if r.get("render_status") == "RENDERED")
    inserted = sum(1 for b in nsi.get("failures", []) for i in b.get("issues", [])
                   if "INSERTED" in json.dumps(i) or "EXTRA_RESOURCE" in json.dumps(i) or "VAR_DEFAULT" in json.dumps(i))
    unchecked = max(0, rendered - int(nsi.get("checked", 0))) if nsi else rendered
    # E2: gabarito das retidas = casos obrigatórios do expected_answers materializado
    ea = C.read_json(frozen_repo / "pilot" / "net" / "expected_answers.json") or {}
    mand = sorted({f for c in ea.get("mandatory_cases", {}).values() for lst in (c.get("calib") or {}).values()
                   for f in lst if f in fx})
    gc = C.read_json(out.parent / "out_grain" / "grain_check.json") or {}
    grow = {r["fixture_id"]: r for r in gc.get("rows", [])}
    g_mis = [f for f in mand if f not in grow or not grow[f].get("equal")]
    g_reord = [f for f in mand if f in grow and not grow[f].get("reorder_invariant")]
    pairs = sorted({tuple(sorted((f, x["expected"]["decomposition_invariant_with"]))) for f, x in fx.items()
                    if x["expected"].get("decomposition_invariant_with") in fx})
    pk = {tuple(sorted(p["pair"])): p["invariant"] for p in gc.get("packaging", [])}
    g_pack = [p for p in pairs if not pk.get(p)]
    # E4
    judged = [r for r in prim if r.get("judge")]
    silent = [r["case_id"] for r in judged if r["judge"]["silent_losses"]]
    carried_neg = [r["case_id"] for r in judged if r["judge"]["negatives_carried"]]
    oe = C.read_json(out / "oracle_eval.json") or {}
    rej_bad = [f"{n['fixture_id']} {d}" for n in oe.get("negatives", []) for d in n.get("transported_when_must_reject", [])]
    ref_bad = [r["case_id"] for r in oe.get("reference", []) if r.get("polarity") == "negative" and r.get("judge") != "REJECT"]
    ref_all = len([t for t in bundle.get("translations", [])])
    correct = sum(1 for r in prim if (r.get("verdict") in GOOD) or
                  (fx.get(r["fixture_id"], {}).get("polarity") == "negative" and r["status"] == "REFUSED"))
    # E5: controles
    inv = rep.get("invariants") or {}
    same = bool(inv.get("same_case_set") and inv.get("same_abox_for_c2_c3") and inv.get("same_loss_policy")
                and inv.get("same_transform_per_claim"))
    by_case = defaultdict(dict)
    for r in rows:
        by_case[(r["fixture_id"], r["direction"])][r["control"]] = r
    cases = []
    for (fid, d), cs in sorted(by_case.items()):
        f = fx.get(fid, {})
        pol = f.get("polarity", "unknown")
        rejects = (f.get("check") or {}).get("kind") == "rejects"

        def outcome(r):
            if r is None:
                return "absent"
            if rejects and pol == "negative":
                if r["status"] == "REFUSED":
                    return "correct"
                return "incorrect" if r.get("render_status") == "RENDERED" else "absent"
            v = r.get("verdict")
            if v in GOOD:
                return "correct"
            if v == "REJECT":
                return "incorrect"
            return "absent"
        rr = {k: cs.get(k) for k in K.CONTROLS}
        cases.append({"case_id": f"{fid} {d}", "family": f.get("case", "?"), "polarity": pol,
                      "c1": outcome(rr["c1_table"]), "c2": outcome(rr["c2_taxonomy"]), "c3": outcome(rr["c3_full"]),
                      "c1_rejects": (rr["c1_table"] or {}).get("status") == "REFUSED",
                      "c2_rejects": (rr["c2_taxonomy"] or {}).get("status") == "REFUSED",
                      "c3_rejects": (rr["c3_full"] or {}).get("status") == "REFUSED", "transport_changed": False})
    just = K.justified([t for t in traces if t.get("control") == "c3"],
                       [c for r in prim for c in (r.get("consequences") or [])])
    rule = K.r_ctrl(cases, K.n_required(frozen_repo))
    counts = K.counts(cases)
    ctrl = {"available": True, "same_input": same, "consequences_counted": bool(cases) and just["c3_bad_justification"] == 0,
            "input_sha": {k: rep.get("abox_sha256") if k != "c1_table" else (rep.get("fixtures") or {}).get("sha256")
                          for k in K.CONTROLS},
            "input_note": "c1 não usa ABox (tabela); c2 e c3 a mesma ABox; o mesmo conjunto de casos e de fixtures nos 3",
            "invariants": {k: inv.get(k) for k in ("same_case_set", "same_abox_for_c2_c3", "same_loss_policy",
                                                   "same_transform_per_claim")},
            "n_cases": len(cases), "counts": counts, "justified": just, "rule": rule,
            "status_by_control": rep.get("counts"),
            "note": "c3 'correto' em fixture negativa do tipo rejects = REFUSED; nas demais = veredito ACCEPT ou "
                    "ACCEPT_WITH_DECLARED_LOSS do juiz do oráculo; REJECT = incorreto; sem julgamento = ausente"}
    return {"directions": dirs, "direction_states_c3": dir_states, "values_total": tg["carried_values"],
            "values_without_trace": tg["without_trace"], "trace_detail": tg,
            "silent_insertions": inserted + unchecked,
            "insertion_detail": {"rendered": rendered, "checked": nsi.get("checked"), "inserted": inserted,
                                 "unchecked": unchecked, "uncaught_mutations": len(nsi.get("uncaught_mutations", []))},
            "grain": {"mandatory_total": len(mand), "compared": sum(1 for f in mand if f in grow),
                      "mismatches": len(g_mis) + len(g_reord), "mismatch_ids": g_mis, "reorder_failures": g_reord,
                      "invariance_variants": len(pairs) + len(mand), "invariance_failures": len(g_pack) + len(g_reord),
                      "packaging_failures": [list(p) for p in g_pack]},
            "oracle": {"items": len(prim), "judged": len(judged), "correct": correct, "silent_losses": len(silent),
                       "negatives_carried": len(carried_neg) + len(rej_bad) + len(ref_bad),
                       "silent_loss_cases": silent, "negative_carried_cases": carried_neg,
                       "rejects_transported": rej_bad, "reference_negatives_not_rejected": ref_bad,
                       "reference_total": ref_all, "reference_ok": sum(1 for r in oe.get("reference", []) if r.get("ok")),
                       "verdicts_c3": dict(Counter(r.get("verdict") for r in judged)),
                       "accuracy_rule": "acerto = caso c3 com veredito ACCEPT/ACCEPT_WITH_DECLARED_LOSS, ou fixture "
                                        "negativa recusada (REFUSED); denominador = todos os casos c3"},
            "controls": ctrl}


# ------------------------------------------------------------------------------------------------- STO
def sto(bundle: dict, frozen_repo: Path, data_root: Path, out: Path, cmd_results: list[dict]) -> dict:
    sd = data_root / "PILOT-STO-E2E" / ".staging"
    pr = C.read_json(out / "sto_probe.json")
    if not pr:
        raise CollectError("STO: a sonda do código congelado não gravou sto_probe.json")
    ent = {e["entry_id"]: e for e in bundle["entries"]}
    fxs = {f["fixture"]["fixture_id"]: f for f in bundle["fixtures"]}
    render = (C.read_json(sd / "render_status.json") or {}).get("plans") or {}

    def rstat(pid):
        v = render.get(pid)
        return v if isinstance(v, str) else (v or {}).get("status")
    rows = pr["rows"]
    prim = [r for r in rows if r["control"] == "c3_full"]

    def state(r):
        if r["status"] == "LOWERED":
            return "OUTPUT" if rstat(r["plan_id"]) == "RENDERED" else "RENDER_BLOCKED"
        return "UNSUPPORTED" if r.get("block_code") else "MISSING"
    srows = [dict(r, state=state(r)) for r in prim]
    dirs, dir_states = directions_from(srows)
    plans = {p["plan_id"]: p for p in _jsonl(sd / "lowering_plan.jsonl")}
    traces = _jsonl(sd / "translation_trace.jsonl")
    case_of = {}
    for t in traces:
        cid = t.get("case_id") or ""
        if cid.startswith("CASE-PSTO-"):
            case_of.setdefault(cid, cid[len("CASE-PSTO-"):])
    tr_rows = [{"case_id": "CASE-PSTO-" + r["entry_id"], "plan_id": r["plan_id"]} for r in prim if r["plan_id"]]
    tg = trace_gaps(tr_rows, plans, [t for t in traces if t.get("control") == "c3"])
    nsi = C.read_json(sd / "nsi_report.json") or {}
    study = nsi.get("study") or {}
    rendered = sum(1 for r in prim if r["status"] == "LOWERED" and rstat(r["plan_id"]) == "RENDERED")
    checked = sum(int(v.get("checked", 0)) for v in study.values() if isinstance(v, dict))
    inserted = sum(len(v.get("problems") or []) for v in study.values() if isinstance(v, dict)) + \
        len(nsi.get("judged_vs_plan") or [])
    unchecked = max(0, rendered - checked)
    # E2: conferências de decomposição das retidas (contadas aqui) x as que o grain_check comparou
    gr = C.read_json(sd / "grain_report.json") or {}
    want = sum(1 for f in fxs.values() for c in f["checks"] if c["kind"] == "decomposition")
    got = int(gr.get("decomposition_checks") or 0)
    g_mis = len(gr.get("decomposition_mismatches") or []) + max(0, want - got)
    g_inv = len(gr.get("reorder_failures") or []) + len(gr.get("packaging_failures") or [])
    # E4 (c3_full)
    judged = [r for r in prim if r["status"] == "LOWERED"]
    silent = [r["entry_id"] for r in judged if r["verdict"] == "REJECT"]
    n3 = pr["negatives"].get("c3_full", {})
    acc_claims = [x["fixture_id"] for x in n3.get("fixture_claims", []) if x["answer"] == "ACCEPT"]
    acc_cand = [x["entry_id"] for x in n3.get("candidates", []) if x["answer"] == "ACCEPT"]
    grain_neg = [x.get("fixture_id") for x in gr.get("negative_not_rejected") or []]
    correct = sum(1 for r in judged if r["verdict"] in GOOD)
    # E5
    rec = C.read_json(sd / "run_record.json") or {}
    pc = rec.get("per_control") or {}
    keys = ("input_sha256", "policy_sha256", "transforms_sha256", "claims_sha256", "verdicts_sha256")
    same = bool(pc) and all(len({(pc.get(c) or {}).get(k) for c in K.CONTROLS}) == 1 for k in keys) and \
        set(pc) == set(K.CONTROLS)
    by = defaultdict(dict)
    for r in rows:
        by[r["entry_id"]][r["control"]] = r

    def outcome(r):
        if not r or r["status"] != "LOWERED":
            return "absent"
        return "correct" if r["verdict"] in GOOD else "incorrect" if r["verdict"] == "REJECT" else "absent"
    cases = []
    for eid, cs in sorted(by.items()):
        e = ent.get(eid, {})
        cases.append({"case_id": eid, "family": e.get("family", "?"), "polarity": e.get("polarity", "unknown"),
                      "c1": outcome(cs.get("c1_table")), "c2": outcome(cs.get("c2_taxonomy")),
                      "c3": outcome(cs.get("c3_full")), "transport_changed": False})
    # contraexemplos das fixtures (alegações): rejeitar é a resposta certa; entram como casos negativos próprios
    fc = {c: {(x["fixture_id"], x.get("about")): x["answer"] for x in pr["negatives"].get(c, {}).get("fixture_claims", [])}
          for c in K.CONTROLS}
    for key in sorted(set().union(*[set(v) for v in fc.values()])):
        ans = {c: fc[c].get(key) for c in K.CONTROLS}
        oc = {c: ("correct" if a == "REJECT" else "incorrect" if a == "ACCEPT" else "absent") for c, a in ans.items()}
        cases.append({"case_id": f"{key[0]}:{key[1]}", "family": (fxs.get(key[0], {}).get("fixture") or {}).get("case", "?"),
                      "polarity": "negative", "c1": oc["c1_table"], "c2": oc["c2_taxonomy"], "c3": oc["c3_full"],
                      "c1_rejects": ans["c1_table"] == "REJECT", "c2_rejects": ans["c2_taxonomy"] == "REJECT",
                      "c3_rejects": ans["c3_full"] == "REJECT", "transport_changed": False})
    just = K.justified([t for t in traces if t.get("control") == "c3"], [])
    rule = K.r_ctrl(cases, K.n_required(frozen_repo))
    ctrl = {"available": True, "same_input": same, "consequences_counted": bool(cases) and just["c3_bad_justification"] == 0,
            "input_sha": {c: (pc.get(c) or {}).get("input_sha256") for c in K.CONTROLS},
            "invariants": {k: len({(pc.get(c) or {}).get(k) for c in K.CONTROLS}) == 1 for k in keys},
            "n_cases": len(cases), "counts": K.counts(cases), "justified": just, "rule": rule,
            "status_by_control": {c: dict(Counter(r["status"] for r in rows if r["control"] == c)) for c in K.CONTROLS},
            "note": "entrada de direção: correto = a tradução que desceu é aceita pelo juiz do oráculo (com ou sem "
                    "perda declarada), incorreto = REJECT, ausente = não desceu; alegação-contraexemplo das fixtures: "
                    "correto = REJECT, incorreto = ACCEPT, ausente = ABSTAIN"}
    return {"directions": dirs, "direction_states_c3": dir_states, "values_total": tg["carried_values"],
            "values_without_trace": tg["without_trace"], "trace_detail": tg, "silent_insertions": inserted + unchecked,
            "insertion_detail": {"rendered": rendered, "checked": checked, "inserted": inserted, "unchecked": unchecked,
                                 "canary": {k: {kk: v.get(kk) for kk in ("plans", "rendered", "checked")}
                                            for k, v in (nsi.get("canary") or {}).items()}},
            "grain": {"mandatory_total": want, "compared": got, "mismatches": g_mis,
                      "invariance_variants": int(gr.get("reorder_trials") or 0) + int(gr.get("packaging_trials") or 0),
                      "invariance_failures": g_inv},
            "oracle": {"items": len(prim), "judged": len(judged), "correct": correct, "silent_losses": len(silent),
                       "negatives_carried": len(acc_claims) + len(acc_cand) + len(grain_neg),
                       "silent_loss_cases": silent, "accepted_negative_claims": acc_claims,
                       "accepted_negative_candidates": acc_cand, "grain_negatives_not_rejected": grain_neg,
                       "verdicts_c3": dict(Counter(r["verdict"] for r in prim)),
                       "block_codes_c3": dict(Counter(r["block_code"] for r in prim if r["block_code"])),
                       "accuracy_rule": "acerto = entrada c3 que desceu e o juiz do oráculo aceita; denominador = "
                                        "todas as entradas de direção c3"},
            "controls": ctrl}


# ------------------------------------------------------------------------------------------------- entrada
def collect(slice_: str, bundle: dict, frozen_repo: Path, data_root: Path, cmd_results: list[dict], logdir: Path,
            out: Path | None = None) -> dict:
    s = C.SLICES[slice_]
    out = out or (logdir.parent / "out")
    ev = (net if slice_ == "net" else sto)(bundle, frozen_repo, data_root, out, cmd_results)
    m, v = data_root / s["map"] / "mapping.sssom.tsv", data_root / s["map"] / "verdicts.jsonl"
    ev["claims"] = claims_check.check(m, v)
    ev["claims"].update({"sssom": f"$BO_DATA/{s['map']}/mapping.sssom.tsv", "verdicts": f"$BO_DATA/{s['map']}/verdicts.jsonl",
                         "sssom_sha256": C.sha_file(m) if m.is_file() else None,
                         "verdicts_sha256": C.sha_file(v) if v.is_file() else None})
    ev.update({"slice": slice_, "e2e": s["e2e"], "measure_rules": RULES,
               "e2e_commands": [{"i": c["i"], "cmd": re.sub(r"/\S+/(run|rehearsal)/", "$BO_TMP/run/", c["cmd"]),
                                 "rc": c["rc"], "seconds": c["seconds"]} for c in cmd_results]})
    return ev
