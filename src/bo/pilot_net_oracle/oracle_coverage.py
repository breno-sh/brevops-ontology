"""G2: python -I -m bo.pilot.oracle_coverage --slice net (o despachante chega aqui).

Reprova se: algum caso obrigatório não tem positivo, negativo e desconhecido na calibração e nas retidas;
alguma direção não tem positivo, negativo e desconhecido na calibração ou contraexemplo retido; retidas < 30%
(por caso, no total de fixtures e no total de traduções); o envelope selado não existe, não confere com o índice,
não é para o certificado D15 ou está dentro de um repositório git; há fixture retida em claro no repositório;
alguma resposta de calibração não é reproduzida pelo avaliador. Relatório em $BO_DATA/PILOT-NET-ORACLE/coverage.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .build import generate
from .coverage_lib import check, summarize
from .seal import data_dir, now, repo, sealed_dir, verify


def _inside_git(p: Path) -> bool:
    r = subprocess.run(["git", "-C", str(p), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def run(slice_: str) -> dict:
    errs = []
    if slice_ != "net":
        return {"errors": [f"fatia {slice_!r}: este módulo só responde por net"]}
    R = repo()
    exp = json.loads((R / "pilot/net/expected_answers.json").read_text(encoding="utf-8"))
    idx = json.loads((R / "pilot/net/oracle/sealed_index.json").read_text(encoding="utf-8"))
    errs += ["selagem: " + e for e in verify()]
    sd = sealed_dir().resolve()
    if _inside_git(sd):
        errs.append(f"selagem: {sd} está dentro de um repositório git")
    if str(sd).startswith(str(R.resolve())):
        errs.append("selagem: envelope dentro do repositório de trabalho")
    # nada retido em claro no repositório
    for p in (R / "pilot/net").rglob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and d.get("split") == "retained":
            errs.append(f"fixture retida em claro: {p.relative_to(R)}")
    for p in (R / "pilot/net/fixtures_calib").rglob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("split") != "calib":
            errs.append(f"{p.relative_to(R)}: split {d.get('split')!r} em fixtures_calib")
    # cobertura
    cal, ret = exp["counts"]["calib"], idx["counts"]
    errs += ["cobertura: " + e for e in check(cal, ret)]
    # o avaliador reproduz as respostas escritas (calibração e exemplos)
    g = generate(check_only=True)
    errs += ["gabarito: " + e for e in g["errors"]]
    if summarize_from_files(R) != cal:
        errs.append("contagens de expected_answers.json não batem com fixtures_calib/")
    rep = {"schema": "bo.pilot_net.coverage/1", "module": "PILOT-NET-ORACLE", "slice": slice_, "at": now(),
           "errors": errs, "calib": cal, "retained": ret,
           "retained_fraction": {
               "fixtures": round(ret["fixtures_in_cases"] / (ret["fixtures_in_cases"] + cal["fixtures_in_cases"]), 3),
               "translations": round(ret["translations_total"] / (ret["translations_total"] + cal["translations_total"]), 3)},
           "sealed": {"envelope": idx["envelope"], "envelope_sha256": idx["envelope_sha256"],
                      "recipient_fingerprint": idx["recipient"]["fingerprint_sha256"]}}
    return rep


def summarize_from_files(R: Path) -> dict:
    fx, tr = [], []
    for p in sorted((R / "pilot/net/fixtures_calib").glob("*.json")):
        fx.append(json.loads(p.read_text(encoding="utf-8")))
    for p in sorted((R / "pilot/net/fixtures_calib/translations").glob("*.json")):
        tr.append(json.loads(p.read_text(encoding="utf-8")))
    return summarize(fx, tr)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="bo.pilot.oracle_coverage")
    ap.add_argument("--slice", required=True)
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(list(sys.argv[1:] if argv is None else argv))
    rep = run(a.slice)
    out = data_dir() / "coverage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for e in rep["errors"]:
        print("ERRO", e)
    if "retained_fraction" in rep:
        print(f"[{rep['at']}] oracle_coverage net: calibração {rep['calib']['fixtures_in_cases']} fixtures/"
              f"{rep['calib']['translations_total']} traduções; retidas {rep['retained']['fixtures_in_cases']}/"
              f"{rep['retained']['translations_total']} ({rep['retained_fraction']['fixtures']:.0%} e "
              f"{rep['retained_fraction']['translations']:.0%}); {'OK' if not rep['errors'] else 'FALHOU'}")
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
