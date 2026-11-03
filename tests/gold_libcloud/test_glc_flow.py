"""Regras R1-R6 num driver sintético (pacote falso escrito no BO_TMP; nada é importado)."""
import textwrap

import pytest

from bo.gold_libcloud import build as B

BASE = '''
class Node:
    def __init__(self, id, name, state, public_ips, private_ips, driver, size=None, image=None, extra=None,
                 created_at=None):
        pass

class NodeAuthPassword:
    def __init__(self, password, generated=False):
        pass
'''
TYPES = '''
class NodeState:
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"
'''
DRIVER = '''
from libcloud.compute.base import Node
from libcloud.compute.types import NodeState
from libcloud.utils.xml import findtext


class FakeNodeDriver:
    NODE_STATE_MAP = {"on": NodeState.RUNNING, "off": NodeState.STOPPED}

    def list_nodes(self):
        data = self.connection.request("/servers").object
        return [self._to_node(s) for s in data["servers"]]

    def list_xml(self):
        body = self.connection.request("/x").object
        return [self._to_xml_node(e) for e in body.findall("item")]

    def _to_node(self, s):
        ips = []
        for nic in s.get("nics", []):
            ips.append(nic["addr"])
        name = s.get("label") or s["id"]
        return Node(id=s["id"], name=name, state=self.NODE_STATE_MAP.get(s["power"], NodeState.UNKNOWN),
                    public_ips=ips, private_ips=[], driver=self, size=int(s["ram"]),
                    image=s["image"].split("/")[-1], extra={"zone": s["zone"]}, created_at=self._mystery(s))

    def _to_xml_node(self, element):
        node_id = findtext(element=element, xpath="instanceId", namespace="ns")
        return Node(node_id, findtext(element=element, xpath="name", namespace="ns"), NodeState.UNKNOWN,
                    [], [], self)

    def create_node(self, name, size):
        return Node(id=None, name=name, state=NodeState.RUNNING, public_ips=[], private_ips=[], driver=self)
'''


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    root = tmp_path_factory.mktemp("fakepkg") / "libcloud"
    (root / "compute" / "drivers").mkdir(parents=True)
    (root / "compute" / "base.py").write_text(textwrap.dedent(BASE))
    (root / "compute" / "types.py").write_text(textwrap.dedent(TYPES))
    (root / "compute" / "drivers" / "fake.py").write_text(textwrap.dedent(DRIVER))
    return B.build(root)


def row(res, subj_end, obj):
    hits = [r for r in res["records"] if r["subject_id"].endswith(subj_end) and r["object_id"] == obj]
    assert len(hits) == 1, (subj_end, obj, [(r["subject_id"], r["object_id"]) for r in res["records"]])
    return hits[0]


def test_normalized_classes_only_resource_classes(res):
    assert sorted(res["norm"]) == ["compute.Node"]          # NodeAuthPassword não tem 'extra'


def test_r1_direct_xml_positional(res):
    r = row(res, "_to_xml_node/element/instanceId", "lcm:compute.Node.id")
    assert (r["predicate_id"], r["curation_rule"], r["transport_fidelity"]) == ("skos:exactMatch", "R1", "lossless")
    assert r["translation_fn"] == {"name": "identity", "params": {}}
    row(res, "_to_xml_node/element/name", "lcm:compute.Node.name")


def test_r1_list_of_items(res):
    r = row(res, "_to_node/s/nics/*/addr", "lcm:compute.Node.public_ips")
    assert r["curation_rule"] == "R1"


def test_r2_cast(res):
    r = row(res, "_to_node/s/ram", "lcm:compute.Node.size")
    assert r["curation_rule"] == "R2" and r["proof"]["normalization"] == {"op": "cast", "to": ["int"]}
    assert r["translation_fn"] is None


def test_r3_enum_with_default_is_close_with_sentinel(res):
    r = row(res, "_to_node/s/power", "lcm:compute.Node.state")
    assert r["curation_rule"] == "R3" and r["predicate_id"] == "skos:closeMatch"
    assert r["translation_fn"]["params"]["table"] == {"off": "stopped", "on": "running"}
    assert r["object_value_type"]["enum"] == ["running", "stopped", "unknown"]
    assert r["value_domain_relation"]["relation"] == "subset"
    assert {x["kind"] for x in r["loss_contract"]} >= {"sentinel", "not_expressible"}


def test_r4_one_of_several_sources(res):
    for end in ("_to_node/s/label", "_to_node/s/id"):
        r = row(res, end, "lcm:compute.Node.name")
        assert (r["curation_rule"], r["semantic_relation"], r["transport_fidelity"]) == ("R4", "close", "partial")


def test_r5_derived(res):
    r = row(res, "_to_node/s/image", "lcm:compute.Node.image")
    assert (r["curation_rule"], r["predicate_id"], r["transport_fidelity"]) == ("R5", "skos:relatedMatch", "none")


def test_r6_unresolved_call(res):
    r = row(res, "_to_node/?", "lcm:compute.Node.created_at")
    assert r["evidence_state"] == "UNRESOLVED" and r["curation_rule"] == "R6"


def test_extra_goes_to_registry_not_sssom(res):
    assert not [r for r in res["records"] if ".extra" in r["object_id"]]
    assert [e for e in res["extras"] if e["extra_key"] == "zone" and e["api_fields"][0].endswith("/s/zone")]


def test_user_input_and_constants_are_not_api(res):
    assert not [r for r in res["records"] if ".create_node/" in r["subject_id"]]
    feeds = {(c["site"].split(":")[1], c["field"]): c["feed"] for c in res["coverage"]}
    create = [k for k in feeds if feeds[k] == "input"]
    assert create and all(k[1] == "name" for k in create)
    assert any(v == "constant" for (_, f), v in feeds.items() if f == "state")


def test_records_valid_c09(res, tmp_path):
    from bo.contracts import validate as VAL  # noqa: F401  (o validador oficial roda no gate; aqui a regra C09)
    from bo.contracts.rules import check_correspondences
    from bo.contracts import sssom as CS
    text = B.render(res)["libcloud.sssom.tsv"]
    meta, recs, cols = CS.read_tsv(text)
    assert check_correspondences(recs, meta, cols) == []
    assert meta["license"] == "https://www.apache.org/licenses/LICENSE-2.0"
