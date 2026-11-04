"""Comandos de nuvem por provedor: regiões lidas da conta, varredura de TODOS os tipos e remoção por tipo.

Lição do prejuízo anterior (~90 dólares, 55 h de duas VMs esquecidas): "zero instâncias rodando" olhou um provedor,
duas regiões fixas e um tipo. Aqui:
  - as regiões são sempre LIDAS DA CONTA (nunca lista fixa): describe-regions, compute regions list,
    account list-locations, region-subscription list;
  - cada provedor tem uma fonte que lista todo tipo de recurso (Tagging API + Resource Explorer na AWS,
    Cloud Asset Inventory no Google, az resource list na Azure, Search na OCI) MAIS as listas por natureza que
    costumam escapar (instâncias, discos, snapshots, imagens, IPs reservados, NAT, ENIs, bancos, LBs, logs,
    funções, chaves em exclusão, cofres em soft delete);
  - cobertura conferida: todo tipo da allowlist tem pelo menos uma fonte de varredura que o enxerga
    (coverage()); a varredura falha se um provedor não respondeu (nunca "zero" por silêncio).
Nada aqui roda sem quem chama passar um executor; nesta fase só o dry-run e os executores gravados (fixture).
Os comandos de remoção são o caminho de reserva (supervisor e órfão de runner morto); o caminho normal é o
terraform destroy no canal efêmero. Primeira execução real deles: SMOKE-<provedor>, com o GO do Breno (D9).
"""

from __future__ import annotations

import json
import re
import subprocess

from .common import PROVIDERS, SafetyError

# ------------------------------------------------------------------------------------------------ regiões
REGION_CMD = {
    "aws": ["aws", "ec2", "describe-regions", "--all-regions", "--output", "json",
            "--filters", "Name=opt-in-status,Values=opt-in-not-required,opted-in"],
    "google": ["gcloud", "compute", "regions", "list", "--project", "{project}", "--format=json"],
    "azurerm": ["az", "account", "list-locations", "-o", "json"],
    "oci": ["oci", "iam", "region-subscription", "list", "--all", "--output", "json"],
}


def parse_regions(provider: str, out: str) -> list[str]:
    d = json.loads(out)
    if provider == "aws":
        regs = [r["RegionName"] for r in d.get("Regions", [])]
    elif provider == "google":
        regs = [r["name"] for r in d]
    elif provider == "azurerm":
        regs = [r["name"] for r in d if (r.get("metadata") or {}).get("regionType", "Physical") != "Logical"]
    else:
        regs = [r["region-name"] for r in d.get("data", []) if r.get("status", "READY") == "READY"]
    if not regs:
        raise SafetyError(f"{provider}: a conta não devolveu nenhuma região (sem varredura, sem 'zero')", "SWEEP")
    return sorted(set(regs))


# ------------------------------------------------------------------------------------------------ fontes
# Fonte: (nome, escopo 'region'|'global', argv, parser). "all_types" marca a fonte que vê qualquer tipo.
def _tags_list(lst, k="Key", v="Value"):
    return {t.get(k): t.get(v) for t in (lst or []) if isinstance(t, dict)}


def _arn_type(arn: str) -> str:
    parts = arn.split(":", 5)
    return f"{parts[2]}:{parts[5].split('/')[0].split(':')[0]}" if len(parts) > 5 else "desconhecido"


def p_aws_tagging(d, region):
    return [{"ref": r["ResourceARN"], "type": _arn_type(r["ResourceARN"]), "region": region,
             "name": r["ResourceARN"].rsplit("/", 1)[-1].rsplit(":", 1)[-1], "tags": _tags_list(r.get("Tags")),
             "state": "active"} for r in d.get("ResourceTagMappingList", [])]


def p_aws_explorer(d, region):
    return [{"ref": r.get("Arn"), "type": r.get("ResourceType", "desconhecido"), "region": r.get("Region", region),
             "name": (r.get("Arn") or "").rsplit("/", 1)[-1],
             "tags": {}, "state": "active"} for r in d.get("Resources", [])]


def _ec2(key, idk, typ, state_k=None, default_k=None):
    def p(d, region):
        rows = []
        src = d.get(key, [])
        if key == "Reservations":
            src = [i for r in src for i in r.get("Instances", [])]
        for x in src:
            st = x.get(state_k) if state_k else "available"
            if isinstance(st, dict):
                st = st.get("Name")
            rows.append({"ref": x.get(idk), "type": typ, "region": region, "name": _tags_list(x.get("Tags")).get("Name"),
                         "tags": _tags_list(x.get("Tags")), "is_default": bool(x.get(default_k)) if default_k else False,
                         "state": {"terminated": "gone", "deleted": "gone", "deleting": "deleting",
                                   "shutting-down": "deleting"}.get(str(st), "active")})
        return [r for r in rows if r["state"] != "gone"]
    return p


def _simple(key, name_k, typ, ref_k=None, tags_k=None, state_fn=None):
    def p(d, region):
        out = []
        for x in d.get(key, []) if isinstance(d, dict) else d:
            if isinstance(x, str):
                x = {name_k: x}
            st = state_fn(x) if state_fn else "active"
            out.append({"ref": x.get(ref_k or name_k), "type": typ, "region": region, "name": x.get(name_k),
                        "tags": _tags_list(x.get(tags_k)) if tags_k else {}, "state": st})
        return out
    return p


def _kms_state(x):
    return {"PendingDeletion": "pending_deletion", "PendingReplicaDeletion": "pending_deletion"}.get(
        x.get("KeyState"), "active")


