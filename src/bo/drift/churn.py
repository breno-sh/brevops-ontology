"""churn.json (C15 result): contagens por intervalo e por provider, lacunas, truncamento e métricas de censo.

As frações são de CENSO (todas as versões amostradas, todos os átomos), não de amostra: lower = upper = est e
sem intervalo de confiança. A incerteza que existe é de datação (censura intervalar), que vai em `data`.
"""
from __future__ import annotations

import datetime as _dt
from collections import Counter
from pathlib import Path

from . import common, core

ESTIMAND = ("superfície do provider Terraform (schema JSON do plugin, `terraform providers schema -json`, "
            "guardado pelos HIST-*), não a nuvem; datas são de publicação da versão do provider "
            "(atraso de disponibilidade no provider Terraform), nunca de lançamento na nuvem")


def _days(a: str, b: str) -> int:
    return (_dt.date.fromisoformat(b) - _dt.date.fromisoformat(a)).days


def provider_stats(pin: common.ProviderInput, res: core.ProviderResult, counts: dict, sents: list,
                   gfiles: list, n_hist: int) -> dict:
    date = {v.version: v.released_at for v in pin.versions}
    obs = [v.version for v in pin.observed]
    gaps = [{"version": v.version, "released_at": v.released_at, "reason": v.gap_reason} for v in pin.gaps]
    order = [v.version for v in pin.versions]
    intervals = []
    for st in res.interval_stats:
        ia, ib = order.index(st["after"]), order.index(st["until"])
        st = dict(st)
        st["after_released_at"], st["until_released_at"] = date[st["after"]], date[st["until"]]
        st["days"] = _days(date[st["after"]], date[st["until"]])
        st["spans_gap"] = order[ia + 1:ib]
        intervals.append(st)
    ev = Counter(e["event_type"] for e in res.events)
    rn = Counter()
    for e in res.events:
        if e["event_type"] == "rename":
            rn["R1_published" if e["evidence"][0]["level"] == "published" else "R2_derived"] += 1
    cand = Counter(c["status"] for c in res.candidates)
    first, last = 0, len(obs) - 1
    H = res.history
    at_first = [a for a, h in H.items() if h[first] is not None]
    at_last = [a for a, h in H.items() if h[last] is not None]
    surv = sum(1 for a in at_first if H[a][last] is not None)
    changed_atoms = {e["atom_id"] for e in res.events if e["event_type"] == "contract_change"}
    changed = sum(1 for a in at_last if a in changed_atoms)
    changed_nobp = {e["atom_id"] for e in res.events
                    if e["event_type"] == "contract_change" and e["change"]["field"] != "block_path"}
    departures = ev.get("removal", 0) + ev.get("rename", 0)
    rt_first = {res.meta[a][0] for a in at_first}
    in_old_types = sum(1 for a in at_last if res.meta[a][0] in rt_first)
    return {
        "provider": pin.provider, "hist_module": pin.module, "versions_json": common.portable(pin.versions_json),
        "versions_listed": len(pin.versions), "versions_observed": len(obs),
        "versions": [{"version": v.version, "released_at": v.released_at, "observed": v.observed,
                      **({"atoms": counts[v.version], "atoms_sha256": v.atoms_sha256} if v.observed else {})}
                     for v in pin.versions],
        "gaps": gaps,
        "left_truncation": {
            "first_listed": order[0], "first_listed_released_at": date[order[0]],
            "first_observed": obs[0], "first_observed_released_at": date[obs[0]],
            "atoms_at_first_observed": len(at_first),
            "rule": "átomo presente na primeira versão observada não tem evento de adição (entrada anterior à "
                    "janela, não observada); lacuna na ponta esquerda empurra o início da observação"},
        "intervals": intervals,
        "events": {t: ev.get(t, 0) for t in core.TYPE_ORDER},
        "contract_change_by_field": {f: sum(i["contract_change_by_field"][f] for i in intervals)
                                     for f in common.COMPARED},
        "block_path_changes_distinct_blocks": sum(i["block_path_changes_distinct_blocks"] for i in intervals),
        "atoms_at_pin_changed": changed,
        "atoms_at_pin_changed_excluding_block_path": sum(1 for a in at_last if a in changed_nobp),
        "renames_by_rule": dict(sorted(rn.items())),
        "rename_candidates_by_status": dict(sorted(cand.items())),
        "atoms_union": len(H), "atom_history_records": n_hist,
        "atoms_at_pin": len(at_last), "atoms_at_pin_in_types_of_first_observed": in_old_types,
        "guides": {"files": [common.portable(p) for p in gfiles],
                   "sha256": {common.portable(p): common.sha256_file(p) for p in gfiles},
                   "sentences_with_cue": len(sents)},
        "_metric_counts": {"survival": [surv, len(at_first)], "changed": [changed, len(at_last)],
                           "renamed_departures": [ev.get("rename", 0), departures]},
    }


