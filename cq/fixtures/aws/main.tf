# Fixtures das CQs (CQFIX) no provider aws — gerado por bo.cqfix.build; não editar.
# Cada seção é uma fixture (FX-...) e só ela; o conjunto de endereços de cada uma está em
# expected_answers.json. Valores reais (conta, região, projeto) nunca entram: vêm das variáveis
# de contexto, ligadas pelo runner do DEP. Variáveis fx_* sem valor são entradas simbólicas de
# fixtures incompletas, de propósito.

terraform {
  required_version = "= 1.15.8"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.71.0"
    }
  }
}

provider "aws" {
  region = var.location_1
  default_tags {
    tags = {
      bo_run    = var.run_id
      bo_module = "CQFIX"
    }
  }
}

variable "run_id" {
  type        = string
  description = "identificador curto da execução (prefixo de nomes e tag bo_run); ligado pelo runner"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.run_id))
    error_message = "run_id: 3 a 12 caracteres, minúsculas e dígitos."
  }
}

variable "location_1" {
  type        = string
  description = "localização l1 das fixtures (região); ligada pelo runner"
}

variable "location_2" {
  type        = string
  description = "localização l2, distinta de l1; ligada pelo runner"
}

# ==== FX-CIS-01-C (CQ-CIS-01, conforming)

resource "aws_iam_user" "fx_cis_01_c_u1" {
  name = "${var.run_id}-fx-cis-01-c-u1"
}

resource "aws_iam_user_login_profile" "fx_cis_01_c_x_console" {
  user                    = aws_iam_user.fx_cis_01_c_u1.name
  password_reset_required = true
}

resource "aws_iam_user_policy" "fx_cis_01_c_d1" {
  name = "${var.run_id}-fx-cis-01-c-d1"
  user = aws_iam_user.fx_cis_01_c_u1.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyWithoutMFA"
        Effect    = "Deny"
        NotAction = ["iam:ChangePassword", "sts:GetSessionToken"]
        Resource  = "*"
        Condition = {
          BoolIfExists = {
            "aws:MultiFactorAuthPresent" = "false"
          }
        }
      },
    ]
  })
}

# ==== FX-CIS-01-N (CQ-CIS-01, nonconforming)

resource "aws_iam_user" "fx_cis_01_n_u1" {
  name = "${var.run_id}-fx-cis-01-n-u1"
}

resource "aws_iam_user_login_profile" "fx_cis_01_n_d1" {
  user                    = aws_iam_user.fx_cis_01_n_u1.name
  password_reset_required = true
}

# ==== FX-CIS-01-I (CQ-CIS-01, incomplete)

variable "fx_cis_01_i_mfa_required" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-01-I; sem valor de propósito"
}

resource "aws_iam_user" "fx_cis_01_i_u1" {
  name = "${var.run_id}-fx-cis-01-i-u1"
}

resource "aws_iam_user_login_profile" "fx_cis_01_i_x_console" {
  user                    = aws_iam_user.fx_cis_01_i_u1.name
  password_reset_required = true
}

resource "aws_iam_user_policy" "fx_cis_01_i_d1" {
  name = "${var.run_id}-fx-cis-01-i-d1"
  user = aws_iam_user.fx_cis_01_i_u1.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyWithoutMFA"
        Effect    = "Deny"
        NotAction = ["iam:ChangePassword", "sts:GetSessionToken"]
        Resource  = "*"
        Condition = {
          BoolIfExists = {
            "aws:MultiFactorAuthPresent" = "${var.fx_cis_01_i_mfa_required ? "false" : "true"}"
          }
        }
      },
    ]
  })
}

# ==== FX-CIS-02-C (CQ-CIS-02, conforming)

resource "aws_iam_user" "fx_cis_02_c_p1" {
  name = "${var.run_id}-fx-cis-02-c-p1"
}

resource "aws_iam_access_key" "fx_cis_02_c_k1" {
  user = aws_iam_user.fx_cis_02_c_p1.name
}

# ==== FX-CIS-02-N (CQ-CIS-02, nonconforming)

resource "aws_iam_user" "fx_cis_02_n_p1" {
  name = "${var.run_id}-fx-cis-02-n-p1"
}

resource "aws_iam_access_key" "fx_cis_02_n_k1" {
  user = aws_iam_user.fx_cis_02_n_p1.name
}

# ==== FX-CIS-02-I (CQ-CIS-02, incomplete)

resource "aws_iam_user" "fx_cis_02_i_p1" {
  name = "${var.run_id}-fx-cis-02-i-p1"
}

resource "aws_iam_access_key" "fx_cis_02_i_k1" {
  user = aws_iam_user.fx_cis_02_i_p1.name
}

# ==== FX-CIS-03-C (CQ-CIS-03, conforming)

resource "aws_kms_key" "fx_cis_03_c_k1" {
  description             = "${var.run_id} FX-CIS-03-C"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  rotation_period_in_days = 90
}

# ==== FX-CIS-03-N (CQ-CIS-03, nonconforming)

resource "aws_kms_key" "fx_cis_03_n_k1" {
  description             = "${var.run_id} FX-CIS-03-N"
  deletion_window_in_days = 7
  enable_key_rotation     = false
}

# ==== FX-CIS-03-I (CQ-CIS-03, incomplete)

variable "fx_cis_03_i_rotation" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-03-I; sem valor de propósito"
}

resource "aws_kms_key" "fx_cis_03_i_k1" {
  description             = "${var.run_id} FX-CIS-03-I"
  deletion_window_in_days = 7
  enable_key_rotation     = var.fx_cis_03_i_rotation
}

# ==== FX-CIS-04-C (CQ-CIS-04, conforming)

resource "aws_vpc" "fx_cis_04_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_cis_04_c_rs1" {
  name   = "${var.run_id}-fx-cis-04-c-rs1"
  vpc_id = aws_vpc.fx_cis_04_c_x_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "fx_cis_04_c_r1" {
  security_group_id = aws_security_group.fx_cis_04_c_rs1.id
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = "203.0.113.0/24"
}

# ==== FX-CIS-04-N (CQ-CIS-04, nonconforming)

resource "aws_vpc" "fx_cis_04_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_cis_04_n_rs1" {
  name   = "${var.run_id}-fx-cis-04-n-rs1"
  vpc_id = aws_vpc.fx_cis_04_n_x_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "fx_cis_04_n_r1" {
  security_group_id = aws_security_group.fx_cis_04_n_rs1.id
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = "0.0.0.0/0"
}

# ==== FX-CIS-04-I (CQ-CIS-04, incomplete)

variable "fx_cis_04_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-04-I; sem valor de propósito"
}

resource "aws_vpc" "fx_cis_04_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_cis_04_i_rs1" {
  name   = "${var.run_id}-fx-cis-04-i-rs1"
  vpc_id = aws_vpc.fx_cis_04_i_x_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "fx_cis_04_i_r1" {
  security_group_id = aws_security_group.fx_cis_04_i_rs1.id
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = var.fx_cis_04_i_source_cidr
}

# ==== FX-CIS-05-C (CQ-CIS-05, conforming)

resource "aws_vpc" "fx_cis_05_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_cis_05_c_rs1" {
  name   = "${var.run_id}-fx-cis-05-c-rs1"
  vpc_id = aws_vpc.fx_cis_05_c_x_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "fx_cis_05_c_r1" {
  security_group_id = aws_security_group.fx_cis_05_c_rs1.id
  ip_protocol       = "tcp"
  from_port         = 3389
  to_port           = 3389
  cidr_ipv4         = "203.0.113.0/24"
}

# ==== FX-CIS-05-N (CQ-CIS-05, nonconforming)

resource "aws_vpc" "fx_cis_05_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_cis_05_n_rs1" {
  name   = "${var.run_id}-fx-cis-05-n-rs1"
  vpc_id = aws_vpc.fx_cis_05_n_x_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "fx_cis_05_n_r1" {
  security_group_id = aws_security_group.fx_cis_05_n_rs1.id
  ip_protocol       = "tcp"
  from_port         = 3389
  to_port           = 3389
  cidr_ipv4         = "0.0.0.0/0"
}

# ==== FX-CIS-05-I (CQ-CIS-05, incomplete)

variable "fx_cis_05_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-05-I; sem valor de propósito"
}

resource "aws_vpc" "fx_cis_05_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_cis_05_i_rs1" {
  name   = "${var.run_id}-fx-cis-05-i-rs1"
  vpc_id = aws_vpc.fx_cis_05_i_x_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "fx_cis_05_i_r1" {
  security_group_id = aws_security_group.fx_cis_05_i_rs1.id
  ip_protocol       = "tcp"
  from_port         = 3389
  to_port           = 3389
  cidr_ipv4         = var.fx_cis_05_i_source_cidr
}

# ==== FX-CIS-06-C (CQ-CIS-06, conforming)

resource "aws_vpc" "fx_cis_06_c_vn1" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cis_06_c_sa" {
  vpc_id     = aws_vpc.fx_cis_06_c_vn1.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_cloudwatch_log_group" "fx_cis_06_c_x_flowlogs" {
  name              = "${var.run_id}/fx/cis/06/c/flowlogs"
  retention_in_days = 1
}

resource "aws_iam_role" "fx_cis_06_c_x_flowlogs" {
  name = "${var.run_id}-fx-cis-06-c-flowrole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Service = "vpc-flow-logs.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_iam_role_policy" "fx_cis_06_c_x_flowlogs" {
  name = "${var.run_id}-fx-cis-06-c-flowpol"
  role = aws_iam_role.fx_cis_06_c_x_flowlogs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Resource = "*"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
      },
    ]
  })
}

resource "aws_flow_log" "fx_cis_06_c_d1" {
  subnet_id       = aws_subnet.fx_cis_06_c_sa.id
  traffic_type    = "ALL"
  log_destination = aws_cloudwatch_log_group.fx_cis_06_c_x_flowlogs.arn
  iam_role_arn    = aws_iam_role.fx_cis_06_c_x_flowlogs.arn
}

# ==== FX-CIS-06-N (CQ-CIS-06, nonconforming)

resource "aws_vpc" "fx_cis_06_n_vn1" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cis_06_n_sa" {
  vpc_id     = aws_vpc.fx_cis_06_n_vn1.id
  cidr_block = "10.20.1.0/24"
}

# ==== FX-CIS-06-I (CQ-CIS-06, incomplete)

