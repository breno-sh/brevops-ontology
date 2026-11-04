"""Realização das fixtures das CQs no provider oci 9.11.0 (registry.terraform.io/oracle/oci).

Escolhas gerais (cada desvio da situação abstrata vai em Fx.deviations):
- contêiner de objetos = oci_objectstorage_bucket; namespace de armazenamento = namespace do Object Storage da
  tenancy (implícito, lido pelo data oci_objectstorage_namespace; sem configuração própria de versionamento ou
  acesso público); o nome do bucket é único por namespace e região;
- conjunto de regras: oci_core_security_list (regras embutidas) ou oci_core_network_security_group (regras
  separadas, anexado à VNIC); os dois só permitem (não há regra de negação nem precedência) e o estado de
  conexão é POR REGRA (stateless); negação explícita só existe na política do Network Firewall
  (oci_network_firewall_network_firewall_policy_security_rule, ação DROP, ordem explícita);
- escopo de autorização = compartimento (hierárquico: política no pai vale para os filhos); a concessão é uma
  declaração textual de oci_identity_policy ("Allow group G to <verbo> <tipo> in compartment C"); a OCI não
  tem objeto de conjunto de permissões: o par verbo+tipo de recurso da declaração faz esse papel;
- interface: VNIC primária embutida na instância (create_vnic_details) e VNIC secundária por
  oci_core_vnic_attachment; a OCI não tem device_index (a ordem é primária x secundária);
- localização: região do bloco provider (location_1; alias oci.loc2 para location_2).
"""
from __future__ import annotations

from ..hcl import Block, Json, Ref, Tpl
from ..model import doc_citation, schema_attr_absent
from .base import Ctx, na, reg

PROVIDER = "oci"
VERSION = "9.11.0"
REALIZERS: dict = {}

CONTEXT_VARS = {
    "run_id": "identificador curto da execução (prefixo de nomes e tag bo_run); ligado pelo runner",
    "location_1": "localização l1 das fixtures (região); ligada pelo runner",
    "location_2": "localização l2, distinta de l1; ligada pelo runner",
    "tenancy_ocid": "tenancy sandbox (raiz: fontes de rede, domínio de identidade); ligado pelo runner, nunca gravado",
    "compartment_ocid": "compartimento da execução (todo recurso nasce nele ou abaixo dele); ligado pelo runner",
    "idcs_endpoint": "URL do domínio de identidade da tenancy sandbox; ligada pelo runner",
    "ssh_public_key": "chave pública SSH gerada pelo runner (só a pública; exigida pelo DB system)",
    "db_admin_password": "senha de administrador gerada na hora pelo runner; Withheld, nunca gravada",
}

DOC = "203.0.113.0/24"
MICRO = "VM.Standard.E2.1.Micro"
A1 = "VM.Standard.A1.Flex"
TCP = "6"
COMP = Ref("var.compartment_ocid")

ALLOWED_TYPES = {
    # rede (lote A: VCN, security list, NSG)
    "oci_core_vcn": {"category": "VCN", "cost_class": "free"},
    "oci_core_subnet": {"category": "VCN", "cost_class": "free"},
    "oci_core_internet_gateway": {"category": "VCN", "cost_class": "free"},
    "oci_core_route_table": {"category": "VCN", "cost_class": "free"},
    "oci_core_security_list": {"category": "security list", "cost_class": "free"},
    "oci_core_network_security_group": {"category": "NSG", "cost_class": "free"},
    "oci_core_network_security_group_security_rule": {"category": "NSG", "cost_class": "free"},
    "oci_core_vnic_attachment": {"category": "VCN (VNIC secundária)", "cost_class": "free"},
    "oci_core_private_ip": {"category": "VCN", "cost_class": "free"},
    "data.oci_core_vnic_attachments": {"category": "VCN (leitura)", "cost_class": "free"},
    "oci_network_firewall_network_firewall_policy": {
        "category": "política de firewall sem firewall implantado (objeto de configuração, sem custo por hora)",
        "cost_class": "free"},
    "oci_network_firewall_network_firewall_policy_security_rule": {"category": "política de firewall",
                                                                   "cost_class": "free"},
    "oci_network_firewall_network_firewall_policy_service": {"category": "política de firewall", "cost_class": "free"},
    "oci_network_firewall_network_firewall_policy_service_list": {"category": "política de firewall",
                                                                  "cost_class": "free"},
    # computação Always Free
    "oci_core_instance": {"category": "computação Always Free (E2.1.Micro ou A1.Flex 1 OCPU)", "cost_class": "free"},
    "data.oci_identity_availability_domains": {"category": "leitura de contexto", "cost_class": "free"},
    "data.oci_core_images": {"category": "leitura de imagem pública", "cost_class": "free"},
    # Object Storage
    "oci_objectstorage_bucket": {"category": "Object Storage", "cost_class": "free"},
    "oci_objectstorage_object_lifecycle_policy": {"category": "Object Storage", "cost_class": "free"},
    "data.oci_objectstorage_namespace": {"category": "Object Storage (leitura)", "cost_class": "free"},
    "data.oci_objectstorage_bucket": {"category": "Object Storage (leitura)", "cost_class": "free"},
    # IAM
    "oci_identity_user": {"category": "IAM", "cost_class": "free"},
    "oci_identity_group": {"category": "IAM", "cost_class": "free"},
    "oci_identity_user_group_membership": {"category": "IAM", "cost_class": "free"},
    "oci_identity_policy": {"category": "IAM", "cost_class": "free"},
    "oci_identity_compartment": {"category": "IAM (compartimento por execução)", "cost_class": "free"},
    "oci_identity_auth_token": {"category": "IAM", "cost_class": "free"},
    "oci_identity_network_source": {"category": "IAM", "cost_class": "free"},
    "oci_identity_domains_authentication_factor_setting": {
        "category": "IAM (configuração do domínio inteiro; só offline)", "cost_class": "free"},
    # Vault DEFAULT, Logging, Notifications, Events, Monitoring
    "oci_kms_vault": {"category": "Vault DEFAULT", "cost_class": "free"},
    "oci_kms_key": {"category": "Vault DEFAULT (chave de software)", "cost_class": "free"},
    "oci_logging_log_group": {"category": "Logging", "cost_class": "free"},
    "oci_logging_log": {"category": "Logging", "cost_class": "free"},
    "oci_ons_notification_topic": {"category": "Notifications", "cost_class": "free"},
    "oci_events_rule": {"category": "Notifications (Events)", "cost_class": "free"},
    "oci_monitoring_alarm": {"category": "Notifications (alarme)", "cost_class": "free"},
    # balanceador e banco
    "oci_load_balancer_load_balancer": {"category": "LB flexível 10 Mbps (Always Free)", "cost_class": "free"},
    "oci_load_balancer_backend_set": {"category": "LB flexível", "cost_class": "free"},
    "oci_load_balancer_backend": {"category": "LB flexível", "cost_class": "free"},
    "oci_load_balancer_listener": {"category": "LB flexível", "cost_class": "free"},
    "oci_load_balancer_load_balancer_routing_policy": {"category": "LB flexível", "cost_class": "free"},
    "oci_database_autonomous_database": {"category": "Autonomous DB Always Free (is_free_tier)", "cost_class": "free"},
    "oci_database_db_system": {"category": "DB system VM (pago; só offline, nunca no lote sem OK)",
                               "cost_class": "high"},
}

SKU_RULES = {
    ("oci_core_instance", "shape"): [MICRO, A1],
    ("oci_core_instance", "shape_config.ocpus"): [1],
    ("oci_core_instance", "shape_config.memory_in_gbs"): [6],
    ("oci_kms_vault", "vault_type"): ["DEFAULT"],
    ("oci_kms_key", "protection_mode"): ["SOFTWARE"],
    ("oci_load_balancer_load_balancer", "shape"): ["flexible"],
    ("oci_load_balancer_load_balancer", "shape_details.minimum_bandwidth_in_mbps"): [10],
    ("oci_load_balancer_load_balancer", "shape_details.maximum_bandwidth_in_mbps"): [10],
    ("oci_database_autonomous_database", "is_free_tier"): [True],
    ("oci_database_db_system", "shape"): ["VM.Standard.E4.Flex"],
    ("oci_database_db_system", "cpu_core_count"): [1],
    ("oci_database_db_system", "node_count"): [1],
}


def header() -> str:
    v = CONTEXT_VARS
    return f'''terraform {{
  required_version = "= 1.15.8"
  required_providers {{
    oci = {{
      source  = "oracle/oci"
      version = "= {VERSION}"
    }}
  }}
}}

provider "oci" {{
  region = var.location_1
}}

provider "oci" {{
  alias  = "loc2"
  region = var.location_2
}}

variable "run_id" {{
  type        = string
  description = "{v['run_id']}"
  validation {{
    condition     = can(regex("^[a-z][a-z0-9]{{2,11}}$", var.run_id))
    error_message = "run_id: 3 a 12 caracteres, minúsculas e dígitos."
  }}
}}

variable "location_1" {{
  type        = string
  description = "{v['location_1']}"
}}

variable "location_2" {{
  type        = string
  description = "{v['location_2']}"
}}

variable "tenancy_ocid" {{
  type        = string
  description = "{v['tenancy_ocid']}"
}}

variable "compartment_ocid" {{
  type        = string
  description = "{v['compartment_ocid']}"
}}

variable "idcs_endpoint" {{
  type        = string
  description = "{v['idcs_endpoint']}"
}}

variable "ssh_public_key" {{
  type        = string
  description = "{v['ssh_public_key']}"
}}

variable "db_admin_password" {{
  type        = string
  description = "{v['db_admin_password']}"
  sensitive   = true
}}
'''


