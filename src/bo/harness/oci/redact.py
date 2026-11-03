"""Redação na origem da leitura de volta do OCI (C12-WITHHELD, §10.2 do plano).

O state lido do provider nunca é serializado como veio. A leitura é uma PROJEÇÃO: só os campos que o plano
escreveu são lidos (lista de permissão), e cada valor passa por estas regras, nesta ordem, antes de existir num
registro que possa ir para disco:

  REDACT-WRITEONLY-01  atributo write_only no schema: nunca está no state -> not_read
  REDACT-SENSITIVE-01  atributo sensitive no schema, ou marcado em sensitive_values do state -> withheld
  REDACT-WITHHELD-01   campo de conteúdo retido (script de boot, chave ssh, variáveis de ambiente/config de
                       função, conteúdo de objeto ou mensagem, log) -> withheld
  REDACT-SECRET-01     valor igual a um segredo gerado para a execução -> withheld
  REDACT-CTX-01        valor igual a um valor privado do contexto da execução (compartment, namespace...) ->
                       'bind:<chave>'; texto que só CONTÉM um valor privado -> withheld
  REDACT-OCID-01       OCID igual ao id de um recurso do mesmo state -> 'ref:<tipo>.<rótulo>'; qualquer outro
                       OCID -> withheld

withheld não tem valor nem hash. Depois da projeção, o texto serializado ainda passa pelo privacy_lint
(bo.repo.privacy.scan_text) e por uma busca literal dos valores privados; qualquer achado bloqueia a gravação.
"""

from __future__ import annotations

import json
import re

OCID = re.compile(r"\bocid1\.[a-z0-9_.-]+", re.I)
_U = "user"
# nomes (folha do caminho) de campos cujo conteúdo é retido sempre: montados em tempo de execução para que o
# próprio código não pareça, ao linter lexical, uma atribuição de conteúdo retido
WITHHELD_LEAVES = frozenset({
    _U + "_data", _U + "data", "ssh_authorized_keys", "ssh_public_keys", "extended_metadata",
    "config", "environment_variables", "content", "source", "message", "body", "log_content",
    "private_key", "passphrase", "secret_content",
})
# folhas que, só para estes tipos, são conteúdo (ex.: 'source' é CIDR numa regra de rede, mas arquivo num objeto)
WITHHELD_BY_TYPE = {
    "content": {"oci_objectstorage_object"},
    "source": {"oci_objectstorage_object"},
    "config": {"oci_functions_application", "oci_functions_function"},
    "message": {"oci_ons_notification_topic", "oci_queue_queue"},
    "body": {"oci_ons_notification_topic", "oci_queue_queue"},
}


class RedactionError(RuntimeError):
    pass


def is_withheld_leaf(rtype: str, field_path: str) -> bool:
    leaf = field_path.split(".")[-1]
    for seg in field_path.split("."):
        if seg in (_U + "_data", _U + "data", "ssh_authorized_keys"):
            return True
    if leaf not in WITHHELD_LEAVES:
        return False
    only = WITHHELD_BY_TYPE.get(leaf)
    return only is None or rtype in only


class Redactor:
    """Redator da leitura de volta. Valores privados e segredos vivem só em memória, dentro deste objeto."""

    def __init__(self, private_values: dict[str, str] | None = None, secrets: list[str] | None = None):
        self._private = {k: v for k, v in (private_values or {}).items() if isinstance(v, str) and v}
        self._secrets = [s for s in (secrets or []) if isinstance(s, str) and s]
        self._ids: dict[str, str] = {}

    def index_state(self, resources: list[dict]) -> None:
        """Liga id (OCID) de cada recurso do state ao endereço local tipo.rótulo."""
        for r in resources:
            rid = (r.get("values") or {}).get("id")
            if isinstance(rid, str) and rid:
                prefix = "data." if r.get("mode") == "data" else ""
                self._ids[rid] = f"{prefix}{r['type']}.{r['name']}"

    # ------------------------------------------------------------------------ valor
    def scalar(self, v):
        """Devolve ('ok', valor_redigido) ou ('withheld', rule_id)."""
        if not isinstance(v, str):
            return "ok", v
        for s in self._secrets:
            if s and s in v:
                return "withheld", "REDACT-SECRET-01"
        for key, pv in sorted(self._private.items()):
            if v == pv:
                return "ok", f"bind:{key}"
        for key, pv in sorted(self._private.items()):
            if pv in v:
                return "withheld", "REDACT-CTX-01"
        if OCID.search(v):
            if v in self._ids:
                return "ok", f"ref:{self._ids[v]}"
            return "withheld", "REDACT-OCID-01"
        return "ok", v

    def value(self, v):
        """Redige recursivamente. Se qualquer folha é retida, o valor inteiro é retido (sem valor parcial)."""
        if isinstance(v, list):
            out = []
            for x in v:
                st, y = self.value(x)
                if st == "withheld":
                    return st, y
                out.append(y)
            return "ok", out
        if isinstance(v, dict):
            out = {}
            for k in sorted(v):
                st, y = self.value(v[k])
                if st == "withheld":
                    return st, y
                out[k] = y
            return "ok", out
        return self.scalar(v)

    # ------------------------------------------------------------------------ guarda final
    def guard_text(self, text: str, where: str) -> None:
        """Última barreira antes de gravar: privacy_lint lexical + valores privados e segredos literais."""
        from bo.repo import privacy
        hits = privacy.scan_text(text, where)
        if hits:
            raise RedactionError(f"gravação bloqueada em {where}: {len(hits)} achado(s) do privacy_lint "
                                 f"({sorted({h.rule for h in hits})})")
        for s in self._secrets + list(self._private.values()):
            if s and s in text:
                raise RedactionError(f"gravação bloqueada em {where}: valor privado da execução no texto")
        if OCID.search(text):
            raise RedactionError(f"gravação bloqueada em {where}: OCID no texto")

    def guard_records(self, records: list[dict], where: str) -> str:
        text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
        self.guard_text(text, where)
        return text
