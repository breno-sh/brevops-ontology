"""Verificador (gate do DECOMPOSE): mesma saída com provedores renomeados e nas 24 ordens.

Uso: python -I -m bo.grain.permutation [--rename] [--schema-atoms 'GLOB' --evidence ARQ] | --fixtures [--rename]

Para cada uma das n! ordens dos provedores (24 com 4), roda a decomposição na ordem dada, sempre com o mesmo
objeto de regras, e compara a assinatura estrutural de cada provedor (bo.grain.schema.signature, sem camada
Terraform e sem provedor) com a da ordem canônica. Com --rename, antes de decompor troca o nome de cada
provedor por um sintético e cada tipo Terraform por um nome opaco (bijeção sorteada com semente fixa), e
exige a mesma assinatura e os mesmos registros C19 depois de desfazer a troca. Controle (--fixtures): um
adaptador que olha o nome do tipo tem de mudar a saída sob renomeação (o teste não é vazio).
"""

from __future__ import annotations

import copy
import itertools
import json
import random
import sys

from . import battery as B
from . import decompose_io as IO
from . import rules as R
from . import schema as S
from .common import stamp
from .evidence import C25Adapter, FixtureAdapter

FIXTURE_WORLDS = ("bucket", "nic", "firewall", "iam")


def _rename_cid(cid: str, tmap: dict) -> str:
    rt, sep, rest = cid.partition(".")
    if ":" in rt:
        rt, g = rt.split(":", 1)
        return tmap.get(rt, rt) + ":" + g
    return tmap.get(rt, rt) + (sep + rest if sep else "")


def rename_world(w: dict, pmap: dict, tmap: dict) -> dict:
    out = {"provider": pmap[w["provider"]], "schema": {tmap[k]: v for k, v in w["schema"].items()},
           "evidence": {}, "configs": {}}
    for cid, ev in w["evidence"].items():
        e = copy.deepcopy(ev)
        if "references" in e:
            e["references"] = {f: tmap.get(t, t) for f, t in e["references"].items()}
        out["evidence"][_rename_cid(cid, tmap)] = e
    return out


def maps(worlds: dict, seed: int):
    rnd = random.Random(seed)
    provs = sorted(w["provider"] for w in worlds.values())
    letters = list("pqrstuvwxyz")
    rnd.shuffle(letters)
    pmap = {p: f"provider_{letters[i]}" for i, p in enumerate(provs)}
    types = sorted({t for w in worlds.values() for t in w["schema"]})
    opaque = [f"t{i:03d}" for i in range(len(types))]
    rnd.shuffle(opaque)
    return pmap, dict(zip(types, opaque))


def run_order(worlds: dict, order, rs) -> dict:
    out = {}
    for name in order:
        res = B.run_schema(worlds[name], rs)
        out[name] = (S.signature(res), S.to_c19(res))
    return out