R = lambda *q: reg(REALIZERS, *q)  # noqa: E731

# ----------------------------------------------------------------------------- ajudantes


def tags(c: Ctx) -> dict:
    return {"bo_run": Ref("var.run_id"), "bo_module": "CQFIX"}


def ns(c: Ctx, entity: str | None = None):
    return c.r("oci_objectstorage_namespace", "x_ns" if not entity else entity, {"compartment_id": COMP},
               kind="data", entity=entity,
               synth=None if entity else "namespace do Object Storage da tenancy (o bucket exige namespace)")


def bucket(c: Ctx, lid: str, n, key: str | None = None, entity: str | None = "", provider=None, **extra):
    a = {"compartment_id": COMP, "name": c.name(key or lid), "namespace": n.ref("namespace")}
    a.update(extra)
    a["freeform_tags"] = tags(c)
    ent = lid if entity == "" else entity
    return c.r("oci_objectstorage_bucket", lid, a, entity=ent,
               synth=None if ent else "contêiner auxiliar exigido pela situação", provider=provider)


def vcn(c: Ctx, lid: str = "x_vcn", cidr: str = "10.30.0.0/16", entity: str | None = None):
    return c.r("oci_core_vcn", lid, {"compartment_id": COMP, "cidr_blocks": [cidr],
                                     "display_name": c.name(lid), "freeform_tags": tags(c)},
               entity=entity, synth=None if entity else "rede exigida pelo schema (sub-rede precisa de vcn_id)")


def subnet(c: Ctx, lid: str, v, cidr: str, entity: str | None = None, **extra):
    a = {"compartment_id": COMP, "vcn_id": v.ref("id"), "cidr_block": cidr, "display_name": c.name(lid)}
    a.update(extra)
    return c.r("oci_core_subnet", lid, a, entity=entity,
               synth=None if entity else "sub-rede exigida pelo schema (VNIC precisa de subnet_id)")


def _ads(c: Ctx):
    if not any(x.label == c.lab("x_ads") for x in c.res):
        c.x("oci_identity_availability_domains", "ads", {"compartment_id": COMP}, kind="data",
            why="domínio de disponibilidade lido do contexto (instância exige availability_domain)")
    return Ref(f"data.oci_identity_availability_domains.{c.lab('x_ads')}.availability_domains[0].name")


def _image(c: Ctx, shape: str):
    role = "img_a1" if shape == A1 else "img"
    lab = c.lab(f"x_{role}")
    if not any(x.label == lab for x in c.res):
        c.x("oci_core_images", role, {"compartment_id": COMP, "operating_system": "Oracle Linux", "shape": shape,
                                      "sort_by": "TIMECREATED", "sort_order": "DESC"}, kind="data",
            why="imagem pública compatível com o shape (instância exige source_details)")
    return Ref(f"data.oci_core_images.{lab}.images[0].id")


def instance(c: Ctx, lid: str, sn, two_nics: bool = False, public_ip: bool = False, nsg_ids=None,
             subnet_id=None, entity: str | None = None):
    shape = A1 if two_nics else MICRO
    vnic = {"subnet_id": subnet_id if subnet_id is not None else sn.ref("id"),
            "assign_public_ip": "true" if public_ip else "false", "display_name": c.name(lid + "-vnic0")}
    if nsg_ids is not None:
        vnic["nsg_ids"] = nsg_ids
    blocks = [Block("create_vnic_details", vnic),
              Block("source_details", {"source_type": "image", "source_id": _image(c, shape)})]
    if two_nics:
        blocks.append(Block("shape_config", {"ocpus": 1, "memory_in_gbs": 6}))
    return c.r("oci_core_instance", lid, {"availability_domain": _ads(c), "compartment_id": COMP, "shape": shape,
                                          "display_name": c.name(lid), "freeform_tags": tags(c)}, blocks,
               entity=entity or lid)


def vnic2(c: Ctx, lid: str, inst, sn, nsg_ids=None, instance_id=None, entity: str | None = None):
    d = {"subnet_id": sn.ref("id"), "assign_public_ip": "false", "display_name": c.name(lid)}
    if nsg_ids is not None:
        d["nsg_ids"] = nsg_ids
    return c.r("oci_core_vnic_attachment", lid,
               {"instance_id": instance_id if instance_id is not None else inst.ref("id"),
                "display_name": c.name(lid + "-att")}, [Block("create_vnic_details", d)], entity=entity or lid)


def sl_rule(port, cidr, stateless=None, protocol=TCP) -> Block:
    a = {"protocol": protocol, "source": cidr, "source_type": "CIDR_BLOCK"}
    if stateless is not None:
        a["stateless"] = stateless
    return Block("ingress_security_rules", a, [Block("tcp_options", {"min": port, "max": port})])


def seclist(c: Ctx, lid: str, v, rules=(), entity: str | None = None):
    return c.r("oci_core_security_list", lid, {"compartment_id": COMP, "vcn_id": v.ref("id"),
                                               "display_name": c.name(lid)}, list(rules), entity=entity or lid)


def nsg(c: Ctx, lid: str, v, entity: str | None = None):
    return c.r("oci_core_network_security_group", lid, {"compartment_id": COMP, "vcn_id": v.ref("id"),
                                                        "display_name": c.name(lid)}, entity=entity or lid)


def nsg_rule(c: Ctx, lid: str, g, port, cidr, entity: str | None = None, stateless: bool = False):
    return c.r("oci_core_network_security_group_security_rule", lid,
               {"network_security_group_id": g.ref("id"), "direction": "INGRESS", "protocol": TCP,
                "source": cidr, "source_type": "CIDR_BLOCK", "stateless": stateless},
               [Block("tcp_options", {}, [Block("destination_port_range", {"min": port, "max": port})])],
               entity=entity or lid)


def group(c: Ctx, lid: str, entity: str | None = None):
    return c.r("oci_identity_group", lid, {"compartment_id": Ref("var.tenancy_ocid"), "name": c.name(lid),
                                           "description": Tpl("${var.run_id} " + c.fid)}, entity=entity or lid)


def user(c: Ctx, lid: str, entity: str | None = None):
    return c.r("oci_identity_user", lid, {"compartment_id": Ref("var.tenancy_ocid"), "name": c.name(lid),
                                          "description": Tpl("${var.run_id} " + c.fid)}, entity=entity or lid)


def compartment(c: Ctx, lid: str, parent, entity: str | None = None):
    return c.r("oci_identity_compartment", lid, {"compartment_id": parent, "name": c.name(lid),
                                                 "description": Tpl("${var.run_id} " + c.fid),
                                                 "enable_delete": True}, entity=entity or lid)


def policy(c: Ctx, lid: str, comp_id, statements, entity: str | None = "", synth: str | None = None):
    ent = lid if entity == "" else entity
    return c.r("oci_identity_policy", lid, {"compartment_id": comp_id, "name": c.name(lid),
                                            "description": Tpl("${var.run_id} " + c.fid),
                                            "statements": statements}, entity=ent, synth=synth)


def stmt(text: str) -> Tpl:
    return Tpl(text)


def gname(g) -> str:
    return "${" + g.address + ".name}"


def cname(cpt) -> str:
    return "${" + cpt.address + ".name}"


def cid(cpt) -> str:
    return "${" + cpt.address + ".id}"


def topic(c: Ctx, lid: str = "t1", entity: str | None = "t1"):
    return c.r("oci_ons_notification_topic", lid, {"compartment_id": COMP, "name": c.name(lid)}, entity=entity,
               synth=None if entity else "tópico de destino")


def adb(c: Ctx, lid: str, code: str, entity: str | None = None, **extra):
    a = {"compartment_id": COMP, "db_name": Tpl("${substr(var.run_id, 0, 8)}" + code), "display_name": c.name(lid),
         "is_free_tier": True, "db_workload": "OLTP", "freeform_tags": tags(c)}
    a.update(extra)
    return c.r("oci_database_autonomous_database", lid, a, entity=entity or lid)


def flow(direction="ingress", protocol="tcp", port=443, source="203.0.113.10/32") -> dict:
    d = {"direction": direction, "port": port, "source_cidr": source}
    if protocol:
        d["protocol"] = protocol
    return d


def request(principal: str, action: str, resource: str, context: dict | None = None) -> dict:
    return {"principal": principal, "action": action, "resource": resource, "context": context or {}}


def nfw_policy(c: Ctx, lid: str = "rs1", entity: str | None = "rs1"):
    return c.r("oci_network_firewall_network_firewall_policy", lid, {"compartment_id": COMP,
                                                                     "display_name": c.name(lid)}, entity=entity)


def nfw_service(c: Ctx, pol, port: int):
    s = c.x("oci_network_firewall_network_firewall_policy_service", f"svc{port}",
            {"network_firewall_policy_id": pol.ref("id"), "name": f"tcp{port}", "type": "TCP_SERVICE"},
            [Block("port_ranges", {"minimum_port": port, "maximum_port": port})],
            why=f"serviço tcp/{port} que a regra referencia (condição da regra exige lista de serviços)")
    return c.x("oci_network_firewall_network_firewall_policy_service_list", f"svcl{port}",
               {"network_firewall_policy_id": pol.ref("id"), "name": f"list{port}", "services": [s.ref("name")]},
               why=f"lista de serviços com tcp/{port}")


