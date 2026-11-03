"""Testes do PRIOR: extratores sobre fixtures sintéticas mínimas, codificação SKOS, ids e o gate G1."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from bo.prior import build as B
from bo.prior import check as CK
from bo.prior import common as C
from bo.prior import sources as S
from bo.prior import x_cartography, x_cloudquery, x_fix, x_owlxml, x_steampipe, x_tosca


def _w(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return p


class Tmp(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="prior-test-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestSteampipe(Tmp):
    GO = '''
    package aws
    func tableAwsThing(_ context.Context) *plugin.Table {
    	return &plugin.Table{
    		Name:        "aws_thing",
    		Description: "AWS Thing",
    		List: &plugin.ListConfig{
    			Hydrate: listThings,
    			Tags: map[string]string{
    				"service": "thing",
    				"action":  "ListThings",
    			},
    		},
    		Columns: awsRegionalColumns([]*plugin.Column{
    			{
    				Name:        "name",
    				Description: "The {braced} name.",
    				Type:        proto.ColumnType_STRING,
    			},
    			{Name: "size", Type: proto.ColumnType_INT, Description: "Size."},
    		}),
    	}
    }
    '''

    def test_tabela_colunas_e_etiqueta_multilinha(self):
        p = _w(self.root, "aws/table_aws_thing.go", self.GO)
        ex = x_steampipe.extract("steampipe", [("f.go", p, "aws")])
        self.assertEqual([c.id for c in ex.classes], ["sp:aws_thing"])
        self.assertEqual(sorted(x.label for x in ex.props), ["name", "size"])
        self.assertEqual(ex.links[0].object, "api_aws:thing.ListThings")
        self.assertEqual(C.ENCODING[ex.links[0].native_relation][0], "related")
        self.assertEqual(ex.counts["column_wrappers"], {"awsRegionalColumns": 1})


class TestCloudQuery(Tmp):
    MD = '''
    # Table: aws_things

    This table shows data for Things.

    https://docs.aws.amazon.com/thing/latest/API_ListThings.html

    The primary key for this table is **_cq_id**.
    ## Relations

    This table depends on [aws_parents](aws_parents.md).

    ## Columns

    | Name          | Type          |
    | ------------- | ------------- |
    |_cq_id (PK)|`uuid`|
    |created|`timestamp[us, tz=UTC]`|
    '''

    def test_pagina_de_tabela(self):
        p = _w(self.root, "aws_things.md", self.MD)
        ex = x_cloudquery.extract("cloudquery", [("t.md", p, "aws")])
        c = ex.classes[0]
        self.assertEqual((c.id, c.parents, c.definition), ("cq:aws_things", ["cq:aws_parents"],
                                                           "This table shows data for Things."))
        self.assertEqual([x.label for x in ex.props], ["_cq_id", "created"])
        self.assertNotIn(" ", ex.props[1].range)
        self.assertTrue(ex.links[0].object.startswith("https://docs.aws.amazon.com/"))


class TestFix(Tmp):
    BASE = '''
    class BaseResource(ABC):
        kind: ClassVar[str] = "resource"
        name: Optional[str] = None
    class BaseInstance(BaseResource):
        kind: ClassVar[str] = "instance"
        instance_cores: float = field(default=0.0, metadata={"description": "cores"})
    class BaseAccount(BaseResource):
        kind: ClassVar[str] = "account"
    '''
    PLUG = '''
    service_name = "ec2"
    class AwsResource(BaseResource):
        kind: ClassVar[str] = "aws_resource"
    class Taggable:
        pass
    class AwsThing(Taggable, AwsResource, BaseInstance):
        kind: ClassVar[str] = "aws_thing"
        _kind_display: ClassVar[str] = "AWS Thing"
        mapping: ClassVar[Dict[str, Bender]] = {
            "name": S("Tags") >> TagsValue("Name"),
            "instance_cores": S("CpuOptions", "CoreCount"),
            "own_field": S("Own"),
        }
        own_field: Optional[str] = None
    '''

    def test_heranca_mais_especifica_e_mapeamento(self):
        b = _w(self.root, "base.py", self.BASE)
        p = _w(self.root, "plug.py", self.PLUG)
        ex = x_fix.extract("fixinventory", ("base.py", b), [("plug.py", p, "aws")])
        cls = {(l.subject, l.object) for l in ex.links if l.level == "class"}
        self.assertIn(("fix:aws_thing", "fix:instance"), cls)
        self.assertNotIn(("fix:aws_thing", "fix:resource"), cls, "base ancestral de outra base não entra")
        self.assertIn(("fix:aws_resource", "fix:resource"), cls)
        prop = {(l.subject, l.object) for l in ex.links if l.level == "property"}
        self.assertIn(("fixapi_aws:aws_thing/CpuOptions.CoreCount", "fixp:instance.instance_cores"), prop)
        self.assertIn(("fixapi_aws:aws_thing/Tags", "fixp:resource.name"), prop)
        self.assertFalse(any("own_field" in o for _, o in prop), "campo próprio do provedor não é vínculo")
        self.assertEqual(C.ENCODING["python:inheritance"][0], "broad")


class TestOwlXml(Tmp):
    OWX = '''
    <?xml version="1.0"?>
    <Ontology xmlns="http://www.w3.org/2002/07/owl#" xml:base="urn:x" ontologyIRI="urn:x">
        <Prefix name="aws" IRI="http://g.example.org/individuals/aws/"/>
        <Prefix name="rdfs" IRI="http://www.w3.org/2000/01/rdf-schema#"/>
        <Declaration><Class IRI="http://g.example.org/classes/Compute"/></Declaration>
        <Declaration><Class IRI="http://g.example.org/classes/VirtualMachine"/></Declaration>
        <Declaration><DataProperty IRI="http://g.example.org/properties/cores"/></Declaration>
        <Declaration><NamedIndividual abbreviatedIRI="aws:EC2Instance"/></Declaration>
        <SubClassOf><Class IRI="http://g.example.org/classes/VirtualMachine"/>
                    <Class IRI="http://g.example.org/classes/Compute"/></SubClassOf>
        <SubClassOf><Class IRI="http://g.example.org/classes/VirtualMachine"/>
            <DataSomeValuesFrom><DataProperty IRI="http://g.example.org/properties/cores"/>
            <Datatype abbreviatedIRI="xsd:integer"/></DataSomeValuesFrom></SubClassOf>
        <ClassAssertion><Class IRI="http://g.example.org/classes/VirtualMachine"/>
            <NamedIndividual abbreviatedIRI="aws:EC2Instance"/></ClassAssertion>
    </Ontology>
    '''

    def test_classes_restricao_e_classassertion(self):
        p = _w(self.root, "o.owx", self.OWX)
        b = "http://g.example.org/"
        ex = x_owlxml.extract("cpg", p, "o.owx", {"g": b + "classes/", "gp": b + "properties/",
                                                   "gi_aws": b + "individuals/aws/"},
                              {b + "individuals/aws/": "aws"})
        vm = next(c for c in ex.classes if c.id == "g:VirtualMachine")
        self.assertEqual(vm.parents, ["g:Compute"])
        self.assertEqual(ex.props[0].domain, ["g:VirtualMachine"])
        self.assertEqual(ex.props[0].domain_kind, "restriction")
        ln = ex.links[0]
        self.assertEqual((ln.subject, ln.object, ln.provider), ("gi_aws:EC2Instance", "g:VirtualMachine", "aws"))
        self.assertGreater(ln.line, 0)


class TestToscaEdmm(Tmp):
    def test_primeiro_ancestral_neutro(self):
        base = _w(self.root, "ubct.yaml", '''
        tosca_definitions_version: tosca_2_0
        profile: com.ubicity:2.5
        node_types:
          Root: {}
          VirtualCompute:
            derived_from: Root
            properties:
              cores: {type: integer}
        ''')
        aws = _w(self.root, "aws.yaml", '''
        tosca_definitions_version: tosca_2_0
        profile: com.amazon.aws:2.5
        imports:
          - profile: com.ubicity:2.5
            namespace: ubct
        node_types:
          Base:
            derived_from: ubct:VirtualCompute
          Ec2:
            derived_from: Base
        ''')
        ed = _w(self.root, "types.yml", '''
        component_types:
          base: {extends: null}
          paas: {extends: base}
          aws_beanstalk: {extends: paas}
        ''')
        ex = x_tosca.extract("tosca-edmm", [("u", base), ("a", aws)], ("t", ed))
        got = {(l.subject, l.object) for l in ex.links}
        self.assertIn(("t_com_amazon_aws:Ec2", "t_com_ubicity:VirtualCompute"), got)
        self.assertIn(("edmm:aws_beanstalk", "edmm:paas"), got)


class TestCartography(Tmp):
    def test_mapeamento_de_no_e_campo(self):
        r = self.root
        _w(r, "cartography/models/ontology/labels.py", '''
        COMPUTE_INSTANCE = ExtraNodeLabel(label="ComputeInstance", description="A cross-provider instance.",
                                          kind=LabelKind.ONTOLOGY)
        ''')
        _w(r, "cartography/models/ontology/mapping/data/computeinstance.py", '''
        _S = {"running": "running"}
        aws_mapping = OntologyMapping(module_name="aws", nodes=[OntologyNodeMapping(node_label="EC2Instance",
            fields=[OntologyFieldMapping(ontology_field="state", node_field="state", special_handling="mapping",
                                         extra={"map": _S}),
                    OntologyFieldMapping(ontology_field="kind", node_field="", special_handling="static_value",
                                         extra={"value": "vm"})])])
        CI_MAPPING = {"aws": aws_mapping}
        ''')
        _w(r, "cartography/models/ontology/mapping/__init__.py", '''
        from cartography.models.ontology.labels import COMPUTE_INSTANCE
        from cartography.models.ontology.mapping.data.computeinstance import CI_MAPPING
        ONTOLOGY_NODES_MAPPING = {}
        SEMANTIC_LABELS_MAPPING = {"computeinstance": CI_MAPPING}
        SEMANTIC_LABEL_BY_CATEGORY = {"computeinstance": COMPUTE_INSTANCE}
        ONTOLOGY_MODELS = {}
        ''')
        ex = x_cartography.extract("cartography", r, "")
        got = {(l.subject, l.object, l.native_relation) for l in ex.links}
        self.assertIn(("cartonode:EC2Instance", "carto:ComputeInstance", "cartography:OntologyNodeMapping"), got)
        self.assertIn(("cartonodep:EC2Instance.state", "cartop:ComputeInstance.state",
                       "cartography:OntologyFieldMapping"), got)
        self.assertEqual(sum(1 for l in ex.links if l.level == "property"), 1, "static_value não é vínculo")
        note = next(l.note for l in ex.links if l.level == "property")
        self.assertIn("special_handling=mapping", note)


class TestIdsECodificacao(unittest.TestCase):
    def test_hash_curto_nunca_tem_12_digitos(self):
        rx = re.compile(r"\d{12}")
        for i in range(20000):
            self.assertIsNone(rx.search(C.short_hash("a", str(i))))

    def test_direcao_skos(self):
        # 'a skos:broadMatch b' = b mais amplo: o termo do provedor é o sujeito
        for k in ("owl:ClassAssertion", "rdfs:subClassOf", "python:inheritance", "tosca:derived_from",
                  "edmm:extends", "cartography:OntologyNodeMapping", "text:subclass", "text:abstracts_over"):
            self.assertEqual(C.ENCODING[k][0], "broad", k)

    def test_registro_cobre_o_indice_model(self):
        self.assertEqual(sorted(S.MODELS), sorted(CK.catalog_models()))

    def test_scrub_omite_campo_com_padrao_barrado(self):
        sc = B.Scrub()
        padrao = "ar" + "n:" + "aws:iam::" + "1" * 12 + ":role/x"   # montado: o literal seria barrado no commit
        out = sc("exemplo " + padrao)
        self.assertTrue(out.startswith("[omitido"))
        self.assertNotIn(padrao[:4], out)
        self.assertEqual(sc("texto comum"), "texto comum")


class TestGateG1(Tmp):
    def _copy(self, model):
        src = C.bo_data() / "PRIOR" / model
        shutil.copytree(src, self.root / model)

    def test_documental_sem_marca_reprova(self):
        self._copy("mosaic")
        p = self.root / "mosaic/SOURCE.txt"
        p.write_text(p.read_text(encoding="utf-8").replace(S.DOCUMENTAL, "artefato"), encoding="utf-8")
        errs = CK.check_model("mosaic", self.root)
        self.assertTrue(any("só documental" in e for e in errs), errs)

    def test_artefato_com_sha_errado_reprova(self):
        self._copy("cocoon")
        p = self.root / "cocoon/SOURCE.txt"
        t = p.read_text(encoding="utf-8")
        m = re.search(r"^([0-9a-f]{64})  ", t, re.M)
        p.write_text(t.replace(m.group(1), "0" * 64, 1), encoding="utf-8")
        errs = CK.check_model("cocoon", self.root)
        self.assertTrue(any("sha256 não confere" in e for e in errs), errs)

    def test_artefato_sem_licenca_reprova(self):
        self._copy("cocoon")
        p = self.root / "cocoon/SOURCE.txt"
        p.write_text(p.read_text(encoding="utf-8").replace("licença: MIT", "licença: NOASSERTION"),
                     encoding="utf-8")
        errs = CK.check_model("cocoon", self.root)
        self.assertTrue(any("licença" in e for e in errs), errs)

    def test_saidas_atuais_passam(self):
        for m in S.ORDER:
            self.assertEqual(CK.check_model(m, C.bo_data() / "PRIOR"), [], m)

    def test_inventario_bate_com_as_saidas(self):
        inv = json.loads((Path(B._repo()) / "results/PRIOR/inventory.json").read_text(encoding="utf-8"))
        for m, v in inv["models"].items():
            n = sum(1 for ln in (C.bo_data() / "PRIOR" / m / "provider_links.sssom.tsv").read_text(
                encoding="utf-8").splitlines() if ln and not ln.startswith("#")) - 1
            self.assertEqual(n, v["links"], m)


if __name__ == "__main__":
    unittest.main()
