"""Sinais textuais de um item da documentação -> candidatos a fato (C03), cada um com a sentença de origem.

Dois lugares de onde sai fato:
  * o parêntese de abertura do item '(Optional, Forces new resource, Default `x`)': extraction_method=parser
  * as sentenças do texto do item: extraction_method=regex
Nada é inferido: o valor sai literal do texto (tipado pelo tf_type do átomo quando é número ou booleano);
o que o texto diz de forma não literal (ex.: 'Defaults to the Region set in the provider configuration') vira
default descrito {"described": texto}. Cláusula de valores válidos sem valor legível vira unknown/ambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TICK = re.compile(r"`([^`]*)`")
NUM = r"-?\d[\d,]*(?:\.\d+)?"

ABBREV = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "Ex.", "ex.", "No.", "U.S.", "a.m.", "p.m.")


@dataclass
class Cue:
    kind: str            # fact_kind do C03
    value: object        # valor (None quando unknown)
    sentence: str        # sentença literal de origem
    method: str          # parser | regex
    unknown: str | None = None   # unknown_reason quando não há valor legível


def split_paren(text: str) -> tuple[str | None, str]:
    """'(Optional, Default `x`) Resto.' -> ('Optional, Default `x`', 'Resto.'). Respeita crases e aninhamento."""
    t = text.lstrip()
    if not t.startswith("("):
        return None, t
    depth, in_tick = 0, False
    for i, ch in enumerate(t):
        if ch == "`":
            in_tick = not in_tick
        elif not in_tick and ch == "(":
            depth += 1
        elif not in_tick and ch == ")":
            depth -= 1
            if depth == 0:
                return t[1:i], t[i + 1:].lstrip(" .,:;-")
    return None, t


def split_top(s: str, sep: str = ",") -> list[str]:
    out, cur, in_tick, depth = [], [], False, 0
    for ch in s:
        if ch == "`":
            in_tick = not in_tick
        elif not in_tick and ch in "([":
            depth += 1
        elif not in_tick and ch in ")]":
            depth -= 1
        if ch == sep and not in_tick and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def sentences(text: str) -> list[str]:
    """Divide em sentenças sem quebrar crases, abreviações nem números decimais."""
    prot = text
    marks = {}
    for k, a in enumerate(ABBREV):
        tok = f"\x00A{k}\x00"
        if a in prot:
            prot = prot.replace(a, tok)
            marks[tok] = a
    ticks = {}

    def _t(m):
        tok = f"\x00T{len(ticks)}\x00"
        ticks[tok] = m.group(0)
        return tok
    prot = TICK.sub(_t, prot)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\x00(\[*~_])", prot)
    out = []
    for p in parts:
        for tok, v in ticks.items():
            p = p.replace(tok, v)
        for tok, v in marks.items():
            p = p.replace(tok, v)
        if p.strip():
            out.append(p.strip())
    return out


def _sentence_end(s: str) -> str:
    return s.rstrip().rstrip(".").rstrip()


# ---------------------------------------------------------------- tipagem do literal

def typed(lit: str, tf_type):
    v = lit.strip()
    if tf_type == "number":
        if re.fullmatch(r"-?\d+", v.replace(",", "")):
            return int(v.replace(",", ""))
        if re.fullmatch(r"-?\d+\.\d+", v):
            return float(v)
        return v
    if tf_type == "bool":
        if v.lower() in ("true", "false"):
            return v.lower() == "true"
        return v
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _num(s: str):
    s = s.replace(",", "")
    return float(s) if "." in s else int(s)


# ---------------------------------------------------------------- padrões

FORCENEW_FLAG = re.compile(r"^(?:forces?\s+new\s+resources?|forcenew|forces?\s+replacement)$", re.I)
FORCENEW_TEXT = re.compile(
    r"\b(?:forces?\s+(?:a\s+)?new\s+resource|forces?\s+(?:the\s+)?(?:creation\s+of\s+a\s+)?new\s+resource|"
    r"ForceNew|forces?\s+(?:a\s+)?replacement|will\s+(?:cause|trigger|force)\s+(?:a\s+)?(?:resource\s+)?"
    r"(?:recreation|replacement|re-creation)|requires?\s+(?:a\s+)?(?:resource\s+)?replacement)\b", re.I)
DEPRECATED = re.compile(r"\b[Dd]eprecated\b|\*\*Deprecated\*\*")
# na sentença, só conta quando o sujeito é o próprio atributo (não um valor: '`X` (deprecated)', 'SHA-1 hashes
# have been deprecated')
DEPRECATED_SELF = re.compile(
    r"^(?:\*\*)?(?:Deprecated|DEPRECATED)\b|^\(Deprecated\b|^\[Deprecated\]|(?<!`)\s\(Deprecated\b|"
    r"\b(?:This|The)\s+(?:argument|attribute|field|parameter|block|property|option|setting|resource)\s+"
    r"(?:is|has\s+been|was|will\s+be)\s+deprecated\b|"
    r"^(?:This|It)\s+(?:is|has\s+been|was)\s+deprecated\b|"
    r"^(?:Is|Has\s+been)\s+deprecated\b|"
    r"\bis\s+deprecated\s+(?:in\s+favor\s+of|and\s+will\s+be\s+removed|[,;]?\s*use)\b")
DEFAULT_FLAG = re.compile(r"^default(?:s)?(?:\s+(?:value|is|to))?\s*:?\s*(.+)$", re.I)
DEFAULT_TEXT = re.compile(
    r"\b(?:[Dd]efaults?\s+(?:value\s+)?(?:to|is|are|of|value is|:)|[Tt]he\s+default\s+(?:value\s+)?(?:is|of)|"
    r"[Dd]efault:|[Bb]y\s+default,?\s+(?:this\s+)?(?:is|it\s+is|the\s+value\s+is)|[Dd]efault\s+is)\s*:?\s*(.+)")
VALID_TEXT = re.compile(
    r"\b(?:[Vv]alid|[Aa]llowed|[Pp]ossible|[Aa]ccepted|[Ss]upported|[Pp]ermitted)\s+(?:values?|options?|inputs?)"
    r"(?:\s+(?:are|is|include|for\s+this\s+(?:argument|attribute|parameter)\s+are))?\s*(?:\([^)]*\))?\s*:?\s*(.+)")
ONEOF_TEXT = re.compile(r"(?:\b[Mm]ust\s+be\s+(?:one\s+of|either)|\b[Cc]an\s+be\s+(?:one\s+of|either)|"
                        r"\b[Oo]ne\s+of\s+the\s+following(?:\s+values)?|^[Oo]ne\s+of(?=\s*:|\s+`[^`]*`\s*,))"
                        r"\s*:?\s*(.+)")
# 'Only one of `a` or `b` can be specified' é exclusão mútua, não lista de valores
ONEOF_NOT = re.compile(r"\b(?:can|must|should|may)\s+(?:be\s+)?(?:specified|set|provided|configured|used)\b|"
                       r"\bis\s+required\b|\bare\s+required\b", re.I)
BETWEEN = re.compile(r"\bbetween\s+`?(" + NUM + r")`?\s*(?:\(inclusive\)\s*)?(?:and|-|to)\s+`?(" + NUM + r")`?", re.I)
FROM_TO = re.compile(r"\b(?:[Rr]ange|[Vv]alid\s+values?\s+(?:are\s+)?from|[Ff]rom)\s+`?(" + NUM + r")`?\s+(?:to|through)\s+`?(" + NUM + r")`?")
_QUAL = r"(?:\s+(?:supported|allowed|valid|permitted|possible))?"
MIN_TEXT = re.compile(r"\b(?:[Mm]inimum" + _QUAL + r"(?:\s+value)?(?:\s+(?:is|of))?|[Mm]in(?:imum)?\s+value|[Aa]t\s+least|"
                      r"[Mm]ust\s+be\s+(?:greater\s+than\s+or\s+equal\s+to|>=))\s*:?\s*`?(" + NUM + r")`?")
MAX_TEXT = re.compile(r"\b(?:[Mm]aximum" + _QUAL + r"(?:\s+value)?(?:\s+(?:is|of))?|[Mm]ax(?:imum)?\s+value|[Aa]t\s+most|[Uu]p\s+to|"
                      r"[Nn]o\s+more\s+than|[Mm]ust\s+be\s+(?:less\s+than\s+or\s+equal\s+to|<=))\s*:?\s*`?(" + NUM + r")`?")
LENGTH_WORD = re.compile(r"^\s*`?\)?\s*(?:\w+\s+)?(characters?|chars|bytes?\s+long|letters)\b", re.I)
NEXT_WORDS = re.compile(r"^\s*`?\)?\s*([A-Za-z][\w/-]*)(?:\s+([A-Za-z][\w/-]*))?")

UNITS = {
    "second": "second", "seconds": "second", "sec": "second", "secs": "second",
    "minute": "minute", "minutes": "minute", "mins": "minute",
    "hour": "hour", "hours": "hour", "day": "day", "days": "day", "week": "week", "weeks": "week",
    "month": "month", "months": "month", "year": "year", "years": "year",
    "millisecond": "millisecond", "milliseconds": "millisecond", "ms": "millisecond",
    "microsecond": "microsecond", "microseconds": "microsecond",
    "byte": "byte", "bytes": "byte", "kilobytes": "kilobyte", "megabytes": "megabyte",
    "gigabytes": "gigabyte", "terabytes": "terabyte",
    "kb": "KB", "kib": "KiB", "mb": "MB", "mib": "MiB", "gb": "GB", "gib": "GiB", "tb": "TB", "tib": "TiB",
    "percent": "percent", "percentage": "percent", "%": "percent",
    "mbps": "Mbps", "gbps": "Gbps", "mib/s": "MiB/s", "mb/s": "MB/s", "mibps": "MiB/s",
    "iops": "IOPS", "vcpus": "vCPU", "vcpu": "vCPU",
}
_U = r"(seconds?|secs?|minutes?|mins|hours?|days?|weeks?|months?|years?|milliseconds?|ms|microseconds?|bytes?|" \
     r"kilobytes|megabytes|gigabytes|terabytes|KB|KiB|MB|MiB|GB|GiB|TB|TiB|percent(?:age)?|Mbps|Gbps|MiB/s|MB/s|" \
     r"MiBps|IOPS|vCPUs?)"
UNIT_PATTERNS = [
    re.compile(r"\b[Ii]n\s+(?:the\s+)?(?:number\s+of\s+)?(?:whole\s+)?" + _U + r"\b"),
    re.compile(r"\(\s*(?:in\s+)?" + _U + r"\s*\)"),
    re.compile(r"\b(?:[Nn]umber|[Aa]mount|[Dd]uration|[Ll]ength|[Ss]ize|[Pp]eriod|[Ii]nterval|[Tt]ime|[Qq]uantity|"
               r"[Cc]ount)\s+of\s+" + _U + r"\b"),
    re.compile(r"\b(?:measured|specified|expressed|given)\s+in\s+" + _U + r"\b"),
    re.compile(r"\b[Uu]nits?\s+(?:is|are|:)\s*`?" + _U + r"\b"),
    re.compile(r"\b" + NUM + r"\s*(?:\(inclusive\)\s*)?" + _U + r"\b(?![-/])"),
]
FORMATS = [
    ("ARN", re.compile(r"^(?:The\s+|An?\s+)?(?:Amazon\s+Resource\s+Name\s+\(ARN\)|ARN)s?\b(?!\s+format\s+of)")),
    ("ARN", re.compile(r"\b(?:Amazon\s+Resource\s+Name|ARN)s?\s+(?:of|for)\s+the\b.*$", re.I)),
    ("CIDR", re.compile(r"\bCIDR\b")),
    ("RFC3339", re.compile(r"\bRFC\s?3339\b", re.I)),
    ("ISO8601", re.compile(r"\bISO[\s-]?8601\b", re.I)),
    ("JSON", re.compile(r"\bJSON(?:[- ](?:formatted|encoded|string|document))?\b|\bjsonencode\b")),
    ("base64", re.compile(r"\bbase64\b|\bbase-64\b", re.I)),
    ("cron", re.compile(r"\bcron\b", re.I)),
    ("UTC timestamp", re.compile(r"\bUTC\b")),
    ("IPv4", re.compile(r"\bIPv4\s+address", re.I)),
    ("IPv6", re.compile(r"\bIPv6\s+address", re.I)),
    ("regex", re.compile(r"\bregular\s+expression\b|\bregex\b", re.I)),
]
CONFLICTS = re.compile(r"\b(?:[Cc]onflicts\s+with|[Cc]annot\s+be\s+(?:used|specified|set)\s+(?:together\s+)?with|"
                       r"[Mm]utually\s+exclusive\s+with)\s+(.+)")
REQUIRED_WHEN = re.compile(r"^(?:[Rr]equired\s+(?:if|when|unless|for|only\s+(?:if|when))\b.*)$")
REQUIRED_WHEN_TEXT = re.compile(r"\b[Rr]equired\s+(?:if|when|unless|only\s+(?:if|when))\b.+")


def _values_from_clause(clause: str) -> list[str] | None:
    """Valores de uma cláusula de valores válidos. Crases mandam; sem crase, só lista de palavras simples."""
    body = clause
    cut = re.search(r"\.\s|\.$|;\s|\s-\s", body)
    if cut:
        body = body[: cut.start()]
    ticks = [t for t in TICK.findall(body) if t.strip() != ""]
    if len(ticks) == 1 and " | " in ticks[0]:
        ticks = [x.strip() for x in ticks[0].split(" | ") if x.strip()]   # '`add | start`'
    if ticks:
        return ticks
    body = re.sub(r"\s+(?:or|and)\s+", ", ", body.strip().rstrip("."))
    parts = [p.strip().strip('"').strip("'") for p in body.split(",") if p.strip()]
    if len(parts) >= 2 and all(re.fullmatch(r"[A-Za-z0-9_.:/+*-]{1,64}", p) for p in parts):
        return parts
    return None


def range_of(after: str) -> str:
    """'value' | 'length' | 'count' pelo que vem depois do número ('... 255 characters', '... 20 entries')."""
    if LENGTH_WORD.match(after):
        return "length"
    m = NEXT_WORDS.match(after)
    if m:
        words = [w for w in m.groups() if w]
        if any(w.lower() in UNITS or w.lower().rstrip("s") in UNITS for w in words):
            return "value"
        if words[0].lower() in ("and", "or", "to", "inclusive", "if", "for", "when", "the", "is", "are", "per",
                                "in", "of", "with", "but", "then", "otherwise", "except"):
            return "value"
        if any(re.fullmatch(r"[a-z][a-z-]*[^s]s", w) for w in words):
            return "count"
    return "value"


def flag_cues(paren: str, tf_type) -> tuple[list[Cue], list[str]]:
    """Fatos do parêntese de abertura; devolve também as marcas não usadas (para auditoria)."""
    out, rest = [], []
    for tok in split_top(paren):
        t = tok.strip()
        tl = t.lower().strip("*").strip().rstrip(":").strip("*").strip()
        if not t:
            continue
        if tl in ("required", "optional", "computed", "read-only", "readonly", "sensitive", "write-only"):
            continue
        if FORCENEW_FLAG.match(tl) or re.fullmatch(r"forces? new resources?", tl):
            out.append(Cue("forces_replacement", True, t, "parser"))
            continue
        if tl in ("deprecated",) or DEPRECATED.fullmatch(t.strip()):
            out.append(Cue("deprecation", True, t, "parser"))
            continue
        m = re.match(r"^required\s*-\s*forces new resources?$", tl)
        if m:
            out.append(Cue("forces_replacement", True, t, "parser"))
            continue
        d = DEFAULT_FLAG.match(t)
        if d and tl.startswith("default"):
            lit = d.group(1).strip()
            tk = TICK.fullmatch(lit)
            if tk:
                out.append(Cue("default", typed(tk.group(1), tf_type), t, "parser"))
            elif re.fullmatch(r"-?\d+(?:\.\d+)?|true|false", lit, re.I):
                out.append(Cue("default", typed(lit, tf_type), t, "parser"))
            else:
                out.append(Cue("default", {"described": lit}, t, "parser"))
            continue
        if REQUIRED_WHEN.match(t):
            out.append(Cue("required_when", t, t, "parser"))
            continue
        c = CONFLICTS.search(t)
        if c:
            names = TICK.findall(c.group(1))
            if names:
                out.append(Cue("conflicts_with", names, t, "parser"))
                continue
        rest.append(t)
    return out, rest


def text_cues(text: str, tf_type) -> list[Cue]:
    out: list[Cue] = []
    primary: list[Cue] = []
    secondary: list[Cue] = []
    sents = sentences(text)
    for k, s in enumerate(sents):
        if FORCENEW_TEXT.search(s):
            out.append(Cue("forces_replacement", True, s, "regex"))
        if DEPRECATED_SELF.search(s) and not re.search(r"`[^`]*`\s+(?:is|are|has\s+been)\s+deprecated", s):
            out.append(Cue("deprecation", True, s, "regex"))
        d = DEFAULT_TEXT.search(s)
        if d:
            lit = d.group(1).strip()
            tk = re.match(r"^`([^`]*)`(?=[\s.,;)]|$)", lit)
            if tk:
                out.append(Cue("default", typed(tk.group(1), tf_type), s, "regex"))
            else:
                m = re.match(r"^(-?\d+(?:\.\d+)?|true|false)(?=[\s.,;)]|$)", lit, re.I)
                withunit = re.match(r"^(-?\d+(?:\.\d+)?)\s*(?:" + _U[1:-1] + r"|characters?)\b", lit)
                if withunit:
                    # número com unidade ('The default is 256 MiB'): a unidade do atributo não é conhecida
                    # aqui, então o default fica descrito, sem converter
                    out.append(Cue("default", {"described": withunit.group(0)}, s, "regex"))
                elif m:
                    out.append(Cue("default", typed(m.group(1), tf_type), s, "regex"))
                else:
                    out.append(Cue("default", {"described": _sentence_end(lit)}, s, "regex"))
        v = VALID_TEXT.search(s) or (ONEOF_TEXT.search(s) if not ONEOF_NOT.search(s) else None)
        if v:
            clause = v.group(1)
            if (BETWEEN.search(clause) or (FROM_TO.search(clause) and not TICK.search(clause.split(" ")[0]))
                    or re.match(r"^`?" + NUM + r"`?\s*(?:" + _U[1:-1] + r")?\s*(?:and|to|-|$|\.)", clause.strip())):
                pass   # faixa ou limite, tratado abaixo
            else:
                vals = _values_from_clause(clause)
                if vals is None and k + 1 < len(sents) and not clause.strip().rstrip(":").strip():
                    vals = _values_from_clause(sents[k + 1])
                if vals:
                    out.append(Cue("allowed_values", [typed(x, tf_type) for x in vals], s, "regex"))
                elif VALID_TEXT.search(s):
                    out.append(Cue("allowed_values", None, s, "regex", unknown="ambiguous"))
        rng = {}
        b = BETWEEN.search(s) or FROM_TO.search(s)
        if b:
            rng = {"min": _num(b.group(1)), "max": _num(b.group(2))}
            after = s[b.end():]
        else:
            mn, mx = MIN_TEXT.search(s), MAX_TEXT.search(s)
            if mn:
                rng["min"] = _num(mn.group(1))
                after = s[mn.end():]
            if mx:
                rng["max"] = _num(mx.group(1))
                after = s[mx.end():]
        if rng:
            rng["of"] = range_of(after)
            if rng["of"] == "value" and re.search(r"\b(?:length|characters?|long)\b", s, re.I):
                rng["of"] = "length"
            if "min" in rng and "max" in rng and rng["min"] > rng["max"]:
                out.append(Cue("range", None, s, "regex", unknown="contradictory"))
            else:
                out.append(Cue("range", rng, s, "regex"))
        for u in _units(s, UNIT_PATTERNS[:-1]):
            primary.append(Cue("unit", u, s, "regex"))
        if rng or d or v:
            for u in _units(s, UNIT_PATTERNS[-1:]):
                secondary.append(Cue("unit", u, s, "regex"))
        fmts = []
        for name, rx in FORMATS:
            if name == "ARN" and k > 0:
                continue
            if rx.search(s) and name not in fmts:
                fmts.append(name)
        for f in fmts:
            out.append(Cue("format", f, s, "regex"))
        c = CONFLICTS.search(s)
        if c:
            names = TICK.findall(c.group(1).split(". ")[0])
            if names:
                out.append(Cue("conflicts_with", names, s, "regex"))
        r = REQUIRED_WHEN_TEXT.search(s)
        if r:
            out.append(Cue("required_when", _sentence_end(r.group(0)), s, "regex"))
    # unidade: a forma explícita ('in seconds', '(in GiB)', 'Number of days') manda; número+unidade só conta em
    # sentença de default/faixa/valores e só quando o item não tem a forma explícita
    out.extend(primary if primary else secondary)
    return out


def _units(s: str, patterns) -> list[str]:
    units = []
    for rx in patterns:
        for m in rx.finditer(s):
            u = UNITS.get(m.group(1).lower()) or UNITS.get(m.group(1).lower().rstrip("s"))
            if u and u not in units:
                units.append(u)
    return units
