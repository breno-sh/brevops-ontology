"""Gera, offline e de forma determinística, a partir do instantâneo em $BO_DATA/PINS/registry_index/:

  $BO_REPO/universe/pins.json             C13 pins: Terraform CLI e a versão estável de cada provider no corte
  $BO_REPO/universe/history_versions.json  lista histórica dos 4 providers (cada um um documento C13 versions)
  $BO_REPO/results/PINS/selection.json     decisão: corte, regra, números, comparação com o pin anterior

  python -I -m bo.pins.build [--check]     --check: regenera em memória e compara byte a byte (sai 1 se diverge)

generated_at = instante do instantâneo (não o relógio), para que duas execuções deem os mesmos bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from . import config, semver
from . import select as S

CONTRACT = {"contract": "C13", "contract_version": "3.0.0"}


class BuildError(Exception):
    pass


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def portable(p: Path) -> str:
    s = str(p)
    for var, root in (("$BO_DATA", config.bo_data()), ("$BO_REPO", config.bo_repo())):
        if s.startswith(str(root) + "/"):
            return var + s[len(str(root)):]
    return s


class Index:
    """Leitura do instantâneo com conferência de sha256 de cada arquivo contra o snapshot.json."""

    def __init__(self, root: Path | None = None):
        self.root = root or config.index_dir()
        sp = self.root / "snapshot.json"
        if not sp.exists():
            raise BuildError(f"instantâneo ausente: {sp} (rode python -I -m bo.pins.fetch)")
        self.snapshot_bytes = sp.read_bytes()
        self.snap = json.loads(self.snapshot_bytes)
        self.files = {f["path"]: f for f in self.snap["files"]}

    def read(self, rel: str) -> bytes:
        rec = self.files.get(rel)
        if rec is None:
            raise BuildError(f"{rel} não está no snapshot.json")
        b = (self.root / rel).read_bytes()
        if sha256_bytes(b) != rec["sha256"]:
            raise BuildError(f"{rel}: sha256 diverge do snapshot.json (instantâneo alterado)")
        return b

    def json(self, rel: str):
        return json.loads(self.read(rel))

    def sha(self, rel: str) -> str:
        self.read(rel)
        return self.files[rel]["sha256"]

    def ref(self, rel: str) -> dict:
        return {"path": portable(self.root / rel), "sha256": self.sha(rel)}


def provider_releases(ix: Index, p: str) -> list[S.Release]:
    base = f"providers/{p}"
    rels, issues = S.releases_from_registry(ix.json(f"{base}/registry-v1-versions.json"),
                                            ix.json(f"{base}/registry-v2-provider-versions.json"))
    if issues:
        raise BuildError(f"{p}: v1 e v2 do Registry divergem: {'; '.join(issues)}")
    return rels


def prefetch_schema(p: str, version: str, source: str, zip_sha: str) -> dict:
    """sha256 do providers-schema.json da pré-busca, conferido contra o MANIFEST.json dela, contra o lock (versão
    e zh: do zip assinado) e contra a chave do provider no próprio JSON. Sem pré-busca da versão: erro claro."""
    d = config.prefetch_dir() / p / version
    man_p, sch_p, lock_p = d / "MANIFEST.json", d / "providers-schema.json", d / "terraform.lock.hcl"
    for f in (man_p, sch_p, lock_p):
        if not f.exists():
            raise BuildError(f"{p} {version}: {f} ausente; extraia o schema da versão fixada (D1) antes do build")
    man = json.loads(man_p.read_bytes())
    want = {x["path"]: x["sha256"] for x in man.get("files", [])}
    sch_sha = sha256_file(sch_p)
    if want.get("providers-schema.json") != sch_sha:
        raise BuildError(f"{p} {version}: providers-schema.json diverge do MANIFEST.json da pré-busca")
    if not str(man.get("terraform_cli", "")).startswith(config.TERRAFORM_VERSION + " "):
        raise BuildError(f"{p} {version}: schema extraído com Terraform {man.get('terraform_cli')!r}, "
                         f"não {config.TERRAFORM_VERSION}")
    lock = lock_p.read_text(encoding="utf-8")
    m = re.search(r'provider\s+"([^"]+)"\s*\{\s*version\s*=\s*"([^"]+)"', lock)
    h1 = re.findall(r'"(h1:[A-Za-z0-9+/=]+)"', lock)
    zh = re.findall(r'"zh:([0-9a-f]{64})"', lock)
    # instalado por filesystem_mirror: o lock só traz h1 (hash do conteúdo descompactado); zh, se houver, tem de
    # ser o zip assinado
    if not m or m.group(1) != source or m.group(2) != version or not h1 or (zh and zip_sha not in zh):
        raise BuildError(f"{p} {version}: terraform.lock.hcl da pré-busca não é deste provider/versão/zip")
    doc = json.loads(sch_p.read_bytes())
    ps = doc.get("provider_schemas", {})
    if list(ps) != [source]:
        raise BuildError(f"{p} {version}: providers-schema.json traz {list(ps)}, esperado [{source}]")
    blk = ps[source]
    canon = json.dumps(blk, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"schema_sha256": sch_sha, "schema_canonical_sha256": sha256_bytes(canon), "lock_h1": h1,
            "schema_file": portable(sch_p), "schema_bytes": sch_p.stat().st_size,
            "format_version": doc.get("format_version"),
            "counts": {k: len(blk.get(k) or {}) for k in ("resource_schemas", "data_source_schemas",
                                                          "ephemeral_resource_schemas", "list_resource_schemas",
                                                          "action_schemas", "functions")}}


def legacy_pins() -> dict:
    p = config.legacy_versions_tf()
    if not p.exists():
        return {"file": str(p), "missing": True, "providers": {}}
    txt = p.read_text(encoding="utf-8")
    out = {}
    for name, src, ver in re.findall(r'(\w+)\s*=\s*\{\s*source\s*=\s*"([^"]+)"\s*,\s*version\s*=\s*"([^"]+)"', txt):
        out[name] = {"source": src, "version": ver}
    return {"file": str(p), "sha256": sha256_file(p), "providers": out}


def build(ix: Index | None = None) -> dict[str, bytes]:
    ix = ix or Index()
    snap = ix.snap
    if snap.get("cutoff_date") != config.CUTOFF_DATE.isoformat():
        raise BuildError(f"instantâneo feito para o corte {snap.get('cutoff_date')}, config diz {config.CUTOFF_DATE}")
    fetched = S.parse_ts(snap["fetched_at"])
    end = config.cutoff_end()
    if fetched < end:
        raise BuildError("instantâneo anterior ao fim do dia de corte: o índice pode não ter o dia inteiro")
    gen = snap["fetched_at"]
    ver = ix.json("verification.json")

    # Terraform CLI
    tv = config.TERRAFORM_VERSION
    os_, arch = config.TERRAFORM_PLATFORM
    tsums = ix.read(f"terraform/terraform_{tv}_SHA256SUMS").decode()
    tlines = dict(reversed(ln.split()) for ln in tsums.splitlines() if ln.strip())
    tf_zip = f"terraform_{tv}_{os_}_{arch}.zip"
    tf_sha = tlines[tf_zip]
    tv_ok = ver["terraform"]
    if not (tv_ok["signature"]["good"] and tv_ok["zip_sha256"] == tf_sha and tv_ok["local_matches_official"]):
        raise BuildError("Terraform CLI: assinatura, zip ou binário local não conferem (verification.json)")
    tf_rel = ix.json(f"terraform/releases-terraform-{tv}.json")
    tf_list = ix.json("terraform/releases-terraform-latest20.json")
    tf_items = [(r["version"], S.parse_ts(r["timestamp_created"])) for r in tf_list]
    if min(t for _, t in tf_items) >= end:
        raise BuildError("a página de releases do Terraform não alcança a data de corte")
    tf_stable_at_cutoff = max((v for v, t in tf_items if t < end and not semver.is_prerelease(v)), key=semver.key)

    pins_providers, hist_providers, sel_providers = [], [], []
    legacy = legacy_pins()
    for p, (ns, typ) in config.PROVIDERS.items():
        source = f"registry.terraform.io/{ns}/{typ}"
        base = f"providers/{p}"
        rels = provider_releases(ix, p)
        pin, picks, det = S.history(rels)
        v = pin.version
        vrec = ver[p]
        if vrec["version"] != v:
            raise BuildError(f"{p}: o fetch conferiu {vrec['version']}, a regra escolhe {v}")
        sums_rel = f"{base}/terraform-provider-{typ}_{v}_SHA256SUMS"
        sums_sha = ix.sha(sums_rel)
        good = (vrec.get("signature_vendor_key") or vrec["signature"])["good"]
        if not (vrec["signature"]["valid"] and good and vrec["zip_sha256_in_shasums"]):
            raise BuildError(f"{p} {v}: SHA256SUMS sem assinatura válida (verification.json)")
        sch = prefetch_schema(p, v, source, vrec["zip_sha256"])
        pins_providers.append({"provider": p, "source": source, "version": v, "shasums_sha256": sums_sha,
                               "schema_sha256": sch["schema_sha256"]})
        v2_rel = f"{base}/registry-v2-provider-versions.json"
        v2_sha = ix.sha(v2_rel)
        versions = []
        selection = []
        for pk in picks:
            r = pk.release
            item = {"version": r.version, "released_at": r.date_recife}
            if r.version == v:
                item["schema_sha256"] = sch["schema_sha256"]
            versions.append(item)
            selection.append({"version": r.version, "published_at": r.published_iso, "released_at": r.date_recife,
                              "reasons": pk.reasons, "index_sha256": v2_sha, "protocols": list(r.protocols),
                              "darwin_arm64": "darwin_arm64" in r.platforms,
                              "linux_amd64": "linux_amd64" in r.platforms})
        hist_providers.append({
            "provider": p, "source": source, "pin": v,
            "index_files": {"registry_v1": ix.ref(f"{base}/registry-v1-versions.json"), "registry_v2": ix.ref(v2_rel)},
            "versions_doc": {"schema": "bo.versions/1", **CONTRACT, "module": config.MODULE, "generated_at": gen,
                             "provider": p, "versions": versions},
            "selection": selection,
            "left_truncation": det["left_truncation"],
        })
        stable = [r for r in rels if r.stable]
        lg = legacy["providers"].get(p)
        lg_info = None
        if lg:
            lr = next((r for r in rels if r.version == lg["version"]), None)
            lg_info = {"version": lg["version"], "published_at": lr.published_iso if lr else None,
                       "stable_releases_between_legacy_and_pin":
                           sum(1 for r in stable if lr and lr.published_at < r.published_at < end
                               and semver.key(r.version) > semver.key(lr.version))}
        sel_providers.append({
            "provider": p, "source": source, "pin": v, "pin_published_at": pin.published_iso,
            "pin_age_days_at_cutoff": (end - pin.published_at).days,
            "releases_total": len(rels), "stable_total": len(stable), "prerelease_total": det["prerelease_total"],
            "stable_in_window": det["stable_in_window"], "history_selected": len(picks),
            "quarters": len(det["quarters"]), "quarters_without_release": det["quarters_without_release"],
            "majors_in_window": [pk.release.version for pk in picks
                                 if any(x.startswith("major_first:") for x in pk.reasons)],
            "index_first_in_window": [pk.release.version for pk in picks if "index_first" in pk.reasons],
            "history_without_darwin_arm64": [s["version"] for s in selection if not s["darwin_arm64"]],
            "history_protocols": sorted({x for s in selection for x in s["protocols"]}),
            "published_after_cutoff_in_snapshot": det["published_after_cutoff"],
            "left_truncation": det["left_truncation"],
            "signature": {"registry_key_good": vrec["signature"]["good"],
                          "registry_key_expired_copy": vrec["signature"]["expired_key"],
                          "vendor_key_good": (vrec.get("signature_vendor_key") or {}).get("good"),
                          "primary_fingerprint": vrec["signature"]["primary_fingerprint"]},
            "schema": {k: sch[k] for k in ("schema_sha256", "schema_canonical_sha256", "lock_h1", "schema_file",
                                           "schema_bytes", "format_version", "counts")},
            "legacy_pin": lg_info,
        })

    pins = {"schema": "bo.pins/1", **CONTRACT, "module": config.MODULE, "generated_at": gen,
            "terraform": {"version": tv, "sha256": tf_sha}, "providers": pins_providers}
    cutoff = {"date": config.CUTOFF_DATE.isoformat(), "timezone": "America/Recife",
              "end_exclusive": end.isoformat(),
              "rule": "pin = maior versão SemVer sem pré-lançamento com published-at (Registry v2) antes de "
                      "end_exclusive; a mesma data para os 4 providers"}
    window = {"start": config.HISTORY_START.isoformat(),
              "rule": "estado (mesma regra do pin) no fim de cada trimestre completo desde start; mais a primeira "
                      "estável de cada major publicada na janela; mais o pin. Antes de start: truncamento à "
                      "esquerda declarado (left_truncation)."}
    snapshot_ref = {"path": portable(ix.root / "snapshot.json"), "sha256": sha256_bytes(ix.snapshot_bytes),
                    "fetched_at": snap["fetched_at"]}
    history = {"schema": "bo.history_versions/1", **CONTRACT, "module": config.MODULE, "generated_at": gen,
               "cutoff": cutoff, "window": window, "index": snapshot_ref, "providers": hist_providers,
               "note": "Cada providers[].versions_doc é um documento C13 versions completo; o envelope com 4 "
                       "providers não tem tipo próprio no C13 3.0.0 (ver results/PINS/CONTRACT_CHANGE.txt)."}
    spread = [S.parse_ts(x["legacy_pin"]["published_at"]) for x in sel_providers
              if x["legacy_pin"] and x["legacy_pin"]["published_at"]]
    selection = {
        "schema": "bo.pins.selection/1", "module": config.MODULE, "generated_at": gen,
        "cutoff": cutoff, "window": window, "index": snapshot_ref,
        "terraform": {"pinned": tv, "pinned_published_at": tf_rel["timestamp_created"],
                      "pinned_status": tf_rel.get("status", {}).get("state"), "zip": tf_zip, "zip_sha256": tf_sha,
                      "stable_at_cutoff": tf_stable_at_cutoff,
                      "local_binary_matches_official": tv_ok["local_matches_official"],
                      "why_not_stable_at_cutoff":
                          "o CLI é ferramenta de extração, não objeto de estudo: fica no que o ambiente usa (mise "
                          "global) e que gerou os schemas da pré-busca; trocar mudaria o PATH global do Mac e o "
                          "formato de saída do schema (e com ele os sha256). A data de corte vale para os providers."},
        "providers": sel_providers,
        "legacy": {"file": legacy["file"], "sha256": legacy.get("sha256"),
                   "published_span_hours": round((max(spread) - min(spread)).total_seconds() / 3600, 1)
                   if len(spread) > 1 else None,
                   "note": "pins anteriores (catálogo C1, versions.tf): versões escolhidas sem data de corte "
                           "declarada; published_span_hours = distância entre a mais antiga e a mais nova delas. O "
                           "PINS declara a data e a regra, e conta quantas estáveis saíram entre cada pin antigo e o "
                           "novo (providers[].legacy_pin)."},
        "schema_sha256_definition": "sha256 dos bytes de `terraform providers schema -json` (Terraform "
                                    f"{tv} {os_}_{arch}) com main.tf só com required_providers desse provider; "
                                    "schema_canonical_sha256 = sha256 do bloco do provider em JSON canônico "
                                    "(chaves ordenadas, sem espaços), estável entre versões do CLI que não mudem o "
                                    "conteúdo",
    }
    return {"universe/pins.json": dumps(pins), "universe/history_versions.json": dumps(history),
            "results/PINS/selection.json": dumps(selection)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.pins.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    try:
        out = build()
    except BuildError as e:
        print(f"[{config.now_iso()}] build: ERRO {e}", file=sys.stderr)
        return 1
    root = config.bo_repo()
    bad = []
    for rel, b in out.items():
        p = root / rel
        if a.check:
            if not p.exists() or p.read_bytes() != b:
                bad.append(rel)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
    if a.check:
        if bad:
            print(f"[{config.now_iso()}] regeneração DIVERGE: {', '.join(bad)}", file=sys.stderr)
            return 1
        print(f"[{config.now_iso()}] regeneração idêntica: {', '.join(out)}")
        return 0
    write_manifest(root)
    print(f"[{config.now_iso()}] gravados: {', '.join(out)} e results/PINS/MANIFEST.sha256")
    return 0


MANIFEST_FILES = ["universe/pins.json", "universe/history_versions.json", "results/PINS/selection.json",
                  "results/PINS/CONTRACT_CHANGE.txt"]


def manifest_text(root: Path) -> str:
    lines = [f"{sha256_file(root / rel)}  {rel}" for rel in MANIFEST_FILES if (root / rel).exists()]
    return "\n".join(lines) + "\n"


def write_manifest(root: Path) -> None:
    (root / "results/PINS/MANIFEST.sha256").write_text(manifest_text(root), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
