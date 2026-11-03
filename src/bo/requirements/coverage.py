"""Gate de cobertura: python -I -m bo.requirements.coverage [--dir PASTA]

Reprova se:
  - algum dos 3 arquivos não valida (schema proposto + regras semânticas, inclusive referências cruzadas);
  - algum dos 6 casos adversariais obrigatórios não tem ao menos um compromisso positivo, um negativo e um
    desconhecido, ou não está aterrado nos 4 provedores, ou não é exercitado por nenhuma CQ;
  - alguma CQ não tem resposta esperada e fixture conforme, não conforme e incompleta (incompleta = UNKNOWN);
  - algum requisito não é verificado por compromisso nem por CQ;
  - algum eixo da ontologia de topo (identidade, tempo, papel) tem menos de 2 compromissos;
  - algum fixture_id se repete entre compromissos e CQs (o CQFIX e os oráculos endereçam fixture por id);
  - alguma objeção que o módulo responde (R1-M3, R1-M8, F1, F9, S2, S4, S13) não é respondida por nenhum registro.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import common, model, validate

MODULE_ANSWERS = ("R1-M8", "R1-M3", "F1", "F9", "S2", "S4", "S13")


def check(d: Path) -> tuple[list[str], dict]:
    errs = []
    for kind, fname in common.KIND_FILE.items():
        errs += validate.validate_file(kind, d / fname)
    reqs, cmts, cqs = common.load_published(d)
    stats: dict = {"requirements": len(reqs), "commitments": len(cmts), "cqs": len(cqs)}

    by_case = defaultdict(Counter)
    grounded = defaultdict(set)
    for c in cmts:
        by_case[c.get("case")][c.get("polarity")] += 1
        for g in c.get("provider_grounding") or []:
            grounded[c.get("case")].add(g.get("provider"))
    cq_cases = Counter(cs for q in cqs for cs in q.get("cases") or [])
    stats["cases"] = {}
    for case in model.ADVERSARIAL_CASES:
        cnt = by_case.get(case, Counter())
        stats["cases"][case] = {p: cnt.get(p, 0) for p in model.POLARITIES} | {
            "providers": sorted(grounded.get(case, set())), "cqs": cq_cases.get(case, 0)}
        for p in model.POLARITIES:
            if cnt.get(p, 0) < 1:
                errs.append(f"caso {case}: nenhum compromisso {p}")
        falta = set(model.PROVIDERS) - grounded.get(case, set())
        if falta:
            errs.append(f"caso {case}: sem aterramento em {', '.join(sorted(falta))}")
        if cq_cases.get(case, 0) < 1:
            errs.append(f"caso {case}: nenhuma CQ o exercita")

    for q in cqs:
        fx = q.get("fixtures") or {}
        for role in ("conforming", "nonconforming", "incomplete"):
            side = fx.get(role) or {}
            if not side.get("fixture") or "value" not in (side.get("expected") or {}):
                errs.append(f"{q.get('cq_id')}: falta fixture {role} com resposta esperada")
        if ((fx.get("incomplete") or {}).get("expected") or {}).get("value") != "UNKNOWN":
            errs.append(f"{q.get('cq_id')}: fixture incompleta não espera UNKNOWN")

    used = {r for c in cmts for r in c.get("requirement_ids") or []} | \
           {r for q in cqs for r in q.get("requirement_ids") or []}
    orphan = sorted({r["req_id"] for r in reqs} - used)
    for r in orphan:
        errs.append(f"requisito {r} sem compromisso nem CQ")

    axes = Counter(a for c in cmts for a in c.get("upper_axes") or [])
    stats["upper_axes"] = {a: axes.get(a, 0) for a in model.UPPER_AXES}
    for a in model.UPPER_AXES:
        if axes.get(a, 0) < 2:
            errs.append(f"eixo de ontologia de topo '{a}' com menos de 2 compromissos")

    answered = {a for rec in reqs + cmts + cqs for a in rec.get("answers") or []}
    for a in MODULE_ANSWERS:
        if a not in answered:
            errs.append(f"objeção {a} não respondida por nenhum registro")
    fx_ids = Counter([f.get("fixture_id") for c in cmts for f in c.get("fixtures") or []] +
                     [((q.get("fixtures") or {}).get(r) or {}).get("fixture", {}).get("fixture_id")
                      for q in cqs for r in ("conforming", "nonconforming", "incomplete")])
    for fid, k in fx_ids.items():
        if k > 1:
            errs.append(f"fixture_id repetido entre compromissos e CQs: {fid}")
    stats["polarity"] = dict(Counter(c.get("polarity") for c in cmts))
    stats["fixtures"] = sum(len(c.get("fixtures") or []) for c in cmts) + 3 * len(cqs)
    return errs, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.requirements.coverage")
    ap.add_argument("--dir", default=None)
    a = ap.parse_args(argv)
    d = Path(a.dir) if a.dir else common.out_dir()
    errs, st = check(d)
    print(f"cobertura C24 em {d}: {st['requirements']} requisitos, {st['commitments']} compromissos "
          f"({st.get('polarity')}), {st['cqs']} CQs, {st['fixtures']} fixtures")
    for case, v in st["cases"].items():
        print(f"  {case:9s} P={v['positive']} N={v['negative']} U={v['unknown']} "
              f"provedores={','.join(v['providers']) or '-'} CQs={v['cqs']}")
    print(f"  eixos de topo: {st['upper_axes']}")
    if errs:
        return common.fail(errs, "coverage")
    print("coverage: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
