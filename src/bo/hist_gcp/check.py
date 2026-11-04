"""bo.hist.check HIST-GCP: toda versão listada extraída ou com motivo; datas monótonas (gate G2).

  python -I -m bo.hist.check HIST-GCP        (despachante do coordenador -> este main)
  python -I -m bo.hist_gcp.check [--deep]

Confere, sem rede:
  1. versions.json passa no validador único (C13 versions) e lista exatamente as versões do history_versions.json
     (google), na mesma ordem e com o mesmo released_at; ordem SemVer estritamente crescente;
  2. datas monótonas: released_at não decresce e published_at (Registry) cresce ao longo da ordem SemVer;
  3. cada versão é 'extracted' ou 'unavailable' no extraction.json, e só isso:
       extracted   -> schema_sha256 no versions.json = extraction.json = receipt = sha da saída crua guardada;
                      átomos: gzip com o sha do receipt, JSONL com o sha do receipt, toda linha com provider google
                      e provider_version = a versão, contagem = receipt, C01 validado no pipeline;
                      cadeia: SHA256SUMS guardado com o sha do receipt e GOODSIG da chave vigente da HashiCorp;
                      binário apagado (nada no plugin cache de $BO_TMP);
       unavailable -> motivo escrito, sem schema_sha256, sem átomos e sem receipt; o índice do PINS (sha conferido)
                      e o history_versions.json confirmam que não há build darwin_arm64;
  4. a última versão é o pin do pins.json e o schema_sha256 dela é o do pin (C13-HIST-PIN);
  5. totais do extraction.json batem com as linhas.
--deep também reconfere cada assinatura com gpgv (bo.hist_gcp.signed.verify_local).
Sai 0 se tudo confere; 1 com a lista de falhas.
"""

from __future__ import annotations

import json
import sys

from . import common as C
from . import extract as E
from . import signed as S


class Report:
    def __init__(self):
        self.fails: list[str] = []
        self.oks: list[str] = []

    def ok(self, cond: bool, good: str, bad: str) -> bool:
        (self.oks if cond else self.fails).append(good if cond else bad)
        return cond


def recife_date(published_at: str) -> str:
    import datetime as dt
    t = dt.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return t.astimezone(C.TZ).date().isoformat()


def atoms_scan(v: str) -> tuple[str, int, set, set]:
    raw = C.gunzip_bytes(C.atoms_path(v))
    provs, vers = set(), set()
    n = 0
    for line in raw.decode("utf-8").splitlines():
        a = json.loads(line)
        provs.add(a.get("provider"))
        vers.add(a.get("provider_version"))
        n += 1
    return C.sha256_bytes(raw), n, provs, vers


