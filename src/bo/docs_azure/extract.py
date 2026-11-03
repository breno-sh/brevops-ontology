"""Regras de extração do DOCS-AZURE: texto de um item (ou nota) -> fatos C03 candidatos.

Cada regra devolve (fact_kind, status, valor | motivo, deslocamento da frase no texto, método, nível).
Nada é inventado: valor só sai de literal escrito na frase (entre crases ou número/booleano solto);
o que a frase diz sem literal vira status=unknown com motivo e a própria frase como fonte.

Regras (todas por expressão regular sobre a frase, method=regex, evidence=published, salvo indicação):
  description        texto do item sem o marcador '(Optional)' (method=parser)
  default            'Defaults to `x`', 'Default value is `x`', 'The default (value) is `x`', 'Default: `x`',
                     '(Defaults to 30 minutes)' nos timeouts; literal tipado pelo tf_type do átomo; sem literal
                     ou com 2+ literais diferentes -> unknown 'ambiguous'
  allowed_values     'Possible|Valid|Allowed|Accepted|Supported|Permitted values|options are|is|include',
                     'The only possible value is', 'must|can|should be (set to) one of|either' -> literais entre
                     crases depois do gatilho, cortados em when/if/unless/Defaults/Changing
  range              'between n and m', 'from n to m', 'in the range (of) n to|- m', 'at least|minimum (of) n',
                     'at most|maximum (of)|up to|no more than|cannot exceed n'; applies_to = length quando a
                     frase fala de caracteres, items quando fala de itens/entradas, senão value
  unit               (só átomo numérico) 'in <unidade>', 'number of <unidade>', 'between n and m <unidade>',
                     '`n` <unidade>', 'percentage'; e o sufixo do nome (_in_days, _seconds, _mb, ...) com
                     evidence=derived; unidades publicadas diferentes -> mais um fato unknown 'contradictory'
  format             ISO 8601 (duração ou data), RFC 3339, CIDR, base64, JSON, UUID/GUID, HH:MM, cron
  forces_replacement 'Changing this|the `x` ... forces a new ...' -> true
  deprecation        marcador (Deprecated), 'is|are|has been|will be deprecated', 'deprecated in favour',
                     'will be removed in' -> {deprecated, scope: attribute|values, values?, removed_in?,
                     replaced_by?}; scope=values quando antes de 'deprecated' há literal que não é o
                     próprio nome nem irmão; irmão (ou nome snake_case) citado ali -> a frase é de outro
                     atributo, sem fato
  conflicts_with     'conflicts with', 'cannot be specified|set|used together with', 'mutually exclusive',
                     'only one of' -> irmãos citados entre crases (atributos ou blocos do mesmo bloco)
  required_when      '(is) required when|if', 'must be specified|set|provided when|if' -> a condição (texto)
  example            'e.g.', 'for example', 'such as' seguidos de literais entre crases (sem nome de irmão,
                     índice '[0]' nem interpolação '${')
  behavior           nota (->, ~>, !>) anexada ao átomo: logo depois do item e citando-o (ou começando por
                     'This'), ou citando por nome um único átomo da seção
"""

from __future__ import annotations

import re

ABBREV = ("e.g", "i.e", "etc", "vs", "approx", "No", "no", "min", "max", "incl", "Inc", "Ltd", "St")


