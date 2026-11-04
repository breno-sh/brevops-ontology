"""Realização das fixtures das CQs no provider azurerm 5.12.0 (registry.terraform.io/hashicorp/azurerm).

Escolhas gerais (cada desvio da situação abstrata vai em Fx.deviations):
- todo slice cria o próprio grupo de recursos (sintetizado, ou indivíduo quando a situação pede um escopo);
- contêiner de objetos = azurerm_storage_container; namespace de armazenamento = azurerm_storage_account
  (blob_properties é configuração do namespace que vale para os seus contêineres);
- conjunto de regras = azurerm_network_security_group (precedência numérica, permitir e negar, com estado;
  o estado não é atributo da regra);
- autorização = azurerm_role_assignment com herança assinatura > grupo de recursos > recurso; principal =
  identidade gerenciada (usuários e grupos humanos vivem no Entra ID, provider azuread, fora dos pins);
- banco: Azure SQL (azurerm_mssql_server) é servidor lógico sem instância exposta; Postgres flexível é a
  instância (B_Standard_B1ms), sempre com autenticação só Entra ID quando a senha não é a pergunta.
"""
from __future__ import annotations

from ..hcl import Block, Json, Ref, Tpl, Var
from ..model import doc_citation, schema_attr_absent, schema_attr_present, schema_type_absent
from .base import Ctx, na, reg

PROVIDER = "azurerm"
VERSION = "5.12.0"
REALIZERS: dict = {}

CONTEXT_VARS = {
    "run_id": "identificador curto da execução (prefixo de nomes e tag bo_run); ligado pelo runner",
    "location_1": "localização l1 das fixtures (região Azure); ligada pelo runner",
    "location_2": "localização l2, distinta de l1; ligada pelo runner",
    "subscription_id": "assinatura sandbox (Azure for Students); ligada pelo runner, nunca gravada",
    "admin_ssh_public_key": "chave SSH PÚBLICA gerada na hora pelo runner para as VMs; a privada nunca sai do runner",
    "db_admin_password": "senha administrativa gerada na hora pelo runner (Withheld; nunca gravada)",
}

DOC = "203.0.113.0/24"
BLOB_READ = "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"

ALLOWED_TYPES = {
    # escopo por execução
    "azurerm_resource_group": {"category": "resource group por execução", "cost_class": "free"},
    "azurerm_resource_group_template_deployment": {"category": "resource group por execução (documento ARM)",
                                                   "cost_class": "free"},
    "data.azurerm_client_config": {"category": "leitura do contexto da sessão", "cost_class": "free"},
    # rede
    "azurerm_virtual_network": {"category": "VNet", "cost_class": "free"},
    "azurerm_subnet": {"category": "VNet", "cost_class": "free"},
    "azurerm_network_interface": {"category": "VNet", "cost_class": "free"},
    "azurerm_public_ip": {"category": "VNet (endereço público Standard)", "cost_class": "low"},
    "azurerm_route_table": {"category": "VNet", "cost_class": "free"},
    "azurerm_route": {"category": "VNet", "cost_class": "free"},
    "azurerm_subnet_route_table_association": {"category": "VNet", "cost_class": "free"},
    "azurerm_network_security_group": {"category": "NSG", "cost_class": "free"},
    "azurerm_network_security_rule": {"category": "NSG", "cost_class": "free"},
    "azurerm_network_interface_security_group_association": {"category": "NSG", "cost_class": "free"},
    "data.azurerm_network_watcher": {"category": "VNet (Network Watcher automático da região)",
                                     "cost_class": "free"},
    "azurerm_network_watcher_flow_log": {"category": "VNet flow log", "cost_class": "low"},
    "azurerm_network_manager": {"category": "NSG administrativo (só offline; custo por VNet gerenciada)",
                                "cost_class": "low"},
    "azurerm_network_manager_network_group": {"category": "NSG administrativo (só offline)", "cost_class": "free"},
    "azurerm_network_manager_security_admin_configuration": {"category": "NSG administrativo (só offline)",
                                                             "cost_class": "free"},
    "azurerm_network_manager_admin_rule_collection": {"category": "NSG administrativo (só offline)",
                                                      "cost_class": "free"},
    "azurerm_network_manager_admin_rule": {"category": "NSG administrativo (só offline)", "cost_class": "free"},
    # computação mínima
    "azurerm_linux_virtual_machine": {"category": "computação mínima (Standard_B1ls)", "cost_class": "low"},
    # armazenamento
    "azurerm_storage_account": {"category": "storage", "cost_class": "free"},
    "azurerm_storage_container": {"category": "storage", "cost_class": "free"},
    "data.azurerm_storage_container": {"category": "storage (leitura)", "cost_class": "free"},
    "azurerm_storage_container_immutability_policy": {"category": "storage", "cost_class": "free"},
    # IAM
    "azurerm_user_assigned_identity": {"category": "IAM (identidade gerenciada)", "cost_class": "free"},
    "azurerm_role_definition": {"category": "IAM", "cost_class": "free"},
    "azurerm_role_assignment": {"category": "IAM", "cost_class": "free"},
    # chaves, logs, alarmes
    "azurerm_key_vault": {"category": "Key Vault (sem purge protection)", "cost_class": "free"},
    "azurerm_key_vault_key": {"category": "Key Vault (sem purge protection)", "cost_class": "low"},
    "azurerm_log_analytics_workspace": {"category": "logs", "cost_class": "free"},
    "azurerm_monitor_action_group": {"category": "alarmes", "cost_class": "free"},
    "azurerm_monitor_activity_log_alert": {"category": "alarmes", "cost_class": "free"},
    "azurerm_monitor_metric_alert": {"category": "alarmes", "cost_class": "free"},
    # balanceador e banco (lote B)
    "azurerm_lb": {"category": "LB Standard (lote B)", "cost_class": "low"},
    "azurerm_lb_backend_address_pool": {"category": "LB Standard (lote B)", "cost_class": "free"},
    "azurerm_lb_probe": {"category": "LB Standard (lote B)", "cost_class": "free"},
    "azurerm_lb_rule": {"category": "LB Standard (lote B)", "cost_class": "free"},
    "azurerm_network_interface_backend_address_pool_association": {"category": "LB Standard (lote B)",
                                                                   "cost_class": "free"},
    "azurerm_postgresql_flexible_server": {"category": "Postgres flexível B1ms (lote B)", "cost_class": "low"},
    "azurerm_postgresql_flexible_server_database": {"category": "Postgres flexível B1ms (lote B)",
                                                    "cost_class": "free"},
    "azurerm_mssql_server": {"category": "Azure SQL Basic (lote B)", "cost_class": "free"},
    "azurerm_mssql_database": {"category": "Azure SQL Basic (lote B)", "cost_class": "low"},
}

SKU_RULES = {
    ("azurerm_linux_virtual_machine", "size"): ["Standard_B1ls"],
    ("azurerm_postgresql_flexible_server", "sku_name"): ["B_Standard_B1ms"],
    ("azurerm_postgresql_flexible_server", "storage_mb"): [32768],
    ("azurerm_mssql_database", "sku_name"): ["Basic"],
    ("azurerm_lb", "sku"): ["Standard"],
    ("azurerm_public_ip", "sku"): ["Standard"],
    ("azurerm_storage_account", "account_tier"): ["Standard"],
    ("azurerm_storage_account", "account_replication_type"): ["LRS"],
    ("azurerm_key_vault", "sku_name"): ["standard"],
    ("azurerm_key_vault", "purge_protection_enabled"): [False],
    ("azurerm_log_analytics_workspace", "sku"): ["PerGB2018"],
}


def header() -> str:
    def var(n, extra=""):
        return f'variable "{n}" {{\n  type        = string\n  description = "{CONTEXT_VARS[n]}"\n{extra}}}\n'
    return f'''terraform {{
  required_version = "= 1.15.8"
  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = "= {VERSION}"
    }}
  }}
}}

provider "azurerm" {{
  features {{}}
  subscription_id = var.subscription_id
}}

variable "run_id" {{
  type        = string
  description = "{CONTEXT_VARS['run_id']}"
  validation {{
    condition     = can(regex("^[a-z][a-z0-9]{{2,11}}$", var.run_id))
    error_message = "run_id: 3 a 12 caracteres, minúsculas e dígitos."
  }}
}}

{var("location_1")}
{var("location_2")}
{var("subscription_id")}
{var("admin_ssh_public_key")}
{var("db_admin_password", "  sensitive   = true" + chr(10))}'''


R = lambda *q: reg(REALIZERS, *q)  # noqa: E731

L1 = Var("location_1")
L2 = Var("location_2")
SUB_SCOPE = Tpl("/subscriptions/${var.subscription_id}")

# ----------------------------------------------------------------------------- ajudantes


def rg(c: Ctx, lid: str = "x_rg", entity: str | None = None, location=L1):
    return c.r("azurerm_resource_group", lid, {"name": c.name(lid), "location": location}, entity=entity,
               synth=None if entity else "grupo de recursos da fixture (slice autocontido; teardown por grupo)")


