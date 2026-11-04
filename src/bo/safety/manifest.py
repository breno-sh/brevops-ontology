"""Manifesto de intenção e de execução (C16 3.0.0): a intenção é gravada ANTES da criação.

Protocolo por recurso (cada linha com fsync antes do passo seguinte):
  intent            gravada antes de qualquer chamada; nome lógico (sintético rastreável), tags, TTL do runner,
                    prazo de expurgo, custo residual máximo, identidade conferida (hash)
  creating          gravada logo ANTES da chamada que cria (apply); exige identidade conferida agora há pouco
  created           depois da criação, com a referência do provedor (só na cópia privada)
  confirmed         leitura direta pela API achou o recurso
  removal_requested gravada ANTES da chamada que remove
  removal_pending   o provedor aceitou e está removendo (assíncrono)
  purge_scheduled   remoção agendada (KMS, cofre em soft delete): resíduo esperado com prazo
  absent            leitura direta devolve "não encontrado" (verified_absent)
Os estágios de cada intenção só sobem (C16-ORDER), e created/confirmed levam a identidade (C16-IDENTITY).

Duas cópias: a PRIVADA (canal privado, fora dos repositórios e de $BO_DATA/<módulo>; visibility=private, com
provider_resource_ref) é a fonte da reconciliação; a PÚBLICA ($BO_DATA/<módulo>/, visibility=public, sem
provider_resource_ref) é projeção da privada e pode ser regerada (publish) depois de uma morte no meio.
Linha rasgada por morte do processo é detectada (common.read_jsonl) e cortada antes do próximo append.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from . import identity as idg
from .common import (SafetyError, append_line, bo_data, canon, inside_git_repo, iso, now_dt, parse_iso, read_jsonl,
                     repair_tail, synthetic_name, tag_value, write_atomic)

STAGES = ["intent", "creating", "created", "confirmed", "removal_requested", "removal_pending", "purge_scheduled",
          "absent"]
RANK = {s: i for i, s in enumerate(STAGES)}
TERMINAL = {"absent", "purge_scheduled"}
INTENT_FILE, RUN_FILE, BIND_FILE = "intent_manifest.jsonl", "run_manifest.jsonl", "bindings.jsonl"


class ManifestRefused(SafetyError):
    def __init__(self, msg):
        super().__init__(msg, "MANIFEST")


def private_root() -> Path:
    return Path(os.environ.get("BO_PRIVATE_DIR") or (Path.home() / ".local" / "state" / "bo" / "manifests"))


@dataclass
class IntentState:
    intent: dict
    runs: list = field(default_factory=list)
    binding: dict | None = None

    @property
    def last(self) -> str:
        return self.runs[-1]["stage"] if self.runs else "intent"

    @property
    def ref(self) -> str | None:
        for r in reversed(self.runs):
            if r.get("provider_resource_ref"):
                return r["provider_resource_ref"]
        return None

    @property
    def iid(self) -> str:
        return self.intent["intent_id"]


class Manifest:
    def __init__(self, module: str, public_dir: Path | None = None, private_dir: Path | None = None):
        self.module = module
        self.public = Path(public_dir or (bo_data() / module))
        self.private = Path(private_dir or (private_root() / module))
        for d in (self.private,):
            if inside_git_repo(d.parent if not d.exists() else d) is not None:
                raise ManifestRefused("canal privado do manifesto dentro de um repositório git")
        pub, prv = self.public.resolve(), self.private.resolve()
        if pub == prv or pub in prv.parents:
            raise ManifestRefused("cópia privada dentro da pasta pública do módulo")
        self.private.mkdir(parents=True, exist_ok=True)
        os.chmod(self.private, 0o700)
        self._repaired = False  # a pasta pública só nasce na primeira gravação (ler não cria nada)

    # ------------------------------------------------------------------------------------------- leitura
    def _p(self, name, private=True) -> Path:
        return (self.private if private else self.public) / name

    def problems(self) -> list[str]:
        out = []
        for name in (INTENT_FILE, RUN_FILE, BIND_FILE):
            _, pr = read_jsonl(self._p(name))
            out += [f"{name}:{x}" for x in pr]
        return out

    def load(self) -> dict[str, IntentState]:
        intents, _ = read_jsonl(self._p(INTENT_FILE))
        runs, _ = read_jsonl(self._p(RUN_FILE))
        binds, _ = read_jsonl(self._p(BIND_FILE))
        st = {i["intent_id"]: IntentState(i) for i in intents}
        for b in binds:
            if b.get("intent_id") in st:
                st[b["intent_id"]].binding = b
        for r in runs:
            if r["intent_id"] in st and r["stage"] != "intent":
                st[r["intent_id"]].runs.append(r)
            elif r["intent_id"] in st:
                continue
        return st

    def repair(self) -> list[str]:
        """Corta caudas rasgadas (morte no meio de uma gravação). Devolve os arquivos cortados."""
        cut = [name for name in (INTENT_FILE, RUN_FILE, BIND_FILE) if repair_tail(self._p(name))]
        for name in cut:
            if self._p(name).stat().st_size == 0:
                self._p(name).unlink()  # só havia a linha rasgada: não há manifesto
        self._repaired = True
        return cut

    def _repair(self):
        if not self._repaired:
            for name in (INTENT_FILE, RUN_FILE, BIND_FILE):
                repair_tail(self._p(name))
            self._repaired = True

    def _next_run_id(self) -> str:
        runs, _ = read_jsonl(self._p(RUN_FILE))
        return f"RUN-{len(runs) + 1:05d}"

    # ------------------------------------------------------------------------------------------- escrita
    def _write_pair(self, name: str, private_rec: dict, public_rec: dict):
        self.public.mkdir(parents=True, exist_ok=True)
        append_line(self._p(name), canon(private_rec), 0o600)
        append_line(self._p(name, private=False), canon(public_rec))

    def record_intent(self, *, provider: str, batch_id: str, resource_type: str, identity_check: dict,
                      ttl_hours: int, table_fields: dict, case_id: str | None = None, address: str | None = None,
                      region: str | None = None, run_tag: str | None = None, now=None) -> dict:
        """Grava a intenção (antes de qualquer criação). table_fields = skus.intent_fields(...)."""
        self._repair()
        idg.require_fresh(identity_check, now=now)
        if not isinstance(ttl_hours, int) or ttl_hours < 1:
            raise ManifestRefused("intenção sem TTL do runner (ttl_hours inteiro >= 1)")
        st = self.load()
        seq = 1 + sum(1 for s in st.values() if s.intent["batch_id"] == batch_id)
        iid = f"INT-{tag_value(batch_id).upper()}-{seq:04d}"
        if iid in st:
            raise ManifestRefused(f"intenção repetida: {iid}")
        t = now or now_dt()
        purge = t + timedelta(hours=ttl_hours + table_fields.get("pending_hours", 0)) + \
            timedelta(days=table_fields.get("purge_days", 0))
        rec = {
            "intent_id": iid, "module": self.module, "provider": provider, "batch_id": batch_id,
            "resource_type": resource_type, "logical_name": synthetic_name(batch_id, seq),
            "recorded_at": iso(t), "effective_identity_check": dict(identity_check),
            "purge_deadline": iso(purge),
            "max_residual_cost": {"amount": float(table_fields["max_residual_usd"]), "currency": "USD"},
            "tag_supported": bool(table_fields["tag_supported"]), "ttl_supported": bool(table_fields["ttl_supported"]),
            "ttl_hours": ttl_hours,
        }
        if case_id:
            rec["case_id"] = case_id
        if rec["tag_supported"]:
            rec["tags"] = {"bo-run": run_tag or tag_value(batch_id), "bo-intent": tag_value(iid)}
        self._write_pair(INTENT_FILE, rec, rec)
        append_line(self._p(BIND_FILE), canon({"intent_id": iid, "address": address, "region": region,
                                              "resource_type": resource_type, "logical_name": rec["logical_name"],
                                              "run_tag": run_tag or tag_value(batch_id),
                                              "trace": table_fields.get("trace")}), 0o600)
        run = {"run_id": self._next_run_id(), "intent_id": iid, "stage": "intent", "at": iso(t)}
        self._write_pair(RUN_FILE, {**run, "visibility": "private"}, {**run, "visibility": "public"})
        return rec

    def stage(self, intent_id: str, stage: str, *, identity_check: dict | None = None, ref: str | None = None,
              residual_usd: float | None = None, note: str | None = None, now=None) -> dict:
        self._repair()
        if stage not in RANK or stage == "intent":
            raise ManifestRefused(f"estágio inválido: {stage}")
        st = self.load().get(intent_id)
        if st is None:
            raise ManifestRefused(f"{stage} sem intenção gravada antes ({intent_id})")
        if RANK[stage] <= RANK[st.last]:
            raise ManifestRefused(f"{intent_id}: {stage} depois de {st.last} (estágios só sobem)")
        if stage == "creating":
            idg.require_fresh(identity_check, now=now)
            if not idg.same_identity(identity_check, st.intent["effective_identity_check"]):
                raise ManifestRefused("identidade mudou entre a intenção e a criação; abortado")
        if stage in ("created", "confirmed"):
            if not identity_check or not identity_check.get("matches_allowlist"):
                raise ManifestRefused(f"{stage} sem identidade conferida (C16-IDENTITY)")
            if not idg.same_identity(identity_check, st.intent["effective_identity_check"]):
                raise ManifestRefused("identidade diferente da da intenção")
        if stage == "created" and not (ref or st.ref):
            raise ManifestRefused("created sem referência do provedor")
        t = now or now_dt()
        if st.runs and t < parse_iso(st.runs[-1]["at"]):
            t = parse_iso(st.runs[-1]["at"])  # relógio nunca volta dentro de uma intenção
        base = {"run_id": self._next_run_id(), "intent_id": intent_id, "stage": stage, "at": iso(t)}
        if identity_check and stage in ("creating", "created", "confirmed", "removal_requested"):
            base["effective_identity_check"] = {k: identity_check[k] for k in
                                                ("identity_sha256", "checked_at", "matches_allowlist")}
        if residual_usd is not None:
            base["residual_cost"] = {"amount": float(residual_usd), "currency": "USD"}
        if note:
            base["note"] = note
        priv = {**base, "visibility": "private"}
        if ref:
            priv["provider_resource_ref"] = ref
        self._write_pair(RUN_FILE, priv, {**base, "visibility": "public"})
        return priv

    # ------------------------------------------------------------------------------------------- projeção pública
    def public_projection(self) -> tuple[str, str]:
        intents, _ = read_jsonl(self._p(INTENT_FILE))
        runs, _ = read_jsonl(self._p(RUN_FILE))
        it = "".join(canon(i) + "\n" for i in intents)
        rn = "".join(canon({k: v for k, v in {**r, "visibility": "public"}.items() if k != "provider_resource_ref"})
                     + "\n" for r in runs)
        return it, rn

    def publish(self) -> None:
        """Regrava a cópia pública a partir da privada (depois de morte entre as duas gravações)."""
        it, rn = self.public_projection()
        if it or rn:
            self.public.mkdir(parents=True, exist_ok=True)
        for name, text in ((INTENT_FILE, it), (RUN_FILE, rn)):
            dest = self._p(name, private=False)
            if text:
                write_atomic(dest, text)
            elif dest.exists():
                dest.unlink()  # sem nenhuma intenção, não há manifesto (arquivo vazio não é C16)

    def public_consistent(self) -> bool:
        it, rn = self.public_projection()
        pi, pr = self._p(INTENT_FILE, private=False), self._p(RUN_FILE, private=False)
        return (pi.read_text(encoding="utf-8") if pi.exists() else "") == it and \
               (pr.read_text(encoding="utf-8") if pr.exists() else "") == rn

    def export_for_supervisor(self) -> list[dict]:
        """Linhas que o supervisor precisa para destruir sem o state: intenção + vínculo + última referência."""
        out = []
        for s in self.load().values():
            out.append({"intent_id": s.iid, "provider": s.intent["provider"], "resource_type": s.intent["resource_type"],
                        "logical_name": s.intent["logical_name"], "tags": s.intent.get("tags", {}),
                        "region": (s.binding or {}).get("region"), "ref": s.ref, "last": s.last,
                        "run_tag": (s.binding or {}).get("run_tag") or tag_value(s.intent["batch_id"]),
                        "purge_deadline": s.intent["purge_deadline"]})
        return out


def load_public(module_dir: Path) -> tuple[list[dict], list[dict], list[str]]:
    it, p1 = read_jsonl(Path(module_dir) / INTENT_FILE)
    rn, p2 = read_jsonl(Path(module_dir) / RUN_FILE)
    return it, rn, p1 + p2


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
