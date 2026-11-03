"""Testes do GOLD-XPLANE com fixtures sintéticas (nada de rede, nada dos downloads)."""
import unittest
from fractions import Fraction

from bo.gold_xplane import build, compose, schema

COMP_RESOURCES = """
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata: {name: c-a, labels: {provider: a}}
spec:
  compositeTypeRef: {apiVersion: ex.org/v1alpha1, kind: XDb}
  patchSets:
    - name: common
      patches:
        - fromFieldPath: spec.parameters.region
          toFieldPath: spec.forProvider.region
  resources:
    - name: db
      base: {apiVersion: database.aws.crossplane.io/v1beta1, kind: RDSInstance}
      patches:
        - type: PatchSet
          patchSetName: common
        - fromFieldPath: spec.parameters.size
          toFieldPath: spec.forProvider.dbInstanceClass
          transforms:
            - type: map
              map: {small: db.t3.small, large: db.m5.large}
        - type: ToCompositeFieldPath
          fromFieldPath: status.atProvider.endpoint.address
          toFieldPath: status.address
        - type: CombineFromComposite
          combine:
            variables: [{fromFieldPath: spec.id}, {fromFieldPath: spec.parameters.region}]
            strategy: string
            string: {fmt: "%s-%s"}
          toFieldPath: spec.forProvider.dbName
"""

COMP_PIPELINE = """
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata: {name: c-b}
spec:
  compositeTypeRef: {apiVersion: ex.org/v1alpha1, kind: XDb}
  mode: Pipeline
  pipeline:
    - step: pt
      functionRef: {name: crossplane-contrib-function-patch-and-transform}
      input:
        apiVersion: pt.fn.crossplane.io/v1beta1
        kind: Resources
        resources:
          - name: sql
            base: {apiVersion: sql.gcp.upbound.io/v1beta1, kind: DatabaseInstance}
            patches:
              - type: FromCompositeFieldPath
                fromFieldPath: spec.parameters.size
                toFieldPath: spec.forProvider.settings[0].tier
    - step: kcl
      functionRef: {name: function-kcl}
      input: {kind: KCLInput}
"""

GO = '''
type InstanceParameters struct {

	// +kubebuilder:validation:Optional
	Settings []SettingsParameters `json:"settings,omitempty" tf:"settings,omitempty"`

	Tags map[string]*string `json:"tags,omitempty" tf:"tags,omitempty"`

	Region *string `json:"region" tf:"-"`

	VPCIDSelector *v1.Selector `json:"vpcIdSelector,omitempty" tf:"-"`
}

type SettingsParameters struct {
	Tier *string `json:"tier,omitempty" tf:"tier,omitempty"`
}
'''


class Paths(unittest.TestCase):
    def test_split(self):
        self.assertEqual(compose.split_path("spec.forProvider.tags[Name]"),
                         [("f", "spec"), ("f", "forProvider"), ("f", "tags"), ("k", "Name")])
        self.assertEqual(compose.split_path("a.b[0].c"), [("f", "a"), ("f", "b"), ("i", "0"), ("f", "c")])
        self.assertEqual(compose.split_path("metadata.labels[crossplane.io/claim-name]")[-1],
                         ("k", "crossplane.io/claim-name"))
        self.assertEqual(compose.join_path(compose.split_path("a.b[0].c[k]")), "a.b[0].c[k]")
        with self.assertRaises(ValueError):
            compose.split_path("")

    def test_classify(self):
        self.assertEqual(schema.classify_mr_path("spec.forProvider.region"), "param")
        self.assertEqual(schema.classify_mr_path("spec.forProvider.vpcIdSelector.matchLabels[x]"), "reference")
        self.assertEqual(schema.classify_mr_path("status.atProvider.arn"), "observed")
        self.assertEqual(schema.classify_mr_path("metadata.annotations[crossplane.io/external-name]"), "external_name")
        self.assertEqual(schema.classify_mr_path("spec.writeConnectionSecretToRef.name"), "runtime")
        self.assertEqual(schema.classify_xr_path("metadata.uid"), "xr_meta")
        self.assertEqual(schema.classify_xr_path("spec.claimRef.namespace"), "xr_runtime")
        self.assertEqual(schema.classify_xr_path("spec.parameters.size"), "xr_field")


