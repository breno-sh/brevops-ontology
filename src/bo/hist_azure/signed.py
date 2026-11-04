"""Cadeia de confiança do pacote assinado do azurerm de UMA versão histórica, sem executar nada baixado.

  metadado do registro (/v1/providers/hashicorp/azurerm/<v>/download/darwin/arm64), lido como JSON:
      URLs de zip, SHA256SUMS e assinatura têm de ser as oficiais montadas aqui (releases.hashicorp.com)
  SHA256SUMS + .sig de releases.hashicorp.com --gpg (GNUPGHOME descartável)--> VALIDSIG da chave primária
      HASHICORP_FPR (para a versão do pin, o sha256 do SHA256SUMS também tem de ser o do pins.json)
  shasum do registro == linha do SHA256SUMS da plataforma
  zip da plataforma --sha256 == SHA256SUMS--> íntegro (baixado para .part; só vira zip se bater)
  zip -> pasta desempacotada no cache de plugin do módulo --h1 (dirhash) == h1 calculado dos membros do zip
  lock = h1 da plataforma + zh de todos os zips do SHA256SUMS assinado (o init reprova pacote fora dele)

Reaproveitamento (sem baixar de novo): metadado, SHA256SUMS e assinatura da pré-busca e o zip do espelho do
SCHEMA-AZURE, quando existem para a versão; são COPIADOS para a pasta do módulo e conferidos do mesmo jeito.
O zip só é lido (zipfile) e desempacotado; quem executa o binário é o terraform, dentro do sandbox da
bo.schema.extract (decisão D1).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
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


def zh_hashes(sums: dict[str, str], version: str) -> list[str]:
    """Hashes 'zh:' (sha256 do zip) de todas as plataformas, como o terraform grava no lock."""
    pref, suf = f"terraform-provider-{common.PROVIDER}_{version}_", ".zip"
    return sorted(f"zh:{s}" for f, s in sums.items() if f.startswith(pref) and f.endswith(suf))


# ------------------------------------------------------------------ metadado do registro

def sig_url_ok(url: str, version: str) -> bool:
    """A assinatura tem de estar ao lado do SHA256SUMS oficial: <SHA256SUMS>.sig ou <SHA256SUMS>.<KEYID8>.sig."""
    want = re.escape(common.sums_url(version))
    return re.fullmatch(want + r"(\.[0-9A-F]{8})?\.sig", url or "") is not None


def check_registry(reg: dict, version: str, platform: str) -> None:
    """O metadado do registro só é aceito se apontar para os arquivos oficiais da versão e da plataforma."""
    os_, arch = platform.split("_", 1)
    if reg.get("os") != os_ or reg.get("arch") != arch:
        raise TrustError(f"metadado do registro é de {reg.get('os')}_{reg.get('arch')}, esperado {platform}")
    if reg.get("filename") != common.zip_name(version, platform):
        raise TrustError("nome do zip no registro diverge do nome oficial")
    if reg.get("download_url") != common.zip_url(version, platform):
        raise TrustError("URL de download do registro diverge da URL oficial montada")
    if reg.get("shasums_url") != common.sums_url(version):
        raise TrustError("URL do SHA256SUMS do registro diverge da URL oficial montada")
    if not sig_url_ok(reg.get("shasums_signature_url"), version):
        raise TrustError("URL da assinatura do registro fora do padrão oficial")
    sh = reg.get("shasum") or ""
    if len(sh) != 64 or any(c not in "0123456789abcdef" for c in sh):
        raise TrustError("shasum do registro mal formado")


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

    EXPKEYSIG (subchave vencida na cópia servida pelo registro) é registrado, não reprovado: a assinatura é
    criptograficamente válida (VALIDSIG) e a chave primária é a âncora fixada aqui.
    """
    gpg = shutil.which("gpg")
    if not gpg:
        raise TrustError("gpg não está no PATH")
    if not armored_keys:
        raise TrustError("o registro não trouxe chave pública para conferir a assinatura")
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


# ------------------------------------------------------------------ download e cópia