def nfw_rule(c: Ctx, lid: str, pol, svcl, action: str, priority: int | None = None, entity: str | None = "r1"):
    a = {"network_firewall_policy_id": pol.ref("id"), "name": lid, "action": action}
    if priority is not None:
        a["priority_order"] = priority
    return c.r("oci_network_firewall_network_firewall_policy_security_rule", lid, a,
               [Block("condition", {"service": [svcl.ref("name")]})], entity=entity)


OCI_ALLOW_ONLY_NSG = schema_attr_absent(
    "oci", "oci_core_network_security_group_security_rule", r"(action|effect|deny|priority|order)",
    "regra de NSG não tem efeito nem precedência: só permite (a decisão é a união das regras)")
OCI_ALLOW_ONLY_SL = schema_attr_absent(
    "oci", "oci_core_security_list", r"(action|effect|deny|priority|order)",
    "regra de security list não tem efeito nem precedência: só permite")
OCI_NS_NO_SETTING = schema_attr_absent(
    "oci", "oci_objectstorage_namespace_metadata", r"(versioning|public|access|retention|kms|encrypt|tier)",
    "o namespace do Object Storage só guarda compartimentos padrão de API; nenhuma configuração de "
    "armazenamento é declarada no namespace e herdada pelos buckets")
OCI_POLICY_ALLOW = doc_citation(
    "https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm",
    "a sintaxe de política da OCI concede com Allow (e Endorse/Admit entre tenancies); a fixture não usa "
    "declaração de negação explícita que vença uma concessão herdada")
OCI_ORDER = doc_citation(
    "https://docs.oracle.com/en-us/iaas/Content/network-firewall/policies.htm",
    "os mecanismos de filtragem da OCI são união de permissões (security list, NSG) ou lista ordenada explícita "
    "(regras da política do Network Firewall por posição/priority_order); não há primeira regra pela posição "
    "textual sem mecanismo de ordem")

# ============================================================================ CIS


@R("CQ-CIS-01")
def cis_mfa(v, c: Ctx):
    user(c, "u1")
    a = {"idcs_endpoint": Ref("var.idcs_endpoint"), "authentication_factor_setting_id": "AuthenticationFactorSettings",
         "schemas": ["urn:ietf:params:scim:schemas:oracle:idcs:AuthenticationFactorSettings"],
         "bypass_code_enabled": False, "push_enabled": False, "security_questions_enabled": False,
         "sms_enabled": False, "totp_enabled": True}
    if v == "incomplete":
        a["mfa_enrollment_type"] = c.symvar("mfa_enrollment_type")
        c.missing("d1", "value", "SYMBOLIC_INPUT", "mfa_enrollment_type do domínio vem de variável sem valor",
                  f"oci_identity_domains_authentication_factor_setting.{c.lab('d1')}")
    else:
        a["mfa_enrollment_type"] = "Required" if v == "conforming" else "Optional"
    blocks = [
        Block("bypass_code_settings", {"help_desk_code_expiry_in_mins": 60, "help_desk_generation_enabled": False,
                                       "help_desk_max_usage": 1, "length": 12, "max_active": 5,
                                       "self_service_generation_enabled": False}),
        Block("client_app_settings", {"device_protection_policy": "NONE", "initial_lockout_period_in_secs": 30,
                                      "key_pair_length": 2048, "lockout_escalation_pattern": "Constant",
                                      "max_failures_before_lockout": 10, "max_failures_before_warning": 5,
                                      "max_lockout_interval_in_secs": 86400, "min_pin_length": 6,
                                      "policy_update_freq_in_days": 4, "request_signing_algo": "SHA256withRSA",
                                      "shared_secret_encoding": "Base32", "unlock_app_for_each_request_enabled": False,
                                      "unlock_app_interval_in_secs": 300, "unlock_on_app_foreground_enabled": False,
                                      "unlock_on_app_start_enabled": False}),
        Block("compliance_policy", {"action": "Allow", "name": "lockScreenRequired", "value": "false"}),
        Block("endpoint_restrictions", {"max_endpoint_trust_duration_in_days": 180, "max_enrolled_devices": 10,
                                        "max_incorrect_attempts": 20, "max_trusted_endpoints": 20,
                                        "trusted_endpoints_enabled": True}),
        Block("notification_settings", {"pull_enabled": False}),
        Block("totp_settings", {"email_otp_validity_duration_in_mins": 10, "email_passcode_length": 6,
                                "hashing_algorithm": "SHA1", "jwt_validity_duration_in_secs": 300,
                                "key_refresh_interval_in_days": 60, "passcode_length": 6,
                                "sms_otp_validity_duration_in_mins": 10, "sms_passcode_length": 6,
                                "time_step_in_secs": 30, "time_step_tolerance": 3}),
    ]
    s = c.r("oci_identity_domains_authentication_factor_setting", "d1", a, blocks, entity="d1")
    c.synth[f"{s.address}#compliance_policy"] = ("bloco exigido pelo schema (ao menos 1); política neutra de "
                                                  "aplicativo cliente que não decide a exigência do segundo fator")
    c.synth[f"{s.address}#bypass_code_settings"] = ("blocos exigidos pelo schema do recurso de domínio; valores "
                                                     "neutros que não decidem a exigência do segundo fator")
    c.dev.append("a exigência de segundo fator da OCI é configuração do domínio de identidade "
                 "(mfa_enrollment_type), não do usuário: dono = domínio, alcance efetivo = todo usuário do "
                 "domínio, inclusive u1; CIS OCI 1.7 audita o fator do usuário de console")
    return c.done("INTERPRETED", deployable=False,
                  deploy_note="configuração única do domínio de identidade inteiro: mudar afeta toda a tenancy; "
                              "só offline")


@R("CQ-CIS-02")
def cis_key_age(v, c: Ctx):
    u = user(c, "p1")
    k = c.r("oci_identity_auth_token", "k1", {"user_id": u.ref("id"), "description": Tpl("${var.run_id} " + c.fid)},
            entity="k1")
    c.synth[f"{k.address}#token"] = "o token gerado é Withheld: nunca lido nem gravado"
    if v == "incomplete":
        c.missing("k1", "observation", "READ_MASK", "nenhuma leitura datada (ListAuthTokens, time_created) foi "
                  "feita; a idade não existe sem observação", k.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done(deploy_note="token de autenticação: segredo só com redator (SAFETY)")
    age = 10 if v == "conforming" else 120
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": k.address, "field": "time_created", "age_days": age},
        "act": {"observed_at": "2026-11-02T10:00:00-03:00", "api": "identity:ListAuthTokens"}}}}
    c.dev.append("CIS OCI 1.8–1.10 cobre chave de API, chave secreta de cliente e token; a fixture usa o token "
                 "de autenticação (oci_identity_auth_token), que não exige material de chave pública")
    if v == "nonconforming":
        return c.done(deployable=False,
                      deploy_note="idade de 120 dias não se produz num deploy novo: só offline com observação gravada")
    return c.done(deploy_note="token de autenticação: segredo só com redator (SAFETY)")


@R("CQ-CIS-03")
def cis_kms(v, c: Ctx):
    vault = c.x("oci_kms_vault", "vault", {"compartment_id": COMP, "display_name": c.name("vault"),
                                           "vault_type": "DEFAULT"},
                why="cofre DEFAULT que hospeda a chave (oci_kms_key exige management_endpoint)")
    a = {"compartment_id": COMP, "display_name": c.name("k1"), "management_endpoint": vault.ref("management_endpoint"),
         "protection_mode": "SOFTWARE"}
    blocks = [Block("key_shape", {"algorithm": "AES", "length": 32})]
    if v == "conforming":
        a["is_auto_rotation_enabled"] = True
        blocks.append(Block("auto_key_rotation_details", {"rotation_interval_in_days": 90}))
    elif v == "nonconforming":
        a["is_auto_rotation_enabled"] = False
    else:
        a["is_auto_rotation_enabled"] = c.symvar("rotation", "bool")
    k = c.r("oci_kms_key", "k1", a, blocks, entity="k1")
    c.map("d1", f"{k.address}#is_auto_rotation_enabled")
    if v == "incomplete":
        c.missing("d1", "value", "SYMBOLIC_INPUT", "is_auto_rotation_enabled vem de variável sem valor", k.address)
    note = ("cofre e chave entram em exclusão agendada (mín. 7 dias): resíduo esperado com prazo")
    if v == "conforming":
        return c.done(deploy_note=note + "; a rotação automática pode não ser aceita em cofre DEFAULT com chave "
                      "de software (conferir no SERVICE-EVIDENCE; REJECTED_BY_API é desfecho válido)")
    return c.done(deploy_note=note)


def _ports(v, c: Ctx, port: int):
    vc = vcn(c)
    if v == "incomplete":
        cidr = c.symvar("source_cidr")
        c.missing("r1", "value", "SYMBOLIC_INPUT", "source da regra embutida vem de variável sem valor",
                  f"oci_core_security_list.{c.lab('rs1')}")
    else:
        cidr = DOC if v == "conforming" else "0.0.0.0/0"
    sl = seclist(c, "rs1", vc, [sl_rule(port, cidr)])
    c.map("r1", f"{sl.address}#ingress_security_rules[0]")
    c.dev.append("a regra é bloco embutido (anônimo) da security list; CIS OCI 2.1/2.2 (security list) e "
                 "2.3/2.4 (NSG) têm a mesma situação")
    return c.done()


@R("CQ-CIS-04")
def cis_ssh(v, c):
    return _ports(v, c, 22)


