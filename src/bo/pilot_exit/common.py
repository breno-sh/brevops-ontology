"""Caminhos, tempo, hashes e a descrição fixa das duas fatias (sem nenhum dado retido)."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "PILOT-EXIT"
TZ = ZoneInfo("America/Recife")
PROVIDERS = ("aws", "google", "azurerm", "oci")
DIRECTIONS = tuple(f"{a}->{b}" for a in PROVIDERS for b in PROVIDERS if a != b)

# VM Oracle do Breno (D15): a chave privada só existe lá; o envelope vai pelo ssh e o texto claro volta pelo pipe.
VM = "ubuntu@136.248.69.238"
# mesmo comando que os oráculos usaram para conferir o selo (bo.pilot_sto_oracle.seal_verify), sem o sha256sum
REMOTE_DECRYPT = ("openssl cms -decrypt -inform PEM -inkey ~/brevops-keys/seal_private.pem "
                  "-recip ~/brevops-keys/seal_cert.pem")
VM_DECRYPT_ARGV = ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", VM, REMOTE_DECRYPT)

SLICES = {
    "sto": {
        "e2e": "PILOT-STO-E2E", "oracle": "PILOT-STO-ORACLE", "map": "PILOT-STO-MAP",
        "envelope": "$BO_DATA/PILOT-STO-ORACLE/sealed/heldout.cms.pem",
        "index": "$BO_DATA/PILOT-STO-ORACLE/sealed/SEALED_INDEX.json",
        "code": ["src/bo/pilot/sto/", "src/bo/pilot_sto_e2e/"],
    },
    "net": {
        "e2e": "PILOT-NET-E2E", "oracle": "PILOT-NET-ORACLE", "map": "PILOT-NET-MAP",
        "envelope": "$BO_DATA/PILOT-NET-ORACLE/sealed/retained.cms.pem",
        "index": "$BO_DATA/PILOT-NET-ORACLE/sealed/sealed_index.json",
        "code": ["src/bo/pilot/net/", "src/bo/pilot_net_e2e/"],
    },
}


def now() -> str:
    return _dt.datetime.now(TZ).isoformat(timespec="seconds")


def repo() -> Path:
    v = os.environ.get("BO_REPO")
    return Path(v) if v else Path(__file__).resolve().parents[3]


def data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or data() / "tmp" / MODULE)
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir(root: Path | None = None) -> Path:
    return (root or repo()) / "results" / MODULE


def data_dir() -> Path:
    return data() / MODULE


def staging_dir() -> Path:
    return data_dir() / ".staging"


def run_data_dir() -> Path:
    """Onde ler a execução: o .staging (mais novo, ainda não promovido) se existe; senão o promovido."""
    st = staging_dir() / "heldout"
    if st.is_dir():
        return st
    return data_dir() / "heldout"


def expand(p: str, root: Path | None = None) -> Path:
    return Path(p.replace("$BO_REPO", str(root or repo())).replace("$BO_DATA", str(data())))


def portable(p: Path | str, root: Path | None = None) -> str:
    s = str(p)
    for k, v in (("$BO_REPO", str(root or repo())), ("$BO_DATA", str(data()))):
        if s == v or s.startswith(v + "/"):
            return k + s[len(v):]
    return s


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".tmp")
    t.write_text(dump(obj), encoding="utf-8")
    t.replace(p)


def read_json(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_jsonl(p: Path) -> list:
    out = []
    for line in Path(p).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def say(msg: str) -> None:
    print(f"[{now()}] {msg}", flush=True)
