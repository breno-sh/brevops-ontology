"""Os três controles de raciocínio sobre a MESMA ABox levantada.

  c1_table     nenhuma inferência: o Knowledge fica vazio (o translate só tem os átomos e as alegações)
  c2_taxonomy  ABox com os tipos das realizações e os fatos estruturais + TBox só com classes, propriedades e
               rdfs:subClassOf; fecho pela semântica RDFS do owlrl (versão do requirements.lock)
  c3_full      a mesma ABox + TBox com o catálogo de axiomas; HermiT pelo ROBOT fixado (toolchain_pins.json do
               ONTPAT), geradores ClassAssertion e PropertyAssertion; depois as formas SHACL (pyshacl)

A ABox é a mesma nos dois controles que a usam (mesma entrada); o c1 não usa ABox porque o controle é a tabela.
Saída: Knowledge por fixture. Resultado do HermiT em cache por sha256 da entrada, em $BO_TMP/reason_cache.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import rdflib
from rdflib import RDF, Literal, Namespace, URIRef

from . import axioms as AX
from . import owlgen
from .knowledge import Knowledge

BO = Namespace("https://w3id.org/brevops/ontology#")
EX = Namespace("https://example.org/bo-example/")
ROBOT_VERSION = "1.9.11"
WATCH = {"hasEffect": "effect", "hasDirection": "direction", "hasConnectionTracking": "state",
         "hasNoMatchIngress": "no_match_ingress", "hasNoMatchEgress": "no_match_egress", "hasPrecedenceOrder": "precedence", "hasTieBreak": "tie_break",
         "hasPriorityRule": "priority_rule"}
VALUE_NEUTRAL = {"Allow": "allow", "Deny": "deny", "Ingress": "ingress", "Egress": "egress", "Stateful": "stateful",
                 "Stateless": "stateless", "OrderIndependent": "order_independent",
                 "LowerValueFirst": "lower_value_first", "DenyOverAllow": "deny_over_allow",
                 "UniquePerCollection": "unique_per_collection"}


class ReasonerError(RuntimeError):
    pass


def ind_iri(fixture_id: str, local: str) -> URIRef:
    return EX[f"{fixture_id.lower().replace('-', '_')}__{local}"]


def local_of(iri) -> tuple[str, str]:
    s = str(iri)[len(str(EX)):]
    fx, local = s.split("__", 1)
    return fx, local


# --------------------------------------------------------------------------------------------- ABox

def abox(lifted: list, structural: bool) -> rdflib.Graph:
    """ABox comum (c2 e c3). structural=False devolve só os indivíduos tipados como regra/conjunto, sem fatos
    estruturais nem tipos de realização (não é usada pelo c1, mas fica para os testes de igualdade de entrada)."""
    g = rdflib.Graph()
    g.bind("bo", BO)
    g.bind("ex", EX)
    for L in lifted:
        fx = L.fixture_id
        for sid, s in L.sets.items():
            si = ind_iri(fx, sid)
            g.add((si, RDF.type, rdflib.OWL.NamedIndividual))
            for c in (AX.REALIZATION_CLASSES.get(s.kind, ["bo:FilterRuleSet"]) if structural else ["bo:FilterRuleSet"]):
                g.add((si, RDF.type, BO[c.split(":")[1]]))
            for rid in s.rules:
                g.add((si, BO.hasRule, ind_iri(fx, rid)))
        for rid, r in L.rules.items():
            ri = ind_iri(fx, rid)
            g.add((ri, RDF.type, rdflib.OWL.NamedIndividual))
            key = r.tf["resource_type"] if "block_path" not in r.tf else (r.tf["resource_type"], r.tf["block_path"])
            for c in (AX.RULE_REALIZATION_CLASSES.get(key, ["bo:FilterRule"]) if structural else ["bo:FilterRule"]):
                g.add((ri, RDF.type, BO[c.split(":")[1]]))
            if not structural:
                continue
            d = r.facts.get("direction")
            if d is not None and d.known() and d.value in ("ingress", "egress"):
                g.add((ri, BO.hasDirection, BO[d.value.capitalize()]))
            e = r.facts.get("effect")
            if e is not None and e.known() and e.value in ("allow", "deny"):
                g.add((ri, BO.hasEffect, BO[e.value.capitalize()]))
            st = r.facts.get("stateless")
            if st is not None:
                if st.status == "known":
                    g.add((ri, RDF.type, BO.StateDeclaredRule))
                    g.add((ri, RDF.type, BO.StatelessTrueRule if st.value else BO.StatelessFalseRule))
                elif st.status == "absent":
                    g.add((ri, RDF.type, BO.StateNotDeclaredRule))
            p = r.facts.get("priority")
            if p is not None and p.known() and isinstance(p.value, int):
                g.add((ri, BO.rulePriority, Literal(p.value)))
        for i, a in enumerate(L.attachments):
            if a.set_id is None:
                continue
            ai = ind_iri(fx, f"att_{i}")
            g.add((ai, RDF.type, rdflib.OWL.NamedIndividual))
            g.add((ai, RDF.type, BO.RuleSetAttachment))
            g.add((ai, BO.attachesRuleSet, ind_iri(fx, a.set_id)))
            ei = ind_iri(fx, f"ep_{a.endpoint}")
            g.add((ei, RDF.type, rdflib.OWL.NamedIndividual))
            g.add((ei, RDF.type, BO.NetworkEndpoint))
            g.add((ai, BO.attachesEndpoint, ei))
    return g


def nt_sorted(g: rdflib.Graph) -> str:
    """N-Triples em ordem estável (a serialização do rdflib não fixa ordem): hash e cache determinísticos."""
    return "\n".join(sorted(l for l in g.serialize(format="nt").splitlines() if l.strip())) + "\n"


def input_sha(lifted: list) -> str:
    return hashlib.sha256(nt_sorted(abox(lifted, True)).encode()).hexdigest()


# --------------------------------------------------------------------------------------------- controles

def run(control: str, lifted: list, cs=None, tmp: Path | None = None) -> dict:
    """fixture_id -> Knowledge do controle."""
    if control == "c1_table":
        return {L.fixture_id: Knowledge(control) for L in lifted}
    if control == "c2_taxonomy":
        return _c2(lifted, cs)
    if control == "c3_full":
        return _c3(lifted, cs, tmp)
    raise ValueError(control)


def _collect(g: rdflib.Graph, lifted: list, control: str, asserted: rdflib.Graph) -> dict:
    out = {L.fixture_id: Knowledge(control, structural=True) for L in lifted}
    for s, p, o in g:
        if not str(s).startswith(str(EX)):
            continue
        fx_low, local = local_of(s)
        fid = next((f for f in out if f.lower().replace("-", "_") == fx_low), None)
        if fid is None:
            continue
        K = out[fid]
        if p == RDF.type and str(o).startswith(str(BO)):
            K.types.setdefault(local, set()).add("bo:" + str(o)[len(str(BO)):])
        elif str(p).startswith(str(BO)) and str(p)[len(str(BO)):] in WATCH:
            prop = WATCH[str(p)[len(str(BO)):]]
            val = VALUE_NEUTRAL.get(str(o)[len(str(BO)):], str(o))
            prev = K.values.setdefault(local, {}).get(prop)
            if prev is not None and prev != val:
                K.values[local][prop] = "CONFLICT"
            else:
                K.values[local][prop] = val
            if (s, p, o) in asserted:
                K.why.setdefault((local, prop), []).append("realização (fato estrutural ou codec do átomo)")
            else:
                K.why[(local, prop)] = _justify(prop, val)
    for K in out.values():
        for (local, prop) in list(K.why):
            if prop.startswith("no_match") and K.why[(local, prop)] and K.why[(local, prop)][0].startswith("AX-"):
                K.why[(local, prop)] = (["AX-NET-12"] if "bo:ImpliedRulesRuleSet" in K.types.get(local, set())
                                        else ["AX-NET-03"])
    return out


def _justify(prop: str, val: str) -> list:
    if prop == "effect":
        return ["AX-NET-01", "AX-NET-10"]
    if prop.startswith("no_match"):
        return ["AX-NET-12"] if val == "allow" else ["AX-NET-03", "AX-NET-12"]
    if prop == "precedence":
        return ["AX-NET-02"] if val == "order_independent" else ["AX-NET-04"]
    if prop == "tie_break":
        return ["AX-NET-05"]
    if prop == "state":
        return ["AX-NET-07", "AX-NET-08", "AX-NET-11"]
    if prop == "priority_rule":
        return ["AX-NET-06"]
    return AX.for_entailment(prop)


def _c2(lifted: list, cs) -> dict:
    import owlrl
    tb = rdflib.Graph().parse(data=owlgen.tbox_ttl("c2_taxonomy", cs), format="turtle")
    ab = abox(lifted, True)
    g = tb + ab
    owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(g)
    return _collect(g, lifted, "c2_taxonomy", ab)


def robot_bin() -> str:
    p = shutil.which("robot") or str(Path.home() / ".local/bin/robot")
    if not Path(p).exists():
        raise ReasonerError("ROBOT não encontrado (toolchain_pins.json do ONTPAT)")
    return p


def robot_version() -> str:
    out = subprocess.run([robot_bin(), "--version"], capture_output=True, text=True, timeout=120)
    return out.stdout.strip()


def hermit(ttl: str, tmp: Path) -> rdflib.Graph:
    tmp.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(ttl.encode()).hexdigest()
    cache = tmp / f"{sha}.reasoned.ttl"
    if not cache.exists():
        inp = tmp / f"{sha}.in.ttl"
        inp.write_text(ttl, encoding="utf-8")
        part = tmp / f"{sha}.partial.ttl"
        env = {"PATH": "/usr/bin:/bin:/opt/homebrew/opt/openjdk@17/bin", "HOME": str(tmp),
               "TMPDIR": str(tmp), "JAVA_TOOL_OPTIONS": f"-Djava.io.tmpdir={tmp}"}
        r = subprocess.run([robot_bin(), "reason", "--reasoner", "HermiT", "--axiom-generators",
                            "ClassAssertion PropertyAssertion", "--include-indirect", "true",
                            "--input", str(inp), "--output", str(part)],
                           capture_output=True, text=True, timeout=600, env=env)
        if r.returncode != 0:
            msg = (r.stderr or r.stdout)[-600:]
            if "inconsistent" in msg.lower() or "unsatisfiable" in msg.lower():
                raise InconsistentError(msg)
            raise ReasonerError(msg)
        part.rename(cache)
    return rdflib.Graph().parse(cache, format="turtle")


class InconsistentError(ReasonerError):
    pass


def _c3(lifted: list, cs, tmp: Path | None) -> dict:
    tmp = tmp or Path(os.environ.get("BO_TMP", ".")) / "reason_cache"
    tb = owlgen.tbox_ttl("c3_full", cs)
    ab = abox(lifted, True)
    out = {}
    try:
        g = hermit(tb + nt_sorted(ab), tmp)
        out = _collect(g, lifted, "c3_full", ab)
        reasoned = g
    except InconsistentError:
        # isola: uma fixture inconsistente não derruba as outras
        reasoned = rdflib.Graph()
        for L in lifted:
            abL = abox([L], True)
            try:
                gL = hermit(tb + nt_sorted(abL), tmp)
                out.update(_collect(gL, [L], "c3_full", abL))
                reasoned += gL
            except InconsistentError as e:
                K = Knowledge("c3_full", structural=True, consistent=False)
                K.violations["*"] = [f"ABox inconsistente no HermiT: {str(e)[-200:]}"]
                out[L.fixture_id] = K
    _shacl(reasoned, lifted, out)
    return out


def _shacl(g: rdflib.Graph, lifted: list, out: dict) -> None:
    import pyshacl
    shapes = rdflib.Graph().parse(data=AX.SHAPES_TTL, format="turtle")
    conforms, rg, _ = pyshacl.validate(g, shacl_graph=shapes, inference="none", advanced=True)
    if conforms:
        return
    SH = Namespace("http://www.w3.org/ns/shacl#")
    for res in rg.subjects(RDF.type, SH.ValidationResult):
        focus = rg.value(res, SH.focusNode)
        msg = str(rg.value(res, SH.resultMessage) or "violação SHACL")
        if focus is None or not str(focus).startswith(str(EX)):
            continue
        fx_low, local = local_of(focus)
        for fid, K in out.items():
            if fid.lower().replace("-", "_") == fx_low:
                K.violations.setdefault(local, []).append(msg)
