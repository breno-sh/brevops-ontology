# Sonda object_versioning no azurerm (PROBEKIT, kit 1.0.0, protocolo 1.0.0 do PREREG). O mesmo template serve ao caso e ao
# controle negativo: o lado entra pelo arquivo side_case.tf ou side_control.tf, que só define os locals do lado.
# Nomes: var.bo_names (nome sintético bo-<lote>-NNNN do manifesto de intenção do SAFETY); tag bo-run = var.bo_run_id.
# Nenhum valor de execução tem default; conta, projeto e assinatura chegam do runner pelo ambiente.

terraform {
  required_version = "= 1.15.8"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 5.12.0"
    }
  }
}

provider "azurerm" {
  features {}
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

resource "azurerm_resource_group" "probe" {
  name     = lookup(var.bo_names, "azurerm_resource_group.probe", "bo-plan-0000")
  location = var.bo_region
  tags = {
    "bo-run" = var.bo_run_id
  }
}

resource "azurerm_storage_account" "probe" {
  name                            = "bo${substr(sha1(lookup(var.bo_names, "azurerm_storage_account.probe", "bo-plan-0000")), 0, 22)}"
  resource_group_name             = azurerm_resource_group.probe.name
  location                        = var.bo_region
  account_kind                    = "StorageV2"
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  access_tier                     = "Hot"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags = {
    "bo-run" = var.bo_run_id
  }
  blob_properties {
    versioning_enabled = local.bo_versioning_enabled
  }
}

resource "azurerm_storage_container" "probe" {
  name                  = lookup(var.bo_names, "azurerm_storage_container.probe", "bo-plan-0000")
  storage_account_id    = azurerm_storage_account.probe.id
  container_access_type = "private"
}
