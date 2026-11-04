"""Gera o ouro do GOLD-MODS a partir de $BO_DATA/HCL/symbolic_config.jsonl (C06), sem rede e sem nuvem.

  python -I -m bo.gold_mods.build              grava em $BO_DATA/GOLD-MODS/.staging/ e results/GOLD-MODS/
  python -I -m bo.gold_mods.build --promote    troca .staging -> $BO_DATA/GOLD-MODS/ (rodar dentro do lock)
  python -I -m bo.gold_mods.build --check      regenera em memória e confere byte a byte (fora o carimbo)

Saídas:
  $BO_DATA/GOLD-MODS/mods.sssom.tsv     C09 3.x: linhas D (1:1 entre provedores, pelo mesmo pivô var.<x> de
                                        variantes da mesma família) e G (grupo 1:N, N:1, N:M quando o pivô
                                        alimenta vários atributos e todo transporte é direto)
  $BO_DATA/GOLD-MODS/traces.jsonl       todo pivô seguido até o atributo, por par de variantes (evidência)
  $BO_DATA/GOLD-MODS/resolution.json    contagens de resolução (lidas pelo bo.gold_mods.resolve)
  $BO_REPO/results/GOLD-MODS/families.json  famílias, variantes, pares, regras e números (com carimbo)

Regras de linha (declaradas antes de olhar os números, salvo L3b, marcada):
  L1  nível DERIVADO em toda linha (proof.evidence[].level = derived; curation_rule); nada de exactMatch;
  L2  close só quando, em pelo menos um par de variantes, a variável é o valor inteiro dos DOIS atributos
      (ops == ()): função identity com perda semântica declarada; senão related (sem função, fidelidade none);
  L3  pivô que alimenta mais de um atributo num lado vira grupo (1:N, N:1, N:M) se todo transporte do pivô é
      direto nos dois lados; se algum é expressão, o grupo é desdobrado em pares (mapping_cardinality anota);
  L3b (acrescentada DEPOIS da 1ª rodada completa) par desdobrado de um pivô N:M com expressão (os dois lados
      com vários atributos, ex. var.name em todo nome de recurso) não é identificado pela variável: a linha
      sai, mas UNRESOLVED (motivo 'nm_unfolded') se TODAS as instâncias que a sustentam são desse tipo. Na 1ª
      rodada eram 3 181 das 3 678 linhas, todas STRUCTURALLY_VALID;
  L4  só atributos (meta-argumentos, for_each de dynamic e caminhos com chave simbólica ficam no traces.jsonl);
  L5  evidence_state STRUCTURALLY_VALID quando os dois lados (todos, no grupo) são átomos bem formados E
      atestados no corpus fora das famílias que sustentam a linha (>= 1 outra família do C06 usa o átomo);
      senão UNRESOLVED. Existência no schema do provider fixado NÃO é conferida aqui (SCHEMA-* não é entrada
      do módulo): fica para o GOLD-AUDIT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bo.contracts import sssom as CSSSOM

from . import scan as S
from .paths import (ID, data_dir, licenses_path, now_iso, results_dir, sha256_file, staging_dir, symbolic_config,
                    symbolic_index)

PROVIDERS = S.PROVIDERS
MAPPING_SET_ID = "https://w3id.org/brevops/gold/modules"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"   # TerraDS (Zenodo 10.5281/zenodo.20339474)
PREFIXES = {
    "aws": "https://w3id.org/brevops/atom/aws/", "google": "https://w3id.org/brevops/atom/google/",
    "azurerm": "https://w3id.org/brevops/atom/azurerm/", "oci": "https://w3id.org/brevops/atom/oci/",
    "skos": "http://www.w3.org/2004/02/skos/core#", "semapv": "https://w3id.org/semapv/vocab/",
    "bosx": "https://w3id.org/brevops/sssom-ext#", "bo": "https://w3id.org/brevops/ontology#",
    "concept": "https://w3id.org/brevops/glossary#",
}
LEVEL_RULE = "GOLD-MODS:nivel=DERIVADO"
SEMANTIC_LOSS = {"kind": "semantic",
                 "note": "família de módulos: o mantenedor passou a mesma variável aos dois atributos; isso não "
                         "prova o mesmo significado nem o mesmo domínio (nível DERIVADO)"}
IDENTITY = {"name": "identity", "params": {}}
MANIFEST_DATA = ("mods.sssom.tsv", "traces.jsonl", "resolution.json")


def short(s: str, n: int = 10) -> str:
    """Hex determinístico que termina em letra e nunca tem 12 dígitos seguidos (o privacy_lint leria como id de
    conta), mesmo encostado em dígitos vizinhos."""
    k = 0
    while True:
        h = hashlib.sha256(f"{s}#{k}".encode() if k else s.encode()).hexdigest()[:n]
        if h[-1] in "abcdef" and h[0] in "abcdef" and not re.search(r"\d{12}", h):
            return h
        k += 1


def atom_id(provider: str, u: dict) -> str:
    return f"{provider}:{u['resource_type']}:{u['atom']}"


def corpus_key(aid: str) -> str:
    return aid.split(":", 1)[1]


EV_PAIRS_IN_ROW = 8   # pares de variantes com evidência na própria linha (o resto está no traces.jsonl)


def ev_item(rid: str, provider: str, u: dict, pivot: str, fam: str, d: str) -> dict:
    """Ocorrência: ref = terrads:<repo_id>:<arquivo>#<endereço>/<attr_path> (tudo já simbolizado no C06)."""
    return {"level": "derived", "ref": f"terrads:{rid}:{u['file']}#{u['address']}/{u['attr_path']}",
            "pivot": pivot, "mode": u["mode"], "family": fam, "atom": atom_id(provider, u)}