def unrename_records(recs, pmap_inv: dict, tmap_inv: dict):
    s = json.dumps(recs, sort_keys=True)
    for new, old in sorted(tmap_inv.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(new, old)
    for new, old in pmap_inv.items():
        s = s.replace(new, old)
    return json.loads(s)


def check(worlds: dict, rs, rename: bool) -> tuple[list[str], int]:
    names = sorted(worlds)
    base = run_order(worlds, names, rs)
    errs, n = [], 0
    for order in itertools.permutations(names):
        n += 1
        got = run_order(worlds, order, rs)
        for k in names:
            if got[k][0] != base[k][0] or got[k][1] != base[k][1]:
                errs.append(f"ordem {order}: {k} mudou")
    if rename:
        for seed in (1, 2, 3):
            pmap, tmap = maps(worlds, seed)
            rw = {k: rename_world(w, pmap, tmap) for k, w in worlds.items()}
            got = run_order(rw, names, rs)
            pinv, tinv = {v: k for k, v in pmap.items()}, {v: k for k, v in tmap.items()}
            for k in names:
                if got[k][0] != base[k][0]:
                    errs.append(f"renomeação {seed}: assinatura de {k} mudou")
                if _bag(unrename_records(got[k][1], pinv, tinv)) != _bag(base[k][1]):
                    errs.append(f"renomeação {seed}: registros C19 de {k} mudaram")
            n += 1
    return errs, n


def _bag(recs) -> list:
    units, atoms = recs
    return [sorted(json.dumps(u, sort_keys=True) for u in units), sorted(json.dumps(a, sort_keys=True) for a in atoms)]


class NameSniffingAdapter(FixtureAdapter):
    """Controle quebrado de propósito: decide pelo nome do tipo (o que as regras não podem fazer)."""

    def evidence(self, cid):
        ev = super().evidence(cid)
        if cid.split(".")[0].endswith("versioning"):
            return FixtureAdapter({}).evidence(cid)
        return ev


def control(rs) -> bool:
    w = B.all_worlds()["bucket"]
    base = S.signature(S.decompose_schema(S.candidates_from_tf_schema(w["provider"], w["schema"]),
                                          NameSniffingAdapter(w["evidence"]), rs))
    pmap, tmap = maps({"bucket": w}, 7)
    rw = rename_world(w, pmap, tmap)
    got = S.signature(S.decompose_schema(S.candidates_from_tf_schema(rw["provider"], rw["schema"]),
                                         NameSniffingAdapter(rw["evidence"]), rs))
    return got != base  # tem de mudar: o verificador pega dependência de nome


def from_inputs(argv) -> dict:
    by = IO.schema_atoms(IO.arg(argv, "--schema-atoms"))
    recs = IO.service_evidence(IO.arg(argv, "--evidence"))
    worlds = {}
    for prov, atoms in sorted(by.items()):
        worlds[prov] = {"provider": prov, "atoms": atoms, "records": [r for r in recs if r["provider"] == prov]}
    return worlds


def check_inputs(worlds: dict, rs, rename: bool) -> tuple[list[str], int]:
    def run(w, pmap=None, tmap=None):
        atoms, recs = w["atoms"], w["records"]
        if pmap:
            s = json.dumps({"a": atoms, "r": recs})
            for old, new in sorted(tmap.items(), key=lambda kv: -len(kv[0])):
                s = s.replace(f'"{old}"', f'"{new}"').replace(f":{old}:", f":{new}:")
            for old, new in pmap.items():
                s = s.replace(f'"{old}"', f'"{new}"').replace(f'"{old}:', f'"{new}:')
            d = json.loads(s)
            atoms, recs = d["a"], d["r"]
        res = S.decompose_schema(S.candidates_from_atoms(atoms), C25Adapter(recs), rs)
        return S.signature(res)

    names = sorted(worlds)
    base = {k: run(worlds[k]) for k in names}
    errs, n = [], 0
    for order in itertools.permutations(names):
        n += 1
        got = {k: run(worlds[k]) for k in order}
        errs += [f"ordem {order}: {k} mudou" for k in names if got[k] != base[k]]
    if rename:
        types = sorted({a["resource_type"] for w in worlds.values() for a in w["atoms"]})
        rnd = random.Random(1)
        opaque = [f"t{i:05d}" for i in range(len(types))]
        rnd.shuffle(opaque)
        tmap = dict(zip(types, opaque))
        pmap = {p: f"provider_{chr(ord('p') + i)}" for i, p in enumerate(names)}
        for k in names:
            n += 1
            if run(worlds[k], pmap, tmap) != base[k]:
                errs.append(f"renomeação: {k} mudou")
    return errs, n


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rs = R.load()
    rename = "--rename" in argv
    if "--fixtures" in argv:
        worlds = {k: v for k, v in B.all_worlds().items() if k in FIXTURE_WORLDS}
        errs, n = check(worlds, rs, rename)
        if rename and not control(rs):
            errs.append("controle: adaptador que lê o nome do tipo passou na renomeação (verificador vazio)")
    else:
        errs, n = check_inputs(from_inputs(argv), rs, rename)
    print(stamp(f"permutation{' --rename' if rename else ''}: {n} execução(ões); {len(errs)} divergência(s)"))
    for e in errs[:30]:
        print("  ", e)
    print("RESULTADO:", "OK" if not errs else "REPROVADO")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
