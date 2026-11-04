"""Gate de resolução do GOLD-MODS: toda linha nasce de variáveis seguidas até atributos no C06, e o estado de
evidência é o que a regra dá.

  python -I -m bo.gold_mods.resolve GOLD-MODS

Confere, relendo $BO_DATA/HCL/symbolic_config.jsonl (pelo índice de bytes) e recalculando a varredura:
  R1  toda evidência de toda linha (ref terrads:<repo>:<arquivo>#<endereço>/<attr_path>) existe no C06: há um
      registro com esse repositório, arquivo, endereço e attr_path cujo termo contém o pivô com o mesmo modo
      (identity|expr), e o attr_path normaliza para o átomo declarado;
  R2  todo átomo de toda linha (os dois lados; todos os do grupo) tem evidência na própria linha, e todo átomo
      evidenciado é um dos átomos da linha, no lado do seu provedor;
  R3  evidence_state = regra L5/L3b: atestação no corpus recalculada (nº de famílias C06 por átomo) bate com
      resolution.json, e STRUCTURALLY_VALID <=> sem motivo de UNRESOLVED; nada DOC_SUPPORTED ou acima;
  R4  nível DERIVADO: nenhuma exactMatch; toda evidência level=derived; curation_rule do módulo; close <=>
      declared_loss com perda semântica; related <=> fidelidade none, sem função;
  R5  toda linha é citada por algum pivô do traces.jsonl e todo pivô cita só linhas que existem;
  R6  grupo: variáveis = átomos da linha, cardinalidade = contagem por lado, passos identity entre lados;
  R7  todo par de variantes do families.json obedece V1-V3 (provedores diferentes, |interseção| >= 2,
      Jaccard >= 0,5) e toda família tem >= 2 provedores.
Sai 0 se tudo confere; 1 com a lista de falhas.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

from bo.contracts import sssom as CSSSOM

from . import build as B
from . import scan as S
from . import terms
from .paths import ID, data_dir, now_iso, results_dir, symbolic_config, symbolic_index

ATOM_RX = __import__("re").compile(r"^(aws|google|azurerm|oci):[a-z][a-z0-9_]*:[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")


def _records_for(refs):
    """{(repo, arquivo, endereço, attr_path): [termo, ...]} lendo só os repositórios citados."""
    index = json.loads(symbolic_index().read_text(encoding="utf-8"))["repos"]
    want = defaultdict(set)
    for rid, f, a, p in refs:
        want[rid].add((f, a, p))
    out = defaultdict(list)
    missing_repo = []
    with open(symbolic_config(), "rb") as fh:
        for rid in sorted(want):
            if rid not in index:
                missing_repo.append(rid)
                continue
            s, e, _n = index[rid]
            fh.seek(s)
            for raw in fh.read(e - s).split(b"\n"):
                if not raw.strip():
                    continue
                rec = json.loads(raw)
                k = (rec["file"], rec["resource_address"], rec["attr_path"])
                if k in want[rid]:
                    out[(rid,) + k].append(rec["term"])
    return out, missing_repo


def check(ddir=None, rdir=None, atom_fams=None):
    """ddir/rdir: pastas de dados e de resultados (padrão: as do módulo). atom_fams: contagem já calculada
    (só nos testes de mutação; o gate sempre recalcula a varredura)."""
    ddir, rdir = ddir or data_dir(), rdir or results_dir()
    fails = []
    text = (ddir / "mods.sssom.tsv").read_text(encoding="utf-8")
    meta, rows, _cols = CSSSOM.read_tsv(text)
    res = json.loads((ddir / "resolution.json").read_text(encoding="utf-8"))
    fam = json.loads((rdir / "families.json").read_text(encoding="utf-8"))
    traces = [json.loads(l) for l in (ddir / "traces.jsonl").read_text(encoding="utf-8").splitlines() if l]
    by_id = {r["claim_id"]: r for r in rows}
    if len(by_id) != len(rows):
        fails.append("R5 claim_id repetido no SSSOM")

    # ---------------------------------------------------------------- R1/R2
    refs = []
    for r in rows:
        for ev in r["proof"].get("evidence", []):
            refs.append(B.parse_ref(ev["ref"]))
    recs, missing = _records_for(set(refs))
    for rid in missing:
        fails.append(f"R1 repositório {rid} citado não está no índice do C06")
    n_ev = 0
    for r in rows:
        o = json.loads(r["other"])
        sa, oa = set(o["subject_atoms"]), set(o["object_atoms"])
        if r["subject_id"] not in sa or r["object_id"] not in oa:
            fails.append(f"R2 {r['claim_id']}: subject_id/object_id fora dos átomos da linha")
        seen_atoms = set()
        sp, op = r["subject_id"].split(":", 1)[0], r["object_id"].split(":", 1)[0]
        for ev in r["proof"].get("evidence", []):
            n_ev += 1
            if ev.get("level") != "derived":
                fails.append(f"R4 {r['claim_id']}: evidência com level {ev.get('level')!r}")
            key = B.parse_ref(ev["ref"])
            terms_here = recs.get(key)
            if not terms_here:
                fails.append(f"R1 {r['claim_id']}: {ev['ref']} não existe no C06")
                continue
            ok = any((ev["pivot"], ev["mode"]) in {(p, terms.mode_of(ops)) for p, ops in terms.var_uses(t)}
                     for t in terms_here)
            if not ok:
                fails.append(f"R1 {r['claim_id']}: pivô {ev['pivot']} ({ev['mode']}) ausente do termo em {ev['ref']}")
            cat, atom = terms.norm_attr(key[3])
            prov = ev["atom"].split(":", 1)[0]
            if cat != "attribute" or ev["atom"] != f"{prov}:{ev['atom'].split(':')[1]}:{atom}":
                fails.append(f"R1 {r['claim_id']}: {key[3]} não normaliza para {ev['atom']}")
            side = sa if prov == sp else oa if prov == op else set()
            if ev["atom"] not in side:
                fails.append(f"R2 {r['claim_id']}: átomo evidenciado {ev['atom']} fora do lado {prov}")
            seen_atoms.add(ev["atom"])
        for a in sorted((sa | oa) - seen_atoms):
            fails.append(f"R2 {r['claim_id']}: átomo {a} sem evidência na linha")
        for a in sa | oa:
            if not ATOM_RX.match(a):
                fails.append(f"R2 {r['claim_id']}: átomo mal formado {a}")

    # ---------------------------------------------------------------- R3
    if atom_fams is None:
        _res, atom_fams = S.scan()
    for a, n in res["atoms"].items():
        if atom_fams.get(B.corpus_key(a), 0) != n:
            fails.append(f"R3 atestação de {a}: resolution.json {n} != recálculo {atom_fams.get(B.corpus_key(a), 0)}")
    for r in rows:
        o = json.loads(r["other"])
        why = []
        for a, out in o["corpus_families_outside_support"].items():
            if atom_fams.get(B.corpus_key(a), 0) - o["support_c06_families"] != out:
                fails.append(f"R3 {r['claim_id']}: contagem fora do suporte de {a} não confere")
            if out < 1:
                why.append("atom_not_attested_outside_support")
        why = sorted(set(why))
        if r["claim_id"].startswith("MOD-D-") and o["instances"].get("unfolded_from_N:M", 0) == o["pivot_instances"]:
            why.append("nm_unfolded")
        if sorted(why) != sorted(o["unresolved_reasons"]):
            fails.append(f"R3 {r['claim_id']}: motivos {o['unresolved_reasons']} != recálculo {why}")
        want = "UNRESOLVED" if why else "STRUCTURALLY_VALID"
        if r["evidence_state"] != want:
            fails.append(f"R3 {r['claim_id']}: evidence_state {r['evidence_state']} != {want}")

    # ---------------------------------------------------------------- R4
    for r in rows:
        cid = r["claim_id"]
        if r["predicate_id"] == "skos:exactMatch" or r["semantic_relation"] == "exact":
            fails.append(f"R4 {cid}: exactMatch num ouro DERIVADO")
        if r.get("curation_rule") != B.LEVEL_RULE:
            fails.append(f"R4 {cid}: curation_rule {r.get('curation_rule')!r}")
        if r["semantic_relation"] == "close":
            if r["transport_fidelity"] != "declared_loss" or not any(
                    x.get("kind") == "semantic" for x in r.get("loss_contract") or []):
                fails.append(f"R4 {cid}: close sem perda semântica declarada")
        elif r["semantic_relation"] == "related":
            if r["transport_fidelity"] != "none" or r.get("translation_fn"):
                fails.append(f"R4 {cid}: related com transporte ou função")
        else:
            fails.append(f"R4 {cid}: relação {r['semantic_relation']} fora de close/related")

    # ---------------------------------------------------------------- R5
    cited = set()
    for t in traces:
        for c in t["claims"]:
            cited.add(c)
            if c not in by_id:
                fails.append(f"R5 pivô {t['pivot']} do par {t['pair']} cita {c}, que não está no SSSOM")
    for c in sorted(set(by_id) - cited):
        fails.append(f"R5 {c}: linha sem pivô no traces.jsonl")

    # ---------------------------------------------------------------- R6
    for r in rows:
        if not r["claim_id"].startswith("MOD-G-"):
            if r.get("group"):
                fails.append(f"R6 {r['claim_id']}: linha D com grupo")
            continue
        g, o = r.get("group") or {}, json.loads(r["other"])
        sv = [v["field"] for v in g.get("variables", []) if v["side"] == "subject"]
        ov = [v["field"] for v in g.get("variables", []) if v["side"] == "object"]
        if sv != o["subject_atoms"] or ov != o["object_atoms"]:
            fails.append(f"R6 {r['claim_id']}: variáveis do grupo != átomos da linha")
        if g.get("cardinality") != B._card(len(sv), len(ov)) or g.get("cardinality") == "1:1":
            fails.append(f"R6 {r['claim_id']}: cardinalidade {g.get('cardinality')} não confere")
        if g.get("bo_group_id") != r.get("bo_group_id"):
            fails.append(f"R6 {r['claim_id']}: bo_group_id da coluna != do grupo")
        if any(s["name"] != "identity" for s in g.get("steps", [])) or len(g.get("steps", [])) != len(sv) * len(ov):
            fails.append(f"R6 {r['claim_id']}: passos do grupo não são identity lado a lado")

    # ---------------------------------------------------------------- R7
    for f in fam["families"]:
        if len(f["providers"]) < 2:
            fails.append(f"R7 {f['family']}: família com um só provedor")
        for p in f["pairs"]:
            if p["provider_a"] == p["provider_b"] or p["n_shared"] < S.PARAMS["min_shared_vars"] \
                    or p["jaccard"] < S.PARAMS["min_jaccard"]:
                fails.append(f"R7 {p['pair']}: par fora de V1-V3")
    info = {"rows": len(rows), "evidence_items": n_ev, "records_read": sum(len(v) for v in recs.values()),
            "atoms": len(res["atoms"]), "traces": len(traces), "families": len(fam["families"])}
    return fails, info


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] != ID:
        print(f"uso: python -I -m bo.gold_mods.resolve {ID}", file=sys.stderr)
        return 2
    fails, info = check()
    if fails:
        print(f"[{now_iso()}] resolve: {len(fails)} falha(s)")
        for f in fails[:200]:
            print("  " + f)
        return 1
    print(f"[{now_iso()}] resolve: OK {json.dumps(info, ensure_ascii=False, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