def check_extracted(r: Report, v: str, row: dict, vrow: dict, key: dict | None, hist: dict) -> None:
    rp = C.receipt_path(v)
    if not r.ok(rp.exists(), f"{v}: receipt", f"{v}: extracted sem receipt"):
        return
    rec = json.loads(rp.read_text(encoding="utf-8"))
    sha = rec["schema_json"]["sha256"]
    r.ok(vrow.get("schema_sha256") == row.get("schema_sha256") == sha,
         f"{v}: schema_sha256 igual no versions.json, extraction.json e receipt",
         f"{v}: schema_sha256 diverge entre versions.json, extraction.json e receipt")
    raw_gz = C.raw_schema_dir(v) / "schema.json.gz"
    if r.ok(raw_gz.exists(), f"{v}: saída crua guardada", f"{v}: saída crua ausente ({C.portable(raw_gz)})"):
        r.ok(C.sha256_bytes(C.gunzip_bytes(raw_gz)) == sha, f"{v}: saída crua com o sha do receipt",
             f"{v}: saída crua não tem o sha do receipt")
    ap = C.atoms_path(v)
    if r.ok(ap.exists(), f"{v}: átomos", f"{v}: extracted sem {ap.name}"):
        r.ok(C.sha256_file(ap) == rec["atoms"]["gz_sha256"] == row.get("atoms_gz_sha256"),
             f"{v}: gzip dos átomos com o sha do receipt", f"{v}: gzip dos átomos diverge do receipt")
        jsha, n, provs, vers = atoms_scan(v)
        r.ok(jsha == rec["atoms"]["jsonl_sha256"], f"{v}: JSONL dos átomos com o sha do receipt",
             f"{v}: JSONL dos átomos diverge do receipt")
        r.ok(n == rec["atoms"]["atoms"] == row["counts"]["atoms"] and n > 0, f"{v}: {n} átomos = receipt",
             f"{v}: contagem de átomos ({n}) diverge do receipt")
        r.ok(provs == {C.PROVIDER} and vers == {v}, f"{v}: todo átomo é google {v}",
             f"{v}: átomos com provider {sorted(map(str, provs))} ou versão {sorted(map(str, vers))}")
    r.ok(rec["atoms"]["C01_validate"]["ok"], f"{v}: C01 validado", f"{v}: C01 não validado no pipeline")
    sums = C.unportable(rec["signed"]["sha256sums"])
    r.ok(sums.exists() and C.sha256_file(sums) == rec["signed"]["sha256sums_sha256"],
         f"{v}: SHA256SUMS guardado confere", f"{v}: SHA256SUMS guardado ausente ou alterado")
    r.ok(rec["signed"]["gpg"]["good"] and rec["signed"]["gpg"]["primary_fingerprint"]
         == json.loads((C.pins_index_dir() / "verification.json").read_text(encoding="utf-8"))
         ["terraform"]["signature"]["primary_fingerprint"],
         f"{v}: GOODSIG da chave vigente da HashiCorp", f"{v}: assinatura sem GOODSIG da chave da HashiCorp")
    r.ok(rec["provider_binary"]["h1"] == rec["lock"]["h1_from_signed_zip"],
         f"{v}: h1 da pasta = h1 do zip assinado", f"{v}: h1 da pasta diverge do zip assinado")
    lk = C.unportable(rec["lock"].get("path", ""))
    r.ok(lk.is_file() and C.sha256_file(lk) == rec["lock"].get("sha256")
         and rec["lock"]["h1_from_signed_zip"] in lk.read_text(encoding="utf-8"),
         f"{v}: lock guardado com o h1 do zip", f"{v}: lock ausente, alterado ou sem o h1 do zip")
    r.ok(not E.provider_dir(v).exists() and not E.work_dir(v).exists() and rec["provider_binary"]["deleted_after_extract"],
         f"{v}: binário apagado", f"{v}: binário ou pasta de trabalho ainda no disco")
    if key is not None:
        try:
            ch = S.verify_local(v, hist, key)
            r.ok(ch["sha256sums_sha256"] == rec["signed"]["sha256sums_sha256"], f"{v}: gpgv reconferido",
                 f"{v}: gpgv reconferido com outro SHA256SUMS")
        except SystemExit as e:
            r.ok(False, "", f"{v}: gpgv: {e}")


def check_unavailable(r: Report, v: str, row: dict, vrow: dict, sel: dict, hist: dict) -> None:
    r.ok(bool(row.get("reason")) and len(row["reason"]) >= 40, f"{v}: motivo escrito",
         f"{v}: unavailable sem motivo")
    r.ok("schema_sha256" not in vrow and "schema_sha256" not in row, f"{v}: sem schema_sha256",
         f"{v}: unavailable com schema_sha256")
    r.ok(not C.atoms_path(v).exists() and not C.receipt_path(v).exists(), f"{v}: sem átomos nem receipt",
         f"{v}: unavailable com arquivo de átomos ou receipt")
    idx = S.index_platforms(hist, v)
    r.ok(C.OS_ARCH not in idx["platforms"] and sel["darwin_arm64"] is False
         and row.get("evidence", {}).get("index_platforms") == idx["platforms"],
         f"{v}: índice do PINS e history_versions sem {C.OS_ARCH}",
         f"{v}: o índice ou o history_versions dizem que há {C.OS_ARCH}")


