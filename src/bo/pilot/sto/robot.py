"""Conferência do módulo OWL da fatia pelo ROBOT fixado (ontology/patterns/toolchain_pins.json), offline.

  1. perfil OWL 2 DL do fecho (módulo c3 + bo-patterns.ttl + descriptor-pattern.ttl), robot validate-profile;
  2. HermiT: TBox coerente e ABox agregado das fixtures de calibração consistente; as classes inferidas e as
     arestas appliesTo dos indivíduos nomeados contêm as do raciocinador RL do pipeline (mesmas consequências);
  3. HermiT: um ABox que o RL acusa de conflito (funcional/disjunção) é inconsistente também.
Uso: python -I -m bo.pilot.sto.robot [--out DIR]   (sai 0 se as três conferências passam)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF

from . import abox as A
from . import common as C
from . import lift as L
from . import pipeline as PL


def pins() -> dict:
    return C.read_json(C.repo() / "ontology" / "patterns" / "toolchain_pins.json")


def robot_cmd() -> list[str]:
    p = pins()["robot"]
    jar = Path(p["jar_path"].replace("$BO_DATA", str(C.data_root())))
    if not jar.exists():
        raise RuntimeError(f"robot.jar ausente: {C.portable(jar)}")
    h = hashlib.sha256(jar.read_bytes()).hexdigest()
    if h != p["jar_sha256"]:
        raise RuntimeError("robot.jar com sha diferente do fixado")
    java = pins()["java"]["path"]
    return [java, "-jar", str(jar)]


def catalog(out: Path) -> Path:
    """Catálogo XML: o IRI de import do módulo resolve para o arquivo local do ONTPAT (sem rede)."""
    pat = C.repo() / "ontology" / "patterns"
    cat = out / "catalog-v001.xml"
    cat.write_text('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
                   '<catalog prefer="public" xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">\n'
                   f'  <uri name="https://w3id.org/brevops/ontology/patterns/0.1.0" uri="file:{pat / "bo-patterns.ttl"}"/>\n'
                   f'  <uri name="https://w3id.org/brevops/ontology/patterns" uri="file:{pat / "bo-patterns.ttl"}"/>\n'
                   '</catalog>\n', encoding="utf-8")
    return cat


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    cat = cwd / "catalog-v001.xml"
    pre = ["--catalog", str(cat)] if cat.exists() else []
    return subprocess.run(robot_cmd() + pre + args, cwd=cwd, capture_output=True, text=True, timeout=900)


def to_rdf(triples: set, g: Graph) -> None:
    for s, p, o in triples:
        if o.startswith("L:"):
            v = json.loads(o[2:])
            g.add((URIRef(s), URIRef(p), Literal(v if isinstance(v, str) else C.canon(v))))
        else:
            g.add((URIRef(s), URIRef(p), URIRef(o)))
            if p != A.TYPE:
                g.add((URIRef(o), RDF.type, OWL.NamedIndividual))
        g.add((URIRef(s), RDF.type, OWL.NamedIndividual))


def check(out: Path | None = None) -> dict:
    out = out or (C.tmp_dir() / "robot")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ctx = PL.prepare(out_dir=out / "owl")
    catalog(out)
    pat = C.repo() / "ontology" / "patterns"
    mod = out / "owl" / "sto-c3_full.ttl"
    rep = {"robot": pins()["robot"]["version"], "hermit": pins()["hermit"]["version"]}
    m = run(["merge", "--input", str(mod), "--input", str(pat / "bo-patterns.ttl"), "--input",
             str(pat / "descriptor-pattern.ttl"), "--output", str(out / "closure.owl")], out)
    if m.returncode:
        return {**rep, "ok": False, "stage": "merge", "tail": (m.stderr + m.stdout)[-600:]}
    prof = run(["validate-profile", "--input", str(out / "closure.owl"), "--profile", "DL",
                "--output", str(out / "profile.txt")], out)
    rep["profile_dl"] = prof.returncode == 0
    rep["profile_tail"] = (out / "profile.txt").read_text(encoding="utf-8")[-400:] if (out / "profile.txt").exists() else prof.stderr[-400:]
    # ABox agregado (consistente pelo RL) e um caso com conflito
    exp = C.read_json(C.repo() / "pilot" / "sto" / "expected_answers.json")
    agg, clash, rl_types, rl_applies = Graph(), None, {}, {}
    for fid, f in sorted(exp["fixtures"].items()):
        fx = C.read_json(C.repo() / f["file"])
        lf = L.lift(fx, ctx.claims, ctx.evidence)
        tr, iri = A.abox_of(lf)
        cl = A.reason(tr, ctx.tbox["c3_full"])
        if cl.clashes:
            if clash is None:
                clash = (fid, tr)
            continue
        to_rdf(tr, agg)
        for (s, p, o) in cl.triples:
            if p == A.TYPE and o.startswith(A.S("")):
                rl_types.setdefault(s, set()).add(o)
            if p == A.S("appliesTo"):
                rl_applies.setdefault(s, set()).add(o)
    agg.add((URIRef("https://w3id.org/brevops/ontology/sto/abox-calib"), RDF.type, OWL.Ontology))
    agg.serialize(out / "abox.ttl", format="turtle")
    mg = run(["merge", "--input", str(out / "closure.owl"), "--input", str(out / "abox.ttl"),
              "--output", str(out / "merged_abox.owl")], out)
    if mg.returncode:
        return {**rep, "ok": False, "stage": "merge_abox", "tail": (mg.stderr + mg.stdout)[-600:]}
    rs = run(["reason", "--input", str(out / "merged_abox.owl"), "--reasoner", "hermit", "--axiom-generators",
              "ClassAssertion PropertyAssertion", "--include-indirect", "true", "--output", str(out / "reasoned.ttl")], out)
    rep["abox_consistent"] = rs.returncode == 0
    if rs.returncode:
        rep["reason_tail"] = (rs.stderr + rs.stdout)[-600:]
        return {**rep, "ok": False}
    hg = Graph()
    hg.parse(out / "reasoned.ttl", format="turtle")
    missing_t, missing_a = 0, 0
    for s, ts in rl_types.items():
        ht = {str(o) for o in hg.objects(URIRef(s), RDF.type)}
        missing_t += len(ts - ht)
    for s, os_ in rl_applies.items():
        ha = {str(o) for o in hg.objects(URIRef(s), URIRef(A.S("appliesTo")))}
        missing_a += len(os_ - ha)
    rep.update({"rl_type_assertions": sum(len(v) for v in rl_types.values()), "rl_types_missing_in_hermit": missing_t,
                "rl_applies": sum(len(v) for v in rl_applies.values()), "rl_applies_missing_in_hermit": missing_a})
    if clash:
        cg = Graph()
        to_rdf(clash[1], cg)
        cg.add((URIRef("https://w3id.org/brevops/ontology/sto/abox-clash"), RDF.type, OWL.Ontology))
        cg.serialize(out / "clash.ttl", format="turtle")
        run(["merge", "--input", str(out / "closure.owl"), "--input", str(out / "clash.ttl"),
             "--output", str(out / "merged_clash.owl")], out)
        rc = run(["explain", "--input", str(out / "merged_clash.owl"), "--reasoner", "hermit", "-M", "inconsistency",
                  "--explanation", str(out / "clash_explanation.md")], out)
        expl = (out / "clash_explanation.md").read_text(encoding="utf-8") if (out / "clash_explanation.md").exists() else ""
        rep["clash_fixture"] = clash[0]
        rep["clash_inconsistent_in_hermit"] = "SubClassOf [Nothing]" in expl
        rep["clash_explanation_axioms"] = sum(1 for x in expl.splitlines() if x.startswith("  - "))
    else:
        rep["clash_inconsistent_in_hermit"] = None
    rep["ok"] = bool(rep["profile_dl"] and rep["abox_consistent"] and missing_t == 0 and missing_a == 0
                     and rep["clash_inconsistent_in_hermit"] in (True, None))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot.sto.robot", description=__doc__)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rep = check(Path(a.out) if a.out else None)
    C.write_json(PL.stage_dir() / "robot_report.json", {**rep, "generated_at": C.now()})
    print(f"[{C.now()}] robot: " + json.dumps({k: v for k, v in rep.items() if not k.endswith("tail")}, ensure_ascii=False))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