def _metric(mid, name, k, n, frame_ref, frame_desc, rule, text) -> dict:
    est = (k / n) if n else None
    v = round(est, 6) if est is not None else None
    return {"metric_id": mid, "name": name, "reading": "field", "axis": "representability",
            "quantifier": "observed_fraction",
            "operational_coverage": {"lower": v if v is not None else 0.0, "upper": v if v is not None else 1.0,
                                     "est": v, "n": n},
            "frame": {"ref": frame_ref, "description": frame_desc},
            "inclusion": {"rule_id": rule, "text": text},
            "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "none"}}


def document(stats: dict, out: Path) -> dict:
    ah = out / "atom_history.jsonl"
    evp = out / "events.jsonl"
    frame = {"path": "$BO_DATA/DRIFT/atom_history.jsonl", "sha256": common.sha256_file(ah)}
    metrics = []
    for p, s in stats.items():
        P = p.upper()
        k, n = s["_metric_counts"]["survival"]
        metrics.append(_metric(f"M-DRIFT-{P}-SURVIVAL",
                               f"fração dos átomos da primeira versão observada ({p}) presentes no pin", k, n, frame,
                               f"átomos {p} presentes em {s['left_truncation']['first_observed']}",
                               "INC-DRIFT-FIRST", "átomo presente na primeira versão observada do provider"))
        k, n = s["_metric_counts"]["changed"]
        metrics.append(_metric(f"M-DRIFT-{P}-CHANGED",
                               f"fração dos átomos do pin ({p}) com ao menos uma mudança de contrato na janela",
                               k, n, frame, f"átomos {p} presentes na última versão observada",
                               "INC-DRIFT-PIN", "átomo presente na última versão observada do provider"))
        k, n = s["_metric_counts"]["renamed_departures"]
        metrics.append(_metric(f"M-DRIFT-{P}-RENAMED",
                               f"fração das saídas de átomo ({p}) explicadas por renome com prova (R1 ou R2)",
                               k, n, frame, f"eventos de remoção e de renome do {p}",
                               "INC-DRIFT-DEPART", "átomo que deixou de existir entre duas versões observadas"))
    clean = {p: {k: v for k, v in s.items() if not k.startswith("_")} for p, s in stats.items()}
    n_events = sum(sum(s["events"].values()) for s in stats.values())
    totals = {"events": n_events,
              "events_by_type": {t: sum(s["events"][t] for s in stats.values()) for t in core.TYPE_ORDER},
              "atoms": sum(s["atoms_union"] for s in stats.values()),
              "rename_candidates": sum(sum(s["rename_candidates_by_status"].values()) for s in stats.values())}
    return {
        "schema": "bo.result/1", "contract": "C15", "contract_version": "3.1.0", "module": common.MODULE,
        "generated_at": common.now(), "metrics": metrics,
        "notes": ("Censo das versões amostradas (fim de trimestre + primeira de cada major, lista do PINS); "
                  "frações sem incerteza amostral (lower = upper = est). Datas por intervalo (after, until]; "
                  "lacunas declaradas, nunca interpoladas. " + ESTIMAND + "."),
        "data": {
            "estimand": ESTIMAND,
            "label": "atraso de disponibilidade no provider Terraform",
            "interval_rule": "evento em (after, until]: after = última versão observada sem a mudança, until = "
                             "primeira observada com ela; lacuna dentro do intervalo fica em spans_gap",
            "compared_fields": list(common.COMPARED),
            "unobservable_fields": common.UNOBSERVABLE,
            "rename_rules": {
                "R1": "frase publicada no guia de atualização da major cruzada, na seção do tipo, citando os dois "
                      "nomes; 'renamed' basta, substituição exige o mesmo tf_type; par único",
                "R2": "ponte de depreciação: antigo vira deprecated no intervalo em que o novo aparece, convivem, o "
                      "antigo sai; mesmo bloco pai e tf_type; tokens de um nome contidos nos do outro; par único",
                "UNPROVEN": "par estrutural sem R1 nem R2 (saiu X, entrou Y no mesmo intervalo, mesmo pai e tf_type, "
                            "tokens relacionados, único): fica em rename_candidates.jsonl; eventos seguem remoção "
                            "+ adição",
                "scope": "renome de tipo de recurso não é evento C13 (C13-RENAME exige o mesmo tipo); entra só nas "
                         "contagens types_added/types_removed"},
            "files": {
                "events": {"path": "$BO_DATA/DRIFT/events.jsonl", "sha256": common.sha256_file(evp)},
                "atom_history": frame,
                "rename_candidates": {"path": "$BO_DATA/DRIFT/rename_candidates.jsonl",
                                      "sha256": common.sha256_file(out / "rename_candidates.jsonl")}},
            "totals": totals,
            "providers": clean,
        },
    }
