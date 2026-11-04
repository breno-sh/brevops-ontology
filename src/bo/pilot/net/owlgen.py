"""Módulo OWL da fatia NET e tabelas C14 (classes, propriedades, realizações), gerados das alegações OK.

O que entra:
  * classes neutras do vocabulário dos compromissos (C24: conjunto, regra, anexação, seleção, ponto de anexação)
    e as classes de realização (lista de permissão, conjunto por precedência...), com a taxonomia do axioms.py;
  * uma propriedade por conceito do glossário que aparece numa alegação OK (subject_concept/object_concept); a
    propriedade sem alegação OK não entra (não há prova de que algum provedor a realiza);
  * uma realização por (provedor, átomo) de alegação OK: o átomo realiza a propriedade do seu conceito;
  * as realizações estruturais (construção -> classe) e o catálogo de axiomas, cada um com a sua evidência.
Controle: TBox do c2 = classes + taxonomia + propriedades; TBox do c3 = isso + axiomas (restrições, valores,
funcionais, disjunções). O c1 não tem TBox.

Sem trocadilho (C14-PUN): valores controlados (bo:Allow, bo:Ingress...) são indivíduos e nunca classes; o descritor
de realização liga a entidade por anotação (bo:describesProperty / bo:describesClass), como no ONTPAT.
"""

from __future__ import annotations

import json

from . import axioms as AX
from . import vocab as V

