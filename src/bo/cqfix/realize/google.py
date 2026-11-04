"""Realização das fixtures das CQs no provider google 8.9.0 (registry.terraform.io/hashicorp/google).

Escolhas gerais (cada desvio da situação abstrata vai em Fx.deviations):
- contêiner de objetos = google_storage_bucket (nome global); namespace de armazenamento = o projeto, que
  não é criado aqui (contexto var.project, sem recurso no main.tf);
- conjunto de regras = o conjunto de regras de firewall de uma rede VPC (sem recurso próprio: mapeado como
  <rede>#firewall); cada regra é um google_compute_firewall, com prioridade, permitir/negar e sempre com
  estado; onde a situação pede um conjunto com recurso próprio, google_compute_network_firewall_policy;
- interfaces de rede são blocos network_interface embutidos na instância (componentes anônimos com índice);
- escopo de autorização: projeto (pai) -> bucket (filho, política IAM do recurso); pasta e organização são
  recursos de organização (Classe C), só em fixture marcada como não implantável;
- localização: atributo region/location ligado a var.location_1/var.location_2.
"""
from __future__ import annotations

from ..hcl import Block, Json, Ref, Tpl, Var
from ..model import doc_citation, schema_attr_absent, schema_type_absent
from .base import Ctx, na, reg

PROVIDER = "google"
VERSION = "8.9.0"
REALIZERS: dict = {}

CONTEXT_VARS = {
    "run_id": "identificador curto da execução (prefixo de nomes e rótulo bo_run); ligado pelo runner",
    "location_1": "localização l1 das fixtures (região); ligada pelo runner",
    "location_2": "localização l2, distinta de l1; ligada pelo runner",
    "project": "projeto sandbox (nunca um id real gravado aqui); ligado pelo runner",
}

DOC = "203.0.113.0/24"
IMAGE = "debian-cloud/debian-12"
OBS_AT = "2026-11-02T10:00:00-03:00"

ALLOWED_TYPES = {
    # VPC e firewall (lote A)
    "google_compute_network": {"category": "VPC", "cost_class": "free"},
    "google_compute_subnetwork": {"category": "VPC", "cost_class": "free"},
    "data.google_compute_subnetwork": {"category": "VPC (leitura)", "cost_class": "free"},
    "google_compute_route": {"category": "VPC", "cost_class": "free"},
    "google_compute_firewall": {"category": "firewall", "cost_class": "free"},
    "google_compute_network_firewall_policy": {"category": "firewall", "cost_class": "free"},
    "google_compute_network_firewall_policy_rule": {"category": "firewall", "cost_class": "free"},
    "google_compute_network_firewall_policy_association": {"category": "firewall", "cost_class": "free"},
    # computação mínima (precisa de GO do Breno no DEP)
    "google_compute_instance": {"category": "computação mínima (e2-micro)", "cost_class": "low"},
    "google_compute_instance_group": {"category": "computação mínima (grupo não gerenciado)", "cost_class": "free"},
    # buckets
    "google_storage_bucket": {"category": "buckets", "cost_class": "free"},
    "data.google_storage_bucket": {"category": "buckets (leitura)", "cost_class": "free"},
    "google_storage_bucket_iam_member": {"category": "buckets", "cost_class": "free"},
    "google_storage_bucket_iam_policy": {"category": "buckets (política autoritativa do próprio bucket)",
                                         "cost_class": "free"},
    "data.google_iam_policy": {"category": "IAM (documento, sem recurso)", "cost_class": "free"},
    # IAM
    "google_service_account": {"category": "IAM", "cost_class": "free"},
    "google_service_account_key": {"category": "IAM", "cost_class": "free"},
    "google_project_iam_member": {"category": "IAM (aditivo)", "cost_class": "free"},
    "google_project_iam_custom_role": {"category": "IAM", "cost_class": "free"},
    "google_iam_deny_policy": {"category": "IAM", "cost_class": "free"},
    "google_folder_iam_member": {"category": "organização (Classe C; só offline)", "cost_class": "free"},
    "google_org_policy_policy": {"category": "organização (Classe C; só offline)", "cost_class": "free"},
    "google_cloud_identity_group": {"category": "Cloud Identity (só offline)", "cost_class": "free"},
    "google_cloud_identity_group_membership": {"category": "Cloud Identity (só offline)", "cost_class": "free"},
    # Pub/Sub, logging, monitoramento, KMS, segredo
    "google_pubsub_topic": {"category": "Pub/Sub", "cost_class": "free"},
    "google_logging_metric": {"category": "logging", "cost_class": "free"},
    "google_logging_project_bucket_config": {"category": "logging", "cost_class": "free"},
    "google_monitoring_alert_policy": {"category": "logging (alarmes)", "cost_class": "free"},
    "google_monitoring_notification_channel": {"category": "logging (alarmes)", "cost_class": "free"},
    "google_kms_key_ring": {"category": "KMS", "cost_class": "free"},
    "google_kms_crypto_key": {"category": "KMS", "cost_class": "low"},
    "google_secret_manager_secret": {"category": "segredo (só o contêiner)", "cost_class": "free"},
    "data.google_secret_manager_secret_version": {"category": "segredo (leitura do valor no plano; Withheld)",
                                                  "cost_class": "free"},
    # balanceador e banco (lote B)
    "google_compute_forwarding_rule": {"category": "forwarding rule (lote B)", "cost_class": "low"},
    "google_compute_region_target_http_proxy": {"category": "forwarding rule (lote B)", "cost_class": "free"},
    "google_compute_region_url_map": {"category": "forwarding rule (lote B)", "cost_class": "free"},
    "google_compute_region_backend_service": {"category": "forwarding rule (lote B)", "cost_class": "free"},
    "google_compute_region_health_check": {"category": "forwarding rule (lote B)", "cost_class": "free"},
    "google_sql_database_instance": {"category": "Cloud SQL db-f1-micro (lote B)", "cost_class": "low"},
    "google_sql_database": {"category": "Cloud SQL (lote B)", "cost_class": "free"},
    "google_spanner_instance": {"category": "Spanner 100 PU (limite da Classe C; só offline)", "cost_class": "medium"},
    "google_spanner_database": {"category": "Spanner (só offline)", "cost_class": "free"},
}

SKU_RULES = {
    ("google_compute_instance", "machine_type"): ["e2-micro"],
    ("google_sql_database_instance", "settings.tier"): ["db-f1-micro"],
    ("google_spanner_instance", "processing_units"): [100],
    ("google_storage_bucket", "force_destroy"): [True],
    ("google_compute_forwarding_rule", "load_balancing_scheme"): ["INTERNAL_MANAGED"],
}


def header() -> str:
    return f'''terraform {{
  required_version = "= 1.15.8"
  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "= {VERSION}"
    }}
  }}
}}

provider "google" {{
  project = var.project
  region  = var.location_1
  default_labels = {{
    bo_run    = var.run_id
    bo_module = "cqfix"
  }}
}}

variable "run_id" {{
  type        = string
  description = "{CONTEXT_VARS['run_id']}"
  validation {{
    condition     = can(regex("^[a-z][a-z0-9]{{2,11}}$", var.run_id))
    error_message = "run_id: 3 a 12 caracteres, minúsculas e dígitos."
  }}
}}

variable "location_1" {{
  type        = string
  description = "{CONTEXT_VARS['location_1']}"
}}

variable "location_2" {{
  type        = string
  description = "{CONTEXT_VARS['location_2']}"
}}

variable "project" {{
  type        = string
  description = "{CONTEXT_VARS['project']}"
}}
'''


R = lambda *q: reg(REALIZERS, *q)  # noqa: E731
L1 = Var("location_1")
L2 = Var("location_2")
PROJECT_IMPLICIT = "implicit:projeto sandbox (var.project), sem recurso no main.tf"

# ----------------------------------------------------------------------------- ajudantes


def bucket(c: Ctx, lid: str, entity: str | None = "", extra: dict | None = None, blocks=None, location=L1):
    a = {"name": c.name(lid), "location": location, "force_destroy": True, "uniform_bucket_level_access": True}
    a.update(extra or {})
    ent = lid if entity == "" else entity
    b = c.r("google_storage_bucket", lid, a, blocks or [], entity=ent,
            synth=None if ent else "bucket auxiliar exigido pela situação")
    c.synth[f"{b.address}#force_destroy"] = "segurança de teardown (SAFETY): apagar com objetos"
    c.synth[f"{b.address}#uniform_bucket_level_access"] = "acesso só por IAM (sem ACL por objeto), para a leitura do IAM ser completa"
    return b


