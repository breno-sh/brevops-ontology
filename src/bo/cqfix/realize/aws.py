"""Realização das fixtures das CQs no provider aws 6.71.0 (registry.terraform.io/hashicorp/aws).

Escolhas gerais (cada desvio da situação abstrata vai em Fx.deviations):
- contêiner de objetos = aws_s3_bucket; namespace de armazenamento = a conta (sem recurso próprio);
- conjunto de regras: aws_security_group (só permitir, com estado) ou aws_network_acl (precedência numérica,
  permitir e negar, sem estado), conforme a situação pede;
- escopo de autorização: a AWS não tem hierarquia de escopos que conceda por herança dentro da conta; o escopo
  é o padrão de ARN no elemento Resource (pai = padrão que contém o do filho) — realização INTERPRETED;
- localização: atributo region por recurso (aws 6.x), ligado às variáveis de contexto location_1/location_2.
"""
from __future__ import annotations

from ..hcl import Block, Json, Ref, Tpl, Var
from ..model import doc_citation, schema_attr_absent
from .base import Ctx, na, reg

PROVIDER = "aws"
VERSION = "6.71.0"
REALIZERS: dict = {}

CONTEXT_VARS = {
    "run_id": "identificador curto da execução (prefixo de nomes e tag bo_run); ligado pelo runner",
    "location_1": "localização l1 das fixtures (região); ligada pelo runner",
    "location_2": "localização l2, distinta de l1; ligada pelo runner",
}

DOC = "203.0.113.0/24"
AMI_PARAM = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"

ALLOWED_TYPES = {
    # rede (lote A: VPC, SG; NAT/EIP só onde a fixture exige endereço público)
    "aws_vpc": {"category": "VPC", "cost_class": "free"},
    "aws_subnet": {"category": "VPC", "cost_class": "free"},
    "aws_internet_gateway": {"category": "VPC", "cost_class": "free"},
    "aws_route_table": {"category": "VPC", "cost_class": "free"},
    "aws_route": {"category": "VPC", "cost_class": "free"},
    "aws_route_table_association": {"category": "VPC", "cost_class": "free"},
    "aws_network_interface": {"category": "VPC", "cost_class": "free"},
    "aws_network_interface_attachment": {"category": "VPC", "cost_class": "free"},
    "aws_eip": {"category": "VPC (endereço público)", "cost_class": "low"},
    "aws_security_group": {"category": "SG", "cost_class": "free"},
    "aws_vpc_security_group_ingress_rule": {"category": "SG", "cost_class": "free"},
    "aws_vpc_security_group_egress_rule": {"category": "SG", "cost_class": "free"},
    "aws_network_acl": {"category": "VPC", "cost_class": "free"},
    "aws_network_acl_rule": {"category": "VPC", "cost_class": "free"},
    "aws_flow_log": {"category": "logs", "cost_class": "low"},
    "aws_networkfirewall_rule_group": {"category": "SG (grupo de regras sem firewall; sem custo por hora)",
                                       "cost_class": "free"},
    # computação mínima (fixtures de interface e caminho; precisam de GO do Breno no DEP)
    "aws_instance": {"category": "computação mínima (t4g.nano)", "cost_class": "low"},
    "data.aws_ssm_parameter": {"category": "leitura de AMI pública", "cost_class": "free"},
    # armazenamento de objetos
    "aws_s3_bucket": {"category": "S3", "cost_class": "free"},
    "aws_s3_bucket_versioning": {"category": "S3", "cost_class": "free"},
    "aws_s3_bucket_public_access_block": {"category": "S3", "cost_class": "free"},
    "aws_s3_account_public_access_block": {"category": "S3 (singleton da conta; só offline)", "cost_class": "free"},
    "aws_s3_bucket_policy": {"category": "S3", "cost_class": "free"},
    "aws_s3_bucket_lifecycle_configuration": {"category": "S3", "cost_class": "free"},
    "aws_s3_bucket_intelligent_tiering_configuration": {"category": "S3", "cost_class": "free"},
    "aws_s3_bucket_object_lock_configuration": {"category": "S3", "cost_class": "free"},
    "aws_s3_bucket_accelerate_configuration": {"category": "S3", "cost_class": "free"},
    "aws_s3_bucket_request_payment_configuration": {"category": "S3", "cost_class": "free"},
    "data.aws_s3_bucket": {"category": "S3 (leitura)", "cost_class": "free"},
    # IAM
    "aws_iam_user": {"category": "IAM", "cost_class": "free"},
    "aws_iam_group": {"category": "IAM", "cost_class": "free"},
    "aws_iam_user_group_membership": {"category": "IAM", "cost_class": "free"},
    "aws_iam_policy": {"category": "IAM", "cost_class": "free"},
    "aws_iam_user_policy": {"category": "IAM", "cost_class": "free"},
    "aws_iam_user_policy_attachment": {"category": "IAM", "cost_class": "free"},
    "aws_iam_group_policy_attachment": {"category": "IAM", "cost_class": "free"},
    "aws_iam_policy_attachment": {"category": "IAM", "cost_class": "free"},
    "aws_iam_role": {"category": "IAM", "cost_class": "free"},
    "aws_iam_role_policy": {"category": "IAM", "cost_class": "free"},
    "aws_iam_role_policy_attachment": {"category": "IAM", "cost_class": "free"},
    "aws_iam_user_login_profile": {"category": "IAM", "cost_class": "free"},
    "aws_iam_access_key": {"category": "IAM", "cost_class": "free"},
    "aws_iam_saml_provider": {"category": "IAM", "cost_class": "free"},
    # mensageria, logs, alarmes, chaves
    "aws_sqs_queue": {"category": "SQS", "cost_class": "free"},
    "data.aws_sqs_queue": {"category": "SQS (leitura)", "cost_class": "free"},
    "aws_sns_topic": {"category": "SNS", "cost_class": "free"},
    "aws_cloudwatch_log_group": {"category": "logs", "cost_class": "free"},
    "aws_cloudwatch_metric_alarm": {"category": "alarmes", "cost_class": "free"},
    "aws_cloudwatch_event_rule": {"category": "alarmes (EventBridge)", "cost_class": "free"},
    "aws_cloudwatch_event_target": {"category": "alarmes (EventBridge)", "cost_class": "free"},
    "aws_kms_key": {"category": "KMS (rateado)", "cost_class": "low"},
    "aws_dynamodb_table": {"category": "DynamoDB sob demanda", "cost_class": "free"},
    # balanceador e banco (lote B)
    "aws_lb": {"category": "ALB (lote B)", "cost_class": "low"},
    "aws_lb_listener": {"category": "ALB (lote B)", "cost_class": "free"},
    "aws_lb_listener_rule": {"category": "ALB (lote B)", "cost_class": "free"},
    "aws_lb_target_group": {"category": "ALB (lote B)", "cost_class": "free"},
    "aws_lb_target_group_attachment": {"category": "ALB (lote B)", "cost_class": "free"},
    "aws_db_subnet_group": {"category": "RDS (lote B)", "cost_class": "free"},
    "aws_db_instance": {"category": "RDS t4g.micro (lote B)", "cost_class": "low"},
    "aws_rds_cluster": {"category": "RDS Aurora sem instância (lote B; só armazenamento)", "cost_class": "low"},
}

SKU_RULES = {
    ("aws_instance", "instance_type"): ["t4g.nano"],
    ("aws_db_instance", "instance_class"): ["db.t4g.micro"],
    ("aws_db_instance", "allocated_storage"): [20],
    ("aws_db_instance", "multi_az"): [False],
    ("aws_dynamodb_table", "billing_mode"): ["PAY_PER_REQUEST"],
    ("aws_lb", "load_balancer_type"): ["application"],
    ("aws_kms_key", "multi_region"): [False],
    ("aws_s3_bucket", "force_destroy"): [True],
}


def header() -> str:
    return f'''terraform {{
  required_version = "= 1.15.8"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "= {VERSION}"
    }}
  }}
}}

provider "aws" {{
  region = var.location_1
  default_tags {{
    tags = {{
      bo_run    = var.run_id
      bo_module = "CQFIX"
    }}
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
'''


R = lambda *q: reg(REALIZERS, *q)  # noqa: E731

# ----------------------------------------------------------------------------- ajudantes


def bucket(c: Ctx, lid: str, key: str | None = None, entity: bool = True, region=None):
    a = {"bucket": c.name(key or lid), "force_destroy": True}
    if region is not None:
        a["region"] = region
    b = c.r("aws_s3_bucket", lid, a, entity=lid if entity else None,
            synth=None if entity else "contêiner auxiliar exigido pela situação")
    c.synth[f"{b.address}#force_destroy"] = "segurança de teardown (SAFETY): apagar com objetos"
    return b


def versioning(c: Ctx, lid: str, b, status, entity: str | None = None, synth: str | None = None):
    return c.r("aws_s3_bucket_versioning", lid, {"bucket": b.ref("id")},
               [Block("versioning_configuration", {"status": status})], entity=entity, synth=synth)


def vpc(c: Ctx, lid: str = "x_vpc", cidr: str = "10.20.0.0/16", entity: str | None = None):
    return c.r("aws_vpc", lid, {"cidr_block": cidr}, entity=entity,
               synth=None if entity else "rede exigida pelo schema (sub-rede e grupo de segurança precisam de vpc_id)")


