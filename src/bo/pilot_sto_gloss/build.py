"""Gera as saídas do PILOT-STO-GLOSS em $BO_DATA/PILOT-STO-GLOSS (determinístico; --check refaz e compara).

  canonical_units.jsonl, canonical_atoms.jsonl  C19, pela biblioteca de grão (bo.pilot_sto_gloss.decompose)
  glossary.jsonl, claims.jsonl, decisions.jsonl C20 3.2.0, do julgamento em spec.py + fatos de documentação
  bundle/                                       pacote fechado do mapeador (GLOSSARY_BRIEF 1.2.0, G1)

Uso: python -I -m bo.pilot_sto_gloss.build [--check]
"""

from __future__ import annotations

import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

from . import common as C
from . import decompose as DEC
from . import spec as SP

RECORDED_AT = "2026-11-04T13:30:00-03:00"   # quando o julgamento do spec.py foi revisto (tentativa 2, C20 3.3.0)
DOCS_DIR = {"aws": "DOCS-AWS", "google": "DOCS-GCP", "azurerm": "DOCS-AZURE", "oci": "DOCS-OCI"}
PAIRS = [("AWSGCP", "aws", "google"), ("AWSAZ", "aws", "azurerm"), ("AWSOCI", "aws", "oci"),
         ("GCPAZ", "google", "azurerm"), ("GCPOCI", "google", "oci"), ("AZOCI", "azurerm", "oci")]
LEVEL_ORDER = {"published": 0, "derived": 1, "interpreted": 2}
STATE_ORDER = ("UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED")
BUNDLE_FILES = ("candidates.jsonl", "glossary.jsonl", "decisions.jsonl", "claims.jsonl", "canonical_units.jsonl",
                "canonical_atoms.jsonl", "value_space.jsonl")


class BuildError(ValueError):
    pass


def jsonl(recs) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)


def doc_descriptions(atom_ids: set[str]) -> dict[str, list[dict]]:
    """atom_id -> fatos de descrição com fonte (DOCS-*), na ordem publicado < derivado < interpretado."""
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for prov, d in DOCS_DIR.items():
        types = C.SLICE[prov]
        with open(C.data_root() / d / "docs_facts.jsonl", encoding="utf-8") as fh:
            for line in fh:
                if not any(f":{t}:" in line for t in types):
                    continue
                f = json.loads(line)
                if (f.get("atom_id") in atom_ids and f.get("fact_kind") == "description" and f.get("source")
                        and f.get("status") == "stated"):
                    out[f["atom_id"]].append(f)
    for v in out.values():
        v.sort(key=lambda f: (LEVEL_ORDER.get(f.get("evidence_level"), 9), f["fact_id"]))
    return out


def counterexample(concept: tuple, anchored: dict[str, str], descs: dict[str, list[dict]]) -> dict:
    """Busca mecânica: átomos da fatia, fora deste conceito, cuja descrição contém algum termo da busca."""
    cid, words = concept[0], concept[7]
    mine = {a for a, c in anchored.items() if c == cid}
    hits = []
    for aid, fs in sorted(descs.items()):
        if aid in mine:
            continue
        text = " ".join(f["source"]["sentence"] for f in fs).lower()
        if any(w.lower() in text for w in words):
            hits.append(aid)
    other = [a for a in hits if a in anchored]
    free = [a for a in hits if a not in anchored]
    q = " | ".join(words)
    if not hits:
        return {"query": q, "found": False, "result": "nenhum outro átomo da fatia com estes termos na descrição"}
    res = (f"{len(hits)} átomo(s) da fatia com os termos fora deste conceito: {len(other)} ancorado(s) em outro "
           f"conceito, {len(free)} sem conceito; lidos pelo glossarista e mantidos fora (outro significado ou outro "
           f"alvo); exemplos: {', '.join(hits[:4])}")
    return {"query": q, "found": True, "result": res}