def sentences(text: str) -> list[tuple[int, str]]:
    """Frases de um texto: corta em . ? ! seguido de espaço e maiúscula/crase/parêntese, fora de crases,
    e antes de um marcador recuado ('\\n  * '). Devolve (deslocamento, frase)."""
    out, start, tick = [], 0, False
    n = len(text)
    i = 0
    while i < n:
        c = text[i]
        if c == "`":
            tick = not tick
        elif not tick and c in ".?!" and i + 1 < n and text[i + 1] in " \n":
            j = i + 1
            while j < n and text[j] in " \n":
                j += 1
            word = re.search(r"([A-Za-z.]+)$", text[start:i])
            abbrev = word and word.group(1).rstrip(".") in ABBREV
            if j < n and (text[j].isupper() or text[j] in "`(*~-") and not abbrev:
                out.append((start, text[start:i + 1]))
                start = j
                i = j
                continue
        elif not tick and c == "\n" and re.match(r"\n\s*[*-]\s", text[i:]):
            if text[start:i].strip():
                out.append((start, text[start:i]))
            start = i + 1
        i += 1
    if text[start:].strip():
        out.append((start, text[start:]))
    return [(o + (len(s) - len(s.lstrip())), " ".join(s.split())) for o, s in out if s.strip()]


TICKS = re.compile(r"`([^`]*)`")
NUM = r"-?\d[\d,]*(?:\.\d+)?"

# ------------------------------------------------------------------------------------------- default
DEFAULT = re.compile(
    r"(?i)\b(?:defaults?\s+(?:value\s+)?(?:is\s+|to\s*:?\s*|of\s+)|default\s+value\s+(?:is|of|will be)\s+|"
    r"the\s+default\s+(?:value\s+)?(?:is|will be)\s+(?:set\s+to\s+)?|default\s*:\s*|"
    r"by\s+default,?\s+(?:this\s+|it\s+)?is\s+(?:set\s+to\s+)?)")
BARE = re.compile(r"^(true|false|null|" + NUM + r")\b(?![-\w])", re.I)


def _literal_after(s: str, pos: int):
    """Literal logo depois de pos: `x` (até 2 palavras antes) ou true/false/null/número solto."""
    rest = s[pos:]
    m = re.match(r"^(?:set\s+to\s+|to\s+)?(?:the\s+value\s+)?`([^`]*)`", rest)
    if m:
        return m.group(1), True
    m = BARE.match(rest)
    if m:
        return m.group(1), True
    return None, False


def typed(lit: str, tf_type):
    """Literal tipado pelo tf_type do átomo; None quando não cabe (ex.: texto num atributo numérico)."""
    t = tf_type if isinstance(tf_type, str) else None
    low = lit.strip().lower()
    if t == "bool":
        return {"true": True, "false": False}.get(low.rstrip("."))
    if t == "number":
        x = lit.strip().rstrip(".").replace(",", "")
        try:
            return int(x)
        except ValueError:
            try:
                return float(x)
            except ValueError:
                return None
    if low == "null":
        return None
    return lit


# ---------------------------------------------------------------------------------------- allowed
ENUM = re.compile(
    r"(?i)\b(?:(?:the\s+)?(?:only\s+)?(?:possible|valid|allowed|accepted|supported|permitted|available)\s+"
    r"(?:values?|options?|inputs?)(?:\s+(?:for\s+this\s+(?:field|property)\s+)?(?:are|is|include|includes|"
    r"can\s+be|must\s+be))?\s*:?|(?:must|can|should|may)\s+be\s+(?:set\s+to\s+)?(?:either|one\s+of(?:\s+the\s+following)?)"
    r"(?:\s+values?)?\s*:?)")
ENUM_STOP = re.compile(r"(?i)\b(?:when|if|unless|defaults?\s+to|default\s+value|changing\s+this|note)\b")
RANGEISH = re.compile(r"(?i)^\s*(?:are\s+|is\s+)?(?:between|range|from|in\s+the\s+range|any\s+(?:number|integer|value))")

# ------------------------------------------------------------------------------------------- range
RANGE2 = [
    re.compile(r"(?i)\bbetween\s+`?(" + NUM + r")`?\s*(?:\(inclusive\)\s*)?(?:and|to|-)\s+`?(" + NUM + r")`?"),
    re.compile(r"(?i)\bfrom\s+`?(" + NUM + r")`?\s+(?:to|through|-)\s+`?(" + NUM + r")`?"),
    re.compile(r"(?i)\bin\s+the\s+range\s+(?:of\s+)?`?(" + NUM + r")`?\s*(?:to|-|and)\s*`?(" + NUM + r")`?"),
    re.compile(r"(?i)\brange\s+(?:is\s+|between\s+)?`?(" + NUM + r")`?\s*(?:-|to)\s*`?(" + NUM + r")`?"),
]
RANGE_MIN = re.compile(r"(?i)\b(?:at\s+least|minimum\s+(?:value\s+)?(?:of|is)|greater\s+than\s+or\s+equal\s+to|"
                       r"no\s+less\s+than|must\s+be\s+>=)\s+`?(" + NUM + r")`?")