def subnet(c: Ctx, lid: str, v, cidr: str, entity: str | None = None, az_index: int | None = None):
    a = {"vpc_id": v.ref("id"), "cidr_block": cidr}
    if az_index is not None:
        a["availability_zone"] = Tpl("${var.location_1}" + "abc"[az_index])
    return c.r("aws_subnet", lid, a, entity=entity,
               synth=None if entity else "sub-rede exigida pelo schema (interface precisa de subnet_id)")


def ami(c: Ctx):
    for r in c.res:
        if r.kind == "data" and r.type == "aws_ssm_parameter":
            return r
    return c.x("aws_ssm_parameter", "ami", {"name": AMI_PARAM}, kind="data",
               why="AMI pública lida no parâmetro SSM público; instância precisa de ami")


def nic(c: Ctx, lid: str, sn, sgs=None, entity: str | None = None, extra: dict | None = None):
    a = {"subnet_id": sn.ref("id") if hasattr(sn, "ref") else sn}
    if sgs is not None:
        a["security_groups"] = sgs
    a.update(extra or {})
    return c.r("aws_network_interface", lid, a, entity=entity or lid)


def instance(c: Ctx, lid: str, primary_nic, img=None, entity: str | None = None):
    img = img or ami(c)
    return c.r("aws_instance", lid, {"ami": img.ref("value"), "instance_type": "t4g.nano"},
               [Block("primary_network_interface", {"network_interface_id": primary_nic.ref("id")})],
               entity=entity or lid)


def attach(c: Ctx, lid: str, n, inst, idx: int, instance_id=None):
    return c.x("aws_network_interface_attachment", lid,
               {"instance_id": instance_id if instance_id is not None else inst.ref("id"),
                "network_interface_id": n.ref("id"), "device_index": idx},
               why=f"relação attached_to ({n.label} -> instância) com device_index {idx}")


def sg(c: Ctx, lid: str, v, ingress=(), entity: str | None = None, name_lid: str | None = None):
    blocks = []
    for r in ingress:
        blocks.append(Block("ingress", {"protocol": r.get("protocol", "tcp"), "from_port": r["port"],
                                        "to_port": r["port"], "cidr_blocks": r["cidrs"]}))
    return c.r("aws_security_group", lid, {"name": c.name(name_lid or lid), "vpc_id": v.ref("id")}, blocks,
               entity=entity or lid)


def sg_rule(c: Ctx, lid: str, g, port, cidr, entity: str | None = None, protocol: str = "tcp"):
    return c.r("aws_vpc_security_group_ingress_rule", lid,
               {"security_group_id": g.ref("id"), "ip_protocol": protocol, "from_port": port, "to_port": port,
                "cidr_ipv4": cidr}, entity=entity or lid)


def nacl_rule(c: Ctx, lid: str, acl, number, action, port, cidr, egress=False, entity: str | None = None,
              synth: str | None = None):
    a = {"network_acl_id": acl.ref("id"), "rule_number": number, "egress": egress, "protocol": "tcp",
         "rule_action": action, "cidr_block": cidr}
    if isinstance(port, tuple):
        a["from_port"], a["to_port"] = port
    else:
        a["from_port"] = a["to_port"] = port
    return c.r("aws_network_acl_rule", lid, a, entity=entity, synth=synth)


def user(c: Ctx, lid: str, entity: str | None = None):
    return c.r("aws_iam_user", lid, {"name": c.name(lid)}, entity=entity or lid)


def s3_read_policy(c: Ctx, lid: str, resources, entity: str | None = None, synth: str | None = None,
                   action: str = "s3:GetObject"):
    doc = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": [action], "Resource": resources}]}
    return c.r("aws_iam_policy", lid, {"name": c.name(lid), "policy": Json(doc)}, entity=entity, synth=synth)


# padrões de ARN da execução montados por format() (o texto não carrega prefixo de ARN literal)
RUN_OBJECTS = Ref('format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)')
RUN_BUCKETS = Ref('format("%s:%s:s3:::%s-*", "arn", "aws", var.run_id)')


def arn_objects(b) -> Tpl:
    return Tpl("${" + b.address + ".arn}/*")


def flow(direction="ingress", protocol="tcp", port=443, source="203.0.113.10/32") -> dict:
    d = {"direction": direction, "port": port, "source_cidr": source}
    if protocol:
        d["protocol"] = protocol
    return d


AWS_S3_NAMES = doc_citation(
    "https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html",
    "nome de bucket S3 é único em toda a partição (todas as contas e regiões): dois buckets com a mesma chave "
    "local em regiões diferentes não podem coexistir")
AWS_SG_STATEFUL = doc_citation(
    "https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html",
    "grupo de segurança é sempre com estado e só permite; NACL é sempre sem estado; o estado não é atributo "
    "declarável por regra")
AWS_IAM_EVAL = doc_citation(
    "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html",
    "negação explícita em qualquer política aplicável vence permissão; o escopo de uma concessão é o "
    "elemento Resource (padrão de ARN), sem hierarquia de escopos que conceda por herança")

# ============================================================================ CIS


@R("CQ-CIS-01")
def cis_mfa(v, c: Ctx):
    u = user(c, "u1")
    lp_attrs = {"user": u.ref("name"), "password_reset_required": True}
    if v == "nonconforming":
        lp = c.r("aws_iam_user_login_profile", "d1", lp_attrs, entity="d1")
    else:
        lp = c.x("aws_iam_user_login_profile", "console", lp_attrs,
                 why="acesso de console do principal humano (o controle CIS vale para quem tem senha de console)")
    c.dev.append("CIS AWS 2.9 audita o dispositivo MFA do usuário (relatório de credenciais); a configuração "
                 "Terraform equivalente é a política que nega tudo sem aws:MultiFactorAuthPresent")
    if v == "nonconforming":
        c.dev.append("d1 = o perfil de console sem política que exija MFA (a configuração lida do usuário)")
        return c.done("INTERPRETED", deploy_note="senha de console gerada vai ao state: só com redator (SAFETY)")
    cond = True if v == "conforming" else c.symvar("mfa_required", "bool")
    doc = {"Version": "2012-10-17", "Statement": [{
        "Sid": "DenyWithoutMFA", "Effect": "Deny", "NotAction": ["iam:ChangePassword", "sts:GetSessionToken"],
        "Resource": "*", "Condition": {"BoolIfExists": {"aws:MultiFactorAuthPresent": "false"}}}]}
    if v == "incomplete":
        doc["Statement"][0]["Condition"] = {"BoolIfExists": {"aws:MultiFactorAuthPresent": Tpl(
            "${" + cond.expr + " ? \"false\" : \"true\"}")}}
        c.missing("d1", "value", "SYMBOLIC_INPUT", "a condição da política vem de variável sem valor",
                  f"aws_iam_user_policy.{c.lab('d1')}")
    c.r("aws_iam_user_policy", "d1", {"name": c.name("d1"), "user": u.ref("name"), "policy": Json(doc)},
        entity="d1")
    return c.done("INTERPRETED", deploy_note="senha de console gerada vai ao state: só com redator (SAFETY)")


@R("CQ-CIS-02")
def cis_key_age(v, c: Ctx):
    u = user(c, "p1")
    k = c.r("aws_iam_access_key", "k1", {"user": u.ref("name")}, entity="k1")
    c.synth[f"{k.address}#secret"] = "o segredo gerado é Withheld: nunca lido nem gravado"
    if v == "incomplete":
        c.missing("k1", "observation", "READ_MASK", "nenhuma leitura datada (ListAccessKeys/GetAccessKeyLastUsed) "
                  "foi feita; a idade não existe sem observação", k.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done("STRUCTURAL", deploy_note="chave de acesso: segredo só com redator (SAFETY)")
    age = 10 if v == "conforming" else 120
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": k.address, "field": "create_date", "age_days": age},
        "act": {"observed_at": "2026-11-02T10:00:00-03:00", "api": "iam:ListAccessKeys"}}}}
    if v == "nonconforming":
        return c.done("STRUCTURAL", deployable=False,
                      deploy_note="idade de 120 dias não se produz num deploy novo: só offline com observação gravada")
    return c.done("STRUCTURAL", deploy_note="chave de acesso: segredo só com redator (SAFETY)")


@R("CQ-CIS-03")
def cis_kms(v, c: Ctx):
    a = {"description": Tpl("${var.run_id} " + c.fid), "deletion_window_in_days": 7}
    if v == "conforming":
        a.update({"enable_key_rotation": True, "rotation_period_in_days": 90})
    elif v == "nonconforming":
        a["enable_key_rotation"] = False
    else:
        a["enable_key_rotation"] = c.symvar("rotation", "bool")
    k = c.r("aws_kms_key", "k1", a, entity="k1")
    c.map("d1", f"{k.address}#enable_key_rotation")
    c.synth[f"{k.address}#deletion_window_in_days"] = "teardown: menor janela de exclusão agendada (SAFETY)"
    if v == "incomplete":
        c.missing("d1", "value", "SYMBOLIC_INPUT", "enable_key_rotation vem de variável sem valor", k.address)
    return c.done(cost_class="low")


