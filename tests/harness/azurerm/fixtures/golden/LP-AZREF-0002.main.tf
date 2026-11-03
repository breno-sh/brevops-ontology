variable "secret_r2_administrator_password" {
  type      = string
  sensitive = true
}

variable "sym_a1b2c3d4e5f60718" {
  type = string
}

resource "azurerm_resource_group" "r1" {
  location = "brazilsouth"
  name     = "bo-${var.sym_a1b2c3d4e5f60718}-rg"
}

resource "azurerm_postgresql_flexible_server" "r2" {
  administrator_login    = "boadmin"
  administrator_password = var.secret_r2_administrator_password
  backup_retention_days  = 7
  location               = azurerm_resource_group.r1.location
  name                   = "bo-${var.sym_a1b2c3d4e5f60718}-pg"
  resource_group_name    = azurerm_resource_group.r1.name
  sku_name               = "B_Standard_B1ms"
  version                = "16"

  depends_on = [azurerm_resource_group.r1]
}

data "azurerm_client_config" "r3" {}

resource "azurerm_key_vault" "r4" {
  location                   = azurerm_resource_group.r1.location
  name                       = "bo-${var.sym_a1b2c3d4e5f60718}-kv"
  purge_protection_enabled   = false
  rbac_authorization_enabled = true
  resource_group_name        = azurerm_resource_group.r1.name
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  tenant_id                  = data.azurerm_client_config.r3.tenant_id

  depends_on = [azurerm_resource_group.r1, data.azurerm_client_config.r3]
}
