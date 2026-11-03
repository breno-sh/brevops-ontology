"""Gate do PINS: 4 providers, mesma data de corte, toda versão com data e sha do índice.

  python -I -m bo.pins.check

Confere, sem rede:
  1. instantâneo: cada arquivo de registry_index/ com o sha256 do snapshot.json e do MANIFEST.sha256; feito
     depois do fim do dia de corte (o índice cobre o dia inteiro);
  2. regeneração: build em memória = bytes de universe/pins.json, universe/history_versions.json e
     results/PINS/selection.json; MANIFEST.sha256 de results/PINS confere;
  3. pins.json: contrato C13 (validador único), exatamente os 4 providers, cada versão = a estável no MESMO
     corte, shasums_sha256 = arquivo do instantâneo, assinatura do SHA256SUMS conferida de novo (gpgv),
     schema_sha256 = providers-schema.json da pré-busca, Terraform = zip do SHA256SUMS assinado;
  4. history_versions.json: mesmo corte e mesmo instantâneo do pins.json; cada versions_doc é C13 versions
     válido; toda versão com data (released_at e published_at) e index_sha256 = sha do arquivo v2 do
     instantâneo; data confere com o índice; datas monótonas na ordem SemVer; todo trimestre completo e toda
     major da janela presentes; a última versão é o pin.
Sai 0 se tudo confere, 1 caso contrário."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from . import build as B
from . import config, semver, sig
from . import select as S


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.oks: list[str] = []

    def ok(self, cond: bool, msg: str, err: str | None = None) -> bool:
        (self.oks if cond else self.errors).append(msg if cond else (err or msg))
        return cond


def check_index(r: Report, ix: B.Index) -> None:
    bad = []
    for rel in ix.files:
        try:
            ix.read(rel)
        except (B.BuildError, OSError) as e:
            bad.append(str(e))
    r.ok(not bad, f"instantâneo: {len(ix.files)} arquivo(s) com sha256 do snapshot.json",
         "instantâneo alterado: " + "; ".join(bad[:3]))
    man = ix.root / "MANIFEST.sha256"
    mism = []
    if man.exists():
        for ln in man.read_text(encoding="utf-8").splitlines():
            h, rel = ln.split("  ", 1)
            p = ix.root / rel
            if not p.exists() or B.sha256_file(p) != h:
                mism.append(rel)
        listed = {ln.split("  ", 1)[1] for ln in man.read_text(encoding="utf-8").splitlines()}
        extra = {p.relative_to(ix.root).as_posix() for p in ix.root.rglob("*") if p.is_file()} - listed - {
            "MANIFEST.sha256"}
        mism += [f"fora do manifesto: {x}" for x in sorted(extra)]
    r.ok(man.exists() and not mism, "registry_index/MANIFEST.sha256 confere",
         f"registry_index/MANIFEST.sha256: {'ausente' if not man.exists() else ', '.join(mism[:5])}")
    fetched = S.parse_ts(ix.snap["fetched_at"])
    r.ok(fetched >= config.cutoff_end(),
         f"instantâneo de {ix.snap['fetched_at']} (depois do fim do corte {config.cutoff_end().isoformat()})",
         "instantâneo anterior ao fim do dia de corte")


def validate_c13(kind_alias: str, doc: dict, fname: str) -> list[str]:
    from bo.contracts import catalog, validate
    with tempfile.TemporaryDirectory(dir=config.bo_tmp()) as d:
        p = Path(d) / fname
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        fk = catalog.resolve(kind_alias, p)
        res = validate.validate_file(fk, p)
        return [f"{fk.cid}:{fk.kind}: {e}" for e in res.errors]


def check_pins(r: Report, ix: B.Index, pins: dict) -> None:
    errs = validate_c13("C13_pins", pins, "pins.json")
    r.ok(not errs, "pins.json confere com C13 pins (validador único)", "pins.json fora do C13: " + "; ".join(errs[:3]))
    provs = [p["provider"] for p in pins.get("providers", [])]
    r.ok(sorted(provs) == sorted(config.PROVIDERS) and len(provs) == 4,
         f"4 providers: {', '.join(provs)}", f"providers esperados {sorted(config.PROVIDERS)}, há {provs}")
    end = config.cutoff_end()
    ver = ix.json("verification.json")
    for p in pins.get("providers", []):
        name = p["provider"]
        if name not in config.PROVIDERS:
            continue
        ns, typ = config.PROVIDERS[name]
        base = f"providers/{name}"
        rels = B.provider_releases(ix, name)
        stable = S.stable_before(rels, end)
        r.ok(stable is not None and p["version"] == stable.version,
             f"{name} {p['version']} = estável no corte {config.CUTOFF_DATE}",
             f"{name}: pin {p['version']} ≠ estável no corte ({stable.version if stable else None})")
        r.ok(p["source"] == f"registry.terraform.io/{ns}/{typ}", f"{name}: source {p['source']}",
             f"{name}: source {p['source']} inesperado")
        sums_rel = f"{base}/terraform-provider-{typ}_{p['version']}_SHA256SUMS"
        if not r.ok(sums_rel in ix.files and p.get("shasums_sha256") == ix.sha(sums_rel),
                    f"{name}: shasums_sha256 = SHA256SUMS do instantâneo",
                    f"{name}: shasums_sha256 não é o SHA256SUMS do instantâneo"):
            continue
        dl = ix.json(f"{base}/registry-download-{p['version']}-darwin_arm64.json")
        key = dl["signing_keys"]["gpg_public_keys"][0]["ascii_armor"]
        try:
            res = sig.verify(ix.root / sums_rel, ix.root / (sums_rel + ".sig"), key)
            good = res["good"]
            if not good and ns == "hashicorp":
                vk = (ix.root / "vendor_keys/hashicorp-pgp-key.txt")
                ix.read("vendor_keys/hashicorp-pgp-key.txt")
                v2 = sig.verify(ix.root / sums_rel, ix.root / (sums_rel + ".sig"), vk.read_text(encoding="utf-8"))
                good = v2["good"] and v2["primary_fingerprint"] == res["primary_fingerprint"]
            r.ok(good, f"{name}: assinatura do SHA256SUMS confere (gpgv, chave {res['primary_fingerprint'][-16:]})",
                 f"{name}: assinatura do SHA256SUMS sem GOODSIG com chave vigente")
        except sig.SigError as e:
            r.ok(False, "", f"{name}: {e}")
        r.ok(ver[name]["version"] == p["version"], f"{name}: verification.json é da versão fixada",
             f"{name}: verification.json é de {ver[name]['version']}")
        try:
            sch = B.prefetch_schema(name, p["version"], p["source"], ver[name]["zip_sha256"])
            r.ok(sch["schema_sha256"] == p["schema_sha256"], f"{name}: schema_sha256 = providers-schema.json extraído",
                 f"{name}: schema_sha256 diverge do providers-schema.json")
        except B.BuildError as e:
            r.ok(False, "", f"{name}: {e}")
    tv = config.TERRAFORM_VERSION
    t = pins.get("terraform", {})
    lines = dict(reversed(ln.split()) for ln in ix.read(f"terraform/terraform_{tv}_SHA256SUMS").decode().splitlines()
                 if ln.strip())
    r.ok(t.get("version") == tv and t.get("sha256") == lines.get(f"terraform_{tv}_darwin_arm64.zip"),
         f"Terraform {tv}: sha256 = zip darwin_arm64 do SHA256SUMS", "Terraform: versão ou sha256 não conferem")
    try:
        res = sig.verify(ix.root / f"terraform/terraform_{tv}_SHA256SUMS",
                         ix.root / f"terraform/terraform_{tv}_SHA256SUMS.72D7468F.sig",
                         ix.read("vendor_keys/hashicorp-pgp-key.txt").decode())
        r.ok(res["good"], "Terraform: SHA256SUMS assinado pela HashiCorp", "Terraform: assinatura sem GOODSIG")
    except sig.SigError as e:
        r.ok(False, "", f"Terraform: {e}")


def check_history(r: Report, ix: B.Index, pins: dict, hist: dict) -> None:
    end = config.cutoff_end()
    snap_sha = B.sha256_bytes(ix.snapshot_bytes)
    c = hist.get("cutoff", {})
    r.ok(c.get("date") == config.CUTOFF_DATE.isoformat() and c.get("end_exclusive") == end.isoformat()
         and ix.snap.get("cutoff_date") == c.get("date"),
         f"mesma data de corte em config, instantâneo e history_versions.json: {c.get('date')}",
         "data de corte diverge entre config, instantâneo e history_versions.json")
    r.ok(hist.get("index", {}).get("sha256") == snap_sha and hist.get("generated_at") == pins.get("generated_at"),
         "history_versions.json e pins.json do mesmo instantâneo", "history_versions.json de outro instantâneo")
    hp = {p["provider"]: p for p in hist.get("providers", [])}
    r.ok(sorted(hp) == sorted(config.PROVIDERS), f"history: 4 providers", f"history: providers {sorted(hp)}")
    pin_of = {p["provider"]: p["version"] for p in pins.get("providers", [])}
    qlabels = [q for q, _ in S.quarters(config.HISTORY_START, end)]
    for name, p in hp.items():
        doc = p["versions_doc"]
        errs = validate_c13("C13_versions", doc, "versions.json")
        r.ok(not errs, f"{name}: versions_doc confere com C13 versions",
             f"{name}: versions_doc fora do C13: " + "; ".join(errs[:3]))
        v2_rel = f"providers/{name}/registry-v2-provider-versions.json"
        v2_sha = ix.sha(v2_rel)
        rels = {x.version: x for x in B.provider_releases(ix, name)}
        sel = p["selection"]
        nodate = [s["version"] for s in sel if not s.get("released_at") or not s.get("published_at")]
        nosha = [s["version"] for s in sel if s.get("index_sha256") != v2_sha]
        wrong = [s["version"] for s in sel if s["version"] not in rels
                 or rels[s["version"]].published_iso != s["published_at"]
                 or rels[s["version"]].date_recife != s["released_at"]]
        r.ok(not nodate and not nosha and not wrong,
             f"{name}: {len(sel)} versão(ões), todas com data e index_sha256 do índice ({v2_sha[:12]}…)",
             f"{name}: sem data {nodate[:3]}, sem sha do índice {nosha[:3]}, data ≠ índice {wrong[:3]}")
        vs = [s["version"] for s in sel]
        r.ok(vs == [x["version"] for x in doc["versions"]]
             and [x["released_at"] for x in doc["versions"]] == [s["released_at"] for s in sel],
             f"{name}: versions_doc = selection", f"{name}: versions_doc diverge de selection")
        dates = [rels[v].published_at for v in vs if v in rels]
        r.ok(vs == sorted(vs, key=semver.key) and dates == sorted(dates),
             f"{name}: ordem SemVer e datas monótonas", f"{name}: ordem SemVer ou datas não monótonas")
        r.ok(vs and vs[-1] == pin_of.get(name) == p.get("pin")
             and doc["versions"][-1].get("schema_sha256") ==
             next(x["schema_sha256"] for x in pins["providers"] if x["provider"] == name),
             f"{name}: última versão = pin {pin_of.get(name)} com schema_sha256",
             f"{name}: última versão {vs[-1] if vs else None} ≠ pin {pin_of.get(name)}")
        reasons = [x for s in sel for x in s["reasons"]]
        rels_l = list(rels.values())
        want_q = [q for q, nxt in zip(qlabels, [n for _, n in S.quarters(config.HISTORY_START, end)])
                  if S.stable_before(rels_l, nxt) is not None]
        got_q = [x.split(":", 1)[1] for x in reasons if x.startswith("quarter_end:")]
        r.ok(got_q == want_q, f"{name}: {len(got_q)} trimestre(s) completos amostrados ({want_q[0]}–{want_q[-1]})",
             f"{name}: trimestres {got_q} ≠ esperados {want_q}")
        firsts = S.first_of_each_major(rels_l, config.day_start(config.HISTORY_START), end)
        want_m = [(r_.version, why) for r_, why in firsts]
        got_m = [(s["version"], x) for s in sel for x in s["reasons"] if x.startswith(("major_first", "index_first"))]
        r.ok(sorted(got_m) == sorted(want_m), f"{name}: majors da janela {', '.join(v for v, _ in want_m)}",
             f"{name}: majors {got_m} ≠ esperadas {want_m}")
        for s in sel:
            q = rels[s["version"]]
            for why in s["reasons"]:
                if why.startswith("quarter_end:"):
                    nxt = dict(S.quarters(config.HISTORY_START, end))[why.split(":", 1)[1]]
                    if S.stable_before(rels_l, nxt).version != q.version:
                        r.ok(False, "", f"{name}: {s['version']} não é o estado de {why}")


def run() -> Report:
    r = Report()
    try:
        ix = B.Index()
    except B.BuildError as e:
        r.ok(False, "", str(e))
        return r
    check_index(r, ix)
    root = config.bo_repo()
    try:
        out = B.build(ix)
    except B.BuildError as e:
        r.ok(False, "", f"build: {e}")
        return r
    for rel, b in out.items():
        p = root / rel
        r.ok(p.exists() and p.read_bytes() == b, f"regeneração idêntica: {rel}", f"regeneração diverge: {rel}")
    man = root / "results/PINS/MANIFEST.sha256"
    r.ok(man.exists() and man.read_text(encoding="utf-8") == B.manifest_text(root),
         "results/PINS/MANIFEST.sha256 confere", "results/PINS/MANIFEST.sha256 diverge")
    pins_p, hist_p = config.pins_path(), config.history_path()
    if not (pins_p.exists() and hist_p.exists()):
        r.ok(False, "", "universe/pins.json ou universe/history_versions.json ausente")
        return r
    pins = json.loads(pins_p.read_bytes())
    hist = json.loads(hist_p.read_bytes())
    check_pins(r, ix, pins)
    check_history(r, ix, pins, hist)
    return r


def main(argv=None) -> int:
    r = run()
    for m in r.oks:
        print(f"  OK   {m}")
    for m in r.errors:
        print(f"  FAIL {m}")
    print(f"[{config.now_iso()}] bo.pins.check: {len(r.oks)} conferência(s) OK, {len(r.errors)} falha(s) -> "
          f"{'OK' if not r.errors else 'REPROVADO'}")
    return 0 if not r.errors else 1


if __name__ == "__main__":
    sys.exit(main())
