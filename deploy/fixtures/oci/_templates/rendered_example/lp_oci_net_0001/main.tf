# HARNESS-OCI: plano LP-OCI-NET-0001 (grafo GIR-OCI-NET-0001), oci 9.11.0.
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
  cidr_blocks    = ["10.0.0.0/16"]
  compartment_id = var.bo_ctx_compartment_id
  display_name   = "bo-net-0001-vcn"
  freeform_tags  = { "bo-run" = var.bo_ctx_run_tag }
}

resource "oci_core_security_list" "r2" {
  compartment_id = var.bo_ctx_compartment_id
  display_name   = "bo-net-0001-sl"
  freeform_tags  = { "bo-run" = var.bo_ctx_run_tag }
  vcn_id         = oci_core_vcn.r1.id
  egress_security_rules {
    destination = "10.0.0.0/16"
    protocol    = "all"
  }
  ingress_security_rules {
    protocol  = "6"
    source    = "10.0.1.0/24"
    stateless = false
    tcp_options {
      max = 22
      min = 22
    }
  }
  ingress_security_rules {
    protocol  = "17"
    source    = "10.0.2.0/24"
    stateless = true
    udp_options {
      max = 53
      min = 53
    }
  }
}

resource "oci_core_network_security_group" "r3" {
  compartment_id = var.bo_ctx_compartment_id
  display_name   = "bo-net-0001-nsg"
  freeform_tags  = { "bo-run" = var.bo_ctx_run_tag }
  vcn_id         = oci_core_vcn.r1.id
}

resource "oci_core_network_security_group_security_rule" "c1" {
  direction                 = "INGRESS"
  network_security_group_id = oci_core_network_security_group.r3.id
  protocol                  = "6"
  source                    = "10.0.3.0/24"
  source_type               = "CIDR_BLOCK"
  stateless                 = false
  tcp_options {
    destination_port_range {
      max = 443
      min = 443
    }
  }
}
