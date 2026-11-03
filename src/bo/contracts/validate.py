"""Validador único dos contratos C00–C29.

  python -I -m bo.contracts.validate <contrato|tipo> ARQ [ARQ ...]   valida arquivos (sai 0 se todos conferem)
  python -I -m bo.contracts.validate --all-stubs                    todo stub de contracts/stubs/ confere, e todo
                                                                    tipo de arquivo de todo contrato tem stub
  python -I -m bo.contracts.validate --mutation-test                cada stub mutado tem de reprovar (e o controle,
                                                                    a cópia sem mutação, tem de passar)
  python -I -m bo.contracts.validate --list                         contratos, tipos de arquivo e aliases

<contrato|tipo>: Cnn, Cnn_<nome>, <nome> (ex.: manifest_receipt), <tipo> (ex.: commitments, realizations,
correspondences) ou Cnn_<tipo> (ex.: C10_composition_table). Contrato com vários arquivos escolhe pelo nome do
arquivo. Duas camadas: JSON Schema (contracts/Cnn_*.schema.json, draft 2020-12) e as regras de
x-bo-contract.semantic_rules (bo.contracts.rules). Relatórios em $BO_DATA/CONTRACTS/.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from . import _base, catalog, fileio, rules


@dataclass
class Result:
    path: str
    kind: str
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    n: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


_VALIDATORS: dict = {}


def validator_for(ref: str, sch: dict):
    key = (ref, id(sch))
    if key not in _VALIDATORS:
        _VALIDATORS[key] = jsonschema.Draft202012Validator({"$ref": ref}, registry=catalog.registry(sch))
    return _VALIDATORS[key]


def validate_file(fk: catalog.FileKind, path: Path, sch: dict | None = None) -> Result:
    sch = sch or catalog.schemas()
    res = Result(str(path), f"{fk.cid}:{fk.kind}")
    try:
        recs, ctx = fileio.read(fk.format, path)
    except fileio.FormatError as e:
        res.errors.append(f"formato {fk.format}: {e}")
        return res
    res.n = len(recs) or len(ctx.get("records") or ctx.get("lines") or [1])
    if fk.ref:
        v = validator_for(fk.ref, sch)
        for where, obj in recs:
            for e in sorted(v.iter_errors(obj), key=lambda e: list(map(str, e.absolute_path))):
                loc = "/".join(str(p) for p in e.absolute_path) or "(raiz)"
                res.errors.append(f"{where}: schema {loc}: {_short(e)}")
    if not res.errors:
        try:
            res.errors += rules.run(fk.cid, fk.kind, [o for _, o in recs], ctx, path)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            res.errors.append(f"regra {fk.cid}:{fk.kind} não pôde rodar: {type(e).__name__}: {str(e)[:200]}")
        res.notes += ctx.get("notes") or []
    return res


def _short(e: jsonschema.ValidationError) -> str:
    msg = e.message
    if e.validator in ("oneOf", "anyOf") and e.context:
        best = jsonschema.exceptions.best_match(e.context)
        msg = f"{msg[:120]} — mais provável: {best.message[:160]}"
    return msg[:300]


def validate(alias: str, path: Path, sch: dict | None = None) -> Result:
    fk = catalog.resolve(alias, path, sch)
    return validate_file(fk, path, sch)


# ------------------------------------------------------------------------------------------------ stubs
def stub_index() -> dict:
    p = _base.stubs_dir() / "INDEX.json"
    return json.loads(p.read_text(encoding="utf-8"))["stubs"]


def all_stubs(sch: dict | None = None) -> tuple[list[Result], list[str]]:
    sch = sch or catalog.schemas()
    idx = stub_index()
    out, problems = [], []
    for rel, kind in sorted(idx.items()):
        cid, k = kind.split(":")
        fk = catalog.resolve(f"{cid}_{k}", _base.stubs_dir() / rel, sch)
        out.append(validate_file(fk, _base.stubs_dir() / rel, sch))
    covered = set(idx.values())
    for fk in catalog.file_kinds(sch):
        if f"{fk.cid}:{fk.kind}" not in covered:
            problems.append(f"sem stub: {fk.cid}:{fk.kind} ({fk.file})")
    on_disk = {str(p.relative_to(_base.stubs_dir())) for p in _base.stubs_dir().rglob("*") if p.is_file()}
    for rel in sorted(on_disk - set(idx) - {"INDEX.json"}):
        problems.append(f"arquivo em stubs/ fora do INDEX.json: {rel}")
    return out, problems


def mutation_test(sch: dict | None = None) -> dict:
    from . import mutations
    sch = sch or catalog.schemas()
    idx = stub_index()
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="mutation-", dir=_base.tmp_dir())) / "stubs"
    report = {"stubs": {}, "survivors": [], "controls_failed": [], "n_mutants": 0, "n_killed": 0}
    for rel, kind in sorted(idx.items()):
        cid, k = kind.split(":")
        src = _base.stubs_dir() / rel
        fk = catalog.resolve(f"{cid}_{k}", src, sch)
        muts = mutations.mutants(fk, src.read_bytes(), rel, sch)
        killed = []
        for mid, data in muts:
            if data == src.read_bytes():
                report["n_mutants"] += 1
                report["survivors"].append(f"{rel} :: {mid} (mutação nula: igual ao original)")
                continue
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(_base.stubs_dir(), work)
            (work / rel).write_bytes(data)
            r = validate_file(fk, work / rel, sch)
            report["n_mutants"] += 1
            if r.ok:
                report["survivors"].append(f"{rel} :: {mid}")
            else:
                report["n_killed"] += 1
                killed.append({"mutant": mid, "first_error": _safe(r.errors[0])[:200]})
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(_base.stubs_dir(), work)
        ctl = validate_file(fk, work / rel, sch)
        if not ctl.ok:
            report["controls_failed"].append(f"{rel}: {ctl.errors[:2]}")
        report["stubs"][rel] = {"kind": kind, "mutants": len(muts), "killed": len(killed), "detail": killed}
        if len(muts) < 3:
            report["survivors"].append(f"{rel} :: só {len(muts)} mutante(s) (mínimo 3)")
    shutil.rmtree(work.parent, ignore_errors=True)
    return report


def _safe(s: str) -> str:
    """Erro de mutante vai para relatório: mascara o que o privacy_lint proíbe (o mutante pode conter o formato)."""
    import re
    s = re.sub(r"(?<![0-9a-fA-F])\d{12,}(?![0-9a-fA-F])", "<dígitos>", s)
    return re.sub(r"(?i)\barn:", "arn[:]", s)


# ------------------------------------------------------------------------------------------------ CLI
def _emit(line: str) -> None:
    print(line, flush=True)


def _write_report(name: str, obj) -> Path:
    d = _base.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 2 if not argv else 0
    try:
        sch = catalog.schemas()
    except FileNotFoundError as e:
        _emit(f"ERRO {e}")
        return 2
    if argv[0] == "--list":
        for fk in catalog.file_kinds(sch):
            v = sch[fk.cid]["x-bo-contract"]["version"]
            _emit(f"{fk.cid} {catalog.NAMES[fk.cid]:<18} {v:<6} {fk.kind:<22} {fk.file:<26} {fk.format}")
        return 0
    if argv[0] == "--all-stubs":
        res, problems = all_stubs(sch)
        bad = [r for r in res if not r.ok]
        for r in res:
            _emit(f"  {'OK  ' if r.ok else 'FAIL'} {r.kind:<28} {Path(r.path).relative_to(_base.stubs_dir())}"
                  f" ({r.n} item(ns))")
            for e in r.errors[:8]:
                _emit(f"       - {e}")
        for p in problems:
            _emit(f"  FAIL {p}")
        rep = {"at": _base.now(), "stubs": len(res), "ok": len(res) - len(bad), "problems": problems,
               "failed": {r.path: r.errors for r in bad}}
        _write_report("all_stubs.json", rep)
        _emit(f"[{_base.now()}] --all-stubs: {len(res) - len(bad)}/{len(res)} stubs conferem; "
              f"{len(catalog.file_kinds(sch))} tipos de arquivo em {len(sch)} contratos; {len(problems)} problema(s)")
        return 0 if not bad and not problems else 1
    if argv[0] == "--mutation-test":
        rep = mutation_test(sch)
        rep["at"] = _base.now()
        _write_report("mutation_report.json", rep)
        for s in rep["survivors"]:
            _emit(f"  SOBREVIVEU {s}")
        for c in rep["controls_failed"]:
            _emit(f"  CONTROLE FALHOU {c}")
        _emit(f"[{_base.now()}] --mutation-test: {rep['n_killed']}/{rep['n_mutants']} mutantes reprovados em "
              f"{len(rep['stubs'])} stubs; {len(rep['survivors'])} sobrevivente(s); "
              f"{len(rep['controls_failed'])} controle(s) com falha")
        return 0 if not rep["survivors"] and not rep["controls_failed"] and rep["n_mutants"] else 1
    if len(argv) < 2:
        _emit("uso: python -I -m bo.contracts.validate <contrato|tipo> ARQ [ARQ ...]")
        return 2
    alias, paths = argv[0], [Path(p) for p in argv[1:]]
    rc = 0
    for p in paths:
        try:
            r = validate(alias, p, sch)
        except KeyError as e:
            _emit(f"ERRO {e.args[0]}")
            return 2
        for e in r.errors[:40]:
            _emit(f"  ERRO {e}")
        if len(r.errors) > 40:
            _emit(f"  ... mais {len(r.errors) - 40} erro(s)")
        for n in r.notes[:10]:
            _emit(f"  nota {n}")
        _emit(f"[{_base.now()}] {r.kind} {p}: {r.n} item(ns), {len(r.errors)} erro(s) -> {'OK' if r.ok else 'REPROVADO'}")
        rc = rc or (0 if r.ok else 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