def client(c: Ctx):
    for x in c.res:
        if x.kind == "data" and x.type == "azurerm_client_config":
            return x
    return c.x("azurerm_client_config", "client", kind="data",
               why="tenant e objeto da sessão (exigidos por Key Vault e por administrador Entra ID)")


def sa(c: Ctx, lid: str, g, entity: str | None = None, location=None, attrs: dict | None = None, blocks=None,
       why: str = "conta de armazenamento (namespace) exigida pelo contêiner"):
    a = {"name": c.name(lid, sep="", maxlen=12), "resource_group_name": g.ref("name"),
         "location": location if location is not None else g.ref("location"),
         "account_tier": "Standard", "account_replication_type": "LRS"}
    a.update(attrs or {})
    return c.r("azurerm_storage_account", lid, a, blocks or [], entity=entity, synth=None if entity else why)


def container(c: Ctx, lid: str, acct, name=None, access=None, entity: str | None = None):
    a = {"name": name if name is not None else c.name(lid), "storage_account_id": acct.ref("id")}
    if access is not None:
        a["container_access_type"] = access
    return c.r("azurerm_storage_container", lid, a, entity=entity or lid)


def vnet(c: Ctx, g, lid: str = "x_vnet", entity: str | None = None, space: str = "10.30.0.0/16"):
    return c.r("azurerm_virtual_network", lid, {"name": c.name(lid), "resource_group_name": g.ref("name"),
                                                 "location": g.ref("location"), "address_space": [space]},
               entity=entity, synth=None if entity else "rede exigida pela sub-rede (virtual_network_name)")


def subnet(c: Ctx, g, vn, lid: str = "x_subnet", prefix: str = "10.30.1.0/24", entity: str | None = None):
    return c.r("azurerm_subnet", lid, {"name": c.name(lid), "resource_group_name": g.ref("name"),
                                        "virtual_network_name": vn.ref("name"), "address_prefixes": [prefix]},
               entity=entity, synth=None if entity else "sub-rede exigida pela interface (ip_configuration.subnet_id)")


def nic(c: Ctx, g, lid: str, subnet_id, entity: str | None = None, public_ip_id=None, extra_ipconfs=(),
        why: str | None = None):
    ipc = {"name": "primary", "subnet_id": subnet_id, "private_ip_address_allocation": "Dynamic"}
    if public_ip_id is not None:
        ipc["public_ip_address_id"] = public_ip_id
    blocks = [Block("ip_configuration", ipc)]
    for i, extra in enumerate(extra_ipconfs):
        blocks.append(Block("ip_configuration", {"name": f"secondary{i + 1}", "subnet_id": subnet_id,
                                                 "private_ip_address_allocation": "Dynamic", **extra}))
    return c.r("azurerm_network_interface", lid, {"name": c.name(lid), "resource_group_name": g.ref("name"),
                                                   "location": g.ref("location")}, blocks,
               entity=None if why else (entity or lid), synth=why)


def vm(c: Ctx, g, lid: str, nic_ids, entity: str | None = None, why: str | None = None):
    a = {"name": c.name(lid), "resource_group_name": g.ref("name"), "location": g.ref("location"),
         "size": "Standard_B1ls", "admin_username": "boadmin", "network_interface_ids": nic_ids}
    blocks = [Block("admin_ssh_key", {"username": "boadmin", "public_key": Var("admin_ssh_public_key")}),
              Block("os_disk", {"caching": "ReadWrite", "storage_account_type": "Standard_LRS"}),
              Block("source_image_reference", {"publisher": "Canonical", "offer": "0001-com-ubuntu-server-jammy",
                                               "sku": "22_04-lts-gen2", "version": "latest"})]
    return c.r("azurerm_linux_virtual_machine", lid, a, blocks, entity=None if why else (entity or lid), synth=why)


def nsg(c: Ctx, g, lid: str, rules=(), entity: str | None = None):
    blocks = [Block("security_rule", r) for r in rules]
    return c.r("azurerm_network_security_group", lid, {"name": c.name(lid), "resource_group_name": g.ref("name"),
                                                        "location": g.ref("location")}, blocks,
               entity=entity or lid)


def rule_obj(name, priority, access, port, source, direction="Inbound", protocol="Tcp"):
    return {"name": name, "priority": priority, "direction": direction, "access": access, "protocol": protocol,
            "source_port_range": "*", "destination_port_range": str(port), "source_address_prefix": source,
            "destination_address_prefix": "*"}


def nsg_rule(c: Ctx, g, sg, lid: str, priority, access, port, source, direction="Inbound", entity: str | None = None,
             synth: str | None = None):
    a = {"name": c.name(lid), "resource_group_name": g.ref("name"), "network_security_group_name": sg.ref("name"),
         **{k: v for k, v in rule_obj(None, priority, access, port, source, direction).items() if k != "name"}}
    return c.r("azurerm_network_security_rule", lid, a, entity=None if synth else (entity or lid), synth=synth)


def nsg_assoc(c: Ctx, n, sg, role: str = "nsg_assoc", nsg_id=None):
    return c.x("azurerm_network_interface_security_group_association", role,
               {"network_interface_id": n.ref("id"),
                "network_security_group_id": nsg_id if nsg_id is not None else sg.ref("id")},
               why="relação attached_to (conjunto de regras -> interface)")


def identity(c: Ctx, g, lid: str, entity: str | None = None):
    return c.r("azurerm_user_assigned_identity", lid, {"name": c.name(lid), "resource_group_name": g.ref("name"),
                                                        "location": g.ref("location")}, entity=entity or lid)


def role_def(c: Ctx, lid: str, scope, data_actions=(BLOB_READ,), entity: str | None = None):
    return c.r("azurerm_role_definition", lid, {"name": c.name(lid), "scope": scope},
               [Block("permissions", {"actions": [], "data_actions": list(data_actions)})],
               entity=entity or lid)


def role_assign(c: Ctx, lid: str, scope, rdef, principal_id, entity: str | None = None, extra: dict | None = None,
                synth: str | None = None):
    a = {"scope": scope, "role_definition_id": rdef.ref("role_definition_resource_id"), "principal_id": principal_id}
    a.update(extra or {})
    return c.r("azurerm_role_assignment", lid, a, entity=None if synth else (entity or lid), synth=synth)


def pg(c: Ctx, g, lid: str, entity: str | None = None, password=None, why: str | None = None):
    a = {"name": c.name(lid), "resource_group_name": g.ref("name"), "location": g.ref("location"),
         "version": "16", "sku_name": "B_Standard_B1ms", "storage_mb": 32768, "zone": "1"}
    if password is None:
        cl = client(c)
        blocks = [Block("authentication", {"active_directory_auth_enabled": True, "password_auth_enabled": False,
                                           "tenant_id": cl.ref("tenant_id")})]
    else:
        a.update({"administrator_login": "boadmin", "administrator_password": password})
        blocks = []
    return c.r("azurerm_postgresql_flexible_server", lid, a, blocks, entity=None if why else (entity or lid),
               synth=why)


def sql_server(c: Ctx, g, lid: str, entity: str | None = None, why: str | None = None):
    cl = client(c)
    return c.r("azurerm_mssql_server", lid, {"name": c.name(lid), "resource_group_name": g.ref("name"),
                                              "location": g.ref("location"), "version": "12.0"},
               [Block("azuread_administrator", {"login_username": "bo-admin", "object_id": cl.ref("object_id"),
                                                "azuread_authentication_only": True})],
               entity=None if why else (entity or lid), synth=why)


def sql_db(c: Ctx, srv, lid: str, entity: str | None = None, blocks=None, synth: str | None = None):
    return c.r("azurerm_mssql_database", lid, {"name": c.name(lid), "server_id": srv.ref("id"), "sku_name": "Basic"},
               blocks or [], entity=None if synth else (entity or lid), synth=synth)


def flow(direction="ingress", protocol="tcp", port=443, source="203.0.113.10/32") -> dict:
    d = {"direction": direction, "port": port, "source_cidr": source}
    if protocol:
        d["protocol"] = protocol
    return d


def action_group(c: Ctx, g, lid: str = "t1"):
    return c.r("azurerm_monitor_action_group", lid, {"name": c.name(lid), "resource_group_name": g.ref("name"),
                                                      "short_name": "bocqfix"}, entity=lid)


AZ_NSG_STATEFUL = doc_citation(
    "https://learn.microsoft.com/azure/virtual-network/network-security-groups-overview",
    "regras de NSG são sempre com estado (o retorno de um fluxo permitido é permitido) e o estado não é "
    "atributo declarável por regra")
AZ_DENY_ASSIGN = doc_citation(
    "https://learn.microsoft.com/azure/role-based-access-control/deny-assignments",
    "atribuições de negação não são criadas diretamente pelo cliente; só por serviços gerenciados da Azure")
EV_NO_DENY = schema_type_absent(
    "azurerm", r"deny",
    "o azurerm 5.12.0 não tem tipo de atribuição de negação (deny assignment); só allow por role_assignment")
EV_NO_MFA = schema_type_absent(
    "azurerm", r"(conditional_access|multi_factor|mfa|two_factor|authentication_method|authentication_strength)",
    "exigência de segundo fator é política do Entra ID (provider azuread, fora dos pins); o azurerm não tem o tipo")