def parse_ref(ref: str):
    """terrads:R-x:arquivo#endereço/attr_path -> (repo_id, arquivo, endereço, attr_path)."""
    _, rid, rest = ref.split(":", 2)
    file, tail = rest.split("#", 1)
    addr, apath = tail.split("/", 1)
    return rid, file, addr, apath


def _licenses() -> dict:
    d = json.loads(licenses_path().read_text(encoding="utf-8"))
    return {r["repo_id"]: r["license"] for r in d["repos"]}


# -------------------------------------------------------------------------------------------- famílias
def select_repos(res):
    """V5: um repositório por family_id do C06 (o de menor repo_id); cópias contadas."""
    copies = Counter(r["family_id"] for r in res if r["pairs"])
    kept, seen = [], set()
    for r in res:
        if not r["pairs"] or r["family_id"] in seen:
            continue
        seen.add(r["family_id"])
        kept.append(r)
    return kept, copies


def fam_key(rid: str, dirs) -> str:
    return "FAM-" + short(rid + "|" + "|".join(sorted(dirs)), 12)


def side_atoms(provider, uses):
    """{átomo: {"modes": {...}, "first": uso}} só de atributos; e contagem do resto por categoria."""
    out, rest = {}, Counter()
    for u in uses:
        if u["category"] != "attribute":
            rest[u["category"]] += 1
            continue
        aid = atom_id(provider, u)
        e = out.setdefault(aid, {"modes": set(), "first": u, "n": 0})
        e["modes"].add(u["mode"])
        e["n"] += 1
    return out, rest


def all_identity(side):
    return all(v["modes"] == {"identity"} for v in side.values())