def _ports(v, c: Ctx, port: int):
    vp = vpc(c)
    g = sg(c, "rs1", vp)
    if v == "incomplete":
        cidr = c.symvar("source_cidr")
        c.missing("r1", "value", "SYMBOLIC_INPUT", "cidr_ipv4 da regra vem de variável sem valor",
                  f"aws_vpc_security_group_ingress_rule.{c.lab('r1')}")
    else:
        cidr = DOC if v == "conforming" else "0.0.0.0/0"
    sg_rule(c, "r1", g, port, cidr)
    return c.done()


@R("CQ-CIS-04")
def cis_ssh(v, c):
    return _ports(v, c, 22)


@R("CQ-CIS-05")
def cis_rdp(v, c):
    return _ports(v, c, 3389)


@R("CQ-CIS-06")
def cis_flow(v, c: Ctx):
    vp = vpc(c, "vn1", entity="vn1")
    sn = subnet(c, "sa", vp, "10.20.1.0/24", entity="sa")
    if v == "nonconforming":
        c.map("s1", "implicit:conta sintética e região location_1, leitura completa declarada dos flow logs")
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "ec2:DescribeFlowLogs", "complete": True}}}
        return c.done()
    lg = c.x("aws_cloudwatch_log_group", "flowlogs", {"name": c.name("flowlogs", sep="/"), "retention_in_days": 1},
             why="destino do registro de fluxo (aws_flow_log exige log_destination)")
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
                                                      "Principal": {"Service": "vpc-flow-logs.amazonaws.com"}}]}
    role = c.x("aws_iam_role", "flowlogs", {"name": c.name("flowrole"), "assume_role_policy": Json(trust)},
               why="papel que o serviço de flow logs assume para escrever no grupo de logs")
    pol = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Resource": "*", "Action": [
        "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]}]}
    c.x("aws_iam_role_policy", "flowlogs", {"name": c.name("flowpol"), "role": role.ref("id"), "policy": Json(pol)},
        why="permissão de escrita do papel do flow log")
    a = {"subnet_id": sn.ref("id"), "traffic_type": "ALL", "log_destination": lg.ref("arn"),
         "iam_role_arn": role.ref("arn")}
    if v == "incomplete":
        a = {"count": Ref(c.symvar("flow_log_enabled", "bool").expr + " ? 1 : 0"), **a}
        c.missing("d1", "value", "SYMBOLIC_INPUT", "a existência do flow log (count) vem de variável sem valor",
                  f"aws_flow_log.{c.lab('d1')}")
    c.r("aws_flow_log", "d1", a, entity="d1")
    return c.done(cost_class="low")


_SG_EVENTS = ["AuthorizeSecurityGroupIngress", "AuthorizeSecurityGroupEgress", "RevokeSecurityGroupIngress",
              "RevokeSecurityGroupEgress", "CreateSecurityGroup", "DeleteSecurityGroup"]
_ROUTE_EVENTS = ["CreateRoute", "CreateRouteTable", "ReplaceRoute", "ReplaceRouteTableAssociation",
                 "DeleteRouteTable", "DeleteRoute", "DisassociateRouteTable"]


@R("CQ-CIS-07")
def cis_alert(v, c: Ctx):
    c.map("s1", "implicit:conta sintética, barramento de eventos padrão em location_1")
    t = c.r("aws_sns_topic", "t1", {"name": c.name("t1")}, entity="t1")
    if v == "incomplete":
        pattern = c.symvar("event_pattern")
        c.missing("al1", "value", "SYMBOLIC_INPUT", "event_pattern da regra vem de variável sem valor",
                  f"aws_cloudwatch_event_rule.{c.lab('al1')}")
    else:
        names = _SG_EVENTS if v == "conforming" else _ROUTE_EVENTS
        pattern = Json({"source": ["aws.ec2"], "detail-type": ["AWS API Call via CloudTrail"],
                        "detail": {"eventName": names}})
    rule = c.r("aws_cloudwatch_event_rule", "al1", {"name": c.name("al1"), "event_pattern": pattern}, entity="al1")
    c.x("aws_cloudwatch_event_target", "notify", {"rule": rule.ref("name"), "arn": t.ref("arn")},
        why="relação notifies (alarme -> tópico)")
    c.dev.append("CIS AWS 5.10 pede filtro de métrica + alarme sobre a trilha no CloudWatch Logs; a fixture usa "
                 "regra do EventBridge sobre o evento de API de controle, que realiza a mesma situação abstrata "
                 "(alarme sobre o evento de mudança, notificando um tópico) sem exigir trilha")
    if v == "nonconforming":
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "events:ListRules", "complete": True}}}
    return c.done("INTERPRETED")


@R("CQ-CIS-08")
def cis_public(v, c: Ctx):
    b = bucket(c, "c1")
    if v == "incomplete":
        flag = c.symvar("block_public", "bool")
        a = {k: flag for k in ("block_public_acls", "block_public_policy", "ignore_public_acls",
                               "restrict_public_buckets")}
        c.missing("k1", "value", "SYMBOLIC_INPUT", "os quatro bloqueios vêm de variável sem valor",
                  f"aws_s3_bucket_public_access_block.{c.lab('k1')}")
    else:
        flag = v == "conforming"
        a = {k: flag for k in ("block_public_acls", "block_public_policy", "ignore_public_acls",
                               "restrict_public_buckets")}
    pab = c.r("aws_s3_bucket_public_access_block", "k1", {"bucket": b.ref("id"), **a}, entity="k1")
    if v == "nonconforming":
        doc = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
                                                        "Resource": arn_objects(b)}]}
        c.x("aws_s3_bucket_policy", "public", {"bucket": b.ref("id"), "policy": Json(doc)},
            depends_on=[pab.address], why="concessão pública (Principal *) que torna o acesso efetivo")
        return c.done(deploy_note="o bloqueio de acesso público da conta sandbox pode recusar a política; "
                                  "a leitura de volta registra REJECTED_BY_API")
    return c.done()


# ============================================================================ identidade e ciclo de vida

L1, L2 = Var("location_1"), Var("location_2")
ACCOUNT = "implicit:conta sintética (a conta AWS sandbox do runner; nunca um id real)"


@R("CQ-IDL-01")
def idl01(v, c: Ctx):
    if v == "conforming":
        b = bucket(c, "c1", key="data_a")
        versioning(c, "x_versioning", b, "Enabled",
                   synth="faceta versionamento do contêiner (a AWS a declara como recurso separado)")
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "versioning_configuration.status", "before": {"address": b.address, "versioning": "ausente"},
            "after": "main.tf", "plan_action_expected": "update"}}}
        c.dev.append("o versionamento é faceta em recurso separado; o bucket não é recriado (ação no bucket: nenhuma)")
        return c.done()
    if v == "nonconforming":
        b = bucket(c, "c2", key="data_a", region=L2)
        c.map("c1", "probe:change.before")
        c.probe = {"kind": "two_phase", "inputs": {"change": {
            "attribute": "region", "before": {"address": b.address, "region": "var.location_1",
                                              "name": "o mesmo nome (chave local data_a)"},
            "after": "main.tf", "plan_action_expected": "replace"}}}
        c.dev.append("c1 é a leitura anterior (mesmo endereço e nome, location_1); c2 é o recurso do main.tf depois "
                     "da troca de região, que força substituição")
        return c.done()
    b = bucket(c, "c1", key="data_a")
    t = c.x("aws_s3_bucket_intelligent_tiering_configuration", "tiering",
            {"bucket": b.ref("id"), "name": "tier"}, [Block("tiering", {"access_tier": "DEEP_ARCHIVE_ACCESS",
                                                                          "days": 180})],
            why="configuração de camada de armazenamento cujo atributo muda entre as leituras")
    c.probe = {"kind": "two_phase", "inputs": {"change": {
        "attribute": "tiering.access_tier", "before": {"address": t.address, "tiering.access_tier": "ARCHIVE_ACCESS",
                                                       "tiering.days": 90},
        "after": "main.tf", "plan_action_expected": None}}}
    c.missing("c1", "mutability", "EVIDENCE_GAP", "o schema JSON do provider não expõe ForceNew e o SERVICE-EVIDENCE "
              "ainda não tem fato sobre a camada ser mutável no lugar", t.address)
    return c.done()


@R("CQ-IDL-02")
def idl02(v, c: Ctx):
    c.map("acc", ACCOUNT)
    c.map("l1", "implicit:var.location_1")
    c.dev.append("bucket S3 tem nome único na partição: dois contêineres com a mesma chave em regiões diferentes não "
                 "existem; a situação usa aws_sqs_queue, cuja chave local (nome) é única por conta e região")
    c.evidence.append(AWS_S3_NAMES)
    q1 = c.r("aws_sqs_queue", "c1", {"name": Tpl("${var.run_id}-data"), "region": L1}, entity="c1")
    if v == "conforming":
        c.map("l2", "implicit:var.location_2")
        c.r("aws_sqs_queue", "c2", {"name": Tpl("${var.run_id}-data"), "region": L2}, entity="c2")
        return c.done("INTERPRETED")
    if v == "nonconforming":
        c.r("aws_sqs_queue", "c2", {"name": q1.ref("name"), "region": L1}, kind="data", entity="c2")
        c.dev.append("c2 é a segunda leitura (data source) do mesmo recurso: mesma conta, região, tipo e chave")
        return c.done("INTERPRETED")
    reg_unknown = c.symvar("c2_location")
    c.r("aws_sqs_queue", "c2", {"name": Tpl("${var.run_id}-data"), "region": reg_unknown}, kind="data", entity="c2")
    c.missing("c2", "location", "SYMBOLIC_INPUT", "a região da leitura de c2 vem de variável sem valor",
              f"data.aws_sqs_queue.{c.lab('c2')}")
    return c.done("INTERPRETED")


