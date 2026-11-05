"""Um stub mínimo válido por arquivo de cada contrato (contracts/stubs/<Cnn>/...), mais contracts/stubs/complex.sssom.tsv
(grupo sobre subgrafo, projeção por ocorrência e realizações alternativas guardadas).

Tudo sintético: nenhum id de conta, ARN, nome de recurso real, projeto, e-mail ou valor da empresa. Nomes de tipo do
Terraform (aws_s3_bucket…) são nomes de schema público, não de recurso. Os stubs são gerados aqui (build) e
gravados byte a byte; o INDEX.json diz o tipo de arquivo de cada um."""

from __future__ import annotations

import copy
import hashlib
import io
import json

import yaml

from ._base import PKG, dumps, jsonl

TS = "2026-11-03T08:00:00-03:00"
TS2 = "2026-11-03T09:30:00-03:00"
TS3 = "2026-11-03T11:00:00-03:00"
DAY = "2026-11-03"


def H(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def yml(d) -> str:
    return yaml.safe_dump(d, sort_keys=False, allow_unicode=True, default_flow_style=False)


def adopted(name: str):
    return json.loads((PKG / "adopted" / f"{name}.json").read_text(encoding="utf-8"))


def hdr(schema: str, cid: str, ver: str, module="EXAMPLE-MOD", gen=True) -> dict:
    d = {"schema": schema, "contract": cid, "contract_version": ver, "module": module}
    if gen:
        d["generated_at"] = TS
    return d


EV_DOC = {"level": "published", "doc": {"repo": "hashicorp/terraform-provider-aws", "tag": "v6.0.0",
                                        "file": "website/docs/r/db_instance.html.markdown", "line": 120,
                                        "sentence": "frase sintética de documentação que sustenta o fato"}}
EV_REF = {"level": "derived", "ref": "DF-aws-0001"}
SYM1, SYM2, SYM3, SYM4 = "SYM-0a1b2c3d4e5f", "SYM-1a2b3c4d5e6f", "SYM-2b3c4d5e6f70", "SYM-3c4d5e6f7081"
REPO1, FAM1, FAM2, REPO2, REPO3 = "R-00a1b2c3d4e5", "F-00a1b2c3d4e5", "F-11b2c3d4e5f6", "R-11b2c3d4e5f6", "R-22c3d4e5f607"


# ------------------------------------------------------------------------------------------------- C00
def c00() -> dict:
    mod = {"id": "EXAMPLE-MOD", "stable_id": "EXAMPLE-MOD", "wave": 0, "deps": [],
           "inputs": ["$BO_REPO/CONVENTIONS.html"], "outputs": ["$BO_REPO/results/EXAMPLE-MOD/"],
           "gates": ["python -I -m bo.contracts.validate --all-stubs"], "contracts": ["C00"],
           "worktree": "/srv/lanes/bo-example-mod", "branch": "bo/example-mod",
           "owns": ["$BO_REPO/results/EXAMPLE-MOD/", "$BO_DATA/EXAMPLE-MOD/"], "tmp_dir": "$BO_DATA/tmp/EXAMPLE-MOD"}
    mod2 = {**copy.deepcopy(mod), "id": "EXAMPLE-NEXT", "stable_id": "EXAMPLE-NEXT", "wave": 1, "deps": ["EXAMPLE-MOD"],
            "inputs": ["$BO_REPO/results/EXAMPLE-MOD/"], "outputs": ["$BO_REPO/results/EXAMPLE-NEXT/{provider}.json"],
            "worktree": "/srv/lanes/bo-example-next", "branch": "bo/example-next",
            "owns": ["$BO_REPO/results/EXAMPLE-NEXT/"], "tmp_dir": "$BO_DATA/tmp/EXAMPLE-NEXT"}
    cat = {"project": "catálogo sintético de exemplo", "generated_at": TS, "timezone": "America/Recife",
           "plan_version": 3, "env": {"BO_REPO": "/srv/bo", "BO_DATA": "/srv/bo-data", "BO_TMP": "$BO_DATA/tmp/<ID>"},
           "index_sets": {"provider": ["aws", "google", "azurerm", "oci"],
                          "pair": ["AWSGCP", "AWSAZ", "AWSOCI", "GCPAZ", "GCPOCI", "AZOCI"],
                          "domain": ["CMP", "NET", "STO", "DB", "SEC", "OPS"], "slice": ["sto", "net"],
                          "model": ["kalinin"], "candidate": ["none"], "probe_type": ["item_ttl"],
                          "control": ["c1_table", "c2_taxonomy", "c3_full"], "lens": ["R1"],
                          "version": "dynamic:$BO_DATA/HIST-*/versions.json"},
           "contracts": {"C00": {"name": "conventions", "version": "3.0.0"}},
           "modules": [mod, mod2]}
    return {"C00/module.json": dumps(mod), "C00/modulos.json": dumps(cat)}


# ------------------------------------------------------------------------------------------------- C01–C05
def c01() -> dict:
    a1 = {"atom_id": "aws:aws_db_instance:backup_retention_period", "provider": "aws", "provider_version": "6.0.0",
          "resource_type": "aws_db_instance", "path": "backup_retention_period", "block_path": [], "tf_type": "number",
          "nesting": "none", "required": False, "optional": True, "computed": True, "sensitive": False,
          "deprecated": False, "configurable": True}
    a2 = {"atom_id": "aws:aws_s3_bucket_lifecycle_configuration:rule.expiration.days", "provider": "aws",
          "provider_version": "6.0.0", "resource_type": "aws_s3_bucket_lifecycle_configuration",
          "path": "rule.expiration.days",
          "block_path": [{"block": "rule", "nesting_mode": "list", "min_items": 1},
                         {"block": "expiration", "nesting_mode": "list", "max_items": 1}],
          "tf_type": "number", "nesting": "list", "required": False, "optional": True, "computed": False,
          "sensitive": False, "deprecated": False, "configurable": True}
    a3 = {"atom_id": "google:google_sql_user:password_wo", "provider": "google", "provider_version": "8.2.0",
          "resource_type": "google_sql_user", "path": "password_wo", "block_path": [], "tf_type": "string",
          "nesting": "none", "required": False, "optional": True, "computed": False, "sensitive": True,
          "deprecated": False, "configurable": True, "write_only": True}
    a4 = {"atom_id": "azurerm:azurerm_example_nested:settings", "provider": "azurerm", "provider_version": "5.5.0",
          "resource_type": "azurerm_example_nested", "path": "settings", "block_path": [],
          "tf_type": ["list", ["object", {"name": "string", "size": "number"}, ["size"]]], "nesting": "none",
          "required": False, "optional": True, "computed": False, "sensitive": False, "deprecated": False,
          "configurable": True}
    a5 = {"atom_id": "aws:aws_security_group:ingress.from_port", "provider": "aws", "provider_version": "6.71.0",
          "resource_type": "aws_security_group", "path": "ingress.from_port",
          "block_path": [{"block": "ingress", "nesting_mode": "set", "kind": "nested_attribute"}],
          "tf_type": "number", "nesting": "set", "required": False, "optional": True, "computed": False,
          "sensitive": False, "deprecated": False, "configurable": True}
    return {"C01/atoms.jsonl": jsonl([a1, a2, a3, a4, a5])}


def c02() -> dict:
    t = {"type_id": "aws:aws_db_instance", "provider": "aws", "provider_version": "6.0.0",
         "resource_type": "aws_db_instance",
         "counts": {"attributes": 90, "blocks": 4, "required": 1, "optional": 70, "computed": 40, "configurable": 71,
                    "sensitive": 1, "deprecated": 2}, "max_depth": 2, "block_sha256": H("aws_db_instance@6.0.0")}
    return {"C02/types.jsonl": jsonl([t])}


def c03() -> dict:
    f1 = {"fact_id": "DF-aws-0001", "atom_id": "aws:aws_db_instance:backup_retention_period",
          "provider_version": "6.0.0", "fact_kind": "default", "status": "stated", "value": 7, "as_of": DAY,
          "source": EV_DOC["doc"], "extraction_method": "parser", "evidence_level": "published"}
    f2 = {"fact_id": "DF-aws-0002", "atom_id": "aws:aws_db_instance:backup_retention_period",
          "provider_version": "6.0.0", "fact_kind": "unit", "status": "unknown", "unknown_reason": "not_documented",
          "extraction_method": "model", "evidence_level": "interpreted", "model_id": "claude-opus-5-5"}
    f3 = {"fact_id": "DF-aws-0003", "atom_id": "aws:aws_wafv2_rule_group:rule.statement.and_statement.statement.byte_match_statement.search_string",
          "provider_version": "6.0.0", "fact_kind": "description", "status": "stated",
          "value": "texto procurado na requisição",
          "source": {**EV_DOC["doc"], "file": "website/docs/r/wafv2_rule_group.html.markdown", "line": 410,
                     "redacted": False},
          "extraction_method": "parser", "evidence_level": "derived",
          "applies_to": ["aws:aws_wafv2_rule_group:rule.statement.or_statement.statement.byte_match_statement.search_string"]}
    f4 = {"fact_id": "DF-oci-0001", "atom_id": "oci:oci_core_instance:launch_options.network_type",
          "provider_version": "9.11.0", "fact_kind": "applicable_when", "status": "stated",
          "value": {"applicable_when": {"source_type": "image"}},
          "source": {"repo": "oracle/terraform-provider-oci", "tag": "v9.11.0", "file": "website/docs/r/core_instance.html.markdown",
                     "line": 88, "sentence": "frase sintética: aplicável quando a origem é imagem"},
          "extraction_method": "regex", "evidence_level": "published"}
    ts_src = lambda line, sent: {"repo": "hashicorp/terraform-provider-azurerm", "tag": "v5.12.0",  # noqa: E731
                                 "file": "website/docs/r/storage_account.html.markdown", "line": line, "sentence": sent}
    t1 = {"type_id": "azurerm:azurerm_storage_account", "provider": "azurerm", "provider_version": "5.12.0",
          "resource_type": "azurerm_storage_account", "kind": "resource", "in_schema": True,
          "doc_file": "website/docs/r/storage_account.html.markdown",
          "title": {"text": "azurerm_storage_account", "line": 9},
          "subcategory": {"status": "stated", "value": "Storage", "source": ts_src(2, 'subcategory: "Storage"'),
                          "extraction_method": "parser", "evidence_level": "published"},
          "import": {"status": "stated", "supported": True,
                     "value": ["/subscriptions/{subscriptionId}/resourceGroups/{rg}/providers/Microsoft.Storage/storageAccounts/{name}"],
                     "key_sentence": ts_src(400, "Storage Accounts can be imported using the `resource id`, e.g."),
                     "source": ts_src(403, "terraform import azurerm_storage_account.example /subscriptions/{subscriptionId}/..."),
                     "methods": ["terraform_import_cli"], "extraction_method": "regex", "evidence_level": "published"}}
    t2 = {"type_id": "aws:aws_alb", "provider": "aws", "provider_version": "6.0.0", "resource_type": "aws_alb",
          "kind": "resource", "in_schema": True, "doc_file": None,
          "alias_of": {"type_id": "aws:aws_lb", "evidence_level": "derived"},
          "subcategory": {"status": "unknown", "unknown_reason": "not_documented", "extraction_method": "parser",
                          "evidence_level": "published"},
          "import": {"status": "stated", "supported": True, "id_attributes": ["arn"], "id_text": ["the `arn`"],
                     "identity": {"required": ["arn"], "optional": []}, "methods": ["import_block_id"],
                     "statements": [{"line": 120, "sentence": "frase sintética: importe usando o `arn`."}],
                     "extraction_method": "regex", "evidence_level": "published"}}
    t3 = {"type_id": "oci:oci_core_vcns", "provider": "oci", "provider_version": "9.11.0", "resource_type": "oci_core_vcns",
          "kind": "data_source", "doc_file": "website/docs/d/core_vcns.html.markdown",
          "subcategory": {"status": "stated", "value": "Core",
                          "source": {"repo": "oracle/terraform-provider-oci", "tag": "v9.11.0",
                                     "file": "website/docs/d/core_vcns.html.markdown", "line": 2,
                                     "sentence": 'subcategory: "Core"'},
                          "extraction_method": "parser", "evidence_level": "published"}}
    t4 = {"type_id": "google:google_storage_bucket", "provider": "google", "provider_version": "8.9.0",
          "resource_type": "google_storage_bucket", "doc_pages": ["website/docs/r/storage_bucket.html.markdown"],
          "subcategory": {"status": "stated", "value": "Cloud Storage",
                          "source": {"repo": "hashicorp/terraform-provider-google", "tag": "v8.9.0",
                                     "file": "website/docs/r/storage_bucket.html.markdown", "line": 2,
                                     "sentence": 'subcategory: "Cloud Storage"'},
                          "extraction_method": "parser", "evidence_level": "published"},
          "import": {"status": "stated", "id_format": "{{project}}/{{name}}", "id_is_plain_id": False,
                     "placeholders": ["project", "name"],
                     "source": {"repo": "hashicorp/terraform-provider-google", "tag": "v8.9.0",
                                "file": "website/docs/r/storage_bucket.html.markdown", "line": 300,
                                "sentence": "frase sintética: {{project}}/{{name}}"},
                     "extraction_method": "parser", "evidence_level": "published"}}
    return {"C03/docs_facts.jsonl": jsonl([f1, f2, f3, f4]), "C03/type_subcategory.jsonl": jsonl([t1, t2, t3, t4])}


def c04() -> dict:
    return {"C04/roles.jsonl": jsonl([
        {"atom_id": "aws:aws_db_instance:backup_retention_period", "role": "CONFIG", "rule_id": "ROLE-DEFAULT-CONFIG"},
        {"atom_id": "aws:aws_db_instance:identifier", "role": "NAME", "rule_id": "ROLE-NAME-01",
         "evidence": [EV_REF]}])}


def c05() -> dict:
    days = {"atom_id": "aws:aws_db_instance:backup_retention_period", "datatype": {"kind": "scalar", "scalar": "integer"},
            "quantity_kind": "quantitykind:Time", "unit_qudt": "unit:DAY", "rate_window": None,
            "byte_convention": "NOT_APPLICABLE", "range": {"min": 0, "max": 35, "step": 1}, "evidence": [EV_DOC]}
    cls = {"atom_id": "aws:aws_s3_bucket:storage_class", "datatype": {"kind": "scalar", "scalar": "enum"},
           "quantity_kind": "NOT_APPLICABLE", "unit_qudt": "NOT_APPLICABLE", "rate_window": None,
           "byte_convention": "NOT_APPLICABLE", "enum": ["STANDARD", "GLACIER"], "evidence": [EV_REF]}
    size = {"atom_id": "aws:aws_db_instance:allocated_storage", "datatype": {"kind": "scalar", "scalar": "integer"},
            "quantity_kind": "quantitykind:AmountOfData", "unit_qudt": "unit:GibiBYTE", "rate_window": None,
            "byte_convention": "IEC", "range": {"min": 20, "max": 65536}, "evidence": [EV_DOC]}
    rate = {"atom_id": "aws:aws_api_gateway_method_settings:settings.throttling_rate_limit",
            "datatype": {"kind": "scalar", "scalar": "decimal"}, "quantity_kind": "quantitykind:Frequency",
            "unit_qudt": "unit:PER-SEC", "rate_window": "PT1S", "byte_convention": "NOT_APPLICABLE",
            "evidence": [{"level": "interpreted", "ref": "DF-aws-0009", "model_id": "claude-opus-5-5"}]}
    unk = {"atom_id": "aws:aws_db_instance:monitoring_interval", "datatype": {"kind": "scalar", "scalar": "integer"},
           "quantity_kind": "UNKNOWN", "unit_qudt": "UNKNOWN", "rate_window": None, "byte_convention": "NOT_APPLICABLE",
           "evidence": [EV_REF]}
    dur = {"atom_id": "aws:aws_db_instance:timeouts.create", "datatype": {"kind": "scalar", "scalar": "duration"},
           "quantity_kind": "quantitykind:Time", "unit_qudt": "NOT_APPLICABLE", "rate_window": None,
           "byte_convention": "NOT_APPLICABLE", "evidence": [EV_REF]}
    bare = {"atom_id": "aws:aws_s3_object:content_length", "datatype": {"kind": "scalar", "scalar": "integer"},
            "quantity_kind": "quantitykind:AmountOfData", "unit_qudt": "unit:BYTE", "rate_window": None,
            "byte_convention": "NOT_APPLICABLE", "evidence": [EV_REF]}
    gb = {"atom_id": "aws:aws_ebs_volume:size", "datatype": {"kind": "scalar", "scalar": "integer"},
          "quantity_kind": "quantitykind:AmountOfData", "unit_qudt": "UNKNOWN", "rate_window": None,
          "byte_convention": "NOT_APPLICABLE", "unit_candidates": ["unit:GigaBYTE", "unit:GibiBYTE"], "evidence": [EV_REF]}
    iv = {"atom_id": "aws:aws_db_instance:monitoring_interval_s", "datatype": {"kind": "scalar", "scalar": "integer"},
          "quantity_kind": "quantitykind:Time", "unit_qudt": "unit:SEC", "rate_window": None,
          "byte_convention": "NOT_APPLICABLE", "allowed_values": [0, 1, 5, 60], "evidence": [EV_DOC]}
    cpu = {"atom_id": "oci:oci_core_instance:shape_config.ocpus", "datatype": {"kind": "scalar", "scalar": "decimal"},
           "quantity_kind": "quantitykind:Count", "unit_qudt": "unit:NUM", "rate_window": None,
           "byte_convention": "NOT_APPLICABLE", "counted": "ocpu", "evidence": [EV_REF]}
    tre = {"atom_id": "aws:aws_lb_target_group:health_check.matcher_ports", "datatype": {"kind": "tree", "format": "list",
                                                                                    "value_scalar": "integer"},
           "quantity_kind": "quantitykind:Count", "unit_qudt": "unit:NUM", "rate_window": None,
           "byte_convention": "NOT_APPLICABLE", "range": {"min": 1, "max": 65535}, "evidence": [EV_REF]}
    return {"C05/value_space.jsonl": jsonl([days, cls, size, rate, unk, dur, bare, gb, iv, cpu, tre])}


# ------------------------------------------------------------------------------------------------- C06
def c06() -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq
    lit = {"repo_id": REPO1, "family_id": FAM1, "file": "modules/db/main.tf",
           "resource_address": f"aws_db_instance.{SYM1}", "resource_type": "aws_db_instance", "provider": "aws",
           "attr_path": "backup_retention_period", "term": {"kind": "literal", "datatype": "number", "value": 7}}
    ref = {**lit, "attr_path": "db_subnet_group_name",
           "term": {"kind": "reference", "target_type": "aws_db_subnet_group",
                    "target_address": f"aws_db_subnet_group.{SYM2}", "attribute": "name"}}
    doc = {**lit, "resource_address": f"module.{SYM3}.aws_s3_bucket_policy.{SYM4}", "resource_type": "aws_s3_bucket_policy",
           "attr_path": "policy",
           "term": {"kind": "document", "format": "policy_json",
                    "tree": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": SYM1},
                                                                     "Action": "s3:GetObject", "Resource": SYM2}]},
                    "symbolized": [{"path": "/Statement/0/Principal/AWS", "symbol_id": SYM1, "role": "principal"},
                                   {"path": "/Statement/0/Resource", "symbol_id": SYM2, "role": "identifier"}]}}
    expr = {**lit, "attr_path": "allocated_storage",
            "term": {"kind": "expression", "op": "max",
                     "args": [{"kind": "symbol", "symbol_id": SYM3, "name_class": "variable", "scope": "repo"},
                              {"kind": "literal", "datatype": "number", "value": 20}]}}
    wh = {**lit, "attr_path": "password", "term": {"kind": "withheld", "reason": "secret"}}
    lst = {**lit, "resource_address": f"aws_instance.{SYM4}", "resource_type": "aws_instance",
           "attr_path": "vpc_security_group_ids",
           "term": {"kind": "list", "items": [
               {"kind": "reference", "target_type": "aws_security_group",
                "target_address": f"aws_security_group.{SYM1}", "attribute": "id"},
               {"kind": "symbol", "symbol_id": SYM2, "name_class": "variable", "scope": "repo"}]}}
    rows = [{"repo_id": REPO1, "family_id": FAM1, "file": "modules/db/main.tf",
             "resource_address": f"aws_db_instance.{SYM1}", "resource_type": "aws_db_instance", "provider": "aws",
             "n_attrs": 12, "has_count": False, "has_for_each": False, "module_depth": 0},
            {"repo_id": REPO1, "family_id": FAM1, "file": "modules/db/main.tf",
             "resource_address": f"aws_db_subnet_group.{SYM2}", "resource_type": "aws_db_subnet_group",
             "provider": "aws", "n_attrs": 3, "has_count": True, "has_for_each": False, "module_depth": 1}]
    schema = pa.schema([("repo_id", pa.string()), ("family_id", pa.string()), ("file", pa.string()),
                        ("resource_address", pa.string()), ("resource_type", pa.string()), ("provider", pa.string()),
                        ("n_attrs", pa.int64()), ("has_count", pa.bool_()), ("has_for_each", pa.bool_()),
                        ("module_depth", pa.int64())])
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), buf, compression="NONE", write_statistics=False)
    usage = {"repo_id": REPO1, "family_id": FAM1, "provider": "aws", "resource_type": "aws_db_instance",
             "atom_id": "aws:aws_db_instance:backup_retention_period", "n_resources": 1, "n_set": 1, "n_literal": 1,
             "n_symbolic": 0, "n_withheld": 0}
    return {"C06/symbolic_config.jsonl": jsonl([lit, ref, doc, expr, wh, lst]), "C06/resources.parquet": buf.getvalue(),
            "C06/usage.jsonl": jsonl([usage])}


