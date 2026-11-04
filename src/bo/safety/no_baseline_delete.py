"""Gate: recurso sem tag da execução nem linha do manifesto próprio nunca é apagado, mesmo fora do baseline.

  python -I -m bo.safety.no_baseline_delete

Para cada provedor, na nuvem simulada: grava o baseline, cria os recursos do lote pelo protocolo (intenção antes)
e, DEPOIS do baseline, recursos alheios que uma limpeza "por diferença de baseline" apagaria:
  N1 sem tag, de outro dono, em outra região
  N2 com a tag bo-run de OUTRA execução
  N3 nome com prefixo bo- de outro lote
  N4 nome no formato sintético DESTE lote, mas sem linha no manifesto (sequência que não existe)
  N5 nome igual ao de uma intenção nossa, mas de outro tipo
  N6 com bo-intent igual ao nosso, sem bo-run (rótulo copiado)
  N7 alheio que já estava no baseline
E um recurso com a tag DESTA execução numa região fora da permitida, sem intenção (vazamento): tem de ser achado
pela varredura de todas as regiões, removido (a tag prova a posse) e relatado como violação.
Confere: (a) a lista "inventário menos baseline" é recusada (ownership.delete_candidates); (b) a limpeza apaga só
o que é nosso e nenhum N1–N7; (c) a varredura classifica N1–N6 como "investigar" e N7 como "baseline", sem apagar;
(d) com a trava cleanup-global tomada por outro dono, uma segunda limpeza paralela é recusada e não apaga nada.
Relatório: $BO_DATA/SAFETY/no_baseline_delete_last.json; results/SAFETY/no_baseline_delete.json só com
--write-results (o gate compara e reprova se divergir).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import locks, residue, skus
from .common import (PROVIDERS, bo_tmp, data_dir, now, publish_result, results_dir, synthetic_name, tag_value,
                     write_json)
from .fakecloud import FakeCloud
from .manifest import Manifest
from .locks import LockBusy
from .ownership import OwnershipRefused, cleanup, delete_candidates, owned, reconcile
from .sim_runner import REGIONS, SCENARIOS, paths, setup, sim_check


def scenario(provider: str, table: dict, res: dict) -> dict:
    d = bo_tmp() / "no_baseline_delete" / provider
    shutil.rmtree(d, ignore_errors=True)
    fc = setup(d, provider, table, foreign=False)
    p = paths(d)
    regs = REGIONS[provider]
    region = table["providers"][provider]["regions_allowed"][0]
    batch = f"B-SIM-{provider.upper()}-01"
    run_tag = tag_value(batch)
    types = [t for t, _ in SCENARIOS[provider]]
    n7 = fc.create(types[0], regs[1], "ja-existia", {}, owner="terceiro")
    baseline = {i["ref"] for i in fc.list_all()}

    man = Manifest(f"SIM-{provider.upper()}", p["public"], p["private"])
    ours = []
    for rtype in types:
        f = skus.intent_fields(table, provider, rtype)
        chk = sim_check(d, provider)
        it = man.record_intent(provider=provider, batch_id=batch, resource_type=rtype, identity_check=chk,
                               ttl_hours=2, table_fields=f, address=f"{rtype}.caso", region=region, run_tag=run_tag)
        man.stage(it["intent_id"], "creating", identity_check=chk)
        name = it["logical_name"] if f["trace"] != "ref" else None
        ref = fc.create(rtype, region, name, it.get("tags"))
        man.stage(it["intent_id"], "created", identity_check=chk, ref=ref)
        ours.append((rtype, ref, it))
    named = next((x for x in ours if x[2]["logical_name"] and not x[2].get("tags")), ours[0])
    other_type = next(t for t in types if t != named[0])
    aliens = {
        "N1": fc.create(types[-1], regs[-1], "app-producao", {}, owner="terceiro"),
        "N2": fc.create(types[-1], region, "dados", {"bo-run": "b-sim-outra-99"}, owner="terceiro"),
        "N3": fc.create(types[1], region, "bo-outro-lote-0001", {}, owner="terceiro"),
        "N4": fc.create(named[0], region, synthetic_name(batch, 99), {}, owner="terceiro"),
        "N5": fc.create(other_type, region, named[2]["logical_name"], {}, owner="terceiro"),
        "N6": fc.create(types[-1], region, "copiado", {"bo-intent": tag_value(ours[-1][2]["intent_id"])},
                        owner="terceiro"),
    }
    aliens["N7"] = n7
    leak_region = next(r for r in regs if r != region)
    sync_type = next(t for t in types if table["providers"][provider]["types"][t]["removal"]["mode"] == "sync"
                     and table["providers"][provider]["types"][t]["trace"] == "tag")
    leak = fc.create(sync_type, leak_region, "vazou", {"bo-run": run_tag})

    out = {"provider": provider, "fails": []}
    # (a) diferença de baseline como lista de candidatos: recusada
    candidates = [i for i in fc.list_all() if i["ref"] not in baseline]
    try:
        delete_candidates(candidates)
        out["fails"].append("(a) lista por diferença de baseline foi aceita")
    except OwnershipRefused:
        out["baseline_diff_refused"] = True
    out["baseline_diff_would_delete_aliens"] = sum(1 for i in candidates if i["ref"] in aliens.values())

    # (c) varredura classifica sem apagar
    states = man.load()
    classes = {}
    for k, ref in aliens.items():
        it = fc.get(ref)
        classes[k] = residue.classify(res, provider, it, owned(it, run_tag, states), baseline)
    out["sweep_classes"] = classes
    for k, c in classes.items():
        want = "baseline" if k == "N7" else "investigar"
        if c != want:
            out["fails"].append(f"(c) {k} classificado como {c}, esperado {want}")

    # (d) trava tomada por outro dono: segunda limpeza paralela recusada, nada apagado
    before = set(fc.items())
    locks.acquire(locks.CLEANUP, "outra-limpeza@teste", root=p["locks"])
    try:
        cleanup(man, fc, run_tag, sim_check(d, provider), owner="SAFETY-no-baseline", lock_root=p["locks"])
        out["fails"].append("(d) limpeza paralela rodou com a trava de outro dono")
    except LockBusy:
        out["parallel_refused"] = True
    finally:
        locks.release(locks.CLEANUP, "outra-limpeza@teste", root=p["locks"])
    if set(fc.items()) != before:
        out["fails"].append("(d) limpeza recusada apagou algo")

    # (b) limpeza de verdade: só o nosso
    order = {t: e["delete_order"] for t, e in table["providers"][provider]["types"].items()}
    rep = cleanup(man, fc, run_tag, sim_check(d, provider), owner="SAFETY-no-baseline",
                  order_fn=lambda t: order.get(t, 0), lock_root=p["locks"], wait_fn=lambda s: fc.advance(3600),
                  poll_s=3600)
    items = fc.items()
    for k, ref in aliens.items():
        if ref not in items:
            out["fails"].append(f"(b) alheio {k} foi apagado")
    if fc.foreign_deletes():
        out["fails"].append("(b) pedido de remoção para recurso alheio")
    for rtype, ref, _ in ours:
        if ref in items and not residue.owned_expected(res, provider, items[ref]):
            out["fails"].append(f"(b) nosso {rtype} sobrou em {items[ref]['state']}")
    if leak in items:
        out["fails"].append("(leak) recurso com a tag da execução em outra região não foi achado")
    if not rep.untracked_seen:
        out["fails"].append("(leak) recurso sem intenção não foi relatado como violação")
    out["deleted_ours"] = sum(1 for _, ref, _ in ours if ref not in items)
    out["kept_aliens"] = sum(1 for ref in aliens.values() if ref in items)
    out["leak_found_and_reported"] = leak not in items and bool(rep.untracked_seen)
    out["foreign_after"] = rep.foreign
    rec = reconcile(man, fc.list_all(), run_tag, sim_check(d, provider), write=False)
    out["owned_live_after"] = len(rec.owned_live)
    if not out["fails"]:
        shutil.rmtree(d, ignore_errors=True)
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    table = skus.load_table()
    res = residue.load()
    rows = [scenario(p, table, res) for p in PROVIDERS]
    nf = sum(len(r["fails"]) for r in rows)
    summary = {
        "schema": "bo.safety.no_baseline_delete/1", "providers": rows,
        "aliens": ["N1 sem tag noutra região", "N2 tag de outra execução", "N3 prefixo bo- de outro lote",
                   "N4 formato sintético deste lote sem manifesto", "N5 nome nosso noutro tipo",
                   "N6 bo-intent copiado sem bo-run", "N7 já no baseline"],
        "failed": nf}
    write_json(data_dir() / "no_baseline_delete_last.json", {**summary, "measured_at": now()})
    drift = publish_result(results_dir() / "no_baseline_delete.json", summary, "--write-results" in argv)
    for d in drift:
        print("  " + d)
        nf += 1
    for r in rows:
        print(f"{r['provider']}: nossos apagados {r.get('deleted_ours')}, alheios mantidos {r.get('kept_aliens')}/7, "
              f"baseline recusado {r.get('baseline_diff_refused', False)}, paralela recusada "
              f"{r.get('parallel_refused', False)}, vazamento achado {r.get('leak_found_and_reported')}"
              + (f"  FALHAS: {r['fails']}" if r["fails"] else ""))
    print(f"no_baseline_delete: {nf} falha(s) -> {'OK' if not nf else 'REPROVADO'}")
    return 0 if nf == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
