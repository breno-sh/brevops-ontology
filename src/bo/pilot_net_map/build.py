"""Pipeline do PILOT-NET-MAP: pacote -> C09 em .staging -> validação -> árbitro -> troca sob trava.

Uso:
  python -I -m bo.pilot_net_map.build [--bundle DIR]            gera em $BO_DATA/PILOT-NET-MAP/.staging e confere
  python -I -m bo.pilot_net_map.build [--bundle DIR] --promote  idem e troca as saídas (exige a trava merge-base
                                                                 com dono PILOT-NET-MAP; ver tools/lock.sh)
O pacote padrão é $BO_DATA/PILOT-NET-GLOSS/bundle. Antes do merge do PILOT-NET-GLOSS o coordenador autorizou rodar
sobre o pacote de diagnóstico do glossarista (--bundle); o relatório registra qual pacote entrou, com o sha256.

Conferências na ordem do MAPPER_BRIEF M10: ida e volta do bo.contracts.sssom, validador oficial do C09,
bo.semantics.skos_roundtrip e o árbitro (bo.arbiter.run --frozen --check-unproven). Se o congelamento do árbitro
não confere com o código em bo/base (saída 3), o árbitro roda sem --frozen, o relatório marca frozen_ok=false e a
troca é recusada: veredito de árbitro não congelado não vira saída do módulo.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from bo.contracts import sssom as CS

from . import bundle as BU
from . import decisions as D
from .common import (MAPPING_SET_ID, MODULE, PAIRS, PREFIXES, TRANSPORTING, data_dir, default_bundle, dump_json,
                     dump_jsonl, emit, load_jsonl, now, repo, results_dir, sha256_file, staging_dir)
from .generate import decisions_log, generate

DATA_FILES = ("mapping.sssom.tsv", "decisions_log.jsonl", "build_report.json", "verdicts.jsonl", "cycles.jsonl",
              "arbiter_report.json", "run_record.json")


def _py(*args, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-B", *args], capture_output=True, text=True,
                          env=env or dict(os.environ), cwd=str(repo()), check=False)


def render(b: BU.Bundle) -> tuple[str, list[dict], dict]:
    recs, stats = generate(b)
    text = CS.write_tsv(recs, MAPPING_SET_ID, PREFIXES)
    _, back, _ = CS.read_tsv(text)
    if back != recs:
        raise SystemExit("ida e volta do bo.contracts.sssom não devolve as mesmas linhas")
    return text, recs, stats


def counts(recs: list[dict], b: BU.Bundle) -> dict:
    by_pair = collections.Counter()
    by_rel = collections.Counter()
    by_ev = collections.Counter()
    absence = collections.Counter()
    groups = projs = fixed = 0
    for r in recs:
        pair = r["claim_id"].split("-")[1]
        kind = "absence" if r.get("absence") else ("group" if r.get("group") else
                                                   ("fixed" if r.get("fixed_default") else "claim"))
        by_pair[(pair, kind)] += 1
        by_rel[r["semantic_relation"]] += 1
        by_ev[r["evidence_state"]] += 1
        if r.get("absence"):
            absence[r["absence"]["kind"]] += 1
        groups += bool(r.get("group"))
        projs += bool(r.get("projection"))
        fixed += bool(r.get("fixed_default"))
    return {"rows": len(recs), "by_pair_kind": {f"{p}|{k}": n for (p, k), n in sorted(by_pair.items())},
            "by_relation": dict(sorted(by_rel.items())), "by_evidence_state": dict(sorted(by_ev.items())),
            "absence_by_kind": dict(sorted(absence.items())), "groups": groups, "rows_with_projection": projs,
            "fixed_default": fixed, "canonical_atoms": len(b.canonical),
            "canonical_atoms_by_provider": {p: len(b.provider_atoms(p)) for p in sorted({a.split(':')[0] for a in b.canonical})}}


def run_checks(stage: Path) -> dict:
    """Os comandos dos gates G1-G3 sobre a cópia em .staging (mesmo interpretador e flags)."""
    f = stage / "mapping.sssom.tsv"
    out = {}
    v = _py("-m", "bo.contracts.validate", "correspondences", str(f))
    out["c09_validate"] = {"rc": v.returncode, "tail": (v.stdout + v.stderr).strip().splitlines()[-1:]}
    s = _py("-m", "bo.semantics.skos_roundtrip", "--file", str(f))
    out["skos_roundtrip"] = {"rc": s.returncode, "tail": (s.stdout + s.stderr).strip().splitlines()[-1:]}
    arb = ["-m", "bo.arbiter.run", "--in", str(f), "--check-unproven", "--out", str(stage)]
    a = _py(*arb[:2], "--frozen", *arb[2:])
    frozen_ok = a.returncode != 3
    if not frozen_ok:
        out["arbiter_frozen"] = {"rc": a.returncode, "tail": (a.stdout + a.stderr).strip().splitlines()[-12:]}
        a = _py(*arb)
    out["arbiter"] = {"rc": a.returncode, "frozen_ok": frozen_ok,
                      "tail": (a.stdout + a.stderr).strip().splitlines()[-2:]}
    return out


def verdict_map_sha256(vs: list[dict]) -> str:
    """Digest do mapa de vereditos (id da versão, veredito, regras, composição): não depende de decided_at,
    arbiter_sha256 nem texto. É o que se publica e o que os gates comparam, nunca o sha do arquivo."""
    from .common import sha256_bytes
    vmap = sorted((v["claim_version_id"], v["verdict"], list(v["rules"]), list(v["composition_used"] or ()))
                  for v in vs)
    return sha256_bytes(json.dumps(vmap, ensure_ascii=False).encode("utf-8"))


def verdict_summary(stage: Path, recs: list[dict]) -> dict:
    vs = load_jsonl(stage / "verdicts.jsonl")
    base = {r["claim_id"]: r for r in recs}
    c = collections.Counter()
    by_kind = collections.Counter()
    rules = collections.Counter()
    for v in vs:
        r = base.get(v["claim_id"])
        if r is None:
            by_kind[("composite", v["verdict"])] += 1
            continue
        kind = "absence" if r.get("absence") else ("group" if r.get("group") else
                                                   ("fixed" if r.get("fixed_default") else r["semantic_relation"]))
        c[v["verdict"]] += 1
        by_kind[(kind, v["verdict"])] += 1
        rules.update(v["rules"])
    sep = {"claims": collections.Counter(), "absences": collections.Counter(), "composites": collections.Counter()}
    for (k, v), n in by_kind.items():
        sep["absences" if k == "absence" else "composites" if k == "composite" else "claims"][v] += n
    return {"verdicts": dict(sorted(c.items())),
            "verdicts_separated": {k: dict(sorted(x.items())) for k, x in sep.items()},
            "by_kind": {f"{k}|{v}": n for (k, v), n in sorted(by_kind.items())},
            "rules": dict(sorted(rules.items())),
            "verdict_map_sha256": verdict_map_sha256(vs)}


def _lock_held() -> bool:
    d = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "locks" / "merge-base" / "owner"
    return d.exists() and f"owner={MODULE}" in d.read_text(encoding="utf-8")


ARBITER_FILES = ("verdicts.jsonl", "cycles.jsonl", "arbiter_report.json", "run_record.json")


def promote(stage: Path, with_verdicts: bool) -> list[str]:
    dest = data_dir()
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for name in DATA_FILES:
        if name in ARBITER_FILES and not with_verdicts:
            continue
        src = stage / name
        if not src.exists():
            continue
        tmp = dest / f".{name}.swap"
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest / name)
        moved.append(name)
    return moved


def write_results(rep: dict) -> None:
    rd = results_dir()
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "report.json").write_text(dump_json(rep), encoding="utf-8")


def write_manifest() -> Path:
    """results/PILOT-NET-MAP/MANIFEST.sha256 (formato do shasum, caminhos relativos à raiz do repositório). As
    saídas em $BO_DATA entram por sha256 no report.json (mapping_sha256, decisions_log_sha256)."""
    rd = results_dir()
    files = sorted(p for p in rd.iterdir() if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [f"{sha256_file(p)}  {p.relative_to(repo())}" for p in files]
    m = rd / "MANIFEST.sha256"
    m.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pilot_net_map.build")
    ap.add_argument("--bundle", default=None)
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--manifest", action="store_true", help="só regrava results/PILOT-NET-MAP/MANIFEST.sha256")
    a = ap.parse_args(argv)
    if a.manifest:
        emit(f"[{now()}] build: manifesto {write_manifest()}")
        return 0
    broot = Path(a.bundle) if a.bundle else default_bundle()
    try:
        b = BU.load(broot)
    except BU.BundleError as e:
        emit(f"[{now()}] build: pacote recusado: {e}")
        return 2
    text, recs, stats = render(b)
    stage = staging_dir()
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    (stage / "mapping.sssom.tsv").write_text(text, encoding="utf-8")
    log = decisions_log(b, recs)
    (stage / "decisions_log.jsonl").write_text(dump_jsonl(log), encoding="utf-8")
    checks = run_checks(stage)
    vsum = verdict_summary(stage, recs)
    official = broot.resolve() == default_bundle().resolve()
    rep = {"schema": "bo.pilot_net_map_report/1", "module": MODULE, "generated_at": now(), "timezone": "America/Recife",
           "mapping_date": D.MAPPING_DATE, "mapping_set_id": MAPPING_SET_ID,
           "bundle": {"path": str(broot), "official": official, "form": b.info["form"],
                      "manifest_sha256": b.info["manifest_sha256"], "files": b.info["files"]},
           "mapping_sha256": sha256_file(stage / "mapping.sssom.tsv"),
           "decisions_log_sha256": sha256_file(stage / "decisions_log.jsonl"),
           "counts": counts(recs, b), "skipped_pairings": stats["skipped_pairings"],
           "missing_members": stats["missing_members"], "checks": checks, "arbiter": vsum,
           "candidates": {"n": len(log), "taken_as_direct": sum(1 for x in log if x["taken_as_direct"])}}
    (stage / "build_report.json").write_text(dump_json(rep), encoding="utf-8")
    ok = (checks["c09_validate"]["rc"] == 0 and checks["skos_roundtrip"]["rc"] == 0
          and checks["arbiter"]["rc"] == 0)
    emit(f"[{now()}] build: {len(recs)} linha(s) em {len(PAIRS)} pares; C09 rc={checks['c09_validate']['rc']}, "
         f"SKOS rc={checks['skos_roundtrip']['rc']}, árbitro rc={checks['arbiter']['rc']} "
         f"(congelado {'confere' if checks['arbiter']['frozen_ok'] else 'NÃO confere'}); vereditos {vsum['verdicts']}; "
         f"pacote {'oficial' if official else 'NÃO oficial: ' + str(broot)}")
    if not a.promote:
        return 0 if ok else 1
    if checks["c09_validate"]["rc"] != 0 or checks["skos_roundtrip"]["rc"] != 0:
        emit("  troca recusada: C09 ou ida e volta SKOS reprovou")
        return 1
    if not official:
        emit("  troca recusada: pacote não oficial (o PILOT-NET-GLOSS ainda não entrou em bo/base)")
        return 4
    if not _lock_held():
        emit("  troca recusada: rode dentro de tools/lock.sh with merge-base --owner PILOT-NET-MAP")
        return 5
    frozen = checks["arbiter"]["frozen_ok"] and checks["arbiter"]["rc"] == 0
    moved = promote(stage, with_verdicts=frozen)
    write_results(rep)
    emit(f"  trocado sob a trava merge-base: {', '.join(moved)}")
    if not frozen:
        emit("  vereditos NÃO trocados: árbitro em bo/base não é o congelado ou o C21 recusa a saída dele "
             "(results/PILOT-NET-MAP/CONTRACT_CHANGE.txt)")
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