EV_NO_DIR = schema_type_absent(
    "azurerm", r"(azuread|_ad_user|_ad_group|aad_user|aad_group|group_member)",
    "usuários humanos, grupos e pertença vivem no Entra ID (provider azuread, fora dos pins)")
EV_NSG_NO_STATE = schema_attr_absent(
    "azurerm", "azurerm_network_security_rule", r"(state|track)",
    "a regra de NSG não tem atributo de estado: não existe regra sem estado no Azure")

# ============================================================================ CIS


@R("CQ-CIS-01")
def cis_mfa(v, c: Ctx):
    return na("o segundo fator do principal humano é configurado no Entra ID, fora do provider azurerm fixado",
              EV_NO_MFA)


@R("CQ-CIS-02")
def cis_key_age(v, c: Ctx):
    g = rg(c)
    acct = sa(c, "k1", g, entity="k1_holder")
    c.emap.pop("k1_holder")
    c.map("k1", f"{acct.address}#primary_access_key")
    c.map("p1", f"implicit:portador da chave compartilhada da conta {acct.address} (quem a usa como credencial)")
    c.synth[f"{acct.address}#primary_access_key"] = "segredo computado: Withheld, nunca lido nem gravado"
    c.dev.append("CIS Azure 9.3.1.2 trata a chave de acesso da conta de armazenamento; a chave é componente "
                 "implícito da conta (sem recurso próprio) e o principal é quem a porta, sem recurso no azurerm")
    if v == "incomplete":
        c.missing("k1", "observation", "READ_MASK", "nenhuma leitura datada de keyCreationTime da conta foi feita; "
                  "a idade da chave não existe sem observação", acct.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done("INTERPRETED", deploy_note="chave de acesso computada: só com redator (SAFETY)")
    age = 10 if v == "conforming" else 120
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": acct.address, "field": "keyCreationTime.key1", "age_days": age},
        "act": {"observed_at": "2026-11-02T10:00:00-03:00", "api": "Microsoft.Storage/storageAccounts/read"}}}}
    if v == "nonconforming":
        return c.done("INTERPRETED", deployable=False,
                      deploy_note="idade de 120 dias não se produz num deploy novo: só offline com observação gravada")
    return c.done("INTERPRETED", deploy_note="chave de acesso computada: só com redator (SAFETY)")


def key_vault(c: Ctx, g):
    cl = client(c)
    kv = c.x("azurerm_key_vault", "kv", {
        "name": c.name("kv", sep="", maxlen=11), "resource_group_name": g.ref("name"), "location": g.ref("location"),
        "tenant_id": cl.ref("tenant_id"), "sku_name": "standard", "purge_protection_enabled": False,
        "soft_delete_retention_days": 7, "rbac_authorization_enabled": True},
        why="cofre que guarda a chave (azurerm_key_vault_key exige key_vault_id); sem purge protection (SAFETY)")
    ra = c.x("azurerm_role_assignment", "kv_officer", {
        "scope": kv.ref("id"), "role_definition_name": "Key Vault Crypto Officer",
        "principal_id": cl.ref("object_id")},
        why="permissão de plano de dados para a sessão criar a chave (cofre com RBAC)")
    return kv, ra


@R("CQ-CIS-03")
def cis_kms(v, c: Ctx):
    g = rg(c)
    kv, ra = key_vault(c, g)
    rot = Block("rotation_policy", {"expire_after": "P180D", "notify_before_expiry": "P29D"},
                [Block("automatic", {"time_after_creation": "P90D"})])
    blocks = []
    if v == "conforming":
        blocks = [rot]
    elif v == "incomplete":
        flag = c.symvar("rotation", "bool")
        blocks = [Block("dynamic", {"for_each": Ref(flag.expr + " ? [1] : []")},
                        [Block("content", rot.attrs, rot.blocks)], labels=("rotation_policy",))]
    k = c.r("azurerm_key_vault_key", "k1", {"name": c.name("k1"), "key_vault_id": kv.ref("id"), "key_type": "RSA",
                                            "key_size": 2048, "key_opts": ["encrypt", "decrypt"]}, blocks,
            entity="k1", depends_on=[ra.address])
    c.map("d1", f"{k.address}#rotation_policy")
    if v == "nonconforming":
        c.dev.append("rotação desligada = bloco rotation_policy ausente (o Key Vault não tem flag booleana)")
    if v == "incomplete":
        c.missing("d1", "value", "SYMBOLIC_INPUT", "a presença do bloco rotation_policy vem de variável sem valor",
                  k.address)
    return c.done(cost_class="low")


def _ports(v, c: Ctx, port: int):
    g = rg(c)
    sg = nsg(c, g, "rs1")
    if v == "incomplete":
        src = c.symvar("source_cidr")
        c.missing("r1", "value", "SYMBOLIC_INPUT", "source_address_prefix da regra vem de variável sem valor",
                  f"azurerm_network_security_rule.{c.lab('r1')}")
    else:
        src = DOC if v == "conforming" else "0.0.0.0/0"
    nsg_rule(c, g, sg, "r1", 100, "Allow", port, src)
    return c.done()


@R("CQ-CIS-04")
def cis_ssh(v, c):
    return _ports(v, c, 22)


@R("CQ-CIS-05")
def cis_rdp(v, c):
    return _ports(v, c, 3389)


@R("CQ-CIS-06")
def cis_flow(v, c: Ctx):
    g = rg(c)
    vn = vnet(c, g, "vn1", entity="vn1")
    sn = subnet(c, g, vn, "sa", entity="sa")
    if v == "nonconforming":
        c.map("s1", "implicit:assinatura sandbox, leitura completa declarada dos flow logs do Network Watcher")
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "Microsoft.Network/networkWatchers/flowLogs/read",
                                                               "complete": True}}}
        return c.done()
    nw = c.x("azurerm_network_watcher", "nw", {"name": Tpl("NetworkWatcher_${var.location_1}"),
                                              "resource_group_name": "NetworkWatcherRG"}, kind="data",
             why="Network Watcher automático da região (um por região e assinatura; o flow log fica no grupo dele)")
    logs = sa(c, "x_logs", g, why="conta que recebe o registro de fluxo (storage_account_id obrigatório)")
    enabled = True
    if v == "incomplete":
        enabled = c.symvar("flow_log_enabled", "bool")
        c.missing("d1", "value", "SYMBOLIC_INPUT", "enabled do flow log vem de variável sem valor",
                  f"azurerm_network_watcher_flow_log.{c.lab('d1')}")
    c.r("azurerm_network_watcher_flow_log", "d1", {
        "name": c.name("d1"), "network_watcher_name": nw.ref("name"), "resource_group_name": nw.ref("resource_group_name"),
        "target_resource_id": sn.ref("id"), "storage_account_id": logs.ref("id"), "enabled": enabled, "version": 2},
        [Block("retention_policy", {"enabled": True, "days": 1})], entity="d1")
    c.dev.append("CIS Azure 6.1.1.7 (VNet flow logs); flow log de NSG novo foi aposentado; o alvo é a sub-rede "
                 "(target_resource_id aceita VNet, sub-rede ou interface)")
    return c.done(cost_class="low", deploy_note="depende do Network Watcher automático da região (NetworkWatcherRG)")


@R("CQ-CIS-07")
def cis_alert(v, c: Ctx):
    g = rg(c, "s1", entity="s1")
    t = action_group(c, g)
    if v == "incomplete":
        op = c.symvar("operation_name")
        c.missing("al1", "value", "SYMBOLIC_INPUT", "criteria.operation_name vem de variável sem valor",
                  f"azurerm_monitor_activity_log_alert.{c.lab('al1')}")
    else:
        op = ("Microsoft.Network/networkSecurityGroups/write" if v == "conforming"
              else "Microsoft.Network/routeTables/write")
    c.r("azurerm_monitor_activity_log_alert", "al1", {
        "name": c.name("al1"), "resource_group_name": g.ref("name"), "location": "global", "scopes": [g.ref("id")]},
        [Block("criteria", {"category": "Administrative", "operation_name": op}),
         Block("action", {"action_group_id": t.ref("id")})], entity="al1")
    c.dev.append("tópico de notificação = action group (destino das notificações do alerta); escopo = o grupo de "
                 "recursos da fixture")
    if v == "nonconforming":
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "Microsoft.Insights/activityLogAlerts/read",
                                                               "complete": True}}}
    return c.done()


@R("CQ-CIS-08")
def cis_public(v, c: Ctx):
    g = rg(c)
    attrs = {}
    if v != "conforming":
        attrs["allow_nested_items_to_be_public"] = True
    acct = sa(c, "x_sa", g, attrs=attrs)
    if v != "conforming":
        c.synth[f"{acct.address}#allow_nested_items_to_be_public"] = (
            "pré-condição do namespace para o nível de acesso do contêiner ter efeito (sem ela o contêiner nunca "
            "seria público e a resposta não dependeria de k1)")
    if v == "incomplete":
        access = c.symvar("access_type")
        c.missing("k1", "value", "SYMBOLIC_INPUT", "container_access_type vem de variável sem valor",
                  f"azurerm_storage_container.{c.lab('c1')}")
    else:
        access = "private" if v == "conforming" else "blob"
    ct = container(c, "c1", acct, access=access)
    c.map("k1", f"{ct.address}#container_access_type")
    c.dev.append("k1 é o nível de acesso declarado no próprio contêiner (dono e alcance = c1); a conta tem a "
                 "pré-condição allow_nested_items_to_be_public, registrada como síntese")
    return c.done()


