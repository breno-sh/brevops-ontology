"""Regras do privacy_lint (§8 do plano): identificadores de conta e recurso, e-mails, dinheiro
fora do cost_estimate.json agregado e qualquer conteúdo Withheld (segredos, env, UserData,
logs, conteúdo de objeto ou mensagem: nunca gravado, nem como hash).

As mensagens citam regra, arquivo e linha; o valor encontrado nunca é impresso inteiro.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# listas privadas, fora do repositório (canal privado do Breno); cada linha é um termo proibido
PRIVATE_LISTS = {
    "projeto_gcp": ("BO_PRIVACY_PROJECTS", Path.home() / ".config" / "bo" / "gcp_projects.txt"),
    "termo_privado": ("BO_PRIVACY_TERMS", Path.home() / ".config" / "bo" / "private_terms.txt"),
}
MONEY_OK_FILES = {"cost_estimate.json"}
ALLOWED_EMAIL_DOMAINS = re.compile(r"@(example\.(com|org|net)|[a-z0-9-]+\.(example|invalid|test))$", re.I)
TEXT_LIMIT = 50 * 1024 * 1024

HEX_TOKEN = re.compile(r"[0-9A-Fa-f]{32,}")

RULES: list[tuple[str, re.Pattern]] = [
    ("arn", re.compile(r"\barn:(aws|aws-cn|aws-us-gov|aws-iso[a-z-]*|partition|\$\{[^}]*\}):", re.I)),
    ("ocid", re.compile(r"\bocid1\.[a-z0-9_-]+\.", re.I)),
    ("azure_subscription", re.compile(
        r"/subscriptions/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("money", re.compile(r"(?:\b(?:US|R|A|C|NZ)\$\s?\d|\bUSD\s?\d|\d[\d.,]*\s?(?:USD|BRL)\b|€\s?\d|£\s?\d|"
                         r"\bEUR\s?\d|(?<![\w$\\])\$\s?\d+[.,]\d{2}\b|(?<![\w$\\])\$\d{1,3}(?:,\d{3})+\b)")),
    # Withheld: segredos
    ("secret_aws_key", re.compile(r"\b(AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b")),
    ("secret_private_key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("secret_token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}|"
                                r"sk-[A-Za-z0-9]{32,}|AIza[0-9A-Za-z_-]{35}|ya29\.[0-9A-Za-z_-]{20,})")),
    ("secret_jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.")),
    ("secret_assignment", re.compile(
        r"(?i)\b(aws_secret_access_key|secret_access_key|client_secret|password|passwd|api[_-]?key|"
        r"access[_-]?token|auth[_-]?token|private_key|sas_token)\b[\"']?\s*[:=]\s*+[\"'](?!REDACTED|WITHHELD|<|\$\{|(?:string|number|bool|dynamic)[\"'])"
        r"[^\"'\s]{6,}[\"']")),
    ("secret_env_line", re.compile(r"^\s*(?:export\s+)?[A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|API_KEY|ACCESS_KEY)[A-Z0-9_]*="
                                   r"(?!\s*$|[\"']?\$|[\"']?REDACTED|[\"']?WITHHELD)\S{6,}")),
    ("secret_conn_string", re.compile(r"(?i)\b(AccountKey|SharedAccessKey|SharedAccessSignature)=[^;\s]{8,}")),
    ("secret_bearer", re.compile(r"(?i)\bauthorization\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9._~+/-]{12,}")),
    ("gcp_service_account_key", re.compile(r"\"type\"\s*:\s*\"service_account\"")),
    # Withheld: conteúdo que nunca é gravado, nem como hash
    ("withheld_hash", re.compile(
        r"(?i)[\"']?\b(user_?data|custom_?data|startup[_-]?script|env(ironment)?[_-]?(vars?|variables)?|secrets?|"
        r"passwords?|message[_-]?(body|content)|object[_-]?(body|content)|log[_-]?(events?|lines?|content))"
        r"[_-]?(sha\d*|md5|hash|digest|base64)\b[\"']?\s*[:=]")),
    ("withheld_content", re.compile(
        r"(?i)[\"'](user_?data|user_data_base64|custom_data|startup-script|metadata_startup_script|"
        r"message_body|messagebody|object_content|log_events|logevents)[\"']\s*:\s*+(?![\"']\s*[\"']|null|"
        r"[\"'](REDACTED|WITHHELD))")),
    ("withheld_env", re.compile(r"(?i)[\"']Environment[\"']\s*:\s*\{\s*[\"']Variables[\"']\s*:\s*\{\s*[\"']")),
]


@dataclass
class Finding:
    rule: str
    file: str
    line: int
    hint: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.rule} ({self.hint})"


def mask(s: str) -> str:
    s = s.strip()
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "…" + f"[{len(s)} car.]"


def load_lists() -> tuple[dict[str, list[str]], list[str]]:
    """Listas privadas (ids de projeto GCP, nomes e valores da empresa). Ausente = regra não aplicada, com nota."""
    lists, notes = {}, []
    for rule, (env, default) in PRIVATE_LISTS.items():
        p = Path(os.environ.get(env) or default)
        if not p.exists():
            notes.append(f"lista {rule} ausente ({p}); regra não aplicada")
            continue
        ids = [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")]
        lists[rule] = ids
        notes.append(f"lista {rule}: {len(ids)} termo(s) de {p}")
    return lists, notes


def twelve_digit_hits(line: str) -> list[str]:
    """12 dígitos seguidos (conta AWS), fora de tokens hex longos (hashes)."""
    hex_spans = [m.span() for m in HEX_TOKEN.finditer(line)]
    out = []
    for m in re.finditer(r"(?<!\d)\d{12}(?!\d)", line):
        a, b = m.span()
        if any(x <= a and b <= y for x, y in hex_spans):
            continue
        out.append(m.group(0))
    return out


def _list_regexes(lists: dict | None) -> list[tuple[str, re.Pattern]]:
    out = []
    for rule, ids in (lists or {}).items():
        if ids:
            out.append((rule, re.compile(r"(?i)(?<![\w-])(" + "|".join(re.escape(x) for x in ids) + r")(?![\w-])")))
    return out


def scan_text(text: str, fname: str, lists: dict | None = None) -> list[Finding]:
    found = []
    base = os.path.basename(fname)
    list_res = _list_regexes(lists)
    for n, line in enumerate(text.splitlines(), 1):
        for hit in twelve_digit_hits(line):
            found.append(Finding("doze_digitos", fname, n, mask(hit)))
        for rule, rx in RULES:
            for m in rx.finditer(line):
                val = m.group(0)
                if rule == "email" and ALLOWED_EMAIL_DOMAINS.search(val):
                    continue
                if rule == "money" and base in MONEY_OK_FILES:
                    continue
                found.append(Finding(rule, fname, n, mask(val)))
        for rule, rx in list_res:
            for m in rx.finditer(line):
                found.append(Finding(rule, fname, n, mask(m.group(0))))
    return found


def is_binary(b: bytes) -> bool:
    return b"\x00" in b[:8192]


def scan_bytes(b: bytes, fname: str, lists=None, strict: bool = False) -> list[Finding]:
    if is_binary(b):
        if strict:
            # em modo estrito, binário também é varrido pelas sequências imprimíveis
            text = "\n".join(x.decode("ascii") for x in re.findall(rb"[\x20-\x7e]{6,}", b))
            return scan_text(text, fname + " (binário)", lists)
        return []
    return scan_text(b.decode("utf-8", errors="replace"), fname, lists)


def scan_large_text(f: Path, lists=None) -> list[Finding]:
    found = []
    with open(f, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            for x in scan_text(line, str(f), lists):
                x.line = i
                found.append(x)
    return found


def _signed_ok(f: Path, root: Path) -> bool:
    """True se o sha256 de f aparece num SIGNED.sha256 na pasta de f ou acima dela (até root).
    O SIGNED.sha256 é escrito pelo módulo que conferiu a assinatura do pacote (formato do sha256sum)."""
    import hashlib
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    top = root if root.is_dir() else root.parent
    d = f.parent
    while True:
        sf = d / "SIGNED.sha256"
        if sf.is_file() and any(l.split()[:1] == [digest] for l in sf.read_text().splitlines()):
            return True
        if d == top or d == d.parent:
            return False
        d = d.parent


def scan_paths(paths: list[Path], strict: bool = False, lists=None) -> tuple[list[Finding], int, list[str]]:
    findings, n, notes = [], 0, []
    for root in paths:
        root = Path(root)
        if not root.exists():
            if strict:
                # estrito: caminho prometido que não existe não passa por vacuidade
                findings.append(Finding("caminho_ausente", str(root), 0, "não existe; --strict exige o caminho"))
            else:
                notes.append(f"caminho ausente (nada a varrer): {root}")
            continue
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" in f.parts or f.suffix == ".pyc":
                continue
            try:
                if f.suffix == ".gz":
                    # comprimido: varre o conteúdo descomprimido, linha a linha (ruído do gzip não é texto)
                    import gzip
                    n += 1
                    with gzip.open(f, "rt", encoding="utf-8", errors="replace") as gz:
                        for i, line in enumerate(gz, 1):
                            for x in scan_text(line, str(f), lists):
                                x.line = i
                                findings.append(x)
                    continue
                if f.suffix == ".parquet":
                    # tabela colunar: varre os valores decodificados de cada coluna, lote a lote (bytes de
                    # zstd/snappy formam padrões por acaso; o que importa é o valor gravado)
                    try:
                        import pyarrow.parquet as pq
                    except ImportError:
                        findings.append(Finding("nao_varrido", str(f), 0, "pyarrow ausente; parquet não varrido"))
                        continue
                    n += 1
                    row = 0
                    for batch in pq.ParquetFile(f).iter_batches(batch_size=65536):
                        cols = [c.to_pylist() for c in batch.columns]
                        for i in range(batch.num_rows):
                            row += 1
                            for c in cols:
                                v = c[i]
                                if v is None or isinstance(v, (int, float, bool)):
                                    continue
                                for x in scan_text(v if isinstance(v, str) else str(v), str(f), lists):
                                    x.line = row
                                    findings.append(x)
                    continue
                if f.stat().st_size > TEXT_LIMIT:
                    with open(f, "rb") as fh:
                        binary = is_binary(fh.read(8192))
                    if not binary:
                        # texto grande (ex.: JSONL de átomos): varrido linha a linha, sem carregar inteiro
                        n += 1
                        findings.extend(scan_large_text(f, lists))
                        continue
                    if binary and _signed_ok(f, root):
                        # binário de pacote assinado e já conferido (ex.: provider Terraform no plugin_cache):
                        # aceito porque o sha256 está num SIGNED.sha256 da mesma pasta ou de uma pasta acima
                        notes.append(f"binário assinado aceito: {f}")
                        continue
                    msg = f"arquivo grande demais para varrer: {f}"
                    if strict:
                        findings.append(Finding("nao_varrido", str(f), 0, msg))
                    notes.append(msg)
                    continue
                b = f.read_bytes()
            except OSError as e:
                findings.append(Finding("ilegivel", str(f), 0, e.strerror or "erro"))
                continue
            n += 1
            findings.extend(scan_bytes(b, str(f), lists, strict))
    return findings, n, notes
