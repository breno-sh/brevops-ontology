# Lado caso: política de TTL no campo bo_expire_at da coleção bo-probe (documentos expiram 1 h depois).
locals {
  bo_side       = "case"
  bo_ttl_fields = 1
}