def net(c: Ctx, lid: str = "x_net", entity: str | None = None, extra: dict | None = None):
    a = {"name": c.name(lid), "auto_create_subnetworks": False}
    a.update(extra or {})
    return c.r("google_compute_network", lid, a, entity=entity,
               synth=None if entity else "rede VPC exigida pelo schema (sub-rede e firewall precisam de network)")


def subnet(c: Ctx, lid: str, n, cidr: str, entity: str | None = None, region=L1, blocks=None, name_key=None):
    a = {"name": c.name(name_key or lid), "network": n.ref("id"), "ip_cidr_range": cidr, "region": region}
    return c.r("google_compute_subnetwork", lid, a, blocks or [], entity=entity,
               synth=None if entity else "sub-rede exigida pelo schema (interface precisa de subnetwork)")


def nic_block(sn=None, public: bool = False, network=None, alias=None) -> Block:
    a = {}
    if network is not None:
        a["network"] = network
    if sn is not None:
        a["subnetwork"] = sn.ref("id") if hasattr(sn, "ref") else sn
    blocks = []
    if public:
        blocks.append(Block("access_config", {"network_tier": "STANDARD"}))
    if alias:
        blocks.append(Block("alias_ip_range", {"ip_cidr_range": alias}))
    return Block("network_interface", a, blocks)


def instance(c: Ctx, lid: str, nics: list, entity: str | None = None, tags=None, extra_blocks=None):
    a = {"name": c.name(lid), "machine_type": "e2-micro", "zone": Tpl("${var.location_1}-a")}
    if tags:
        a["tags"] = tags
    blocks = [Block("boot_disk", {}, [Block("initialize_params", {"image": IMAGE})])] + nics + (extra_blocks or [])
    r = c.r("google_compute_instance", lid, a, blocks, entity=entity or lid)
    c.synth[f"{r.address}#boot_disk"] = "disco de boot exigido pelo schema (imagem pública Debian)"
    return r


def fw(c: Ctx, lid: str, n, port, cidrs, action: str = "allow", priority: int = 1000, entity: str | None = None,
       direction: str = "INGRESS", extra: dict | None = None, protocol: str = "tcp"):
    a = {"name": c.name(lid), "network": n.ref("id"), "direction": direction, "priority": priority,
         "source_ranges": cidrs}
    a.update(extra or {})
    blk = Block(action, {"protocol": protocol, "ports": [str(port)]})
    return c.r("google_compute_firewall", lid, a, [blk], entity=entity or lid)


def sa(c: Ctx, lid: str, entity: str | None = ""):
    ent = lid if entity == "" else entity
    return c.r("google_service_account", lid, {"account_id": c.name(lid, maxlen=24),
                                                "display_name": Tpl("${var.run_id} " + c.fid)},
               entity=ent, synth=None if ent else "identidade de serviço auxiliar")


def member(s) -> Tpl:
    return Tpl("serviceAccount:${" + s.address + ".email}")


def custom_role(c: Ctx, lid: str, perms, entity: str | None = ""):
    ent = lid if entity == "" else entity
    return c.r("google_project_iam_custom_role", lid,
               {"role_id": Tpl("${var.run_id}_" + c.slug + "_" + lid), "title": Tpl("${var.run_id} " + c.fid),
                "permissions": perms}, entity=ent, synth=None if ent else "papel auxiliar")


def flow(direction="ingress", protocol="tcp", port=443, source="203.0.113.10/32") -> dict:
    d = {"direction": direction, "port": port, "source_cidr": source}
    if protocol:
        d["protocol"] = protocol
    return d


def dynamic(name: str, for_each, content: dict, blocks=None) -> Block:
    return Block("dynamic", {"for_each": for_each}, [Block("content", content, blocks or [])], labels=(name,))


GCS_NAMES = doc_citation(
    "https://cloud.google.com/storage/docs/buckets#naming",
    "nome de bucket do Cloud Storage é global (único entre todos os projetos e locais): dois buckets com a "
    "mesma chave local em locais diferentes não podem coexistir")
GCP_FW_STATEFUL = doc_citation(
    "https://cloud.google.com/firewall/docs/firewalls#specifications",
    "regras de firewall VPC são sempre com estado; não há regra sem estado nem atributo de estado por regra")
GCP_IAM_HIER = doc_citation(
    "https://cloud.google.com/iam/docs/resource-hierarchy-access-control",
    "política IAM herdada desce da organização e pasta para projeto e recurso; a política efetiva é a união")
GCP_DENY_ATTACH = doc_citation(
    "https://cloud.google.com/iam/docs/deny-overview",
    "política de negação se anexa a organização, pasta ou projeto (não a bucket) e vence concessões")
GCP_FW_ORDER = doc_citation(
    "https://cloud.google.com/firewall/docs/firewalls#priority_order_for_firewall_rules",
    "a ordem de avaliação das regras de firewall é só pela prioridade numérica; a posição no código não conta")
GCP_DURATION = doc_citation(
    "https://cloud.google.com/apis/design/design_patterns#time_and_duration",
    "durações nas APIs do Google Cloud são em segundos (google.protobuf.Duration) ou em dias inteiros; não há "
    "campo de retenção em meses de calendário")

# ============================================================================ CIS


@R("CQ-CIS-01")
def cis_mfa(v, c: Ctx):
    return na("o provider google não configura o segundo fator das contas humanas (verificação em duas etapas "
              "fica no console do Workspace/Cloud Identity, fora do Terraform)",
              schema_type_absent("google", r"^google_(cloud_identity_(user|policy|setting)|workspace|admin_)",
                                 "não há tipo de usuário humano nem de política de autenticação do Cloud Identity"),
              schema_type_absent("google", r"(2sv|two_step|2_step|second_factor)",
                                 "não há tipo para verificação em duas etapas"),
              doc_citation("https://cloud.google.com/identity/docs/how-to/enforce-2sv",
                           "a verificação em duas etapas das contas do Cloud Identity é imposta pelo Admin console; "
                           "o mfa do Identity Platform é de usuários finais de aplicação, não do console"))


@R("CQ-CIS-02")
def cis_key_age(v, c: Ctx):
    s = sa(c, "p1")
    k = c.r("google_service_account_key", "k1", {"service_account_id": s.ref("name")}, entity="k1")
    c.synth[f"{k.address}#private_key"] = "o segredo gerado é Withheld: nunca lido nem gravado"
    if v == "incomplete":
        c.missing("k1", "observation", "READ_MASK", "nenhuma leitura datada de serviceAccounts.keys.get "
                  "(validAfterTime) foi feita; a idade não existe sem observação", k.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done(deploy_note="chave de conta de serviço: segredo só com redator (SAFETY)")
    age = 10 if v == "conforming" else 120
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": k.address, "field": "valid_after", "age_days": age},
        "act": {"observed_at": OBS_AT, "api": "iam.projects.serviceAccounts.keys.get"}}}}
    if v == "nonconforming":
        return c.done(deployable=False,
                      deploy_note="idade de 120 dias não se produz num deploy novo: só offline com observação gravada")
    return c.done(deploy_note="chave de conta de serviço: segredo só com redator (SAFETY)")


@R("CQ-CIS-03")
def cis_kms(v, c: Ctx):
    kr = c.x("google_kms_key_ring", "ring", {"name": c.name("ring"), "location": L1},
             why="chaveiro exigido pelo schema (crypto_key precisa de key_ring); não é apagável (resíduo esperado)")
    a = {"name": c.name("k1"), "key_ring": kr.ref("id"), "destroy_scheduled_duration": "86400s"}
    if v == "conforming":
        a["rotation_period"] = "7776000s"
    elif v == "incomplete":
        a["rotation_period"] = c.symvar("rotation_period")
        c.missing("d1", "value", "SYMBOLIC_INPUT", "rotation_period vem de variável sem valor",
                  f"google_kms_crypto_key.{c.lab('k1')}")
    else:
        c.dev.append("no GCP a rotação desligada é a ausência de rotation_period (não há flag explícita); a "
                     "configuração lida continua sem rotação, então a resposta (false) não muda")
    k = c.r("google_kms_crypto_key", "k1", a, entity="k1")
    c.map("d1", f"{k.address}#rotation_period")
    c.synth[f"{k.address}#destroy_scheduled_duration"] = "teardown: menor janela de destruição agendada (SAFETY)"
    return c.done(cost_class="low", deploy_note="chaveiro KMS não se apaga: resíduo esperado com prazo")