RANGE_MIN_X = re.compile(r"(?i)\b(?:must\s+be\s+)?(?:greater|larger|more)\s+than\s+`?(" + NUM + r")`?")
RANGE_MAX = re.compile(r"(?i)\b(?:at\s+most|maximum\s+(?:value\s+)?(?:of|is)|up\s+to|less\s+than\s+or\s+equal\s+to|"
                       r"no\s+more\s+than|cannot\s+exceed|must\s+not\s+exceed|must\s+be\s+<=)\s+`?(" + NUM + r")`?")
LENGTH = re.compile(r"(?i)\bcharacters?\b|\blength\b|\blong\b")
ITEMS = re.compile(r"(?i)\b(?:items?|entries|elements|values\s+in\s+the\s+list)\b|`?\d+`?\s+values\b")


def _num(x: str):
    x = x.replace(",", "")
    try:
        return int(x)
    except ValueError:
        return float(x)


# -------------------------------------------------------------------------------------------- unit
UNITS = {
    "millisecond": "millisecond", "milliseconds": "millisecond", "ms": "millisecond",
    "second": "second", "seconds": "second", "sec": "second", "secs": "second",
    "minute": "minute", "minutes": "minute", "min": "minute", "mins": "minute",
    "hour": "hour", "hours": "hour", "day": "day", "days": "day", "week": "week", "weeks": "week",
    "month": "month", "months": "month", "year": "year", "years": "year",
    "byte": "byte", "bytes": "byte", "kilobyte": "kilobyte", "kilobytes": "kilobyte", "kb": "kilobyte",
    "kib": "kibibyte", "megabyte": "megabyte", "megabytes": "megabyte", "mb": "megabyte", "mib": "mebibyte",
    "gigabyte": "gigabyte", "gigabytes": "gigabyte", "gb": "gigabyte", "gib": "gibibyte",
    "terabyte": "terabyte", "terabytes": "terabyte", "tb": "terabyte", "tib": "tebibyte",
    "percent": "percent", "percentage": "percent", "%": "percent",
    "mbps": "megabit_per_second", "gbps": "gigabit_per_second", "iops": "io_operation_per_second",
}
UW = (r"(milliseconds?|ms|seconds?|secs?|minutes?|mins?|hours?|days?|weeks?|months?|years?|bytes?|kilobytes?|"
      r"KB|KiB|megabytes?|MB|MiB|gigabytes?|GB|GiB|terabytes?|TB|TiB|percent(?:age)?|Mbps|Gbps|IOPS)")
