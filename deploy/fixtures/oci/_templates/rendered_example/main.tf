# HARNESS-OCI: raiz renderizada; 4 de 4 plano(s) renderizado(s).
# Situação de cada plano em render_report.json.

terraform {
  required_version = "= 1.15.8"
  required_providers {
    oci = { source = "oracle/oci", version = "= 9.11.0" }
  }
}

provider "oci" {
  region = var.bo_region
}

variable "bo_ctx_compartment_id" {
  type = string
}

variable "bo_ctx_objectstorage_namespace" {
  type = string
}

variable "bo_ctx_run_tag" {
  type = string
}

variable "bo_region" {
  type = string
}

module "lp_oci_net_0001" {
  source                = "./lp_oci_net_0001"
  bo_ctx_compartment_id = var.bo_ctx_compartment_id
  bo_ctx_run_tag        = var.bo_ctx_run_tag
}

module "lp_oci_sto_0001" {
  source                         = "./lp_oci_sto_0001"
  bo_ctx_compartment_id          = var.bo_ctx_compartment_id
  bo_ctx_objectstorage_namespace = var.bo_ctx_objectstorage_namespace
  bo_ctx_run_tag                 = var.bo_ctx_run_tag
}

module "lp_oci_net_0002" {
  source                = "./lp_oci_net_0002"
  bo_ctx_compartment_id = var.bo_ctx_compartment_id
  bo_ctx_run_tag        = var.bo_ctx_run_tag
}

module "lp_oci_net_0003" {
  source                = "./lp_oci_net_0003"
  bo_ctx_compartment_id = var.bo_ctx_compartment_id
  bo_ctx_run_tag        = var.bo_ctx_run_tag
}