class Parse(unittest.TestCase):
    def test_resources_mode_and_patchset(self):
        c = compose.parse_file(COMP_RESOURCES)["compositions"][0]
        ps = c["resources"][0]["patches"]
        self.assertEqual([p["type"] for p in ps],
                         ["FromCompositeFieldPath", "FromCompositeFieldPath", "ToCompositeFieldPath",
                          "CombineFromComposite"])
        self.assertEqual(ps[0]["patch_set"], "common")
        self.assertEqual(ps[0]["to_field_path"], "spec.forProvider.region")
        self.assertEqual(ps[3]["from_field_paths"], ["spec.id", "spec.parameters.region"])
        self.assertTrue(all(isinstance(p["line"], int) for p in ps))
        self.assertNotIn("__line__", str(ps[1]["transforms"]))

    def test_pipeline_reads_only_pt(self):
        c = compose.parse_file(COMP_PIPELINE)["compositions"][0]
        self.assertEqual(len(c["resources"]), 1)
        self.assertEqual(c["resources"][0]["mr"]["kind"], "DatabaseInstance")
        self.assertEqual([u["function"] for u in c["unread_steps"]], ["function-kcl"])

    def test_missing_patchset_is_reported(self):
        txt = COMP_RESOURCES.replace("patchSetName: common", "patchSetName: nope")
        ps = compose.parse_file(txt)["compositions"][0]["resources"][0]["patches"]
        self.assertEqual(ps[0]["status"], "patchset_ausente")


class Schema(unittest.TestCase):
    SCH = {"type": "object", "properties": {"spec": {"type": "object", "properties": {
        "forProvider": {"type": "object", "properties": {
            "settings": {"type": "array", "items": {"type": "object", "properties": {"tier": {"type": "string"}}}},
            "tags": {"type": "object", "additionalProperties": {"type": "string"}},
            "size": {"type": "integer"}}}}}}}

    def test_walk(self):
        ok, node, _ = schema.walk_schema(self.SCH, compose.split_path("spec.forProvider.settings[0].tier"))
        self.assertTrue(ok)
        self.assertEqual(schema.value_type(node), {"datatype": "string"})
        self.assertTrue(schema.walk_schema(self.SCH, compose.split_path("spec.forProvider.tags[Name]"))[0])
        ok, _, why = schema.walk_schema(self.SCH, compose.split_path("spec.forProvider.nope"))
        self.assertFalse(ok)
        self.assertIn("nope", why)
        self.assertFalse(schema.walk_schema(self.SCH, compose.split_path("spec.forProvider.size[0]"))[0])

    def test_tf_bridge(self):
        go = {"tf_type": "google_sql_database_instance", "structs": schema.parse_go_structs(GO), "file": "x.go"}
        b = schema.tf_bridge(go, "Instance", compose.split_path("spec.forProvider.settings[0].tier"))
        self.assertEqual((b["status"], b["tf_path"]), ("resolved", "settings.tier"))
        b = schema.tf_bridge(go, "Instance", compose.split_path("spec.forProvider.tags[team]"))
        self.assertEqual((b["tf_path"], b["map_key"]), ("tags", "team"))
        for p in ("spec.forProvider.region", "spec.forProvider.vpcIdSelector.matchLabels[a]"):
            self.assertEqual(schema.tf_bridge(go, "Instance", compose.split_path(p))["status"], "unresolved")
        self.assertEqual(schema.tf_bridge(None, "Instance", compose.split_path("spec.forProvider.x"))["status"],
                         "unresolved")


