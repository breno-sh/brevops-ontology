# Fixtures das CQs (CQFIX) no provider azurerm — gerado por bo.cqfix.build; não editar.
# Cada seção é uma fixture (FX-...) e só ela; o conjunto de endereços de cada uma está em
# expected_answers.json. Valores reais (conta, região, projeto) nunca entram: vêm das variáveis
# de contexto, ligadas pelo runner do DEP. Variáveis fx_* sem valor são entradas simbólicas de
# fixtures incompletas, de propósito.

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
  subscription_id = var.subscription_id
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
  description = "localização l1 das fixtures (região Azure); ligada pelo runner"
}

variable "location_2" {
  type        = string
  description = "localização l2, distinta de l1; ligada pelo runner"
}

variable "subscription_id" {
  type        = string
  description = "assinatura sandbox (Azure for Students); ligada pelo runner, nunca gravada"
}

variable "admin_ssh_public_key" {
  type        = string
  description = "chave SSH PÚBLICA gerada na hora pelo runner para as VMs; a privada nunca sai do runner"
}

variable "db_admin_password" {
  type        = string
  description = "senha administrativa gerada na hora pelo runner (Withheld; nunca gravada)"
  sensitive   = true
}

# ==== FX-CIS-01-C (CQ-CIS-01, conforming): NOT_APPLICABLE — o segundo fator do principal humano é configurado no Entra ID, fora do provider azurerm fixado

# ==== FX-CIS-01-N (CQ-CIS-01, nonconforming): NOT_APPLICABLE — o segundo fator do principal humano é configurado no Entra ID, fora do provider azurerm fixado

# ==== FX-CIS-01-I (CQ-CIS-01, incomplete): NOT_APPLICABLE — o segundo fator do principal humano é configurado no Entra ID, fora do provider azurerm fixado

# ==== FX-CIS-02-C (CQ-CIS-02, conforming)