@R("CQ-CIS-05")
def cis_rdp(v, c):
    return _ports(v, c, 3389)


@R("CQ-CIS-06")
def cis_flow(v, c: Ctx):
    vc = vcn(c, "vn1", entity="vn1")
    sn = subnet(c, "sa", vc, "10.30.1.0/24", entity="sa")
    if v == "nonconforming":
        c.map("s1", "implicit:compartimento da execução em location_1, leitura completa declarada dos logs de serviço")
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "logging:ListLogs (service flowlogs)",
                                                               "complete": True}}}
        return c.done()
    lg = c.x("oci_logging_log_group", "flowlogs", {"compartment_id": COMP, "display_name": c.name("flowlogs")},
             why="grupo de logs que recebe o registro de fluxo (oci_logging_log exige log_group_id)")
    a = {"display_name": c.name("d1"), "log_group_id": lg.ref("id"), "log_type": "SERVICE"}
    if v == "incomplete":
        a["is_enabled"] = c.symvar("flow_log_enabled", "bool")
        c.missing("d1", "value", "SYMBOLIC_INPUT", "is_enabled do log de fluxo vem de variável sem valor",
                  f"oci_logging_log.{c.lab('d1')}")
    else:
        a["is_enabled"] = True
    c.r("oci_logging_log", "d1", a, [Block("configuration", {"compartment_id": COMP}, [
        Block("source", {"category": "all", "resource": sn.ref("id"), "service": "flowlogs",
                         "source_type": "OCISERVICE"})])], entity="d1")
    return c.done()


_SL_EVENTS = ["com.oraclecloud.virtualnetwork.createsecuritylist", "com.oraclecloud.virtualnetwork.updatesecuritylist",
              "com.oraclecloud.virtualnetwork.deletesecuritylist",
              "com.oraclecloud.virtualnetwork.changesecuritylistcompartment"]
_RT_EVENTS = ["com.oraclecloud.virtualnetwork.createroutetable", "com.oraclecloud.virtualnetwork.updateroutetable",
              "com.oraclecloud.virtualnetwork.deleteroutetable",
              "com.oraclecloud.virtualnetwork.changeroutetablecompartment"]


@R("CQ-CIS-07")
def cis_alert(v, c: Ctx):
    c.map("s1", "implicit:compartimento da execução (as regras de evento valem para ele e os filhos)")
    t = topic(c)
    if v == "incomplete":
        cond = c.symvar("event_condition")
        c.missing("al1", "value", "SYMBOLIC_INPUT", "condition da regra de evento vem de variável sem valor",
                  f"oci_events_rule.{c.lab('al1')}")
    else:
        cond = Json({"eventType": _SL_EVENTS if v == "conforming" else _RT_EVENTS})
    c.r("oci_events_rule", "al1", {"compartment_id": COMP, "display_name": c.name("al1"), "is_enabled": True,
                                   "condition": cond},
        [Block("actions", {}, [Block("actions", {"action_type": "ONS", "is_enabled": True,
                                                 "topic_id": t.ref("id")})])], entity="al1")
    c.dev.append("a relação notifies é a ação ONS embutida na regra de evento (CIS OCI 4.10 é exatamente "
                 "regra de evento + tópico de notificação)")
    if v == "nonconforming":
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "events:ListRules", "complete": True}}}
    return c.done()


@R("CQ-CIS-08")
def cis_public(v, c: Ctx):
    n = ns(c)
    if v == "incomplete":
        at = c.symvar("access_type")
        c.missing("k1", "value", "SYMBOLIC_INPUT", "access_type do bucket vem de variável sem valor",
                  f"oci_objectstorage_bucket.{c.lab('c1')}")
    else:
        at = "NoPublicAccess" if v == "conforming" else "ObjectRead"
    b = bucket(c, "c1", n, access_type=at)
    c.map("k1", f"{b.address}#access_type")
    c.dev.append("a configuração de acesso público é atributo do próprio bucket (faceta: dono e alcance = c1)")
    return c.done()

# ============================================================================ identidade e ciclo de vida


@R("CQ-IDL-01")
def idl_01(v, c: Ctx):
    n = ns(c)
    if v == "conforming":
        b = bucket(c, "c1", n, key="data_a", versioning="Enabled")
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "versioning", "before": {"of": b.address, "versioning": "Disabled"}, "after": "main.tf",
            "plan_action_expected": "update"}}}
        return c.done()
    if v == "nonconforming":
        b = bucket(c, "c2", n, key="data_a", provider="oci.loc2")
        c.map("c1", "probe:change.before")
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "location",
            "before": {"of": b.address, "provider": "oci (var.location_1)", "name": "mesmo nome (data_a)"},
            "after": "main.tf", "plan_action_expected": "replace (delete + create)"}}}
        c.dev.append("a região do bucket vem do bloco provider: mudar de location_1 para location_2 apaga e cria")
        return c.done()
    b = bucket(c, "c1", n, key="data_a", storage_tier="Archive")
    c.probe = {"kind": "two_phase", "inputs": {"change": {
        "attribute": "storage_tier", "before": {"of": b.address, "storage_tier": "Standard"}, "after": "main.tf",
        "plan_action_expected": "UNKNOWN"}}}
    c.missing("c1", "mutability", "EVIDENCE_GAP", "o schema JSON do provider não expõe ForceNew e não há fato do "
              "SERVICE-EVIDENCE sobre storage_tier: não se sabe se a mudança é no lugar", b.address)
    return c.done()


@R("CQ-IDL-02")
def idl_02(v, c: Ctx):
    n = ns(c)
    c.map("acc", "implicit:tenancy sandbox (conta sintética), compartimento var.compartment_ocid")
    c.map("l1", "implicit:var.location_1")
    b1 = bucket(c, "c1", n, key="data")
    if v == "conforming":
        c.map("l2", "implicit:var.location_2")
        bucket(c, "c2", n, key="data", provider="oci.loc2")
        return c.done()
    if v == "nonconforming":
        c.r("oci_objectstorage_bucket", "c2", {"name": b1.ref("name"), "namespace": n.ref("namespace")},
            kind="data", entity="c2")
        c.dev.append("c2 é a segunda leitura do mesmo bucket (data source pelo mesmo nome, namespace e região)")
        return c.done()
    loc = c.symvar("c2_location", desc=f"região do contêiner c2 da fixture {c.fid}; não lida, sem valor de propósito")
    c.map("c2", f"external:{loc.expr}: contêiner com a chave local 'data' lido fora desta leitura; região não lida")
    c.missing("c2", "location", "SYMBOLIC_INPUT", "a região de c2 é variável sem valor; o provider da OCI fixa a "
              "região por bloco provider, e c2 não pertence a nenhum bloco lido")
    return c.done()


@R("CQ-IDL-03")
def idl_03(v, c: Ctx):
    if v == "conforming":
        g = group(c, "p1")
        c.map("ps1", "implicit:verbo+tipo 'read buckets' da declaração (a OCI não tem objeto de conjunto de permissões)")
        c.map("s1", "implicit:compartimento var.compartment_ocid")
        p = policy(c, "a1", COMP, [stmt(f"Allow group {gname(g)} to read buckets in compartment id ${{var.compartment_ocid}}")])
        c.probe = {"kind": "static", "inputs": {"removal": {"X": g.address, "Y": p.address}}}
        c.dev.append("a atribuição é a declaração da política (vínculo grupo x verbo+tipo x compartimento)")
        return c.done("INTERPRETED")
    if v == "nonconforming":
        n = ns(c, entity="ns1")
        b = bucket(c, "c1", n)
        c.probe = {"kind": "static", "inputs": {"removal": {"X": b.address, "Y": n.address}}}
        return c.done(deployable=False, deploy_note="o namespace do Object Storage é da tenancy e não se remove; "
                                                   "a remoção do pai só se avalia offline")
    n = ns(c)
    b = bucket(c, "c1", n)
    lp = c.r("oci_objectstorage_object_lifecycle_policy", "s1",
             {"bucket": b.ref("name"), "namespace": n.ref("namespace")},
             [Block("rules", {"action": "DELETE", "is_enabled": True, "name": "retention", "target": "objects",
                              "time_amount": "30", "time_unit": "DAYS"})], entity="s1")
    c.probe = {"kind": "static", "inputs": {"removal": {"X": lp.address, "Y": b.address}}}
    c.missing("s1", "lifecycle", "EVIDENCE_GAP", "não há fato do SERVICE-EVIDENCE sobre o controlador de ciclo de "
              "vida da política de ciclo de vida (recurso separado com identidade própria ou faceta do bucket)",
              lp.address)
    return c.done(deploy_note="a política de ciclo de vida exige permissão do serviço Object Storage na região "
                              "(declaração Allow service objectstorage-<região>)")


