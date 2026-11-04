"""Testes da contagem do CORPUS-AZURE (dados sintéticos; nada do TerraDS)."""
from bo.corpus_azure.count import AtomIndex, atom_path, classify, is_data_address, module_of, repo_usage, weakest

R = "R-00000000000a"
F = "F-00000000000a"


def lit(v, dt="string"):
    return {"kind": "literal", "datatype": dt, "value": v}


def sym(cls, sid="SYM-0a1b2c3d4e5f"):
    return {"kind": "symbol", "symbol_id": sid, "name_class": cls, "scope": "repo"}


def ex(op, *args):
    return {"kind": "expression", "op": op, "args": list(args)}


ATOMS = [
    {"atom_id": "azurerm:azurerm_resource_group:name", "resource_type": "azurerm_resource_group", "path": "name",
     "tf_type": "string"},
    {"atom_id": "azurerm:azurerm_resource_group:location", "resource_type": "azurerm_resource_group",
     "path": "location", "tf_type": "string"},
    {"atom_id": "azurerm:azurerm_network_security_group:security_rule",
     "resource_type": "azurerm_network_security_group", "path": "security_rule",
     "tf_type": ["set", ["object", {"access": "string", "priority": "number"}]]},
    {"atom_id": "azurerm:azurerm_network_security_group:name", "resource_type": "azurerm_network_security_group",
     "path": "name", "tf_type": "string"},
    {"atom_id": "azurerm:azurerm_linux_web_app:site_config.always_on", "resource_type": "azurerm_linux_web_app",
     "path": "site_config.always_on", "tf_type": "bool"},
    {"atom_id": "azurerm:azurerm_linux_web_app:site_config.application_stack.python_version",
     "resource_type": "azurerm_linux_web_app", "path": "site_config.application_stack.python_version",
     "tf_type": "string"},
]
IDX = AtomIndex(ATOMS)


def rec(file, addr, rtype, path, term, provider="azurerm"):
    return {"repo_id": R, "family_id": F, "file": file, "resource_address": addr, "resource_type": rtype,
            "provider": provider, "attr_path": path, "term": term}


def test_atom_path_strips_indices_and_dynamic():
    assert atom_path("site_config[0].always_on") == ("site_config.always_on", None)
    assert atom_path('dynamic["site_config"][0].content.always_on') == ("site_config.always_on", None)
    assert atom_path('site_config[0].dynamic["application_stack"][1].content.python_version') == \
        ("site_config.application_stack.python_version", None)
    assert atom_path('dynamic["site_config"][0].for_each') == (None, "dynamic_meta")
    assert atom_path('dynamic["site_config"][0].iterator') == (None, "dynamic_meta")
    for meta in ("count", "for_each", "provider", "depends_on", "lifecycle[0].ignore_changes"):
        assert atom_path(meta) == (None, "meta_argument")


def test_classify_literal_symbolic_withheld():
    assert classify(lit("eastus")) == "literal"
    assert classify(sym("unknown")) == "literal"  # cadeia constante simbolizada por privacidade
    assert classify(ex("cidr", lit("10.0.0.0"), lit(16, "number"), lit("private"))) == "literal"
    assert classify(ex("lower", lit("X"))) == "literal"
    assert classify(sym("variable")) == "symbolic"
    assert classify(sym("local")) == "symbolic"
    assert classify(sym("each_key")) == "symbolic"
    assert classify({"kind": "reference", "target_type": "azurerm_resource_group",
                     "target_address": "azurerm_resource_group.SYM-0a1b2c3d4e5f", "attribute": "name"}) == "symbolic"
    assert classify(ex("format", lit("%s-x"), sym("variable"))) == "symbolic"
    assert classify(ex("file", lit("x.json"))) == "symbolic"
    assert classify(ex("timestamp")) == "symbolic"
    assert classify({"kind": "withheld", "reason": "secret"}) == "withheld"
    assert classify(ex("hcl_object", lit("k"), {"kind": "withheld", "reason": "secret"})) == "withheld"


def test_classify_document():
    doc = {"kind": "document", "format": "json", "symbolized": [], "tree": {"a": 1, "b": "SYM-0a1b2c3d4e5f"}}
    assert classify(doc) == "literal"
    doc2 = {"kind": "document", "format": "json", "symbolized": [],
            "tree": {"a": {"$term": sym("variable")}}}
    assert classify(doc2) == "symbolic"


def test_weakest_order():
    assert weakest(None, "literal") == "literal"
    assert weakest("literal", "symbolic") == "symbolic"
    assert weakest("withheld", "literal") == "withheld"


def test_resolve_object_attribute_written_as_block():
    t = lit("Allow")
    assert IDX.resolve("azurerm_network_security_group", "security_rule[0].access", t) == \
        ("azurerm:azurerm_network_security_group:security_rule", "object_attr")
    assert IDX.resolve("azurerm_network_security_group", "security_rule[0].nao_existe", t) == \
        (None, "attr_not_in_schema")
    assert IDX.resolve("azurerm_resource_group", "name", t) == ("azurerm:azurerm_resource_group:name", None)
    assert IDX.resolve("azurerm_resource_group", "managed_by_x", t) == (None, "attr_not_in_schema")
    assert IDX.resolve("azurerm_app_service", "name", t) == (None, "type_not_in_schema")
    assert IDX.resolve("azurerm_linux_web_app", "site_config[0]", {"kind": "withheld", "reason": "secret"}) == \
        (None, "withheld_block")
    assert IDX.resolve("azurerm_linux_web_app", "site_config[0].application_stack", lit("x")) == \
        (None, "block_without_leaf")