PREFIXES = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix bo: <https://w3id.org/brevops/ontology#> .
@prefix ex: <https://example.org/bo-example/> .
"""
ONTOLOGY_IRI = "https://w3id.org/brevops/ontology/net-pilot"
VERSION_IRI = "https://w3id.org/brevops/ontology/net-pilot/0.1.0"

CLASSES = {
    "bo:FilterRuleSet": ("conjunto de regras de filtragem", "Conjunto de regras de filtragem é uma configuração que "
                         "reúne regras de tráfego avaliadas juntas e anexadas por inteiro.", []),
    "bo:FilterRule": ("regra de filtragem", "Regra de filtragem é uma configuração que liga uma condição sobre "
                      "fluxos de rede a um efeito.", []),
    "bo:RuleSetAttachment": ("anexação de conjunto", "Anexação de conjunto é um vínculo que faz o tráfego de um ponto "
                             "de rede passar pela avaliação de um conjunto de regras.", []),
    "bo:RuleTargetSelection": ("seleção de alvo da regra", "Seleção de alvo é um vínculo que restringe a regra aos "
                               "membros da rede que carregam um rótulo.", []),
    "bo:NetworkEndpoint": ("ponto de rede", "Ponto de rede é um recurso cujo tráfego passa pelos conjuntos anexados "
                           "(interface, sub-rede ou instância).", []),
    "bo:PermissionListRuleSet": ("conjunto lista de permissão", "Conjunto lista de permissão é um conjunto de regras "
                                 "cujas regras só podem permitir.", ["bo:FilterRuleSet"]),
    "bo:PrecedenceRuleSet": ("conjunto por precedência", "Conjunto por precedência é um conjunto de regras em que a "
                             "regra de maior precedência decide entre permitir e negar.", ["bo:FilterRuleSet"]),
    "bo:DenyTieRuleSet": ("conjunto com desempate por negação", "Conjunto com desempate por negação é um conjunto por "
                          "precedência em que, na mesma prioridade, negar vence.", ["bo:PrecedenceRuleSet"]),
    "bo:UniquePriorityRuleSet": ("conjunto de prioridade única", "Conjunto de prioridade única é um conjunto por "
                                 "precedência em que duas regras do mesmo sentido não repetem prioridade.",
                                 ["bo:PrecedenceRuleSet"]),
    "bo:NoMatchDenyRuleSet": ("conjunto que nega sem regra", "Conjunto que nega sem regra é um conjunto de regras em "
                              "que o fluxo sem regra que case é negado.", ["bo:FilterRuleSet"]),
    "bo:IngressRule": ("regra de entrada", "Regra de entrada é uma regra de filtragem sobre tráfego que chega.",
                       ["bo:FilterRule"]),
    "bo:EgressRule": ("regra de saída", "Regra de saída é uma regra de filtragem sobre tráfego que sai.",
                      ["bo:FilterRule"]),
    "bo:AllowingRule": ("regra que permite", "Regra que permite é uma regra de filtragem cujo efeito é permitir.",
                        ["bo:FilterRule"]),
    "bo:DenyingRule": ("regra que nega", "Regra que nega é uma regra de filtragem cujo efeito é negar.",
                       ["bo:FilterRule"]),
    "bo:DeclaredDefaultStateRule": ("regra com estado padrão publicado", "Regra com estado padrão publicado é uma "
                                    "regra de filtragem cujo atributo de estado tem padrão publicado.",
                                    ["bo:FilterRule"]),
    "bo:StateDeclaredRule": ("regra com estado declarado", "Regra com estado declarado é uma regra de filtragem cuja "
                             "configuração declara o estado de conexão.", []),
    "bo:StateNotDeclaredRule": ("regra sem estado declarado", "Regra sem estado declarado é uma regra de filtragem "
                                "cuja configuração não declara o estado de conexão.", []),
    "bo:StatelessTrueRule": ("regra declarada sem estado", "Regra declarada sem estado é uma regra de filtragem cuja "
                             "configuração declara que ela não rastreia conexão.", []),
    "bo:StatelessFalseRule": ("regra declarada com estado", "Regra declarada com estado é uma regra de filtragem cuja "
                              "configuração declara que ela rastreia conexão.", []),
    "bo:ControlledValue": ("valor controlado", "Valor controlado é um indivíduo que nomeia um valor do protocolo "
                           "(efeito, sentido, estado, ordem).", []),
}
OBJECT_PROPS = {
    "bo:hasRule": ("tem regra", "bo:FilterRuleSet", "bo:FilterRule"),
    "bo:hasEffect": ("tem efeito", "bo:FilterRule", "bo:ControlledValue"),
    "bo:hasDirection": ("tem sentido", "bo:FilterRule", "bo:ControlledValue"),
    "bo:hasConnectionTracking": ("tem rastreio de conexão", "bo:FilterRule", "bo:ControlledValue"),
    "bo:hasNoMatchDecision": ("tem decisão sem regra", "bo:FilterRuleSet", "bo:ControlledValue"),
    "bo:hasPrecedenceOrder": ("tem ordem de precedência", "bo:FilterRuleSet", "bo:ControlledValue"),
    "bo:hasTieBreak": ("tem desempate", "bo:FilterRuleSet", "bo:ControlledValue"),
    "bo:hasPriorityRule": ("tem regra de prioridade", "bo:FilterRuleSet", "bo:ControlledValue"),
    "bo:attachesRuleSet": ("anexa conjunto", "bo:RuleSetAttachment", "bo:FilterRuleSet"),
    "bo:attachesEndpoint": ("anexa ponto", "bo:RuleSetAttachment", "bo:NetworkEndpoint"),
}
DATA_PROPS = {"bo:rulePriority": ("prioridade da regra", "bo:FilterRule", "xsd:integer")}


def concept_properties(cs) -> dict:
    """conceito -> IRI de propriedade, só os conceitos de alegações OK que o vocabulário neutro conhece."""
    out = {}
    if cs is None:
        return out
    for atom, cons in cs.concepts_by_atom().items():
        for c in cons:
            prop = V.CONCEPT_PROPERTY.get(c)
            if prop and prop in V.PROPERTY_IRI:
                out[c] = V.PROPERTY_IRI[prop]
    return out


def tbox_ttl(control: str, cs=None) -> str:
    lines = [PREFIXES, f"<{ONTOLOGY_IRI}> a owl:Ontology ; owl:versionIRI <{VERSION_IRI}> ;",
             '    rdfs:label "módulo da fatia NET do piloto (PILOT-NET-E2E)"@pt .', ""]
    for iri, (label, definition, parents) in sorted(CLASSES.items()):
        lines.append(f'{iri} a owl:Class ; rdfs:label "{label}"@pt ; skos:definition "{definition}"@pt .')
        for p in parents:
            lines.append(f"{iri} rdfs:subClassOf {p} .")
    for sub, sup in AX.TAXONOMY:
        lines.append(f"{sub} rdfs:subClassOf {sup} .")
    for iri, (label, dom, rng) in sorted(OBJECT_PROPS.items()):
        lines.append(f'{iri} a owl:ObjectProperty ; rdfs:label "{label}"@pt ; rdfs:domain {dom} ; rdfs:range {rng} .')
    for iri, (label, dom, rng) in sorted(DATA_PROPS.items()):
        lines.append(f'{iri} a owl:DatatypeProperty ; rdfs:label "{label}"@pt ; rdfs:domain {dom} ; rdfs:range {rng} .')
    seen = set(OBJECT_PROPS) | set(DATA_PROPS)
    for concept, iri in sorted(concept_properties(cs).items()):
        if iri in seen:
            continue
        seen.add(iri)
        lines.append(f'{iri} a owl:DatatypeProperty ; rdfs:label "{concept.split(":", 1)[1]}"@pt ; '
                     f'rdfs:domain bo:FilterRule ; bo:fromConcept "{concept}" .')
    lines.append("bo:fromConcept a owl:AnnotationProperty .")
    lines.append("skos:definition a owl:AnnotationProperty .")
    for v in AX.CONTROLLED_VALUES:
        lines.append(f"{v} a owl:NamedIndividual , bo:ControlledValue .")
    if control == "c3_full":
        lines.append("")
        lines.append("# axiomas do catálogo (só published/derived)")
        for a in AX.AXIOMS:
            if a["level"] not in ("published", "derived"):
                continue
            lines.append(f"# {a['axiom_id']}: {a['text']}")
            lines.append(a["ttl"])
    return "\n".join(lines) + "\n"


def c14_tables(cs, generated_by: str) -> dict:
    """classes.jsonl, properties.jsonl, realizations.jsonl (C14 3.0.0)."""
    classes = []
    for iri, (label, definition, parents) in sorted(CLASSES.items()):
        row = {"class_id": iri, "label": label, "definition": definition,
               "parents": [{"iri": p, "kind": "nested"} for p in parents],
               "model_role": "ConfigurationDescription" if iri != "bo:NetworkEndpoint" else "Resource",
               "status": "active", "evidence_state": "STRUCTURALLY_VALID"}
        if row["model_role"] == "Resource":
            row["identity"] = {"fields": ["synthetic_account", "provider", "type", "local_key"], "composite": True}
        classes.append(row)
    props = []
    for iri, (label, dom, rng) in sorted(OBJECT_PROPS.items()):
        props.append({"property_id": iri, "label": label, "kind": "object", "domain": {"kind": "single", "class": dom},
                      "range": rng, "definition": f"{label}: propriedade de objeto da fatia NET (vocabulário neutro).",
                      "value_marks": ["configured", "inferred"], "unknown_marks": ["unknown", "absent", "not_read"],
                      "status": "active", "evidence_state": "STRUCTURALLY_VALID"})
    for iri, (label, dom, rng) in sorted(DATA_PROPS.items()):
        props.append({"property_id": iri, "label": label, "kind": "datatype", "domain": {"kind": "single", "class": dom},
                      "range": rng, "definition": f"{label}: propriedade de dado da fatia NET.",
                      "value_marks": ["configured"], "unknown_marks": ["unknown", "absent"],
                      "status": "active", "evidence_state": "STRUCTURALLY_VALID"})
    seen = {p["property_id"] for p in props}
    for concept, iri in sorted(concept_properties(cs).items()):
        if iri in seen:
            continue
        seen.add(iri)
        props.append({"property_id": iri, "label": concept.split(":", 1)[1].replace("_", " "), "kind": "datatype",
                      "domain": {"kind": "single", "class": "bo:FilterRule"}, "range": "xsd:string",
                      "definition": f"propriedade do conceito {concept} do glossário, realizada por átomo de alegação OK.",
                      "value_marks": ["configured"], "unknown_marks": ["unknown", "absent", "not_read"],
                      "status": "active", "evidence_state": "STRUCTURALLY_VALID"})
    reals = []
    n = 0
    for (prov, rtype, block, prop), ev in sorted(V.STRUCTURAL_EVIDENCE.items(), key=str):
        n += 1
        reals.append({"realization_id": f"RZ-NET-S{n:03d}", "of": {"descriptor_key": prop, "kind": "property",
                                                                   "describes": V.PROPERTY_IRI[prop].replace("bo:", "https://w3id.org/brevops/ontology#")},
                      "provider": prov, "realized_by": [{"artifact_name": rtype, "schema": f"{prov}@pins",
                                                         **({"artifact_path": block} if block else {})}],
                      "lifting_fidelity": "Lossless", "lowering_fidelity": "Lossless",
                      "evidence_state": "DocSupported", "derived_from": ev, "generated_by": generated_by})
    for key, classes_ in sorted(AX.REALIZATION_CLASSES.items(), key=str):
        prov = key.split("_", 1)[0]
        prov = {"aws": "aws", "google": "google", "azurerm": "azurerm", "oci": "oci"}[prov]
        for c in classes_:
            n += 1
            reals.append({"realization_id": f"RZ-NET-C{n:03d}", "of": {"descriptor_key": c.split(":")[1], "kind": "class",
                                                                       "describes": c.replace("bo:", "https://w3id.org/brevops/ontology#")},
                          "provider": prov, "realized_by": [{"artifact_name": key, "schema": f"{prov}@pins"}],
                          "lifting_fidelity": "Lossless", "lowering_fidelity": "Lossless",
                          "evidence_state": "DocSupported", "derived_from": _class_evidence(key, c),
                          "generated_by": generated_by})
    if cs is not None:
        for atom, cons in sorted(cs.concepts_by_atom().items()):
            prov, rtype, path = atom.split(":", 2)
            for c in sorted(cons):
                prop = V.CONCEPT_PROPERTY.get(c)
                if not prop or prop not in V.PROPERTY_IRI:
                    continue
                n += 1
                claims = sorted(r["claim_id"] for r in cs.records if cs.verdicts.get(r["claim_id"]) == "OK"
                                and atom in (r["subject_id"], r["object_id"]))
                reals.append({"realization_id": f"RZ-NET-A{n:03d}", "of": {"descriptor_key": prop, "kind": "property",
                                                                           "describes": V.PROPERTY_IRI[prop].replace("bo:", "https://w3id.org/brevops/ontology#")},
                              "provider": prov, "realized_by": [{"artifact_name": rtype, "artifact_path": path,
                                                                 "schema": f"{prov}@pins"}],
                              "lifting_fidelity": "Lossless", "lowering_fidelity": "Lossless",
                              "evidence_state": "StructurallyValid", "derived_from": claims[:20] or [atom],
                              "generated_by": generated_by})
    return {"classes": classes, "properties": props, "realizations": reals}


def _class_evidence(key, cls) -> list:
    t = key if isinstance(key, str) else key[0]
    ev = []
    for a in AX.AXIOMS:
        if t in a.get("applies_to_types", []):
            ev += a["evidence"]
    if cls == "bo:PermissionListRuleSet":
        ev += AX.by_id()["AX-NET-01"]["evidence"]
    if cls in ("bo:PrecedenceRuleSet", "bo:DenyTieRuleSet", "bo:UniquePriorityRuleSet"):
        ev += AX.by_id()["AX-NET-04"]["evidence"]
    if cls == "bo:DeclaredDefaultStateRule":
        ev += AX.by_id()["AX-NET-07"]["evidence"]
    return sorted(set(ev)) or ["C24:REQ-NET-01"]


def jsonl(rows) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)
