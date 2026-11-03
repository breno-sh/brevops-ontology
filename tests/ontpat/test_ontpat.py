"""Testes do ONTPAT: as formas SHACL pegam cada violação plantada (não passam por vacuidade), o verificador de
punning e o OntoClean discriminam, e os artefatos gerados são os que o gerador produz."""

from __future__ import annotations

import unittest

import rdflib
from pyshacl import validate

from bo.ontpat import build, common as c, no_punning, ontoclean

SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
PFX = """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix prov: <http://www.w3.org/ns/prov#> . @prefix bo: <https://w3id.org/brevops/ontology#> .
@prefix exv: <https://example.org/bo-example/vocab#> . @prefix ex: <https://example.org/bo-example/abox#> .
@prefix t: <https://example.org/bo-test#> .
"""
GOOD_VALUE = """t:o a bo:ObservedState ; bo:stateOf ex:vm1 ; prov:wasGeneratedBy ex:ob1 ; bo:hasSettingValue t:v .
t:v a bo:SettingValue , bo:NaryRelation ; bo:of ex:desc_capacity ; bo:valueOrigin bo:Observed ; """

# (rótulo, triplas acrescentadas ao ABox de exemplo, forma que tem de acusar)
BAD = [
    ("retido com valor", GOOD_VALUE + 'bo:valueState bo:Withheld ; bo:literalValue "x" .', "WithheldShape"),
    ("retido com hash em propriedade auxiliar", GOOD_VALUE + 'bo:valueState bo:Withheld ; rdfs:seeAlso "sha256:ab" .', "WithheldShape"),
    ("conhecido sem valor", GOOD_VALUE + "bo:valueState bo:Known .", "KnownValueShape"),
    ("desconhecido sem motivo", GOOD_VALUE + "bo:valueState bo:Unknown .", "UnknownNeedsReasonShape"),
    ("numérico sem unidade", GOOD_VALUE + 'bo:valueState bo:Known ; bo:literalValue "3"^^xsd:decimal .', "NumericNeedsUnitShape"),
    ("unidade como string", GOOD_VALUE + 'bo:valueState bo:Known ; bo:literalValue "3"^^xsd:decimal ; bo:hasUnit t:gb .\nt:gb a bo:UnitOfMeasure .', "UnitIriShape"),
    ("duração com unidade QUDT", GOOD_VALUE + 'bo:valueState bo:Known ; bo:literalValue "P1M"^^xsd:duration ; bo:hasUnit <http://qudt.org/vocab/unit/SEC> .\n<http://qudt.org/vocab/unit/SEC> a bo:UnitOfMeasure .', "DurationNoUnitShape"),
    ("ausente sob leitura parcial", """t:o a bo:ObservedState ; bo:stateOf ex:vm1 ; prov:wasGeneratedBy ex:ob2 ; bo:hasSettingValue t:v .
t:v a bo:SettingValue , bo:NaryRelation ; bo:of ex:desc_lifecycleRule ; bo:valueOrigin bo:Observed ; bo:valueState bo:Absent .""", "AbsentNeedsCompleteReadShape"),
    ("valor direto na unidade", """t:v a bo:SettingValue , bo:NaryRelation ; bo:of ex:desc_capacity ; bo:valueOrigin bo:Observed ; bo:valueState bo:Known ; bo:literalValue "1"^^xsd:decimal ; bo:hasUnit bo:UnitUnknown .
ex:vm1 bo:hasSettingValue t:v .""", "SettingValueShape"),
    ("padrão e configurado juntos", """ex:d1 bo:hasSettingValue t:v .
t:v a bo:SettingValue , bo:NaryRelation ; bo:of ex:desc_versioningStatus ; bo:iriValue exv:Enabled ; bo:valueOrigin bo:ProviderDefault ; bo:valueState bo:Known .""", "DefaultNotConfiguredShape"),
    ("descritor apontando para indivíduo", "t:d a bo:PropertyDescriptor ; bo:descriptorKey \"vm1\" ; bo:describesProperty ex:vm1 .", "PropertyDescriptorShape"),
    ("descritor sem a propriedade descrita", "t:d a bo:PropertyDescriptor ; bo:descriptorKey \"x\" .", "PropertyDescriptorShape"),
    ("bo:of apontando para o IRI da propriedade (punning)", "ex:v_o3_cap bo:of exv:capacity .", "OfShape"),
    ("realização sem fidelidade de descida", """t:r a bo:Realization , bo:NaryRelation ; bo:of ex:desc_ComputeInstance ; bo:onProvider ex:provider_a ; bo:realizedBy ex:ptype_instance ;
  bo:liftingFidelity bo:Lossless ; bo:evidenceState bo:DocSupported ; prov:wasDerivedFrom ex:schema_a ; prov:wasGeneratedBy ex:map_run1 .""", "RealizationShape"),
    ("sem perda sem evidência documental", """t:r a bo:Realization , bo:NaryRelation ; bo:of ex:desc_ComputeInstance ; bo:onProvider ex:provider_a ; bo:realizedBy ex:ptype_instance ;
  bo:liftingFidelity bo:Lossless ; bo:loweringFidelity bo:Lossless ; bo:evidenceState bo:Unresolved ; prov:wasDerivedFrom ex:schema_a ; prov:wasGeneratedBy ex:map_run1 .""", "RealizationShape"),
    ("perda declarada sem registro", """t:r a bo:Realization , bo:NaryRelation ; bo:of ex:desc_ComputeInstance ; bo:onProvider ex:provider_a ; bo:realizedBy ex:ptype_instance ;
  bo:liftingFidelity bo:DeclaredLoss ; bo:loweringFidelity bo:NoTransport ; bo:evidenceState bo:DocSupported ; prov:wasDerivedFrom ex:schema_a ; prov:wasGeneratedBy ex:map_run1 .""", "RealizationShape"),
    ("alternativa sem guarda", """t:r a bo:Realization , bo:NaryRelation ; bo:of ex:desc_versioningStatus ; bo:onProvider ex:provider_b ; bo:realizedBy ex:art_b_lock ;
  bo:liftingFidelity bo:NoTransport ; bo:loweringFidelity bo:NoTransport ; bo:evidenceState bo:Unresolved ; bo:alternativeTo ex:r_ver_b ;
  prov:wasDerivedFrom ex:schema_b ; prov:wasGeneratedBy ex:map_run1 .""", "RealizationShape"),
    ("faceta sem alcance", "t:f a exv:VersioningSetting , bo:Facet , bo:Unit ; bo:facetOf ex:c2 .", "FacetShape"),
    ("faceta com dois donos", "t:f a exv:VersioningSetting , bo:Facet , bo:Unit ; bo:facetOf ex:c1 , ex:c2 ; bo:appliesTo ex:c1 .", "FacetShape"),
    ("chave de ocorrência posicional", "ex:c2 bo:occurrenceKey \"pos=1\" .", "ComponentShape"),
    ("zona sem região", "t:z a bo:Location ; bo:ofProvider ex:provider_a ; bo:locationScope bo:ZonalScope ; bo:locationCode \"z\" .", "LocationShape"),
    ("substituição com a mesma encarnação", """t:x a exv:ComputeInstance , bo:IndependentResource , bo:Resource , bo:Unit ; bo:inAccount ex:acct_1 ; bo:ofProvider ex:provider_a ;
  bo:inLocation ex:zone_a1x ; bo:hasProviderType ex:ptype_instance ; bo:localKey "vm-a" ; bo:incarnationKey "inc-0001" ; bo:replacedBy ex:vm1 ; bo:endedBy ex:rep_vm0 .""", "ReplacedShape"),
    ("substituída sem fim de vida", "ex:sa bo:replacedBy ex:nic1 .", "ReplacedShape"),
    ("recurso sem localização nem marca", """t:x a exv:Subnet , bo:IndependentResource , bo:Resource , bo:Unit ; bo:inAccount ex:acct_1 ; bo:ofProvider ex:provider_a ;
  bo:hasProviderType ex:ptype_subnet ; bo:localKey "s" .""", "ResourceShape"),
    ("descrição que também é recurso", "ex:d1 a bo:Unit .", "S1SeparationShape"),
    ("observação sem fuso", 't:ob a bo:Observation ; prov:startedAtTime "2026-11-02T10:00:00"^^xsd:dateTime ; bo:readCompleteness bo:CompleteRead ; bo:coversScope ex:acct_1 .', "ObservationShape"),
    ("vínculo com um extremo só", "t:a a exv:Assignment , bo:Binding , bo:Unit ; exv:assignsPrincipal ex:p1 .", "BindingShape"),
]