@R("CQ-IDL-03")
def idl03(v, c: Ctx):
    if v == "conforming":
        u = user(c, "p1")
        pol = s3_read_policy(c, "ps1", RUN_OBJECTS, entity="ps1")
        c.r("aws_iam_user_policy_attachment", "a1", {"user": u.ref("name"), "policy_arn": pol.ref("arn")}, entity="a1")
        c.map("s1", "implicit:padrão de ARN do Resource da política (escopo da concessão)")
        c.probe = {"kind": "static", "inputs": {"removal": {"X": "p1", "Y": "a1"}}}
        c.evidence.append(AWS_IAM_EVAL)
        return c.done("INTERPRETED")
    if v == "nonconforming":
        t = c.r("aws_dynamodb_table", "ns1", {"name": c.name("ns1"), "billing_mode": "PAY_PER_REQUEST",
                                              "hash_key": "pk", "range_key": "sk"},
                [Block("attribute", {"name": "pk", "type": "S"}), Block("attribute", {"name": "sk", "type": "S"}),
                 Block("global_secondary_index", {"name": "c1", "projection_type": "KEYS_ONLY"},
                       [Block("key_schema", {"attribute_name": "sk", "key_type": "HASH"})])],
                entity="ns1")
        c.map("c1", f"{t.address}#global_secondary_index[c1]")
        c.dev.append("na AWS o contêiner de objetos não tem namespace com recurso próprio (o namespace é a conta); a "
                     "situação 'componente acaba com o pai' usa tabela DynamoDB (pai) e índice secundário global "
                     "declarado embutido (componente, ciclo de vida preso à tabela)")
        c.probe = {"kind": "static", "inputs": {"removal": {"X": "c1", "Y": "ns1"}}}
        return c.done("INTERPRETED")
    b = bucket(c, "c1")
    s = c.r("aws_s3_bucket_lifecycle_configuration", "s1", {"bucket": b.ref("id")},
            [Block("rule", {"id": "retention", "status": "Enabled"}, [Block("filter", {}),
                                                                      Block("expiration", {"days": 30})])],
            entity="s1")
    c.probe = {"kind": "static", "inputs": {"removal": {"X": "s1", "Y": "c1"}}}
    c.missing("s1", "lifecycle", "EVIDENCE_GAP", "não há fato de SERVICE-EVIDENCE sobre quem controla o ciclo de vida da "
              "configuração de ciclo de vida do bucket (sobrevive ou não à remoção do bucket)", s.address)
    return c.done()


def _rules_sg(c, ports_positions, port_var=None):
    vp = vpc(c)
    blocks = []
    for lid, port, _pos in sorted(ports_positions, key=lambda x: x[2]):
        p = port_var if (port_var is not None and lid == "r1") else port
        blocks.append(Block("ingress", {"protocol": "tcp", "from_port": p, "to_port": p, "cidr_blocks": [DOC]}))
    g = c.r("aws_security_group", "rs1", {"name": c.name("rs1"), "vpc_id": vp.ref("id")}, blocks, entity="rs1")
    return g, [lid for lid, _p, _pos in sorted(ports_positions, key=lambda x: x[2])]


@R("CQ-IDL-04")
def idl04(v, c: Ctx):
    if v == "conforming":
        g, order = _rules_sg(c, [("r1", 443, 2), ("r2", 22, 1)])
        before = [{"rule": "r1", "port": 443}, {"rule": "r2", "port": 22}]
    elif v == "nonconforming":
        g, order = _rules_sg(c, [("r1", 8443, 1), ("r2", 22, 2)])
        before = [{"rule": "r1", "port": 443}, {"rule": "r2", "port": 22}]
    else:
        pv = c.symvar("r1_port", "number")
        g, order = _rules_sg(c, [("r1", 0, 1), ("r2", 22, 2)], port_var=pv)
        before = [{"rule": "r1", "port": 443}, {"rule": "r2", "port": 22}]
        c.missing("r1", "identity_fields", "SYMBOLIC_INPUT", "porta (campo de identidade) da regra r1 vem de variável",
                  g.address)
    for i, lid in enumerate(order):
        c.map(lid, f"{g.address}#ingress[{i}]")
    c.probe = {"kind": "two_phase", "inputs": {"change": {
        "attribute": "ingress (ordem textual)", "before": {"address": g.address, "ingress_in_order": before},
        "after": "main.tf", "plan_action_expected": "none" if v == "conforming" else "update"}}}
    c.dev.append("regras embutidas no grupo de segurança são anônimas (sem identidade própria na API); a ocorrência "
                 "vem dos campos protocolo, portas e origem")
    return c.done()


# ============================================================================ composição


def _vm_chain(c: Ctx, sn_id=None, with_subnet=True, entity_sa="sa", entity_vn="vn1"):
    vp = vpc(c, "vn1" if entity_vn else "x_vpc", entity=entity_vn)
    sn = subnet(c, entity_sa, vp, "10.20.1.0/24", entity=entity_sa) if with_subnet else None
    return vp, sn


@R("CQ-CMP-01")
def cmp01(v, c: Ctx):
    if v == "conforming":
        vp, sn = _vm_chain(c)
        n = nic(c, "nic1", sn)
    elif v == "nonconforming":
        vp = vpc(c, "vn1", entity="vn1")
        n = nic(c, "nic1", "subnet-0a1b2c3d4e5f60789")
        c.dev.append("a sub-rede referenciada (id sintético) não existe na leitura completa; o harness não a cria")
    else:
        ext = c.symvar("subnet_id")
        n = nic(c, "nic1", ext)
        c.map("sa", f"external:var.{c.slug}_subnet_id: sub-rede em escopo não lido")
        c.missing("sa", "scope", "EXTERNAL_REFERENCE", "subnet_id vem de variável: a sub-rede e a cadeia acima dela "
                  "não foram lidas", n.address)
    instance(c, "vm1", n)
    if v == "nonconforming":
        return c.done(deployable=False, deploy_note="dependência obrigatória ausente: o apply tem de falhar; fica "
                                                    "como caso negativo offline", cost_class="low")
    return c.done(cost_class="low")


@R("CQ-CMP-02")
def cmp02(v, c: Ctx):
    vp = vpc(c)
    sn = subnet(c, "x_subnet", vp, "10.20.1.0/24")
    n1 = nic(c, "nic1", sn)
    vm = instance(c, "vm1", n1)
    if v == "conforming":
        n2 = nic(c, "nic2", sn)
        attach(c, "attach2", n2, vm, 1)
    elif v == "incomplete":
        n2 = nic(c, "nic2", sn)
        other = c.symvar("nic2_instance_id")
        attach(c, "attach2", n2, vm, 1, instance_id=other)
        c.missing("nic2", "attachment", "EXTERNAL_REFERENCE", "a anexação de nic2 aponta para instância vinda de "
                  "variável: não se sabe se é vm1", f"aws_network_interface_attachment.{c.lab('x_attach2')}")
    c.dev.append("a interface primária (índice 0) é declarada no bloco primary_network_interface da instância")
    return c.done(cost_class="low")


def _alb_base(c: Ctx):
    vp = vpc(c)
    s1 = subnet(c, "x_subnet_a", vp, "10.20.1.0/24", az_index=0)
    s2 = subnet(c, "x_subnet_b", vp, "10.20.2.0/24", az_index=1)
    c.synth[s2.address] = "o ALB exige sub-redes em duas zonas"
    g = c.x("aws_security_group", "lb", {"name": c.name("lbsg"), "vpc_id": vp.ref("id")},
            why="o ALB exige grupo de segurança")
    lb = c.r("aws_lb", "lb1", {"name": c.name("lb1", maxlen=20), "internal": True, "load_balancer_type": "application",
                                "subnets": [s1.ref("id"), s2.ref("id")], "security_groups": [g.ref("id")]},
             entity="lb1")
    c.map("fe1", f"{lb.address}#frontend (endereços e DNS do ALB; sem recurso próprio)")
    return vp, s1, lb


