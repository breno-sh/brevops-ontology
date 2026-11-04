"""Gerador do módulo OWL da fatia sto (C14 3.0.0) a partir das alegações OK do PILOT-STO-MAP.

Saídas (em $BO_DATA/PILOT-STO-E2E/owl/, regeneração idêntica para a mesma entrada):
  sto-c3_full.ttl       módulo completo: classes, propriedades, domínios por união, disjunções, funcionais, cadeias
                        de alcance efetivo e os descritores de realização (padrão de descritor do ONTPAT, sem punning)
  sto-c2_taxonomy.ttl   o mesmo vocabulário só com taxonomia (subClassOf/subPropertyOf) e descritores
  sto-c1_table.ttl      a tabela das correspondências OK em RDF (sem nenhum axioma de classe ou propriedade)
  classes.jsonl, properties.jsonl, realizations.jsonl   tabelas do C14
O módulo importa os padrões do ONTPAT (ontology/patterns/bo-patterns.ttl) por IRI de documento; o perfil OWL 2 DL
do fecho de imports é conferido pelo ROBOT fixado (bo.pilot.sto.robot).
"""

from __future__ import annotations

from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from . import common as C
from . import tbox as T

STO = Namespace(T.STO)
BO = Namespace(T.BO)
STODESC = Namespace("https://w3id.org/brevops/ontology/sto/descriptor#")
CORR = Namespace("https://w3id.org/brevops/ontology/sto/correspondence#")
MODULE_IRI = URIRef("https://w3id.org/brevops/ontology/sto")
PATTERNS_DOC = "https://w3id.org/brevops/ontology/patterns/0.1.0"

OBJECT_PROPS = {
    "facetOfContainer": ("bo:facetOf", "StorageSetting", "ObjectContainer", "faceta de configuração de um contêiner"),
    "facetOfNamespace": ("bo:facetOf", "StorageSetting", "StorageNamespace", "faceta de configuração de um espaço de nomes"),
    "facetOfAccount": ("bo:facetOf", "StorageSetting", None, "faceta de configuração da conta (contexto)"),
    "inScope": (None, "ObjectContainer", None, "contêiner dentro de um espaço de nomes ou conta"),
    "hasContainer": (None, None, "ObjectContainer", "espaço de nomes ou conta que contém o contêiner"),
    "scopeAnchor": (None, "StorageSetting", None, "nó cujo conteúdo inteiro a configuração alcança"),
    "appliesTo": (None, "StorageSetting", "ObjectContainer", "contêiner que a configuração efetivamente alcança"),
    "hasRule": (None, "LifecycleSetting", "LifecycleRule", "regra de uma configuração de ciclo de vida"),
    "selectsContainer": (None, "LifecycleRule", "ObjectContainer", "contêiner selecionado pelo filtro da regra"),
}


def _c(name: str) -> URIRef:
    if name.startswith("bo:"):
        return BO[name[3:]]
    if name.startswith("sto:"):
        return STO[name[4:]]
    return STO[name]


def concept_props(concepts: list[str]) -> list[str]:
    return sorted({T.prop_local(c) for c in concepts if T.concept_class(c)})