variable "fx_cis_06_i_flow_log_enabled" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-06-I; sem valor de propósito"
}

resource "aws_vpc" "fx_cis_06_i_vn1" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cis_06_i_sa" {
  vpc_id     = aws_vpc.fx_cis_06_i_vn1.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_cloudwatch_log_group" "fx_cis_06_i_x_flowlogs" {
  name              = "${var.run_id}/fx/cis/06/i/flowlogs"
  retention_in_days = 1
}

resource "aws_iam_role" "fx_cis_06_i_x_flowlogs" {
  name = "${var.run_id}-fx-cis-06-i-flowrole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Service = "vpc-flow-logs.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_iam_role_policy" "fx_cis_06_i_x_flowlogs" {
  name = "${var.run_id}-fx-cis-06-i-flowpol"
  role = aws_iam_role.fx_cis_06_i_x_flowlogs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Resource = "*"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
      },
    ]
  })
}

resource "aws_flow_log" "fx_cis_06_i_d1" {
  count           = var.fx_cis_06_i_flow_log_enabled ? 1 : 0
  subnet_id       = aws_subnet.fx_cis_06_i_sa.id
  traffic_type    = "ALL"
  log_destination = aws_cloudwatch_log_group.fx_cis_06_i_x_flowlogs.arn
  iam_role_arn    = aws_iam_role.fx_cis_06_i_x_flowlogs.arn
}

# ==== FX-CIS-07-C (CQ-CIS-07, conforming)

resource "aws_sns_topic" "fx_cis_07_c_t1" {
  name = "${var.run_id}-fx-cis-07-c-t1"
}