# ------------------------------------------------------------------------------------------------- C07–C08
def c07() -> dict:
    u = {**hdr("bo.universe/1", "C07", "3.0.0", "UNIVERSE"),
         "rule": {"rule_id": "U-RULE-01", "text": "unidades canônicas do pin com domínio declarado e evidência"},
         "closure": {"rule": "fecho por referência obrigatória até ponto fixo", "iterations": 2, "fixed_point": True},
         "seed": 20261103, "split_ref": {"path": "$BO_DATA/SPLIT/split.json", "sha256": H("split")},
         "units": [{"unit_id": "CU-aws-db-instance", "provider": "aws", "domain": "DB", "rule_id": "U-RULE-01",
                    "in_universe": True},
                   {"unit_id": "CU-aws-db-backup-window", "provider": "aws", "domain": "DB", "rule_id": "U-RULE-01",
                    "in_universe": False, "reason": "faceta sem evidência de dono"}],
         "pilot_exposed": {"CU-aws-db-instance": True, "CU-aws-db-backup-window": False},
         "holdout": {"encrypted_sha256": H("holdout"), "path": "$BO_DATA/SPLIT/sealed/holdout.jsonl.age",
                     "cipher": "age", "recipient_fingerprint": "age1" + "q" * 58}}
    return {"C07/universe.json": dumps(u)}


def c08() -> dict:
    sub = {"nodes": [{"node_id": "n0", "kind": "unit", "ref": "CU-aws-db-instance"},
                     {"node_id": "n1", "kind": "atom", "ref": "aws:aws_db_instance:backup_retention_period"}],
           "edges": [{"from": "n1", "to": "n0", "kind": "facet_of"}], "cross_facets": []}
    obj = {"nodes": [{"node_id": "n0", "kind": "unit", "ref": "CU-google-sql-instance"},
                     {"node_id": "n1", "kind": "atom",
                      "ref": "google:google_sql_database_instance:settings.backup_configuration.backup_retention_settings.retained_backups"}],
           "edges": [{"from": "n1", "to": "n0", "kind": "component_of"}], "cross_facets": ["n1"]}
    c = {"candidate_id": "CAND-AWSGCP-DB-0001", "pair": "AWSGCP", "domain": "DB", "subject_provider": "aws",
         "object_provider": "google", "subject": sub, "object": obj, "concept": "concept:backup_retention",
         "features": {"name_similarity": 0.62, "same_quantity_kind": True}, "generated_by": "CAND"}
    return {"C08/candidates.jsonl": jsonl([c])}


# ------------------------------------------------------------------------------------------------- C09
T_INT_DAYS = {"datatype": "integer", "quantity_kind": "quantitykind:Time", "unit": "unit:DAY",
              "range": {"min": 0, "max": 35}}
T_INT_DAYS_B = {"datatype": "integer", "quantity_kind": "quantitykind:Time", "unit": "unit:DAY",
                "range": {"min": 0, "max": 365}}
PROOF = {"type": "normalization", "evidence": [{"date": DAY, "source": "fixture:doc-sintetica",
                                                 "sentence": "frase sintética que sustenta a alegação"}],
         "tests": [{"input": 7, "expected": 7}]}