_SHAPES = None


def shapes() -> rdflib.Graph:
    global _SHAPES
    if _SHAPES is None:
        _SHAPES = c.parse(c.repo() / "shapes" / "patterns.shacl.ttl")
    return _SHAPES


def example() -> rdflib.Graph:
    return c.parse(c.patterns_dir() / c.EXAMPLE)


def violated_shapes(g: rdflib.Graph) -> set[str]:
    conforms, rg, _ = validate(g, shacl_graph=shapes(), inference="none", advanced=True)
    out = set()
    for r in rg.subjects(rdflib.RDF.type, SH.ValidationResult):
        src = rg.value(r, SH.sourceShape)
        names = {str(src)}
        for parent in shapes().subjects(SH.property, src):
            names.add(str(parent))
        for parent in shapes().subjects(SH.sparql, src):
            names.add(str(parent))
        out |= {n.split("#")[-1] for n in names}
    return out


class ShapesTest(unittest.TestCase):
    def test_example_conforms(self):
        conforms, _, text = validate(example(), shacl_graph=shapes(), inference="none", advanced=True)
        self.assertTrue(conforms, text[:2000])

    def test_each_planted_violation_is_caught(self):
        for label, ttl, shape in BAD:
            with self.subTest(label):
                g = example()
                g.parse(data=PFX + ttl, format="turtle")
                got = violated_shapes(g)
                self.assertIn(shape, got, f"{label}: formas acusadas {sorted(got)}")