AWS_REGION_SOURCES = [
    ("tagging", ["aws", "resourcegroupstaggingapi", "get-resources", "--region", "{region}", "--output", "json"],
     p_aws_tagging, True),
    ("ec2_instances", ["aws", "ec2", "describe-instances", "--region", "{region}", "--output", "json"],
     _ec2("Reservations", "InstanceId", "aws_instance", "State"), False),
    ("ec2_volumes", ["aws", "ec2", "describe-volumes", "--region", "{region}", "--output", "json"],
     _ec2("Volumes", "VolumeId", "aws_ebs_volume", "State"), False),
    ("ec2_snapshots", ["aws", "ec2", "describe-snapshots", "--owner-ids", "self", "--region", "{region}",
                       "--output", "json"], _ec2("Snapshots", "SnapshotId", "aws_ebs_snapshot", "State"), False),
    ("ec2_images", ["aws", "ec2", "describe-images", "--owners", "self", "--region", "{region}", "--output", "json"],
     _ec2("Images", "ImageId", "aws_ami", "State"), False),
    ("ec2_eips", ["aws", "ec2", "describe-addresses", "--region", "{region}", "--output", "json"],
     _ec2("Addresses", "AllocationId", "aws_eip"), False),
    ("ec2_nat", ["aws", "ec2", "describe-nat-gateways", "--region", "{region}", "--output", "json"],
     _ec2("NatGateways", "NatGatewayId", "aws_nat_gateway", "State"), False),
    ("ec2_enis", ["aws", "ec2", "describe-network-interfaces", "--region", "{region}", "--output", "json"],
     _ec2("NetworkInterfaces", "NetworkInterfaceId", "aws_network_interface"), False),
    ("ec2_vpcs", ["aws", "ec2", "describe-vpcs", "--region", "{region}", "--output", "json"],
     _ec2("Vpcs", "VpcId", "aws_vpc", "State", "IsDefault"), False),
    ("rds_instances", ["aws", "rds", "describe-db-instances", "--region", "{region}", "--output", "json"],
     _simple("DBInstances", "DBInstanceIdentifier", "aws_db_instance", "DBInstanceArn", "TagList",
             lambda x: "deleting" if x.get("DBInstanceStatus") == "deleting" else "active"), False),
    ("rds_snapshots", ["aws", "rds", "describe-db-snapshots", "--snapshot-type", "manual", "--region", "{region}",
                       "--output", "json"],
     _simple("DBSnapshots", "DBSnapshotIdentifier", "aws_db_snapshot", "DBSnapshotArn", "TagList"), False),
    ("elbv2", ["aws", "elbv2", "describe-load-balancers", "--region", "{region}", "--output", "json"],
     _simple("LoadBalancers", "LoadBalancerName", "aws_lb", "LoadBalancerArn"), False),
    ("logs", ["aws", "logs", "describe-log-groups", "--region", "{region}", "--output", "json"],
     _simple("logGroups", "logGroupName", "aws_cloudwatch_log_group", "arn"), False),
    ("lambda", ["aws", "lambda", "list-functions", "--region", "{region}", "--output", "json"],
     _simple("Functions", "FunctionName", "aws_lambda_function", "FunctionArn"), False),
    ("dynamodb", ["aws", "dynamodb", "list-tables", "--region", "{region}", "--output", "json"],
     _simple("TableNames", "name", "aws_dynamodb_table"), False),
    ("sqs", ["aws", "sqs", "list-queues", "--region", "{region}", "--output", "json"],
     _simple("QueueUrls", "url", "aws_sqs_queue"), False),
    ("sns", ["aws", "sns", "list-topics", "--region", "{region}", "--output", "json"],
     _simple("Topics", "TopicArn", "aws_sns_topic"), False),
    ("kms", ["aws", "kms", "list-keys", "--region", "{region}", "--output", "json"],
     _simple("Keys", "KeyId", "aws_kms_key", "KeyArn"), False),
    ("kms_aliases", ["aws", "kms", "list-aliases", "--region", "{region}", "--output", "json"],
     _simple("Aliases", "AliasName", "aws_kms_alias", "AliasArn"), False),
    ("elasticache", ["aws", "elasticache", "describe-cache-clusters", "--region", "{region}", "--output", "json"],
     _simple("CacheClusters", "CacheClusterId", "aws_elasticache_cluster", "ARN", None,
             lambda x: "deleting" if x.get("CacheClusterStatus") == "deleting" else "active"), False),
    ("efs", ["aws", "efs", "describe-file-systems", "--region", "{region}", "--output", "json"],
     _simple("FileSystems", "FileSystemId", "aws_efs_file_system", "FileSystemArn", "Tags"), False),
    ("apigw", ["aws", "apigateway", "get-rest-apis", "--region", "{region}", "--output", "json"],
     _simple("items", "name", "aws_api_gateway_rest_api", "id"), False),
    ("apigwv2", ["aws", "apigatewayv2", "get-apis", "--region", "{region}", "--output", "json"],
     _simple("Items", "Name", "aws_apigatewayv2_api", "ApiId"), False),
    ("secrets", ["aws", "secretsmanager", "list-secrets", "--include-planned-deletion", "--region", "{region}",
                 "--output", "json"],
     _simple("SecretList", "Name", "aws_secretsmanager_secret", "ARN", "Tags",
             lambda x: "pending_deletion" if x.get("DeletedDate") else "active"), False),
    ("cloudformation", ["aws", "cloudformation", "list-stacks", "--region", "{region}", "--output", "json",
                        "--stack-status-filter", "CREATE_COMPLETE", "UPDATE_COMPLETE", "ROLLBACK_COMPLETE",
                        "DELETE_FAILED"],
     _simple("StackSummaries", "StackName", "aws_cloudformation_stack", "StackId"), False),
]
AWS_REGION_BEST_EFFORT = [
    ("resource_explorer", ["aws", "resource-explorer-2", "search", "--query-string", "*", "--region", "{region}",
                           "--output", "json"], p_aws_explorer, True),
]
AWS_GLOBAL_SOURCES = [
    ("s3", ["aws", "s3api", "list-buckets", "--output", "json"],
     _simple("Buckets", "Name", "aws_s3_bucket"), False),
    ("iam_roles", ["aws", "iam", "list-roles", "--output", "json"], _simple("Roles", "RoleName", "aws_iam_role", "Arn"), False),
    ("iam_policies", ["aws", "iam", "list-policies", "--scope", "Local", "--output", "json"],
     _simple("Policies", "PolicyName", "aws_iam_policy", "Arn"), False),
    ("iam_users", ["aws", "iam", "list-users", "--output", "json"], _simple("Users", "UserName", "aws_iam_user", "Arn"), False),
    ("route53", ["aws", "route53", "list-hosted-zones", "--output", "json"],
     _simple("HostedZones", "Name", "aws_route53_zone", "Id"), False),
    ("cloudfront", ["aws", "cloudfront", "list-distributions", "--output", "json"],
     lambda d, r: _simple("Items", "DomainName", "aws_cloudfront_distribution", "Id")(
         (d.get("DistributionList") or {}), r), False),
]

