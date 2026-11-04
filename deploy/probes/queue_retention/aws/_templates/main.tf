# Sonda queue_retention no aws (PROBEKIT, kit 1.0.0, protocolo 1.0.0 do PREREG). O mesmo template serve ao caso e ao
# controle negativo: o lado entra pelo arquivo side_case.tf ou side_control.tf, que só define os locals do lado.
# Nomes: var.bo_names (nome sintético bo-<lote>-NNNN do manifesto de intenção do SAFETY); tag bo-run = var.bo_run_id.
# Nenhum valor de execução tem default; conta, projeto e assinatura chegam do runner pelo ambiente.

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
  region              = var.bo_region
  allowed_account_ids = var.bo_allowed_account_ids
}

variable "bo_region" {
  type     = string
  nullable = false
}

variable "bo_run_id" {
  type     = string
  nullable = false
}

variable "bo_names" {
  type    = map(string)
  default = {}
}

variable "bo_allowed_account_ids" {
  type      = list(string)
  nullable  = false
  sensitive = true
}

resource "aws_sqs_queue" "probe" {
  count                     = 3
  name                      = lookup(var.bo_names, "aws_sqs_queue.probe[${count.index}]", "bo-plan-000${count.index}")
  message_retention_seconds = local.bo_retention_seconds
  sqs_managed_sse_enabled   = true
  tags = {
    "bo-run" = var.bo_run_id
  }
}
