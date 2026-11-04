"""bo.corpus_oci.counting: caminho → átomo, classe do termo, precedência e agregação por repositório."""
import json

import pytest
from conftest import ATOMS, EXPR_WH, LIT, REF, SYM, WH

from bo.corpus_oci import counting


@pytest.fixture
def ix(tmp_path_factory, data_root):
    return counting.AtomIndex.load(str(data_root / "SCHEMA-OCI" / "atoms.jsonl"), "oci")


def test_normalize_path():
    n = counting.normalize_path
    assert n("shape_config[0].ocpus") == "shape_config.ocpus"
    assert n('dynamic["shape_config"][3].content.ocpus') == "shape_config.ocpus"
    assert n('a[0].dynamic["b"][1].content.c[2].d') == "a.b.c.d"
    assert n('dynamic["b"][0].for_each') == 'dynamic["b"].for_each'


def test_resolve_causes(ix):
    r = ix.resolve
    assert r("oci_core_instance", "shape") == ("oci:oci_core_instance:shape", None)
    assert r("oci_core_instance", "metadata.user_data") == ("oci:oci_core_instance:metadata", None)
    assert r("oci_core_instance", 'dynamic["shape_config"][0].content.ocpus') == \
        ("oci:oci_core_instance:shape_config.ocpus", None)
    assert r("oci_core_instance", "count") == (None, "meta_argument")
    assert r("oci_core_instance", 'provisioner["local-exec"][0].command') == (None, "meta_argument")
    assert r("oci_core_instance", "lifecycle.ignore_changes") == (None, "meta_argument")
    assert r("oci_core_instance", 'dynamic["shape_config"][0].for_each') == (None, "dynamic_meta")
    assert r("oci_core_security_list", "ingress_security_rules") == (None, "block_as_attribute")
    assert r("oci_core_security_list", "ingress_security_rules[0].tcp_options") == (None, "block_as_attribute")
    assert r("oci_core_instance", "removed_attr") == (None, "attr_not_in_schema")
    # atributo desconhecido dentro de bloco conhecido não sobe para o bloco (bloco não é átomo)
    assert r("oci_core_instance", "shape_config[0].nope") == (None, "attr_not_in_schema")
    assert r("oci_tag", "name") == (None, "type_not_in_schema")


def test_term_class():
    """Regra comum dos 4 CORPUS: literal = não depende de variável, recurso, data, local ou função de plano."""
    c = counting.term_class
    assert c(LIT) == "literal"
    assert c(SYM) == "symbolic"  # variável
    assert c(REF) == "symbolic"
    assert c(WH) == "withheld"
    assert c(EXPR_WH) == "withheld"  # retido em qualquer profundidade
    redacted = {"kind": "symbol", "symbol_id": "SYM-0000000000cc", "name_class": "unknown", "scope": "repo"}
    assert c(redacted) == "literal"  # cadeia constante simbolizada por privacidade: redação, não dependência
    for nc in ("local", "module_output", "data_source", "resource_attribute", "count_index", "each_key",
               "path", "workspace"):
        assert c({**redacted, "name_class": nc}) == "symbolic", nc
    assert c({"kind": "expression", "op": "tolist", "args": [LIT, redacted]}) == "literal"  # função pura
    assert c({"kind": "expression", "op": "upper", "args": [SYM]}) == "symbolic"
    assert c({"kind": "expression", "op": "file", "args": [LIT]}) == "symbolic"  # lê arquivo no plano
    assert c({"kind": "expression", "op": "timestamp", "args": []}) == "symbolic"
    assert c({"kind": "expression", "op": "hcl_provider_function", "args": [LIT]}) == "symbolic"
    doc = {"kind": "document", "format": "json", "tree": {"a": 1}, "symbolized": []}
    assert c(doc) == "literal"
    assert c({**doc, "symbolized": [{"path": "/a", "symbol_id": "SYM-0000000000aa", "role": "identifier"}]}) \
        == "literal"  # identificador simbolizado é redação
    assert c({**doc, "tree": {"a": {"$term": REF}}}) == "symbolic"
    assert c({**doc, "tree": {"a": {"$term": WH}}}) == "withheld"
    assert c({**doc, "tree": {"a": {"$key": SYM, "v": 1}}}) == "symbolic"
    # valor literal com cara de termo não é termo
    assert c({"kind": "literal", "datatype": "map", "value": {"kind": "withheld"}}) == "literal"
    with pytest.raises(ValueError):
        c({"kind": "novo"})


def test_precedence():
    w = counting.worse
    assert w(None, "literal") == "literal"
    assert w("literal", "symbolic") == "symbolic"
    assert w("withheld", "literal") == "withheld"
    assert w("symbolic", "withheld") == "withheld"


def test_data_address():
    assert counting.is_data_address("data.oci_core_images.SYM-00000000000d")
    assert counting.is_data_address("module.SYM-00000000000m.data.oci_core_images.SYM-00000000000d")
    assert not counting.is_data_address("oci_core_instance.SYM-00000000000a")
    assert not counting.is_data_address("module.SYM-00000000000m.oci_core_instance.SYM-00000000000a")


def test_atoms_of_other_provider_rejected(data_root):
    p = data_root / "SCHEMA-OCI" / "atoms.jsonl"
    p.write_text(p.read_text() + json.dumps({**ATOMS[0], "provider": "aws", "atom_id": "aws:x:y"}) + "\n")
    with pytest.raises(ValueError):
        counting.AtomIndex.load(str(p), "oci")


def test_safe_report_path(ix):
    assert counting.safe_report_path(ix, "metadata") == "metadata"
    assert counting.safe_report_path(ix, "count") == "count"
    assert counting.safe_report_path(ix, 'dynamic["shape_config"].iterator') == 'dynamic["shape_config"].iterator'
    assert counting.safe_report_path(ix, "nome_da_empresa") == "<fora do vocabulário do schema>"
    assert counting.safe_report_path(ix, "shape_config.nome_da_empresa") == "<fora do vocabulário do schema>"