def _ports(v, c: Ctx, port: int):
    n = net(c, entity="rs1")
    c.map("rs1", f"{n.address}#firewall")
    c.dev.append("o conjunto de regras é o conjunto de regras de firewall da rede VPC (sem recurso próprio); "
                 "cada regra é um google_compute_firewall")
    if v == "incomplete":
        cidrs = Ref("[" + c.symvar("source_cidr").expr + "]")
        c.missing("r1", "value", "SYMBOLIC_INPUT", "source_ranges da regra vem de variável sem valor",
                  f"google_compute_firewall.{c.lab('r1')}")
    else:
        cidrs = [DOC] if v == "conforming" else ["0.0.0.0/0"]
    fw(c, "r1", n, port, cidrs)
    return c.done()


@R("CQ-CIS-04")
def cis_ssh(v, c):
    return _ports(v, c, 22)


@R("CQ-CIS-05")
def cis_rdp(v, c):
    return _ports(v, c, 3389)


@R("CQ-CIS-06")
def cis_flow(v, c: Ctx):
    n = net(c, "vn1", entity="vn1")
    log = {"aggregation_interval": "INTERVAL_10_MIN", "flow_sampling": 0.5, "metadata": "INCLUDE_ALL_METADATA"}
    blocks = []
    if v == "conforming":
        blocks = [Block("log_config", log)]
    elif v == "incomplete":
        flag = c.symvar("flow_log_enabled", "bool")
        blocks = [dynamic("log_config", Ref(flag.expr + " ? [1] : []"), log)]
        c.missing("d1", "value", "SYMBOLIC_INPUT", "a existência do log_config (bloco dinâmico) vem de variável "
                  "sem valor", f"google_compute_subnetwork.{c.lab('sa')}")
    sn = subnet(c, "sa", n, "10.20.1.0/24", entity="sa", blocks=blocks)
    if v == "nonconforming":
        c.map("s1", PROJECT_IMPLICIT + "; leitura completa declarada das sub-redes")
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "compute.subnetworks.list", "complete": True}}}
    else:
        c.map("d1", f"{sn.address}#log_config")
        c.dev.append("o registro de fluxo do GCP é o bloco log_config da sub-rede (faceta, sem recurso próprio)")
    return c.done()


_FW_FILTER = ('resource.type="gce_firewall_rule" AND (protoPayload.methodName:"compute.firewalls.patch" OR '
              'protoPayload.methodName:"compute.firewalls.insert" OR protoPayload.methodName:"compute.firewalls.delete")')
_ROUTE_FILTER = ('resource.type="gce_route" AND (protoPayload.methodName:"compute.routes.delete" OR '
                 'protoPayload.methodName:"compute.routes.insert")')


def _alert(c: Ctx, topic):
    ch = c.x("google_monitoring_notification_channel", "channel",
             {"display_name": Tpl("${var.run_id} " + c.fid), "type": "pubsub",
              "labels": {"topic": topic.ref("id")}},
             why="canal de notificação que entrega no tópico (relação notifies)")
    return ch


@R("CQ-CIS-07")
def cis_alert(v, c: Ctx):
    c.map("s1", PROJECT_IMPLICIT)
    t = c.r("google_pubsub_topic", "t1", {"name": c.name("t1")}, entity="t1")
    ch = _alert(c, t)
    if v == "incomplete":
        filt = c.symvar("log_filter")
        c.missing("al1", "value", "SYMBOLIC_INPUT", "o filtro de log da métrica vem de variável sem valor",
                  f"google_logging_metric.{c.lab('x_metric')}")
    else:
        filt = _FW_FILTER if v == "conforming" else _ROUTE_FILTER
    m = c.x("google_logging_metric", "metric", {"name": c.name("metric"), "filter": filt},
            [Block("metric_descriptor", {"metric_kind": "DELTA", "value_type": "INT64"})],
            why="métrica de log que define o evento observado pelo alarme (forma do CIS GCP 2.7)")
    cond = Block("conditions", {"display_name": "evento"}, [Block("condition_threshold", {
        "filter": Tpl('resource.type = \\"global\\" AND metric.type = \\"logging.googleapis.com/user/${'
                      + m.address + '.name}\\"'),
        "comparison": "COMPARISON_GT", "threshold_value": 0, "duration": "0s"},
        [Block("aggregations", {"alignment_period": "60s", "per_series_aligner": "ALIGN_COUNT"})])])
    c.r("google_monitoring_alert_policy", "al1",
        {"display_name": Tpl("${var.run_id} " + c.fid), "combiner": "OR", "notification_channels": [ch.ref("id")]},
        [cond], entity="al1")
    if v == "nonconforming":
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "monitoring.alertPolicies.list",
                                                               "complete": True}}}
    return c.done()


@R("CQ-CIS-08")
def cis_public(v, c: Ctx):
    if v == "conforming":
        b = bucket(c, "c1", extra={"public_access_prevention": "enforced"})
        c.map("k1", f"{b.address}#public_access_prevention")
        return c.done()
    if v == "incomplete":
        b = bucket(c, "c1", extra={"public_access_prevention": c.symvar("public_access_prevention")})
        c.map("k1", f"{b.address}#public_access_prevention")
        c.missing("k1", "value", "SYMBOLIC_INPUT", "public_access_prevention vem de variável sem valor", b.address)
        return c.done()
    b = bucket(c, "c1", extra={"public_access_prevention": "inherited"})
    c.r("google_storage_bucket_iam_member", "k1", {"bucket": b.ref("name"), "role": "roles/storage.objectViewer",
                                                   "member": "allUsers"}, entity="k1")
    c.dev.append("k1 = a concessão a allUsers (o acesso público efetivo); public_access_prevention 'inherited' "
                 "deixa o bucket aberto se a política da organização não impuser")
    return c.done(deploy_note="política da organização do projeto sandbox pode recusar allUsers; a leitura de "
                              "volta registra REJECTED_BY_API")


# ============================================================================ identidade e ciclo de vida


@R("CQ-IDL-01")
def idl01(v, c: Ctx):
    if v == "conforming":
        b = bucket(c, "c1", blocks=[Block("versioning", {"enabled": True})])
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "versioning.enabled", "before": {"address": b.address, "versioning.enabled": False},
            "after": "main.tf", "plan_action_expected": "update"}}}
        return c.done()
    if v == "nonconforming":
        b = bucket(c, "c2", location=L2)
        c.map("c1", "probe:change.before")
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "location", "before": {"address": b.address, "location": "var.location_1",
                                                "name": "o mesmo nome (chave local data_a)"},
            "after": "main.tf", "plan_action_expected": "replace"}}}
        c.dev.append("c1 é a leitura anterior (mesmo endereço e nome, location_1); c2 é o recurso do main.tf "
                     "depois da troca de location, que força substituição")
        return c.done()
    b = bucket(c, "c1", extra={"storage_class": "NEARLINE"})
    c.probe = {"kind": "two_phase", "inputs": {"change": {
        "attribute": "storage_class", "before": {"address": b.address, "storage_class": "STANDARD"},
        "after": "main.tf", "plan_action_expected": None}}}
    c.missing("c1", "mutability", "EVIDENCE_GAP", "o schema JSON do provider não expõe ForceNew e o "
              "SERVICE-EVIDENCE ainda não tem fato sobre storage_class ser mutável no lugar", b.address)
    return c.done()


@R("CQ-IDL-02")
def idl02(v, c: Ctx):
    c.map("acc", PROJECT_IMPLICIT)
    c.map("l1", "implicit:var.location_1")
    n = net(c)
    c.dev.append("bucket do GCS tem nome global (não existem dois com a mesma chave em locais diferentes); a "
                 "situação usa google_compute_subnetwork, cuja chave local (nome) é única por projeto e região")
    c.evidence.append(GCS_NAMES)
    c1 = subnet(c, "c1", n, "10.20.1.0/24", entity="c1", name_key="data")
    if v == "conforming":
        c.map("l2", "implicit:var.location_2")
        subnet(c, "c2", n, "10.20.2.0/24", entity="c2", region=L2, name_key="data")
        return c.done("INTERPRETED")
    if v == "nonconforming":
        c.r("google_compute_subnetwork", "c2", {"name": c.name("data"), "region": L1}, kind="data",
            entity="c2", depends_on=[c1.address])
        c.dev.append("c2 é a segunda leitura (data source) do mesmo recurso: mesma conta, região, tipo e chave")
        return c.done("INTERPRETED")
    reg_ = c.symvar("c2_region")
    c.r("google_compute_subnetwork", "c2", {"name": c.name("data"), "region": reg_}, kind="data", entity="c2")
    c.missing("c2", "location", "SYMBOLIC_INPUT", "a região da segunda leitura vem de variável sem valor",
              f"data.google_compute_subnetwork.{c.lab('c2')}")
    return c.done("INTERPRETED")