# -------------------------------------------------------------------------------------------- linhas
class Acc:
    def __init__(self, kind, sids, oids, p1, p2):
        self.kind, self.sids, self.oids, self.p1, self.p2 = kind, sids, oids, p1, p2
        self.ev_by_pair: dict = {}
        self.pairs, self.repos, self.c06_families, self.licenses = set(), set(), set(), set()
        self.inst = Counter()        # identity_both | expr | unfolded
        self.pivots = 0

    def add_ev(self, pid, items):
        cur = self.ev_by_pair.setdefault(pid, [])
        for it in items:
            if it not in cur:
                cur.append(it)

    def evidence(self):
        out = []
        for pid in sorted(self.ev_by_pair)[:EV_PAIRS_IN_ROW]:
            out.extend(self.ev_by_pair[pid])
        return out


def collect(kept, lic):
    d_acc: dict = {}
    g_acc: dict = {}
    traces, tstats = [], Counter()
    fam_out = []
    for r in kept:
        rid = r["repo_id"]
        comps = r["families"]
        fam_of = {d: fam_key(rid, c) for c in comps for d in c}
        fam_pairs = defaultdict(list)
        for p in r["pairs"]:
            fk = fam_of[p["dir_a"]]
            pid = f"{fk}:{short(p['dir_a'] + '|' + p['dir_b'], 8)}"
            pa, pb = p["provider_a"], p["provider_b"]
            claims = set()
            n_piv = 0
            for piv, f in sorted(p["feeds"].items()):
                A, ra = side_atoms(pa, f["a"])
                B, rb = side_atoms(pb, f["b"])
                tstats.update({f"a:{k}": v for k, v in ra.items()})
                tstats.update({f"b:{k}": v for k, v in rb.items()})
                rows_here = []
                if A and B:
                    n_piv += 1
                    rows_here = _emit(d_acc, g_acc, A, B, pa, pb, piv, pid, rid, r["family_id"], fk, p, lic)
                    claims.update(rows_here)
                else:
                    tstats["pivot_without_attribute_on_a_side"] += 1
                traces.append({"family": fk, "pair": pid, "repo_id": rid, "dir_a": p["dir_a"], "dir_b": p["dir_b"],
                               "provider_a": pa, "provider_b": pb, "pivot": piv,
                               "a": f["a"], "b": f["b"], "claims": sorted(rows_here)})
            fam_pairs[fk].append({"pair": pid, "dir_a": p["dir_a"], "dir_b": p["dir_b"], "provider_a": pa,
                                  "provider_b": pb, "n_vars_a": p["n_vars_a"], "n_vars_b": p["n_vars_b"],
                                  "n_shared": p["n_shared"], "jaccard": p["jaccard"],
                                  "equal_interface": p["equal_interface"],
                                  "common_dir_depth": p["common_dir_depth"], "pivots_traced": len(p["feeds"]),
                                  "pivots_with_rows": n_piv, "n_claims": len(claims)})
        for c in comps:
            fk = fam_of[c[0]]
            fam_out.append({"family": fk, "repo_id": rid, "c06_family_id": r["family_id"],
                            "license": lic.get(rid, "UNKNOWN"),
                            "variants": [{"dir": d, "provider": r["variants"][d]} for d in c],
                            "providers": sorted({r["variants"][d] for d in c}, key=PROVIDERS.index),
                            "pairs": fam_pairs[fk]})
    return d_acc, g_acc, traces, tstats, fam_out