# ============================================================================ identidade e ciclo de vida


@R("CQ-IDL-01")
def idl_change(v, c: Ctx):
    if v == "nonconforming":
        g = rg(c, location=L2)
        acct = sa(c, "x_sa", g, location=L2, why="conta (namespace) do contêiner, agora em location_2")
        ct = container(c, "c2", acct, name=c.name("data_a"))
        c.map("c1", "probe:change.before")
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "location (da conta que contém o contêiner)",
            "before": {"address": ct.address, "storage_account_location": "var.location_1",
                       "name": "${var.run_id}-fx-idl-01-n-data-a"},
            "after": "main.tf", "plan_action_expected": "replace"}}}
        c.dev.append("o contêiner não tem localização própria: a mudança de localização é da conta que o contém "
                     "(location força substituição da conta e, com ela, do contêiner)")
        return c.done()
    g = rg(c)
    if v == "conforming":
        acct = sa(c, "x_sa", g)
        ct = container(c, "c1", acct, name=c.name("data_a"))
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "metadata", "before": {"address": ct.address, "metadata": {}},
            "after": "main.tf", "plan_action_expected": "update"}}}
        ct.attrs["metadata"] = {"bo_phase": "after"}
        c.dev.append("o versionamento no Azure é da conta (namespace), não do contêiner; a mudança mutável no "
                     "próprio contêiner é metadata, atualizada no lugar")
        return c.done()
    acct = sa(c, "x_sa", g, attrs={"access_tier": "Cool"})
    container(c, "c1", acct, name=c.name("data_a"))
    c.probe = {"kind": "two_phase", "inputs": {"change": {
        "attribute": "access_tier (da conta)", "before": {"address": acct.address, "access_tier": "Hot"},
        "after": "main.tf", "plan_action_expected": "UNKNOWN"}}}
    c.missing("c1", "mutability", "EVIDENCE_GAP", "o schema JSON do provider não expõe ForceNew; não há fato de "
              "serviço (SERVICE-EVIDENCE) dizendo se access_tier muda no lugar", acct.address)
    c.dev.append("camada de armazenamento é da conta (access_tier), vale para os blobs do contêiner")
    return c.done()


@R("CQ-IDL-02")
def idl_same_key(v, c: Ctx):
    c.map("acc", "implicit:assinatura sandbox (var.subscription_id)")
    c.map("l1", "implicit:var.location_1")
    g = rg(c)
    a1 = sa(c, "x_sa1", g, location=L1, why="conta em location_1 que contém c1")
    container(c, "c1", a1, name="data")
    if v == "conforming":
        c.map("l2", "implicit:var.location_2")
        a2 = sa(c, "x_sa2", g, location=L2, why="conta em location_2 que contém c2")
        container(c, "c2", a2, name="data")
        c.dev.append("a chave local do contêiner é única só dentro da conta; as duas contas (sintetizadas) dão as "
                     "localizações diferentes; a identidade composta também difere pela conta, o que mantém a "
                     "resposta (indivíduos distintos)")
        return c.done()
    if v == "nonconforming":
        c.r("azurerm_storage_container", "c2", {"name": "data", "storage_account_id": a1.ref("id")}, kind="data",
            entity="c2")
        c.dev.append("c2 é a segunda leitura (data source) do mesmo contêiner: mesma conta, localização e chave")
        return c.done()
    acct = c.symvar("storage_account_id")
    c.r("azurerm_storage_container", "c2", {"name": "data", "storage_account_id": acct}, kind="data", entity="c2")
    c.missing("c2", "location", "EXTERNAL_REFERENCE", "c2 é lido numa conta dada por variável sem valor; a "
              "localização dele (a da conta) não foi lida", f"data.azurerm_storage_container.{c.lab('c2')}")
    return c.done()


@R("CQ-IDL-03")
def idl_survive(v, c: Ctx):
    if v == "conforming":
        g = rg(c, "s1", entity="s1")
        p = identity(c, g, "p1")
        d = role_def(c, "ps1", g.ref("id"))
        a = role_assign(c, "a1", g.ref("id"), d, p.ref("principal_id"))
        c.probe = {"kind": "static", "inputs": {"removal": {"X": p.address, "Y": a.address}}}
        return c.done()
    g = rg(c)
    if v == "nonconforming":
        acct = sa(c, "ns1", g, entity="ns1")
        ct = container(c, "c1", acct)
        c.probe = {"kind": "static", "inputs": {"removal": {"X": ct.address, "Y": acct.address}}}
        return c.done()
    acct = sa(c, "x_sa", g)
    ct = container(c, "c1", acct)
    s = c.r("azurerm_storage_container_immutability_policy", "s1", {
        "storage_container_resource_manager_id": ct.ref("id"), "immutability_period_in_days": 1, "locked": False},
        entity="s1")
    c.probe = {"kind": "static", "inputs": {"removal": {"X": s.address, "Y": ct.address}}}
    c.missing("s1", "lifecycle", "EVIDENCE_GAP", "sem fato de serviço sobre quem controla o ciclo de vida da "
              "política de imutabilidade (recurso separado com id próprio, mas preso ao contêiner?)", s.address)
    c.dev.append("retenção = política de imutabilidade por tempo do contêiner (não bloqueada, 1 dia)")
    return c.done()


@R("CQ-IDL-04")
def idl_occurrence(v, c: Ctx):
    if v == "nonconforming":
        return na("no NSG cada regra tem nome obrigatório (chave local) e é ele que identifica a ocorrência; mudar a "
                  "porta de uma regra com o mesmo nome é atualização da mesma regra, não outra ocorrência anônima",
                  schema_attr_present("azurerm", "azurerm_network_security_rule", "name",
                                      "nome obrigatório da regra (também obrigatório no bloco security_rule do NSG)"))
    g = rg(c)
    r2 = rule_obj("r2-ssh", 210, "Allow", 22, DOC)
    if v == "conforming":
        r1 = rule_obj("r1-https", 200, "Allow", 443, DOC)
        sg = nsg(c, g, "rs1", [r2, r1])
        c.map("r1", f"{sg.address}#security_rule[r1-https]")
        c.map("r2", f"{sg.address}#security_rule[r2-ssh]")
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "ordem textual dos blocos security_rule",
            "before": {"address": sg.address, "order": ["r1-https", "r2-ssh"]},
            "after": "main.tf", "plan_action_expected": "no-op"}}}
        c.dev.append("as regras do NSG não são anônimas: têm nome; a identidade vem do nome, nunca da posição, o "
                     "que mantém a resposta (trocar a ordem não muda as identidades)")
        return c.done()
    name = c.symvar("r1_name")
    port = c.symvar("r1_port")
    r1 = {"name": name, "priority": 200, "direction": "Inbound", "access": "Allow", "protocol": "Tcp",
          "source_port_range": "*", "destination_port_range": port, "source_address_prefix": DOC,
          "destination_address_prefix": "*"}
    sg = nsg(c, g, "rs1", [r2, r1])
    c.map("r1", f"{sg.address}#security_rule[var.{c.slug}_r1_name]")
    c.map("r2", f"{sg.address}#security_rule[r2-ssh]")
    c.probe = {"kind": "two_phase", "inputs": {"change": {
        "attribute": "campos de identidade de r1", "before": {"address": sg.address},
        "after": "main.tf", "plan_action_expected": "UNKNOWN"}}}
    c.missing("r1", "identity_fields", "SYMBOLIC_INPUT", "nome e porta de r1 vêm de variáveis sem valor", sg.address)
    return c.done()


# ============================================================================ composição


@R("CQ-CMP-01")
def cmp_unit(v, c: Ctx):
    g = rg(c)
    if v == "conforming":
        vn = vnet(c, g, "vn1", entity="vn1")
        sn = subnet(c, g, vn, "sa", entity="sa")
        n = nic(c, g, "nic1", sn.ref("id"))
        vm(c, g, "vm1", [n.ref("id")])
        return c.done(cost_class="low")
    if v == "nonconforming":
        vnet(c, g, "vn1", entity="vn1")
        n = nic(c, g, "nic1", "/subscriptions/sub-sintetica/resourceGroups/rg-ausente/providers/"
                                "Microsoft.Network/virtualNetworks/vn-ausente/subnets/sub-ausente")
        vm(c, g, "vm1", [n.ref("id")])
        c.dev.append("a sub-rede referenciada é um id sintético (sem guid) que não existe na leitura completa")
        return c.done(deployable=False, deploy_note="o apply tem de falhar (dependência ausente); fica para o DEP "
                                                    "decidir se testa REJECTED_BY_API")
    sid = c.symvar("subnet_id")
    c.map("sa", f"external:var.{c.slug}_subnet_id: sub-rede em escopo não lido")
    n = nic(c, g, "nic1", sid)
    vm(c, g, "vm1", [n.ref("id")])
    c.missing("sa", "scope", "EXTERNAL_REFERENCE", "subnet_id vem de variável: a sub-rede e a cadeia acima dela "
              "(rede) estão fora da leitura", n.address)
    return c.done(cost_class="low")


