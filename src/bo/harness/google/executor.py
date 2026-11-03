"""Executor do harness google: apply -> espera -> leitura -> destroy, com as travas do S16 na ordem certa.

Ordem por caso (cada passo só roda se o anterior passou):
  1. diretório exclusivo em $BO_TMP/runs/<run_id>/<case_id> (N8; nunca /tmp; nunca reaproveitado);
  2. render do plano (C26); reprovado -> desfecho UNKNOWN com o código (UNKNOWN_INPUT, ...), sem apply;
  3. guardas adiadas reavaliadas com o contexto de execução; não TRUE -> UNKNOWN, sem apply;
  4. ligação das variáveis: símbolo sem valor sintético declarado -> UNKNOWN (UNKNOWN_INPUT), sem apply;
     segredo gerado na hora, só em memória, registrado no canário do redator;
  5. identidade efetiva (identity_guard) -> se não casar, ABORTA o lote (IdentityRefused);
  6. intenção gravada ANTES do apply (intent); falhou a gravação -> aborta, sem apply;
  7. apply; falha -> classe de erro (_templates/api_errors.json) -> REJECTED_BY_API / INFRA_ERROR / UNKNOWN;
  8. espera e duas leituras (refresh-only + show) separadas pelo intervalo; leituras diferentes -> UNKNOWN;
  9. redator antes de qualquer gravação: só campos C12 saem da memória; state cru nunca vai para disco;
 10. destroy SEMPRE (finally), confirmação de ausência no state; resíduo vira ResidueError depois de gravar o
     que já foi decidido; nunca se escreve "zero recursos" sem a confirmação;
 11. canal efêmero (state, plugin cache, saída do terraform) apagado no fim.
Nesta fase só roda com RecordedRunner (respostas gravadas). TerraformRunner existe para os módulos de nuvem e
recusa apply/destroy sem CloudAuthorization (GO do lote, trava cloud-google e identidade conferida).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from bo.transforms import guards as G
from bo.transforms.markers import SYMBOLIC

from . import common as C
from . import readback as RB
from . import render as R
from .redact import GoogleRedactor, resources_by_address


class IdentityRefused(RuntimeError):
    pass


class IntentNotRecorded(RuntimeError):
    pass


class CloudForbidden(RuntimeError):
    pass


class ResidueError(RuntimeError):
    def __init__(self, addresses: list[str]):
        super().__init__(f"resíduo depois do destroy: {', '.join(addresses)}")
        self.addresses = addresses


@dataclass
class ApplyResult:
    ok: bool
    output: str = ""        # só em memória; nunca gravado (REDACT-LOG-01)


# ------------------------------------------------------------------------------------------------ runners
class Runner:
    """Interface do runner. state = dict do 'terraform show -json' (com segredos em claro: só em memória)."""

    def init(self, workdir: Path, ephemeral: Path) -> ApplyResult: ...
    def apply(self, workdir: Path, ephemeral: Path, env: dict) -> ApplyResult: ...
    def refresh_show(self, workdir: Path, ephemeral: Path, env: dict) -> dict: ...
    def destroy(self, workdir: Path, ephemeral: Path, env: dict) -> ApplyResult: ...


class RecordedRunner(Runner):
    """Respostas gravadas (offline). gravação = {apply: {ok, output?}, reads: [state, ...], destroy: {ok},
    after_destroy: state}. Guarda a sequência de chamadas para os testes conferirem a ordem."""

    def __init__(self, recording: dict):
        self.rec = recording
        self.calls: list[str] = []
        self._reads = list(recording.get("reads", []))
        self.destroyed = False
        self.env_seen: dict = {}

    def init(self, workdir, ephemeral):
        self.calls.append("init")
        return ApplyResult(True)

    def apply(self, workdir, ephemeral, env):
        self.calls.append("apply")
        self.env_seen = dict(env)
        a = self.rec.get("apply", {"ok": True})
        return ApplyResult(a["ok"], a.get("output", ""))

    def refresh_show(self, workdir, ephemeral, env):
        """Como o terraform real, o state devolve os segredos EM CLARO: '<TF_VAR:nome>' vira o valor ligado."""
        self.calls.append("read")
        if self.destroyed:
            st = self.rec.get("after_destroy", {"values": {"root_module": {"resources": []}}})
        else:
            st = self._reads.pop(0) if len(self._reads) > 1 else (self._reads[0] if self._reads else {})
        return _fill(json.loads(json.dumps(st)), env)

    def destroy(self, workdir, ephemeral, env):
        self.calls.append("destroy")
        d = self.rec.get("destroy", {"ok": True})
        self.destroyed = True           # depois do destroy (com ou sem erro) a leitura é a gravada para depois
        return ApplyResult(d["ok"], d.get("output", ""))


def _fill(v, env: dict):
    if isinstance(v, str):
        m = re.fullmatch(r"<TF_VAR:([a-z0-9_]+)>", v)
        return env.get("TF_VAR_" + m.group(1), v) if m else v
    if isinstance(v, list):
        return [_fill(x, env) for x in v]
    if isinstance(v, dict):
        return {k: _fill(x, env) for k, x in v.items()}
    return v


@dataclass(frozen=True)
class CloudAuthorization:
    """Prova de que o lote pode tocar a nuvem: GO do Breno (D9), trava cloud-google e identidade conferida."""
    run_id: str
    go_token: str
    lock_dir: Path
    identity_checked: bool


class TerraformRunner(Runner):
    """Runner real (para SMOKE/DEP). Sem CloudAuthorization válida, apply e destroy recusam (CloudForbidden).

    Ambiente mínimo (env -i): PATH do Terraform fixado, HOME e TF_DATA_DIR no canal efêmero, variáveis TF_VAR_*
    só em memória; saída capturada e nunca gravada.
    """

    def __init__(self, terraform: str = "terraform", authorization: CloudAuthorization | None = None,
                 timeout: int = 1800):
        self.tf, self.auth, self.timeout = terraform, authorization, timeout

    def _authorized(self) -> None:
        a = self.auth
        ok = (a is not None and a.identity_checked and a.go_token and os.environ.get("BO_CLOUD_GO") == a.go_token
              and (a.lock_dir / "owner").exists() and a.lock_dir.name == "cloud-google")
        if not ok:
            raise CloudForbidden("nuvem proibida: falta GO do lote, trava cloud-google ou identidade conferida")

    def _run(self, args, workdir, ephemeral, env) -> ApplyResult:
        base = {"PATH": os.path.dirname(shutil.which(self.tf) or self.tf) + ":/usr/bin:/bin",
                "HOME": str(ephemeral), "TF_DATA_DIR": str(ephemeral / ".terraform"),
                "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"}
        p = subprocess.run([self.tf, f"-chdir={workdir}"] + args, env={**base, **env}, capture_output=True,
                           text=True, timeout=self.timeout)
        return ApplyResult(p.returncode == 0, p.stdout + p.stderr)

    def init(self, workdir, ephemeral):
        return self._run(["init", "-input=false", "-no-color", "-backend=false"], workdir, ephemeral, {})

    def apply(self, workdir, ephemeral, env):
        self._authorized()
        return self._run(["apply", "-input=false", "-no-color", "-auto-approve",
                          f"-state={ephemeral / 'terraform.tfstate'}"], workdir, ephemeral, env)

    def refresh_show(self, workdir, ephemeral, env):
        self._authorized()
        st = ephemeral / "terraform.tfstate"
        r = self._run(["apply", "-refresh-only", "-auto-approve", "-input=false", "-no-color", f"-state={st}"],
                      workdir, ephemeral, env)
        if not r.ok:
            raise RuntimeError("refresh-only falhou")
        p = subprocess.run([self.tf, f"-chdir={workdir}", "show", "-json", str(st)], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin", "HOME": str(ephemeral)}, timeout=self.timeout)
        return json.loads(p.stdout or "{}")

    def destroy(self, workdir, ephemeral, env):
        self._authorized()
        return self._run(["destroy", "-input=false", "-no-color", "-auto-approve",
                          f"-state={ephemeral / 'terraform.tfstate'}"], workdir, ephemeral, env)


# ------------------------------------------------------------------------------------------------ apoio
class Ephemeral:
    """Canal privado efêmero do state. Aqui é diretório 0700 em $BO_TMP (sem cifra, sem RAM): o executor só o
    aceita com allow_disk=True, que é o modo offline; o disco de RAM cifrado é do SAFETY."""

    def __init__(self, root: Path, encrypted_ram: bool = False):
        self.root, self.encrypted_ram = root, encrypted_ram

    def open(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=False)
        os.chmod(self.root, 0o700)
        return self.root

    def wipe(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)


def classify_error(output: str) -> tuple[str, str, str]:
    """(class_id, desfecho, detalhe) pela primeira classe de _templates/api_errors.json que casa; senão UNKNOWN."""
    spec = json.loads((C.templates() / "api_errors.json").read_text(encoding="utf-8"))
    for c in spec["classes"]:
        if any(re.search(p, output) for p in c["patterns"]):
            return c["class_id"], c["outcome"], c["detail"]
    return "UNCLASSIFIED", "UNKNOWN", "falha sem classe conhecida; não se adivinha o desfecho"


@dataclass
class CaseRun:
    case_id: str
    outcome: dict
    readback: dict | None = None
    events: list = field(default_factory=list)
    residue: list = field(default_factory=list)
    render_status: str = ""


class Executor:
    def __init__(self, runner: Runner, *, identity_guard, intent, run_id: str, schema=None, redactor=None,
                 sleep=time.sleep, wait_s: float = 30.0, read_interval_s: float = 15.0,
                 allow_disk_ephemeral: bool = False, heartbeat=None):
        if not re.match(r"^[a-z0-9][a-z0-9-]{2,40}$", run_id):
            raise ValueError("run_id: minúsculas, dígitos e '-', 3 a 41 caracteres")
        self.runner, self.identity_guard, self.intent, self.run_id = runner, identity_guard, intent, run_id
        self.schema = schema or R.Schema.load()
        self.redactor = redactor or GoogleRedactor(self.schema)
        self.sleep, self.wait_s, self.read_interval_s = sleep, wait_s, read_interval_s
        self.allow_disk_ephemeral, self.heartbeat = allow_disk_ephemeral, heartbeat or (lambda step: None)
        self.root = C.tmp() / "runs" / run_id
        self.n_out = 0

    # --- gravação: só depois do redator, só registros C12 e eventos sem conteúdo
    def _ev(self, run: CaseRun, step: str, **kw):
        ev = {"at": C.now(), "case_id": run.case_id, "step": step, **kw}
        self.redactor.assert_clean(ev)
        run.events.append(ev)
        self.heartbeat(step)

    def _outcome(self, case, value, detail, before, rb_id=None):
        self.n_out += 1
        return RB.outcome_record(case, value, detail, f"OUT-{self.run_id}-{self.n_out:04d}", before, rb_id)

    def run_case(self, case: dict, plan: dict, graph: dict, *, bindings: dict, runtime_context: dict,
                 evidence_before: str = "DOC_SUPPORTED") -> CaseRun:
        run = CaseRun(case["case_id"], {})
        wd = self.root / case["case_id"]
        wd.mkdir(parents=True, exist_ok=False)
        rendered = R.render_plan(plan, graph, self.schema, case["side"] if case["side"] != "both" else "object")
        run.render_status = rendered.status
        self._ev(run, "render", status=rendered.status, codes=[f["code"] for f in rendered.failures])
        if rendered.status != R.RENDERED:
            codes = ", ".join(sorted({f["code"] for f in rendered.failures}))
            run.outcome = self._outcome(case, "UNKNOWN", f"{rendered.status}: {codes}; sem apply", evidence_before)
            return run
        for dg in rendered.deferred_guards:
            ctx = {}
            for k, v in runtime_context.items():
                ctx[f"{case['side'] if case['side'] != 'both' else 'object'}.{k}"] = v if v is not None else SYMBOLIC
            verdict, terms = G.evaluate(dg["guard"], ctx)
            if verdict != G.TRUE:
                self._ev(run, "guard", verdict=verdict)
                run.outcome = self._outcome(case, "UNKNOWN", f"guarda adiada {dg['what']} = {verdict} no contexto "
                                            "de execução; sem apply", evidence_before)
                return run
        env, missing = {}, []
        for v in rendered.variables:
            if v["kind"] == "symbolic_input":
                val = bindings.get(v["symbol_id"])
                if not isinstance(val, str) or not re.match(r"^[a-z][a-z0-9-]{0,40}$", val):
                    missing.append(v["symbol_id"])
                    continue
                env["TF_VAR_" + v["name"]] = val
            else:
                sec = secrets.token_urlsafe(24)
                self.redactor.register_secret(sec)
                env["TF_VAR_" + v["name"]] = sec
        if missing:
            self._ev(run, "bind", missing=len(missing))
            run.outcome = self._outcome(case, "UNKNOWN", "UNKNOWN_INPUT: símbolo sem valor sintético declarado: "
                                        + ", ".join(missing), evidence_before)
            return run
        (wd / "versions.tf").write_text(R.versions_tf(self.schema), encoding="utf-8")
        (wd / R.file_name(plan["plan_id"])).write_text(rendered.hcl, encoding="utf-8")
        if self.identity_guard() is not True:
            self._ev(run, "identity", ok=False)
            raise IdentityRefused("identidade efetiva fora da allowlist; lote abortado antes do apply")
        self._ev(run, "identity", ok=True)
        eph = Ephemeral(C.tmp() / "ephemeral" / self.run_id / case["case_id"])
        if not eph.encrypted_ram and not self.allow_disk_ephemeral:
            raise CloudForbidden("canal efêmero sem cifra/RAM só no modo offline (allow_disk_ephemeral)")
        addresses = sorted(rendered.addresses.values())
        try:
            ok = self.intent("intent", self.run_id, case["case_id"], addresses)
        except Exception as e:  # noqa: BLE001 - qualquer falha da intenção impede o apply
            raise IntentNotRecorded(f"intenção não gravada ({type(e).__name__}); sem apply") from e
        if ok is not True:
            raise IntentNotRecorded("intenção não gravada; sem apply")
        self._ev(run, "intent", resources=len(addresses))
        ep = eph.open()
        try:
            self.runner.init(wd, ep)
            res = self.runner.apply(wd, ep, env)
            self.intent("created" if res.ok else "apply_failed", self.run_id, case["case_id"], addresses)
            if not res.ok:
                cid, value, detail = classify_error(res.output)
                self._ev(run, "apply", ok=False, error_class=cid)
                run.outcome = self._outcome(case, value, f"{cid}: {detail}", evidence_before)
                return run
            self._ev(run, "apply", ok=True)
            self.sleep(self.wait_s)
            first = self.runner.refresh_show(wd, ep, env)
            self.sleep(self.read_interval_s)
            second = self.runner.refresh_show(wd, ep, env)
            leaves = RB.plan_leaves(plan, graph, self.schema)
            rb1 = RB.build_readback(case, leaves, resources_by_address(first), self.redactor, "RB-tmp")
            rb_id = f"RB-{self.run_id}-{case['case_id'].removeprefix('CASE-')}"
            rb = RB.build_readback(case, leaves, resources_by_address(second), self.redactor, rb_id)
            res2 = resources_by_address(second)
            del first, second
            self._ev(run, "read", fields=len(rb["fields"]))
            if [f.get("value") for f in rb1["fields"]] != [f.get("value") for f in rb["fields"]]:
                run.readback = rb
                run.outcome = self._outcome(case, "UNKNOWN", "leituras sucessivas diferentes (consistência "
                                            "eventual); sem decisão", evidence_before, rb_id)
                return run
            value, detail = RB.decide(case, leaves, rb, res2)
            del res2
            run.readback = rb
            run.outcome = self._outcome(case, value, detail, evidence_before, rb_id)
            return run
        finally:
            self._teardown(run, wd, ep, env, addresses)
            eph.wipe()

    def _teardown(self, run, wd, ep, env, addresses):
        self.intent("removal_requested", self.run_id, run.case_id, addresses)
        d = self.runner.destroy(wd, ep, env)
        after = resources_by_address(self.runner.refresh_show(wd, ep, env))
        left = sorted(a for a in addresses if a in after and not a.startswith("data."))
        run.residue = left if (left or d.ok) else addresses
        if run.residue:
            self.intent("residue", self.run_id, run.case_id, run.residue)
            self._ev(run, "destroy", ok=False, residue=len(run.residue))
        else:
            self.intent("verified_absent", self.run_id, run.case_id, addresses)
            self._ev(run, "destroy", ok=True)

    # --- saída (C12), validada pelo validador único
    def write(self, runs: list[CaseRun], out_dir: Path) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        rbs = [r.readback for r in runs if r.readback is not None]
        outs = [r.outcome for r in runs]
        for obj in rbs + outs:
            self.redactor.assert_clean(obj)
        paths = {}
        if rbs:
            C.write_jsonl(out_dir / "readback.jsonl", rbs)
            paths["readback"] = out_dir / "readback.jsonl"
        C.write_jsonl(out_dir / "outcomes.jsonl", outs)
        paths["outcomes"] = out_dir / "outcomes.jsonl"
        C.write_jsonl(out_dir / "run_events.jsonl", [e for r in runs for e in r.events])
        errs = []
        for p in paths.values():
            errs += C.validate("C12", p)
        if errs:
            for p in paths.values():
                p.unlink()
            raise ValueError("saída C12 inválida, apagada: " + "; ".join(errs[:3]))
        residue = [a for r in runs for a in r.residue]
        if residue:
            raise ResidueError(residue)
        return {k: str(v) for k, v in paths.items()}
