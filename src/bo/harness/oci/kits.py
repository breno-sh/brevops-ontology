"""Kit de segurança visto pelo executor.

O executor só fala com o kit por esta interface: identidade antes do apply, intenção ANTES da criação e os eventos
seguintes (criação, confirmação, remoção), valores das variáveis só em memória e o redator antes de qualquer
gravação. O kit de nuvem de verdade é do SAFETY (deploy/safety/: redactor, identity_guard, intent_manifest) e entra
quando ele existir, com o GO do Breno. Nesta fase há só o OfflineKit, que serve exclusivamente às respostas gravadas:
recusa qualquer executor que não seja gravado, gera o contexto da execução sintético em memória e aplica o
redact.Redactor do harness.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from . import repo_root
from .redact import Redactor
from .runners import fake_ocid


class IdentityMismatch(RuntimeError):
    pass


class SafetyKitMissing(RuntimeError):
    pass


SAFETY_FILES = ("redactor.py", "identity_guard.py", "intent_manifest.py")


def safety_kit_present() -> bool:
    d = repo_root() / "deploy" / "safety"
    return all((d / f).exists() for f in SAFETY_FILES)


@dataclass
class OfflineKit:
    """Kit para respostas gravadas. live_authorized é sempre False."""
    run_tag: str = "bo-offline-run"
    events: list = field(default_factory=list)
    live_authorized: bool = False

    def __post_init__(self):
        self._ctx = {
            "compartment_id": fake_ocid("oci_identity_compartment", 1),
            "objectstorage_namespace": "bonsoffline" + secrets.token_hex(4),
            "availability_domain": "AD-SYN-1",
            "run_tag": self.run_tag,
            "region": "syn-region-1",
        }
        self._secrets: dict[str, str] = {}
        self.redactor = Redactor({k: v for k, v in self._ctx.items() if k != "region"}, [])

    # ------------------------------------------------------------------ identidade e contexto
    def check_identity(self, runner) -> None:
        if not getattr(runner, "recorded", False) or getattr(runner, "live", True):
            raise IdentityMismatch("OfflineKit só aceita executor gravado; nuvem exige o kit do SAFETY")
        if runner.identity != "sandbox-synthetic":
            raise IdentityMismatch("identidade da gravação não é a sandbox sintética esperada")
        self.events.append(("identity_ok", None))

    def context(self) -> dict:
        """Contexto privado da execução (só em memória; nunca gravado)."""
        return dict(self._ctx)

    def var_values(self, variables: list) -> dict:
        out = {"bo_region": self._ctx["region"]}
        for v in variables:
            if v.source.startswith("binding:"):
                key = v.source.split(":", 1)[1]
                out[v.name] = self._ctx[key]
            elif v.source.startswith("withheld:"):
                s = self._secrets.setdefault(v.name, "Syn" + secrets.token_urlsafe(18))
                out[v.name] = s
        self.redactor = Redactor({k: v for k, v in self._ctx.items() if k != "region"}, list(self._secrets.values()))
        return out

    # ------------------------------------------------------------------ manifesto de intenção (em memória)
    def record(self, event: str, case_id: str, detail=None) -> None:
        if event not in ("intent", "created", "confirmed", "removal_requested", "removed", "residue"):
            raise ValueError(f"evento de manifesto desconhecido: {event}")
        if event == "created" and not any(e[0] == "intent" and e[1] == case_id for e in self.events):
            raise RuntimeError("criação sem intenção gravada antes")
        self.events.append((event, case_id))

    # ------------------------------------------------------------------ redator
    def redact_records(self, records: list[dict], where: str) -> str:
        """Redator do kit antes da gravação: devolve o texto JSONL já conferido (ou levanta RedactionError)."""
        return self.redactor.guard_records(records, where)


def live_kit():
    """Kit de nuvem: exige o SAFETY. Nesta fase sempre recusa."""
    if not safety_kit_present():
        raise SafetyKitMissing("deploy/safety/ (SAFETY) ausente: sem redator, guarda de identidade e manifesto de "
                               "intenção de verdade, nada roda contra nuvem")
    raise SafetyKitMissing("integração com o SAFETY só no SMOKE-OCI, com o GO do Breno (nuvem proibida nesta fase)")