def build_glossary(canon_atoms: set[str]) -> dict:
    anchors = [(c, a) for c in SP.CONCEPTS for a in c[8]]
    anchored = {a[0]: c[0] for c, a in anchors}
    dup = [k for k, n in collections.Counter(a[0] for _, a in anchors).items() if n > 1]
    if dup:
        raise BuildError(f"átomo ancorado em dois conceitos: {dup}")
    all_descs = doc_descriptions(canon_atoms)
    claims, n_by_prov, errs = [], collections.Counter(), []
    states: dict[str, list[str]] = collections.defaultdict(list)
    for c, (aid, mark, note) in anchors:
        if aid not in canon_atoms:
            errs.append(f"{aid}: fora dos átomos canônicos da fatia")
            continue
        prov = aid.split(":")[0]
        n_by_prov[prov] += 1
        cl_id = f"ANC-{prov}-{n_by_prov[prov]:04d}"
        if mark == "UX":
            # C20-UNRESOLVED: sem sentença; o motivo vai no context (nunca sentença inventada ou emprestada)
            claims.append({"claim_id": cl_id, "claim_version_id": f"{cl_id}@1", "event_id": f"EV-{cl_id}-1",
                           "concept_id": c[0], "atom_id": aid, "anchor_kind": "atom", "context": note,
                           "counterexample_search": counterexample(c, anchored, all_descs),
                           "extraction_method": "manual", "evidence_level": "derived",
                           "evidence_state": "UNRESOLVED", "recorded_at": RECORDED_AT})
            states[c[0]].append("UNRESOLVED")
            continue
        fs = all_descs.get(aid)
        if not fs:
            errs.append(f"{aid}: sem fato de documentação (descrição com fonte)")
            continue
        f = fs[0]
        level = f["evidence_level"]
        state = "STRUCTURALLY_VALID" if mark == "SV" and level in ("published", "derived") else "UNRESOLVED"
        src = {k: f["source"][k] for k in ("repo", "tag", "file", "line", "sentence")}
        rec = {"claim_id": cl_id, "claim_version_id": f"{cl_id}@1", "event_id": f"EV-{cl_id}-1",
               "concept_id": c[0], "atom_id": aid, "anchor_kind": "atom", "sentence": src["sentence"],
               "context": f"{note}; fato {f['fact_id']}", "counterexample_search": counterexample(c, anchored, all_descs),
               "extraction_method": f.get("extraction_method", "parser"), "evidence_level": level,
               "evidence_state": state, "source": src, "evidence_ref": {"contract": "C03", "id": f["fact_id"]},
               "recorded_at": RECORDED_AT}
        if level == "interpreted":
            rec["model_id"] = f.get("model_id") or C.MODEL_ID
        claims.append(rec)
        states[c[0]].append(state)
    if errs:
        raise BuildError("; ".join(errs))
    glossary = []
    for c in SP.CONCEPTS:
        st = min(states[c[0]], key=STATE_ORDER.index) if states[c[0]] else "UNRESOLVED"
        rec = {"concept_id": c[0], "label": c[1], "definition": c[2], "domain": "STO", "quantity_kind": c[3],
               "status": "active", "evidence_state": st}
        if c[3] != "UNKNOWN":
            rec["unit"] = c[4]
        glossary.append(rec)
    decisions = build_decisions(claims)
    return {"glossary": glossary, "claims": claims, "decisions": decisions}


def build_decisions(claims: list[dict]) -> list[dict]:
    provs = collections.defaultdict(set)
    for cl in claims:
        provs[cl["concept_id"]].add(cl["atom_id"].split(":")[0])
    out = []

    def add(kind, cid, reason, **kw):
        out.append({"schema": "bo.glossary_decision/1", "decision_id": f"GD-STO-{len(out) + 1:04d}", "kind": kind,
                    "concept_id": cid, "reason": reason, "evidence": [], "author": C.MODULE,
                    "recorded_at": RECORDED_AT, **kw})

    for c in SP.CONCEPTS:
        val = {"datatype": c[5], "enum_semantics": c[6]}
        if c[3] == "quantitykind:AmountOfData":
            val["byte_convention"] = "NOT_APPLICABLE"
        add("value_type", c[0], "tipo de valor e semântica do valor do conceito (bytes exatos não têm convenção "
            "SI/IEC)" if "byte_convention" in val else "tipo de valor e semântica do valor do conceito", value=val)
    for c in SP.CONCEPTS:
        ps = sorted(provs[c[0]])
        if len(ps) == 1:
            add("exclusive", c[0], f"conceito de um provedor só nesta fatia ({ps[0]}); nenhuma âncora forçada nos "
                f"outros três")
    for narrow, broad, why in SP.HIERARCHY:
        add("broader", narrow, why, related_concept=broad)
    for a, b, why in SP.DISTINCT:
        add("same_kind_distinct", a, why, related_concept=b)
    return out


def node_side(atoms: list[str], unit_of: dict, kind_of: dict) -> dict:
    nodes, edges, units = [], [], {}
    for aid in atoms:
        u = unit_of[aid]
        if u not in units:
            units[u] = f"n{len(nodes)}"
            nodes.append({"node_id": units[u], "kind": "unit", "ref": u})
    first_unit = unit_of[atoms[0]]
    cross = []
    for aid in atoms:
        nid = f"n{len(nodes)}"
        nodes.append({"node_id": nid, "kind": "atom", "ref": aid})
        k = kind_of[unit_of[aid]]
        if k in ("FACET", "COMPONENT"):
            edges.append({"from": nid, "to": units[unit_of[aid]], "kind": "facet_of" if k == "FACET" else "component_of"})
        if unit_of[aid] != first_unit:
            cross.append(nid)
    return {"nodes": nodes, "edges": edges, "cross_facets": cross}