@R("CQ-CMP-03")
def cmp03(v, c: Ctx):
    vp, s1, lb = _alb_base(c)
    tg = c.r("aws_lb_target_group", "pool1", {"name": c.name("pool1", maxlen=20), "port": 80, "protocol": "HTTP",
                                               "vpc_id": vp.ref("id"), "target_type": "instance"},
             [Block("health_check", {"enabled": True, "path": "/", "protocol": "HTTP"})], entity="pool1")
    c.map("hp1", f"{tg.address}#health_check")
    li = c.r("aws_lb_listener", "li1", {"load_balancer_arn": lb.ref("arn"), "port": 443, "protocol": "HTTP"},
             [Block("default_action", {"type": "fixed-response"}, [Block("fixed_response", {
                 "content_type": "text/plain", "status_code": "404"})])], entity="li1")
    cond = [Block("condition", {}, [Block("path_pattern", {"values": ["/*"]})])]
    c.r("aws_lb_listener_rule", "ru1", {"listener_arn": li.ref("arn"), "priority": 100},
        [Block("action", {"type": "forward", "target_group_arn": tg.ref("arn")})] + cond, entity="ru1")
    c.dev.append("listener na porta 443 com protocolo HTTP (a fixture não pede TLS); regra com path_pattern /* "
                 "realiza match any")
    if v == "conforming":
        n = nic(c, "x_nic", s1, entity=None)
        c.synth.pop(n.address, None)
        c.emap.pop("x_nic", None)
        c.synth[n.address] = "interface primária da instância membro"
        vm = instance(c, "vm1", n)
        c.x("aws_lb_target_group_attachment", "member", {"target_group_arn": tg.ref("arn"), "target_id": vm.ref("id")},
            why="relação member_of_pool (vm1 -> pool1)")
    elif v == "incomplete":
        c.missing("pool1", "membership", "READ_MASK", "membros do pool são registrados fora desta configuração "
                  "(RegisterTargets) e a leitura não incluiu DescribeTargetHealth", tg.address)
    return c.done(cost_class="low")


@R("CQ-CMP-04")
def cmp04(v, c: Ctx):
    c.dev.append("a AWS não tem namespace de armazenamento com versionamento próprio; o nível 'namespace' é a conta e "
                 "a configuração declarada nele que vale para os contêineres é o bloqueio de acesso público da conta "
                 "(setting_kind public_access no lugar de versioning)")
    if v == "conforming":
        b = bucket(c, "c1")
        c.map("ns1", ACCOUNT)
        c.r("aws_s3_account_public_access_block", "k1", {"block_public_acls": True, "block_public_policy": True,
                                                          "ignore_public_acls": True, "restrict_public_buckets": True},
            entity="k1")
        return c.done("INTERPRETED", deployable=False,
                      deploy_note="singleton da conta inteira: aplicar muda a conta sandbox; só offline")
    if v == "nonconforming":
        bucket(c, "c1")
        b2 = bucket(c, "c2")
        c.map("ns1", ACCOUNT)
        c.r("aws_s3_bucket_public_access_block", "k1", {"bucket": b2.ref("id"), "block_public_acls": True,
                                                         "block_public_policy": True, "ignore_public_acls": True,
                                                         "restrict_public_buckets": True}, entity="k1")
        return c.done("INTERPRETED")
    ext = c.symvar("c1_bucket")
    c.r("aws_s3_bucket", "c1", {"bucket": ext}, kind="data", entity="c1")
    c.map("ns1", ACCOUNT)
    c.r("aws_s3_account_public_access_block", "k1", {"block_public_acls": True, "block_public_policy": True,
                                                      "ignore_public_acls": True, "restrict_public_buckets": True},
        entity="k1")
    c.missing("c1", "membership", "EXTERNAL_REFERENCE", "c1 é lido por nome vindo de variável: a conta (namespace) a "
              "que pertence não foi lida", f"data.aws_s3_bucket.{c.lab('c1')}")
    return c.done("INTERPRETED", deployable=False, deploy_note="singleton da conta inteira: só offline")


def _db_subnets(c: Ctx):
    vp = vpc(c)
    s1 = subnet(c, "x_subnet_a", vp, "10.20.1.0/24", az_index=0)
    s2 = subnet(c, "x_subnet_b", vp, "10.20.2.0/24", az_index=1)
    c.synth[s2.address] = "o grupo de sub-redes de banco exige duas zonas"
    return c.x("aws_db_subnet_group", "db", {"name": c.name("dbsn"), "subnet_ids": [s1.ref("id"), s2.ref("id")]},
               why="grupo de sub-redes exigido pela instância/cluster de banco")


def rds(c: Ctx, lid: str, entity: str | None = None, extra: dict | None = None, synth: str | None = None):
    g = _db_subnets(c)
    a = {"identifier": c.name(lid), "engine": "postgres", "instance_class": "db.t4g.micro", "allocated_storage": 20,
         "db_subnet_group_name": g.ref("name"), "username": "boadmin", "manage_master_user_password": True,
         "skip_final_snapshot": True, "multi_az": False}
    a.update(extra or {})
    r = c.r("aws_db_instance", lid, a, entity=entity, synth=synth)
    c.synth[f"{r.address}#skip_final_snapshot"] = "teardown sem snapshot residual (SAFETY)"
    return r


@R("CQ-CMP-05")
def cmp05(v, c: Ctx):
    if v == "conforming":
        i = rds(c, "i1", entity="i1", extra={"db_name": "db1"})
        c.map("db1", f"{i.address}#db_name")
        c.dev.append("engine_b = postgres (motor abstrato)")
        return c.done(cost_class="low")
    g = _db_subnets(c)
    lid = "srv1" if v == "nonconforming" else "srv2"
    a = {"cluster_identifier": c.name(lid), "engine": "aurora-postgresql", "database_name": "db1",
         "master_username": "boadmin", "manage_master_user_password": True, "skip_final_snapshot": True,
         "db_subnet_group_name": g.ref("name")}
    cl = c.r("aws_rds_cluster", lid, a, entity=lid)
    c.map("db1", f"{cl.address}#database_name")
    c.synth[f"{cl.address}#skip_final_snapshot"] = "teardown sem snapshot residual (SAFETY)"
    if v == "nonconforming":
        c.dev.append("cluster Aurora sem aws_rds_cluster_instance: servidor lógico sem instância exposta")
        return c.done("INTERPRETED", cost_class="low")
    c.dev.append("ha_managed: o armazenamento do cluster Aurora é replicado pelo serviço em várias zonas; quantas "
                 "instâncias de computação o sustentam não aparece na configuração")
    c.missing("srv2", "instance_count", "EVIDENCE_GAP", "o número de instâncias que sustentam o cluster não está no "
              "schema nem em fato de SERVICE-EVIDENCE", cl.address)
    return c.done("INTERPRETED", cost_class="low")


# ============================================================================ autorização


def _req(principal, action, resource, context=None) -> dict:
    d = {"principal": principal, "action": action, "resource": resource}
    if context:
        d["context"] = context
    return d


@R("CQ-AUT-01")
def aut01(v, c: Ctx):
    c.evidence.append(AWS_IAM_EVAL)
    c.dev.append("escopo pai = padrão de ARN de todos os buckets da execução; escopo filho = padrão dos objetos de r1; "
                 "o pai contém o filho por inclusão de padrão (a AWS não tem nó de escopo que conceda por herança)")
    u = user(c, "p1")
    r1 = bucket(c, "r1")
    parent = RUN_OBJECTS.expr
    c.map("s_parent", "probe:scope.parent")
    c.map("s_child", "probe:scope.child")
    c.map("q1", "probe:access_request")
    inputs = {"scope": {"parent": {"arn_pattern": parent}, "child": {"arn_pattern": "${" + r1.address + ".arn}/*",
                                                                       "child_of": "parent"}},
              "access_request": _req(u.address, "s3:GetObject (read)", r1.address)}
    c.probe = {"kind": "static", "inputs": inputs}
    if v == "incomplete":
        c.missing("s_parent", "scope", "READ_MASK", "as políticas de identidade de p1 no escopo pai (anexadas fora "
                  "desta configuração) não foram lidas", u.address)
        return c.done("INTERPRETED")
    pol = s3_read_policy(c, "ps1", RUN_OBJECTS, entity="ps1")
    c.map("perm1", f"{pol.address}#policy.Statement[0]")
    c.r("aws_iam_user_policy_attachment", "a1", {"user": u.ref("name"), "policy_arn": pol.ref("arn")}, entity="a1")
    if v == "nonconforming":
        doc = {"Version": "2012-10-17", "Statement": [{"Effect": "Deny", "Action": ["s3:GetObject"],
                                                        "Resource": arn_objects(r1)}]}
        c.r("aws_iam_user_policy", "d1", {"name": c.name("d1"), "user": u.ref("name"), "policy": Json(doc)},
            entity="d1")
    return c.done("INTERPRETED")


@R("CQ-AUT-02")
def aut02(v, c: Ctx):
    u = user(c, "p1")
    c.map("s1", "implicit:padrão de ARN do Resource das políticas (o mesmo nas duas atribuições)")
    pol = s3_read_policy(c, "ps1", RUN_OBJECTS, entity="ps1")
    c.r("aws_iam_user_policy_attachment", "a1", {"user": u.ref("name"), "policy_arn": pol.ref("arn")}, entity="a1")
    if v == "nonconforming":
        pol2 = s3_read_policy(c, "ps2", RUN_BUCKETS, entity="ps2", action="s3:ListBucket")
        c.r("aws_iam_user_policy_attachment", "a2", {"user": u.ref("name"), "policy_arn": pol2.ref("arn")},
            entity="a2")
        return c.done()
    users = [u.ref("name")] if v == "conforming" else [c.symvar("a2_principal")]
    att = c.r("aws_iam_policy_attachment", "doc1", {"name": c.name("doc1"), "policy_arn": pol.ref("arn"),
                                                    "users": users}, entity="doc1")
    c.map("a2", f"{att.address}#users[0]")
    c.dev.append("a AWS não tem documento de ligação papel->membros como o GCP; a forma 'documento' é a anexação "
                 "autoritativa (aws_iam_policy_attachment), que lista os membros da política ps1")
    if v == "incomplete":
        c.missing("a2", "reference", "SYMBOLIC_INPUT", "o membro listado na anexação vem de variável sem valor",
                  att.address)
    return c.done("INTERPRETED", deploy_note="aws_iam_policy_attachment é exclusivo para ps1 (política da própria "
                                             "fixture)")


