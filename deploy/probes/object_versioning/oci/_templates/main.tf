# Sonda object_versioning no oci (PROBEKIT, kit 1.0.0, protocolo 1.0.0 do PREREG). O mesmo template serve ao caso e ao
# controle negativo: o lado entra pelo arquivo side_case.tf ou side_control.tf, que só define os locals do lado.
# Nomes: var.bo_names (nome sintético bo-<lote>-NNNN do manifesto de intenção do SAFETY); tag bo-run = var.bo_run_id.
# Nenhum valor de execução tem default; conta, projeto e assinatura chegam do runner pelo ambiente.

terraform {
  required_version = "= 1.15.8"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "= 9.11.0"
    }
  }
}

provider "oci" {
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

variable "bo_compartment_id" {
  type      = string
  nullable  = false
  sensitive = true
}

data "oci_objectstorage_namespace" "probe" {
  compartment_id = var.bo_compartment_id
}

resource "oci_objectstorage_bucket" "probe" {
  compartment_id = var.bo_compartment_id
  namespace      = data.oci_objectstorage_namespace.probe.namespace
  name           = lookup(var.bo_names, "oci_objectstorage_bucket.probe", "bo-plan-0000")
  access_type    = "NoPublicAccess"
  storage_tier   = "Standard"
  versioning     = local.bo_versioning
  freeform_tags = {
    "bo-run" = var.bo_run_id
  }
}
