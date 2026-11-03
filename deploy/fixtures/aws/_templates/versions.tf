# Inserção declarada do harness (HI-01, HI-02): versões fixadas em universe/pins.json (PINS).
terraform {
  required_version = "= 1.15.8"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.71.0"
    }
  }
}
