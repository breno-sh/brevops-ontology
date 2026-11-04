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
