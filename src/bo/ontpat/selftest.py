"""Selftest do grão nos padrões (CMT-NIC-P01, P02, P03): VM com 2 NICs = 3 indivíduos; com 1 NIC = 2; mesma
estrutura de relações.

  python -I -m bo.ontpat.selftest

A fixture é montada com os padrões (interface = recurso com identidade própria; anexação = vínculo reificado
com índice) e levada ao HermiT do ROBOT fixado junto com o fecho de bo-patterns.ttl. A contagem é por
CONSEQUÊNCIA: indivíduos nomeados inferidos bo:Resource, agrupados por sameAs inferido, e exata só se cada par
é inferido distinto. A estrutura é o conjunto de assinaturas (tipos mais específicos do sujeito, propriedade,
tipos mais específicos do objeto) das relações entre unidades. Controle: com a interface como bloco sem
identidade (atributo da instância), a contagem tem de cair, senão o teste não discrimina.
"""

from __future__ import annotations

import sys
from itertools import combinations

import rdflib
from rdflib.namespace import OWL, RDF

from . import common as c
from . import robot
from . import trial_spec as S
from . import upper_trial as U

CID = "SELFTEST-NIC"
TBOX = """
tv:attachesInterface a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:subPropertyOf bo:relates ; rdfs:domain tv:NicAttachment ; rdfs:range tv:NetworkInterface .
tv:attachesTo a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:subPropertyOf bo:relates ; rdfs:domain tv:NicAttachment ; rdfs:range tv:ComputeInstance .
tv:deviceIndex a owl:DatatypeProperty , owl:FunctionalProperty ; rdfs:domain tv:NicAttachment ; rdfs:range xsd:nonNegativeInteger .
tv:NicAttachment a owl:Class ; rdfs:subClassOf bo:Binding ; bo:rigidity bo:Rigid ; owl:hasKey ( tv:attachesInterface tv:attachesTo ) .
tv:inSubnet a owl:ObjectProperty ; rdfs:subPropertyOf bo:references .
tv:Subnet a owl:Class ; rdfs:subClassOf bo:IndependentResource ; bo:rigidity bo:Rigid .
tv:nicBlock a owl:DatatypeProperty .
"""


def fixture(n: int, as_block: bool = False) -> str:
    out = [f"K:vm1 a owl:NamedIndividual , tv:ComputeInstance ; {S.ident(ptype='tv:pt_instance', key='vm_a', inc='inc-vm1')} .",
           f"K:sa a owl:NamedIndividual , tv:Subnet ; {S.ident(ptype='tv:pt_instance', key='subnet_a', inc='inc-sa')} ."]
    for i in range(n):
        if as_block:  # controle: interface como bloco sem identidade, atributo literal da instância
            out.append(f'K:vm1 tv:nicBlock "device_index={i}" .')
            continue
        out.append(f"K:nic{i + 1} a owl:NamedIndividual , tv:NetworkInterface , bo:IndependentResource ; "
                   f"{S.ident(ptype='tv:pt_instance', key=f'nic_{i}', inc=f'inc-nic{i + 1}')} ; tv:inSubnet K:sa .")
        out.append(f"K:att{i + 1} a owl:NamedIndividual , tv:NicAttachment ; tv:attachesInterface K:nic{i + 1} ; "
                   f"tv:attachesTo K:vm1 ; tv:deviceIndex {i} .")
    return "\n".join(out) + "\n"


