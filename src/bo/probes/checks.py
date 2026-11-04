"""Checagens dos módulos que usam o kit (nenhuma julga comportamento; o julgamento é só do PROBE-JOIN).

  supervisor_heartbeat ID   (gate do PROBE-*) toda execução de janela longa teve heartbeat contínuo: maior
                            intervalo sem batida aceita <= carência; execução sem isso tem as repetições como erro
  join_complete             (gate do PROBE-JOIN) todo pair_case_id observado tem julgamento; julgamento que não é
                            censura/infra/suporte cita os dois lados (A e B) e eles existem
  negative_controls         (gate do PROBE-JOIN) observação com controle negativo falho => o par é INFRA_ERROR
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

from .common import ProbeError, data, read_jsonl

NON_COMPARATIVE = {"NOT_OBSERVED_IN_WINDOW", "INFRA_ERROR", "PROTOCOL_UNSUPPORTED", "UNKNOWN"}


def heartbeat_problems(trace: list[dict]) -> list[str]:
    out = []
    for t in trace:
        hb = t.get("heartbeat")
        who = f"{t.get('pair_case_id')}/{t.get('side')}/{t.get('role')}/r{t.get('rep')}"
        if hb is None:
            out.append(f"{who}: rastro sem registro de heartbeat")
            continue
        if not hb.get("required"):
            continue
        if hb.get("beats", 0) < 1:
            if t.get("result") != "error":
                out.append(f"{who}: janela longa sem nenhuma batida e resultado {t.get('result')}")
        elif hb["max_gap_s"] > hb["grace_s"] and t.get("result") != "error":
            out.append(f"{who}: {hb['max_gap_s']:.0f} s sem heartbeat (carência {hb['grace_s']:.0f} s) e resultado "
                       f"{t.get('result')}")
    return out


def main_supervisor_heartbeat(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.probes.supervisor_heartbeat")
    ap.add_argument("module", help="ID do módulo PROBE-* (lê $BO_DATA/<ID>/probe_trace.jsonl)")
    ap.add_argument("--dir", help="pasta com observations.jsonl e probe_trace.jsonl (padrão: $BO_DATA/<ID>)")
    a = ap.parse_args(argv)
    d = Path(a.dir) if a.dir else data() / a.module
    tf, of = d / "probe_trace.jsonl", d / "observations.jsonl"
    if not tf.is_file() or not of.is_file():
        print(f"supervisor_heartbeat: {a.module}: sem observations.jsonl/probe_trace.jsonl (nada rodou)")
        return 1
    trace, obs = read_jsonl(tf), read_jsonl(of)
    probs = heartbeat_problems(trace)
    seen = {(t["pair_case_id"], t["side"]) for t in trace}
    for o in obs:
        if (o["pair_case_id"], o["side"]) not in seen:
            probs.append(f"{o['observation_id']}: observação sem rastro")
    long_ = sum(1 for t in trace if (t.get("heartbeat") or {}).get("required"))
    for p in probs:
        print("  PROBLEMA:", p)
    print(f"supervisor_heartbeat: {a.module}: {len(trace)} repetição(ões) no rastro, {long_} de janela longa; "
          + ("OK" if not probs else "REPROVADO"))
    return 0 if not probs else 1


def _load_obs(patterns: list[str]) -> dict[str, dict]:
    out = {}
    for pat in patterns:
        for f in sorted(glob.glob(pat)):
            for o in read_jsonl(Path(f)):
                if o["observation_id"] in out:
                    raise ProbeError(f"observation_id repetido entre módulos: {o['observation_id']}", "DUPLICATE")
                out[o["observation_id"]] = o
    return out


def _join_args(prog: str, argv):
    ap = argparse.ArgumentParser(prog=prog)
    ap.add_argument("--judgements", default=str(data() / "PROBE-JOIN" / "pair_judgements.jsonl"))
    ap.add_argument("--observations", nargs="*", default=[str(data() / "PROBE-*" / "observations.jsonl")])
    ap.add_argument("--cases", nargs="*", default=[str(data() / "DEPSAMPLE" / "probe_cases_*.jsonl")],
                    help="casos sorteados (pair_case_id), quando existirem")
    return ap.parse_args(argv)


def join_problems(judgements: list[dict], obs: dict[str, dict], case_ids: set[str]) -> list[str]:
    out = []
    by_pair: dict[str, list[dict]] = {}
    for j in judgements:
        by_pair.setdefault(j["pair_case_id"], []).append(j)
    observed_pairs = {o["pair_case_id"] for o in obs.values()}
    for pc in sorted(observed_pairs | case_ids):
        js = by_pair.get(pc) or []
        if len(js) != 1:
            out.append(f"{pc}: {len(js)} julgamento(s) (esperado 1)")
            continue
        j = js[0]
        val = j["outcome"]["value"]
        sides = {}
        for side in ("A", "B"):
            o = obs.get(j["observations"][side])
            if o is not None and o["side"] == side and o["pair_case_id"] == pc:
                sides[side] = o
        if val not in NON_COMPARATIVE and len(sides) != 2:
            out.append(f"{pc}: {val} sem os dois lados observados")
    return out


def main_join_complete(argv=None) -> int:
    a = _join_args("bo.probes.join_complete", argv)
    jf = Path(a.judgements)
    if not jf.is_file():
        print(f"join_complete: {jf.name} ausente")
        return 1
    obs = _load_obs(a.observations)
    cases = set()
    for pat in a.cases:
        for f in sorted(glob.glob(pat)):
            cases |= {c["pair_case_id"] for c in read_jsonl(Path(f)) if c.get("pair_case_id")}
    probs = join_problems(read_jsonl(jf), obs, cases)
    for p in probs:
        print("  PROBLEMA:", p)
    print(f"join_complete: {len(obs)} observação(ões), {len(cases)} caso(s) sorteado(s); "
          + ("OK" if not probs else "REPROVADO"))
    return 0 if not probs else 1


def negative_control_problems(judgements: list[dict], obs: dict[str, dict]) -> list[str]:
    out = []
    for j in judgements:
        bad = [s for s in ("A", "B") if (obs.get(j["observations"][s]) or {}).get("negative_control_ok") is False]
        missing = [s for s in ("A", "B") if j["observations"][s] not in obs]
        if (bad or missing) and j["outcome"]["value"] != "INFRA_ERROR":
            why = (f"controle negativo falho no lado {','.join(bad)}" if bad else
                   f"observação do lado {','.join(missing)} ausente")
            out.append(f"{j['pair_case_id']}: {why} e desfecho {j['outcome']['value']} (esperado INFRA_ERROR)")
    return out


def main_negative_controls(argv=None) -> int:
    a = _join_args("bo.probes.negative_controls", argv)
    jf = Path(a.judgements)
    if not jf.is_file():
        print(f"negative_controls: {jf.name} ausente")
        return 1
    obs = _load_obs(a.observations)
    js = read_jsonl(jf)
    probs = negative_control_problems(js, obs)
    for p in probs:
        print("  PROBLEMA:", p)
    print(f"negative_controls: {len(js)} julgamento(s); " + ("OK" if not probs else "REPROVADO"))
    return 0 if not probs else 1
