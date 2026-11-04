"""Gate G1: toda CQ tem fixture conforme, não conforme e incompleta em cada provedor onde se aplica.

  python -I -m bo.cq.fixture_check [DIR]     (despachante -> bo.cqfix.fixture_check; DIR padrão cq/fixtures)

Confere, sem rede:
  1. catálogo: 29 CQs do REQUIREMENTS + 8 CIS (os conceitos com concept_in_all_four do CQSRC); a especificação
     CIS gravada (results/CQFIX/cq_spec_cis.jsonl) é a que o código gera e passa no validador do C24;
  2. expected_answers.json: para toda CQ x provedor x variante, a resposta esperada e a leitura declarada são
     idênticas às da especificação (nunca outra); status REALIZED ou NOT_APPLICABLE; todo NOT_APPLICABLE tem
     evidência que confere (schema fixado) ou citação marcada INTERPRETED; toda CQ se aplica (>= 1 variante
     realizada) em ao menos um provedor e cada provedor onde se aplica cobre as 3 variantes (realizada ou NA
     com evidência);
  3. cada realização regenerada passa nas regras estruturais (fxlint): entidades mapeadas, incompletude que
     cobre exatamente o not_read, nada sintetizado sem motivo; e coincide com o que está gravado;
  4. main.tf: todo endereço gravado existe, todo bloco pertence a uma fixture, todo tipo de recurso existe no
     schema fixado, variáveis simbólicas só nas incompletas e sem default, fixture completa não lê variável fx_*;
  5. probes.yaml: uma sonda por fixture realizada, com o mesmo slice;
  6. controles CIS por provedor iguais aos do cis_cross_provider.csv.
Relatório: $BO_DATA/CQFIX/fixture_check.json. Sai 0 só sem achados.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from . import MODULE_ID, PROVIDERS, VARIANTS, data_root, fixtures_dir, now_iso, repo_root, results_dir
from . import build, cis_spec, fxlint, schema_index, spec, tfparse
from .model import Fx

EXPECTED_CIS = 8
EXPECTED_BEYOND = 29


def _req_ids():
    p = repo_root() / "requirements"
    req = {json.loads(ln)["req_id"] for ln in open(p / "requirements.jsonl", encoding="utf-8") if ln.strip()}
    cmt = {json.loads(ln)["commitment_id"] for ln in open(p / "commitments.jsonl", encoding="utf-8") if ln.strip()}
    return req, cmt


def check(root: Path) -> dict:
    errs: list[str] = []
    E = errs.append
    cat = spec.catalog()
    cis = [q for q in cat if q["family"] == "cis"]
    if len(cis) != EXPECTED_CIS or len(cat) - len(cis) != EXPECTED_BEYOND:
        E(f"catálogo com {len(cis)} CIS e {len(cat) - len(cis)} além do CIS (esperado 8 e 29)")
    ctl = cis_spec.cis_controls()
    if set(ctl) != set(cis_spec.CONCEPT_CQ):
        E(f"conceitos CIS nos 4 do CSV {sorted(ctl)} != os do CQFIX {sorted(cis_spec.CONCEPT_CQ)}")
    from bo.requirements.model import validate_cq_spec
    req, cmt = _req_ids()
    for e in validate_cq_spec(list(cis_spec.records()), req, cmt):
        E(f"cq_spec CIS: {e}")
    rec_path = results_dir() / "cq_spec_cis.jsonl"
    want = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in cis_spec.records())
    if not rec_path.is_file() or rec_path.read_text(encoding="utf-8") != want:
        E("results/CQFIX/cq_spec_cis.jsonl difere da especificação gerada")

    ea = json.loads((root / "expected_answers.json").read_text(encoding="utf-8"))
    pr = yaml.safe_load((root / "probes.yaml").read_text(encoding="utf-8"))
    probes = {p["probe_id"]: p for p in pr["probes"]}
    by_q = {q["cq_id"]: q for q in ea["cqs"]}
    if [q["cq_id"] for q in ea["cqs"]] != [q["cq_id"] for q in cat]:
        E("expected_answers.json não lista as CQs do catálogo na ordem")
    res = build.realize_all()
    docs = {p: tfparse.load(root / p / "main.tf") for p in PROVIDERS}
    owned = {p: {} for p in PROVIDERS}
    stats = {p: {"REALIZED": 0, "NOT_APPLICABLE": 0, "evidence_checked": 0, "interpreted_citations": 0}
             for p in PROVIDERS}
    per_cq = {}
    for q in cat:
        qid = q["cq_id"]
        ent = by_q.get(qid)
        if not ent:
            E(f"{qid}: ausente de expected_answers.json")
            continue
        if q["family"] == "cis":
            con = ent.get("cis_concept")
            for p in PROVIDERS:
                got = [(x["control_id"], x["cis_item_id"], x["title"], x["cis_version"])
                       for x in ent.get("cis_controls", {}).get(p, [])]
                if got != ctl.get(con, {}).get("providers", {}).get(p, []):
                    E(f"{qid}/{p}: controles CIS diferem do cis_cross_provider.csv")
                if not got:
                    E(f"{qid}/{p}: conceito CIS sem controle neste provedor")
        applies_somewhere = False
        per_cq[qid] = {}
        for p in PROVIDERS:
            pe = ent["providers"].get(p)
            if not pe:
                E(f"{qid}/{p}: provedor ausente")
                continue
            realized = 0
            for v in VARIANTS:
                x = pe["variants"].get(v)
                if not x:
                    E(f"{qid}/{p}/{v}: variante ausente")
                    continue
                w = f"{qid}/{p}/{v}"
                if x["expected"] != spec.expected(q, v):
                    E(f"{w}: resposta esperada difere da especificação")
                if x["read"] != spec.fixture(q, v)["read"]:
                    E(f"{w}: leitura declarada difere da especificação")
                if x["fixture_id"] != spec.fixture(q, v)["fixture_id"]:
                    E(f"{w}: fixture_id difere")
                if v == "incomplete" and x["expected"].get("value") != "UNKNOWN":
                    E(f"{w}: incompleta sem UNKNOWN")
                r, fid = res[p][qid][v]
                for e in fxlint.lint(q, v, fid, r):
                    E(f"{p}: {e}")
                if x["status"] == "NOT_APPLICABLE":
                    stats[p]["NOT_APPLICABLE"] += 1
                    if isinstance(r, Fx):
                        E(f"{w}: gravado NOT_APPLICABLE mas o realizador realiza")
                    if not x.get("evidence"):
                        E(f"{w}: NOT_APPLICABLE sem evidência")
                    for ev in x.get("evidence", []):
                        why = schema_index.check_evidence(ev)
                        stats[p]["evidence_checked"] += 1
                        if ev["kind"] == "doc_citation":
                            stats[p]["interpreted_citations"] += 1
                        if why:
                            E(f"{w}: evidência não confere: {why}")
                    if all(ev["kind"] == "doc_citation" for ev in x.get("evidence", [])):
                        stats[p].setdefault("na_only_citation", []).append(w)
                    continue
                if x["status"] != "REALIZED":
                    E(f"{w}: status inválido {x['status']!r}")
                    continue
                realized += 1
                stats[p]["REALIZED"] += 1
                if not isinstance(r, Fx):
                    E(f"{w}: gravado REALIZED mas o realizador dá NOT_APPLICABLE")
                    continue
                if x["addresses"] != [b.address for b in r.resources] or x["entity_map"] != r.entity_map \
                        or x["incompleteness"] != r.incompleteness:
                    E(f"{w}: expected_answers.json difere da realização regenerada")
                if not x["addresses"]:
                    E(f"{w}: fixture realizada sem nenhum bloco no main.tf")
                for a in x["addresses"]:
                    if a in owned[p]:
                        E(f"{p}: {a} em duas fixtures ({owned[p][a]}, {fid})")
                    owned[p][a] = fid
                prb = probes.get(x["probe_id"])
                if not prb:
                    E(f"{w}: sonda {x['probe_id']} ausente do probes.yaml")
                elif prb["slice"] != x["addresses"] or prb["fixture_id"] != fid:
                    E(f"{w}: sonda com slice ou fixture diferente")
                for e2 in x["entity_map"].values():
                    if e2.startswith("probe:") and prb and not fxlint._probe_key_exists(prb["inputs"], e2[6:]):
                        E(f"{w}: {e2} sem entrada no probes.yaml")
            if realized:
                applies_somewhere = True
            want_app = "APPLICABLE" if realized == 3 else "NOT_APPLICABLE" if realized == 0 else "PARTIAL"
            if pe.get("applicability") != want_app:
                E(f"{qid}/{p}: applicability {pe.get('applicability')} != {want_app}")
            per_cq[qid][p] = want_app
        if not applies_somewhere:
            E(f"{qid}: não se aplica a nenhum provedor")
        if not any(per_cq[qid].get(p) == "APPLICABLE" for p in PROVIDERS):
            E(f"{qid}: nenhum provedor tem as 3 variantes realizadas")

    for p in PROVIDERS:
        doc = docs[p]
        addrs = {b.address: b for b in doc["blocks"]}
        for a in owned[p]:
            if a not in addrs:
                E(f"{p}: {a} gravado em expected_answers mas ausente do main.tf")
        for a in addrs:
            if a not in owned[p]:
                E(f"{p}: bloco {a} do main.tf não pertence a nenhuma fixture")
        types = schema_index.resource_types(p)
        for b in doc["blocks"]:
            if b.kind == "resource" and b.type not in types:
                E(f"{p}: tipo {b.type} não existe no schema fixado {schema_index.provider_version(p)}")
        text = (root / p / "main.tf").read_text(encoding="utf-8")
        declared = {}
        for vv in doc["variable"]:
            for name, body in vv.items():
                declared[name] = body
        for name, body in declared.items():
            if name.startswith("fx_"):
                if "default" in body:
                    E(f"{p}: variável simbólica {name} com default")
                fid_slug = re.match(r"^(fx_[a-z]+_\d{2}_[cni])_", name)
                if not fid_slug or not fid_slug.group(1).endswith("_i"):
                    E(f"{p}: variável simbólica {name} fora de fixture incompleta")
        for b in doc["blocks"]:
            fid = owned[p].get(b.address, "")
            if fid and not fid.endswith("-I"):
                body = json.dumps(b.body, default=lambda o: getattr(o, "text", str(o)))
                if "var.fx_" in body:
                    E(f"{p}: {b.address} de fixture completa lê variável simbólica")
        if len(probes) == 0:
            E("probes.yaml vazio")
        del text
    n_real = sum(s["REALIZED"] for s in stats.values())
    if len(probes) != n_real:
        E(f"probes.yaml tem {len(probes)} sondas para {n_real} fixtures realizadas")
    return {"schema": "bo.cqfix.fixture_check/1", "module": MODULE_ID, "generated_at": now_iso(), "root": str(root),
            "cq_count": len(cat), "cis_cq_count": len(cis), "providers": stats, "applicability": per_cq,
            "errors": errs, "ok": not errs}


def main(argv=None) -> int:
    argv = [a for a in (sys.argv[1:] if argv is None else argv) if a != MODULE_ID]
    root = Path(argv[0]) if argv else fixtures_dir()
    rep = check(root)
    out = data_root() / MODULE_ID / "fixture_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for e in rep["errors"][:60]:
        print("REPROVA", e)
    s = rep["providers"]
    print("fixture_check: " + "; ".join(f"{p} {s[p]['REALIZED']} realizadas/{s[p]['NOT_APPLICABLE']} NA"
                                        for p in PROVIDERS)
          + f"; {len(rep['errors'])} achado(s) -> {'OK' if rep['ok'] else 'REPROVADO'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
