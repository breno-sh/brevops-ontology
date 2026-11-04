# Lado caso: TTL ligado no atributo bo_expire_at (itens expiram 1 h depois da gravação).
locals {
  bo_side           = "case"
  bo_ttl_attributes = ["bo_expire_at"]
}
