# HARNESS-OCI: plano LP-OCI-NET-0003 (grafo GIR-OCI-NET-0003), oci 9.11.0.
# Gerado por bo.harness.oci.render; cada atributo vem do plano (ver render_report.json), salvo a tag bo-run declarada (HI-OCI-01).

terraform {
  required_providers {
    oci = { source = "oracle/oci", version = "= 9.11.0" }
  }
}

variable "bo_ctx_compartment_id" {
  type = string
}

variable "bo_ctx_run_tag" {
  type = string
}

resource "oci_core_vcn" "r1" {
  cidr_blocks    = ["10.3.0.0/16"]
  compartment_id = var.bo_ctx_compartment_id
  display_name   = "bo-net-0003-vcn"
  freeform_tags  = { "bo-run" = var.bo_ctx_run_tag }
}

resource "oci_core_security_list" "r2" {
  compartment_id = var.bo_ctx_compartment_id
  display_name   = "bo-net-0003-sl-a"
  freeform_tags  = { "bo-run" = var.bo_ctx_run_tag }
  vcn_id         = oci_core_vcn.r1.id
}

resource "oci_core_security_list" "r3" {
  compartment_id = var.bo_ctx_compartment_id
  display_name   = "bo-net-0003-sl-b"
  freeform_tags  = { "bo-run" = var.bo_ctx_run_tag }
  vcn_id         = oci_core_vcn.r1.id
}

resource "oci_core_subnet" "r4" {
  cidr_block        = "10.3.1.0/24"
  compartment_id    = var.bo_ctx_compartment_id
  display_name      = "bo-net-0003-subnet"
  freeform_tags     = { "bo-run" = var.bo_ctx_run_tag }
  security_list_ids = [oci_core_security_list.r2.id, oci_core_security_list.r3.id]
  vcn_id            = oci_core_vcn.r1.id
}
