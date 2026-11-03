"""Cadeia de confiança do pacote assinado do azurerm, sem executar nada baixado.

  SHA256SUMS (pré-busca) --sha256 == pins.json--> o mesmo SHA256SUMS que o PINS fixou
  SHA256SUMS.sig --gpg (GNUPGHOME descartável)--> VALIDSIG com chave primária HASHICORP_FPR
  shasum do registro == linha do SHA256SUMS da plataforma
  zip da plataforma (reaproveitado ou baixado de releases.hashicorp.com) --sha256 == SHA256SUMS--> íntegro
  zip -> pasta desempacotada no cache de plugin --h1 (dirhash) == h1 do lock da pré-busca
  lock do módulo = h1 da plataforma + zh de todos os zips do SHA256SUMS assinado

O zip só é lido (zipfile) e desempacotado; quem executa o binário é o terraform, dentro do sandbox da
bo.schema.extract (decisão D1).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
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


def zh_hashes(sums: dict[str, str], name: str, version: str) -> list[str]:
    """Hashes 'zh:' (sha256 do zip) de todas as plataformas, como o terraform grava no lock."""
    pref, suf = f"terraform-provider-{name}_{version}_", ".zip"
    return sorted(f"zh:{s}" for f, s in sums.items() if f.startswith(pref) and f.endswith(suf))


# ------------------------------------------------------------------ GPG

def parse_gpg_status(status: str) -> dict:
    """Linhas [GNUPG:] relevantes. O texto de UID (tem e-mail) nunca é guardado."""
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
    """Confere a assinatura com um GNUPGHOME descartável; exige VALIDSIG da chave primária HASHICORP_FPR.

    EXPKEYSIG (subchave vencida na cópia da chave servida pelo registro) é registrado, não reprovado: a
    assinatura é criptograficamente válida (VALIDSIG) e o próprio terraform aceita o mesmo pacote.
    """
    gpg = shutil.which("gpg")
    if not gpg:
        raise TrustError("gpg não está no PATH")
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
        gpgconf = shutil.which("gpgconf")
        if gpgconf:     # derruba o gpg-agent do GNUPGHOME descartável antes de apagá-lo
            subprocess.run([gpgconf, "--kill", "all"], env=env, capture_output=True, check=False)
        shutil.rmtree(home, ignore_errors=True)
    st = parse_gpg_status(r.stdout.decode(errors="replace"))
    st["gpg_rc"] = r.returncode
    if st["badsig"] or st["errsig"] or not st["validsig"]:
        raise TrustError(f"assinatura do SHA256SUMS não confere (status {st})")
    if st["primary_fpr"] != common.HASHICORP_FPR:
        raise TrustError(f"assinado por chave primária {st['primary_fpr']}, esperado {common.HASHICORP_FPR}")
    return st


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


# ------------------------------------------------------------------ zip

def fetch_zip(version: str, platform: str, want_sha: str) -> Path:
    """O zip da plataforma em $BO_DATA/downloads/terraform-azurerm-<v>/mirror/...; baixa se faltar.

    O download vai para um .part e só vira o zip depois de o sha256 bater com o SHA256SUMS assinado.
    """
    d = common.zip_dir(version)
    zp = d / common.zip_name(version, platform)
    if zp.exists():
        return zp
    d.mkdir(parents=True, exist_ok=True)
    url = common.zip_url(version, platform)
    part = zp.with_suffix(".zip.part")
    h = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=300) as r, open(part, "wb") as out:   # noqa: S310 (URL fixa)
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
            out.write(chunk)
    if h.hexdigest() != want_sha:
        part.unlink()
        raise TrustError(f"{zp.name} baixado com sha256 {h.hexdigest()} != SHA256SUMS assinado {want_sha}")
    os.rename(part, zp)
    from bo.repo.core import now
    (d.parents[3] / "SOURCE.txt").write_text(
        f"Fonte: {url}\nBaixado em {now()} (America/Recife) pelo {common.MODULE} (decisão D1).\n"
        f"sha256 {want_sha}, igual ao SHA256SUMS assinado (GPG VALIDSIG, chave primária da HashiCorp)\n"
        f"em $BO_DATA/downloads/prefetch/{common.PROVIDER}/{version}/ e à versão fixada em universe/pins.json.\n"
        f"Layout: filesystem mirror empacotado (mirror/registry.terraform.io/hashicorp/{common.PROVIDER}/*.zip).\n"
        "Só lido (zipfile) e desempacotado no cache de plugin; o binário roda apenas pelo terraform em sandbox\n"
        "sem credenciais (env -i, HOME temporário, sandbox-exec), para schema e validate. Nunca plan/apply.\n",
        encoding="utf-8")
    return zp


def unpack(zip_path: Path, dest: Path) -> dict:
    """Desempacota o zip conferido em dest (layout desempacotado do terraform), de forma atômica.

    Se dest já existe com o mesmo h1, não toca. Devolve {arquivo: {sha256, bytes, mode}} e o h1.
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
            got = dirhash_h1(dest)
            if got != want:
                raise TrustError(f"{dest} já existe com h1 {got} != {want} do zip conferido")
        else:
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


