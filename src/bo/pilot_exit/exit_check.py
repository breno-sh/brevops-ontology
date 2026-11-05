"""G2: aplica E1–E8 (prereg/pilot_exit.yaml) à execução registrada e grava a saída.

  python -I -m bo.pilot.exit_check --criteria $BO_REPO/prereg/pilot_exit.yaml   (-> bo.pilot_exit.exit_check)

Ordem: evidência das fatias (heldout_run) -> E6 (ledger de emendas, invalidação, catálogo) -> E7 (esforço; grava
effort_calibration.json pelo mesmo código do bo.plan.reestimate) -> adendo (controles, R-CTRL, emendas, esforço)
-> E5 (adendo antes da escala) -> E8 (tentativas) -> exit_report.json (C15). Sai 0 só se E1–E8 passam.
Reprovação é resultado: nada é ajustado. Com E1–E6 reprovados a expansão fica bloqueada
(results/PILOT-EXIT/EXPANSION_BLOCKED.txt); na 2ª tentativa reprovada o plano volta para revisão (v4).
FREEZE-P (freeze/FREEZE-P/freeze_receipt.json) só é criado quando a saída passa (é o congelamento que libera a
escala; comprovante é único, então não se cria um para uma saída reprovada).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from . import addendum as AD, amendments as AM, common as C, criteria as CR, reestimate as RE

STAMP = re.compile(r"Escrito por PILOT-EXIT em [^ ]+ ")


def catalog_modules() -> dict:
    return {m["stable_id"]: m for m in RE.catalog()["modules"]}


def scale_started(root: Path, cat: dict) -> list[str]:
    """Módulo de escala (o que espera o PILOT-EXIT, §3b) com commit em bo/base = a escala começou."""
    wait = {m for m in cat if m.startswith(("MAP-", "SMOKE-", "DEP-", "PROBE-")) or m == "DECOMPOSE"
            or re.fullmatch(r"GLOSSARY-(CMP|DB|NET|OPS|SEC|STO)", m)}
    subj = subprocess.run(["git", "-C", str(root), "log", "--format=%s", "bo/base"], capture_output=True,
                          text=True).stdout.splitlines()
    return sorted({m for s in subj for m in wait if s.startswith(f"[{m}]")})


FROZEN_MODULES = ("PILOT-STO-E2E", "PILOT-STO-MAP", "PILOT-STO-GLOSS", "PILOT-STO-ORACLE", "PILOT-NET-E2E",
                  "PILOT-NET-MAP", "PILOT-NET-GLOSS", "PILOT-NET-ORACLE", "GRAIN", "SERVICE-EVIDENCE", "ARBITERLIB",
                  "CONTRACTS", "SEMANTICS")
DECL_MARKS = ("DESVIO DECLARADO", "REGRA DE CONSOLIDAÇÃO", "DECLARAÇÕES DE INTEGRIDADE", "CORREÇÃO DA R2",
              "CICLO V4", "REGRA R6", "DECLARAÇÃO D-")


def reseals(root: Path) -> dict:
    """Re-selagens declaradas pelos oráculos no índice selado ativo (sem conteúdo retido)."""
    from . import unseal
    out = {}
    for s in C.SLICES:
        try:
            i = unseal.index_of(s, root)
        except unseal.SealError:
            continue
        out[s] = {"envelope_sha256": unseal.envelope_sha(s, i), "plaintext_sha256": i.get("plaintext_sha256"),
                  "set_version": i.get("set_version"), "revision": i.get("revision"),
                  "reason": i.get("reseal_reason") or (i.get("revision") or {}).get("reason") if isinstance(
                      i.get("revision"), dict) else i.get("reseal_reason")}
    return out


def frozen_state(root: Path, base: str) -> dict:
    """Último commit [ID] de cada módulo de que a avaliação depende, no bo/base da execução."""
    log = subprocess.run(["git", "-C", str(root), "log", "--format=%h%x09%s", base], capture_output=True,
                         text=True).stdout.splitlines()
    out = {}
    for m in FROZEN_MODULES:
        for line in log:
            h, sj = line.split("\t", 1)
            if sj.startswith(f"[{m}]"):
                out[m] = h
                break
    arb = root / "arbiter" / "ARBITER.sha256"
    out["arbiter/ARBITER.sha256"] = C.sha_file(arb)[:16] if arb.is_file() else None
    return out


def prereg_declarations(root: Path) -> list[str]:
    """Declarações do PREREG que valem para esta tentativa (results/PREREG/AMENDMENTS.txt), copiadas como estão."""
    p = root / "results" / "PREREG" / "AMENDMENTS.txt"
    if not p.is_file():
        return []
    blocks, cur = [], None
    for line in p.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\d{4}-\d\d-\d\dT", line):
            cur = [line] if any(k in line for k in DECL_MARKS) else None
            if cur is not None:
                blocks.append(cur)
        elif cur is not None:
            cur.append(line)
    return ["\n".join(b) for b in blocks]


def e2_split(ev_slices: dict) -> dict | None:
    """Declaração D-e do PREREG: o E2 relatado em duas partes, (i) itens nunca reabertos e (ii) itens reabertos no
    diagnóstico DIAG_T3. A lista de reabertos fica em $BO_DATA/PILOT-EXIT/reopened_T3.json (ids, fora do git);
    aqui só as contagens. O veredito oficial do E2 continua o do conjunto todo."""
    ro = C.read_json(C.data_dir() / "reopened_T3.json")
    if not ro:
        return None
    out = {}
    for s, e in sorted(ev_slices.items()):
        g = e.get("grain") or {}
        reo = set(ro.get(s, []))
        mis = set(g.get("mismatch_ids") or [])
        inv = set(g.get("invariance_failure_ids") or [])
        for pr in g.get("packaging_failures") or []:
            inv.update(pr)
        out[s] = {"reopened_items": len(reo),
                  "never_reopened": {"mismatches": len(mis - reo), "invariance_failures": len(inv - reo)},
                  "reopened": {"mismatches": len(mis & reo), "invariance_failures": len(inv & reo)},
                  "unattributed": max(0, int(g.get("mismatches") or 0) - len(mis))}
    return out


def load_evidence() -> dict:
    out = {}
    for s in C.SLICES:
        p = C.run_data_dir() / s / "evidence.json"
        if p.is_file():
            out[s] = C.read_json(p)
    return out


VOLATILE = re.compile(r"\[\d{4}-\d\d-\d\dT[\d:]+[-+]\d\d:\d\d\] | in \d+\.\d+s")


def stable(tail: dict) -> dict:
    """Cauda de saída sem carimbo de hora nem duração (o relatório regenera igual)."""
    return {"rc": tail["rc"], "tail": VOLATILE.sub("", tail["tail"])}


def write_if_changed(p: Path, text: str, stamp_re=None) -> None:
    if p.is_file():
        old = p.read_text(encoding="utf-8")
        a, b = (stamp_re.sub("", old), stamp_re.sub("", text)) if stamp_re else (old, text)
        if a == b:
            return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def metric(mid: str, name: str, k: int, n: int, frame: str, rule: str, text: str) -> dict:
    from bo.metrics.core import wilson
    lo, hi = wilson(k, n) if n else (0.0, 1.0)
    return {"metric_id": mid, "name": name, "reading": "decision", "axis": "operational",
            "quantifier": "observed_fraction",
            "operational_coverage": {"lower": round(lo, 4), "upper": round(hi, 4),
                                     "est": round(k / n, 4) if n else None, "n": n, "n_known": n},
            "frame": {"description": frame}, "inclusion": {"rule_id": rule, "text": text},
            "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "wilson", "level": 0.95}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_exit.exit_check")
    ap.add_argument("--criteria", required=True)
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)
    root = C.repo()
    crit_p = Path(a.criteria)
    crit = yaml.safe_load(crit_p.read_text(encoding="utf-8"))
    crit_sha = C.sha_file(crit_p)
    rec = C.read_json(C.results_dir(root) / "heldout_run.json") or {}
    ev_slices = load_evidence()
    problems = []
    if not rec:
        problems.append("sem execução registrada (rode bo.pilot.heldout_run)")
    elif rec.get("criteria", {}).get("sha256") != crit_sha:
        problems.append("critérios mudaram depois da execução (o pré-registro não pode mudar)")
    cat = catalog_modules()
    led = AM.ledger(root, cat)
    stale = AM.stale_not_marked(root)
    catok = AM.catalog_ok(root)
    catok = {"catalog_ok": catok["catalog_ok"], "where": catok["where"], "core_integration": stable(catok["core_integration"]),
             "contracts_all_stubs": stable(catok["contracts_all_stubs"])}
    eff = RE.build(root / "results", root)
    C.write_json(C.results_dir(root) / "effort_calibration.json", RE.c15(eff))
    for m, r in eff["pilot_modules"].items():
        r["plan_h"] = cat.get(m, {}).get("effort_h")
    attempts = rec.get("attempt", 0)
    ev = {"slices": ev_slices,
          "amendments": {"unversioned_changes": led["unversioned_changes"], "stale_not_marked": stale["stale_not_marked"],
                         "catalog_ok": catok["catalog_ok"]},
          "effort": {"steps_without_effort": eff["steps_without_effort"], "schedule_recomputed": eff["schedule_recomputed"]}}
    first = CR.evaluate(crit["criteria"], ev, only={"E1", "E2", "E3", "E4", "E6", "E7"})
    controls = {s: (e.get("controls") or {"available": False, "why": "fatia sem evidência"}) for s, e in
                {s: ev_slices.get(s, {}) for s in C.SLICES}.items()}
    for s, c in controls.items():
        c.setdefault("oracle", C.SLICES[s]["oracle"])
    gen_at = rec.get("finished_at") or C.now()
    started = scale_started(root, cat)
    base = (rec.get("frozen_code") or {}).get("sto", {}).get("base_head") or "bo/base"
    fstate = frozen_state(root, base)
    decls = prereg_declarations(root)
    claims_vs_abs = {s: {k: (e.get("claims") or {}).get(k) for k in ("total", "absences")} for s, e in ev_slices.items()}
    rs = reseals(root)
    add_doc = {"written_at": C.now(), "frozen_state": fstate, "reseals": rs, "attempt_global": rec.get("attempt_global"), "declarations": decls, "claims_vs_absences": claims_vs_abs,
               "base": base, "criteria_sha256": crit_sha, "attempt": attempts,
               "attempts_max": crit.get("attempts_max"), "controls": controls, "amendments": led,
               "effort": eff, "criteria": first, "decision": "(provisório: E5 e E8 ainda não avaliados)"}
    add_p = root / "prereg" / "ADDENDUM_PILOTS.html"
    txt = AD.render(add_doc, crit["reasoning_controls_rule"])     # o arquivo é gravado uma vez, no fim desta execução
    has_lines = all(f"Fatia {s}: R-CTRL-" in txt for s in C.SLICES)
    ev["addendum"] = {"written_before_scale": bool(has_lines and not started), "path": C.portable(add_p, root),
                      "scale_modules_started": started, "has_r_ctrl_lines": has_lines}
    e16_fail = [k for k in ("E1", "E2", "E3", "E4", "E6") if not first[k]["pass"]]
    e5 = CR.evaluate(crit["criteria"], ev, only={"E5"})["E5"]
    if not e5["pass"]:
        e16_fail.append("E5")
    failed = bool(e16_fail) or bool(problems)
    notice = C.results_dir(root) / "EXPANSION_BLOCKED.txt"
    blocked = failed
    v4 = failed and attempts >= int(crit.get("attempts_max", 2))
    if failed:
        write_if_changed(notice, (
            f"EXPANSÃO BLOQUEADA — PILOT-EXIT, resultado de {gen_at} (America/Recife)\n"
            f"Tentativa {attempts} de {crit.get('attempts_max')}. Critérios E1–E6 reprovados: {', '.join(e16_fail) or '-'}.\n"
            + (f"Problemas da execução: {'; '.join(problems)}\n" if problems else "")
            + ("O PLANO VOLTA PARA REVISÃO (v4): E1–E6 falharam duas vezes (E8).\n"
               "Caminho de saída: conjunto retido NOVO ou provedor retido (Alibaba); este conjunto retido não é "
               "reusado em nenhuma tentativa.\n" if v4 else
               "Corrigir por emenda versionada e repetir (conta uma tentativa); a escala não começa.\n")
            + "Aviso ao Breno: este arquivo e o relatório do módulo (o coordenador repassa).\n"
            "Bloqueia: DECOMPOSE, 6 glossários, 36 mapeadores e 16 módulos de nuvem.\n"))
    elif notice.is_file():
        notice.unlink()
    ev["attempts"] = {"attempts": attempts, "expansion_blocked": blocked, "plan_returned_v4": v4,
                      "breno_notified": notice.is_file() if failed else False}
    final = dict(first, E5=e5, **CR.evaluate(crit["criteria"], ev, only={"E8"}))
    final = {k: final[k] for k in sorted(final)}
    ok = all(v["pass"] for v in final.values()) and not problems
    decision = ("SAÍDA APROVADA: E1–E8 passam; a escala pode começar depois do FREEZE-P" if ok else
                f"SAÍDA REPROVADA (tentativa {attempts}): {', '.join(k for k, v in final.items() if not v['pass'])} "
                "reprovam; a expansão não começa" + ("; o plano volta para revisão (v4)" if v4 else ""))
    add_doc.update(criteria=final, decision=decision)
    write_if_changed(add_p, AD.render(add_doc, crit["reasoning_controls_rule"]), STAMP)
    open_items = [r for r in led["requests"] if r["status"] == "OPEN"]
    cc = C.results_dir(root) / "CONTRACT_CHANGE.txt"
    parts = []
    if open_items:
        parts.append("E6: mudanças pedidas pelos pilotos sem emenda versionada. O avaliador não escreve em contracts/, "
                     "grain/, briefs/ nem arbiter/: cada dono aplica a emenda (versão nova, motivo, invalidate.py check "
                     "--apply).\n" + "".join(f"- {r['module']} item {r['item']}: {r['file']}\n" for r in open_items))
    rp = root / "freeze" / "FREEZE-P" / "freeze_receipt.json"
    if rp.is_file():
        v = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "manifest_receipt", str(rp)],
                           capture_output=True, text=True, cwd=str(root))
        errs = [l.strip() for l in (v.stdout + v.stderr).splitlines() if "ERRO" in l]
        if errs:
            n_ext = sum(1 for e in errs if "transitive_inputs" in e)
            parts.append("C17 (dono: REPO, tools/freeze.py e bo.repo.receipts; e CONTRACTS, C17): o comprovante que o "
                         "tools/freeze.py grava para o FREEZE-P não passa no validador do C17: "
                         f"{len(errs)} erro(s), {n_ext} deles em transitive_inputs[].path com caminho absoluto fora de "
                         "$BO_REPO/$BO_DATA (entradas externas do catálogo nos fechos das deps; a CONVENTIONS diz que "
                         "entrada externa é ext:... e não é conferida por hash).\n"
                         "Proposta: o freeze.py grava entrada externa como 'ext:<caminho>' (ou a omite), ou o C17 aceita "
                         "o prefixo ext: em transitive_inputs[].path. O comprovante em si confere (freeze.py verify).\n")
    if parts:
        write_if_changed(cc, f"CONTRACT_CHANGE — PILOT-EXIT, resultado de {gen_at} (America/Recife)\n\n" + "\n".join(parts))
    elif cc.is_file():
        cc.unlink()
    metrics = []
    for s, e in sorted(ev_slices.items()):
        o = e.get("oracle") or {}
        if o.get("items"):
            metrics.append(metric(f"M-PILOT-ORACLE-ACC-{s.upper()}", f"fração de acerto do pipeline nas retidas ({s})",
                                  int(o.get("correct", 0)), int(o["items"]),
                                  f"itens retidos da fatia {s} (selo do {C.SLICES[s]['oracle']})",
                                  "INC-PILOT-HELDOUT-01", "todo item retido julgado pelo oráculo; relatado, não é limiar"))
        d = e.get("directions") or {}
        if d:
            metrics.append(metric(f"M-PILOT-DIRS-{s.upper()}", f"direções com saída ou UNSUPPORTED declarado ({s})",
                                  sum(1 for v in d.values() if v in ("OUTPUT", "UNSUPPORTED")), len(d),
                                  "as 12 direções ordenadas", "INC-PILOT-DIRS-01", "cada direção A->B com A != B"))
    if not metrics:
        metrics.append(metric("M-PILOT-DIRS-NONE", "direções avaliadas (sem evidência de fatia)", 0, 0,
                              "as 12 direções ordenadas", "INC-PILOT-DIRS-01", "sem execução registrada"))
    report = {"schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": C.MODULE,
              "generated_at": gen_at, "metrics": metrics,
              "notes": "PILOT-EXIT: E1–E8 do prereg/pilot_exit.yaml aplicados ao código congelado nas retidas",
              "data": {"decision": decision, "passed": ok, "attempt": attempts,
                       "criteria_file": {"path": "$BO_REPO/prereg/pilot_exit.yaml", "sha256": crit_sha},
                       "evaluated_code": {s: (rec.get("frozen_code") or {}).get(s, {}).get("code_sha256") for s in C.SLICES},
                       "problems": problems, "criteria": final,
                       "e6": {"ledger": led, "stale": stale, "catalog": catok},
                       "e7": {"class_ratio": eff["class_ratio"], "steps_without_effort": eff["steps_without_effort"],
                              "makespan_plan_h": eff["schedule"]["plan"]["makespan_h"],
                              "makespan_recalibrated_h": eff["schedule"]["recalibrated"]["makespan_h"]},
                       "e5": {"addendum": ev["addendum"],
                              "r_ctrl": {s: (c.get("rule") or {}).get("main") for s, c in controls.items()}},
                       "e8": ev["attempts"], "frozen_state": fstate, "prereg_declarations": decls,
                       "claims_vs_absences": claims_vs_abs, "e2_split_D_e": e2_split(ev_slices),
                       "reseals": rs, "attempt_global": rec.get("attempt_global"),
                       "attempt_scope": "por conjunto retido (PREREG, ciclo v4)"}}
    C.write_json(C.results_dir(root) / "exit_report.json", report)
    for k, v in final.items():
        C.say(f"exit_check: {k} {v.get('name', '')}: {'PASSA' if v['pass'] else 'REPROVA'}"
              + (f" ({v['error']})" if v.get("error") else ""))
    C.say("exit_check: " + decision)
    if ok:
        r = subprocess.run([sys.executable, "-I", str(root / "tools/freeze.py"), "create", "FREEZE-P", "--paths",
                            "$BO_REPO/prereg/ADDENDUM_PILOTS.html", "$BO_REPO/results/PILOT-EXIT/exit_report.json",
                            "$BO_REPO/results/PILOT-EXIT/effort_calibration.json", "$BO_REPO/prereg/pilot_exit.yaml",
                            "--owner", C.MODULE, "--out", str(root / "freeze/FREEZE-P/freeze_receipt.json"),
                            "--note", "FREEZE-P (§9.3): emendas dos pilotos e adendo do pré-registro"],
                           capture_output=True, text=True)
        if r.returncode != 0 and not (root / "freeze/FREEZE-P/freeze_receipt.json").is_file():
            C.say("exit_check: FREEZE-P não pôde ser criado: " + (r.stdout + r.stderr)[-300:])
            return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
