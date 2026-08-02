##
## Azure module — implemented in M5. See plan.md §C3.
## Resources to land in M5: Resource Group, PostgreSQL Flexible Server, Service Bus,
## Container Apps environment + apps, Blob Storage, Static Web Apps, Key Vault.
##

terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }
}

provider "azurerm" {
  features {}
}

resource "null_resource" "placeholder" {
  triggers = { stack = var.stack_name }
}