def build_graph(level: str, concepts: list[str], realizations: list[dict]) -> Graph:
    """level: c2_taxonomy | c3_full."""
    g = Graph()
    g.bind("sto", STO), g.bind("bo", BO), g.bind("owl", OWL), g.bind("stod", STODESC)
    g.add((MODULE_IRI, RDF.type, OWL.Ontology))
    g.add((MODULE_IRI, OWL.imports, URIRef(PATTERNS_DOC)))
    g.add((MODULE_IRI, RDFS.comment, Literal(f"Módulo da fatia sto do PILOT-STO-E2E, nível {level}; gerado de alegações OK.", lang="pt")))
    for name, d in T.CLASSES.items():
        g.add((STO[name], RDF.type, OWL.Class))
        g.add((STO[name], RDFS.label, Literal(d["label"], lang="pt")))
        g.add((STO[name], RDFS.subClassOf, _c(d["parent"])))
    for name, (sup, dom, rng, label) in OBJECT_PROPS.items():
        p = STO[name]
        g.add((p, RDF.type, OWL.ObjectProperty))
        g.add((p, RDFS.label, Literal(label, lang="pt")))
        if sup:
            g.add((p, RDFS.subPropertyOf, _c(sup)))
    g.add((STO.facetOfContainer, RDFS.subPropertyOf, STO.appliesTo))
    props = concept_props(concepts)
    for pl in props:
        p = STO[pl]
        g.add((p, RDF.type, OWL.DatatypeProperty))
        g.add((p, RDFS.label, Literal(pl.replace("_", " "), lang="pt")))
    if level == "c3_full":
        _axioms(g, props)
    # descritores (padrão de descritor do ONTPAT: o indivíduo descritor, nunca o IRI da propriedade, é citado)
    for pl in props:
        d = STODESC["desc_" + pl]
        g.add((d, RDF.type, OWL.NamedIndividual))
        g.add((d, RDF.type, BO.PropertyDescriptor))
        g.add((d, BO.descriptorKey, Literal(pl)))
        g.add((d, BO.describesProperty, STO[pl]))
    fid_ind = {"Lossless": BO.Lossless, "DeclaredLoss": BO.DeclaredLoss, "PartialTransport": BO.PartialTransport,
               "NoTransport": BO.NoTransport}
    for r in realizations:
        # padrão P7/P8 do ONTPAT: realização (nó n-ário) -> bo:realizedBy -> artefato do provedor
        key = r["realization_id"].replace(":", "_").replace(".", "_")
        ri, art = STODESC["real_" + key], STODESC["art_" + key]
        g.add((ri, RDF.type, OWL.NamedIndividual))
        g.add((ri, RDF.type, BO.Realization))
        g.add((ri, BO.of, STODESC["desc_" + r["of"]["descriptor_key"]]))
        g.add((ri, BO.realizedBy, art))
        g.add((ri, BO.liftingFidelity, fid_ind[r["lifting_fidelity"]]))
        g.add((ri, BO.loweringFidelity, fid_ind[r["lowering_fidelity"]]))
        g.add((art, RDF.type, OWL.NamedIndividual))
        g.add((art, RDF.type, BO.ProviderArtifact))
        g.add((art, BO.artifactName, Literal(r["realized_by"][0]["artifact_name"])))
        if r["realized_by"][0].get("artifact_path"):
            g.add((art, BO.artifactPath, Literal(r["realized_by"][0]["artifact_path"])))
    return g


def _axioms(g: Graph, props: list[str]) -> None:
    """Axiomas que só o c3 carrega."""
    def chain(sup, a, b):
        lst = BNode()
        Collection(g, lst, [STO[a], STO[b]])
        g.add((STO[sup], OWL.propertyChainAxiom, lst))

    def disjoint(names):
        n = BNode()
        lst = BNode()
        Collection(g, lst, [_c(x) for x in names])
        g.add((n, RDF.type, OWL.AllDisjointClasses))
        g.add((n, OWL.members, lst))

    disjoint(["StorageNamespace", "ObjectContainer"])
    disjoint(T.SETTING_CLASSES)
    disjoint(["sto:StorageSetting", "sto:LifecycleRule", "sto:ObjectContainer", "sto:StorageNamespace"])
    g.add((STO.hasContainer, OWL.inverseOf, STO.inScope))
    chain("appliesTo", "scopeAnchor", "hasContainer")
    chain("appliesTo", "hasRule", "selectsContainer")
    for name, (sup, dom, rng, _) in OBJECT_PROPS.items():
        if dom:
            g.add((STO[name], RDFS.domain, STO[dom]))
        if rng:
            g.add((STO[name], RDFS.range, STO[rng]))
    for name in ("facetOfContainer", "facetOfNamespace", "facetOfAccount"):
        g.add((STO[name], RDF.type, OWL.FunctionalProperty))
    for pl in props:
        cls = T.CONCEPT_CLASS[pl]
        g.add((STO[pl], RDFS.domain, STO[cls]))
        if pl in T.FUNCTIONAL:
            g.add((STO[pl], RDF.type, OWL.FunctionalProperty))


