"""Gera as fixtures das CQs por provedor e os arquivos de resposta e de sonda.

  python -I -m bo.cqfix.build            grava cq/fixtures/{provider}/main.tf, expected_answers.json, probes.yaml
                                         e results/CQFIX/cq_spec_cis.jsonl, build_report.json
  python -I -m bo.cqfix.build --check    regenera em $BO_TMP e compara byte a byte (generated_at não conta)

A resposta esperada é copiada da especificação C24 (cq_spec.jsonl e cq_spec_cis.jsonl); o build nunca a
calcula. main.tf passa pelo terraform fmt fixado (offline, sandbox sem credenciais).
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import yaml

from . import MODULE_ID, PROVIDERS, VARIANT_LETTER, VARIANTS, fixtures_dir, now_iso, results_dir, tmp_root
from . import cis_spec, hcl, spec, tf
from .model import NA, Fx
from .realize.base import Ctx

SCHEMA_EXPECTED = "bo.cqfix.expected_answers/1"
SCHEMA_PROBES = "bo.cqfix.probes/1"
VOLATILE = ("generated_at",)


def provider_module(p: str):
    return importlib.import_module(f"bo.cqfix.realize.{p}")


def realize_all(providers=PROVIDERS) -> dict:
    out = {}
    for p in providers:
        mod = provider_module(p)
        out[p] = {}
        for q in spec.catalog():
            fn = mod.REALIZERS.get(q["cq_id"])
            if fn is None:
                raise SystemExit(f"{p}: sem realizador para {q['cq_id']}")
            out[p][q["cq_id"]] = {}
            for v in VARIANTS:
                c = Ctx(p, q, v)
                r = fn(v, c)
                if not isinstance(r, (Fx, NA)):
                    raise SystemExit(f"{p} {q['cq_id']} {v}: realizador devolveu {type(r).__name__}")
                out[p][q["cq_id"]][v] = (r, c.fid)
    return out


def render_main(p: str, res: dict) -> str:
    mod = provider_module(p)
    parts = [f"# Fixtures das CQs ({MODULE_ID}) no provider {p} — gerado por bo.cqfix.build; não editar.\n"
             "# Cada seção é uma fixture (FX-...) e só ela; o conjunto de endereços de cada uma está em\n"
             "# expected_answers.json. Valores reais (conta, região, projeto) nunca entram: vêm das variáveis\n"
             "# de contexto, ligadas pelo runner do DEP. Variáveis fx_* sem valor são entradas simbólicas de\n"
             "# fixtures incompletas, de propósito.\n\n", mod.header()]
    for q in spec.catalog():
        for v in VARIANTS:
            r, fid = res[q["cq_id"]][v]
            if isinstance(r, NA):
                parts.append(f"\n# ==== {fid} ({q['cq_id']}, {v}): NOT_APPLICABLE — {r.reason}\n")
                continue
            parts.append(f"\n# ==== {fid} ({q['cq_id']}, {v})\n")
            for vd in r.variables:
                parts.append("\n" + hcl.variable(vd))
            for x in r.resources:
                parts.append("\n" + hcl.resource(x))
    return tf.fmt_text("".join(parts))


def _c11_seed(p: str, q: dict, v: str, fid: str, r: Fx) -> dict:
    return {
        "case_id": f"CASE-CQ-{p.upper()}-{fid[3:]}",
        "group_id": f"G-CQ-{q['cq_id'][3:]}-{p.upper()}",
        "origin": "cq", "cq_id": q["cq_id"], "side": "subject",
        "comparator": {"name": "exact"}, "cost_class": r.cost_class,
        "pending": {
            "claim_id": "a CQ de provedor único ainda não tem alegação de correspondência (MAP/RECONCILE)",
            "claim_version_id": "idem",
            "stratum": "par e domínio saem da alegação",
            "frame_ref": "frame do DEPSAMPLE",
            "weight": "peso do frame do DEPSAMPLE",
            "lowering_plan": "plano C26 do GRAPH-LOWERING; a fixture é o HCL deste main.tf",
            "values": "termos do plano C26",
        },
    }


def expected_answers(res: dict) -> dict:
    cqs = []
    cis_ctl = cis_spec.cis_controls()
    concept_of = {v: k for k, v in cis_spec.CONCEPT_CQ.items()}
    for q in spec.catalog():
        entry = {"cq_id": q["cq_id"], "family": q["family"], "answer_form": q["answer_form"],
                 "question": q["question"], "source": spec.source_of(q), "providers": {}}
        if q["family"] == "cis":
            con = concept_of[q["cq_id"]]
            entry["cis_concept"] = con
            entry["cis_controls"] = {pp: [{"control_id": a, "cis_item_id": b, "title": t, "cis_version": ver}
                                          for a, b, t, ver in cis_ctl[con]["providers"].get(pp, [])]
                                     for pp in PROVIDERS}
        for p in PROVIDERS:
            if p not in res:
                continue
            vs = {}
            for v in VARIANTS:
                r, fid = res[p][q["cq_id"]][v]
                exp = spec.expected(q, v)
                f = spec.fixture(q, v)
                base = {"fixture_id": fid, "expected": exp, "read": f["read"]}
                if isinstance(r, NA):
                    vs[v] = {**base, "status": "NOT_APPLICABLE", "reason": r.reason, "evidence": r.evidence}
                    continue
                vs[v] = {**base, "status": "REALIZED",
                         "addresses": [x.address for x in r.resources],
                         "entity_map": r.entity_map,
                         "synthesized": r.synthesized,
                         "symbolic_inputs": [vd.name for vd in r.variables],
                         "incompleteness": r.incompleteness,
                         "deviations": r.deviations,
                         "evidence_level": r.evidence_level,
                         "evidence": r.evidence,
                         "probe_id": f"PRB-{p.upper()}-{fid[3:]}",
                         "c11_case_seed": _c11_seed(p, q, v, fid, r)}
            realized = [v for v in VARIANTS if vs[v]["status"] == "REALIZED"]
            entry["providers"][p] = {
                "applicability": ("APPLICABLE" if len(realized) == 3 else
                                  "NOT_APPLICABLE" if not realized else "PARTIAL"),
                "variants": vs}
        cqs.append(entry)
    return {"schema": SCHEMA_EXPECTED, "contract": "C24", "contract_version": "1.0.0", "module": MODULE_ID,
            "generated_at": now_iso(),
            "note": ("resposta esperada copiada da especificação C24 (cq_spec.jsonl e results/CQFIX/"
                     "cq_spec_cis.jsonl); nunca calculada por mapeador. status por variante: REALIZED ou "
                     "NOT_APPLICABLE (com evidência conferível pelo fixture_check)."),
            "providers": {p: provider_module(p).VERSION for p in PROVIDERS if p in res},
            "cqs": cqs}


def probes(res: dict) -> dict:
    out = []
    for q in spec.catalog():
        for p in PROVIDERS:
            if p not in res:
                continue
            for v in VARIANTS:
                r, fid = res[p][q["cq_id"]][v]
                if isinstance(r, NA):
                    continue
                f = spec.fixture(q, v)
                pr = dict(r.probe) if r.probe else {"kind": "static", "inputs": {}}
                out.append({
                    "probe_id": f"PRB-{p.upper()}-{fid[3:]}",
                    "fixture_id": fid, "cq_id": q["cq_id"], "variant": v, "provider": p,
                    "kind": pr.get("kind", "static"),
                    "inputs": pr.get("inputs", {}),
                    "slice": [x.address for x in r.resources],
                    "read": {"completeness": f["read"]["completeness"],
                             "masked": [i for i in r.incompleteness if i["mechanism"] == "READ_MASK"],
                             "symbolic": [i for i in r.incompleteness if i["mechanism"] == "SYMBOLIC_INPUT"],
                             "external": [i for i in r.incompleteness if i["mechanism"] == "EXTERNAL_REFERENCE"],
                             "evidence_gaps": [i for i in r.incompleteness if i["mechanism"] == "EVIDENCE_GAP"],
                             "withheld": f["read"]["withheld"]},
                    "deployable": r.deployable,
                    "deploy_note": r.deploy_note,
                    "cost_class": r.cost_class,
                    "answer_from": "expected_answers.json (especificação), nunca do mapeador",
                })
    return {"schema": SCHEMA_PROBES, "module": MODULE_ID, "generated_at": now_iso(),
            "context_vars": {p: provider_module(p).CONTEXT_VARS for p in PROVIDERS if p in res},
            "kinds": {"static": "a resposta sai da configuração e da leitura declarada, sem nuvem",
                      "readback": "precisa da leitura de volta (observação datada) depois do apply",
                      "two_phase": "aplica o estado anterior (inputs.change.before) e depois o main.tf; lê a ação do plano",
                      "translation": "a configuração de origem está no main.tf; o destino é o da especificação (inputs.target)"},
            "probes": out}


def report(res: dict) -> dict:
    rep = {"schema": "bo.cqfix.build_report/1", "module": MODULE_ID, "generated_at": now_iso(),
           "cq_count": len(spec.catalog()), "cis_cq_count": len(cis_spec.CONCEPT_CQ),
           "cis_concepts_plan_estimate": cis_spec.PLAN_ESTIMATE,
           "cis_note": ("o CQSRC achou 8 conceitos CIS com controle nos 4 benchmarks (o plano estimava ~10); "
                        "o CQFIX trabalha com os 8"),
           "providers": {}}
    for p, byq in res.items():
        n = {"REALIZED": 0, "NOT_APPLICABLE": 0}
        app = {"APPLICABLE": 0, "PARTIAL": 0, "NOT_APPLICABLE": 0}
        levels = {"STRUCTURAL": 0, "INTERPRETED": 0}
        nres = 0
        for qid, vs in byq.items():
            k = sum(isinstance(vs[v][0], Fx) for v in VARIANTS)
            app["APPLICABLE" if k == 3 else "NOT_APPLICABLE" if k == 0 else "PARTIAL"] += 1
            for v in VARIANTS:
                r = vs[v][0]
                if isinstance(r, Fx):
                    n["REALIZED"] += 1
                    levels[r.evidence_level] += 1
                    nres += len(r.resources)
                else:
                    n["NOT_APPLICABLE"] += 1
        rep["providers"][p] = {"variants": n, "cqs": app, "evidence_level": levels, "resources": nres}
    return rep


def _dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def outputs(providers=PROVIDERS) -> dict[Path, str]:
    res = realize_all(providers)
    fx = fixtures_dir()
    out = {}
    for p in providers:
        out[fx / p / "main.tf"] = render_main(p, res[p])
    out[fx / "expected_answers.json"] = _dump_json(expected_answers(res))
    out[fx / "probes.yaml"] = yaml.safe_dump(probes(res), allow_unicode=True, sort_keys=False, width=110)
    out[results_dir() / "cq_spec_cis.jsonl"] = "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in cis_spec.records())
    out[results_dir() / "build_report.json"] = _dump_json(report(res))
    return out


def _strip(path: Path, text: str) -> str:
    if path.suffix == ".json":
        d = json.loads(text)
        for k in VOLATILE:
            d.pop(k, None)
        return json.dumps(d, sort_keys=True)
    if path.suffix == ".yaml":
        d = yaml.safe_load(text)
        for k in VOLATILE:
            d.pop(k, None)
        return json.dumps(d, sort_keys=True)
    return text


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    providers = PROVIDERS
    if "--only" in argv:
        providers = tuple(argv[argv.index("--only") + 1].split(","))
    outs = outputs(providers)
    if "--check" in argv:
        bad = []
        for p, text in outs.items():
            if not p.is_file() or _strip(p, p.read_text(encoding="utf-8")) != _strip(p, text):
                bad.append(str(p))
        if bad:
            print("build --check: difere da regeneração:", *bad, sep="\n  ", file=sys.stderr)
            return 1
        print(f"build --check: {len(outs)} arquivo(s) idênticos à regeneração")
        return 0
    for p, text in outs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"gravado {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
