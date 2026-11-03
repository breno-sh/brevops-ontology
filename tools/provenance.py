#!/usr/bin/env python3
"""Gravador de proveniência de agente (C17 summary.json: agent_provenance e sources).

  provenance.py record ID --brief ARQ [--model M] [--param k=v ...] [--input P ...]
                        [--source 'uri|licença|transformação' ...] [--note T] [--out ARQ]
  provenance.py verify ID [--file ARQ]     brief e entradas ainda batem com o registrado
  provenance.py show ID
  provenance.py --selftest

A proveniência vai para os metadados do dataset (results/ID/summary.json), nunca para o commit.
Sem --input, as entradas são as do módulo no catálogo. Conteúdo Withheld nunca é registrado.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import argparse  # noqa: E402
import subprocess  # noqa: E402

from bo.repo import catalog, core, fixtures, receipts  # noqa: E402

DEFAULT_MODEL = "claude-opus-5-5"
ME = str(Path(__file__).resolve())


def summary_path(mid: str, out: str | None) -> Path:
    return Path(out) if out else core.bo_repo() / "results" / mid / "summary.json"


def parse_source(s: str) -> dict:
    parts = [x.strip() for x in s.split("|")]
    if len(parts) != 3 or not all(parts):
        raise core.BoError(f"--source precisa de 'uri|licença|transformação': {s!r}", code=2)
    return {"uri": parts[0], "license": parts[1], "transformation": parts[2]}


def record(a) -> int:
    repo = core.bo_repo()
    cat = catalog.load(repo)
    mod = cat.get(a.module, allow_synthetic=True)
    brief = Path(a.brief)
    if not brief.is_file():
        raise core.BoError(f"brief não encontrado: {brief}")
    params = {}
    for kv in a.param or []:
        k, sep, v = kv.partition("=")
        if not sep:
            raise core.BoError(f"--param precisa de k=v: {kv!r}", code=2)
        params[k] = v
    inputs = []
    pats = a.input if a.input else [i for i in mod.inputs if catalog.is_file_input(i)]
    for pat in pats:
        hits = receipts.expand_existing(cat, pat, mod.id, repo) if (pat.startswith("$BO_") or "*" in pat) \
            else ([Path(pat)] if Path(pat).exists() else [])
        if not hits:
            raise core.BoError(f"entrada não existe: {pat}")
        for h in hits:
            e = core.hash_path(h)
            inputs.append({"path": receipts.portable(h, repo), "kind": e["kind"], "sha256": e["sha256"]})
    p = summary_path(mod.id, a.out)
    summ = core.read_json(p) or {}
    summ.update({"schema": "bo.summary/1", "contract": "C17", "contract_version": "3.0.0", "module": mod.id,
                 "generated_at": core.now()})
    summ["agent_provenance"] = {
        "model_id": a.model, "brief_path": str(brief), "brief_sha256": core.sha256_file(brief),
        "params": params, "inputs": inputs, "recorded_at": core.now(),
    }
    if a.source:
        summ["sources"] = [parse_source(s) for s in a.source]
    else:
        summ.setdefault("sources", [])
    if a.note:
        summ["notes"] = a.note
    core.write_json(p, summ)
    core.emit(f"[{core.now()}] proveniência de {mod.id} gravada em {p}: modelo {a.model}, "
              f"brief {summ['agent_provenance']['brief_sha256'][:12]}…, {len(inputs)} entrada(s)")
    return 0


def verify(mid: str, f: str | None) -> int:
    repo = core.bo_repo()
    p = summary_path(mid, f)
    summ = core.read_json(p)
    if summ is None:
        raise core.BoError(f"{p} não existe (rode provenance.py record {mid} ...)")
    ap = summ.get("agent_provenance") or {}
    probs = []
    for k in ("model_id", "brief_sha256", "params", "inputs"):
        if k not in ap:
            probs.append(f"agent_provenance sem {k}")
    b = Path(ap.get("brief_path", ""))
    if not b.is_file():
        probs.append(f"brief registrado não existe: {b}")
    elif core.sha256_file(b) != ap.get("brief_sha256"):
        probs.append("brief mudou depois do registro (sha256 não bate)")
    for e in ap.get("inputs", []):
        cur = core.hash_path(receipts.resolve(e["path"], repo))
        if cur["sha256"] != e.get("sha256"):
            probs.append(f"entrada mudou: {e['path']}")
    if not isinstance(summ.get("sources"), list):
        probs.append("sources ausente")
    for s in summ.get("sources") or []:
        if not all(s.get(k) for k in ("uri", "license", "transformation")):
            probs.append(f"source incompleta: {s}")
    core.emit(f"[{core.now()}] proveniência {mid}: {p}")
    for x in probs:
        core.emit(f"  FAIL {x}")
    core.emit("RESULTADO: " + ("OK" if not probs else "REPROVADO"))
    return 1 if probs else 0


def selftest() -> int:
    ck = fixtures.Checks("provenance.py --selftest")
    with fixtures.sandbox([fixtures.module("A", inputs=["$BO_DATA/X/in.txt"])]) as root:
        data = root / "data"
        (data / "X").mkdir()
        (data / "X" / "in.txt").write_text("entrada\n", encoding="utf-8")
        brief = root / "brief.txt"
        brief.write_text("brief do teste\n", encoding="utf-8")
        run = lambda *a: subprocess.run([sys.executable, "-I", ME, *a], capture_output=True, text=True)  # noqa: E731
        r = run("record", "A", "--brief", str(brief), "--param", "effort=alto",
                "--source", "file:in.txt|interno|lido sem transformação")
        ck.expect("record sai 0", r.returncode == 0, r.stderr[-200:])
        s = core.read_json(root / "repo" / "results" / "A" / "summary.json") or {}
        ap = s.get("agent_provenance", {})
        ck.expect("model_id padrão registrado", ap.get("model_id") == DEFAULT_MODEL)
        ck.expect("sha do brief registrado", ap.get("brief_sha256") == core.sha256_file(brief))
        ck.expect("parâmetros e entradas do catálogo registrados",
                  ap.get("params") == {"effort": "alto"} and ap.get("inputs", [{}])[0].get("path") == "$BO_DATA/X/in.txt")
        ck.expect("sources com uri, licença e transformação", s.get("sources", [{}])[0].get("license") == "interno")
        ck.expect("verify passa sem mudança", run("verify", "A").returncode == 0)
        brief.write_text("brief alterado\n", encoding="utf-8")
        ck.expect("verify reprova se o brief mudou", run("verify", "A").returncode == 1)
        r = run("record", "A", "--brief", str(brief), "--input", "$BO_DATA/X/nao-existe")
        ck.expect("entrada inexistente reprova", r.returncode != 0)
    return ck.report()


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    ap = argparse.ArgumentParser(prog="provenance.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("module")
    r.add_argument("--brief", required=True)
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--param", action="append")
    r.add_argument("--input", action="append")
    r.add_argument("--source", action="append")
    r.add_argument("--note")
    r.add_argument("--out")
    v = sub.add_parser("verify")
    v.add_argument("module")
    v.add_argument("--file")
    s = sub.add_parser("show")
    s.add_argument("module")
    a = ap.parse_args()
    if a.cmd == "record":
        return record(a)
    if a.cmd == "verify":
        return verify(a.module, a.file)
    if a.cmd == "show":
        p = summary_path(a.module, None)
        print(p.read_text(encoding="utf-8") if p.exists() else f"{p} não existe")
        return 0
    return 2


if __name__ == "__main__":
    core.run_main(main)