GCP_ASSET_TYPE = re.compile(r"^(?P<svc>[a-z]+)\.googleapis\.com/(?P<kind>.+)$")


# Tipo nativo da fonte "todos os tipos" -> tipo Terraform, para o filtro de posse por nome sintético (tipos sem
# rótulo/tag). Tipo fora do mapa fica com o nome nativo: só casa por tag ou referência, nunca por nome.
NATIVE_TO_TF = {
    "google": {"compute.googleapis.com/Network": "google_compute_network",
               "compute.googleapis.com/Subnetwork": "google_compute_subnetwork",
               "compute.googleapis.com/Firewall": "google_compute_firewall",
               "compute.googleapis.com/Router": "google_compute_router",
               "compute.googleapis.com/Address": "google_compute_address",
               "compute.googleapis.com/GlobalAddress": "google_compute_global_address",
               "compute.googleapis.com/ForwardingRule": "google_compute_forwarding_rule",
               "compute.googleapis.com/Instance": "google_compute_instance",
               "compute.googleapis.com/Disk": "google_compute_disk",
               "storage.googleapis.com/Bucket": "google_storage_bucket",
               "pubsub.googleapis.com/Topic": "google_pubsub_topic",
               "pubsub.googleapis.com/Subscription": "google_pubsub_subscription",
               "run.googleapis.com/Service": "google_cloud_run_v2_service",
               "cloudfunctions.googleapis.com/Function": "google_cloudfunctions2_function",
               "logging.googleapis.com/LogMetric": "google_logging_metric",
               "iam.googleapis.com/ServiceAccount": "google_service_account",
               "cloudkms.googleapis.com/KeyRing": "google_kms_key_ring",
               "cloudkms.googleapis.com/CryptoKey": "google_kms_crypto_key",
               "sqladmin.googleapis.com/Instance": "google_sql_database_instance",
               "redis.googleapis.com/Instance": "google_redis_instance",
               "firestore.googleapis.com/Database": "google_firestore_database"},
    "azurerm": {"microsoft.resources/resourcegroups": "azurerm_resource_group",
                "microsoft.network/virtualnetworks": "azurerm_virtual_network",
                "microsoft.network/networksecuritygroups": "azurerm_network_security_group",
                "microsoft.storage/storageaccounts": "azurerm_storage_account",
                "microsoft.servicebus/namespaces": "azurerm_servicebus_namespace",
                "microsoft.keyvault/vaults": "azurerm_key_vault",
                "microsoft.web/serverfarms": "azurerm_service_plan",
                "microsoft.web/sites": "azurerm_linux_function_app",
                "microsoft.operationalinsights/workspaces": "azurerm_log_analytics_workspace",
                "microsoft.dbforpostgresql/flexibleservers": "azurerm_postgresql_flexible_server",
                "microsoft.sql/servers": "azurerm_mssql_server",
                "microsoft.sql/servers/databases": "azurerm_mssql_database",
                "microsoft.network/publicipaddresses": "azurerm_public_ip",
                "microsoft.network/loadbalancers": "azurerm_lb",
                "microsoft.network/natgateways": "azurerm_nat_gateway",
                "microsoft.cdn/profiles": "azurerm_cdn_frontdoor_profile",
                "microsoft.documentdb/databaseaccounts": "azurerm_cosmosdb_account",
                "microsoft.apimanagement/service": "azurerm_api_management"},
    "oci": {"Compartment": "oci_identity_compartment", "Vcn": "oci_core_vcn", "Subnet": "oci_core_subnet",
            "InternetGateway": "oci_core_internet_gateway", "RouteTable": "oci_core_route_table",
            "SecurityList": "oci_core_security_list", "NetworkSecurityGroup": "oci_core_network_security_group",
            "Bucket": "oci_objectstorage_bucket", "Vault": "oci_kms_vault", "Key": "oci_kms_key",
            "FunctionsApplication": "oci_functions_application", "FunctionsFunction": "oci_functions_function",
            "LogGroup": "oci_logging_log_group", "Log": "oci_logging_log", "OnsTopic": "oci_ons_notification_topic",
            "OnsSubscription": "oci_ons_subscription", "NoSqlTable": "oci_nosql_table", "Queue": "oci_queue_queue"},
}


