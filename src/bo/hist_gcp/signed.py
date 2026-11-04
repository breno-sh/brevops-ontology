"""Cadeia de confiança de cada versão histórica: índice do PINS -> rota de download -> SHA256SUMS assinado -> lock.

Para uma versão V da lista do PINS:
  1. o índice v1 do Registry guardado pelo PINS (sha conferido contra o history_versions.json) diz se há build
     darwin_arm64. Sem build, a versão é INDISPONÍVEL e o motivo sai daqui e da própria rota de download
     (resposta HTTP do Registry), sem inventar nada;
  2. rota https://registry.terraform.io/v1/providers/hashicorp/google/V/download/darwin/arm64 (metadado público):
     nome do zip, protocolos, shasum, URLs do SHA256SUMS e da assinatura, só em releases.hashicorp.com;
  3. SHA256SUMS e assinatura destacada baixados; assinatura conferida com gpgv (bo.pins.sig, sem chaveiro do
     usuário) pela chave VIGENTE da HashiCorp do instantâneo do PINS; a impressão digital primária tem de ser a
     que o PINS conferiu para o Terraform;
  4. a linha darwin_arm64 do SHA256SUMS tem de ser o shasum da rota de download;
  5. o zip darwin_arm64 é baixado como dado, conferido contra o SHA256SUMS assinado e lido (sem extrair para o disco)
     para calcular o h1 (dirhash.HashZip); o lock leva os zh: de TODAS as plataformas mais esse h1. O
     'terraform init -lockfile=readonly' reprova zip que não bata com um zh:, e o 'providers schema' reprova pasta
     desempacotada que não bata com o h1; o h1 da pasta é recalculado depois da extração e comparado.
Os arquivos baixados ficam em $BO_DATA/downloads/hist-gcp/google-V/ com SOURCE.txt; são dado, nunca executados.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from bo.schema import lockfile

from . import common as C

REGISTRY = "https://registry.terraform.io"
ALLOWED_HOSTS = {"registry.terraform.io", "releases.hashicorp.com"}
USER_AGENT = "bo-hist-gcp/1 (metadado público; sem credencial)"


def download_url(version: str) -> str:
    os_, arch = C.OS_ARCH.split("_")
    return f"{REGISTRY}/v1/providers/{C.SOURCE}/{version}/download/{os_}/{arch}"


def _get(url: str, timeout: int = 120) -> tuple[int, bytes]:
    host = urllib.parse.urlparse(url).hostname
    if urllib.parse.urlparse(url).scheme != "https" or host not in ALLOWED_HOSTS:
        raise C.HistError(f"URL fora dos hosts permitidos: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def index_platforms(hist: dict, version: str) -> dict:
    """Plataformas e protocolos da versão no índice v1 guardado pelo PINS (sha conferido)."""
    ref = hist["index_files"]["registry_v1"]
    p = C.unportable(ref["path"])
    if C.sha256_file(p) != ref["sha256"]:
        raise C.HistError(f"{ref['path']}: sha256 não confere com o history_versions.json")
    doc = json.loads(p.read_text(encoding="utf-8"))
    hits = [v for v in doc.get("versions", []) if v.get("version") == version]
    if len(hits) != 1:
        raise C.HistError(f"índice v1: versão {version} aparece {len(hits)} vez(es)")
    plats = sorted(f"{x['os']}_{x['arch']}" for x in hits[0].get("platforms", []))
    return {"platforms": plats, "protocols": hits[0].get("protocols", []), "index": ref["path"],
            "index_sha256": ref["sha256"]}


_SUMS_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")


def parse_sha256sums(text: str, version: str) -> dict[str, str]:
    """{plataforma: sha256 do zip} do SHA256SUMS do release (o manifest.json não é pacote)."""
    out = {}
    pref = f"terraform-provider-{C.PROVIDER}_{version}_"
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _SUMS_LINE.match(line)
        if not m:
            raise C.HistError(f"SHA256SUMS: linha fora do formato: {line[:80]!r}")
        sha, fname = m.groups()
        if not fname.startswith(pref):
            raise C.HistError(f"SHA256SUMS: arquivo de outro release: {fname}")
        if fname.endswith(".zip"):
            plat = fname[len(pref):-4]
            if plat in out:
                raise C.HistError(f"SHA256SUMS: plataforma repetida: {plat}")
            out[plat] = sha
    if not out:
        raise C.HistError("SHA256SUMS sem nenhum zip")
    return out


def locked_provider(version: str, zips: dict[str, str], h1: str | None = None) -> lockfile.LockedProvider:
    """Lock do google: zh: de todas as plataformas do SHA256SUMS assinado (+ h1 do zip darwin_arm64 conferido)."""
    hashes = [f"zh:{s}" for s in zips.values()] + ([h1] if h1 else [])
    return lockfile.LockedProvider(C.ADDRESS, version, version, tuple(sorted(hashes)))


def zip_h1(zip_path: Path) -> str:
    """h1 (dirhash.HashZip do terraform) de um zip de provider, lido como dado: nada é extraído para o disco."""
    import base64
    import hashlib
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(i.filename for i in z.infolist() if not i.is_dir())
        summary = hashlib.sha256()
        for name in names:
            if "\n" in name or name.startswith("/") or ".." in name.split("/"):
                raise C.HistError(f"zip com nome de arquivo inválido: {name!r}")
            h = hashlib.sha256()
            with z.open(name) as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            summary.update(f"{h.hexdigest()}  {name}\n".encode("utf-8"))
    return "h1:" + base64.b64encode(summary.digest()).decode("ascii")


def fetch_zip_h1(version: str, chain: dict) -> str:
    """Baixa o zip darwin_arm64 para $BO_TMP, confere o sha256 contra o SHA256SUMS assinado, calcula o h1 e apaga
    o zip. O h1 entra no lock para o 'providers schema' aceitar a pasta desempacotada pelo init (-lockfile=readonly
    não grava hash novo); o init continua conferindo o zip baixado por ele contra os zh:."""
    url = chain["meta"]["download_url"]
    status, body = _get(url, timeout=600)
    if status != 200:
        raise C.HistError(f"{version}: zip HTTP {status}")
    if C.sha256_bytes(body) != chain["zips"][C.OS_ARCH]:
        raise C.HistError(f"{version}: sha256 do zip baixado != SHA256SUMS assinado")
    tmp = C.bo_tmp() / "zips" / chain["meta"]["filename"]
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(body)
    try:
        return zip_h1(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def check_download_meta(meta: dict, version: str) -> None:
    os_, arch = C.OS_ARCH.split("_")
    want = f"terraform-provider-{C.PROVIDER}_{version}_{C.OS_ARCH}.zip"
    if (meta.get("os"), meta.get("arch"), meta.get("filename")) != (os_, arch, want):
        raise C.HistError(f"rota de download de {version}: plataforma ou nome do zip inesperados")
    for k in ("shasums_url", "shasums_signature_url", "download_url"):
        u = meta.get(k, "")
        if urllib.parse.urlparse(u).hostname != "releases.hashicorp.com" or not u.startswith("https://"):
            raise C.HistError(f"rota de download de {version}: {k} fora de https://releases.hashicorp.com")
    if not re.fullmatch(r"[0-9a-f]{64}", meta.get("shasum", "")):
        raise C.HistError(f"rota de download de {version}: shasum fora do formato")


def source_txt(version: str, meta: dict | None, status: int) -> str:
    lines = [f"Metadado e somas assinadas do release {C.SOURCE} {version} ({C.OS_ARCH}), baixados por",
             "python -I -m bo.hist_gcp.pipeline (módulo HIST-GCP), sem conta nem credencial.",
             f"Rota de download do Registry: {download_url(version)} (HTTP {status})."]
    if meta:
        lines += [f"SHA256SUMS: {meta['shasums_url']}", f"Assinatura: {meta['shasums_signature_url']}",
                  "Assinatura conferida com gpgv pela chave vigente da HashiCorp do instantâneo do PINS",
                  "($BO_DATA/PINS/registry_index/vendor_keys/hashicorp-pgp-key.txt).",
                  "schema/: saída de 'terraform providers schema -json' do binário assinado (bo.schema.extract,",
                  "sandbox sem credenciais e sem rede no passo do schema); o binário foi apagado depois."]
    lines += ["Licença: metadados públicos do Terraform Registry (termos da HashiCorp); provider MPL-2.0.",
              "Dado não confiável: lido como texto/JSON, nunca executado."]
    return "\n".join(lines) + "\n"


def fetch_and_verify(version: str, hist: dict, key: dict) -> dict:
    """Baixa (ou reaproveita) e confere a cadeia de uma versão. Devolve {'available': bool, ...}."""
    d = C.download_dir(version)
    d.mkdir(parents=True, exist_ok=True)
    idx = index_platforms(hist, version)
    status, body = _get(download_url(version))
    if status != 200:
        if C.OS_ARCH in idx["platforms"]:
            # o índice diz que o build existe: falha da rota não vira "indisponível"
            raise C.HistError(f"{version}: rota de download HTTP {status}, mas o índice do PINS lista {C.OS_ARCH}")
        try:
            err = json.loads(body).get("errors")
        except (ValueError, AttributeError):
            err = None
        (d / "SOURCE.txt").write_text(source_txt(version, None, status), encoding="utf-8")
        C.write_json(d / "registry-download-darwin_arm64.response.json",
                     {"url": download_url(version), "http_status": status, "errors": err})
        return {"available": False, "http_status": status, "registry_errors": err, "index": idx}
    meta = json.loads(body)
    check_download_meta(meta, version)
    if C.OS_ARCH not in idx["platforms"]:
        raise C.HistError(f"{version}: a rota de download tem {C.OS_ARCH}, o índice do PINS não")
    (d / "registry-download-darwin_arm64.json").write_bytes(body)
    s_status, sums = _get(meta["shasums_url"])
    g_status, sig = _get(meta["shasums_signature_url"])
    if s_status != 200 or g_status != 200:
        raise C.HistError(f"{version}: SHA256SUMS (HTTP {s_status}) ou assinatura (HTTP {g_status}) indisponível")
    sums_p = d / f"terraform-provider-{C.PROVIDER}_{version}_SHA256SUMS"
    sig_p = d / f"terraform-provider-{C.PROVIDER}_{version}_SHA256SUMS.sig"
    sums_p.write_bytes(sums)
    sig_p.write_bytes(sig)
    (d / "SOURCE.txt").write_text(source_txt(version, meta, status), encoding="utf-8")
    return verify_local(version, hist, key, idx)


def verify_local(version: str, hist: dict, key: dict, idx: dict | None = None) -> dict:
    """Reconfere, sem rede, os arquivos já baixados de uma versão disponível."""
    from bo.pins import sig as S
    d = C.download_dir(version)
    idx = idx or index_platforms(hist, version)
    meta = json.loads((d / "registry-download-darwin_arm64.json").read_text(encoding="utf-8"))
    check_download_meta(meta, version)
    sums_p = d / f"terraform-provider-{C.PROVIDER}_{version}_SHA256SUMS"
    sig_p = d / f"terraform-provider-{C.PROVIDER}_{version}_SHA256SUMS.sig"
    try:
        res = S.verify(sums_p, sig_p, key["armor"])
    except S.SigError as e:
        raise C.HistError(f"{version}: {e}") from None
    if not (res["valid"] and res["good"] and res["primary_fingerprint"] == key["primary_fingerprint"]):
        raise C.HistError(f"{version}: SHA256SUMS sem GOODSIG da chave {key['primary_fingerprint'][-16:]}")
    zips = parse_sha256sums(sums_p.read_text(encoding="utf-8"), version)
    if zips.get(C.OS_ARCH) != meta["shasum"]:
        raise C.HistError(f"{version}: zip {C.OS_ARCH} do SHA256SUMS != shasum da rota de download")
    return {"available": True, "index": idx, "meta": meta, "zips": zips,
            "sha256sums": sums_p, "sha256sums_sha256": C.sha256_file(sums_p),
            "signature": sig_p, "signature_sha256": C.sha256_file(sig_p),
            "gpg": {"fingerprint": res["fingerprint"], "primary_fingerprint": res["primary_fingerprint"],
                    "good": res["good"], "expired_key": res["expired_key"], "sig_date": res["sig_date"]}}


def write_lock(lp: lockfile.LockedProvider, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(lockfile.render([lp]), encoding="utf-8")
    return dest
