"""Põe o pacote retido (em memória) na árvore congelada temporária, no MESMO leiaute da calibração.

O código congelado do E2E só sabe ler pilot/<fatia>/fixtures_calib/ e pilot/<fatia>/expected_answers.json; o
avaliador não muda esse código. Então a cópia congelada em $BO_TMP recebe as retidas no lugar da calibração,
escritas exatamente como o oráculo escreve a calibração (bo.pilot_sto_oracle.build.write_calib e
bo.pilot_net_oracle.build.generate). O teste tests/pilot_exit/test_materialize.py prova a fidelidade: o pacote
montado com a calibração pública, materializado, reproduz byte a byte os arquivos da calibração no git.
A árvore é apagada no fim da execução (heldout_run).
"""
from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path


def _sto_canon(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _net_dump(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def sto(bundle: dict, root: Path) -> dict:
    from bo.pilot_sto_oracle.build import SCHEMA_ENTRY, c11_seed
    base = root / "pilot" / "sto"
    fc = base / "fixtures_calib"
    if fc.exists():
        shutil.rmtree(fc)
    fixtures, directions = {}, {}
    for f in bundle["fixtures"]:
        fx = f["fixture"]
        rel = f"fixtures_calib/{fx['provider']}/{fx['fixture_id']}.json"
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_bytes(_sto_canon(fx))
        fixtures[fx["fixture_id"]] = {"file": f"pilot/sto/{rel}", "provider": fx["provider"], "case": fx["case"],
                                      "polarity": fx["polarity"], "summary": fx["summary"],
                                      "invariant_group": fx.get("invariant_group"), "checks": f["checks"]}
    for e in bundle["entries"]:
        a, b = e["direction"].split("->")
        rel = f"fixtures_calib/directions/{a}-{b}/{e['entry_id']}.json"
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        doc = {"schema": SCHEMA_ENTRY, "entry_id": e["entry_id"], "direction": e["direction"], "family": e["family"],
               "variant": e["variant"], "note": e["note"], "source": e["source"], "target": e["target"],
               "container_map": e["container_map"], "declared_losses": e["declared_losses"]}
        (base / rel).write_bytes(_sto_canon(doc))
        directions[e["entry_id"]] = {"file": f"pilot/sto/{rel}", "direction": e["direction"], "family": e["family"],
                                     "variant": e["variant"], "polarity": e["polarity"], "declared_losses": e["declared_losses"],
                                     "expect": e["expect"], "note": e["note"], "c11_case_seed": c11_seed(e)}
    ea_p = base / "expected_answers.json"
    ea = json.loads(ea_p.read_text(encoding="utf-8"))
    ea["fixtures"], ea["directions"] = fixtures, directions
    ea_p.write_bytes(_sto_canon(ea))
    return {"fixtures": len(fixtures), "direction_entries": len(directions)}


def _net_oracle(root: Path):
    p = str(root / "pilot/net/oracle")
    for k in [k for k in sys.modules if k == "net_oracle" or k.startswith("net_oracle.")]:
        del sys.modules[k]
    sys.path.insert(0, p)
    try:
        return importlib.import_module("net_oracle"), importlib.import_module("net_oracle.decomposing")
    finally:
        sys.path.remove(p)


def net(bundle: dict, root: Path) -> dict:
    from bo.pilot_net_oracle.build import c11_seed
    from bo.pilot_net_oracle.coverage_lib import summarize
    no, dec = _net_oracle(root)
    base = root / "pilot" / "net"
    fc = base / "fixtures_calib"
    if fc.exists():
        shutil.rmtree(fc)
    (fc / "translations").mkdir(parents=True)
    fx, tr = bundle["fixtures"], bundle["translations"]
    by_id = {f["fixture_id"]: f for f in fx}
    exp_fx, exp_tr = {}, {}
    for f in fx:
        (fc / f"{f['fixture_id']}.json").write_text(_net_dump(f), encoding="utf-8")
        e = {k: f[k] for k in ("provider", "case", "polarity", "commitment_ids", "check")}
        e.update(f["expected"])
        e["decomposition"] = dec.apply_disputes(f["expected"]["decomposition"])
        exp_fx[f["fixture_id"]] = e
    for t in tr:
        src = by_id[t["source_fixture"]]
        tgt = dict(t["target"], fixture_id=t["case_id"] + "-TARGET", flows=src["flows"],
                   read={"completeness": "complete", "not_read": [], "withheld": []})
        j = no.judge(src, tgt, t["declared_losses"], t["direction"])
        (fc / "translations" / f"{t['case_id']}.json").write_text(_net_dump(dict(t, target=tgt)), encoding="utf-8")
        exp_tr[t["case_id"]] = {"direction": t["direction"], "polarity": t["polarity"],
                                "source_fixture": t["source_fixture"], "declared_losses": t["declared_losses"],
                                "expected": t["expected"], "per_flow": j["per_flow"], "c11_case_seed": c11_seed(t)}
    ea_p = base / "expected_answers.json"
    ea = json.loads(ea_p.read_text(encoding="utf-8"))
    ea["fixtures"], ea["translations"] = exp_fx, exp_tr
    for c, v in ea.get("mandatory_cases", {}).items():
        if c == "NET-C10":
            v["calib"] = {p: sorted(t["case_id"] for t in tr if t["polarity"] == p) for p in ("positive", "negative", "unknown")}
        else:
            v["calib"] = {p: sorted(f["fixture_id"] for f in fx if f["case"] == c and f["polarity"] == p)
                          for p in ("positive", "negative", "unknown")}
    ea["counts"] = dict(ea.get("counts", {}), calib=summarize(fx, tr))
    dirs = ea.get("directions", {})
    for d, v in dirs.items():
        if isinstance(v, dict) and "calib_cases" in v:
            v["calib_cases"] = sorted(t["case_id"] for t in tr if t["direction"] == d)
    ea_p.write_text(_net_dump(ea), encoding="utf-8")
    dj = base / "oracle" / "directions.json"
    if dj.is_file():
        dd = json.loads(dj.read_text(encoding="utf-8"))
        for d, v in dd.get("directions", {}).items():
            v["calib_cases"] = sorted(t["case_id"] for t in tr if t["direction"] == d)
        dj.write_text(_net_dump(dd), encoding="utf-8")
    return {"fixtures": len(fx), "translations": len(tr)}


def materialize(slice_: str, bundle: dict, root: Path) -> dict:
    return sto(bundle, root) if slice_ == "sto" else net(bundle, root)
