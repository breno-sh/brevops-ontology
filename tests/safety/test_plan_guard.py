"""plan_guard: SKU caro, TTL ausente, tag/nome faltando, Classe C, custo (com armazenamento, tráfego e
requisições), credencial no provider, backend e provisioner: todos recusados; plano barato e marcado passa."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta

import pytest

from bo.safety import plan_check as G
from bo.safety import skus
from bo.safety.common import bo_repo, iso, now_dt
from safety_helpers import ctx, plan, rc

TAGS = {"bo-run": "b-aws-01"}


def codes(rep):
    return sorted({f["code"] for f in rep["findings"]})


def good_db(**over):
    a = {"instance_class": "db.t4g.micro", "allocated_storage": 20, "storage_type": "gp3", "multi_az": False,
         "skip_final_snapshot": True, "deletion_protection": False, "backup_retention_period": 1,
         "tags": TAGS, "tags_all": TAGS}
    a.update(over)
    return rc("aws_db_instance.caso", "aws_db_instance", a)


def good_bucket(**over):
    a = {"bucket": "bo-caso", "force_destroy": True, "tags_all": TAGS}
    a.update(over)
    return rc("aws_s3_bucket.caso", "aws_s3_bucket", a)


def test_cheap_tagged_plan_passes():
    rep = G.check_plan(plan(good_db(), good_bucket()), ctx())
    assert rep["ok"], rep["findings"]
    assert rep["cost"]["total"] > 0 and set(rep["cost"]["includes"]) >= {"storage", "traffic", "requests"}


@pytest.mark.parametrize("over,code", [
    ({"instance_class": "db.r6g.16xlarge"}, "PG-SKU"),        # SKU caro
    ({"allocated_storage": 2000}, "PG-SKU"),
    ({"multi_az": True}, "PG-SKU"),
    ({"skip_final_snapshot": False}, "PG-RULE"),              # snapshot final = resíduo cobrando
    ({"deletion_protection": True}, "PG-RULE"),
])
def test_expensive_sku_and_residue_rules_refused(over, code):
    rep = G.check_plan(plan(good_db(**over)), ctx())
    assert not rep["ok"] and code in codes(rep)


def test_unknown_sku_in_plan_refused():
    r = good_db()
    r["change"]["after"].pop("instance_class")
    r["change"]["after_unknown"] = {"instance_class": True}
    rep = G.check_plan(plan(r), ctx())
    assert "PG-SKU" in codes(rep)


def test_ttl_absent_refused():
    rep = G.check_plan(plan(good_bucket()), ctx(ttl_hours=None))
    assert "PG-TTL" in codes(rep)
    assert any("ausente" in f["detail"] for f in rep["findings"])


def test_ttl_above_type_window_refused():
    z = rc("aws_route53_zone.z", "aws_route53_zone", {"name": "bo.example", "force_destroy": True, "tags_all": TAGS})
    assert G.check_plan(plan(z), ctx(ttl_hours=2))["ok"]
    rep = G.check_plan(plan(z), ctx(ttl_hours=24, window_hours=24,
                                     supervisor={"last_ack_at": iso(now_dt()), "run_tag": "b-aws-01"}))
    assert "PG-TTL" in codes(rep) and any("janela do tipo" in f["detail"] for f in rep["findings"])


def test_long_window_requires_live_supervisor():
    p = plan(good_bucket())
    rep = G.check_plan(p, ctx(ttl_hours=24, window_hours=24))
    assert "PG-TTL" in codes(rep) and any("supervisor" in f["detail"] for f in rep["findings"])
    stale = {"last_ack_at": iso(now_dt() - timedelta(hours=1)), "run_tag": "b-aws-01"}
    assert "PG-TTL" in codes(G.check_plan(p, ctx(ttl_hours=24, window_hours=24, supervisor=stale)))
    other = {"last_ack_at": iso(now_dt()), "run_tag": "b-outra"}
    assert "PG-TTL" in codes(G.check_plan(p, ctx(ttl_hours=24, window_hours=24, supervisor=other)))
    live = {"last_ack_at": iso(now_dt()), "run_tag": "b-aws-01"}
    assert G.check_plan(p, ctx(ttl_hours=24, window_hours=24, supervisor=live))["ok"]


def test_ttl_above_global_max_refused():
    live = {"last_ack_at": iso(now_dt()), "run_tag": "b-aws-01"}
    assert "PG-TTL" in codes(G.check_plan(plan(good_bucket()), ctx(ttl_hours=100, supervisor=live)))


def test_missing_or_wrong_run_tag_refused():
    assert "PG-TAG" in codes(G.check_plan(plan(good_bucket(tags_all={})), ctx()))
    assert "PG-TAG" in codes(G.check_plan(plan(good_bucket(tags_all={"bo-run": "b-outra"})), ctx()))


def test_untaggable_type_requires_synthetic_name():
    ok = rc("aws_kms_alias.a", "aws_kms_alias", {"name": "alias/bo-aws-01-0003", "target_key_id": "k"})
    assert G.check_plan(plan(ok), ctx())["ok"]
    bad = rc("aws_kms_alias.a", "aws_kms_alias", {"name": "alias/minha-chave", "target_key_id": "k"})
    assert "PG-NAME" in codes(G.check_plan(plan(bad), ctx()))
    other_batch = rc("aws_kms_alias.a", "aws_kms_alias", {"name": "alias/bo-aws-02-0003"})
    assert "PG-NAME" in codes(G.check_plan(plan(other_batch), ctx()))


def test_type_outside_allowlist_and_class_c_refused():
    assert "PG-TYPE" in codes(G.check_plan(plan(rc("aws_instance.x", "aws_instance", {"tags_all": TAGS})), ctx()))
    r = rc("aws_redshift_cluster.x", "aws_redshift_cluster", {"tags_all": TAGS})
    assert "PG-CLASSC" in codes(G.check_plan(plan(r), ctx()))
    # OK do Breno para a Classe C não basta: o tipo ainda tem de estar na allowlist com SKU e custo
    assert "PG-TYPE" in codes(G.check_plan(plan(r), ctx(approved_class_c=["aws_redshift_cluster"])))


def test_delete_or_replace_in_apply_refused():
    r = good_bucket()
    r["change"]["actions"] = ["delete", "create"]
    assert "PG-DELETE" in codes(G.check_plan(plan(r), ctx()))


@pytest.mark.parametrize("expr,detail", [
    ({"access_key": {"constant_value": "x"}, "allowed_account_ids": {"references": ["var.a"]}}, "access_key"),
    ({"profile": {"constant_value": "pessoal"}, "allowed_account_ids": {"references": ["var.a"]}}, "profile"),
    ({"assume_role": [{"role_arn": {"constant_value": "x"}}], "allowed_account_ids": {"references": ["var.a"]}},
     "assume_role"),
    ({"region": {"references": ["var.bo_region"]}}, "allowed_account_ids"),
    ({"region": {"constant_value": "ap-south-1"}, "allowed_account_ids": {"references": ["var.a"]}}, "região"),
])
def test_provider_block_credentials_and_region(expr, detail):
    rep = G.check_plan(plan(good_bucket(), provider_expr=expr), ctx())
    assert not rep["ok"] and any(detail in f["detail"] for f in rep["findings"])


def test_azure_key_vault_requires_purge_on_destroy():
    kv = rc("azurerm_key_vault.k", "azurerm_key_vault",
            {"sku_name": "standard", "purge_protection_enabled": False, "soft_delete_retention_days": 7,
             "tags": {"bo-run": "b-aws-01"}}, provider="azurerm")
    assert G.check_plan(plan(kv, provider="azurerm"), ctx("azurerm"))["ok"]
    rep = G.check_plan(plan(kv, provider="azurerm", provider_expr={"features": [{}]}), ctx("azurerm"))
    assert "PG-PROVIDER" in codes(rep)


def test_cost_cap_counts_storage_traffic_and_requests():
    """Bucket não tem custo por hora: só armazenamento, tráfego e requisições o fazem estourar."""
    p = plan(good_bucket())
    big = {"aws_s3_bucket.caso": {"storage_gb": 0, "egress_gb": 400, "requests_millions": 0}}
    rep = G.check_plan(p, ctx(usage=big))
    assert "PG-COST" in codes(rep) and rep["cost"]["items"][0]["traffic"] > 30
    reqs = {"aws_s3_bucket.caso": {"storage_gb": 0, "egress_gb": 0, "requests_millions": 10}}
    assert "PG-COST" in codes(G.check_plan(p, ctx(usage=reqs)))
    storage = {"aws_s3_bucket.caso": {"storage_gb": 1_000_000, "egress_gb": 0, "requests_millions": 0}}
    assert "PG-COST" in codes(G.check_plan(p, ctx(usage=storage)))
    small = {"aws_s3_bucket.caso": {"storage_gb": 1, "egress_gb": 1, "requests_millions": 0.01}}
    assert G.check_plan(p, ctx(usage=small))["ok"]


def test_cost_cap_counts_prior_spend_and_batch_cap():
    p = plan(good_db())
    assert "PG-COST" in codes(G.check_plan(p, ctx(spent_usd={"aws": 29.99, "total": 29.99})))
    assert "PG-COST" in codes(G.check_plan(p, ctx(spent_usd={"aws": 0, "total": 99.99})))
    assert "PG-COST" in codes(G.check_plan(p, ctx(batch_cap_usd=0.001)))


def test_residual_cost_enters_estimate():
    key = rc("aws_kms_key.k", "aws_kms_key", {"deletion_window_in_days": 7,
                                              "customer_master_key_spec": "SYMMETRIC_DEFAULT", "tags_all": TAGS})
    rep = G.check_plan(plan(key), ctx())
    assert rep["ok"] and rep["cost"]["items"][0]["residual"] == 1.0
    long = rc("aws_kms_key.k", "aws_kms_key", {"deletion_window_in_days": 30,
                                               "customer_master_key_spec": "SYMMETRIC_DEFAULT", "tags_all": TAGS})
    assert "PG-RULE" in codes(G.check_plan(plan(long), ctx()))


def test_live_price_above_table_refused():
    lp = {"aws": {"aws_db_instance": {"hourly": 0.5}}}
    assert "PG-PRICE" in codes(G.check_plan(plan(good_db()), ctx(), live_prices=lp))


def test_backend_and_provisioner_in_config_refused(work):
    (work / "main.tf").write_text('terraform {\n  backend "s3" {}\n}\nresource "null_resource" "x" {\n'
                                  '  provisioner "local-exec" { command = "true" }\n}\n')
    rep = G.check_plan(plan(good_bucket()), ctx(), tf_dir=work)
    assert {"PG-BACKEND", "PG-PROVISIONER"} <= set(codes(rep))
    (work / "main.tf").write_text('# backend "s3" comentado\nresource "aws_s3_bucket" "caso" {}\n')
    assert G.check_plan(plan(good_bucket()), ctx(), tf_dir=work)["ok"]


def test_intent_not_recorded_refused():
    p = plan(good_bucket())
    rep = G.check_plan(p, ctx(), intents=[])
    assert "PG-INTENT" in codes(rep)
    binding = [{"address": "aws_s3_bucket.caso", "intent_id": "INT-B-AWS-01-0001", "resource_type": "aws_s3_bucket"}]
    assert G.check_plan(p, ctx(), intents=binding)["ok"]
    wrong_type = [dict(binding[0], resource_type="aws_sqs_queue")]
    assert "PG-INTENT" in codes(G.check_plan(p, ctx(), intents=wrong_type))


def test_resource_of_other_provider_refused():
    g = rc("google_storage_bucket.b", "google_storage_bucket", {"labels": {"bo-run": "b-aws-01"}}, provider="google")
    assert "PG-TYPE" in codes(G.check_plan(plan(good_bucket(), g), ctx()))


def test_enforce_raises_with_findings():
    with pytest.raises(G.PlanRefused) as e:
        G.enforce(plan(good_db(instance_class="db.m5.24xlarge")), ctx())
    assert e.value.findings and e.value.code == "PLAN"


@pytest.mark.parametrize("provider,rtype,after", [
    ("google", "google_sql_database_instance", {"name": "bo-aws-01-0001", "deletion_protection": False,
                                                 "settings": [{"tier": "db-custom-8-32768", "disk_size": 10}]}),
    ("azurerm", "azurerm_postgresql_flexible_server", {"sku_name": "GP_Standard_D16s_v3", "storage_mb": 32768,
                                                       "tags": {"bo-run": "b-aws-01"}}),
    ("oci", "oci_kms_vault", {"vault_type": "VIRTUAL_PRIVATE", "freeform_tags": {"bo-run": "b-aws-01"}}),
    ("azurerm", "azurerm_cdn_frontdoor_profile", {"sku_name": "Premium_AzureFrontDoor", "tags": {"bo-run": "b-aws-01"}}),
])
def test_expensive_sku_other_providers(provider, rtype, after):
    rep = G.check_plan(plan(rc(f"{rtype}.x", rtype, after, provider=provider), provider=provider), ctx(provider))
    assert "PG-SKU" in codes(rep)


def test_every_allowlisted_type_has_cost_removal_and_trace():
    t = skus.load_table()
    for p, pv in t["providers"].items():
        for rtype, e in pv["types"].items():
            assert set(e["cost"]) == set(skus.COST_KEYS), rtype
            assert e["removal"]["mode"] in skus.REMOVAL_MODES
            assert e["trace"] in ("tag", "name", "ref")
            assert e["ttl"]["native_resource_destruction"] is False  # TTL do tipo nunca é destruição


def test_cli_reads_plan_from_stdin(work):
    c = work / "ctx.json"
    c.write_text(json.dumps(ctx()))
    cli = bo_repo() / "deploy" / "safety" / "plan_guard.py"
    ok = subprocess.run([sys.executable, "-I", str(cli), "--context", str(c)], input=json.dumps(plan(good_bucket())),
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "APROVADO" in ok.stdout
    bad = subprocess.run([sys.executable, "-I", str(cli), "--context", str(c)],
                         input=json.dumps(plan(good_db(instance_class="db.x2g.16xlarge"))), capture_output=True,
                         text=True)
    assert bad.returncode == 1 and "PG-SKU" in bad.stdout


def test_resource_level_region_or_location_outside_allowed_refused():
    assert "PG-REGION" in codes(G.check_plan(plan(good_bucket(region="eu-west-1")), ctx()))
    sa = rc("azurerm_storage_account.s", "azurerm_storage_account",
            {"account_tier": "Standard", "account_replication_type": "LRS", "account_kind": "StorageV2",
             "location": "West Europe", "tags": {"bo-run": "b-aws-01"}}, provider="azurerm")
    assert "PG-REGION" in codes(G.check_plan(plan(sa, provider="azurerm"), ctx("azurerm")))
    sa["change"]["after"]["location"] = "East US"
    assert G.check_plan(plan(sa, provider="azurerm"), ctx("azurerm"))["ok"]
