"""Gate F4 do PILOT-NET-GLOSS: toda âncora multi-provedor é alegação com evidência.

  python -I -m bo.glossary.anchor_claims PILOT-NET-GLOSS     (despachante) → bo.pilot_net_gloss.anchor_claims

Reprova (saída 1) se:
  A1 alguma âncora não tem sentença, contexto, busca de contraexemplo, ou a fonte publicada não é a sentença de um
     fato do SERVICE-EVIDENCE (C25) do tipo do átomo ou de um docs_facts (C03) do átomo (mesmo repo, tag, arquivo,
     linha e frase);
     A1 também: âncora com sentença sem evidence_ref, ou evidence_ref que não é o fato C03 do átomo (ou C25 do
     tipo) com a mesma sentença (C20-EVREF, C20 3.3.0);
  A2 alguma âncora tem estado acima do que o glossarista pode gravar (só UNRESOLVED e STRUCTURALLY_VALID), ou
     método model sem evidence_level interpreted e model_id claude-opus-5-5;
  A3 o conceito da âncora não existe, ou o evidence_state do conceito não é o menor entre as suas âncoras;
  A4 algum caminho átomo→conceito←átomo entre provedores diferentes não está registrado em anchor_paths.jsonl, ou
     o registrado diverge do recalculado pelo bo.semantics (hub_claim e obrigações);
  A5 algum caminho transporta (COMPOSED ou veredito OK) sem DOC_SUPPORTED (ou acima) nas duas âncoras;
  A6 o controle positivo falha: onde os dois lados têm tipo escalar conhecido, com as mesmas âncoras promovidas em
     memória a DOC_SUPPORTED, a composição tem de sair COMPOSED exact (senão o UNPROVEN acima poderia vir de outra
     causa); e todo caminho real com tipos conhecidos tem de falhar por ANCHOR-NOT-PROOF (A5),
     não por acaso; sem tipo conhecido o UNPROVEN vem de KIND-UNKNOWN e o controle não se aplica.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import build, hub
from . import slice as SL

SUPPORT = ("DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED")


def _load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def published_facts(inp: dict) -> dict[tuple, set]:
    """(tipo, repo, tag, arquivo, linha) -> sentenças publicadas: dos fatos C25 do tipo e dos fatos C03 do átomo."""
    facts: dict[tuple, set] = {}
    for r in inp.get("se", []):
        doc = r.get("doc") or {}
        if doc.get("sentence"):
            facts.setdefault((r.get("terraform_resource_type"), doc.get("repo"), doc.get("tag"), doc.get("file"),
                              doc.get("line")), set()).add(doc["sentence"])
    for r in inp.get("docs", []):
        doc = r.get("source") or {}
        if doc.get("sentence") and r.get("atom_id"):
            facts.setdefault((r["atom_id"].split(":")[1], doc.get("repo"), doc.get("tag"), doc.get("file"),
                              doc.get("line")), set()).add(doc["sentence"])
    return facts


def run(d: Path, inp: dict | None = None) -> tuple[list[str], dict]:
    errs: list[str] = []
    claims, glossary = _load(d / "claims.jsonl"), _load(d / "glossary.jsonl")
    decisions, stored = _load(d / "decisions.jsonl"), _load(d / "anchor_paths.jsonl")
    inp = inp if inp is not None else build.inputs()
    vs = inp["vs"]
    types = set(inp.get("types") or SL.all_types())
    facts = published_facts(inp)
    by_id = {("C25", r["evidence_id"]): {"type": r.get("terraform_resource_type"),
                                         "sentence": (r.get("doc") or {}).get("sentence")} for r in inp.get("se", [])}
    for r in inp.get("docs", []):
        by_id[("C03", r.get("fact_id"))] = {"atom": r.get("atom_id"),
                                            "sentence": (r.get("source") or {}).get("sentence")}
    cmap = {c["concept_id"]: c for c in glossary}
    for a in claims:
        cid = a.get("claim_id")
        unres = a.get("evidence_state") == "UNRESOLVED" and not a.get("sentence")
        if unres:
            if len(a.get("context") or "") < 15 or a.get("source") or a.get("evidence_ref"):
                errs.append(f"A1 {cid}: UNRESOLVED sem sentença exige motivo no context e nenhuma fonte (C20-UNRESOLVED)")
        elif len(a.get("sentence") or "") < 10 or len(a.get("context") or "") < 5:
            errs.append(f"A1 {cid}: sem sentença ou contexto")
        cs = a.get("counterexample_search") or {}
        if not (cs.get("query") and isinstance(cs.get("found"), bool) and cs.get("result")):
            errs.append(f"A1 {cid}: busca de contraexemplo incompleta")
        src = a.get("source")
        if not unres and (a.get("evidence_level") in ("published", "derived") or src):
            if not src:
                errs.append(f"A1 {cid}: âncora {a.get('evidence_level')} sem fonte")
            else:
                rt = hub.ref_of(a).split(":")[1]
                key = (rt, src.get("repo"), src.get("tag"), src.get("file"), src.get("line"))
                if src.get("sentence") not in facts.get(key, set()) or a.get("sentence") != src.get("sentence"):
                    errs.append(f"A1 {cid}: a sentença não é a de um fato do SERVICE-EVIDENCE do tipo {rt} "
                                f"em {src.get('file')}:{src.get('line')}")
        er = a.get("evidence_ref")
        if a.get("sentence"):
            if not er:
                errs.append(f"A1 {cid}: âncora com sentença sem evidence_ref (C20-EVREF)")
            else:
                f = by_id.get((er.get("contract"), er.get("id")))
                ok = f is not None and f["sentence"] == a.get("sentence") and (
                    f["atom"] == hub.ref_of(a) if er["contract"] == "C03" else f["type"] == hub.ref_of(a).split(":")[1])
                if not ok:
                    errs.append(f"A1 {cid}: evidence_ref {er} não é fato {'do átomo' if er.get('contract') == 'C03' else 'do tipo'} "
                                "com esta sentença")
        if a.get("evidence_state") not in ("UNRESOLVED", "STRUCTURALLY_VALID"):
            errs.append(f"A2 {cid}: estado {a.get('evidence_state')} não pode ser gravado pelo glossarista")
        if a.get("extraction_method") == "model" and (a.get("evidence_level") != "interpreted"
                                                      or a.get("model_id") != SL.MODEL_ID):
            errs.append(f"A2 {cid}: extração por modelo sem interpreted/{SL.MODEL_ID}")
        ref = hub.ref_of(a)
        if not ref or ref.split(":")[1] not in types:
            errs.append(f"A1 {cid}: âncora {ref} fora dos tipos da fatia")
        if a.get("anchor_kind") in ("block", "type") and not (a.get("implication") or {}).get("rule"):
            errs.append(f"A1 {cid}: âncora de {a['anchor_kind']} sem implicação")
        if a.get("concept_id") not in cmap:
            errs.append(f"A3 {cid}: conceito {a.get('concept_id')} ausente do glossário")
    for c in glossary:
        sts = [a["evidence_state"] for a in claims if a["concept_id"] == c["concept_id"]]
        want = min(sts, key=hub.OB_RANK.get) if sts else "UNRESOLVED"
        if c["evidence_state"] != want:
            errs.append(f"A3 {c['concept_id']}: evidence_state {c['evidence_state']} ≠ menor das âncoras ({want})")
    pairs = hub.paths(claims)
    rows = hub.evaluate(claims, glossary, decisions, vs)
    by_stored = {r.get("path_id"): r for r in stored}
    by_calc = {r["path_id"]: r for r in rows}
    for pid in sorted(set(by_calc) - set(by_stored)):
        errs.append(f"A4 {pid}: caminho entre provedores não registrado")
    for pid in sorted(set(by_stored) - set(by_calc)):
        errs.append(f"A4 {pid}: caminho registrado que não existe nas âncoras")
    for pid in sorted(set(by_calc) & set(by_stored)):
        if build.dumps(by_calc[pid]) != build.dumps(by_stored[pid]):
            errs.append(f"A4 {pid}: registro diverge do recalculado")
    for r in rows:
        both = r["subject_anchor_state"] in SUPPORT and r["object_anchor_state"] in SUPPORT
        if not both and (r["hub_outcome"] == "COMPOSED" or r["shared_concept_verdict"] == "OK"):
            errs.append(f"A5 {r['path_id']}: transporta sem DOC_SUPPORTED nas duas âncoras")
    ctrl = hub.evaluate(claims, glossary, decisions, vs, promote="DOC_SUPPORTED")
    for r in ctrl:
        if r["types_known"] and (r["hub_outcome"] != "COMPOSED" or r["hub_relation"] != "exact"):
            errs.append(f"A6 {r['path_id']}: controle positivo não compõe exact ({r['hub_outcome']}, {r['hub_rule']})")
    for r in rows:
        if r["types_known"] and "ANCHOR-NOT-PROOF" not in r["shared_concept_failed_rules"] and not (
                r["subject_anchor_state"] in SUPPORT and r["object_anchor_state"] in SUPPORT):
            errs.append(f"A5 {r['path_id']}: o UNPROVEN não vem da regra das âncoras (ANCHOR-NOT-PROOF)")
    stats = {"anchors": len(claims), "concepts": len(glossary), "multi_provider_paths": len(pairs),
             "outcomes": sorted({r["hub_outcome"] for r in rows}),
             "control_composed_exact": sum(1 for r in ctrl if r["hub_outcome"] == "COMPOSED"
                                           and r["hub_relation"] == "exact"),
             "control_applicable": sum(1 for r in ctrl if r["types_known"])}
    return errs, stats


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    d = build.out_dir()
    for a in argv:
        if a.startswith("--dir="):
            d = Path(a.split("=", 1)[1])
    for n in ("claims.jsonl", "glossary.jsonl", "decisions.jsonl", "anchor_paths.jsonl"):
        if not (d / n).is_file():
            print(f"anchor_claims: entrada ausente {d / n}")
            return 2
    errs, st = run(d)
    for e in errs:
        print(e)
    print(f"[{build.now()}] anchor_claims {SL.MODULE}: {st['anchors']} âncora(s), {st['concepts']} conceito(s), "
          f"{st['multi_provider_paths']} caminho(s) entre provedores (desfechos {st['outcomes']}), controle "
          f"positivo {st['control_composed_exact']}/{st['control_applicable']} exact (onde o tipo dos dois lados é "
          f"escalar conhecido); "
          f"{len(errs)} problema(s) -> {'OK' if not errs else 'REPROVADO'}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
