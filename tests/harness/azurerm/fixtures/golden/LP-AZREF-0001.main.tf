variable "sym_a1b2c3d4e5f60718" {
  type = string
}

resource "azurerm_resource_group" "r1" {
  location = "brazilsouth"
  name     = "bo-${var.sym_a1b2c3d4e5f60718}-rg"
}

resource "azurerm_storage_account" "r2" {
  account_replication_type = "LRS"
  account_tier             = "Standard"
  location                 = azurerm_resource_group.r1.location
  min_tls_version          = "TLS1_2"
  name                     = "bo${var.sym_a1b2c3d4e5f60718}st"
  resource_group_name      = azurerm_resource_group.r1.name

  tags = {
    env = "test"
  }

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 7
    }
  }

  depends_on = [azurerm_resource_group.r1]
}

resource "azurerm_virtual_network" "r3" {
  address_space       = ["10.20.0.0/16"]
  location            = azurerm_resource_group.r1.location
  name                = "bo-${var.sym_a1b2c3d4e5f60718}-vnet"
  resource_group_name = azurerm_resource_group.r1.name

  depends_on = [azurerm_resource_group.r1]
}

resource "azurerm_subnet" "r4" {
  address_prefixes     = ["10.20.1.0/24"]
  name                 = "bo-${var.sym_a1b2c3d4e5f60718}-snet"
  resource_group_name  = azurerm_resource_group.r1.name
  virtual_network_name = azurerm_virtual_network.r3.name

  depends_on = [azurerm_resource_group.r1, azurerm_virtual_network.r3]
}
