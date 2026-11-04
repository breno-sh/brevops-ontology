"""Caminhos, relógio (America/Recife), durações xsd e gravação do PROBEKIT. Temporário só em $BO_TMP."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import MODULE_ID

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Recife")
except Exception:  # pragma: no cover - sem tzdata o fuso de Recife é fixo em -03:00
    TZ = timezone(timedelta(hours=-3), "America/Recife")


class ProbeError(RuntimeError):
    """Recusa do kit (pré-condição, protocolo incoerente, suporte não validado, backend sem GO)."""

    def __init__(self, msg: str, code: str = "PROBE"):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------------------------------------- caminhos
def repo() -> Path:
    env = os.environ.get("BO_REPO")
    if env and (Path(env) / "prereg").is_dir():
        return Path(env)
    return Path(__file__).resolve().parents[3]


def data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def tmp() -> Path:
    p = Path(os.environ.get("BO_TMP") or (data() / "tmp" / MODULE_ID))
    rp = str(p.resolve())
    if rp == "/tmp" or rp.startswith(("/tmp/", "/private/tmp/")):
        raise ProbeError(f"BO_TMP aponta para /tmp ({rp}); o kit só usa $BO_DATA/tmp/<ID>", "TMP")
    p.mkdir(parents=True, exist_ok=True)
    return p


def deploy_dir() -> Path:
    return repo() / "deploy" / "probes"


def results_dir() -> Path:
    return repo() / "results" / MODULE_ID


def data_dir() -> Path:
    return data() / MODULE_ID


def prereg_path() -> Path:
    return repo() / "prereg" / "probe_types.yaml"


def service_evidence_path() -> Path:
    return data() / "SERVICE-EVIDENCE" / "protocol_support.jsonl"


def sku_table_path() -> Path:
    return repo() / "deploy" / "safety" / "allowlist_skus.yaml"


def pins_path() -> Path:
    return repo() / "universe" / "pins.json"


def portable(p: Path | str) -> str:
    s = str(p)
    for k, v in (("$BO_REPO", str(repo())), ("$BO_DATA", str(data()))):
        if s == v or s.startswith(v + "/"):
            return k + s[len(v):]
    return s


# ---------------------------------------------------------------------------------------------- relógio
def now_dt() -> datetime:
    return datetime.now(TZ).replace(microsecond=0)


def iso(t: datetime) -> str:
    return t.astimezone(TZ).isoformat(timespec="seconds")


def now() -> str:
    return iso(now_dt())


DUR_RX = re.compile(r"^P(?=\d|T\d)(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?"
                    r"(?:T(?=\d)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


def duration_s(s: str) -> float:
    """xsd:duration em segundos. Ano e mês não têm tamanho fixo: o protocolo só usa semana, dia e hora."""
    m = DUR_RX.match(s or "")
    if not m:
        raise ProbeError(f"duração inválida: {s!r}", "DURATION")
    y, mo, w, d, h, mi, se = m.groups()
    if y or mo:
        raise ProbeError(f"duração com ano/mês não é exata: {s!r}", "DURATION")
    return (int(w or 0) * 7 * 86400 + int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi or 0) * 60
            + float(se or 0))


def fmt_duration(sec: float) -> str:
    sec = int(round(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    out = "P" + (f"{d}D" if d else "")
    t = (f"{h}H" if h else "") + (f"{m}M" if m else "") + (f"{s}S" if s else "")
    return out + ("T" + t if t else ("" if d else "T0S"))


# ---------------------------------------------------------------------------------------------- arquivos
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_atomic(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    t = path.with_name(f".{path.name}.{os.getpid()}.part")
    t.write_text(text, encoding="utf-8")
    os.replace(t, path)


def write_json(path: Path, obj) -> None:
    write_atomic(path, dumps(obj))


def read_jsonl(path: Path) -> list[dict]:
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ProbeError(f"{path.name}:{n}: JSON inválido ({e.msg})", "JSONL") from None
    return out


def compare_or_write(path: Path, obj, write: bool, ignore: tuple = ("generated_at",)) -> list[str]:
    """Gate: com write grava; senão compara com o gravado ignorando carimbos e devolve as diferenças."""
    path = Path(path)
    if write:
        write_json(path, obj)
        return []
    if not path.exists():
        return [f"{portable(path)} ausente (rode com --write)"]
    old = json.loads(path.read_text(encoding="utf-8"))
    new = json.loads(json.dumps(obj))
    for k in ignore:
        old.pop(k, None)
        new.pop(k, None)
    if old != new:
        keys = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
        return [f"{portable(path)} difere do regenerado em: {', '.join(keys) or '(conteúdo)'}"]
    return []