def tf_type(provider: str, native: str | None) -> str | None:
    m = NATIVE_TO_TF.get(provider, {})
    if native is None:
        return None
    return m.get(native) or m.get(native.lower()) or native


def p_gcp_asset(d, region):
    out = []
    for r in d:
        loc = r.get("location", "global")
        st = str(r.get("state", "ACTIVE")).upper()
        out.append({"ref": r.get("name"), "type": tf_type("google", r.get("assetType", "desconhecido")), "region": loc,
                    "name": (r.get("displayName") or r.get("name", "")).rsplit("/", 1)[-1],
                    "tags": dict(r.get("labels") or {}),
                    "state": {"DELETING": "deleting", "DESTROY_SCHEDULED": "pending_deletion",
                              "DELETE_REQUESTED": "deleting"}.get(st, "active")})
    return out


def _gcp(typ):
    def p(d, region):
        return [{"ref": x.get("selfLink") or x.get("name"), "type": typ, "region": (x.get("region") or x.get("zone")
                 or "global").rsplit("/", 1)[-1], "name": x.get("name"), "tags": dict(x.get("labels") or {}),
                 "state": "active"} for x in d]
    return p


GOOGLE_GLOBAL_SOURCES = [
    ("asset_inventory", ["gcloud", "asset", "search-all-resources", "--scope=projects/{project}", "--format=json"],
     p_gcp_asset, True),
    ("compute_instances", ["gcloud", "compute", "instances", "list", "--project", "{project}", "--format=json"],
     _gcp("google_compute_instance"), False),
    ("compute_addresses", ["gcloud", "compute", "addresses", "list", "--project", "{project}", "--format=json"],
     _gcp("google_compute_address"), False),
    ("compute_disks", ["gcloud", "compute", "disks", "list", "--project", "{project}", "--format=json"],
     _gcp("google_compute_disk"), False),
    ("compute_snapshots", ["gcloud", "compute", "snapshots", "list", "--project", "{project}", "--format=json"],
     _gcp("google_compute_snapshot"), False),
    ("compute_images", ["gcloud", "compute", "images", "list", "--no-standard-images", "--project", "{project}",
                        "--format=json"], _gcp("google_compute_image"), False),
    ("sql_instances", ["gcloud", "sql", "instances", "list", "--project", "{project}", "--format=json"],
     _gcp("google_sql_database_instance"), False),
]
GOOGLE_REGION_SOURCES = [
    ("kms_keyrings", ["gcloud", "kms", "keyrings", "list", "--location", "{region}", "--project", "{project}",
                      "--format=json"], _gcp("google_kms_key_ring"), False),
]


def p_az_resource(d, region):
    return [{"ref": r.get("id"), "type": tf_type("azurerm", r.get("type", "desconhecido")),
             "region": r.get("location", "global"),
             "name": r.get("name"), "tags": dict(r.get("tags") or {}), "state": "active",
             "resource_group": r.get("resourceGroup")} for r in d]


def p_az_group(d, region):
    return [{"ref": g.get("id"), "type": "azurerm_resource_group", "region": g.get("location"), "name": g.get("name"),
             "tags": dict(g.get("tags") or {}),
             "state": "deleting" if (g.get("properties") or {}).get("provisioningState") == "Deleting" else "active"}
            for g in d]


def p_az_deleted_kv(d, region):
    return [{"ref": v.get("id"), "type": "azurerm_key_vault", "region": (v.get("properties") or {}).get("location"),
             "name": v.get("name"), "tags": dict((v.get("properties") or {}).get("tags") or {}),
             "state": "soft_deleted"} for v in d]


def p_az_deleted_apim(d, region):
    return [{"ref": v.get("id"), "type": "azurerm_api_management", "region": v.get("location"), "name": v.get("name"),
             "tags": {}, "state": "soft_deleted"} for v in d]


AZURE_GLOBAL_SOURCES = [
    ("resources", ["az", "resource", "list", "-o", "json"], p_az_resource, True),
    ("groups", ["az", "group", "list", "-o", "json"], p_az_group, False),
    ("keyvault_deleted", ["az", "keyvault", "list-deleted", "--resource-type", "vault", "-o", "json"],
     p_az_deleted_kv, False),
    ("apim_deleted", ["az", "apim", "deletedservice", "list", "-o", "json"], p_az_deleted_apim, False),
]


def p_oci_search(d, region):
    out = []
    for r in d.get("data", {}).get("items", []):
        st = str(r.get("lifecycle-state", "ACTIVE")).upper()
        out.append({"ref": r.get("identifier"), "type": tf_type("oci", r.get("resource-type", "desconhecido")),
                    "region": region,
                    "name": r.get("display-name"), "tags": dict(r.get("freeform-tags") or {}),
                    "state": {"DELETED": "gone", "TERMINATED": "gone", "DELETING": "deleting",
                              "TERMINATING": "deleting", "PENDING_DELETION": "pending_deletion",
                              "SCHEDULING_DELETION": "pending_deletion"}.get(st, "active"),
                    "lifecycle": st})
    return [x for x in out if x["state"] != "gone" or x["type"] == "oci_identity_compartment"]


