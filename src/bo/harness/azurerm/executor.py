"""Executor do harness azurerm: render -> entradas -> identidade -> intenção -> apply -> espera -> leitura
(redator antes de gravar) -> destroy -> conferência de resíduo. Nesta fase só roda com backend de respostas
GRAVADAS (ReplayBackend); o backend real (TerraformBackend) existe para os módulos de nuvem e recusa rodar
sem as travas de nuvem (GO do Breno, catálogo com needs_cloud, kit SAFETY, trava cloud-azure).

  python -I -m bo.harness.azurerm.executor --replay GRAVACAO.json --plan PLANO.jsonl --plan-id LP-x
         --cases CASOS.jsonl --out DIR [--run-id RUN-x] [--batch-id B-x] [--module ID] [--side object]

Ordem garantida (testada): intenção gravada antes do apply; redator antes de qualquer gravação de leitura;
destroy sempre que houve apply, inclusive quando o apply falha; state e segredos só no diretório efêmero do
kit, apagado no fim. Grava em DIR: intent_manifest.jsonl e run_manifest.jsonl (C16), readback.jsonl (C12),
outcomes.jsonl (C12, só desfecho de infraestrutura) e case_result.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets as _secrets
import shutil
import string
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import readback as RB
from . import redact as RD
from . import render as R
from . import schema as S
from ._common import MODULE, HarnessError, dumps, jsonl, now, portable, read_jsonl, tmp_dir

RECORDING_SCHEMA = "bo.harness_azurerm.recording/1"
RESULT_SCHEMA = "bo.harness_azurerm.case_result/1"

# classificação de falha do apply (só a CLASSE e o nome do padrão são gravados; o texto do erro, nunca)
INFRA_PATTERNS = [("quota", r"QuotaExceeded|exceeds? (the )?quota|OperationNotAllowed.*quota"),
                  ("sku_indisponivel", r"SkuNotAvailable|NotAvailableForSubscription|LocationNotAvailable"),
                  ("autorizacao", r"AuthorizationFailed|AuthenticationFailed|InvalidAuthenticationToken|403"),
                  ("registro_de_provedor", r"MissingSubscriptionRegistration|NoRegisteredProviderFound"),
                  ("limite_de_taxa", r"TooManyRequests|throttl|StatusCode=429"),
                  ("rede", r"context deadline exceeded|connection reset|i/o timeout|no such host|TLS handshake"),
                  ("politica", r"RequestDisallowedByPolicy")]
API_PATTERNS = [("api_400", r"StatusCode=400|Status=400|BadRequest|InvalidParameter|InvalidRequestContent|"
                            r"ValidationError|Code=\"Invalid|ResourceNameInvalid|AccountNameInvalid|Conflict"),
                ("validacao_do_provider", r"Error: expected |Error: invalid value|Error: Invalid value|"
                                          r"must be between|is not a valid|doesn't match")]


class CloudRefused(Exception):
    """O caminho de nuvem foi pedido sem as travas (nesta fase, sempre)."""


# ------------------------------------------------------------------------------------------------ kit de segurança
class OfflineKit:
    """Kit para respostas gravadas: identidade da gravação, efêmero em $BO_TMP, sem nuvem. Registra eventos."""

    def __init__(self, identity_sha256: str, matches_allowlist: bool = True, extra_redactors=None,
                 max_residual_usd: float = 0.0, purge_hours: int = 24):
        self.identity_sha256 = identity_sha256
        self.matches = matches_allowlist
        self.extra_redactors = list(extra_redactors or [])
        self.max_residual_usd = max_residual_usd
        self.purge_hours = purge_hours
        self.events: list[str] = []
        self.heartbeats: list[str] = []

    def identity(self) -> dict:
        self.events.append("identity_checked")
        return {"identity_sha256": self.identity_sha256, "checked_at": now(), "matches_allowlist": self.matches}

    def ephemeral_dir(self, run_id: str) -> Path:
        p = tmp_dir() / "ephemeral" / run_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def heartbeat(self, stage: str):
        self.heartbeats.append(stage)


def cloud_gate(module_id: str) -> None:
    """Condições do caminho de nuvem (§10.2). Nesta fase o catálogo não tem módulo de nuvem que use o harness
    sem SAFETY, e nenhum GO foi dado: a função sempre recusa aqui."""
    if os.environ.get("BO_CLOUD_GO") != "1":
        raise CloudRefused("sem GO do Breno para este lote (BO_CLOUD_GO != 1)")
    try:
        import bo.safety  # noqa: F401  (kit SAFETY: identidade, redator, intenção, supervisor)
    except ModuleNotFoundError:
        raise CloudRefused("kit SAFETY (bo.safety) não está mergeado") from None
    cat = os.environ.get("BO_MODULES")
    mods = {m["stable_id"]: m for m in json.load(open(cat))["modules"]} if cat else {}
    if not mods.get(module_id, {}).get("needs_cloud"):
        raise CloudRefused(f"{module_id} não é módulo de nuvem no catálogo")
    lock = Path(os.environ.get("BO_DATA", "")) / "locks" / "cloud-azure"
    if not lock.is_dir():
        raise CloudRefused("trava cloud-azure não está tomada")


# ------------------------------------------------------------------------------------------------ backends
class ReplayBackend:
    """Respostas gravadas de terraform apply/show/destroy. Marcadores trocados só em memória:
    "{{SUBSCRIPTION_PATH}}" vira /subscriptions/<guid aleatório>; "{{GUID:nome}}" vira um GUID aleatório (o mesmo
    nome, o mesmo GUID); "{{CONNSTR}}" vira uma connection string sintética com chave aleatória;
    "{{SECRET:var}}" e "{{VAR:var}}" viram o valor ligado à variável na execução."""

    def __init__(self, recording: dict):
        if recording.get("schema") != RECORDING_SCHEMA:
            raise HarnessError("gravação sem schema bo.harness_azurerm.recording/1")
        self.rec = recording
        self.calls: list[str] = []
        self._env: dict = {}
        self._polls = 0

    def _fill(self, obj):
        sub = "/subscriptions/" + str(uuid.uuid4())
        s = json.dumps(obj).replace("{{SUBSCRIPTION_PATH}}", sub)
        s = s.replace("{{CONNSTR}}", "DefaultEndpointsProtocol=https;AccountName=bo;Account" + "Key="
                      + _secrets.token_urlsafe(24))
        for g in set(re.findall(r"\{\{GUID:([a-z]+)\}\}", s)):
            s = s.replace("{{GUID:%s}}" % g, str(uuid.uuid4()))
        for kind, m in set(re.findall(r"\{\{(SECRET|VAR):([a-z0-9_]+)\}\}", s)):
            s = s.replace("{{%s:%s}}" % (kind, m), json.dumps(self._env.get("TF_VAR_" + m, ""))[1:-1])
        return json.loads(s)

    def apply(self, work: Path, env: dict):
        self.calls.append("apply")
        self._env = dict(env)
        a = self.rec["apply"]
        return a["rc"], a.get("stderr", "")

    def show(self, work: Path) -> dict:
        self.calls.append("show")
        polls = self.rec.get("show") or [{}]
        st = polls[min(self._polls, len(polls) - 1)]
        self._polls += 1
        return self._fill(st)

    def destroy(self, work: Path, env: dict):
        self.calls.append("destroy")
        d = self.rec.get("destroy") or {"rc": 0}
        return d["rc"], d.get("stderr", "")

    def state_list(self, work: Path) -> list[str]:
        self.calls.append("state_list")
        return list(self.rec.get("state_list_after_destroy", []))


class TerraformBackend:
    """Backend real (apply de verdade). Só instancia com cloud_gate() aprovado; nesta fase sempre recusa."""

    def __init__(self, module_id: str, timeout: int = 3600):
        cloud_gate(module_id)
        self.timeout = timeout
        self.calls: list[str] = []

    def _tf(self, work: Path, args: list[str], env: dict) -> subprocess.CompletedProcess:
        tf = shutil.which("terraform")
        base = {"HOME": str(work / ".home"), "PATH": "/usr/bin:/bin:" + str(Path(tf).parent),
                "TMPDIR": str(work / ".tmp"), "CHECKPOINT_DISABLE": "1", "TF_IN_AUTOMATION": "1"}
        (work / ".home").mkdir(exist_ok=True)
        (work / ".tmp").mkdir(exist_ok=True)
        return subprocess.run([tf, f"-chdir={work}", *args], env={**base, **env}, capture_output=True, text=True,
                              timeout=self.timeout)

    def apply(self, work: Path, env: dict):
        self.calls.append("apply")
        from ._common import templates_dir
        shutil.copy2(templates_dir() / "terraform.lock.hcl", work / ".terraform.lock.hcl")
        p = self._tf(work, ["init", "-input=false", "-lockfile=readonly"], env)
        if p.returncode != 0:
            return p.returncode, p.stderr
        p = self._tf(work, ["apply", "-input=false", "-auto-approve"], env)
        return p.returncode, p.stderr

    def show(self, work: Path) -> dict:
        self.calls.append("show")
        p = self._tf(work, ["show", "-json"], {})
        return json.loads(p.stdout or "{}")

    def destroy(self, work: Path, env: dict):
        self.calls.append("destroy")
        p = self._tf(work, ["destroy", "-input=false", "-auto-approve"], env)
        return p.returncode, p.stderr

    def state_list(self, work: Path) -> list[str]:
        self.calls.append("state_list")
        p = self._tf(work, ["state", "list"], {})
        return [x for x in p.stdout.splitlines() if x.strip()]


# ------------------------------------------------------------------------------------------------ execução
@dataclass
class CaseRef:
    case_id: str
    group_id: str
    claim_id: str
    side: str
    evidence_before: str = "DOC_SUPPORTED"


@dataclass
class RunConfig:
    run_id: str
    batch_id: str
    module: str
    max_polls: int = 5
    poll_interval_s: float = 10.0
    sleep: object = field(default=time.sleep)


def classify(stderr: str) -> tuple[str, str]:
    for name, pat in INFRA_PATTERNS:
        if re.search(pat, stderr or "", re.I):
            return "INFRA_ERROR", name
    for name, pat in API_PATTERNS:
        if re.search(pat, stderr or ""):
            return "REJECTED_BY_API", name
    return "UNKNOWN", "nao_classificado"


def run_token(run_id: str, plan_id: str) -> str:
    return "r" + hashlib.sha256(f"{run_id}|{plan_id}".encode()).hexdigest()[:7]


def make_secret() -> str:
    alpha = string.ascii_letters + string.digits
    core = "".join(_secrets.choice(alpha) for _ in range(28))
    return core + "aZ7!"


def _append(path: Path, recs: list[dict]):
    with open(path, "a", encoding="utf-8") as f:
        f.write(jsonl(recs))


def run_case(plan_file: Path, plan_id: str, case: CaseRef, cfg: RunConfig, out: Path, backend, kit,
             graph_file: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    sch = S.load()
    ev = kit.events
    eph = kit.ephemeral_dir(cfg.run_id)
    work = eph / plan_id
    token = run_token(cfg.run_id, plan_id)
    tags = {"bo-run": cfg.run_id, "bo-case": case.case_id}
    res = {"schema": RESULT_SCHEMA, "module": cfg.module, "harness": MODULE, "run_id": cfg.run_id,
           "plan_id": plan_id, "case_id": case.case_id, "started_at": now(), "status": None, "issues": [],
           "bindings": [], "intents": [], "apply": None, "readback_id": None, "residue": None}
    secrets_used: list[str] = []
    applied = False
    try:
        rep = R.render_file(plan_file, work, graph_file, plan_id, ownership_tags=tags)
        ev.append("rendered")
        row = rep["plans"][0]
        if row["status"] != "RENDERED":
            res["status"] = row["status"]
            res["issues"] = row["issues"]
            return res
        manifest = json.loads((work / "render_manifest.json").read_text(encoding="utf-8"))
        plan = next(p for p in read_jsonl(plan_file) if p["plan_id"] == plan_id)
        # entradas declaradas
        env = {}
        for inp in manifest["inputs"]:
            if inp["kind"] == "name_symbol":
                env["TF_VAR_" + inp["variable"]] = token
                res["bindings"].append({"variable": inp["variable"], "kind": "name_symbol", "value": token,
                                        "origin": "harness.run_token", "steps": inp["steps"]})
            elif inp["kind"] == "secret_at_run":
                sv = make_secret()
                secrets_used.append(sv)
                env["TF_VAR_" + inp["variable"]] = sv
                res["bindings"].append({"variable": inp["variable"], "kind": "secret_at_run",
                                        "origin": "gerado na execução; nunca gravado", "steps": inp["steps"]})
            else:
                res["status"] = "BLOCKED"
                res["issues"] = [{"code": "UNKNOWN_INPUT", "order": None, "field": inp["variable"],
                                  "detail": "entrada sem ligação declarada"}]
                return res
        # identidade efetiva
        idc = kit.identity()
        if not idc["matches_allowlist"]:
            res["status"] = "REFUSED_IDENTITY"
            return res
        # intenção ANTES da criação
        intents, runs = [], []
        seq = iter(range(1, 10**6))

        def _rid() -> str:  # run_id único por linha do run_manifest (C16: run_id não repete)
            return f"{cfg.run_id}-{next(seq):03d}"

        labels = R._labels(plan["steps"])
        for s in sorted(plan["steps"], key=lambda s: s["order"]):
            if s["action"] == "reference":
                continue
            node = sch.node("resource", s["resource_type"])
            tag_ok = "tags" in S.attrs(node) and S.attrs(node)["tags"].configurable
            iid = f"INT-{token}-{labels[s['order']]}".replace("_", "-")
            rec = {"intent_id": iid, "module": cfg.module, "provider": "azurerm", "batch_id": cfg.batch_id,
                   "case_id": case.case_id, "resource_type": s["resource_type"],
                   "logical_name": f"bo-{token}-{labels[s['order']].replace('_', '-')}", "recorded_at": now(),
                   "effective_identity_check": idc,
                   "purge_deadline": _plus_hours(kit.purge_hours),
                   "max_residual_cost": {"amount": kit.max_residual_usd, "currency": "USD"},
                   "tag_supported": tag_ok, "ttl_supported": False}
            if tag_ok:
                rec["tags"] = dict(tags)
            intents.append(rec)
            runs.append({"run_id": _rid(), "intent_id": iid, "stage": "intent", "at": now(),
                         "visibility": "public"})
        _append(out / "intent_manifest.jsonl", intents)
        _append(out / "run_manifest.jsonl", runs)
        res["intents"] = [i["intent_id"] for i in intents]
        ev.append("intent_written")

        def stage(st, **kw):
            _append(out / "run_manifest.jsonl", [dict({"run_id": _rid(), "intent_id": i, "stage": st,
                                                        "at": now(), "visibility": "public"}, **kw)
                                                  for i in res["intents"]])
            kit.heartbeat(st)

        stage("creating")
        ev.append("apply")
        applied = True
        rc, err = backend.apply(work, env)
        if rc != 0:
            cls, pat = classify(err)
            res["apply"] = {"ok": False, "class": cls, "pattern": pat}
            res["status"] = "APPLY_FAILED"
            _append(out / "outcomes.jsonl", [RB.infra_outcome(
                outcome_id=f"OUT-{token}", case_id=case.case_id, group_id=case.group_id, claim_id=case.claim_id,
                side=case.side, value=cls, detail=f"apply falhou ({pat})", evidence_before=case.evidence_before,
                decided_at=now())])
        else:
            res["apply"] = {"ok": True}
            stage("created", effective_identity_check=idc)
            # espera: consistência eventual (lê até todos os endereços aparecerem)
            want = {a for a in manifest["addresses"].values() if not a.startswith("data.")}
            raw = None
            for i in range(cfg.max_polls):
                ev.append("show")
                raw = backend.show(work)
                have = {r.get("address") for r in ((raw.get("values") or {}).get("root_module") or {})
                        .get("resources", [])}
                if want <= have:
                    break
                if i < cfg.max_polls - 1:
                    cfg.sleep(cfg.poll_interval_s)
            red = RD.redact_state(raw, sch)
            for extra in kit.extra_redactors:
                red = extra(red)
            del raw
            ev.append("redacted")
            RD.assert_clean(red, secrets_used)
            rbid = f"RB-{token}"
            htags: dict = {}
            for e in manifest["entries"]:
                if e["origin"] == "harness.ownership_tag":
                    htags.setdefault(labels[e["order"]], []).append(e["field"].split(".", 1)[1])
            rb = RB.build_readback(plan, red, readback_id=rbid, case_id=case.case_id, group_id=case.group_id,
                                   claim_id=case.claim_id, side=case.side, read_at=now(), sch=sch,
                                   harness_tags=htags)
            RD.assert_clean(rb, secrets_used)
            _append(out / "readback.jsonl", [rb])
            ev.append("readback_written")
            res["readback_id"] = rbid
            res["status"] = "READ"
            stage("confirmed", effective_identity_check=idc)
    except RD.RedactionError:
        res["status"] = "REDACTION_FAILED"  # nada da leitura foi gravado; o destroy roda no finally
        raise
    finally:
        if applied:
            stage("removal_requested")
            ev.append("destroy")
            drc, _derr = backend.destroy(work, env)
            left = backend.state_list(work)
            res["residue"] = {"destroy_ok": drc == 0, "state_entries_left": len(left)}
            if drc == 0 and not left:
                stage("absent")
            else:
                stage("removal_pending", note="destroy incompleto: entra na varredura com filtro de propriedade")
                res["status"] = (res["status"] or "") + "+RESIDUE"
        shutil.rmtree(eph, ignore_errors=True)
        ev.append("ephemeral_removed")
        res["finished_at"] = now()
        (out / "case_result.json").write_text(dumps(res), encoding="utf-8")
    return res


def _plus_hours(h: int) -> str:
    import datetime as dt
    from ._common import TZ
    return (dt.datetime.now(TZ).replace(microsecond=0) + dt.timedelta(hours=h)).isoformat()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.azurerm.executor")
    ap.add_argument("--replay", required=True, help="gravação bo.harness_azurerm.recording/1 (offline)")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--plan-id", required=True)
    ap.add_argument("--cases", required=True, help="C11 cases.jsonl (pega o caso do graph_ir do plano)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--batch-id", default="B-AZ-OFFLINE")
    ap.add_argument("--module", default=MODULE)
    ap.add_argument("--side", default="object", choices=["subject", "object"])
    a = ap.parse_args([x for x in (argv if argv is not None else sys.argv[1:]) if x != MODULE])
    try:
        rec = json.loads(Path(a.replay).read_text(encoding="utf-8"))
        plan_file = Path(a.plan)
        plan = next((p for p in read_jsonl(plan_file) if p["plan_id"] == a.plan_id), None)
        if plan is None:
            raise HarnessError(f"{a.plan_id} não está em {plan_file}")
        graphs = R.load_graphs(plan_file, None)
        cid = (graphs.get(plan["graph_id"]) or {}).get("case_id")
        cs = [c for c in read_jsonl(Path(a.cases)) if c["case_id"] == cid]
        if len(cs) != 1:
            raise HarnessError(f"caso {cid} não achado (ou repetido) em {a.cases}")
        c = cs[0]
        case = CaseRef(c["case_id"], c["group_id"], c["claim_id"], a.side)
        run_id = a.run_id or "RUN-" + run_token(now(), a.plan_id)
        kit = OfflineKit(rec["identity_sha256"])
        res = run_case(plan_file, a.plan_id, case, RunConfig(run_id, a.batch_id, a.module, sleep=lambda s: None),
                       Path(a.out), ReplayBackend(rec), kit)
    except (HarnessError, RD.RedactionError, OSError, KeyError) as e:
        print(f"executor: {e}", file=sys.stderr)
        return 2
    print(f"[{res['finished_at']}] executor (gravação): {a.plan_id} -> {res['status']}; saída em {portable(Path(a.out))}")
    return 0 if res["status"] in ("READ", "BLOCKED", "APPLY_FAILED") else 1


if __name__ == "__main__":
    sys.exit(main())
