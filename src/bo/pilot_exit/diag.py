"""Diagnóstico das falhas de E2 de uma execução registrada, SEM rodar a avaliação de novo.

  python -I -m bo.pilot_exit.diag e2 --out ARQ_BRUTO

Não é tentativa: não roda os gates do E2E, não grava evidência nem livro de tentativas. Decifra pela VM (D15,
pipe ssh) só para reabrir os itens que a execução registrada já marcou como falha de E2, põe a retida na cópia
congelada do MESMO commit avaliado (sha conferido), e chama, na caixa sem rede e sem escrita fora de $BO_TMP,
só a decomposição do código congelado e o comparador do oráculo nesses itens. O arquivo bruto (com conteúdo da
retida) fica em $BO_TMP e é apagado por quem o lê; para o repositório vai só a classe e a regra (DIAG_T3.json).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import common as C, frozen, materialize, runner, unseal

NET_PROBE = r'''
import json, sys
from bo.pilot.net import decompose as DC, oracle as O
no = O.load()
from net_oracle import decomposing as ND
ids, pairs, out = json.loads(sys.argv[1]), json.loads(sys.argv[2]), {"fixtures": {}, "pairs": []}
fxs = {f["fixture_id"]: f for f in O.fixtures(__import__("pathlib").Path(sys.argv[3]), None)}
def slim(u):
    return {k: u.get(k) for k in ("domain_unit", "kind", "accepted_kinds", "parent", "occurrence", "tf", "evidence",
                                  "missing", "unknown", "dispute", "kind_without_dispute", "grain", "reasons", "rule",
                                  "rules", "source") if k in u}
for fid in ids:
    fx = fxs[fid]
    units = DC.decompose(fx)
    exp = ND.apply_disputes(fx["expected"]["decomposition"])
    cmp = no.compare_decomposition(fx["expected"]["decomposition"], units)
    e, a = ND.normalize(exp), ND.normalize(units)
    out["fixtures"][fid] = {"provider": fx["provider"], "case": fx["case"], "cmp": cmp,
                            "expected": {k: slim(v) for k, v in e.items()}, "actual": {k: slim(v) for k, v in a.items()}}
for x, y in pairs:
    ua, ub = DC.decompose(fxs[x]), DC.decompose(fxs[y])
    sa = {ND._key(u): u for u in ua}; sb = {ND._key(u): u for u in ub}
    out["pairs"].append({"pair": [x, y], "only_a": [slim(sa[k]) for k in sorted(set(sa) - set(sb))],
                         "only_b": [slim(sb[k]) for k in sorted(set(sb) - set(sa))],
                         "kind_diff": [[slim(sa[k]), slim(sb[k])] for k in sorted(set(sa) & set(sb)) if sa[k]["kind"] != sb[k]["kind"]]})
json.dump(out, open(sys.argv[4], "w"), ensure_ascii=False, sort_keys=True, default=str)
'''

STO_PROBE = r'''
import json, sys
from bo.pilot.sto import common as C, evaluate as E, lift as L, pipeline as PL
ctx = PL.prepare(out_dir=C.tmp_dir() / "diag_owl")
g = E.grain(ctx)
exp = C.read_json(C.repo() / "pilot" / "sto" / "expected_answers.json")
out = {"mismatches": []}
for m in g["decomposition_mismatches"]:
    f = exp["fixtures"][m["fixture_id"]]
    fx = C.read_json(C.repo() / f["file"])
    dec = L.decomposition(L.lift(fx, ctx.claims, ctx.evidence))
    out["mismatches"].append({"fixture_id": m["fixture_id"], "case": f["case"], "provider": f["provider"],
                              "polarity": f["polarity"], "unit": m["unit"], "expect": m["expect"], "got": m["got"],
                              "actual_unit": dec.get(m["unit"]), "summary": f.get("summary"),
                              "units_present": sorted(dec)})
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, sort_keys=True, default=str)
'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_exit.diag")
    ap.add_argument("what", choices=("e2",))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    root = C.repo()
    rec = C.read_json(C.results_dir(root) / "heldout_run.json") or {}
    work = C.tmp() / "diag"
    if work.exists():
        shutil.rmtree(work)
    raw = {}
    try:
        for s in ("net", "sto"):
            ev = C.read_json(C.run_data_dir() / s / "evidence.json") or {}
            g = ev.get("grain") or {}
            if not g.get("mismatches") and not g.get("invariance_failures"):
                continue
            ident = frozen.identify(s, root)
            if ident["code_sha256"] != (rec.get("frozen_code") or {}).get(s, {}).get("code_sha256"):
                C.say(f"diag: {s}: código em bo/base ≠ código da execução registrada; não diagnostico código diferente")
                return 2
            mid = C.SLICES[s]["e2e"]
            repo_c = frozen.export(root, (rec["frozen_code"][s])["base_head"], work / s / "repo")
            data_root = runner.overlay(C.data(), C.tmp() / "d", mid)
            opened = unseal.open_slice(s, root=root)
            materialize.materialize(s, opened["bundle"], repo_c)
            del opened["bundle"]
            out = work / s / "out"
            out.mkdir(parents=True)
            probe = out / "probe.py"
            res_p = out / "raw.json"
            if s == "net":
                probe.write_text(NET_PROBE, encoding="utf-8")
                cmd = (f"python -I {probe} '{json.dumps(g.get('mismatch_ids', []))}' "
                       f"'{json.dumps(g.get('packaging_failures', []))}' {repo_c / 'pilot/net/fixtures_calib'} {res_p}")
            else:
                probe.write_text(STO_PROBE, encoding="utf-8")
                cmd = f"python -I {probe} {res_p}"
            r = runner.run_commands([cmd], repo_c, data_root, mid, out / "logs",
                                    tmp_root=data_root / "tmp" / mid if s == "sto" else None)
            if r[0]["rc"] != 0:
                C.say(f"diag: {s}: sonda saiu {r[0]['rc']}: " + (out / "logs" / "01.err").read_text()[-600:])
                return 1
            raw[s] = json.loads(res_p.read_text(encoding="utf-8"))
    finally:
        for d in (work, C.tmp() / "d", C.tmp() / "t"):
            shutil.rmtree(d, ignore_errors=True)
    Path(a.out).write_text(json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    C.say(f"diag: bruto em {C.portable(Path(a.out))} (conteúdo retido: apagar depois de ler; nunca no git)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
