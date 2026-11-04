variable "sym_a1b2c3d4e5f60744" {
  type = string
}

resource "azurerm_resource_group" "r1" {
  location = "brazilsouth"
  name     = "bo-${var.sym_a1b2c3d4e5f60744}-rg"
}

resource "azurerm_network_security_group" "r2" {
  location            = azurerm_resource_group.r1.location
  name                = "bo-${var.sym_a1b2c3d4e5f60744}-nsg"
  resource_group_name = azurerm_resource_group.r1.name

  depends_on = [azurerm_resource_group.r1]
}

resource "azurerm_application_security_group" "r3" {
  location            = azurerm_resource_group.r1.location
  name                = "bo-${var.sym_a1b2c3d4e5f60744}-asg-web"
  resource_group_name = azurerm_resource_group.r1.name

  depends_on = [azurerm_resource_group.r1]
}

resource "azurerm_application_security_group" "r4" {
  location            = azurerm_resource_group.r1.location
  name                = "bo-${var.sym_a1b2c3d4e5f60744}-asg-db"
  resource_group_name = azurerm_resource_group.r1.name

  depends_on = [azurerm_resource_group.r1]
}

resource "azurerm_network_security_rule" "r5" {
  access                                     = "Allow"
  destination_application_security_group_ids = [azurerm_application_security_group.r4.id]
  destination_port_ranges                    = ["22", "443"]
  direction                                  = "Inbound"
  name                                       = "bo-${var.sym_a1b2c3d4e5f60744}-rule"
  network_security_group_name                = azurerm_network_security_group.r2.name
  priority                                   = 100
  protocol                                   = "Tcp"
  resource_group_name                        = azurerm_resource_group.r1.name
  source_application_security_group_ids      = [azurerm_application_security_group.r3.id, azurerm_application_security_group.r4.id]
  source_port_range                          = "*"

  depends_on = [azurerm_resource_group.r1, azurerm_network_security_group.r2, azurerm_application_security_group.r3, azurerm_application_security_group.r4]
}
