"""Grandeza única por unidade entre UNITS, SEMANTICS e TRANSFORMS, decidida pelo QUDT fixado (STO-MAP CC-5).

  python -I -m bo.units.crosscheck            compara os três núcleos com o QUDT 3.5.3; sai 1 se algum discorda
  python -I -m bo.units.crosscheck --write    grava results/UNITS/quantity_kind_decision.json (só a decisão e a
                                              citação; o estado dos outros módulos é ao vivo, não vai para o arquivo)
  python -I -m bo.units.crosscheck --check    o arquivo gravado é igual ao regenerado

Decisão (UNITS-QK-01, emenda 1 do UNITS): a grandeza de uma unidade é a que o QUDT 3.5.3 afirma por
qudt:unitForQuantityKind | qudt:hasQuantityKind | qudt:applicableUnit. Para BYTE, BIT e prefixos o QUDT afirma
quantitykind:AmountOfData (e ByteDataVolume/BitDataVolume), nunca quantitykind:InformationEntropy (cujas unidades no
QUDT 3.5.3 são BAN, ERLANG, HART, NAT e SHANNON). Entre as grandezas que o QUDT liga, vale a mais geral comum a
byte e bit: AmountOfData.
"""

from __future__ import annotations

import json
import sys

from . import qudt
from . import rules as R
from .build import results_dir

DECISION_VERSION = "1.0.0"
CITATION = {
    "source": "QUDT 3.5.3, github.com/qudt/qudt-public-repo tag v3.5.3",
    "file": "$BO_DATA/downloads/qudt-3.5.3/VOCAB_QUDT-UNITS-ALL.ttl",
    "sha256": qudt.FILES["VOCAB_QUDT-UNITS-ALL.ttl"],
    "statements": [
        {"line": 4384, "subject": "unit:BYTE"},
        {"line": 4415, "triple": "unit:BYTE qudt:unitForQuantityKind quantitykind:AmountOfData"},
        {"line": 4416, "triple": "unit:BYTE qudt:unitForQuantityKind quantitykind:ByteDataVolume"},
        {"line": 2528, "subject": "unit:BIT"},
        {"line": 2558, "triple": "unit:BIT qudt:unitForQuantityKind quantitykind:AmountOfData"},
    ],
    "absent": "nenhuma tripla liga unit:BYTE (ou BIT e prefixos) a quantitykind:InformationEntropy, por "
              "hasQuantityKind, unitForQuantityKind ou applicableUnit; qudt:hasQuantityKind não aparece no arquivo "
              "de grandezas e não liga BYTE no de unidades",
}


def semantics_units() -> dict:
    try:
        from bo.semantics import valuetypes
    except ImportError:
        return {}
    return {u: v[0] for u, v in valuetypes.UNITS.items()}


def transforms_units() -> dict:
    from bo.transforms import units as tu
    return {u: x.kind for u, x in tu.UNITS.items()}


def decision() -> dict:
    idx = qudt.index()
    rows = []
    for u, k in sorted(R.UNIT_KIND.items()):
        kinds = sorted(idx["units"][qudt.unit_local(u)]["kinds"])
        rows.append({"unit": u, "quantity_kind": k, "qudt_links": kinds,
                     "qudt_supports": qudt.qk_local(k) in kinds})
    return {"schema": "bo.units.quantity_kind_decision/1", "module": "UNITS", "version": DECISION_VERSION,
            "rule": "UNITS-QK-01", "resolves": ["PILOT-STO-MAP CC-5"],
            "decision": "uma grandeza por unidade, a que o QUDT 3.5.3 afirma; byte e bit: quantitykind:AmountOfData",
            "citation": CITATION, "units": rows,
            "owners_to_adopt": {
                "SEMANTICS": "src/bo/semantics/valuetypes.py INFO (e content/examples, counterexamples)",
                "TRANSFORMS": "src/bo/transforms/units.py INFO e transforms/transforms.yaml",
                "CONTRACTS": "stub C05 (value_space.jsonl) e src/bo/contracts/stubs.py",
                "ARBITERLIB": "valuetypes.py e transforms/units.py estão no ARBITER.sha256: recongelar no mesmo "
                              "merge (regra do CC-1)"}}


def compare() -> list[str]:
    out = []
    want = {r["unit"]: r["quantity_kind"] for r in decision()["units"]}
    for name, got in (("SEMANTICS", semantics_units()), ("TRANSFORMS", transforms_units())):
        for u, k in sorted(got.items()):
            if u in want and k != want[u]:
                out.append(f"{name}: {u} em {k}; o QUDT 3.5.3 dá {want[u]}")
    for r in decision()["units"]:
        if not r["qudt_supports"]:
            out.append(f"UNITS: {r['unit']} em {r['quantity_kind']} sem apoio do QUDT")
    return out


def render() -> str:
    return json.dumps(decision(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = results_dir() / "quantity_kind_decision.json"
    if "--write" in argv:
        p.write_text(render(), encoding="utf-8")
        print(f"gravado {p}")
        return 0
    if "--check" in argv:
        ok = p.exists() and p.read_text(encoding="utf-8") == render()
        print(f"quantity_kind_decision.json {'confere' if ok else 'DIFERENTE do regenerado'}")
        return 0 if ok else 1
    diffs = compare()
    for d in diffs:
        print("  " + d)
    print(f"crosscheck UNITS x SEMANTICS x TRANSFORMS (QUDT {qudt.QUDT_VERSION}): {len(diffs)} divergência(s)")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
