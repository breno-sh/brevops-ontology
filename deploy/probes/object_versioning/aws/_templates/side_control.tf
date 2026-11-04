# Lado controle negativo: sem aws_s3_bucket_versioning (bucket novo nasce sem versionamento).
locals {
  bo_side                 = "control"
  bo_versioning_resources = 0
}