@R("CQ-AUT-03")
def aut03(v, c: Ctx):
    c.evidence.append(AWS_IAM_EVAL)
    u = user(c, "p1")
    r1x = bucket(c, "x_child_bucket", entity=False)
    r2 = bucket(c, "r2")
    parent = RUN_OBJECTS.expr
    child = "${" + r1x.address + ".arn}/*"
    c.map("s_parent", "probe:scope.parent")
    c.map("s_child", "probe:scope.child")
    c.map("q1", "probe:access_request")
    scope_res = RUN_OBJECTS if v == "nonconforming" else (Tpl(child) if v == "conforming" else
                                                           c.symvar("child_scope_arn"))
    pol = s3_read_policy(c, "ps1", scope_res, entity="ps1")
    c.map("perm1", f"{pol.address}#policy.Statement[0]")
    c.r("aws_iam_user_policy_attachment", "a1", {"user": u.ref("name"), "policy_arn": pol.ref("arn")}, entity="a1")
    child_in = {"arn_pattern": child, "child_of": "parent"} if v != "incomplete" else {
        "arn_pattern": "var." + c.slug + "_child_scope_arn"}
    c.probe = {"kind": "static", "inputs": {"scope": {"parent": {"arn_pattern": parent}, "child": child_in},
                                            "access_request": _req(u.address, "s3:GetObject (read)", r2.address)}}
    c.dev.append("escopos são padrões de ARN; r2 casa o padrão pai e não o do filho")
    if v == "incomplete":
        c.missing("s_child", "scope", "SYMBOLIC_INPUT", "o padrão do escopo filho vem de variável: não se sabe se está "
                  "contido no pai nem se contém r2", pol.address)
    return c.done("INTERPRETED")


@R("CQ-AUT-04")
def aut04(v, c: Ctx):
    c.map("s1", "implicit:padrão de ARN do Resource da política ps1")
    pol = s3_read_policy(c, "ps1", RUN_OBJECTS, entity="ps1")
    if v == "incomplete":
        idp = c.r("aws_iam_saml_provider", "dir1", {"name": c.name("dir1"),
                                                    "saml_metadata_document": c.symvar("idp_metadata")}, entity="dir1")
        trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRoleWithSAML",
                                                          "Principal": {"Federated": idp.ref("arn")}}]}
        role = c.r("aws_iam_role", "a1", {"name": c.name("a1"), "assume_role_policy": Json(trust)}, entity="a1")
        c.x("aws_iam_role_policy_attachment", "ps", {"role": role.ref("name"), "policy_arn": pol.ref("arn")},
            why="relação assigns_set (atribuição federada -> ps1)")
        c.map("g1", "external:grupo do IdP SAML: mantido no diretório externo, fora dos pins")
        c.map("u1", "external:usuário do IdP SAML: mantido no diretório externo, fora dos pins")
        c.missing("u1", "group_membership", "EXTERNAL_REFERENCE", "a pertença de u1 a g1 vive no IdP externo (fora do "
                  "pin); o metadado do IdP vem de variável", idp.address)
        c.dev.append("grupo e usuário do diretório externo chegam por federação SAML; a atribuição é o papel federado")
        return c.done("INTERPRETED", deployable=False, deploy_note="exige metadado SAML de um IdP externo")
    g = c.r("aws_iam_group", "g1", {"name": c.name("g1")}, entity="g1")
    u = user(c, "u1")
    c.r("aws_iam_group_policy_attachment", "a1", {"group": g.ref("name"), "policy_arn": pol.ref("arn")}, entity="a1")
    if v == "conforming":
        c.x("aws_iam_user_group_membership", "member", {"user": u.ref("name"), "groups": [g.ref("name")]},
            why="relação member_of_group (u1 -> g1)")
    return c.done()


@R("CQ-AUT-05")
def aut05(v, c: Ctx):
    u = user(c, "p1")
    r1 = bucket(c, "r1")
    c.map("s1", "implicit:padrão de ARN dos objetos de r1")
    if v == "incomplete":
        cond = {"StringEquals": {"aws:PrincipalTag/device_posture": "compliant"}}
        ctx = None
    else:
        cond = {"IpAddress": {"aws:SourceIp": "198.51.100.0/24"}}
        ctx = {"aws:SourceIp": "198.51.100.7" if v == "conforming" else "203.0.113.9"}
    doc = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"],
                                                    "Resource": arn_objects(r1), "Condition": cond}]}
    pol = c.r("aws_iam_policy", "ps1", {"name": c.name("ps1"), "policy": Json(doc)}, entity="ps1")
    c.map("perm1", f"{pol.address}#policy.Statement[0].Action")
    c.map("c1", f"{pol.address}#policy.Statement[0].Condition")
    c.r("aws_iam_user_policy_attachment", "a1", {"user": u.ref("name"), "policy_arn": pol.ref("arn")}, entity="a1")
    c.map("q1", "probe:access_request")
    c.probe = {"kind": "static", "inputs": {"access_request": _req(u.address, "s3:GetObject (read)", r1.address, ctx)}}
    c.dev.append("a condição fica na declaração da política anexada (a AWS condiciona a declaração, não a anexação)")
    if v == "incomplete":
        c.missing("c1", "condition_attribute", "EVIDENCE_GAP", "a condição usa etiqueta de principal (postura do "
                  "dispositivo) que o vocabulário não tem; o pedido não traz esse atributo", pol.address)
    return c.done("INTERPRETED")


# ============================================================================ caminho de rede


def _public_path(c: Ctx, public=True, route=True, rt_external=False):
    vp = vpc(c)
    sn = subnet(c, "sa", vp, "10.20.1.0/24", entity="sa")
    if rt_external:
        rid = c.symvar("route_table_id")
        c.x("aws_route_table_association", "rt", {"subnet_id": sn.ref("id"), "route_table_id": rid},
            why="relação routes_via (sa -> rt1) com tabela fora da leitura")
        c.map("rt1", f"external:var.{c.slug}_route_table_id: tabela de rotas não lida")
    else:
        rt = c.r("aws_route_table", "rt1", {"vpc_id": vp.ref("id")}, entity="rt1")
        c.x("aws_route_table_association", "rt", {"subnet_id": sn.ref("id"), "route_table_id": rt.ref("id")},
            why="relação routes_via (sa -> rt1)")
        if route:
            igw = c.r("aws_internet_gateway", "igw", {"vpc_id": vp.ref("id")}, entity="igw")
            c.r("aws_route", "rte1", {"route_table_id": rt.ref("id"), "destination_cidr_block": "0.0.0.0/0",
                                      "gateway_id": igw.ref("id")}, entity="rte1")
    return vp, sn


@R("CQ-NET-01")
def net01(v, c: Ctx):
    vp, sn = _public_path(c)
    acl = c.r("aws_network_acl", "rs1", {"vpc_id": vp.ref("id"), "subnet_ids": [sn.ref("id")]}, entity="rs1")
    g = c.x("aws_security_group", "nic", {"name": c.name("nicsg"), "vpc_id": vp.ref("id")},
            [Block("ingress", {"protocol": "tcp", "from_port": 443, "to_port": 443, "cidr_blocks": ["0.0.0.0/0"]})],
            why="a interface AWS sempre tem grupo de segurança; este permite 443 para não ser a peça que decide")
    n = nic(c, "nic1", sn, sgs=[g.ref("id")])
    instance(c, "vm1", n)
    c.r("aws_eip", "ip1", {"domain": "vpc", "network_interface": n.ref("id")}, entity="ip1")
    port = 22 if v == "incomplete" else 443
    nacl_rule(c, "r1", acl, 200, "allow", port, DOC, entity="r1")
    nacl_rule(c, "x_egress", acl, 200, "allow", (1024, 65535), "0.0.0.0/0", egress=True,
              synth="saída efêmera para o retorno (a NACL não tem estado)")
    if v == "nonconforming":
        nacl_rule(c, "r2", acl, 100, "deny", 443, "0.0.0.0/0", entity="r2")
    if v == "incomplete":
        c.missing("rs1", "rules", "READ_MASK", "regras da NACL além de r1 (DescribeNetworkAcls) não foram lidas; "
                  "nenhuma regra lida cobre a porta de F", acl.address)
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow()}}
    c.dev.append("conjunto de regras com precedência e negar = NACL (anexada à sub-rede de nic1, sem estado); o "
                 "estado do conjunto difere da fixture (stateful), o que não muda a decisão de entrada")
    return c.done("INTERPRETED", cost_class="low")