def table_graph(ok_claims) -> Graph:
    """c1: as correspondências OK como RDF (sem axioma). Cada linha vira um nó com sujeito, objeto, relação SKOS
    na direção correta, fidelidade e a transformação."""
    g = Graph()
    g.bind("corr", CORR), g.bind("skos", SKOS)
    for cl in ok_claims:
        n = CORR[cl.claim_id.replace(":", "_")]
        g.add((n, CORR.subject, Literal(cl.subject_id)))
        g.add((n, CORR.object, Literal(cl.object_id)))
        g.add((n, CORR.predicate, URIRef(SKOS + cl.predicate_id.split(":", 1)[1]) if cl.predicate_id.startswith("skos:")
               else Literal(cl.predicate_id)))
        g.add((n, CORR.transportFidelity, Literal(cl.transport_fidelity)))
        g.add((n, CORR.translationFn, Literal(C.canon(cl.row.get("translation_fn")))))
        g.add((n, CORR.lossContract, Literal(C.canon(cl.row.get("loss_contract") or []))))
        g.add((n, CORR.guard, Literal(C.canon(cl.row.get("guard") or {"all": []}))))
    return g


# ----------------------------------------------------------------------------------------------------------
# tabelas do C14
# ----------------------------------------------------------------------------------------------------------
def classes_rows() -> list[dict]:
    out = []
    for name, d in T.CLASSES.items():
        role = "Resource" if d["kind"] == "ENTITY" else "ConfigurationDescription"
        row = {"class_id": "sto:" + name, "label": d["label"], "definition": d["definition"],
               "parents": [{"iri": d["parent"], "kind": "nested"}], "model_role": role, "status": "active",
               "evidence_state": "STRUCTURALLY_VALID"}
        if d["kind"] == "ENTITY":
            row["identity"] = {"composite": True, "fields": ["synthetic_account", "provider", "location", "type", "local_key"]}
        out.append(row)
    return out


def properties_rows(concepts: list[str], glossary: dict[str, dict]) -> list[dict]:
    out = []
    for pl in concept_props(concepts):
        g = glossary.get("concept:" + pl, {})
        out.append({"property_id": "sto:" + pl, "label": g.get("label") or pl.replace("_", " "), "kind": "datatype",
                    "domain": {"kind": "single", "class": "sto:" + T.CONCEPT_CLASS[pl]}, "range": "rdfs:Literal",
                    "definition": g.get("definition") or f"valor do conceito {pl} da fatia sto",
                    "value_marks": ["configured", "default", "inferred"], "unknown_marks": ["unknown", "absent", "not_read", "withheld"],
                    "status": "active", "evidence_state": "STRUCTURALLY_VALID"})
    for name, (sup, dom, rng, label) in OBJECT_PROPS.items():
        row = {"property_id": "sto:" + name, "label": label, "kind": "object",
               "domain": {"kind": "single", "class": "sto:" + (dom or "StorageSetting")},
               "range": "sto:" + (rng or "StorageNamespace"),
               "definition": f"{label} (estrutura da fatia; usada pelo lowering e pelo alcance efetivo)",
               "value_marks": ["configured", "inferred"], "unknown_marks": ["unknown", "absent"], "status": "active",
               "evidence_state": "STRUCTURALLY_VALID"}
        out.append(row)
    return out


FID = {"lossless": "Lossless", "declared_loss": "DeclaredLoss", "partial": "PartialTransport", "none": "NoTransport"}
EST = {"STRUCTURALLY_VALID": "StructurallyValid", "DOC_SUPPORTED": "DocSupported", "PERSISTENCE_VERIFIED": "PersistenceVerified",
       "OBSERVATION_TESTED": "ObservationTested", "UNRESOLVED": "Unresolved"}