def _emit(d_acc, g_acc, A, B, pa, pb, piv, pid, rid, c06f, fk, p, lic):
    def ev_for(side, prov, d, ids):
        return [ev_item(rid, prov, side[i]["first"], piv, fk, d) for i in ids]

    out = []
    sids, oids = sorted(A), sorted(B)
    ident = all_identity(A) and all_identity(B)
    if len(sids) == 1 and len(oids) == 1:
        units = [((sids[0], oids[0]), "D", ident, False)]
    elif ident:
        units = [((tuple(sids), tuple(oids)), "G", True, False)]
    else:
        units = [((s, o), "D", A[s]["modes"] == {"identity"} and B[o]["modes"] == {"identity"}, True)
                 for s in sids for o in oids]
    for key, kind, idn, unfolded in units:
        accs = d_acc if kind == "D" else g_acc
        acc = accs.get(key)
        if acc is None:
            ks = (key[0],) if kind == "D" else key[0]
            ko = (key[1],) if kind == "D" else key[1]
            acc = accs[key] = Acc(kind, list(ks), list(ko), pa, pb)
        acc.pairs.add(pid)
        acc.repos.add(rid)
        acc.c06_families.add(c06f)
        acc.licenses.add(lic.get(rid, "UNKNOWN"))
        acc.pivots += 1
        acc.inst["identity_both" if idn else "expr"] += 1
        if unfolded:
            acc.inst[f"unfolded_from_{_card(len(sids), len(oids))}"] += 1
        acc.add_ev(pid, ev_for(A, pa, p["dir_a"], acc.sids) + ev_for(B, pb, p["dir_b"], acc.oids))
        out.append(claim_id(acc))
    return out


def _card(n, m):
    return "1:1" if n == m == 1 else "1:N" if n == 1 else "N:1" if m == 1 else "N:M"


def claim_id(acc) -> str:
    if acc.kind == "D":
        return f"MOD-D-{acc.p1}-{acc.p2}-{short(acc.sids[0] + '|' + acc.oids[0])}"
    return f"MOD-G-{acc.p1}-{acc.p2}-{short('+'.join(acc.sids) + '|' + '+'.join(acc.oids))}"


def state_of(acc, atom_fams):
    """-> (estado, contagem fora do suporte por átomo, motivos de UNRESOLVED)."""
    sup = len(acc.c06_families)
    outside = {a: atom_fams.get(corpus_key(a), 0) - sup for a in acc.sids + acc.oids}
    why = []
    if not all(v >= 1 for v in outside.values()):
        why.append("atom_not_attested_outside_support")
    if acc.kind == "D" and acc.inst["unfolded_from_N:M"] == acc.pivots:
        why.append("nm_unfolded")
    return ("UNRESOLVED" if why else "STRUCTURALLY_VALID"), outside, why