@R("CQ-IDL-03")
def idl03(v, c: Ctx):
    if v == "conforming":
        p = sa(c, "p1")
        role = custom_role(c, "ps1", ["storage.objects.get"])
        c.map("s1", PROJECT_IMPLICIT)
        a = c.r("google_project_iam_member", "a1", {"project": Var("project"), "role": role.ref("id"),
                                                    "member": member(p)}, entity="a1")
        c.probe = {"kind": "static", "inputs": {"removal": {"X": p.address, "Y": a.address}}}
        return c.done()
    if v == "nonconforming":
        c.map("ns1", "implicit:projeto sandbox como namespace dos buckets (var.project; sem recurso no main.tf)")
        b = bucket(c, "c1")
        c.probe = {"kind": "static", "inputs": {"removal": {"X": b.address, "Y": "projeto (var.project)"}}}
        c.dev.append("no GCP o namespace dos buckets é o projeto; apagar o projeto apaga os buckets")
        return c.done("INTERPRETED", deployable=False,
                      deploy_note="remover o projeto sandbox não é feito em fixture: só offline")
    b = bucket(c, "c1", blocks=[Block("retention_policy", {"retention_period": 86400})])
    c.map("s1", f"{b.address}#retention_policy")
    c.missing("s1", "lifecycle", "EVIDENCE_GAP", "o schema diz só que retention_policy é bloco do bucket; não há "
              "fato do SERVICE-EVIDENCE sobre quem cria e apaga a política de retenção", b.address)
    c.probe = {"kind": "static", "inputs": {"removal": {"X": f"{b.address}#retention_policy", "Y": b.address}}}
    return c.done(deploy_note="retenção de 1 dia: o bucket só se apaga depois que os objetos vencem (vazio, apaga)")


@R("CQ-IDL-04")
def idl04(v, c: Ctx):
    n = net(c)
    port1 = 443 if v == "conforming" else 8443
    if v == "incomplete":
        port1 = Ref(c.symvar("r1_port").expr)
        c.missing("r1", "identity_fields", "SYMBOLIC_INPUT", "as portas do primeiro bloco allow vêm de variável "
                  "sem valor", f"google_compute_firewall.{c.lab('rs1')}")
    r1 = Block("allow", {"protocol": "tcp", "ports": [port1 if isinstance(port1, Ref) else str(port1)]})
    r2 = Block("allow", {"protocol": "tcp", "ports": ["22"]})
    blocks = [r2, r1] if v == "conforming" else [r1, r2]
    f = c.r("google_compute_firewall", "rs1", {"name": c.name("rs1"), "network": n.ref("id"), "direction": "INGRESS",
                                               "source_ranges": [DOC]}, blocks, entity="rs1")
    c.map("r1", f"{f.address}#allow[tcp:443]" if v != "incomplete" else f"{f.address}#allow[0]")
    c.map("r2", f"{f.address}#allow[tcp:22]")
    if v == "nonconforming":
        c.map("r1", f"{f.address}#allow[tcp:8443]")
    c.dev.append("as regras anônimas são os blocos allow de uma google_compute_firewall (rs1)")
    before = [{"protocol": "tcp", "ports": ["443"]}, {"protocol": "tcp", "ports": ["22"]}]
    c.probe = {"kind": "two_phase", "inputs": {"change": {
        "attribute": "ordem textual dos blocos allow" if v != "nonconforming" else "porta do bloco r1",
        "before": {"address": f.address, "allow": before}, "after": "main.tf",
        "plan_action_expected": "update"}}}
    return c.done()


# ============================================================================ composição


@R("CQ-CMP-01")
def cmp01(v, c: Ctx):
    if v != "incomplete":
        n = net(c, "vn1", entity="vn1")
    if v == "conforming":
        sn = subnet(c, "sa", n, "10.20.1.0/24", entity="sa")
        vm = instance(c, "vm1", [nic_block(sn)])
    elif v == "nonconforming":
        vm = instance(c, "vm1", [nic_block("fx-missing-subnet")])
        c.dev.append("a interface referencia uma sub-rede pelo nome 'fx-missing-subnet', que não existe na leitura")
    else:
        ext = c.symvar("subnetwork")
        c.map("sa", f"external:{ext.expr}: sub-rede em escopo não lido")
        vm = instance(c, "vm1", [nic_block(ext)])
        c.missing("sa", "scope", "EXTERNAL_REFERENCE", "a interface usa sub-rede vinda de variável; a cadeia acima "
                  "dela (rede) não foi lida", vm.address)
    c.map("nic1", f"{vm.address}#network_interface[0]")
    if v == "nonconforming":
        return c.done(deployable=False, deploy_note="o apply tem de falhar (sub-rede inexistente); o DEP decide")
    return c.done(cost_class="low")


def _two_nets(c: Ctx):
    na_ = net(c, "x_net_a")
    nb = c.x("google_compute_network", "net_b", {"name": c.name("netb"), "auto_create_subnetworks": False},
             why="no GCP cada interface de uma instância fica numa rede VPC diferente")
    sa_ = subnet(c, "x_sub_a", na_, "10.20.1.0/24")
    sb = c.x("google_compute_subnetwork", "sub_b", {"name": c.name("subb"), "network": nb.ref("id"),
                                                     "ip_cidr_range": "10.21.1.0/24", "region": L1},
             why="sub-rede da segunda interface")
    return na_, nb, sa_, sb


@R("CQ-CMP-02", "CQ-NEW-02")
def nic_count(v, c: Ctx):
    if c.cq_id == "CQ-NEW-02":
        c.map("p4", "implicit:provedor google no papel de provedor retirado (P4)")
    if v == "conforming":
        _, _, sa_, sb = _two_nets(c)
        vm = instance(c, "vm1", [nic_block(sa_), nic_block(sb)])
        c.map("nic2", f"{vm.address}#network_interface[1]")
    elif v == "nonconforming":
        sa_ = subnet(c, "x_sub_a", net(c, "x_net_a"), "10.20.1.0/24")
        if c.cq_id == "CQ-NEW-02":
            vm = instance(c, "vm1", [nic_block(sa_, alias="/32")])
            c.map("ip2", f"{vm.address}#network_interface[0].alias_ip_range")
            c.dev.append("o endereço secundário é um alias_ip_range da primeira interface, não uma interface")
        else:
            vm = instance(c, "vm1", [nic_block(sa_)])
    else:
        sa_ = subnet(c, "x_sub_a", net(c, "x_net_a"), "10.20.1.0/24")
        extra = c.symvar("extra_interfaces", "list(string)")
        vm = instance(c, "vm1", [nic_block(sa_), dynamic("network_interface", Ref(extra.expr),
                                                          {"subnetwork": Ref("network_interface.value")})])
        c.map("nic2", f"external:{extra.expr}: segunda interface declarada por bloco dinâmico sem valor")
        c.missing("nic2", "attachment", "SYMBOLIC_INPUT", "as interfaces além da primeira vêm de bloco dinâmico "
                  "sobre variável sem valor", vm.address)
    c.map("nic1", f"{vm.address}#network_interface[0]")
    return c.done(cost_class="low")


def _find(c: Ctx, lid: str) -> str:
    for x in c.res:
        if x.label == c.lab(lid):
            return x.address
    raise KeyError(lid)