UNIT_TEXT = [
    re.compile(r"\b[Ii]n\s+(?:units\s+of\s+|the\s+unit\s+of\s+)?" + UW + r"\b"),
    re.compile(r"\b[Nn]umber\s+of\s+" + UW + r"\b"),
    re.compile(r"(?i:\bbetween)\s+`?" + NUM + r"`?\s+(?i:and|to)\s+`?" + NUM + r"`?\s*" + UW + r"\b"),
    re.compile(r"`" + NUM + r"`\s*" + UW + r"\b"),
    re.compile(r"\b[Pp]ercentage\b()"),
    re.compile(r"\(" + UW + r"\)"),
]
NAME_UNIT = [
    (re.compile(r"(?:^|_)(?:in_)?(milliseconds|ms)$"), "millisecond"),
    (re.compile(r"(?:^|_)(?:in_)?(seconds|secs?)$"), "second"),
    (re.compile(r"(?:^|_)(minutes|in_mins?)$"), "minute"),
    (re.compile(r"(?:^|_)(hours|in_hour)$"), "hour"),
    (re.compile(r"(?:^|_)(days|in_day)$"), "day"),
    (re.compile(r"(?:^|_)(weeks|in_week)$"), "week"),
    (re.compile(r"(?:^|_)(months|in_month)$"), "month"),
    (re.compile(r"(?:^|_)(years|in_year)$"), "year"),
    (re.compile(r"(?:^|_)(?:in_)?(bytes)$"), "byte"),
    (re.compile(r"(?:^|_)(?:in_)?(kb)$"), "kilobyte"),
    (re.compile(r"(?:^|_)(?:in_)?(mb|mbs)$"), "megabyte"),
    (re.compile(r"(?:^|_)(?:in_)?(gb|gbs)$"), "gigabyte"),
    (re.compile(r"(?:^|_)(?:in_)?(tb|tbs)$"), "terabyte"),
    (re.compile(r"(?:^|_)(?:in_)?(percent|percentage)$"), "percent"),
    (re.compile(r"(?:^|_)(?:in_)?(mbps)$"), "megabit_per_second"),
    (re.compile(r"(?:^|_)(?:in_)?(iops)$"), "io_operation_per_second"),
]
# posição de calendário ou de relógio ('day_of_week', 'start_hour', 'hours_of_day'), não grandeza
NAME_NOT_UNIT = re.compile(r"(?:^|_)of_|_of$|(?:^|_)(?:start|starting|end|ending|scan)_")


def is_numeric(tf_type) -> bool:
    if tf_type == "number":
        return True
    return isinstance(tf_type, list) and len(tf_type) == 2 and tf_type[0] in ("list", "set") and tf_type[1] == "number"


def name_unit(name: str):
    if NAME_NOT_UNIT.search(name):
        return None
    for rx, u in NAME_UNIT:
        m = rx.search(name)
        if m:
            return u, m.group(1)
    return None


# ------------------------------------------------------------------------------------------ format
FORMATS = [
    (re.compile(r"(?i)\bISO[- ]?8601\b[^.]{0,40}\bduration\b|\bduration\b[^.]{0,40}\bISO[- ]?8601\b"), "ISO8601_duration"),
    (re.compile(r"(?i)\bISO[- ]?8601\b"), "ISO8601"),
    (re.compile(r"(?i)\bRFC[- ]?3339\b"), "RFC3339"),
    (re.compile(r"\bCIDR\b"), "CIDR"),
    (re.compile(r"(?i)\bbase[- ]?64\b"), "base64"),
    (re.compile(r"\bJSON\b"), "JSON"),
    (re.compile(r"\b(?:UUID|GUID)\b"), "UUID"),
    (re.compile(r"\bHH:MM(?::SS)?\b"), "HH:MM"),
    (re.compile(r"(?i)\bcron\b"), "cron"),
]

FORCES = re.compile(r"(?i)\bchanging\s+(?:this|the\s+`?[\w.]+`?|these|any\s+of\s+these)\b[^.]{0,80}?\bforces?\s+(?:a\s+)?new\b")
DEPREC = re.compile(r"(?i)\b(?:is|are|has\s+been|have\s+been|will\s+be|being)\s+deprecated\b|"
                    r"\bdeprecated\s+in\s+favou?r\b|\bwill\s+be\s+removed\s+in\b")
REMOVED_IN = re.compile(r"(?i)\bremoved\s+in\s+(?:version\s+|v)?(\d+\.\d+(?:\.\d+)?)")
REPLACED = re.compile(r"(?i)\b(?:in\s+favou?r\s+of|use|superseded\s+by|replaced\s+by)\s+(?:the\s+)?`([^`]+)`")
CONFLICT = re.compile(r"(?i)\bconflicts?\s+with\b|\bcannot\s+be\s+(?:specified|set|used|configured|defined)\s+"
                      r"(?:together\s+)?(?:with|alongside|at\s+the\s+same\s+time\s+as)\b|\bmutually\s+exclusive\b|"
                      r"\bonly\s+one\s+of\b|\bcan(?:not|'t)\s+be\s+used\s+in\s+conjunction\s+with\b")