@R("CQ-IDL-04")
def idl_04(v, c: Ctx):
    vc = vcn(c)
    if v == "conforming":
        sl = seclist(c, "rs1", vc, [sl_rule(22, DOC), sl_rule(443, DOC)])
        c.map("r2", f"{sl.address}#ingress_security_rules[0]")
        c.map("r1", f"{sl.address}#ingress_security_rules[1]")
        before = {"of": sl.address, "order": ["r1 (tcp/443)", "r2 (tcp/22)"]}
        exp = "no-op na identidade (a ordem textual não é identidade)"
    elif v == "nonconforming":
        sl = seclist(c, "rs1", vc, [sl_rule(8443, DOC), sl_rule(22, DOC)])
        c.map("r1", f"{sl.address}#ingress_security_rules[0]")
        c.map("r2", f"{sl.address}#ingress_security_rules[1]")
        before = {"of": sl.address, "order": ["r1 (tcp/443)", "r2 (tcp/22)"]}
        exp = "update: r1 vira outra ocorrência (porta é campo de identidade)"
    else:
        port = c.symvar("r1_port", "number")
        sl = seclist(c, "rs1", vc, [sl_rule(port, DOC), sl_rule(22, DOC)])
        c.map("r1", f"{sl.address}#ingress_security_rules[0]")
        c.map("r2", f"{sl.address}#ingress_security_rules[1]")
        before = {"of": sl.address, "order": ["r1 (tcp/443)", "r2 (tcp/22)"]}
        exp = "UNKNOWN"
        c.missing("r1", "identity_fields", "SYMBOLIC_INPUT", "a porta de r1 (campo de identidade) vem de variável "
                  "sem valor", sl.address)
    c.probe = {"kind": "two_phase", "inputs": {"change": {"attribute": "ordem textual das regras embutidas",
                                                          "before": before, "after": "main.tf",
                                                          "plan_action_expected": exp}}}
    c.dev.append("as regras são blocos anônimos embutidos na security list; a origem 203.0.113.0/24 é sintetizada "
                 "(o schema exige source) e é igual nas duas leituras")
    return c.done()

# ============================================================================ composição


def _net(c: Ctx, vlid="x_vcn", slid="x_subnet", vent=None, sent=None, **subnet_extra):
    vc = vcn(c, vlid, entity=vent)
    sn = subnet(c, slid, vc, "10.30.1.0/24", entity=sent, **subnet_extra)
    return vc, sn


@R("CQ-CMP-01")
def cmp_01(v, c: Ctx):
    if v == "conforming":
        vc, sn = _net(c, "vn1", "sa", "vn1", "sa")
        vm = instance(c, "vm1", sn)
        c.map("nic1", f"{vm.address}#create_vnic_details")
        return c.done()
    if v == "nonconforming":
        vcn(c, "vn1", entity="vn1")
        vm = instance(c, "vm1", None, subnet_id="subnet-referenciada-ausente")
        c.map("nic1", f"{vm.address}#create_vnic_details")
        c.dev.append("a sub-rede referenciada é literal que não existe na leitura completa (nenhum recurso a define)")
        return c.done(deployable=False, deploy_note="o apply tem de ser recusado (sub-rede inexistente); "
                                                   "avaliação offline, o DEP decide se testa a recusa")
    sid = c.symvar("subnet_id", desc=f"sub-rede externa da fixture {c.fid}; fora da leitura, sem valor de propósito")
    vm = instance(c, "vm1", None, subnet_id=sid)
    c.map("nic1", f"{vm.address}#create_vnic_details")
    c.map("sa", f"external:{sid.expr}: sub-rede em escopo não lido")
    c.missing("sa", "scope", "EXTERNAL_REFERENCE", "subnet_id da VNIC aponta para sub-rede fora da leitura (variável); "
              "a cadeia acima dela não foi lida", vm.address)
    return c.done(deployable=False, deploy_note="a sub-rede externa não existe na sandbox: só offline")


@R("CQ-CMP-02")
def cmp_02(v, c: Ctx):
    vc, sn = _net(c)
    vm = instance(c, "vm1", sn, two_nics=v != "nonconforming")
    c.map("nic1", f"{vm.address}#create_vnic_details")
    if v == "conforming":
        att = vnic2(c, "nic2", vm, sn)
        c.map("nic2", f"{att.address}#create_vnic_details")
    elif v == "incomplete":
        iid = c.symvar("nic2_instance_id", desc=f"instância de anexação da VNIC nic2 da fixture {c.fid}; não lida")
        att = vnic2(c, "nic2", None, sn, instance_id=iid)
        c.map("nic2", f"{att.address}#create_vnic_details")
        c.missing("nic2", "attachment", "EXTERNAL_REFERENCE", "instance_id da anexação de nic2 é variável sem valor: "
                  "não se sabe a que instância a VNIC se anexa", att.address)
    c.dev.append("a OCI não tem device_index: nic1 = VNIC primária embutida, nic2 = VNIC secundária por "
                 "oci_core_vnic_attachment (que cria a VNIC e a anexa)")
    return c.done(deploy_note="duas VNICs exigem shape A1.Flex (Always Free, 1 OCPU); conferir limite de VNIC "
                              "do shape no SERVICE-EVIDENCE")


@R("CQ-CMP-03")
def cmp_03(v, c: Ctx):
    vc, sn = _net(c)
    lb = c.r("oci_load_balancer_load_balancer", "lb1",
             {"compartment_id": COMP, "display_name": c.name("lb1"), "shape": "flexible", "subnet_ids": [sn.ref("id")],
              "is_private": True, "freeform_tags": tags(c)},
             [Block("shape_details", {"minimum_bandwidth_in_mbps": 10, "maximum_bandwidth_in_mbps": 10})],
             entity="lb1")
    c.map("fe1", f"{lb.address}#ip_address_details")
    bs = c.r("oci_load_balancer_backend_set", "pool1", {"load_balancer_id": lb.ref("id"), "name": "pool1",
                                                        "policy": "ROUND_ROBIN"},
             [Block("health_checker", {"protocol": "HTTP", "port": 80, "url_path": "/", "return_code": 200})],
             entity="pool1")
    c.map("hp1", f"{bs.address}#health_checker")
    rp = c.r("oci_load_balancer_load_balancer_routing_policy", "ru1",
             {"load_balancer_id": lb.ref("id"), "name": "ru1", "condition_language_version": "V1"},
             [Block("rules", {"name": "any", "condition": "any(http.request.url.path sw '/')"},
                    [Block("actions", {"name": "FORWARD_TO_BACKENDSET", "backend_set_name": bs.ref("name")})])],
             entity="ru1")
    c.r("oci_load_balancer_listener", "li1", {"load_balancer_id": lb.ref("id"), "name": "li1", "port": 443,
                                              "protocol": "HTTP", "default_backend_set_name": bs.ref("name"),
                                              "routing_policy_name": rp.ref("name")}, entity="li1")
    c.dev.append("o frontend é o endereço do próprio balanceador (componente sem recurso próprio); o listener "
                 "escuta HTTP na porta 443 (a fixture não pede TLS); a regra 'any' casa todo caminho")
    if v == "conforming":
        vm = instance(c, "vm1", sn)
        c.x("oci_load_balancer_backend", "member", {"load_balancer_id": lb.ref("id"), "backendset_name": bs.ref("name"),
                                                    "ip_address": vm.ref("private_ip"), "port": 80},
            why="relação member_of_pool (vm1 -> pool1)")
    elif v == "incomplete":
        c.missing("pool1", "membership", "READ_MASK", "os backends do pool não foram lidos (ListBackends fora da "
                  "leitura); a configuração não declara membros, e pool lido sem membros não é pool vazio", bs.address)
    return c.done(deploy_note="LB flexível 10 Mbps (Always Free); privado")


@R("CQ-CMP-04")
def cmp_04(v, c: Ctx):
    if v != "nonconforming":
        return na("a OCI não tem configuração de armazenamento (versionamento) declarada no namespace e herdada "
                  "pelos buckets: o namespace só guarda compartimentos padrão de API", OCI_NS_NO_SETTING)
    n = ns(c, entity="ns1")
    bucket(c, "c1", n)
    b2 = bucket(c, "c2", n, versioning="Enabled")
    c.map("k1", f"{b2.address}#versioning")
    return c.done()


@R("CQ-CMP-05")
def cmp_05(v, c: Ctx):
    if v == "conforming":
        vc, sn = _net(c)
        ds = c.r("oci_database_db_system", "i1",
                 {"availability_domain": _ads(c), "compartment_id": COMP, "shape": "VM.Standard.E4.Flex",
                  "cpu_core_count": 1, "node_count": 1, "subnet_id": sn.ref("id"),
                  "ssh_public_keys": [Ref("var.ssh_public_key")], "hostname": Tpl("${var.run_id}cmp05"),
                  "database_edition": "STANDARD_EDITION", "data_storage_size_in_gb": 256,
                  "license_model": "LICENSE_INCLUDED", "display_name": c.name("i1")},
                 [Block("db_home", {"db_version": "19.0.0.0"}, [
                     Block("database", {"admin_password": Ref("var.db_admin_password"), "db_name": "cqfx5c"})])],
                 entity="i1")
        c.map("db1", f"{ds.address}#db_home.database")
        c.synth[f"{ds.address}#db_home.database.admin_password"] = "senha exigida pelo schema; Withheld (variável sensível de contexto)"
        c.dev.append("engine_b = Oracle Database; o banco lógico é o bloco database do db_home (componente)")
        return c.done(deployable=False, cost_class="high",
                      deploy_note="DB system VM é pago (fora do Always Free): só offline sem OK do Breno")
    if v == "nonconforming":
        d = adb(c, "srv1", "c05n")
        c.map("db1", f"{d.address}#db_name")
        c.dev.append("srv1 = Autonomous Database: o serviço não expõe instância (servidor lógico gerido); db1 = o "
                     "banco nomeado em db_name; ha_managed=false = sem Data Guard local")
        return c.done("INTERPRETED", deploy_note="Always Free permite 2 Autonomous DB por tenancy: implantar em lotes")
    d = adb(c, "srv2", "c05i", is_local_data_guard_enabled=True)
    c.map("db1", f"{d.address}#db_name")
    c.missing("srv2", "instance_count", "EVIDENCE_GAP", "com Data Guard local o serviço mantém standby que não "
              "aparece na configuração nem no schema; sem fato do SERVICE-EVIDENCE sobre o número de instâncias",
              d.address)
    c.dev.append("ha_managed=true = Data Guard local gerido pelo serviço (is_local_data_guard_enabled)")
    return c.done("INTERPRETED", deployable=False,
                  deploy_note="Data Guard local não existe no Always Free: só offline")

