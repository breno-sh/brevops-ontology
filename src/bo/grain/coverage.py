"""Verificador (gate do DECOMPOSE): todo átomo tem endereço canônico ou está em UNKNOWN com a evidência que falta.

Uso: python -I -m bo.grain.coverage [--units U --atoms A --schema-atoms 'GLOB'] | --fixtures

Confere: (1) todo atom_id dos átomos C01 aparece em canonical_atoms, uma vez só (C19-UNIQ); (2) todo
canonical_atom aponta para unidade existente (C19-LINK); (3) toda unidade UNKNOWN tem missing_evidence não
vazio e toda não-UNKNOWN tem missing vazio (C19-UNKNOWN); (4) nenhum canonical_atom sem átomo C01 de origem.
--fixtures roda nos mundos sintéticos e em dois controles quebrados (átomo sem endereço; UNKNOWN sem
missing), que têm de reprovar.
"""

from __future__ import annotations

import copy
import sys
from collections import Counter

from . import battery as B
from . import decompose_io as IO
from . import rules as R
from . import schema as S
from .common import stamp


def check(schema_atoms: list[dict], units: list[dict], atoms: list[dict]) -> list[str]:
    errs = []
    uids = Counter(u["unit_id"] for u in units)
    errs += [f"unit_id repetido: {k}" for k, v in uids.items() if v > 1]
    for u in units:
        if u["kind"] == "UNKNOWN" and not u.get("missing_evidence"):
            errs.append(f"{u['unit_id']}: UNKNOWN sem a evidência que falta")
        if u["kind"] != "UNKNOWN" and u.get("missing_evidence"):
            errs.append(f"{u['unit_id']}: {u['kind']} com missing_evidence")
    seen = Counter(a["atom_id"] for a in atoms)
    errs += [f"átomo em mais de uma unidade: {k}" for k, v in seen.items() if v > 1]
    errs += [f"canonical_atom aponta para unidade inexistente: {a['atom_id']}" for a in atoms
             if a["unit_id"] not in uids]
    src = {a["atom_id"] for a in schema_atoms}
    # sub-átomos virtuais (T2): derivados do tipo cty de um átomo de coleção de objetos do C01
    from .schema import collection_fields
    colls = tuple(a["atom_id"] + "." for a in schema_atoms if collection_fields(a.get("tf_type")))
    errs += [f"átomo sem endereço canônico: {k}" for k in sorted(src - set(seen))]
    errs += [f"canonical_atom sem átomo de origem: {k}" for k in sorted(set(seen) - src) if not k.startswith(colls)]
    return errs


def fixtures() -> list[str]:
    rs = R.load()
    errs = []
    n = 0
    for name, w in sorted(B.all_worlds().items()):
        res = B.run_schema(w, rs)
        units, atoms = S.to_c19(res)
        src = S.atoms_from_tf_schema(w["provider"], w["schema"])
        e = check(src, units, atoms)
        errs += [f"{name}: {x}" for x in e]
        n += len(src)
        if name == "bucket":
            if not check(src, units, atoms[1:]):
                errs.append("controle: átomo sem endereço passou")
            bad = copy.deepcopy(units)
            k = next(i for i, u in enumerate(bad) if u["kind"] != "UNKNOWN")
            bad[k]["kind"] = "UNKNOWN"
            if not check(src, bad, atoms):
                errs.append("controle: UNKNOWN sem missing passou")
    print(stamp(f"coverage --fixtures: {n} átomo(s) em {len(B.all_worlds())} mundo(s); 2 controle(s)"))
    return errs


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--fixtures" in argv:
        errs = fixtures()
    else:
        by = IO.schema_atoms(IO.arg(argv, "--schema-atoms"))
        units, atoms = IO.c19(IO.arg(argv, "--units"), IO.arg(argv, "--atoms"))
        src = [a for v in by.values() for a in v]
        errs = check(src, units, atoms)
        print(stamp(f"coverage: {len(src)} átomo(s) C01, {len(units)} unidade(s), {len(atoms)} átomo(s) C19"))
    for e in errs[:50]:
        print("  ", e)
    print("RESULTADO:", "OK" if not errs else f"REPROVADO ({len(errs)})")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