resource "azurerm_resource_group" "fx_cis_02_c_x_rg" {
  name     = "${var.run_id}-fx-cis-02-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cis_02_c_k1" {
  name                     = "${var.run_id}fxcis02ck1"
  resource_group_name      = azurerm_resource_group.fx_cis_02_c_x_rg.name
  location                 = azurerm_resource_group.fx_cis_02_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

# ==== FX-CIS-02-N (CQ-CIS-02, nonconforming)

resource "azurerm_resource_group" "fx_cis_02_n_x_rg" {
  name     = "${var.run_id}-fx-cis-02-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cis_02_n_k1" {
  name                     = "${var.run_id}fxcis02nk1"
  resource_group_name      = azurerm_resource_group.fx_cis_02_n_x_rg.name
  location                 = azurerm_resource_group.fx_cis_02_n_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

# ==== FX-CIS-02-I (CQ-CIS-02, incomplete)

resource "azurerm_resource_group" "fx_cis_02_i_x_rg" {
  name     = "${var.run_id}-fx-cis-02-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cis_02_i_k1" {
  name                     = "${var.run_id}fxcis02ik1"
  resource_group_name      = azurerm_resource_group.fx_cis_02_i_x_rg.name
  location                 = azurerm_resource_group.fx_cis_02_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

# ==== FX-CIS-03-C (CQ-CIS-03, conforming)

resource "azurerm_resource_group" "fx_cis_03_c_x_rg" {
  name     = "${var.run_id}-fx-cis-03-c-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cis_03_c_x_client" {
}

resource "azurerm_key_vault" "fx_cis_03_c_x_kv" {
  name                       = "${var.run_id}fxcis03ckv"
  resource_group_name        = azurerm_resource_group.fx_cis_03_c_x_rg.name
  location                   = azurerm_resource_group.fx_cis_03_c_x_rg.location
  tenant_id                  = data.azurerm_client_config.fx_cis_03_c_x_client.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  rbac_authorization_enabled = true
}

resource "azurerm_role_assignment" "fx_cis_03_c_x_kv_officer" {
  scope                = azurerm_key_vault.fx_cis_03_c_x_kv.id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = data.azurerm_client_config.fx_cis_03_c_x_client.object_id
}

resource "azurerm_key_vault_key" "fx_cis_03_c_k1" {
  name         = "${var.run_id}-fx-cis-03-c-k1"
  key_vault_id = azurerm_key_vault.fx_cis_03_c_x_kv.id
  key_type     = "RSA"
  key_size     = 2048
  key_opts     = ["encrypt", "decrypt"]
  rotation_policy {
    expire_after         = "P180D"
    notify_before_expiry = "P29D"
    automatic {
      time_after_creation = "P90D"
    }
  }
  depends_on = [azurerm_role_assignment.fx_cis_03_c_x_kv_officer]
}

# ==== FX-CIS-03-N (CQ-CIS-03, nonconforming)

resource "azurerm_resource_group" "fx_cis_03_n_x_rg" {
  name     = "${var.run_id}-fx-cis-03-n-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cis_03_n_x_client" {
}

resource "azurerm_key_vault" "fx_cis_03_n_x_kv" {
  name                       = "${var.run_id}fxcis03nkv"
  resource_group_name        = azurerm_resource_group.fx_cis_03_n_x_rg.name
  location                   = azurerm_resource_group.fx_cis_03_n_x_rg.location
  tenant_id                  = data.azurerm_client_config.fx_cis_03_n_x_client.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  rbac_authorization_enabled = true
}

resource "azurerm_role_assignment" "fx_cis_03_n_x_kv_officer" {
  scope                = azurerm_key_vault.fx_cis_03_n_x_kv.id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = data.azurerm_client_config.fx_cis_03_n_x_client.object_id
}

resource "azurerm_key_vault_key" "fx_cis_03_n_k1" {
  name         = "${var.run_id}-fx-cis-03-n-k1"
  key_vault_id = azurerm_key_vault.fx_cis_03_n_x_kv.id
  key_type     = "RSA"
  key_size     = 2048
  key_opts     = ["encrypt", "decrypt"]
  depends_on   = [azurerm_role_assignment.fx_cis_03_n_x_kv_officer]
}

# ==== FX-CIS-03-I (CQ-CIS-03, incomplete)

variable "fx_cis_03_i_rotation" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-03-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cis_03_i_x_rg" {
  name     = "${var.run_id}-fx-cis-03-i-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cis_03_i_x_client" {
}

resource "azurerm_key_vault" "fx_cis_03_i_x_kv" {
  name                       = "${var.run_id}fxcis03ikv"
  resource_group_name        = azurerm_resource_group.fx_cis_03_i_x_rg.name
  location                   = azurerm_resource_group.fx_cis_03_i_x_rg.location
  tenant_id                  = data.azurerm_client_config.fx_cis_03_i_x_client.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  rbac_authorization_enabled = true
}

resource "azurerm_role_assignment" "fx_cis_03_i_x_kv_officer" {
  scope                = azurerm_key_vault.fx_cis_03_i_x_kv.id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = data.azurerm_client_config.fx_cis_03_i_x_client.object_id
}

resource "azurerm_key_vault_key" "fx_cis_03_i_k1" {
  name         = "${var.run_id}-fx-cis-03-i-k1"
  key_vault_id = azurerm_key_vault.fx_cis_03_i_x_kv.id
  key_type     = "RSA"
  key_size     = 2048
  key_opts     = ["encrypt", "decrypt"]
  dynamic "rotation_policy" {
    for_each = var.fx_cis_03_i_rotation ? [1] : []
    content {
      expire_after         = "P180D"
      notify_before_expiry = "P29D"
      automatic {
        time_after_creation = "P90D"
      }
    }
  }
  depends_on = [azurerm_role_assignment.fx_cis_03_i_x_kv_officer]
}

# ==== FX-CIS-04-C (CQ-CIS-04, conforming)

resource "azurerm_resource_group" "fx_cis_04_c_x_rg" {
  name     = "${var.run_id}-fx-cis-04-c-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_cis_04_c_rs1" {
  name                = "${var.run_id}-fx-cis-04-c-rs1"
  resource_group_name = azurerm_resource_group.fx_cis_04_c_x_rg.name
  location            = azurerm_resource_group.fx_cis_04_c_x_rg.location
}

resource "azurerm_network_security_rule" "fx_cis_04_c_r1" {
  name                        = "${var.run_id}-fx-cis-04-c-r1"
  resource_group_name         = azurerm_resource_group.fx_cis_04_c_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_cis_04_c_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "203.0.113.0/24"
  destination_address_prefix  = "*"
}

# ==== FX-CIS-04-N (CQ-CIS-04, nonconforming)

resource "azurerm_resource_group" "fx_cis_04_n_x_rg" {
  name     = "${var.run_id}-fx-cis-04-n-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_cis_04_n_rs1" {
  name                = "${var.run_id}-fx-cis-04-n-rs1"
  resource_group_name = azurerm_resource_group.fx_cis_04_n_x_rg.name
  location            = azurerm_resource_group.fx_cis_04_n_x_rg.location
}

resource "azurerm_network_security_rule" "fx_cis_04_n_r1" {
  name                        = "${var.run_id}-fx-cis-04-n-r1"
  resource_group_name         = azurerm_resource_group.fx_cis_04_n_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_cis_04_n_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

# ==== FX-CIS-04-I (CQ-CIS-04, incomplete)

variable "fx_cis_04_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-04-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cis_04_i_x_rg" {
  name     = "${var.run_id}-fx-cis-04-i-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_cis_04_i_rs1" {
  name                = "${var.run_id}-fx-cis-04-i-rs1"
  resource_group_name = azurerm_resource_group.fx_cis_04_i_x_rg.name
  location            = azurerm_resource_group.fx_cis_04_i_x_rg.location
}

resource "azurerm_network_security_rule" "fx_cis_04_i_r1" {
  name                        = "${var.run_id}-fx-cis-04-i-r1"
  resource_group_name         = azurerm_resource_group.fx_cis_04_i_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_cis_04_i_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = var.fx_cis_04_i_source_cidr
  destination_address_prefix  = "*"
}

# ==== FX-CIS-05-C (CQ-CIS-05, conforming)

resource "azurerm_resource_group" "fx_cis_05_c_x_rg" {
  name     = "${var.run_id}-fx-cis-05-c-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_cis_05_c_rs1" {
  name                = "${var.run_id}-fx-cis-05-c-rs1"
  resource_group_name = azurerm_resource_group.fx_cis_05_c_x_rg.name
  location            = azurerm_resource_group.fx_cis_05_c_x_rg.location
}

resource "azurerm_network_security_rule" "fx_cis_05_c_r1" {
  name                        = "${var.run_id}-fx-cis-05-c-r1"
  resource_group_name         = azurerm_resource_group.fx_cis_05_c_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_cis_05_c_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "3389"
  source_address_prefix       = "203.0.113.0/24"
  destination_address_prefix  = "*"
}

# ==== FX-CIS-05-N (CQ-CIS-05, nonconforming)

resource "azurerm_resource_group" "fx_cis_05_n_x_rg" {
  name     = "${var.run_id}-fx-cis-05-n-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_cis_05_n_rs1" {
  name                = "${var.run_id}-fx-cis-05-n-rs1"
  resource_group_name = azurerm_resource_group.fx_cis_05_n_x_rg.name
  location            = azurerm_resource_group.fx_cis_05_n_x_rg.location
}

resource "azurerm_network_security_rule" "fx_cis_05_n_r1" {
  name                        = "${var.run_id}-fx-cis-05-n-r1"
  resource_group_name         = azurerm_resource_group.fx_cis_05_n_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_cis_05_n_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "3389"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

# ==== FX-CIS-05-I (CQ-CIS-05, incomplete)

variable "fx_cis_05_i_source_cidr" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-05-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cis_05_i_x_rg" {
  name     = "${var.run_id}-fx-cis-05-i-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_cis_05_i_rs1" {
  name                = "${var.run_id}-fx-cis-05-i-rs1"
  resource_group_name = azurerm_resource_group.fx_cis_05_i_x_rg.name
  location            = azurerm_resource_group.fx_cis_05_i_x_rg.location
}

resource "azurerm_network_security_rule" "fx_cis_05_i_r1" {
  name                        = "${var.run_id}-fx-cis-05-i-r1"
  resource_group_name         = azurerm_resource_group.fx_cis_05_i_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_cis_05_i_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "3389"
  source_address_prefix       = var.fx_cis_05_i_source_cidr
  destination_address_prefix  = "*"
}

# ==== FX-CIS-06-C (CQ-CIS-06, conforming)

resource "azurerm_resource_group" "fx_cis_06_c_x_rg" {
  name     = "${var.run_id}-fx-cis-06-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cis_06_c_vn1" {
  name                = "${var.run_id}-fx-cis-06-c-vn1"
  resource_group_name = azurerm_resource_group.fx_cis_06_c_x_rg.name
  location            = azurerm_resource_group.fx_cis_06_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cis_06_c_sa" {
  name                 = "${var.run_id}-fx-cis-06-c-sa"
  resource_group_name  = azurerm_resource_group.fx_cis_06_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cis_06_c_vn1.name
  address_prefixes     = ["10.30.1.0/24"]
}

data "azurerm_network_watcher" "fx_cis_06_c_x_nw" {
  name                = "NetworkWatcher_${var.location_1}"
  resource_group_name = "NetworkWatcherRG"
}

resource "azurerm_storage_account" "fx_cis_06_c_x_logs" {
  name                     = "${var.run_id}fxcis06cxlog"
  resource_group_name      = azurerm_resource_group.fx_cis_06_c_x_rg.name
  location                 = azurerm_resource_group.fx_cis_06_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_network_watcher_flow_log" "fx_cis_06_c_d1" {
  name                 = "${var.run_id}-fx-cis-06-c-d1"
  network_watcher_name = data.azurerm_network_watcher.fx_cis_06_c_x_nw.name
  resource_group_name  = data.azurerm_network_watcher.fx_cis_06_c_x_nw.resource_group_name
  target_resource_id   = azurerm_subnet.fx_cis_06_c_sa.id
  storage_account_id   = azurerm_storage_account.fx_cis_06_c_x_logs.id
  enabled              = true
  version              = 2
  retention_policy {
    enabled = true
    days    = 1
  }
}

# ==== FX-CIS-06-N (CQ-CIS-06, nonconforming)

resource "azurerm_resource_group" "fx_cis_06_n_x_rg" {
  name     = "${var.run_id}-fx-cis-06-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cis_06_n_vn1" {
  name                = "${var.run_id}-fx-cis-06-n-vn1"
  resource_group_name = azurerm_resource_group.fx_cis_06_n_x_rg.name
  location            = azurerm_resource_group.fx_cis_06_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cis_06_n_sa" {
  name                 = "${var.run_id}-fx-cis-06-n-sa"
  resource_group_name  = azurerm_resource_group.fx_cis_06_n_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cis_06_n_vn1.name
  address_prefixes     = ["10.30.1.0/24"]
}

# ==== FX-CIS-06-I (CQ-CIS-06, incomplete)

variable "fx_cis_06_i_flow_log_enabled" {
  type        = bool
  description = "entrada simbólica da fixture FX-CIS-06-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cis_06_i_x_rg" {
  name     = "${var.run_id}-fx-cis-06-i-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cis_06_i_vn1" {
  name                = "${var.run_id}-fx-cis-06-i-vn1"
  resource_group_name = azurerm_resource_group.fx_cis_06_i_x_rg.name
  location            = azurerm_resource_group.fx_cis_06_i_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cis_06_i_sa" {
  name                 = "${var.run_id}-fx-cis-06-i-sa"
  resource_group_name  = azurerm_resource_group.fx_cis_06_i_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cis_06_i_vn1.name
  address_prefixes     = ["10.30.1.0/24"]
}

data "azurerm_network_watcher" "fx_cis_06_i_x_nw" {
  name                = "NetworkWatcher_${var.location_1}"
  resource_group_name = "NetworkWatcherRG"
}

resource "azurerm_storage_account" "fx_cis_06_i_x_logs" {
  name                     = "${var.run_id}fxcis06ixlog"
  resource_group_name      = azurerm_resource_group.fx_cis_06_i_x_rg.name
  location                 = azurerm_resource_group.fx_cis_06_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_network_watcher_flow_log" "fx_cis_06_i_d1" {
  name                 = "${var.run_id}-fx-cis-06-i-d1"
  network_watcher_name = data.azurerm_network_watcher.fx_cis_06_i_x_nw.name
  resource_group_name  = data.azurerm_network_watcher.fx_cis_06_i_x_nw.resource_group_name
  target_resource_id   = azurerm_subnet.fx_cis_06_i_sa.id
  storage_account_id   = azurerm_storage_account.fx_cis_06_i_x_logs.id
  enabled              = var.fx_cis_06_i_flow_log_enabled
  version              = 2
  retention_policy {
    enabled = true
    days    = 1
  }
}

# ==== FX-CIS-07-C (CQ-CIS-07, conforming)

resource "azurerm_resource_group" "fx_cis_07_c_s1" {
  name     = "${var.run_id}-fx-cis-07-c-s1"
  location = var.location_1
}

resource "azurerm_monitor_action_group" "fx_cis_07_c_t1" {
  name                = "${var.run_id}-fx-cis-07-c-t1"
  resource_group_name = azurerm_resource_group.fx_cis_07_c_s1.name
  short_name          = "bocqfix"
}

resource "azurerm_monitor_activity_log_alert" "fx_cis_07_c_al1" {
  name                = "${var.run_id}-fx-cis-07-c-al1"
  resource_group_name = azurerm_resource_group.fx_cis_07_c_s1.name
  location            = "global"
  scopes              = [azurerm_resource_group.fx_cis_07_c_s1.id]
  criteria {
    category       = "Administrative"
    operation_name = "Microsoft.Network/networkSecurityGroups/write"
  }
  action {
    action_group_id = azurerm_monitor_action_group.fx_cis_07_c_t1.id
  }
}

# ==== FX-CIS-07-N (CQ-CIS-07, nonconforming)

resource "azurerm_resource_group" "fx_cis_07_n_s1" {
  name     = "${var.run_id}-fx-cis-07-n-s1"
  location = var.location_1
}

resource "azurerm_monitor_action_group" "fx_cis_07_n_t1" {
  name                = "${var.run_id}-fx-cis-07-n-t1"
  resource_group_name = azurerm_resource_group.fx_cis_07_n_s1.name
  short_name          = "bocqfix"
}

resource "azurerm_monitor_activity_log_alert" "fx_cis_07_n_al1" {
  name                = "${var.run_id}-fx-cis-07-n-al1"
  resource_group_name = azurerm_resource_group.fx_cis_07_n_s1.name
  location            = "global"
  scopes              = [azurerm_resource_group.fx_cis_07_n_s1.id]
  criteria {
    category       = "Administrative"
    operation_name = "Microsoft.Network/routeTables/write"
  }
  action {
    action_group_id = azurerm_monitor_action_group.fx_cis_07_n_t1.id
  }
}

# ==== FX-CIS-07-I (CQ-CIS-07, incomplete)

variable "fx_cis_07_i_operation_name" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-07-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cis_07_i_s1" {
  name     = "${var.run_id}-fx-cis-07-i-s1"
  location = var.location_1
}

resource "azurerm_monitor_action_group" "fx_cis_07_i_t1" {
  name                = "${var.run_id}-fx-cis-07-i-t1"
  resource_group_name = azurerm_resource_group.fx_cis_07_i_s1.name
  short_name          = "bocqfix"
}

resource "azurerm_monitor_activity_log_alert" "fx_cis_07_i_al1" {
  name                = "${var.run_id}-fx-cis-07-i-al1"
  resource_group_name = azurerm_resource_group.fx_cis_07_i_s1.name
  location            = "global"
  scopes              = [azurerm_resource_group.fx_cis_07_i_s1.id]
  criteria {
    category       = "Administrative"
    operation_name = var.fx_cis_07_i_operation_name
  }
  action {
    action_group_id = azurerm_monitor_action_group.fx_cis_07_i_t1.id
  }
}

# ==== FX-CIS-08-C (CQ-CIS-08, conforming)

resource "azurerm_resource_group" "fx_cis_08_c_x_rg" {
  name     = "${var.run_id}-fx-cis-08-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cis_08_c_x_sa" {
  name                     = "${var.run_id}fxcis08cxsa"
  resource_group_name      = azurerm_resource_group.fx_cis_08_c_x_rg.name
  location                 = azurerm_resource_group.fx_cis_08_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_cis_08_c_c1" {
  name                  = "${var.run_id}-fx-cis-08-c-c1"
  storage_account_id    = azurerm_storage_account.fx_cis_08_c_x_sa.id
  container_access_type = "private"
}

# ==== FX-CIS-08-N (CQ-CIS-08, nonconforming)

resource "azurerm_resource_group" "fx_cis_08_n_x_rg" {
  name     = "${var.run_id}-fx-cis-08-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cis_08_n_x_sa" {
  name                            = "${var.run_id}fxcis08nxsa"
  resource_group_name             = azurerm_resource_group.fx_cis_08_n_x_rg.name
  location                        = azurerm_resource_group.fx_cis_08_n_x_rg.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = true
}

resource "azurerm_storage_container" "fx_cis_08_n_c1" {
  name                  = "${var.run_id}-fx-cis-08-n-c1"
  storage_account_id    = azurerm_storage_account.fx_cis_08_n_x_sa.id
  container_access_type = "blob"
}

# ==== FX-CIS-08-I (CQ-CIS-08, incomplete)

variable "fx_cis_08_i_access_type" {
  type        = string
  description = "entrada simbólica da fixture FX-CIS-08-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cis_08_i_x_rg" {
  name     = "${var.run_id}-fx-cis-08-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cis_08_i_x_sa" {
  name                            = "${var.run_id}fxcis08ixsa"
  resource_group_name             = azurerm_resource_group.fx_cis_08_i_x_rg.name
  location                        = azurerm_resource_group.fx_cis_08_i_x_rg.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = true
}

resource "azurerm_storage_container" "fx_cis_08_i_c1" {
  name                  = "${var.run_id}-fx-cis-08-i-c1"
  storage_account_id    = azurerm_storage_account.fx_cis_08_i_x_sa.id
  container_access_type = var.fx_cis_08_i_access_type
}

# ==== FX-IDL-01-C (CQ-IDL-01, conforming)

resource "azurerm_resource_group" "fx_idl_01_c_x_rg" {
  name     = "${var.run_id}-fx-idl-01-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_idl_01_c_x_sa" {
  name                     = "${var.run_id}fxidl01cxsa"
  resource_group_name      = azurerm_resource_group.fx_idl_01_c_x_rg.name
  location                 = azurerm_resource_group.fx_idl_01_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_01_c_c1" {
  name               = "${var.run_id}-fx-idl-01-c-data-a"
  storage_account_id = azurerm_storage_account.fx_idl_01_c_x_sa.id
  metadata = {
    bo_phase = "after"
  }
}

# ==== FX-IDL-01-N (CQ-IDL-01, nonconforming)

resource "azurerm_resource_group" "fx_idl_01_n_x_rg" {
  name     = "${var.run_id}-fx-idl-01-n-x-rg"
  location = var.location_2
}

resource "azurerm_storage_account" "fx_idl_01_n_x_sa" {
  name                     = "${var.run_id}fxidl01nxsa"
  resource_group_name      = azurerm_resource_group.fx_idl_01_n_x_rg.name
  location                 = var.location_2
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_01_n_c2" {
  name               = "${var.run_id}-fx-idl-01-n-data-a"
  storage_account_id = azurerm_storage_account.fx_idl_01_n_x_sa.id
}

# ==== FX-IDL-01-I (CQ-IDL-01, incomplete)

resource "azurerm_resource_group" "fx_idl_01_i_x_rg" {
  name     = "${var.run_id}-fx-idl-01-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_idl_01_i_x_sa" {
  name                     = "${var.run_id}fxidl01ixsa"
  resource_group_name      = azurerm_resource_group.fx_idl_01_i_x_rg.name
  location                 = azurerm_resource_group.fx_idl_01_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  access_tier              = "Cool"
}

resource "azurerm_storage_container" "fx_idl_01_i_c1" {
  name               = "${var.run_id}-fx-idl-01-i-data-a"
  storage_account_id = azurerm_storage_account.fx_idl_01_i_x_sa.id
}

# ==== FX-IDL-02-C (CQ-IDL-02, conforming)

resource "azurerm_resource_group" "fx_idl_02_c_x_rg" {
  name     = "${var.run_id}-fx-idl-02-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_idl_02_c_x_sa1" {
  name                     = "${var.run_id}fxidl02cxsa1"
  resource_group_name      = azurerm_resource_group.fx_idl_02_c_x_rg.name
  location                 = var.location_1
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_02_c_c1" {
  name               = "data"
  storage_account_id = azurerm_storage_account.fx_idl_02_c_x_sa1.id
}

resource "azurerm_storage_account" "fx_idl_02_c_x_sa2" {
  name                     = "${var.run_id}fxidl02cxsa2"
  resource_group_name      = azurerm_resource_group.fx_idl_02_c_x_rg.name
  location                 = var.location_2
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_02_c_c2" {
  name               = "data"
  storage_account_id = azurerm_storage_account.fx_idl_02_c_x_sa2.id
}

# ==== FX-IDL-02-N (CQ-IDL-02, nonconforming)

resource "azurerm_resource_group" "fx_idl_02_n_x_rg" {
  name     = "${var.run_id}-fx-idl-02-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_idl_02_n_x_sa1" {
  name                     = "${var.run_id}fxidl02nxsa1"
  resource_group_name      = azurerm_resource_group.fx_idl_02_n_x_rg.name
  location                 = var.location_1
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_02_n_c1" {
  name               = "data"
  storage_account_id = azurerm_storage_account.fx_idl_02_n_x_sa1.id
}

data "azurerm_storage_container" "fx_idl_02_n_c2" {
  name               = "data"
  storage_account_id = azurerm_storage_account.fx_idl_02_n_x_sa1.id
}

# ==== FX-IDL-02-I (CQ-IDL-02, incomplete)

variable "fx_idl_02_i_storage_account_id" {
  type        = string
  description = "entrada simbólica da fixture FX-IDL-02-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_idl_02_i_x_rg" {
  name     = "${var.run_id}-fx-idl-02-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_idl_02_i_x_sa1" {
  name                     = "${var.run_id}fxidl02ixsa1"
  resource_group_name      = azurerm_resource_group.fx_idl_02_i_x_rg.name
  location                 = var.location_1
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_02_i_c1" {
  name               = "data"
  storage_account_id = azurerm_storage_account.fx_idl_02_i_x_sa1.id
}

data "azurerm_storage_container" "fx_idl_02_i_c2" {
  name               = "data"
  storage_account_id = var.fx_idl_02_i_storage_account_id
}

# ==== FX-IDL-03-C (CQ-IDL-03, conforming)

resource "azurerm_resource_group" "fx_idl_03_c_s1" {
  name     = "${var.run_id}-fx-idl-03-c-s1"
  location = var.location_1
}

resource "azurerm_user_assigned_identity" "fx_idl_03_c_p1" {
  name                = "${var.run_id}-fx-idl-03-c-p1"
  resource_group_name = azurerm_resource_group.fx_idl_03_c_s1.name
  location            = azurerm_resource_group.fx_idl_03_c_s1.location
}

resource "azurerm_role_definition" "fx_idl_03_c_ps1" {
  name  = "${var.run_id}-fx-idl-03-c-ps1"
  scope = azurerm_resource_group.fx_idl_03_c_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_idl_03_c_a1" {
  scope              = azurerm_resource_group.fx_idl_03_c_s1.id
  role_definition_id = azurerm_role_definition.fx_idl_03_c_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_idl_03_c_p1.principal_id
}

# ==== FX-IDL-03-N (CQ-IDL-03, nonconforming)

resource "azurerm_resource_group" "fx_idl_03_n_x_rg" {
  name     = "${var.run_id}-fx-idl-03-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_idl_03_n_ns1" {
  name                     = "${var.run_id}fxidl03nns1"
  resource_group_name      = azurerm_resource_group.fx_idl_03_n_x_rg.name
  location                 = azurerm_resource_group.fx_idl_03_n_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_03_n_c1" {
  name               = "${var.run_id}-fx-idl-03-n-c1"
  storage_account_id = azurerm_storage_account.fx_idl_03_n_ns1.id
}

# ==== FX-IDL-03-I (CQ-IDL-03, incomplete)

resource "azurerm_resource_group" "fx_idl_03_i_x_rg" {
  name     = "${var.run_id}-fx-idl-03-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_idl_03_i_x_sa" {
  name                     = "${var.run_id}fxidl03ixsa"
  resource_group_name      = azurerm_resource_group.fx_idl_03_i_x_rg.name
  location                 = azurerm_resource_group.fx_idl_03_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_idl_03_i_c1" {
  name               = "${var.run_id}-fx-idl-03-i-c1"
  storage_account_id = azurerm_storage_account.fx_idl_03_i_x_sa.id
}

resource "azurerm_storage_container_immutability_policy" "fx_idl_03_i_s1" {
  storage_container_resource_manager_id = azurerm_storage_container.fx_idl_03_i_c1.id
  immutability_period_in_days           = 1
  locked                                = false
}

# ==== FX-IDL-04-C (CQ-IDL-04, conforming)

resource "azurerm_resource_group" "fx_idl_04_c_x_rg" {
  name     = "${var.run_id}-fx-idl-04-c-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_idl_04_c_rs1" {
  name                = "${var.run_id}-fx-idl-04-c-rs1"
  resource_group_name = azurerm_resource_group.fx_idl_04_c_x_rg.name
  location            = azurerm_resource_group.fx_idl_04_c_x_rg.location
  security_rule {
    name                       = "r2-ssh"
    priority                   = 210
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "203.0.113.0/24"
    destination_address_prefix = "*"
  }
  security_rule {
    name                       = "r1-https"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "203.0.113.0/24"
    destination_address_prefix = "*"
  }
}

# ==== FX-IDL-04-N (CQ-IDL-04, nonconforming): NOT_APPLICABLE — no NSG cada regra tem nome obrigatório (chave local) e é ele que identifica a ocorrência; mudar a porta de uma regra com o mesmo nome é atualização da mesma regra, não outra ocorrência anônima

# ==== FX-IDL-04-I (CQ-IDL-04, incomplete)

variable "fx_idl_04_i_r1_name" {
  type        = string
  description = "entrada simbólica da fixture FX-IDL-04-I; sem valor de propósito"
}

variable "fx_idl_04_i_r1_port" {
  type        = string
  description = "entrada simbólica da fixture FX-IDL-04-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_idl_04_i_x_rg" {
  name     = "${var.run_id}-fx-idl-04-i-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_idl_04_i_rs1" {
  name                = "${var.run_id}-fx-idl-04-i-rs1"
  resource_group_name = azurerm_resource_group.fx_idl_04_i_x_rg.name
  location            = azurerm_resource_group.fx_idl_04_i_x_rg.location
  security_rule {
    name                       = "r2-ssh"
    priority                   = 210
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "203.0.113.0/24"
    destination_address_prefix = "*"
  }
  security_rule {
    name                       = var.fx_idl_04_i_r1_name
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = var.fx_idl_04_i_r1_port
    source_address_prefix      = "203.0.113.0/24"
    destination_address_prefix = "*"
  }
}

# ==== FX-CMP-01-C (CQ-CMP-01, conforming)

resource "azurerm_resource_group" "fx_cmp_01_c_x_rg" {
  name     = "${var.run_id}-fx-cmp-01-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_01_c_vn1" {
  name                = "${var.run_id}-fx-cmp-01-c-vn1"
  resource_group_name = azurerm_resource_group.fx_cmp_01_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_01_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cmp_01_c_sa" {
  name                 = "${var.run_id}-fx-cmp-01-c-sa"
  resource_group_name  = azurerm_resource_group.fx_cmp_01_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cmp_01_c_vn1.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_cmp_01_c_nic1" {
  name                = "${var.run_id}-fx-cmp-01-c-nic1"
  resource_group_name = azurerm_resource_group.fx_cmp_01_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_01_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_cmp_01_c_sa.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_cmp_01_c_vm1" {
  name                  = "${var.run_id}-fx-cmp-01-c-vm1"
  resource_group_name   = azurerm_resource_group.fx_cmp_01_c_x_rg.name
  location              = azurerm_resource_group.fx_cmp_01_c_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_cmp_01_c_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-CMP-01-N (CQ-CMP-01, nonconforming)

resource "azurerm_resource_group" "fx_cmp_01_n_x_rg" {
  name     = "${var.run_id}-fx-cmp-01-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_01_n_vn1" {
  name                = "${var.run_id}-fx-cmp-01-n-vn1"
  resource_group_name = azurerm_resource_group.fx_cmp_01_n_x_rg.name
  location            = azurerm_resource_group.fx_cmp_01_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_network_interface" "fx_cmp_01_n_nic1" {
  name                = "${var.run_id}-fx-cmp-01-n-nic1"
  resource_group_name = azurerm_resource_group.fx_cmp_01_n_x_rg.name
  location            = azurerm_resource_group.fx_cmp_01_n_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = "/subscriptions/sub-sintetica/resourceGroups/rg-ausente/providers/Microsoft.Network/virtualNetworks/vn-ausente/subnets/sub-ausente"
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_cmp_01_n_vm1" {
  name                  = "${var.run_id}-fx-cmp-01-n-vm1"
  resource_group_name   = azurerm_resource_group.fx_cmp_01_n_x_rg.name
  location              = azurerm_resource_group.fx_cmp_01_n_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_cmp_01_n_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-CMP-01-I (CQ-CMP-01, incomplete)

variable "fx_cmp_01_i_subnet_id" {
  type        = string
  description = "entrada simbólica da fixture FX-CMP-01-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cmp_01_i_x_rg" {
  name     = "${var.run_id}-fx-cmp-01-i-x-rg"
  location = var.location_1
}

resource "azurerm_network_interface" "fx_cmp_01_i_nic1" {
  name                = "${var.run_id}-fx-cmp-01-i-nic1"
  resource_group_name = azurerm_resource_group.fx_cmp_01_i_x_rg.name
  location            = azurerm_resource_group.fx_cmp_01_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = var.fx_cmp_01_i_subnet_id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_cmp_01_i_vm1" {
  name                  = "${var.run_id}-fx-cmp-01-i-vm1"
  resource_group_name   = azurerm_resource_group.fx_cmp_01_i_x_rg.name
  location              = azurerm_resource_group.fx_cmp_01_i_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_cmp_01_i_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-CMP-02-C (CQ-CMP-02, conforming)

resource "azurerm_resource_group" "fx_cmp_02_c_x_rg" {
  name     = "${var.run_id}-fx-cmp-02-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_02_c_x_vnet" {
  name                = "${var.run_id}-fx-cmp-02-c-x-vnet"
  resource_group_name = azurerm_resource_group.fx_cmp_02_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cmp_02_c_x_subnet" {
  name                 = "${var.run_id}-fx-cmp-02-c-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_cmp_02_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cmp_02_c_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_cmp_02_c_nic1" {
  name                = "${var.run_id}-fx-cmp-02-c-nic1"
  resource_group_name = azurerm_resource_group.fx_cmp_02_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_cmp_02_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "fx_cmp_02_c_nic2" {
  name                = "${var.run_id}-fx-cmp-02-c-nic2"
  resource_group_name = azurerm_resource_group.fx_cmp_02_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_cmp_02_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_cmp_02_c_vm1" {
  name                = "${var.run_id}-fx-cmp-02-c-vm1"
  resource_group_name = azurerm_resource_group.fx_cmp_02_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_c_x_rg.location
  size                = "Standard_B1ls"
  admin_username      = "boadmin"
  network_interface_ids = [
    azurerm_network_interface.fx_cmp_02_c_nic1.id,
    azurerm_network_interface.fx_cmp_02_c_nic2.id,
  ]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-CMP-02-N (CQ-CMP-02, nonconforming)

resource "azurerm_resource_group" "fx_cmp_02_n_x_rg" {
  name     = "${var.run_id}-fx-cmp-02-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_02_n_x_vnet" {
  name                = "${var.run_id}-fx-cmp-02-n-x-vnet"
  resource_group_name = azurerm_resource_group.fx_cmp_02_n_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cmp_02_n_x_subnet" {
  name                 = "${var.run_id}-fx-cmp-02-n-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_cmp_02_n_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cmp_02_n_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_cmp_02_n_nic1" {
  name                = "${var.run_id}-fx-cmp-02-n-nic1"
  resource_group_name = azurerm_resource_group.fx_cmp_02_n_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_n_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_cmp_02_n_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_cmp_02_n_vm1" {
  name                  = "${var.run_id}-fx-cmp-02-n-vm1"
  resource_group_name   = azurerm_resource_group.fx_cmp_02_n_x_rg.name
  location              = azurerm_resource_group.fx_cmp_02_n_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_cmp_02_n_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-CMP-02-I (CQ-CMP-02, incomplete)

variable "fx_cmp_02_i_extra_nic_ids" {
  type        = list(string)
  description = "entrada simbólica da fixture FX-CMP-02-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cmp_02_i_x_rg" {
  name     = "${var.run_id}-fx-cmp-02-i-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_02_i_x_vnet" {
  name                = "${var.run_id}-fx-cmp-02-i-x-vnet"
  resource_group_name = azurerm_resource_group.fx_cmp_02_i_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_i_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cmp_02_i_x_subnet" {
  name                 = "${var.run_id}-fx-cmp-02-i-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_cmp_02_i_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cmp_02_i_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_cmp_02_i_nic1" {
  name                = "${var.run_id}-fx-cmp-02-i-nic1"
  resource_group_name = azurerm_resource_group.fx_cmp_02_i_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_cmp_02_i_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "fx_cmp_02_i_nic2" {
  name                = "${var.run_id}-fx-cmp-02-i-nic2"
  resource_group_name = azurerm_resource_group.fx_cmp_02_i_x_rg.name
  location            = azurerm_resource_group.fx_cmp_02_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_cmp_02_i_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_cmp_02_i_vm1" {
  name                  = "${var.run_id}-fx-cmp-02-i-vm1"
  resource_group_name   = azurerm_resource_group.fx_cmp_02_i_x_rg.name
  location              = azurerm_resource_group.fx_cmp_02_i_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = concat([azurerm_network_interface.fx_cmp_02_i_nic1.id], var.fx_cmp_02_i_extra_nic_ids)
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-CMP-03-C (CQ-CMP-03, conforming)

resource "azurerm_resource_group" "fx_cmp_03_c_x_rg" {
  name     = "${var.run_id}-fx-cmp-03-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_03_c_x_vnet" {
  name                = "${var.run_id}-fx-cmp-03-c-x-vnet"
  resource_group_name = azurerm_resource_group.fx_cmp_03_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_03_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cmp_03_c_x_subnet" {
  name                 = "${var.run_id}-fx-cmp-03-c-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_cmp_03_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cmp_03_c_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_lb" "fx_cmp_03_c_lb1" {
  name                = "${var.run_id}-fx-cmp-03-c-lb1"
  resource_group_name = azurerm_resource_group.fx_cmp_03_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_03_c_x_rg.location
  sku                 = "Standard"
  frontend_ip_configuration {
    name                          = "fe1"
    subnet_id                     = azurerm_subnet.fx_cmp_03_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_lb_backend_address_pool" "fx_cmp_03_c_pool1" {
  name            = "${var.run_id}-fx-cmp-03-c-pool1"
  loadbalancer_id = azurerm_lb.fx_cmp_03_c_lb1.id
}

resource "azurerm_lb_probe" "fx_cmp_03_c_hp1" {
  name            = "${var.run_id}-fx-cmp-03-c-hp1"
  loadbalancer_id = azurerm_lb.fx_cmp_03_c_lb1.id
  port            = 443
  protocol        = "Tcp"
}

resource "azurerm_lb_rule" "fx_cmp_03_c_ru1" {
  name                           = "${var.run_id}-fx-cmp-03-c-ru1"
  loadbalancer_id                = azurerm_lb.fx_cmp_03_c_lb1.id
  protocol                       = "Tcp"
  frontend_port                  = 443
  backend_port                   = 443
  frontend_ip_configuration_name = "fe1"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.fx_cmp_03_c_pool1.id]
  probe_id                       = azurerm_lb_probe.fx_cmp_03_c_hp1.id
}

resource "azurerm_network_interface" "fx_cmp_03_c_x_nic" {
  name                = "${var.run_id}-fx-cmp-03-c-x-nic"
  resource_group_name = azurerm_resource_group.fx_cmp_03_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_03_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_cmp_03_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_cmp_03_c_vm1" {
  name                  = "${var.run_id}-fx-cmp-03-c-vm1"
  resource_group_name   = azurerm_resource_group.fx_cmp_03_c_x_rg.name
  location              = azurerm_resource_group.fx_cmp_03_c_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_cmp_03_c_x_nic.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_network_interface_backend_address_pool_association" "fx_cmp_03_c_x_member" {
  network_interface_id    = azurerm_network_interface.fx_cmp_03_c_x_nic.id
  ip_configuration_name   = "primary"
  backend_address_pool_id = azurerm_lb_backend_address_pool.fx_cmp_03_c_pool1.id
}

# ==== FX-CMP-03-N (CQ-CMP-03, nonconforming)

resource "azurerm_resource_group" "fx_cmp_03_n_x_rg" {
  name     = "${var.run_id}-fx-cmp-03-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_03_n_x_vnet" {
  name                = "${var.run_id}-fx-cmp-03-n-x-vnet"
  resource_group_name = azurerm_resource_group.fx_cmp_03_n_x_rg.name
  location            = azurerm_resource_group.fx_cmp_03_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cmp_03_n_x_subnet" {
  name                 = "${var.run_id}-fx-cmp-03-n-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_cmp_03_n_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cmp_03_n_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_lb" "fx_cmp_03_n_lb1" {
  name                = "${var.run_id}-fx-cmp-03-n-lb1"
  resource_group_name = azurerm_resource_group.fx_cmp_03_n_x_rg.name
  location            = azurerm_resource_group.fx_cmp_03_n_x_rg.location
  sku                 = "Standard"
  frontend_ip_configuration {
    name                          = "fe1"
    subnet_id                     = azurerm_subnet.fx_cmp_03_n_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_lb_backend_address_pool" "fx_cmp_03_n_pool1" {
  name            = "${var.run_id}-fx-cmp-03-n-pool1"
  loadbalancer_id = azurerm_lb.fx_cmp_03_n_lb1.id
}

resource "azurerm_lb_probe" "fx_cmp_03_n_hp1" {
  name            = "${var.run_id}-fx-cmp-03-n-hp1"
  loadbalancer_id = azurerm_lb.fx_cmp_03_n_lb1.id
  port            = 443
  protocol        = "Tcp"
}

resource "azurerm_lb_rule" "fx_cmp_03_n_ru1" {
  name                           = "${var.run_id}-fx-cmp-03-n-ru1"
  loadbalancer_id                = azurerm_lb.fx_cmp_03_n_lb1.id
  protocol                       = "Tcp"
  frontend_port                  = 443
  backend_port                   = 443
  frontend_ip_configuration_name = "fe1"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.fx_cmp_03_n_pool1.id]
  probe_id                       = azurerm_lb_probe.fx_cmp_03_n_hp1.id
}

# ==== FX-CMP-03-I (CQ-CMP-03, incomplete)

resource "azurerm_resource_group" "fx_cmp_03_i_x_rg" {
  name     = "${var.run_id}-fx-cmp-03-i-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_cmp_03_i_x_vnet" {
  name                = "${var.run_id}-fx-cmp-03-i-x-vnet"
  resource_group_name = azurerm_resource_group.fx_cmp_03_i_x_rg.name
  location            = azurerm_resource_group.fx_cmp_03_i_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_cmp_03_i_x_subnet" {
  name                 = "${var.run_id}-fx-cmp-03-i-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_cmp_03_i_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_cmp_03_i_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_lb" "fx_cmp_03_i_lb1" {
  name                = "${var.run_id}-fx-cmp-03-i-lb1"
  resource_group_name = azurerm_resource_group.fx_cmp_03_i_x_rg.name
  location            = azurerm_resource_group.fx_cmp_03_i_x_rg.location
  sku                 = "Standard"
  frontend_ip_configuration {
    name                          = "fe1"
    subnet_id                     = azurerm_subnet.fx_cmp_03_i_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_lb_backend_address_pool" "fx_cmp_03_i_pool1" {
  name            = "${var.run_id}-fx-cmp-03-i-pool1"
  loadbalancer_id = azurerm_lb.fx_cmp_03_i_lb1.id
}

resource "azurerm_lb_probe" "fx_cmp_03_i_hp1" {
  name            = "${var.run_id}-fx-cmp-03-i-hp1"
  loadbalancer_id = azurerm_lb.fx_cmp_03_i_lb1.id
  port            = 443
  protocol        = "Tcp"
}

resource "azurerm_lb_rule" "fx_cmp_03_i_ru1" {
  name                           = "${var.run_id}-fx-cmp-03-i-ru1"
  loadbalancer_id                = azurerm_lb.fx_cmp_03_i_lb1.id
  protocol                       = "Tcp"
  frontend_port                  = 443
  backend_port                   = 443
  frontend_ip_configuration_name = "fe1"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.fx_cmp_03_i_pool1.id]
  probe_id                       = azurerm_lb_probe.fx_cmp_03_i_hp1.id
}

# ==== FX-CMP-04-C (CQ-CMP-04, conforming)

resource "azurerm_resource_group" "fx_cmp_04_c_x_rg" {
  name     = "${var.run_id}-fx-cmp-04-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cmp_04_c_ns1" {
  name                     = "${var.run_id}fxcmp04cns1"
  resource_group_name      = azurerm_resource_group.fx_cmp_04_c_x_rg.name
  location                 = azurerm_resource_group.fx_cmp_04_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

resource "azurerm_storage_container" "fx_cmp_04_c_c1" {
  name               = "${var.run_id}-fx-cmp-04-c-c1"
  storage_account_id = azurerm_storage_account.fx_cmp_04_c_ns1.id
}

# ==== FX-CMP-04-N (CQ-CMP-04, nonconforming)

resource "azurerm_resource_group" "fx_cmp_04_n_x_rg" {
  name     = "${var.run_id}-fx-cmp-04-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cmp_04_n_ns1" {
  name                     = "${var.run_id}fxcmp04nns1"
  resource_group_name      = azurerm_resource_group.fx_cmp_04_n_x_rg.name
  location                 = azurerm_resource_group.fx_cmp_04_n_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_cmp_04_n_c1" {
  name               = "${var.run_id}-fx-cmp-04-n-c1"
  storage_account_id = azurerm_storage_account.fx_cmp_04_n_ns1.id
}

resource "azurerm_storage_container" "fx_cmp_04_n_c2" {
  name               = "${var.run_id}-fx-cmp-04-n-c2"
  storage_account_id = azurerm_storage_account.fx_cmp_04_n_ns1.id
}

resource "azurerm_storage_container_immutability_policy" "fx_cmp_04_n_k1" {
  storage_container_resource_manager_id = azurerm_storage_container.fx_cmp_04_n_c2.id
  immutability_period_in_days           = 1
  locked                                = false
}

# ==== FX-CMP-04-I (CQ-CMP-04, incomplete)

variable "fx_cmp_04_i_storage_account_id" {
  type        = string
  description = "entrada simbólica da fixture FX-CMP-04-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cmp_04_i_x_rg" {
  name     = "${var.run_id}-fx-cmp-04-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cmp_04_i_ns1" {
  name                     = "${var.run_id}fxcmp04ins1"
  resource_group_name      = azurerm_resource_group.fx_cmp_04_i_x_rg.name
  location                 = azurerm_resource_group.fx_cmp_04_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

data "azurerm_storage_container" "fx_cmp_04_i_c1" {
  name               = "data"
  storage_account_id = var.fx_cmp_04_i_storage_account_id
}

# ==== FX-CMP-05-C (CQ-CMP-05, conforming)

resource "azurerm_resource_group" "fx_cmp_05_c_x_rg" {
  name     = "${var.run_id}-fx-cmp-05-c-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cmp_05_c_x_client" {
}

resource "azurerm_postgresql_flexible_server" "fx_cmp_05_c_i1" {
  name                = "${var.run_id}-fx-cmp-05-c-i1"
  resource_group_name = azurerm_resource_group.fx_cmp_05_c_x_rg.name
  location            = azurerm_resource_group.fx_cmp_05_c_x_rg.location
  version             = "16"
  sku_name            = "B_Standard_B1ms"
  storage_mb          = 32768
  zone                = "1"
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.fx_cmp_05_c_x_client.tenant_id
  }
}

resource "azurerm_postgresql_flexible_server_database" "fx_cmp_05_c_db1" {
  name      = "bodb"
  server_id = azurerm_postgresql_flexible_server.fx_cmp_05_c_i1.id
}

# ==== FX-CMP-05-N (CQ-CMP-05, nonconforming)

resource "azurerm_resource_group" "fx_cmp_05_n_x_rg" {
  name     = "${var.run_id}-fx-cmp-05-n-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cmp_05_n_x_client" {
}

resource "azurerm_mssql_server" "fx_cmp_05_n_srv1" {
  name                = "${var.run_id}-fx-cmp-05-n-srv1"
  resource_group_name = azurerm_resource_group.fx_cmp_05_n_x_rg.name
  location            = azurerm_resource_group.fx_cmp_05_n_x_rg.location
  version             = "12.0"
  azuread_administrator {
    login_username              = "bo-admin"
    object_id                   = data.azurerm_client_config.fx_cmp_05_n_x_client.object_id
    azuread_authentication_only = true
  }
}

resource "azurerm_mssql_database" "fx_cmp_05_n_db1" {
  name      = "${var.run_id}-fx-cmp-05-n-db1"
  server_id = azurerm_mssql_server.fx_cmp_05_n_srv1.id
  sku_name  = "Basic"
}

# ==== FX-CMP-05-I (CQ-CMP-05, incomplete)

resource "azurerm_resource_group" "fx_cmp_05_i_x_rg" {
  name     = "${var.run_id}-fx-cmp-05-i-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cmp_05_i_x_client" {
}

resource "azurerm_mssql_server" "fx_cmp_05_i_srv2" {
  name                = "${var.run_id}-fx-cmp-05-i-srv2"
  resource_group_name = azurerm_resource_group.fx_cmp_05_i_x_rg.name
  location            = azurerm_resource_group.fx_cmp_05_i_x_rg.location
  version             = "12.0"
  azuread_administrator {
    login_username              = "bo-admin"
    object_id                   = data.azurerm_client_config.fx_cmp_05_i_x_client.object_id
    azuread_authentication_only = true
  }
}

resource "azurerm_mssql_database" "fx_cmp_05_i_db1" {
  name      = "${var.run_id}-fx-cmp-05-i-db1"
  server_id = azurerm_mssql_server.fx_cmp_05_i_srv2.id
  sku_name  = "Basic"
}

# ==== FX-AUT-01-C (CQ-AUT-01, conforming)

resource "azurerm_resource_group" "fx_aut_01_c_s_parent" {
  name     = "${var.run_id}-fx-aut-01-c-s-parent"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_aut_01_c_s_child" {
  name                     = "${var.run_id}fxaut01cschi"
  resource_group_name      = azurerm_resource_group.fx_aut_01_c_s_parent.name
  location                 = azurerm_resource_group.fx_aut_01_c_s_parent.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_01_c_r1" {
  name               = "${var.run_id}-fx-aut-01-c-r1"
  storage_account_id = azurerm_storage_account.fx_aut_01_c_s_child.id
}

resource "azurerm_user_assigned_identity" "fx_aut_01_c_p1" {
  name                = "${var.run_id}-fx-aut-01-c-p1"
  resource_group_name = azurerm_resource_group.fx_aut_01_c_s_parent.name
  location            = azurerm_resource_group.fx_aut_01_c_s_parent.location
}

resource "azurerm_role_definition" "fx_aut_01_c_ps1" {
  name  = "${var.run_id}-fx-aut-01-c-ps1"
  scope = azurerm_resource_group.fx_aut_01_c_s_parent.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_01_c_a1" {
  scope              = azurerm_resource_group.fx_aut_01_c_s_parent.id
  role_definition_id = azurerm_role_definition.fx_aut_01_c_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_01_c_p1.principal_id
}

# ==== FX-AUT-01-N (CQ-AUT-01, nonconforming): NOT_APPLICABLE — negação explícita aplicável no escopo filho não é criável: o azurerm não tem atribuição de negação

# ==== FX-AUT-01-I (CQ-AUT-01, incomplete)

variable "fx_aut_01_i_parent_rg_name" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-01-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_aut_01_i_x_rg" {
  name     = "${var.run_id}-fx-aut-01-i-x-rg"
  location = var.location_1
}

resource "azurerm_user_assigned_identity" "fx_aut_01_i_p1" {
  name                = "${var.run_id}-fx-aut-01-i-p1"
  resource_group_name = azurerm_resource_group.fx_aut_01_i_x_rg.name
  location            = azurerm_resource_group.fx_aut_01_i_x_rg.location
}

resource "azurerm_storage_account" "fx_aut_01_i_s_child" {
  name                     = "${var.run_id}fxaut01ischi"
  resource_group_name      = var.fx_aut_01_i_parent_rg_name
  location                 = var.location_1
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_01_i_r1" {
  name               = "${var.run_id}-fx-aut-01-i-r1"
  storage_account_id = azurerm_storage_account.fx_aut_01_i_s_child.id
}

# ==== FX-AUT-02-C (CQ-AUT-02, conforming)

resource "azurerm_resource_group" "fx_aut_02_c_s1" {
  name     = "${var.run_id}-fx-aut-02-c-s1"
  location = var.location_1
}

resource "azurerm_user_assigned_identity" "fx_aut_02_c_p1" {
  name                = "${var.run_id}-fx-aut-02-c-p1"
  resource_group_name = azurerm_resource_group.fx_aut_02_c_s1.name
  location            = azurerm_resource_group.fx_aut_02_c_s1.location
}

resource "azurerm_role_definition" "fx_aut_02_c_ps1" {
  name  = "${var.run_id}-fx-aut-02-c-ps1"
  scope = azurerm_resource_group.fx_aut_02_c_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_02_c_a1" {
  scope              = azurerm_resource_group.fx_aut_02_c_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_02_c_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_02_c_p1.principal_id
}

resource "azurerm_resource_group_template_deployment" "fx_aut_02_c_doc1" {
  name                = "${var.run_id}-fx-aut-02-c-doc1"
  resource_group_name = azurerm_resource_group.fx_aut_02_c_s1.name
  deployment_mode     = "Incremental"
  template_content = jsonencode({
    "$schema"      = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
    contentVersion = "1.0.0.0"
    parameters = {
      principalId = {
        type = "string"
      }
      roleDefinitionId = {
        type = "string"
      }
    }
    resources = [
      {
        type       = "Microsoft.Authorization/roleAssignments"
        apiVersion = "2022-04-01"
        name       = "[guid(resourceGroup().id, parameters('principalId'), 'a2')]"
        properties = {
          principalId      = "[parameters('principalId')]"
          roleDefinitionId = "[parameters('roleDefinitionId')]"
        }
      },
    ]
  })
  parameters_content = jsonencode({
    principalId = {
      value = azurerm_user_assigned_identity.fx_aut_02_c_p1.principal_id
    }
    roleDefinitionId = {
      value = azurerm_role_definition.fx_aut_02_c_ps1.role_definition_resource_id
    }
  })
}

# ==== FX-AUT-02-N (CQ-AUT-02, nonconforming)

resource "azurerm_resource_group" "fx_aut_02_n_s1" {
  name     = "${var.run_id}-fx-aut-02-n-s1"
  location = var.location_1
}

resource "azurerm_user_assigned_identity" "fx_aut_02_n_p1" {
  name                = "${var.run_id}-fx-aut-02-n-p1"
  resource_group_name = azurerm_resource_group.fx_aut_02_n_s1.name
  location            = azurerm_resource_group.fx_aut_02_n_s1.location
}

resource "azurerm_role_definition" "fx_aut_02_n_ps1" {
  name  = "${var.run_id}-fx-aut-02-n-ps1"
  scope = azurerm_resource_group.fx_aut_02_n_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_02_n_a1" {
  scope              = azurerm_resource_group.fx_aut_02_n_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_02_n_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_02_n_p1.principal_id
}

resource "azurerm_role_definition" "fx_aut_02_n_ps2" {
  name  = "${var.run_id}-fx-aut-02-n-ps2"
  scope = azurerm_resource_group.fx_aut_02_n_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write"]
  }
}

resource "azurerm_role_assignment" "fx_aut_02_n_a2" {
  scope              = azurerm_resource_group.fx_aut_02_n_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_02_n_ps2.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_02_n_p1.principal_id
}

# ==== FX-AUT-02-I (CQ-AUT-02, incomplete)

variable "fx_aut_02_i_principal_id" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-02-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_aut_02_i_s1" {
  name     = "${var.run_id}-fx-aut-02-i-s1"
  location = var.location_1
}

resource "azurerm_user_assigned_identity" "fx_aut_02_i_p1" {
  name                = "${var.run_id}-fx-aut-02-i-p1"
  resource_group_name = azurerm_resource_group.fx_aut_02_i_s1.name
  location            = azurerm_resource_group.fx_aut_02_i_s1.location
}

resource "azurerm_role_definition" "fx_aut_02_i_ps1" {
  name  = "${var.run_id}-fx-aut-02-i-ps1"
  scope = azurerm_resource_group.fx_aut_02_i_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_02_i_a1" {
  scope              = azurerm_resource_group.fx_aut_02_i_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_02_i_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_02_i_p1.principal_id
}

resource "azurerm_resource_group_template_deployment" "fx_aut_02_i_doc1" {
  name                = "${var.run_id}-fx-aut-02-i-doc1"
  resource_group_name = azurerm_resource_group.fx_aut_02_i_s1.name
  deployment_mode     = "Incremental"
  template_content = jsonencode({
    "$schema"      = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
    contentVersion = "1.0.0.0"
    parameters = {
      principalId = {
        type = "string"
      }
      roleDefinitionId = {
        type = "string"
      }
    }
    resources = [
      {
        type       = "Microsoft.Authorization/roleAssignments"
        apiVersion = "2022-04-01"
        name       = "[guid(resourceGroup().id, parameters('principalId'), 'a2')]"
        properties = {
          principalId      = "[parameters('principalId')]"
          roleDefinitionId = "[parameters('roleDefinitionId')]"
        }
      },
    ]
  })
  parameters_content = jsonencode({
    principalId = {
      value = var.fx_aut_02_i_principal_id
    }
    roleDefinitionId = {
      value = azurerm_role_definition.fx_aut_02_i_ps1.role_definition_resource_id
    }
  })
}

# ==== FX-AUT-03-C (CQ-AUT-03, conforming)

resource "azurerm_resource_group" "fx_aut_03_c_s_parent" {
  name     = "${var.run_id}-fx-aut-03-c-s-parent"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_aut_03_c_s_child" {
  name                     = "${var.run_id}fxaut03cschi"
  resource_group_name      = azurerm_resource_group.fx_aut_03_c_s_parent.name
  location                 = azurerm_resource_group.fx_aut_03_c_s_parent.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_account" "fx_aut_03_c_x_sa2" {
  name                     = "${var.run_id}fxaut03cxsa2"
  resource_group_name      = azurerm_resource_group.fx_aut_03_c_s_parent.name
  location                 = azurerm_resource_group.fx_aut_03_c_s_parent.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_03_c_r2" {
  name               = "${var.run_id}-fx-aut-03-c-r2"
  storage_account_id = azurerm_storage_account.fx_aut_03_c_x_sa2.id
}

resource "azurerm_user_assigned_identity" "fx_aut_03_c_p1" {
  name                = "${var.run_id}-fx-aut-03-c-p1"
  resource_group_name = azurerm_resource_group.fx_aut_03_c_s_parent.name
  location            = azurerm_resource_group.fx_aut_03_c_s_parent.location
}

resource "azurerm_role_definition" "fx_aut_03_c_ps1" {
  name  = "${var.run_id}-fx-aut-03-c-ps1"
  scope = azurerm_resource_group.fx_aut_03_c_s_parent.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_03_c_a1" {
  scope              = azurerm_storage_account.fx_aut_03_c_s_child.id
  role_definition_id = azurerm_role_definition.fx_aut_03_c_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_03_c_p1.principal_id
}

# ==== FX-AUT-03-N (CQ-AUT-03, nonconforming)

resource "azurerm_resource_group" "fx_aut_03_n_s_parent" {
  name     = "${var.run_id}-fx-aut-03-n-s-parent"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_aut_03_n_s_child" {
  name                     = "${var.run_id}fxaut03nschi"
  resource_group_name      = azurerm_resource_group.fx_aut_03_n_s_parent.name
  location                 = azurerm_resource_group.fx_aut_03_n_s_parent.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_account" "fx_aut_03_n_x_sa2" {
  name                     = "${var.run_id}fxaut03nxsa2"
  resource_group_name      = azurerm_resource_group.fx_aut_03_n_s_parent.name
  location                 = azurerm_resource_group.fx_aut_03_n_s_parent.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_03_n_r2" {
  name               = "${var.run_id}-fx-aut-03-n-r2"
  storage_account_id = azurerm_storage_account.fx_aut_03_n_x_sa2.id
}

resource "azurerm_user_assigned_identity" "fx_aut_03_n_p1" {
  name                = "${var.run_id}-fx-aut-03-n-p1"
  resource_group_name = azurerm_resource_group.fx_aut_03_n_s_parent.name
  location            = azurerm_resource_group.fx_aut_03_n_s_parent.location
}

resource "azurerm_role_definition" "fx_aut_03_n_ps1" {
  name  = "${var.run_id}-fx-aut-03-n-ps1"
  scope = azurerm_resource_group.fx_aut_03_n_s_parent.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_03_n_a1" {
  scope              = azurerm_resource_group.fx_aut_03_n_s_parent.id
  role_definition_id = azurerm_role_definition.fx_aut_03_n_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_03_n_p1.principal_id
}

# ==== FX-AUT-03-I (CQ-AUT-03, incomplete)

variable "fx_aut_03_i_assignment_scope" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-03-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_aut_03_i_s_parent" {
  name     = "${var.run_id}-fx-aut-03-i-s-parent"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_aut_03_i_s_child" {
  name                     = "${var.run_id}fxaut03ischi"
  resource_group_name      = azurerm_resource_group.fx_aut_03_i_s_parent.name
  location                 = azurerm_resource_group.fx_aut_03_i_s_parent.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_account" "fx_aut_03_i_x_sa2" {
  name                     = "${var.run_id}fxaut03ixsa2"
  resource_group_name      = azurerm_resource_group.fx_aut_03_i_s_parent.name
  location                 = azurerm_resource_group.fx_aut_03_i_s_parent.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_03_i_r2" {
  name               = "${var.run_id}-fx-aut-03-i-r2"
  storage_account_id = azurerm_storage_account.fx_aut_03_i_x_sa2.id
}

resource "azurerm_user_assigned_identity" "fx_aut_03_i_p1" {
  name                = "${var.run_id}-fx-aut-03-i-p1"
  resource_group_name = azurerm_resource_group.fx_aut_03_i_s_parent.name
  location            = azurerm_resource_group.fx_aut_03_i_s_parent.location
}

resource "azurerm_role_definition" "fx_aut_03_i_ps1" {
  name  = "${var.run_id}-fx-aut-03-i-ps1"
  scope = azurerm_resource_group.fx_aut_03_i_s_parent.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_03_i_a1" {
  scope              = var.fx_aut_03_i_assignment_scope
  role_definition_id = azurerm_role_definition.fx_aut_03_i_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_03_i_p1.principal_id
}

# ==== FX-AUT-04-C (CQ-AUT-04, conforming): NOT_APPLICABLE — usuário humano, grupo e pertença não existem no azurerm fixado (Entra ID, provider azuread)

# ==== FX-AUT-04-N (CQ-AUT-04, nonconforming): NOT_APPLICABLE — usuário humano, grupo e pertença não existem no azurerm fixado (Entra ID, provider azuread)

# ==== FX-AUT-04-I (CQ-AUT-04, incomplete)

variable "fx_aut_04_i_group_object_id" {
  type        = string
  description = "entrada simbólica da fixture FX-AUT-04-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_aut_04_i_s1" {
  name     = "${var.run_id}-fx-aut-04-i-s1"
  location = var.location_1
}

resource "azurerm_role_definition" "fx_aut_04_i_ps1" {
  name  = "${var.run_id}-fx-aut-04-i-ps1"
  scope = azurerm_resource_group.fx_aut_04_i_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_role_assignment" "fx_aut_04_i_a1" {
  scope              = azurerm_resource_group.fx_aut_04_i_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_04_i_ps1.role_definition_resource_id
  principal_id       = var.fx_aut_04_i_group_object_id
  principal_type     = "Group"
}

# ==== FX-AUT-05-C (CQ-AUT-05, conforming)

resource "azurerm_resource_group" "fx_aut_05_c_s1" {
  name     = "${var.run_id}-fx-aut-05-c-s1"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_aut_05_c_x_sa" {
  name                     = "${var.run_id}fxaut05cxsa"
  resource_group_name      = azurerm_resource_group.fx_aut_05_c_s1.name
  location                 = azurerm_resource_group.fx_aut_05_c_s1.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_05_c_r1" {
  name               = "${var.run_id}-fx-aut-05-c-r1"
  storage_account_id = azurerm_storage_account.fx_aut_05_c_x_sa.id
}

resource "azurerm_user_assigned_identity" "fx_aut_05_c_p1" {
  name                = "${var.run_id}-fx-aut-05-c-p1"
  resource_group_name = azurerm_resource_group.fx_aut_05_c_s1.name
  location            = azurerm_resource_group.fx_aut_05_c_s1.location
}

resource "azurerm_role_definition" "fx_aut_05_c_ps1" {
  name  = "${var.run_id}-fx-aut-05-c-ps1"
  scope = azurerm_resource_group.fx_aut_05_c_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_virtual_network" "fx_aut_05_c_x_vnet" {
  name                = "${var.run_id}-fx-aut-05-c-x-vnet"
  resource_group_name = azurerm_resource_group.fx_aut_05_c_s1.name
  location            = azurerm_resource_group.fx_aut_05_c_s1.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_aut_05_c_x_subnet_ok" {
  name                 = "${var.run_id}-fx-aut-05-c-x-subnet-ok"
  resource_group_name  = azurerm_resource_group.fx_aut_05_c_s1.name
  virtual_network_name = azurerm_virtual_network.fx_aut_05_c_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_subnet" "fx_aut_05_c_x_subnet_other" {
  name                 = "${var.run_id}-fx-aut-05-c-x-subnet-other"
  resource_group_name  = azurerm_resource_group.fx_aut_05_c_s1.name
  virtual_network_name = azurerm_virtual_network.fx_aut_05_c_x_vnet.name
  address_prefixes     = ["10.30.2.0/24"]
}

resource "azurerm_role_assignment" "fx_aut_05_c_a1" {
  scope              = azurerm_resource_group.fx_aut_05_c_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_05_c_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_05_c_p1.principal_id
  condition          = "((!(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'})) OR (@Environment[Microsoft.Network/virtualNetworks/subnets] ForAnyOfAnyValues:StringEqualsIgnoreCase '${azurerm_subnet.fx_aut_05_c_x_subnet_ok.id}'))"
  condition_version  = "2.0"
}

# ==== FX-AUT-05-N (CQ-AUT-05, nonconforming)

resource "azurerm_resource_group" "fx_aut_05_n_s1" {
  name     = "${var.run_id}-fx-aut-05-n-s1"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_aut_05_n_x_sa" {
  name                     = "${var.run_id}fxaut05nxsa"
  resource_group_name      = azurerm_resource_group.fx_aut_05_n_s1.name
  location                 = azurerm_resource_group.fx_aut_05_n_s1.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_05_n_r1" {
  name               = "${var.run_id}-fx-aut-05-n-r1"
  storage_account_id = azurerm_storage_account.fx_aut_05_n_x_sa.id
}

resource "azurerm_user_assigned_identity" "fx_aut_05_n_p1" {
  name                = "${var.run_id}-fx-aut-05-n-p1"
  resource_group_name = azurerm_resource_group.fx_aut_05_n_s1.name
  location            = azurerm_resource_group.fx_aut_05_n_s1.location
}

resource "azurerm_role_definition" "fx_aut_05_n_ps1" {
  name  = "${var.run_id}-fx-aut-05-n-ps1"
  scope = azurerm_resource_group.fx_aut_05_n_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_virtual_network" "fx_aut_05_n_x_vnet" {
  name                = "${var.run_id}-fx-aut-05-n-x-vnet"
  resource_group_name = azurerm_resource_group.fx_aut_05_n_s1.name
  location            = azurerm_resource_group.fx_aut_05_n_s1.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_aut_05_n_x_subnet_ok" {
  name                 = "${var.run_id}-fx-aut-05-n-x-subnet-ok"
  resource_group_name  = azurerm_resource_group.fx_aut_05_n_s1.name
  virtual_network_name = azurerm_virtual_network.fx_aut_05_n_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_subnet" "fx_aut_05_n_x_subnet_other" {
  name                 = "${var.run_id}-fx-aut-05-n-x-subnet-other"
  resource_group_name  = azurerm_resource_group.fx_aut_05_n_s1.name
  virtual_network_name = azurerm_virtual_network.fx_aut_05_n_x_vnet.name
  address_prefixes     = ["10.30.2.0/24"]
}

resource "azurerm_role_assignment" "fx_aut_05_n_a1" {
  scope              = azurerm_resource_group.fx_aut_05_n_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_05_n_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_05_n_p1.principal_id
  condition          = "((!(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'})) OR (@Environment[Microsoft.Network/virtualNetworks/subnets] ForAnyOfAnyValues:StringEqualsIgnoreCase '${azurerm_subnet.fx_aut_05_n_x_subnet_ok.id}'))"
  condition_version  = "2.0"
}

# ==== FX-AUT-05-I (CQ-AUT-05, incomplete)

resource "azurerm_resource_group" "fx_aut_05_i_s1" {
  name     = "${var.run_id}-fx-aut-05-i-s1"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_aut_05_i_x_sa" {
  name                     = "${var.run_id}fxaut05ixsa"
  resource_group_name      = azurerm_resource_group.fx_aut_05_i_s1.name
  location                 = azurerm_resource_group.fx_aut_05_i_s1.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_aut_05_i_r1" {
  name               = "${var.run_id}-fx-aut-05-i-r1"
  storage_account_id = azurerm_storage_account.fx_aut_05_i_x_sa.id
}

resource "azurerm_user_assigned_identity" "fx_aut_05_i_p1" {
  name                = "${var.run_id}-fx-aut-05-i-p1"
  resource_group_name = azurerm_resource_group.fx_aut_05_i_s1.name
  location            = azurerm_resource_group.fx_aut_05_i_s1.location
}

resource "azurerm_role_definition" "fx_aut_05_i_ps1" {
  name  = "${var.run_id}-fx-aut-05-i-ps1"
  scope = azurerm_resource_group.fx_aut_05_i_s1.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"]
  }
}

resource "azurerm_virtual_network" "fx_aut_05_i_x_vnet" {
  name                = "${var.run_id}-fx-aut-05-i-x-vnet"
  resource_group_name = azurerm_resource_group.fx_aut_05_i_s1.name
  location            = azurerm_resource_group.fx_aut_05_i_s1.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_aut_05_i_x_subnet_ok" {
  name                 = "${var.run_id}-fx-aut-05-i-x-subnet-ok"
  resource_group_name  = azurerm_resource_group.fx_aut_05_i_s1.name
  virtual_network_name = azurerm_virtual_network.fx_aut_05_i_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_subnet" "fx_aut_05_i_x_subnet_other" {
  name                 = "${var.run_id}-fx-aut-05-i-x-subnet-other"
  resource_group_name  = azurerm_resource_group.fx_aut_05_i_s1.name
  virtual_network_name = azurerm_virtual_network.fx_aut_05_i_x_vnet.name
  address_prefixes     = ["10.30.2.0/24"]
}

resource "azurerm_role_assignment" "fx_aut_05_i_a1" {
  scope              = azurerm_resource_group.fx_aut_05_i_s1.id
  role_definition_id = azurerm_role_definition.fx_aut_05_i_ps1.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.fx_aut_05_i_p1.principal_id
  condition          = "((!(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'})) OR (@Principal[Microsoft.Directory/CustomSecurityAttributes/Attributes:posture_compliant] StringEquals 'true'))"
  condition_version  = "2.0"
}

# ==== FX-NET-01-C (CQ-NET-01, conforming)

resource "azurerm_resource_group" "fx_net_01_c_x_rg" {
  name     = "${var.run_id}-fx-net-01-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_01_c_x_vnet" {
  name                = "${var.run_id}-fx-net-01-c-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_01_c_x_rg.name
  location            = azurerm_resource_group.fx_net_01_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_01_c_sa" {
  name                 = "${var.run_id}-fx-net-01-c-sa"
  resource_group_name  = azurerm_resource_group.fx_net_01_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_01_c_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_public_ip" "fx_net_01_c_ip1" {
  name                = "${var.run_id}-fx-net-01-c-ip1"
  resource_group_name = azurerm_resource_group.fx_net_01_c_x_rg.name
  location            = azurerm_resource_group.fx_net_01_c_x_rg.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "fx_net_01_c_nic1" {
  name                = "${var.run_id}-fx-net-01-c-nic1"
  resource_group_name = azurerm_resource_group.fx_net_01_c_x_rg.name
  location            = azurerm_resource_group.fx_net_01_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_01_c_sa.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.fx_net_01_c_ip1.id
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_01_c_vm1" {
  name                  = "${var.run_id}-fx-net-01-c-vm1"
  resource_group_name   = azurerm_resource_group.fx_net_01_c_x_rg.name
  location              = azurerm_resource_group.fx_net_01_c_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_01_c_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_route_table" "fx_net_01_c_rt1" {
  name                = "${var.run_id}-fx-net-01-c-rt1"
  resource_group_name = azurerm_resource_group.fx_net_01_c_x_rg.name
  location            = azurerm_resource_group.fx_net_01_c_x_rg.location
}

resource "azurerm_subnet_route_table_association" "fx_net_01_c_x_rt_assoc" {
  subnet_id      = azurerm_subnet.fx_net_01_c_sa.id
  route_table_id = azurerm_route_table.fx_net_01_c_rt1.id
}

resource "azurerm_route" "fx_net_01_c_rte1" {
  name                = "${var.run_id}-fx-net-01-c-rte1"
  resource_group_name = azurerm_resource_group.fx_net_01_c_x_rg.name
  route_table_name    = azurerm_route_table.fx_net_01_c_rt1.name
  address_prefix      = "0.0.0.0/0"
  next_hop_type       = "Internet"
}

resource "azurerm_network_security_group" "fx_net_01_c_rs1" {
  name                = "${var.run_id}-fx-net-01-c-rs1"
  resource_group_name = azurerm_resource_group.fx_net_01_c_x_rg.name
  location            = azurerm_resource_group.fx_net_01_c_x_rg.location
}

resource "azurerm_network_security_rule" "fx_net_01_c_r1" {
  name                        = "${var.run_id}-fx-net-01-c-r1"
  resource_group_name         = azurerm_resource_group.fx_net_01_c_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_01_c_rs1.name
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "203.0.113.0/24"
  destination_address_prefix  = "*"
}

resource "azurerm_network_interface_security_group_association" "fx_net_01_c_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_01_c_nic1.id
  network_security_group_id = azurerm_network_security_group.fx_net_01_c_rs1.id
}

# ==== FX-NET-01-N (CQ-NET-01, nonconforming)

resource "azurerm_resource_group" "fx_net_01_n_x_rg" {
  name     = "${var.run_id}-fx-net-01-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_01_n_x_vnet" {
  name                = "${var.run_id}-fx-net-01-n-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_01_n_x_rg.name
  location            = azurerm_resource_group.fx_net_01_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_01_n_sa" {
  name                 = "${var.run_id}-fx-net-01-n-sa"
  resource_group_name  = azurerm_resource_group.fx_net_01_n_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_01_n_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_public_ip" "fx_net_01_n_ip1" {
  name                = "${var.run_id}-fx-net-01-n-ip1"
  resource_group_name = azurerm_resource_group.fx_net_01_n_x_rg.name
  location            = azurerm_resource_group.fx_net_01_n_x_rg.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "fx_net_01_n_nic1" {
  name                = "${var.run_id}-fx-net-01-n-nic1"
  resource_group_name = azurerm_resource_group.fx_net_01_n_x_rg.name
  location            = azurerm_resource_group.fx_net_01_n_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_01_n_sa.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.fx_net_01_n_ip1.id
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_01_n_vm1" {
  name                  = "${var.run_id}-fx-net-01-n-vm1"
  resource_group_name   = azurerm_resource_group.fx_net_01_n_x_rg.name
  location              = azurerm_resource_group.fx_net_01_n_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_01_n_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_route_table" "fx_net_01_n_rt1" {
  name                = "${var.run_id}-fx-net-01-n-rt1"
  resource_group_name = azurerm_resource_group.fx_net_01_n_x_rg.name
  location            = azurerm_resource_group.fx_net_01_n_x_rg.location
}

resource "azurerm_subnet_route_table_association" "fx_net_01_n_x_rt_assoc" {
  subnet_id      = azurerm_subnet.fx_net_01_n_sa.id
  route_table_id = azurerm_route_table.fx_net_01_n_rt1.id
}

resource "azurerm_route" "fx_net_01_n_rte1" {
  name                = "${var.run_id}-fx-net-01-n-rte1"
  resource_group_name = azurerm_resource_group.fx_net_01_n_x_rg.name
  route_table_name    = azurerm_route_table.fx_net_01_n_rt1.name
  address_prefix      = "0.0.0.0/0"
  next_hop_type       = "Internet"
}

resource "azurerm_network_security_group" "fx_net_01_n_rs1" {
  name                = "${var.run_id}-fx-net-01-n-rs1"
  resource_group_name = azurerm_resource_group.fx_net_01_n_x_rg.name
  location            = azurerm_resource_group.fx_net_01_n_x_rg.location
}

resource "azurerm_network_security_rule" "fx_net_01_n_r1" {
  name                        = "${var.run_id}-fx-net-01-n-r1"
  resource_group_name         = azurerm_resource_group.fx_net_01_n_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_01_n_rs1.name
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "203.0.113.0/24"
  destination_address_prefix  = "*"
}

resource "azurerm_network_security_rule" "fx_net_01_n_r2" {
  name                        = "${var.run_id}-fx-net-01-n-r2"
  resource_group_name         = azurerm_resource_group.fx_net_01_n_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_01_n_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

resource "azurerm_network_interface_security_group_association" "fx_net_01_n_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_01_n_nic1.id
  network_security_group_id = azurerm_network_security_group.fx_net_01_n_rs1.id
}

# ==== FX-NET-01-I (CQ-NET-01, incomplete)

resource "azurerm_resource_group" "fx_net_01_i_x_rg" {
  name     = "${var.run_id}-fx-net-01-i-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_01_i_x_vnet" {
  name                = "${var.run_id}-fx-net-01-i-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_01_i_x_rg.name
  location            = azurerm_resource_group.fx_net_01_i_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_01_i_sa" {
  name                 = "${var.run_id}-fx-net-01-i-sa"
  resource_group_name  = azurerm_resource_group.fx_net_01_i_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_01_i_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_public_ip" "fx_net_01_i_ip1" {
  name                = "${var.run_id}-fx-net-01-i-ip1"
  resource_group_name = azurerm_resource_group.fx_net_01_i_x_rg.name
  location            = azurerm_resource_group.fx_net_01_i_x_rg.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "fx_net_01_i_nic1" {
  name                = "${var.run_id}-fx-net-01-i-nic1"
  resource_group_name = azurerm_resource_group.fx_net_01_i_x_rg.name
  location            = azurerm_resource_group.fx_net_01_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_01_i_sa.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.fx_net_01_i_ip1.id
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_01_i_vm1" {
  name                  = "${var.run_id}-fx-net-01-i-vm1"
  resource_group_name   = azurerm_resource_group.fx_net_01_i_x_rg.name
  location              = azurerm_resource_group.fx_net_01_i_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_01_i_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_route_table" "fx_net_01_i_rt1" {
  name                = "${var.run_id}-fx-net-01-i-rt1"
  resource_group_name = azurerm_resource_group.fx_net_01_i_x_rg.name
  location            = azurerm_resource_group.fx_net_01_i_x_rg.location
}

resource "azurerm_subnet_route_table_association" "fx_net_01_i_x_rt_assoc" {
  subnet_id      = azurerm_subnet.fx_net_01_i_sa.id
  route_table_id = azurerm_route_table.fx_net_01_i_rt1.id
}

resource "azurerm_route" "fx_net_01_i_rte1" {
  name                = "${var.run_id}-fx-net-01-i-rte1"
  resource_group_name = azurerm_resource_group.fx_net_01_i_x_rg.name
  route_table_name    = azurerm_route_table.fx_net_01_i_rt1.name
  address_prefix      = "0.0.0.0/0"
  next_hop_type       = "Internet"
}

resource "azurerm_network_security_group" "fx_net_01_i_rs1" {
  name                = "${var.run_id}-fx-net-01-i-rs1"
  resource_group_name = azurerm_resource_group.fx_net_01_i_x_rg.name
  location            = azurerm_resource_group.fx_net_01_i_x_rg.location
}

resource "azurerm_network_security_rule" "fx_net_01_i_r1" {
  name                        = "${var.run_id}-fx-net-01-i-r1"
  resource_group_name         = azurerm_resource_group.fx_net_01_i_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_01_i_rs1.name
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "203.0.113.0/24"
  destination_address_prefix  = "*"
}

resource "azurerm_network_interface_security_group_association" "fx_net_01_i_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_01_i_nic1.id
  network_security_group_id = azurerm_network_security_group.fx_net_01_i_rs1.id
}

# ==== FX-NET-02-C (CQ-NET-02, conforming)

resource "azurerm_resource_group" "fx_net_02_c_x_rg" {
  name     = "${var.run_id}-fx-net-02-c-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_net_02_c_rs1" {
  name                = "${var.run_id}-fx-net-02-c-rs1"
  resource_group_name = azurerm_resource_group.fx_net_02_c_x_rg.name
  location            = azurerm_resource_group.fx_net_02_c_x_rg.location
}

resource "azurerm_network_security_rule" "fx_net_02_c_r1" {
  name                        = "${var.run_id}-fx-net-02-c-r1"
  resource_group_name         = azurerm_resource_group.fx_net_02_c_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_02_c_rs1.name
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "203.0.113.0/24"
  destination_address_prefix  = "*"
}

# ==== FX-NET-02-N (CQ-NET-02, nonconforming): NOT_APPLICABLE — regra sem estado não existe no NSG do Azure

# ==== FX-NET-02-I (CQ-NET-02, incomplete): NOT_APPLICABLE — no NSG o estado de conexão é fixo do mecanismo (sempre com estado) e documentado: não há regra com estado não declarado e padrão sem evidência

# ==== FX-NET-03-C (CQ-NET-03, conforming)

resource "azurerm_resource_group" "fx_net_03_c_x_rg" {
  name     = "${var.run_id}-fx-net-03-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_03_c_x_vnet" {
  name                = "${var.run_id}-fx-net-03-c-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_03_c_x_rg.name
  location            = azurerm_resource_group.fx_net_03_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_03_c_sa" {
  name                 = "${var.run_id}-fx-net-03-c-sa"
  resource_group_name  = azurerm_resource_group.fx_net_03_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_03_c_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_public_ip" "fx_net_03_c_ip1" {
  name                = "${var.run_id}-fx-net-03-c-ip1"
  resource_group_name = azurerm_resource_group.fx_net_03_c_x_rg.name
  location            = azurerm_resource_group.fx_net_03_c_x_rg.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "fx_net_03_c_nic1" {
  name                = "${var.run_id}-fx-net-03-c-nic1"
  resource_group_name = azurerm_resource_group.fx_net_03_c_x_rg.name
  location            = azurerm_resource_group.fx_net_03_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_03_c_sa.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.fx_net_03_c_ip1.id
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_03_c_vm1" {
  name                  = "${var.run_id}-fx-net-03-c-vm1"
  resource_group_name   = azurerm_resource_group.fx_net_03_c_x_rg.name
  location              = azurerm_resource_group.fx_net_03_c_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_03_c_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_route_table" "fx_net_03_c_rt1" {
  name                = "${var.run_id}-fx-net-03-c-rt1"
  resource_group_name = azurerm_resource_group.fx_net_03_c_x_rg.name
  location            = azurerm_resource_group.fx_net_03_c_x_rg.location
}

resource "azurerm_subnet_route_table_association" "fx_net_03_c_x_rt_assoc" {
  subnet_id      = azurerm_subnet.fx_net_03_c_sa.id
  route_table_id = azurerm_route_table.fx_net_03_c_rt1.id
}

resource "azurerm_route" "fx_net_03_c_rte1" {
  name                = "${var.run_id}-fx-net-03-c-rte1"
  resource_group_name = azurerm_resource_group.fx_net_03_c_x_rg.name
  route_table_name    = azurerm_route_table.fx_net_03_c_rt1.name
  address_prefix      = "0.0.0.0/0"
  next_hop_type       = "Internet"
}

resource "azurerm_network_security_group" "fx_net_03_c_rs1" {
  name                = "${var.run_id}-fx-net-03-c-rs1"
  resource_group_name = azurerm_resource_group.fx_net_03_c_x_rg.name
  location            = azurerm_resource_group.fx_net_03_c_x_rg.location
}

resource "azurerm_network_security_rule" "fx_net_03_c_r1" {
  name                        = "${var.run_id}-fx-net-03-c-r1"
  resource_group_name         = azurerm_resource_group.fx_net_03_c_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_03_c_rs1.name
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

resource "azurerm_network_interface_security_group_association" "fx_net_03_c_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_03_c_nic1.id
  network_security_group_id = azurerm_network_security_group.fx_net_03_c_rs1.id
}

# ==== FX-NET-03-N (CQ-NET-03, nonconforming)

resource "azurerm_resource_group" "fx_net_03_n_x_rg" {
  name     = "${var.run_id}-fx-net-03-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_03_n_x_vnet" {
  name                = "${var.run_id}-fx-net-03-n-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_03_n_x_rg.name
  location            = azurerm_resource_group.fx_net_03_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_03_n_sa" {
  name                 = "${var.run_id}-fx-net-03-n-sa"
  resource_group_name  = azurerm_resource_group.fx_net_03_n_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_03_n_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_net_03_n_nic1" {
  name                = "${var.run_id}-fx-net-03-n-nic1"
  resource_group_name = azurerm_resource_group.fx_net_03_n_x_rg.name
  location            = azurerm_resource_group.fx_net_03_n_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_03_n_sa.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_03_n_vm1" {
  name                  = "${var.run_id}-fx-net-03-n-vm1"
  resource_group_name   = azurerm_resource_group.fx_net_03_n_x_rg.name
  location              = azurerm_resource_group.fx_net_03_n_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_03_n_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_route_table" "fx_net_03_n_rt1" {
  name                = "${var.run_id}-fx-net-03-n-rt1"
  resource_group_name = azurerm_resource_group.fx_net_03_n_x_rg.name
  location            = azurerm_resource_group.fx_net_03_n_x_rg.location
}

resource "azurerm_subnet_route_table_association" "fx_net_03_n_x_rt_assoc" {
  subnet_id      = azurerm_subnet.fx_net_03_n_sa.id
  route_table_id = azurerm_route_table.fx_net_03_n_rt1.id
}

resource "azurerm_route" "fx_net_03_n_x_drop" {
  name                = "${var.run_id}-fx-net-03-n-drop"
  resource_group_name = azurerm_resource_group.fx_net_03_n_x_rg.name
  route_table_name    = azurerm_route_table.fx_net_03_n_rt1.name
  address_prefix      = "0.0.0.0/0"
  next_hop_type       = "None"
}

resource "azurerm_network_security_group" "fx_net_03_n_rs1" {
  name                = "${var.run_id}-fx-net-03-n-rs1"
  resource_group_name = azurerm_resource_group.fx_net_03_n_x_rg.name
  location            = azurerm_resource_group.fx_net_03_n_x_rg.location
}

resource "azurerm_network_security_rule" "fx_net_03_n_r1" {
  name                        = "${var.run_id}-fx-net-03-n-r1"
  resource_group_name         = azurerm_resource_group.fx_net_03_n_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_03_n_rs1.name
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

resource "azurerm_network_interface_security_group_association" "fx_net_03_n_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_03_n_nic1.id
  network_security_group_id = azurerm_network_security_group.fx_net_03_n_rs1.id
}

# ==== FX-NET-03-I (CQ-NET-03, incomplete)

variable "fx_net_03_i_route_table_id" {
  type        = string
  description = "entrada simbólica da fixture FX-NET-03-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_net_03_i_x_rg" {
  name     = "${var.run_id}-fx-net-03-i-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_03_i_x_vnet" {
  name                = "${var.run_id}-fx-net-03-i-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_03_i_x_rg.name
  location            = azurerm_resource_group.fx_net_03_i_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_03_i_sa" {
  name                 = "${var.run_id}-fx-net-03-i-sa"
  resource_group_name  = azurerm_resource_group.fx_net_03_i_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_03_i_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_public_ip" "fx_net_03_i_ip1" {
  name                = "${var.run_id}-fx-net-03-i-ip1"
  resource_group_name = azurerm_resource_group.fx_net_03_i_x_rg.name
  location            = azurerm_resource_group.fx_net_03_i_x_rg.location
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "fx_net_03_i_nic1" {
  name                = "${var.run_id}-fx-net-03-i-nic1"
  resource_group_name = azurerm_resource_group.fx_net_03_i_x_rg.name
  location            = azurerm_resource_group.fx_net_03_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_03_i_sa.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.fx_net_03_i_ip1.id
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_03_i_vm1" {
  name                  = "${var.run_id}-fx-net-03-i-vm1"
  resource_group_name   = azurerm_resource_group.fx_net_03_i_x_rg.name
  location              = azurerm_resource_group.fx_net_03_i_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_03_i_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_subnet_route_table_association" "fx_net_03_i_x_rt_assoc" {
  subnet_id      = azurerm_subnet.fx_net_03_i_sa.id
  route_table_id = var.fx_net_03_i_route_table_id
}

resource "azurerm_network_security_group" "fx_net_03_i_rs1" {
  name                = "${var.run_id}-fx-net-03-i-rs1"
  resource_group_name = azurerm_resource_group.fx_net_03_i_x_rg.name
  location            = azurerm_resource_group.fx_net_03_i_x_rg.location
}

resource "azurerm_network_security_rule" "fx_net_03_i_r1" {
  name                        = "${var.run_id}-fx-net-03-i-r1"
  resource_group_name         = azurerm_resource_group.fx_net_03_i_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_net_03_i_rs1.name
  priority                    = 200
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

resource "azurerm_network_interface_security_group_association" "fx_net_03_i_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_03_i_nic1.id
  network_security_group_id = azurerm_network_security_group.fx_net_03_i_rs1.id
}

# ==== FX-NET-04-C (CQ-NET-04, conforming)

resource "azurerm_resource_group" "fx_net_04_c_x_rg" {
  name     = "${var.run_id}-fx-net-04-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_04_c_x_vnet" {
  name                = "${var.run_id}-fx-net-04-c-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_04_c_x_rg.name
  location            = azurerm_resource_group.fx_net_04_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_04_c_x_subnet" {
  name                 = "${var.run_id}-fx-net-04-c-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_net_04_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_04_c_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_security_group" "fx_net_04_c_rs1" {
  name                = "${var.run_id}-fx-net-04-c-rs1"
  resource_group_name = azurerm_resource_group.fx_net_04_c_x_rg.name
  location            = azurerm_resource_group.fx_net_04_c_x_rg.location
}

resource "azurerm_network_interface" "fx_net_04_c_nic1" {
  name                = "${var.run_id}-fx-net-04-c-nic1"
  resource_group_name = azurerm_resource_group.fx_net_04_c_x_rg.name
  location            = azurerm_resource_group.fx_net_04_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_04_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "fx_net_04_c_nic2" {
  name                = "${var.run_id}-fx-net-04-c-nic2"
  resource_group_name = azurerm_resource_group.fx_net_04_c_x_rg.name
  location            = azurerm_resource_group.fx_net_04_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_04_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_04_c_vm1" {
  name                = "${var.run_id}-fx-net-04-c-vm1"
  resource_group_name = azurerm_resource_group.fx_net_04_c_x_rg.name
  location            = azurerm_resource_group.fx_net_04_c_x_rg.location
  size                = "Standard_B1ls"
  admin_username      = "boadmin"
  network_interface_ids = [
    azurerm_network_interface.fx_net_04_c_nic1.id,
    azurerm_network_interface.fx_net_04_c_nic2.id,
  ]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_network_interface_security_group_association" "fx_net_04_c_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_04_c_nic2.id
  network_security_group_id = azurerm_network_security_group.fx_net_04_c_rs1.id
}

# ==== FX-NET-04-N (CQ-NET-04, nonconforming)

resource "azurerm_resource_group" "fx_net_04_n_x_rg" {
  name     = "${var.run_id}-fx-net-04-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_04_n_x_vnet" {
  name                = "${var.run_id}-fx-net-04-n-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_04_n_x_rg.name
  location            = azurerm_resource_group.fx_net_04_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_04_n_x_subnet" {
  name                 = "${var.run_id}-fx-net-04-n-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_net_04_n_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_04_n_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_security_group" "fx_net_04_n_rs1" {
  name                = "${var.run_id}-fx-net-04-n-rs1"
  resource_group_name = azurerm_resource_group.fx_net_04_n_x_rg.name
  location            = azurerm_resource_group.fx_net_04_n_x_rg.location
}

resource "azurerm_network_interface" "fx_net_04_n_nic1" {
  name                = "${var.run_id}-fx-net-04-n-nic1"
  resource_group_name = azurerm_resource_group.fx_net_04_n_x_rg.name
  location            = azurerm_resource_group.fx_net_04_n_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_04_n_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_04_n_vm1" {
  name                  = "${var.run_id}-fx-net-04-n-vm1"
  resource_group_name   = azurerm_resource_group.fx_net_04_n_x_rg.name
  location              = azurerm_resource_group.fx_net_04_n_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_04_n_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_network_interface" "fx_net_04_n_nic3" {
  name                = "${var.run_id}-fx-net-04-n-nic3"
  resource_group_name = azurerm_resource_group.fx_net_04_n_x_rg.name
  location            = azurerm_resource_group.fx_net_04_n_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_04_n_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_04_n_vm2" {
  name                  = "${var.run_id}-fx-net-04-n-vm2"
  resource_group_name   = azurerm_resource_group.fx_net_04_n_x_rg.name
  location              = azurerm_resource_group.fx_net_04_n_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_net_04_n_nic3.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_network_interface_security_group_association" "fx_net_04_n_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_04_n_nic3.id
  network_security_group_id = azurerm_network_security_group.fx_net_04_n_rs1.id
}

# ==== FX-NET-04-I (CQ-NET-04, incomplete)

variable "fx_net_04_i_nic2_nsg_id" {
  type        = string
  description = "entrada simbólica da fixture FX-NET-04-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_net_04_i_x_rg" {
  name     = "${var.run_id}-fx-net-04-i-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_net_04_i_x_vnet" {
  name                = "${var.run_id}-fx-net-04-i-x-vnet"
  resource_group_name = azurerm_resource_group.fx_net_04_i_x_rg.name
  location            = azurerm_resource_group.fx_net_04_i_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_net_04_i_x_subnet" {
  name                 = "${var.run_id}-fx-net-04-i-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_net_04_i_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_net_04_i_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_security_group" "fx_net_04_i_rs1" {
  name                = "${var.run_id}-fx-net-04-i-rs1"
  resource_group_name = azurerm_resource_group.fx_net_04_i_x_rg.name
  location            = azurerm_resource_group.fx_net_04_i_x_rg.location
}

resource "azurerm_network_interface" "fx_net_04_i_nic1" {
  name                = "${var.run_id}-fx-net-04-i-nic1"
  resource_group_name = azurerm_resource_group.fx_net_04_i_x_rg.name
  location            = azurerm_resource_group.fx_net_04_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_04_i_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "fx_net_04_i_nic2" {
  name                = "${var.run_id}-fx-net-04-i-nic2"
  resource_group_name = azurerm_resource_group.fx_net_04_i_x_rg.name
  location            = azurerm_resource_group.fx_net_04_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_net_04_i_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_net_04_i_vm1" {
  name                = "${var.run_id}-fx-net-04-i-vm1"
  resource_group_name = azurerm_resource_group.fx_net_04_i_x_rg.name
  location            = azurerm_resource_group.fx_net_04_i_x_rg.location
  size                = "Standard_B1ls"
  admin_username      = "boadmin"
  network_interface_ids = [
    azurerm_network_interface.fx_net_04_i_nic1.id,
    azurerm_network_interface.fx_net_04_i_nic2.id,
  ]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_network_interface_security_group_association" "fx_net_04_i_x_nsg_assoc" {
  network_interface_id      = azurerm_network_interface.fx_net_04_i_nic2.id
  network_security_group_id = var.fx_net_04_i_nic2_nsg_id
}

# ==== FX-CVO-01-C (CQ-CVO-01, conforming)

resource "azurerm_resource_group" "fx_cvo_01_c_x_rg" {
  name     = "${var.run_id}-fx-cvo-01-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cvo_01_c_x_sa" {
  name                     = "${var.run_id}fxcvo01cxsa"
  resource_group_name      = azurerm_resource_group.fx_cvo_01_c_x_rg.name
  location                 = azurerm_resource_group.fx_cvo_01_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

resource "azurerm_storage_container" "fx_cvo_01_c_c1" {
  name               = "${var.run_id}-fx-cvo-01-c-c1"
  storage_account_id = azurerm_storage_account.fx_cvo_01_c_x_sa.id
}

# ==== FX-CVO-01-N (CQ-CVO-01, nonconforming)

resource "azurerm_resource_group" "fx_cvo_01_n_x_rg" {
  name     = "${var.run_id}-fx-cvo-01-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cvo_01_n_x_sa" {
  name                     = "${var.run_id}fxcvo01nxsa"
  resource_group_name      = azurerm_resource_group.fx_cvo_01_n_x_rg.name
  location                 = azurerm_resource_group.fx_cvo_01_n_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

resource "azurerm_storage_container" "fx_cvo_01_n_c1" {
  name               = "${var.run_id}-fx-cvo-01-n-c1"
  storage_account_id = azurerm_storage_account.fx_cvo_01_n_x_sa.id
}

# ==== FX-CVO-01-I (CQ-CVO-01, incomplete)

resource "azurerm_resource_group" "fx_cvo_01_i_x_rg" {
  name     = "${var.run_id}-fx-cvo-01-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cvo_01_i_x_sa" {
  name                     = "${var.run_id}fxcvo01ixsa"
  resource_group_name      = azurerm_resource_group.fx_cvo_01_i_x_rg.name
  location                 = azurerm_resource_group.fx_cvo_01_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

resource "azurerm_storage_container" "fx_cvo_01_i_c1" {
  name               = "${var.run_id}-fx-cvo-01-i-c1"
  storage_account_id = azurerm_storage_account.fx_cvo_01_i_x_sa.id
}

# ==== FX-CVO-02-C (CQ-CVO-02, conforming)

resource "azurerm_resource_group" "fx_cvo_02_c_x_rg" {
  name     = "${var.run_id}-fx-cvo-02-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cvo_02_c_x_sa" {
  name                     = "${var.run_id}fxcvo02cxsa"
  resource_group_name      = azurerm_resource_group.fx_cvo_02_c_x_rg.name
  location                 = azurerm_resource_group.fx_cvo_02_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

resource "azurerm_storage_container" "fx_cvo_02_c_c1" {
  name               = "${var.run_id}-fx-cvo-02-c-c1"
  storage_account_id = azurerm_storage_account.fx_cvo_02_c_x_sa.id
}

# ==== FX-CVO-02-N (CQ-CVO-02, nonconforming)

resource "azurerm_resource_group" "fx_cvo_02_n_x_rg" {
  name     = "${var.run_id}-fx-cvo-02-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cvo_02_n_x_sa" {
  name                     = "${var.run_id}fxcvo02nxsa"
  resource_group_name      = azurerm_resource_group.fx_cvo_02_n_x_rg.name
  location                 = azurerm_resource_group.fx_cvo_02_n_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "fx_cvo_02_n_c1" {
  name               = "${var.run_id}-fx-cvo-02-n-c1"
  storage_account_id = azurerm_storage_account.fx_cvo_02_n_x_sa.id
}

# ==== FX-CVO-02-I (CQ-CVO-02, incomplete)

variable "fx_cvo_02_i_versioning" {
  type        = bool
  description = "entrada simbólica da fixture FX-CVO-02-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_cvo_02_i_x_rg" {
  name     = "${var.run_id}-fx-cvo-02-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_cvo_02_i_x_sa" {
  name                     = "${var.run_id}fxcvo02ixsa"
  resource_group_name      = azurerm_resource_group.fx_cvo_02_i_x_rg.name
  location                 = azurerm_resource_group.fx_cvo_02_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = var.fx_cvo_02_i_versioning
  }
}

resource "azurerm_storage_container" "fx_cvo_02_i_c1" {
  name               = "${var.run_id}-fx-cvo-02-i-c1"
  storage_account_id = azurerm_storage_account.fx_cvo_02_i_x_sa.id
}

# ==== FX-CVO-03-C (CQ-CVO-03, conforming)

resource "azurerm_resource_group" "fx_cvo_03_c_x_rg" {
  name     = "${var.run_id}-fx-cvo-03-c-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cvo_03_c_x_client" {
}

resource "azurerm_postgresql_flexible_server" "fx_cvo_03_c_i1" {
  name                = "${var.run_id}-fx-cvo-03-c-i1"
  resource_group_name = azurerm_resource_group.fx_cvo_03_c_x_rg.name
  location            = azurerm_resource_group.fx_cvo_03_c_x_rg.location
  version             = "16"
  sku_name            = "B_Standard_B1ms"
  storage_mb          = 32768
  zone                = "1"
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.fx_cvo_03_c_x_client.tenant_id
  }
}

resource "azurerm_monitor_action_group" "fx_cvo_03_c_t1" {
  name                = "${var.run_id}-fx-cvo-03-c-t1"
  resource_group_name = azurerm_resource_group.fx_cvo_03_c_x_rg.name
  short_name          = "bocqfix"
}

resource "azurerm_monitor_metric_alert" "fx_cvo_03_c_al1" {
  name                = "${var.run_id}-fx-cvo-03-c-al1"
  resource_group_name = azurerm_resource_group.fx_cvo_03_c_x_rg.name
  scopes              = [azurerm_postgresql_flexible_server.fx_cvo_03_c_i1.id]
  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "cpu_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }
  action {
    action_group_id = azurerm_monitor_action_group.fx_cvo_03_c_t1.id
  }
}

# ==== FX-CVO-03-N (CQ-CVO-03, nonconforming)

resource "azurerm_resource_group" "fx_cvo_03_n_s1" {
  name     = "${var.run_id}-fx-cvo-03-n-s1"
  location = var.location_1
}

data "azurerm_client_config" "fx_cvo_03_n_x_client" {
}

resource "azurerm_postgresql_flexible_server" "fx_cvo_03_n_i1" {
  name                = "${var.run_id}-fx-cvo-03-n-i1"
  resource_group_name = azurerm_resource_group.fx_cvo_03_n_s1.name
  location            = azurerm_resource_group.fx_cvo_03_n_s1.location
  version             = "16"
  sku_name            = "B_Standard_B1ms"
  storage_mb          = 32768
  zone                = "1"
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.fx_cvo_03_n_x_client.tenant_id
  }
}

# ==== FX-CVO-03-I (CQ-CVO-03, incomplete)

resource "azurerm_resource_group" "fx_cvo_03_i_s1" {
  name     = "${var.run_id}-fx-cvo-03-i-s1"
  location = var.location_1
}

data "azurerm_client_config" "fx_cvo_03_i_x_client" {
}

resource "azurerm_postgresql_flexible_server" "fx_cvo_03_i_i1" {
  name                = "${var.run_id}-fx-cvo-03-i-i1"
  resource_group_name = azurerm_resource_group.fx_cvo_03_i_s1.name
  location            = azurerm_resource_group.fx_cvo_03_i_s1.location
  version             = "16"
  sku_name            = "B_Standard_B1ms"
  storage_mb          = 32768
  zone                = "1"
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.fx_cvo_03_i_x_client.tenant_id
  }
}

# ==== FX-CVO-04-C (CQ-CVO-04, conforming)

resource "azurerm_resource_group" "fx_cvo_04_c_x_rg" {
  name     = "${var.run_id}-fx-cvo-04-c-x-rg"
  location = var.location_1
}

resource "azurerm_postgresql_flexible_server" "fx_cvo_04_c_i1" {
  name                   = "${var.run_id}-fx-cvo-04-c-i1"
  resource_group_name    = azurerm_resource_group.fx_cvo_04_c_x_rg.name
  location               = azurerm_resource_group.fx_cvo_04_c_x_rg.location
  version                = "16"
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
  zone                   = "1"
  administrator_login    = "boadmin"
  administrator_password = var.db_admin_password
}

# ==== FX-CVO-04-N (CQ-CVO-04, nonconforming)

resource "azurerm_resource_group" "fx_cvo_04_n_x_rg" {
  name     = "${var.run_id}-fx-cvo-04-n-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_cvo_04_n_x_client" {
}

resource "azurerm_postgresql_flexible_server" "fx_cvo_04_n_i1" {
  name                = "${var.run_id}-fx-cvo-04-n-i1"
  resource_group_name = azurerm_resource_group.fx_cvo_04_n_x_rg.name
  location            = azurerm_resource_group.fx_cvo_04_n_x_rg.location
  version             = "16"
  sku_name            = "B_Standard_B1ms"
  storage_mb          = 32768
  zone                = "1"
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.fx_cvo_04_n_x_client.tenant_id
  }
}

# ==== FX-CVO-04-I (CQ-CVO-04, incomplete)

variable "fx_cvo_04_i_admin_password" {
  type        = string
  description = "entrada simbólica da fixture FX-CVO-04-I; sem valor de propósito"
  sensitive   = true
}

resource "azurerm_resource_group" "fx_cvo_04_i_x_rg" {
  name     = "${var.run_id}-fx-cvo-04-i-x-rg"
  location = var.location_1
}

resource "azurerm_postgresql_flexible_server" "fx_cvo_04_i_i1" {
  name                   = "${var.run_id}-fx-cvo-04-i-i1"
  resource_group_name    = azurerm_resource_group.fx_cvo_04_i_x_rg.name
  location               = azurerm_resource_group.fx_cvo_04_i_x_rg.location
  version                = "16"
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
  zone                   = "1"
  administrator_login    = "boadmin"
  administrator_password = var.fx_cvo_04_i_admin_password
}

# ==== FX-LOSS-01-C (CQ-LOSS-01, conforming)

resource "azurerm_resource_group" "fx_loss_01_c_x_rg" {
  name     = "${var.run_id}-fx-loss-01-c-x-rg"
  location = var.location_1
}

resource "azurerm_log_analytics_workspace" "fx_loss_01_c_s1" {
  name                = "${var.run_id}-fx-loss-01-c-s1"
  resource_group_name = azurerm_resource_group.fx_loss_01_c_x_rg.name
  location            = azurerm_resource_group.fx_loss_01_c_x_rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# ==== FX-LOSS-01-N (CQ-LOSS-01, nonconforming)

resource "azurerm_resource_group" "fx_loss_01_n_x_rg" {
  name     = "${var.run_id}-fx-loss-01-n-x-rg"
  location = var.location_1
}

resource "azurerm_log_analytics_workspace" "fx_loss_01_n_s1" {
  name                = "${var.run_id}-fx-loss-01-n-s1"
  resource_group_name = azurerm_resource_group.fx_loss_01_n_x_rg.name
  location            = azurerm_resource_group.fx_loss_01_n_x_rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 400
}

# ==== FX-LOSS-01-I (CQ-LOSS-01, incomplete)

resource "azurerm_resource_group" "fx_loss_01_i_x_rg" {
  name     = "${var.run_id}-fx-loss-01-i-x-rg"
  location = var.location_1
}

resource "azurerm_log_analytics_workspace" "fx_loss_01_i_s1" {
  name                = "${var.run_id}-fx-loss-01-i-s1"
  resource_group_name = azurerm_resource_group.fx_loss_01_i_x_rg.name
  location            = azurerm_resource_group.fx_loss_01_i_x_rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# ==== FX-LOSS-02-C (CQ-LOSS-02, conforming)

resource "azurerm_resource_group" "fx_loss_02_c_x_rg" {
  name     = "${var.run_id}-fx-loss-02-c-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_loss_02_c_rs1" {
  name                = "${var.run_id}-fx-loss-02-c-rs1"
  resource_group_name = azurerm_resource_group.fx_loss_02_c_x_rg.name
  location            = azurerm_resource_group.fx_loss_02_c_x_rg.location
}

resource "azurerm_network_security_rule" "fx_loss_02_c_r1" {
  name                        = "${var.run_id}-fx-loss-02-c-r1"
  resource_group_name         = azurerm_resource_group.fx_loss_02_c_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_loss_02_c_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

# ==== FX-LOSS-02-N (CQ-LOSS-02, nonconforming)

resource "azurerm_resource_group" "fx_loss_02_n_x_rg" {
  name     = "${var.run_id}-fx-loss-02-n-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_loss_02_n_rs1" {
  name                = "${var.run_id}-fx-loss-02-n-rs1"
  resource_group_name = azurerm_resource_group.fx_loss_02_n_x_rg.name
  location            = azurerm_resource_group.fx_loss_02_n_x_rg.location
}

resource "azurerm_network_security_rule" "fx_loss_02_n_r1" {
  name                        = "${var.run_id}-fx-loss-02-n-r1"
  resource_group_name         = azurerm_resource_group.fx_loss_02_n_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_loss_02_n_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

# ==== FX-LOSS-02-I (CQ-LOSS-02, incomplete)

resource "azurerm_resource_group" "fx_loss_02_i_x_rg" {
  name     = "${var.run_id}-fx-loss-02-i-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_loss_02_i_rs1" {
  name                = "${var.run_id}-fx-loss-02-i-rs1"
  resource_group_name = azurerm_resource_group.fx_loss_02_i_x_rg.name
  location            = azurerm_resource_group.fx_loss_02_i_x_rg.location
}

resource "azurerm_network_security_rule" "fx_loss_02_i_r1" {
  name                        = "${var.run_id}-fx-loss-02-i-r1"
  resource_group_name         = azurerm_resource_group.fx_loss_02_i_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_loss_02_i_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

# ==== FX-LOSS-03-C (CQ-LOSS-03, conforming)

resource "azurerm_resource_group" "fx_loss_03_c_x_rg" {
  name     = "${var.run_id}-fx-loss-03-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_loss_03_c_x_sa" {
  name                     = "${var.run_id}fxloss03cxsa"
  resource_group_name      = azurerm_resource_group.fx_loss_03_c_x_rg.name
  location                 = azurerm_resource_group.fx_loss_03_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

# ==== FX-LOSS-03-N (CQ-LOSS-03, nonconforming)

resource "azurerm_resource_group" "fx_loss_03_n_x_rg" {
  name     = "${var.run_id}-fx-loss-03-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_loss_03_n_x_sa" {
  name                     = "${var.run_id}fxloss03nxsa"
  resource_group_name      = azurerm_resource_group.fx_loss_03_n_x_rg.name
  location                 = azurerm_resource_group.fx_loss_03_n_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

# ==== FX-LOSS-03-I (CQ-LOSS-03, incomplete)

variable "fx_loss_03_i_value" {
  type        = bool
  description = "entrada simbólica da fixture FX-LOSS-03-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_loss_03_i_x_rg" {
  name     = "${var.run_id}-fx-loss-03-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_loss_03_i_x_sa" {
  name                     = "${var.run_id}fxloss03ixsa"
  resource_group_name      = azurerm_resource_group.fx_loss_03_i_x_rg.name
  location                 = azurerm_resource_group.fx_loss_03_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = var.fx_loss_03_i_value
  }
}

# ==== FX-LOSS-04-C (CQ-LOSS-04, conforming)

resource "azurerm_resource_group" "fx_loss_04_c_x_rg" {
  name     = "${var.run_id}-fx-loss-04-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_loss_04_c_x_sa" {
  name                     = "${var.run_id}fxloss04cxsa"
  resource_group_name      = azurerm_resource_group.fx_loss_04_c_x_rg.name
  location                 = azurerm_resource_group.fx_loss_04_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

# ==== FX-LOSS-04-N (CQ-LOSS-04, nonconforming)

resource "azurerm_resource_group" "fx_loss_04_n_x_rg" {
  name     = "${var.run_id}-fx-loss-04-n-x-rg"
  location = var.location_1
}

data "azurerm_client_config" "fx_loss_04_n_x_client" {
}

resource "azurerm_mssql_server" "fx_loss_04_n_x_sql" {
  name                = "${var.run_id}-fx-loss-04-n-x-sql"
  resource_group_name = azurerm_resource_group.fx_loss_04_n_x_rg.name
  location            = azurerm_resource_group.fx_loss_04_n_x_rg.location
  version             = "12.0"
  azuread_administrator {
    login_username              = "bo-admin"
    object_id                   = data.azurerm_client_config.fx_loss_04_n_x_client.object_id
    azuread_authentication_only = true
  }
}

resource "azurerm_mssql_database" "fx_loss_04_n_x_db" {
  name      = "${var.run_id}-fx-loss-04-n-x-db"
  server_id = azurerm_mssql_server.fx_loss_04_n_x_sql.id
  sku_name  = "Basic"
  long_term_retention_policy {
    monthly_retention = "P1M"
  }
}

# ==== FX-LOSS-04-I (CQ-LOSS-04, incomplete)

resource "azurerm_resource_group" "fx_loss_04_i_x_rg" {
  name     = "${var.run_id}-fx-loss-04-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_loss_04_i_x_sa" {
  name                     = "${var.run_id}fxloss04ixsa"
  resource_group_name      = azurerm_resource_group.fx_loss_04_i_x_rg.name
  location                 = azurerm_resource_group.fx_loss_04_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    container_delete_retention_policy {
      days = 30
    }
  }
}

# ==== FX-NEW-01-C (CQ-NEW-01, conforming)

resource "azurerm_resource_group" "fx_new_01_c_x_rg" {
  name     = "${var.run_id}-fx-new-01-c-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_new_01_c_x_sa" {
  name                     = "${var.run_id}fxnew01cxsa"
  resource_group_name      = azurerm_resource_group.fx_new_01_c_x_rg.name
  location                 = azurerm_resource_group.fx_new_01_c_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  blob_properties {
    versioning_enabled = true
  }
}

# ==== FX-NEW-01-N (CQ-NEW-01, nonconforming)

resource "azurerm_resource_group" "fx_new_01_n_x_rg" {
  name     = "${var.run_id}-fx-new-01-n-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_new_01_n_x_sa" {
  name                     = "${var.run_id}fxnew01nxsa"
  resource_group_name      = azurerm_resource_group.fx_new_01_n_x_rg.name
  location                 = azurerm_resource_group.fx_new_01_n_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  allowed_copy_scope       = "PrivateLink"
}

# ==== FX-NEW-01-I (CQ-NEW-01, incomplete)

resource "azurerm_resource_group" "fx_new_01_i_x_rg" {
  name     = "${var.run_id}-fx-new-01-i-x-rg"
  location = var.location_1
}

resource "azurerm_storage_account" "fx_new_01_i_x_sa" {
  name                     = "${var.run_id}fxnew01ixsa"
  resource_group_name      = azurerm_resource_group.fx_new_01_i_x_rg.name
  location                 = azurerm_resource_group.fx_new_01_i_x_rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  dns_endpoint_type        = "Standard"
}

# ==== FX-NEW-02-C (CQ-NEW-02, conforming)

resource "azurerm_resource_group" "fx_new_02_c_x_rg" {
  name     = "${var.run_id}-fx-new-02-c-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_new_02_c_x_vnet" {
  name                = "${var.run_id}-fx-new-02-c-x-vnet"
  resource_group_name = azurerm_resource_group.fx_new_02_c_x_rg.name
  location            = azurerm_resource_group.fx_new_02_c_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_new_02_c_x_subnet" {
  name                 = "${var.run_id}-fx-new-02-c-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_new_02_c_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_new_02_c_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_new_02_c_nic1" {
  name                = "${var.run_id}-fx-new-02-c-nic1"
  resource_group_name = azurerm_resource_group.fx_new_02_c_x_rg.name
  location            = azurerm_resource_group.fx_new_02_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_new_02_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "fx_new_02_c_nic2" {
  name                = "${var.run_id}-fx-new-02-c-nic2"
  resource_group_name = azurerm_resource_group.fx_new_02_c_x_rg.name
  location            = azurerm_resource_group.fx_new_02_c_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_new_02_c_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_new_02_c_vm1" {
  name                = "${var.run_id}-fx-new-02-c-vm1"
  resource_group_name = azurerm_resource_group.fx_new_02_c_x_rg.name
  location            = azurerm_resource_group.fx_new_02_c_x_rg.location
  size                = "Standard_B1ls"
  admin_username      = "boadmin"
  network_interface_ids = [
    azurerm_network_interface.fx_new_02_c_nic1.id,
    azurerm_network_interface.fx_new_02_c_nic2.id,
  ]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-NEW-02-N (CQ-NEW-02, nonconforming)

resource "azurerm_resource_group" "fx_new_02_n_x_rg" {
  name     = "${var.run_id}-fx-new-02-n-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_new_02_n_x_vnet" {
  name                = "${var.run_id}-fx-new-02-n-x-vnet"
  resource_group_name = azurerm_resource_group.fx_new_02_n_x_rg.name
  location            = azurerm_resource_group.fx_new_02_n_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_new_02_n_x_subnet" {
  name                 = "${var.run_id}-fx-new-02-n-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_new_02_n_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_new_02_n_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_new_02_n_nic1" {
  name                = "${var.run_id}-fx-new-02-n-nic1"
  resource_group_name = azurerm_resource_group.fx_new_02_n_x_rg.name
  location            = azurerm_resource_group.fx_new_02_n_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_new_02_n_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
  ip_configuration {
    name                          = "secondary1"
    subnet_id                     = azurerm_subnet.fx_new_02_n_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_new_02_n_vm1" {
  name                  = "${var.run_id}-fx-new-02-n-vm1"
  resource_group_name   = azurerm_resource_group.fx_new_02_n_x_rg.name
  location              = azurerm_resource_group.fx_new_02_n_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = [azurerm_network_interface.fx_new_02_n_nic1.id]
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-NEW-02-I (CQ-NEW-02, incomplete)

variable "fx_new_02_i_extra_nic_ids" {
  type        = list(string)
  description = "entrada simbólica da fixture FX-NEW-02-I; sem valor de propósito"
}

resource "azurerm_resource_group" "fx_new_02_i_x_rg" {
  name     = "${var.run_id}-fx-new-02-i-x-rg"
  location = var.location_1
}

resource "azurerm_virtual_network" "fx_new_02_i_x_vnet" {
  name                = "${var.run_id}-fx-new-02-i-x-vnet"
  resource_group_name = azurerm_resource_group.fx_new_02_i_x_rg.name
  location            = azurerm_resource_group.fx_new_02_i_x_rg.location
  address_space       = ["10.30.0.0/16"]
}

resource "azurerm_subnet" "fx_new_02_i_x_subnet" {
  name                 = "${var.run_id}-fx-new-02-i-x-subnet"
  resource_group_name  = azurerm_resource_group.fx_new_02_i_x_rg.name
  virtual_network_name = azurerm_virtual_network.fx_new_02_i_x_vnet.name
  address_prefixes     = ["10.30.1.0/24"]
}

resource "azurerm_network_interface" "fx_new_02_i_nic1" {
  name                = "${var.run_id}-fx-new-02-i-nic1"
  resource_group_name = azurerm_resource_group.fx_new_02_i_x_rg.name
  location            = azurerm_resource_group.fx_new_02_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_new_02_i_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_network_interface" "fx_new_02_i_nic2" {
  name                = "${var.run_id}-fx-new-02-i-nic2"
  resource_group_name = azurerm_resource_group.fx_new_02_i_x_rg.name
  location            = azurerm_resource_group.fx_new_02_i_x_rg.location
  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.fx_new_02_i_x_subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "fx_new_02_i_vm1" {
  name                  = "${var.run_id}-fx-new-02-i-vm1"
  resource_group_name   = azurerm_resource_group.fx_new_02_i_x_rg.name
  location              = azurerm_resource_group.fx_new_02_i_x_rg.location
  size                  = "Standard_B1ls"
  admin_username        = "boadmin"
  network_interface_ids = concat([azurerm_network_interface.fx_new_02_i_nic1.id], var.fx_new_02_i_extra_nic_ids)
  admin_ssh_key {
    username   = "boadmin"
    public_key = var.admin_ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

# ==== FX-NEW-03-C (CQ-NEW-03, conforming)

resource "azurerm_resource_group" "fx_new_03_c_x_rg" {
  name     = "${var.run_id}-fx-new-03-c-x-rg"
  location = var.location_1
}

resource "azurerm_network_security_group" "fx_new_03_c_rs1" {
  name                = "${var.run_id}-fx-new-03-c-rs1"
  resource_group_name = azurerm_resource_group.fx_new_03_c_x_rg.name
  location            = azurerm_resource_group.fx_new_03_c_x_rg.location
}

resource "azurerm_network_security_rule" "fx_new_03_c_r1" {
  name                        = "${var.run_id}-fx-new-03-c-r1"
  resource_group_name         = azurerm_resource_group.fx_new_03_c_x_rg.name
  network_security_group_name = azurerm_network_security_group.fx_new_03_c_rs1.name
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = "0.0.0.0/0"
  destination_address_prefix  = "*"
}

# ==== FX-NEW-03-N (CQ-NEW-03, nonconforming): NOT_APPLICABLE — no Azure toda regra de filtragem tem precedência numérica obrigatória: não há mecanismo de primeira correspondência por posição textual

# ==== FX-NEW-03-I (CQ-NEW-03, incomplete)

resource "azurerm_resource_group" "fx_new_03_i_x_rg" {
  name     = "${var.run_id}-fx-new-03-i-x-rg"
  location = var.location_1
}

resource "azurerm_network_manager" "fx_new_03_i_x_nm" {
  name                = "${var.run_id}-fx-new-03-i-nm"
  resource_group_name = azurerm_resource_group.fx_new_03_i_x_rg.name
  location            = azurerm_resource_group.fx_new_03_i_x_rg.location
  scope_accesses      = ["SecurityAdmin"]
  scope {
    subscription_ids = ["/subscriptions/${var.subscription_id}"]
  }
}

resource "azurerm_network_manager_network_group" "fx_new_03_i_x_ng" {
  name               = "${var.run_id}-fx-new-03-i-ng"
  network_manager_id = azurerm_network_manager.fx_new_03_i_x_nm.id
}

resource "azurerm_network_manager_security_admin_configuration" "fx_new_03_i_x_cfg" {
  name               = "${var.run_id}-fx-new-03-i-cfg"
  network_manager_id = azurerm_network_manager.fx_new_03_i_x_nm.id
}

resource "azurerm_network_manager_admin_rule_collection" "fx_new_03_i_rs1" {
  name                            = "${var.run_id}-fx-new-03-i-rs1"
  security_admin_configuration_id = azurerm_network_manager_security_admin_configuration.fx_new_03_i_x_cfg.id
  network_group_ids               = [azurerm_network_manager_network_group.fx_new_03_i_x_ng.id]
}

resource "azurerm_network_manager_admin_rule" "fx_new_03_i_r1" {
  name                     = "${var.run_id}-fx-new-03-i-r1"
  admin_rule_collection_id = azurerm_network_manager_admin_rule_collection.fx_new_03_i_rs1.id
  action                   = "Deny"
  direction                = "Inbound"
  priority                 = 100
  protocol                 = "Tcp"
  destination_port_ranges  = ["22"]
  source {
    address_prefix_type = "IPPrefix"
    address_prefix      = "0.0.0.0/0"
  }
  destination {
    address_prefix_type = "IPPrefix"
    address_prefix      = "*"
  }
}