def claim(cid, ver, subj, rel, obj, **kw) -> dict:
    pred = {"exact": "skos:exactMatch", "close": "skos:closeMatch", "broad": "skos:broadMatch",
            "narrow": "skos:narrowMatch", "related": "skos:relatedMatch"}[rel]
    r = {"subject_id": subj, "predicate_id": pred, "object_id": obj, "mapping_justification": "semapv:ManualMappingCuration",
         "claim_id": cid, "claim_version_id": f"{cid}@{ver}", "event_id": f"EV-{cid}-{ver}", "semantic_relation": rel,
         "value_domain_relation": {"relation": "subset", "orientation": "subject_to_object"},
         "transport_fidelity": "lossless", "guard": {"all": []}, "translation_fn": {"name": "identity", "params": {}},
         "loss_contract": [], "proof": PROOF, "evidence_state": "DOC_SUPPORTED", "basis": "direct",
         "subject_concept": "concept:backup_retention", "object_concept": "concept:backup_retention",
         "subject_value_type": T_INT_DAYS, "object_value_type": T_INT_DAYS_B}
    r.update(kw)
    return r


def c09_records() -> list[dict]:
    v1 = claim("CLM-EX-01", 1, "pa:backup_retention_days", "exact", "pb:backup_retention_days",
               evidence_state="STRUCTURALLY_VALID")
    v2 = claim("CLM-EX-01", 2, "pa:backup_retention_days", "exact", "pb:backup_retention_days",
               supersedes="CLM-EX-01@1", confidence=0.9)
    br = claim("CLM-BR-01", 1, "pa:archive_class", "broad", "pb:storage_class",
               translation_fn={"name": "enum_map", "params": {"table": {"deep_archive": "archive",
                                                                        "flexible_retrieval": "coldline"}}},
               membership_predicate={"subset": "subject", "expr": {"op": "in", "values": ["coldline", "archive"]},
                                     "tests": {"members": ["archive"], "non_members": ["standard"]}},
               proof={"type": "membership", "evidence": PROOF["evidence"],
                      "tests": [{"input": "deep_archive", "expected": "archive"}]},
               subject_concept="bo:UNGLOSSED", object_concept="bo:UNGLOSSED",
               subject_value_type={"datatype": "enum", "enum": ["flexible_retrieval", "deep_archive"],
                                   "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"},
               object_value_type={"datatype": "enum", "enum": ["standard", "nearline", "coldline", "archive"],
                                  "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"})
    none = claim("CLM-NONE-01", 1, "pa:spin_rate", "related", "sssom:NoTermFound", translation_fn=None,
                 transport_fidelity="none", loss_contract=[],
                 value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
                 proof={"type": "absence", "evidence": PROOF["evidence"], "tests": []},
                 evidence_state="STRUCTURALLY_VALID", subject_concept="concept:backup_retention",
                 object_concept="bo:UNGLOSSED", object_value_type={"datatype": "integer", "quantity_kind": "UNKNOWN",
                                                                   "unit": "UNKNOWN"},
                 absence={"kind": "ABSENCE_DEMONSTRATED", "block_code": "NO_REALIZATION",
                          "searched": ["atributos do tipo e vizinhos por referência no pin"],
                          "evidence": [{"date": DAY, "source": "fixture:pacote-sintetico"}]})
    legacy = {**copy.deepcopy(none), "claim_id": "CLM-NONE-02", "claim_version_id": "CLM-NONE-02@1",
              "event_id": "EV-CLM-NONE-02-1", "subject_id": "pa:spin_window", "curation_rule": "bo:NONE_OUT_OF_PIN"}
    legacy.pop("absence")
    hunt = claim("CLM-HUNT-01", 1, "pa:spin_rate", "close", "pb:rotation_speed", disputes=["CLM-NONE-01"],
                 evidence_state="STRUCTURALLY_VALID")
    pfx = {"datatype": "list", "item_type": {"datatype": "string", "quantity_kind": "NOT_APPLICABLE",
                                             "unit": "NOT_APPLICABLE"},
           "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}
    lst = claim("CLM-LIST-01", 1, "pb:address_prefixes", "exact", "pc:cidr_blocks", subject_value_type=pfx,
                object_value_type=pfx, value_domain_relation={"relation": "equal", "orientation": "subject_to_object"},
                subject_concept="bo:UNGLOSSED", object_concept="bo:UNGLOSSED",
                proof={"type": "normalization", "evidence": PROOF["evidence"],
                       "tests": [{"input": ["10.0.0.0/16"], "expected": ["10.0.0.0/16"]}]})
    obj_none = {**copy.deepcopy(none), "claim_id": "CLM-NONE-03", "claim_version_id": "CLM-NONE-03@1",
                "event_id": "EV-CLM-NONE-03-1", "subject_id": "sssom:NoTermFound", "object_id": "pb:spin_window",
                "subject_concept": "bo:UNGLOSSED", "object_concept": "concept:backup_retention",
                "subject_value_type": none["object_value_type"], "object_value_type": none["subject_value_type"],
                "absence": {**none["absence"], "side": "object"}}
    return [v1, v2, br, none, legacy, hunt, lst, obj_none]


EDITION_STD = [{"term": "object.edition", "op": "edition_in", "value": ["standard"]}]
EDITION_PREM = [{"term": "object.edition", "op": "edition_in", "value": ["premium"]}]
PORT_GROUP = {
    "bo_group_id": "GRP-PORTS-01", "cardinality": "N:M",
    "variables": [
        {"name": "?proto", "side": "subject", "field": "pa:rule.protocol", "occurrence": "?r"},
        {"name": "?from", "side": "subject", "field": "pa:rule.from_port", "occurrence": "?r"},
        {"name": "?to", "side": "subject", "field": "pa:rule.to_port", "occurrence": "?r"},
        {"name": "?proto_b", "side": "object", "field": "pb:allow.protocol", "occurrence": "?a"},
        {"name": "?ports", "side": "object", "field": "pb:allow.ports", "occurrence": "?a"}],
    "occurrence_vars": ["?r", "?a"], "joins": [],
    "steps": [{"name": "identity", "inputs": {"value": "?proto"}, "outputs": {"value": "?proto_b"}},
              {"name": "join_port_range", "inputs": {"from_port": "?from", "to_port": "?to"},
               "outputs": {"ports": "?ports"}}]}
CIDR_GROUP = {
    "bo_group_id": "GRP-CIDR-01", "cardinality": "N:1",
    "variables": [
        {"name": "?addr", "side": "subject", "field": "pa:network.base_address", "occurrence": "?n"},
        {"name": "?plen", "side": "subject", "field": "pa:subnet_sizing.prefix_length", "occurrence": "?s"},
        {"name": "?cidr", "side": "object", "field": "pb:subnet.cidr", "occurrence": "?b"}],
    "occurrence_vars": ["?n", "?s", "?b"], "joins": [{"left": "?s", "right": "?n", "via": "facet_of"}],
    "steps": [{"name": "join_cidr", "inputs": {"address": "?addr", "prefix_length": "?plen"},
               "outputs": {"cidr": "?cidr"}}]}
PORT_T = {"datatype": "integer", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE",
          "range": {"min": 0, "max": 65535}}
PROJ = [
    {"projection_id": "PRJ-LST-from", "field": "pa:listener.port_range",
     "occurrence": {"scope": "block", "key_fields": ["protocol", "port_range"]},
     "extractor": {"name": "split_port_range", "component": "from_port"}, "concept": "concept:listener_port_from",
     "type": PORT_T, "tests": [{"input": "80-443", "expected": 80}]},
    {"projection_id": "PRJ-LST-to", "field": "pa:listener.port_range",
     "occurrence": {"scope": "block", "key_fields": ["protocol", "port_range"]},
     "extractor": {"name": "split_port_range", "component": "to_port"}, "concept": "concept:listener_port_to",
     "type": PORT_T, "tests": [{"input": "80-443", "expected": 443}]}]
TUPLE_T = {"datatype": "tuple", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}
BOOL_T = {"datatype": "boolean", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}
ENUM_T = {"datatype": "enum", "enum": ["enabled", "suspended"], "quantity_kind": "NOT_APPLICABLE",
          "unit": "NOT_APPLICABLE"}


def complex_records() -> list[dict]:
    na = {"subject_concept": "bo:UNGLOSSED", "object_concept": "bo:UNGLOSSED", "evidence_state": "STRUCTURALLY_VALID",
          "proof": {"type": "group_execution", "evidence": [], "tests": [{"input": {"?from": 80, "?to": 443},
                                                                          "expected": {"?ports": "80-443"}}]}}
    grp = claim("CLM-GRP-PORTS-01", 1, "pa:rule", "exact", "pb:allow", translation_fn=None,
                bo_group_id="GRP-PORTS-01", group=PORT_GROUP, subject_value_type=TUPLE_T, object_value_type=TUPLE_T,
                value_domain_relation={"relation": "equal", "orientation": "subject_to_object"}, **na)
    cidr = claim("CLM-GRP-CIDR-01", 1, "pa:network.base_address", "exact", "pb:subnet.cidr", translation_fn=None,
                 bo_group_id="GRP-CIDR-01", group=CIDR_GROUP, subject_value_type=TUPLE_T,
                 object_value_type={"datatype": "string", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"},
                 value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
                 transport_fidelity="partial", **na)
    prj = claim("CLM-PRJ-LST-01", 1, "pa:listener.port_range", "exact", "pb:listener.from_port",
                translation_fn={"name": "split_port_range", "params": {}}, projection=PROJ,
                subject_value_type={"datatype": "string", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"},
                object_value_type=PORT_T, value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
                transport_fidelity="partial", **na)
    alt_std = claim("CLM-ALT-VER-STD", 1, "pa:versioning", "exact", "pb:versioning.mode",
                    guard={"all": EDITION_STD}, alternative_to=["CLM-ALT-VER-PREM"], exclusivity="ProvenExclusive",
                    subject_value_type=ENUM_T, object_value_type=ENUM_T,
                    proof={"type": "normalization", "evidence": PROOF["evidence"],
                           "tests": [{"input": "enabled", "expected": "enabled"}]},
                    value_domain_relation={"relation": "equal", "orientation": "subject_to_object"},
                    subject_concept="concept:object_versioning", object_concept="concept:object_versioning")
    alt_prem = claim("CLM-ALT-VER-PREM", 1, "pa:versioning", "close", "pb:retention_lock.enabled",
                     guard={"all": EDITION_PREM}, alternative_to=["CLM-ALT-VER-STD"], exclusivity="ProvenExclusive",
                     translation_fn={"name": "enum_map", "params": {"table": {"enabled": True, "suspended": False}}},
                     loss_contract=[{"kind": "semantic", "values": ["suspended"],
                                     "what": "suspenso e nunca ativado caem em false"}],
                     transport_fidelity="declared_loss", subject_value_type=ENUM_T, object_value_type=BOOL_T,
                     proof={"type": "loss_declared", "evidence": PROOF["evidence"],
                            "tests": [{"input": "enabled", "expected": True}]},
                     value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
                     subject_concept="concept:object_versioning", object_concept="bo:UNGLOSSED")
    return [grp, cidr, prj, alt_std, alt_prem]


def c09() -> dict:
    from bo.semantics import edoal
    from .sssom import write_tsv
    recs = c09_records()
    g, _ = edoal.export([recs[1]], uri="https://example.org/alignment/stub")
    from bo.semantics.sssom_io import PREFIXES
    px = {**PREFIXES, "sssom": "https://w3id.org/sssom/"}
    return {"C09/correspondences.sssom.tsv": write_tsv(recs, "https://example.org/mapping-set/contracts-stub", px),
            "C09/correspondences.jsonl": jsonl(recs),
            "C09/correspondences.edoal.ttl": g.serialize(format="turtle"),
            "complex.sssom.tsv": write_tsv(complex_records(), "https://example.org/mapping-set/contracts-complex")}


# ------------------------------------------------------------------------------------------------- C10
def c10() -> dict:
    tdoc = {**hdr("bo.transforms/1", "C10", "3.1.0", "TRANSFORMS"),
            "scalar": [
                {"name": "identity", "kind": "scalar",
                 "domain": {"datatype": "any", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"},
                 "codomain": {"datatype": "any", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"},
                 "precondition": "nenhuma", "error": "nunca", "loss": "nenhuma",
                 "inverse": {"name": "identity", "partial": False}},
                {"name": "unit_convert", "kind": "scalar",
                 "domain": {"datatype": "number", "quantity_kind": "quantitykind:Time", "unit": "unit:HR"},
                 "codomain": {"datatype": "number", "quantity_kind": "quantitykind:Time", "unit": "unit:DAY"},
                 "precondition": "mesma grandeza; fatores fixos", "error": "OutOfDomain se mês/ano",
                 "loss": "arredondamento declarado à parte", "inverse": {"name": "unit_convert", "partial": True},
                 "params": {"from": {"type": "string"}, "to": {"type": "string"}}},
                {"name": "number_to_duration", "kind": "scalar",
                 "domain": {"datatype": "integer", "quantity_kind": "quantitykind:Time", "unit": "unit:SEC"},
                 "codomain": {"datatype": "duration", "quantity_kind": "quantitykind:Time", "unit": "NOT_APPLICABLE"},
                 "precondition": "segundos inteiros", "error": "OutOfDomain", "loss": "nenhuma",
                 "inverse": {"name": None, "partial": False}, "duration_calendar": "forbidden"}],
            "combinators": [
                {"name": "split_port_range", "kind": "tuple", "inputs": [{"name": "ports", "datatype": "string"}],
                 "outputs": [{"name": "from_port", "datatype": "integer"}, {"name": "to_port", "datatype": "integer"}],
                 "precondition": "texto 'p1-p2' com p1 <= p2", "error": "OutOfDomain", "loss": "nenhuma",
                 "inverse": {"name": "join_port_range", "partial": False}},
                {"name": "join_port_range", "kind": "tuple",
                 "inputs": [{"name": "from_port", "datatype": "integer"}, {"name": "to_port", "datatype": "integer"}],
                 "outputs": [{"name": "ports", "datatype": "string"}], "precondition": "from_port <= to_port",
                 "error": "OutOfDomain", "loss": "nenhuma", "inverse": {"name": "split_port_range", "partial": False}},
                {"name": "wrap_list", "kind": "tuple", "inputs": [{"name": "value", "datatype": "string"}],
                 "outputs": [{"name": "items", "datatype": "list",
                              "item_type": {"datatype": "string", "quantity_kind": "NOT_APPLICABLE",
                                            "unit": "NOT_APPLICABLE"}}],
                 "precondition": "valor escalar presente", "error": "nunca", "loss": "nenhuma",
                 "inverse": {"name": "unwrap_single", "partial": True}},
                {"name": "list_to_set", "kind": "tuple",
                 "inputs": [{"name": "items", "datatype": "list", "item_type": {"datatype": "any"}}],
                 "outputs": [{"name": "items", "datatype": "set", "item_type": {"datatype": "any"}}],
                 "precondition": "lista sem repetição", "error": "OutOfDomain", "loss": "ordem",
                 "inverse": {"name": None, "partial": False}},
                {"name": "unwrap_single", "kind": "tuple",
                 "inputs": [{"name": "items", "datatype": "list",
                             "item_type": {"datatype": "string", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE"}}],
                 "outputs": [{"name": "value", "datatype": "string"}], "precondition": "lista com um elemento",
                 "error": "OutOfDomain", "loss": "nenhuma", "inverse": {"name": "wrap_list", "partial": False}}]}
    gram = adopted("C10_conditions_grammar")
    gram["sat_tests"] = [
        {"test_id": "SAT-EDITION-ONE", "guard": {"all": EDITION_STD}, "expected": "SAT"},
        {"test_id": "SAT-EDITION-DISJ", "guard": {"all": EDITION_STD + EDITION_PREM}, "expected": "UNSAT"},
        {"test_id": "SAT-KIND-OPEN", "guard": {"all": [
            {"term": "object.target", "op": "refers_to_kind", "value": "subnet"},
            {"term": "object.target", "op": "refers_to_kind", "value": "network_interface"}]}, "expected": "UNKNOWN"}]
    comp = adopted("C10_composition_table_stub")
    return {"C10/transforms.yaml": yml(tdoc), "C10/conditions.grammar.json": dumps(gram),
            "C10/composition_table.json": dumps(comp), "C10/guard.json": dumps({"all": EDITION_STD})}


# ------------------------------------------------------------------------------------------------- C11–C13
def c11() -> dict:
    c = {"case_id": "CASE-AWSGCP-DB-0001", "group_id": "G-AWSGCP-DB-0001", "claim_id": "CLM-EX-01",
         "claim_version_id": "CLM-EX-01@2",
         "stratum": {"pair": "AWSGCP", "domain": "DB", "cardinality": "1:1", "relation": "exact", "direction": "forward"},
         "frame_ref": {"path": "$BO_DATA/DEPSAMPLE/frame.jsonl", "sha256": H("frame")}, "weight": 12.5,
         "origin": "sample", "side": "object", "lowering_plan": {"plan_id": "LP-HG-BUCKET", "graph_id": "GIR-HG-BUCKET"},
         "values": [{"var": "pa:backup_retention_days", "term": {"kind": "literal", "datatype": "number", "value": 7}}],
         "comparator": {"name": "exact"}, "cost_class": "low"}
    c2 = {**copy.deepcopy(c), "case_id": "CASE-CQ-0001", "origin": "cq", "cq_id": "CQ-CVO-04",
          "comparator": {"name": "numeric_tolerance", "tolerance": 0}}
    return {"C11/cases.jsonl": jsonl([c, c2])}


def c12() -> dict:
    rb = {"readback_id": "RB-0001", "case_id": "CASE-AWSGCP-DB-0001", "group_id": "G-AWSGCP-DB-0001",
          "claim_id": "CLM-EX-01", "side": "object", "provider": "google", "read_at": TS2, "protocol_version": "1.0.0",
          "fields": [{"path": "settings.backup_configuration.retained_backups", "state": "read", "value": 7},
                     {"path": "root_password", "state": "withheld",
                      "redaction": {"rule_id": "REDACT-SECRET-01", "at_source": True}},
                     {"path": "settings.insights_config", "state": "not_read"},
                     {"path": "network", "node_id": "r1", "state": "read", "value": "default"},
                     {"path": "network", "node_id": "r2", "state": "read", "value": "default"}]}
    oc = {"outcome_id": "OUT-0001", "case_id": "CASE-AWSGCP-DB-0001", "group_id": "G-AWSGCP-DB-0001",
          "claim_id": "CLM-EX-01", "side": "object", "outcome": {"axis": "persistence", "value": "PERSISTED"},
          "evidence_state_before": "DOC_SUPPORTED", "evidence_state_after": "PERSISTENCE_VERIFIED",
          "readback_id": "RB-0001", "rule_id": "JUDGE-PERSIST-01", "decided_at": TS3}
    oc2 = {**copy.deepcopy(oc), "outcome_id": "OUT-0002", "outcome": {"axis": "persistence", "value": "INFRA_ERROR",
                                                                     "detail": "quota da conta sintética"},
           "evidence_state_after": "DOC_SUPPORTED"}
    oc2.pop("readback_id")
    oc3 = {**copy.deepcopy(oc2), "outcome_id": "OUT-0003",
           "outcome": {"axis": "persistence", "value": "UNKNOWN", "block_code": "UNKNOWN_INPUT",
                       "detail": "obrigatório no destino sem valor na origem"}}
    return {"C12/readback.jsonl": jsonl([rb]), "C12/outcomes.jsonl": jsonl([oc, oc2, oc3])}


def c13() -> dict:
    pins = {**hdr("bo.pins/1", "C13", "3.0.0", "PINS"), "terraform": {"version": "1.13.4", "sha256": H("terraform")},
            "providers": [{"provider": "aws", "source": "registry.terraform.io/hashicorp/aws", "version": "6.0.0",
                           "shasums_sha256": H("aws-shasums"), "schema_sha256": H("aws-schema")},
                          {"provider": "google", "source": "registry.terraform.io/hashicorp/google",
                           "version": "7.0.0", "schema_sha256": H("google-schema")}]}
    vers = {**hdr("bo.versions/1", "C13", "3.0.0", "HIST-AWS"), "provider": "aws",
            "versions": [{"version": "5.90.0", "released_at": "2026-03-01"},
                         {"version": "6.0.0", "released_at": "2026-06-18", "schema_sha256": H("aws-schema")}]}
    evs = [{"event_id": "EV-HIST-aws-0001", "provider": "aws", "resource_type": "aws_db_instance",
            "event_type": "rename", "from_atom": "aws:aws_db_instance:name", "to_atom": "aws:aws_db_instance:db_name",
            "version_interval": {"after": "5.90.0", "until": "6.0.0"}, "evidence": [EV_DOC]},
           {"event_id": "EV-HIST-aws-0002", "provider": "aws", "resource_type": "aws_db_instance",
            "event_type": "addition", "atom_id": "aws:aws_db_instance:dedicated_log_volume",
            "version_interval": {"after": "5.90.0", "until": "6.0.0"}, "evidence": [EV_REF]},
           {"event_id": "EV-HIST-aws-0003", "provider": "aws", "resource_type": "aws_db_instance",
            "event_type": "contract_change", "atom_id": "aws:aws_db_instance:backup_retention_period",
            "change": {"field": "computed", "before": False, "after": True},
            "version_interval": {"after": "5.90.0", "until": "6.0.0"}, "evidence": [EV_REF]}]
    vd_aws = {**hdr("bo.versions/1", "C13", "3.0.0", "PINS"), "provider": "aws",
              "versions": [{"version": "5.90.0", "released_at": "2026-03-01"},
                           {"version": "6.0.0", "released_at": "2026-06-18", "schema_sha256": H("aws-schema")}]}
    sel = lambda v, pub, rel, reasons: {"version": v, "published_at": pub, "released_at": rel, "reasons": reasons,  # noqa: E731
                                        "index_sha256": H("idx-" + v), "protocols": ["5.0"], "darwin_arm64": True,
                                        "linux_amd64": True}
    hist = {**hdr("bo.history_versions/1", "C13", "3.1.0", "PINS"),
            "cutoff": {"date": "2026-11-02", "timezone": "America/Recife", "end_exclusive": "2026-11-03T00:00:00-03:00",
                       "rule": "pin = maior versão estável publicada até o corte"},
            "window": {"start": "2026-01-01", "rule": "estado no fim de cada trimestre e primeira de cada major"},
            "index": {"path": "$BO_DATA/PINS/registry_index/snapshot.json", "sha256": H("snapshot"), "fetched_at": TS},
            "providers": [{"provider": "aws", "source": "registry.terraform.io/hashicorp/aws", "pin": "6.0.0",
                           "index_files": {"registry_v1": {"path": "$BO_DATA/PINS/registry_index/aws_v1.json",
                                                           "sha256": H("v1")},
                                           "registry_v2": {"path": "$BO_DATA/PINS/registry_index/aws_v2.json",
                                                           "sha256": H("v2")}},
                           "versions_doc": vd_aws,
                           "selection": [sel("5.90.0", "2026-03-01T15:00:00Z", "2026-03-01", ["quarter_end:2026Q1"]),
                                         sel("6.0.0", "2026-06-18T20:10:00Z", "2026-06-18",
                                             ["major_first:6", "cutoff:2026-11-02"])],
                           "left_truncation": {"at": "2026-01-01T00:00:00-03:00", "version_in_force": "5.80.0",
                                               "major_in_force": 5, "index_first_version": "0.1.0",
                                               "index_first_published_at": "2017-07-12T17:43:35Z"}}],
            "note": "stub"}
    ah = [{"atom_id": "aws:aws_db_instance:db_name", "provider": "aws", "resource_type": "aws_db_instance",
           "path": "db_name",
           "history": [{"version": "5.90.0", "state": "absent"},
                       {"version": "6.0.0", "state": "present", "tf_type": "string", "required": False,
                        "optional": True, "computed": True, "force_new": True}],
           "first_seen": "6.0.0", "last_seen": "6.0.0", "events": ["EV-HIST-aws-0001"]},
          {"atom_id": "aws:aws_db_instance:name", "provider": "aws", "resource_type": "aws_db_instance", "path": "name",
           "history": [{"version": "5.90.0", "state": "present", "tf_type": "string", "required": False,
                        "optional": True, "computed": True}, {"version": "6.0.0", "state": "absent"}],
           "first_seen": "5.90.0", "last_seen": "5.90.0", "events": ["EV-HIST-aws-0001"]}]
    return {"C13/pins.json": dumps(pins), "C13/versions.json": dumps(vers), "C13/events.jsonl": jsonl(evs),
            "C13/history_versions.json": dumps(hist), "C13/atom_history.jsonl": jsonl(ah)}


# ------------------------------------------------------------------------------------------------- C14
TTL = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix bo: <https://w3id.org/brevops/ontology#> .
@prefix x: <https://example.org/bo-stub#> .

x:Resource a owl:Class .
x:StorageContainer a owl:Class ; rdfs:subClassOf x:Resource .
x:DatabaseInstance a owl:Class ; rdfs:subClassOf x:Resource .
x:Encryptable a owl:Class .
x:backupRetention a owl:DatatypeProperty ;
    rdfs:domain [ a owl:Class ; owl:unionOf ( x:StorageContainer x:DatabaseInstance ) ] .
bo:describesProperty a owl:AnnotationProperty .
bo:of a owl:ObjectProperty .
x:desc_backupRetention a owl:NamedIndividual , bo:PropertyDescriptor ; bo:describesProperty x:backupRetention .
x:real_db_a a owl:NamedIndividual , bo:Realization ; bo:of x:desc_backupRetention .
bo:PropertyDescriptor a owl:Class .
bo:Realization a owl:Class .
"""


def c14() -> dict:
    classes = [{"class_id": "x:Resource", "label": "recurso", "definition": "coisa gerenciada com identidade própria na API",
                "parents": [], "model_role": "Resource",
                "identity": {"fields": ["synthetic_account", "provider", "location", "type", "local_key"],
                             "composite": True}, "status": "active", "evidence_state": "STRUCTURALLY_VALID"},
               {"class_id": "x:EncryptedDatabaseInstance", "label": "instância de banco cifrada",
                "definition": "instância de banco cuja configuração declara cifragem em repouso",
                "parents": [{"iri": "x:DatabaseInstance", "kind": "nested"},
                            {"iri": "x:Encryptable", "kind": "orthogonal", "axis": "proteção de dados"},
                            {"iri": "x:PremiumOnly", "kind": "conditional",
                             "guard": {"all": [{"term": "subject.edition", "op": "edition_in", "value": ["premium"]}]}}],
                "model_role": "Resource", "identity": {"fields": ["provider", "type", "local_key"], "composite": True},
                "status": "active", "evidence_state": "DOC_SUPPORTED"},
               {"class_id": "x:DbInstanceObservedState", "label": "estado observado da instância",
                "definition": "o que a leitura da API devolveu numa hora datada", "parents": [],
                "model_role": "ObservedState", "status": "deprecated", "replaced_by": ["x:Observation"],
                "evidence_state": "UNRESOLVED"}]
    props = [{"property_id": "x:backupRetention", "label": "retenção de backup", "kind": "datatype",
              "domain": {"kind": "union", "classes": ["x:StorageContainer", "x:DatabaseInstance"]},
              "range": "xsd:duration", "definition": "por quanto tempo o backup é mantido",
              "value_marks": ["configured", "default", "observed"], "unknown_marks": ["unknown", "not_read"],
              "status": "active", "evidence_state": "DOC_SUPPORTED"},
             {"property_id": "x:hasListener", "label": "tem ouvinte", "kind": "object",
              "domain": {"kind": "local_restriction", "class": "x:LoadBalancer", "restriction": "some"},
              "range": "x:Listener", "definition": "liga o balanceador a um ouvinte",
              "value_marks": ["configured", "inferred"], "unknown_marks": ["absent", "withheld"],
              "status": "active", "evidence_state": "STRUCTURALLY_VALID"}]
    reals = adopted("C14_realizations_stub")
    return {"C14/classes.jsonl": jsonl(classes), "C14/properties.jsonl": jsonl(props),
            "C14/realizations.jsonl": jsonl(reals), "C14/ontology.ttl": TTL}


# ------------------------------------------------------------------------------------------------- C15–C18
METRIC = {"metric_id": "M-OPCOV-FIELD", "name": "cobertura operacional por campo", "reading": "field",
          "axis": "operational", "quantifier": "observed_fraction",
          "operational_coverage": {"lower": 0.41, "upper": 0.58, "est": 0.47, "n": 120},
          "frame": {"ref": {"path": "$BO_DATA/UNIVERSE/universe.json", "sha256": H("universe")},
                    "description": "unidades do universo U no pin"},
          "inclusion": {"rule_id": "INC-FIELD-01", "text": "átomo configurável com evidência"},
          "weights": {"scheme": "uniform"},
          "joint_uncertainty": {"method": "bootstrap", "level": 0.95, "correlated_with": ["M-PERS-FIELD"]}}
METRIC2 = {**copy.deepcopy(METRIC), "metric_id": "M-PERS-FIELD", "name": "persistência por campo",
           "axis": "persistence", "operational_coverage": {"lower": 0.0, "upper": 1.0, "est": None, "n": 0},
           "joint_uncertainty": {"method": "none"}}
METRIC3 = {**copy.deepcopy(METRIC), "metric_id": "M-PERS-DIR", "name": "persistência numa direção",
           "axis": "persistence", "operational_coverage": {"lower": 0.0, "upper": 1.0, "est": None, "n": 1,
                                                           "n_known": 0},
           "joint_uncertainty": {"method": "none"}}


def c15() -> dict:
    spec = {**hdr("bo.metrics_spec/1", "C15", "3.0.0", "METRICSLIB"),
            "metrics": [{"metric_id": "M-OPCOV-FIELD", "definition": "fração dos campos do universo emitidos em B",
                         "reading": "field", "axis": "operational", "quantifier": "observed_fraction",
                         "frame": "universo U", "inclusion": "INC-FIELD-01", "weights": "uniform",
                         "uncertainty": "bootstrap"}]}
    res = {**hdr("bo.result/1", "C15", "3.1.0", "MATRIX"), "metrics": [METRIC, METRIC2, METRIC3],
           "absence_audit": {"n_absences": 14, "n_audited": 14, "method": "NONEHUNT dirigido por par"},
           "data": {"pairs": 6}}
    summ = {**hdr("bo.summary/1", "C17", "3.0.0", "CAND"), "agent_provenance": AP, "sources": [SRC],
            "results": [METRIC, METRIC2]}
    return {"C15/metrics_spec.yaml": yml(spec), "C15/result.json": dumps(res), "C15/summary.json": dumps(summ)}


AP = {"model_id": "claude-opus-5-5", "brief_path": "/srv/briefs/EXAMPLE-MOD.txt", "brief_sha256": H("brief"),
      "params": {"effort": "maximo"}, "inputs": [{"path": "$BO_REPO/CONVENTIONS.html", "kind": "file",
                                                  "sha256": H("conventions")}], "recorded_at": TS}
SRC = {"uri": "https://registry.terraform.io/providers/hashicorp/aws/6.0.0", "license": "MPL-2.0",
       "transformation": "schema lido com terraform providers schema -json"}


def c16() -> dict:
    idc = {"identity_sha256": H("identidade-sintetica"), "checked_at": TS, "matches_allowlist": True}
    it = {"intent_id": "INT-0001", "module": "DEP-AWS-A", "provider": "aws", "batch_id": "B-AWS-01",
          "case_id": "CASE-AWSGCP-DB-0001", "resource_type": "aws_db_instance", "logical_name": "bo-case-0001",
          "recorded_at": TS, "effective_identity_check": idc, "purge_deadline": "2026-11-04T08:00:00-03:00",
          "max_residual_cost": {"amount": 2.5, "currency": "USD"}, "tag_supported": True, "ttl_supported": False,
          "tags": {"bo-run": "B-AWS-01", "bo-case": "CASE-0001"}}
    runs = [{"run_id": "RUN-0001", "intent_id": "INT-0001", "stage": "intent", "at": TS, "visibility": "public"},
            {"run_id": "RUN-0002", "intent_id": "INT-0001", "stage": "created", "at": TS2, "visibility": "public",
             "effective_identity_check": {**idc, "checked_at": TS2}},
            {"run_id": "RUN-0003", "intent_id": "INT-0001", "stage": "absent", "at": TS3, "visibility": "public",
             "residual_cost": {"amount": 0, "currency": "USD"}}]
    return {"C16/intent_manifest.jsonl": jsonl([it]), "C16/run_manifest.jsonl": jsonl(runs)}


def c17() -> dict:
    from bo.repo import receipts
    summ = {**hdr("bo.summary/1", "C17", "3.0.0"), "agent_provenance": AP, "sources": [SRC], "notes": "stub"}
    rec = {"schema": "bo.freeze_receipt/1", "contract": "C17", "contract_version": "3.0.0", "name": "FREEZE0",
           "owner": "coordenador", "created_at": TS, "note": "",
           "git": {"commit": "0" * 40, "tag": "bo-freeze-FREEZE0"}, "modules": ["EXAMPLE-MOD"],
           "artifacts": [{"path": "$BO_REPO/results/EXAMPLE-MOD/out.json", "kind": "file", "sha256": H("out"),
                          "producers": ["EXAMPLE-MOD"]}],
           "transitive_inputs": [{"path": "$BO_REPO/CONVENTIONS.html", "kind": "file", "sha256": H("conventions"),
                                  "via": "EXAMPLE-MOD"}]}
    rec["digest"] = receipts.receipt_digest(rec)
    rec["ots"] = {"status": "PENDING", "reason": "cliente ots ausente", "digest": rec["digest"]}
    man = f"{H('out')}  results/EXAMPLE-MOD/out.json\n{H('summary')}  $BO_REPO/results/EXAMPLE-MOD/summary.json\n"
    return {"C17/MANIFEST.sha256": man, "C17/summary.json": dumps(summ), "C17/freeze_receipt.json": dumps(rec)}


def c18() -> dict:
    macros = {"PersFieldRate": {"value": 0.47, "display": "47\\,\\%", "file": "$BO_REPO/results/MATRIX/matrix.json",
                                "sha256": H("matrix"), "pointer": "/metrics/0/operational_coverage/est",
                                "category": "persistence"},
              "CovFieldN": {"value": 120, "display": "120", "file": "$BO_REPO/results/MATRIX/matrix.json",
                            "sha256": H("matrix"), "pointer": "/metrics/0/operational_coverage/n", "category": "coverage"}}
    doc = {**hdr("bo.numbers/1", "C18", "2.0.0", "STATS"), "macros": macros}
    tex = "% gerado de numbers.json (C18)\n" + "".join(f"\\newcommand{{\\{k}}}{{{v['display']}}}\n"
                                                       for k, v in macros.items())
    return {"C18/numbers.json": dumps(doc), "C18/numbers.tex": tex}


# ------------------------------------------------------------------------------------------------- C19–C23
def c19() -> dict:
    u1 = {"unit_id": "CU-aws-db-instance", "provider": "aws", "kind": "ENTITY",
          "layers": {"api_resource": {"service": "rds", "resource": "DBInstance"},
                     "terraform": {"resource_type": "aws_db_instance"}, "domain_unit": "instância de banco"},
          "identity": {"evidence": [EV_DOC], "key_fields": ["identifier"], "anonymous": False, "occurrence_key": []},
          "lifecycle_controller": {"kind": "self"}, "owner": {"kind": "self"}, "effective_scope": {"kind": "self"},
          "evidence": [EV_DOC], "rule_applied": "GRAIN-ENTITY-01", "missing_evidence": []}
    u2 = {"unit_id": "CU-aws-sg-rule-block", "provider": "aws", "kind": "COMPONENT",
          "layers": {"terraform": {"resource_type": "aws_security_group", "block_path": "ingress"},
                     "domain_unit": "regra de entrada"},
          "identity": {"evidence": [EV_REF], "key_fields": [], "anonymous": True,
                       "occurrence_key": ["protocol", "from_port", "to_port", "cidr_blocks"]},
          "lifecycle_controller": {"kind": "parent", "ref": "CU-aws-security-group"},
          "owner": {"kind": "parent", "ref": "CU-aws-security-group"}, "effective_scope": {"kind": "parent"},
          "evidence": [EV_REF], "rule_applied": "GRAIN-COMPONENT-01", "missing_evidence": []}
    u3 = {"unit_id": "CU-aws-db-option-x", "provider": "aws", "kind": "UNKNOWN",
          "layers": {"terraform": {"resource_type": "aws_db_option_group", "block_path": "option"},
                     "domain_unit": "opção de banco"},
          "identity": {"evidence": [], "key_fields": [], "anonymous": True, "occurrence_key": ["option_name"]},
          "lifecycle_controller": {"kind": "UNKNOWN"}, "owner": {"kind": "UNKNOWN"}, "effective_scope": {"kind": "UNKNOWN"},
          "evidence": [], "rule_applied": "GRAIN-UNKNOWN-01", "missing_evidence": ["lifecycle_controller", "owner"]}
    atoms = [{"atom_id": "aws:aws_db_instance:backup_retention_period", "unit_id": "CU-aws-db-instance",
              "path_in_unit": "backup_retention_period", "role": "CONFIG"},
             {"atom_id": "aws:aws_security_group:ingress.from_port", "unit_id": "CU-aws-sg-rule-block",
              "path_in_unit": "from_port"}]
    u4 = {"unit_id": "CU-aws-route-table-assoc", "provider": "aws", "kind": "BINDING",
          "layers": {"terraform": {"resource_type": "aws_route_table_association"}, "domain_unit": "associação de rota"},
          "identity": {"evidence": [EV_REF], "key_fields": ["subnet_id", "route_table_id"], "anonymous": False,
                       "occurrence_key": []},
          "endpoints": [{"role": "subnet", "unit_id": "CU-aws-subnet"}, {"role": "route_table", "unit_id": "CU-aws-route-table"}],
          "lifecycle_controller": {"kind": "self"}, "owner": {"kind": "self"}, "effective_scope": {"kind": "parent",
                                                                                                   "ref": "CU-aws-subnet"},
          "evidence": [EV_REF, {"level": "observed", "ref": "SE-azurerm-0011",
                                "note": "observado: run obs-az-01, 2 repetições, com controle"}],
          "rule_applied": "GRAIN-BINDING-01", "missing_evidence": []}
    u5 = {"unit_id": "CU-aws-peering-options", "provider": "aws", "kind": "FACET",
          "layers": {"terraform": {"resource_type": "aws_vpc_peering_connection_options"}, "domain_unit": "opções do peering"},
          "identity": {"evidence": [EV_REF], "key_fields": ["vpc_peering_connection_id"], "anonymous": False,
                       "occurrence_key": []},
          "lifecycle_controller": {"kind": "parent", "ref": "CU-aws-vpc-peering"},
          "owner": {"kind": "parent", "ref": "CU-aws-vpc-peering", "refs": ["CU-aws-vpc-peering", "CU-aws-vpc"]},
          "effective_scope": {"kind": "parent", "ref": "CU-aws-vpc-peering"}, "evidence": [EV_REF],
          "rule_applied": "GRAIN-G3-FACET", "missing_evidence": []}
    u6 = {"unit_id": "CU-aws-nic-sg-attach-sym", "provider": "aws", "kind": "BINDING",
          "layers": {"terraform": {"resource_type": "aws_network_interface_sg_attachment"},
                     "domain_unit": "anexação de grupo por referência simbólica"},
          "identity": {"evidence": [EV_REF], "key_fields": ["network_interface_id", "security_group_id"],
                       "anonymous": False, "occurrence_key": []},
          "endpoints": [{"role": "network_interface", "unit_id": "CU-aws-eni"},
                        {"role": "security_group", "kind": "EXTERNAL", "symbol": "var.sg_id",
                         "target_type": "aws_security_group"}],
          "lifecycle_controller": {"kind": "self"}, "owner": {"kind": "self"}, "effective_scope": {"kind": "self"},
          "evidence": [EV_REF], "rule_applied": "R-GRAIN-T51B", "missing_evidence": []}
    return {"C19/canonical_units.jsonl": jsonl([u1, u2, u3, u4, u5, u6]), "C19/canonical_atoms.jsonl": jsonl(atoms)}


def c20() -> dict:
    con = [{"concept_id": "concept:backup_retention", "label": "retenção de backup",
            "definition": "tempo durante o qual uma cópia de segurança automática é mantida", "domain": "DB",
            "quantity_kind": "quantitykind:Time", "unit": "unit:DAY", "status": "active",
            "evidence_state": "DOC_SUPPORTED"},
           {"concept_id": "concept:storage_tier", "label": "classe de armazenamento",
            "definition": "nível de custo e latência de acesso de um objeto armazenado", "domain": "STO",
            "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE", "status": "merged",
            "replaced_by": ["concept:storage_class"], "evidence_state": "STRUCTURALLY_VALID"},
           {"concept_id": "concept:backup_retention_automated", "label": "retenção de backup automático",
            "definition": "tempo de retenção só das cópias automáticas (não das manuais)", "domain": "DB",
            "quantity_kind": "quantitykind:Time", "unit": "unit:DAY", "status": "active",
            "evidence_state": "STRUCTURALLY_VALID"},
           {"concept_id": "concept:monitoring_interval", "label": "intervalo de monitoramento",
            "definition": "período entre duas coletas de métricas aprimoradas", "domain": "OPS",
            "quantity_kind": "UNKNOWN", "status": "active", "evidence_state": "UNRESOLVED"}]
    base = {"claim_id": "ANC-aws-0001", "concept_id": "concept:backup_retention",
            "atom_id": "aws:aws_db_instance:backup_retention_period",
            "sentence": "frase sintética: dias de retenção dos backups automáticos",
            "context": "seção de argumentos do recurso",
            "counterexample_search": {"query": "retention backups snapshot manual", "found": False,
                                      "result": "nenhum uso com outro significado"},
            "extraction_method": "parser", "evidence_level": "published", "source": EV_DOC["doc"]}
    v1 = {**base, "claim_version_id": "ANC-aws-0001@1", "event_id": "EV-GLOSS-0001", "evidence_state": "STRUCTURALLY_VALID",
          "recorded_at": TS, "evidence_ref": {"contract": "C03", "id": "DF-aws-0001"}}
    v2 = {**base, "claim_version_id": "ANC-aws-0001@2", "event_id": "EV-AUDIT-0007", "supersedes": "ANC-aws-0001@1",
          "evidence_state": "DOC_SUPPORTED", "recorded_at": TS2}
    blk = {**{k: v for k, v in base.items() if k != "atom_id"}, "claim_id": "ANC-google-fw-0001",
           "claim_version_id": "ANC-google-fw-0001@1", "event_id": "EV-GLOSS-0101", "concept_id": "concept:rule_effect",
           "anchor_kind": "block", "block_id": "google:google_compute_firewall:deny",
           "implication": {"realization": "block_choice", "value": "deny",
                           "rule": "o bloco deny{} usado na regra implica efeito = deny",
                           "alternatives": [{"ref": "google:google_compute_firewall:allow", "value": "allow"}]},
           "sentence": "frase sintética: o bloco deny especifica as regras de negação",
           "evidence_state": "DOC_SUPPORTED", "recorded_at": TS2}
    typ = {**{k: v for k, v in base.items() if k != "atom_id"}, "claim_id": "ANC-aws-sg-0001",
           "claim_version_id": "ANC-aws-sg-0001@1", "event_id": "EV-GLOSS-0102", "concept_id": "concept:rule_direction",
           "anchor_kind": "type", "type_id": "aws:aws_vpc_security_group_egress_rule",
           "implication": {"realization": "type_choice", "value": "egress",
                           "rule": "o tipo *_egress_rule implica sentido = egress",
                           "alternatives": [{"ref": "aws:aws_vpc_security_group_ingress_rule", "value": "ingress"}]},
           "sentence": "frase sintética: o recurso gerencia uma regra de saída", "evidence_state": "DOC_SUPPORTED",
           "recorded_at": TS2}
    aud = {"audit_id": "GA-0001", "claim_id": "ANC-aws-0001", "claim_version_id": "ANC-aws-0001@2",
           "event_id": "EV-AUDIT-0007", "check": "evidence_support", "result": "pass",
           "evidence_state_before": "STRUCTURALLY_VALID", "evidence_state_after": "DOC_SUPPORTED",
           "auditor": "GLOSSARY-AUDIT", "at": TS2}
    dh = {"schema": "bo.glossary_decision/1", "author": "GLOSSARY-DB", "recorded_at": TS2,
          "evidence": [{"source": "fixture:doc-sintetica", "sentence": "frase sintética", "date": DAY}]}
    decs = [{**dh, "decision_id": "GD-DB-0001", "kind": "broader", "concept_id": "concept:backup_retention_automated",
             "related_concept": "concept:backup_retention", "reason": "toda retenção automática é retenção de backup"},
            {**dh, "decision_id": "GD-DB-0002", "kind": "narrower", "concept_id": "concept:backup_retention",
             "related_concept": "concept:backup_retention_automated", "reason": "a mesma relação lida do lado amplo"},
            {**dh, "decision_id": "GD-DB-0003", "kind": "value_type", "concept_id": "concept:storage_tier",
             "value": {"datatype": "enum", "enum_semantics": "ordinal por custo de acesso"},
             "reason": "tipo de valor e semântica do enum"},
            {**dh, "decision_id": "GD-DB-0004", "kind": "same_kind_distinct", "concept_id": "concept:backup_retention",
             "related_concept": "concept:monitoring_interval", "evidence": [],
             "reason": "mesma grandeza (tempo), significados distintos"}]
    unr = {k: v for k, v in base.items() if k not in ("sentence", "source")}
    unr.update({"claim_id": "ANC-aws-0009", "claim_version_id": "ANC-aws-0009@1", "event_id": "EV-GLOSS-0109",
                "atom_id": "aws:aws_s3_bucket_acl:access_control_policy.grant.permission",
                "concept_id": "concept:storage_tier", "evidence_state": "UNRESOLVED", "recorded_at": TS2,
                "context": "a descrição publicada fala de outra coisa (parece cópia de outra página); sem sentença própria"})
    return {"C20/glossary.jsonl": jsonl(con), "C20/claims.jsonl": jsonl([v1, v2, blk, typ, unr]),
            "C20/glossary_audit.jsonl": jsonl([aud]), "C20/decisions.jsonl": jsonl(decs)}


def c21() -> dict:
    v = [{"claim_id": "CLM-EX-01", "claim_version_id": "CLM-EX-01@2", "event_id": "EV-ARB-0001", "verdict": "OK",
          "rules": [], "cycle": 1, "composition_used": None, "arbiter_sha256": H("arbiter"), "decided_at": TS},
         {"claim_id": "CLM-EX-01∘CLM-BR-01", "claim_version_id": "CLM-EX-01∘CLM-BR-01@1", "event_id": "EV-ARB-0002",
          "verdict": "UNPROVEN", "rules": ["COMP-DOMAIN"], "cycle": 1, "composition_used": ["CLM-EX-01", "CLM-BR-01"],
          "arbiter_sha256": H("arbiter"), "decided_at": TS}]
    return {"C21/verdicts.jsonl": jsonl(v)}


def c22() -> dict:
    pt = {**hdr("bo.probe_types/1", "C22", "3.0.0", "PROBEKIT"), "protocol_version": "1.0.0",
          "probe_types": [{"probe_type": "item_ttl", "preconditions": ["tabela com TTL habilitado no atributo declarado"],
                           "negative_control": {"description": "item sem atributo de TTL",
                                                "expected": "continua legível ao fim da janela"},
                           "repetitions": 3, "tolerance": {"kind": "exact", "value": 0},
                           "polling": {"interval": "PT15M", "max_wait": "PT48H"},
                           "window": {"duration": "PT72H", "margin_over_ttl": "PT24H"},
                           "cost_limit": {"amount": 1.0, "currency": "USD"},
                           "validated_support": [{"provider": "aws", "status": "validated", "evidence": [EV_DOC]},
                                                 {"provider": "oci", "status": "unknown", "evidence": []}]}]}
    obs = [{"observation_id": "OBS-A-0001", "pair_case_id": "PC-0001", "side": "A", "provider": "aws",
            "probe_type": "item_ttl", "timestamp": TS2, "protocol_version": "1.0.0",
            "counts": {"attempts": 3, "observed": 3, "not_observed": 0, "errors": 0}, "negative_control_ok": True},
           {"observation_id": "OBS-B-0001", "pair_case_id": "PC-0001", "side": "B", "provider": "google",
            "probe_type": "item_ttl", "timestamp": TS3, "protocol_version": "1.0.0",
            "counts": {"attempts": 3, "observed": 1, "observed_out_of_tolerance": 1, "not_observed": 0, "errors": 1},
            "negative_control_ok": True}]
    pj = {"judgement_id": "PJ-0001", "pair_case_id": "PC-0001", "case_id": "CASE-AWSGCP-DB-0001",
          "group_id": "G-AWSGCP-DB-0001", "observations": {"A": "OBS-A-0001", "B": "OBS-B-0001"},
          "outcome": {"axis": "behavior", "value": "OBSERVATIONS_MATCH_UNDER_PROTOCOL"}, "protocol_version": "1.0.0",
          "judged_by": "PROBE-JOIN", "judged_at": TS3}
    return {"C22/probe_types.yaml": yml(pt), "C22/observations.jsonl": jsonl(obs), "C22/pair_judgements.jsonl": jsonl([pj])}


def c23() -> dict:
    inp = {"atom_id": "aws:aws_db_instance:backup_retention_period",
           "term": {"kind": "literal", "datatype": "number", "value": 7}}
    t1 = {"trace_id": "TR-0001", "case_id": "CASE-AWSGCP-DB-0001", "claim_id": "CLM-EX-01", "input": inp,
          "individual": "x:db_a", "inferred_classes": ["x:DatabaseInstance"], "property": "x:backupRetention",
          "realization_id": "r_ret_google", "transform": {"name": "identity", "params": {}},
          "justifying_axioms": ["x:backupRetention rdfs:domain (StorageContainer ⊔ DatabaseInstance)"],
          "consulted_metadata": ["rdfs:label x:backupRetention"], "control": "c3",
          "output": {"atom_id": "google:google_sql_database_instance:settings.backup_configuration.retained_backups",
                     "term": {"kind": "literal", "datatype": "number", "value": 7}}, "result": "carried"}
    t2 = {"trace_id": "TR-0002", "claim_id": "CLM-ALT-VER-PREM", "input": inp, "control": "c3",
          "guard_evaluated": {"guard": {"all": EDITION_PREM}, "result": "FALSE"},
          "justifying_axioms": [], "consulted_metadata": [], "result": "blocked", "block_code": "CONDITION_FALSE",
          "rule": "T-GUARD"}
    t3 = {"trace_id": "TR-0003", "input": inp, "control": "c1", "justifying_axioms": [], "consulted_metadata": [],
          "result": "blocked", "block_code": "REFUTED_BY_RULE", "rule": "T-UNPROVEN"}
    t4 = {"trace_id": "TR-0004", "input": {"atom_id": "aws:aws_db_instance:monitoring_interval",
                                           "term": {"kind": "literal", "datatype": "null", "value": None}},
          "control": "c2", "justifying_axioms": [], "consulted_metadata": [], "result": "omitted"}
    return {"C23/translation_trace.jsonl": jsonl([t1, t2, t3, t4])}


# ------------------------------------------------------------------------------------------------- C24–C29
def c24() -> dict:
    d = adopted("C24_stub_records")
    seed = lambda cid, pair, dom: {  # noqa: E731
        "case_id": cid, "group_id": "G-PSTO-T1-AWSAZ", "comparator": {"name": "exact"}, "cost_class": "free",
        "side": "subject", "stratum_partial": {"cardinality": "1:1", "direction": "forward", "domain": dom, "pair": pair},
        "values": [{"var": "psto:versioning", "term": {"kind": "literal", "datatype": "string", "value": "ENABLED"}}],
        "pending": {"claim_id": "o oráculo não lê alegações", "claim_version_id": "idem",
                    "frame_ref": "piloto não sorteia", "lowering_plan": "plano C26 do E2E",
                    "stratum.relation": "sai da alegação", "weight": "idem", "origin": "pilot (C11 3.1.0)"}}
    sto = {"schema": "bo.pilot.sto.expected_answers/1", "contract": "C24", "contract_version": "1.1.0",
           "module": "PILOT-STO-ORACLE", "generated_at": TS, "note": "gabarito sintético mínimo do stub",
           "oracle_sha256": H("sto-oracle"), "oracle_version": "1.0.0",
           "providers": {"aws": "6.71.0", "azurerm": "5.12.0", "google": "8.9.0", "oci": "9.11.0"},
           "fixtures": {"FX-STO-AWS-VER-P01": {
               "case": "MC-VER", "file": "pilot/sto/fixtures_calib/aws/FX-STO-AWS-VER-P01.json", "invariant_group": None,
               "polarity": "positive", "provider": "aws", "summary": "versionamento ligado no recurso separado",
               "checks": [{"kind": "versioning", "container": "c1", "expect": "ENABLED"},
                          {"kind": "claim", "claim": {"about": "decomposition", "value": {"kind": "FACET"}},
                           "expect": {"verdict": "ACCEPT"}}]}},
           "directions": {"DX-AWS-AZ-T1-acceptable-01": {
               "c11_case_seed": seed("CASE-PSTO-DX-01", "AWSAZ", "STO"), "declared_losses": [],
               "direction": "aws->azurerm", "expect": {"verdict": "ACCEPT"}, "family": "T1-VERSIONED",
               "file": "pilot/sto/fixtures_calib/directions/aws-azurerm-T1.json", "note": "", "polarity": "positive",
               "variant": "acceptable"},
               "DX-AWS-AZ-T1-negative-01": {
               "c11_case_seed": seed("CASE-PSTO-DX-02", "AWSAZ", "STO"), "declared_losses": [],
               "direction": "aws->azurerm", "expect": {"verdict": "REJECT", "code": "EARLY_DELETION"},
               "family": "T1-VERSIONED", "file": "pilot/sto/fixtures_calib/directions/aws-azurerm-T1.json", "note": "",
               "polarity": "negative", "variant": "negative"}},
           "heldout": {"ciphertext_sha256": H("ct"), "plaintext_sha256": H("pt"), "recipient_fingerprint_sha256": H("rcpt"),
                       "sealed_at": TS, "sealed_file": "$BO_DATA/PILOT-STO-ORACLE/sealed/heldout.cms.pem",
                       "counts": {"fixtures": 1, "direction_entries": 2}}}
    return {"C24/requirements.jsonl": jsonl(d["requirements"]), "C24/commitments.jsonl": jsonl(d["commitments"]),
            "C24/cq_spec.jsonl": jsonl(d["cq_spec"]), "C24/expected_answers.json": dumps(sto)}


def c25() -> dict:
    cit = {"uri": "https://docs.example.org/provider-a/db/backups", "retrieved_at": TS,
           "sentence": "frase sintética: o backup automático pertence à instância e some com ela"}
    e1 = {"evidence_id": "SE-aws-0001", "provider": "aws", "pin": {"provider_version": "6.0.0", "api_version": "2014-10-31"},
          "api_resource": {"service": "rds", "resource": "DBInstance"}, "terraform_resource_type": "aws_db_instance",
          "fact_kind": "lifecycle_controller", "status": "stated", "value": "self", "level": "published",
          "citation": cit}
    e2 = {**copy.deepcopy(e1), "evidence_id": "SE-aws-0002", "fact_kind": "owner", "value": "self", "level": "derived",
          "derived_from": ["SE-aws-0001"]}
    e2.pop("citation")
    e3 = {"evidence_id": "SE-aws-0003", "provider": "aws", "pin": {"provider_version": "6.0.0"},
          "api_resource": {"service": "rds", "resource": "OptionGroupOption"}, "fact_kind": "ttl_support",
          "status": "unknown", "unknown_reason": "not_documented", "level": "interpreted", "model_id": "claude-opus-5-5",
          "consulted": {"uri": "https://docs.example.org/provider-a/db/option-groups", "retrieved_at": TS}}
    sch = {"provider_source": "registry.terraform.io/hashicorp/aws", "schema_sha256": H("aws-schema"), "op": "keys",
           "pointer": "/provider_schemas/registry.terraform.io~1hashicorp~1aws/resource_schemas/aws_db_instance/block",
           "sentence": '["attributes","block_types"]', "retrieved_at": TS}
    e4 = {"evidence_id": "SE-aws-0004", "provider": "aws", "pin": {"provider_version": "6.0.0"},
          "api_resource": {"service": "rds", "resource": "UNKNOWN"}, "terraform_resource_type": "aws_db_instance",
          "block_path": "blue_green_update", "fact_kind": "identity", "status": "stated",
          "value": {"aspect": "block_schema"}, "level": "published", "schema": {**sch, "op": "shape"},
          "rule_id": "R-BLOCK-SHAPE"}
    e5 = {"evidence_id": "SE-aws-0005", "provider": "aws", "pin": {"provider_version": "6.0.0"},
          "api_resource": {"service": "rds", "resource": "DBInstance"}, "terraform_resource_type": "aws_db_instance",
          "fact_kind": "api_bridge", "status": "stated", "value": {"api_resource": "DBInstance"}, "level": "published",
          "citation": cit}
    e6 = {"evidence_id": "SE-aws-0006", "provider": "aws", "pin": {"provider_version": "6.0.0"},
          "api_resource": {"service": "rds", "resource": "DBInstance"}, "terraform_resource_type": "aws_db_instance",
          "fact_kind": "default", "status": "stated", "value": {"attribute": "backup_retention_period", "default": 7},
          "as_of": DAY, "level": "derived", "derived_from": ["SE-aws-0001"]}
    e7 = {"evidence_id": "SE-aws-0007", "provider": "aws", "pin": {"provider_version": "6.0.0"},
          "api_resource": {"service": "rds", "resource": "UNKNOWN"}, "fact_kind": "tag_support", "status": "unknown",
          "unknown_reason": "not_documented", "consulted": sch}
    ps = [{"schema": "bo.protocol_support/1", "probe_type": "object_versioning", "provider": "aws",
           "pin": {"provider_version": "6.0.0"}, "terraform_resource_type": "aws_s3_bucket_versioning",
           "attributes": ["versioning_configuration.status"], "status": "documented_supported",
           "requirement": {"text": "atributo que liga o versionamento do contêiner", "max_seconds": None},
           "documented": {}, "validated": False,
           "evidence": [{"level": "published", "doc": EV_DOC["doc"]},
                        {"level": "interpreted", "model_id": "claude-opus-5-5",
                         "note": "escolha do tipo e dos atributos que realizam a sonda"}]},
          {"schema": "bo.protocol_support/1", "probe_type": "rate_limit", "provider": "oci",
           "pin": {"provider_version": "9.11.0"}, "terraform_resource_type": "oci_apigateway_deployment",
           "attributes": [], "status": "unknown", "reason": "a documentação fixada não diz a janela do limite",
           "requirement": {"text": "limite de taxa com janela declarada", "max_seconds": 60}, "documented": {},
           "validated": False, "evidence": [{"level": "derived", "note": "busca nas páginas do tipo sem frase"}]}]
    e8 = {"evidence_id": "SE-oci-0008", "provider": "oci", "pin": {"provider_version": "9.11.0"},
          "api_resource": {"service": "core", "resource": "SecurityList"}, "terraform_resource_type": "oci_core_security_list",
          "block_path": "ingress_security_rules", "fact_kind": "identity", "status": "stated",
          "value": {"aspect": "item_identity", "has_id": True, "requires_parent": False}, "level": "published",
          "citation": {"uri": "https://docs.example.org/provider-d/security-list", "retrieved_at": TS,
                       "sentence": "frase sintética: cada regra da lista é um item"}}
    e9 = {"evidence_id": "SE-oci-0009", "provider": "oci", "pin": {"provider_version": "9.11.0"},
          "api_resource": {"service": "core", "resource": "SecurityList"}, "terraform_resource_type": "oci_core_security_list",
          "block_path": "ingress_security_rules", "fact_kind": "identity", "status": "stated",
          "value": {"aspect": "item_identity", "has_id": False, "replaced_whole": True, "duplicates_accepted": True},
          "level": "observed", "observation_ref": {"path": "$BO_DATA/OBS-GAPS/observations.jsonl",
                                                   "record_id": "obs-gaps-20261104-1548/sl_rule_identity/2"},
          "run_id": "obs-gaps-20261104-1548", "repetitions": 2, "observed_at": TS2,
          "control": {"description": "lista sem regras lida antes e depois", "result": "sem itens, sem id"},
          "disputes": ["SE-oci-0008"]}
    e10 = {"evidence_id": "SE-oci-0010", "provider": "oci", "pin": {"provider_version": "9.11.0"},
           "api_resource": {"service": "core", "resource": "NetworkSecurityGroupSecurityRule"},
           "terraform_resource_type": "oci_core_network_security_group_security_rule", "fact_kind": "identity",
           "status": "stated", "value": {"aspect": "item_identity", "has_id": True, "requires_parent": True,
                                         "parent_attribute": "network_security_group_id",
                                         "parent_type": "oci_core_network_security_group"},
           "level": "derived", "derived_from": ["SE-oci-0008"], "rule_id": "R-OWN-SPEC"}
    e11 = {"evidence_id": "SE-azurerm-0011", "provider": "azurerm", "pin": {"provider_version": "5.12.0"},
           "api_resource": {"service": "network", "resource": "NetworkInterfaceSecurityGroupAssociation"},
           "terraform_resource_type": "azurerm_network_interface_security_group_association",
           "fact_kind": "lifecycle_controller", "status": "stated", "value": {"kind": "self"}, "level": "observed",
           "observation_ref": {"path": "$BO_DATA/OBS-GAPS-AZ/observations.jsonl", "record_id": "obs-az-01/assoc_life/2"},
           "run_id": "obs-az-01", "repetitions": 2, "observed_at": TS3,
           "control": {"description": "NIC sem associação lida antes e depois", "result": "sem associação"},
           "rule_id": "R-OBS-ASSOC-LIFE"}
    e12 = {"evidence_id": "SE-oci-0012", "provider": "oci", "pin": {"provider_version": "9.11.0"},
           "api_resource": {"service": "objectstorage", "resource": "Namespace"},
           "terraform_resource_type": "oci_objectstorage_bucket", "fact_kind": "lifecycle_controller",
           "status": "stated", "value": {"aspect": "namespace_cascade", "cascade": False}, "level": "published",
           "citation": {"uri": "https://docs.example.org/provider-d/object-storage", "retrieved_at": TS,
                        "sentence": "frase sintética: o contêiner precisa estar vazio para ser apagado"}}
    disp = {"schema": "bo.spec_disputes/1", "module": "SERVICE-EVIDENCE", "contract": "C25", "contract_version": "1.6.1",
            "generated_at": TS3, "note": "conflito spec x doc: os dois fatos ficam no C25",
            "disputes": [
                {"provider": "azurerm", "terraform_resource_type": "azurerm_network_interface_security_group_association",
                 "fact": "owner", "doc": {"kind": "self", "rule": "R-OWN-API"},
                 "spec": {"kind": "parent", "rule": "R-OWN-SPEC"}, "evidence": ["SE-aws-0001", "SE-aws-0002"]},
                {"provider": "oci", "terraform_resource_type": "oci_core_network_security_group_security_rule",
                 "fact": "lifecycle_controller", "doc": {"kind": "self", "rule": "R-LIFE-API"},
                 "spec": {"kind": "parent", "rule": "R-LIFE-SPEC-PARENT"}, "evidence": ["SE-oci-0008", "SE-oci-0010"],
                 "status": "resolvida-por-observação", "sides": ["SE-oci-0008", "SE-oci-0010"],
                 "resolved_to": "spec", "observation_id": "SE-oci-0009", "resolved_at": TS3},
                {"provider": "oci", "terraform_resource_type": "oci_core_network_security_group_security_rule",
                 "fact": "effective_scope", "kind": "doc_x_spec", "doc": {"kind": "self", "rule": "R-SCOPE-SELF"},
                 "spec": {"kind": "parent", "rule": "R-SCOPE-SPEC"}, "evidence": ["SE-oci-0013", "SE-oci-0014"],
                 "status": "resolvida-por-publicação", "sides": ["SE-oci-0013", "SE-oci-0014"],
                 "resolved_to": "spec", "publication_id": "SE-oci-0015", "resolved_at": TS3}]}
    nsg = {"provider": "oci", "pin": {"provider_version": "9.11.0"},
           "api_resource": {"service": "core", "resource": "NetworkSecurityGroupSecurityRule"},
           "terraform_resource_type": "oci_core_network_security_group_security_rule", "fact_kind": "effective_scope",
           "status": "stated"}
    e13 = {"evidence_id": "SE-oci-0013", **nsg, "value": {"kind": "self"}, "level": "derived",
           "derived_from": ["SE-oci-0008"], "rule_id": "R-SCOPE-SELF"}
    e14 = {"evidence_id": "SE-oci-0014", **nsg, "value": {"kind": "parent"}, "level": "derived",
           "derived_from": ["SE-oci-0008"], "rule_id": "R-SCOPE-SPEC"}
    e15 = {"evidence_id": "SE-oci-0015", **nsg, "value": {"kind": "parent"}, "level": "published",
           "citation": {"uri": "https://docs.example.org/provider-d/nsg", "retrieved_at": TS,
                        "sentence": "frase sintética: as regras do grupo valem para as interfaces do grupo"}}
    return {"C25/service_evidence.jsonl": jsonl([e1, e2, e3, e4, e5, e6, e7, e8, e9, e10, e11, e12, e13, e14, e15]),
            "C25/protocol_support.jsonl": jsonl(ps), "C25/spec_disputes.json": dumps(disp)}


def c26() -> dict:
    """Um plano mínimo por provedor (aws, google, azurerm, oci), cada um com o graph_ir irmão; copiados das fixtures
    dos HARNESS-* (adopted/C26_plans_stub.json): renderizam no pin do PINS, então o gate de render de cada
    HARNESS acha exatamente UM plano do seu provedor (emenda C26 1.1.0)."""
    d = adopted("C26_plans_stub")
    return {"C26/graph_ir.jsonl": jsonl(d["graph_irs"]), "C26/lowering_plan.jsonl": jsonl(d["lowering_plans"])}


def c27() -> dict:
    s = {**hdr("bo.split/1", "C27", "1.0.0", "SPLIT"), "seed": 20261103, "method": "split por família, estratificado por provedor",
         "dedup": {"method": "near_dup_minhash", "threshold": 0.9},
         "partitions": {"train": {"n_families": 1, "ids_sha256": H("train-ids")},
                        "dev": {"n_families": 1, "ids_sha256": H("dev-ids")},
                        "test": {"n_families": 1, "encrypted": {"path": "$BO_DATA/SPLIT/sealed/test_families.jsonl.age",
                                                                "sha256": H("test-sealed"), "cipher": "age",
                                                                "recipient_fingerprint": "age1" + "q" * 58}}},
         "role_projections": {"mapper": {"partitions": ["train"]}, "glossarist": {"partitions": ["train", "dev"]}},
         "opening_receipt": None}
    fams = [{"family_id": FAM1, "members": [REPO1, REPO2], "dedup_method": "near_dup_minhash",
             "signature_sha256": H("fam1"), "partition": "train"},
            {"family_id": FAM2, "members": [REPO3], "dedup_method": "exact_hash", "signature_sha256": H("fam2"),
             "partition": "dev"}]
    return {"C27/split.json": dumps(s), "C27/families.jsonl": jsonl(fams)}


def c28() -> dict:
    comps = {**hdr("bo.comparators/1", "C28", "1.0.0", "BENCH-CONTRACT"), "comparators": [
        {"comparator_id": "kalinin", "version": "artigo publicado", "source": {"uri": "https://example.org/fixture/kalinin-paper",
                                                                               "kind": "paper"},
         "native_scope": "ontologia OWL DL de recursos de nuvem com ABox e checagem de conformidade",
         "artifact": "no", "native_task": "verificação de conformidade (CSPM)", "decision": "adapt",
         "decision_reason": "sem artefato público: reconstrução da família sob o mesmo orçamento",
         "axes": ["native", "representation"], "adaptation_budget": {"hours": 6, "unit": "agent_hours"},
         "kalinin_family": True,
         "metrics": [{"axis": "representation", "name": "cobertura de CQs", "value": 0.31},
                     {"axis": "translation", "name": "cobertura operacional", "value": "NOT_APPLICABLE",
                      "reason": "sem tradutor nem artefato"},
                     {"axis": "native", "name": "acurácia CSPM", "value": "UNKNOWN"}]},
        {"comparator_id": "cartography", "version": "fixture", "source": {"uri": "https://example.org/fixture/cartography-repo",
                                                                          "kind": "repo"},
         "native_scope": "grafo de inventário multi-nuvem", "artifact": "yes", "native_task": "inventário e consulta",
         "decision": "include", "decision_reason": "artefato executável no mesmo universo",
         "axes": ["native", "representation", "translation"], "adaptation_budget": {"hours": 6, "unit": "agent_hours"},
         "kalinin_family": False, "metrics": []}]}
    fair = {**hdr("bo.h2h_fairness/1", "C28", "1.0.0", "BENCH-CONTRACT"),
            "universe_ref": {"path": "$BO_DATA/UNIVERSE/universe.json", "sha256": H("universe")},
            "cq_ref": {"path": "$BO_REPO/cq/CQ_INDEX.json", "sha256": H("cq")},
            "budget": {"unit": "agent_hours", "per_comparator": 6},
            "comparators": [{"comparator_id": "kalinin", "budget_hours": 6, "same_universe": True, "same_cqs": True},
                            {"comparator_id": "cartography", "budget_hours": 6, "same_universe": True,
                             "same_cqs": True}],
            "rules": ["mesmo orçamento de adaptação para todos os comparadores", "NOT_APPLICABLE nunca vira zero"]}
    return {"C28/comparators.yaml": yml(comps), "C28/h2h_fairness.yaml": yml(fair)}


def c29() -> dict:
    dim = lambda s, note="": {"status": s, **({"note": note} if note else {})}  # noqa: E731
    dc = {**hdr("bo.domain_contracts/1", "C29", "1.0.0", "DOMAIN-CONTRACTS"), "domains": [
        {"domain": "NET", "identity": {"key_fields": ["provider", "location", "type", "local_key"], "composite": True},
         "owner": {"rule": "dono = controlador de ciclo de vida da rede"},
         "scope": {"rule": "alcance efetivo = rede ou sub-rede citada"},
         "authorization": {"principal": dim("SUPPORTED"), "permission": dim("SUPPORTED"), "effect": dim("SUPPORTED"),
                           "binding": dim("UNRESOLVED", "binding por tag sem evidência"),
                           "scope": dim("SUPPORTED"), "inheritance": dim("UNSUPPORTED_BY_TRANSLATOR"),
                           "context": dim("OUT_OF_PIN"),
                           "combination": {"status": "ABSENCE_DEMONSTRATED", "evidence": [EV_DOC]}},
         "network_fragment": "FRG-NET-01",
         "decision_units": [{"name": "ingress_allowed", "decision": "tráfego de entrada permitido no destino",
                             "units": ["CU-aws-sg-rule-block"]}],
         "observability": {"signals": ["flow_logs"], "status": "UNRESOLVED"},
         "out_of_support": [{"item": "regras de prefix list gerenciada", "status": "OUT_OF_PIN"}]}]}
    frag = {"fragment_id": "FRG-NET-01", "domain": "NET", "kind": "network",
            "nodes": [{"node_id": "n0", "kind": "virtual_network"},
                      {"node_id": "n1", "kind": "subnet"},
                      {"node_id": "n2", "kind": "filter_rule", "unit_id": "CU-aws-sg-rule-block"}],
            "edges": [{"from": "n1", "to": "n0", "kind": "contained_in"}, {"from": "n2", "to": "n1", "kind": "applies_to"}],
            "status": "SUPPORTED"}
    return {"C29/domain_contracts.yaml": yml(dc), "C29/fragments/FRG-NET-01.json": dumps(frag)}


BUILDERS = [c00, c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, c20,
            c21, c22, c23, c24, c25, c26, c27, c28, c29]


def all_stubs() -> dict:
    out = {}
    for b in BUILDERS:
        out.update(b())
    return out


KIND_OF = {  # caminho do stub -> "Cnn:tipo"
    "C00/module.json": "C00:module", "C00/modulos.json": "C00:module_catalog",
    "C01/atoms.jsonl": "C01:atoms", "C02/types.jsonl": "C02:types", "C03/docs_facts.jsonl": "C03:docs_facts",
    "C03/type_subcategory.jsonl": "C03:type_subcategory",
    "C04/roles.jsonl": "C04:roles", "C05/value_space.jsonl": "C05:value_space",
    "C06/symbolic_config.jsonl": "C06:symbolic_config", "C06/resources.parquet": "C06:resources",
    "C06/usage.jsonl": "C06:usage", "C07/universe.json": "C07:universe", "C08/candidates.jsonl": "C08:candidates",
    "C09/correspondences.sssom.tsv": "C09:correspondences", "C09/correspondences.jsonl": "C09:correspondences_jsonl",
    "C09/correspondences.edoal.ttl": "C09:edoal", "complex.sssom.tsv": "C09:correspondences",
    "C10/transforms.yaml": "C10:transforms", "C10/conditions.grammar.json": "C10:conditions_grammar",
    "C10/composition_table.json": "C10:composition_table", "C10/guard.json": "C10:guard",
    "C11/cases.jsonl": "C11:cases", "C12/readback.jsonl": "C12:readback", "C12/outcomes.jsonl": "C12:outcomes",
    "C13/pins.json": "C13:pins", "C13/versions.json": "C13:versions", "C13/events.jsonl": "C13:events",
    "C13/history_versions.json": "C13:history_versions", "C13/atom_history.jsonl": "C13:atom_history",
    "C14/classes.jsonl": "C14:classes", "C14/properties.jsonl": "C14:properties",
    "C14/realizations.jsonl": "C14:realizations", "C14/ontology.ttl": "C14:ttl",
    "C15/metrics_spec.yaml": "C15:metrics_spec", "C15/result.json": "C15:result",
    "C15/summary.json": "C15:summary_results", "C16/intent_manifest.jsonl": "C16:intent_manifest",
    "C16/run_manifest.jsonl": "C16:run_manifest", "C17/MANIFEST.sha256": "C17:manifest",
    "C17/summary.json": "C17:summary", "C17/freeze_receipt.json": "C17:freeze_receipt",
    "C18/numbers.json": "C18:numbers", "C18/numbers.tex": "C18:numbers_tex",
    "C19/canonical_units.jsonl": "C19:canonical_units", "C19/canonical_atoms.jsonl": "C19:canonical_atoms",
    "C20/glossary.jsonl": "C20:glossary", "C20/claims.jsonl": "C20:claims", "C20/glossary_audit.jsonl": "C20:glossary_audit",
    "C20/decisions.jsonl": "C20:decisions",
    "C21/verdicts.jsonl": "C21:verdicts", "C22/probe_types.yaml": "C22:probe_types",
    "C22/observations.jsonl": "C22:observations", "C22/pair_judgements.jsonl": "C22:pair_judgements",
    "C23/translation_trace.jsonl": "C23:translation_trace", "C24/requirements.jsonl": "C24:requirements",
    "C24/commitments.jsonl": "C24:commitments", "C24/cq_spec.jsonl": "C24:cq_spec",
    "C24/expected_answers.json": "C24:pilot_expected_answers",
    "C25/service_evidence.jsonl": "C25:service_evidence",
    "C25/protocol_support.jsonl": "C25:protocol_support",
    "C25/spec_disputes.json": "C25:spec_disputes", "C26/graph_ir.jsonl": "C26:graph_ir",
    "C26/lowering_plan.jsonl": "C26:lowering_plan", "C27/split.json": "C27:split", "C27/families.jsonl": "C27:families",
    "C28/comparators.yaml": "C28:comparators", "C28/h2h_fairness.yaml": "C28:h2h_fairness",
    "C29/domain_contracts.yaml": "C29:domain_contracts", "C29/fragments/FRG-NET-01.json": "C29:fragment",
}