def run() -> dict:
    work = c.tmp_dir() / "selftest"
    work.mkdir(parents=True, exist_ok=True)
    for p in work.iterdir():
        p.unlink()
    inputs = U.write_inputs(work)
    base = U._nt(inputs["full"][0]) + U._nt(U._ttl_graph(S.PREFIXES + S.TRIAL_TBOX + TBOX))
    pl = U.Plan(work)
    variants = {"n2": fixture(2), "n1": fixture(1), "ctl_block2": fixture(2, as_block=True)}
    for name, fx in variants.items():
        fx_nt = U._nt(U._ttl_graph(U.render(CID, S.PREFIXES + U.case_header(CID) + fx)))
        jid = f"self__{name}"
        pl.job(jid, [pl.file(f"job_{jid}.nt", base + fx_nt)], {"kind": "self", "fx": fx})
        inds = sorted(set(__import__("re").findall(r"(?m)^K:([A-Za-z0-9_]+) a ", fx)))
        for a, b in combinations(inds, 2):
            pl.ent(jid, f"diff:{a}:{b}", U.query_ttl(CID, [(f"K:{a}", "owl:differentFrom", f"K:{b}")]))
        pl.dump(jid)
    U.parse_output(pl, robot.harness(work / "jobs.tsv", work / "out.tsv") if _write_jobs(pl, work) else [])
    out = {}
    pre = f"{U.CASE_NS}{CID}#"
    for name in variants:
        J = pl.jobs[f"self__{name}"]
        d = U.read_dump(J["dump"])
        out[name] = {"consistent": J["consistent"],
                     "resources": count(d, J, pre, {str(U.TV.ComputeInstance), str(U.TV.NetworkInterface)}),
                     "attachments": count(d, J, pre, {str(U.TV.NicAttachment)}),
                     "structure": structure(d, J["fx"], pre)}
    return out


def _write_jobs(pl, work) -> bool:
    (work / "jobs.tsv").write_text("\n".join(pl.lines) + "\n", encoding="utf-8")
    return True


def count(d: dict, J: dict, pre: str, classes: set):
    members = sorted(i for i, ts in d["types"].items() if i.startswith(pre) and classes & ts)
    groups = []
    for m in members:
        if not any(m in g for g in groups):
            groups.append({m} | d["same"].get(m, set()))
    reps = [sorted(g)[0].split("#")[1] for g in groups]
    exact = all(J["ents"].get(f"diff:{a}:{b}", J["ents"].get(f"diff:{b}:{a}")) == "true" for a, b in combinations(reps, 2))
    return len(reps) if exact else "UNKNOWN"


def most_specific(d: dict, ind: str) -> tuple:
    ts = {t for t in d["types"].get(ind, set()) if t.startswith((str(c.BO), str(U.TV)))}
    sub = d["sub"]
    keep = [t for t in ts if not any((rdflib.URIRef(o), rdflib.URIRef(t)) in sub and o != t and o in ts for o in ts)]
    return tuple(sorted(x.split("#")[1] for x in keep))


def structure(d: dict, fx: str, pre: str) -> list:
    g = U._ttl_graph(U.render(CID, S.PREFIXES + U.case_header(CID) + fx))
    sig = set()
    for s, p, o in g:
        if p == RDF.type or not isinstance(o, rdflib.URIRef) or not str(o).startswith(pre):
            continue
        sig.add((most_specific(d, str(s)), str(p).split("#")[1], most_specific(d, str(o))))
    return sorted(sig)


def main(argv=None) -> int:
    r = run()
    n2, n1, ctl = r["n2"], r["n1"], r["ctl_block2"]
    checks = [
        ("VM com 2 NICs = 3 recursos (instância + interfaces, como no CMT-NIC-P01)", n2["resources"] == 3, n2["resources"]),
        ("VM com 2 NICs = 2 anexações", n2["attachments"] == 2, n2["attachments"]),
        ("VM com 1 NIC = 2 recursos", n1["resources"] == 2, n1["resources"]),
        ("VM com 1 NIC = 1 anexação", n1["attachments"] == 1, n1["attachments"]),
        ("mesma estrutura de relações (1 e 2 NICs)", n1["structure"] == n2["structure"], len(n2["structure"])),
        ("as três leituras são consistentes", n1["consistent"] and n2["consistent"] and ctl["consistent"], None),
        ("controle: NIC como bloco sem identidade não conta 3 (o teste discrimina)", ctl["resources"] != 3, ctl["resources"]),
    ]
    for label, ok, val in checks:
        c.emit(f"{'ok  ' if ok else 'FALHA'} {label}" + (f" (medido: {val})" if val is not None else ""))
    c.emit("assinaturas: " + "; ".join(f"{a}-{p}->{b}" for a, p, b in n2["structure"]))
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
