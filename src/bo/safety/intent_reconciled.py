"""Gate dos módulos de nuvem: toda criação teve intenção gravada antes e remoção confirmada.

  python -I -m bo.safety.intent_reconciled MODULO [--dir PASTA_PUBLICA] [--no-sweep]

Confere na cópia pública ($BO_DATA/<MODULO>/intent_manifest.jsonl e run_manifest.jsonl):
  I1 os dois arquivos existem, sem linha rasgada, e validam no C16 (schema + regras C16-ORDER/INTENT/IDENTITY)
  I2 created/confirmed só depois de creating (ou adoção marcada "reconciliado"), e creating depois da intenção
  I3 toda intenção termina em absent, ou em purge_scheduled de um tipo previsto no EXPECTED_RESIDUE, com
     custo residual declarado não acima do máximo da intenção
  I4 a cópia pública é a projeção da privada (quando o canal privado está acessível)
  I5 a varredura final (results/<MODULO>/sweep_report.json) foi com --expect-empty, passou e é posterior ao
     último estágio
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import residue
from .common import bo_data, bo_repo, parse_iso, read_jsonl
from .manifest import RANK, Manifest, private_root


def check(module: str, pub: Path, sweep: bool = True) -> list[str]:
    errs = []
    it_p, rn_p = pub / "intent_manifest.jsonl", pub / "run_manifest.jsonl"
    if not it_p.exists() or not rn_p.exists():
        return [f"I1 manifesto público ausente em {pub}"]
    intents, p1 = read_jsonl(it_p)
    runs, p2 = read_jsonl(rn_p)
    errs += [f"I1 {x}" for x in p1 + p2]
    from bo.contracts import validate as V
    for p in (it_p, rn_p):
        r = V.validate("C16", p)
        errs += [f"I1 {p.name}: {e}" for e in r.errors[:5]]
    res = residue.load()
    by = {}
    for r in runs:
        by.setdefault(r["intent_id"], []).append(r)
    last_at = None
    for it in intents:
        rs = by.get(it["intent_id"], [])
        st = [r["stage"] for r in rs]
        for s in ("created", "confirmed"):
            if s in st:
                i = st.index(s)
                if "creating" not in st[:i] and "reconciliado" not in (rs[i].get("note") or ""):
                    errs.append(f"I2 {it['intent_id']}: {s} sem creating antes")
        if st and st[0] != "intent":
            errs.append(f"I2 {it['intent_id']}: primeiro estágio não é intent")
        final = st[-1] if st else "intent"
        if final == "purge_scheduled":
            if not any(r["provider"] == it["provider"] and r["resource_type"] == it["resource_type"]
                       for r in res["owned"]):
                errs.append(f"I3 {it['intent_id']}: agendado de tipo fora do EXPECTED_RESIDUE")
        elif final != "absent":
            errs.append(f"I3 {it['intent_id']}: termina em {final}")
        for r in rs:
            rc = (r.get("residual_cost") or {}).get("amount")
            if rc is not None and rc > it["max_residual_cost"]["amount"] + 1e-9:
                errs.append(f"I3 {it['intent_id']}: custo residual acima do máximo declarado")
            if last_at is None or parse_iso(r["at"]) > last_at:
                last_at = parse_iso(r["at"])
        ranks = [RANK[s] for s in st]
        if ranks != sorted(ranks):
            errs.append(f"I2 {it['intent_id']}: estágios fora de ordem")
    priv = private_root() / module
    if priv.exists():
        man = Manifest(module, pub, priv)
        if not man.public_consistent():
            errs.append("I4 cópia pública diferente da projeção da privada")
    if sweep:
        sp = bo_repo() / "results" / module / "sweep_report.json"
        if not sp.exists():
            errs.append("I5 sem sweep_report.json da varredura final")
        else:
            s = json.loads(sp.read_text(encoding="utf-8"))
            if not (s.get("ok") and s.get("expect_empty")):
                errs.append("I5 varredura final não passou com --expect-empty")
            elif last_at and parse_iso(s["at"]) < last_at:
                errs.append("I5 varredura anterior ao último estágio do manifesto")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_reconciled")
    ap.add_argument("module")
    ap.add_argument("--dir")
    ap.add_argument("--no-sweep", action="store_true")
    a = ap.parse_args(argv)
    pub = Path(a.dir) if a.dir else bo_data() / a.module
    errs = check(a.module, pub, sweep=not a.no_sweep)
    for e in errs:
        print("  " + e)
    print(f"intent_reconciled {a.module}: {len(errs)} problema(s) -> {'OK' if not errs else 'REPROVADO'}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