def test_data_address_and_module():
    assert is_data_address("data.azurerm_client_config.SYM-0a1b2c3d4e5f")
    assert is_data_address("module.SYM-0a1b2c3d4e5f.data.azurerm_subnet.SYM-0a1b2c3d4e5f")
    assert not is_data_address("module.SYM-0a1b2c3d4e5f.azurerm_subnet.SYM-0a1b2c3d4e5f")
    assert module_of("SYM-0a1b2c3d/main.tf") == "SYM-0a1b2c3d"
    assert module_of("main.tf") == ""


def test_repo_usage_rows_and_precedence():
    rg1, rg2 = "azurerm_resource_group.SYM-abcdef000001", "azurerm_resource_group.SYM-abcdef000002"
    nsg = "azurerm_network_security_group.SYM-abcdef000003"
    resources = [("a/main.tf", rg1, "azurerm_resource_group", F), ("b/main.tf", rg2, "azurerm_resource_group", F),
                 ("a/main.tf", nsg, "azurerm_network_security_group", F),
                 ("a/main.tf", "azurerm_app_service.SYM-abcdef000004", "azurerm_app_service", F)]
    records = [
        rec("a/main.tf", rg1, "azurerm_resource_group", "name", lit("x")),
        rec("a/main.tf", rg1, "azurerm_resource_group", "location", sym("variable")),
        rec("b/main.tf", rg2, "azurerm_resource_group", "name", sym("variable")),
        rec("b/main.tf", rg2, "azurerm_resource_group", "depends_on", lit([], "list")),
        rec("a/main.tf", nsg, "azurerm_network_security_group", "security_rule[0].access", lit("Allow")),
        rec("a/main.tf", nsg, "azurerm_network_security_group", "security_rule[1].access", sym("variable")),
        rec("a/main.tf", "azurerm_app_service.SYM-abcdef000004", "azurerm_app_service", "name", lit("x")),
        rec("a/main.tf", "data.azurerm_resource_group.SYM-abcdef000005", "azurerm_resource_group", "name", lit("x")),
        rec("a/main.tf", "aws_s3_bucket.SYM-abcdef000006", "aws_s3_bucket", "bucket", lit("x"), provider="aws"),
        rec("a/main.tf", "azurerm_resource_group.SYM-abcdef00000f", "azurerm_resource_group", "name", lit("x")),
    ]
    u = repo_usage("azurerm", R, resources, records, IDX)
    rows = {(r["resource_type"], r.get("atom_id")): r for r in u["rows"]}
    name = rows[("azurerm_resource_group", "azurerm:azurerm_resource_group:name")]
    assert (name["n_resources"], name["n_set"], name["n_literal"], name["n_symbolic"]) == (2, 2, 1, 1)
    loc = rows[("azurerm_resource_group", "azurerm:azurerm_resource_group:location")]
    assert (loc["n_set"], loc["n_symbolic"]) == (1, 1)
    rg = rows[("azurerm_resource_group", None)]
    assert (rg["n_resources"], rg["n_set"], rg["n_literal"], rg["n_symbolic"]) == (2, 2, 0, 2)
    sr = rows[("azurerm_network_security_group", "azurerm:azurerm_network_security_group:security_rule")]
    assert (sr["n_set"], sr["n_literal"], sr["n_symbolic"]) == (1, 0, 1)  # literal só se toda ocorrência é
    app = rows[("azurerm_app_service", None)]
    assert (app["n_resources"], app["n_set"]) == (1, 0)
    assert not any(r.get("atom_id", "").startswith("azurerm:azurerm_app_service") for r in u["rows"])
    for r in u["rows"]:
        assert r["n_literal"] + r["n_symbolic"] + r["n_withheld"] == r["n_set"] <= r["n_resources"]
        assert r["provider"] == "azurerm" and r["family_id"] == F
    assert u["atom_modules"]["azurerm:azurerm_resource_group:name"] == 2
    assert u["n_modules"] == 2
    au = u["audit"]
    assert au["records_provider"] == 9 and au["records_data_source"] == 1 and au["records_orphan"] == 1
    assert au["unmatched:meta_argument"] == 1 and au["unmatched:type_not_in_schema"] == 1
    assert au["records_matched_object_attr"] == 2
    # ordem determinística: tipo, depois átomos em ordem
    keys = [(r["resource_type"], r.get("atom_id", "")) for r in u["rows"]]
    assert keys == sorted(keys)


def test_repo_without_records_keeps_type_rows():
    resources = [("main.tf", "azurerm_resource_group.SYM-abcdef000001", "azurerm_resource_group", F)]
    u = repo_usage("azurerm", R, resources, [], IDX)
    assert u["rows"] == [{"repo_id": R, "family_id": F, "provider": "azurerm",
                          "resource_type": "azurerm_resource_group", "n_resources": 1, "n_set": 0,
                          "n_literal": 0, "n_symbolic": 0, "n_withheld": 0}]