OCI_REGION_SOURCES = [
    ("search", ["oci", "search", "resource", "structured-search", "--query-text", "query all resources",
                "--region", "{region}", "--limit", "1000", "--output", "json"], p_oci_search, True),
]
OCI_GLOBAL_SOURCES = [
    ("compartments", ["oci", "iam", "compartment", "list", "--compartment-id-in-subtree", "true", "--all",
                      "--include-root", "--compartment-id", "{tenancy}", "--output", "json"],
     lambda d, r: [{"ref": c.get("id"), "type": "oci_identity_compartment", "region": "global",
                    "name": c.get("name"), "tags": dict(c.get("freeform-tags") or {}),
                    "state": "deleting" if c.get("lifecycle-state") == "DELETING" else
                    ("gone" if c.get("lifecycle-state") == "DELETED" else "active")}
                   for c in d.get("data", [])], False),
]

SOURCES = {
    "aws": {"region": AWS_REGION_SOURCES, "region_best_effort": AWS_REGION_BEST_EFFORT, "global": AWS_GLOBAL_SOURCES},
    "google": {"region": GOOGLE_REGION_SOURCES, "region_best_effort": [], "global": GOOGLE_GLOBAL_SOURCES},
    "azurerm": {"region": [], "region_best_effort": [], "global": AZURE_GLOBAL_SOURCES},
    "oci": {"region": OCI_REGION_SOURCES, "region_best_effort": [], "global": OCI_GLOBAL_SOURCES},
}


def coverage(table: dict) -> dict:
    """{provedor: {tipo: [fontes]}}: quem enxerga cada tipo da allowlist na varredura."""
    out = {}
    for p in PROVIDERS:
        srcs = SOURCES[p]["region"] + SOURCES[p]["global"]
        all_types = [s[0] for s in srcs if s[3]]
        out[p] = {}
        for t, e in table["providers"][p]["types"].items():
            named = [s[0] for s in srcs if not s[3] and _source_type(s) == t]
            via = list(named)
            if all_types and (p != "aws" or e["tag"]["supported"]):
                via += all_types  # Tagging API só lista o que tem tag; as outras três veem qualquer tipo
            if e["trace"] == "ref":
                via.append("cascata:pai")  # vínculo sem nome some com o pai (custo zero, conferido na política)
            out[p][t] = sorted(set(via))
    return out


def _source_type(src) -> str | None:
    try:
        rows = src[2]({"Reservations": [{"Instances": [{"x": 1}]}]} if src[0] == "ec2_instances" else
                      _probe_doc(src[0]), "r")
        return rows[0]["type"] if rows else None
    except Exception:
        return None


def _probe_doc(name: str):
    keys = {"ec2_volumes": "Volumes", "ec2_snapshots": "Snapshots", "ec2_images": "Images", "ec2_eips": "Addresses",
            "ec2_nat": "NatGateways", "ec2_enis": "NetworkInterfaces", "ec2_vpcs": "Vpcs",
            "rds_instances": "DBInstances", "rds_snapshots": "DBSnapshots", "elbv2": "LoadBalancers",
            "logs": "logGroups", "lambda": "Functions", "dynamodb": "TableNames", "sqs": "QueueUrls",
            "sns": "Topics", "kms": "Keys", "kms_aliases": "Aliases", "elasticache": "CacheClusters",
            "efs": "FileSystems", "apigw": "items", "apigwv2": "Items", "secrets": "SecretList",
            "cloudformation": "StackSummaries", "s3": "Buckets", "iam_roles": "Roles", "iam_policies": "Policies",
            "iam_users": "Users", "route53": "HostedZones"}
    if name == "cloudfront":
        return {"DistributionList": {"Items": [{"Id": "x"}]}}
    if name in keys:
        return {keys[name]: [{"x": 1}]}
    if name in ("groups",):
        return [{"name": "x"}]
    if name in ("keyvault_deleted", "apim_deleted"):
        return [{"name": "x"}]
    if name == "compartments":
        return {"data": [{"id": "x"}]}
    return [{"name": "x"}]


