"""Caminhos, versões e leitura das entradas do DRIFT (somente leitura: saídas dos HIST-*)."""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "DRIFT"
TZ = ZoneInfo("America/Recife")

#: provider -> (módulo HIST, repositório da documentação, tag da cópia, pasta dos guias de atualização)
PROVIDERS = {
    "aws": ("HIST-AWS", "hashicorp/terraform-provider-aws", "v6.71.0",
            "downloads/docs-aws/v6.71.0/website/docs/guides"),
    "google": ("HIST-GCP", "hashicorp/terraform-provider-google", "v8.9.0",
               "downloads/docs-google/website/docs/guides"),
    "azurerm": ("HIST-AZURE", "hashicorp/terraform-provider-azurerm", "v5.12.0",
                "downloads/docs-azurerm/v5.12.0/website/docs/guides"),
    "oci": ("HIST-OCI", "oracle/terraform-provider-oci", "v9.11.0",
            "downloads/docs-oci/website/docs/guides"),
}
ORDER = list(PROVIDERS)

#: campos do contrato que o schema JSON do plugin expõe e que o DRIFT compara (mudança de contrato)
COMPARED = ("tf_type", "required", "optional", "computed", "sensitive", "deprecated", "write_only",
            "nesting", "block_path")
#: campos que o brief pede e que o estimando não observa: `terraform providers schema -json` não exporta
UNOBSERVABLE = {
    "force_new": "ForceNew/RequiresReplace não faz parte do schema JSON do plugin (só aparece no plano)",
    "default": "Default não é exportado pelo schema JSON do plugin (protocolos 5 e 6)",
}


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def bo_repo() -> Path:
    v = os.environ.get("BO_REPO")
    return Path(v) if v else Path(__file__).resolve().parents[3]


def bo_tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / MODULE)
    p.mkdir(parents=True, exist_ok=True)
    return p


def out_dir() -> Path:
    return bo_data() / MODULE


def staging_dir() -> Path:
    return out_dir() / ".staging"


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def now() -> str:
    return _dt.datetime.now(TZ).isoformat(timespec="seconds")


def portable(p: Path) -> str:
    s = str(p)
    for var, root in (("$BO_DATA", str(bo_data())), ("$BO_REPO", str(bo_repo()))):
        if s == root or s.startswith(root + "/"):
            return var + s[len(root):]
    return s


def semver_key(v: str) -> tuple:
    core = v.split("-", 1)[0].split("+", 1)[0]
    return tuple(int(x) for x in core.split("."))


def major(v: str) -> int:
    return semver_key(v)[0]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dumps(obj) -> str:
    """JSON canônico de uma linha (chaves ordenadas, sem espaços, UTF-8)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass
class Version:
    version: str
    released_at: str
    atoms_path: Path | None = None   # None: lacuna declarada (sem átomos no MANIFEST do HIST)
    atoms_sha256: str | None = None
    gap_reason: str | None = None

    @property
    def observed(self) -> bool:
        return self.atoms_path is not None


@dataclass
class ProviderInput:
    provider: str
    module: str
    versions_json: Path
    versions: list[Version] = field(default_factory=list)

    @property
    def observed(self) -> list[Version]:
        return [v for v in self.versions if v.observed]

    @property
    def gaps(self) -> list[Version]:
        return [v for v in self.versions if not v.observed]


def _manifest(mf: Path) -> dict[str, str]:
    out = {}
    for line in mf.read_text(encoding="utf-8").splitlines():
        if line.strip():
            sha, rel = line.split(None, 1)
            out[rel.strip()] = sha
    return out


def _gap_reason(hist_dir: Path, version: str) -> str:
    """Motivo declarado pelo HIST para a versão sem átomos (texto curto, só o status e o começo do motivo)."""
    for name in ("extraction.json", "extract_report.json"):
        p = hist_dir / name
        if not p.is_file():
            continue
        vs = json.loads(p.read_text(encoding="utf-8")).get("versions")
        items = vs.values() if isinstance(vs, dict) else (vs or [])
        for it in items:
            if isinstance(it, dict) and it.get("version") == version:
                st = it.get("status") or "?"
                why = str(it.get("reason") or it.get("motivo") or "").split(":", 1)[0].split(";", 1)[0]
                return f"{name}: status {st}" + (f" ({why.strip()[:120]})" if why.strip() else "")
    return "versão listada sem átomos no MANIFEST do HIST"


def load_provider(provider: str, data: Path | None = None) -> ProviderInput:
    data = data or bo_data()
    mod = PROVIDERS[provider][0]
    hist = data / mod
    vj = hist / "versions.json"
    doc = json.loads(vj.read_text(encoding="utf-8"))
    if doc.get("provider") != provider:
        raise ValueError(f"{vj}: provider {doc.get('provider')} != {provider}")
    mf = _manifest(hist / "MANIFEST.sha256")
    pin = ProviderInput(provider, mod, vj)
    for v in doc["versions"]:
        rel = f"atoms_{v['version']}.jsonl.gz"
        if rel in mf and (hist / rel).is_file():
            pin.versions.append(Version(v["version"], v["released_at"], hist / rel, mf[rel]))
        else:
            pin.versions.append(Version(v["version"], v["released_at"], gap_reason=_gap_reason(hist, v["version"])))
    ks = [semver_key(v.version) for v in pin.versions]
    if ks != sorted(ks) or len(set(ks)) != len(ks):
        raise ValueError(f"{vj}: versões fora de ordem ou repetidas")
    return pin


def read_atoms(path: Path, verify_sha: str | None = None) -> list[dict]:
    raw = path.read_bytes()
    if verify_sha and hashlib.sha256(raw).hexdigest() != verify_sha:
        raise ValueError(f"{path}: sha256 diverge do MANIFEST do HIST")
    return [json.loads(l) for l in gzip.decompress(raw).decode("utf-8").splitlines() if l.strip()]
