"""bo.hist.check HIST-AWS (despachado para bo.hist_aws.check): toda versão listada extraída ou com motivo;
datas monótonas.

  python -I -m bo.hist.check HIST-AWS [--deep]

Confere, contra universe/history_versions.json (PINS) e universe/pins.json:
  * versions.json lista exatamente as versões do PINS, na mesma ordem e com o mesmo released_at;
  * versões em ordem semver estritamente crescente e released_at não decrescente (datas monótonas);
  * cada versão está em extraction.json como EXTRACTED ou com motivo (FAILED, texto não vazio);
  * EXTRACTED: schema_sha256 do versions.json == schema.json.sha256 == sha256 do schema.json.gz descomprimido;
    atoms_<v>.jsonl.gz existe com o sha256 registrado; trust.json com VALIDSIG da âncora, binário == membro do
    zip, zip/pasta desempacotada apagados (só schema e hashes ficam);
  * não extraída: sem schema_sha256 no versions.json e sem atoms_<v>.jsonl.gz;
  * o pin é EXTRACTED e o sha256 do schema bate com pins.json;
  * --deep: cada atoms_<v>.jsonl.gz descomprime, conta o número registrado, todo átomo é aws e da versão.
Sai 0 se tudo confere, 1 se não.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

from . import atoms, common


def gz_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(out: Path | None = None, deep: bool = False, hist: common.History | None = None,
          pins: common.Pins | None = None, schema_root: Path | None = None) -> list[str]:
    out = out or common.out_dir()
    hist = hist or common.read_history()
    pins = pins or common.read_pins()
    errs: list[str] = []
    vp, ep = out / "versions.json", out / "extraction.json"
    if not vp.is_file() or not ep.is_file():
        return [f"falta {vp.name if not vp.is_file() else ep.name} em {common.portable(out)}"]
    vd = json.loads(vp.read_text(encoding="utf-8"))
    ext = json.loads(ep.read_text(encoding="utf-8")).get("versions") or {}
    if vd.get("module") != common.MODULE or vd.get("provider") != common.PROVIDER:
        errs.append(f"versions.json de {vd.get('module')}/{vd.get('provider')}, esperado {common.MODULE}/aws")
    got = [(v["version"], v["released_at"]) for v in vd.get("versions") or []]
    want = [(it.version, it.released_at) for it in hist.versions]
    if got != want:
        miss = sorted(set(want) - set(got), key=lambda x: common.semver_key(x[0]))
        extra = sorted(set(got) - set(want), key=lambda x: common.semver_key(x[0]))
        errs.append(f"versions.json != lista do PINS (faltam {miss[:5]}, sobram {extra[:5]}, ou ordem diferente)")
    for (a, da), (b, db) in zip(got, got[1:]):
        if common.semver_key(a) >= common.semver_key(b):
            errs.append(f"semver não crescente: {a} antes de {b}")
        if da > db:
            errs.append(f"datas não monótonas: {a} ({da}) antes de {b} ({db})")
    if set(ext) - {it.version for it in hist.versions}:
        errs.append(f"extraction.json com versões fora da lista: {sorted(set(ext) - {it.version for it in hist.versions})}")
    shas = {v["version"]: v.get("schema_sha256") for v in vd.get("versions") or []}
    for it in hist.versions:
        v = it.version
        r = ext.get(v)
        ap = out / f"atoms_{v}.jsonl.gz"
        if r is None:
            errs.append(f"{v}: nem extraída nem com motivo (ausente de extraction.json)")
            continue
        st = r.get("status")
        if st == "EXTRACTED":
            sdir = common.schema_dir(v, schema_root)
            sf = sdir / "schema.json.sha256"
            if not sf.is_file() or not (sdir / "schema.json.gz").is_file():
                errs.append(f"{v}: schema extraído ausente em {common.portable(sdir)}")
                continue
            ssha = sf.read_text(encoding="utf-8").split()[0]
            if shas.get(v) != ssha or r.get("schema_sha256") != ssha:
                errs.append(f"{v}: schema_sha256 diverge (versions.json {shas.get(v)}, arquivo {ssha}, "
                            f"extraction {r.get('schema_sha256')})")
            if gz_sha256(sdir / "schema.json.gz") != ssha:
                errs.append(f"{v}: schema.json.gz não descomprime no sha256 registrado")
            if not ap.is_file():
                errs.append(f"{v}: EXTRACTED sem {ap.name}")
                continue
            if common.sha256_file(ap) != r.get("atoms_gz_sha256"):
                errs.append(f"{v}: sha256 de {ap.name} diverge do registrado")
            tp = sdir / "trust.json"
            if not tp.is_file():
                errs.append(f"{v}: sem trust.json")
            else:
                t = json.loads(tp.read_text(encoding="utf-8"))
                if t["gpg"]["primary_fpr"] != common.HASHICORP_FPR or not t["gpg"]["validsig_subkey"]:
                    errs.append(f"{v}: trust.json sem VALIDSIG da âncora")
                if not t["binary"]["igual_ao_membro_do_zip"] or t["binary"]["sha256"] != \
                        t["unpacked"]["files"].get(t["binary"]["file"], {}).get("sha256"):
                    errs.append(f"{v}: binário carregado != membro do zip assinado")
                if t["schema_json_sha256"] != ssha:
                    errs.append(f"{v}: trust.json com outro schema_sha256")
                if not t["unpacked"]["apagado"] or (t["zip"]["reaproveitado_de"] is None
                                                     and not t["zip"]["apagado"]):
                    errs.append(f"{v}: binário não apagado depois da extração")
            if deep:
                n, bad = 0, 0
                try:
                    for a in atoms.read_atoms(ap):
                        n += 1
                        bad += a["provider"] != common.PROVIDER or a["provider_version"] != v
                except (OSError, EOFError, ValueError, KeyError) as e:
                    errs.append(f"{v}: {ap.name} ilegível ({type(e).__name__})")
                    continue
                if n != r.get("atoms"):
                    errs.append(f"{v}: {ap.name} tem {n} átomos, registrado {r.get('atoms')}")
                if bad:
                    errs.append(f"{v}: {bad} átomo(s) de outro provider ou versão")
        else:
            if not str(r.get("motivo") or "").strip():
                errs.append(f"{v}: status {st} sem motivo")
            if shas.get(v):
                errs.append(f"{v}: não extraída mas com schema_sha256 no versions.json")
            if ap.exists():
                errs.append(f"{v}: não extraída mas {ap.name} existe")
    pr = ext.get(hist.pin) or {}
    if pr.get("status") != "EXTRACTED":
        errs.append(f"pin {hist.pin} não extraído")
    elif pr.get("schema_sha256") != pins.schema_sha256:
        errs.append(f"pin {hist.pin}: schema {pr.get('schema_sha256')} != pins.json {pins.schema_sha256}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hist.check", description=__doc__.split("\n")[0])
    ap.add_argument("module", nargs="?", default=common.MODULE)
    ap.add_argument("--deep", action="store_true")
    a = ap.parse_args(argv)
    if a.module != common.MODULE:
        print(f"bo.hist_aws.check: módulo {a.module} não é {common.MODULE}", file=sys.stderr)
        return 2
    errs = check(deep=a.deep)
    hist = common.read_history()
    ext = json.loads((common.out_dir() / "extraction.json").read_text(encoding="utf-8")).get("versions") \
        if (common.out_dir() / "extraction.json").is_file() else {}
    n_ok = sum((ext.get(it.version) or {}).get("status") == "EXTRACTED" for it in hist.versions)
    for e in errs:
        print(f"  FAIL {e}")
    print(f"HIST-AWS: {len(hist.versions)} versões listadas, {n_ok} extraídas, "
          f"{len(hist.versions) - n_ok} com motivo; {len(errs)} problema(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
