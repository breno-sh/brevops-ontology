# Inserções declaradas do harness (HI-03, HI-04, HI-05). Nenhum valor de execução tem default:
# região, execução, caso e contas permitidas chegam do executor (TF_VAR_*) e nunca são gravados.
provider "aws" {
  region              = var.bo_region
  allowed_account_ids = var.bo_allowed_account_ids
  default_tags {
    tags = {
      "bo-run"  = var.bo_run_id
      "bo-case" = var.bo_case_id
    }
  }
}