def _net_base(c: Ctx, g):
    vn = vnet(c, g)
    sn = subnet(c, g, vn)
    return vn, sn


@R("CQ-CMP-02")
def cmp_two_nics(v, c: Ctx):
    g = rg(c)
    _, sn = _net_base(c, g)
    n1 = nic(c, g, "nic1", sn.ref("id"))
    if v == "conforming":
        n2 = nic(c, g, "nic2", sn.ref("id"))
        vm(c, g, "vm1", [n1.ref("id"), n2.ref("id")])
        c.dev.append("anexação por referência (network_interface_ids, ordem = índice; a primeira é a primária)")
        return c.done(cost_class="low")
    if v == "nonconforming":
        vm(c, g, "vm1", [n1.ref("id")])
        return c.done(cost_class="low")
    nic(c, g, "nic2", sn.ref("id"))
    extra = c.symvar("extra_nic_ids", "list(string)")
    vm(c, g, "vm1", Ref(f"concat([{n1.address}.id], {extra.expr})"))
    c.missing("nic2", "attachment", "SYMBOLIC_INPUT", "as demais interfaces da VM vêm de variável sem valor: não se "
              "sabe se nic2 está anexada", f"azurerm_linux_virtual_machine.{c.lab('vm1')}")
    return c.done(cost_class="low")


@R("CQ-CMP-03")
def cmp_lb(v, c: Ctx):
    g = rg(c)
    _, sn = _net_base(c, g)
    lb = c.r("azurerm_lb", "lb1", {"name": c.name("lb1"), "resource_group_name": g.ref("name"),
                                   "location": g.ref("location"), "sku": "Standard"},
             [Block("frontend_ip_configuration", {"name": "fe1", "subnet_id": sn.ref("id"),
                                                  "private_ip_address_allocation": "Dynamic"})], entity="lb1")
    c.map("fe1", f"{lb.address}#frontend_ip_configuration[fe1]")
    pool = c.r("azurerm_lb_backend_address_pool", "pool1", {"name": c.name("pool1"), "loadbalancer_id": lb.ref("id")},
               entity="pool1")
    hp = c.r("azurerm_lb_probe", "hp1", {"name": c.name("hp1"), "loadbalancer_id": lb.ref("id"), "port": 443,
                                         "protocol": "Tcp"}, entity="hp1")
    ru = c.r("azurerm_lb_rule", "ru1", {"name": c.name("ru1"), "loadbalancer_id": lb.ref("id"), "protocol": "Tcp",
                                        "frontend_port": 443, "backend_port": 443, "frontend_ip_configuration_name": "fe1",
                                        "backend_address_pool_ids": [pool.ref("id")], "probe_id": hp.ref("id")},
             entity="ru1")
    c.map("li1", f"{ru.address}#frontend_port")
    c.dev.append("o LB Standard é de camada 4 (lb1.layer=7 na situação abstrata): listener e regra de roteamento "
                 "são a mesma regra (frontend_port -> pool), 'match any' = toda conexão TCP na porta; a sonda se liga "
                 "ao pool pela regra (probe_id). A cadeia que a CQ pergunta é a mesma")
    if v == "conforming":
        n = nic(c, g, "x_nic", sn.ref("id"), why="interface pela qual a VM entra no pool")
        vm(c, g, "vm1", [n.ref("id")])
        c.x("azurerm_network_interface_backend_address_pool_association", "member", {
            "network_interface_id": n.ref("id"), "ip_configuration_name": "primary",
            "backend_address_pool_id": pool.ref("id")}, why="relação member_of_pool (VM -> pool)")
        return c.done(cost_class="low")
    if v == "incomplete":
        c.missing("pool1", "membership", "READ_MASK", "os membros do pool (backendAddressPools/loadBalancer"
                  "BackendAddresses e associações de interface) não foram lidos", pool.address)
    return c.done(cost_class="low")


@R("CQ-CMP-04")
def cmp_scope(v, c: Ctx):
    g = rg(c)
    if v == "conforming":
        acct = sa(c, "ns1", g, entity="ns1", blocks=[Block("blob_properties", {"versioning_enabled": True})])
        container(c, "c1", acct)
        c.map("k1", f"{acct.address}#blob_properties.versioning_enabled")
        return c.done()
    if v == "nonconforming":
        acct = sa(c, "ns1", g, entity="ns1")
        container(c, "c1", acct)
        c2 = container(c, "c2", acct)
        c.r("azurerm_storage_container_immutability_policy", "k1", {
            "storage_container_resource_manager_id": c2.ref("id"), "immutability_period_in_days": 1, "locked": False},
            entity="k1")
        c.dev.append("versionamento no Azure só existe no nível da conta; a configuração declarada e guardada em "
                     "outro contêiner é a política de imutabilidade de c2 (proteção de versão no nível do "
                     "contêiner); dono e alcance continuam sendo c2, o que mantém a resposta")
        return c.done()
    acct = sa(c, "ns1", g, entity="ns1", blocks=[Block("blob_properties", {"versioning_enabled": True})])
    c.map("k1", f"{acct.address}#blob_properties.versioning_enabled")
    other = c.symvar("storage_account_id")
    c.r("azurerm_storage_container", "c1", {"name": "data", "storage_account_id": other}, kind="data", entity="c1")
    c.missing("c1", "membership", "EXTERNAL_REFERENCE", "c1 é lido numa conta dada por variável sem valor: não se "
              "sabe se pertence a ns1", f"data.azurerm_storage_container.{c.lab('c1')}")
    return c.done()


@R("CQ-CMP-05")
def cmp_db(v, c: Ctx):
    g = rg(c)
    if v == "conforming":
        s = pg(c, g, "i1")
        c.r("azurerm_postgresql_flexible_server_database", "db1", {"name": "bodb", "server_id": s.ref("id")},
            entity="db1")
        c.dev.append("engine_b = PostgreSQL 16 (motor abstrato)")
        return c.done(cost_class="low")
    if v == "nonconforming":
        s = sql_server(c, g, "srv1")
        sql_db(c, s, "db1")
        c.dev.append("Azure SQL: o servidor lógico não expõe instância; a situação abstrata diz ha_managed=false e o "
                     "serviço mantém réplicas internas, mas nenhuma é recurso ou indivíduo lido — a resposta "
                     "(servidor lógico não conta como instância) não depende disso")
        return c.done(cost_class="low", evidence_level="INTERPRETED")
    s = sql_server(c, g, "srv2")
    sql_db(c, s, "db1")
    c.missing("srv2", "instance_count", "EVIDENCE_GAP", "o número de réplicas que sustentam o banco Basic não é "
              "atributo do schema nem fato de serviço registrado", s.address)
    return c.done(cost_class="low", evidence_level="INTERPRETED")


# ============================================================================ autorização


def _aut_scopes(c: Ctx):
    g = rg(c, "s_parent", entity="s_parent")
    acct = sa(c, "s_child", g, entity="s_child")
    ct = container(c, "r1", acct)
    return g, acct, ct


def _req(principal, resource, context=None):
    return {"principal": principal, "action": "read", "resource": resource, "context": context or {}}


@R("CQ-AUT-01")
def aut_inherit(v, c: Ctx):
    if v == "nonconforming":
        return na("negação explícita aplicável no escopo filho não é criável: o azurerm não tem atribuição de "
                  "negação", EV_NO_DENY, AZ_DENY_ASSIGN)
    if v == "conforming":
        g, acct, ct = _aut_scopes(c)
        p = identity(c, g, "p1")
        d = role_def(c, "ps1", g.ref("id"))
        c.map("perm1", f"{d.address}#permissions.data_actions[0]")
        role_assign(c, "a1", g.ref("id"), d, p.ref("principal_id"))
        c.map("q1", "probe:access_request")
        c.probe = {"kind": "static", "inputs": {"access_request": _req(p.address, ct.address)}}
        return c.done()
    gx = rg(c)
    p = identity(c, gx, "p1")
    parent = c.symvar("parent_rg_name")
    acct = c.r("azurerm_storage_account", "s_child", {
        "name": c.name("s_child", sep="", maxlen=12), "resource_group_name": parent, "location": L1,
        "account_tier": "Standard", "account_replication_type": "LRS"}, entity="s_child")
    ct = container(c, "r1", acct)
    c.map("s_parent", f"external:var.{c.slug}_parent_rg_name: grupo de recursos pai fora da leitura")
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": _req(p.address, ct.address)}}
    c.missing("s_parent", "scope", "EXTERNAL_REFERENCE", "o grupo de recursos pai vem de variável; atribuições "
              "nele (e acima, na assinatura) não foram lidas", acct.address)
    return c.done()


