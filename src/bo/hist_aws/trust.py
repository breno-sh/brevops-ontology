"""Cadeia de confiança do pacote assinado de uma versão do provider, sem executar nada baixado.

  registro (v1 .../download/darwin/arm64) -> shasum do zip, URLs do SHA256SUMS e da assinatura, chaves públicas
  SHA256SUMS.sig --gpg (GNUPGHOME descartável)--> VALIDSIG cuja chave primária é HASHICORP_FPR (âncora fixa)
  zip --sha256 == linha do SHA256SUMS assinado == shasum do registro--> pacote íntegro
  zip -> pasta desempacotada no cache de plugin do módulo --h1 (dirhash) == h1 calculado dos membros do zip
  lock = h1 da plataforma + zh de todos os zips do SHA256SUMS assinado (o init -lockfile=readonly confere)

O zip só é lido (zipfile) e desempacotado; quem executa o binário é o terraform, dentro do sandbox da
bo.schema.extract (SCHEMALIB).
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import common


class TrustError(RuntimeError):
    """Elo da cadeia de confiança que não confere."""


# ------------------------------------------------------------------ SHA256SUMS

def parse_shasums(text: str) -> dict[str, str]:
    """{arquivo: sha256} de um SHA256SUMS ('<sha>  <arquivo>' por linha)."""
    out = {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or len(parts[0]) != 64 or any(c not in "0123456789abcdef" for c in parts[0]):
            raise TrustError(f"SHA256SUMS linha {n} mal formada")
        if parts[1] in out:
            raise TrustError(f"SHA256SUMS com {parts[1]} repetido")
        out[parts[1]] = parts[0]
    return out


def zip_name(version: str, platform: str = common.PLATFORM) -> str:
    return f"terraform-provider-{common.NAME}_{version}_{platform}.zip"


def zh_hashes(sums: dict[str, str], version: str) -> list[str]:
    """Hashes 'zh:' (sha256 do zip) de todas as plataformas, como o terraform grava no lock."""
    pref, suf = f"terraform-provider-{common.NAME}_{version}_", ".zip"
    return sorted(f"zh:{s}" for f, s in sums.items() if f.startswith(pref) and f.endswith(suf))


# ------------------------------------------------------------------ GPG

def parse_gpg_status(status: str) -> dict:
    """Linhas [GNUPG:] relevantes (sem UIDs: o texto do UID tem e-mail e não é gravado)."""
    st = {"validsig": None, "primary_fpr": None, "goodsig": False, "expkeysig": False, "badsig": False,
          "errsig": False, "sig_created": None}
    for line in status.splitlines():
        p = line.split()
        if len(p) < 2 or p[0] != "[GNUPG:]":
            continue
        tag = p[1]
        if tag == "VALIDSIG" and len(p) >= 12:
            st["validsig"] = p[2]
            st["sig_created"] = p[3]
            st["primary_fpr"] = p[-1]
        elif tag == "GOODSIG":
            st["goodsig"] = True
        elif tag == "EXPKEYSIG":
            st["expkeysig"] = True
        elif tag == "BADSIG":
            st["badsig"] = True
        elif tag == "ERRSIG":
            st["errsig"] = True
    return st


def gpg_verify(sums: Path, sig: Path, armored_keys: list[str], work: Path) -> dict:
    """Confere a assinatura com um GNUPGHOME descartável. Exige VALIDSIG da chave primária HASHICORP_FPR.

    EXPKEYSIG (subchave vencida na cópia da chave servida pelo registro) é registrado, não reprovado: a
    assinatura é criptograficamente válida (VALIDSIG) e a chave primária é a âncora.
    """
    gpg = shutil.which("gpg")
    if not gpg:
        raise TrustError("gpg não está no PATH")
    if not armored_keys:
        raise TrustError("registro sem chave pública de assinatura")
    home = work / "gnupg"
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True, mode=0o700)
    env = {"PATH": "/usr/bin:/bin:" + str(Path(gpg).parent), "GNUPGHOME": str(home), "LANG": "C"}
    try:
        for k in armored_keys:
            r = subprocess.run([gpg, "--batch", "--quiet", "--import"], input=k.encode(), env=env,
                               capture_output=True, check=False)
            if r.returncode not in (0, 2):     # 2 = importou com avisos (ex.: subchave vencida)
                raise TrustError(f"gpg --import falhou (rc {r.returncode})")
        r = subprocess.run([gpg, "--batch", "--status-fd", "1", "--verify", str(sig), str(sums)], env=env,
                           capture_output=True, check=False)
    finally:
        subprocess.run(["/usr/bin/env", "-i", f"PATH={env['PATH']}", f"GNUPGHOME={home}", "gpgconf", "--kill",
                        "all"], capture_output=True, check=False)
        shutil.rmtree(home, ignore_errors=True)
    st = parse_gpg_status(r.stdout.decode(errors="replace"))
    st["gpg_rc"] = r.returncode
    check_gpg_status(st)
    return st


def check_gpg_status(st: dict) -> None:
    if st["badsig"] or st["errsig"] or not st["validsig"]:
        raise TrustError(f"assinatura do SHA256SUMS não confere (status {st})")
    if st["primary_fpr"] != common.HASHICORP_FPR:
        raise TrustError(f"assinado por chave primária {st['primary_fpr']}, esperado {common.HASHICORP_FPR}")


# ------------------------------------------------------------------ h1 (dirhash.Hash1 do Go)

def dirhash_h1(root: Path) -> str:
    """h1 do terraform: sha256 das linhas '<sha256 hex>  <caminho relativo>\\n' em ordem, em base64."""
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    h = hashlib.sha256()
    for f in files:
        h.update(f"{common.sha256_file(root / f)}  {f}\n".encode())
    return "h1:" + base64.b64encode(h.digest()).decode()


def zip_h1(zf: zipfile.ZipFile) -> str:
    """O mesmo h1, calculado direto dos membros do zip (para conferir a pasta desempacotada)."""
    h = hashlib.sha256()
    for name in sorted(i.filename for i in zf.infolist() if not i.is_dir()):
        m = hashlib.sha256()
        with zf.open(name) as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                m.update(chunk)
        h.update(f"{m.hexdigest()}  {name}\n".encode())
    return "h1:" + base64.b64encode(h.digest()).decode()


def unpack(zip_path: Path, dest: Path) -> dict:
    """Desempacota o zip conferido em dest (layout desempacotado do terraform), de forma atômica.

    Reprova membro com caminho absoluto, '..' ou subpasta. Devolve {h1, files: {nome: {sha256, bytes, mode}}}.
    """
    with zipfile.ZipFile(zip_path) as zf:
        want = zip_h1(zf)
        members = {}
        for i in zf.infolist():
            if i.is_dir():
                continue
            if i.filename.startswith("/") or ".." in Path(i.filename).parts or "/" in i.filename:
                raise TrustError(f"membro inesperado no zip: {i.filename!r}")
            members[i.filename] = i
        if dest.exists():
            shutil.rmtree(dest)
        stage = dest.parent / f".stage-{os.getpid()}-{dest.name}"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        for name, i in sorted(members.items()):
            with zf.open(i) as src, open(stage / name, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            mode = (i.external_attr >> 16) & 0o777
            os.chmod(stage / name, mode or 0o644)
        os.rename(stage, dest)
    files = {}
    for p in sorted(dest.iterdir()):
        files[p.name] = {"sha256": common.sha256_file(p), "bytes": p.stat().st_size,
                         "mode": oct(p.stat().st_mode & 0o777)}
    got = dirhash_h1(dest)
    if got != want:
        raise TrustError(f"h1 da pasta desempacotada {got} != h1 do zip {want}")
    return {"h1": got, "files": files}
