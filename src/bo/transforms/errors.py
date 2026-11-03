"""Erros do registro fechado de transformações (C10).

Dois tempos distintos:
  - erro de VALOR (no transporte): o valor está fora do domínio da função parcial. O código é um block_code do C00
    (o mesmo que o C23 grava no traço): TRANSFORM_OUT_OF_DOMAIN, UNKNOWN_INPUT, UNKNOWN_SYMBOLIC_INPUT, NO_UNIT.
  - erro de DECLARAÇÃO (na checagem da cadeia, antes de rodar): parâmetros mal tipados, grandezas diferentes numa
    escalar, tolerância não declarada. Código DECLARATION_ERROR; nunca vira traço de transporte, reprova a alegação.
"""

from __future__ import annotations

# códigos de erro de valor: subconjunto do block_code do C00 (conferido em tests/transforms)
VALUE_ERROR_CODES = ("TRANSFORM_OUT_OF_DOMAIN", "UNKNOWN_INPUT", "UNKNOWN_SYMBOLIC_INPUT", "NO_UNIT")
DECLARATION_ERROR = "DECLARATION_ERROR"
ERROR_CODES = VALUE_ERROR_CODES + (DECLARATION_ERROR,)


class TransformError(ValueError):
    code = "TRANSFORM_OUT_OF_DOMAIN"

    def __init__(self, msg: str, code: str | None = None):
        super().__init__(msg)
        if code is not None:
            if code not in ERROR_CODES:
                raise ValueError(f"código de erro fora do registro: {code}")
            self.code = code

    def __str__(self) -> str:
        return f"{self.code}: {self.args[0]}"


class OutOfDomain(TransformError):
    """Valor fora do domínio da função parcial (TRANSFORM_OUT_OF_DOMAIN)."""
    code = "TRANSFORM_OUT_OF_DOMAIN"


class UnknownInput(TransformError):
    """Componente ausente ou valor não lido (UNKNOWN_INPUT)."""
    code = "UNKNOWN_INPUT"


class SymbolicInput(TransformError):
    """Valor simbólico ainda não resolvido, conhecido só depois da criação (UNKNOWN_SYMBOLIC_INPUT)."""
    code = "UNKNOWN_SYMBOLIC_INPUT"


class NoUnit(TransformError):
    """Unidade ausente, UNKNOWN ou fora do registro (NO_UNIT)."""
    code = "NO_UNIT"


class DeclarationError(TransformError):
    """Cadeia ou parâmetros mal declarados (DECLARATION_ERROR): reprova antes de transportar."""
    code = DECLARATION_ERROR