@R("CQ-CMP-03")
def cmp03(v, c: Ctx):
    n = net(c)
    sn = subnet(c, "x_sub", n, "10.20.1.0/24")
    c.x("google_compute_subnetwork", "proxy_sub", {"name": c.name("proxy"), "network": n.ref("id"),
                                                    "ip_cidr_range": "10.20.250.0/24", "region": L1,
                                                    "purpose": "REGIONAL_MANAGED_PROXY", "role": "ACTIVE"},
        why="sub-rede só de proxy exigida pelo balanceador HTTP interno regional")
    hp = c.r("google_compute_region_health_check", "hp1", {"name": c.name("hp1"), "region": L1},
             [Block("http_health_check", {"port": 80})], entity="hp1")
    grp_a = {"name": c.name("grp"), "zone": Tpl("${var.location_1}-a")}
    if v == "conforming":
        vm = instance(c, "vm1", [nic_block(sn)])
        grp_a["instances"] = [vm.ref("self_link")]
    elif v == "incomplete":
        ext = c.symvar("group_instances", "list(string)")
        grp_a["instances"] = Ref(ext.expr)
    grp = c.x("google_compute_instance_group", "group", grp_a,
              why="grupo não gerenciado que realiza a relação member_of_pool (membros do pool)")
    pool = c.r("google_compute_region_backend_service", "pool1",
               {"name": c.name("pool1"), "region": L1, "load_balancing_scheme": "INTERNAL_MANAGED",
                "protocol": "HTTP", "health_checks": [hp.ref("id")]},
               [Block("backend", {"group": grp.ref("id"), "balancing_mode": "UTILIZATION", "capacity_scaler": 1.0})],
               entity="pool1")
    um = c.r("google_compute_region_url_map", "ru1", {"name": c.name("ru1"), "region": L1,
                                                      "default_service": pool.ref("id")}, entity="ru1")
    px = c.r("google_compute_region_target_http_proxy", "li1", {"name": c.name("li1"), "region": L1,
                                                               "url_map": um.ref("id")}, entity="li1")
    c.r("google_compute_forwarding_rule", "fe1", {"name": c.name("fe1"), "region": L1,
                                                  "load_balancing_scheme": "INTERNAL_MANAGED", "port_range": "443",
                                                  "network": n.ref("id"), "subnetwork": sn.ref("id"),
                                                  "target": px.ref("id")},
        depends_on=[f"google_compute_subnetwork.{c.lab('x_proxy_sub')}"], entity="fe1")
    c.map("lb1", "implicit:o balanceador como todo não tem recurso próprio no GCP; é o grafo forwarding rule -> "
                 "proxy -> url map -> backend service")
    c.dev.append("ru1 (match any) = default_service do url map; listener = proxy HTTP alvo da forwarding rule "
                 "na porta 443 (sem TLS: a situação não pede TLS)")
    if v == "incomplete":
        c.missing("pool1", "membership", "EXTERNAL_REFERENCE", "os membros do grupo vêm de variável sem valor "
                  "(lista possivelmente vazia)", grp.address)
    return c.done("INTERPRETED", cost_class="low")


@R("CQ-CMP-04")
def cmp04(v, c: Ctx):
    c.dev.append("o GCP não tem configuração de armazenamento declarada no namespace (projeto) a não ser por "
                 "política da organização; a situação usa a restrição storage.publicAccessPrevention no lugar "
                 "do versionamento (o tipo da configuração não muda a pergunta de alcance)")
    if v == "conforming":
        c.map("ns1", PROJECT_IMPLICIT + " (namespace dos buckets)")
        bucket(c, "c1")
        c.r("google_org_policy_policy", "k1",
            {"name": Tpl("projects/${var.project}/policies/storage.publicAccessPrevention"),
             "parent": Tpl("projects/${var.project}")},
            [Block("spec", {}, [Block("rules", {"enforce": "TRUE"})])], entity="k1")
        return c.done("INTERPRETED", deployable=False,
                      deploy_note="política de organização no projeto exige organização (Classe C): só offline")
    if v == "nonconforming":
        c.map("ns1", PROJECT_IMPLICIT + " (namespace dos buckets)")
        bucket(c, "c1")
        b2 = bucket(c, "c2", extra={"public_access_prevention": "enforced"})
        c.map("k1", f"{b2.address}#public_access_prevention")
        return c.done("INTERPRETED")
    c.map("ns1", PROJECT_IMPLICIT + " (namespace dos buckets)")
    nm = c.symvar("c1_name")
    c.r("google_storage_bucket", "c1", {"name": nm}, kind="data", entity="c1")
    c.r("google_org_policy_policy", "k1",
        {"name": Tpl("projects/${var.project}/policies/storage.publicAccessPrevention"),
         "parent": Tpl("projects/${var.project}")},
        [Block("spec", {}, [Block("rules", {"enforce": "TRUE"})])], entity="k1")
    c.missing("c1", "membership", "EXTERNAL_REFERENCE", "o bucket é lido por nome vindo de variável; não se sabe "
              "em que projeto (namespace) ele está", f"data.google_storage_bucket.{c.lab('c1')}")
    return c.done("INTERPRETED", deployable=False,
                  deploy_note="política de organização no projeto exige organização (Classe C): só offline")


@R("CQ-CMP-05")
def cmp05(v, c: Ctx):
    if v == "conforming":
        i = c.r("google_sql_database_instance", "i1",
                {"name": c.name("i1"), "region": L1, "database_version": "POSTGRES_16", "deletion_protection": False},
                [Block("settings", {"tier": "db-f1-micro", "edition": "ENTERPRISE"})], entity="i1")
        c.synth[f"{i.address}#deletion_protection"] = "teardown (SAFETY)"
        c.r("google_sql_database", "db1", {"name": "fxdb", "instance": i.ref("name")}, entity="db1")
        c.dev.append("engine_b = POSTGRES_16 (o motor abstrato não muda a pergunta)")
        return c.done(cost_class="low")
    if v == "nonconforming":
        s = c.r("google_spanner_instance", "srv1", {"name": c.name("srv1", maxlen=24), "config": Tpl(
            "regional-${var.location_1}"), "display_name": Tpl("${var.run_id} srv1"), "processing_units": 100,
            "force_destroy": True}, entity="srv1")
        c.r("google_spanner_database", "db1", {"name": "fxdb", "instance": s.ref("name"),
                                               "deletion_protection": False}, entity="db1")
        c.dev.append("servidor lógico = instância Spanner: alocação de capacidade sem máquina de banco exposta "
                     "(nós não são recursos); interpretação a conferir no SERVICE-EVIDENCE")
        return c.done("INTERPRETED", deployable=False, cost_class="medium",
                      deploy_note="Spanner 100 PU custa por hora; só com OK do Breno (limite da Classe C)")
    i = c.r("google_sql_database_instance", "srv2",
            {"name": c.name("srv2"), "region": L1, "database_version": "POSTGRES_16", "deletion_protection": False},
            [Block("settings", {"tier": "db-f1-micro", "edition": "ENTERPRISE", "availability_type": "REGIONAL"})],
            entity="srv2")
    c.r("google_sql_database", "db1", {"name": "fxdb", "instance": i.ref("name")}, entity="db1")
    c.dev.append("srv2 = Cloud SQL com availability_type REGIONAL: serviço com alta disponibilidade gerida; a "
                 "primária e a standby não são recursos expostos")
    c.missing("srv2", "instance_count", "EVIDENCE_GAP", "quantas instâncias sustentam o serviço REGIONAL não está "
              "no schema nem no SERVICE-EVIDENCE", i.address)
    return c.done("INTERPRETED", deployable=False, cost_class="low",
                  deploy_note="alta disponibilidade pode não valer para o tier compartilhado db-f1-micro; o DEP decide")


# ============================================================================ autorização


def _req(principal: str, resource: str, action: str = "read", context=None) -> dict:
    d = {"principal": principal, "action": action, "resource": resource}
    if context is not None:
        d["context"] = context
    return d


@R("CQ-AUT-01")
def aut01(v, c: Ctx):
    p = sa(c, "p1")
    r1 = bucket(c, "r1")
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": _req(p.address, r1.address)}}
    c.evidence.append(GCP_IAM_HIER)
    if v == "incomplete":
        c.map("s_parent", PROJECT_IMPLICIT + " (escopo pai, política IAM não lida)")
        c.map("s_child", f"{r1.address}#iam_scope")
        c.missing("s_parent", "scope", "READ_MASK", "a política IAM do projeto (getIamPolicy do projeto e das pastas "
                  "acima) não foi lida; a herança pode conceder ou negar")
        return c.done("INTERPRETED")
    role = custom_role(c, "ps1", ["storage.objects.get"])
    c.map("perm1", f"{role.address}#permissions[storage.objects.get]")
    if v == "conforming":
        c.map("s_parent", PROJECT_IMPLICIT + " (escopo pai)")
        c.map("s_child", f"{r1.address}#iam_scope")
        c.r("google_project_iam_member", "a1", {"project": Var("project"), "role": role.ref("id"),
                                                "member": member(p)}, entity="a1")
        c.dev.append("escopo filho = a política IAM do bucket r1; a concessão no projeto desce para ele")
        return c.done("INTERPRETED")
    c.map("s_parent", "implicit:pasta acima do projeto (recurso de organização, não criado; nome marcador)")
    c.map("s_child", PROJECT_IMPLICIT + " (escopo filho da pasta)")
    c.r("google_folder_iam_member", "a1", {"folder": Tpl("folders/${var.project}-parent"), "role": role.ref("id"),
                                           "member": member(p)}, entity="a1")
    c.r("google_iam_deny_policy", "d1",
        {"name": c.name("d1"), "display_name": Tpl("${var.run_id} " + c.fid),
         "parent": Tpl("cloudresourcemanager.googleapis.com%2Fprojects%2F${var.project}")},
        [Block("rules", {}, [Block("deny_rule", {
            "denied_principals": [Tpl("principal://iam.googleapis.com/projects/-/serviceAccounts/${"
                                      + p.address + ".email}")],
            "denied_permissions": ["storage.googleapis.com/objects.get"]})])], entity="d1")
    c.dev.append("negação não se anexa a bucket no GCP (só organização, pasta ou projeto): a hierarquia da "
                 "situação vira pasta (pai, concessão) -> projeto (filho, negação) -> bucket r1")
    c.evidence.append(GCP_DENY_ATTACH)
    return c.done("INTERPRETED", deployable=False,
                  deploy_note="concessão em pasta exige organização (Classe C); o nome da pasta é marcador: só offline")


