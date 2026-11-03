"""Gate de higiene: o termo antigo da v2 não aparece fora da nota de renomeação.

  python -I -m bo.prereg.no_oldterm [--paths ARQ ...]

Varre tudo o que o PREREG publica (prereg/ do módulo, src/bo/prereg/, tests/prereg/, gates/PREREG.sh,
results/PREREG/) e reprova:
  T-TEXT  o termo antigo (palavra inteira, sem distinguir caixa) fora da nota de renomeação: no PREREG.html,
          fora de <section id="nota-renomeacao">; em código e testes, fora das linhas entre os marcadores
          'nota-renomeacao: início' e 'nota-renomeacao: fim'; em dado (YAML, JSON, TXT), em qualquer lugar
  T-KEY   chave de YAML/JSON que contenha o termo como subcadeia (regra C15-OLDTERM)
  T-NOTE  a nota de renomeação ausente do PREREG.html, ou sem o termo antigo e o novo (a nota existe e explica)
Fora do escopo do módulo, conta (sem reprovar) as ocorrências no resto do repositório, para o coordenador.
Relatório em $BO_DATA/PREREG/no_oldterm.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from . import common, content as C

TERM_RE = re.compile(r"(?i)\b(" + "|".join(re.escape(t) for t in C.OLD_TERMS) + r")\b")
KEY_RE = re.compile(r"(?i)(" + "|".join(re.escape(t) for t in C.OLD_TERMS[::2]) + r")")
NOTE_OPEN = re.compile(r'<section id="nota-renomeacao"[^>]*>')
MARK_A, MARK_B = "nota-renomeacao: início", "nota-renomeacao: fim"
CODE_EXT = {".py", ".sh"}
DATA_EXT = {".yaml", ".yml", ".json", ".jsonl", ".txt", ".sha256", ".tsv", ".csv"}


def scope() -> list[Path]:
    R = common.REPO
    out = [p for p in common.FILES.values()]
    for d in (R / "src" / "bo" / "prereg", R / "tests" / "prereg", R / "results" / "PREREG"):
        if d.exists():
            out += sorted(p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    g = R / "gates" / "PREREG.sh"
    if g.exists():
        out.append(g)
    return out


def html_hits(text: str) -> tuple[list[int], bool]:
    """Linhas com o termo fora da nota e se a nota existe com os dois termos."""
    m = NOTE_OPEN.search(text)
    lo = hi = -1
    note_ok = False
    if m:
        lo = m.start()
        hi = text.find("</section>", m.end())
        note = text[m.end():hi] if hi > 0 else ""
        note_ok = bool(TERM_RE.search(note)) and C.NEW_TERM.lower() in note.lower()
    bad = []
    for mm in TERM_RE.finditer(text):
        if not (lo <= mm.start() < hi):
            bad.append(text.count("\n", 0, mm.start()) + 1)
    return bad, note_ok


def code_hits(text: str) -> list[int]:
    bad, inside = [], False
    for i, ln in enumerate(text.splitlines(), 1):
        if MARK_A in ln:
            inside = True
        if TERM_RE.search(ln) and not inside:
            bad.append(i)
        if MARK_B in ln:
            inside = False
    return bad


def key_hits(obj, path="") -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if KEY_RE.search(str(k)):
                out.append(f"{path}/{k}")
            out += key_hits(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += key_hits(v, f"{path}/{i}")
    return out


def scan(paths: list[Path]) -> tuple[list[str], dict]:
    errs: list[str] = []
    seen_note = False
    for p in paths:
        if not p.exists():
            errs.append(f"T-MISSING {p}: arquivo do escopo ausente")
            continue
        text = p.read_text(encoding="utf-8")
        rel = p.name
        if p.suffix == ".html":
            bad, ok = html_hits(text)
            errs += [f"T-TEXT {rel}:{ln}: termo antigo fora da nota" for ln in bad]
            if p.name == common.FILES["html"].name:
                seen_note = ok
                if not ok:
                    errs.append(f"T-NOTE {rel}: nota de renomeação ausente ou sem o termo antigo e o novo")
        elif p.suffix in CODE_EXT:
            errs += [f"T-TEXT {rel}:{ln}: termo antigo fora dos marcadores da nota" for ln in code_hits(text)]
        else:
            for mm in TERM_RE.finditer(text):
                errs.append(f"T-TEXT {rel}:{text.count(chr(10), 0, mm.start()) + 1}: termo antigo em arquivo de dado")
            if p.suffix in (".yaml", ".yml", ".json"):
                try:
                    obj = common.yaml_load(p) if p.suffix != ".json" else json.loads(text)
                except Exception as e:  # noqa: BLE001
                    errs.append(f"T-KEY {rel}: ilegível ({e.__class__.__name__})")
                    obj = None
                errs += [f"T-KEY {rel}: chave {k} contém o termo antigo" for k in key_hits(obj)]
    return errs, {"note_present": seen_note, "n_files": len(paths)}


def elsewhere(paths: list[Path]) -> int:
    """Ocorrências fora do escopo do módulo (informativo; não reprova)."""
    mine = {p.resolve() for p in paths}
    n = 0
    for p in common.REPO.rglob("*"):
        if (p.is_file() and p.resolve() not in mine and ".git" not in p.parts and "__pycache__" not in p.parts
                and p.suffix in CODE_EXT | DATA_EXT | {".html", ".md", ".tex", ".ttl"}):
            try:
                n += len(TERM_RE.findall(p.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="o termo antigo só na nota de renomeação")
    ap.add_argument("--paths", nargs="*")
    ap.add_argument("--no-report", action="store_true")
    a = ap.parse_args(argv)
    paths = [Path(x) for x in a.paths] if a.paths else scope()
    errs, info = scan(paths)
    if not a.no_report:
        rep = {"module": "PREREG", "check": "no_oldterm",
               "at": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="seconds"),
               "files": info["n_files"], "note_present": info["note_present"], "errors": errs,
               "occurrences_outside_module": elsewhere(paths) if not a.paths else None}
        common.OUT_DATA.mkdir(parents=True, exist_ok=True)
        (common.OUT_DATA / "no_oldterm.json").write_text(common.json_dump(rep), encoding="utf-8")
    for x in errs:
        print("FAIL", x)
    if errs:
        print(f"RESULTADO: REPROVADO ({len(errs)})")
        return 1
    print(f"RESULTADO: OK ({info['n_files']} arquivos; termo antigo só na nota de renomeação)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
