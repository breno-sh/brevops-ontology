"""Conferências do gate do PILOT-NET-MAP (gates/PILOT-NET-MAP.sh).

Uso: python -I -m bo.pilot_net_map.verify [--dir DIR] [--bundle DIR]
  --dir     onde estão as saídas (padrão $BO_DATA/PILOT-NET-MAP; o .staging serve antes da troca)
  --bundle  pacote (padrão: o registrado no build_report.json da pasta)
Confere, nesta ordem, e sai 1 na primeira classe que reprovar (todas são impressas):
  regen       o pacote confere com o manifesto e a geração refeita dá os mesmos bytes do mapping.sssom.tsv
  exhaustive  todo átomo canônico dos dois lados de cada par aparece numa linha do par (sujeito, objeto, variável
              de grupo) — as correspondências que transportam, ou a ausência tipada
  bundle_only todo átomo citado (sujeito, objeto, variável, projeção, guarda) é do pacote
  registry    funções, passos de grupo e operadores de guarda só do registro fechado (transforms/)
  orientation fora das ausências, sujeito = primeiro provedor do par e objeto = segundo; claim_id no par certo
  verdicts    verdicts.jsonl válido no C21 e com o mesmo mapa de vereditos que o árbitro dá de novo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from bo.contracts import sssom as CS

from . import bundle as BU
from .build import render
from .common import NO_TERM, PAIRS, TRANSPORTING, data_dir, default_bundle, emit, load_jsonl, now, provider_of, repo

GUARD_OPS = None


def _registry() -> tuple[set, set]:
    reg = yaml.safe_load((repo() / "transforms" / "transforms.yaml").read_text(encoding="utf-8"))
    sections = [reg] if isinstance(reg, list) else [v for v in reg.values() if isinstance(v, list)]
    names = {x["name"] for items in sections for x in items if isinstance(x, dict) and "name" in x}
    gram = json.loads((repo() / "transforms" / "conditions.grammar.json").read_text(encoding="utf-8"))
    return names, set(gram["operators"])


def _atom_from_field(f: str) -> str:
    p, rest = f.split(":", 1)
    t, path = rest.split(".", 1)
    return f"{p}:{t}:{path}"


def _rows_atoms(r: dict) -> set:
    xs = set()
    for k in ("subject_id", "object_id"):
        if r.get(k) and r[k] != NO_TERM:
            xs.add(r[k])
    for v in (r.get("group") or {}).get("variables") or []:
        xs.add(_atom_from_field(v["field"]))
    for p in r.get("projection") or []:
        xs.add(p["field"])
    return xs


def check_exhaustive(recs, b) -> list[str]:
    bad = []
    for pair, (P, Q) in PAIRS.items():
        seen = set()
        for r in recs:
            if r["claim_id"].split("-")[1] != pair:
                continue
            if r["semantic_relation"] in TRANSPORTING or r.get("absence"):
                seen |= _rows_atoms(r)
        for prov in (P, Q):
            miss = [a for a in b.provider_atoms(prov) if a not in seen]
            if miss:
                bad.append(f"{pair}: {len(miss)} átomo(s) de {prov} sem linha (ex.: {miss[0]})")
    return bad


def check_bundle_only(recs, b) -> list[str]:
    bad = set()
    for r in recs:
        for x in _rows_atoms(r):
            if x.count(":") == 1:
                if not b.has_type(x):
                    bad.add(f"tipo fora do pacote: {x}")
            elif not b.has_atom(x):
                bad.add(f"átomo fora do pacote: {x}")
        for g in (r.get("guard") or {}).get("all") or []:
            role, path = g["term"].split(".", 1)
            if path in ("region", "edition", "provider_version"):
                continue
            side = r["subject_id"] if role == "subject" else r["object_id"]
            if side == NO_TERM:
                bad.add(f"{r['claim_id']}: guarda no lado da ausência")
                continue
            rt = ":".join(side.split(":")[:2])
            atom = f"{rt}:{path}"
            block_ok = any(a.startswith(f"{rt}:{path}.") for a in b.canonical)
            if not (b.has_atom(atom) or block_ok):
                bad.add(f"{r['claim_id']}: termo de guarda fora do pacote: {atom}")
    return sorted(bad)


def check_registry(recs) -> list[str]:
    names, ops = _registry()
    bad = set()
    for r in recs:
        fn = r.get("translation_fn")
        for f in (fn if isinstance(fn, list) else [fn] if fn else []):
            if f["name"] not in names:
                bad.add(f"{r['claim_id']}: função fora do registro: {f['name']}")
        for s in (r.get("group") or {}).get("steps") or []:
            if s["name"] not in names:
                bad.add(f"{r['claim_id']}: passo fora do registro: {s['name']}")
        for p in r.get("projection") or []:
            if p["extractor"]["name"] not in names:
                bad.add(f"{r['claim_id']}: extrator fora do registro: {p['extractor']['name']}")
        for g in (r.get("guard") or {}).get("all") or []:
            if g["op"] not in ops:
                bad.add(f"{r['claim_id']}: operador de guarda fora da gramática: {g['op']}")
    return sorted(bad)


def check_orientation(recs) -> list[str]:
    bad = []
    for r in recs:
        pair = r["claim_id"].split("-")[1]
        if pair not in PAIRS:
            bad.append(f"{r['claim_id']}: par desconhecido")
            continue
        P, Q = PAIRS[pair]
        if r.get("absence"):
            if provider_of(r["subject_id"]) not in (P, Q) or r["object_id"] != NO_TERM:
                bad.append(f"{r['claim_id']}: ausência fora do par")
            continue
        if provider_of(r["subject_id"]) != P or provider_of(r["object_id"]) != Q:
            bad.append(f"{r['claim_id']}: orientação {provider_of(r['subject_id'])}->{provider_of(r['object_id'])} "
                       f"no par {pair} ({P}->{Q})")
    return bad


def check_verdicts(d: Path) -> list[str]:
    from bo.arbiter import engine
    from bo.arbiter.inputs import load as aload
    from bo.arbiter.run import validate_c21
    vp = d / "verdicts.jsonl"
    if not vp.exists():
        return [f"{vp}: ausente"]
    bad = [f"C21: {e}" for e in validate_c21(vp)[:5]]
    got = engine.verdict_map(load_jsonl(vp))
    res = engine.arbitrate(aload([str(d / "mapping.sssom.tsv")]), decided_at=now(), arbiter_sha256="0" * 64)
    want = engine.verdict_map(res["verdicts"])
    if got != want:
        diff = sorted(set(got.items()) ^ set(want.items()))[:3]
        bad.append(f"vereditos gravados diferem do árbitro rodado de novo ({len(set(got) ^ set(want))} id(s); {diff})")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_net_map.verify")
    ap.add_argument("--dir")
    ap.add_argument("--bundle")
    ap.add_argument("--skip-verdicts", action="store_true")
    a = ap.parse_args(argv)
    d = Path(a.dir) if a.dir else data_dir()
    f = d / "mapping.sssom.tsv"
    if not f.exists():
        emit(f"[{now()}] verify: {f} ausente")
        return 1
    rep = json.loads((d / "build_report.json").read_text(encoding="utf-8")) if (d / "build_report.json").exists() else {}
    broot = Path(a.bundle) if a.bundle else Path((rep.get("bundle") or {}).get("path") or default_bundle())
    out: dict[str, list[str]] = {}
    try:
        b = BU.load(broot)
        text, recs, _ = render(b)
        out["regen"] = [] if text == f.read_text(encoding="utf-8") else ["geração refeita difere do mapping.sssom.tsv"]
    except BU.BundleError as e:
        emit(f"[{now()}] verify: pacote recusado: {e}")
        return 1
    _, recs_file, _ = CS.read_tsv(f.read_text(encoding="utf-8"))
    out["exhaustive"] = check_exhaustive(recs_file, b)
    out["bundle_only"] = check_bundle_only(recs_file, b)
    out["registry"] = check_registry(recs_file)
    out["orientation"] = check_orientation(recs_file)
    if not a.skip_verdicts:
        out["verdicts"] = check_verdicts(d)
    rc = 0
    for k, errs in out.items():
        emit(f"  {'ok   ' if not errs else 'FALHA'} {k}: {len(errs)} problema(s)")
        for e in errs[:8]:
            emit(f"        {e}")
        rc = rc or (1 if errs else 0)
    emit(f"[{now()}] verify {d}: {len(recs_file)} linha(s); pacote {broot}; "
         f"{'PASS' if rc == 0 else 'FAIL'}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
