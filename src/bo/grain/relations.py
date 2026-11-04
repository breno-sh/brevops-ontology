"""Verificador (gate do DECOMPOSE): relações entre unidades (anexação, referência) preservadas.

Uso: python -I -m bo.grain.relations [--schema-atoms 'GLOB' --evidence ARQ --units U --atoms A] | --fixtures

Toda referência resolvida da camada Terraform (campo de referência com alvo) tem de reaparecer na camada de
domínio de exatamente uma forma: como pai (componente ou faceta), como ponta de vínculo, como dono/alcance,
ou como referência simples entre unidades (átomo de referência atribuído à unidade de origem). Nenhuma some
porque o grão mudou de embalagem. Nas entradas do DECOMPOSE, as unidades C19 publicadas são conferidas
contra as relações recalculadas (pai, dono, alcance, pontas em endpoints).
--fixtures roda nos mundos sintéticos, confere a mesma assinatura de relações entre as embalagens do
contêiner e entre anexação embutida e separada, e um controle quebrado (relação apagada) tem de reprovar.
"""

from __future__ import annotations

import sys

from . import battery as B
from . import decompose_io as IO
from . import rules as R
from . import schema as S
from .common import stamp
from .evidence import PARENT, C25Adapter


def relations(res: S.SchemaResult, keep=None) -> tuple[list, list]:
    """(relações de domínio por rótulo, erros). Cada referência da camada Terraform (campo de referência com
    alvo, ou o pai estrutural) tem de virar exatamente uma relação de domínio: pai, ponta de vínculo, dono,
    declarada em (faceta declarada num extremo e dona de outro), chave (referência na identidade de um
    componente que não é o pai) ou referência simples."""
    rels, errs = [], []
    decs = res.decisions

    def lab(nid, seen=()):
        if nid is None or nid in seen:
            return ()
        if nid.startswith("EXT:"):
            return ("EXTERNAL:" + nid[4:],)
        d = decs[nid]
        return lab(d.parent, seen + (nid,)) + (d.label,)

    for nid in sorted(res.nodes if keep is None else keep):
        n, d = res.nodes[nid], decs[nid]
        if d.grain == "UNKNOWN":
            continue
        refs = {f: t for f, t in n.ref_targets.items() if t is not None}
        if n.parent is not None:
            refs[PARENT] = n.parent
        ends = {t: r for r, t in d.endpoints.items()}
        for f, t in sorted(refs.items()):
            how = None
            if d.grain == "BINDING" and f in d.identity.refs:
                how = "endpoint:" + (n.ev.parent_role if f == PARENT else f) if t in ends else None
            elif t == d.parent and (f in d.identity.refs or f == PARENT or
                                    t == (d.lifecycle.get("target"))):
                how = "parent"
            elif d.grain == "FACET" and f in d.identity.refs:
                how = "declared_on"
            elif f in d.identity.refs:
                how = "key:" + f
            elif f == PARENT:
                how = "declared_in"
            else:
                how = "ref:" + f
            if how is None:
                errs.append(f"{nid}.{f} -> {t}: relação perdida")
                continue
            rels.append((lab(nid), how, lab(t)))
        for t in d.owner.get("targets") or []:
            if t != d.parent:
                errs.append(f"{nid}: dono {t} diferente do pai {d.parent}")
        if d.grain in ("COMPONENT", "FACET") and d.parent is None:
            errs.append(f"{nid}: {d.grain} sem pai")
        if d.grain == "BINDING":
            got = {h for (a, h, b) in rels if a == lab(nid) and h.startswith("endpoint:")}
            if len(got) != len(d.endpoints) or len(d.endpoints) < 2:
                errs.append(f"{nid}: vínculo com pontas {sorted(d.endpoints)} e relações {sorted(got)}")
    return sorted(set(rels)), errs


def c19_relations(units: list[dict]) -> dict:
    out = {}
    for u in units:
        ends = sorted(f"{e['role']}={e['unit_id']}" for e in u.get("endpoints", []))
        out[u["unit_id"]] = (u["owner"].get("ref"), u["lifecycle_controller"].get("ref"),
                             u["effective_scope"].get("ref"), tuple(ends))
    return out


def fixtures() -> list[str]:
    rs = R.load()
    errs = []
    worlds = B.all_worlds()
    for name, w in sorted(worlds.items()):
        res = B.run_schema(w, rs)
        _, e = relations(res)
        errs += [f"{name}: {x}" for x in e]
        units, _ = S.to_c19(res)
        if c19_relations(units) != c19_relations(S.to_c19(res)[0]):
            errs.append(f"{name}: relações do C19 não determinísticas")
    res = B.run_schema(worlds["bucket"], rs)
    from .fixtures import BUCKET_PACKAGINGS
    per = {k: [(a, h.split(":")[0], b) for a, h, b in relations(res, S._closure(res, cids))[0]]
           for k, cids in BUCKET_PACKAGINGS.items()}
    if len({repr(sorted(set(v))) for v in per.values()}) != 1 or not per["inline"]:
        errs.append(f"bucket: assinatura de relações difere entre embalagens: {per}")
    nic = B.run_schema(worlds["nic"], rs)
    r_in = relations(nic, ["b_instance.network_interface", "b_instance", "b_nic"])[0]
    r_sep = relations(nic, ["b_nic_attachment", "b_instance", "b_nic"])[0]
    if r_in != r_sep or len(r_in) != 3:
        errs.append(f"nic: anexação embutida e separada com relações diferentes: {r_in} x {r_sep}")
    lb = B.run_schema(worlds["lb"], rs)
    pk = worlds["lb"]["packagings"]
    rl = {k: relations(lb, S._closure(lb, v))[0] for k, v in pk.items()}
    if rl["embedded"] != rl["separate"] or not any(h == "ref:pool" for _, h, _ in rl["embedded"]):
        errs.append(f"lb: relações embutido x separado diferem: {rl}")
    # controle: apagar a ponta de um vínculo tem de reprovar
    bad = B.run_schema(worlds["iam"], rs)
    bad.decisions["d_assignment"].endpoints.pop("principal")
    if not relations(bad)[1]:
        errs.append("controle: relação apagada passou")
    print(stamp(f"relations --fixtures: {len(worlds)} mundo(s), 4 embalagens do contêiner, 2 do balanceador, "
                f"1 controle"))
    return errs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--fixtures" in argv:
        errs = fixtures()
    else:
        rs = R.load()
        by = IO.schema_atoms(IO.arg(argv, "--schema-atoms"))
        recs = IO.service_evidence(IO.arg(argv, "--evidence"))
        units, _ = IO.c19(IO.arg(argv, "--units"), IO.arg(argv, "--atoms"))
        published = c19_relations(units)
        errs, n = [], 0
        for prov, atoms in sorted(by.items()):
            res = S.decompose_schema(S.candidates_from_atoms(atoms), C25Adapter([r for r in recs if r["provider"] ==
                                                                                 prov]), rs)
            _, e = relations(res)
            errs += [f"{prov}: {x}" for x in e]
            for uid, rel in c19_relations(S.to_c19(res)[0]).items():
                n += 1
                if uid in published and published[uid] != rel:
                    errs.append(f"{uid}: relações publicadas {published[uid]} != recalculadas {rel}")
        print(stamp(f"relations: {n} unidade(s) recalculada(s), {len(units)} publicada(s)"))
    for e in errs[:40]:
        print("  ", e)
    print("RESULTADO:", "OK" if not errs else "REPROVADO")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