def to_row(acc, atom_fams):
    cid = claim_id(acc)
    state, outside, why = state_of(acc, atom_fams)
    close = acc.inst["identity_both"] > 0 if acc.kind == "D" else True
    lic = sorted(acc.licenses)
    other = {"support_variant_pairs": len(acc.pairs), "support_repos": len(acc.repos),
             "support_c06_families": len(acc.c06_families), "pivot_instances": acc.pivots,
             "instances": dict(sorted(acc.inst.items())), "licenses": lic,
             "corpus_families_outside_support": dict(sorted(outside.items())),
             "subject_atoms": acc.sids, "object_atoms": acc.oids,
             "unresolved_reasons": why,
             "evidence_pairs_in_row": min(len(acc.ev_by_pair), EV_PAIRS_IN_ROW),
             "evidence_pairs_total": len(acc.ev_by_pair), "full_trace": "$BO_DATA/GOLD-MODS/traces.jsonl"}
    r = {"claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
         "subject_id": acc.sids[0], "object_id": acc.oids[0],
         "predicate_id": "skos:closeMatch" if close else "skos:relatedMatch",
         "semantic_relation": "close" if close else "related", "mapping_justification": "semapv:MappingChaining",
         "value_domain_relation": {"orientation": "subject_to_object", "relation": "unknown"},
         "transport_fidelity": "declared_loss" if close else "none", "guard": {"all": []},
         "translation_fn": IDENTITY if (close and acc.kind == "D") else None,
         "loss_contract": [SEMANTIC_LOSS] if close else [],
         "proof": {"type": "module_family_variable_trace", "evidence": acc.evidence(), "tests": []},
         "evidence_state": state, "basis": "composition", "subject_concept": "bo:UNGLOSSED",
         "object_concept": "bo:UNGLOSSED", "curation_rule": LEVEL_RULE,
         "curation_rule_text": "variáveis comuns de variantes por provedor de uma família de módulos; nível "
                               "DERIVADO, nunca prova de equivalência",
         "mapping_tool": "bo.gold_mods.build", "subject_category": "terraform_attribute",
         "object_category": "terraform_attribute",
         "author_label": f"TerraDS: {len(acc.repos)} repositório(s) anonimizado(s)",
         "comment": f"derivado: {acc.p1} e {acc.p2} recebem a mesma variável numa família de módulos do mesmo "
                    f"mantenedor; não prova equivalência"}
    if len(lic) == 1 and lic[0] != "UNKNOWN":
        r["license"] = f"https://spdx.org/licenses/{lic[0]}.html"
    if acc.kind == "D":
        unf = [k for k in acc.inst if k.startswith("unfolded_from_")]
        r["mapping_cardinality"] = "1:1" if not unf else "1:1 (desdobrado de " + \
            ", ".join(sorted(k.split("_")[-1] for k in unf)) + ")"
    else:
        gid = f"GRP-MOD-{short('+'.join(acc.sids) + '|' + '+'.join(acc.oids), 12)}"
        sv = [{"name": f"?s{i + 1}", "side": "subject", "field": x, "occurrence": f"?rs{i + 1}"}
              for i, x in enumerate(acc.sids)]
        ov = [{"name": f"?o{j + 1}", "side": "object", "field": x, "occurrence": f"?ro{j + 1}"}
              for j, x in enumerate(acc.oids)]
        steps = [{"name": "identity", "inputs": {"value": f"?s{i + 1}"}, "outputs": {"value": f"?o{j + 1}"}}
                 for i in range(len(acc.sids)) for j in range(len(acc.oids))]
        card = _card(len(acc.sids), len(acc.oids))
        r.update(bo_group_id=gid, mapping_cardinality=card,
                 group={"bo_group_id": gid, "cardinality": card, "variables": sv + ov,
                        "occurrence_vars": [v["occurrence"] for v in sv + ov], "joins": [], "steps": steps})
    r["other"] = json.dumps(other, ensure_ascii=False, sort_keys=True)
    return r


# ---------------------------------------------------------------------------------------------- build
def compute(workers=14, cache=False):
    """cache=True (só desenvolvimento) reaproveita a varredura em $BO_TMP/scan.pickle; gates nunca usam."""
    import pickle
    from .paths import tmp_dir
    cp = tmp_dir() / "scan.pickle"
    if cache and cp.is_file():
        res, atom_fams = pickle.loads(cp.read_bytes())
    else:
        res, atom_fams = S.scan(workers)
        if cache:
            cp.write_bytes(pickle.dumps((res, atom_fams)))
    lic = _licenses()
    kept, copies = select_repos(res)
    d_acc, g_acc, traces, tstats, fams = collect(kept, lic)
    rows = sorted((to_row(a, atom_fams) for a in d_acc.values()), key=lambda r: r["claim_id"]) + \
        sorted((to_row(a, atom_fams) for a in g_acc.values()), key=lambda r: r["claim_id"])
    return {"res": res, "atom_fams": atom_fams, "kept": kept, "copies": copies, "rows": rows, "traces": traces,
            "tstats": tstats, "families": fams}


def inputs_record():
    return [{"path": "$BO_DATA/HCL/" + p.name, "kind": "file", "sha256": sha256_file(p)}
            for p in (symbolic_config(), symbolic_index(), licenses_path())]


