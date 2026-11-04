"""Caminhos, relógio, hashes e gravação atômica do SAFETY. Só biblioteca padrão (vai para a VM do supervisor)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE = "SAFETY"
MODEL_ID = "claude-opus-5-5"
PROVIDERS = ("aws", "google", "azurerm", "oci")

try:  # a VM pode não ter tzdata; o fuso de Recife é fixo em -03:00 (sem horário de verão desde 2019)
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Recife")
except Exception:  # pragma: no cover
    TZ = timezone(timedelta(hours=-3), "America/Recife")


class SafetyError(RuntimeError):
    """Recusa do kit. code distingue a família da recusa nos relatórios."""

    def __init__(self, msg: str, code: str = "SAFETY"):
        super().__init__(msg)
        self.code = code


# ------------------------------------------------------------------------------------------------- caminhos
def src_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bo_repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    here = src_root().parent
    return here if (here / "deploy").is_dir() else Path("/Users/breno/doutorado/brevops-ontology")


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or (bo_data() / "tmp" / MODULE))
    p.mkdir(parents=True, exist_ok=True)
    return p


def deploy_dir() -> Path:
    return bo_repo() / "deploy" / "safety"


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def data_dir() -> Path:
    return bo_data() / MODULE


def portable(p: Path) -> str:
    s = str(p)
    for k, v in (("$BO_REPO", str(bo_repo())), ("$BO_DATA", str(bo_data()))):
        if s == v or s.startswith(v + "/"):
            return k + s[len(v):]
    return s


def real(p: str) -> Path:
    return Path(p.replace("$BO_REPO", str(bo_repo())).replace("$BO_DATA", str(bo_data())))


def inside_git_repo(p: Path) -> Path | None:
    """Raiz do repositório git que contém p (ou None). Canal privado nunca fica dentro de um."""
    p = Path(p).resolve()
    for d in [p, *p.parents]:
        if (d / ".git").exists():
            return d
    return None


# ------------------------------------------------------------------------------------------------- relógio
def now_dt() -> datetime:
    return datetime.now(TZ).replace(microsecond=0)


def iso(t: datetime) -> str:
    return t.astimezone(TZ).isoformat(timespec="seconds")


def now() -> str:
    return iso(now_dt())


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def from_epoch(x: float) -> str:
    return iso(datetime.fromtimestamp(x, TZ))


# ------------------------------------------------------------------------------------------------- hashes
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------------------------------------------- gravação
def write_atomic(path: Path, text: str, mode: int | None = None) -> None:
    """Grava em arquivo temporário irmão, fsync, rename e fsync do diretório (sobrevive a SIGKILL)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.novo")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode if mode is not None else 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    fsync_dir(path.parent)


def fsync_dir(d: Path) -> None:
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def append_line(path: Path, line: str, mode: int = 0o644) -> None:
    """Uma linha JSONL num único write com O_APPEND e fsync. Linha truncada por morte do processo é detectada
    na leitura (read_jsonl), nunca confundida com registro válido."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def read_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    """Registros válidos e problemas. A última linha sem '\\n' ou que não é JSON é cauda rasgada (torn tail):
    vira problema 'cauda_rasgada' e é ignorada; uma linha inválida no meio é 'linha_invalida' (corrupção)."""
    path = Path(path)
    if not path.exists():
        return [], []
    raw = path.read_bytes().decode("utf-8", errors="replace")
    recs, probs = [], []
    lines = raw.split("\n")
    tail = lines.pop()  # depois do último '\n' (vazio se o arquivo termina bem)
    for n, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        try:
            recs.append(json.loads(ln))
        except json.JSONDecodeError:
            probs.append(f"linha_invalida:{n}")
    if tail.strip():
        try:
            json.loads(tail)
            probs.append("cauda_sem_quebra")  # registro completo sem '\n': também não conta (escrita interrompida)
        except json.JSONDecodeError:
            probs.append("cauda_rasgada")
    return recs, probs


def repair_tail(path: Path) -> bool:
    """Corta a cauda rasgada (bytes depois do último '\\n'). Devolve True se cortou."""
    path = Path(path)
    if not path.exists():
        return False
    b = path.read_bytes()
    if not b or b.endswith(b"\n"):
        return False
    cut = b.rfind(b"\n") + 1
    with open(path, "r+b") as f:
        f.truncate(cut)
        f.flush()
        os.fsync(f.fileno())
    return True


def write_json(path: Path, obj, mode: int | None = None) -> None:
    write_atomic(path, json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", mode)


# ------------------------------------------------------------------------------------------------- nomes
SLUG_RX = re.compile(r"[^a-z0-9]+")


def slug(s: str) -> str:
    return SLUG_RX.sub("-", s.lower()).strip("-")


def tag_value(s: str) -> str:
    """Valor de tag aceito pelos 4 (rótulo GCP: minúsculas, dígitos, '-' e '_'; até 63)."""
    v = slug(s)[:63]
    if not v:
        raise SafetyError(f"valor de tag vazio a partir de {s!r}", "TAG")
    return v


def synthetic_name(batch_id: str, seq: int) -> str:
    """Nome sintético rastreável para tipo sem tag: bo-<lote>-<seq 4 dígitos> (casa ^bo-[a-z0-9-]{3,40}$)."""
    b = slug(batch_id)
    if b.startswith("b-"):
        b = b[2:]
    name = f"bo-{b[:30]}-{seq:04d}"
    if not re.fullmatch(r"bo-[a-z0-9\-]{3,40}", name):
        raise SafetyError(f"nome sintético inválido: {name}", "NAME")
    return name


def monotonic() -> float:
    return time.monotonic()


def publish_result(path: Path, obj: dict, write: bool, stamp_key: str = "measured_at") -> list[str]:
    """Relatório de gate: com write=True grava (com carimbo); senão compara com o gravado ignorando o carimbo e
    devolve as diferenças (relatório do repositório nunca muda sozinho num gate)."""
    path = Path(path)
    if write:
        write_json(path, {**obj, stamp_key: now()})
        return []
    if not path.exists():
        return [f"{path.name} ausente (rode com --write-results)"]
    old = json.loads(path.read_text(encoding="utf-8"))
    old.pop(stamp_key, None)
    new = json.loads(json.dumps(obj))
    if old != new:
        keys = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
        return [f"{path.name} difere da medição atual em: {', '.join(keys)}"]
    return []
