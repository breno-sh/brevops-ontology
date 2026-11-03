"""Higiene do ROLES: a mesma regra nos 4 provedores e nenhuma regra cita provedor.

  python -I -m bo.roles.symmetry     sai 0 só se tudo abaixo vale; relatório em $BO_DATA/ROLES/symmetry_report.json

Confere:
  1. rules.yaml é coerente (papéis do C04, condições do vocabulário fechado, léxicos existentes, padrão no fim)
     e nenhuma regra tem escopo: as chaves de regra são só id, role, text e when.
  2. Nenhum nome de provedor (os do campo provider dos átomos e os nomes das empresas) aparece como palavra
     em rules.yaml nem no código que classifica (engine.py, build.py).
  3. Entrada simétrica: os 4 provedores têm átomos e fatos de documentação carregados.
  4. Permutação e renomeação: girar os rótulos de provedor entre os 4 e trocá-los por rótulos neutros não muda
     nenhum papel, regra nem evidência de nenhum átomo (o provedor só entra como dado).
  5. roles.jsonl gravado tem um papel por átomo e é o que as regras dão hoje.
Achado (não reprova): regras que disparam em menos de 4 provedores, com a contagem por provedor.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from . import build, engine

# nomes das empresas e marcas, além dos rótulos de provedor que vêm dos próprios átomos
VENDOR_NAMES = ("amazon", "aws", "google", "gcp", "azure", "azurerm", "microsoft", "oracle", "oci")
RULE_KEYS = {"id", "role", "text", "when"}
TOP_KEYS = {"schema", "version", "contract", "contract_version", "normalize", "lexicons", "format_classes",
            "patterns", "rules"}
CODE_FILES = ("engine.py", "build.py")


def word_hits(text: str, terms: set[str]) -> list[str]:
    out = []
    for t in sorted(terms):
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])", text, re.I):
            out.append(t)
    return out


def relabel(atoms: list[dict], facts: dict[str, list[dict]], mapping: dict[str, str]):
    """Troca o rótulo de provedor no átomo (provider, prefixo do resource_type, atom_id) e nas chaves dos fatos."""
    def new_id(aid: str) -> str:
        prov, rt, path = aid.split(":", 2)
        m = mapping[prov]
        rt2 = m + rt[len(prov):] if rt.startswith(prov + "_") else rt
        return f"{m}:{rt2}:{path}"

    back = {}
    out_atoms = []
    for a in atoms:
        b = dict(a)
        p = a["provider"]
        b["provider"] = mapping[p]
        rt = a["resource_type"]
        b["resource_type"] = mapping[p] + rt[len(p):] if rt.startswith(p + "_") else rt
        b["atom_id"] = new_id(a["atom_id"])
        back[b["atom_id"]] = a["atom_id"]
        out_atoms.append(b)
    out_facts = {new_id(k): v for k, v in facts.items() if k.split(":", 1)[0] in mapping}
    return out_atoms, out_facts, back


def comparable(recs, back=None) -> dict[str, tuple]:
    out = {}
    for r, _ in recs:
        aid = back[r["atom_id"]] if back else r["atom_id"]
        out[aid] = (r["role"], r["rule_id"], json.dumps(r.get("evidence", []), sort_keys=True))
    return out


def main(argv=None) -> int:
    report = {"module": build.MODULE, "generated_at": build.now(), "checks": {}, "findings": {}}
    fails = []

    def check(name, ok, detail):
        report["checks"][name] = {"ok": bool(ok), "detail": detail}
        print(("  OK   " if ok else "  FAIL ") + f"{name}: {detail}")
        if not ok:
            fails.append(name)

    print(f"[{build.now()}] bo.roles.symmetry")
    rules, atoms, facts, inputs = build.load_everything()
    raw = rules.raw
    bad_top = sorted(set(raw) - TOP_KEYS)
    bad_rule = sorted({f"{r.get('id')}:{k}" for r in raw["rules"] for k in r if k not in RULE_KEYS})
    check("regras_coerentes", not engine.validate(rules) and not bad_top and not bad_rule,
          f"{len(rules.rules)} regras; chaves extras no topo {bad_top or 'nenhuma'}; "
          f"chaves fora de id/role/text/when {bad_rule or 'nenhuma'}")

    providers = sorted({a["provider"] for a in atoms})
    banned = set(VENDOR_NAMES) | set(providers)
    hits = {}
    texts = {"roles/rules.yaml": rules.path.read_text(encoding="utf-8")}
    here = Path(engine.__file__).parent
    for f in CODE_FILES:
        texts[f"src/bo/roles/{f}"] = (here / f).read_text(encoding="utf-8")
    for name, txt in texts.items():
        h = word_hits(txt, banned)
        if h:
            hits[name] = h
    check("sem_nome_de_provedor", not hits,
          f"{len(banned)} termos proibidos procurados em {len(texts)} arquivos; achados {hits or 'nenhum'}")

    n_atoms = Counter(a["provider"] for a in atoms)
    n_docs = Counter(k.split(":", 1)[0] for k in facts)
    sym_in = len(providers) == 4 and all(n_atoms[p] > 0 and n_docs[p] > 0 for p in providers)
    check("entrada_simetrica", sym_in,
          "átomos " + json.dumps(dict(sorted(n_atoms.items()))) + "; átomos com fatos de docs "
          + json.dumps(dict(sorted(n_docs.items()))))

    base = build.classify_all(atoms, facts, rules)
    ref = comparable(base)
    rot = {p: providers[(i + 1) % len(providers)] for i, p in enumerate(providers)}
    neutral = {p: f"prov{i}" for i, p in enumerate(providers)}
    for label, mapping in (("permutacao", rot), ("renomeacao", neutral)):
        a2, f2, back = relabel(atoms, facts, mapping)
        got = comparable(build.classify_all(a2, f2, rules), back)
        diff = [k for k in ref if got.get(k) != ref[k]]
        check(f"invariancia_{label}", not diff and len(got) == len(ref),
              f"{len(ref)} átomos reclassificados com rótulos trocados ({json.dumps(mapping)}); "
              f"{len(diff)} diferem" + (f", ex. {diff[:3]}" if diff else ""))

    blob = build.serialize(base)
    on_disk = build.out_path()
    same = on_disk.exists() and on_disk.read_bytes() == blob
    check("roles_jsonl_atual", same and not build.completeness(base, atoms),
          f"{on_disk} {'confere com' if same else 'DIFERE de'} as regras de hoje; "
          f"{len(base)} papéis para {len(atoms)} átomos")

    fire = {r.id: Counter() for r in rules.rules}
    for r, x in base:
        fire[r["rule_id"]][x.provider] += 1
    partial = {rid: {p: c[p] for p in providers} for rid, c in fire.items() if 0 < len(c) < len(providers)}
    never = [rid for rid, c in fire.items() if not c]
    report["findings"] = {"rules_firing_in_fewer_than_all_providers": partial, "rules_never_firing": never,
                          "rule_firings": {rid: {p: c[p] for p in providers} for rid, c in fire.items()}}
    print(f"  achado: {len(partial)} regra(s) disparam em menos de {len(providers)} provedores: "
          + ", ".join(f"{k} {json.dumps(v)}" for k, v in partial.items()))
    if never:
        print(f"  achado: {len(never)} regra(s) nunca disparam: {', '.join(never)}")
    report["result"] = "FAIL" if fails else "PASS"
    out = build.bo_data() / build.MODULE / "symmetry_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RESULTADO: {'REPROVADO (' + ', '.join(fails) + ')' if fails else 'APROVADO'}  ({out})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