resource "aws_cloudwatch_event_rule" "fx_cis_07_c_al1" {
  name = "${var.run_id}-fx-cis-07-c-al1"
  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        "AuthorizeSecurityGroupIngress",
        "AuthorizeSecurityGroupEgress",
        "RevokeSecurityGroupIngress",
        "RevokeSecurityGroupEgress",
        "CreateSecurityGroup",
        "DeleteSecurityGroup",
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "fx_cis_07_c_x_notify" {
  rule = aws_cloudwatch_event_rule.fx_cis_07_c_al1.name
  arn  = aws_sns_topic.fx_cis_07_c_t1.arn
}

# ==== FX-CIS-07-N (CQ-CIS-07, nonconforming)

resource "aws_sns_topic" "fx_cis_07_n_t1" {
  name = "${var.run_id}-fx-cis-07-n-t1"
}

resource "aws_cloudwatch_event_rule" "fx_cis_07_n_al1" {
  name = "${var.run_id}-fx-cis-07-n-al1"
  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventName = [
        "CreateRoute",
        "CreateRouteTable",
        "ReplaceRoute",
        "ReplaceRouteTableAssociation",
        "DeleteRouteTable",
        "DeleteRoute",
        "DisassociateRouteTable",
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "fx_cis_07_n_x_notify" {
  rule = aws_cloudwatch_event_rule.fx_cis_07_n_al1.name
  arn  = aws_sns_topic.fx_cis_07_n_t1.arn
}

# ==== FX-CIS-07-I (CQ-CIS-07, incomplete)

variable "fx_cis_07_i_event_pattern" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-07-I; sem valor de propósito"
}

resource "aws_sns_topic" "fx_cis_07_i_t1" {
  name = "${var.run_id}-fx-cis-07-i-t1"
}

resource "aws_cloudwatch_event_rule" "fx_cis_07_i_al1" {
  name          = "${var.run_id}-fx-cis-07-i-al1"
  event_pattern = var.fx_cis_07_i_event_pattern
}

resource "aws_cloudwatch_event_target" "fx_cis_07_i_x_notify" {
  rule = aws_cloudwatch_event_rule.fx_cis_07_i_al1.name
  arn  = aws_sns_topic.fx_cis_07_i_t1.arn
}

# ==== FX-CIS-08-C (CQ-CIS-08, conforming)

resource "aws_s3_bucket" "fx_cis_08_c_c1" {
  bucket        = "${var.run_id}-fx-cis-08-c-c1"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "fx_cis_08_c_k1" {
  bucket                  = aws_s3_bucket.fx_cis_08_c_c1.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ==== FX-CIS-08-N (CQ-CIS-08, nonconforming)

resource "aws_s3_bucket" "fx_cis_08_n_c1" {
  bucket        = "${var.run_id}-fx-cis-08-n-c1"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "fx_cis_08_n_k1" {
  bucket                  = aws_s3_bucket.fx_cis_08_n_c1.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "fx_cis_08_n_x_public" {
  bucket = aws_s3_bucket.fx_cis_08_n_c1.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.fx_cis_08_n_c1.arn}/*"
      },
    ]
  })
  depends_on = [aws_s3_bucket_public_access_block.fx_cis_08_n_k1]
}

# ==== FX-CIS-08-I (CQ-CIS-08, incomplete)

variable "fx_cis_08_i_block_public" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-08-I; sem valor de propósito"
}

resource "aws_s3_bucket" "fx_cis_08_i_c1" {
  bucket        = "${var.run_id}-fx-cis-08-i-c1"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "fx_cis_08_i_k1" {
  bucket                  = aws_s3_bucket.fx_cis_08_i_c1.id
  block_public_acls       = var.fx_cis_08_i_block_public
  block_public_policy     = var.fx_cis_08_i_block_public
  ignore_public_acls      = var.fx_cis_08_i_block_public
  restrict_public_buckets = var.fx_cis_08_i_block_public
}

# ==== FX-IDL-01-C (CQ-IDL-01, conforming)

resource "aws_s3_bucket" "fx_idl_01_c_c1" {
  bucket        = "${var.run_id}-fx-idl-01-c-data-a"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_idl_01_c_x_versioning" {
  bucket = aws_s3_bucket.fx_idl_01_c_c1.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ==== FX-IDL-01-N (CQ-IDL-01, nonconforming)

resource "aws_s3_bucket" "fx_idl_01_n_c2" {
  bucket        = "${var.run_id}-fx-idl-01-n-data-a"
  force_destroy = true
  region        = var.location_2
}

# ==== FX-IDL-01-I (CQ-IDL-01, incomplete)

resource "aws_s3_bucket" "fx_idl_01_i_c1" {
  bucket        = "${var.run_id}-fx-idl-01-i-data-a"
  force_destroy = true
}

resource "aws_s3_bucket_intelligent_tiering_configuration" "fx_idl_01_i_x_tiering" {
  bucket = aws_s3_bucket.fx_idl_01_i_c1.id
  name   = "tier"
  tiering {
    access_tier = "DEEP_ARCHIVE_ACCESS"
    days        = 180
  }
}

# ==== FX-IDL-02-C (CQ-IDL-02, conforming)

resource "aws_sqs_queue" "fx_idl_02_c_c1" {
  name   = "${var.run_id}-data"
  region = var.location_1
}

resource "aws_sqs_queue" "fx_idl_02_c_c2" {
  name   = "${var.run_id}-data"
  region = var.location_2
}

# ==== FX-IDL-02-N (CQ-IDL-02, nonconforming)

resource "aws_sqs_queue" "fx_idl_02_n_c1" {
  name   = "${var.run_id}-data"
  region = var.location_1
}

data "aws_sqs_queue" "fx_idl_02_n_c2" {
  name   = aws_sqs_queue.fx_idl_02_n_c1.name
  region = var.location_1
}

# ==== FX-IDL-02-I (CQ-IDL-02, incomplete)

variable "fx_idl_02_i_c2_location" {
  type        = string
  description = "entrada simbólica da fixture FX-IDL-02-I; sem valor de propósito"
}

resource "aws_sqs_queue" "fx_idl_02_i_c1" {
  name   = "${var.run_id}-data"
  region = var.location_1
}

data "aws_sqs_queue" "fx_idl_02_i_c2" {
  name   = "${var.run_id}-data"
  region = var.fx_idl_02_i_c2_location
}

# ==== FX-IDL-03-C (CQ-IDL-03, conforming)

resource "aws_iam_user" "fx_idl_03_c_p1" {
  name = "${var.run_id}-fx-idl-03-c-p1"
}

resource "aws_iam_policy" "fx_idl_03_c_ps1" {
  name = "${var.run_id}-fx-idl-03-c-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_idl_03_c_a1" {
  user       = aws_iam_user.fx_idl_03_c_p1.name
  policy_arn = aws_iam_policy.fx_idl_03_c_ps1.arn
}

# ==== FX-IDL-03-N (CQ-IDL-03, nonconforming)

resource "aws_dynamodb_table" "fx_idl_03_n_ns1" {
  name         = "${var.run_id}-fx-idl-03-n-ns1"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  global_secondary_index {
    name            = "c1"
    projection_type = "KEYS_ONLY"
    key_schema {
      attribute_name = "sk"
      key_type       = "HASH"
    }
  }
}

# ==== FX-IDL-03-I (CQ-IDL-03, incomplete)

resource "aws_s3_bucket" "fx_idl_03_i_c1" {
  bucket        = "${var.run_id}-fx-idl-03-i-c1"
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "fx_idl_03_i_s1" {
  bucket = aws_s3_bucket.fx_idl_03_i_c1.id
  rule {
    id     = "retention"
    status = "Enabled"
    filter {
    }
    expiration {
      days = 30
    }
  }
}

# ==== FX-IDL-04-C (CQ-IDL-04, conforming)

resource "aws_vpc" "fx_idl_04_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_idl_04_c_rs1" {
  name   = "${var.run_id}-fx-idl-04-c-rs1"
  vpc_id = aws_vpc.fx_idl_04_c_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["203.0.113.0/24"]
  }
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["203.0.113.0/24"]
  }
}

# ==== FX-IDL-04-N (CQ-IDL-04, nonconforming)

resource "aws_vpc" "fx_idl_04_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_idl_04_n_rs1" {
  name   = "${var.run_id}-fx-idl-04-n-rs1"
  vpc_id = aws_vpc.fx_idl_04_n_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 8443
    to_port     = 8443
    cidr_blocks = ["203.0.113.0/24"]
  }
  ingress {
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["203.0.113.0/24"]
  }
}

# ==== FX-IDL-04-I (CQ-IDL-04, incomplete)

variable "fx_idl_04_i_r1_port" {
  type        = number
  description = "entrada simbólica da fixture FX-IDL-04-I; sem valor de propósito"
}

resource "aws_vpc" "fx_idl_04_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_idl_04_i_rs1" {
  name   = "${var.run_id}-fx-idl-04-i-rs1"
  vpc_id = aws_vpc.fx_idl_04_i_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = var.fx_idl_04_i_r1_port
    to_port     = var.fx_idl_04_i_r1_port
    cidr_blocks = ["203.0.113.0/24"]
  }
  ingress {
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["203.0.113.0/24"]
  }
}

# ==== FX-CMP-01-C (CQ-CMP-01, conforming)

resource "aws_vpc" "fx_cmp_01_c_vn1" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_01_c_sa" {
  vpc_id     = aws_vpc.fx_cmp_01_c_vn1.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_network_interface" "fx_cmp_01_c_nic1" {
  subnet_id = aws_subnet.fx_cmp_01_c_sa.id
}

data "aws_ssm_parameter" "fx_cmp_01_c_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_cmp_01_c_vm1" {
  ami           = data.aws_ssm_parameter.fx_cmp_01_c_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_cmp_01_c_nic1.id
  }
}

# ==== FX-CMP-01-N (CQ-CMP-01, nonconforming)

resource "aws_vpc" "fx_cmp_01_n_vn1" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_network_interface" "fx_cmp_01_n_nic1" {
  subnet_id = "subnet-0a1b2c3d4e5f60789"
}

data "aws_ssm_parameter" "fx_cmp_01_n_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_cmp_01_n_vm1" {
  ami           = data.aws_ssm_parameter.fx_cmp_01_n_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_cmp_01_n_nic1.id
  }
}

# ==== FX-CMP-01-I (CQ-CMP-01, incomplete)

variable "fx_cmp_01_i_subnet_id" {
  type        = string
  description = "entrada simbólica da fixture FX-CMP-01-I; sem valor de propósito"
}

resource "aws_network_interface" "fx_cmp_01_i_nic1" {
  subnet_id = var.fx_cmp_01_i_subnet_id
}

data "aws_ssm_parameter" "fx_cmp_01_i_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_cmp_01_i_vm1" {
  ami           = data.aws_ssm_parameter.fx_cmp_01_i_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_cmp_01_i_nic1.id
  }
}

# ==== FX-CMP-02-C (CQ-CMP-02, conforming)

resource "aws_vpc" "fx_cmp_02_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_02_c_x_subnet" {
  vpc_id     = aws_vpc.fx_cmp_02_c_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_network_interface" "fx_cmp_02_c_nic1" {
  subnet_id = aws_subnet.fx_cmp_02_c_x_subnet.id
}

data "aws_ssm_parameter" "fx_cmp_02_c_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_cmp_02_c_vm1" {
  ami           = data.aws_ssm_parameter.fx_cmp_02_c_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_cmp_02_c_nic1.id
  }
}

resource "aws_network_interface" "fx_cmp_02_c_nic2" {
  subnet_id = aws_subnet.fx_cmp_02_c_x_subnet.id
}

resource "aws_network_interface_attachment" "fx_cmp_02_c_x_attach2" {
  instance_id          = aws_instance.fx_cmp_02_c_vm1.id
  network_interface_id = aws_network_interface.fx_cmp_02_c_nic2.id
  device_index         = 1
}

# ==== FX-CMP-02-N (CQ-CMP-02, nonconforming)

resource "aws_vpc" "fx_cmp_02_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_02_n_x_subnet" {
  vpc_id     = aws_vpc.fx_cmp_02_n_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_network_interface" "fx_cmp_02_n_nic1" {
  subnet_id = aws_subnet.fx_cmp_02_n_x_subnet.id
}

data "aws_ssm_parameter" "fx_cmp_02_n_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_cmp_02_n_vm1" {
  ami           = data.aws_ssm_parameter.fx_cmp_02_n_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_cmp_02_n_nic1.id
  }
}

# ==== FX-CMP-02-I (CQ-CMP-02, incomplete)

variable "fx_cmp_02_i_nic2_instance_id" {
  type        = string
  description = "entrada simbólica da fixture FX-CMP-02-I; sem valor de propósito"
}

resource "aws_vpc" "fx_cmp_02_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_02_i_x_subnet" {
  vpc_id     = aws_vpc.fx_cmp_02_i_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_network_interface" "fx_cmp_02_i_nic1" {
  subnet_id = aws_subnet.fx_cmp_02_i_x_subnet.id
}

data "aws_ssm_parameter" "fx_cmp_02_i_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_cmp_02_i_vm1" {
  ami           = data.aws_ssm_parameter.fx_cmp_02_i_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_cmp_02_i_nic1.id
  }
}

resource "aws_network_interface" "fx_cmp_02_i_nic2" {
  subnet_id = aws_subnet.fx_cmp_02_i_x_subnet.id
}

resource "aws_network_interface_attachment" "fx_cmp_02_i_x_attach2" {
  instance_id          = var.fx_cmp_02_i_nic2_instance_id
  network_interface_id = aws_network_interface.fx_cmp_02_i_nic2.id
  device_index         = 1
}

# ==== FX-CMP-03-C (CQ-CMP-03, conforming)

resource "aws_vpc" "fx_cmp_03_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_03_c_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cmp_03_c_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cmp_03_c_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cmp_03_c_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_security_group" "fx_cmp_03_c_x_lb" {
  name   = "${var.run_id}-fx-cmp-03-c-lbsg"
  vpc_id = aws_vpc.fx_cmp_03_c_x_vpc.id
}

resource "aws_lb" "fx_cmp_03_c_lb1" {
  name               = "${var.run_id}-fx-cmp-03-c-lb1"
  internal           = true
  load_balancer_type = "application"
  subnets            = [aws_subnet.fx_cmp_03_c_x_subnet_a.id, aws_subnet.fx_cmp_03_c_x_subnet_b.id]
  security_groups    = [aws_security_group.fx_cmp_03_c_x_lb.id]
}

resource "aws_lb_target_group" "fx_cmp_03_c_pool1" {
  name        = "${var.run_id}-fx-cmp-03-c-pool1"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.fx_cmp_03_c_x_vpc.id
  target_type = "instance"
  health_check {
    enabled  = true
    path     = "/"
    protocol = "HTTP"
  }
}

resource "aws_lb_listener" "fx_cmp_03_c_li1" {
  load_balancer_arn = aws_lb.fx_cmp_03_c_lb1.arn
  port              = 443
  protocol          = "HTTP"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener_rule" "fx_cmp_03_c_ru1" {
  listener_arn = aws_lb_listener.fx_cmp_03_c_li1.arn
  priority     = 100
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.fx_cmp_03_c_pool1.arn
  }
  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

resource "aws_network_interface" "fx_cmp_03_c_x_nic" {
  subnet_id = aws_subnet.fx_cmp_03_c_x_subnet_a.id
}

data "aws_ssm_parameter" "fx_cmp_03_c_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_cmp_03_c_vm1" {
  ami           = data.aws_ssm_parameter.fx_cmp_03_c_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_cmp_03_c_x_nic.id
  }
}

resource "aws_lb_target_group_attachment" "fx_cmp_03_c_x_member" {
  target_group_arn = aws_lb_target_group.fx_cmp_03_c_pool1.arn
  target_id        = aws_instance.fx_cmp_03_c_vm1.id
}

# ==== FX-CMP-03-N (CQ-CMP-03, nonconforming)

resource "aws_vpc" "fx_cmp_03_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_03_n_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cmp_03_n_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cmp_03_n_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cmp_03_n_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_security_group" "fx_cmp_03_n_x_lb" {
  name   = "${var.run_id}-fx-cmp-03-n-lbsg"
  vpc_id = aws_vpc.fx_cmp_03_n_x_vpc.id
}

resource "aws_lb" "fx_cmp_03_n_lb1" {
  name               = "${var.run_id}-fx-cmp-03-n-lb1"
  internal           = true
  load_balancer_type = "application"
  subnets            = [aws_subnet.fx_cmp_03_n_x_subnet_a.id, aws_subnet.fx_cmp_03_n_x_subnet_b.id]
  security_groups    = [aws_security_group.fx_cmp_03_n_x_lb.id]
}

resource "aws_lb_target_group" "fx_cmp_03_n_pool1" {
  name        = "${var.run_id}-fx-cmp-03-n-pool1"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.fx_cmp_03_n_x_vpc.id
  target_type = "instance"
  health_check {
    enabled  = true
    path     = "/"
    protocol = "HTTP"
  }
}

resource "aws_lb_listener" "fx_cmp_03_n_li1" {
  load_balancer_arn = aws_lb.fx_cmp_03_n_lb1.arn
  port              = 443
  protocol          = "HTTP"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener_rule" "fx_cmp_03_n_ru1" {
  listener_arn = aws_lb_listener.fx_cmp_03_n_li1.arn
  priority     = 100
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.fx_cmp_03_n_pool1.arn
  }
  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

# ==== FX-CMP-03-I (CQ-CMP-03, incomplete)

resource "aws_vpc" "fx_cmp_03_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_03_i_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cmp_03_i_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cmp_03_i_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cmp_03_i_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_security_group" "fx_cmp_03_i_x_lb" {
  name   = "${var.run_id}-fx-cmp-03-i-lbsg"
  vpc_id = aws_vpc.fx_cmp_03_i_x_vpc.id
}

resource "aws_lb" "fx_cmp_03_i_lb1" {
  name               = "${var.run_id}-fx-cmp-03-i-lb1"
  internal           = true
  load_balancer_type = "application"
  subnets            = [aws_subnet.fx_cmp_03_i_x_subnet_a.id, aws_subnet.fx_cmp_03_i_x_subnet_b.id]
  security_groups    = [aws_security_group.fx_cmp_03_i_x_lb.id]
}

resource "aws_lb_target_group" "fx_cmp_03_i_pool1" {
  name        = "${var.run_id}-fx-cmp-03-i-pool1"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.fx_cmp_03_i_x_vpc.id
  target_type = "instance"
  health_check {
    enabled  = true
    path     = "/"
    protocol = "HTTP"
  }
}

resource "aws_lb_listener" "fx_cmp_03_i_li1" {
  load_balancer_arn = aws_lb.fx_cmp_03_i_lb1.arn
  port              = 443
  protocol          = "HTTP"
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener_rule" "fx_cmp_03_i_ru1" {
  listener_arn = aws_lb_listener.fx_cmp_03_i_li1.arn
  priority     = 100
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.fx_cmp_03_i_pool1.arn
  }
  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

# ==== FX-CMP-04-C (CQ-CMP-04, conforming)

resource "aws_s3_bucket" "fx_cmp_04_c_c1" {
  bucket        = "${var.run_id}-fx-cmp-04-c-c1"
  force_destroy = true
}

resource "aws_s3_account_public_access_block" "fx_cmp_04_c_k1" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ==== FX-CMP-04-N (CQ-CMP-04, nonconforming)

resource "aws_s3_bucket" "fx_cmp_04_n_c1" {
  bucket        = "${var.run_id}-fx-cmp-04-n-c1"
  force_destroy = true
}

resource "aws_s3_bucket" "fx_cmp_04_n_c2" {
  bucket        = "${var.run_id}-fx-cmp-04-n-c2"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "fx_cmp_04_n_k1" {
  bucket                  = aws_s3_bucket.fx_cmp_04_n_c2.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ==== FX-CMP-04-I (CQ-CMP-04, incomplete)

variable "fx_cmp_04_i_c1_bucket" {
  type        = string
  description = "entrada simbólica da fixture FX-CMP-04-I; sem valor de propósito"
}

data "aws_s3_bucket" "fx_cmp_04_i_c1" {
  bucket = var.fx_cmp_04_i_c1_bucket
}

resource "aws_s3_account_public_access_block" "fx_cmp_04_i_k1" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ==== FX-CMP-05-C (CQ-CMP-05, conforming)

resource "aws_vpc" "fx_cmp_05_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_05_c_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cmp_05_c_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cmp_05_c_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cmp_05_c_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cmp_05_c_x_db" {
  name       = "${var.run_id}-fx-cmp-05-c-dbsn"
  subnet_ids = [aws_subnet.fx_cmp_05_c_x_subnet_a.id, aws_subnet.fx_cmp_05_c_x_subnet_b.id]
}

resource "aws_db_instance" "fx_cmp_05_c_i1" {
  identifier                  = "${var.run_id}-fx-cmp-05-c-i1"
  engine                      = "postgres"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  db_subnet_group_name        = aws_db_subnet_group.fx_cmp_05_c_x_db.name
  username                    = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  multi_az                    = false
  db_name                     = "db1"
}

# ==== FX-CMP-05-N (CQ-CMP-05, nonconforming)

resource "aws_vpc" "fx_cmp_05_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_05_n_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cmp_05_n_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cmp_05_n_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cmp_05_n_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cmp_05_n_x_db" {
  name       = "${var.run_id}-fx-cmp-05-n-dbsn"
  subnet_ids = [aws_subnet.fx_cmp_05_n_x_subnet_a.id, aws_subnet.fx_cmp_05_n_x_subnet_b.id]
}

resource "aws_rds_cluster" "fx_cmp_05_n_srv1" {
  cluster_identifier          = "${var.run_id}-fx-cmp-05-n-srv1"
  engine                      = "aurora-postgresql"
  database_name               = "db1"
  master_username             = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  db_subnet_group_name        = aws_db_subnet_group.fx_cmp_05_n_x_db.name
}

# ==== FX-CMP-05-I (CQ-CMP-05, incomplete)

resource "aws_vpc" "fx_cmp_05_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cmp_05_i_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cmp_05_i_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cmp_05_i_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cmp_05_i_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cmp_05_i_x_db" {
  name       = "${var.run_id}-fx-cmp-05-i-dbsn"
  subnet_ids = [aws_subnet.fx_cmp_05_i_x_subnet_a.id, aws_subnet.fx_cmp_05_i_x_subnet_b.id]
}

resource "aws_rds_cluster" "fx_cmp_05_i_srv2" {
  cluster_identifier          = "${var.run_id}-fx-cmp-05-i-srv2"
  engine                      = "aurora-postgresql"
  database_name               = "db1"
  master_username             = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  db_subnet_group_name        = aws_db_subnet_group.fx_cmp_05_i_x_db.name
}

# ==== FX-AUT-01-C (CQ-AUT-01, conforming)

resource "aws_iam_user" "fx_aut_01_c_p1" {
  name = "${var.run_id}-fx-aut-01-c-p1"
}

resource "aws_s3_bucket" "fx_aut_01_c_r1" {
  bucket        = "${var.run_id}-fx-aut-01-c-r1"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_01_c_ps1" {
  name = "${var.run_id}-fx-aut-01-c-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_01_c_a1" {
  user       = aws_iam_user.fx_aut_01_c_p1.name
  policy_arn = aws_iam_policy.fx_aut_01_c_ps1.arn
}

# ==== FX-AUT-01-N (CQ-AUT-01, nonconforming)

resource "aws_iam_user" "fx_aut_01_n_p1" {
  name = "${var.run_id}-fx-aut-01-n-p1"
}

resource "aws_s3_bucket" "fx_aut_01_n_r1" {
  bucket        = "${var.run_id}-fx-aut-01-n-r1"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_01_n_ps1" {
  name = "${var.run_id}-fx-aut-01-n-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_01_n_a1" {
  user       = aws_iam_user.fx_aut_01_n_p1.name
  policy_arn = aws_iam_policy.fx_aut_01_n_ps1.arn
}

resource "aws_iam_user_policy" "fx_aut_01_n_d1" {
  name = "${var.run_id}-fx-aut-01-n-d1"
  user = aws_iam_user.fx_aut_01_n_p1.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Deny"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.fx_aut_01_n_r1.arn}/*"
      },
    ]
  })
}

# ==== FX-AUT-01-I (CQ-AUT-01, incomplete)

resource "aws_iam_user" "fx_aut_01_i_p1" {
  name = "${var.run_id}-fx-aut-01-i-p1"
}

resource "aws_s3_bucket" "fx_aut_01_i_r1" {
  bucket        = "${var.run_id}-fx-aut-01-i-r1"
  force_destroy = true
}

# ==== FX-AUT-02-C (CQ-AUT-02, conforming)

resource "aws_iam_user" "fx_aut_02_c_p1" {
  name = "${var.run_id}-fx-aut-02-c-p1"
}

resource "aws_iam_policy" "fx_aut_02_c_ps1" {
  name = "${var.run_id}-fx-aut-02-c-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_02_c_a1" {
  user       = aws_iam_user.fx_aut_02_c_p1.name
  policy_arn = aws_iam_policy.fx_aut_02_c_ps1.arn
}

resource "aws_iam_policy_attachment" "fx_aut_02_c_doc1" {
  name       = "${var.run_id}-fx-aut-02-c-doc1"
  policy_arn = aws_iam_policy.fx_aut_02_c_ps1.arn
  users      = [aws_iam_user.fx_aut_02_c_p1.name]
}

# ==== FX-AUT-02-N (CQ-AUT-02, nonconforming)

resource "aws_iam_user" "fx_aut_02_n_p1" {
  name = "${var.run_id}-fx-aut-02-n-p1"
}

resource "aws_iam_policy" "fx_aut_02_n_ps1" {
  name = "${var.run_id}-fx-aut-02-n-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_02_n_a1" {
  user       = aws_iam_user.fx_aut_02_n_p1.name
  policy_arn = aws_iam_policy.fx_aut_02_n_ps1.arn
}

resource "aws_iam_policy" "fx_aut_02_n_ps2" {
  name = "${var.run_id}-fx-aut-02-n-ps2"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = format("%s:%s:s3:::%s-*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_02_n_a2" {
  user       = aws_iam_user.fx_aut_02_n_p1.name
  policy_arn = aws_iam_policy.fx_aut_02_n_ps2.arn
}

# ==== FX-AUT-02-I (CQ-AUT-02, incomplete)

variable "fx_aut_02_i_a2_principal" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-02-I; sem valor de propósito"
}

resource "aws_iam_user" "fx_aut_02_i_p1" {
  name = "${var.run_id}-fx-aut-02-i-p1"
}

resource "aws_iam_policy" "fx_aut_02_i_ps1" {
  name = "${var.run_id}-fx-aut-02-i-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_02_i_a1" {
  user       = aws_iam_user.fx_aut_02_i_p1.name
  policy_arn = aws_iam_policy.fx_aut_02_i_ps1.arn
}

resource "aws_iam_policy_attachment" "fx_aut_02_i_doc1" {
  name       = "${var.run_id}-fx-aut-02-i-doc1"
  policy_arn = aws_iam_policy.fx_aut_02_i_ps1.arn
  users      = [var.fx_aut_02_i_a2_principal]
}

# ==== FX-AUT-03-C (CQ-AUT-03, conforming)

resource "aws_iam_user" "fx_aut_03_c_p1" {
  name = "${var.run_id}-fx-aut-03-c-p1"
}

resource "aws_s3_bucket" "fx_aut_03_c_x_child_bucket" {
  bucket        = "${var.run_id}-fx-aut-03-c-x-child-bucket"
  force_destroy = true
}

resource "aws_s3_bucket" "fx_aut_03_c_r2" {
  bucket        = "${var.run_id}-fx-aut-03-c-r2"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_03_c_ps1" {
  name = "${var.run_id}-fx-aut-03-c-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.fx_aut_03_c_x_child_bucket.arn}/*"
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_03_c_a1" {
  user       = aws_iam_user.fx_aut_03_c_p1.name
  policy_arn = aws_iam_policy.fx_aut_03_c_ps1.arn
}

# ==== FX-AUT-03-N (CQ-AUT-03, nonconforming)

resource "aws_iam_user" "fx_aut_03_n_p1" {
  name = "${var.run_id}-fx-aut-03-n-p1"
}

resource "aws_s3_bucket" "fx_aut_03_n_x_child_bucket" {
  bucket        = "${var.run_id}-fx-aut-03-n-x-child-bucket"
  force_destroy = true
}

resource "aws_s3_bucket" "fx_aut_03_n_r2" {
  bucket        = "${var.run_id}-fx-aut-03-n-r2"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_03_n_ps1" {
  name = "${var.run_id}-fx-aut-03-n-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_03_n_a1" {
  user       = aws_iam_user.fx_aut_03_n_p1.name
  policy_arn = aws_iam_policy.fx_aut_03_n_ps1.arn
}

# ==== FX-AUT-03-I (CQ-AUT-03, incomplete)

variable "fx_aut_03_i_child_scope_arn" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-03-I; sem valor de propósito"
}

resource "aws_iam_user" "fx_aut_03_i_p1" {
  name = "${var.run_id}-fx-aut-03-i-p1"
}

resource "aws_s3_bucket" "fx_aut_03_i_x_child_bucket" {
  bucket        = "${var.run_id}-fx-aut-03-i-x-child-bucket"
  force_destroy = true
}

resource "aws_s3_bucket" "fx_aut_03_i_r2" {
  bucket        = "${var.run_id}-fx-aut-03-i-r2"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_03_i_ps1" {
  name = "${var.run_id}-fx-aut-03-i-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = var.fx_aut_03_i_child_scope_arn
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_03_i_a1" {
  user       = aws_iam_user.fx_aut_03_i_p1.name
  policy_arn = aws_iam_policy.fx_aut_03_i_ps1.arn
}

# ==== FX-AUT-04-C (CQ-AUT-04, conforming)

resource "aws_iam_policy" "fx_aut_04_c_ps1" {
  name = "${var.run_id}-fx-aut-04-c-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_group" "fx_aut_04_c_g1" {
  name = "${var.run_id}-fx-aut-04-c-g1"
}

resource "aws_iam_user" "fx_aut_04_c_u1" {
  name = "${var.run_id}-fx-aut-04-c-u1"
}

resource "aws_iam_group_policy_attachment" "fx_aut_04_c_a1" {
  group      = aws_iam_group.fx_aut_04_c_g1.name
  policy_arn = aws_iam_policy.fx_aut_04_c_ps1.arn
}

resource "aws_iam_user_group_membership" "fx_aut_04_c_x_member" {
  user   = aws_iam_user.fx_aut_04_c_u1.name
  groups = [aws_iam_group.fx_aut_04_c_g1.name]
}

# ==== FX-AUT-04-N (CQ-AUT-04, nonconforming)

resource "aws_iam_policy" "fx_aut_04_n_ps1" {
  name = "${var.run_id}-fx-aut-04-n-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_group" "fx_aut_04_n_g1" {
  name = "${var.run_id}-fx-aut-04-n-g1"
}

resource "aws_iam_user" "fx_aut_04_n_u1" {
  name = "${var.run_id}-fx-aut-04-n-u1"
}

resource "aws_iam_group_policy_attachment" "fx_aut_04_n_a1" {
  group      = aws_iam_group.fx_aut_04_n_g1.name
  policy_arn = aws_iam_policy.fx_aut_04_n_ps1.arn
}

# ==== FX-AUT-04-I (CQ-AUT-04, incomplete)

variable "fx_aut_04_i_idp_metadata" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-04-I; sem valor de propósito"
}

resource "aws_iam_policy" "fx_aut_04_i_ps1" {
  name = "${var.run_id}-fx-aut-04-i-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = format("%s:%s:s3:::%s-*/*", "arn", "aws", var.run_id)
      },
    ]
  })
}

resource "aws_iam_saml_provider" "fx_aut_04_i_dir1" {
  name                   = "${var.run_id}-fx-aut-04-i-dir1"
  saml_metadata_document = var.fx_aut_04_i_idp_metadata
}

resource "aws_iam_role" "fx_aut_04_i_a1" {
  name = "${var.run_id}-fx-aut-04-i-a1"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRoleWithSAML"
        Principal = {
          Federated = aws_iam_saml_provider.fx_aut_04_i_dir1.arn
        }
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "fx_aut_04_i_x_ps" {
  role       = aws_iam_role.fx_aut_04_i_a1.name
  policy_arn = aws_iam_policy.fx_aut_04_i_ps1.arn
}

# ==== FX-AUT-05-C (CQ-AUT-05, conforming)

resource "aws_iam_user" "fx_aut_05_c_p1" {
  name = "${var.run_id}-fx-aut-05-c-p1"
}

resource "aws_s3_bucket" "fx_aut_05_c_r1" {
  bucket        = "${var.run_id}-fx-aut-05-c-r1"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_05_c_ps1" {
  name = "${var.run_id}-fx-aut-05-c-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.fx_aut_05_c_r1.arn}/*"
        Condition = {
          IpAddress = {
            "aws:SourceIp" = "198.51.100.0/24"
          }
        }
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_05_c_a1" {
  user       = aws_iam_user.fx_aut_05_c_p1.name
  policy_arn = aws_iam_policy.fx_aut_05_c_ps1.arn
}

# ==== FX-AUT-05-N (CQ-AUT-05, nonconforming)

resource "aws_iam_user" "fx_aut_05_n_p1" {
  name = "${var.run_id}-fx-aut-05-n-p1"
}

resource "aws_s3_bucket" "fx_aut_05_n_r1" {
  bucket        = "${var.run_id}-fx-aut-05-n-r1"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_05_n_ps1" {
  name = "${var.run_id}-fx-aut-05-n-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.fx_aut_05_n_r1.arn}/*"
        Condition = {
          IpAddress = {
            "aws:SourceIp" = "198.51.100.0/24"
          }
        }
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_05_n_a1" {
  user       = aws_iam_user.fx_aut_05_n_p1.name
  policy_arn = aws_iam_policy.fx_aut_05_n_ps1.arn
}

# ==== FX-AUT-05-I (CQ-AUT-05, incomplete)

resource "aws_iam_user" "fx_aut_05_i_p1" {
  name = "${var.run_id}-fx-aut-05-i-p1"
}

resource "aws_s3_bucket" "fx_aut_05_i_r1" {
  bucket        = "${var.run_id}-fx-aut-05-i-r1"
  force_destroy = true
}

resource "aws_iam_policy" "fx_aut_05_i_ps1" {
  name = "${var.run_id}-fx-aut-05-i-ps1"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.fx_aut_05_i_r1.arn}/*"
        Condition = {
          StringEquals = {
            "aws:PrincipalTag/device_posture" = "compliant"
          }
        }
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "fx_aut_05_i_a1" {
  user       = aws_iam_user.fx_aut_05_i_p1.name
  policy_arn = aws_iam_policy.fx_aut_05_i_ps1.arn
}

# ==== FX-NET-01-C (CQ-NET-01, conforming)

resource "aws_vpc" "fx_net_01_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_01_c_sa" {
  vpc_id     = aws_vpc.fx_net_01_c_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_route_table" "fx_net_01_c_rt1" {
  vpc_id = aws_vpc.fx_net_01_c_x_vpc.id
}

resource "aws_route_table_association" "fx_net_01_c_x_rt" {
  subnet_id      = aws_subnet.fx_net_01_c_sa.id
  route_table_id = aws_route_table.fx_net_01_c_rt1.id
}

resource "aws_internet_gateway" "fx_net_01_c_igw" {
  vpc_id = aws_vpc.fx_net_01_c_x_vpc.id
}

resource "aws_route" "fx_net_01_c_rte1" {
  route_table_id         = aws_route_table.fx_net_01_c_rt1.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.fx_net_01_c_igw.id
}

resource "aws_network_acl" "fx_net_01_c_rs1" {
  vpc_id     = aws_vpc.fx_net_01_c_x_vpc.id
  subnet_ids = [aws_subnet.fx_net_01_c_sa.id]
}

resource "aws_security_group" "fx_net_01_c_x_nic" {
  name   = "${var.run_id}-fx-net-01-c-nicsg"
  vpc_id = aws_vpc.fx_net_01_c_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "fx_net_01_c_nic1" {
  subnet_id       = aws_subnet.fx_net_01_c_sa.id
  security_groups = [aws_security_group.fx_net_01_c_x_nic.id]
}

data "aws_ssm_parameter" "fx_net_01_c_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_01_c_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_01_c_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_01_c_nic1.id
  }
}

resource "aws_eip" "fx_net_01_c_ip1" {
  domain            = "vpc"
  network_interface = aws_network_interface.fx_net_01_c_nic1.id
}

resource "aws_network_acl_rule" "fx_net_01_c_r1" {
  network_acl_id = aws_network_acl.fx_net_01_c_rs1.id
  rule_number    = 200
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "203.0.113.0/24"
  from_port      = 443
  to_port        = 443
}

resource "aws_network_acl_rule" "fx_net_01_c_x_egress" {
  network_acl_id = aws_network_acl.fx_net_01_c_rs1.id
  rule_number    = 200
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# ==== FX-NET-01-N (CQ-NET-01, nonconforming)

resource "aws_vpc" "fx_net_01_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_01_n_sa" {
  vpc_id     = aws_vpc.fx_net_01_n_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_route_table" "fx_net_01_n_rt1" {
  vpc_id = aws_vpc.fx_net_01_n_x_vpc.id
}

resource "aws_route_table_association" "fx_net_01_n_x_rt" {
  subnet_id      = aws_subnet.fx_net_01_n_sa.id
  route_table_id = aws_route_table.fx_net_01_n_rt1.id
}

resource "aws_internet_gateway" "fx_net_01_n_igw" {
  vpc_id = aws_vpc.fx_net_01_n_x_vpc.id
}

resource "aws_route" "fx_net_01_n_rte1" {
  route_table_id         = aws_route_table.fx_net_01_n_rt1.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.fx_net_01_n_igw.id
}

resource "aws_network_acl" "fx_net_01_n_rs1" {
  vpc_id     = aws_vpc.fx_net_01_n_x_vpc.id
  subnet_ids = [aws_subnet.fx_net_01_n_sa.id]
}

resource "aws_security_group" "fx_net_01_n_x_nic" {
  name   = "${var.run_id}-fx-net-01-n-nicsg"
  vpc_id = aws_vpc.fx_net_01_n_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "fx_net_01_n_nic1" {
  subnet_id       = aws_subnet.fx_net_01_n_sa.id
  security_groups = [aws_security_group.fx_net_01_n_x_nic.id]
}

data "aws_ssm_parameter" "fx_net_01_n_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_01_n_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_01_n_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_01_n_nic1.id
  }
}

resource "aws_eip" "fx_net_01_n_ip1" {
  domain            = "vpc"
  network_interface = aws_network_interface.fx_net_01_n_nic1.id
}

resource "aws_network_acl_rule" "fx_net_01_n_r1" {
  network_acl_id = aws_network_acl.fx_net_01_n_rs1.id
  rule_number    = 200
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "203.0.113.0/24"
  from_port      = 443
  to_port        = 443
}

resource "aws_network_acl_rule" "fx_net_01_n_x_egress" {
  network_acl_id = aws_network_acl.fx_net_01_n_rs1.id
  rule_number    = 200
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

resource "aws_network_acl_rule" "fx_net_01_n_r2" {
  network_acl_id = aws_network_acl.fx_net_01_n_rs1.id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "deny"
  cidr_block     = "0.0.0.0/0"
  from_port      = 443
  to_port        = 443
}

# ==== FX-NET-01-I (CQ-NET-01, incomplete)

resource "aws_vpc" "fx_net_01_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_01_i_sa" {
  vpc_id     = aws_vpc.fx_net_01_i_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_route_table" "fx_net_01_i_rt1" {
  vpc_id = aws_vpc.fx_net_01_i_x_vpc.id
}

resource "aws_route_table_association" "fx_net_01_i_x_rt" {
  subnet_id      = aws_subnet.fx_net_01_i_sa.id
  route_table_id = aws_route_table.fx_net_01_i_rt1.id
}

resource "aws_internet_gateway" "fx_net_01_i_igw" {
  vpc_id = aws_vpc.fx_net_01_i_x_vpc.id
}

resource "aws_route" "fx_net_01_i_rte1" {
  route_table_id         = aws_route_table.fx_net_01_i_rt1.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.fx_net_01_i_igw.id
}

resource "aws_network_acl" "fx_net_01_i_rs1" {
  vpc_id     = aws_vpc.fx_net_01_i_x_vpc.id
  subnet_ids = [aws_subnet.fx_net_01_i_sa.id]
}

resource "aws_security_group" "fx_net_01_i_x_nic" {
  name   = "${var.run_id}-fx-net-01-i-nicsg"
  vpc_id = aws_vpc.fx_net_01_i_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "fx_net_01_i_nic1" {
  subnet_id       = aws_subnet.fx_net_01_i_sa.id
  security_groups = [aws_security_group.fx_net_01_i_x_nic.id]
}

data "aws_ssm_parameter" "fx_net_01_i_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_01_i_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_01_i_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_01_i_nic1.id
  }
}

resource "aws_eip" "fx_net_01_i_ip1" {
  domain            = "vpc"
  network_interface = aws_network_interface.fx_net_01_i_nic1.id
}

resource "aws_network_acl_rule" "fx_net_01_i_r1" {
  network_acl_id = aws_network_acl.fx_net_01_i_rs1.id
  rule_number    = 200
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "203.0.113.0/24"
  from_port      = 22
  to_port        = 22
}

resource "aws_network_acl_rule" "fx_net_01_i_x_egress" {
  network_acl_id = aws_network_acl.fx_net_01_i_rs1.id
  rule_number    = 200
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# ==== FX-NET-02-C (CQ-NET-02, conforming)

resource "aws_vpc" "fx_net_02_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_security_group" "fx_net_02_c_rs1" {
  name   = "${var.run_id}-fx-net-02-c-rs1"
  vpc_id = aws_vpc.fx_net_02_c_x_vpc.id
}

resource "aws_vpc_security_group_ingress_rule" "fx_net_02_c_r1" {
  security_group_id = aws_security_group.fx_net_02_c_rs1.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "203.0.113.0/24"
}

# ==== FX-NET-02-N (CQ-NET-02, nonconforming)

resource "aws_vpc" "fx_net_02_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_network_acl" "fx_net_02_n_rs1" {
  vpc_id = aws_vpc.fx_net_02_n_x_vpc.id
}

resource "aws_network_acl_rule" "fx_net_02_n_r1" {
  network_acl_id = aws_network_acl.fx_net_02_n_rs1.id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "203.0.113.0/24"
  from_port      = 443
  to_port        = 443
}

# ==== FX-NET-02-I (CQ-NET-02, incomplete): NOT_APPLICABLE — na AWS o estado de conexão não é declarável por regra e o mecanismo fixa o padrão (grupo de segurança com estado, NACL sem estado): a situação 'estado não declarado e padrão sem evidência' não existe

# ==== FX-NET-03-C (CQ-NET-03, conforming)

resource "aws_vpc" "fx_net_03_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_03_c_sa" {
  vpc_id     = aws_vpc.fx_net_03_c_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_route_table" "fx_net_03_c_rt1" {
  vpc_id = aws_vpc.fx_net_03_c_x_vpc.id
}

resource "aws_route_table_association" "fx_net_03_c_x_rt" {
  subnet_id      = aws_subnet.fx_net_03_c_sa.id
  route_table_id = aws_route_table.fx_net_03_c_rt1.id
}

resource "aws_internet_gateway" "fx_net_03_c_igw" {
  vpc_id = aws_vpc.fx_net_03_c_x_vpc.id
}

resource "aws_route" "fx_net_03_c_rte1" {
  route_table_id         = aws_route_table.fx_net_03_c_rt1.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.fx_net_03_c_igw.id
}

resource "aws_security_group" "fx_net_03_c_rs1" {
  name   = "${var.run_id}-fx-net-03-c-rs1"
  vpc_id = aws_vpc.fx_net_03_c_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "fx_net_03_c_nic1" {
  subnet_id       = aws_subnet.fx_net_03_c_sa.id
  security_groups = [aws_security_group.fx_net_03_c_rs1.id]
}

data "aws_ssm_parameter" "fx_net_03_c_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_03_c_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_03_c_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_03_c_nic1.id
  }
}

resource "aws_eip" "fx_net_03_c_ip1" {
  domain            = "vpc"
  network_interface = aws_network_interface.fx_net_03_c_nic1.id
}

# ==== FX-NET-03-N (CQ-NET-03, nonconforming)

resource "aws_vpc" "fx_net_03_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_03_n_sa" {
  vpc_id     = aws_vpc.fx_net_03_n_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_route_table" "fx_net_03_n_rt1" {
  vpc_id = aws_vpc.fx_net_03_n_x_vpc.id
}

resource "aws_route_table_association" "fx_net_03_n_x_rt" {
  subnet_id      = aws_subnet.fx_net_03_n_sa.id
  route_table_id = aws_route_table.fx_net_03_n_rt1.id
}

resource "aws_security_group" "fx_net_03_n_rs1" {
  name   = "${var.run_id}-fx-net-03-n-rs1"
  vpc_id = aws_vpc.fx_net_03_n_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "fx_net_03_n_nic1" {
  subnet_id       = aws_subnet.fx_net_03_n_sa.id
  security_groups = [aws_security_group.fx_net_03_n_rs1.id]
}

data "aws_ssm_parameter" "fx_net_03_n_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_03_n_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_03_n_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_03_n_nic1.id
  }
}

# ==== FX-NET-03-I (CQ-NET-03, incomplete)

variable "fx_net_03_i_route_table_id" {
  type        = string
  description = "entrada simbólica da fixture FX-NET-03-I; sem valor de propósito"
}

resource "aws_vpc" "fx_net_03_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_03_i_sa" {
  vpc_id     = aws_vpc.fx_net_03_i_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_route_table_association" "fx_net_03_i_x_rt" {
  subnet_id      = aws_subnet.fx_net_03_i_sa.id
  route_table_id = var.fx_net_03_i_route_table_id
}

resource "aws_security_group" "fx_net_03_i_rs1" {
  name   = "${var.run_id}-fx-net-03-i-rs1"
  vpc_id = aws_vpc.fx_net_03_i_x_vpc.id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_network_interface" "fx_net_03_i_nic1" {
  subnet_id       = aws_subnet.fx_net_03_i_sa.id
  security_groups = [aws_security_group.fx_net_03_i_rs1.id]
}

data "aws_ssm_parameter" "fx_net_03_i_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_03_i_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_03_i_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_03_i_nic1.id
  }
}

resource "aws_eip" "fx_net_03_i_ip1" {
  domain            = "vpc"
  network_interface = aws_network_interface.fx_net_03_i_nic1.id
}

# ==== FX-NET-04-C (CQ-NET-04, conforming)

resource "aws_vpc" "fx_net_04_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_04_c_x_subnet" {
  vpc_id     = aws_vpc.fx_net_04_c_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_security_group" "fx_net_04_c_rs1" {
  name   = "${var.run_id}-fx-net-04-c-rs1"
  vpc_id = aws_vpc.fx_net_04_c_x_vpc.id
}

resource "aws_network_interface" "fx_net_04_c_nic1" {
  subnet_id = aws_subnet.fx_net_04_c_x_subnet.id
}

data "aws_ssm_parameter" "fx_net_04_c_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_04_c_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_04_c_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_04_c_nic1.id
  }
}

resource "aws_network_interface" "fx_net_04_c_nic2" {
  subnet_id       = aws_subnet.fx_net_04_c_x_subnet.id
  security_groups = [aws_security_group.fx_net_04_c_rs1.id]
}

resource "aws_network_interface_attachment" "fx_net_04_c_x_attach2" {
  instance_id          = aws_instance.fx_net_04_c_vm1.id
  network_interface_id = aws_network_interface.fx_net_04_c_nic2.id
  device_index         = 1
}

# ==== FX-NET-04-N (CQ-NET-04, nonconforming)

resource "aws_vpc" "fx_net_04_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_04_n_x_subnet" {
  vpc_id     = aws_vpc.fx_net_04_n_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_security_group" "fx_net_04_n_rs1" {
  name   = "${var.run_id}-fx-net-04-n-rs1"
  vpc_id = aws_vpc.fx_net_04_n_x_vpc.id
}

resource "aws_network_interface" "fx_net_04_n_nic1" {
  subnet_id = aws_subnet.fx_net_04_n_x_subnet.id
}

data "aws_ssm_parameter" "fx_net_04_n_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_04_n_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_04_n_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_04_n_nic1.id
  }
}

resource "aws_network_interface" "fx_net_04_n_nic3" {
  subnet_id       = aws_subnet.fx_net_04_n_x_subnet.id
  security_groups = [aws_security_group.fx_net_04_n_rs1.id]
}

resource "aws_instance" "fx_net_04_n_vm2" {
  ami           = data.aws_ssm_parameter.fx_net_04_n_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_04_n_nic3.id
  }
}

# ==== FX-NET-04-I (CQ-NET-04, incomplete)

variable "fx_net_04_i_nic2_security_groups" {
  type        = list(string)
  description = "entrada simbólica da fixture FX-NET-04-I; sem valor de propósito"
}

resource "aws_vpc" "fx_net_04_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_net_04_i_x_subnet" {
  vpc_id     = aws_vpc.fx_net_04_i_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_security_group" "fx_net_04_i_rs1" {
  name   = "${var.run_id}-fx-net-04-i-rs1"
  vpc_id = aws_vpc.fx_net_04_i_x_vpc.id
}

resource "aws_network_interface" "fx_net_04_i_nic1" {
  subnet_id = aws_subnet.fx_net_04_i_x_subnet.id
}

data "aws_ssm_parameter" "fx_net_04_i_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_net_04_i_vm1" {
  ami           = data.aws_ssm_parameter.fx_net_04_i_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_net_04_i_nic1.id
  }
}

resource "aws_network_interface" "fx_net_04_i_nic2" {
  subnet_id       = aws_subnet.fx_net_04_i_x_subnet.id
  security_groups = var.fx_net_04_i_nic2_security_groups
}

resource "aws_network_interface_attachment" "fx_net_04_i_x_attach2" {
  instance_id          = aws_instance.fx_net_04_i_vm1.id
  network_interface_id = aws_network_interface.fx_net_04_i_nic2.id
  device_index         = 1
}

# ==== FX-CVO-01-C (CQ-CVO-01, conforming)

resource "aws_s3_bucket" "fx_cvo_01_c_c1" {
  bucket        = "${var.run_id}-fx-cvo-01-c-c1"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_cvo_01_c_d1" {
  bucket = aws_s3_bucket.fx_cvo_01_c_c1.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ==== FX-CVO-01-N (CQ-CVO-01, nonconforming)

resource "aws_s3_bucket" "fx_cvo_01_n_c1" {
  bucket        = "${var.run_id}-fx-cvo-01-n-c1"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_cvo_01_n_d1" {
  bucket = aws_s3_bucket.fx_cvo_01_n_c1.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ==== FX-CVO-01-I (CQ-CVO-01, incomplete)

resource "aws_s3_bucket" "fx_cvo_01_i_c1" {
  bucket        = "${var.run_id}-fx-cvo-01-i-c1"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_cvo_01_i_d1" {
  bucket = aws_s3_bucket.fx_cvo_01_i_c1.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ==== FX-CVO-02-C (CQ-CVO-02, conforming)

resource "aws_s3_bucket" "fx_cvo_02_c_c1" {
  bucket        = "${var.run_id}-fx-cvo-02-c-c1"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_cvo_02_c_x_versioning" {
  bucket = aws_s3_bucket.fx_cvo_02_c_c1.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ==== FX-CVO-02-N (CQ-CVO-02, nonconforming)

resource "aws_s3_bucket" "fx_cvo_02_n_c1" {
  bucket        = "${var.run_id}-fx-cvo-02-n-c1"
  force_destroy = true
}

# ==== FX-CVO-02-I (CQ-CVO-02, incomplete)

variable "fx_cvo_02_i_versioning_status" {
  type        = string
  description = "entrada simbólica da fixture FX-CVO-02-I; sem valor de propósito"
}

resource "aws_s3_bucket" "fx_cvo_02_i_c1" {
  bucket        = "${var.run_id}-fx-cvo-02-i-c1"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_cvo_02_i_x_versioning" {
  bucket = aws_s3_bucket.fx_cvo_02_i_c1.id
  versioning_configuration {
    status = var.fx_cvo_02_i_versioning_status
  }
}

# ==== FX-CVO-03-C (CQ-CVO-03, conforming)

resource "aws_vpc" "fx_cvo_03_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cvo_03_c_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cvo_03_c_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cvo_03_c_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cvo_03_c_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cvo_03_c_x_db" {
  name       = "${var.run_id}-fx-cvo-03-c-dbsn"
  subnet_ids = [aws_subnet.fx_cvo_03_c_x_subnet_a.id, aws_subnet.fx_cvo_03_c_x_subnet_b.id]
}

resource "aws_db_instance" "fx_cvo_03_c_i1" {
  identifier                  = "${var.run_id}-fx-cvo-03-c-i1"
  engine                      = "postgres"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  db_subnet_group_name        = aws_db_subnet_group.fx_cvo_03_c_x_db.name
  username                    = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  multi_az                    = false
}

resource "aws_sns_topic" "fx_cvo_03_c_t1" {
  name = "${var.run_id}-fx-cvo-03-c-t1"
}

resource "aws_cloudwatch_metric_alarm" "fx_cvo_03_c_al1" {
  alarm_name          = "${var.run_id}-fx-cvo-03-c-al1"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 1
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  dimensions = {
    DBInstanceIdentifier = aws_db_instance.fx_cvo_03_c_i1.identifier
  }
  alarm_actions = [aws_sns_topic.fx_cvo_03_c_t1.arn]
}

# ==== FX-CVO-03-N (CQ-CVO-03, nonconforming)

resource "aws_vpc" "fx_cvo_03_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cvo_03_n_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cvo_03_n_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cvo_03_n_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cvo_03_n_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cvo_03_n_x_db" {
  name       = "${var.run_id}-fx-cvo-03-n-dbsn"
  subnet_ids = [aws_subnet.fx_cvo_03_n_x_subnet_a.id, aws_subnet.fx_cvo_03_n_x_subnet_b.id]
}

resource "aws_db_instance" "fx_cvo_03_n_i1" {
  identifier                  = "${var.run_id}-fx-cvo-03-n-i1"
  engine                      = "postgres"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  db_subnet_group_name        = aws_db_subnet_group.fx_cvo_03_n_x_db.name
  username                    = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  multi_az                    = false
}

# ==== FX-CVO-03-I (CQ-CVO-03, incomplete)

resource "aws_vpc" "fx_cvo_03_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cvo_03_i_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cvo_03_i_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cvo_03_i_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cvo_03_i_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cvo_03_i_x_db" {
  name       = "${var.run_id}-fx-cvo-03-i-dbsn"
  subnet_ids = [aws_subnet.fx_cvo_03_i_x_subnet_a.id, aws_subnet.fx_cvo_03_i_x_subnet_b.id]
}

resource "aws_db_instance" "fx_cvo_03_i_i1" {
  identifier                  = "${var.run_id}-fx-cvo-03-i-i1"
  engine                      = "postgres"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  db_subnet_group_name        = aws_db_subnet_group.fx_cvo_03_i_x_db.name
  username                    = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  multi_az                    = false
}

# ==== FX-CVO-04-C (CQ-CVO-04, conforming)

resource "aws_vpc" "fx_cvo_04_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cvo_04_c_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cvo_04_c_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cvo_04_c_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cvo_04_c_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cvo_04_c_x_db" {
  name       = "${var.run_id}-fx-cvo-04-c-dbsn"
  subnet_ids = [aws_subnet.fx_cvo_04_c_x_subnet_a.id, aws_subnet.fx_cvo_04_c_x_subnet_b.id]
}

resource "aws_db_instance" "fx_cvo_04_c_i1" {
  identifier                  = "${var.run_id}-fx-cvo-04-c-i1"
  engine                      = "postgres"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  db_subnet_group_name        = aws_db_subnet_group.fx_cvo_04_c_x_db.name
  username                    = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  multi_az                    = false
}

# ==== FX-CVO-04-N (CQ-CVO-04, nonconforming)

resource "aws_vpc" "fx_cvo_04_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cvo_04_n_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cvo_04_n_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cvo_04_n_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cvo_04_n_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cvo_04_n_x_db" {
  name       = "${var.run_id}-fx-cvo-04-n-dbsn"
  subnet_ids = [aws_subnet.fx_cvo_04_n_x_subnet_a.id, aws_subnet.fx_cvo_04_n_x_subnet_b.id]
}

resource "aws_db_instance" "fx_cvo_04_n_x_primary" {
  identifier                  = "${var.run_id}-fx-cvo-04-n-x-primary"
  engine                      = "postgres"
  instance_class              = "db.t4g.micro"
  allocated_storage           = 20
  db_subnet_group_name        = aws_db_subnet_group.fx_cvo_04_n_x_db.name
  username                    = "boadmin"
  manage_master_user_password = true
  skip_final_snapshot         = true
  multi_az                    = false
}

resource "aws_db_instance" "fx_cvo_04_n_i1" {
  identifier          = "${var.run_id}-fx-cvo-04-n-i1"
  replicate_source_db = aws_db_instance.fx_cvo_04_n_x_primary.identifier
  instance_class      = "db.t4g.micro"
  skip_final_snapshot = true
}

# ==== FX-CVO-04-I (CQ-CVO-04, incomplete)

variable "fx_cvo_04_i_admin_password" {
  type        = string
  description = "entrada simbólica da fixture FX-CVO-04-I; sem valor de propósito"
  sensitive   = true
}

resource "aws_vpc" "fx_cvo_04_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_cvo_04_i_x_subnet_a" {
  vpc_id            = aws_vpc.fx_cvo_04_i_x_vpc.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = "${var.location_1}a"
}

resource "aws_subnet" "fx_cvo_04_i_x_subnet_b" {
  vpc_id            = aws_vpc.fx_cvo_04_i_x_vpc.id
  cidr_block        = "10.20.2.0/24"
  availability_zone = "${var.location_1}b"
}

resource "aws_db_subnet_group" "fx_cvo_04_i_x_db" {
  name       = "${var.run_id}-fx-cvo-04-i-dbsn"
  subnet_ids = [aws_subnet.fx_cvo_04_i_x_subnet_a.id, aws_subnet.fx_cvo_04_i_x_subnet_b.id]
}

resource "aws_db_instance" "fx_cvo_04_i_i1" {
  identifier           = "${var.run_id}-fx-cvo-04-i-i1"
  engine               = "postgres"
  instance_class       = "db.t4g.micro"
  allocated_storage    = 20
  db_subnet_group_name = aws_db_subnet_group.fx_cvo_04_i_x_db.name
  username             = "boadmin"
  password             = var.fx_cvo_04_i_admin_password
  skip_final_snapshot  = true
  multi_az             = false
}

# ==== FX-LOSS-01-C (CQ-LOSS-01, conforming)

resource "aws_cloudwatch_log_group" "fx_loss_01_c_s1" {
  name              = "${var.run_id}/fx/loss/01/c/s1"
  retention_in_days = 30
}

# ==== FX-LOSS-01-N (CQ-LOSS-01, nonconforming)

resource "aws_cloudwatch_log_group" "fx_loss_01_n_s1" {
  name              = "${var.run_id}/fx/loss/01/n/s1"
  retention_in_days = 400
}

# ==== FX-LOSS-01-I (CQ-LOSS-01, incomplete)

resource "aws_cloudwatch_log_group" "fx_loss_01_i_s1" {
  name              = "${var.run_id}/fx/loss/01/i/s1"
  retention_in_days = 30
}

# ==== FX-LOSS-02-C (CQ-LOSS-02, conforming)

resource "aws_vpc" "fx_loss_02_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_network_acl" "fx_loss_02_c_rs1" {
  vpc_id = aws_vpc.fx_loss_02_c_x_vpc.id
}

resource "aws_network_acl_rule" "fx_loss_02_c_r1" {
  network_acl_id = aws_network_acl.fx_loss_02_c_rs1.id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "deny"
  cidr_block     = "0.0.0.0/0"
  from_port      = 22
  to_port        = 22
}

# ==== FX-LOSS-02-N (CQ-LOSS-02, nonconforming)

resource "aws_vpc" "fx_loss_02_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_network_acl" "fx_loss_02_n_rs1" {
  vpc_id = aws_vpc.fx_loss_02_n_x_vpc.id
}

resource "aws_network_acl_rule" "fx_loss_02_n_r1" {
  network_acl_id = aws_network_acl.fx_loss_02_n_rs1.id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "deny"
  cidr_block     = "0.0.0.0/0"
  from_port      = 22
  to_port        = 22
}

# ==== FX-LOSS-02-I (CQ-LOSS-02, incomplete)

resource "aws_vpc" "fx_loss_02_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_network_acl" "fx_loss_02_i_rs1" {
  vpc_id = aws_vpc.fx_loss_02_i_x_vpc.id
}

resource "aws_network_acl_rule" "fx_loss_02_i_r1" {
  network_acl_id = aws_network_acl.fx_loss_02_i_rs1.id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "deny"
  cidr_block     = "0.0.0.0/0"
  from_port      = 22
  to_port        = 22
}

# ==== FX-LOSS-03-C (CQ-LOSS-03, conforming)

resource "aws_s3_bucket" "fx_loss_03_c_x_bucket" {
  bucket        = "${var.run_id}-fx-loss-03-c-x-bucket"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_loss_03_c_s1" {
  bucket = aws_s3_bucket.fx_loss_03_c_x_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ==== FX-LOSS-03-N (CQ-LOSS-03, nonconforming)

resource "aws_s3_bucket" "fx_loss_03_n_x_bucket" {
  bucket        = "${var.run_id}-fx-loss-03-n-x-bucket"
  force_destroy = true
}

# ==== FX-LOSS-03-I (CQ-LOSS-03, incomplete)

variable "fx_loss_03_i_versioning_status" {
  type        = string
  description = "entrada simbólica da fixture FX-LOSS-03-I; sem valor de propósito"
}

resource "aws_s3_bucket" "fx_loss_03_i_x_bucket" {
  bucket        = "${var.run_id}-fx-loss-03-i-x-bucket"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_loss_03_i_s1" {
  bucket = aws_s3_bucket.fx_loss_03_i_x_bucket.id
  versioning_configuration {
    status = var.fx_loss_03_i_versioning_status
  }
}

# ==== FX-LOSS-04-C (CQ-LOSS-04, conforming)

resource "aws_cloudwatch_log_group" "fx_loss_04_c_s1" {
  name              = "${var.run_id}/fx/loss/04/c/s1"
  retention_in_days = 7
}

# ==== FX-LOSS-04-N (CQ-LOSS-04, nonconforming)

resource "aws_s3_bucket" "fx_loss_04_n_x_bucket" {
  bucket        = "${var.run_id}-fx-loss-04-n-x-bucket"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_loss_04_n_x_versioning" {
  bucket = aws_s3_bucket.fx_loss_04_n_x_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "fx_loss_04_n_s1" {
  bucket = aws_s3_bucket.fx_loss_04_n_x_bucket.id
  rule {
    default_retention {
      mode  = "GOVERNANCE"
      years = 1
    }
  }
}

# ==== FX-LOSS-04-I (CQ-LOSS-04, incomplete)

variable "fx_loss_04_i_vpc_id" {
  type        = string
  description = "entrada simbólica da fixture FX-LOSS-04-I; sem valor de propósito"
}

resource "aws_lb_target_group" "fx_loss_04_i_s1" {
  name                 = "${var.run_id}-fx-loss-04-i-s1"
  port                 = 80
  protocol             = "HTTP"
  deregistration_delay = 30
  vpc_id               = var.fx_loss_04_i_vpc_id
}

# ==== FX-NEW-01-C (CQ-NEW-01, conforming)

resource "aws_s3_bucket" "fx_new_01_c_x_bucket" {
  bucket        = "${var.run_id}-fx-new-01-c-x-bucket"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "fx_new_01_c_s1" {
  bucket = aws_s3_bucket.fx_new_01_c_x_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ==== FX-NEW-01-N (CQ-NEW-01, nonconforming)

resource "aws_s3_bucket" "fx_new_01_n_x_bucket" {
  bucket        = "${var.run_id}-fx-new-01-n-x-bucket"
  force_destroy = true
}

resource "aws_s3_bucket_accelerate_configuration" "fx_new_01_n_s2" {
  bucket = aws_s3_bucket.fx_new_01_n_x_bucket.id
  status = "Enabled"
}

# ==== FX-NEW-01-I (CQ-NEW-01, incomplete)

resource "aws_s3_bucket" "fx_new_01_i_x_bucket" {
  bucket        = "${var.run_id}-fx-new-01-i-x-bucket"
  force_destroy = true
}

resource "aws_s3_bucket_request_payment_configuration" "fx_new_01_i_src3" {
  bucket = aws_s3_bucket.fx_new_01_i_x_bucket.id
  payer  = "Requester"
}

# ==== FX-NEW-02-C (CQ-NEW-02, conforming)

resource "aws_vpc" "fx_new_02_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_new_02_c_x_subnet" {
  vpc_id     = aws_vpc.fx_new_02_c_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_network_interface" "fx_new_02_c_nic1" {
  subnet_id = aws_subnet.fx_new_02_c_x_subnet.id
}

data "aws_ssm_parameter" "fx_new_02_c_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_new_02_c_vm1" {
  ami           = data.aws_ssm_parameter.fx_new_02_c_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_new_02_c_nic1.id
  }
}

resource "aws_network_interface" "fx_new_02_c_nic2" {
  subnet_id = aws_subnet.fx_new_02_c_x_subnet.id
}

resource "aws_network_interface_attachment" "fx_new_02_c_x_attach2" {
  instance_id          = aws_instance.fx_new_02_c_vm1.id
  network_interface_id = aws_network_interface.fx_new_02_c_nic2.id
  device_index         = 1
}

# ==== FX-NEW-02-N (CQ-NEW-02, nonconforming)

resource "aws_vpc" "fx_new_02_n_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_new_02_n_x_subnet" {
  vpc_id     = aws_vpc.fx_new_02_n_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_network_interface" "fx_new_02_n_nic1" {
  subnet_id         = aws_subnet.fx_new_02_n_x_subnet.id
  private_ips_count = 1
}

data "aws_ssm_parameter" "fx_new_02_n_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_new_02_n_vm1" {
  ami           = data.aws_ssm_parameter.fx_new_02_n_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_new_02_n_nic1.id
  }
}

# ==== FX-NEW-02-I (CQ-NEW-02, incomplete)

variable "fx_new_02_i_nic2_instance_id" {
  type        = string
  description = "entrada simbólica da fixture FX-NEW-02-I; sem valor de propósito"
}

resource "aws_vpc" "fx_new_02_i_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_subnet" "fx_new_02_i_x_subnet" {
  vpc_id     = aws_vpc.fx_new_02_i_x_vpc.id
  cidr_block = "10.20.1.0/24"
}

resource "aws_network_interface" "fx_new_02_i_nic1" {
  subnet_id = aws_subnet.fx_new_02_i_x_subnet.id
}

data "aws_ssm_parameter" "fx_new_02_i_x_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "fx_new_02_i_vm1" {
  ami           = data.aws_ssm_parameter.fx_new_02_i_x_ami.value
  instance_type = "t4g.nano"
  primary_network_interface {
    network_interface_id = aws_network_interface.fx_new_02_i_nic1.id
  }
}

resource "aws_network_interface" "fx_new_02_i_nic2" {
  subnet_id = aws_subnet.fx_new_02_i_x_subnet.id
}

resource "aws_network_interface_attachment" "fx_new_02_i_x_attach2" {
  instance_id          = var.fx_new_02_i_nic2_instance_id
  network_interface_id = aws_network_interface.fx_new_02_i_nic2.id
  device_index         = 1
}

# ==== FX-NEW-03-C (CQ-NEW-03, conforming)

resource "aws_vpc" "fx_new_03_c_x_vpc" {
  cidr_block = "10.20.0.0/16"
}

resource "aws_network_acl" "fx_new_03_c_rs1" {
  vpc_id = aws_vpc.fx_new_03_c_x_vpc.id
}

resource "aws_network_acl_rule" "fx_new_03_c_r1" {
  network_acl_id = aws_network_acl.fx_new_03_c_rs1.id
  rule_number    = 100
  egress         = false
  protocol       = "tcp"
  rule_action    = "deny"
  cidr_block     = "0.0.0.0/0"
  from_port      = 22
  to_port        = 22
}

# ==== FX-NEW-03-N (CQ-NEW-03, nonconforming)

resource "aws_networkfirewall_rule_group" "fx_new_03_n_rs1" {
  name     = "${var.run_id}-fx-new-03-n-rs1"
  capacity = 10
  type     = "STATEFUL"
  rule_group {
    rules_source {
      rules_string = "drop tcp any any -> any 22 (msg:\"r1\"; sid:1;)\n"
    }
    stateful_rule_options {
      rule_order = "STRICT_ORDER"
    }
  }
}

# ==== FX-NEW-03-I (CQ-NEW-03, incomplete)

resource "aws_networkfirewall_rule_group" "fx_new_03_i_rs1" {
  name     = "${var.run_id}-fx-new-03-i-rs1"
  capacity = 10
  type     = "STATEFUL"
  rule_group {
    rules_source {
      stateful_rule {
        action = "DROP"
        header {
          destination      = "ANY"
          destination_port = "22"
          direction        = "FORWARD"
          protocol         = "TCP"
          source           = "ANY"
          source_port      = "ANY"
        }
        rule_option {
          keyword  = "sid"
          settings = ["1"]
        }
      }
    }
  }
}