# ============================================================================ autorização


@R("CQ-AUT-01")
def aut_01(v, c: Ctx):
    if v == "nonconforming":
        return na("a fixture exige negação explícita no escopo filho que vença a concessão herdada; a política da "
                  "OCI concede com Allow e não há declaração de negação no vocabulário de política usado",
                  OCI_POLICY_ALLOW)
    n = ns(c)
    p = group(c, "p1")
    c.map("s_parent", "implicit:compartimento var.compartment_ocid (pai)")
    child = compartment(c, "s_child", COMP)
    b = bucket(c, "r1", n, compartment_id=child.ref("id"))
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": request(p.address, "read", b.address)}}
    if v == "incomplete":
        c.missing("s_parent", "scope", "READ_MASK", "as políticas do compartimento pai (e acima) não foram lidas; "
                  "a herança descendente pode conceder")
        return c.done("INTERPRETED")
    c.map("ps1", "implicit:verbo+tipo 'read objects' da declaração")
    c.map("perm1", "implicit:permissão OBJECT_READ coberta pelo verbo read sobre objects")
    policy(c, "a1", COMP, [stmt(f"Allow group {gname(p)} to read objects in compartment id ${{var.compartment_ocid}}")])
    c.dev.append("a política fica no pai e vale para o compartimento filho, onde está r1 (herança descendente)")
    return c.done("INTERPRETED")


@R("CQ-AUT-02")
def aut_02(v, c: Ctx):
    c.map("s1", "implicit:compartimento var.compartment_ocid")
    g = group(c, "p1")
    c.map("ps1", "implicit:verbo+tipo 'read buckets' das declarações")
    s_read = f"Allow group {gname(g)} to read buckets in compartment id ${{var.compartment_ocid}}"
    if v == "nonconforming":
        c.map("ps2", "implicit:verbo+tipo 'manage objects' (outro conjunto)")
        policy(c, "a1", COMP, [stmt(s_read)])
        policy(c, "a2", COMP, [stmt(f"Allow group {gname(g)} to manage objects in compartment id "
                                    "${var.compartment_ocid}")])
        return c.done("INTERPRETED")
    policy(c, "a1", COMP, [stmt(s_read)])
    if v == "conforming":
        doc = policy(c, "doc1", COMP, [stmt(s_read),
                                       stmt("Allow group " + gname(g) + " to inspect compartments in compartment id "
                                            "${var.compartment_ocid}")])
    else:
        gv = c.symvar("a2_group", desc=f"grupo da declaração a2 da fixture {c.fid}; não resolvido")
        doc = policy(c, "doc1", COMP, [stmt("Allow group ${" + gv.expr + "} to read buckets in compartment id "
                                            "${var.compartment_ocid}"),
                                       stmt("Allow group " + gname(g) + " to inspect compartments in compartment id "
                                            "${var.compartment_ocid}")])
        c.missing("a2", "reference", "SYMBOLIC_INPUT", "o grupo da declaração a2 vem de variável sem valor",
                  doc.address)
    c.map("a2", f"{doc.address}#statements[0]")
    c.dev.append("a OCI só tem a forma documento: a1 é a declaração única da política a1 e a2 a mesma declaração "
                 "dentro do documento doc1 com outras declarações (a forma 'member' vira política de uma declaração)")
    return c.done("INTERPRETED")


@R("CQ-AUT-03")
def aut_03(v, c: Ctx):
    n = ns(c)
    p = group(c, "p1")
    c.map("ps1", "implicit:verbo+tipo 'read objects' da declaração")
    c.map("perm1", "implicit:permissão OBJECT_READ coberta pelo verbo read sobre objects")
    c.map("s_parent", "implicit:compartimento var.compartment_ocid (pai)")
    b = bucket(c, "r2", n)
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": request(p.address, "read", b.address)}}
    if v == "incomplete":
        cv = c.symvar("s_child_id", desc=f"compartimento s_child da fixture {c.fid}; hierarquia não lida")
        c.map("s_child", f"external:{cv.expr}: compartimento cuja posição na hierarquia não foi lida")
        policy(c, "a1", COMP, [stmt("Allow group " + gname(p) + " to read objects in compartment id ${" + cv.expr + "}")])
        c.missing("s_child", "scope", "SYMBOLIC_INPUT", "o compartimento da atribuição é variável sem valor: não se "
                  "sabe se contém ou é contido pelo compartimento de r2")
        return c.done("INTERPRETED")
    child = compartment(c, "s_child", COMP)
    if v == "conforming":
        policy(c, "a1", child.ref("id"), [stmt("Allow group " + gname(p) + " to read objects in compartment id "
                                               + cid(child))])
    else:
        policy(c, "a1", COMP, [stmt("Allow group " + gname(p) + " to read objects in compartment id "
                                    "${var.compartment_ocid}")])
    return c.done("INTERPRETED")


@R("CQ-AUT-04")
def aut_04(v, c: Ctx):
    c.map("ps1", "implicit:verbo+tipo 'read buckets' da declaração")
    c.map("s1", "implicit:compartimento var.compartment_ocid")
    if v == "incomplete":
        gv = c.symvar("g1_name", desc=f"grupo do IdP federado da fixture {c.fid}; fora do pin")
        c.map("dir1", "external:IdP federado ao domínio de identidade (fora dos providers fixados)")
        c.map("g1", f"external:{gv.expr}: grupo mantido no IdP federado")
        c.map("u1", "external:usuário mantido no IdP federado (pertença não legível pelo pin)")
        policy(c, "a1", COMP, [stmt("Allow group ${" + gv.expr + "} to read buckets in compartment id "
                                    "${var.compartment_ocid}")])
        c.missing("u1", "group_membership", "EXTERNAL_REFERENCE", "a pertença de u1 ao grupo vive no IdP externo, "
                  "fora dos providers fixados (OUT_OF_PIN)")
        return c.done("INTERPRETED", deployable=False, deploy_note="exige IdP federado externo: só offline")
    g = group(c, "g1")
    u = user(c, "u1")
    if v == "conforming":
        c.x("oci_identity_user_group_membership", "member", {"group_id": g.ref("id"), "user_id": u.ref("id")},
            why="relação member_of_group (u1 -> g1)")
    policy(c, "a1", COMP, [stmt(f"Allow group {gname(g)} to read buckets in compartment id ${{var.compartment_ocid}}")])
    return c.done()


@R("CQ-AUT-05")
def aut_05(v, c: Ctx):
    n = ns(c)
    p = group(c, "p1")
    c.map("ps1", "implicit:verbo+tipo 'read objects' da declaração")
    c.map("perm1", "implicit:permissão OBJECT_READ coberta pelo verbo read sobre objects")
    c.map("s1", "implicit:compartimento var.compartment_ocid")
    b = bucket(c, "r1", n)
    base = f"Allow group {gname(p)} to read objects in compartment id ${{var.compartment_ocid}}"
    if v == "incomplete":
        a = policy(c, "a1", COMP, [stmt(base + " where request.principal.group.tag.posture.state = 'compliant'")])
        c.map("c1", f"{a.address}#statements[0].where")
        c.missing("c1", "condition_attribute", "EVIDENCE_GAP", "a condição usa atributo de contexto (postura do "
                  "dispositivo por tag) que o vocabulário não modela: a avaliação é indeterminada", a.address)
        c.map("q1", "probe:access_request")
        c.probe = {"kind": "static", "inputs": {"access_request": request(p.address, "read", b.address)}}
        return c.done("INTERPRETED")
    src = c.r("oci_identity_network_source", "c1",
              {"compartment_id": Ref("var.tenancy_ocid"), "name": c.name("c1"),
               "description": Tpl("${var.run_id} " + c.fid), "public_source_list": ["198.51.100.0/24"]},
              entity="c1")
    policy(c, "a1", COMP, [stmt(base + " where request.networkSource.name = '" + "${" + src.address + ".name}'")])
    origin = "198.51.100.7" if v == "conforming" else "203.0.113.9"
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": request(p.address, "read", b.address,
                                                                      {"origin": origin})}}
    c.dev.append("a condição é a fonte de rede (oci_identity_network_source) citada na cláusula where")
    return c.done("INTERPRETED")

# ============================================================================ caminho de rede


def _public_net(c: Ctx, with_route: bool = True, rt_external=None):
    vc = vcn(c)
    igw = None
    if with_route:
        igw = c.r("oci_core_internet_gateway", "igw", {"compartment_id": COMP, "vcn_id": vc.ref("id"),
                                                       "display_name": c.name("igw"), "enabled": True}, entity="igw")
        rt = c.r("oci_core_route_table", "rt1", {"compartment_id": COMP, "vcn_id": vc.ref("id"),
                                                 "display_name": c.name("rt1")},
                 [Block("route_rules", {"destination": "0.0.0.0/0", "destination_type": "CIDR_BLOCK",
                                        "network_entity_id": igw.ref("id")})], entity="rt1")
        c.map("rte1", f"{rt.address}#route_rules[0]")
        rt_id = rt.ref("id")
    elif rt_external is not None:
        rt_id = rt_external
    else:
        rt = c.r("oci_core_route_table", "rt1", {"compartment_id": COMP, "vcn_id": vc.ref("id"),
                                                 "display_name": c.name("rt1")}, entity="rt1")
        rt_id = rt.ref("id")
    extra = {"route_table_id": rt_id, "prohibit_public_ip_on_vnic": not with_route and rt_external is None}
    sn = subnet(c, "sa", vc, "10.30.1.0/24", entity="sa", **extra)
    return vc, sn