def fetch(url: str, dest: Path, want_sha: str | None = None, timeout: int = 600) -> Path:
    """Baixa url para dest via .part; se want_sha, só vira dest com o sha256 igual."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "bo-hist-azure"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as out:   # noqa: S310 (URL montada)
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
            out.write(chunk)
    if want_sha and h.hexdigest() != want_sha:
        part.unlink()
        raise TrustError(f"{dest.name} baixado com sha256 {h.hexdigest()} != esperado {want_sha}")
    os.replace(part, dest)
    return dest


def copy_checked(src: Path, dest: Path, want_sha: str | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    shutil.copyfile(src, part)
    if want_sha and common.sha256_file(part) != want_sha:
        part.unlink()
        raise TrustError(f"cópia de {src.name} com sha256 diferente do esperado")
    os.replace(part, dest)
    return dest


def prefetch_dir(version: str) -> Path:
    return common.bo_data() / "downloads" / "prefetch" / common.PROVIDER / version


def mirror_zip(version: str, platform: str) -> Path:
    """Zip assinado já baixado por outro módulo (espelho do SCHEMA-AZURE), reaproveitado só por cópia."""
    return (common.bo_data() / "downloads" / f"terraform-{common.PROVIDER}-{version}" / "mirror" /
            "registry.terraform.io" / "hashicorp" / common.PROVIDER / common.zip_name(version, platform))


def get_registry(version: str, platform: str) -> tuple[Path, dict, str]:
    d = common.dl_dir(version)
    p = d / f"registry-download-{platform}.json"
    origin = "existente"
    if not p.exists():
        pre = prefetch_dir(version) / f"registry-download-{platform}.json"
        if pre.exists():
            copy_checked(pre, p)
            origin = "pré-busca"
        else:
            fetch(common.registry_download_url(version, platform), p)
            origin = "registro"
    return p, json.loads(p.read_text(encoding="utf-8")), origin


def get_sums(version: str, sig_url: str) -> tuple[Path, Path, str]:
    d = common.dl_dir(version)
    sums_p = d / common.sums_name(version)
    sig_p = d / (common.sums_name(version) + ".sig")
    origin = "existente"
    if not (sums_p.exists() and sig_p.exists()):
        pre = prefetch_dir(version)
        ps, pg = pre / common.sums_name(version), pre / (common.sums_name(version) + ".sig")
        if ps.exists() and pg.exists():
            copy_checked(ps, sums_p)
            copy_checked(pg, sig_p)
            origin = "pré-busca"
        else:
            fetch(common.sums_url(version), sums_p)
            fetch(sig_url, sig_p)
            origin = "releases.hashicorp.com"
    return sums_p, sig_p, origin


def get_zip(version: str, platform: str, want_sha: str) -> tuple[Path, str]:
    zp = common.dl_dir(version) / common.zip_name(version, platform)
    if zp.exists():
        if common.sha256_file(zp) == want_sha:
            return zp, "existente"
        zp.unlink()
    mz = mirror_zip(version, platform)
    if mz.exists() and common.sha256_file(mz) == want_sha:
        return copy_checked(mz, zp, want_sha), "espelho do SCHEMA-AZURE (cópia)"
    return fetch(common.zip_url(version, platform), zp, want_sha), "releases.hashicorp.com"


def unpack(zip_path: Path, dest: Path) -> dict:
    """Desempacota o zip conferido em dest (layout desempacotado do terraform), de forma atômica.

    Se dest já existe, tem de ter o mesmo h1 do zip. Devolve {h1, files: {arquivo: {sha256, bytes, mode}}}.
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

def chain(version: str, platform: str, work: Path) -> dict:
    """Confere a cadeia toda e semeia o cache de plugin do módulo. Devolve o relatório (sem segredo, sem UID)."""
    from bo.schema import lockfile
    rep: dict = {"platform": platform}

    reg_p, reg, reg_origin = get_registry(version, platform)
    check_registry(reg, version, platform)
    rep["registry"] = {"path": common.portable(reg_p), "sha256": common.sha256_file(reg_p), "origem": reg_origin,
                       "protocols": reg.get("protocols"), "shasum": reg["shasum"]}

    sums_p, sig_p, sums_origin = get_sums(version, reg["shasums_signature_url"])
    sums_sha = common.sha256_file(sums_p)
    pin_sha = common.pin_shasums_sha256(version)
    if pin_sha is not None and sums_sha != pin_sha:
        raise TrustError(f"SHA256SUMS {sums_sha} != pins.json {pin_sha}")
    rep["shasums"] = {"path": common.portable(sums_p), "sha256": sums_sha, "origem": sums_origin,
                      "igual_ao_pins": (sums_sha == pin_sha) if pin_sha else None}
    rep["signature"] = {"path": common.portable(sig_p), "sha256": common.sha256_file(sig_p),
                        "url": reg["shasums_signature_url"]}

    keys = [k["ascii_armor"] for k in (reg.get("signing_keys") or {}).get("gpg_public_keys") or []]
    st = gpg_verify(sums_p, sig_p, keys, work)
    rep["gpg"] = {"validsig_subkey": st["validsig"], "primary_fpr": st["primary_fpr"],
                  "sig_created": st["sig_created"], "expkeysig": st["expkeysig"], "goodsig": st["goodsig"],
                  "nota": ("EXPKEYSIG: a subchave está vencida na cópia da chave servida pelo registro; a "
                           "assinatura é válida (VALIDSIG) e a chave primária é a da HashiCorp")
                  if st["expkeysig"] else ""}

    sums = parse_shasums(sums_p.read_text(encoding="utf-8"))
    zfn = common.zip_name(version, platform)
    if zfn not in sums:
        raise TrustError(f"SHA256SUMS sem {zfn}")
    if reg["shasum"] != sums[zfn]:
        raise TrustError("shasum do registro diverge do SHA256SUMS assinado")
    zp, zorigin = get_zip(version, platform, sums[zfn])
    zsha = common.sha256_file(zp)
    if zsha != sums[zfn]:
        raise TrustError(f"{zp.name}: sha256 {zsha} != SHA256SUMS assinado {sums[zfn]}")
    rep["zip"] = {"file": zfn, "sha256": zsha, "bytes": zp.stat().st_size, "origem": zorigin,
                  "igual_ao_shasums": True, "_path": zp}

    dest = common.unpacked_dir(version, platform)
    un = unpack(zp, dest)
    rep["unpacked"] = {"path": common.portable(dest), "h1": un["h1"], "files": un["files"]}

    lp = lockfile.LockedProvider(common.ADDRESS, version, version,
                                 tuple(sorted({un["h1"], *zh_hashes(sums, version)})))
    rep["lock"] = {"version": lp.version, "hashes": len(lp.hashes),
                   "zh": sum(h.startswith("zh:") for h in lp.hashes), "h1": un["h1"]}
    rep["_locked"] = lp
    return rep
