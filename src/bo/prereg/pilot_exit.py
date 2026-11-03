"""Validador de prereg/pilot_exit.yaml (bo.pilot_exit/1; arquivo sem contrato C, consumido pelo PILOT-EXIT).

  python -I -m bo.prereg.pilot_exit [ARQ]

Confere: E1–E8 presentes e únicos, cada um com exigência, medidas, regra de aprovação, evidência portátil e ação
de falha; nenhum critério com limiar sobre cobertura (§9.5); limite de 2 tentativas; as duas fatias e as 12
direções; a regra dos 3 controles com os controles do index_set, as invariantes e uma consequência para cada
desfecho (inclusive nulo e inconclusivo); o adendo com caminho e escritor.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from . import common

IDS = [f"E{i}" for i in range(1, 9)]
PORTABLE = re.compile(r"^\$BO_(REPO|DATA)(/[^/\s]+)*/?$")
COVERAGE_WORDS = re.compile(r"(?i)\b(coverage|cobertura|opcov)\b")
REQUIRED_OUTCOMES = {"R-CTRL-1", "R-CTRL-2", "R-CTRL-3", "R-CTRL-4", "R-CTRL-5", "R-CTRL-6"}


def check(doc: dict) -> list[str]:
    errs = []
    if doc.get("schema") != "bo.pilot_exit/1" or doc.get("module") != "PREREG":
        errs.append("cabeçalho: schema bo.pilot_exit/1 e module PREREG")
    if doc.get("slices") != ["sto", "net"] or doc.get("directions") != 12:
        errs.append("fatias sto e net e 12 direções")
    if doc.get("attempts_max") != 2:
        errs.append("attempts_max tem de ser 2 (E8)")
    if not str(doc.get("coverage_threshold", "")).startswith("nenhum"):
        errs.append("coverage_threshold tem de declarar que não há limiar sobre cobertura")
    crit = doc.get("criteria") or []
    ids = [c.get("id") for c in crit]
    if ids != IDS:
        errs.append(f"critérios {ids} != {IDS}")
    for c in crit:
        cid = c.get("id")
        for k in ("name", "requirement", "pass_rule", "on_fail"):
            if len(str(c.get(k) or "")) < 3:
                errs.append(f"{cid}: sem {k}")
        if not c.get("measures"):
            errs.append(f"{cid}: sem medidas")
        if not c.get("evidence") or not all(PORTABLE.match(x) for x in c["evidence"]):
            errs.append(f"{cid}: evidência ausente ou caminho não portátil")
        if COVERAGE_WORDS.search(str(c.get("pass_rule"))):
            errs.append(f"{cid}: regra de aprovação com limiar sobre cobertura (proibido, §9.5)")
    cr = doc.get("reasoning_controls_rule") or {}
    if cr.get("controls") != ["c1_table", "c2_taxonomy", "c3_full"]:
        errs.append("controles têm de ser c1_table, c2_taxonomy, c3_full")
    if len(cr.get("invariants") or []) < 3:
        errs.append("invariantes dos controles incompletas")
    got = {o.get("id") for o in cr.get("outcomes") or []}
    if got != REQUIRED_OUTCOMES:
        errs.append(f"desfechos dos controles {sorted(got)} != {sorted(REQUIRED_OUTCOMES)}")
    for o in cr.get("outcomes") or []:
        if len(o.get("condition", "")) < 10 or len(o.get("consequence", "")) < 10:
            errs.append(f"{o.get('id')}: condição ou consequência vazia")
    ad = doc.get("addendum") or {}
    if not PORTABLE.match(str(ad.get("path", ""))) or ad.get("writer") != "PILOT-EXIT" or not ad.get("must_contain"):
        errs.append("adendo sem caminho portátil, escritor PILOT-EXIT ou conteúdo exigido")
    return errs


def main(argv=None) -> int:
    path = Path((argv or sys.argv[1:] or [str(common.FILES["pilot_exit"])])[0])
    errs = check(common.yaml_load(path))
    for x in errs:
        print("FAIL", x)
    if errs:
        print(f"RESULTADO: REPROVADO ({len(errs)})")
        return 1
    print("RESULTADO: OK (E1–E8, limite de 2 tentativas, regra dos 3 controles com 6 desfechos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
