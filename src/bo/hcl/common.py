"""Caminhos, ids sintéticos e escrita canônica do módulo HCL."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "HCL"
TZ = ZoneInfo("America/Recife")
TERRADS_DIR = Path("/Users/breno/doutorado/pesquisa/superficie/data/terrads/zenodo-20339474")
TAR = TERRADS_DIR / "TerraDS.tar.gz"
SQLITE = TERRADS_DIR / "TerraDS.sqlite"

# provedores do C00 (prefixo do tipo -> provider)
PROVIDERS = {"aws": "aws", "google": "google", "azurerm": "azurerm", "oci": "oci"}

# parâmetros fixados (vão para parse_stats.json e summary.json)
PARAMS = {
    "vocab_min_families": 5,       # valor de cadeia só fica literal se aparece em >= 5 famílias no mesmo contexto
    "vocab_enum_share": 0.5,       # e o contexto é de enumeração: >= 50% das ocorrências são de valores comuns
    "file_timeout_s": 20,          # tempo-limite por arquivo no parser
    "max_file_bytes": 4 * 1024 * 1024,  # arquivo maior não é lido (conta como falha 'too_large')
    "sym_hex": 12,
    "workers": 14,
}


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def out_dir() -> Path:
    return bo_data() / MODULE


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or (bo_data() / "tmp" / MODULE))
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


_TWELVE = re.compile(r"(?<!\d)\d{12}(?!\d)")


def _hex_id(seed: str, n: int) -> str:
    """Hex determinístico que nunca contém 12 dígitos seguidos (o privacy_lint leria como conta) e que termina
    em letra: assim nenhum byte vizinho (o prefixo de tamanho do valor seguinte num parquet, por exemplo)
    estende uma sequência de dígitos do id até 12."""
    k = 0
    while True:
        h = hashlib.sha256(f"{seed}#{k}".encode()).hexdigest()[:n]
        if h[-1] in "abcdef" and not _TWELVE.search("-" + h + "-") and not re.search(r"\d{12}", h):
            return h
        k += 1


def repo_id(terrads_id: int | str) -> str:
    return "R-" + _hex_id(f"terrads-repo:{terrads_id}", 12)


def family_id(content_digest: str) -> str:
    return "F-" + _hex_id(f"terrads-family:{content_digest}", 12)


def sym_id(rid: str, ordinal: int) -> str:
    """Símbolo por repositório: depende só do repo_id e da ordem da 1ª ocorrência (nunca do texto)."""
    return "SYM-" + _hex_id(f"{rid}|{ordinal}", PARAMS["sym_hex"])


def provider_of(rtype: str) -> str | None:
    return PROVIDERS.get(rtype.split("_", 1)[0]) if "_" in rtype else None


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def key64(*parts: str) -> int:
    """Chave de 64 bits para o vocabulário (contexto + valor), sem guardar o texto."""
    return int.from_bytes(hashlib.blake2b("\x00".join(parts).encode("utf-8", "surrogatepass"),
                                          digest_size=8).digest(), "big")