# ------------------------------------------------------------------------------------------------ remoção
# Passos por tipo: argv com {id}, {name}, {region}, {project}, {rg}. "cascade" = some com o pai (vínculo sem
# custo). Tipos com remoção agendada levam o prazo mínimo (KMS: 7 dias; GCP: versão destruída em 1 dia).
DELETE = {
    "aws": {
        "aws_vpc": [["aws", "ec2", "delete-vpc", "--vpc-id", "{id}", "--region", "{region}"]],
        "aws_subnet": [["aws", "ec2", "delete-subnet", "--subnet-id", "{id}", "--region", "{region}"]],
        "aws_internet_gateway": [["aws", "ec2", "detach-internet-gateway", "--internet-gateway-id", "{id}",
                                  "--vpc-id", "{vpc_id}", "--region", "{region}", "?"],
                                 ["aws", "ec2", "delete-internet-gateway", "--internet-gateway-id", "{id}",
                                  "--region", "{region}"]],
        "aws_route_table": [["aws", "ec2", "delete-route-table", "--route-table-id", "{id}", "--region", "{region}"]],
        "aws_route_table_association": "cascade",
        "aws_security_group": [["aws", "ec2", "delete-security-group", "--group-id", "{id}", "--region", "{region}"]],
        "aws_vpc_security_group_ingress_rule": [["aws", "ec2", "revoke-security-group-ingress", "--group-id",
                                                 "{parent_id}", "--security-group-rule-ids", "{id}", "--region",
                                                 "{region}"]],
        "aws_vpc_security_group_egress_rule": [["aws", "ec2", "revoke-security-group-egress", "--group-id",
                                                "{parent_id}", "--security-group-rule-ids", "{id}", "--region",
                                                "{region}"]],
        "aws_iam_role": [["aws", "iam", "delete-role", "--role-name", "{name}"]],
        "aws_iam_policy": [["aws", "iam", "delete-policy", "--policy-arn", "{id}"]],
        "aws_iam_role_policy_attachment": [["aws", "iam", "detach-role-policy", "--role-name", "{parent_name}",
                                            "--policy-arn", "{id}"]],
        "aws_s3_bucket": [["aws", "s3", "rb", "s3://{name}", "--force"]],
        "aws_s3_bucket_versioning": "cascade",
        "aws_s3_bucket_lifecycle_configuration": "cascade",
        "aws_s3_bucket_public_access_block": "cascade",
        "aws_s3_bucket_server_side_encryption_configuration": "cascade",
        "aws_sqs_queue": [["aws", "sqs", "delete-queue", "--queue-url", "{id}", "--region", "{region}"]],
        "aws_sns_topic": [["aws", "sns", "delete-topic", "--topic-arn", "{id}", "--region", "{region}"]],
        "aws_cloudwatch_log_group": [["aws", "logs", "delete-log-group", "--log-group-name", "{name}", "--region",
                                      "{region}"]],
        "aws_cloudwatch_metric_alarm": [["aws", "cloudwatch", "delete-alarms", "--alarm-names", "{name}",
                                         "--region", "{region}"]],
        "aws_lambda_function": [["aws", "lambda", "delete-function", "--function-name", "{name}", "--region",
                                 "{region}"]],
        "aws_dynamodb_table": [["aws", "dynamodb", "delete-table", "--table-name", "{name}", "--region", "{region}"]],
        "aws_kms_key": [["aws", "kms", "schedule-key-deletion", "--key-id", "{id}", "--pending-window-in-days", "7",
                         "--region", "{region}"]],
        "aws_kms_alias": [["aws", "kms", "delete-alias", "--alias-name", "{name}", "--region", "{region}"]],
        "aws_route53_zone": [["aws", "route53", "delete-hosted-zone", "--id", "{id}"]],
        "aws_db_subnet_group": [["aws", "rds", "delete-db-subnet-group", "--db-subnet-group-name", "{name}",
                                 "--region", "{region}"]],
        "aws_db_instance": [["aws", "rds", "delete-db-instance", "--db-instance-identifier", "{name}",
                             "--skip-final-snapshot", "--delete-automated-backups", "--region", "{region}"]],
        "aws_lb": [["aws", "elbv2", "delete-load-balancer", "--load-balancer-arn", "{id}", "--region", "{region}"]],
        "aws_lb_target_group": [["aws", "elbv2", "delete-target-group", "--target-group-arn", "{id}", "--region",
                                 "{region}"]],
        "aws_lb_listener": [["aws", "elbv2", "delete-listener", "--listener-arn", "{id}", "--region", "{region}"]],
        "aws_eip": [["aws", "ec2", "release-address", "--allocation-id", "{id}", "--region", "{region}"]],
        "aws_nat_gateway": [["aws", "ec2", "delete-nat-gateway", "--nat-gateway-id", "{id}", "--region", "{region}"]],
        "aws_elasticache_subnet_group": [["aws", "elasticache", "delete-cache-subnet-group",
                                          "--cache-subnet-group-name", "{name}", "--region", "{region}"]],
        "aws_elasticache_cluster": [["aws", "elasticache", "delete-cache-cluster", "--cache-cluster-id", "{name}",
                                     "--region", "{region}"]],
        "aws_efs_file_system": [["aws", "efs", "delete-file-system", "--file-system-id", "{id}", "--region",
                                 "{region}"]],
        "aws_efs_mount_target": [["aws", "efs", "delete-mount-target", "--mount-target-id", "{id}", "--region",
                                  "{region}"]],
        "aws_api_gateway_rest_api": [["aws", "apigateway", "delete-rest-api", "--rest-api-id", "{id}", "--region",
                                      "{region}"]],
        "aws_apigatewayv2_api": [["aws", "apigatewayv2", "delete-api", "--api-id", "{id}", "--region", "{region}"]],
    },
    "google": {
        "google_compute_network": [["gcloud", "compute", "networks", "delete", "{name}", "--project", "{project}",
                                    "--quiet"]],
        "google_compute_subnetwork": [["gcloud", "compute", "networks", "subnets", "delete", "{name}", "--region",
                                       "{region}", "--project", "{project}", "--quiet"]],
        "google_compute_firewall": [["gcloud", "compute", "firewall-rules", "delete", "{name}", "--project",
                                     "{project}", "--quiet"]],
        "google_compute_router": [["gcloud", "compute", "routers", "delete", "{name}", "--region", "{region}",
                                   "--project", "{project}", "--quiet"]],
        "google_compute_router_nat": [["gcloud", "compute", "routers", "nats", "delete", "{name}", "--router",
                                       "{parent_name}", "--region", "{region}", "--project", "{project}", "--quiet"]],
        "google_compute_address": [["gcloud", "compute", "addresses", "delete", "{name}", "--region", "{region}",
                                    "--project", "{project}", "--quiet"]],
        "google_compute_global_address": [["gcloud", "compute", "addresses", "delete", "{name}", "--global",
                                           "--project", "{project}", "--quiet"]],
        "google_compute_forwarding_rule": [["gcloud", "compute", "forwarding-rules", "delete", "{name}", "--region",
                                            "{region}", "--project", "{project}", "--quiet"]],
        "google_storage_bucket": [["gcloud", "storage", "rm", "--recursive", "gs://{name}", "--project",
                                   "{project}", "--quiet"]],
        "google_pubsub_topic": [["gcloud", "pubsub", "topics", "delete", "{name}", "--project", "{project}",
                                 "--quiet"]],
        "google_pubsub_subscription": [["gcloud", "pubsub", "subscriptions", "delete", "{name}", "--project",
                                        "{project}", "--quiet"]],
        "google_cloud_run_v2_service": [["gcloud", "run", "services", "delete", "{name}", "--region", "{region}",
                                         "--project", "{project}", "--quiet"]],
        "google_cloudfunctions2_function": [["gcloud", "functions", "delete", "{name}", "--gen2", "--region",
                                             "{region}", "--project", "{project}", "--quiet"]],
        "google_logging_metric": [["gcloud", "logging", "metrics", "delete", "{name}", "--project", "{project}",
                                   "--quiet"]],
        "google_service_account": [["gcloud", "iam", "service-accounts", "delete", "{id}", "--project", "{project}",
                                    "--quiet"]],
        "google_project_iam_member": "cascade",
        "google_kms_key_ring": "retained",
        "google_kms_crypto_key": [["gcloud", "kms", "keys", "versions", "destroy", "1", "--key", "{name}",
                                   "--keyring", "{parent_name}", "--location", "{region}", "--project", "{project}",
                                   "--quiet"]],
        "google_sql_database_instance": [["gcloud", "sql", "instances", "delete", "{name}", "--project", "{project}",
                                          "--quiet"]],
        "google_redis_instance": [["gcloud", "redis", "instances", "delete", "{name}", "--region", "{region}",
                                   "--project", "{project}", "--quiet"]],
        "google_firestore_database": [["gcloud", "firestore", "databases", "delete", "--database", "{name}",
                                       "--project", "{project}", "--quiet"]],
        "google_firestore_field": "cascade",
    },
    "azurerm": {
        # tudo da execução vive no resource group da execução: apagar o grupo leva o resto; cofre e APIM depois
        # passam por purge (soft delete) e a varredura confere list-deleted vazio.
        "azurerm_resource_group": [["az", "group", "delete", "--name", "{name}", "--yes", "--no-wait"]],
        "azurerm_key_vault": [["az", "keyvault", "delete", "--name", "{name}"],
                              ["az", "keyvault", "purge", "--name", "{name}", "--no-wait"]],
        "azurerm_api_management": [["az", "apim", "delete", "--name", "{name}", "--resource-group", "{rg}", "--yes"],
                                   ["az", "apim", "deletedservice", "purge", "--service-name", "{name}",
                                    "--location", "{region}"]],
        "*": [["az", "resource", "delete", "--ids", "{id}"]],
    },
    "oci": {
        "oci_identity_compartment": [["oci", "iam", "compartment", "delete", "--compartment-id", "{id}", "--force"]],
        "oci_core_vcn": [["oci", "network", "vcn", "delete", "--vcn-id", "{id}", "--force", "--region", "{region}"]],
        "oci_core_subnet": [["oci", "network", "subnet", "delete", "--subnet-id", "{id}", "--force", "--region",
                             "{region}"]],
        "oci_core_internet_gateway": [["oci", "network", "internet-gateway", "delete", "--ig-id", "{id}", "--force",
                                       "--region", "{region}"]],
        "oci_core_route_table": [["oci", "network", "route-table", "delete", "--rt-id", "{id}", "--force",
                                  "--region", "{region}"]],
        "oci_core_security_list": [["oci", "network", "security-list", "delete", "--security-list-id", "{id}",
                                    "--force", "--region", "{region}"]],
        "oci_core_network_security_group": [["oci", "network", "nsg", "delete", "--nsg-id", "{id}", "--force",
                                             "--region", "{region}"]],
        "oci_core_network_security_group_security_rule": "cascade",
        "oci_objectstorage_bucket": [["oci", "os", "object", "bulk-delete", "--bucket-name", "{name}", "--force",
                                      "--region", "{region}"],
                                     ["oci", "os", "bucket", "delete", "--bucket-name", "{name}", "--force",
                                      "--region", "{region}"]],
        "oci_kms_vault": [["oci", "kms", "management", "vault", "schedule-deletion", "--vault-id", "{id}",
                           "--time-of-deletion", "{in7days}", "--region", "{region}"]],
        "oci_kms_key": [["oci", "kms", "management", "key", "schedule-deletion", "--key-id", "{id}",
                         "--endpoint", "{endpoint}", "--time-of-deletion", "{in7days}"]],
        "oci_functions_application": [["oci", "fn", "application", "delete", "--application-id", "{id}", "--force",
                                       "--region", "{region}"]],
        "oci_functions_function": [["oci", "fn", "function", "delete", "--function-id", "{id}", "--force",
                                    "--region", "{region}"]],
        "oci_logging_log_group": [["oci", "logging", "log-group", "delete", "--log-group-id", "{id}", "--force",
                                   "--region", "{region}"]],
        "oci_logging_log": [["oci", "logging", "log", "delete", "--log-group-id", "{parent_id}", "--log-id", "{id}",
                             "--force", "--region", "{region}"]],
        "oci_ons_notification_topic": [["oci", "ons", "topic", "delete", "--topic-id", "{id}", "--force",
                                        "--region", "{region}"]],
        "oci_ons_subscription": [["oci", "ons", "subscription", "delete", "--subscription-id", "{id}", "--force",
                                  "--region", "{region}"]],
        "oci_nosql_table": [["oci", "nosql", "table", "delete", "--table-name-or-id", "{id}", "--force", "--region",
                             "{region}"]],
        "oci_queue_queue": [["oci", "queue", "queue-admin", "queue", "delete", "--queue-id", "{id}", "--force",
                             "--region", "{region}"]],
    },
}
PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")


