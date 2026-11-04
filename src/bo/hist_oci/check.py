"""Gate 'python -I -m bo.hist.check HIST-OCI' (despachante do coordenador -> este módulo).

  python -I -m bo.hist_oci.check [HIST-OCI]

Toda versão da lista histórica do PINS (entrada do oci em universe/history_versions.json) está extraída ou tem
motivo, e as datas são monótonas. Em detalhe, reprova (sai 1) se:
  * versions.json não é C13 válido, não é do HIST-OCI/oci, ou não lista as mesmas versões e datas, na mesma
    ordem, que a lista histórica;
  * released_at (ou published_at) decresce ao longo da ordem semver;
  * alguma versão listada não tem registro em extraction.json, ou tem estado fora de extracted/not_extracted;
  * versão not_extracted sem motivo, ou com atoms_<versão>.jsonl.gz ou schema_sha256 publicados;
  * versão extracted cujo atoms_<versão>.jsonl.gz falta, não bate com o sha256 registrado (comprimido e
    descomprimido), tem nº de linhas diferente, ou átomo de outra versão/provedor; cujo schema extraído falta ou
    não descomprime no schema_sha256 do versions.json; ou cuja assinatura não é da chave primária da Oracle;
  * o pin (última versão) não está extraído ou o schema dele difere do schema_sha256 da lista histórica;
  * o truncamento à esquerda registrado difere do da lista histórica;
  * sobrou binário (zip ou pasta desempacotada) de alguma versão.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from . import common

MIN_MOTIVO = 20


def _validate_versions(path: Path) -> list[str]:
    from bo.contracts import validate as V
    r = V.validate("versions", path)
    return [f"versions.json C13: {e}" for e in r.errors]


def check(hist: common.History, out: Path, schema_dir=common.tfschema_dir, binary_dirs=None,
          validate=True) -> tuple[list[str], dict]:
    probs: list[str] = []
    vp, ep = out / "versions.json", out / "extraction.json"
    for p in (vp, ep):
        if not p.is_file():
            return [f"{p.name} não existe"], {}
    if validate:
        probs += _validate_versions(vp)
    vdoc = json.loads(vp.read_text(encoding="utf-8"))
    ext = json.loads(ep.read_text(encoding="utf-8"))
    if vdoc.get("module") != common.MODULE or vdoc.get("provider") != common.PROVIDER:
        probs.append(f"versions.json é de {vdoc.get('module')}/{vdoc.get('provider')}")
    listed = [(lv.version, lv.released_at) for lv in hist.versions]
    got = [(v.get("version"), v.get("released_at")) for v in vdoc.get("versions", [])]
    if got != listed:
        miss = sorted({x[0] for x in listed} - {x[0] for x in got})
        extra = sorted({x[0] for x in got} - {x[0] for x in listed})
        probs.append(f"versions.json != lista histórica (faltam {miss}, sobram {extra}, ou ordem/data diferente)")

    # datas monótonas na ordem semver
    keys = [common.semver_key(lv.version) for lv in hist.versions]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        probs.append("lista histórica fora da ordem semver ou com versão repetida")
    for a, b in zip(hist.versions, hist.versions[1:]):
        if b.released_at < a.released_at:
            probs.append(f"released_at decresce: {a.version} {a.released_at} -> {b.version} {b.released_at}")
        if b.published_at < a.published_at:
            probs.append(f"published_at decresce: {a.version} {a.published_at} -> {b.version} {b.published_at}")
    for a, b in zip(got, got[1:]):
        if a[1] and b[1] and b[1] < a[1]:
            probs.append(f"versions.json: released_at decresce em {a[0]} -> {b[0]}")

    by = {r.get("version"): r for r in ext.get("versions", [])}
    vby = {v.get("version"): v for v in vdoc.get("versions", [])}
    st = {"extracted": [], "not_extracted": []}
    for lv in hist.versions:
        v = lv.version
        r = by.get(v)
        if r is None:
            probs.append(f"{v}: sem registro em extraction.json")
            continue
        s = r.get("status")
        if s not in st:
            probs.append(f"{v}: estado {s!r} (esperado extracted ou not_extracted)")
            continue
        st[s].append(v)
        ap = out / f"atoms_{v}.jsonl.gz"
        if s == "not_extracted":
            if len((r.get("motivo") or "").strip()) < MIN_MOTIVO:
                probs.append(f"{v}: not_extracted sem motivo")
            if ap.exists():
                probs.append(f"{v}: not_extracted mas {ap.name} existe")
            if "schema_sha256" in vby.get(v, {}):
                probs.append(f"{v}: not_extracted mas versions.json traz schema_sha256")
            continue
        probs += _check_extracted(v, r, ap, vby.get(v, {}), schema_dir(v))
    pin = hist.versions[-1]
    if pin.version != hist.pin:
        probs.append(f"última versão listada {pin.version} != pin {hist.pin}")
    if pin.version not in st["extracted"]:
        probs.append(f"pin {pin.version} não extraído")
    elif pin.schema_sha256 and vby.get(pin.version, {}).get("schema_sha256") != pin.schema_sha256:
        probs.append(f"pin {pin.version}: schema_sha256 != lista histórica")
    lt = {k: v for k, v in (ext.get("left_truncation") or {}).items() if k != "declarado"}
    if lt != hist.left_truncation:
        probs.append("left_truncation registrado != lista histórica")
    if not (ext.get("left_truncation") or {}).get("declarado"):
        probs.append("truncamento à esquerda sem declaração")
    dirs = binary_dirs(hist) if binary_dirs else _binary_dirs(hist)
    for d in dirs:
        if d.exists() and any(p.is_file() for p in d.rglob("*")):
            probs.append(f"binário não apagado: {common.portable(d)}")
    return probs, {k: len(v) for k, v in st.items()} | {"listed": len(hist.versions)}


def _binary_dirs(hist: common.History) -> list[Path]:
    out = []
    for lv in hist.versions:
        out += [common.zip_dir(lv.version), common.unpacked_dir(lv.version)]
    return out


def _check_extracted(v: str, r: dict, ap: Path, ventry: dict, sdir: Path) -> list[str]:
    probs = []
    if not ap.is_file():
        return [f"{v}: extracted mas {ap.name} não existe"]
    if common.sha256_file(ap) != r.get("atoms_gz_sha256"):
        probs.append(f"{v}: {ap.name} não bate com atoms_gz_sha256")
    h, n, bad = hashlib.sha256(), 0, 0
    with gzip.open(ap, "rb") as f:
        for line in f:
            h.update(line)
            n += 1
            a = json.loads(line)
            bad += a.get("provider_version") != v or a.get("provider") != common.PROVIDER
    if h.hexdigest() != r.get("atoms_jsonl_sha256"):
        probs.append(f"{v}: conteúdo de {ap.name} não bate com atoms_jsonl_sha256")
    if n != r.get("atoms") or n == 0:
        probs.append(f"{v}: {n} linhas != {r.get('atoms')} átomos registrados")
    if bad:
        probs.append(f"{v}: {bad} átomo(s) de outra versão ou provedor")
    sha = r.get("schema_sha256")
    if not sha or ventry.get("schema_sha256") != sha:
        probs.append(f"{v}: schema_sha256 do versions.json != extraction.json")
    gz = sdir / "schema.json.gz"
    if not gz.is_file():
        probs.append(f"{v}: schema extraído ausente ({common.portable(gz)})")
    elif common.gz_sha256(gz) != sha:
        probs.append(f"{v}: schema.json.gz não descomprime no schema_sha256")
    if r.get("gpg_primary_fpr") != common.ORACLE_FPR:
        probs.append(f"{v}: assinatura não é da chave primária âncora")
    if not r.get("binarios_apagados"):
        probs.append(f"{v}: binários não marcados como apagados")
    return probs


def main(argv=None) -> int:
    argv = [a for a in (argv or []) if a != common.MODULE]
    if argv:
        print(f"check: argumentos inesperados {argv}", file=sys.stderr)
        return 2
    hist = common.read_history()
    probs, counts = check(hist, common.out_dir())
    for p in probs:
        print(f"  FALHA {p}")
    print(f"hist.check {common.MODULE}: {counts} -> {'OK' if not probs else f'{len(probs)} problema(s)'}")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
