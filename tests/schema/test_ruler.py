"""bo.schema.ruler: a régua do C1 (catalogo4v2), contas feitas à mão no schema sintético."""
from bo.schema import core, ruler

from conftest import schema_doc


def ts_of(name):
    ps = core.providers(schema_doc())["provider_a"]
    return core.type_schema("provider_a", "1.0.0", name, ps["resource_schemas"][name]["block"])


def atom(path="x", **f):
    base = {"path": path, "required": False, "optional": False, "computed": False}
    base.update(f)
    return base


def test_classify_order_of_decision():
    assert ruler.classify(atom("id", optional=True, computed=True)) == "provider_populated"
    assert ruler.classify(atom("arn", computed=True)) == "provider_populated"
    assert ruler.classify(atom("rule.id", optional=True, computed=True)) == "provider_populated"
    assert ruler.classify(atom("id", required=True)) == "cfg"            # required nunca é provider_populated
    assert ruler.classify(atom("id", optional=True)) == "cfg"            # sem computed: o operador decide
    assert ruler.classify(atom("status", computed=True)) == "computed_only"
    assert ruler.classify(atom("size", optional=True, computed=True)) == "cfg"
    assert ruler.classify(atom("nothing")) is None


def test_counts_by_hand():
    assert ruler.counts(ts_of("provider_a_widget")) == {
        "n_atributos_total": 22, "n_atributos_cfg": 15, "n_provider_populated": 5, "n_atributos_cfg_raw": 20,
        "n_computed_only": 2, "n_blocos_total": 8}
    assert ruler.counts(ts_of("provider_a_gadget")) == {
        "n_atributos_total": 2, "n_atributos_cfg": 1, "n_provider_populated": 1, "n_atributos_cfg_raw": 2,
        "n_computed_only": 0, "n_blocos_total": 0}


def test_tree_matches_catalog_shape():
    t = ruler.tree(ts_of("provider_a_gadget"))
    assert t == {"blocos": {}, "cfg": ["label"], "computed_only": [], "n_attr": 2, "opt": [],
                 "provider_populated": ["id"], "req": ["label"]}
    w = ruler.tree(ts_of("provider_a_widget"))
    assert w["blocos"]["empty_marker"] == {"blocos": {}, "cfg": [], "computed_only": [], "n_attr": 0, "opt": [],
                                           "provider_populated": [], "req": []}
    assert w["blocos"]["rule"]["provider_populated"] == ["id"] and w["blocos"]["rule"]["opt"] == ["id"]
    assert w["blocos"]["rule"]["blocos"]["expiration"]["cfg"] == ["days"]
    assert w["computed_only"] == ["listeners", "status"]
    assert list(w["blocos"]) == sorted(w["blocos"])