def realization_rows(ok_claims, concept_of) -> list[dict]:
    """Uma realização por (provedor, átomo) de conceito com classe, das alegações OK (os dois lados)."""
    seen: dict[str, dict] = {}
    for cl in ok_claims:
        for atom, other in ((cl.subject_id, cl.object_id), (cl.object_id, cl.subject_id)):
            concept = concept_of(atom)
            if not T.concept_class(concept):
                continue
            pl = T.prop_local(concept)
            prov, rtype, path = atom.split(":", 2)
            rid = f"r_{prov}_{rtype}_{path}".replace(".", "_")
            fid = FID.get(cl.transport_fidelity, "NoTransport")
            losses = sorted({("LOSS_" + (x.get("kind") or "semantic").upper()) for x in (cl.row.get("loss_contract") or [])
                             if isinstance(x, dict)})
            if fid in ("DeclaredLoss", "PartialTransport") and not losses:
                losses = ["PARTIAL_TRANSPORT"]
            row = seen.get(rid)
            if row is None:
                row = {"realization_id": rid, "of": {"descriptor_key": pl, "kind": "property", "describes": T.STO + pl},
                       "provider": prov, "realized_by": [{"artifact_name": rtype, "artifact_path": path, "schema": f"{prov}@terraform"}],
                       "lifting_fidelity": fid, "lowering_fidelity": fid,
                       "evidence_state": EST.get(cl.row.get("evidence_state") or "", "Unresolved"),
                       "derived_from": [], "generated_by": "PILOT-STO-E2E/owl", "attributed_to": C.MODULE}
                if losses:
                    row["losses"] = losses
                ref = T.REF_FIELD.get(rtype)
                if ref:
                    row["references"] = [{"from_artifact": rtype, "to_artifact": "owner", "via_field": ref[0]}]
                seen[rid] = row
            row["derived_from"] = sorted(set(row["derived_from"]) | {cl.claim_id})
            if fid == "Lossless" and row["lowering_fidelity"] != "Lossless":
                pass
    return [seen[k] for k in sorted(seen)]


def build_module(claims, glossary: dict[str, dict], out_dir: Path) -> dict:
    ok = claims.ok_claims()
    concepts = sorted(set(claims.concept_of.values()) | set(glossary))
    reals = realization_rows(ok, claims.concept)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for level in ("c2_taxonomy", "c3_full"):
        g = build_graph(level, concepts, reals)
        p = out_dir / f"sto-{level}.ttl"
        p.write_text(_ttl(g), encoding="utf-8")
        files[level] = p
    p = out_dir / "sto-c1_table.ttl"
    p.write_text(_ttl(table_graph(ok)), encoding="utf-8")
    files["c1_table"] = p
    C.write_jsonl(out_dir / "classes.jsonl", classes_rows())
    C.write_jsonl(out_dir / "properties.jsonl", properties_rows(concepts, glossary))
    C.write_jsonl(out_dir / "realizations.jsonl", reals)
    return {"files": {k: C.portable(v) for k, v in files.items()}, "ok_claims": len(ok), "realizations": len(reals),
            "properties": len(concept_props(concepts))}


def _ttl(g: Graph) -> str:
    """Turtle determinístico: N-Triples (subconjunto do Turtle) com nós em branco de rótulo canônico
    (rdflib.compare) e linhas ordenadas; a mesma entrada dá os mesmos bytes."""
    from rdflib.compare import to_canonical_graph
    cg = to_canonical_graph(g)
    lines = sorted(x for x in cg.serialize(format="nt").splitlines() if x.strip())
    head = ("# Módulo OWL da fatia sto (PILOT-STO-E2E), gerado por bo.pilot.sto.owl; não editar à mão.\n"
            "# Fatia sintética: nenhum nome, conta ou valor real. Formato: N-Triples ordenado (Turtle válido).\n")
    return head + "\n".join(lines) + "\n"
