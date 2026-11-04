"""Gera as fixtures de calibração, a resposta esperada e (com --seal) as fixtures retidas cifradas.

  python -I -m bo.pilot_sto_oracle.build            regrava a calibração, expected_answers.json, MANDATORY.json,
                                                    RULES.json e ORACLE.sha256 (as retidas já seladas ficam)
  python -I -m bo.pilot_sto_oracle.build --seal     sorteia retidas novas, confere avaliador == resposta analítica e
                                                    schema fixado, cifra com o certificado público da VM (D15) e só
                                                    então grava; o texto claro nunca toca o disco
  python -I -m bo.pilot_sto_oracle.build --check    regenera a calibração em $BO_TMP e compara byte a byte
                                                    (generated_at não conta); confere o selo contra o índice

Antes de gravar qualquer coisa, toda conferência analítica tem de bater com o avaliador (pilot/sto/oracle).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import cases, schema_check

MODULE = "PILOT-STO-ORACLE"
TZ = dt.timezone(dt.timedelta(hours=-3))
SCHEMA_EA = "bo.pilot.sto.expected_answers/1"
SCHEMA_ENTRY = "bo.pilot.sto.direction_entry/1"
SCHEMA_HELD = "bo.pilot.sto.heldout_bundle/1"
SCHEMA_INDEX = "bo.pilot.sto.sealed_index/1"
PAIR = {frozenset(("aws", "google")): ("AWSGCP", "aws"), frozenset(("aws", "azurerm")): ("AWSAZ", "aws"),
        frozenset(("aws", "oci")): ("AWSOCI", "aws"), frozenset(("google", "azurerm")): ("GCPAZ", "google"),
        frozenset(("google", "oci")): ("GCPOCI", "google"), frozenset(("azurerm", "oci")): ("AZOCI", "azurerm")}


def now_iso():
    return dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def sto(root=None) -> Path:
    return (root or repo()) / "pilot" / "sto"


def sealed_dir() -> Path:
    return data() / MODULE / "sealed"


def load_oracle(root=None):
    path = sto(root) / "oracle" / "sto_oracle.py"
    spec = importlib.util.spec_from_file_location("sto_oracle", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def canon(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    return sha(p.read_bytes())


# ------------------------------------------------------------------ conferência analítica × avaliador
def verify(gen, oracle):
    bad = []
    for f in gen.fixtures:
        for c in f["checks"]:
            try:
                ok, got = oracle.evaluate_check(f["fixture"], c)
            except Exception as e:  # noqa: BLE001 (relatado e reprovado)
                ok, got = False, repr(e)
            if not ok:
                bad.append(f"{f['fixture']['fixture_id']} {c['kind']}: esperado {c['expect']!r}, avaliador {got!r}")
        bad += schema_check.check_fixture(f["fixture"])
        if not oracle.polarity_consistent(f["fixture"]["polarity"], f["checks"]):
            bad.append(f"{f['fixture']['fixture_id']}: polaridade {f['fixture']['polarity']} sem a conferência que a define")
    for e in gen.entries:
        try:
            ok, j = oracle.evaluate_entry(e)
        except Exception as ex:  # noqa: BLE001
            ok, j = False, repr(ex)
        if not ok:
            bad.append(f"{e['entry_id']}: esperado {e['expect']!r}, avaliador {j!r}"[:400])
        bad += schema_check.check_fixture(e["source"]) + schema_check.check_fixture(e["target"])
    return bad


def c11_seed(e):
    a, b = e["direction"].split("->")
    pair, first = PAIR[frozenset((a, b))]
    fam = e["family"]
    src = e["source"]
    if fam.startswith("T1"):
        values = [{"var": "psto:versioning", "term": {"kind": "literal", "datatype": "string", "value": "ENABLED"}}]
    elif fam.startswith("T2"):
        values = [{"var": "psto:anonymous_read", "term": {"kind": "literal", "datatype": "bool", "value": True}},
                  {"var": "psto:anonymous_list", "term": {"kind": "literal", "datatype": "bool", "value": False}}]
    else:
        values = [{"var": "psto:timeline_eval_day", "term": {"kind": "literal", "datatype": "number", "value": src["timeline"]["eval_day"]}}]
    return {"case_id": "CASE-PSTO-" + e["entry_id"], "group_id": f"G-PSTO-{fam.split('-')[0]}-{pair}",
            "stratum_partial": {"pair": pair, "domain": "STO", "cardinality": "1:1",
                                "direction": "forward" if a == first else "inverse"},
            "side": "subject", "comparator": {"name": "exact"}, "cost_class": "free", "values": values,
            "pending": {"claim_id": "o oráculo não lê alegações (independente do mapeamento); vem do PILOT-STO-MAP",
                        "claim_version_id": "idem", "stratum.relation": "sai da alegação",
                        "frame_ref": "piloto não sorteia: sem frame do DEPSAMPLE", "weight": "idem",
                        "lowering_plan": "plano C26 do PILOT-STO-E2E", "origin": "nenhum valor do C11 3.0.1 descreve caso de piloto"}}


# ------------------------------------------------------------------ escrita da calibração
def write_calib(root: Path, gen, oracle, index: dict | None, generated_at: str):
    base = sto(root)
    fc = base / "fixtures_calib"
    if fc.exists():
        shutil.rmtree(fc)
    fixtures, directions = {}, {}
    for f in gen.fixtures:
        fx = f["fixture"]
        rel = f"fixtures_calib/{fx['provider']}/{fx['fixture_id']}.json"
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_bytes(canon(fx))
        fixtures[fx["fixture_id"]] = {"file": f"pilot/sto/{rel}", "provider": fx["provider"], "case": fx["case"],
                                      "polarity": fx["polarity"], "summary": fx["summary"],
                                      "invariant_group": fx.get("invariant_group"), "checks": f["checks"]}
    for e in gen.entries:
        a, b = e["direction"].split("->")
        rel = f"fixtures_calib/directions/{a}-{b}/{e['entry_id']}.json"
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        doc = {"schema": SCHEMA_ENTRY, "entry_id": e["entry_id"], "direction": e["direction"], "family": e["family"],
               "variant": e["variant"], "note": e["note"], "source": e["source"], "target": e["target"],
               "container_map": e["container_map"], "declared_losses": e["declared_losses"]}
        (base / rel).write_bytes(canon(doc))
        directions[e["entry_id"]] = {"file": f"pilot/sto/{rel}", "direction": e["direction"], "family": e["family"],
                                     "variant": e["variant"], "polarity": e["polarity"], "declared_losses": e["declared_losses"],
                                     "expect": e["expect"], "note": e["note"], "c11_case_seed": c11_seed(e)}
    (base / "oracle" / "MANDATORY.json").write_bytes(canon({
        "schema": "bo.pilot.sto.mandatory/1", "mandatory_cases": cases.MANDATORY, "direction_families": cases.FAMILIES,
        "directions": [f"{a}->{b}" for a, b in cases.DIRECTIONS], "polarities": list(cases.POL),
        "loss_codes": oracle.LOSS_CODES, "never_coverable": sorted(oracle.NEVER_COVERABLE)}))
    (base / "oracle" / "RULES.json").write_bytes(canon({"schema": "bo.pilot.sto.rules/1", "oracle_version": oracle.ORACLE_VERSION,
                                                        "docs_root": "$BO_DATA/downloads/", "rules": oracle.RULES}))
    ea = {"schema": SCHEMA_EA, "contract": "C24", "contract_version": "1.0.0", "module": MODULE,
          "generated_at": generated_at, "oracle_version": oracle.ORACLE_VERSION,
          "oracle_sha256": sha_file(base / "oracle" / "sto_oracle.py"), "providers": cases.PIN,
          "note": ("resposta esperada escrita a partir dos compromissos (C24), da evidência publicada (SERVICE-EVIDENCE e docs "
                   "fixados) e das fórmulas de cases.py; conferida contra o avaliador antes de gravar; nunca saída de mapeador. "
                   "Retidas: só o índice abaixo; o conteúdo existe só cifrado."),
          "fixtures": fixtures, "directions": directions,
          "heldout": None if index is None else {k: index[k] for k in (
              "sealed_file", "ciphertext_sha256", "plaintext_sha256", "recipient_fingerprint_sha256", "counts", "sealed_at")}}
    (base / "expected_answers.json").write_bytes(canon(ea))


def write_manifest(root: Path):
    base = sto(root)
    files = [p for p in sorted((base / "oracle").rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    files += sorted(p for p in (base / "fixtures_calib").rglob("*.json"))
    files.append(base / "expected_answers.json")
    lines = [f"{sha_file(p)}  {p.relative_to(root)}" for p in files]
    sd = sealed_dir()
    for name in ("heldout.cms.pem", "SEALED_INDEX.json", "recipient_cert.pem"):
        p = sd / name
        if p.exists():
            lines.append(f"{sha_file(p)}  {p}")
    (base / "ORACLE.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ selagem
def cert_fingerprint(cert: Path) -> str:
    out = subprocess.run(["openssl", "x509", "-in", str(cert), "-noout", "-fingerprint", "-sha256"],
                         capture_output=True, text=True, check=True).stdout
    return out.strip().split("=", 1)[1].replace(":", "").lower()


def item_hash(obj) -> str:
    return sha(canon(obj))


def seal(gen, oracle) -> dict:
    sd = sealed_dir()
    cert = sd / "recipient_cert.pem"
    if not cert.is_file():
        raise SystemExit(f"certificado público ausente: {cert} (D15: só a pública vem da VM)")
    bundle = {"schema": SCHEMA_HELD, "module": MODULE, "oracle_version": oracle.ORACLE_VERSION,
              "fixtures": gen.fixtures, "entries": gen.entries}
    plain = canon(bundle)
    tmp = sd / "heldout.cms.pem.tmp"
    r = subprocess.run(["openssl", "cms", "-encrypt", "-binary", "-aes256", "-outform", "PEM", "-out", str(tmp), str(cert)],
                       input=plain, capture_output=True)
    if r.returncode != 0:
        raise SystemExit("openssl cms -encrypt falhou: " + r.stderr.decode(errors="replace")[:300])
    tmp.replace(sd / "heldout.cms.pem")
    items = []
    for f in gen.fixtures:
        fx = f["fixture"]
        items.append({"item_id": fx["fixture_id"], "kind": "fixture", "case": fx["case"], "polarity": fx["polarity"],
                      "provider": fx["provider"], "n_checks": len(f["checks"]), "sha256": item_hash(fx)})
    for e in gen.entries:
        items.append({"item_id": e["entry_id"], "kind": "direction_entry", "family": e["family"], "polarity": e["polarity"],
                      "direction": e["direction"], "sha256": item_hash({"source": e["source"], "target": e["target"]})})
    counts = {"fixtures": len(gen.fixtures), "direction_entries": len(gen.entries), "checks": sum(len(f["checks"]) for f in gen.fixtures)}
    idx = {"schema": SCHEMA_INDEX, "module": MODULE, "sealed_at": now_iso(),
           "sealed_file": f"$BO_DATA/{MODULE}/sealed/heldout.cms.pem", "cipher": "openssl cms -encrypt -aes256 (PEM)",
           "ciphertext_sha256": sha_file(sd / "heldout.cms.pem"), "plaintext_sha256": sha(plain),
           "recipient_fingerprint_sha256": cert_fingerprint(cert),
           "recipient_note": "certificado público da VM Oracle do Breno (D15); a chave privada nunca saiu de lá",
           "reader": "PILOT-EXIT (o Breno decifra na VM; nenhum agente lê o texto claro antes)",
           "counts": counts, "items": items}
    (sd / "SEALED_INDEX.json").write_bytes(canon(idx))
    return idx


# ------------------------------------------------------------------ main
def build(root: Path, do_seal: bool, generated_at: str | None = None):
    oracle = load_oracle(root)
    calib = cases.generate("calib")
    bad = verify(calib, oracle)
    if bad:
        for b in bad[:30]:
            print("  DIVERGE", b)
        raise SystemExit(f"calibração: {len(bad)} divergência(s) entre a resposta analítica e o avaliador")
    index = None
    if do_seal:
        held = cases.generate("heldout")
        bad = verify(held, oracle)
        if bad:
            raise SystemExit(f"retidas: {len(bad)} divergência(s) (texto não impresso: partição selada)")
        index = seal(held, oracle)
        del held
    elif (sealed_dir() / "SEALED_INDEX.json").exists():
        index = json.loads((sealed_dir() / "SEALED_INDEX.json").read_text(encoding="utf-8"))
    write_calib(root, calib, oracle, index, generated_at or now_iso())
    return calib, index


def _strip(b: bytes) -> bytes:
    try:
        d = json.loads(b)
    except ValueError:
        return b
    if isinstance(d, dict):
        d.pop("generated_at", None)
    return canon(d)


def check() -> int:
    root = repo()
    tmp = Path(os.environ.get("BO_TMP", str(data() / "tmp" / MODULE))) / "regen"
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "pilot" / "sto" / "oracle").mkdir(parents=True)
    shutil.copy2(sto(root) / "oracle" / "sto_oracle.py", tmp / "pilot" / "sto" / "oracle" / "sto_oracle.py")
    build(tmp, do_seal=False, generated_at="X")
    diffs = []
    for p in sorted((tmp / "pilot" / "sto").rglob("*.json")):
        rel = p.relative_to(tmp)
        q = root / rel
        if not q.exists() or _strip(q.read_bytes()) != _strip(p.read_bytes()):
            diffs.append(str(rel))
    have = {p.relative_to(root) for p in (sto(root) / "fixtures_calib").rglob("*.json")}
    want = {p.relative_to(tmp) for p in (tmp / "pilot" / "sto" / "fixtures_calib").rglob("*.json")}
    diffs += [f"sobra: {x}" for x in sorted(have - want)]
    idx = json.loads((sealed_dir() / "SEALED_INDEX.json").read_text(encoding="utf-8"))
    if sha_file(sealed_dir() / "heldout.cms.pem") != idx["ciphertext_sha256"]:
        diffs.append("heldout.cms.pem não bate com o índice selado")
    if cert_fingerprint(sealed_dir() / "recipient_cert.pem") != idx["recipient_fingerprint_sha256"]:
        diffs.append("certificado do destinatário mudou")
    shutil.rmtree(tmp)
    for d in diffs[:30]:
        print("  DIFERE", d)
    print(f"build --check: {'OK' if not diffs else str(len(diffs)) + ' diferença(s)'}")
    return 1 if diffs else 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return check()
    root = repo()
    calib, index = build(root, do_seal="--seal" in argv)
    write_manifest(root)
    rep = {"schema": "bo.pilot.sto.build_report/1", "module": MODULE, "generated_at": now_iso(),
           "calib": {"fixtures": len(calib.fixtures), "direction_entries": len(calib.entries),
                     "checks": sum(len(f["checks"]) for f in calib.fixtures)},
           "heldout": None if index is None else index["counts"],
           "verification": "avaliador == resposta analítica e schema fixado em todas as fixtures (calibração e retidas)"}
    out = root / "results" / MODULE
    out.mkdir(parents=True, exist_ok=True)
    (out / "build_report.json").write_bytes(canon(rep))
    print(json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