def delete_steps(provider: str, rtype: str):
    d = DELETE[provider]
    return d.get(rtype, d.get("*"))


def render(step: list[str], fields: dict) -> list[str] | None:
    """argv com os campos do item; None se um campo opcional ('?' no fim) falta; erro se um obrigatório falta."""
    optional = step and step[-1] == "?"
    argv = step[:-1] if optional else list(step)
    out = []
    for a in argv:
        miss = [k for k in PLACEHOLDER.findall(a) if fields.get(k) in (None, "")]
        if miss:
            if optional:
                return None
            raise SafetyError(f"remoção sem o campo {miss[0]}", "TEARDOWN")
        out.append(PLACEHOLDER.sub(lambda m: str(fields[m.group(1)]), a))
    return out


# ------------------------------------------------------------------------------------------------ executor
def subprocess_runner(argv, env=None):  # pragma: no cover - só com nuvem (GO do Breno)
    r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout


class CliAdapter:
    """Adaptador real: mesma interface da FakeCloud. ctx: project (google), tenancy (oci)."""

    def __init__(self, provider: str, run, ctx: dict | None = None):
        if provider not in PROVIDERS:
            raise SafetyError(f"provedor desconhecido: {provider}", "SWEEP")
        self.provider, self.run, self.ctx = provider, run, dict(ctx or {})
        self.errors: list[str] = []
        self._regions: list[str] | None = None

    def _call(self, argv, fields=None, required=True):
        argv = render(argv, {**self.ctx, **(fields or {})})
        rc, out = self.run(argv, None)
        if rc != 0:
            msg = f"{argv[0]} {argv[1]} {argv[2] if len(argv) > 2 else ''} falhou ({rc})"
            if required:
                raise SafetyError(msg, "SWEEP")
            self.errors.append(msg)
            return None
        return json.loads(out) if out.strip() else {}

    def regions(self) -> list[str]:
        if self._regions is None:
            rc, out = self.run(render(REGION_CMD[self.provider], self.ctx), None)
            if rc != 0:
                raise SafetyError(f"{self.provider}: leitura das regiões falhou ({rc})", "SWEEP")
            self._regions = parse_regions(self.provider, out)
        return self._regions

    def list_region(self, region: str) -> list[dict]:
        rows = []
        for name, argv, parser, _ in SOURCES[self.provider]["region"]:
            d = self._call(argv, {"region": region})
            rows += [dict(r, source=name) for r in parser(d, region)]
        for name, argv, parser, _ in SOURCES[self.provider]["region_best_effort"]:
            d = self._call(argv, {"region": region}, required=False)
            if d is not None:
                rows += [dict(r, source=name) for r in parser(d, region)]
        return rows

    def list_global(self) -> list[dict]:
        rows = []
        for name, argv, parser, _ in SOURCES[self.provider]["global"]:
            d = self._call(argv)
            rows += [dict(r, source=name) for r in parser(d, "global")]
        return rows

    def list_all(self) -> list[dict]:
        rows = self.list_global()
        for r in self.regions():
            rows += self.list_region(r)
        return dedupe(rows)

    def delete(self, item: dict) -> str:
        steps = delete_steps(self.provider, item.get("type"))
        if steps in ("cascade", None):
            return "removal_pending" if steps == "cascade" else "absent"
        if steps == "retained":
            return "purge_scheduled"
        fields = {**item, "id": item.get("id") or item.get("ref")}
        for st in steps:
            argv = render(st, {**self.ctx, **fields})
            if argv is None:
                continue
            rc, _ = self.run(argv, None)
            if rc != 0:
                raise SafetyError(f"remoção {item.get('type')} falhou ({rc})", "TEARDOWN")
        e_mode = {"aws_kms_key": "purge_scheduled", "oci_kms_vault": "purge_scheduled", "oci_kms_key": "purge_scheduled",
                  "google_kms_crypto_key": "purge_scheduled"}
        return e_mode.get(item.get("type"), "removal_pending")


def dedupe(rows: list[dict]) -> list[dict]:
    """A mesma referência vista por duas fontes vira um item (o da fonte específica prevalece no tipo)."""
    by = {}
    for r in rows:
        k = r.get("ref")
        if k is None:
            continue
        if k in by:
            old = by[k]
            if old.get("type", "").startswith(("aws_", "google_", "azurerm_", "oci_")):
                old["tags"] = {**r.get("tags", {}), **old.get("tags", {})}
                continue
            r = {**r, "tags": {**old.get("tags", {}), **r.get("tags", {})}}
        by[k] = r
    return list(by.values())