REQ_WHEN = re.compile(r"(?i)\b(?:is\s+|are\s+)?required\s+(?:when|if)\b|\bmust\s+be\s+(?:specified|set|provided|"
                      r"configured|defined)\s+(?:when|if)\b")
EXAMPLE = re.compile(r"(?i)\b(?:e\.g\.?|for\s+example|such\s+as)\s*[,:]?\s*")


def extract(text: str, atom: dict, siblings: set, *, timeouts: bool = False) -> list[dict]:
    """Fatos candidatos de um texto (item ou nota) para um átomo. Cada um: kind, status, value|reason, off,
    method, level."""
    out = []
    name = atom["path"].rsplit(".", 1)[-1]
    tf = atom["tf_type"]
    numeric = is_numeric(tf)
    sents = sentences(text)
    defaults = []
    units_pub = []
    for off, s in sents:
        # default ---------------------------------------------------------------------------------
        if timeouts:
            m = re.search(r"\((?:Defaults?\s+to\s+)([^)]+)\)", s)
            if m:
                defaults.append((off, s, m.group(1).strip(), True))
        else:
            for m in DEFAULT.finditer(s):
                lit, ok = _literal_after(s, m.end())
                defaults.append((off, s, lit, ok))
        # allowed_values ---------------------------------------------------------------------------
        for m in ENUM.finditer(s):
            rest = s[m.end():]
            if RANGEISH.match(rest):
                continue
            stop = ENUM_STOP.search(rest)
            seg = rest[:stop.start()] if stop else rest
            vals = []
            for v in TICKS.findall(seg):
                if v and v not in vals:
                    vals.append(v)
            if vals:
                out.append(dict(kind="allowed_values", status="stated", value=vals, off=off, s=s,
                                method="regex", level="published"))
                break
        # range -----------------------------------------------------------------------------------
        rng = None
        for rx in RANGE2:
            m = rx.search(s)
            if m:
                lo, hi = _num(m.group(1)), _num(m.group(2))
                if lo <= hi:
                    rng = {"min": lo, "max": hi}
                break
        if rng is None:
            mn, mx = RANGE_MIN.search(s), RANGE_MAX.search(s)
            if mn or mx:
                rng = {}
                if mn:
                    rng["min"] = _num(mn.group(1))
                if mx:
                    rng["max"] = _num(mx.group(1))
            else:
                mx2 = RANGE_MIN_X.search(s)
                if mx2:
                    rng = {"min": _num(mx2.group(1)), "min_exclusive": True}
        if rng:
            rng["applies_to"] = "length" if LENGTH.search(s) else ("items" if ITEMS.search(s) else "value")
            out.append(dict(kind="range", status="stated", value=rng, off=off, s=s, method="regex",
                            level="published"))
        # unit (publicada) --------------------------------------------------------------------------
        if numeric:
            for rx in UNIT_TEXT:
                for m in rx.finditer(s):
                    lit = m.group(1) or "percentage"
                    u = UNITS.get(lit.lower()) if lit not in ("MB", "GB", "KB", "TB") else UNITS[lit.lower()]
                    if lit.lower() in ("ms", "min", "mins") and lit != lit.lower():
                        u = None
                    if u and all(x[0] != u for x in units_pub):
                        units_pub.append((u, lit, off, s))
        # format ----------------------------------------------------------------------------------
        plain = TICKS.sub("``", s)        # palavra-chave dentro de crase é valor (ex.: enum `JSON`), não formato
        for rx, f in FORMATS:
            if rx.search(plain):
                out.append(dict(kind="format", status="stated", value=f, off=off, s=s, method="regex",
                                level="published"))
                break
        # forces_replacement ----------------------------------------------------------------------
        if FORCES.search(s):
            out.append(dict(kind="forces_replacement", status="stated", value=True, off=off, s=s,
                            method="regex", level="published"))
        # deprecation -----------------------------------------------------------------------------
        dm = DEPREC.search(s)
        if dm:
            head = TICKS.findall(s[:dm.start()])
            if any((t in siblings or re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", t)) and t != name for t in head):
                dm = None                                   # a frase deprecia outro atributo
            elif [t for t in head if t != name]:
                v = {"deprecated": True, "scope": "values", "values": [t for t in head if t != name]}
            else:
                v = {"deprecated": True, "scope": "attribute"}
        if dm:
            r = REMOVED_IN.search(s)
            if r:
                v["removed_in"] = r.group(1)
            r = REPLACED.search(s)
            if r and r.group(1) != name:
                v["replaced_by"] = r.group(1)
            out.append(dict(kind="deprecation", status="stated", value=v, off=off, s=s, method="regex",
                            level="published"))
        # conflicts_with --------------------------------------------------------------------------
        if CONFLICT.search(s):
            others = sorted({t for t in TICKS.findall(s) if t in siblings and t != name})
            if others:
                out.append(dict(kind="conflicts_with", status="stated", value=others, off=off, s=s,
                                method="regex", level="published"))
        # required_when ---------------------------------------------------------------------------
        m = REQ_WHEN.search(s)
        if m:
            cond = s[m.start():].rstrip(". ")
            out.append(dict(kind="required_when", status="stated", value=cond, off=off, s=s,
                            method="regex", level="published"))
        # example ---------------------------------------------------------------------------------
        for m in EXAMPLE.finditer(s):
            seg = s[m.end():m.end() + 120]
            vals = []
            for v in re.findall(r"^`([^`]+)`|(?<=[\s,(])`([^`]+)`", seg)[:6]:
                v = v[0] or v[1]
                if not v or v in siblings or "[" in v or "${" in v:
                    continue
                if v not in vals:
                    vals.append(v)
            if vals and seg.lstrip().startswith("`"):
                out.append(dict(kind="example", status="stated", value=vals, off=off, s=s, method="regex",
                                level="published"))
                break
    # default: literal único tipado; senão unknown com a frase --------------------------------------
    if defaults:
        lits = []
        for off, s, lit, ok in defaults:
            if not ok:
                continue
            v = lit if timeouts else typed(lit, tf)
            if v is None and not timeouts:
                lits.append(("__untyped__", off, s))
            elif all(x[0] != v or type(x[0]) is not type(v) for x in lits):
                lits.append((v, off, s))
        good = [x for x in lits if x[0] != "__untyped__"]
        if len(good) == 1 and len(lits) == 1:
            v, off, s = good[0]
            out.append(dict(kind="default", status="stated", value=v, off=off, s=s, method="regex",
                            level="published"))
        else:
            off, s = defaults[0][0], defaults[0][1]
            out.append(dict(kind="default", status="unknown", reason="ambiguous", off=off, s=s, method="regex",
                            level="published"))
    # unit: publicada, derivada do nome, conflito ---------------------------------------------------
    if numeric:
        for u, lit, off, s in units_pub:
            out.append(dict(kind="unit", status="stated", value={"unit": u, "literal": lit}, off=off, s=s,
                            method="regex", level="published"))
        nu = name_unit(name)
        if nu:
            off, s = sents[0] if sents else (0, text)
            out.append(dict(kind="unit", status="stated", value={"unit": nu[0], "literal": nu[1], "from": "name"},
                            off=off, s=s, method="regex", level="derived"))
        if len({u for u, *_ in units_pub}) > 1:
            off, s = units_pub[0][2], units_pub[0][3]
            out.append(dict(kind="unit", status="unknown", reason="contradictory", off=off, s=s, method="regex",
                            level="published"))
    return out
