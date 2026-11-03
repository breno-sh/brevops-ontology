# Inserção declarada do harness (HI-06): entradas da execução, sem default.
variable "bo_region" {
  type     = string
  nullable = false
}

variable "bo_run_id" {
  type     = string
  nullable = false
}

variable "bo_case_id" {
  type     = string
  nullable = false
}

variable "bo_allowed_account_ids" {
  type      = list(string)
  nullable  = false
  sensitive = true
}
