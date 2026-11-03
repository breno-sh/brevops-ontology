"""Gera as saídas do METRICSLIB a partir dos stubs dos contratos (nenhum dado do estudo).

  python -I -m bo.metrics.build            grava results/METRICSLIB/{stub_readings.json, binding.json,
                                           MANIFEST.sha256} e prereg/metrics_lib.sha256
  python -I -m bo.metrics.build --check    regenera em memória e reprova se algo diverge (regeneração idêntica)
  python -I -m bo.metrics.build --out DIR  grava os mesmos arquivos em DIR (usado por bo.metrics.recompute)

stub_readings.json (C15 3.0.0, result): a escada calculada sobre os stubs C23 (traços), C11/C12 (casos e
desfechos de persistência), C22 (julgamento de sonda) e C06 (configuração simbólica com documento de
política), só para provar que o caminho inteiro gera um documento válido. binding.json: métrica -> eixo,
leitura, quantificador, cálculo e códigos no intervalo; contraste -> métricas e regra; estimandos.
metrics_lib.sha256: sha256 do código, dos testes, do gate e do metrics_spec.yaml (entrada fixada), no formato
do shasum, caminhos relativos à raiz do repositório.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


from . import LIB_VERSION
from . import contrasts as CT
from . import core, units as U
from .c15 import entries_for, result_document
from .spec import BINDINGS, SPEC_SHA256, check_spec, load_spec, repo_root, spec_by_id

MODULE = "METRICSLIB"
CONTENT_TIME = "2026-11-03T07:30:00-03:00"  # hora do conteúdo (America/Recife); fixa para regeneração idêntica
LIB_FILES_GLOBS = ("src/bo/metrics/*.py", "tests/metrics/*.py")
LIB_FIXED = ("gates/METRICSLIB.sh", "prereg/metrics_spec.yaml")


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def dumps(doc) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def stub_readings(root: Path) -> dict:
    st = root / "contracts" / "stubs"
    spec = spec_by_id(load_spec(root / "prereg" / "metrics_spec.yaml"))
    families = _jsonl(st / "C27" / "families.jsonl")
    fam_of_repo = {r: f["family_id"] for f in families for r in f["members"]}

    # configuração (C06) e papéis (C04): denominadores por campo e por decisão
    roles = {r["atom_id"]: r["role"] for r in _jsonl(st / "C04" / "roles.jsonl")}
    sym = _jsonl(st / "C06" / "symbolic_config.jsonl")
    fields = U.fields_from_symbolic(sym, roles.get)
    n_fields = len(U.field_units(fields))
    decisions = U.decision_units(U.field_units(fields))

    # traços C23 (controle c3): cada traço é uma decisão do stub; família pelo C06 usage
    usage = _jsonl(st / "C06" / "usage.jsonl")
    fam_of_atom = {u["atom_id"]: (u["family_id"], u["repo_id"]) for u in usage}
    traces = _jsonl(st / "C23" / "translation_trace.jsonl")
    op_units = []
    for t in traces:
        if t["control"] != "c3":
            continue
        fam, repo = fam_of_atom.get(t["input"]["atom_id"], ("F-unknown", "R-unknown"))
        op_units.append(U.Unit(t["trace_id"], fam, repo, "aws", "google", codes=tuple(U.trace_codes([t])),
                               attrs=U.mk_attrs(complex=bool(t.get("guard_evaluated")))))
    opcov = core.reading("M-OPCOV-DEC", op_units)

    # persistência (C11 + C12) e comportamento (C22)
    cases = _jsonl(st / "C11" / "cases.jsonl")
    outcomes = _jsonl(st / "C12" / "outcomes.jsonl")
    pers_units = U.case_units(cases, outcomes)
    pers = core.reading("M-PERS-DEC", pers_units)
    comb = core.combined_reading(op_units, pers_units)
    judg = _jsonl(st / "C22" / "pair_judgements.jsonl")
    beh_units = U.probe_units(judg, cases)
    beh = core.reading("M-BEHAV-DEC", beh_units)

    entries, undef = [], []
    for mid, cells, corr in (("M-OPCOV-DEC", opcov, None), ("M-PERS-DEC", pers, None),
                             ("M-OPCOV-PERS-DEC", comb, ["M-OPCOV-DEC", "M-PERS-DEC"]),
                             ("M-BEHAV-DEC", beh, None)):
        ok, un = entries_for(mid, cells, spec[mid], correlated=corr)
        entries += ok
        undef += un
    notes = ("Leituras sobre os stubs dos contratos (C06, C11, C12, C22, C23, C27), sem dado do estudo: só "
             "provam que o caminho gera C15 válido. Células com n > 0 e nenhum desfecho conhecido não têm est e "
             "ficam em data.est_undefined (lacuna do C15, ver results/METRICSLIB/CONTRACT_CHANGE.txt).")
    data = {"library_version": LIB_VERSION, "spec_sha256": SPEC_SHA256,
            "denominators": {"fields_INC_FIELD_01": n_fields, "decisions_INC_DEC_01": len(decisions)},
            "ladder": core.ladder({"M-OPCOV-DEC": opcov, "M-PERS-DEC": pers, "M-BEHAV-DEC": beh})}
    return result_document(MODULE, CONTENT_TIME, entries, undef, notes, data)


def binding_doc() -> dict:
    ms = {}
    for mid, b in sorted(BINDINGS.items()):
        ms[mid] = {"name": b.name, "axis": b.axis, "reading": b.reading, "quantifier": b.quantifier,
                   "weights": b.weights, "uncertainty": b.uncertainty, "kind": b.kind,
                   "directional": b.directional, "only_oci": b.only_oci, "bounded_codes": sorted(b.unknown),
                   "outcome_table": dict(sorted(b.table.items()))}
    cs = {cid: {"metrics": m, "judge": f"bo.metrics.contrasts.{fn.__name__}"}
          for cid, (m, fn) in sorted(CT.REGISTRY.items())}
    return {"schema": "bo.metrics_binding/1", "module": MODULE, "generated_at": CONTENT_TIME,
            "library_version": LIB_VERSION, "spec_sha256": SPEC_SHA256, "metrics": ms, "contrasts": cs,
            "estimands": dict(sorted(CT.ESTIMANDS.items()))}


def lib_manifest(root: Path) -> str:
    files = sorted({str(p.relative_to(root)) for g in LIB_FILES_GLOBS for p in root.glob(g)} | set(LIB_FIXED))
    lines = []
    for f in files:
        lines.append(f"{hashlib.sha256((root / f).read_bytes()).hexdigest()}  {f}")
    return "\n".join(lines) + "\n"


def outputs(root: Path) -> dict[str, str]:
    errs = check_spec(load_spec(root / "prereg" / "metrics_spec.yaml")) + CT.check_power(root / "prereg" /
                                                                                          "power.json")
    if errs:
        raise SystemExit("spec/power x biblioteca:\n  " + "\n  ".join(errs))
    out = {"results/METRICSLIB/stub_readings.json": dumps(stub_readings(root)),
           "results/METRICSLIB/binding.json": dumps(binding_doc()),
           "prereg/metrics_lib.sha256": lib_manifest(root)}
    man = "".join(f"{hashlib.sha256(v.encode()).hexdigest()}  {k}\n" for k, v in sorted(out.items()))
    out["results/METRICSLIB/MANIFEST.sha256"] = man
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.metrics.build")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    root = repo_root()
    outs = outputs(root)
    if a.check:
        bad = [k for k, v in outs.items() if not (root / k).is_file() or (root / k).read_text(encoding="utf-8") != v]
        if bad:
            print("regeneração diverge: " + ", ".join(bad))
            return 1
        print(f"regeneração idêntica: {len(outs)} arquivo(s)")
        return 0
    base = Path(a.out) if a.out else root
    for k, v in outs.items():
        p = base / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v, encoding="utf-8")
    print(f"gravado(s) {len(outs)} arquivo(s) em {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
