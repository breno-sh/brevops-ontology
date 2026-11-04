"""Nuvem simulada em arquivo (JSON + flock), com a mesma interface dos adaptadores reais (providers.Adapter).

Serve às injeções de falha (o runner simulado morre por SIGKILL e o estado da "nuvem" sobrevive no arquivo) e
aos testes de propriedade. Modela o que derrubou a limpeza antiga: vários tipos (não só instância), várias
regiões e recursos globais, e o modo de remoção de cada tipo lido da allowlist (removal.mode):
  sync         some no pedido
  async        fica "deleting" por pending_hours e some
  scheduled    fica "pending_deletion" até o expurgo (purge_days; KMS)
  soft_delete  fica "soft_deleted" até o expurgo; purge() apaga na hora (cofre sem purge protection)
  retained     não se apaga: fica "retained" (anel de chaves); resíduo esperado com custo zero
Recurso filho (parent) some junto com o pai (vínculos sem nome próprio).
"""

from __future__ import annotations

import fcntl
import json
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from .common import write_atomic


class FakeCloud:
    def __init__(self, path: Path, provider: str = "aws", regions=("r-east-1", "r-west-2", "r-south-1"),
                 modes: dict | None = None, global_types=(), clock: float | None = None):
        self.path = Path(path)
        self.provider = provider
        self.lock = self.path.with_suffix(".lock")
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(self.path, json.dumps({
                "provider": provider, "regions": list(regions), "clock": clock or time.time(), "items": {},
                "calls": [], "modes": modes or {}, "global_types": list(global_types)}))

    @contextmanager
    def _tx(self, write=True):
        with open(self.lock, "a+") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                yield data
                if write:
                    write_atomic(self.path, json.dumps(data, sort_keys=True))
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    # ------------------------------------------------------------------------------------- relógio e efeitos
    def advance(self, seconds: float) -> None:
        with self._tx() as d:
            d["clock"] += seconds
            self._settle(d)

    @staticmethod
    def _settle(d):
        for ref, it in list(d["items"].items()):
            if it["state"] in ("deleting", "pending_deletion", "soft_deleted") and d["clock"] >= it["gone_at"]:
                FakeCloud._remove(d, ref)

    @staticmethod
    def _remove(d, ref):
        d["items"].pop(ref, None)
        for cref, c in list(d["items"].items()):
            if c.get("parent") == ref:
                FakeCloud._remove(d, cref)

    # ------------------------------------------------------------------------------------- interface Adapter
    def regions(self) -> list[str]:
        with self._tx(write=False) as d:
            return list(d["regions"])

    def create(self, rtype: str, region: str, name: str | None, tags: dict | None = None, owner: str = "bo",
               parent: str | None = None) -> str:
        with self._tx() as d:
            ref = f"ref-{rtype}-{secrets.token_hex(6)}"
            d["items"][ref] = {"ref": ref, "type": rtype,
                               "region": "global" if rtype in d["global_types"] else region,
                               "name": name, "tags": dict(tags or {}), "state": "active", "created_at": d["clock"],
                               "owner": owner, "parent": parent}
            d["calls"].append(["create", rtype])
            return ref

    @staticmethod
    def _view(it):
        return {k: v for k, v in it.items() if k not in ("owner", "gone_at")}

    def list_region(self, region: str) -> list[dict]:
        with self._tx() as d:
            self._settle(d)
            return [self._view(i) for i in d["items"].values() if i["region"] == region]

    def list_global(self) -> list[dict]:
        with self._tx() as d:
            self._settle(d)
            return [self._view(i) for i in d["items"].values() if i["region"] == "global"]

    def list_all(self) -> list[dict]:
        out = self.list_global()
        for r in self.regions():
            out += self.list_region(r)
        return out

    def get(self, ref: str) -> dict | None:
        with self._tx() as d:
            self._settle(d)
            it = d["items"].get(ref)
            return self._view(it) if it else None

    def delete(self, item: dict) -> str:
        """Estado depois do pedido: absent, removal_pending ou purge_scheduled."""
        with self._tx() as d:
            it = d["items"].get(item["ref"])
            d["calls"].append(["delete", item.get("type"), item.get("owner_hint")])
            if it is None:
                return "absent"
            if it.get("owner") != "bo":
                d.setdefault("foreign_deletes", []).append(item["ref"])
            mode, secs = d["modes"].get(it["type"], ["sync", 0])
            if mode == "sync":
                self._remove(d, item["ref"])
                return "absent"
            if mode == "async":
                if it["state"] == "active":
                    it["state"], it["gone_at"] = "deleting", d["clock"] + secs
                return "removal_pending"
            if mode in ("scheduled", "soft_delete"):
                if it["state"] == "active":
                    it["state"] = "pending_deletion" if mode == "scheduled" else "soft_deleted"
                    it["gone_at"] = d["clock"] + secs
                return "purge_scheduled"
            it["state"] = "retained"
            return "purge_scheduled"

    def purge(self, item: dict) -> str:
        with self._tx() as d:
            it = d["items"].get(item["ref"])
            if it is None:
                return "absent"
            if it["state"] == "soft_deleted":
                self._remove(d, item["ref"])
                return "absent"
            return "purge_scheduled"

    # ------------------------------------------------------------------------------------- inspeção (testes)
    def snapshot(self) -> dict:
        with self._tx(write=False) as d:
            return json.loads(json.dumps(d))

    def foreign_deletes(self) -> list:
        return self.snapshot().get("foreign_deletes", [])

    def items(self) -> dict:
        return self.snapshot()["items"]


def modes_from_table(table: dict, provider: str) -> dict:
    out = {}
    for t, e in table["providers"][provider]["types"].items():
        rm = e["removal"]
        secs = {"async": rm["pending_hours"] * 3600, "scheduled": rm["purge_days"] * 86400,
                "soft_delete": rm["purge_days"] * 86400}.get(rm["mode"], 0)
        out[t] = [rm["mode"], secs]
    return out