@R("CQ-AUT-02")
def aut02(v, c: Ctx):
    p = sa(c, "p1")
    b = bucket(c, "x_scope", entity="s1")
    c.map("s1", f"{b.address}#iam_scope")
    role = custom_role(c, "ps1", ["storage.objects.get"])
    c.r("google_storage_bucket_iam_member", "a1", {"bucket": b.ref("name"), "role": role.ref("id"),
                                                   "member": member(p)}, entity="a1")
    if v == "nonconforming":
        role2 = custom_role(c, "ps2", ["storage.objects.list"])
        c.r("google_storage_bucket_iam_member", "a2", {"bucket": b.ref("name"), "role": role2.ref("id"),
                                                       "member": member(p)}, entity="a2")
        return c.done()
    members = [member(p)]
    if v == "incomplete":
        members = Ref("[" + c.symvar("doc_member").expr + "]")
    doc = c.r("google_iam_policy", "doc1", {}, [Block("binding", {"role": role.ref("id"), "members": members})],
              kind="data", entity="doc1")
    c.map("a2", f"{doc.address}#binding[{role.label}]")
    c.x("google_storage_bucket_iam_policy", "apply_doc", {"bucket": b.ref("name"), "policy_data": doc.ref("policy_data")},
        why="aplica o documento de política ao bucket (forma documento da mesma concessão)")
    if v == "incomplete":
        c.missing("a2", "reference", "SYMBOLIC_INPUT", "o membro do binding do documento vem de variável sem valor",
                  doc.address)
    return c.done(deployable=False, deploy_note="política autoritativa e membro aditivo no mesmo bucket brigam a cada "
                                                "apply (antipadrão documentado): só offline")


@R("CQ-AUT-03")
def aut03(v, c: Ctx):
    p = sa(c, "p1")
    role = custom_role(c, "ps1", ["storage.objects.get"])
    c.map("perm1", f"{role.address}#permissions[storage.objects.get]")
    r2 = bucket(c, "r2")
    c.map("s_parent", PROJECT_IMPLICIT + " (escopo pai, que contém r2 diretamente)")
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": _req(p.address, r2.address)}}
    if v == "nonconforming":
        child = bucket(c, "x_child", entity="s_child")
        c.map("s_child", f"{child.address}#iam_scope")
        c.r("google_project_iam_member", "a1", {"project": Var("project"), "role": role.ref("id"),
                                                "member": member(p)}, entity="a1")
        return c.done()
    if v == "conforming":
        child = bucket(c, "x_child", entity="s_child")
        c.map("s_child", f"{child.address}#iam_scope")
        c.r("google_storage_bucket_iam_member", "a1", {"bucket": child.ref("name"), "role": role.ref("id"),
                                                       "member": member(p)}, entity="a1")
        c.dev.append("escopo filho = a política IAM de outro bucket; r2 está só no projeto")
        return c.done()
    ext = c.symvar("child_scope_bucket")
    c.map("s_child", f"external:{ext.expr}: escopo da atribuição sem lugar conhecido na hierarquia")
    a = c.r("google_storage_bucket_iam_member", "a1", {"bucket": ext, "role": role.ref("id"), "member": member(p)},
            entity="a1")
    c.missing("s_child", "scope", "SYMBOLIC_INPUT", "o bucket (escopo) da atribuição vem de variável sem valor; "
              "não se sabe se contém r2", a.address)
    return c.done()


@R("CQ-AUT-04")
def aut04(v, c: Ctx):
    role = custom_role(c, "ps1", ["storage.objects.get"])
    c.map("s1", PROJECT_IMPLICIT)
    if v == "incomplete":
        pool = c.symvar("workforce_pool")
        grp = c.symvar("external_group")
        c.map("dir1", f"external:{pool.expr}: pool de força de trabalho federado a IdP externo (fora dos pins)")
        c.map("g1", f"external:{grp.expr}: grupo mantido no IdP externo")
        c.map("u1", "external:usuário mantido no IdP externo (fora dos pins)")
        c.r("google_project_iam_member", "a1", {
            "project": Var("project"), "role": role.ref("id"),
            "member": Tpl("principalSet://iam.googleapis.com/locations/global/workforcePools/${" + pool.expr
                          + "}/group/${" + grp.expr + "}")}, entity="a1")
        c.missing("u1", "group_membership", "EXTERNAL_REFERENCE", "a pertença do usuário ao grupo está no IdP "
                  "externo do pool de força de trabalho; nenhum provider fixado a lê")
        return c.done("INTERPRETED", deployable=False,
                      deploy_note="pool de força de trabalho é recurso de organização: só offline")
    u = sa(c, "u1")
    c.dev.append("u1 é uma conta de serviço como membro do grupo (o google provider não cria usuário humano); "
                 "a pergunta é sobre a concessão via pertença, que não muda")
    g = c.r("google_cloud_identity_group", "g1", {
        "parent": Tpl("customers/${var.project}-customer"), "display_name": Tpl("${var.run_id} g1"),
        "labels": {"cloudidentity.googleapis.com/groups.discussion_forum": ""}},
        [Block("group_key", {"id": Tpl("${var.run_id}-g1@example.com")})], entity="g1")
    if v == "conforming":
        c.x("google_cloud_identity_group_membership", "membership", {"group": g.ref("id")},
            [Block("preferred_member_key", {"id": u.ref("email")}), Block("roles", {"name": "MEMBER"})],
            why="relação member_of_group (u1 -> g1)")
    c.r("google_project_iam_member", "a1", {"project": Var("project"), "role": role.ref("id"),
                                            "member": Tpl("group:${" + g.address + ".group_key[0].id}")}, entity="a1")
    return c.done("INTERPRETED", deployable=False,
                  deploy_note="grupo do Cloud Identity exige cliente Workspace/Cloud Identity (o marcador de "
                              "cliente e o domínio example.com não são reais): só offline")


@R("CQ-AUT-05")
def aut05(v, c: Ctx):
    p = sa(c, "p1")
    r1 = bucket(c, "r1")
    role = custom_role(c, "ps1", ["storage.objects.get"])
    c.map("perm1", f"{role.address}#permissions[storage.objects.get]")
    c.map("s1", PROJECT_IMPLICIT)
    if v == "incomplete":
        expr = '"accessPolicies/0/accessLevels/compliant_device" in request.auth.access_levels'
    else:
        expr = 'request.time < timestamp("2027-01-01T00:00:00Z")'
    a = c.r("google_project_iam_member", "a1", {"project": Var("project"), "role": role.ref("id"),
                                                "member": member(p)},
            [Block("condition", {"title": "fxcond", "expression": expr})], entity="a1")
    c.map("c1", f"{a.address}#condition")
    ctx = {"conforming": "request.time=2026-11-02T13:00:00Z", "nonconforming": "request.time=2027-02-01T13:00:00Z"}
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": _req(p.address, r1.address,
                                                                   context=ctx.get(v))}}
    if v == "incomplete":
        c.missing("c1", "condition_attribute", "EVIDENCE_GAP", "a condição usa request.auth.access_levels (nível de "
                  "acesso do dispositivo), atributo que o vocabulário não tem", a.address)
        return c.done("INTERPRETED", deployable=False,
                      deploy_note="nível de acesso é do Access Context Manager (organização): só offline")
    c.dev.append("condição IAM do GCP não testa origem IP; a situação usa janela de tempo (request.time) como "
                 "condição de contexto equivalente: satisfeita na conforme, não satisfeita na não conforme")
    return c.done("INTERPRETED")


# ============================================================================ caminho de rede


