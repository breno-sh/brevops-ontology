"""Runner simulado de um lote, que pode ser morto (SIGKILL de verdade) em qualquer etapa.

  python -I -m bo.safety.sim_runner --dir D --provider aws --kill-at K [--mode before|torn|split]

Faz o mesmo protocolo do runner real (runner.py), contra a nuvem simulada em D/cloud.json:
  para cada recurso: intenção -> creating -> chamada de criação -> created -> leitura direta -> confirmed
  depois o teardown do próprio runner: removal_requested -> chamada de remoção -> estágio pós-remoção, e a espera
  até ausente/agendado; por fim publica a cópia pública.
Cada passo tem um número. Com --kill-at K o processo se mata com SIGKILL antes do passo K; --mode torn: se o passo
K grava o manifesto, grava só metade da linha e se mata (escrita rasgada); --mode split: grava a cópia privada e
morre antes da pública. Sem --kill-at, roda até o fim.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from . import common, identity, skus
from .common import tag_value
from .fakecloud import FakeCloud, modes_from_table
from .manifest import Manifest

SCENARIOS = {
    # (tipo, pai) na ordem de criação; o pai é o índice do recurso de que o vínculo depende
    "aws": [("aws_route_table", None), ("aws_route_table_association", 0), ("aws_s3_bucket", None),
            ("aws_kms_key", None), ("aws_kms_alias", None), ("aws_db_instance", None)],
    "google": [("google_compute_network", None), ("google_project_iam_member", 0), ("google_storage_bucket", None),
               ("google_kms_key_ring", None), ("google_kms_crypto_key", None), ("google_sql_database_instance", None)],
    "azurerm": [("azurerm_resource_group", None), ("azurerm_subnet", None),
                ("azurerm_subnet_network_security_group_association", 1), ("azurerm_storage_account", None),
                ("azurerm_key_vault", None)],
    "oci": [("oci_identity_compartment", None), ("oci_core_network_security_group", None),
            ("oci_core_network_security_group_security_rule", 1), ("oci_objectstorage_bucket", None),
            ("oci_kms_vault", None)],
}
GLOBAL = {"aws": ["aws_s3_bucket"], "google": [], "azurerm": [], "oci": []}
REGIONS = {"aws": ["us-east-1", "us-west-2", "eu-west-1", "sa-east-1"],
           "google": ["us-central1", "us-east1", "europe-west1"],
           "azurerm": ["eastus", "westus2", "brazilsouth"],
           "oci": ["sa-saopaulo-1", "us-ashburn-1", "eu-frankfurt-1"]}
SIM_ACCOUNT = "conta-sandbox-simulada"


def paths(d: Path) -> dict:
    return {"cloud": d / "cloud.json", "public": d / "public", "private": d / "private", "locks": d / "locks",
            "allowlist": d / "allowlist"}


def setup(d: Path, provider: str, table: dict, foreign: bool = True) -> FakeCloud:
    """Nuvem simulada, allowlist privada (600) e recursos de terceiros em todas as regiões."""
    p = paths(d)
    d.mkdir(parents=True, exist_ok=True)
    fc = FakeCloud(p["cloud"], provider, REGIONS[provider], modes_from_table(table, provider), GLOBAL[provider])
    canon_id = f"{provider}|sim={SIM_ACCOUNT}"
    p["allowlist"].write_text(f"{provider} sha256:{identity.identity_hash(canon_id)} sandbox-simulada\n")
    os.chmod(p["allowlist"], 0o600)
    if foreign:
        types = [t for t, _ in SCENARIOS[provider]]
        regs = REGIONS[provider]
        for n, t in enumerate(types):
            fc.create(t, regs[n % len(regs)], f"bo-alheio-{n:04d}", {"dono": "terceiro"}, owner="terceiro")
        fc.create(types[2], regs[-1], "bo-outro-0001", {"bo-run": "outra-execucao"}, owner="terceiro")
    return fc


def sim_check(d: Path, provider: str) -> dict:
    """Conferência real (allowlist, permissão, hash) sobre a leitura simulada."""
    p = paths(d)
    allowed = identity.load_allowlist(p["allowlist"])
    h = identity.identity_hash(f"{provider}|sim={SIM_ACCOUNT}")
    if h not in allowed[provider]:
        raise identity.IdentityRefused("simulada fora da allowlist")
    return {"identity_sha256": h, "checked_at": common.now(), "matches_allowlist": True}


MODES = ("before", "torn", "split")


class Killer:
    """before: SIGKILL antes do passo; torn: o passo grava meia linha e morre; split: o passo grava a cópia
    privada inteira e morre antes da pública."""

    def __init__(self, kill_at: int | None, mode: str = "before"):
        self.kill_at, self.mode, self.n = kill_at, mode, 0
        self.writes: list[int] = []

    def step(self, writes: bool = False):
        self.n += 1
        if writes:
            self.writes.append(self.n)
        if self.kill_at is None or self.n != self.kill_at:
            return
        if self.mode == "before" or not writes:
            os.kill(os.getpid(), signal.SIGKILL)
        import bo.safety.manifest as mm
        orig = mm.append_line
        mode = self.mode

        def hooked(path, line, fmode=0o644):
            if mode == "split":
                orig(path, line, fmode)
            else:
                data = (line.rstrip("\n") + "\n").encode()
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, fmode)
                os.write(fd, data[: max(1, len(data) // 2)])
                os.fsync(fd)
                os.close(fd)
            os.kill(os.getpid(), signal.SIGKILL)
        mm.append_line = hooked


def run_batch(d: Path, provider: str, kill_at: int | None = None, mode: str = "before") -> int:
    table = skus.load_table()
    p = paths(d)
    fc = FakeCloud(p["cloud"])
    module = f"SIM-{provider.upper()}"
    batch = f"B-SIM-{provider.upper()}-01"
    run_tag = tag_value(batch)
    man = Manifest(module, p["public"], p["private"])
    k = Killer(kill_at, mode)
    region = table["providers"][provider]["regions_allowed"][0]
    refs: dict[int, str] = {}
    iids: dict[int, str] = {}
    scen = SCENARIOS[provider]
    for i, (rtype, parent) in enumerate(scen):
        f = skus.intent_fields(table, provider, rtype)
        chk = sim_check(d, provider)
        k.step(writes=True)
        it = man.record_intent(provider=provider, batch_id=batch, resource_type=rtype, identity_check=chk,
                               ttl_hours=2, table_fields=f, address=f"{rtype}.caso", region=region, run_tag=run_tag)
        iids[i] = it["intent_id"]
        k.step(writes=True)
        man.stage(iids[i], "creating", identity_check=sim_check(d, provider))
        k.step()
        tags = dict(it.get("tags") or {})
        name = it["logical_name"] if f["trace"] == "name" else (None if f["trace"] == "ref" else it["logical_name"])
        refs[i] = fc.create(rtype, region, name, tags, parent=refs.get(parent) if parent is not None else None)
        k.step(writes=True)
        man.stage(iids[i], "created", identity_check=chk, ref=refs[i])
        k.step(writes=True)
        if fc.get(refs[i]) is None:
            raise SystemExit("leitura direta não achou o recurso criado")
        man.stage(iids[i], "confirmed", identity_check=chk)
    order = {t: e["delete_order"] for t, e in table["providers"][provider]["types"].items()}
    chk = sim_check(d, provider)
    for i in sorted(refs, key=lambda i: -order[scen[i][0]]):
        k.step(writes=True)
        man.stage(iids[i], "removal_requested", identity_check=chk)
        k.step()
        res = fc.delete({"ref": refs[i], "type": scen[i][0]})
        k.step(writes=True)
        if res == "removal_pending":
            man.stage(iids[i], "removal_pending")
        elif res == "purge_scheduled":
            man.stage(iids[i], "purge_scheduled", residual_usd=skus.intent_fields(table, provider, scen[i][0])["max_residual_usd"])
        else:
            man.stage(iids[i], "absent", residual_usd=0.0)
    for _ in range(6):
        k.step()
        fc.advance(3600)
        for i in refs:
            st = man.load()[iids[i]]
            it = fc.get(refs[i])
            if st.last == "removal_pending" and it is None:
                man.stage(iids[i], "absent", residual_usd=0.0)
            elif st.last == "purge_scheduled" and it is not None and it["state"] == "soft_deleted":
                fc.purge(it)
                man.stage(iids[i], "absent", residual_usd=0.0, note="expurgado pelo teardown")
    k.step()
    man.publish()
    return k.n, k.writes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--provider", required=True, choices=list(SCENARIOS))
    ap.add_argument("--kill-at", type=int)
    ap.add_argument("--mode", choices=MODES, default="before")
    a = ap.parse_args(argv)
    n, writes = run_batch(Path(a.dir), a.provider, a.kill_at, a.mode)
    print(json.dumps({"steps": n, "writes": writes}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