def resolution_report(c):
    rows = c["rows"]
    st = Counter(r["evidence_state"] for r in rows)
    unres = [r["claim_id"] for r in rows if r["evidence_state"] == "UNRESOLVED"]
    why = Counter(w for r in rows for w in json.loads(r["other"])["unresolved_reasons"])
    atoms = sorted({a for r in rows for a in json.loads(r["other"])["subject_atoms"] +
                    json.loads(r["other"])["object_atoms"]})
    return {"schema": "bo.gold_mods.resolution/1", "rows": len(rows), "by_state": dict(sorted(st.items())),
            "unresolved_rows": unres, "unresolved_reasons": dict(sorted(why.items())),
            "atoms": {a: c["atom_fams"].get(corpus_key(a), 0) for a in atoms},
            "trace_categories": dict(sorted(c["tstats"].items())),
            "rule": "lado resolve quando o átomo é bem formado e atestado no C06 fora das famílias que sustentam "
                    "a linha (>= 1); par só desdobrado de pivô N:M não resolve o par (nm_unfolded); senão a linha é "
                    "STRUCTURALLY_VALID. Schema do provider fixado: GOLD-AUDIT."}


def families_report(c, inputs):
    rows, fams, res = c["rows"], c["families"], c["res"]
    kinds = Counter(r["claim_id"].split("-")[1] for r in rows)
    rel = Counter(f"{r['claim_id'].split('-')[1]}:{r['semantic_relation']}" for r in rows)
    st = Counter(r["evidence_state"] for r in rows)
    pp = Counter("-".join(r["claim_id"].split("-")[2:4]) for r in rows)
    gcard = Counter(r["mapping_cardinality"] for r in rows if r["claim_id"].startswith("MOD-G-"))
    dcard = Counter(r["mapping_cardinality"] for r in rows if r["claim_id"].startswith("MOD-D-"))
    sup = Counter(min(json.loads(r["other"])["support_repos"], 5) for r in rows)
    pairs = [p for f in fams for p in f["pairs"]]
    top = sorted(rows, key=lambda r: (-json.loads(r["other"])["support_repos"], r["claim_id"]))[:25]
    stats = {
        "repos_scanned": len(res),
        "repos_with_variants_of_2plus_providers": sum(1 for r in res if r["multi_provider_variants"]),
        "repos_with_pairs_before_dedupe": sum(1 for r in res if r["pairs"]),
        "repos_with_families": len(c["kept"]),
        "c06_copies_skipped": sum(v - 1 for v in c["copies"].values()),
        "threshold_pairs_V3": sum(r["n_threshold_pairs"] for r in c["kept"]),
        "variant_pairs_V3b": len(pairs),
        "families": len(fams),
        "family_size": dict(sorted(Counter(str(len(f["variants"])) for f in fams).items())),
        "families_by_providers": dict(sorted(Counter("+".join(f["providers"]) for f in fams).items())),
        "pairs_by_providers": dict(sorted(Counter(f"{p['provider_a']}-{p['provider_b']}" for p in pairs).items())),
        "pairs_equal_interface": sum(1 for p in pairs if p["equal_interface"]),
        "pairs_without_rows": sum(1 for p in pairs if not p["n_claims"]),
        "pivots_traced": len(c["traces"]),
        "pivots_with_rows": sum(1 for t in c["traces"] if t["claims"]),
        "rows": dict(sorted(kinds.items())), "rows_by_relation": dict(sorted(rel.items())),
        "rows_by_evidence_state": dict(sorted(st.items())), "rows_by_provider_pair": dict(sorted(pp.items())),
        "group_cardinality": dict(sorted(gcard.items())), "d_cardinality": dict(sorted(dcard.items())),
        "rows_by_support_repos_capped5": {str(k): v for k, v in sorted(sup.items())},
        "top_support": [{"claim_id": r["claim_id"], "subject_id": r["subject_id"], "object_id": r["object_id"],
                         "semantic_relation": r["semantic_relation"],
                         "support_repos": json.loads(r["other"])["support_repos"]} for r in top],
    }
    return {"schema": "bo.gold_mods.families/1", "module": ID, "generated_at": now_iso(),
            "level": "DERIVADO em todas as linhas: família de módulos não prova equivalência",
            "rules": {"variants": S.PARAMS, "text": S.__doc__.split("Regras", 1)[1].strip(),
                      "rows": __doc__.split("Regras de linha", 1)[1].strip()},
            "inputs": inputs, "stats": stats,
            "row_kinds": {"D": "1:1 entre provedores pelo mesmo pivô", "G": "grupo 1:N, N:1 ou N:M (transporte direto)"},
            "limits": ["símbolos do C06 são por repositório: família espalhada em vários repositórios do mesmo dono "
                       "não é detectável", "declaração de variável e chamada de módulo não estão no C06: a interface "
                       "é o conjunto de variáveis que chegam a atributos", "átomo não conferido no schema do "
                       "provider fixado (GOLD-AUDIT)", "silêncio do ouro não é negativo"],
            "families": fams}