# ------------------------------------------------------------------ cadeia inteira

def chain(pin: common.Pin, platform: str, work: Path) -> dict:
    """Confere a cadeia toda e semeia o cache de plugin. Devolve o relatório (sem segredo, sem UID)."""
    name, v = common.PROVIDER, pin.version
    pf = common.prefetch_dir(v)
    sums_p = pf / f"terraform-provider-{name}_{v}_SHA256SUMS"
    sig_p = pf / f"terraform-provider-{name}_{v}_SHA256SUMS.sig"
    reg_p = pf / f"registry-download-{platform}.json"
    rep: dict = {"platform": platform}

    sums_sha = common.sha256_file(sums_p)
    if sums_sha != pin.shasums_sha256:
        raise TrustError(f"SHA256SUMS {sums_sha} != pins.json {pin.shasums_sha256}")
    rep["shasums"] = {"path": common.portable(sums_p), "sha256": sums_sha, "igual_ao_pins": True}

    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    keys = [k["ascii_armor"] for k in (reg.get("signing_keys") or {}).get("gpg_public_keys") or []]
    st = gpg_verify(sums_p, sig_p, keys, work)
    rep["gpg"] = {"validsig_subkey": st["validsig"], "primary_fpr": st["primary_fpr"],
                  "sig_created": st["sig_created"], "expkeysig": st["expkeysig"], "goodsig": st["goodsig"],
                  "nota": ("EXPKEYSIG: a subchave está vencida na cópia da chave servida pelo registro; a "
                           "assinatura é válida (VALIDSIG) e a chave primária é a da HashiCorp")
                  if st["expkeysig"] else ""}

    sums = parse_shasums(sums_p.read_text(encoding="utf-8"))
    zfn = common.zip_name(v, platform)
    if zfn not in sums:
        raise TrustError(f"SHA256SUMS sem {zfn}")
    if reg.get("shasum") != sums[zfn]:
        raise TrustError("shasum do registro diverge do SHA256SUMS assinado")
    if reg.get("download_url") != common.zip_url(v, platform):
        raise TrustError("URL de download do registro diverge da URL oficial montada")
    zp = fetch_zip(v, platform, sums[zfn])
    zsha = common.sha256_file(zp)
    if zsha != sums[zfn]:
        raise TrustError(f"{zp.name}: sha256 {zsha} != SHA256SUMS assinado {sums[zfn]}")
    rep["zip"] = {"file": zfn, "path": common.portable(zp), "sha256": zsha, "bytes": zp.stat().st_size,
                  "igual_ao_shasums": True}

    dest = common.shared_cache() / "registry.terraform.io" / "hashicorp" / name / v / platform
    un = unpack(zp, dest)
    rep["unpacked"] = {"path": common.portable(dest), "h1": un["h1"], "files": un["files"]}

    from bo.schema import lockfile
    pre = lockfile.find(lockfile.read(pf / "terraform.lock.hcl"), common.SOURCE)
    pre_h1 = sorted(h for h in pre.hashes if h.startswith("h1:"))
    if pre.version != v:
        raise TrustError(f"lock da pré-busca fixa {pre.version}, pins.json {v}")
    if un["h1"] not in pre_h1:
        raise TrustError(f"h1 {un['h1']} fora do lock da pré-busca {pre_h1}")
    rep["prefetch_lock_h1_igual"] = True

    lp = lockfile.LockedProvider(pin.source, v, v, tuple(sorted({un["h1"], *zh_hashes(sums, name, v)})))
    rep["lock"] = {"version": lp.version, "hashes": len(lp.hashes),
                   "zh": sum(h.startswith("zh:") for h in lp.hashes), "h1": un["h1"]}
    rep["_locked"] = lp
    return rep