@R("CQ-NET-01")
def net_01(v, c: Ctx):
    if v == "nonconforming":
        return na("a fixture exige regra de negação de maior precedência no conjunto anexado à interface; NSG e "
                  "security list da OCI só permitem, sem efeito nem precedência", OCI_ALLOW_ONLY_NSG,
                  OCI_ALLOW_ONLY_SL)
    vc, sn = _public_net(c)
    g = nsg(c, "rs1", vc)
    vm = instance(c, "vm1", sn, public_ip=True, nsg_ids=[g.ref("id")])
    c.map("nic1", f"{vm.address}#create_vnic_details")
    c.map("ip1", f"{vm.address}#create_vnic_details.assign_public_ip")
    port = 443 if v == "conforming" else 22
    nsg_rule(c, "r1", g, port, DOC)
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow()}}
    c.dev.append("rs1 é NSG anexado à VNIC: só permite e cada regra declara o estado (stateless=false); a "
                 "fixture diz avaliação priority_allow_deny com estado, o que na OCI vira só-permitir com estado — "
                 "sem regra de negação a resposta não muda")
    if v == "incomplete":
        c.missing("rs1", "rules", "READ_MASK", "o NSG pode ter regras criadas fora desta configuração; só r1 (tcp/22) "
                  "foi lida (ListNetworkSecurityGroupSecurityRules fora da leitura)", g.address)
    return c.done(deploy_note="instância Always Free com IP público efêmero")


@R("CQ-NET-02")
def net_02(v, c: Ctx):
    vc = vcn(c)
    st = {"conforming": False, "nonconforming": True, "incomplete": None}[v]
    sl = seclist(c, "rs1", vc, [sl_rule(443, DOC, stateless=st)])
    c.map("r1", f"{sl.address}#ingress_security_rules[0]")
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(protocol=None)}}
    c.dev.append("o estado de conexão é atributo por regra (stateless) na security list, que só permite; nenhuma "
                 "regra de saída é declarada")
    if v == "incomplete":
        c.missing("r1", "state_tracking", "EVIDENCE_GAP", "stateless omitido: o padrão do provedor não tem fato no "
                  "SERVICE-EVIDENCE, e o estado não é assumido", sl.address)
    return c.done()


@R("CQ-NET-03")
def net_03(v, c: Ctx):
    if v == "conforming":
        vc, sn = _public_net(c)
    elif v == "nonconforming":
        vc, sn = _public_net(c, with_route=False)
    else:
        rv = c.symvar("rt1_id", desc=f"tabela de rotas da fixture {c.fid}; não lida")
        vc, sn = _public_net(c, with_route=False, rt_external=rv)
        c.map("rt1", f"external:{rv.expr}: tabela de rotas fora da leitura")
        c.missing("rt1", "route_table", "EXTERNAL_REFERENCE", "route_table_id da sub-rede é variável sem valor: as "
                  "rotas não foram lidas", sn.address)
    g = nsg(c, "rs1", vc)
    vm = instance(c, "vm1", sn, public_ip=v != "nonconforming", nsg_ids=[g.ref("id")])
    c.map("nic1", f"{vm.address}#create_vnic_details")
    c.map("ip1", f"{vm.address}#create_vnic_details.assign_public_ip")
    nsg_rule(c, "r1", g, 443, "0.0.0.0/0")
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(source="198.51.100.20/32",
                                                         protocol="tcp" if v == "conforming" else None)}}
    c.dev.append("rs1 é NSG só-permitir com estado; em C a fixture diz priority_allow_deny, sem regra de negação "
                 "a resposta não muda")
    if v == "nonconforming":
        c.dev.append("sem rota para gateway de internet e com prohibit_public_ip_on_vnic: ip1 é só privado")
    return c.done(deploy_note="instância Always Free")


@R("CQ-NET-04")
def net_04(v, c: Ctx):
    vc, sn = _net(c)
    g = nsg(c, "rs1", vc)
    if v == "nonconforming":
        vm1 = instance(c, "vm1", sn)
        vm2 = instance(c, "vm2", sn, nsg_ids=[g.ref("id")])
        c.map("nic1", f"{vm1.address}#create_vnic_details")
        c.map("nic3", f"{vm2.address}#create_vnic_details")
        return c.done()
    vm = instance(c, "vm1", sn, two_nics=True)
    c.map("nic1", f"{vm.address}#create_vnic_details")
    if v == "conforming":
        att = vnic2(c, "nic2", vm, sn, nsg_ids=[g.ref("id")])
    else:
        lv = c.symvar("nic2_nsg_ids", "list(string)", f"NSGs da VNIC nic2 da fixture {c.fid}; não lidos")
        att = vnic2(c, "nic2", vm, sn, nsg_ids=lv)
        c.missing("nic2", "attachment", "SYMBOLIC_INPUT", "os NSGs anexados à VNIC nic2 vêm de variável sem valor",
                  att.address)
    c.map("nic2", f"{att.address}#create_vnic_details")
    return c.done(deploy_note="duas VNICs exigem shape A1.Flex (Always Free, 1 OCPU)")

# ============================================================================ configuração x observação


@R("CQ-CVO-01")
def cvo_01(v, c: Ctx):
    n = ns(c)
    b = bucket(c, "c1", n, versioning="Enabled")
    c.map("d1", f"{b.address}#versioning")
    if v == "incomplete":
        c.missing("c1", "observation", "READ_MASK", "nenhuma leitura de volta (GetBucket) foi feita: não há estado "
                  "observado", b.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done()
    obs = "Enabled" if v == "conforming" else "Disabled"
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": b.address, "field": "versioning", "value": obs},
        "act": {"observed_at": "2026-11-02T10:00:00-03:00", "api": "objectstorage:GetBucket"}}}}
    if v == "nonconforming":
        return c.done(deployable=False, deploy_note="a divergência exige mudança fora do Terraform: só offline com "
                                                    "observação gravada")
    return c.done()


@R("CQ-CVO-02")
def cvo_02(v, c: Ctx):
    n = ns(c)
    if v == "conforming":
        b = bucket(c, "c1", n, versioning="Enabled")
    elif v == "nonconforming":
        b = bucket(c, "c1", n)
        c.dev.append("versioning omitido: o valor disabled vem do padrão do provedor")
    else:
        b = bucket(c, "c1", n, versioning=c.symvar("versioning"))
        c.missing("c1", "value", "SYMBOLIC_INPUT", "versioning vem de variável sem valor", b.address)
    return c.done()


@R("CQ-CVO-03")
def cvo_03(v, c: Ctx):
    d = adb(c, "i1", "cvo3" + {"conforming": "c", "nonconforming": "n", "incomplete": "i"}[v])
    c.dev.append("i1 (instância de banco) é Autonomous DB Always Free; a pergunta é sobre alarme, não sobre o tipo")
    if v == "conforming":
        t = topic(c)
        q = ('CpuUtilization[1m]{resourceId = \\"${' + d.address + '.id}\\"}.mean() > 80')
        c.r("oci_monitoring_alarm", "al1", {"compartment_id": COMP, "destinations": [t.ref("id")],
                                            "display_name": c.name("al1"), "is_enabled": True,
                                            "metric_compartment_id": COMP, "namespace": "oci_autonomous_database",
                                            "query": Tpl(q), "severity": "CRITICAL"}, entity="al1")
        return c.done(deploy_note="Always Free permite 2 Autonomous DB por tenancy: implantar em lotes")
    c.map("s1", "implicit:compartimento da execução (alarmes de monitoramento)")
    if v == "nonconforming":
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "monitoring:ListAlarms", "complete": True}}}
    else:
        c.missing("s1", "alarm", "READ_MASK", "os alarmes do compartimento não foram lidos (ListAlarms fora da "
                  "leitura)")
    return c.done(deploy_note="Always Free permite 2 Autonomous DB por tenancy: implantar em lotes")


@R("CQ-CVO-04")
def cvo_04(v, c: Ctx):
    code = "cvo4" + {"conforming": "c", "nonconforming": "n", "incomplete": "i"}[v]
    if v == "conforming":
        d = adb(c, "i1", code, admin_password=Ref("var.db_admin_password"))
        c.map("k1", f"{d.address}#admin_password")
    elif v == "nonconforming":
        d = adb(c, "i1", code)
        c.map("k1", f"{d.address}#admin_password")
        c.dev.append("admin_password omitido sob leitura completa: o segredo não foi definido")
    else:
        pv = c.symvar("admin_password", desc=f"senha da fixture {c.fid}; não lida")
        c.vars[-1].sensitive = True
        d = adb(c, "i1", code, admin_password=pv)
        c.map("k1", f"{d.address}#admin_password")
        c.missing("k1", "secret", "SYMBOLIC_INPUT", "admin_password vem de variável sensível sem valor (pode ser "
                  "nula): presença não lida", d.address)
    c.dev.append("i1 é Autonomous DB Always Free; o valor do segredo nunca é lido nem gravado")
    return c.done(deploy_note="Always Free permite 2 Autonomous DB por tenancy; segredo só com redator (SAFETY)")

