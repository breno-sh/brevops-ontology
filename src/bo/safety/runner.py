"""Sequência segura de um lote (o que SMOKE-*, DEP-* e PROBE-* chamam). Nesta fase só roda com executor simulado.

  pré-condições   GO do Breno (BO_CLOUD_GO=1), módulo de nuvem no catálogo, trava cloud-<provedor> tomada, canal
                  efêmero de RAM cifrado, ambiente do Terraform limpo, nenhum state/plano cru na pasta persistente
  plano 1         init + plan no canal efêmero; show -json só em memória -> lista de recursos a criar
  intenção        uma linha por recurso ANTES de qualquer criação (nome sintético para tipo sem tag)
  plano 2         com bo_run_id e bo_names (nomes sintéticos) -> plan_guard (tipo, SKU, tag, nome, intenção, TTL,
                  custo com armazenamento/tráfego/requisições, provider, backend) -> recusa ou segue
  supervisor      janela longa exige registro e ack fresco do supervisor; heartbeat a cada passo
  identidade      conferida de novo IMEDIATAMENTE antes do apply (≤ identity_fresh_seconds)
  creating        gravado para todos os recursos; apply do plano 2 (o mesmo que foi checado)
  created         lido do state (show -json, em memória) -> referência só na cópia privada
  confirmed       leitura direta (readback_fn do harness) achou o recurso
  persistência    só o que passa pelo redator (redaction.write_redacted)
  destroy         teardown.terraform_destroy + ownership.cleanup + complete
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import ephemeral, identity, plan_check, redaction, skus
from .common import SafetyError, bo_data, tag_value
from .manifest import Manifest


class RunRefused(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "RUN")


def cloud_preconditions(module: str, provider: str, env: dict | None = None) -> list[str]:
    env = dict(os.environ if env is None else env)
    probs = []
    if env.get("BO_CLOUD_GO") != "1":
        probs.append("sem GO do Breno para este lote (BO_CLOUD_GO != 1)")
    cat = env.get("BO_MODULES")
    mods = {}
    if cat and Path(cat).exists():
        mods = {m["stable_id"]: m for m in json.loads(Path(cat).read_text(encoding="utf-8"))["modules"]}
    if not mods.get(module, {}).get("needs_cloud"):
        probs.append(f"{module} não é módulo de nuvem no catálogo")
    if not (Path(env.get("BO_DATA", str(bo_data()))) / "locks" / f"cloud-{provider}").is_dir():
        probs.append(f"trava cloud-{provider} não está tomada")
    probs += ephemeral.assert_terraform_env_clean(env)
    probs += identity.env_conflicts(provider, env)
    return probs


class SafeRun:
    def __init__(self, *, module: str, provider: str, batch_id: str, ttl_hours: int, window_hours: float,
                 tf_dir: Path, region: str, executor, identity_fn, channel: ephemeral.EphemeralChannel,
                 manifest: Manifest, out_dir: Path, readback_fn=None, supervisor=None, table=None,
                 usage=None, approved_class_c=(), spent_usd=None, simulation: bool = False):
        self.module, self.provider, self.batch = module, provider, batch_id
        self.ttl, self.window, self.region = ttl_hours, window_hours, region
        self.tf_dir, self.exe, self.identity_fn, self.ch = Path(tf_dir), executor, identity_fn, channel
        self.man, self.out_dir, self.readback_fn, self.sup = manifest, Path(out_dir), readback_fn, supervisor
        self.table = table or skus.load_table()
        self.usage, self.approved, self.spent = usage or {}, list(approved_class_c), spent_usd or {}
        self.simulation = simulation
        self.run_tag = tag_value(batch_id)
        self.bindings: list[dict] = []
        self.report: dict = {}

    # ------------------------------------------------------------------------------------- pré-condições
    def preflight(self):
        if not self.simulation:
            probs = cloud_preconditions(self.module, self.provider)
            if not self.ch.live_ok:
                probs.append("canal efêmero não é RAM cifrada")
            if probs:
                raise RunRefused("; ".join(probs))
        elif self.ch.live_ok is False and not isinstance(self.ch.backend, ephemeral.SimulatedBackend):
            raise RunRefused("simulação só com o canal simulado")
        raw = redaction.find_raw_tf_artifacts([self.tf_dir, self.out_dir])
        if raw:
            raise RunRefused(f"state/plano cru fora do canal efêmero: {len(raw)} arquivo(s)")
        if self.ch.path is None:
            raise RunRefused("canal efêmero fechado")

    def _tf(self, *args, extra_env=None) -> str:
        env = {**self.ch.env(), **(extra_env or {})}
        rc, out = self.exe(["terraform", *args], self.ch.workdir(), env)
        if rc != 0:
            raise RunRefused(f"terraform {args[0]} saiu {rc}")
        return out

    def _vars(self, names: dict) -> list[str]:
        f = self.ch.path / "bo.auto.tfvars.json"
        f.write_text(json.dumps({"bo_run_id": self.run_tag, "bo_names": names, "bo_region": self.region}))
        return ["-var-file", str(f)]

    def _copy_config(self):
        wd = self.ch.workdir()
        for p in self.tf_dir.glob("*.tf"):
            shutil.copy2(p, wd / p.name)

    # ------------------------------------------------------------------------------------- lote
    def plan_and_record(self) -> dict:
        self.preflight()
        self._copy_config()
        self._tf("init", "-input=false", "-no-color")
        self._tf("plan", "-input=false", "-no-color", "-out", str(self.ch.plan_path()), *self._vars({}))
        plan1 = json.loads(self._tf("show", "-json", str(self.ch.plan_path())))
        creates = [rc for rc in plan1.get("resource_changes", []) if rc.get("mode") != "data"
                   and "create" in (rc.get("change") or {}).get("actions", [])]
        chk = self.identity_fn(self.provider)
        names = {}
        for rc in creates:
            f = skus.intent_fields(self.table, self.provider, rc["type"]) if skus.entry(
                self.table, self.provider, rc["type"]) else None
            if f is None:
                continue  # o plan_guard recusa o tipo fora da allowlist logo abaixo
            it = self.man.record_intent(provider=self.provider, batch_id=self.batch, resource_type=rc["type"],
                                        identity_check=chk, ttl_hours=int(self.ttl), table_fields=f,
                                        address=rc["address"], region=self.region, run_tag=self.run_tag)
            self.bindings.append({"address": rc["address"], "intent_id": it["intent_id"], "resource_type": rc["type"],
                                  "logical_name": it["logical_name"], "trace": f["trace"]})
            names[rc["address"]] = it["logical_name"]
        self._tf("plan", "-input=false", "-no-color", "-out", str(self.ch.plan_path()), *self._vars(names))
        plan2 = json.loads(self._tf("show", "-json", str(self.ch.plan_path())))
        ctx = {"module": self.module, "provider": self.provider, "batch_id": self.batch, "run_tag": self.run_tag,
               "ttl_hours": self.ttl, "window_hours": self.window, "region": self.region, "usage": self.usage,
               "approved_class_c": self.approved, "spent_usd": self.spent,
               "supervisor": self.sup.plan_context() if self.sup else {}}
        rep = plan_check.check_plan(plan2, ctx, self.table, intents=self.bindings, tf_dir=self.tf_dir)
        self.report["plan_guard"] = {"ok": rep["ok"], "findings": rep["findings"], "cost": rep["cost"]}
        redaction.write_redacted(self.out_dir / "plan_redacted.json", redaction.redact_tf(plan2, "plan"),
                                 ephemeral_roots=[self.ch.path])
        if not rep["ok"]:
            for b in self.bindings:
                self.man.stage(b["intent_id"], "absent", residual_usd=0.0, note="plano recusado pelo plan_guard")
            raise plan_check.PlanRefused("plano recusado", rep["findings"])
        return rep

    def apply(self) -> list[dict]:
        if self.sup:
            self.sup.beat()
        chk = self.identity_fn(self.provider)  # imediatamente antes do apply
        identity.require_fresh(chk)
        for b in self.bindings:
            self.man.stage(b["intent_id"], "creating", identity_check=chk)
        self._tf("apply", "-input=false", "-no-color", "-auto-approve", str(self.ch.plan_path()))
        state = json.loads(self._tf("show", "-json"))
        by_addr = {r["address"]: r for r in (state.get("values") or {}).get("root_module", {}).get("resources", [])}
        done = []
        for b in self.bindings:
            r = by_addr.get(b["address"])
            if r is None:
                continue  # não criado: a reconciliação do teardown marca ausente
            ref = str((r.get("values") or {}).get("id") or "")
            self.man.stage(b["intent_id"], "created", identity_check=chk, ref=ref or None)
            if self.readback_fn and self.readback_fn(b, r):
                self.man.stage(b["intent_id"], "confirmed", identity_check=chk)
            done.append(b)
        redaction.write_redacted(self.out_dir / "state_redacted.json", redaction.redact_tf(state, "state"),
                                 ephemeral_roots=[self.ch.path])
        if self.sup:
            self.sup.beat()
        return done
