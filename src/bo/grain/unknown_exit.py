"""Gate: evidência faltando (ou contraditória) → UNKNOWN com a lista do que falta; nunca ENTITY por exclusão.

Bateria de mutação sobre todos os mundos sintéticos: para cada candidato e cada campo de evidência, (a) apaga
as alegações do campo e (b) injeta uma alegação divergente. Em cada mutante confere:
  A. nenhum nó vira ENTITY se não era ENTITY no original (nunca ENTITY por exclusão);
  B. todo UNKNOWN tem missing_evidence não vazio e regra GRAIN-G0-*;
  C. nó cujo grão mudou virou UNKNOWN (falta de evidência nunca troca um grão por outro);
  D. o candidato mutado, se virou UNKNOWN, lista o campo mutado (no vocabulário do C19);
  E. apagar os três campos de identidade de um candidato dá sempre UNKNOWN com identity.
Mais os casos nomeados dos compromissos (CMT-BKT-U02, CMT-NIC-U02, CMT-LC-U01) na camada de instância.
Não vacuidade: a bateria precisa produzir mutantes que mudam o resultado (contagem no relatório).
Relatório em $BO_DATA/GRAIN/unknown_exit.json. Sai 0 só sem violação.
"""

from __future__ import annotations

import copy
import json
import sys

from . import battery as B
from . import fixtures as F
from . import instance as I
from . import rules as R
from .common import data_dir, dump_json, now, stamp
from .evidence import C19_OF_FIELD, FIELDS, FixtureAdapter

ID_FIELDS = ("identity", "import_key", "element_name_key")


def _check(base: dict, mut: dict, cid: str, fld: str | None, mode: str, viol: list, stats: dict):
    for nid, d in mut.items():
        b = base.get(nid)
        if d.grain == "UNKNOWN":
            if not d.missing or not d.rule.startswith("GRAIN-G0-"):
                viol.append(f"B {mode}:{cid}.{fld} -> {nid}: UNKNOWN sem missing ou com regra {d.rule}")
        if d.grain == "ENTITY" and (b is None or b.grain != "ENTITY"):
            viol.append(f"A {mode}:{cid}.{fld} -> {nid}: virou ENTITY (era {b.grain if b else 'transparente'})")
        changed = b is None or b.grain != d.grain
        if changed and d.grain != "UNKNOWN":
            viol.append(f"C {mode}:{cid}.{fld} -> {nid}: grão mudou {b.grain if b else 'transparente'} -> {d.grain}")
        if changed:
            stats["changed_nodes"] += 1
    d = mut.get(cid)
    b = base.get(cid)
    if d is not None and d.grain == "UNKNOWN" and (b is None or b.grain != "UNKNOWN") and fld:
        need = C19_OF_FIELD[fld]
        if need not in d.missing:
            viol.append(f"D {mode}:{cid}.{fld}: UNKNOWN sem listar {need} (missing={d.missing})")
        stats["became_unknown"] += 1


def run(rs: R.RuleSet | None = None) -> dict:
    rs = rs or R.load()
    worlds = B.all_worlds()
    viol: list[str] = []
    stats = {"worlds": len(worlds), "mutants": 0, "changed_nodes": 0, "became_unknown": 0,
             "identity_wipes": 0, "named_cases": 0}
    for wname, w in sorted(worlds.items()):
        base = B.run_schema(w, rs).decisions
        for cid, path in B.evidence_slots(w["evidence"]):
            for fld in FIELDS:
                for mode in ("drop", "contradict"):
                    ev = copy.deepcopy(w["evidence"])
                    slot = B.get_slot(ev, path)
                    if mode == "drop":
                        if not slot.get(fld):
                            continue
                        slot[fld] = []
                    else:
                        slot[fld] = B.contradiction(fld, slot.get(fld, []))
                    mut = B.run_schema(w, rs, ev).decisions
                    stats["mutants"] += 1
                    _check(base, mut, cid, fld, f"{wname}/{mode}", viol, stats)
            ev = copy.deepcopy(w["evidence"])
            slot = B.get_slot(ev, path)
            for fld in ID_FIELDS:
                slot[fld] = []
            mut = B.run_schema(w, rs, ev).decisions
            stats["mutants"] += 1
            stats["identity_wipes"] += 1
            _check(base, mut, cid, None, f"{wname}/wipe_identity", viol, stats)
            d = mut.get(cid)
            if d is not None and (d.grain != "UNKNOWN" or "identity" not in d.missing):
                viol.append(f"E {wname}:{cid}: sem evidência de identidade deu {d.grain} {d.missing}")
    viol += named_cases(rs, stats)
    ok = not viol and stats["became_unknown"] > 0 and stats["changed_nodes"] > 0
    return {"schema": "bo.grain.unknown_exit/1", "module": "GRAIN", "rules_version": rs.version,
            "generated_at": now(), "ok": ok, "stats": stats, "violations": viol}


