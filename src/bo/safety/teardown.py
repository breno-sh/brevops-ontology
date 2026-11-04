"""Teardown de um lote (§10.3), por provedor: o mesmo caminho do runner, do supervisor e da recuperação.

  python -I -m bo.safety.teardown --provider P --run MODULO [--batch B] [--workdir EFEMERO] --dry-run|--apply

Ordem: (1) com --workdir (canal efêmero do runner vivo): terraform destroy e `terraform state list` vazio;
(2) identidade conferida contra a allowlist; (3) sob a trava cleanup-global, reconciliação do manifesto com a
varredura de todas as regiões, remoção SÓ do que tem a tag da execução ou linha do manifesto próprio, em ordem
de dependência, gravando removal_requested ANTES de cada chamada; (4) espera até ausente ou expurgo agendado;
(5) teardown completo (ownership.complete) contra o EXPECTED_RESIDUE; (6) cópia pública regerada.
--dry-run não chama CLI de nuvem: mostra os passos e os comandos de remoção por tipo da allowlist.
Execução de verdade exige BO_CLOUD_GO=1 (GO do Breno, D9); nesta fase sempre recusa.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import identity, residue, skus
from .common import PROVIDERS, SafetyError, bo_repo, tag_value, write_json
from .manifest import Manifest
from .ownership import cleanup, complete
from .providers import CliAdapter, delete_steps


def terraform_destroy(workdir: Path, env: dict, run=None) -> list[str]:
    """destroy + state list vazio, no canal efêmero. Devolve problemas."""
    run = run or (lambda argv: subprocess.run(argv, cwd=workdir, env=env, capture_output=True, text=True,
                                              timeout=3600, stdin=subprocess.DEVNULL))
    probs = []
    r = run(["terraform", "destroy", "-auto-approve", "-input=false", "-no-color"])
    if r.returncode != 0:
        probs.append(f"terraform destroy saiu {r.returncode}")
    r = run(["terraform", "state", "list", "-no-color"])
    if r.returncode != 0 or r.stdout.strip():
        probs.append("terraform state list não está vazio depois do destroy")
    return probs


def dry_run(provider: str, table: dict) -> list[str]:
    lines = [f"[{provider}] teardown (dry-run: nenhuma CLI de nuvem é chamada)",
             "  1 terraform destroy -auto-approve no canal efêmero; terraform state list vazio",
             "  2 identidade efetiva conferida contra ~/.config/bo/allowlist",
             "  3 trava cleanup-global; varredura de todas as regiões lidas da conta; filtro de posse",
             "  4 removal_requested gravado antes de cada chamada; ordem de dependência (delete_order)",
             "  5 espera ausente/agendado; 6 teardown completo contra o EXPECTED_RESIDUE; 7 cópia pública"]
    for t, e in sorted(table["providers"][provider]["types"].items(), key=lambda kv: -kv[1]["delete_order"]):
        st = delete_steps(provider, t)
        txt = st if isinstance(st, str) else " && ".join(" ".join(x for x in s if x != "?") for s in st)
        lines.append(f"  {e['delete_order']:>3} {t:<52} {txt}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="teardown")
    ap.add_argument("--provider", required=True, choices=PROVIDERS)
    ap.add_argument("--run")
    ap.add_argument("--batch")
    ap.add_argument("--workdir")
    ap.add_argument("--project")
    ap.add_argument("--tenancy")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    table = skus.load_table()
    if a.dry_run:
        print("\n".join(dry_run(a.provider, table)))
        return 0
    if os.environ.get("BO_CLOUD_GO") != "1":
        print("teardown: recusado; sem GO do Breno (BO_CLOUD_GO=1) nenhuma CLI de nuvem roda", file=sys.stderr)
        return 2
    if not a.run:
        print("teardown: --run MODULO obrigatório (o manifesto é a prova de posse)", file=sys.stderr)
        return 2
    try:  # pragma: no cover - caminho de nuvem
        probs = terraform_destroy(Path(a.workdir), dict(os.environ)) if a.workdir else []
        chk = identity.check(a.provider)
        man = Manifest(a.run)
        st = man.load()
        batch = a.batch or (next(iter(st.values())).intent["batch_id"] if st else None)
        if not batch:
            print("teardown: manifesto vazio e sem --batch: nada a provar como nosso")
            return 1
        from .providers import subprocess_runner
        ctx = {k: v for k, v in (("project", a.project or os.environ.get("GOOGLE_PROJECT")),
                                 ("tenancy", a.tenancy)) if v}
        adapter = CliAdapter(a.provider, subprocess_runner, ctx)
        order = {t: e["delete_order"] for t, e in table["providers"][a.provider]["types"].items()}
        res = residue.load()
        rep = cleanup(man, adapter, tag_value(batch), chk, owner=f"{a.run}-teardown",
                      order_fn=lambda t: order.get(t, 0), wait_lock_s=600)
        ok, why = complete(rep, man, lambda it: residue.owned_expected(res, a.provider, it))
        out = {"provider": a.provider, "run": a.run, "complete": ok and not probs, "why": why + probs,
               "intents": rep.intents, "foreign_untouched": rep.foreign}
        write_json(bo_repo() / "results" / a.run / f"teardown_{a.provider}.json", out)
        print(f"teardown {a.provider}: {'COMPLETO' if out['complete'] else 'INCOMPLETO'} " + "; ".join(out["why"]))
        return 0 if out["complete"] else 1
    except SafetyError as e:  # pragma: no cover
        print(f"teardown {a.provider}: recusado ({e.code}): {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
