"""Cadeia de confiança de UMA versão histórica do terraform-provider-oci, sem executar nada baixado.

  metadado do registro (v1 .../<versão>/download/darwin/arm64) -> URLs do release oficial, shasum, chaves
  SHA256SUMS.sig --gpg (GNUPGHOME descartável)--> VALIDSIG com chave primária common.ORACLE_FPR
  zip da plataforma --sha256 == linha do SHA256SUMS assinado == shasum do registro--> pacote íntegro
  zip -> pasta desempacotada no cache de plugin próprio --h1 (dirhash) == h1 calculado dos membros do zip
  lock = h1 da plataforma + zh de todos os zips do SHA256SUMS assinado

Os primitivos (parse do SHA256SUMS, gpg, h1, desempacotar) são os da bo.schema_oci.signed, usados como
biblioteca; o que muda aqui é a origem (download por versão, não a pré-busca) e o destino (pastas próprias).
Downloads só de common.REGISTRY_PREFIX e common.RELEASE_PREFIX, cada um numa pasta própria com SOURCE.txt;
o zip é só lido (zipfile) e desempacotado. Quem executa o binário é o terraform, no sandbox da bo.schema.extract.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from bo.schema import lockfile
from bo.schema_oci import signed

from . import common

TrustError = signed.TrustError
GITHUB_API_RELEASE = "https://api.github.com/repos/oracle/terraform-provider-oci/releases/tags/"


class Unavailable(RuntimeError):
    """O pacote assinado da versão não pode ser obtido da fonte oficial (ex.: release apagado). Não é
    transitório: não se tenta de novo, e o motivo (com as URLs e os códigos HTTP) fica no registro da versão."""


def _get(url: str, allowed: tuple[str, ...], timeout: int = 120) -> bytes:
    if not url.startswith(allowed):
        raise TrustError(f"URL fora das fontes aceitas: {url!r}")
    req = urllib.request.Request(url, headers={"User-Agent": "bo-hist-oci/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 (prefixo conferido)
        return r.read()


def _write_source(d: Path, lines: list[str]) -> None:
    from bo.repo.core import now
    (d / "SOURCE.txt").write_text("\n".join(lines) + f"\nGravado por python -I -m bo.hist_oci.pipeline (HIST-OCI) em "
                                  f"{now()}.\nDado não confiável: lido como JSON/texto, nunca executado.\n",
                                  encoding="utf-8")


def fetch_release_meta(version: str, download: bool = True) -> dict:
    """Metadado do registro + SHA256SUMS + .sig da versão, em common.version_dl(version). Reaproveita o que
    já está gravado (o sha256 de cada arquivo entra no relatório; a assinatura é conferida de novo sempre)."""
    d = common.version_dl(version)
    reg_p = d / f"registry-download-{common.PLATFORM}.json"
    sums_p = d / f"terraform-provider-{common.NAME}_{version}_SHA256SUMS"
    sig_p = d / f"terraform-provider-{common.NAME}_{version}_SHA256SUMS.sig"
    if not (reg_p.is_file() and sums_p.is_file() and sig_p.is_file()):
        if not download:
            raise TrustError(f"metadado de {version} ausente em {d} e download desligado")
        d.mkdir(parents=True, exist_ok=True)
        os_, arch = common.PLATFORM.split("_")
        reg_url = f"{common.REGISTRY_PREFIX}{version}/download/{os_}/{arch}"
        raw = _get(reg_url, (common.REGISTRY_PREFIX,))
        reg = json.loads(raw)
        reg_p.write_bytes(raw)                    # fica mesmo se o release faltar: é a prova do que o registro diz
        rel = common.RELEASE_PREFIX + f"v{version}/"
        su, sg = reg.get("shasums_url", ""), reg.get("shasums_signature_url", "")
        try:
            sums = _get(su, (rel,))
            sig = _get(sg, (rel,))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            _write_source(d, [f"GET {reg_url} (200)", f"GET {su} ({e.code})",
                              "O registro aponta para um release que a fonte oficial não serve mais."])
            raise Unavailable(release_gone(version, su, e.code)) from None
        for p, b in ((reg_p, raw), (sums_p, sums), (sig_p, sig)):
            p.write_bytes(b)
        _write_source(d, [f"GET {reg_url}", f"GET {su}", f"GET {sg}",
                          f"Metadado público do Terraform Registry e SHA256SUMS(.sig) do release oficial do "
                          f"terraform-provider-oci {version} (sem conta, sem credencial)."])
    return {"registry": reg_p, "shasums": sums_p, "sig": sig_p}


def release_gone(version: str, url: str, code: int) -> str:
    """Motivo verificável de um release ausente: o código HTTP da URL do registro e o que a API pública do
    GitHub diz da tag (metadado, sem conta)."""
    api = GITHUB_API_RELEASE + f"v{version}"
    try:
        _get(api, (GITHUB_API_RELEASE,), timeout=60)
        tag = "a API do GitHub ainda lista o release da tag"
    except urllib.error.HTTPError as e:
        tag = f"a API do GitHub responde {e.code} para o release da tag v{version}"
    except OSError as e:
        tag = f"a API do GitHub não respondeu ({type(e).__name__})"
    return (f"pacote assinado indisponível: o registro ({common.REGISTRY_PREFIX}{version}/download/...) aponta o "
            f"SHA256SUMS para {url}, que responde HTTP {code}; {tag}. Sem SHA256SUMS assinado não há cadeia de "
            "confiança, e o terraform init falharia na mesma URL. A versão continua na lista, sem schema.")


def verify(version: str, download: bool = True) -> dict:
    """Confere metadado, assinatura e SHA256SUMS; baixa o zip se faltar; desempacota no cache próprio.

    Devolve o relatório (sem UID de chave, sem e-mail) e, em '_locked', o LockedProvider para o extract.
    """
    work = common.bo_tmp() / "chain" / version
    work.mkdir(parents=True, exist_ok=True)
    m = fetch_release_meta(version, download)
    reg = json.loads(m["registry"].read_text(encoding="utf-8"))
    rep: dict = {"platform": common.PLATFORM}
    if reg.get("version") not in (None, version):
        raise TrustError(f"registro devolveu versão {reg.get('version')} para {version}")
    if reg.get("os") not in (None, common.PLATFORM.split("_")[0]) or reg.get("arch") not in (None, common.PLATFORM.split("_")[1]):
        raise TrustError("registro devolveu outra plataforma")

    gk = (reg.get("signing_keys") or {}).get("gpg_public_keys") or []
    if not any(k.get("key_id") and common.ORACLE_FPR.endswith(str(k["key_id"]).upper()) for k in gk):
        raise TrustError("nenhuma chave do registro tem key_id que seja sufixo da âncora ORACLE_FPR")
    st = signed.gpg_verify(m["shasums"], m["sig"], [k["ascii_armor"] for k in gk], work, anchor=common.ORACLE_FPR)
    rep["gpg"] = {"validsig_subkey": st["validsig"], "primary_fpr": st["primary_fpr"],
                  "sig_created": st["sig_created"], "expkeysig": st["expkeysig"], "goodsig": st["goodsig"],
                  "registry_key_ids": sorted(str(k.get("key_id")) for k in gk)}
    rep["registry_meta"] = {"path": common.portable(m["registry"]), "sha256": common.sha256_file(m["registry"]),
                            "protocols": reg.get("protocols")}
    rep["shasums"] = {"path": common.portable(m["shasums"]), "sha256": common.sha256_file(m["shasums"])}
    rep["signature"] = {"path": common.portable(m["sig"]), "sha256": common.sha256_file(m["sig"])}

    sums = signed.parse_shasums(m["shasums"].read_text(encoding="utf-8"))
    zfn = f"terraform-provider-{common.NAME}_{version}_{common.PLATFORM}.zip"
    if zfn not in sums:
        raise TrustError(f"SHA256SUMS sem {zfn}")
    if reg.get("shasum") != sums[zfn] or reg.get("filename") != zfn:
        raise TrustError("shasum/filename do registro diverge do SHA256SUMS assinado")
    url = reg.get("download_url", "")
    if not url.startswith(common.RELEASE_PREFIX + f"v{version}/"):
        raise TrustError(f"download_url fora do release oficial: {url!r}")
    zp = common.zip_dir(version) / zfn
    rep["zip_baixado_agora"] = False
    if not zp.exists():
        if not download:
            raise TrustError(f"zip {zp} ausente e download desligado")
        fetch_zip(url, zp, sums[zfn], version)
        rep["zip_baixado_agora"] = True
    zsha = common.sha256_file(zp)
    if zsha != sums[zfn]:
        raise TrustError(f"{zp.name}: sha256 {zsha} != SHA256SUMS assinado {sums[zfn]}")
    rep["zip"] = {"file": zfn, "url": url, "sha256": zsha, "bytes": zp.stat().st_size,
                  "igual_ao_shasums": True, "igual_ao_registro": True}

    dest = common.unpacked_dir(version)
    dest.parent.mkdir(parents=True, exist_ok=True)
    un = signed.unpack(zp, dest)
    rep["unpacked"] = {"h1": un["h1"], "files": un["files"]}
    lp = lockfile.LockedProvider(common.ADDRESS, version, version,
                                 tuple(sorted({un["h1"], *signed.zh_hashes(sums, common.NAME, version)})))
    rep["lock"] = {"hashes": len(lp.hashes), "zh": sum(h.startswith("zh:") for h in lp.hashes), "h1": un["h1"]}
    rep["_locked"] = lp
    shutil.rmtree(work, ignore_errors=True)
    return rep


def fetch_zip(url: str, dest: Path, want_sha: str, version: str) -> Path:
    """Baixa o zip do release oficial para uma pasta própria, confere o sha256 e grava SOURCE.txt."""
    if not url.startswith(common.RELEASE_PREFIX + f"v{version}/"):
        raise TrustError(f"download_url fora do release oficial: {url!r}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "bo-hist-oci/1"})
    with urllib.request.urlopen(req, timeout=900) as r, open(part, "wb") as f:   # noqa: S310 (prefixo conferido)
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest() != want_sha:
        part.unlink()
        raise TrustError(f"zip baixado com sha256 {h.hexdigest()} != SHA256SUMS assinado {want_sha}")
    os.replace(part, dest)
    _write_source(dest.parent, [f"GET {url}",
                                f"Pacote do release oficial do terraform-provider-oci {version} (binário assinado, "
                                f"decisão D1). sha256 {want_sha} conferido contra o SHA256SUMS assinado (chave "
                                f"primária {common.ORACLE_FPR}).",
                                "Só lido como zip e desempacotado no cache de plugin próprio; quem executa o binário "
                                "é o terraform, em sandbox sem credenciais (bo.schema.extract). Apagado depois da "
                                "extração."])
    return dest


def cleanup_binaries(version: str) -> dict:
    """Apaga o zip, a pasta desempacotada e a pasta de trabalho do extract (que tem o binário em .terraform/).
    Devolve o que foi apagado e confirma que nada ficou."""
    from bo.schema import extract as libx
    gone = []
    for p in (common.zip_dir(version), common.unpacked_dir(version).parent,
              libx.bo_tmp() / "extract" / f"{common.NAME}-{version}"):
        if p.exists():
            shutil.rmtree(p)
            gone.append(common.portable(p))
    left = [common.portable(p) for p in (common.zip_dir(version), common.unpacked_dir(version)) if p.exists()]
    if left:
        raise RuntimeError(f"binários de {version} não foram apagados: {left}")
    return {"apagados": gone, "restantes": []}