def _path(c: Ctx, v: str, public: bool, route: bool | None, rules: list, entity_rules=True):
    """instância + interface + sub-rede + rotas da rede + regras de firewall; route None = simbólico."""
    extra = {"delete_default_routes_on_create": True}
    if route is None:
        extra = {"delete_default_routes_on_create": Ref(c.symvar("delete_default_routes", "bool").expr)}
    n = net(c, extra=extra, entity="rs1")
    sn = subnet(c, "sa", n, "10.20.1.0/24", entity="sa")
    vm = instance(c, "vm1", [nic_block(sn, public=public)])
    c.map("nic1", f"{vm.address}#network_interface[0]")
    c.map("ip1", f"{vm.address}#network_interface[0].access_config" if public
          else f"{vm.address}#network_interface[0].network_ip")
    c.map("rt1", f"{n.address}#routes")
    c.map("rs1", f"{n.address}#firewall")
    if route:
        c.r("google_compute_route", "rte1", {"name": c.name("rte1"), "network": n.ref("id"), "dest_range": "0.0.0.0/0",
                                             "next_hop_gateway": "default-internet-gateway"}, entity="rte1")
        c.map("igw", "implicit:default-internet-gateway do GCP (próximo salto sem recurso)")
    for lid, port, cidrs, action, prio in rules:
        fw(c, lid, n, port, cidrs, action=action, priority=prio)
    c.dev.append("tabela de rotas = rotas da rede VPC (sem recurso de tabela); conjunto de regras = firewall da "
                 "rede; a regra vale para as instâncias da rede (sem alvo por etiqueta)")
    return n, vm


@R("CQ-NET-01")
def net01(v, c: Ctx):
    rules = [("r1", 443 if v != "incomplete" else 22, [DOC], "allow", 200)]
    if v == "nonconforming":
        rules.append(("r2", 443, ["0.0.0.0/0"], "deny", 100))
    _path(c, v, True, True, rules)
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(source="203.0.113.10/32")}}
    if v == "incomplete":
        c.missing("rs1", "rules", "READ_MASK", "as demais regras de firewall da rede (e políticas de firewall de rede "
                  "e hierárquicas) não foram lidas; só r1 (porta 22) foi lida")
    return c.done(cost_class="low")


@R("CQ-NET-02")
def net02(v, c: Ctx):
    if v == "nonconforming":
        return na("o firewall do GCP não tem regra sem estado",
                  schema_attr_absent("google", "google_compute_firewall", r"(stateless|state_tracking|tracking|"
                                     r"connection_state)", "regra de firewall VPC sem atributo de estado"),
                  schema_attr_absent("google", "google_compute_network_firewall_policy_rule",
                                     r"(stateless|state_tracking|tracking)", "regra de política de firewall idem"),
                  GCP_FW_STATEFUL)
    if v == "incomplete":
        return na("o estado de conexão não é declarável no GCP e o mecanismo é documentado como sempre com estado: "
                  "a situação 'estado não declarado e padrão sem evidência' não existe",
                  schema_attr_absent("google", "google_compute_firewall", r"(stateless|state_tracking|tracking|"
                                     r"connection_state)", "não há atributo de estado para deixar sem declarar"),
                  GCP_FW_STATEFUL)
    n = net(c, entity="rs1")
    c.map("rs1", f"{n.address}#firewall")
    fw(c, "r1", n, 443, [DOC])
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(protocol=None)}}
    c.dev.append("estado de conexão vem do mecanismo (firewall VPC sempre com estado), não de atributo da regra; "
                 "avaliação do GCP é por prioridade com permitir/negar, não só permitir — a regra única permite F")
    c.evidence.append(GCP_FW_STATEFUL)
    return c.done("INTERPRETED")


@R("CQ-NET-03")
def net03(v, c: Ctx):
    if v == "conforming":
        _path(c, v, True, True, [("r1", 443, ["0.0.0.0/0"], "allow", 200)])
    elif v == "nonconforming":
        _path(c, v, False, False, [("r1", 443, ["0.0.0.0/0"], "allow", 1000)])
    else:
        _path(c, v, True, None, [("r1", 443, ["0.0.0.0/0"], "allow", 1000)])
        c.missing("rt1", "route_table", "SYMBOLIC_INPUT", "se a rede mantém a rota padrão para a internet vem de "
                  "variável sem valor (delete_default_routes_on_create)", _find(c, "x_net"))
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(source="198.51.100.20/32",
                                                         protocol="tcp" if v == "conforming" else None)}}
    return c.done(cost_class="low")


@R("CQ-NET-04")
def net04(v, c: Ctx):
    na_, nb, sa_, sb = _two_nets(c)
    tag = Tpl("${var.run_id}-fxtag")
    if v == "conforming":
        vm = instance(c, "vm1", [nic_block(sa_), nic_block(sb)], tags=[tag])
        c.map("nic2", f"{vm.address}#network_interface[1]")
    elif v == "nonconforming":
        vm = instance(c, "vm1", [nic_block(sa_)])
        vm2 = instance(c, "vm2", [nic_block(sb)], tags=[tag])
        c.map("nic3", f"{vm2.address}#network_interface[0]")
    else:
        ext = c.symvar("nic2_subnetwork")
        vm = instance(c, "vm1", [nic_block(sa_), nic_block(ext)], tags=[tag])
        c.map("nic2", f"{vm.address}#network_interface[1]")
        c.missing("nic2", "attachment", "EXTERNAL_REFERENCE", "a sub-rede (e a rede) da segunda interface vem de "
                  "variável; não se sabe se a regra da rede B a alcança", vm.address)
    c.map("nic1", f"{vm.address}#network_interface[0]")
    c.r("google_compute_firewall", "rs1", {"name": c.name("rs1"), "network": nb.ref("id"), "direction": "INGRESS",
                                           "source_ranges": [DOC], "target_tags": [tag]},
        [Block("allow", {"protocol": "tcp", "ports": ["443"]})], entity="rs1")
    c.dev.append("a regra da rede B seleciona a instância pela etiqueta e vale pela interface ligada à rede B "
                 "(aplicação por rede + rótulo, não por anexação à interface)")
    return c.done("INTERPRETED", cost_class="low")


# ============================================================================ configuração x observação


@R("CQ-CVO-01")
def cvo01(v, c: Ctx):
    b = bucket(c, "c1", blocks=[Block("versioning", {"enabled": True})])
    c.map("d1", f"{b.address}#versioning")
    if v == "incomplete":
        c.missing("c1", "observation", "READ_MASK", "nenhuma leitura de volta (storage.buckets.get) foi feita",
                  b.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done()
    obs = "enabled" if v == "conforming" else "disabled"
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": b.address, "field": "versioning.enabled", "value": obs},
        "act": {"observed_at": OBS_AT, "api": "storage.buckets.get"}}}}
    if v == "nonconforming":
        return c.done(deployable=False, deploy_note="divergência exige mudança fora do Terraform depois do apply: "
                                                    "só offline com observação gravada")
    return c.done()


@R("CQ-CVO-02", "CQ-LOSS-03")
def configured_value(v, c: Ctx):
    sid = "c1" if c.cq_id == "CQ-CVO-02" else "s1"
    if v == "conforming":
        b = bucket(c, sid, blocks=[Block("versioning", {"enabled": True})])
    elif v == "nonconforming":
        b = bucket(c, sid)
        c.dev.append("sem bloco versioning o valor vem do padrão do provedor (desligado)")
    else:
        b = bucket(c, sid, blocks=[Block("versioning", {"enabled": c.symvar("versioning", "bool")})])
        c.missing(sid, "value", "SYMBOLIC_INPUT", "versioning.enabled vem de variável sem valor", b.address)
    if c.cq_id == "CQ-LOSS-03":
        c.map(sid, f"{b.address}#versioning")
        c.map("t1", "probe:target")
        c.probe = {"kind": "translation", "inputs": {"target": {"required": True, "from_spec": "t1 da fixture"}}}
    return c.done()


@R("CQ-CVO-03")
def cvo03(v, c: Ctx):
    i = c.r("google_sql_database_instance", "i1",
            {"name": c.name("i1"), "region": L1, "database_version": "POSTGRES_16", "deletion_protection": False},
            [Block("settings", {"tier": "db-f1-micro", "edition": "ENTERPRISE"})], entity="i1")
    c.synth[f"{i.address}#deletion_protection"] = "teardown (SAFETY)"
    if v == "conforming":
        t = c.r("google_pubsub_topic", "t1", {"name": c.name("t1")}, entity="t1")
        ch = _alert(c, t)
        cond = Block("conditions", {"display_name": "cpu"}, [Block("condition_threshold", {
            "filter": Tpl('resource.type = \\"cloudsql_database\\" AND resource.labels.database_id = \\"${var.project}:${'
                          + i.address + '.name}\\" AND metric.type = \\"cloudsql.googleapis.com/database/cpu/utilization\\"'),
            "comparison": "COMPARISON_GT", "threshold_value": 0.9, "duration": "300s"},
            [Block("aggregations", {"alignment_period": "60s", "per_series_aligner": "ALIGN_MEAN"})])])
        c.r("google_monitoring_alert_policy", "al1", {"display_name": Tpl("${var.run_id} " + c.fid), "combiner": "OR",
                                                      "notification_channels": [ch.ref("id")]}, [cond], entity="al1")
        return c.done(cost_class="low")
    c.map("s1", PROJECT_IMPLICIT)
    if v == "nonconforming":
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "monitoring.alertPolicies.list",
                                                               "complete": True}}}
    else:
        c.missing("s1", "alarm", "READ_MASK", "as políticas de alerta do projeto não foram lidas (leitura parcial "
                  "declarada)")
    return c.done(cost_class="low")