class Compose(unittest.TestCase):
    def test_map_through_pivot(self):
        a = [("enum_map", {"small": "db.t3.small", "large": "db.m5.large"})]
        b = [("enum_map", {"small": "db-small", "large": "db-large"})]
        fn, tests = build.compose_forward(a, b)
        self.assertEqual(fn, {"name": "enum_map", "params": {"table": {"db.m5.large": "db-large",
                                                                      "db.t3.small": "db-small"}}})
        self.assertEqual(len(tests), 2)

    def test_non_injective_side_is_not_a_function(self):
        a = [("enum_map", {"small": "x", "medium": "x", "large": "y"})]
        b = [("enum_map", {"small": "1", "medium": "2", "large": "3"})]
        self.assertIsNone(build.compose_forward(a, b))

    def test_scale_and_identity(self):
        self.assertEqual(build.compose_forward([], [("scale", Fraction(1024))])[0],
                         {"name": "scale", "params": {"factor": 1024}})
        self.assertEqual(build.compose_forward([], [])[0], {"name": "identity", "params": {}})
        self.assertEqual(build.compose_backward([], [])[0], {"name": "identity", "params": {}})

    def test_string_transform_does_not_compose(self):
        self.assertIsNone(build.chain_steps([{"type": "string", "string": {"fmt": "%s-a"}}]))
        self.assertIsNone(build.compose_forward(None, []))
        self.assertIsNone(build.step_of({"type": "convert", "convert": {"toType": "string"}}))

    def test_backward_map(self):
        fn, _ = build.compose_backward([("enum_map", {"RUNNING": "ok", "ERROR": "bad"})], [])
        self.assertEqual(fn["params"]["table"], {"ERROR": "bad", "RUNNING": "ok"})
        self.assertIsNone(build.compose_backward([], [("enum_map", {"a": "x", "b": "x"})]))


class Rows(unittest.TestCase):
    def test_related_has_no_transport(self):
        r = build.base_row("XPL-T-1", "pa:x", "pb:y", "related", {"name": "identity"}, [{"input": 1, "expected": 1}],
                           [{"level": "derived", "ref": "r"}], "STRUCTURALLY_VALID", "direct",
                           "semapv:ManualMappingCuration", {})
        self.assertEqual((r["predicate_id"], r["transport_fidelity"], r["translation_fn"], r["loss_contract"]),
                         ("skos:relatedMatch", "none", None, []))

    def test_close_declares_semantic_loss_never_exact(self):
        r = build.base_row("XPL-T-2", "pa:x", "pb:y", "close", {"name": "identity", "params": {}}, [],
                           [{"level": "derived", "ref": "r"}], "STRUCTURALLY_VALID", "direct",
                           "semapv:ManualMappingCuration", {})
        self.assertEqual(r["predicate_id"], "skos:closeMatch")
        self.assertEqual(r["loss_contract"][0]["kind"], "semantic")
        self.assertEqual(r["transport_fidelity"], "declared_loss")
        self.assertEqual(r["curation_rule"], build.LEVEL_RULE)

    def test_assessment_never_ok_for_close(self):
        from bo.semantics import obligations as O
        r = build.base_row("XPL-T-3", "pa:x", "pb:y", "close", {"name": "identity", "params": {}}, [],
                           [{"level": "derived", "ref": "r"}], "STRUCTURALLY_VALID", "direct",
                           "semapv:ManualMappingCuration",
                           {"subject_value_type": {"datatype": "string", "quantity_kind": "NOT_APPLICABLE",
                                                   "unit": "NOT_APPLICABLE"},
                            "object_value_type": {"datatype": "string", "quantity_kind": "NOT_APPLICABLE",
                                                  "unit": "NOT_APPLICABLE"}})
        a = O.assess(r).to_dict()
        self.assertEqual(a["verdict"], "UNPROVEN")     # derivado sem citação: nunca vira prova


if __name__ == "__main__":
    unittest.main()
