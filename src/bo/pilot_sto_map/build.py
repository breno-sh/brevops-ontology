"""Pacote do glossarista + decisões do mapeador -> mapping.sssom.tsv (C09 3.1.0) e build_record.json.

Uso: python -I -m bo.pilot_sto_map.build [--bundle DIR] [--out DIR] [--check]
  --out    pasta de saída (padrão $BO_DATA/PILOT-STO-MAP/.staging; o definitivo só muda no pipeline --promote)
  --check  regera numa pasta temporária e compara byte a byte com o definitivo ($BO_DATA/PILOT-STO-MAP)

Do pacote saem, a cada build: tipos de valor (C05 -> tipo do C09), conceitos (âncora corrente do átomo ou
bo:UNGLOSSED), sentenças publicadas citadas (repo, tag, arquivo, linha), estado de evidência (DOC_SUPPORTED só
com as duas sentenças publicadas e nenhuma âncora UNRESOLVED; senão STRUCTURALLY_VALID) e a lista de átomos para
a exaustividade. Das decisões saem relação, função, fidelidade, perdas e testes. Átomo de um par sem alegação que
transporte ganha a linha de ausência tipada (sssom:NoTermFound). Decisão que cita átomo que saiu do pacote não
vira linha: vai a 'dropped' no build_record (a rerodada com pacote novo não quebra nem inventa).
Determinístico: sem hora no conteúdo; a mesma entrada dá os mesmos bytes.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from bo.contracts import sssom as CS
from bo.semantics.valuetypes import OutOfDomain, TypeError_, ValueType

from . import decisions as DEC
from .common import (MAPPING_SET_ID, MODEL_ID, MODULE, PAIR_SIDES, PAIRS, PREFIXES, Bundle, dump_json, emit,
                     load_bundle, now, out_dir, provider_of, run_main, sha256_bytes, sha256_file, staging_dir,
                     tmp_dir)

NO_TERM = "sssom:NoTermFound"
UNGLOSSED = "bo:UNGLOSSED"
PREDICATE = {"exact": "skos:exactMatch", "close": "skos:closeMatch", "broad": "skos:broadMatch",
             "narrow": "skos:narrowMatch", "related": "skos:relatedMatch"}
TRANSPORTING = ("exact", "close", "broad", "narrow")
SCALARS = {"string": "string", "boolean": "boolean", "decimal": "decimal", "integer": "integer", "enum": "enum"}
PUBLISHED = ("published", "derived")


# ------------------------------------------------------------------------------------------------ tipo de valor
def value_type(b: Bundle, atom: str) -> dict | None:
    """C05 (value_space) -> tipo de valor do C09. None quando o C09 não exprime o tipo (lista, mapa, documento):
    o lado fica sem tipo declarado e o árbitro devolve UNPROVEN (KIND-UNKNOWN), nunca um tipo inventado."""
    v = b.value_space.get(atom)
    if v is None:
        return None
    dt = v.get("datatype") or {}
    if dt.get("kind") != "scalar" or dt.get("scalar") not in SCALARS:
        return None
    out = {"datatype": SCALARS[dt["scalar"]], "quantity_kind": v.get("quantity_kind", "UNKNOWN"),
           "unit": v.get("unit_qudt", "UNKNOWN")}
    if out["datatype"] == "enum":
        if not v.get("enum"):
            return None
        out["enum"] = list(v["enum"])
    rng = v.get("range")
    if isinstance(rng, dict) and ({"min", "max"} & set(rng)):
        out["range"] = {k: rng[k] for k in ("min", "max") if k in rng}
    bc = v.get("byte_convention")
    if bc in ("SI", "IEC"):
        out["byte_convention"] = bc
    if v.get("rate_window"):
        out["rate_window"] = v["rate_window"]
    return out


# --------------------------------------------------------------------------------------------------- evidência
def citation(b: Bundle, atom: str) -> dict | None:
    a = b.anchors.get(atom)
    if not a or a.get("evidence_level") not in PUBLISHED or not a.get("sentence"):
        return None
    s = a.get("source") or {}
    if not all(s.get(k) for k in ("repo", "tag", "file", "line")):
        return None
    return {"source": f"{s['repo']}@{s['tag']}:{s['file']}#L{s['line']}", "sentence": a["sentence"],
            "date": str(a.get("recorded_at", ""))[:10], "atom_id": atom, "repo": s["repo"], "tag": s["tag"],
            "file": s["file"], "line": s["line"], "evidence_level": a["evidence_level"],
            "extraction_method": a.get("extraction_method")}


def evidence_for(b: Bundle, d: DEC.Decision) -> tuple[str, list[dict], str]:
    """-> (estado, citações, motivo do rebaixamento ou '')."""
    cites = [c for c in (citation(b, d.subject), citation(b, d.object)) if c]
    if d.evidence != "doc":
        return "STRUCTURALLY_VALID", cites, "decisão sem sentença que sustente (structural)"
    why = []
    for atom in (d.subject, d.object):
        a = b.anchors.get(atom)
        if citation(b, atom) is None:
            why.append(f"{atom}: sem sentença publicada no pacote")
        elif a.get("evidence_state") == "UNRESOLVED":
            why.append(f"{atom}: âncora UNRESOLVED no pacote (a sentença não sustenta o átomo)")
    if why:
        return "STRUCTURALLY_VALID", cites, "; ".join(why)
    return "DOC_SUPPORTED", cites, ""


def counterexample(b: Bundle, d: DEC.Decision, pair_decisions: list[DEC.Decision]) -> dict:
    """Contraexemplo procurado no pacote: outros átomos do lado objeto no mesmo conceito e outras alegações do
    mesmo sujeito no par."""
    c = b.concept_of(d.object)
    q = provider_of(d.object)
    same = [a for a in b.by_provider.get(q, []) if a != d.object and c != UNGLOSSED and b.concept_of(a) == c]
    other = sorted({x.object for x in pair_decisions if x.subject == d.subject and x.object != d.object})
    return {"query": f"átomos de {q} no pacote com o conceito {c}; outras alegações de {d.subject} no par",
            "found": bool(same or other),
            "result": f"{len(same)} outro(s) átomo(s) no conceito {sorted(same)[:6]}; "
                      f"{len(other)} outra(s) alegação(ões) do sujeito {other[:6]}"}


# ---------------------------------------------------------------------------------------------------- projeção
def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s)


def block_of(atom: str):
    for prefix, keys, why in DEC.BLOCKS:
        if atom.startswith(prefix):
            return keys, why
    return None


def projection_for(b: Bundle, atom: str, vt: dict | None, sample, log: dict) -> dict | None:
    """Projeção por ocorrência (scope=block com os campos-chave sustentados pelo pacote). O tipo da projeção é
    obrigatório e tem de ser aceito pelo núcleo do SEMANTICS; tipo do C05 que o núcleo recusa (ex. grandeza e
    unidade incoerentes) não vira projeção inválida: a projeção fica de fora e o motivo vai ao build_record."""
    blk = block_of(atom)
    if blk is None:
        return None
    if vt is None:
        log["projection_skipped"].append({"atom_id": atom, "why": "tipo do C05 sem forma no C09 (lista, mapa ou documento)"})
        return None
    try:
        ValueType.from_dict(vt)
    except (TypeError_, OutOfDomain, ValueError) as e:
        log["projection_skipped"].append({"atom_id": atom, "why": f"tipo do C05 recusado pelo núcleo do SEMANTICS: {e}"})
        return None
    return {"projection_id": f"PRJ-{_slug(atom)}", "field": atom,
            "occurrence": {"scope": "block", "key_fields": list(blk[0])},
            "extractor": {"name": "identity"}, "concept": b.concept_of(atom), "type": vt,
            "tests": [{"input": sample, "expected": sample}]}


def sample_of(vt: dict):
    """Valor de teste admitido pelo tipo (para o teste do extrator identidade da projeção)."""
    dt = vt.get("datatype")
    if dt == "boolean":
        return True
    if dt == "enum":
        return vt["enum"][0]
    if dt in ("integer", "decimal"):
        rng = vt.get("range") or {}
        return rng.get("min", rng.get("max", 1))
    return "exemplo-01"


def projections(b: Bundle, sides, log: dict) -> list[dict]:
    """sides: [(átomo, tipo, amostra ou None)]. Todo uso de átomo em bloco repetido com chave sustentada leva a
    projeção scope=block (alegação, related e ausência), para a ocorrência ser identificada em toda linha."""
    out = []
    for atom, vt, sample in sides:
        if atom == NO_TERM:
            continue
        p = projection_for(b, atom, vt, sample if sample is not None else (sample_of(vt) if vt else None), log)
        if p is not None:
            out.append(p)
    return out


# ------------------------------------------------------------------------------------------------------ linhas
def _common(claim_id: str) -> dict:
    return {"claim_id": claim_id, "claim_version_id": f"{claim_id}@1", "event_id": f"EV-{claim_id}-1",
            "mapping_justification": "semapv:UnspecifiedMatching", "mapping_tool": MODEL_ID,
            "creator_id": MODULE, "mapping_date": DEC.MAPPING_DATE, "basis": "direct"}


def claim_row(b: Bundle, d: DEC.Decision, pair_decisions: list[DEC.Decision], log: dict) -> dict:
    st, cites, why = evidence_for(b, d)
    if why:
        log["downgraded"].append({"claim_id": d.claim_id, "why": why})
    r = _common(d.claim_id)
    r.update({"subject_id": d.subject, "object_id": d.object, "predicate_id": PREDICATE[d.relation],
              "semantic_relation": d.relation,
              "value_domain_relation": {"relation": d.vdr, "orientation": "subject_to_object"},
              "transport_fidelity": d.fidelity, "guard": d.guard, "loss_contract": [dict(x) for x in d.loss],
              "evidence_state": st, "subject_concept": b.concept_of(d.subject),
              "object_concept": b.concept_of(d.object)})
    st_t, ob_t = value_type(b, d.subject), value_type(b, d.object)
    if st_t is not None:
        r["subject_value_type"] = st_t
    if ob_t is not None:
        r["object_value_type"] = ob_t
    proof = {"type": "relatedness" if d.relation == "related" else
             ("membership" if d.relation in ("broad", "narrow") else "normalization"),
             "evidence": cites, "tests": [dict(t) for t in d.tests],
             "counterexample_search": counterexample(b, d, pair_decisions)}
    r["proof"] = proof
    t0 = d.tests[0] if d.tests else {}
    projs = projections(b, ((d.subject, st_t, t0.get("input")), (d.object, ob_t, t0.get("expected"))), log)
    if projs:
        r["projection"] = projs
    if d.relation != "related":
        r["translation_fn"] = d.fn
        if d.membership is not None:
            r["membership_predicate"] = d.membership
    notes = [x for x in (d.note, f"evidência rebaixada: {why}" if why and d.evidence == "doc" else "") if x]
    if d.relation == "related" and d.absence_why:
        notes.append(f"sem transporte: {d.absence_why}")
    if notes:
        r["comment"] = " | ".join(notes)
    return r


def absence_row(b: Bundle, pair: str, atom: str, related: list[DEC.Decision], other: str, log: dict) -> dict:
    concept = b.concept_of(atom)
    same_other = [a for a in b.by_provider.get(other, []) if concept != UNGLOSSED and b.concept_of(a) == concept]
    cand = [c["candidate_id"] for c in b.candidates if c.get("pair") == pair and any(
        n.get("ref") == atom for side in ("subject", "object") for n in (c.get(side) or {}).get("nodes", []))]
    searched = [f"conceito do átomo no glossário congelado: {concept}",
                f"átomos de {other} no pacote ancorados no mesmo conceito: {len(same_other)}",
                f"candidatos C08 do par {pair} com o átomo: {len(cand)}"]
    evidence = []
    if related:
        kind = sorted(related, key=lambda d: d.claim_id)[0].absence_kind
        for d in sorted(related, key=lambda d: d.claim_id):
            searched.append(f"alegação related {d.claim_id} (sem transporte)")
            evidence.append({"source": f"mapper:{MODULE}#{d.claim_id}", "sentence": d.absence_why,
                             "date": DEC.MAPPING_DATE, "evidence_level": "interpreted",
                             "extraction_method": "model", "model_id": MODEL_ID})
    elif concept in DEC.DEMONSTRATED_CONCEPTS and not same_other and not cand:
        kind = "ABSENCE_DEMONSTRATED"
        gd = [x for x in b.decisions if x.get("concept_id") == concept and x.get("kind") == "exclusive"]
        searched.append(f"atributos e blocos dos tipos de {other} no pacote ({len(b.by_provider.get(other, []))} átomos)")
        for x in gd:
            evidence.append({"source": f"bundle:PILOT-STO-GLOSS/decisions.jsonl#{x['decision_id']}",
                             "sentence": x.get("reason", ""), "date": str(x.get("recorded_at", ""))[:10],
                             "evidence_level": "derived"})
        evidence.append({"source": f"mapper:{MODULE}#DEMONSTRATED_CONCEPTS", "date": DEC.MAPPING_DATE,
                         "sentence": f"nenhum átomo de {other} no pacote ancorado em {concept} e nenhum candidato "
                                     f"do par; o mapeador confirma que a decisão não aparece como valor de enum",
                         "evidence_level": "interpreted", "extraction_method": "model", "model_id": MODEL_ID})
    else:
        kind = "UNRESOLVED"
    cid = f"CLM-{pair}-STO-NONE-{atom}"
    r = _common(cid)
    absence = {"kind": kind, "searched": searched}
    if evidence:
        absence["evidence"] = evidence
    r.update({"subject_id": atom, "object_id": NO_TERM, "predicate_id": "skos:relatedMatch",
              "semantic_relation": "related",
              "value_domain_relation": {"relation": "unknown", "orientation": "subject_to_object"},
              "transport_fidelity": "none", "guard": {"all": []}, "loss_contract": [],
              "evidence_state": "STRUCTURALLY_VALID", "subject_concept": concept, "object_concept": UNGLOSSED,
              "absence": absence, "proof": {"type": "absence", "evidence": evidence, "tests": []}})
    vt = value_type(b, atom)
    if vt is not None:
        r["subject_value_type"] = vt
    projs = projections(b, ((atom, vt, None),), log)
    if projs:
        r["projection"] = projs
    return r


def pair_of(claim_id: str) -> str:
    m = re.match(r"^CLM-([A-Z]+)-STO-", claim_id)
    return m.group(1) if m else ""


def build_records(b: Bundle) -> tuple[list[dict], dict]:
    log = {"dropped": [], "downgraded": [], "projection_skipped": []}
    by_pair: dict[str, list[DEC.Decision]] = {p: [] for p, _, _ in PAIRS}
    seen = set()
    for d in DEC.DECISIONS:
        if d.claim_id in seen:
            raise ValueError(f"claim_id repetido nas decisões: {d.claim_id}")
        seen.add(d.claim_id)
        sp, op = PAIR_SIDES[d.pair]
        miss = [a for a in (d.subject, d.object) if a not in b.atoms]
        wrong = provider_of(d.subject) != sp or provider_of(d.object) != op
        if miss or wrong or pair_of(d.claim_id) != d.pair:
            log["dropped"].append({"claim_id": d.claim_id,
                                   "why": f"fora do pacote: {miss}" if miss else "orientação ou par errado"})
            continue
        by_pair[d.pair].append(d)
    rows = []
    for pair, sp, op in PAIRS:
        ds = by_pair[pair]
        rows += [claim_row(b, d, ds, log) for d in ds]
        moved = {a for d in ds if d.relation in TRANSPORTING for a in (d.subject, d.object)}
        for prov, other in ((sp, op), (op, sp)):
            for atom in b.by_provider.get(prov, []):
                if atom in moved:
                    continue
                rel = [d for d in ds if d.relation == "related" and atom in (d.subject, d.object)]
                rows.append(absence_row(b, pair, atom, rel, other, log))
    rows.sort(key=lambda r: r["claim_id"])
    return rows, log


def exhaustive_gaps(b: Bundle, rows: list[dict]) -> list[str]:
    """Todo átomo dos dois lados de cada par aparece numa linha do par (MAPPER_BRIEF M1)."""
    seen: dict[str, set] = {}
    for r in rows:
        seen.setdefault(pair_of(r["claim_id"]), set()).update({r["subject_id"], r["object_id"]})
    gaps = []
    for pair, sp, op in PAIRS:
        for atom in b.by_provider.get(sp, []) + b.by_provider.get(op, []):
            if atom not in seen.get(pair, set()):
                gaps.append(f"{pair}: {atom}")
    return gaps


def _uniq(xs: list[dict]) -> list[dict]:
    out, seen = [], set()
    for x in xs:
        k = (x.get("atom_id"), x.get("why"))
        if k not in seen:
            seen.add(k)
            out.append(x)
    return sorted(out, key=lambda x: (x["atom_id"], x["why"]))


def counts(rows: list[dict]) -> dict:
    from collections import Counter
    out = {"rows": len(rows), "by_pair": {}, "by_relation": dict(Counter(r["semantic_relation"] for r in rows
                                                                          if r["object_id"] != NO_TERM)),
           "by_evidence_state": dict(Counter(r["evidence_state"] for r in rows if r["object_id"] != NO_TERM)),
           "absence_kinds": dict(Counter(r["absence"]["kind"] for r in rows if r["object_id"] == NO_TERM)),
           "projections": sum(len(r.get("projection") or []) for r in rows),
           "groups": sum(1 for r in rows if r.get("group"))}
    for pair, _, _ in PAIRS:
        rs = [r for r in rows if pair_of(r["claim_id"]) == pair]
        out["by_pair"][pair] = {
            "transport": sum(1 for r in rs if r["semantic_relation"] in TRANSPORTING),
            "related": sum(1 for r in rs if r["semantic_relation"] == "related" and r["object_id"] != NO_TERM),
            "absence": sum(1 for r in rs if r["object_id"] == NO_TERM)}
    return out


def build(b: Bundle, out: Path) -> dict:
    rows, log = build_records(b)
    gaps = exhaustive_gaps(b, rows)
    if gaps:
        raise ValueError(f"exaustividade: {len(gaps)} átomo(s) sem linha, ex. {gaps[:5]}")
    text = CS.write_tsv(rows, MAPPING_SET_ID, PREFIXES)
    _meta, back, _cols = CS.read_tsv(text)
    if back != rows:
        bad = [r["claim_id"] for r, x in zip(rows, back) if r != x][:5]
        raise ValueError(f"ida e volta do C09 pelo bo.contracts.sssom não devolveu as linhas: {bad}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "mapping.sssom.tsv").write_text(text, encoding="utf-8")
    here = Path(__file__).resolve().parent
    rec = {"schema": "bo.pilot_sto_map.build/1", "module": MODULE, "mapping_set_id": MAPPING_SET_ID,
           "mapping_date": DEC.MAPPING_DATE, "model_id": MODEL_ID,
           "inputs": {"bundle": {"path": "$BO_DATA/PILOT-STO-GLOSS/bundle", "manifest_sha256": b.sha256,
                                 "files": b.hashes},
                      "code": {f"src/bo/pilot_sto_map/{n}": sha256_file(here / n)
                               for n in ("decisions.py", "build.py", "common.py")}},
           "mapping_sha256": sha256_bytes(text.encode("utf-8")), "counts": counts(rows),
           "decisions": len(DEC.DECISIONS), "dropped": log["dropped"], "downgraded": log["downgraded"],
           "projection_skipped": _uniq(log["projection_skipped"]),
           "unkeyed_blocks": [{"prefix": p, "why": w} for p, w in DEC.UNKEYED_BLOCKS],
           "keyed_blocks": [{"prefix": p, "key_fields": list(k), "source": w} for p, k, w in DEC.BLOCKS]}
    (out / "build_record.json").write_text(dump_json(rec), encoding="utf-8")
    return rec


def check(b: Bundle) -> int:
    tmp = tmp_dir() / "build_check"
    rec = build(b, tmp)
    bad = []
    for name in ("mapping.sssom.tsv", "build_record.json"):
        ref = out_dir() / name
        if not ref.is_file():
            bad.append(f"{ref} ausente")
        elif ref.read_bytes() != (tmp / name).read_bytes():
            bad.append(f"{name} regerado difere do definitivo")
    for x in bad:
        emit(f"  FALHA {x}")
    emit(f"[{now()}] build --check: {rec['counts']['rows']} linha(s) regeradas; "
         f"{'idêntico ao definitivo' if not bad else 'DIFERENTE do definitivo'}")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_sto_map.build")
    ap.add_argument("--bundle")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    b = load_bundle(Path(a.bundle) if a.bundle else None)
    if a.check:
        return check(b)
    out = Path(a.out) if a.out else staging_dir()
    rec = build(b, out)
    emit(f"[{now()}] build: {rec['counts']['rows']} linha(s) -> {out / 'mapping.sssom.tsv'}; "
         f"pacote {b.sha256[:16]}; {len(rec['dropped'])} decisão(ões) fora do pacote; "
         f"{len(rec['downgraded'])} rebaixada(s) para STRUCTURALLY_VALID")
    return 0


if __name__ == "__main__":
    run_main(main)
