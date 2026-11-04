"""Supervisor independente com heartbeat (D16): roda FORA do Mac de trabalho (a VM Oracle do Breno).

O runner registra a execução, manda um heartbeat a cada heartbeat_interval_seconds (com as linhas novas do
manifesto privado) e fecha a execução quando o teardown dele termina. O supervisor, num tick periódico
(timer do systemd, 60 s), destrói os recursos da execução se:
  - o heartbeat parou por mais de grace_seconds (Mac dormiu, desligou, caiu a rede, runner morreu), ou
  - passou o prazo da execução (TTL do runner), mesmo com heartbeat chegando.
A destruição é a mesma do teardown: identidade conferida contra a allowlist da VM, trava cleanup-global da VM,
filtro de posse (tag da execução ou linha do manifesto recebido), ordem de dependência, estados de remoção.
O watchdog no terminal do Breno continua, mas não basta. Sem ack do supervisor, nenhuma janela longa (plan_check).

Comandos (pelo ssh com forced command; ver deploy/safety/supervisor/authorized_keys.example):
  register --run R --provider P --deadline ISO [--grace S]     stdin: {"files": {nome: [linhas]}}
  beat --run R --seq N                                          stdin: {"files": {nome: [linhas novas]}}
  close --run R
  status --run R
  tick                                                          (timer)
Resposta: JSON numa linha (ack com contagem de linhas por arquivo, para o runner mandar só o que falta).
Só biblioteca padrão.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

from . import locks
from .common import SafetyError, append_line, iso, now_dt, parse_iso, read_jsonl, write_json
from .manifest import BIND_FILE, INTENT_FILE, RUN_FILE, Manifest

FILES = (INTENT_FILE, RUN_FILE, BIND_FILE)
RUN_RX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
VERBS = {"register", "beat", "close", "status", "tick"}


class SupervisorError(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "SUPERVISOR")


def home() -> Path:
    return Path(os.environ.get("BO_SUPERVISOR_HOME") or (Path.home() / "bo-supervisor"))


class Supervisor:
    """adapter_factory(provider) -> adaptador (CliAdapter na VM; FakeCloud nos testes);
    identity_fn(provider) -> effective_identity_check; clock() -> datetime."""

    def __init__(self, root: Path | None = None, adapter_factory=None, identity_fn=None, clock=None,
                 order_fn=None, residue_fn=None, wait_fn=None, poll_s: float = 60.0):
        self.root = Path(root or home())
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.adapter_factory, self.identity_fn = adapter_factory, identity_fn
        self.clock = clock or now_dt
        self.order_fn, self.residue_fn, self.wait_fn, self.poll_s = order_fn, residue_fn, wait_fn, poll_s

    # --------------------------------------------------------------------------------------- estado
    def _dir(self, run: str) -> Path:
        if not RUN_RX.match(run or ""):
            raise SupervisorError("identificador de execução inválido")
        return self.root / "runs" / run

    def _meta(self, run: str) -> dict:
        p = self._dir(run) / "meta.json"
        if not p.exists():
            raise SupervisorError(f"execução {run} não registrada")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save(self, run: str, meta: dict):
        write_json(self._dir(run) / "meta.json", meta, 0o600)

    def _counts(self, run: str) -> dict:
        d = self._dir(run) / "private"
        return {f: len(read_jsonl(d / f)[0]) for f in FILES}

    def _ingest(self, run: str, payload: dict):
        d = self._dir(run) / "private"
        d.mkdir(parents=True, exist_ok=True)
        for name, lines in (payload.get("files") or {}).items():
            if name not in FILES:
                raise SupervisorError(f"arquivo de manifesto desconhecido: {name}")
            for ln in lines:
                json.loads(ln)  # só linha JSON completa entra
                append_line(d / name, ln, 0o600)

    def _ack(self, run: str, meta: dict) -> dict:
        return {"run": run, "status": meta["status"], "ack_at": iso(self.clock()), "seq": meta.get("seq", 0),
                "counts": self._counts(run), "deadline": meta["deadline"]}

    # --------------------------------------------------------------------------------------- comandos
    def register(self, run: str, provider: str, deadline: str, grace_s: int, payload: dict) -> dict:
        d = self._dir(run)
        if (d / "meta.json").exists():
            meta = self._meta(run)
            if meta["status"] not in ("watching",):
                raise SupervisorError(f"execução {run} já está {meta['status']}")
        parse_iso(deadline)
        if provider not in ("aws", "google", "azurerm", "oci"):
            raise SupervisorError("provedor inválido")
        d.mkdir(parents=True, exist_ok=True)
        now = self.clock()
        meta = {"run": run, "provider": provider, "deadline": deadline, "grace_s": int(grace_s),
                "registered_at": iso(now), "last_beat_at": iso(now), "seq": 0, "status": "watching", "events": []}
        self._ingest(run, payload)
        self._save(run, meta)
        return self._ack(run, meta)

    def beat(self, run: str, seq: int, payload: dict) -> dict:
        meta = self._meta(run)
        if meta["status"] != "watching":
            return {**self._ack(run, meta), "refused": f"execução {meta['status']}: pare de criar"}
        if seq <= meta["seq"]:
            return {**self._ack(run, meta), "ignored": "seq repetido ou fora de ordem"}
        self._ingest(run, payload)
        meta["seq"], meta["last_beat_at"] = seq, iso(self.clock())
        self._save(run, meta)
        return self._ack(run, meta)

    def close(self, run: str) -> dict:
        meta = self._meta(run)
        if meta["status"] == "watching":
            meta["status"] = "closed"
            meta["events"].append({"at": iso(self.clock()), "event": "fechado pelo runner"})
            self._save(run, meta)
        return self._ack(run, meta)

    def status(self, run: str) -> dict:
        return self._ack(run, self._meta(run))

    def tick(self) -> list[dict]:
        out = []
        base = self.root / "runs"
        for d in sorted(base.iterdir()) if base.exists() else []:
            meta = self._meta(d.name)
            if meta["status"] not in ("watching", "tearing_down"):
                continue
            now = self.clock()
            silent = (now - parse_iso(meta["last_beat_at"])).total_seconds()
            reason = None
            if meta["status"] == "tearing_down":
                reason = meta.get("reason", "retomada")
            elif silent > meta["grace_s"]:
                reason = f"heartbeat parado há {int(silent)} s (> {meta['grace_s']} s)"
            elif now > parse_iso(meta["deadline"]):
                reason = "prazo da execução (TTL do runner) vencido"
            if reason:
                out.append(self._destroy(d.name, meta, reason))
        return out

    # --------------------------------------------------------------------------------------- destruição
    def _destroy(self, run: str, meta: dict, reason: str) -> dict:
        from .ownership import cleanup, complete
        meta["status"], meta["reason"] = "tearing_down", reason
        meta["events"].append({"at": iso(self.clock()), "event": "destruição", "reason": reason})
        self._save(run, meta)
        d = self._dir(run)
        try:
            man = Manifest(f"SUP-{run.upper()}"[:60].rstrip("-"), d / "public", d / "private")
            binds, _ = read_jsonl(d / "private" / BIND_FILE)
            run_tag = (binds[0].get("run_tag") if binds else None) or run
            chk = self.identity_fn(meta["provider"])
            adapter = self.adapter_factory(meta["provider"])
            rep = cleanup(man, adapter, run_tag, chk, owner=f"supervisor-{run}", order_fn=self.order_fn,
                          lock_root=self.root / "locks", wait_lock_s=30, wait_fn=self.wait_fn, poll_s=self.poll_s)
            ok, why = complete(rep, man, self.residue_fn)
            meta["status"] = "done" if ok else "tearing_down"
            meta["result"] = {"complete": ok, "why": why, "intents": rep.intents, "foreign_untouched": rep.foreign,
                              "at": iso(self.clock())}
        except Exception as e:  # tenta de novo no próximo tick; nunca desiste calado
            meta["result"] = {"complete": False, "error": f"{type(e).__name__}: {str(e)[:200]}",
                              "at": iso(self.clock())}
        self._save(run, meta)
        return {"run": run, "reason": reason, **meta["result"]}


# --------------------------------------------------------------------------------------------- ssh
def parse_ssh_command(cmd: str) -> tuple[str, dict]:
    """Forced command: só os verbos e opções conhecidos, sem metacaractere de shell."""
    if re.search(r"[;&|`$<>\\\n]", cmd or ""):
        raise SupervisorError("comando com metacaractere recusado")
    parts = shlex.split(cmd or "")
    if not parts or parts[0] not in VERBS:
        raise SupervisorError("verbo desconhecido")
    verb, opts, i = parts[0], {}, 1
    allowed = {"--run", "--provider", "--deadline", "--grace", "--seq"}
    while i < len(parts):
        if parts[i] not in allowed or i + 1 >= len(parts):
            raise SupervisorError(f"opção recusada: {parts[i]}")
        opts[parts[i][2:]] = parts[i + 1]
        i += 2
    return verb, opts


def handle(sup: Supervisor, cmd: str, stdin_text: str) -> dict:
    verb, o = parse_ssh_command(cmd)
    payload = json.loads(stdin_text) if stdin_text.strip() else {}
    if verb == "register":
        return sup.register(o["run"], o["provider"], o["deadline"], int(o.get("grace", 600)), payload)
    if verb == "beat":
        return sup.beat(o["run"], int(o["seq"]), payload)
    if verb == "close":
        return sup.close(o["run"])
    if verb == "status":
        return sup.status(o["run"])
    return {"tick": sup.tick()}


# --------------------------------------------------------------------------------------------- cliente
class Client:
    """Lado do runner. transport(cmd, stdin) -> (rc, stdout). Em produção: ssh BatchMode para o host do
    supervisor lido do canal privado (~/.config/bo/supervisor), nunca do repositório."""

    def __init__(self, transport, man: Manifest, run: str):
        self.t, self.man, self.run, self.seq = transport, man, run, 0
        self.sent = {f: 0 for f in FILES}
        self.last_ack: dict | None = None

    def _delta(self, full=False) -> dict:
        files = {}
        for f in FILES:
            p = self.man.private / f
            lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()] if p.exists() else []
            start = 0 if full else self.sent[f]
            files[f] = lines[start:]
        return {"files": files}

    def _call(self, cmd: str, payload: dict) -> dict:
        rc, out = self.t(cmd, json.dumps(payload))
        if rc != 0:
            raise SupervisorError(f"supervisor não respondeu ({rc})")
        ack = json.loads(out.strip().splitlines()[-1])
        self.sent = dict(ack.get("counts", self.sent))
        self.last_ack = ack
        return ack

    def register(self, provider: str, deadline: str, grace_s: int) -> dict:
        return self._call(f"register --run {self.run} --provider {provider} --deadline {deadline} --grace {grace_s}",
                          self._delta(full=True))

    def beat(self) -> dict:
        self.seq += 1
        return self._call(f"beat --run {self.run} --seq {self.seq}", self._delta())

    def close(self) -> dict:
        self.beat()
        return self._call(f"close --run {self.run}", {})

    def plan_context(self) -> dict:
        """Campo 'supervisor' do contexto do plan_check (janela longa só com ack fresco)."""
        if not self.last_ack or self.last_ack.get("status") != "watching":
            return {}
        return {"last_ack_at": self.last_ack["ack_at"], "run_tag": self.run}


def ssh_transport(host: str, key: str | None = None):  # pragma: no cover - só com a VM (D16)
    import subprocess

    def t(cmd, stdin_text):
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"] + (["-i", key] if key else []) + [host, cmd]
        r = subprocess.run(argv, input=stdin_text, capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout
    return t


def main(argv=None) -> int:  # pragma: no cover - entrada da VM (bo_supervisor.py)
    argv = list(sys.argv[1:] if argv is None else argv)
    from . import identity, residue, skus
    from .providers import CliAdapter, subprocess_runner
    table = skus.load_table()
    res = residue.load()

    def order(t):
        for p in table["providers"].values():
            if t in p["types"]:
                return p["types"][t]["delete_order"]
        return 0
    sup = Supervisor(adapter_factory=lambda p: CliAdapter(p, subprocess_runner,
                                                          json.loads(os.environ.get("BO_SUPERVISOR_CTX", "{}"))),
                     identity_fn=lambda p: identity.check(p), order_fn=order,
                     residue_fn=lambda it: any(residue.owned_expected(res, p, it) for p in table["providers"]))
    cmd = os.environ.get("SSH_ORIGINAL_COMMAND") if argv[:1] == ["ssh-entry"] else " ".join(argv)
    try:
        out = handle(sup, cmd, sys.stdin.read() if cmd and not cmd.startswith(("tick", "status", "close")) else "")
    except (SafetyError, KeyError, ValueError) as e:
        print(json.dumps({"error": str(e)[:200]}))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0
