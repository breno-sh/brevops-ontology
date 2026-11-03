"""Teste da ontologia de topo (S2): BFO 2020, DUL, gUFO e nenhuma, sobre os casos de identidade, tempo e papel.

  python -I -m bo.ontpat.upper_trial --run     roda o teste (HermiT do ROBOT fixado) e grava results/ONTPAT/upper_trial.json
  python -I -m bo.ontpat.upper_trial --check   confere: as 4 candidatas rodaram os 16 casos do REQUIREMENTS (+ extra),
                                               entradas com o mesmo sha, decisão pela regra escrita antes, inferências
                                               esperadas e custo presentes, e RE-EXECUTA o teste: as respostas têm de
                                               sair iguais às gravadas (tempos podem variar)

Cada compromisso com eixo de topo vira uma ou mais variantes (fixture levantada nos padrões do bo) com consultas
cuja consequência o HermiT decide. Para cada candidata o teste roda em dois modos: COMPLETO (bo inteiro) e SEM
EXCLUSÕES (axiomas de exclusão do bo retirados), para medir o que a candidata protege sozinha (regra D3). Cada
variante com mutação roda também a mutação, que tem de virar a resposta: prova que a consulta não passa por
vacuidade.
"""

from __future__ import annotations

import re
import sys
import time
from itertools import combinations
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF

from . import common as c
from . import ontoclean, robot
from . import trial_spec as S

CASE_NS = "https://example.org/bo-trial/case/"
TV = rdflib.Namespace("https://example.org/bo-trial/vocab#")
CAND_NS = {"bfo": "http://purl.obolibrary.org/obo/BFO_", "dul": "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#",
           "gufo": "http://purl.org/nemo/gufo#", "none": None}
RESULT = "upper_trial.json"


# ---------------------------------------------------------------- entradas

