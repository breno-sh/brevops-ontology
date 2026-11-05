"""Selagem das fixtures RETIDAS (D15): CMS com AES-256 para o certificado público da VM Oracle.

  python -I -m bo.pilot_net_oracle.seal seal --bundle B.json --source retained.py   cifra, indexa e confere
  python -I -m bo.pilot_net_oracle.seal verify                                       confere envelope e índice

A chave privada fica só na VM (ssh ubuntu@136.248.69.238, ~/brevops-keys/seal_private.pem); o Mac só tem o
certificado. Abertura (PILOT-EXIT): ssh <vm> 'openssl cms -decrypt -inform PEM -inkey ~/brevops-keys/seal_private.pem'
< retained.cms.pem > retained.tar, num $BO_TMP do PILOT-EXIT. O índice público guarda só contagens e resumos
com sal (o sal está dentro do envelope): nenhum conteúdo de fixture retida fica legível fora dele.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VM = "ubuntu@136.248.69.238"
PRIV = "~/brevops-keys/seal_private.pem"


def data_dir() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "PILOT-NET-ORACLE"


def repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def sealed_dir() -> Path:
    return data_dir() / "sealed"


def cert_path() -> Path:
    return repo() / "pilot/net/oracle/seal_cert.pem"


def now() -> str:
    return datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canon(o) -> bytes:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def cert_info() -> dict:
    out = subprocess.run(["openssl", "x509", "-in", str(cert_path()), "-noout", "-serial", "-fingerprint", "-sha256",
                          "-subject"], capture_output=True, text=True, check=True).stdout
    kv = {}
    for line in out.splitlines():
        k, _, v = line.partition("=")
        kv[k.strip().lower()] = v.strip()
    return {"serial": kv.get("serial"), "fingerprint_sha256": kv.get("sha256 fingerprint"),
            "subject": kv.get("subject"), "cert_sha256": sha(cert_path().read_bytes())}


def envelope_recipient(env: Path) -> str | None:
    """Número de série do destinatário lido do envelope (sem decifrar)."""
    out = subprocess.run(["openssl", "cms", "-cmsout", "-print", "-inform", "PEM", "-in", str(env)],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    lines = out.stdout.splitlines()
    for i, l in enumerate(lines):
        if "serialNumber:" in l:
            v = l.split("serialNumber:", 1)[1].strip()
            if not v and i + 1 < len(lines):
                v = lines[i + 1].strip()
            v = v.split("(")[-1].rstrip(")") if "(" in v else v
            v = v.replace("0x", "").replace(":", "").upper()
            return v
    return None


def _tar(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name in sorted(files):
            data = files[name]
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime, ti.mode, ti.uid, ti.gid = len(data), 0, 0o600, 0, 0
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def index_for(bundle: dict, salt: str) -> dict:
    from collections import Counter
    from .coverage_lib import summarize
    items = [{"digest": sha(salt.encode() + canon(x))} for x in bundle["fixtures"] + bundle["translations"]]
    out = {"counts": summarize(bundle["fixtures"], bundle["translations"]),
           "salted_digests": sorted(i["digest"] for i in items)}
    fx = bundle["fixtures"]
    if fx and isinstance(fx[0].get("basis"), dict):
        out["basis_counts"] = {
            "decisions": dict(Counter(e["basis"] for f in fx for e in f["expected"]["decisions"].values())),
            "decomposition_units": dict(Counter(u["basis"] for f in fx for u in f["expected"]["decomposition"])),
            "translations": dict(Counter(t["basis"] for t in bundle["translations"])),
            "rule": bundle.get("basis_rule")}
    return out


def envelope_path(idx: dict) -> Path:
    e = idx["envelope"]
    return Path(e.replace("$BO_DATA", str(data_dir().parent))) if e.startswith("$BO_DATA") else Path(e)


def seal(bundle_path: Path, source_path: Path, version: int = 1, retire: Path | None = None, revision: int = 1,
         retire_status: str = "usado 2×, aposentado", reason: str = "") -> dict:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if any(x.get("split") != "retained" for x in bundle["fixtures"] + bundle["translations"]):
        raise SystemExit("seal: o pacote tem item que não é retido")
    salt = secrets.token_hex(32)
    files = {"bundle.json": bundle_path.read_bytes(), source_path.name: source_path.read_bytes(),
             "SALT.txt": (salt + "\n").encode(),
             "README.txt": ("Fixtures RETIDAS da fatia NET (PILOT-NET-ORACLE). Só o PILOT-EXIT abre.\n"
                            "Conferência: sha256(sal || json canônico do item) deve estar em salted_digests do\n"
                            "sealed_index.json; sha256 deste tar = plaintext_sha256.\n").encode()}
    plain = _tar(files)
    sd = sealed_dir()
    sd.mkdir(parents=True, exist_ok=True)
    name = "retained.cms.pem" if version == 1 else (f"retained_v{version}.cms.pem" if revision == 1 else f"retained_v{version}r{revision}.cms.pem")
    env = sd / name
    if env.exists():
        raise SystemExit(f"seal: {env} já existe; selo não se sobrescreve")
    r = subprocess.run(["openssl", "cms", "-encrypt", "-aes256", "-binary", "-outform", "PEM", "-out", str(env),
                        str(cert_path())], input=plain, capture_output=True)
    if r.returncode != 0:
        raise SystemExit("seal: openssl cms falhou: " + r.stderr.decode()[-300:])
    ci = cert_info()
    rec = envelope_recipient(env)
    if rec != ci["serial"].upper():
        raise SystemExit(f"seal: destinatário do envelope ({rec}) != série do certificado ({ci['serial']})")
    # prova de ida e volta: a VM decifra e devolve só o sha256 do texto claro (nada volta em claro)
    rt = subprocess.run(["ssh", "-o", "BatchMode=yes", VM, f"openssl cms -decrypt -inform PEM -inkey {PRIV} | sha256sum"],
                        input=env.read_bytes(), capture_output=True)
    vm_sha = rt.stdout.decode().split()[0] if rt.returncode == 0 and rt.stdout else None
    if vm_sha != sha(plain):
        raise SystemExit(f"seal: ida e volta na VM não confere (vm={vm_sha})")
    idx = {"schema": "bo.pilot_net.sealed_index/1", "module": "PILOT-NET-ORACLE", "slice": "net",
           "set_version": version, "revision": revision, "status": "ativo", "reseal_reason": reason or None,
           "created_at": now(), "envelope": f"$BO_DATA/PILOT-NET-ORACLE/sealed/{name}",
           "envelope_sha256": sha(env.read_bytes()), "plaintext_sha256": sha(plain),
           "cipher": "CMS EnvelopedData, AES-256-CBC, chave RSA 4096 do certificado brevops-seal-D15",
           "recipient": ci, "roundtrip": {"at": now(), "host": "VM Oracle (D15)", "plaintext_sha256_from_vm": vm_sha},
           "opened_by": "PILOT-EXIT", **index_for(bundle, salt)}
    if retire is not None:
        old = json.loads(retire.read_text(encoding="utf-8"))
        carried = old.pop("retired_sets", [])
        old.update({"status": retire_status, "retired_at": now(),
                    "retired_reason": reason or ("o PILOT-EXIT 2/2 já usou este conjunto; substituído pelo conjunto v%d (ciclo v4)" % version)})
        old.setdefault("set_version", 1)
        tag = f"v{old['set_version']}" + (f"r{old.get('revision', 1)}" if old.get("revision", 1) > 1 or old["set_version"] == version else "")
        (sd / f"sealed_index_{tag}_retired.json").write_text(
            json.dumps(old, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        idx["retired_sets"] = carried + [{"set_version": old["set_version"], "revision": old.get("revision", 1),
                                          "index": f"$BO_DATA/PILOT-NET-ORACLE/sealed/sealed_index_{tag}_retired.json",
                                          "envelope": old["envelope"], "envelope_sha256": old["envelope_sha256"], "status": old["status"]}]
    (sd / "sealed_index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return idx


def verify(index_path: Path | None = None) -> list:
    """Erros (vazio = ok): envelope existe, sha confere, destinatário é o certificado, índice coerente."""
    errs = []
    idx_p = index_path or (repo() / "pilot/net/oracle/sealed_index.json")
    if not idx_p.is_file():
        return [f"índice ausente: {idx_p}"]
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    env = envelope_path(idx)
    if not env.is_file():
        return [f"envelope ausente: {env}"]
    for old in idx.get("retired_sets", []):
        oe = envelope_path(old)
        if not oe.is_file() or sha(oe.read_bytes()) != old["envelope_sha256"]:
            errs.append(f"conjunto aposentado v{old['set_version']}: envelope ausente ou alterado")
    if sha(env.read_bytes()) != idx["envelope_sha256"]:
        errs.append("sha256 do envelope difere do índice")
    ci = cert_info()
    if ci["cert_sha256"] != idx["recipient"]["cert_sha256"]:
        errs.append("certificado do repositório difere do usado na selagem")
    if envelope_recipient(env) != (ci["serial"] or "").upper():
        errs.append("destinatário do envelope não é o certificado D15")
    if idx["roundtrip"]["plaintext_sha256_from_vm"] != idx["plaintext_sha256"]:
        errs.append("ida e volta na VM não registrada como conferida")
    head = env.read_text(errors="replace")[:40]
    if "BEGIN CMS" not in head and "BEGIN PKCS7" not in head:
        errs.append("envelope não está em PEM CMS")
    return errs


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="bo.pilot_net_oracle.seal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seal")
    s.add_argument("--bundle", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--version", type=int, default=1)
    s.add_argument("--retire", help="índice do conjunto anterior, a aposentar")
    s.add_argument("--revision", type=int, default=1)
    s.add_argument("--retire-status", default="usado 2×, aposentado")
    s.add_argument("--reason", default="")
    sub.add_parser("verify")
    a = ap.parse_args(argv)
    if a.cmd == "seal":
        idx = seal(Path(a.bundle), Path(a.source), a.version, Path(a.retire) if a.retire else None, a.revision,
                   a.retire_status, a.reason)
        print(f"[{now()}] selado: {idx['envelope']} sha256={idx['envelope_sha256'][:16]}… itens={len(idx['salted_digests'])}")
        return 0
    errs = verify()
    for e in errs:
        print("ERRO", e)
    print(f"[{now()}] verify: {'OK' if not errs else 'FALHOU'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
