"""Gate: recurso que só liga dois outros vira VÍNCULO mesmo sendo recurso Terraform separado.

Casos (mundos sintéticos de bo.grain.worlds):
  P1. anexação separada (id opaco, ciclo de vida próprio, recurso de API próprio, chave de importação =
      instância + interface): a leitura por embalagem (regra da v2: recurso de topo com chave de importação
      e ciclo de vida próprio é entidade) diz ENTITY; o procedimento diz BINDING por G1.
  P2. anexação embutida e separada dão a MESMA ocorrência de vínculo (mesmo hash) e as mesmas pontas.
  P3. atribuição <principal, conjunto, escopo> separada: BINDING com três pontas.
  P4. a prioridade carrega peso: numa anexação embutida cujo ciclo de vida é preso à instância, G1 e G2
      aceitam a evidência; com a ordem real dá BINDING e com G2 antes de G1 (mutação) dá COMPONENT.
  P5. sem G1 (mutação), a anexação separada NÃO cai em ENTITY: dá UNKNOWN (nunca entidade por exclusão).
  P6. controles negativos: regra de firewall com duas referências cujo dono é o conjunto continua
      COMPONENT (G1 não rouba); configuração separada com uma referência continua FACET.
Relatório em $BO_DATA/GRAIN/priority.json. Sai 0 só se todos valem.
"""

from __future__ import annotations

import copy
import sys

from . import battery as B
from . import fixtures as F
from . import instance as I
from . import rules as R
from .common import data_dir, dump_json, now, stamp
from .evidence import FixtureAdapter, consolidate


def naive_v2(world: dict, cid: str) -> str:
    """Leitura por embalagem (o que a v2 fazia): recurso Terraform de topo com chave de importação e ciclo de
    vida próprio é entidade. Só para mostrar o contraste; não é usada em decisão."""
    ev = world["evidence"].get(cid, {})
    top = "." not in cid and ":" not in cid
    imp = consolidate("import_key", ev.get("import_key", []))
    lc = consolidate("lifecycle_controller", ev.get("lifecycle_controller", []))
    if top and imp.known and imp.value["status"] == "present" and lc.known and lc.value["kind"] == "self":
        return "ENTITY"
    return "OTHER"


def run(rs: R.RuleSet | None = None) -> dict:
    rs = rs or R.load()
    W = B.all_worlds()
    checks = []

    def chk(cid, ok, detail):
        checks.append({"case": cid, "ok": bool(ok), "detail": detail})

    nic = W["nic"]
    res = B.run_schema(nic, rs)
    d = res.decisions["b_nic_attachment"]
    g4 = rs.by_id("GRAIN-G4-ENTITY")
    from .engine import Context, derive_identity
    ctx = Context(res.nodes["b_nic_attachment"], d.identity, res.decisions, {})
    g4_guard_ok = all(R.eval_pred(k, v, ctx) for k, v in g4.guard.items())
    chk("P1", d.grain == "BINDING" and d.rule == "GRAIN-G1-BINDING" and naive_v2(nic, "b_nic_attachment") == "ENTITY"
        and g4_guard_ok and sorted(d.endpoints) == ["instance", "interface"],
        {"procedure": [d.grain, d.rule, d.identity.cls], "naive_v2": naive_v2(nic, "b_nic_attachment"),
         "g4_guard_would_accept": g4_guard_ok, "endpoints": sorted(d.endpoints)})

    blocks = F.schema_blocks(nic["schema"])
    ad = FixtureAdapter(nic["evidence"])
    occ_in = [o for o in I.decompose_config(nic["configs"]["inline_2"], ad, blocks, rs) if o.grain == "BINDING"]
    occ_sep = [o for o in I.decompose_config(nic["configs"]["separate_2"], ad, blocks, rs) if o.grain == "BINDING"]
    chk("P2", len(occ_in) == len(occ_sep) == 2 and I.canonical_rows(occ_in) == I.canonical_rows(occ_sep),
        {"inline": sorted(o.occ_id for o in occ_in), "separate": sorted(o.occ_id for o in occ_sep)})

    iam = W["iam"]
    d = B.run_schema(iam, rs).decisions["d_assignment"]
    chk("P3", d.grain == "BINDING" and sorted(d.endpoints) == ["permission_set", "principal", "scope"]
        and naive_v2(iam, "d_assignment") == "ENTITY",
        {"procedure": [d.grain, d.rule], "endpoints": sorted(d.endpoints), "naive_v2": naive_v2(iam, "d_assignment")})

    ev = copy.deepcopy(nic["evidence"])
    ev["b_instance.network_interface"]["lifecycle_controller"] = [F.c(kind="parent", tag="att-lc")]
    real = B.run_schema(nic, rs, ev).decisions["b_instance.network_interface"]
    order = [r.id for r in rs.rules]
    i1, i2 = order.index("GRAIN-G1-BINDING"), order.index("GRAIN-G2-COMPONENT")
    swapped = order[:]
    swapped[i1], swapped[i2] = swapped[i2], swapped[i1]
    mut = B.run_schema(nic, R.reprioritized(rs, swapped), ev).decisions["b_instance.network_interface"]
    chk("P4", real.grain == "BINDING" and mut.grain == "COMPONENT",
        {"real_order": real.grain, "g2_before_g1": mut.grain})

    no_g1 = R.RuleSet(rules=[r for r in rs.rules if r.id != "GRAIN-G1-BINDING"], version=rs.version + "-noG1",
                      status="MUTATED", raw=rs.raw)
    d5 = B.run_schema(nic, no_g1).decisions["b_nic_attachment"]
    chk("P5", d5.grain == "UNKNOWN" and d5.missing, {"without_g1": [d5.grain, d5.rule, d5.missing]})

    fw = B.run_schema(W["firewall"], rs).decisions["c_rule_from_set"]
    ver = B.run_schema(W["bucket"], rs).decisions["a_bucket_versioning"]
    chk("P6", fw.grain == "COMPONENT" and fw.identity.cls == "REF_TUPLE_PLUS" and ver.grain == "FACET",
        {"rule_from_set": [fw.grain, fw.identity.cls], "versioning_resource": [ver.grain, ver.identity.cls]})
    ok = all(c["ok"] for c in checks)
    return {"schema": "bo.grain.priority/1", "module": "GRAIN", "rules_version": rs.version, "generated_at": now(),
            "ok": ok, "checks": checks}


def main(argv=None) -> int:
    rep = run()
    p = data_dir() / "priority.json"
    p.write_text(dump_json(rep), encoding="utf-8")
    for c in rep["checks"]:
        print(f"  {'OK  ' if c['ok'] else 'FAIL'} {c['case']} {c['detail']}")
    print(stamp(f"priority: {sum(c['ok'] for c in rep['checks'])}/{len(rep['checks'])} caso(s); relatório {p}"))
    print("RESULTADO:", "OK" if rep["ok"] else "REPROVADO")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