def named_cases(rs, stats) -> list:
    """Casos dos compromissos na camada de instância."""
    out = []
    W = B.all_worlds()

    def occs(world, cfg):
        return I.decompose_config(world["configs"][cfg], FixtureAdapter(world["evidence"]),
                                  F.schema_blocks(world["schema"]), rs)

    # CMT-BKT-U02: configuração separada com referência ao contêiner não resolvida
    o = [x for x in occs(W["namespace"], "unresolved") if x.label == "retention"]
    stats["named_cases"] += 1
    if not (len(o) == 1 and o[0].grain == "UNKNOWN" and "owner" in o[0].missing):
        out.append(f"CMT-BKT-U02: esperado UNKNOWN com owner, veio {[(x.grain, x.missing) for x in o]}")
    # CMT-NIC-U02: anexação separada com referência simbólica à interface
    o = [x for x in occs(W["nic"], "separate_unresolved") if x.label == "interface attachment"]
    stats["named_cases"] += 1
    if not (len(o) == 1 and o[0].grain == "UNKNOWN" and "identity" in o[0].missing):
        out.append(f"CMT-NIC-U02: esperado UNKNOWN com identity, veio {[(x.grain, x.missing) for x in o]}")
    # CMT-LC-U01: configuração sem evidência de controlador de ciclo de vida
    res = B.run_schema(W["namespace"], rs)
    d = res.decisions["e_orphan_setting"]
    stats["named_cases"] += 1
    if not (d.grain == "UNKNOWN" and d.missing == ["lifecycle_controller"]):
        out.append(f"CMT-LC-U01: esperado UNKNOWN [lifecycle_controller], veio {d.grain} {d.missing}")
    # faceta com vários donos sem vínculo entre eles: UNKNOWN com owner, nunca faceta de um só dono
    d = B.run_schema(W["multi_owner_nobinding"], rs).decisions["g_exchange_setting"]
    stats["named_cases"] += 1
    if not (d.grain == "UNKNOWN" and "owner" in d.missing):
        out.append(f"faceta de vários donos sem vínculo: veio {d.grain} {d.missing}")
    return out


def broken_rules(rs: R.RuleSet) -> R.RuleSet:
    """Controle: regras no estilo da v2 (o resto vira entidade). A bateria TEM de reprovar este conjunto."""
    raw = copy.deepcopy(rs.raw)
    for r in raw["rules"]:
        if r["id"] == "GRAIN-G0-IDENTITY":
            r["match"] = {"identity_class_in": ["CONTRADICTORY"]}
        if r["id"] == "GRAIN-G4-ENTITY":
            r["match"] = {"identity_class_in": ["INDEPENDENT", "ABSENT", "ORPHAN", "UNRESOLVED"]}
            r["needs"] = []
            r["guard"] = {}
    return R.parse(raw)


def main(argv=None) -> int:
    rep = run()
    ctl = run(broken_rules(R.load()))
    rep["control_v2_style"] = {"violations": len(ctl["violations"]), "detected": not ctl["ok"],
                               "sample": ctl["violations"][:5]}
    if not rep["control_v2_style"]["detected"]:
        rep["ok"] = False
        rep["violations"].append("controle: a bateria não reprovou as regras no estilo da v2 (gate vazio)")
    p = data_dir() / "unknown_exit.json"
    p.write_text(dump_json(rep), encoding="utf-8")
    s = rep["stats"]
    print(stamp(f"unknown_exit: {s['mutants']} mutante(s) em {s['worlds']} mundo(s); "
                f"{s['became_unknown']} candidato(s) viraram UNKNOWN; {s['changed_nodes']} nó(s) mudaram; "
                f"{s['named_cases']} caso(s) nomeado(s); {len(rep['violations'])} violação(ões)"))
    for v in rep["violations"][:40]:
        print("  VIOLA", v)
    print(f"  controle (regras estilo v2, resto vira ENTITY): {rep['control_v2_style']['violations']} violação(ões) "
          f"detectada(s) -> {'reprovado, como deve' if rep['control_v2_style']['detected'] else 'NÃO REPROVOU'}")
    print(f"  relatório: {p}")
    print("RESULTADO:", "OK" if rep["ok"] else "REPROVADO")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