# ============================================================================ perda


def _target(c: Ctx, target: dict):
    c.map("t1" if "t1" in [e["id"] for e in c.fixture["entities"]] else "tgt", "probe:target")
    c.probe = {"kind": "translation", "inputs": {"target": target}}


def _retention_bucket(c: Ctx, lid: str, amount, unit: str):
    n = ns(c)
    return bucket(c, lid, n, retention_rules=None) if amount is None else c.r(
        "oci_objectstorage_bucket", lid,
        {"compartment_id": COMP, "name": c.name(lid), "namespace": n.ref("namespace"), "freeform_tags": tags(c)},
        [Block("retention_rules", {"display_name": "retention"},
               [Block("duration", {"time_amount": str(amount), "time_unit": unit})])], entity=lid)


@R("CQ-LOSS-01")
def loss_01(v, c: Ctx):
    days = {"conforming": 30, "nonconforming": 400, "incomplete": 30}[v]
    b = _retention_bucket(c, "s1", days, "DAYS")
    c.dev.append("s1 = regra de retenção do bucket (time_amount em dias); a retenção de log da OCI só aceita 30 a "
                 "180 dias e não exprime 400")
    tgt = {"conforming": {"retention_unit": "second", "domain_max": "31536000_second"},
           "nonconforming": {"domain_max": "365_day"},
           "incomplete": {"note": "destino da especificação; a correspondência não tem prova"}}[v]
    tgt.update({"semantic_relation": "exact",
                "evidence_state": "UNRESOLVED" if v == "incomplete" else "DOC_SUPPORTED"})
    _target(c, tgt)
    if v == "incomplete":
        c.dev.append("o valor de origem existe (30 dias); o que falta é a prova da correspondência")
        c.missing("s1", "correspondence", "EVIDENCE_GAP", "a correspondência s1 -> t1 está UNRESOLVED (sem prova); "
                  "não há transporte sem prova", b.address)
    return c.done(deploy_note="regra de retenção destravada (time_rule_locked ausente); bucket vazio é apagável")


@R("CQ-LOSS-02")
def loss_02(v, c: Ctx):
    pol = nfw_policy(c)
    sl = nfw_service(c, pol, 22)
    nfw_rule(c, "r1", pol, sl, "DROP")
    c.dev.append("a negação explícita da OCI só existe na política do Network Firewall (ação DROP); a direção "
                 "ingress da fixture é a do tráfego que atravessa o firewall")
    sup = {"conforming": True, "nonconforming": False, "incomplete": "unknown"}[v]
    _target(c, {"supports_deny": sup})
    if v == "incomplete":
        c.missing("tgt", "target_semantics", "EVIDENCE_GAP", "não há fato do SERVICE-EVIDENCE sobre a semântica de "
                  "negação do destino")
    return c.done("INTERPRETED", deploy_note="política de firewall sem firewall implantado (sem custo por hora)")


@R("CQ-LOSS-03")
def loss_03(v, c: Ctx):
    n = ns(c)
    if v == "conforming":
        bucket(c, "s1", n, versioning="Enabled")
    elif v == "nonconforming":
        bucket(c, "s1", n)
        c.dev.append("s1 sem versioning declarado: a origem não tem o valor")
    else:
        b = bucket(c, "s1", n, versioning=c.symvar("versioning"))
        c.missing("s1", "value", "SYMBOLIC_INPUT", "versioning de origem vem de variável sem valor", b.address)
    _target(c, {"required": True, "attribute": "versionamento no destino"})
    return c.done()


@R("CQ-LOSS-04")
def loss_04(v, c: Ctx):
    if v == "incomplete":
        lg = c.x("oci_logging_log_group", "lg", {"compartment_id": COMP, "display_name": c.name("lg")},
                 why="grupo exigido pelo log")
        lg_log = c.r("oci_logging_log", "s1", {"display_name": c.name("s1"), "log_group_id": lg.ref("id"),
                                               "log_type": "CUSTOM", "retention_duration": 30}, entity="s1")
        c.missing("s1", "unit", "EVIDENCE_GAP", "retention_duration não traz unidade no nome nem no schema, e o UNITS "
                  "ainda não determinou a unidade: 30 sozinho não converte", lg_log.address)
    elif v == "conforming":
        _retention_bucket(c, "s1", 7, "DAYS")
    else:
        _retention_bucket(c, "s1", 1, "YEARS")
        c.dev.append("a regra de retenção da OCI só tem DAYS e YEARS: o mês da fixture vira 1 ano, que também não é "
                     "número fixo de segundos (ano bissexto): a resposta continua a mesma")
    _target(c, {"retention_unit": "second", **({"required": False} if v == "nonconforming" else {})})
    return c.done()

# ============================================================================ provedor novo


P4 = "implicit:provedor oci no papel de provedor retirado (P4)"


@R("CQ-NEW-01")
def new_01(v, c: Ctx):
    c.map("p4", P4)
    if v == "conforming":
        n = ns(c)
        b = bucket(c, "s1", n, versioning="Enabled")
        c.map("k1", "probe:concept.k1")
        c.probe = {"kind": "static", "inputs": {"concept": {"k1": {"label": "versionamento de objetos",
                                                                   "exclusive": False, "anchor": f"{b.address}#versioning"}}}}
        return c.done()
    if v == "nonconforming":
        c.r("oci_core_vcn", "s2", {"compartment_id": COMP, "cidr_blocks": ["10.30.0.0/16"],
                                   "display_name": c.name("s2"), "is_ipv6enabled": True,
                                   "is_oracle_gua_allocation_enabled": True}, entity="s2")
        c.map("k2", "probe:concept.k2")
        c.probe = {"kind": "static", "inputs": {"concept": {"k2": {
            "label": "alocação de endereço IPv6 global pela Oracle", "exclusive": True,
            "anchor": f"oci_core_vcn.{c.lab('s2')}#is_oracle_gua_allocation_enabled"}}}}
        c.dev.append("a exclusividade do conceito é declarada aqui como entrada da pergunta; quem a confirma é o "
                     "GLOSSARY (INTERPRETED)")
        return c.done("INTERPRETED")
    n = ns(c)
    b = bucket(c, "src3", n, auto_tiering="InfrequentAccess")
    c.missing("src3", "concept", "EVIDENCE_GAP", "o conceito de auto_tiering não foi determinado (GLOSSARY não "
              "rodou): UNGLOSSED explícito", b.address)
    c.dev.append("a fixture diz documented=false; a conferência da documentação do atributo é do DOCS-OCI/GLOSSARY")
    return c.done("INTERPRETED")


@R("CQ-NEW-02")
def new_02(v, c: Ctx):
    c.map("p4", P4)
    vc, sn = _net(c)
    vm = instance(c, "vm1", sn, two_nics=v != "nonconforming")
    c.map("nic1", f"{vm.address}#create_vnic_details")
    if v == "conforming":
        att = vnic2(c, "nic2", vm, sn)
        c.map("nic2", f"{att.address}#create_vnic_details")
        c.dev.append("nic1 é embutida (declared_inline=true); nic2 é oci_core_vnic_attachment, não bloco embutido "
                     "(declared_inline=false na OCI): a estrutura abstrata (3 indivíduos, 2 anexações) não muda")
    elif v == "nonconforming":
        va = c.x("oci_core_vnic_attachments", "vnics", {"compartment_id": COMP, "instance_id": vm.ref("id")},
                 kind="data", why="leitura da VNIC primária (o IP secundário exige vnic_id)")
        c.r("oci_core_private_ip", "ip2", {"vnic_id": Ref(f"{va.address}.vnic_attachments[0].vnic_id"),
                                           "display_name": c.name("ip2")}, entity="ip2")
    else:
        iid = c.symvar("nic2_instance_id", desc=f"instância de anexação de nic2 da fixture {c.fid}; não lida")
        att = vnic2(c, "nic2", None, sn, instance_id=iid)
        c.map("nic2", f"{att.address}#create_vnic_details")
        c.missing("nic2", "attachment", "EXTERNAL_REFERENCE", "instance_id da anexação de nic2 é variável sem valor",
                  att.address)
    return c.done(deploy_note="instância Always Free")


@R("CQ-NEW-03")
def new_03(v, c: Ctx):
    c.map("p4", P4)
    if v == "nonconforming":
        return na("a fixture exige precedência por posição textual sem mecanismo de ordem; na OCI a filtragem é "
                  "união de permissões (sem precedência) ou lista ordenada explícita do Network Firewall",
                  OCI_ORDER, OCI_ALLOW_ONLY_SL)
    pol = nfw_policy(c)
    sl = nfw_service(c, pol, 22)
    if v == "conforming":
        nfw_rule(c, "r1", pol, sl, "DROP", priority=1)
        c.dev.append("precedência numérica = priority_order da regra da política de firewall (r1 é a única: "
                     "ordem 1, no lugar da prioridade 100 da fixture); ações ALLOW/DROP")
    else:
        r = nfw_rule(c, "r1", pol, sl, "DROP")
        c.missing("rs1", "precedence", "EVIDENCE_GAP", "a regra não declara posição nem priority_order, e não há "
                  "fato do SERVICE-EVIDENCE sobre a ordem padrão: o mecanismo de precedência não tem evidência",
                  r.address)
    return c.done("INTERPRETED", deploy_note="política de firewall sem firewall implantado (sem custo por hora)")