@R("CQ-AUT-02")
def aut_count(v, c: Ctx):
    g = rg(c, "s1", entity="s1")
    p = identity(c, g, "p1")
    d1 = role_def(c, "ps1", g.ref("id"))
    role_assign(c, "a1", g.ref("id"), d1, p.ref("principal_id"))
    if v == "nonconforming":
        d2 = role_def(c, "ps2", g.ref("id"), data_actions=("Microsoft.Storage/storageAccounts/blobServices/"
                                                            "containers/blobs/write",))
        role_assign(c, "a2", g.ref("id"), d2, p.ref("principal_id"))
        return c.done()
    principal = p.ref("principal_id") if v == "conforming" else c.symvar("principal_id")
    tmpl = {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
            "contentVersion": "1.0.0.0",
            "parameters": {"principalId": {"type": "string"}, "roleDefinitionId": {"type": "string"}},
            "resources": [{"type": "Microsoft.Authorization/roleAssignments", "apiVersion": "2022-04-01",
                           "name": "[guid(resourceGroup().id, parameters('principalId'), 'a2')]",
                           "properties": {"principalId": "[parameters('principalId')]",
                                          "roleDefinitionId": "[parameters('roleDefinitionId')]"}}]}
    params = {"principalId": {"value": principal},
              "roleDefinitionId": {"value": d1.ref("role_definition_resource_id")}}
    doc = c.r("azurerm_resource_group_template_deployment", "doc1", {
        "name": c.name("doc1"), "resource_group_name": g.ref("name"), "deployment_mode": "Incremental",
        "template_content": Json(tmpl), "parameters_content": Json(params)}, entity="doc1")
    c.map("a2", f"{doc.address}#template_content.resources[0]")
    c.dev.append("a forma 'documento' no Azure é o modelo ARM implantado (declaração roleAssignments dentro do "
                 "documento); realização INTERPRETED")
    if v == "incomplete":
        c.missing("a2", "reference", "SYMBOLIC_INPUT", "o principal da declaração no documento vem de variável sem "
                  "valor", doc.address)
        return c.done("INTERPRETED", deployable=False, deploy_note="o principal simbólico não implanta")
    return c.done("INTERPRETED", deployable=False,
                  deploy_note="a API recusa a segunda atribuição idêntica (RoleAssignmentExists): só offline")


@R("CQ-AUT-03")
def aut_no_upward(v, c: Ctx):
    g = rg(c, "s_parent", entity="s_parent")
    child = sa(c, "s_child", g, entity="s_child")
    other = sa(c, "x_sa2", g, why="conta que contém r2: r2 está no escopo pai e fora do escopo filho")
    r2 = container(c, "r2", other)
    p = identity(c, g, "p1")
    d = role_def(c, "ps1", g.ref("id"))
    c.map("perm1", f"{d.address}#permissions.data_actions[0]")
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": _req(p.address, r2.address)}}
    if v == "nonconforming":
        role_assign(c, "a1", g.ref("id"), d, p.ref("principal_id"))
        return c.done()
    if v == "conforming":
        role_assign(c, "a1", child.ref("id"), d, p.ref("principal_id"))
        return c.done()
    scope = c.symvar("assignment_scope")
    role_assign(c, "a1", scope, d, p.ref("principal_id"))
    c.missing("s_child", "scope", "SYMBOLIC_INPUT", "o escopo da atribuição vem de variável sem valor: não se sabe "
              "qual escopo contém qual", f"azurerm_role_assignment.{c.lab('a1')}")
    return c.done()


@R("CQ-AUT-04")
def aut_group(v, c: Ctx):
    if v != "incomplete":
        return na("usuário humano, grupo e pertença não existem no azurerm fixado (Entra ID, provider azuread)",
                  EV_NO_DIR)
    g = rg(c, "s1", entity="s1")
    d = role_def(c, "ps1", g.ref("id"))
    gid = c.symvar("group_object_id")
    role_assign(c, "a1", g.ref("id"), d, gid, extra={"principal_type": "Group"})
    c.map("g1", f"external:var.{c.slug}_group_object_id: grupo mantido no Entra ID (fora dos pins)")
    c.map("u1", "external:usuário mantido no Entra ID (fora dos pins), sem endereço na configuração")
    c.map("dir1", "implicit:Entra ID do tenant (diretório fora dos providers fixados)")
    c.missing("u1", "group_membership", "EXTERNAL_REFERENCE", "a pertença do usuário ao grupo é do Entra ID, "
              "fora do pin (OUT_OF_PIN)", f"azurerm_role_assignment.{c.lab('a1')}")
    return c.done()


@R("CQ-AUT-05")
def aut_condition(v, c: Ctx):
    g = rg(c, "s1", entity="s1")
    acct = sa(c, "x_sa", g)
    ct = container(c, "r1", acct)
    p = identity(c, g, "p1")
    d = role_def(c, "ps1", g.ref("id"))
    c.map("perm1", f"{d.address}#permissions.data_actions[0]")
    vn = vnet(c, g)
    sn_ok = subnet(c, g, vn, "x_subnet_ok", "10.30.1.0/24")
    sn_other = subnet(c, g, vn, "x_subnet_other", "10.30.2.0/24")
    if v == "incomplete":
        cond = (f"((!(ActionMatches{{'{BLOB_READ}'}})) OR "
                "(@Principal[Microsoft.Directory/CustomSecurityAttributes/Attributes:posture_compliant] "
                "StringEquals 'true'))")
        cond_val = cond
    else:
        cond_val = Tpl(f"((!(ActionMatches{{'{BLOB_READ}'}})) OR "
                       "(@Environment[Microsoft.Network/virtualNetworks/subnets] "
                       "ForAnyOfAnyValues:StringEqualsIgnoreCase '${" + sn_ok.address + ".id}'))")
    a = role_assign(c, "a1", g.ref("id"), d, p.ref("principal_id"),
                    extra={"condition": cond_val, "condition_version": "2.0"})
    c.map("c1", f"{a.address}#condition")
    c.map("q1", "probe:access_request")
    c.dev.append("a condição ABAC do Azure não tem origem por CIDR de IP; a origem do pedido é a sub-rede "
                 "(@Environment subnets): 'origem dentro da faixa' vira 'pedido vindo da sub-rede x_subnet_ok'")
    if v == "conforming":
        ctx = {"origin_subnet": sn_ok.address}
    elif v == "nonconforming":
        ctx = {"origin_subnet": sn_other.address}
    else:
        ctx = {}
        c.missing("c1", "condition_attribute", "EVIDENCE_GAP", "a condição usa atributo de segurança customizado do "
                  "Entra ID (posture_compliant) que o vocabulário não tem", a.address)
    c.probe = {"kind": "static", "inputs": {"access_request": _req(p.address, ct.address, ctx)}}
    return c.done("INTERPRETED")


# ============================================================================ caminho de rede


def _path(c: Ctx, v, rules, public=True, route_internet=True, rt_external=False, attach=True, separate=True):
    """Instância com interface, sub-rede, tabela de rotas e NSG; rules = [(lid, prioridade, acesso, porta, origem)]."""
    g = rg(c)
    vn = vnet(c, g)
    sn = subnet(c, g, vn, "sa", entity="sa")
    ip = None
    if public:
        ip = c.r("azurerm_public_ip", "ip1", {"name": c.name("ip1"), "resource_group_name": g.ref("name"),
                                              "location": g.ref("location"), "allocation_method": "Static",
                                              "sku": "Standard"}, entity="ip1")
    n = nic(c, g, "nic1", sn.ref("id"), public_ip_id=ip.ref("id") if ip else None)
    if not public:
        c.map("ip1", f"{n.address}#ip_configuration[primary].private_ip_address")
    vm(c, g, "vm1", [n.ref("id")])
    if rt_external:
        rid = c.symvar("route_table_id")
        c.map("rt1", f"external:var.{c.slug}_route_table_id: tabela de rotas fora da leitura")
        c.x("azurerm_subnet_route_table_association", "rt_assoc", {"subnet_id": sn.ref("id"), "route_table_id": rid},
            why="relação routes_via (sub-rede -> tabela de rotas)")
    else:
        rt = c.r("azurerm_route_table", "rt1", {"name": c.name("rt1"), "resource_group_name": g.ref("name"),
                                                "location": g.ref("location")}, entity="rt1")
        c.x("azurerm_subnet_route_table_association", "rt_assoc", {"subnet_id": sn.ref("id"), "route_table_id": rt.ref("id")},
            why="relação routes_via (sub-rede -> tabela de rotas)")
        if route_internet:
            c.r("azurerm_route", "rte1", {"name": c.name("rte1"), "resource_group_name": g.ref("name"),
                                          "route_table_name": rt.ref("name"), "address_prefix": "0.0.0.0/0",
                                          "next_hop_type": "Internet"}, entity="rte1")
            c.map("igw", "implicit:próximo salto Internet do Azure (sem recurso de gateway próprio)")
        else:
            c.x("azurerm_route", "drop", {"name": c.name("drop"), "resource_group_name": g.ref("name"),
                                          "route_table_name": rt.ref("name"), "address_prefix": "0.0.0.0/0",
                                          "next_hop_type": "None"},
                why="rota 0.0.0.0/0 -> None: anula a rota de sistema para a Internet (realiza 'sem rota pública')")
    sg = nsg(c, g, "rs1")
    for lid, pri, acc, port, src in rules:
        nsg_rule(c, g, sg, lid, pri, acc, port, src)
    nsg_assoc(c, n, sg)
    return g, sg