@R("CQ-NET-02")
def net02(v, c: Ctx):
    if v == "incomplete":
        return na("na AWS o estado de conexão não é declarável por regra e o mecanismo fixa o padrão (grupo de "
                  "segurança com estado, NACL sem estado): a situação 'estado não declarado e padrão sem evidência' "
                  "não existe",
                  schema_attr_absent("aws", "aws_vpc_security_group_ingress_rule", r"(state|stateless|tracking)",
                                     "a regra do grupo de segurança não tem atributo de estado"),
                  schema_attr_absent("aws", "aws_network_acl_rule", r"(state|stateless|tracking)",
                                     "a regra da NACL não tem atributo de estado"),
                  AWS_SG_STATEFUL)
    vp = vpc(c)
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(protocol=None)}}
    c.evidence.append(AWS_SG_STATEFUL)
    if v == "conforming":
        g = sg(c, "rs1", vp)
        sg_rule(c, "r1", g, 443, DOC)
        c.dev.append("o estado vem do mecanismo (grupo de segurança é sempre com estado), não de atributo da regra")
        return c.done("INTERPRETED")
    acl = c.r("aws_network_acl", "rs1", {"vpc_id": vp.ref("id")}, entity="rs1")
    nacl_rule(c, "r1", acl, 100, "allow", 443, DOC, entity="r1")
    c.dev.append("regra sem estado = regra de NACL; a NACL avalia por precedência (não só permitir), o que não "
                 "muda a resposta: sem regra de saída o retorno é negado")
    return c.done("INTERPRETED")


@R("CQ-NET-03")
def net03(v, c: Ctx):
    if v == "conforming":
        vp, sn = _public_path(c)
    elif v == "nonconforming":
        vp, sn = _public_path(c, route=False)
    else:
        vp, sn = _public_path(c, rt_external=True)
    g = c.r("aws_security_group", "rs1", {"name": c.name("rs1"), "vpc_id": vp.ref("id")},
            [Block("ingress", {"protocol": "tcp", "from_port": 443, "to_port": 443, "cidr_blocks": ["0.0.0.0/0"]})],
            entity="rs1")
    c.map("r1", f"{g.address}#ingress[0]")
    n = nic(c, "nic1", sn, sgs=[g.ref("id")])
    instance(c, "vm1", n)
    if v == "nonconforming":
        c.map("ip1", f"{n.address}#private_ip")
    else:
        c.r("aws_eip", "ip1", {"domain": "vpc", "network_interface": n.ref("id")}, entity="ip1")
    if v == "incomplete":
        c.missing("rt1", "route_table", "EXTERNAL_REFERENCE", "a sub-rede usa tabela de rotas vinda de variável, não "
                  "lida", f"aws_route_table_association.{c.lab('x_rt')}")
    c.map("f1", "probe:flow")
    c.probe = {"kind": "static", "inputs": {"flow": flow(protocol="tcp" if v == "conforming" else None,
                                                         source="198.51.100.20/32")}}
    c.dev.append("conjunto = grupo de segurança (só permitir, com estado); onde a fixture diz precedência, a decisão "
                 "de entrada é a mesma")
    return c.done("INTERPRETED", cost_class="low")


@R("CQ-NET-04")
def net04(v, c: Ctx):
    vp = vpc(c)
    sn = subnet(c, "x_subnet", vp, "10.20.1.0/24")
    g = sg(c, "rs1", vp)
    n1 = nic(c, "nic1", sn)
    vm = instance(c, "vm1", n1)
    if v == "nonconforming":
        n3 = nic(c, "nic3", sn, sgs=[g.ref("id")])
        instance(c, "vm2", n3, img=None)
        return c.done(cost_class="low")
    sgs = [g.ref("id")] if v == "conforming" else c.symvar("nic2_security_groups", "list(string)")
    n2 = nic(c, "nic2", sn, sgs=sgs)
    attach(c, "attach2", n2, vm, 1)
    if v == "incomplete":
        c.missing("nic2", "attachment", "SYMBOLIC_INPUT", "os grupos de segurança de nic2 vêm de variável sem valor",
                  n2.address)
    return c.done(cost_class="low")


# ============================================================================ configuração x observação


@R("CQ-CVO-01")
def cvo01(v, c: Ctx):
    b = bucket(c, "c1")
    versioning(c, "d1", b, "Enabled", entity="d1")
    if v == "incomplete":
        c.missing("c1", "observation", "READ_MASK", "nenhuma leitura de volta (GetBucketVersioning) foi feita",
                  b.address)
        c.probe = {"kind": "readback", "inputs": {}}
        return c.done()
    c.map("o1", "probe:observation.state")
    c.map("ob1", "probe:observation.act")
    obs = "Enabled" if v == "conforming" else "Suspended"
    c.probe = {"kind": "readback", "inputs": {"observation": {
        "state": {"of": b.address, "field": "versioning_configuration.status", "value": obs},
        "act": {"observed_at": "2026-11-02T10:00:00-03:00", "api": "s3:GetBucketVersioning"}}}}
    if v == "nonconforming":
        c.dev.append("observado desligado = Suspended (a AWS não volta a 'nunca ligado')")
        return c.done(deployable=False, deploy_note="a divergência exige mudança fora do Terraform depois do apply; "
                                                    "offline com observação gravada")
    return c.done()


@R("CQ-CVO-02")
def cvo02(v, c: Ctx):
    b = bucket(c, "c1")
    if v == "conforming":
        versioning(c, "x_versioning", b, "Enabled", synth="valor declarado de versioning do contêiner c1")
    elif v == "nonconforming":
        c.dev.append("sem aws_s3_bucket_versioning: o versionamento observado (desligado) vem do padrão do provedor")
    else:
        versioning(c, "x_versioning", b, c.symvar("versioning_status"),
                   synth="valor de versioning vindo de entrada de módulo não resolvida")
        c.missing("c1", "value", "SYMBOLIC_INPUT", "status do versionamento vem de variável sem valor",
                  f"aws_s3_bucket_versioning.{c.lab('x_versioning')}")
    return c.done()


def _alarm_db(c: Ctx, with_alarm: bool):
    i = rds(c, "i1", entity="i1")
    if with_alarm:
        t = c.r("aws_sns_topic", "t1", {"name": c.name("t1")}, entity="t1")
        c.r("aws_cloudwatch_metric_alarm", "al1", {
            "alarm_name": c.name("al1"), "namespace": "AWS/RDS", "metric_name": "CPUUtilization",
            "statistic": "Average", "period": 300, "evaluation_periods": 1, "threshold": 80,
            "comparison_operator": "GreaterThanThreshold", "dimensions": {"DBInstanceIdentifier": i.ref("identifier")},
            "alarm_actions": [t.ref("arn")]}, entity="al1")
    return i


@R("CQ-CVO-03")
def cvo03(v, c: Ctx):
    i = _alarm_db(c, v == "conforming")
    if v != "conforming":
        c.map("s1", "implicit:conta sintética e região location_1 (escopo dos alarmes)")
        c.probe = {"kind": "static", "inputs": {"read_scope": {"api": "cloudwatch:DescribeAlarms",
                                                               "complete": v == "nonconforming"}}}
    if v == "incomplete":
        c.missing("s1", "alarm", "READ_MASK", "os alarmes do escopo não foram lidos (leitura declarada parcial)",
                  i.address)
    return c.done(cost_class="low")


@R("CQ-CVO-04")
def cvo04(v, c: Ctx):
    if v == "conforming":
        i = rds(c, "i1", entity="i1")
        c.map("k1", f"{i.address}#master_user_secret")
        c.dev.append("segredo administrativo gerido pela AWS (manage_master_user_password): presença conhecida, valor "
                     "nunca no state")
        return c.done(cost_class="low")
    if v == "nonconforming":
        p = rds(c, "x_primary", synth="primária da réplica (a réplica não tem senha administrativa própria)")
        i = c.r("aws_db_instance", "i1", {"identifier": c.name("i1"), "replicate_source_db": p.ref("identifier"),
                                          "instance_class": "db.t4g.micro", "skip_final_snapshot": True},
                entity="i1")
        c.map("k1", f"{i.address}#password (ausente: réplica de leitura não define senha administrativa)")
        c.dev.append("instância sem senha administrativa definida = réplica de leitura (a primária a define)")
        return c.done(cost_class="low")
    pw = c.symvar("admin_password")
    c.vars[-1].sensitive = True
    g = _db_subnets(c)
    i = c.r("aws_db_instance", "i1", {"identifier": c.name("i1"), "engine": "postgres", "instance_class": "db.t4g.micro",
                                      "allocated_storage": 20, "db_subnet_group_name": g.ref("name"),
                                      "username": "boadmin", "password": pw, "skip_final_snapshot": True,
                                      "multi_az": False}, entity="i1")
    c.map("k1", f"{i.address}#password")
    c.missing("k1", "secret", "SYMBOLIC_INPUT", "a senha vem de variável sensível sem valor: não se sabe se foi "
              "definida (nunca é lida nem gravada)", i.address)
    return c.done(cost_class="low", deployable=False, deploy_note="senha simbólica sem valor: só offline")


# ============================================================================ perda


def _log_group(c: Ctx, lid: str, days, entity: str):
    return c.r("aws_cloudwatch_log_group", lid, {"name": c.name(lid, sep="/"), "retention_in_days": days},
               entity=entity)


