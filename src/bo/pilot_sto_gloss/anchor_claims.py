"""Gate do PILOT-STO-GLOSS: toda âncora multi-provedor é alegação com evidência (GLOSSARY_BRIEF G2, achado F4).

Chamado pelo despachante (python -I -m bo.glossary.anchor_claims PILOT-STO-GLOSS) ou direto. Lê, em
$BO_DATA/PILOT-STO-GLOSS (ou --dir): glossary.jsonl, claims.jsonl, decisions.jsonl e canonical_atoms.jsonl, e reprova
quando:
  - falta um dos arquivos, ou algum não passa no validador oficial (bo.contracts.validate);
  - uma âncora cita conceito fora do glossário ou átomo fora da fatia (canonical_atoms.jsonl irmão);
  - uma âncora grava estado acima de STRUCTURALLY_VALID (DOC_SUPPORTED e acima são de outro papel);
  - uma âncora STRUCTURALLY_VALID não traz source {repo, tag, file, line, sentence} ou a busca de contraexemplo;
  - extraction_method model sem evidence_level interpreted e model_id claude-opus-5-5;
  - o evidence_state do conceito não é o menor estado das suas âncoras (UNRESOLVED sem âncora);
  - âncora com sentença sem evidence_ref ao fato C03 do átomo (C20-EVREF), ou âncora sem sentença que não é
    UNRESOLVED com motivo no context (C20-UNRESOLVED);
  - num caminho átomo→conceito←átomo entre provedores diferentes, uma ponta sem sentença com fonte que não esteja
    declarada UNRESOLVED; cada caminho conta como alegação de correspondência, e os sem prova nas duas pontas
    saem no total (paths_without_evidence) como hipótese, nunca como correspondência.
Saída 0 = passou; 1 = reprovou (motivos impressos); 2 = entrada ausente.
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

from . import common as C

ORDER = ("UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED")
WRITABLE = {"UNRESOLVED", "STRUCTURALLY_VALID"}
FILES = ("glossary.jsonl", "claims.jsonl", "decisions.jsonl", "canonical_atoms.jsonl")
VALIDATE_ALIAS = {"glossary.jsonl": "glossary", "claims.jsonl": "claims", "decisions.jsonl": "decisions",
                  "canonical_atoms.jsonl": "canonical_atoms"}


def has_evidence(cl: dict) -> bool:
    src = cl.get("source") or {}
    return bool(cl.get("sentence")) and all(src.get(k) for k in ("repo", "tag", "file", "line", "sentence"))


def latest(claims: list[dict]) -> list[dict]:
    """A versão mais nova de cada alegação (claim_version_id = <claim_id>@n)."""
    best: dict[str, tuple[int, dict]] = {}
    for cl in claims:
        n = int(str(cl.get("claim_version_id", "@1")).rsplit("@", 1)[-1].split("~")[0] or 1)
        if cl.get("claim_id") not in best or n > best[cl["claim_id"]][0]:
            best[cl.get("claim_id")] = (n, cl)
    return [v for _, v in sorted(best.values(), key=lambda x: str(x[1].get("claim_id")))]


def check(d: Path, validate=True) -> tuple[list[str], dict]:
    errs: list[str] = []
    missing = [f for f in FILES if not (d / f).is_file()]
    if missing:
        return [f"entrada ausente: {d / f}" for f in missing], {"missing": missing}
    if validate:
        from bo.contracts import validate as V
        for f in FILES:
            r = V.validate(VALIDATE_ALIAS[f], d / f)
            if not r.ok:
                errs.append(f"{f}: reprovado pelo validador oficial ({'; '.join(map(str, r.errors[:3]))})")
    concepts = {c["concept_id"]: c for c in C.load_jsonl(d / "glossary.jsonl")}
    claims = latest(C.load_jsonl(d / "claims.jsonl"))
    atoms = {a["atom_id"] for a in C.load_jsonl(d / "canonical_atoms.jsonl")}
    by_concept: dict[str, list[dict]] = {}
    for cl in claims:
        cid, aid, st = cl.get("concept_id"), cl.get("atom_id"), cl.get("evidence_state")
        tag = cl.get("claim_version_id", cl.get("claim_id"))
        if cid not in concepts:
            errs.append(f"{tag}: conceito {cid} fora do glossário")
        if aid not in atoms:
            errs.append(f"{tag}: átomo {aid} fora da fatia (canonical_atoms.jsonl)")
        if st not in WRITABLE:
            errs.append(f"{tag}: estado {st} não é do glossarista (só UNRESOLVED ou STRUCTURALLY_VALID)")
        if st == "STRUCTURALLY_VALID" and not has_evidence(cl):
            errs.append(f"{tag}: STRUCTURALLY_VALID sem sentença e fonte completas")
        if cl.get("sentence"):
            ref = cl.get("evidence_ref") or {}
            if ref.get("contract") != "C03" or not str(ref.get("id", "")).startswith("DF-"):
                errs.append(f"{tag}: sentença sem evidence_ref ao fato C03 do átomo (C20-EVREF)")
        else:
            if st != "UNRESOLVED" or len(cl.get("context") or "") < 15 or cl.get("source") or cl.get("evidence_ref"):
                errs.append(f"{tag}: âncora sem sentença tem de ser UNRESOLVED, com motivo no context e sem fonte")
        if not (cl.get("counterexample_search") or {}).get("query"):
            errs.append(f"{tag}: sem busca de contraexemplo")
        if cl.get("extraction_method") == "model" and (cl.get("evidence_level") != "interpreted"
                                                       or cl.get("model_id") != C.MODEL_ID):
            errs.append(f"{tag}: extração por modelo sem interpreted/model_id {C.MODEL_ID}")
        by_concept.setdefault(cid, []).append(cl)
    for cid, c in concepts.items():
        sts = [cl.get("evidence_state") for cl in by_concept.get(cid, []) if cl.get("evidence_state") in ORDER]
        want = min(sts, key=ORDER.index) if sts else "UNRESOLVED"
        if c.get("evidence_state") != want:
            errs.append(f"{cid}: evidence_state {c.get('evidence_state')} ≠ menor das âncoras ({want})")
    paths = unproven = hypothesis = 0
    for cid, cls in sorted(by_concept.items()):
        for a, b in itertools.combinations(sorted(cls, key=lambda x: x["claim_id"]), 2):
            if a["atom_id"].split(":")[0] == b["atom_id"].split(":")[0]:
                continue
            paths += 1
            hypothesis += "UNRESOLVED" in (a.get("evidence_state"), b.get("evidence_state"))
            if not (has_evidence(a) and has_evidence(b)):
                unproven += 1
                # sem sentença com fonte numa ponta: só pode ser hipótese declarada (UNRESOLVED com motivo)
                for x in (a, b):
                    if not has_evidence(x) and x.get("evidence_state") != "UNRESOLVED":
                        errs.append(f"caminho {a['claim_id']}→{cid}←{b['claim_id']}: {x['claim_id']} sem "
                                    f"evidência e acima de UNRESOLVED")
    stats = {"concepts": len(concepts), "anchors": len(claims), "multi_provider_paths": paths,
             "paths_without_evidence": unproven, "paths_with_unresolved_anchor": hypothesis}
    return errs, stats


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    d = C.data_dir()
    if "--dir" in argv:
        d = Path(argv[argv.index("--dir") + 1])
    errs, stats = check(d)
    print(f"[{C.now()}] anchor_claims {C.MODULE} em {d}: {stats}")
    if stats.get("missing"):
        for e in errs:
            print("  " + e)
        print("RESULTADO: ENTRADA AUSENTE")
        return 2
    for e in errs[:50]:
        print("  " + e)
    if errs:
        print(f"RESULTADO: REPROVADO ({len(errs)} problema(s))")
        return 1
    print("RESULTADO: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
