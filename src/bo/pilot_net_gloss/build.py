"""Gera as saídas do PILOT-NET-GLOSS a partir só das entradas do catálogo (regeneração idêntica).

  python -I -m bo.pilot_net_gloss.build            grava em $BO_DATA/PILOT-NET-GLOSS e results/PILOT-NET-GLOSS
  python -I -m bo.pilot_net_gloss.build --check    regenera em $BO_TMP/regen e compara byte a byte com o gravado
  python -I -m bo.pilot_net_gloss.build --diagnostic   gera só em $BO_TMP/diagnostic, com os bloqueios listados
O build sem flag recusa (saída 4) gravar a saída oficial enquanto faltar docs_facts (CC-2) ou átomos de schema (CC-3).

Saídas (C19, C20, C08): canonical_units.jsonl, canonical_atoms.jsonl, grain_unknown_reasons.jsonl, glossary.jsonl,
claims.jsonl, decisions.jsonl, anchor_paths.jsonl e bundle/ (pacote fechado do mapeador do piloto).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from . import grain_apply, hub
from . import slice as SL

DATA_FILES = ["canonical_units.jsonl", "canonical_atoms.jsonl", "grain_unknown_reasons.jsonl", "glossary.jsonl",
              "claims.jsonl", "decisions.jsonl", "anchor_paths.jsonl"]
BUNDLE_FILES = ["glossary.jsonl", "decisions.jsonl", "claims.jsonl", "canonical_units.jsonl",
                "canonical_atoms.jsonl", "atoms.jsonl", "service_evidence.jsonl", "candidates.jsonl",
                "slice_notes.jsonl", "anchor_paths.jsonl", "bundle.json"]


def repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def tmp() -> Path:
    return Path(os.environ.get("BO_TMP") or data() / "tmp" / SL.MODULE)


def out_dir() -> Path:
    return data() / SL.MODULE


def results_dir() -> Path:
    return repo() / "results" / SL.MODULE


def now() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="seconds")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))


def write_jsonl(p: Path, recs: list[dict]):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(dumps(r) + "\n" for r in recs), encoding="utf-8")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------- entradas
def inputs() -> dict:
    types = set(SL.all_types())
    se = [json.loads(l) for l in open(data() / "SERVICE-EVIDENCE" / "service_evidence.jsonl", encoding="utf-8")]
    vs, roles = {}, {}
    for l in open(data() / "UNITS" / "value_space.jsonl", encoding="utf-8"):
        if not any(f":{t}:" in l for t in types):
            continue
        r = json.loads(l)
        if r["atom_id"].split(":")[1] in types:
            vs[r["atom_id"]] = r
    for l in open(data() / "ROLES" / "roles.jsonl", encoding="utf-8"):
        if not any(f":{t}:" in l for t in types):
            continue
        r = json.loads(l)
        if r["atom_id"].split(":")[1] in types:
            roles[r["atom_id"]] = r
    # entradas acrescentadas ao catálogo em 2026-11-04 (CC-2/CC-3 do PILOT-STO-GLOSS): fatos de documentação por
    # átomo (C03) e átomos de schema (C01); sem elas a lista fica vazia e as âncoras só citam o C25
    docs, schema_atoms = [], []
    for f in sorted(data().glob("DOCS-*/docs_facts.jsonl")):
        for l in open(f, encoding="utf-8"):
            if any(f":{t}:" in l for t in types):
                r = json.loads(l)
                if r.get("atom_id", "::").split(":")[1] in types:
                    docs.append(r)
    for f in sorted(data().glob("SCHEMA-*/atoms.jsonl")):
        for l in open(f, encoding="utf-8"):
            if any(f":{t}:" in l for t in types):
                r = json.loads(l)
                if r.get("resource_type") in types:
                    schema_atoms.append(r)
    return {"se": se, "vs": vs, "roles": roles, "docs": docs, "schema_atoms": schema_atoms}


# ------------------------------------------------------------------------------------------------- âncoras
def _se_by_id(se):
    return {r["evidence_id"]: r for r in se}


def counterexample(spec: dict, se: list[dict]) -> dict:
    prov = spec["atom_id"].split(":", 1)[0]
    rx = re.compile(spec["query"], re.I)
    hits, types = 0, set()
    for r in se:
        if r.get("provider") != prov:
            continue
        s = (r.get("doc") or {}).get("sentence") or ""
        if rx.search(s):
            hits += 1
            types.add(r.get("terraform_resource_type"))
    return {"query": spec["query"], "found": bool(spec["found"]),
            "result": (f"{hits} sentença(s) com o termo em {len(types)} tipo(s) do provedor no SERVICE-EVIDENCE; "
                       f"{spec['note']}")}


def build_claims(se, vs, docs=None) -> list[dict]:
    by = _se_by_id(se)
    dby = {r["fact_id"]: r for r in (docs or [])}
    out = []
    for spec in SL.ANCHORS:
        if spec.get("fact_id"):          # fato de documentação do próprio átomo (C03)
            f = dby.get(spec["fact_id"])
            if f is None or f.get("atom_id") != spec["atom_id"]:
                raise SystemExit(f"{spec['claim_id']}: fato C03 {spec['fact_id']} ausente ou de outro átomo")
            r = {"level": f.get("evidence_level"), "doc": f.get("source") or {},
                 "terraform_resource_type": spec["atom_id"].split(":")[1]}
        else:                            # fato de serviço do tipo do átomo (C25)
            r = by.get(spec["evidence_id"])
        if r is None:
            raise SystemExit(f"{spec['claim_id']}: fato {spec.get('evidence_id')} ausente do SERVICE-EVIDENCE")
        if spec["atom_id"] not in vs:
            raise SystemExit(f"{spec['claim_id']}: átomo {spec['atom_id']} fora do value_space")
        doc = r.get("doc") or {}
        if not doc.get("sentence") or r["terraform_resource_type"] != spec["atom_id"].split(":")[1]:
            raise SystemExit(f"{spec['claim_id']}: o fato não traz sentença do tipo do átomo")
        rec = {"claim_id": spec["claim_id"], "claim_version_id": f"{spec['claim_id']}@1",
               "event_id": f"EV-{spec['claim_id']}-1", "concept_id": spec["concept_id"], "atom_id": spec["atom_id"],
               "sentence": doc["sentence"], "context": spec["context"],
               "source": {k: doc[k] for k in ("repo", "tag", "file", "line", "sentence")},
               "counterexample_search": counterexample(spec, se),
               "evidence_state": "STRUCTURALLY_VALID", "recorded_at": SL.RECORDED_AT}
        if r.get("level") == "interpreted":
            rec.update(extraction_method="model", evidence_level="interpreted", model_id=SL.MODEL_ID)
        else:
            rec.update(extraction_method="parser", evidence_level=r["level"])
        out.append(rec)
    return out


RANK = hub.OB_RANK
STATES = sorted(RANK, key=RANK.get)


def build_glossary(claims) -> list[dict]:
    out = []
    for c in SL.CONCEPTS:
        sts = [a["evidence_state"] for a in claims if a["concept_id"] == c["concept_id"] and a.get("sentence")]
        out.append(dict(c, evidence_state=min(sts, key=RANK.get) if sts else "UNRESOLVED"))
    return out


def _ev_item(r: dict) -> dict:
    d = r.get("doc") or {}
    return {"source": f"{r['evidence_id']} ({d.get('repo')}/{d.get('file')}:{d.get('line')}@{d.get('tag')})",
            "sentence": d.get("sentence"), "date": SL.DECIDED_ON}


def build_decisions(se) -> list[dict]:
    by = _se_by_id(se)
    out = []
    for n, kind, concept, related, value, reason, evs in SL.DECISION_SPECS:
        items = []
        for e in evs:
            r = by.get(e)
            if r is None or not (r.get("doc") or {}).get("sentence"):
                raise SystemExit(f"GD-NET-{n:04d}: evidência {e} ausente ou sem sentença")
            items.append(_ev_item(r))
        out.append(SL._dec(n, kind, concept, reason, related=related, value=value, evidence=items))
    return out


# ------------------------------------------------------------------------------------------------- pacote
def _select(se, sel) -> list[str]:
    if isinstance(sel, str):
        return [sel]
    types = set(SL.SLICE_TYPES[sel["provider"]])
    return sorted(r["evidence_id"] for r in se if r.get("terraform_resource_type") in types
                  and r["fact_kind"] == sel["fact_kind"] and r["status"] == sel["status"])


def build_notes(se) -> list[dict]:
    ids = {r["evidence_id"] for r in se}
    out = []
    for i, n in enumerate(SL.SLICE_NOTES, 1):
        ev = sorted({x for s in n["evidence"] for x in _select(se, s)})
        miss = [x for x in ev if x not in ids]
        if miss:
            raise SystemExit(f"nota {i}: evidência inexistente {miss}")
        out.append({"note_id": f"SN-NET-{i:04d}", "concept_id": n["concept_id"], "provider": n["provider"],
                    "note": n["note"], "evidence": ev, "author": SL.MODULE, "recorded_at": SL.RECORDED_AT})
    return out


def build_candidates(paths_rows) -> list[dict]:
    """Candidatos C08 só onde o glossário já pôs o mesmo conceito nos dois lados de um par (base shared_concept).
    Não é decisão nem correspondência: o mapeador julga; o desfecho do árbitro vai como feature."""
    out, seq = [], {}
    order = {p: i for i, p in enumerate(SL.PROVIDERS)}
    for row in paths_rows:
        a, b = row["subject_atom"], row["object_atom"]
        pa, pb = hub.provider_of(a), hub.provider_of(b)
        if order[pa] > order[pb]:
            a, b, pa, pb = b, a, pb, pa
        pair = (pa, pb) if (pa, pb) in SL.PAIRS else (pb, pa)
        code = SL.PAIR_CODE[pair[0]] + SL.PAIR_CODE[pair[1]]
        seq[code] = seq.get(code, 0) + 1
        out.append({"candidate_id": f"CAND-{code}-{SL.DOMAIN}-{seq[code]:04d}", "pair": code, "domain": SL.DOMAIN,
                    "subject_provider": pair[0], "object_provider": pair[1],
                    "subject": {"nodes": [{"node_id": "n0", "kind": "atom", "ref": a}], "edges": [], "cross_facets": []},
                    "object": {"nodes": [{"node_id": "n0", "kind": "atom", "ref": b}], "edges": [], "cross_facets": []},
                    "concept": row["concept_id"],
                    "features": {"basis": "shared_concept", "hub_outcome": row["hub_outcome"],
                                 "subject_anchor_state": row["subject_anchor_state"],
                                 "object_anchor_state": row["object_anchor_state"]},
                    "generated_by": SL.MODULE})
    return out


def build_atoms(vs, roles, units, atoms) -> list[dict]:
    unit_of = {a["atom_id"]: a["unit_id"] for a in atoms}
    out = []
    for aid in sorted(vs):
        v = vs[aid]
        rec = {"atom_id": aid, "provider": aid.split(":")[0], "resource_type": aid.split(":")[1],
               "path": aid.split(":", 2)[2], "role": (roles.get(aid) or {}).get("role"),
               "datatype": v.get("datatype"), "quantity_kind": v.get("quantity_kind"), "unit": v.get("unit_qudt"),
               "unit_id": unit_of.get(aid)}
        for k in ("enum", "range"):
            if v.get(k) is not None:
                rec[k] = v[k]
        out.append(rec)
    return out


# ------------------------------------------------------------------------------------------------- tudo
def generate(dst: Path) -> dict:
    inp = inputs()
    se, vs, roles = inp["se"], inp["vs"], inp["roles"]
    g = grain_apply.decompose(se, inp["schema_atoms"], {k: r["role"] for k, r in roles.items()})
    claims = build_claims(se, vs, inp["docs"])
    glossary = build_glossary(claims)
    decisions = build_decisions(se)
    rows = hub.evaluate(claims, glossary, decisions, vs)
    files = {"canonical_units.jsonl": g["units"], "canonical_atoms.jsonl": g["atoms"],
             "grain_unknown_reasons.jsonl": g["ledger"], "glossary.jsonl": glossary, "claims.jsonl": claims,
             "decisions.jsonl": decisions, "anchor_paths.jsonl": rows}
    for name, recs in files.items():
        write_jsonl(dst / name, recs)
    types = set(SL.all_types())
    bundle = {"glossary.jsonl": glossary, "decisions.jsonl": decisions, "claims.jsonl": claims,
              "canonical_units.jsonl": g["units"], "canonical_atoms.jsonl": g["atoms"],
              "atoms.jsonl": build_atoms(vs, roles, g["units"], g["atoms"]),
              "service_evidence.jsonl": sorted((r for r in se if r.get("terraform_resource_type") in types),
                                               key=lambda r: r["evidence_id"]),
              "candidates.jsonl": build_candidates(rows), "slice_notes.jsonl": build_notes(se),
              "anchor_paths.jsonl": rows}
    bdir = dst / "bundle"
    for name, recs in bundle.items():
        write_jsonl(bdir / name, recs)
    index = {"schema": "bo.pilot_bundle/1", "module": SL.MODULE, "slice": SL.SLICE, "domain": SL.DOMAIN,
             "contracts": {"canonical_units.jsonl": "C19@3.1.0", "canonical_atoms.jsonl": "C19@3.1.0",
                           "glossary.jsonl": "C20@3.1.0", "claims.jsonl": "C20@3.1.0", "decisions.jsonl": "C20@3.1.0",
                           "candidates.jsonl": "C08@3.0.0", "service_evidence.jsonl": "C25@1.0.0"},
             "types": SL.SLICE_TYPES, "pairs": [SL.PAIR_CODE[a] + SL.PAIR_CODE[b] for a, b in SL.PAIRS],
             "projection": "treino (o SPLIT ainda não existe em bo/base: toda a fatia é treino; nada de teste ou ouro)",
             "files": {n: sha(bdir / n) for n in sorted(bundle)},
             "note": ("pacote fechado do mapeador: glossário, âncoras (hipóteses de alinhamento, STRUCTURALLY_VALID), "
                      "decisões, grão mecânico, átomos com tipo e papel, fatos de documentação da fatia e candidatos "
                      "de base shared_concept; sem mapeamento, sem uso, sem valores de deploy, sem ouro")}
    (bdir / "bundle.json").write_text(json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                      encoding="utf-8")
    return {"inputs": inp, "grain": g, "claims": claims, "glossary": glossary, "decisions": decisions, "rows": rows,
            "bundle": bundle}


def e2(units: list[dict]) -> list[dict]:
    """Embutido = separado? Compara grão, regra e o que falta (a camada Terraform não entra)."""
    by = {u["unit_id"]: u for u in units}
    out = []
    for prov, inline, sep in SL.E2_PAIRS:
        a, b = by.get(f"CU-{prov}-{inline}"), by.get(f"CU-{prov}-{sep}")
        sig = lambda u: None if u is None else [u["kind"], u["rule_applied"], u["missing_evidence"]]
        out.append({"inline": inline, "separate": sep, "inline_sig": sig(a), "separate_sig": sig(b),
                    "equal": a is not None and b is not None and sig(a) == sig(b) and a["kind"] != "UNKNOWN"})
    return out


def report(res: dict) -> dict:
    import collections
    g = res["grain"]
    kinds = collections.Counter(u["kind"] for u in g["units"])
    rules = collections.Counter(u["rule_applied"] for u in g["units"])
    miss = collections.Counter(m for u in g["units"] for m in u["missing_evidence"])
    per_prov = collections.Counter(u["provider"] for u in g["units"])
    rows = res["rows"]
    return {"schema": "bo.pilot_gloss_report/1", "module": SL.MODULE, "generated_at": now(),
            "decisions_recorded_at": SL.RECORDED_AT,
            "grain": {"units": len(g["units"]), "atoms": len(g["atoms"]), "by_kind": dict(sorted(kinds.items())),
                      "by_rule": dict(sorted(rules.items())), "missing": dict(sorted(miss.items())),
                      "units_by_provider": dict(sorted(per_prov.items())),
                      "unknown_reasons": len(g["ledger"])},
            "glossary": {"concepts": len(res["glossary"]), "anchors": len(res["claims"]),
                         "concepts_without_anchor": sum(1 for c in res["glossary"] if c["evidence_state"] == "UNRESOLVED"),
                         "model_extracted_anchors": sum(1 for a in res["claims"] if a["extraction_method"] == "model"),
                         "anchors_by_provider": dict(sorted(collections.Counter(
                             a["atom_id"].split(":")[0] for a in res["claims"]).items())),
                         "decisions": dict(sorted(collections.Counter(d["kind"] for d in res["decisions"]).items()))},
            "anchor_paths": {"n": len(rows), "outcomes": dict(sorted(collections.Counter(
                r["hub_outcome"] for r in rows).items()))},
            "candidates": len(res["bundle"]["candidates.jsonl"]), "e2_inline_vs_separate": e2(g["units"])}


def manifest_lines() -> list[str]:
    lines = []
    for n in DATA_FILES:
        lines.append(f"{sha(out_dir() / n)}  $BO_DATA/{SL.MODULE}/{n}")
    for n in BUNDLE_FILES:
        lines.append(f"{sha(out_dir() / 'bundle' / n)}  $BO_DATA/{SL.MODULE}/bundle/{n}")
    for n in ("CONTRACT_CHANGE.txt",):
        p = results_dir() / n
        if p.is_file():
            lines.append(f"{sha(p)}  $BO_REPO/results/{SL.MODULE}/{n}")
    return lines


def check() -> int:
    regen = tmp() / "regen"
    if regen.exists():
        for p in sorted(regen.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    generate(regen)
    bad = []
    for n in DATA_FILES + [f"bundle/{x}" for x in BUNDLE_FILES]:
        a, b = out_dir() / n, regen / n
        if not a.is_file() or a.read_bytes() != b.read_bytes():
            bad.append(n)
    mf = results_dir() / "MANIFEST.sha256"
    if not mf.is_file() or mf.read_text(encoding="utf-8").splitlines() != manifest_lines():
        bad.append("results/MANIFEST.sha256")
    if bad:
        print("regeneração diverge do gravado: " + ", ".join(bad))
        return 1
    print(f"regeneração idêntica: {len(DATA_FILES) + len(BUNDLE_FILES)} arquivos e o MANIFEST conferem")
    return 0


def blockers(res: dict) -> list[str]:
    """Pacote com evidência incompleta passaria nos gates e seria inútil: o build recusa gravar a saída oficial
    enquanto faltar fato de documentação por átomo (CC-2) ou átomo de schema (CC-3) da fatia. O CC-1 (alegação
    ilegível) não chega aqui: o C25Adapter da biblioteca levanta erro e o build para."""
    out = []
    if not res["inputs"]["docs"]:
        out.append("CC-2: nenhum docs_facts (C03) da fatia nas entradas")
    if not res["inputs"]["schema_atoms"]:
        out.append("CC-3: nenhum átomo de schema (C01) da fatia nas entradas")
    return out


def diagnostic(dst: Path) -> int:
    res = generate(dst)
    rep = report(res)
    rep["blockers"] = blockers(res)
    (dst / "build_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                           encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return check()
    if "--diagnostic" in argv:
        return diagnostic(tmp() / "diagnostic")
    stage = tmp() / "stage"
    res = generate(stage)
    bl = blockers(res)
    if bl:
        print("build recusado (saída oficial não gravada; diagnóstico em " + str(stage) + "):")
        for b in bl:
            print("  " + b)
        return 4
    res = generate(out_dir())
    results_dir().mkdir(parents=True, exist_ok=True)
    rep = report(res)
    (results_dir() / "build_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True)
                                                     + "\n", encoding="utf-8")
    (results_dir() / "MANIFEST.sha256").write_text("\n".join(manifest_lines()) + "\n", encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