def commitments() -> dict:
    out = {}
    for line in (c.repo() / "requirements" / "commitments.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = __import__("json").loads(line)
            out[d["commitment_id"]] = d
    return out


def upper_case_ids(cm: dict) -> list[str]:
    return sorted(k for k, d in cm.items() if d.get("upper_axes"))


def case_prefix(cid: str) -> str:
    return "k" + re.sub(r"[^a-z0-9]", "", cid.lower())


def render(cid: str, ttl: str) -> str:
    return re.sub(r"(?<![A-Za-z0-9_])K:", case_prefix(cid) + ":", ttl)


def case_header(cid: str) -> str:
    return f"@prefix {case_prefix(cid)}: <{CASE_NS}{cid}#> .\n"


def candidate_file(cand: str) -> Path | None:
    rel = S.CANDIDATE_FILES[cand][0]
    return c.data_dir() / "downloads" / rel if rel else None


def cases_path(cand: str) -> Path:
    return c.patterns_dir() / "upper_trial" / cand / "cases.ttl"


def cases_texts() -> dict[Path, str]:
    out = {}
    for cand in c.CANDIDATES:
        al = S.ALIGNMENTS[cand]
        parts = [f"# BrevOps ONTPAT: teste de ontologia de topo, candidata '{cand}' ({S.CANDIDATE_FILES[cand][1]}).\n"
                 "# Gerado por bo.ontpat.build a partir de src/bo/ontpat/trial_spec.py; não editar.\n"
                 "# Não carregar inteiro como uma ontologia só: cada caso (prefixo k...) é um grafo próprio, levantado\n"
                 "# junto com bo-patterns.ttl, a candidata, o alinhamento e o vocabulário de teste (resultados em\n"
                 "# results/ONTPAT/upper_trial.json). As consultas e as mutações estão no JSON.\n",
                 S.PREFIXES,
                 f"\n### alinhamento mínimo ({len(alignment_axioms(cand))} axiomas)\n",
                 al["ttl"] or "# nenhuma: os padrões do bo ficam sem categoria de topo\n"]
        for i, m in enumerate(al["misfits"], 1):
            parts.append(f"# desajuste {i}: {m}\n")
        parts.append("\n### vocabulário de teste e contexto comum\n" + S.TRIAL_TBOX)
        for cid, variants in S.CASES.items():
            parts.append(f"\n### {cid}\n" + case_header(cid))
            for v in variants:
                parts.append(f"# variante {v['variant']}\n" + render(cid, v["fixture"]))
        out[cases_path(cand)] = "".join(parts)
    return out


def alignment_axioms(cand: str) -> list[str]:
    return [ln.split("#")[0].strip() for ln in S.ALIGNMENTS[cand]["ttl"].splitlines() if ln.split("#")[0].strip()]


# ---------------------------------------------------------------- ablação

def _ablate(g: rdflib.Graph) -> rdflib.Graph:
    out = rdflib.Graph()
    out += g
    for p in (OWL.disjointWith, OWL.propertyDisjointWith, OWL.differentFrom, OWL.disjointUnionOf):
        out.remove((None, p, None))
    for t in (OWL.AllDisjointClasses, OWL.AllDifferent, OWL.AllDisjointProperties):
        for b in list(out.subjects(RDF.type, t)):
            for p, o in list(out.predicate_objects(b)):
                out.remove((b, p, o))
    for t in (OWL.IrreflexiveProperty, OWL.AsymmetricProperty):
        out.remove((None, RDF.type, t))
    # listas órfãs (de AllDisjoint/AllDifferent/disjointUnionOf) ficariam como triplas rdf:first/rest soltas: tirar
    changed = True
    while changed:
        changed = False
        for b in list(out.subjects(RDF.first, None)):
            if isinstance(b, rdflib.BNode) and not any(out.subjects(None, b)):
                for p, o in list(out.predicate_objects(b)):
                    out.remove((b, p, o))
                changed = True
    return out


def write_inputs(work: Path) -> dict:
    """Arquivos de trabalho: bo-patterns completo (o próprio), bo-patterns sem exclusões, vocabulário de teste."""
    pdir = c.patterns_dir()
    closure, _ = c.load_closure(pdir / c.PATTERNS)
    for t in list(closure.triples((None, OWL.imports, None))):
        closure.remove(t)
    ab = work / "bo-patterns.ablated.ttl"
    _ablate(closure).serialize(ab, format="turtle")
    tv = work / "trial_tbox.ttl"
    tv.write_text(S.PREFIXES + S.TRIAL_TBOX, encoding="utf-8")
    tvg = rdflib.Graph().parse(tv, format="turtle")
    tva = work / "trial_tbox.ablated.ttl"
    _ablate(tvg).serialize(tva, format="turtle")
    files = {"full": (pdir / c.PATTERNS, tv), "ablated": (ab, tva)}
    for cand in c.CANDIDATES:
        al = work / f"align_{cand}.ttl"
        al.write_text(S.PREFIXES + S.ALIGNMENTS[cand]["ttl"] + "\n", encoding="utf-8")
    return files


# ---------------------------------------------------------------- consultas

def _decl(triples) -> str:
    out, inds, props, classes = [], set(), set(), set()
    for s, p, o in triples:
        inds.add(s)
        if p == "a":
            classes.add(o)
        elif p in ("owl:sameAs", "owl:differentFrom"):
            inds.add(o)
        else:
            props.add(p)
            inds.add(o)
    out += [f"{i} a owl:NamedIndividual ." for i in sorted(inds)]
    out += [f"{p} a owl:ObjectProperty ." for p in sorted(props)]
    out += [f"{k} a owl:Class ." for k in sorted(classes)]
    return "\n".join(out) + "\n"


def query_ttl(cid: str, triples, negate: bool = False) -> str:
    body = []
    if not negate:
        for s, p, o in triples:
            body.append(f"{s} {p} {o} .")
    else:  # só para consultas de uma tripla (UNKNOWN = nem α nem ¬α)
        (s, p, o), = triples
        if p == "owl:sameAs":
            body.append(f"{s} owl:differentFrom {o} .")
        elif p == "owl:differentFrom":
            body.append(f"{s} owl:sameAs {o} .")
        elif p == "a":
            body.append(f"{s} a [ a owl:Class ; owl:complementOf {o} ] .")
        else:
            body.append(f"[] a owl:NegativePropertyAssertion ; owl:sourceIndividual {s} ; owl:assertionProperty {p} ; owl:targetIndividual {o} .")
    return render(cid, S.PREFIXES + case_header(cid) + _decl(triples) + "\n".join(body) + "\n")


def mutate(fixture: str, mut: dict | None) -> tuple[str, str]:
    """Devolve (fixture mutada, TBox extra)."""
    if not mut:
        return fixture, ""
    fx = fixture
    if "replace" in mut:
        a, b = mut["replace"]
        if a not in fx:
            raise ValueError(f"mutação não se aplica: {a!r}")
        fx = fx.replace(a, b)
    for a, b in mut.get("replace_all", []):
        if a not in fx:
            raise ValueError(f"mutação não se aplica: {a!r}")
        fx = fx.replace(a, b)
    fx += mut.get("extra", "")
    return fx, mut.get("tbox", "")


# ---------------------------------------------------------------- montagem e execução

class Plan:
    def __init__(self, work: Path):
        self.work = work
        self.lines: list[str] = []
        self.jobs: dict[str, dict] = {}
        self.n = 0

    def file(self, name: str, text: str) -> Path:
        p = self.work / name
        p.write_text(text, encoding="utf-8")
        return p

    def job(self, jid: str, files: list[Path], meta: dict) -> None:
        self.lines.append(f"JOB\t{jid}\t" + "|".join(str(f) for f in files if f))
        self.jobs[jid] = dict(meta, files=[str(f) for f in files if f], ents={}, dump=None)

    def ent(self, jid: str, key: str, ttl: str) -> None:
        self.n += 1
        p = self.file(f"q{self.n}.ttl", ttl)
        self.lines.append(f"ENT\t{jid}::{key}\t{p}")

    def dump(self, jid: str) -> None:
        p = self.work / f"dump_{jid}.tsv"
        self.lines.append(f"DUMP\t{p}")
        self.jobs[jid]["dump"] = str(p)


def plan_candidate(cand: str, work: Path, inputs: dict) -> Plan:
    pl = Plan(work)
    cf = candidate_file(cand)
    al = work / f"align_{cand}.ttl"
    if cf:
        pl.job(f"{cand}__alone", [cf], {"kind": "alone"})
    pl.job(f"{cand}__example", [c.patterns_dir() / c.EXAMPLE, cf, al], {"kind": "example"})
    for mode in ("full", "ablated"):
        bo_file, tv_file = inputs[mode]
        for cid, variants in S.CASES.items():
            for vi, v in enumerate(variants):
                runs = [("base", None)]
                if mode == "full" and v.get("mutation"):
                    runs.append(("mutation", v["mutation"]))
                for rname, mut in runs:
                    fx, tbox_extra = mutate(v["fixture"], mut)
                    jid = f"{cand}__{mode}__{cid}__{vi}__{rname}"
                    fx_file = pl.file(f"fx_{jid}.ttl", render(cid, S.PREFIXES + case_header(cid) + fx + "\n" + tbox_extra))
                    pl.job(jid, [bo_file, cf, al, tv_file, fx_file],
                           {"kind": "case", "cand": cand, "mode": mode, "case": cid, "variant": vi, "run": rname})
                    need_dump = False
                    for ci, chk in enumerate(v["checks"]):
                        kind = chk[0]
                        if kind in ("ent", "not_ent"):
                            pl.ent(jid, f"{ci}", query_ttl(cid, chk[2]))
                        elif kind == "unknown":
                            pl.ent(jid, f"{ci}", query_ttl(cid, chk[2]))
                            pl.ent(jid, f"{ci}neg", query_ttl(cid, chk[2], negate=True))
                        elif kind in ("count", "ask", "code"):
                            need_dump = True
                            if kind == "count":
                                inds = sorted(set(re.findall(r"(?m)^K:([A-Za-z0-9_]+) a ", fx)))
                                for a, b in combinations(inds, 2):
                                    pl.ent(jid, f"{ci}diff:{a}:{b}", query_ttl(cid, [(f"K:{a}", "owl:differentFrom", f"K:{b}")]))
                    if need_dump:
                        pl.dump(jid)
                    for ci, chk in enumerate(v["checks"]):
                        if chk[0] in ("oc_reject", "oc_accept"):
                            ojid = f"{jid}__oc{ci}"
                            oc_file = pl.file(f"oc_{ojid}.ttl", render(cid, S.PREFIXES + chk[2]))
                            pl.job(ojid, [bo_file, cf, al, tv_file, fx_file, oc_file],
                                   {"kind": "oc", "parent": jid, "check": ci})
                            pl.dump(ojid)
    probe = S.ALIGNMENTS[cand].get("role_probe")
    if probe:
        v = S.CASES["CMT-LB-P04"][0]
        jid = f"{cand}__roleprobe"
        fx_file = pl.file(f"fx_{jid}.ttl", render("CMT-LB-P04", S.PREFIXES + case_header("CMT-LB-P04") + v["fixture"] + probe["ttl"]))
        pl.job(jid, [inputs["full"][0], cf, al, inputs["full"][1], fx_file], {"kind": "roleprobe"})
    return pl


def parse_output(pl: Plan, lines: list[str]) -> None:
    cur = None
    for ln in lines:
        f = ln.split("\t")
        if f[0] == "JOB":
            cur = f[1]
            kv = dict(x.split("=", 1) for x in f[2:])
            pl.jobs[cur].update(consistent=kv["consistent"] == "true", axioms=int(kv["axioms"]),
                                classes=int(kv["classes"]), individuals=int(kv["individuals"]),
                                load_ms=int(kv["load_ms"]), reason_ms=int(kv["reason_ms"]))
        elif f[0] == "ENT":
            jid, key = f[1].split("::", 1)
            ms = int(f[3].split("=")[1])
            pl.jobs[jid]["ents"][key] = f[2]
            pl.jobs[jid]["reason_ms"] = pl.jobs[jid].get("reason_ms", 0) + ms
        elif f[0] == "DUMP":
            pass


def read_dump(path: str) -> dict:
    out = {"types": {}, "same": {}, "sub": set(), "inconsistent": False}
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        f = ln.split("\t")
        if f[0] == "INCONSISTENT":
            out["inconsistent"] = True
        elif f[0] == "TYPE":
            out["types"].setdefault(f[1], set()).add(f[2])
        elif f[0] == "SAME":
            out["same"].setdefault(f[1], set()).add(f[2])
        elif f[0] == "SUB":
            out["sub"].add((rdflib.URIRef(f[1]), rdflib.URIRef(f[2])))
    return out


def graph_of(files: list[str]) -> rdflib.Graph:
    g = rdflib.Graph()
    for f in files:
        p = Path(f)
        if p.name == c.PATTERNS:
            cl, _ = c.load_closure(p)
            g += cl
        else:
            g.parse(p, format="turtle")
    return g


# ---------------------------------------------------------------- avaliação

def reason_label(g: rdflib.Graph, r) -> str:
    for o in g.objects(r, rdflib.RDFS.label):
        return str(o)
    return str(r)


def evaluate_variant(pl: Plan, jid: str, v: dict, cid: str, cm: dict) -> dict:
    J = pl.jobs[jid]
    exp = cm["expected_answer"]
    res = []
    for ci, chk in enumerate(v["checks"]):
        kind, label = chk[0], chk[1]
        r = {"check": label, "kind": kind}
        if kind in ("ent", "not_ent"):
            got = J["ents"].get(str(ci))
            r["entailed"] = got
            r["pass"] = (got == "true") if kind == "ent" else (got == "false")
            r["observed"] = {"true": "ENTAILED", "false": "NOT_ENTAILED"}.get(got, got.upper() if got else "MISSING")
        elif kind == "unknown":
            a, n = J["ents"].get(str(ci)), J["ents"].get(f"{ci}neg")
            r["entailed"], r["negation_entailed"] = a, n
            r["observed"] = "UNKNOWN" if (a, n) == ("false", "false") else ("ENTAILED" if a == "true" and n == "false" else
                            ("REFUTED" if n == "true" and a == "false" else "INCONSISTENT" if not J["consistent"] else "ERROR"))
            r["pass"] = r["observed"] == "UNKNOWN"
        elif kind == "consistent":
            r["observed"] = "CONSISTENT" if J["consistent"] else "INCONSISTENT"
            r["pass"] = J["consistent"]
        elif kind == "inconsistent":
            r["observed"] = "REJECTED" if not J["consistent"] else "ACCEPTED"
            r["pass"] = not J["consistent"]
        elif kind in ("oc_reject", "oc_accept"):
            O = pl.jobs[f"{jid}__oc{ci}"]
            if not O["consistent"]:
                r["observed"], r["pass"] = "INCONSISTENT", False
            else:
                d = read_dump(O["dump"])
                g = graph_of(O["files"])
                rep = ontoclean.check(ontoclean.rigidity_map(g), d["sub"] | ontoclean.asserted_pairs(g))
                r["violations"] = [f"{a.split('#')[-1]} ⊑ {b.split('#')[-1]} ({ra} sob {rb})" for a, b, ra, rb in rep.violations]
                r["observed"] = "REJECTED" if rep.violations else "ACCEPTED"
                r["pass"] = (r["observed"] == "REJECTED") if kind == "oc_reject" else (r["observed"] == "ACCEPTED")
        elif kind == "count":
            cls = chk[2][0].replace("tv:", str(TV))
            if not J["consistent"]:
                r["observed"], r["pass"] = "INCONSISTENT", False
            else:
                d = read_dump(J["dump"])
                pre = f"{CASE_NS}{cid}#"
                members = sorted(i for i, ts in d["types"].items() if i.startswith(pre) and cls in ts)
                groups = []
                for m in members:
                    if not any(m in gset for gset in groups):
                        groups.append({m} | d["same"].get(m, set()))
                reps = [sorted(gs)[0] for gs in groups]
                exact = all(J["ents"].get(f"{ci}diff:{a.split('#')[1]}:{b.split('#')[1]}",
                                          J["ents"].get(f"{ci}diff:{b.split('#')[1]}:{a.split('#')[1]}")) == "true"
                            for a, b in combinations(reps, 2))
                r["members"] = [m.split("#")[1] for m in reps]
                r["observed"] = len(reps) if exact else "UNKNOWN"
                r["pass"] = r["observed"] == exp["value"]
        elif kind == "ask":
            q, want = chk[2]
            if not J["consistent"]:
                r["observed"], r["pass"] = "INCONSISTENT", False
            else:
                g = graph_of(J["files"])
                d = read_dump(J["dump"])
                for i, ts in d["types"].items():
                    for t in ts:
                        g.add((rdflib.URIRef(i), RDF.type, rdflib.URIRef(t)))
                ans = bool(g.query(S.PREFIXES.replace("@prefix", "PREFIX").replace(" .\n", "\n") + q).askAnswer)
                r["observed"], r["pass"] = ans, ans == want
        elif kind == "code":
            unit, desc = chk[2]
            g = graph_of(J["files"])
            pref = rdflib.URIRef(f"{CASE_NS}{cid}#")
            u = rdflib.URIRef(str(pref) + unit.split(":")[1])
            dsc = c.BO[desc.split(":")[1]]
            codes = sorted(reason_label(g, rr) for m in g.subjects(c.BO.markerOf, u) if (m, c.BO.of, dsc) in g
                           for rr in g.objects(m, c.BO.unknownReason))
            r["observed"] = codes[0] if len(codes) == 1 else (codes or "NONE")
            r["pass"] = r["observed"] == exp.get("code")
        res.append(r)
    return {"consistent": J["consistent"], "checks": res, "pass": all(x["pass"] for x in res),
            "axioms": J.get("axioms"), "reason_ms": J.get("reason_ms")}


def expected_inferences(pl: Plan, cand: str) -> dict:
    ns = CAND_NS[cand]
    if not ns:
        return {"count": 0, "by_class": {}, "examples": []}
    by_class, examples, total = {}, [], 0
    for jid, J in pl.jobs.items():
        if J.get("kind") != "case" or J.get("mode") != "full" or J.get("run") != "base" or not J.get("consistent"):
            continue
        if not J.get("dump"):
            continue
        d = read_dump(J["dump"])
        for i, ts in d["types"].items():
            if not i.startswith(CASE_NS):
                continue
            for t in ts:
                if t.startswith(ns):
                    total += 1
                    k = t[len(ns):] if cand != "bfo" else "BFO_" + t[len(ns):]
                    by_class[k] = by_class.get(k, 0) + 1
                    if len(examples) < 8:
                        examples.append(f"{i.split('/')[-1]} a {k}")
    return {"count": total, "by_class": dict(sorted(by_class.items())), "examples": examples}


def run_candidate(cand: str, cm: dict, work: Path, inputs: dict) -> dict:
    pl = plan_candidate(cand, work, inputs)
    # DUMP de todas as variantes base do modo completo, para as inferências esperadas
    extra = []
    for jid, J in pl.jobs.items():
        if J.get("kind") == "case" and J["mode"] == "full" and J["run"] == "base" and not J["dump"]:
            extra.append(jid)
    lines = []
    for ln in pl.lines:
        lines.append(ln)
    jobs_file = work / f"jobs_{cand}.tsv"
    # insere DUMP logo depois das ENT do job (a diretiva DUMP age sobre o job corrente)
    out_lines, cur = [], None
    for ln in lines:
        if ln.startswith("JOB\t") and cur in extra:
            p = work / f"dump_{cur}.tsv"
            out_lines.append(f"DUMP\t{p}")
            pl.jobs[cur]["dump"] = str(p)
        if ln.startswith("JOB\t"):
            cur = ln.split("\t")[1]
        out_lines.append(ln)
    if cur in extra:
        p = work / f"dump_{cur}.tsv"
        out_lines.append(f"DUMP\t{p}")
        pl.jobs[cur]["dump"] = str(p)
    jobs_file.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    t0 = time.monotonic()
    out = robot.harness(jobs_file, work / f"out_{cand}.tsv")
    wall = time.monotonic() - t0
    parse_output(pl, out)

    cases, modes = {}, {"full": {}, "ablated": {}}
    for cid, variants in S.CASES.items():
        for mode in ("full", "ablated"):
            vs = []
            for vi, v in enumerate(variants):
                ev = evaluate_variant(pl, f"{cand}__{mode}__{cid}__{vi}__base", v, cid, cm[cid])
                ev["variant"] = v["variant"]
                if mode == "full" and v.get("mutation"):
                    mev = evaluate_variant(pl, f"{cand}__{mode}__{cid}__{vi}__mutation", v, cid, cm[cid])
                    fi = v["mutation"]["flips"]
                    ev["mutation"] = {"label": v["mutation"]["label"],
                                      "observed": mev["checks"][fi]["observed"],
                                      "flipped": mev["checks"][fi]["pass"] != ev["checks"][fi]["pass"]}
                vs.append(ev)
            modes[mode][cid] = {"pass": all(x["pass"] for x in vs), "variants": vs}
    for cid in S.CASES:
        exp = cm[cid]["expected_answer"]
        full = modes["full"][cid]
        cases[cid] = {
            "axes": cm[cid].get("upper_axes", []), "extra": cid in S.EXTRA_CASES,
            "expected": {k: exp[k] for k in ("value", "code") if k in exp},
            "observed": exp["value"] if full["pass"] else "DIVERGE: " + "; ".join(
                f"{ch['check']}={ch['observed']}" for v in full["variants"] for ch in v["checks"] if not ch["pass"]),
            "reproduces": full["pass"], "reproduces_without_bo_exclusions": modes["ablated"][cid]["pass"],
            "variants": full["variants"],
            "ablated_variants": [{"variant": v["variant"], "pass": v["pass"],
                                  "checks": [{"check": ch["check"], "observed": ch["observed"], "pass": ch["pass"]} for ch in v["checks"]]}
                                 for v in modes["ablated"][cid]["variants"]],
        }
    case_jobs = [J for J in pl.jobs.values() if J.get("kind") == "case" and J["mode"] == "full" and J["run"] == "base"]
    axioms_typical = sorted(J["axioms"] for J in case_jobs)[len(case_jobs) // 2]
    ex = pl.jobs[f"{cand}__example"]
    probe = S.ALIGNMENTS[cand].get("role_probe")
    probe_res = None
    if probe:
        J = pl.jobs[f"{cand}__roleprobe"]
        probe_res = {"label": probe["label"], "consistent": J["consistent"]}
        if probe["expect"] == "punning":
            from . import no_punning
            g = graph_of(J["files"][-2:])  # vocabulário de teste + fixture com a sonda
            probe_res["punning"] = [str(x) for x in no_punning.punned(g)]
    return {
        "candidate": cand, "label": S.CANDIDATE_FILES[cand][1],
        "file": f"$BO_DATA/downloads/{S.CANDIDATE_FILES[cand][0]}" if S.CANDIDATE_FILES[cand][0] else None,
        "file_sha256": c.sha256_file(candidate_file(cand)) if candidate_file(cand) else None,
        "alignment_axioms": alignment_axioms(cand),
        "misfits": S.ALIGNMENTS[cand]["misfits"],
        "cases": cases,
        "reproduced": sum(1 for v in cases.values() if v["reproduces"]),
        "reproduced_without_bo_exclusions": sum(1 for v in cases.values() if v["reproduces_without_bo_exclusions"]),
        "mutations_flipped": sum(1 for v in cases.values() for vv in v["variants"] if vv.get("mutation", {}).get("flipped")),
        "mutations_total": sum(1 for v in cases.values() for vv in v["variants"] if vv.get("mutation")),
        "expected_inferences": expected_inferences(pl, cand),
        "role_probe": probe_res,
        "example_abox_consistent": ex["consistent"],
        "cost": {
            "candidate_axioms": pl.jobs.get(f"{cand}__alone", {}).get("axioms", 0),
            "closure_axioms_typical_case": axioms_typical,
            "closure_axioms_example_abox": ex["axioms"],
            "alignment_axioms": len(alignment_axioms(cand)),
            "misfits": len(S.ALIGNMENTS[cand]["misfits"]),
            "hermit_ms_total": sum(J.get("reason_ms", 0) for J in pl.jobs.values()),
            "harness_wall_s": round(wall, 1),
            "jobs": len(pl.jobs),
        },
    }


def decide(res: dict) -> dict:
    none_abl = {cid for cid, v in res["none"]["cases"].items() if v["reproduces_without_bo_exclusions"]}
    rows = {}
    for cand, r in res.items():
        d1 = r["reproduced"] == len(S.CASES)
        prof = r["profile"]
        d2 = prof["in_profile"] and r["example_abox_consistent"] and not r["alignment_punning"]
        own = sorted(cid for cid, v in r["cases"].items() if v["reproduces_without_bo_exclusions"] and cid not in none_abl)
        rows[cand] = {"D1_reproduz_todos": d1, "D2_dl_consistente_sem_punning": d2, "D3_protecoes_proprias": own,
                      "D4_custo": [r["cost"]["misfits"], r["cost"]["closure_axioms_typical_case"], r["cost"]["hermit_ms_total"]]}
    elig = [k for k, v in rows.items() if v["D1_reproduz_todos"] and v["D2_dl_consistente_sem_punning"]]
    if not elig:
        return {"rule_version": S.DECISION_RULE_VERSION, "rows": rows, "eligible": [], "chosen": None,
                "why": "nenhuma candidata elegível em D1/D2"}
    best3 = max(len(rows[k]["D3_protecoes_proprias"]) for k in elig)
    top = [k for k in elig if len(rows[k]["D3_protecoes_proprias"]) == best3]
    top.sort(key=lambda k: rows[k]["D4_custo"])
    chosen = top[0]
    step = "D3" if len(top) == 1 else "D4"
    why = (f"elegíveis em D1/D2: {', '.join(elig)}; maior número de proteções próprias (D3) = {best3} "
           f"({', '.join(top)}); decidido em {step}" + (f" pelo custo (desajustes, axiomas, ms) = {rows[chosen]['D4_custo']}" if step == "D4" else ""))
    return {"rule_version": S.DECISION_RULE_VERSION, "rows": rows, "eligible": elig, "tied_after_D3": top,
            "chosen": chosen, "decided_at_step": step, "why": why}


def inputs_digest() -> dict:
    pdir = c.patterns_dir()
    out = {"$BO_REPO/ontology/patterns/bo-patterns.ttl": c.sha256_file(pdir / c.PATTERNS),
           "$BO_REPO/ontology/patterns/descriptor-pattern.ttl": c.sha256_file(pdir / c.DESCRIPTOR),
           "$BO_REPO/ontology/patterns/example-abox.ttl": c.sha256_file(pdir / c.EXAMPLE),
           "$BO_REPO/requirements/commitments.jsonl": c.sha256_file(c.repo() / "requirements" / "commitments.jsonl"),
           "$BO_REPO/src/bo/ontpat/trial_spec.py": c.sha256_file(Path(S.__file__)),
           "$BO_REPO/src/bo/ontpat/java/TrialReasoner.java": c.sha256_file(Path(__file__).resolve().parent / "java" / "TrialReasoner.java")}
    for cand in c.CANDIDATES:
        out[f"$BO_REPO/ontology/patterns/upper_trial/{cand}/cases.ttl"] = c.sha256_file(cases_path(cand))
    return out


def run_all() -> dict:
    cm = commitments()
    ids = upper_case_ids(cm)
    missing = [i for i in ids if i not in S.CASES]
    if missing:
        raise RuntimeError("compromissos com eixo de topo sem caso no teste: " + ", ".join(missing))
    work = c.tmp_dir() / "upper_trial"
    if work.exists():
        for p in work.iterdir():
            p.unlink()
    work.mkdir(parents=True, exist_ok=True)
    inputs = write_inputs(work)
    from . import no_punning
    res = {}
    for cand in c.CANDIDATES:
        c.emit(f"[{c.now()}] candidata {cand}")
        r = run_candidate(cand, cm, work, inputs)
        files = [c.patterns_dir() / c.PATTERNS] + ([candidate_file(cand)] if candidate_file(cand) else []) + [work / f"align_{cand}.ttl"]
        r["profile"] = robot.validate_profile(files, cand)
        ag = rdflib.Graph().parse(work / f"align_{cand}.ttl", format="turtle")
        r["alignment_punning"] = [str(x) for x in no_punning.punned(ag)]
        res[cand] = r
    dec = decide(res)
    return {
        "schema": "bo.upper_trial/1", "module": "ONTPAT", "generated_at": c.now(),
        "decision_rule": {"version": S.DECISION_RULE_VERSION, "written_at": S.DECISION_RULE_WRITTEN_AT,
                          "items": [{"id": a, "text": b} for a, b in S.DECISION_RULE],
                          "ablation": {"predicates": S.ABLATED_PREDICATES, "types": S.ABLATED_TYPES, "other": S.ABLATED_OTHER}},
        "case_ids": ids, "extra_case_ids": list(S.EXTRA_CASES),
        "axes_count": {ax: sum(1 for i in ids if ax in cm[i]["upper_axes"]) for ax in ("identity", "time", "role")},
        "toolchain": {k: robot.pins()[k]["version"] for k in ("robot", "hermit", "elk", "owlapi")},
        "inputs": inputs_digest(),
        "candidates": res,
        "decision": dec,
    }


# ---------------------------------------------------------------- conferência

def answers_view(doc: dict) -> dict:
    out = {}
    for cand, r in doc["candidates"].items():
        out[cand] = {cid: (v["reproduces"], v["reproduces_without_bo_exclusions"],
                           [vv.get("mutation", {}).get("flipped") for vv in v["variants"]]) for cid, v in r["cases"].items()}
        out[cand]["_profile"] = r["profile"]["in_profile"]
        out[cand]["_example"] = r["example_abox_consistent"]
        out[cand]["_infer"] = r["expected_inferences"]["count"]
    out["_chosen"] = doc["decision"]["chosen"]
    return out


def check(rerun: bool = True) -> list[str]:
    bad = []
    p = c.results_dir() / RESULT
    if not p.exists():
        return [f"{p} ausente"]
    doc = c.read_json(p)
    cm = commitments()
    ids = upper_case_ids(cm)
    if doc.get("case_ids") != ids:
        bad.append("casos com eixo de topo divergem do REQUIREMENTS")
    if len(ids) != 16:
        bad.append(f"esperados 16 compromissos com eixo de topo, há {len(ids)}")
    if set(doc.get("candidates", {})) != set(c.CANDIDATES):
        bad.append("as 4 candidatas não estão todas no resultado")
    for cand, r in doc.get("candidates", {}).items():
        miss = [i for i in ids if i not in r.get("cases", {})]
        if miss:
            bad.append(f"{cand}: casos sem resultado: {miss}")
        if "expected_inferences" not in r or "cost" not in r:
            bad.append(f"{cand}: sem inferências esperadas ou custo")
        for k in ("candidate_axioms", "closure_axioms_typical_case", "alignment_axioms", "misfits", "hermit_ms_total"):
            if k not in r.get("cost", {}):
                bad.append(f"{cand}: custo sem {k}")
        if r.get("mutations_flipped") != r.get("mutations_total"):
            bad.append(f"{cand}: mutação que não virou a resposta ({r.get('mutations_flipped')}/{r.get('mutations_total')}): consulta vácua")
    if doc.get("inputs") != inputs_digest():
        bad.append("entradas mudaram desde a execução (sha256): rode --run de novo")
    dec = doc.get("decision", {})
    if not dec.get("chosen") or dec.get("rule_version") != S.DECISION_RULE_VERSION:
        bad.append("decisão ausente ou com regra de outra versão")
    elif decide(doc["candidates"]) != dec:
        bad.append("a decisão gravada não é a que a regra produz sobre os resultados gravados")
    html = c.patterns_dir() / "UPPER_DECISION.html"
    if not html.exists():
        bad.append("UPPER_DECISION.html ausente")
    else:
        from . import docs
        if html.read_text(encoding="utf-8") != docs.upper_decision_html(doc):
            bad.append("UPPER_DECISION.html não é o gerado a partir de upper_trial.json")
    if rerun and not bad:
        new = run_all()
        if answers_view(new) != answers_view(doc):
            bad.append("re-execução deu respostas diferentes das gravadas")
    return bad


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--run" in argv:
        doc = run_all()
        c.write_json(c.results_dir() / RESULT, doc)
        d = doc["decision"]
        for cand, r in doc["candidates"].items():
            c.emit(f"{cand}: reproduz {r['reproduced']}/{len(S.CASES)}; sem exclusões do bo {r['reproduced_without_bo_exclusions']}; "
                   f"mutações viradas {r['mutations_flipped']}/{r['mutations_total']}; DL={r['profile']['in_profile']}; "
                   f"inferências da candidata {r['expected_inferences']['count']}; custo {r['cost']}")
        c.emit(f"decisão: {d['chosen']} ({d['why']})")
        return 0
    if "--check" in argv:
        bad = check(rerun="--no-rerun" not in argv)
        for b in bad:
            c.emit("FALHA: " + b)
        if not bad:
            doc = c.read_json(c.results_dir() / RESULT)
            c.emit(f"upper_trial ok: 4 candidatas x {len(doc['case_ids'])} casos (+{len(doc['extra_case_ids'])} extra), "
                   f"decisão {doc['decision']['chosen']} ({doc['decision']['decided_at_step']}), re-execução idêntica")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