@R("CQ-NET-01")
def net_path(v, c: Ctx):
    rules = [("r1", 200, "Allow", 443 if v != "incomplete" else 22, DOC)]
    if v == "nonconforming":
        rules.append(("r2", 100, "Deny", 443, "0.0.0.0/0"))
    _path(c, v, rules)
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(source="203.0.113.10/32")}}
    if v == "incomplete":
        c.missing("rs1", "rules", "READ_MASK", "só a regra r1 do NSG foi lida; as demais regras do conjunto "
                  "(securityRules, fora deste slice) não foram lidas", f"azurerm_network_security_group.{c.lab('rs1')}")
    return c.done(cost_class="low")


@R("CQ-NET-02")
def net_return(v, c: Ctx):
    if v == "nonconforming":
        return na("regra sem estado não existe no NSG do Azure", EV_NSG_NO_STATE, AZ_NSG_STATEFUL)
    if v == "incomplete":
        return na("no NSG o estado de conexão é fixo do mecanismo (sempre com estado) e documentado: não há regra "
                  "com estado não declarado e padrão sem evidência", EV_NSG_NO_STATE, AZ_NSG_STATEFUL)
    g = rg(c)
    sg = nsg(c, g, "rs1")
    nsg_rule(c, g, sg, "r1", 200, "Allow", 443, DOC)
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(protocol=None)}}
    c.dev.append("o NSG avalia por precedência com permitir e negar (rs1.evaluation=allow_only na situação); o estado "
                 "da regra vem do mecanismo (sempre com estado), não de atributo; a resposta (o retorno é "
                 "permitido) se mantém")
    c.evidence.append(AZ_NSG_STATEFUL)
    return c.done("INTERPRETED")


@R("CQ-NET-03")
def net_reach(v, c: Ctx):
    if v == "conforming":
        _path(c, v, [("r1", 200, "Allow", 443, "0.0.0.0/0")])
    elif v == "nonconforming":
        _path(c, v, [("r1", 200, "Allow", 443, "0.0.0.0/0")], public=False, route_internet=False)
        c.dev.append("o NSG tem precedência com permitir e negar (rs1.evaluation=allow_only na situação); só há uma "
                     "regra de permitir, então a avaliação dá o mesmo")
    else:
        _path(c, v, [("r1", 200, "Allow", 443, "0.0.0.0/0")], rt_external=True)
        c.missing("rt1", "route_table", "EXTERNAL_REFERENCE", "a tabela de rotas da sub-rede vem de variável: rotas "
                  "não lidas", f"azurerm_subnet_route_table_association.{c.lab('x_rt_assoc')}")
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(source="198.51.100.20/32",
                                                         protocol="tcp" if v == "conforming" else None)}}
    return c.done(cost_class="low")


@R("CQ-NET-04")
def net_applies(v, c: Ctx):
    g = rg(c)
    _, sn = _net_base(c, g)
    sg = nsg(c, g, "rs1")
    n1 = nic(c, g, "nic1", sn.ref("id"))
    if v == "nonconforming":
        vm(c, g, "vm1", [n1.ref("id")])
        n3 = nic(c, g, "nic3", sn.ref("id"))
        vm(c, g, "vm2", [n3.ref("id")])
        nsg_assoc(c, n3, sg)
        return c.done(cost_class="low")
    n2 = nic(c, g, "nic2", sn.ref("id"))
    vm(c, g, "vm1", [n1.ref("id"), n2.ref("id")])
    if v == "conforming":
        nsg_assoc(c, n2, sg)
        return c.done(cost_class="low")
    nid = c.symvar("nic2_nsg_id")
    nsg_assoc(c, n2, sg, nsg_id=nid)
    c.missing("nic2", "attachment", "SYMBOLIC_INPUT", "o NSG associado a nic2 vem de variável sem valor",
              f"azurerm_network_interface_security_group_association.{c.lab('x_nsg_assoc')}")
    return c.done(cost_class="low")


# ============================================================================ configuração x observação


def _versioned(c: Ctx, g, value):
    blocks = [] if value is None else [Block("blob_properties", {"versioning_enabled": value})]
    acct = sa(c, "x_sa", g, blocks=blocks)
    ct = container(c, "c1", acct)
    return acct, ct


@R("CQ-CVO-01")
def cvo_drift(v, c: Ctx):
    g = rg(c)
    acct, ct = _versioned(c, g, True)
    c.map("d1", f"{acct.address}#blob_properties.versioning_enabled")
    c.dev.append("versionamento é configuração da conta (namespace) que vale para o contêiner c1")
    if v == "incomplete":
        c.missing("c1", "observation", "READ_MASK", "nenhuma leitura de volta (blobServices/default) foi feita",
                  acct.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done()
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": acct.address, "field": "blob_properties.versioning_enabled",
                  "value": v == "conforming"},
        "act": {"observed_at": "2026-11-02T10:00:00-03:00",
                "api": "Microsoft.Storage/storageAccounts/blobServices/read"}}}}
    if v == "nonconforming":
        return c.done(deployable=False, deploy_note="divergência exige mudança fora do Terraform; só offline com "
                                                    "observação gravada")
    return c.done()


@R("CQ-CVO-02")
def cvo_origin(v, c: Ctx):
    g = rg(c)
    if v == "incomplete":
        val = c.symvar("versioning", "bool")
        _versioned(c, g, val)
        c.missing("c1", "value", "SYMBOLIC_INPUT", "versioning_enabled vem de variável sem valor",
                  f"azurerm_storage_account.{c.lab('x_sa')}")
    else:
        _versioned(c, g, True if v == "conforming" else None)
    c.dev.append("o valor de versionamento do contêiner c1 é o da conta que o contém (blob_properties)")
    return c.done()


@R("CQ-CVO-03")
def cvo_alarm(v, c: Ctx):
    if v == "conforming":
        g = rg(c)
        s = pg(c, g, "i1")
        t = action_group(c, g)
        c.r("azurerm_monitor_metric_alert", "al1", {"name": c.name("al1"), "resource_group_name": g.ref("name"),
                                                     "scopes": [s.ref("id")]},
            [Block("criteria", {"metric_namespace": "Microsoft.DBforPostgreSQL/flexibleServers",
                                "metric_name": "cpu_percent", "aggregation": "Average", "operator": "GreaterThan",
                                "threshold": 80}),
             Block("action", {"action_group_id": t.ref("id")})], entity="al1")
        return c.done(cost_class="low")
    g = rg(c, "s1", entity="s1")
    pg(c, g, "i1")
    if v == "nonconforming":
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "Microsoft.Insights/metricAlerts/read",
                                                               "complete": True}}}
        return c.done(cost_class="low")
    c.missing("s1", "alarm", "READ_MASK", "os alertas do grupo de recursos não foram lidos (metricAlerts e "
              "activityLogAlerts fora da leitura)", g.address)
    return c.done(cost_class="low")


@R("CQ-CVO-04")
def cvo_secret(v, c: Ctx):
    g = rg(c)
    if v == "conforming":
        s = pg(c, g, "i1", password=Var("db_admin_password"))
        c.map("k1", f"{s.address}#administrator_password")
        return c.done(cost_class="low", deploy_note="senha gerada pelo runner, Withheld; state só com redator")
    if v == "nonconforming":
        s = pg(c, g, "i1")
        c.map("k1", f"absent:{s.address} usa só autenticação Entra ID (password_auth_enabled = false): sem senha")
        return c.done(cost_class="low")
    pw = c.symvar("admin_password")
    pw_decl = c.vars[-1]
    pw_decl.sensitive = True
    s = pg(c, g, "i1", password=pw)
    c.map("k1", f"{s.address}#administrator_password")
    c.missing("k1", "secret", "SYMBOLIC_INPUT", "a senha vem de variável sensível sem valor: não se sabe se está "
              "definida", s.address)
    return c.done(cost_class="low")


# ============================================================================ perda


def _target(**kw):
    return {"target": {"abstract": True, "from_spec": True, **kw}}


@R("CQ-LOSS-01")
def loss_saturate(v, c: Ctx):
    g = rg(c)
    days = 400 if v == "nonconforming" else 30
    c.r("azurerm_log_analytics_workspace", "s1", {"name": c.name("s1"), "resource_group_name": g.ref("name"),
                                                   "location": g.ref("location"), "sku": "PerGB2018",
                                                   "retention_in_days": days}, entity="s1")
    c.map("t1", "probe:target")
    if v == "conforming":
        c.probe = {"kind": "translation", "inputs": _target(retention_unit="second", domain_max="31536000_second")}
    elif v == "nonconforming":
        c.probe = {"kind": "translation", "inputs": _target(domain_max="365_day")}
    else:
        c.probe = {"kind": "translation", "inputs": _target(correspondence="exact", evidence_state="UNRESOLVED")}
        c.missing("s1", "correspondence", "EVIDENCE_GAP", "a correspondência s1 -> t1 não tem prova (UNRESOLVED)",
                  f"azurerm_log_analytics_workspace.{c.lab('s1')}")
        c.dev.append("o valor de origem (30 dias) existe; o que falta é a prova da correspondência")
    return c.done()


