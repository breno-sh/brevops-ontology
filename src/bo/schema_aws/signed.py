"""Cadeia de confiança do pacote assinado do provider, sem executar nada baixado.

  SHA256SUMS (pré-busca) --sha256 == pins.json--> conferido contra o PINS
  SHA256SUMS.sig --gpg (GNUPGHOME temporário)--> VALIDSIG com chave primária HASHICORP_FPR
  zip da plataforma --sha256 == linha do SHA256SUMS--> pacote íntegro
  zip -> pasta desempacotada no cache de plugin --h1 (dirhash) == hash h1 do lock da pré-busca
  lock do módulo = h1 da plataforma + zh de todos os zips do SHA256SUMS assinado

O zip só é lido (zipfile) e desempacotado; quem executa o binário é o terraform, dentro do sandbox da
bo.schema.extract.
"""

from __future__ import annotations

import base64
import hashlib
import json
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


def zh_hashes(sums: dict[str, str], name: str, version: str) -> list[str]:
    """Hashes 'zh:' (sha256 do zip) de todas as plataformas, como o terraform grava no lock."""
    pref, suf = f"terraform-provider-{name}_{version}_", ".zip"
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
    assinatura é criptograficamente válida (VALIDSIG) e o terraform aceita o mesmo pacote.
    """
    gpg = shutil.which("gpg")
    if not gpg:
        raise TrustError("gpg não está no PATH")
    home = work / "gnupg"
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True, mode=0o700)
    env = {"PATH": "/usr/bin:/bin:" + str(Path(gpg).parent), "GNUPGHOME": str(home), "LANG": "C"}
    for k in armored_keys:
        r = subprocess.run([gpg, "--batch", "--quiet", "--import"], input=k.encode(), env=env,
                           capture_output=True, check=False)
        if r.returncode not in (0, 2):     # 2 = importou com avisos (ex.: subchave vencida)
            raise TrustError(f"gpg --import falhou (rc {r.returncode})")
    r = subprocess.run([gpg, "--batch", "--status-fd", "1", "--verify", str(sig), str(sums)], env=env,
                       capture_output=True, check=False)
    st = parse_gpg_status(r.stdout.decode(errors="replace"))
    shutil.rmtree(home, ignore_errors=True)
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


# ------------------------------------------------------------------ zip -> cache

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

def find_zip(name: str, version: str, platform: str) -> Path:
    """O zip da plataforma já baixado em $BO_DATA/downloads (reaproveitado; conferido por sha256 depois)."""
    fn = f"terraform-provider-{name}_{version}_{platform}.zip"
    root = common.bo_data() / "downloads"
    cands = sorted(root.glob(f"*/mirror/registry.terraform.io/hashicorp/{name}/{fn}")) + \
        sorted(root.glob(f"*/{fn}")) + sorted(root.glob(f"*/*/{fn}"))
    if not cands:
        raise TrustError(f"zip {fn} não encontrado em $BO_DATA/downloads (baixe com terraform init "
                         "ou rode bo.schema.extract sem semear o cache)")
    return cands[0]


def chain(pin: common.Pin, platform: str, work: Path) -> dict:
    """Confere a cadeia toda e semeia o cache de plugin. Devolve o relatório (sem segredo, sem UID)."""
    name = pin.source.rsplit("/", 1)[-1]
    pf = common.prefetch_dir(pin.version)
    sums_p = pf / f"terraform-provider-{name}_{pin.version}_SHA256SUMS"
    sig_p = pf / f"terraform-provider-{name}_{pin.version}_SHA256SUMS.sig"
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
    zfn = f"terraform-provider-{name}_{pin.version}_{platform}.zip"
    if zfn not in sums:
        raise TrustError(f"SHA256SUMS sem {zfn}")
    if reg.get("shasum") != sums[zfn]:
        raise TrustError("shasum do registro diverge do SHA256SUMS assinado")
    zp = find_zip(name, pin.version, platform)
    zsha = common.sha256_file(zp)
    if zsha != sums[zfn]:
        raise TrustError(f"{zp.name}: sha256 {zsha} != SHA256SUMS assinado {sums[zfn]}")
    rep["zip"] = {"file": zfn, "path": common.portable(zp), "sha256": zsha, "bytes": zp.stat().st_size,
                  "igual_ao_shasums": True}

    dest = common.shared_cache() / "registry.terraform.io" / "hashicorp" / name / pin.version / platform
    un = unpack(zp, dest)
    rep["unpacked"] = {"path": common.portable(dest), "h1": un["h1"], "files": un["files"]}

    from bo.schema import lockfile
    pre = lockfile.find(lockfile.read(pf / "terraform.lock.hcl"), pin.source)
    pre_h1 = sorted(h for h in pre.hashes if h.startswith("h1:"))
    if pre.version != pin.version:
        raise TrustError(f"lock da pré-busca fixa {pre.version}, pins.json {pin.version}")
    if un["h1"] not in pre_h1:
        raise TrustError(f"h1 {un['h1']} fora do lock da pré-busca {pre_h1}")
    rep["prefetch_lock_h1_igual"] = True

    lp = lockfile.LockedProvider(pin.source, pin.version, pin.version,
                                 tuple(sorted({un["h1"], *zh_hashes(sums, name, pin.version)})))
    rep["lock"] = {"version": lp.version, "hashes": len(lp.hashes),
                   "zh": sum(h.startswith("zh:") for h in lp.hashes), "h1": un["h1"]}
    rep["_locked"] = lp
    return rep