def outputs(workers=14, cache=False):
    c = compute(workers, cache)
    tsv = CSSSOM.write_tsv(c["rows"], MAPPING_SET_ID, PREFIXES)
    tsv = tsv.replace(f"# license: {CSSSOM.SIO.LICENSE}\n", f"# license: {LICENSE}\n")
    traces = "".join(json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n" for t in c["traces"])
    res = resolution_report(c)
    fam = families_report(c, inputs_record())
    files = {"mods.sssom.tsv": tsv, "traces.jsonl": traces,
             "resolution.json": json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n"}
    return files, fam


def _strip_ts(t: str) -> str:
    d = json.loads(t)
    d.pop("generated_at", None)
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def write_manifest(ddir: Path, rdir: Path):
    """results/GOLD-MODS/MANIFEST.sha256 (C17): saídas em $BO_DATA (caminho portátil) e families.json."""
    lines = [(sha256_file(ddir / n), f"$BO_DATA/{ID}/{n}") for n in MANIFEST_DATA]
    lines.append((sha256_file(rdir / "families.json"), f"results/{ID}/families.json"))
    (rdir / "MANIFEST.sha256").write_text("".join(f"{h}  {p}\n" for h, p in lines), encoding="utf-8")


def promote() -> int:
    """.staging -> $BO_DATA/GOLD-MODS (troca atômica por arquivo; chamar dentro de tools/lock.sh)."""
    st, dd = staging_dir(), data_dir()
    missing = [n for n in MANIFEST_DATA if not (st / n).is_file()]
    if missing:
        print("promote: faltam em .staging:", *missing)
        return 1
    for n in MANIFEST_DATA:
        os.replace(st / n, dd / n)
    shutil.rmtree(st, ignore_errors=True)
    write_manifest(dd, results_dir())
    print(f"[{now_iso()}] promote: {len(MANIFEST_DATA)} arquivo(s) em {dd}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.gold_mods.build")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--dev-cache", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.promote:
        return promote()
    files, fam = outputs(a.workers, a.dev_cache and not a.check)
    if a.check:
        bad = []
        for n, t in files.items():
            p = data_dir() / n
            if not p.exists() or p.read_text(encoding="utf-8") != t:
                bad.append(str(p))
        p = results_dir() / "families.json"
        if not p.exists() or _strip_ts(p.read_text(encoding="utf-8")) != _strip_ts(json.dumps(fam, ensure_ascii=False)):
            bad.append(str(p))
        if bad:
            print("regeneração diverge:", *bad, sep="\n  ")
            return 1
        print(f"[{now_iso()}] build --check: {len(files) + 1} arquivo(s) idênticos à regeneração")
        return 0
    st = staging_dir()
    st.mkdir(parents=True, exist_ok=True)
    for n, t in files.items():
        (st / n).write_text(t, encoding="utf-8")
    rd = results_dir()
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "families.json").write_text(json.dumps(fam, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    s = fam["stats"]
    print(f"[{now_iso()}] build: {s['families']} famílias, {s['variant_pairs_V3b']} pares, linhas {s['rows']}, "
          f"estados {s['rows_by_evidence_state']} -> {st} (promover dentro do lock)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