def run(deep: bool = False) -> Report:
    from bo.contracts import validate as V
    r = Report()
    out = C.out_dir()
    hist = C.history()
    pn = C.pins()
    vp, xp = out / "versions.json", out / "extraction.json"
    if not (r.ok(vp.exists(), "versions.json", "versions.json ausente")
            and r.ok(xp.exists(), "extraction.json", "extraction.json ausente")):
        return r
    res = V.validate("versions", vp)
    r.ok(res.ok, "versions.json passa no C13 (validador único)", f"versions.json reprova no C13: {res.errors[:3]}")
    vd = json.loads(vp.read_text(encoding="utf-8"))
    xd = json.loads(xp.read_text(encoding="utf-8"))
    r.ok(vd.get("module") == C.ID and vd.get("provider") == C.PROVIDER, "versions.json do HIST-GCP/google",
         "versions.json com module/provider errado")
    sel = hist["selection"]
    want = [(s["version"], s["released_at"]) for s in sel]
    got = [(x["version"], x["released_at"]) for x in vd["versions"]]
    r.ok(got == want, f"versions.json = lista do PINS ({len(want)} versões, mesma ordem e datas)",
         f"versions.json difere da lista do PINS ({len(got)} x {len(want)})")
    xs = [x["version"] for x in xd.get("versions", [])]
    r.ok(xs == [w[0] for w in want], "extraction.json = lista do PINS", "extraction.json difere da lista do PINS")

    keys = [C.semver_key(v) for v, _ in got]
    r.ok(all(a < b for a, b in zip(keys, keys[1:])), "ordem SemVer estritamente crescente",
         "versões fora da ordem SemVer ou repetidas")
    for name, dates in (("versions.json", [d for _, d in got]), ("history_versions.json", [d for _, d in want])):
        r.ok(all(a <= b for a, b in zip(dates, dates[1:])), f"released_at monótono no {name} (não decresce)",
             f"released_at decresce em algum ponto da ordem SemVer ({name})")
    pubs = [s["published_at"] for s in sel]
    r.ok(all(a < b for a, b in zip(pubs, pubs[1:])), "published_at estritamente crescente",
         "published_at não cresce ao longo da ordem SemVer")
    r.ok(all(recife_date(s["published_at"]) == s["released_at"] for s in sel),
         "released_at = data de published_at (UTC do Registry) em America/Recife",
         "released_at diverge da data de published_at em America/Recife")

    key = C.vendor_key() if deep else None
    vrows = {x["version"]: x for x in vd["versions"]}
    xrows = {x["version"]: x for x in xd.get("versions", [])}
    n_ok = n_un = 0
    for s in sel:
        v = s["version"]
        row, vrow = xrows.get(v, {}), vrows.get(v, {})
        st = row.get("status")
        if not r.ok(st in ("extracted", "unavailable"), f"{v}: {st}", f"{v}: situação {st!r} (nem extraída nem com motivo)"):
            continue
        if st == "extracted":
            n_ok += 1
            check_extracted(r, v, row, vrow, key, hist)
        else:
            n_un += 1
            check_unavailable(r, v, row, vrow, s, hist)

    last = vd["versions"][-1]
    pin = pn["google"]
    r.ok(last["version"] == pin["version"] == hist["pin"], f"última versão = pin {pin['version']}",
         f"última versão {last['version']} != pin {pin['version']}")
    r.ok(last.get("schema_sha256") == pin["schema_sha256"], "schema_sha256 do pin = pins.json (C13-HIST-PIN)",
         "schema_sha256 da última versão != pins.json")
    t = xd.get("totals", {})
    r.ok(t == {"listed": len(sel), "extracted": n_ok, "unavailable": n_un},
         f"totais: {len(sel)} listadas, {n_ok} extraídas, {n_un} indisponíveis",
         f"totais do extraction.json ({t}) não batem com as linhas")
    r.summary = {"listed": len(sel), "extracted": n_ok, "unavailable": n_un}
    return r


def main(argv=None) -> int:
    args = [a for a in (argv or []) if a != C.ID]
    deep = "--deep" in args
    args = [a for a in args if a != "--deep"]
    if args:
        print(f"check: argumentos desconhecidos: {args}", file=sys.stderr)
        return 2
    r = run(deep)
    s = getattr(r, "summary", {})
    print(f"[{C.now()}] bo.hist.check {C.ID}: {len(r.oks)} conferência(s) OK, {len(r.fails)} falha(s); "
          f"{s.get('listed', '?')} listadas, {s.get('extracted', '?')} extraídas, "
          f"{s.get('unavailable', '?')} indisponíveis com motivo -> {'OK' if not r.fails else 'FAIL'}")
    for f in r.fails:
        print(f"  FAIL {f}")
    return 0 if not r.fails else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
