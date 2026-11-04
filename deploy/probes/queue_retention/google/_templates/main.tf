# Sonda queue_retention no google (PROBEKIT, kit 1.0.0, protocolo 1.0.0 do PREREG). O mesmo template serve ao caso e ao
# controle negativo: o lado entra pelo arquivo side_case.tf ou side_control.tf, que só define os locals do lado.
# Nomes: var.bo_names (nome sintético bo-<lote>-NNNN do manifesto de intenção do SAFETY); tag bo-run = var.bo_run_id.
# Nenhum valor de execução tem default; conta, projeto e assinatura chegam do runner pelo ambiente.

terraform {
  required_version = "= 1.15.8"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.9.0"
    }
  }
}

provider "google" {
  region = var.bo_region
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

resource "google_pubsub_topic" "probe" {
  count = 3
  name  = lookup(var.bo_names, "google_pubsub_topic.probe[${count.index}]", "bo-plan-000${count.index}")
  labels = {
    "bo-run" = var.bo_run_id
  }
}

resource "google_pubsub_subscription" "probe" {
  count                      = 3
  name                       = lookup(var.bo_names, "google_pubsub_subscription.probe[${count.index}]", "bo-plan-100${count.index}")
  topic                      = google_pubsub_topic.probe[count.index].id
  message_retention_duration = local.bo_retention_duration
  labels = {
    "bo-run" = var.bo_run_id
  }
}
