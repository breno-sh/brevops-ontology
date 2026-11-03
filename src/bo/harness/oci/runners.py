"""Executores do Terraform para o ciclo apply -> espera -> leitura -> destroy.

RecordedRunner  respostas gravadas (offline). A gravação é presa ao HCL: o sha256 do main.tf do módulo renderizado
                tem de ser o da gravação, senão nada é reproduzido. Marcadores na gravação viram valores só em
                memória: '@CTX:<chave>' (contexto da execução, dado pelo kit) e '@OCID:<tipo>:<n>' (OCID sintético).
LiveRunner      terraform de verdade. Recusa ser criado sem um kit com live_authorized (o kit ao vivo vem do SAFETY
                e do GO do Breno; nesta fase não existe) e sem a trava cloud-oci. Nenhum teste o executa.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path

RECORDING_SCHEMA = "bo.harness.oci.recording/1"


@dataclass
class ApplyResult:
    ok: bool
    status: int | None = None       # status HTTP da API, quando houve erro de API
    code: str | None = None         # código de serviço da API (ex. InvalidParameter), nunca a mensagem
    phase: str = "apply"


@dataclass
class DestroyResult:
    ok: bool
    status: int | None = None
    code: str | None = None


class RecordingMismatch(RuntimeError):
    pass


def fake_ocid(rtype: str, n: int) -> str:
    """OCID sintético (só em memória; montado em partes para não existir literal no código)."""
    import hashlib
    kind = rtype.replace("oci_", "").split("_")[-1]
    tail = hashlib.sha256(f"{rtype}:{n}".encode()).hexdigest()[:20]
    return "oc" + "id1." + kind + ".oc1..aaaasyn" + tail


def _expand(obj, ctx: dict):
    if isinstance(obj, str):
        if obj.startswith("@CTX:"):
            key = obj[5:]
            if key not in ctx:
                raise RecordingMismatch(f"gravação pede o contexto {key}, que o kit não deu")
            return ctx[key]
        m = re.match(r"^@OCID:([a-z0-9_]+):(\d+)$", obj)
        if m:
            return fake_ocid(m.group(1), int(m.group(2)))
        if "@CTX:" in obj:
            def sub(mm):
                if mm.group(1) not in ctx:
                    raise RecordingMismatch(f"gravação pede o contexto {mm.group(1)}, que o kit não deu")
                return ctx[mm.group(1)]
            return re.sub(r"@CTX:([a-z_]+)", sub, obj)
        return obj
    if isinstance(obj, list):
        return [_expand(x, ctx) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand(v, ctx) for k, v in obj.items()}
    return obj


class RecordedRunner:
    """Reproduz uma gravação: apply, leituras sucessivas do state (para a espera), destroy e state list final."""
    recorded = True
    live = False

    def __init__(self, recording_path: Path):
        self.path = Path(recording_path)
        self.rec = json.loads(self.path.read_text(encoding="utf-8"))
        if self.rec.get("schema") != RECORDING_SCHEMA:
            raise RecordingMismatch(f"{self.path.name} não é {RECORDING_SCHEMA}")
        if self.rec.get("synthetic") is not True:
            raise RecordingMismatch(f"{self.path.name}: só gravações sintéticas marcadas são aceitas offline")
        self.ctx: dict = {}
        self._poll = 0
        self.calls: list[str] = []
        self._destroyed = False

    @property
    def identity(self) -> str:
        return self.rec["identity"]

    def bind(self, module_sha256: str, plan_id: str, ctx: dict) -> None:
        if self.rec["plan_id"] != plan_id:
            raise RecordingMismatch(f"gravação é do plano {self.rec['plan_id']}, não de {plan_id}")
        if self.rec["module_sha256"] != module_sha256:
            raise RecordingMismatch("o HCL renderizado difere do HCL da gravação (sha256 do módulo)")
        self.ctx = dict(ctx)

    def init(self, workdir: Path) -> None:
        self.calls.append("init")

    def apply(self, workdir: Path, var_values: dict) -> ApplyResult:
        self.calls.append("apply")
        missing = sorted(set(self.rec.get("expects_vars", [])) - set(var_values))
        if missing:
            raise RecordingMismatch(f"apply sem as variáveis {missing}")
        a = self.rec["apply"]
        return ApplyResult(a["ok"], a.get("status"), a.get("code"))

    def show_state(self, workdir: Path) -> dict:
        self.calls.append("show")
        polls = self.rec.get("polls") or []
        if not polls:
            return {"format_version": "1.0", "values": {"root_module": {}}}
        st = polls[min(self._poll, len(polls) - 1)]
        self._poll += 1
        return _expand(copy.deepcopy(st), self.ctx)

    def destroy(self, workdir: Path, var_values: dict) -> DestroyResult:
        self.calls.append("destroy")
        self._destroyed = True
        d = self.rec["destroy"]
        return DestroyResult(d["ok"], d.get("status"), d.get("code"))

    def state_list(self, workdir: Path) -> list[str]:
        self.calls.append("state_list")
        return list(self.rec.get("state_list_after_destroy", [])) if self._destroyed else ["(antes do destroy)"]


SERVICE_ERROR = re.compile(r"Service error:\s*([A-Za-z]+)\..*?http status code:\s*(\d{3})", re.S)


def parse_service_error(stderr: str) -> tuple[int | None, str | None]:
    """Extrai (status, código) do erro do provider oci; a mensagem (que pode citar OCIDs) é descartada."""
    m = SERVICE_ERROR.search(stderr or "")
    if not m:
        return None, None
    return int(m.group(2)), m.group(1)


class LiveRunner:
    """Terraform de verdade. Só com kit autorizado para nuvem (SAFETY + GO) e a trava cloud-oci; não usado offline."""
    recorded = False
    live = True

    def __init__(self, kit, lock_held: bool = False):
        if not getattr(kit, "live_authorized", False):
            raise PermissionError("LiveRunner recusado: kit sem autorização de nuvem (SAFETY e GO do Breno ausentes)")
        if not lock_held:
            raise PermissionError("LiveRunner recusado: trava cloud-oci não está com este processo")
        self.kit = kit

    def _tf(self, args, workdir: Path, var_values: dict):
        import subprocess
        env = self.kit.terraform_env(var_values)     # env efêmero do kit (credencial nunca passa por aqui em texto)
        state = self.kit.ephemeral_state_path(workdir)
        return subprocess.run(["terraform", *args, f"-state={state}"] if args[0] in ("apply", "destroy") else
                              ["terraform", *args], cwd=str(workdir), env=env, capture_output=True, text=True,
                              timeout=3600)

    def init(self, workdir: Path) -> None:
        p = self._tf(["init", "-input=false", "-no-color"], workdir, {})
        if p.returncode != 0:
            raise RuntimeError("terraform init falhou")

    def apply(self, workdir: Path, var_values: dict) -> ApplyResult:
        p = self._tf(["apply", "-auto-approve", "-input=false", "-no-color"], workdir, var_values)
        if p.returncode == 0:
            return ApplyResult(True)
        st, code = parse_service_error(p.stderr)
        return ApplyResult(False, st, code)

    def show_state(self, workdir: Path) -> dict:
        p = self._tf(["show", "-json", str(self.kit.ephemeral_state_path(workdir))], workdir, {})
        return json.loads(p.stdout)

    def destroy(self, workdir: Path, var_values: dict) -> DestroyResult:
        p = self._tf(["destroy", "-auto-approve", "-input=false", "-no-color"], workdir, var_values)
        if p.returncode == 0:
            return DestroyResult(True)
        st, code = parse_service_error(p.stderr)
        return DestroyResult(False, st, code)

    def state_list(self, workdir: Path) -> list[str]:
        p = self._tf(["state", "list", f"-state={self.kit.ephemeral_state_path(workdir)}"], workdir, {})
        return [x for x in p.stdout.splitlines() if x.strip()]


@dataclass
class ErrorClass:
    outcome: str
    detail: str


def classify_error(status: int | None, code: str | None, phase: str = "apply") -> ErrorClass:
    """Erro da API -> desfecho. A API recusou a configuração (4xx de validação) é REJECTED_BY_API; autorização,
    inexistência, conflito, cota, limite de taxa, 5xx e erro sem status são INFRA_ERROR."""
    tag = f"{phase}:{status if status is not None else 'sem-status'}:{code or 'sem-codigo'}"
    if status is None:
        return ErrorClass("INFRA_ERROR", f"erro sem status da API ({tag})")
    if status in (400, 422) and code not in ("LimitExceeded", "QuotaExceeded", "TooManyRequests"):
        return ErrorClass("REJECTED_BY_API", f"API recusou a configuração ({tag})")
    return ErrorClass("INFRA_ERROR", f"erro de infraestrutura ({tag})")