@R("CQ-CVO-04")
def cvo04(v, c: Ctx):
    a = {"name": c.name("i1"), "region": L1, "database_version": "POSTGRES_16", "deletion_protection": False}
    if v == "conforming":
        sec = c.x("google_secret_manager_secret", "secret", {"secret_id": c.name("secret")},
                  [Block("replication", {}, [Block("auto", {})])],
                  why="contêiner do segredo; a versão (valor) é criada pelo runner na hora e nunca gravada")
        ver = c.x("google_secret_manager_secret_version", "secret_value", {"secret": sec.ref("id")}, kind="data",
                  why="lê o valor do segredo no plano para o atributo; o valor é Withheld")
        a["root_password"] = ver.ref("secret_data")
    elif v == "incomplete":
        a["root_password"] = c.symvar("root_password")
    i = c.r("google_sql_database_instance", "i1", a,
            [Block("settings", {"tier": "db-f1-micro", "edition": "ENTERPRISE"})], entity="i1")
    c.synth[f"{i.address}#deletion_protection"] = "teardown (SAFETY)"
    c.map("k1", f"{i.address}#root_password")
    if v == "incomplete":
        c.missing("k1", "secret", "SYMBOLIC_INPUT", "root_password vem de variável sem valor (pode ser nula): "
                  "presença não lida", i.address)
        return c.done(cost_class="low")
    if v == "conforming":
        return c.done(cost_class="low", deploy_note="a versão do segredo é gerada pelo runner na hora (SAFETY)")
    c.dev.append("sem root_password o usuário administrativo fica sem senha definida sob leitura completa")
    return c.done(cost_class="low")


# ============================================================================ perda


def _log_bucket(c: Ctx, lid: str, days, entity: str):
    return c.r("google_logging_project_bucket_config", lid, {"project": Var("project"), "location": "global",
                                                              "bucket_id": c.name(lid, sep="_"),
                                                              "retention_days": days}, entity=entity)


@R("CQ-LOSS-01")
def loss01(v, c: Ctx):
    days = {"conforming": 30, "nonconforming": 400, "incomplete": 30}[v]
    s = _log_bucket(c, "s1", days, "s1")
    c.map("t1", "probe:target")
    tgt = {"conforming": {"unit": "second", "domain_max": "31536000_second"},
           "nonconforming": {"domain_max": "365_day"}, "incomplete": {}}[v]
    c.probe = {"kind": "translation", "inputs": {"target": {**tgt, "from_spec": "t1 da fixture"}}}
    if v == "incomplete":
        c.missing("s1", "correspondence", "EVIDENCE_GAP", "a correspondência de retention_days com o destino não "
                  "tem prova (UNPROVEN); o valor de origem existe", s.address)
        c.dev.append("o valor de origem (30 dias) está presente; a falta é da prova da correspondência")
    return c.done()


@R("CQ-LOSS-02")
def loss02(v, c: Ctx):
    n = net(c, entity="rs1")
    c.map("rs1", f"{n.address}#firewall")
    fw(c, "r1", n, 22, ["0.0.0.0/0"], action="deny", priority=100)
    c.map("tgt", "probe:target")
    sup = {"conforming": True, "nonconforming": False, "incomplete": "unknown"}[v]
    c.probe = {"kind": "translation", "inputs": {"target": {"supports_deny": sup, "from_spec": "tgt da fixture"}}}
    if v == "incomplete":
        c.missing("tgt", "target_semantics", "EVIDENCE_GAP", "o destino abstrato da especificação não tem evidência de "
                  "exprimir negação")
    return c.done()


@R("CQ-LOSS-04")
def loss04(v, c: Ctx):
    if v == "nonconforming":
        return na("o GCP não exprime retenção em meses de calendário: durações são segundos ou dias inteiros",
                  GCP_DURATION)
    c.map("t1", "probe:target")
    c.probe = {"kind": "translation", "inputs": {"target": {"unit": "second", "from_spec": "t1 da fixture"}}}
    if v == "conforming":
        _log_bucket(c, "s1", 7, "s1")
        return c.done()
    b = bucket(c, "s1", blocks=[Block("lifecycle_rule", {}, [Block("condition", {"age": 30}),
                                                             Block("action", {"type": "Delete"})])])
    c.map("s1", f"{b.address}#lifecycle_rule.condition.age")
    c.missing("s1", "unit", "EVIDENCE_GAP", "lifecycle_rule.condition.age = 30 não traz a unidade no nome nem no "
              "schema; o UNITS ainda não determinou a unidade", b.address)
    return c.done()


# ============================================================================ provedor novo


@R("CQ-NEW-01")
def new01(v, c: Ctx):
    c.map("p4", "implicit:provedor google no papel de provedor retirado (P4)")
    if v == "conforming":
        b = bucket(c, "x_c", entity="s1", blocks=[Block("versioning", {"enabled": True})])
        c.map("s1", f"{b.address}#versioning")
        c.map("k1", "probe:concept.k1")
        c.probe = {"kind": "static", "inputs": {"concept": {"k1": {"label": "versionamento de objetos",
                                                                   "exclusive": False}}}}
        return c.done()
    if v == "nonconforming":
        b = bucket(c, "x_c", entity="s2", location="NAM4", extra={"rpo": "ASYNC_TURBO"})
        c.map("s2", f"{b.address}#rpo")
        c.map("k2", "probe:concept.k2")
        c.probe = {"kind": "static", "inputs": {"concept": {"k2": {
            "label": "replicação turbo com RPO garantido de bucket birregional", "exclusive": True,
            "note": "exclusividade é hipótese da fixture; o GLOSSARY confirma"}}}}
        return c.done("INTERPRETED", deployable=False,
                      deploy_note="bucket birregional com replicação turbo cobra replicação: só com OK")
    b = bucket(c, "x_c", entity="src3", blocks=[Block("ip_filter", {"mode": "Disabled"})])
    c.map("src3", f"{b.address}#ip_filter")
    c.missing("src3", "concept", "EVIDENCE_GAP", "o conceito de ip_filter (filtro de IP do bucket) não foi "
              "determinado: sem âncora no glossário", b.address)
    return c.done("INTERPRETED")


@R("CQ-NEW-03")
def new03(v, c: Ctx):
    c.map("p4", "implicit:provedor google no papel de provedor retirado (P4)")
    if v == "nonconforming":
        return na("o GCP não tem conjunto de regras de filtragem com precedência pela posição textual: toda "
                  "precedência é numérica", GCP_FW_ORDER,
                  schema_attr_absent("google", "google_compute_firewall", r"(order|position|sequence)",
                                     "regra de firewall sem atributo de ordem textual"))
    if v == "conforming":
        n = net(c, entity="rs1")
        c.map("rs1", f"{n.address}#firewall")
        fw(c, "r1", n, 22, ["0.0.0.0/0"], action="deny", priority=100)
        return c.done()
    ext = c.symvar("network")
    pol = c.r("google_compute_network_firewall_policy", "rs1", {"name": c.name("rs1")}, entity="rs1")
    c.r("google_compute_network_firewall_policy_rule", "r1", {
        "firewall_policy": pol.ref("name"), "priority": 100, "action": "deny", "direction": "INGRESS"},
        [Block("match", {"src_ip_ranges": ["0.0.0.0/0"]}, [Block("layer4_configs", {"ip_protocol": "tcp",
                                                                                     "ports": ["22"]})])],
        entity="r1")
    c.x("google_compute_network_firewall_policy_association", "assoc", {
        "name": c.name("assoc"), "firewall_policy": pol.ref("name"), "attachment_target": ext},
        why="associa a política a uma rede vinda de variável")
    c.missing("rs1", "precedence", "EXTERNAL_REFERENCE", "a precedência entre a política e as regras clássicas "
              "depende de network_firewall_policy_enforcement_order da rede associada, que vem de variável e não "
              "foi lida", pol.address)
    return c.done()
