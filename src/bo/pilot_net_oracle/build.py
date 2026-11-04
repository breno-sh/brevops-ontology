"""Gera os artefatos públicos do oráculo NET a partir das fontes escritas à mão e confere tudo contra o avaliador.

  python -I -m bo.pilot_net_oracle.build          grava fixtures_calib/, directions.json, documented_examples.json,
                                                  expected_answers.json, ORACLE.sha256 e results/PILOT-NET-ORACLE/build_report.json
  python -I -m bo.pilot_net_oracle.build --check  regenera em memória e compara (sem gravar); sai 1 se diferir

Para o build: resposta escrita à mão ≠ avaliador (é erro de um dos dois; nada se ajusta para casar).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import calib, examples, spec
from .coverage_lib import check as cov_check, summarize
from .seal import now, repo, sealed_dir

PAIR_CODE = {"aws": "AWS", "google": "GCP", "azurerm": "AZ", "oci": "OCI"}
ORDER = ["aws", "google", "azurerm", "oci"]


def _oracle():
    sys.path.insert(0, str(repo() / "pilot/net/oracle"))
    import net_oracle  # noqa: E402
    return net_oracle


def _dump(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def c11_seed(t: dict) -> dict:
    a, b = t["direction"].split("->")
    first, second = sorted((a, b), key=ORDER.index)
    return {"case_id": "CASE-" + t["case_id"], "group_id": f"G-NET-{PAIR_CODE[a]}-{PAIR_CODE[b]}",
            "stratum_partial": {"pair": PAIR_CODE[first] + PAIR_CODE[second], "domain": "NET", "cardinality": "1:1",
                                "direction": "forward" if a == first else "inverse"},
            "side": "both", "comparator": {"name": "exact"}, "cost_class": "free",
            "pending": {"claim_id": "o oráculo não lê alegação de correspondência (independência do mapeamento)",
                        "claim_version_id": "idem", "stratum.relation": "sai da alegação",
                        "origin": "o C11 não tem origem para caso de piloto (ver CONTRACT_CHANGE.txt)",
                        "frame_ref": "frame do DEPSAMPLE", "weight": "peso do frame do DEPSAMPLE",
                        "lowering_plan": "plano C26 do PILOT-NET-E2E", "values": "termos do plano C26"}}


def generate(check_only: bool = False) -> dict:
    no = _oracle()
    R = repo()
    errors, files = [], {}
    fx = calib.fixtures()
    tr = calib.translations()
    by_id = {f["fixture_id"]: f for f in fx}
    if len(by_id) != len(fx):
        errors.append("fixture_id repetido")
    # directions.json primeiro (o juiz lê o catálogo)
    directions = {"schema": "bo.pilot_net.directions/1", "module": "PILOT-NET-ORACLE",
                  "loss_catalog": spec.LOSS_CATALOG, "target_requirements": spec.TARGET_REQUIREMENTS,
                  "directions": {}}
    for d in spec.DIRECTIONS:
        e = spec.direction_entry(d)
        e["calib_cases"] = sorted(t["case_id"] for t in tr if t["direction"] == d)
        directions["directions"][d] = e
    files["pilot/net/oracle/directions.json"] = _dump(directions)
    dpath = R / "pilot/net/oracle/directions.json"
    if not check_only:
        dpath.write_text(files["pilot/net/oracle/directions.json"], encoding="utf-8")
    sens = {"strict": 0, "lenient": 0, "flows": 0, "flips": []}
    exp_fx = {}
    for f in fx:
        r = no.evaluate_fixture(f)
        for fid, e in f["expected"]["decisions"].items():
            g = r["decisions"].get(fid)
            if g is None or g["value"] != e["value"] or (e["value"] == "UNKNOWN" and g["code"] != e.get("code")):
                errors.append(f"{f['fixture_id']}/{fid}: escrito {e['value']}/{e.get('code')} x avaliador {g}")
        if r["validity"]["value"] != f["expected"]["validity"]["value"]:
            errors.append(f"{f['fixture_id']}: validade escrita {f['expected']['validity']} x {r['validity']['value']}")
        for rd in ("strict", "lenient"):
            rr = no.evaluate_fixture(f, rd)["decisions"]
            for fid in f["expected"]["decisions"]:
                if rr[fid]["value"] != r["decisions"][fid]["value"]:
                    sens[rd] += 1
                    sens["flips"].append({"reading": rd, "fixture": f["fixture_id"], "flow": fid,
                                          "default": r["decisions"][fid]["value"], "other": rr[fid]["value"]})
        sens["flows"] += len(f["expected"]["decisions"])
        inv = f["expected"].get("decomposition_invariant_with")
        if inv:
            from net_oracle.decomposing import invariant
            if not invariant(f["expected"]["decomposition"], by_id[inv]["expected"]["decomposition"]):
                errors.append(f"{f['fixture_id']}: decomposição não invariante com {inv}")
            if {k: v["value"] for k, v in f["expected"]["decisions"].items()} != \
                    {k: v["value"] for k, v in by_id[inv]["expected"]["decisions"].items()}:
                errors.append(f"{f['fixture_id']}: decisões diferentes de {inv}")
        files[f"pilot/net/fixtures_calib/{f['fixture_id']}.json"] = _dump(f)
        exp_fx[f["fixture_id"]] = {k: f[k] for k in ("provider", "case", "polarity", "commitment_ids", "check")}
        exp_fx[f["fixture_id"]].update(f["expected"])
    exp_tr = {}
    for t in tr:
        src = by_id[t["source_fixture"]]
        tgt = dict(t["target"], fixture_id=t["case_id"] + "-TARGET", flows=src["flows"],
                   read={"completeness": "complete", "not_read": [], "withheld": []})
        j = no.judge(src, tgt, t["declared_losses"], t["direction"])
        ok = j["verdict"] == t["expected"]["verdict"]
        for k in ("negatives_carried", "silent_losses", "covered", "undetermined"):
            if k in t["expected"] and sorted(t["expected"][k]) != sorted(j[k]):
                ok = False
        if not ok:
            errors.append(f"{t['case_id']}: escrito {t['expected']} x juiz {j['verdict']}")
        t2 = dict(t, target=tgt)
        files[f"pilot/net/fixtures_calib/translations/{t['case_id']}.json"] = _dump(t2)
        exp_tr[t["case_id"]] = {"direction": t["direction"], "polarity": t["polarity"], "source_fixture": t["source_fixture"],
                                "declared_losses": t["declared_losses"], "expected": t["expected"],
                                "per_flow": j["per_flow"], "c11_case_seed": c11_seed(t)}
    ex = examples.examples()
    for e in ex:
        r = no.evaluate_fixture(e["fixture"])
        for fid, x in e["expected"]["decisions"].items():
            if r["decisions"][fid]["value"] != x["value"]:
                errors.append(f"{e['example_id']}/{fid}: exemplo documentado {x['value']} x {r['decisions'][fid]['value']}")
        if r["validity"]["value"] != e["expected"]["validity"]["value"]:
            errors.append(f"{e['example_id']}: validade {e['expected']['validity']['value']} x {r['validity']['value']}")
    files["pilot/net/oracle/documented_examples.json"] = _dump({"schema": "bo.pilot_net.documented_examples/1", "examples": ex})
    # índice selado (público): cópia do que a selagem gravou em $BO_DATA
    sidx = sealed_dir() / "sealed_index.json"
    retained = None
    if sidx.is_file():
        files["pilot/net/oracle/sealed_index.json"] = sidx.read_text(encoding="utf-8")
        retained = json.loads(files["pilot/net/oracle/sealed_index.json"])["counts"]
    else:
        errors.append(f"índice selado ausente: {sidx} (rode bo.pilot_net_oracle.seal seal)")
    cal = summarize(fx, tr)
    if retained:
        errors.extend("cobertura: " + e for e in cov_check(cal, retained))
    inputs = {p: _sha(R / p) for p in ("requirements/commitments.jsonl", "semantics/SEMANTICS.html")}
    se = Path(__import__("os").environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "SERVICE-EVIDENCE/service_evidence.jsonl"
    inputs["$BO_DATA/SERVICE-EVIDENCE/service_evidence.jsonl"] = _sha(se)
    expected = {
        "schema": "bo.pilot_net.expected_answers/1", "contract": "C24", "contract_version": "1.0.0",
        "module": "PILOT-NET-ORACLE", "slice": "net",
        "note": "gabarito escrito à mão a partir de compromissos e requisitos (C24) e da evidência do SERVICE-EVIDENCE; nunca de mapeador. Leitura de evidência: default (published, derived, oracle_derived). Retidas: só contagens aqui; conteúdo cifrado em $BO_DATA/PILOT-NET-ORACLE/sealed/.",
        "oracle": {"path": "$BO_REPO/pilot/net/oracle/net_oracle", "version": no.ORACLE_VERSION, "reading": "default",
                   "api": "net_oracle.evaluate_fixture(fx) / net_oracle.judge(src, tgt, losses, direction) / net_oracle.compare_decomposition(exp, act)"},
        "inputs_sha256": inputs,
        "mandatory_cases": {c: dict(v, calib={p: sorted(f["fixture_id"] for f in fx if f["case"] == c and f["polarity"] == p)
                                               for p in ("positive", "negative", "unknown")} if c != "NET-C10" else
                                    {p: sorted(t["case_id"] for t in tr if t["polarity"] == p) for p in ("positive", "negative", "unknown")},
                                    retained=(retained["by_case"].get(c) if retained and c != "NET-C10" else
                                              ({p: sum(v[p] for v in retained["by_direction"].values()) for p in ("positive", "negative", "unknown")} if retained else None)))
                            for c, v in spec.CASES.items()},
        "fixtures": exp_fx, "translations": exp_tr,
        "directions": directions["directions"],
        "counts": {"calib": cal, "retained": retained},
        "retained_index": "$BO_REPO/pilot/net/oracle/sealed_index.json",
    }
    files["pilot/net/expected_answers.json"] = _dump(expected)
    report = {"schema": "bo.pilot_net.build_report/1", "module": "PILOT-NET-ORACLE", "errors": errors,
              "counts": {"calib": cal, "retained": retained}, "documented_examples": len(ex),
              "sensitivity": {"flows": sens["flows"], "flips_strict": sens["strict"], "flips_lenient": sens["lenient"],
                              "flips": sens["flips"]}}
    files["results/PILOT-NET-ORACLE/build_report.json"] = _dump(report)
    # ORACLE.sha256 sobre tudo que é público e congelado (caminhos relativos à raiz do repositório)
    oracle_files = sorted(set(list(files) + [str(p.relative_to(R)) for p in (R / "pilot/net/oracle").rglob("*")
                                             if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts]))
    oracle_files = [p for p in oracle_files if p.startswith("pilot/net/") and p != "pilot/net/ORACLE.sha256"]
    lines = []
    for p in oracle_files:
        data = files[p].encode("utf-8") if p in files else (R / p).read_bytes()
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {p}")
    files["pilot/net/ORACLE.sha256"] = "\n".join(lines) + "\n"
    return {"files": files, "errors": errors, "report": report}


def write_manifest() -> Path:
    """results/PILOT-NET-ORACLE/MANIFEST.sha256 (C17), caminhos relativos à raiz; rodar depois do provenance record."""
    R = repo()
    paths = sorted(str(p.relative_to(R)) for p in (R / "results/PILOT-NET-ORACLE").iterdir()
                   if p.is_file() and p.name != "MANIFEST.sha256")
    paths += ["pilot/net/ORACLE.sha256", "pilot/net/expected_answers.json", "pilot/net/oracle/sealed_index.json"]
    out = R / "results/PILOT-NET-ORACLE/MANIFEST.sha256"
    out.write_text("".join(f"{_sha(R / p)}  {p}\n" for p in paths), encoding="utf-8")
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--manifest" in argv:
        print(f"[{now()}] manifesto: {write_manifest()}")
        return 0
    check = "--check" in argv
    g = generate(check_only=check)
    R = repo()
    if g["errors"]:
        for e in g["errors"][:50]:
            print("ERRO", e)
        print(f"[{now()}] build: {len(g['errors'])} erro(s)")
        return 1
    if check:
        diff = []
        for p, content in g["files"].items():
            q = R / p
            if not q.is_file() or q.read_text(encoding="utf-8") != content:
                diff.append(p)
        stale = [str(p.relative_to(R)) for p in (R / "pilot/net/fixtures_calib").rglob("*.json")
                 if str(p.relative_to(R)) not in g["files"]]
        for p in diff + stale:
            print("DIFERE", p)
        print(f"[{now()}] build --check: {len(g['files'])} arquivo(s), {len(diff) + len(stale)} diferença(s)")
        return 1 if (diff or stale) else 0
    for old in (R / "pilot/net/fixtures_calib").rglob("*.json"):
        if str(old.relative_to(R)) not in g["files"]:
            old.unlink()
    for p, content in g["files"].items():
        q = R / p
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(content, encoding="utf-8")
    c = g["report"]["counts"]
    print(f"[{now()}] build: {c['calib']['fixtures_total']} fixtures e {c['calib']['translations_total']} traduções de calibração; "
          f"retidas {c['retained']['fixtures_total'] if c['retained'] else 0}/{c['retained']['translations_total'] if c['retained'] else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