def build_candidates(claims, units, atoms, vspace) -> list[dict]:
    unit_of = {a["atom_id"]: a["unit_id"] for a in atoms}
    kind_of = {u["unit_id"]: u["kind"] for u in units}
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for cl in claims:
        by[cl["concept_id"]][cl["atom_id"].split(":")[0]].append(cl["atom_id"])
    out = []
    for pair, sp, op in PAIRS:
        n = 0
        for c in SP.CONCEPTS:
            s, o = sorted(by[c[0]].get(sp, [])), sorted(by[c[0]].get(op, []))
            if not s or not o:
                continue
            n += 1

            def kinds(xs):
                return sorted({json.dumps(vspace[a].get("datatype"), sort_keys=True) for a in xs if a in vspace})

            def qks(xs):
                return sorted({vspace[a].get("quantity_kind") for a in xs if a in vspace})

            out.append({"candidate_id": f"CAND-{pair}-STO-{n:04d}", "pair": pair, "domain": "STO",
                        "subject_provider": sp, "object_provider": op,
                        "subject": node_side(s, unit_of, kind_of), "object": node_side(o, unit_of, kind_of),
                        "concept": c[0],
                        "features": {"shared_concept": True, "subject_atoms": len(s), "object_atoms": len(o),
                                     "same_quantity_kind": qks(s) == qks(o),
                                     "same_value_datatype": kinds(s) == kinds(o),
                                     "subject_units": len({unit_of[a] for a in s}),
                                     "object_units": len({unit_of[a] for a in o})},
                        "generated_by": C.MODULE})
    return out


def produce() -> dict[str, str]:
    """nome relativo em $BO_DATA/PILOT-STO-GLOSS -> conteúdo."""
    dec = DEC.run()
    units, atoms = dec["units"], dec["atoms"]
    canon = {a["atom_id"] for a in atoms}
    g = build_glossary(canon)
    vspace = {r["atom_id"]: r for r in C.iter_jsonl(C.data_root() / "UNITS" / "value_space.jsonl")
              if r["atom_id"] in canon}
    cands = build_candidates(g["claims"], units, atoms, vspace)
    files = {"canonical_units.jsonl": jsonl(units), "canonical_atoms.jsonl": jsonl(atoms),
             "glossary.jsonl": jsonl(g["glossary"]), "claims.jsonl": jsonl(g["claims"]),
             "decisions.jsonl": jsonl(g["decisions"])}
    bundle = {"candidates.jsonl": jsonl(cands), "value_space.jsonl": jsonl(vspace[a] for a in sorted(vspace))}
    for k in ("glossary.jsonl", "decisions.jsonl", "claims.jsonl", "canonical_units.jsonl", "canonical_atoms.jsonl"):
        bundle[k] = files[k]
    man = "".join(f"{hashlib.sha256(bundle[k].encode()).hexdigest()}  {k}\n" for k in BUNDLE_FILES)
    for k in BUNDLE_FILES:
        files[f"bundle/{k}"] = bundle[k]
    files["bundle/MANIFEST.sha256"] = man
    files["decompose_report.json"] = C.dump_json(dec["report"])
    return files


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        files = produce()
    except BuildError as e:
        print(f"FALHA: {e}")
        return 1
    d = C.data_dir()
    if "--check" in argv:
        bad = [k for k, v in files.items() if not (d / k).is_file() or (d / k).read_text(encoding="utf-8") != v]
        extra = sorted(str(p.relative_to(d / "bundle")) for p in (d / "bundle").glob("*")
                       if p.name not in BUNDLE_FILES + ("MANIFEST.sha256",)) if (d / "bundle").is_dir() else []
        if bad or extra:
            print(f"FALHA: saídas diferem do que as entradas dão hoje: {bad} {extra}")
            return 1
        print(f"OK: {len(files)} arquivo(s) regenerado(s) idêntico(s)")
        return 0
    if (d / "bundle").is_dir():
        shutil.rmtree(d / "bundle")
    for k, v in files.items():
        p = d / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v, encoding="utf-8")
    rep = json.loads(files["decompose_report.json"])
    print(f"[{C.now()}] gravado em {d}: " + ", ".join(f"{k} {v.count(chr(10))}" for k, v in files.items()
                                                     if k.endswith(".jsonl")))
    for p, r in rep.items():
        c = r["container"]
        print(f"  {p}: contêiner {c['type']} = {c['grain']} ({c.get('rule')}; falta {c.get('missing')}); "
              f"grãos {r['grains']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
