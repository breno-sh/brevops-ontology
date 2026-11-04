"""Gate do HIST-AZURE: toda versão listada extraída ou com motivo; datas monótonas.

  python -I -m bo.hist.check HIST-AZURE        (despachante do coordenador -> bo.hist_azure.check)
  python -I -m bo.hist_azure.check

Confere, contra a lista histórica do PINS (universe/history_versions.json, azurerm):
  LISTA      versions.json e extract_report.json listam exatamente as versões do PINS, na mesma ordem, com o
             mesmo released_at (e o mesmo published_at no relatório);
  MONOTONIA  versões em ordem SemVer estrita; released_at não decrescente; published_at estritamente crescente;
  COBERTURA  cada versão é EXTRACTED (schema_sha256 no versions.json igual ao do relatório; schema.json.gz,
             atoms_<v>.jsonl.gz e types_<v>.jsonl.gz existem e batem com os sha256 registrados; todo átomo
             tem provider_version = v e a contagem registrada) ou NOT_EXTRACTED com motivo não vazio e sem
             schema_sha256;
  PIN        a versão do pin está extraída e o schema_sha256 é o que o PINS registrou;
  BINÁRIOS   nenhum binário de provider nem zip sobrou nas pastas do módulo (só schema e hashes);
  MANIFESTO  MANIFEST.sha256 confere e cobre toda saída extraída, sem log volátil (integration/, gate_report).
Sai 0 só se tudo confere; imprime uma linha por conferência.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from . import common, pipeline

VOLATILE = ("integration/", "gate_report.json", "consume_ledger.json")


def _atoms_ok(p: Path, version: str, want: int) -> str | None:
    n = 0
    with gzip.open(p, "rt", encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            if a.get("provider_version") != version or a.get("provider") != common.PROVIDER:
                return f"átomo {a.get('atom_id')} com provider/provider_version {a.get('provider')}/" \
                       f"{a.get('provider_version')}"
            n += 1
    if n != want:
        return f"{n} átomos no arquivo, {want} no relatório"
    return None


def check_lists(hist: common.History, vdoc: dict, rep: dict) -> list[str]:
    errs = []
    want = [(it.version, it.released_at) for it in hist.listed]
    got = [(v["version"], v["released_at"]) for v in vdoc.get("versions", [])]
    if got != want:
        errs.append(f"LISTA: versions.json {len(got)} versões != PINS {len(want)} (ou ordem/data diferente)")
    rv = [(r.get("version"), r.get("released_at"), r.get("published_at")) for r in rep.get("versions", [])]
    wr = [(it.version, it.released_at, it.published_at) for it in hist.listed]
    if rv != wr:
        errs.append("LISTA: extract_report.json não lista as versões do PINS na mesma ordem e com as mesmas datas")
    if vdoc.get("provider") != common.PROVIDER or vdoc.get("module") != common.MODULE:
        errs.append("LISTA: versions.json com provider/module errado")
    return errs


def check_monotonic(hist: common.History) -> list[str]:
    errs = []
    L = hist.listed
    for a, b in zip(L, L[1:]):
        if not common.semver_key(a.version) < common.semver_key(b.version):
            errs.append(f"MONOTONIA: {a.version} -> {b.version} não é crescente (SemVer)")
        if not a.released_at <= b.released_at:
            errs.append(f"MONOTONIA: released_at {a.version} {a.released_at} > {b.version} {b.released_at}")
        if not a.published_at < b.published_at:
            errs.append(f"MONOTONIA: published_at {a.version} {a.published_at} >= {b.version} {b.published_at}")
    return errs


def check_coverage(hist: common.History, vdoc: dict, rep: dict) -> tuple[list[str], dict]:
    errs = []
    vsha = {v["version"]: v.get("schema_sha256") for v in vdoc.get("versions", [])}
    recs = {r.get("version"): r for r in rep.get("versions", [])}
    stat = {"EXTRACTED": 0, "NOT_EXTRACTED": 0}
    for it in hist.listed:
        v = it.version
        r = recs.get(v)
        if not r:
            errs.append(f"COBERTURA: {v} fora do relatório")
            continue
        st = r.get("status")
        if st == "EXTRACTED":
            stat[st] += 1
            sha = r["schema"]["sha256"]
            if vsha.get(v) != sha:
                errs.append(f"COBERTURA: {v} schema_sha256 do versions.json != relatório")
            sd = common.schema_dir(v)
            try:
                if common.gz_sha256(sd / "schema.json.gz") != sha:
                    errs.append(f"COBERTURA: {v} schema.json.gz não descomprime no schema_sha256")
                if (sd / "schema.json.sha256").read_text(encoding="utf-8").split()[0] != sha:
                    errs.append(f"COBERTURA: {v} schema.json.sha256 != schema_sha256")
                if common.sha256_file(common.atoms_path(v)) != r["atoms"]["gz_sha256"]:
                    errs.append(f"COBERTURA: {v} atoms_{v}.jsonl.gz != sha256 registrado")
                if common.sha256_file(common.types_path(v)) != r["types"]["gz_sha256"]:
                    errs.append(f"COBERTURA: {v} types_{v}.jsonl.gz != sha256 registrado")
                bad = _atoms_ok(common.atoms_path(v), v, r["atoms"]["count"])
                if bad:
                    errs.append(f"COBERTURA: {v} {bad}")
            except OSError as e:
                errs.append(f"COBERTURA: {v} arquivo ausente ({e.strerror})")
        elif st == "NOT_EXTRACTED":
            stat[st] += 1
            if not str(r.get("reason") or "").strip():
                errs.append(f"COBERTURA: {v} NOT_EXTRACTED sem motivo")
            if vsha.get(v):
                errs.append(f"COBERTURA: {v} NOT_EXTRACTED com schema_sha256 no versions.json")
        else:
            errs.append(f"COBERTURA: {v} com status {st!r}")
    return errs, stat


def check_pin(hist: common.History, rep: dict) -> list[str]:
    pin = [it for it in hist.listed if it.version == hist.pin]
    if len(pin) != 1:
        return [f"PIN: {hist.pin} não está (uma vez) na lista do PINS"]
    if hist.listed[-1].version != hist.pin:
        return [f"PIN: a última versão listada não é o pin {hist.pin}"]
    r = next((x for x in rep.get("versions", []) if x.get("version") == hist.pin), None)
    if not r or r.get("status") != "EXTRACTED":
        return [f"PIN: {hist.pin} não foi extraída"]
    if not pin[0].schema_sha256:
        return [f"PIN: o PINS não registrou schema_sha256 de {hist.pin}"]
    if r["schema"]["sha256"] != pin[0].schema_sha256:
        return [f"PIN: schema de {hist.pin} {r['schema']['sha256']} != PINS {pin[0].schema_sha256}"]
    return []


def check_manifest(hist: common.History, rep: dict) -> list[str]:
    mf = common.out_dir() / "MANIFEST.sha256"
    if not mf.exists():
        return ["MANIFESTO: MANIFEST.sha256 ausente"]
    errs, paths = [], set()
    for n, line in enumerate(mf.read_text(encoding="utf-8").splitlines(), 1):
        sha, _, rel = line.partition("  ")
        if any(rel.startswith(x) or rel.endswith(x) for x in VOLATILE):
            errs.append(f"MANIFESTO: linha {n} lista log volátil {rel}")
        p = common.expand(rel) if rel.startswith("$") else common.out_dir() / rel
        paths.add(str(p))
        try:
            if common.sha256_file(p) != sha:
                errs.append(f"MANIFESTO: {rel} não confere")
        except OSError:
            errs.append(f"MANIFESTO: {rel} ausente")
    need = [common.versions_path(), common.report_path()]
    for r in rep.get("versions", []):
        if r.get("status") == "EXTRACTED":
            v = r["version"]
            need += [common.atoms_path(v), common.types_path(v), common.schema_dir(v) / "schema.json.gz"]
    for p in need:
        if str(p) not in paths:
            errs.append(f"MANIFESTO: não cobre {common.portable(p)}")
    return errs


def run() -> tuple[int, list[str]]:
    hist = common.read_history()
    lines, errs = [], []
    try:
        vdoc = json.loads(common.versions_path().read_text(encoding="utf-8"))
        rep = json.loads(common.report_path().read_text(encoding="utf-8"))
    except OSError as e:
        return 1, [f"FAIL saídas ausentes: {e.filename}"]
    for name, es in (("LISTA", check_lists(hist, vdoc, rep)), ("MONOTONIA", check_monotonic(hist))):
        lines.append(f"{'OK  ' if not es else 'FAIL'} {name}: {len(hist.listed)} versões" if not es else
                     f"FAIL {name}: {len(es)} problema(s)")
        errs += es
    es, stat = check_coverage(hist, vdoc, rep)
    lines.append(f"{'OK  ' if not es else 'FAIL'} COBERTURA: {stat['EXTRACTED']} extraídas, "
                 f"{stat['NOT_EXTRACTED']} com motivo, de {len(hist.listed)}")
    errs += es
    es = check_pin(hist, rep)
    lines.append(f"{'OK  ' if not es else 'FAIL'} PIN: {hist.pin}")
    errs += es
    left = pipeline.leftover_binaries()
    lines.append(f"{'OK  ' if not left else 'FAIL'} BINÁRIOS: {len(left)} binário(s)/zip(s) restantes")
    errs += [f"BINÁRIOS: sobrou {x}" for x in left]
    es = check_manifest(hist, rep)
    lines.append(f"{'OK  ' if not es else 'FAIL'} MANIFESTO: MANIFEST.sha256")
    errs += es
    return (0 if not errs else 1), lines + [f"  {e}" for e in errs]


def main(argv=None) -> int:
    rc, lines = run()
    for ln in lines:
        print(ln)
    print("RESULTADO:", "OK" if rc == 0 else "FALHA")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