@R("CQ-LOSS-01")
def loss01(v, c: Ctx):
    days = {"conforming": 30, "nonconforming": 400, "incomplete": 30}[v]
    s = _log_group(c, "s1", days, "s1")
    c.map("t1", "probe:target")
    tgt = {"conforming": {"unit": "second", "domain_max": "31536000_second"},
           "nonconforming": {"domain_max": "365_day"}, "incomplete": {}}[v]
    c.probe = {"kind": "translation", "inputs": {"target": {**tgt, "from_spec": "t1 da fixture"}}}
    if v == "incomplete":
        c.missing("s1", "correspondence", "EVIDENCE_GAP", "a correspondência de retention_in_days com o destino não "
                  "tem prova (UNPROVEN); o valor de origem existe", s.address)
        c.dev.append("o valor de origem (30 dias) está presente; a falta é da prova da correspondência")
    return c.done()


@R("CQ-LOSS-02")
def loss02(v, c: Ctx):
    vp = vpc(c)
    acl = c.r("aws_network_acl", "rs1", {"vpc_id": vp.ref("id")}, entity="rs1")
    nacl_rule(c, "r1", acl, 100, "deny", 22, "0.0.0.0/0", entity="r1")
    c.map("tgt", "probe:target")
    sup = {"conforming": True, "nonconforming": False, "incomplete": "unknown"}[v]
    c.probe = {"kind": "translation", "inputs": {"target": {"supports_deny": sup, "from_spec": "tgt da fixture"}}}
    if v == "incomplete":
        c.missing("tgt", "target_semantics", "EVIDENCE_GAP", "o destino abstrato da especificação não tem evidência de "
                  "exprimir negação")
    return c.done()


@R("CQ-LOSS-03")
def loss03(v, c: Ctx):
    b = bucket(c, "x_bucket", entity=False)
    c.map("t1", "probe:target")
    c.probe = {"kind": "translation", "inputs": {"target": {"required": True, "from_spec": "t1 da fixture"}}}
    if v == "conforming":
        versioning(c, "s1", b, "Enabled", entity="s1")
    elif v == "nonconforming":
        c.map("s1", f"{b.address}#versioning (ausente: sem valor e sem regra que o sintetize)")
    else:
        versioning(c, "s1", b, c.symvar("versioning_status"), entity="s1")
        c.missing("s1", "value", "SYMBOLIC_INPUT", "o valor de origem vem de variável sem valor",
                  f"aws_s3_bucket_versioning.{c.lab('s1')}")
    return c.done()


@R("CQ-LOSS-04")
def loss04(v, c: Ctx):
    c.map("t1", "probe:target")
    c.probe = {"kind": "translation", "inputs": {"target": {"retention_unit": "second", "from_spec": "t1 da fixture"}}}
    if v == "conforming":
        _log_group(c, "s1", 7, "s1")
        return c.done()
    if v == "nonconforming":
        b = bucket(c, "x_bucket", entity=False)
        c.r("aws_s3_bucket_versioning", "x_versioning", {"bucket": b.ref("id")},
            [Block("versioning_configuration", {"status": "Enabled"})], synth="o object lock exige versionamento")
        c.r("aws_s3_bucket_object_lock_configuration", "s1", {"bucket": b.ref("id")},
            [Block("rule", {}, [Block("default_retention", {"mode": "GOVERNANCE", "years": 1})])], entity="s1")
        c.synth[f"aws_s3_bucket.{c.lab('x_bucket')}#object_lock_enabled"] = "exigido pelo object lock"
        c.dev.append("a AWS não exprime retenção em meses; a retenção de calendário mais próxima é em anos (1 ano), que "
                     "também não é número fixo de segundos: a resposta (não) continua a mesma")
        return c.done("INTERPRETED", deploy_note="object lock em GOVERNANCE: o teardown precisa de bypass")
    tg = c.r("aws_lb_target_group", "s1", {"name": c.name("s1", maxlen=20), "port": 80, "protocol": "HTTP",
                                           "deregistration_delay": 30, "vpc_id": c.symvar("vpc_id")}, entity="s1")
    c.missing("s1", "unit", "EVIDENCE_GAP", "deregistration_delay não traz a unidade no nome nem no schema; o UNITS "
              "ainda não a determinou", tg.address)
    c.dev.append("o valor 30 é de um atributo de espera (não retenção) cuja unidade não está no schema")
    return c.done("INTERPRETED", deployable=False, deploy_note="vpc_id simbólico: só offline")


# ============================================================================ provedor novo

P4 = "implicit:provedor aws no papel de provedor retirado (P4)"


@R("CQ-NEW-01")
def new01(v, c: Ctx):
    c.map("p4", P4)
    b = bucket(c, "x_bucket", entity=False)
    if v == "conforming":
        versioning(c, "s1", b, "Enabled", entity="s1")
        c.map("k1", "probe:concept.k1")
        c.probe = {"kind": "static", "inputs": {"concept": {"k1": {"label": "versionamento de objetos",
                                                                   "exclusive": False}}}}
    elif v == "nonconforming":
        c.r("aws_s3_bucket_accelerate_configuration", "s2", {"bucket": b.ref("id"), "status": "Enabled"}, entity="s2")
        c.map("k2", "probe:concept.k2")
        c.probe = {"kind": "static", "inputs": {"concept": {"k2": {"label": "aceleração de transferência pela borda",
                                                                   "exclusive": True}}}}
        c.dev.append("exclusividade do conceito é hipótese até o GLOSSARY confirmar")
    else:
        s = c.r("aws_s3_bucket_request_payment_configuration", "src3", {"bucket": b.ref("id"), "payer": "Requester"},
                entity="src3")
        c.missing("src3", "concept", "EVIDENCE_GAP", "o atributo ainda não foi glosado (UNGLOSSED): sem conceito "
                  "determinado", s.address)
    return c.done("INTERPRETED")


@R("CQ-NEW-02")
def new02(v, c: Ctx):
    c.map("p4", P4)
    vp = vpc(c)
    sn = subnet(c, "x_subnet", vp, "10.20.1.0/24")
    if v == "nonconforming":
        n1 = nic(c, "nic1", sn, extra={"private_ips_count": 1})
        c.map("ip2", f"{n1.address}#private_ips_count (endereço secundário)")
        instance(c, "vm1", n1)
        return c.done(cost_class="low")
    n1 = nic(c, "nic1", sn)
    vm = instance(c, "vm1", n1)
    n2 = nic(c, "nic2", sn)
    if v == "conforming":
        attach(c, "attach2", n2, vm, 1)
        c.dev.append("na AWS as interfaces são recursos separados (declared_inline false); a estrutura (três "
                     "indivíduos, duas anexações) é a mesma")
    else:
        attach(c, "attach2", n2, vm, 1, instance_id=c.symvar("nic2_instance_id"))
        c.missing("nic2", "attachment", "EXTERNAL_REFERENCE", "a anexação de nic2 aponta para instância vinda de "
                  "variável", f"aws_network_interface_attachment.{c.lab('x_attach2')}")
    return c.done("INTERPRETED", cost_class="low")


@R("CQ-NEW-03")
def new03(v, c: Ctx):
    c.map("p4", P4)
    if v == "nonconforming":
        g = c.r("aws_networkfirewall_rule_group", "rs1", {"name": c.name("rs1"), "capacity": 10, "type": "STATEFUL"},
                [Block("rule_group", {}, [
                    Block("rules_source", {"rules_string": "drop tcp any any -> any 22 (msg:\"r1\"; sid:1;)\n"}),
                    Block("stateful_rule_options", {"rule_order": "STRICT_ORDER"})])], entity="rs1")
        c.map("r1", f"{g.address}#rule_group.rules_source.rules_string[linha 1]")
        c.dev.append("primeira correspondência pela posição textual = grupo de regras do Network Firewall em "
                     "STRICT_ORDER com regras em texto (avaliadas na ordem escrita, sem número de precedência)")
        return c.done("INTERPRETED", deployable=False, deploy_note="grupo de regras do Network Firewall: só offline")
    if v == "conforming":
        vp = vpc(c)
        acl = c.r("aws_network_acl", "rs1", {"vpc_id": vp.ref("id")}, entity="rs1")
        nacl_rule(c, "r1", acl, 100, "deny", 22, "0.0.0.0/0", entity="r1")
        return c.done()
    g = c.r("aws_networkfirewall_rule_group", "rs1", {"name": c.name("rs1"), "capacity": 10, "type": "STATEFUL"},
            [Block("rule_group", {}, [Block("rules_source", {}, [Block("stateful_rule", {"action": "DROP"}, [
                Block("header", {"destination": "ANY", "destination_port": "22", "direction": "FORWARD",
                                 "protocol": "TCP", "source": "ANY", "source_port": "ANY"}),
                Block("rule_option", {"keyword": "sid", "settings": ["1"]})])])])], entity="rs1")
    c.map("r1", f"{g.address}#rule_group.rules_source.stateful_rule[0]")
    c.missing("rs1", "precedence", "EXTERNAL_REFERENCE", "sem stateful_rule_options.rule_order, a ordem (ação padrão "
              "ou estrita) é decidida pela política de firewall, fora desta configuração", g.address)
    return c.done("INTERPRETED", deployable=False, deploy_note="grupo de regras do Network Firewall: só offline")
