"""Materializa o TRANSFORMS: python -I -m bo.transforms.build [--check]

Escreve, só a partir de src/bo/transforms:
  transforms/transforms.yaml            registro fechado (C10 transforms)
  transforms/conditions.grammar.json    gramática de guarda com os sat_tests (C10 conditions_grammar)
  results/TRANSFORMS/registro.json      índice do registro (itens, perdas, inversas, exemplos) e achados
  results/TRANSFORMS/MANIFEST.sha256    hashes (C17) das saídas, do código, dos testes, do gate e do summary.json
Antes de gravar, confere que cada sat_test dá o esperado nas duas implementações (esta e a do SEMANTICS) e no
oráculo de força bruta, e que todo exemplo do registro passa.
--check não grava: sai 1 se algo publicado difere do que o código produz (regeneração idêntica).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

from . import common as C
from . import grammar as GR
from . import guards as M
from . import registry as R
from .examples import run_all

FINDINGS = [
    "bo.semantics.guards.satisfiable dava SAT (ou UNKNOWN) onde não há valor possível em duas classes de guarda, "
    "e esta implementação (conferida por força bruta) dá UNSAT: (a) version_range sobre termo de universo fechado "
    "(enum ou boolean) ou não textual; (b) refers_to_kind junto com restrição de valor escalar ou universo fechado "
    "no mesmo termo. Eram 39 de 3998 guardas aleatórias; o SEMANTICS corrigiu em f48865f, os sat_tests passaram a "
    "incluir as duas classes e o guard_sat agora exige igualdade total (ver $BO_DATA/TRANSFORMS/guard_sat.json).",
    "O C10 não tem variável de tipo: uma escalar polimórfica que preserva a grandeza não se declara com grandeza "
    "concreta. O registro declara por grandeza (unit_convert_time, round_information, ...) e deixa só identity "
    "polimórfica, com grandeza NOT_APPLICABLE como no stub do CONTRACTS; NOT_APPLICABLE ali quer dizer 'não impõe "
    "nem muda grandeza', não 'valor sem grandeza'. Sugestão ao CONTRACTS: quantity_kind '$in' (variável) no C10.",
    "O comparador numeric_tolerance do C11 tem só {name, tolerance}, sem dizer se a tolerância é absoluta ou "
    "relativa (o C22 tem kind). O registro declara ABSOLUTA, na unidade do expected; tipos de unidade diferentes "
    "dos dois lados vão por compare_quantity_tolerance. Sugestão ao CONTRACTS: tolerance_kind no C11.",
    "O C10 3.2.0 (emendas 8 e 9 do CONTRACTS, pedidas pelo TRANSFORMS) aceita list/set/map com item_type nas "
    "portas e item_type {datatype: any} para porta polimórfica: o registro 1.5.0 usa os dois; o tipo exato de cada "
    "uso sai de collection_type_out.",
    "O C10 combinador não tem params: o que é parâmetro no núcleo do SEMANTICS (key de json_get/map_get) vira porta "
    "de entrada aqui; json_get e map_get ficam com duas entradas e uma saída.",
    "xsd:duration segue o espaço de valores do XSD 1.1 (meses, segundos): P0M1D não tem meses e vira 86400 s sem "
    "contexto; P1M e P1Y sem contexto de calendário são TRANSFORM_OUT_OF_DOMAIN; P1M = P30D é falso (duration_equal).",
    "BYTE e BIT sem prefixo: o registro dá convenção de byte None (fator 1 em SI e IEC) e aceita a convenção vácua "
    "que o UNITS grava (SI, UNITS-BYTE-00) ou NOT_APPLICABLE (C05 3.1.0); grandeza e convenção dos prefixados "
    "iguais a bo.units.rules, e bo.units.crosscheck dá 0 divergências (test_tr_units_rules).",
    "Os IRIs de unidade seguem o padrão do C00 e as grandezas do UNITS (QUDT 3.5.3); a existência de cada IRI no QUDT "
    "(iri_status = pattern_only) é conferida pelo UNITS, não aqui.",
    "O núcleo do SEMANTICS tem scale (fator sem unidade) e rate_window_convert sem grandeza; o registro fechado não "
    "os inclui: unit_convert_<grandeza> e rate_window_convert_<grandeza> cobrem os usos com tipo concreto.",
]


# emendas versionadas do registro: qual pedido cada commit resolve (o commit é citado pelo assunto, estável no rebase)
EMENDAS = [
    {"registry_version": "1.1.0", "commit_subject": "[TRANSFORMS] emenda 1.1.0: domínio finito de enum_to_bool (CC-9)",
     "request": "PILOT-STO-MAP CC-9 (results/CONTRACTS/emenda7.json: NÃO É DO CONTRACTS, dono ARBITERLIB, TRANSFORMS)",
     "change": "finite_domain/finite_image no registro; enum_to_bool declara domínio = true ∪ false, bool_to_enum "
               "domínio {true, false} e imagem {params.true, params.false}, enum_map domínio = chaves (part_of nos "
               "params e na pré-condição); o ARBITERLIB recongela para usar no VDR"},
    {"registry_version": "1.2.0", "commit_subject": "[TRANSFORMS] emenda 1.2.0: combinadores de coleção (CC-6)",
     "request": "PILOT-STO-MAP CC-6 (results/CONTRACTS/emenda7.json: ACEITO, C09 3.2.0; combinadores do registro "
                "do C10 com o TRANSFORMS)",
     "change": "wrap_list/unwrap_single (escalar <-> lista de um), list_to_set (perda declarada de ordem e "
               "repetição)/set_to_list, map_list/map_set/map_values (escalar do registro elemento a elemento, "
               "inversa com a inversa da escalar) e collection_type_out (value_type do C09 3.2.0); portas tuple + "
               "collection porque o C10 3.0.0 não tem list/set/map (CONTRACT_CHANGE.txt)"},
    {"registry_version": "1.3.0", "commit_subject": "[TRANSFORMS] emenda 1.3.0: bytes e bits em AmountOfData (CC-5)",
     "request": "PILOT-STO-MAP CC-5 (results/CONTRACTS/emenda7.json: NÃO É DO CONTRACTS, donos UNITS e SEMANTICS; "
                "alinhamento do registro pedido pelo coordenador)",
     "change": "quantitykind de BIT, BYTE e prefixos = quantitykind:AmountOfData (QUDT 3.5.3, "
               "qudt:unitForQuantityKind), igual a bo.units.rules e ao SEMANTICS (313e4d4); as escalares "
               "*_information mantêm o nome e mudam a grandeza declarada; teste contra bo.units.rules"},
    {"registry_version": "1.4.0", "commit_subject": "[TRANSFORMS] emenda 1.4.0: portas list/map do C10 3.1.0 (CC-6)",
     "request": "PILOT-STO-MAP CC-6, segunda parte: adoção do C10 3.1.0 (CONTRACTS emenda 8, 4abc6e3), que atendeu a "
                "proposta do CONTRACT_CHANGE.txt do TRANSFORMS",
     "change": "documento em contract_version 3.1.0; portas de elemento concreto viram list/map com item_type "
               "(tags_list_to_map, tags_map_to_list); portas polimórficas (wrap_list, map_list, list_to_set...) "
               "continuam tuple porque o value_type do C09 não tem 'any' para item_type (nova proposta no "
               "CONTRACT_CHANGE.txt)"},
    {"registry_version": "1.5.0", "commit_subject": "[TRANSFORMS] emenda 1.5.0: porta any do C10 3.2.0 e bytes do UNITS",
     "request": "adoção do C10 3.2.0 (CONTRACTS emenda 9, 2367bcd, item_type any pedido no CONTRACT_CHANGE.txt) e "
                "alinhamento com bo.units.rules pedido pelo coordenador (STO-MAP CC-5, continuação)",
     "change": "portas polimórficas de coleção (wrap_list, unwrap_single, list_to_set, set_to_list, map_list, map_set, "
               "map_values, map_get, compare_set_equal) saem list/set/map com item_type {datatype: any}; UnitType "
               "aceita a convenção vácua SI/IEC/NOT_APPLICABLE em BYTE e BIT sem prefixo (UNITS-BYTE-00, C05 3.1.0); "
               "teste contra bo.units.rules e bo.units.crosscheck (0 divergências)"},
]


def _yaml_text(doc: dict) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110, default_flow_style=False)


def _json_text(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def verify_inputs() -> list[str]:
    from bo.semantics import guards as S
    errs = []
    for tid, g, exp in GR.SAT_TESTS:
        m, s, b = M.satisfiable(g)[0], S.satisfiable(g)[0], M.brute_force(g)
        if not m == s == b == exp:
            errs.append(f"{tid}: esperado {exp}, TRANSFORMS {m}, SEMANTICS {s}, força bruta {b}")
    bad = [r for r in run_all() if not r["ok"]]
    errs += [f"exemplo {r['name']}[{r['i']}]: {r['detail']}" for r in bad]
    return errs


def registro() -> dict:
    items = []
    for t in R.SCALARS + R.COMBINATORS:
        items.append({"name": t.name, "kind": t.kind,
                      "signature": ({"domain": t.domain, "codomain": t.codomain} if t.kind == "scalar" else
                                    {"inputs": [p[0] for p in t.inputs], "outputs": [p[0] for p in t.outputs]}),
                      "loss": list(t.loss), "inverse": t.inverse, "partial": t.partial,
                      "error_codes": [c for c, _ in t.errors],
                      "examples": {"positive": sum(1 for e in t.examples if e.err is None and not e.roundtrip),
                                   "roundtrip": sum(1 for e in t.examples if e.roundtrip),
                                   "error": sum(1 for e in t.examples if e.err)},
                      **({"c11_comparator": t.c11_name} if getattr(t, "c11_name", None) else {})})
    return {"schema": "bo.transforms_index/1", "module": "TRANSFORMS", "registry_version": R.REGISTRY_VERSION,
            "generated_at": R.GENERATED_AT,
            "counts": {"scalar": len(R.SCALARS), "combinators": len(R.COMBINATORS),
                       "comparators": sum(1 for c in R.COMBINATORS if c.c11_name),
                       "examples": sum(len(t.examples) for t in R.REGISTRY.values()),
                       "sat_tests": len(GR.SAT_TESTS), "incompatible_pairs": len(GR.INCOMPATIBLE_PAIRS),
                       "compatible_pairs": len(GR.COMPATIBLE_PAIRS), "compositions": len(GR.COMPOSITIONS)},
            "units": [{"iri": u.iri, "quantity_kind": u.kind, "byte_convention": u.byte_convention,
                       "fixed_factor": u.factor is not None, "iri_status": "pattern_only"}
                      for u in __import__("bo.transforms.units", fromlist=["UNITS"]).UNITS.values()],
            "items": items, "findings": FINDINGS}


def _manifest_paths(root: Path) -> list[str]:
    paths = ["transforms/transforms.yaml", "transforms/conditions.grammar.json", "gates/TRANSFORMS.sh",
             "results/TRANSFORMS/registro.json", "results/TRANSFORMS/emendas.json"]
    paths += sorted(str(p.relative_to(root)) for p in (root / "src/bo/transforms").glob("*.py"))
    paths += sorted(str(p.relative_to(root)) for p in (root / "tests/transforms").glob("*.py"))
    if (root / "results/TRANSFORMS/summary.json").is_file():
        paths.append("results/TRANSFORMS/summary.json")
    return paths


def _manifest(root: Path, outputs: dict[str, str]) -> str:
    lines = []
    for rel in _manifest_paths(root):
        b = outputs[rel].encode("utf-8") if rel in outputs else (root / rel).read_bytes()
        lines.append(f"{hashlib.sha256(b).hexdigest()}  {rel}")
    return "\n".join(lines) + "\n"


def products(root: Path) -> dict[str, str]:
    out = {"transforms/transforms.yaml": _yaml_text(R.document()),
           "transforms/conditions.grammar.json": _json_text(GR.document()),
           "results/TRANSFORMS/registro.json": _json_text(registro())}
    out["results/TRANSFORMS/emendas.json"] = _json_text({"schema": "bo.transforms_amendments/1", "module": "TRANSFORMS",
                                                         "registry_version": R.REGISTRY_VERSION,
                                                         "generated_at": R.GENERATED_AT, "amendments": EMENDAS})
    out["results/TRANSFORMS/MANIFEST.sha256"] = _manifest(root, out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.transforms.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = C.repo()
    errs = verify_inputs()
    if errs:
        for e in errs:
            print(f"REPROVADO: {e}", file=sys.stderr)
        return 1
    prods = products(root)
    if yaml.safe_load(prods["transforms/transforms.yaml"]) != R.document():
        print("REPROVADO: o YAML gravado não relê igual ao documento", file=sys.stderr)
        return 1
    diff = [rel for rel, txt in prods.items()
            if not (root / rel).is_file() or (root / rel).read_text(encoding="utf-8") != txt]
    if a.check:
        if diff:
            for rel in diff:
                print(f"REPROVADO: {rel} difere do que o código produz", file=sys.stderr)
            return 1
        C.say(f"build --check: {len(prods)} arquivos idênticos ao que o código produz")
        return 0
    for rel, txt in prods.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    C.say(f"build: {len(prods)} arquivos gravados ({', '.join(diff) or 'nenhuma mudança'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