@R("CQ-LOSS-02")
def loss_deny(v, c: Ctx):
    g = rg(c)
    sg = nsg(c, g, "rs1")
    nsg_rule(c, g, sg, "r1", 100, "Deny", 22, "0.0.0.0/0")
    c.map("tgt", "probe:target")
    sup = {"conforming": True, "nonconforming": False, "incomplete": "unknown"}[v]
    c.probe = {"kind": "translation", "inputs": _target(supports_deny=sup)}
    if v == "incomplete":
        c.missing("tgt", "target_semantics", "EVIDENCE_GAP", "sem fato sobre se o destino exprime negação",
                  sg.address)
    return c.done()


@R("CQ-LOSS-03")
def loss_required(v, c: Ctx):
    g = rg(c)
    if v == "conforming":
        acct = sa(c, "x_sa", g, blocks=[Block("blob_properties", {"versioning_enabled": True})])
    elif v == "nonconforming":
        acct = sa(c, "x_sa", g)
    else:
        acct = sa(c, "x_sa", g, blocks=[Block("blob_properties", {"versioning_enabled": c.symvar("value", "bool")})])
        c.missing("s1", "value", "SYMBOLIC_INPUT", "versioning_enabled vem de variável sem valor", acct.address)
    c.map("s1", f"{acct.address}#blob_properties.versioning_enabled")
    c.map("t1", "probe:target")
    c.probe = {"kind": "translation", "inputs": _target(required=True)}
    return c.done()


@R("CQ-LOSS-04")
def loss_seconds(v, c: Ctx):
    g = rg(c)
    c.map("t1", "probe:target")
    c.probe = {"kind": "translation", "inputs": _target(retention_unit="second")}
    if v == "conforming":
        acct = sa(c, "x_sa", g, blocks=[Block("blob_properties", {}, [Block("delete_retention_policy", {"days": 7})])])
        c.map("s1", f"{acct.address}#blob_properties.delete_retention_policy.days")
        return c.done()
    if v == "nonconforming":
        s = sql_server(c, g, "x_sql", why="servidor lógico exigido pelo banco")
        db = sql_db(c, s, "x_db", blocks=[Block("long_term_retention_policy", {"monthly_retention": "P1M"})],
                    synth="banco cuja política de retenção longa é s1")
        c.emap["s1"] = f"{db.address}#long_term_retention_policy.monthly_retention"
        c.synth.pop(db.address, None)
        c.dev.append("retenção em meses (ISO-8601 P1M) só aparece na retenção longa do Azure SQL")
        return c.done(cost_class="low")
    acct = sa(c, "x_sa", g, blocks=[Block("blob_properties", {}, [Block("container_delete_retention_policy",
                                                                        {"days": 30})])])
    c.map("s1", f"{acct.address}#blob_properties.container_delete_retention_policy.days")
    c.missing("s1", "unit", "EVIDENCE_GAP", "a unidade do valor 30 ainda não foi determinada por IRI QUDT (UNITS); "
              "o nome do campo sugere dias, mas sugestão lexical não é evidência", acct.address)
    return c.done()


# ============================================================================ provedor novo

P4 = "implicit:provedor azurerm no papel de provedor retirado (P4)"


@R("CQ-NEW-01")
def new_concept(v, c: Ctx):
    g = rg(c)
    c.map("p4", P4)
    if v == "conforming":
        acct = sa(c, "x_sa", g, blocks=[Block("blob_properties", {"versioning_enabled": True})])
        c.map("s1", f"{acct.address}#blob_properties.versioning_enabled")
        c.map("k1", "probe:concept.k1")
        c.probe = {"kind": "static", "inputs": {"concept": {"k1": {"label": "versionamento de objetos",
                                                                    "exclusive": False}}}}
        return c.done("INTERPRETED")
    if v == "nonconforming":
        acct = sa(c, "x_sa", g, attrs={"allowed_copy_scope": "PrivateLink"})
        c.map("s2", f"{acct.address}#allowed_copy_scope")
        c.map("k2", "probe:concept.k2")
        c.probe = {"kind": "static", "inputs": {"concept": {"k2": {
            "label": "escopo permitido de cópia entre contas de armazenamento", "exclusive": True}}}}
        return c.done("INTERPRETED")
    acct = sa(c, "x_sa", g, attrs={"dns_endpoint_type": "Standard"})
    c.map("src3", f"{acct.address}#dns_endpoint_type")
    c.missing("src3", "concept", "EVIDENCE_GAP", "o conceito do atributo não foi determinado (GLOSSARY ainda não "
              "o ancorou; fica UNGLOSSED)", acct.address)
    return c.done("INTERPRETED")


@R("CQ-NEW-02")
def new_nics(v, c: Ctx):
    g = rg(c)
    c.map("p4", P4)
    _, sn = _net_base(c, g)
    if v == "nonconforming":
        n1 = nic(c, g, "nic1", sn.ref("id"), extra_ipconfs=[{}])
        vm(c, g, "vm1", [n1.ref("id")])
        c.map("ip2", f"{n1.address}#ip_configuration[secondary1]")
        return c.done(cost_class="low")
    n1 = nic(c, g, "nic1", sn.ref("id"))
    nic(c, g, "nic2", sn.ref("id"))
    if v == "conforming":
        vm(c, g, "vm1", [n1.ref("id"), Ref(f"azurerm_network_interface.{c.lab('nic2')}.id")])
        c.dev.append("no Azure a interface é recurso separado referenciado pela VM (declared_inline=true na "
                     "situação); a estrutura (três indivíduos, duas anexações) é a mesma")
        return c.done(cost_class="low")
    extra = c.symvar("extra_nic_ids", "list(string)")
    vm(c, g, "vm1", Ref(f"concat([{n1.address}.id], {extra.expr})"))
    c.missing("nic2", "attachment", "SYMBOLIC_INPUT", "as demais interfaces da VM vêm de variável sem valor",
              f"azurerm_linux_virtual_machine.{c.lab('vm1')}")
    return c.done(cost_class="low")


@R("CQ-NEW-03")
def new_precedence(v, c: Ctx):
    c.map("p4", P4)
    if v == "nonconforming":
        return na("no Azure toda regra de filtragem tem precedência numérica obrigatória: não há mecanismo de "
                  "primeira correspondência por posição textual",
                  schema_attr_present("azurerm", "azurerm_network_security_rule", "priority",
                                      "prioridade numérica obrigatória da regra do NSG"))
    g = rg(c)
    if v == "conforming":
        sg = nsg(c, g, "rs1")
        nsg_rule(c, g, sg, "r1", 100, "Deny", 22, "0.0.0.0/0")
        return c.done()
    nm = c.x("azurerm_network_manager", "nm", {"name": c.name("nm"), "resource_group_name": g.ref("name"),
                                               "location": g.ref("location"), "scope_accesses": ["SecurityAdmin"]},
             [Block("scope", {"subscription_ids": [SUB_SCOPE]})],
             why="gerenciador de rede que contém a configuração de regras administrativas")
    ng = c.x("azurerm_network_manager_network_group", "ng", {"name": c.name("ng"), "network_manager_id": nm.ref("id")},
             why="grupo de redes alvo da coleção de regras (exigido por network_group_ids)")
    cfg = c.x("azurerm_network_manager_security_admin_configuration", "cfg", {
        "name": c.name("cfg"), "network_manager_id": nm.ref("id")},
        why="configuração de segurança administrativa que contém a coleção")
    rs = c.r("azurerm_network_manager_admin_rule_collection", "rs1", {
        "name": c.name("rs1"), "security_admin_configuration_id": cfg.ref("id"), "network_group_ids": [ng.ref("id")]},
        entity="rs1")
    c.r("azurerm_network_manager_admin_rule", "r1", {
        "name": c.name("r1"), "admin_rule_collection_id": rs.ref("id"), "action": "Deny", "direction": "Inbound",
        "priority": 100, "protocol": "Tcp", "destination_port_ranges": ["22"]},
        [Block("source", {"address_prefix_type": "IPPrefix", "address_prefix": "0.0.0.0/0"}),
         Block("destination", {"address_prefix_type": "IPPrefix", "address_prefix": "*"})], entity="r1")
    c.missing("rs1", "precedence", "EVIDENCE_GAP", "a precedência de regra administrativa do Network Manager "
              "sobre as regras do NSG (Allow passa adiante, Deny e AlwaysAllow decidem) não tem fato de serviço "
              "registrado", rs.address)
    c.dev.append("regra administrativa tem prioridade própria, mas a combinação com o NSG é um segundo nível de "
                 "precedência cujo mecanismo não tem evidência")
    return c.done(deployable=False, deploy_note="Network Manager cobra por rede gerenciada: só offline, salvo OK",
                  cost_class="low")
