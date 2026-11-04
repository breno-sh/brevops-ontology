# HARNESS-OCI: plano LP-OCI-STO-0001 (grafo GIR-OCI-STO-0001), oci 9.11.0.
# Gerado por bo.harness.oci.render; cada atributo vem do plano (ver render_report.json), salvo a tag bo-run declarada (HI-OCI-01).

terraform {
  required_providers {
    oci = { source = "oracle/oci", version = "= 9.11.0" }
  }
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

resource "oci_objectstorage_bucket" "r1" {
  access_type    = "NoPublicAccess"
  compartment_id = var.bo_ctx_compartment_id
  freeform_tags  = { "bo-run" = var.bo_ctx_run_tag }
  name           = "bo-sto-0001"
  namespace      = var.bo_ctx_objectstorage_namespace
  versioning     = "Enabled"
}

resource "oci_objectstorage_object_lifecycle_policy" "c1" {
  bucket    = oci_objectstorage_bucket.r1.name
  namespace = var.bo_ctx_objectstorage_namespace
  rules {
    action      = "DELETE"
    is_enabled  = true
    name        = "bo-sto-0001-expire"
    target      = "objects"
    time_amount = "30"
    time_unit   = "DAYS"
  }
}