class PunningTest(unittest.TestCase):
    def test_controls(self):
        self.assertEqual(no_punning.controls(), [])

    def test_planted_punning_in_example(self):
        g = example()
        g.parse(data=PFX + "ex:v_o3_cap bo:of exv:capacity .", format="turtle")
        closure, _ = c.load_closure(c.patterns_dir() / c.PATTERNS)
        g += closure
        rep = no_punning.report(g)
        self.assertIn(str(c.EXV.capacity), rep["property_and_individual"])

    def test_metamodelling_detected(self):
        g = rdflib.Graph().parse(data=PFX + "t:hasRealization a owl:ObjectProperty ; rdfs:domain owl:Class .", format="turtle")
        self.assertTrue(no_punning.report(g)["metamodelling"])

    def test_artifacts_clean(self):
        for name, g in no_punning.default_targets():
            with self.subTest(name):
                self.assertTrue(no_punning.clean(no_punning.report(g)), name)


class OntoCleanTest(unittest.TestCase):
    def g(self, ttl):
        return rdflib.Graph().parse(data=PFX + "t:P bo:rigidity bo:Rigid . t:E bo:rigidity bo:AntiRigid .\n" + ttl, format="turtle")

    def test_role_under_type_ok(self):
        self.assertTrue(ontoclean.check_graph(self.g("t:E rdfs:subClassOf t:P .")).ok)

    def test_type_under_role_rejected(self):
        self.assertFalse(ontoclean.check_graph(self.g("t:P rdfs:subClassOf t:E .")).ok)

    def test_inferred_pairs_used(self):
        rep = ontoclean.check(ontoclean.rigidity_map(self.g("")), {(rdflib.URIRef("https://example.org/bo-test#P"), rdflib.URIRef("https://example.org/bo-test#E"))})
        self.assertFalse(rep.ok)


class GeneratedTest(unittest.TestCase):
    def test_regeneration_identical(self):
        for p, text in build.targets().items():
            with self.subTest(str(p)):
                self.assertEqual(p.read_text(encoding="utf-8"), text)

    def test_example_context_is_subset_of_closure(self):
        closure, _ = c.load_closure(c.patterns_dir() / c.PATTERNS)
        txt = (c.patterns_dir() / c.EXAMPLE).read_text(encoding="utf-8")
        ctx = txt.split(build.CONTEXT_MARK, 1)[1]
        g = rdflib.Graph().parse(data=ctx, format="nt")
        missing = [t for t in g if t not in closure]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
