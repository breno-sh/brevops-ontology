"""Backends do executor: respostas gravadas (offline) e a CLI do Terraform (bloqueada sem GO e identidade).

Interface comum (todas as saídas ficam em memória; nada aqui grava em disco persistente):
  init(work)                         -> Step
  apply(work, tfvars)                -> Step   (diagnósticos do 'terraform apply -json')
  read(work, tfvars)                 -> dict   (state lido de volta: refresh pela API + 'terraform show -json')
  destroy(work, tfvars)              -> Step
  state_list(work)                   -> list[str]

RecordedBackend reproduz uma gravação JSON (tests/harness/aws/fixtures/recorded/*.json) e registra as chamadas.
TerraformCLIBackend chama o binário com env -i: só PATH mínimo, HOME efêmero, TF_VAR_* da execução e as
credenciais que o kit de segurança entregar. Recusa começar sem um GoToken válido: GO explícito do Breno para o
run_id (variável BO_CLOUD_GO igual ao run_id) e identidade efetiva conferida pelo kit contra a allowlist.
Nesta fase (F1) só roda contra um 'terraform' falso dos testes; nenhuma credencial existe no ambiente.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import pins


@dataclass
class Step:
    ok: bool
    diagnostics: list = field(default_factory=list)   # [{severity, summary, detail}]


class Backend:
    name = "abstract"

    def init(self, work: Path) -> Step:
        raise NotImplementedError

    def apply(self, work: Path, tfvars: dict) -> Step:
        raise NotImplementedError

    def read(self, work: Path, tfvars: dict) -> dict:
        raise NotImplementedError

    def destroy(self, work: Path, tfvars: dict) -> Step:
        raise NotImplementedError

    def state_list(self, work: Path) -> list[str]:
        raise NotImplementedError


# ------------------------------------------------------------------------------------------ gravado
class RecordedBackend(Backend):
    """Gravação: {"init": Step, "apply": Step, "reads": [show_json, ...], "destroy": Step,
    "state_list_after_destroy": [...]}. reads é consumido em ordem (a espera vê a consistência eventual);
    depois do último, repete o último."""

    name = "recorded"

    def __init__(self, recording: dict):
        self.rec = recording
        self.calls: list[str] = []
        self.tfvars_seen: list[set] = []
        self._reads = 0
        self._destroyed = False

    @classmethod
    def from_file(cls, p: Path) -> "RecordedBackend":
        return cls(json.loads(Path(p).read_text(encoding="utf-8")))

    def _step(self, k: str) -> Step:
        d = self.rec.get(k) or {"ok": True}
        return Step(bool(d.get("ok", True)), list(d.get("diagnostics") or []))

    def init(self, work):
        self.calls.append("init")
        return self._step("init")

    def apply(self, work, tfvars):
        self.calls.append("apply")
        self.tfvars_seen.append(set(tfvars))
        return self._step("apply")

    def read(self, work, tfvars):
        self.calls.append("read")
        reads = self.rec.get("reads") or [{}]
        r = reads[min(self._reads, len(reads) - 1)]
        self._reads += 1
        return r

    def destroy(self, work, tfvars):
        self.calls.append("destroy")
        self._destroyed = True
        return self._step("destroy")

    def state_list(self, work):
        self.calls.append("state_list")
        return list(self.rec.get("state_list_after_destroy" if self._destroyed else "state_list", []))


# ------------------------------------------------------------------------------------------ CLI real
class GoRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class GoToken:
    run_id: str
    identity_matched: bool

    def check(self):
        if os.environ.get("BO_CLOUD_GO") != self.run_id:
            raise GoRefused(f"sem GO explícito para {self.run_id} (BO_CLOUD_GO diferente do run_id)")
        if not self.identity_matched:
            raise GoRefused("identidade efetiva não conferiu com a allowlist privada")


class TerraformCLIBackend(Backend):
    name = "terraform-cli"

    def __init__(self, terraform: str, go: GoToken, credential_env: dict | None = None, timeout: int = 3600,
                 plugin_dir: str | None = None):
        go.check()
        self.tf = str(terraform)
        self.go = go
        self.cred = dict(credential_env or {})
        self.timeout = timeout
        self.plugin_dir = plugin_dir

    def _env(self, work: Path, tfvars: dict) -> dict:
        home = work / ".home"
        home.mkdir(exist_ok=True)
        (home / ".terraformrc").write_text("", encoding="utf-8")
        env = {"PATH": f"{Path(self.tf).parent}:/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(pins.socket_dir()),
               "TF_IN_AUTOMATION": "1", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1",
               "TF_CLI_CONFIG_FILE": str(home / ".terraformrc")}
        env.update(self.cred)
        env.update({f"TF_VAR_{k}": v if isinstance(v, str) else json.dumps(v) for k, v in tfvars.items()})
        return env

    def _run(self, args, work, tfvars):
        self.go.check()
        r = subprocess.run([self.tf] + args, cwd=work, env=self._env(work, tfvars), capture_output=True,
                           text=True, timeout=self.timeout)
        return r

    @staticmethod
    def _diags(stdout: str) -> list:
        out = []
        for line in stdout.splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "diagnostic":
                g = d.get("diagnostic") or {}
                out.append({"severity": g.get("severity", ""), "summary": g.get("summary", ""),
                            "detail": g.get("detail", "")})
        return out

    def init(self, work):
        args = ["init", "-input=false", "-no-color"]
        if self.plugin_dir:
            args.append(f"-plugin-dir={self.plugin_dir}")
        r = self._run(args, work, {})
        return Step(r.returncode == 0, [] if r.returncode == 0 else
                    [{"severity": "error", "summary": "init falhou", "detail": (r.stderr or r.stdout)[-400:]}])

    def apply(self, work, tfvars):
        r = self._run(["apply", "-auto-approve", "-input=false", "-no-color", "-json"], work, tfvars)
        return Step(r.returncode == 0, self._diags(r.stdout))

    def read(self, work, tfvars):
        r = self._run(["apply", "-refresh-only", "-auto-approve", "-input=false", "-no-color", "-json"], work, tfvars)
        if r.returncode != 0:
            return {"$error": self._diags(r.stdout) or [{"severity": "error", "summary": "refresh falhou",
                                                         "detail": r.stderr[-300:]}]}
        s = self._run(["show", "-json", "-no-color"], work, tfvars)
        try:
            return json.loads(s.stdout)
        except json.JSONDecodeError:
            return {"$error": [{"severity": "error", "summary": "show sem JSON", "detail": s.stderr[-300:]}]}

    def destroy(self, work, tfvars):
        r = self._run(["destroy", "-auto-approve", "-input=false", "-no-color", "-json"], work, tfvars)
        return Step(r.returncode == 0, self._diags(r.stdout))

    def state_list(self, work):
        r = self._run(["state", "list", "-no-color"], work, {})
        return [x for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else ["$erro:state-list"]
