"""Regras de extração: um item de documentação (parse.Item) + o átomo do schema -> fatos C03 crus.

Cada regra devolve fatos com a linha e a sentença de origem, o método (parser = estrutura da página:
marcadores e itens; regex = padrão lexical no texto) e o nível de evidência (published = dito na página;
derived = deduzido de outra coisa dita, ex.: ausência de '(Updatable)' + nota da página -> ForceNew).
Gatilho achado sem valor literal legível vira status=unknown, unknown_reason=ambiguous (nunca valor
inventado); valores diferentes do mesmo tipo de fato no mesmo átomo viram unknown/contradictory.
"""

from __future__ import annotations

import re

NUM = r"-?\d[\d,]*(?:\.\d+)?"

# ------------------------------------------------------------------ unidades
UNIT_WORDS = {
    "second": "s", "seconds": "s", "sec": "s", "secs": "s",
    "millisecond": "ms", "milliseconds": "ms", "ms": "ms", "millis": "ms",
    "microsecond": "us", "microseconds": "us",
    "nanosecond": "ns", "nanoseconds": "ns",
    "minute": "min", "minutes": "min", "mins": "min",
    "hour": "h", "hours": "h", "hrs": "h",
    "day": "d", "days": "d",
    "week": "wk", "weeks": "wk",
    "month": "mo", "months": "mo",
    "year": "yr", "years": "yr",
    "byte": "B", "bytes": "B",
    "kb": "KB", "kbs": "KB", "kilobyte": "KB", "kilobytes": "KB",
    "mb": "MB", "mbs": "MB", "megabyte": "MB", "megabytes": "MB",
    "gb": "GB", "gbs": "GB", "gigabyte": "GB", "gigabytes": "GB",
    "tb": "TB", "tbs": "TB", "terabyte": "TB", "terabytes": "TB",
    "pb": "PB", "pbs": "PB",
    "kib": "KiB", "mib": "MiB", "gib": "GiB", "tib": "TiB",
    "kibs": "KiB", "mibs": "MiB", "gibs": "GiB", "tibs": "TiB",
    "kbps": "Kbps", "mbps": "Mbps", "gbps": "Gbps",
    "percent": "%", "percentage": "%", "percentages": "%",
    "ocpu": "OCPU", "ocpus": "OCPU", "ecpu": "ECPU", "ecpus": "ECPU",
    "iops": "IOPS",
}
_UW = "|".join(sorted((re.escape(k) for k in UNIT_WORDS), key=len, reverse=True))
UNIT_PATTERNS = [
    re.compile(rf"\b[Ii]n[ \t]+(?:units[ \t]+of[ \t]+)?(?:the[ \t]+)?(?P<u>{_UW})\b", re.I),
    re.compile(rf"\((?:in[ \t]+)?(?P<u>{_UW})\)", re.I),
    re.compile(rf"\b[Uu]nits?(?:[ \t]+is|[ \t]+are|:)[ \t]*`?(?P<u>{_UW})\b", re.I),
    re.compile(r"\b[Nn]umber[ \t]+of[ \t]+(?P<u>seconds|minutes|hours|days|milliseconds|bytes|OCPUs|ECPUs)\b"),
]
# sufixo do nome do atributo: size_in_gbs, timeout_in_seconds, ...
NAME_UNIT = re.compile(r"_in_(?P<u>[a-z]+)$")
NAME_UNIT_OK = {"gbs", "seconds", "minutes", "days", "tbs", "mins", "mbs", "gb", "hours", "bytes", "millis",
                "weeks", "ms", "milliseconds", "kbs", "mbps", "sec", "secs", "gbps", "percent", "hrs", "years",
                "gigabytes", "mb", "kb", "kilobytes"}

# ------------------------------------------------------------------ default
VAL = (r"(?:`(?P<bt>[^`]+)`|'(?P<sq>[^']+)'|\"(?P<dq>[^\"]+)\"|"
       rf"(?P<num>{NUM}(?![\w./:])(?:[ \t]+(?:{_UW})\b)?)|"
       r"(?P<tok>\b(?:[A-Z][A-Z0-9_]+|true|false|True|False|TRUE|FALSE|null|NULL)\b))")
DEFAULT_TRIGGERS = [
    re.compile(r"\b(?:[Dd]efault(?:[ \t]+[Vv]alue)?(?:[ \t]+is|[ \t]*:|[ \t]*=)|[Dd]efaults[ \t]+to)[ \t]+"),
    re.compile(r"\b[Tt]he[ \t]+default(?:[ \t]+value)?[ \t]+(?:is|will[ \t]+be)[ \t]+"),
    re.compile(r"\b[Ii]f[ \t]+not[ \t]+(?:specified|provided|set)\b[^.]{0,40}?,[ \t]*(?:the[ \t]+)?(?:value[ \t]+|it[ \t]+)?"
               r"(?:defaults[ \t]+to|is[ \t]+set[ \t]+to|will[ \t]+be(?:[ \t]+set[ \t]+to)?)[ \t]+"),
]
VAL_RE = re.compile(VAL)

# ------------------------------------------------------------------ valores válidos
ENUM_TRIGGER = re.compile(
    r"\b(?:(?:[Aa]llowed|[Vv]alid|[Ss]upported|[Pp]ossible|[Aa]ccepted|[Pp]ermitted)[ \t]+values?"
    r"(?:[ \t]+for[ \t]+(?:this[ \t]+(?:field|property|parameter)|`?(?P<for>[A-Za-z_][A-Za-z0-9_]*)`?))?"
    r"(?:[ \t]+(?:are|is|include))?"
    r"|(?:[Mm]ust|[Cc]an|[Ss]hould)[ \t]+be[ \t]+one[ \t]+of(?:[ \t]+(?:the[ \t]+)?(?:following|these)(?:[ \t]+values)?)?"
    r"|[Oo]ne[ \t]+of[ \t]+(?:the[ \t]+)?(?:following|these)[ \t]+values)"
    r"[ \t]*(?:[:\-–][ \t]*)?")
ENUM_TOKEN = re.compile(r"^[A-Za-z0-9_.:/+\-]+$")
LIST_BULLET = re.compile(r"^[ \t]*[*-][ \t]+(?:`(?P<bt>[^`]+)`|'(?P<sq>[^']+)'|\"(?P<dq>[^\"]+)\"|(?P<w>[A-Z0-9_][A-Z0-9_.\-]*)\b)")

# ------------------------------------------------------------------ faixa
# a doc de identity_domains lista as propriedades SCIM++ do campo: '* idcsMinValue: 1' e '* idcsMaxValue: 20'
SCIM_MIN = re.compile(rf"\bidcsMinValue:[ \t]*(?P<a>{NUM})(?!\d|[:.]\d)")
SCIM_MAX = re.compile(rf"\bidcsMaxValue:[ \t]*(?P<b>{NUM})(?!\d|[:.]\d)")
RANGE_PATTERNS = [
    ("both", re.compile(rf"\bbetween[ \t]+(?P<a>{NUM})[ \t]+(?:and|to)[ \t]+(?P<b>{NUM})(?!\d|[:.]\d)")),
    ("both", re.compile(rf"\b(?:range|ranges|ranging|can[ \t]+be|must[ \t]+be|values?[ \t]+(?:is|are))[ \t]+(?:is[ \t]+)?"
                        rf"from[ \t]+(?P<a>{NUM})[ \t]+(?:to|through)[ \t]+(?P<b>{NUM})(?!\d|[:.]\d)")),
    ("both", re.compile(rf"\brange[^.\[]{{0,20}}\[[ \t]*(?P<a>{NUM})[ \t]*,[ \t]*(?P<b>{NUM})[ \t]*\]")),
    ("min", re.compile(rf"\b[Mm]inimum(?:[ \t]+(?:value|length|size|number))?(?:[ \t]+of[ \t]+`?[A-Za-z_][A-Za-z0-9_]*`?(?=[ \t]+is))?(?:[ \t]+is|[ \t]+of|:)?[ \t]+(?P<a>{NUM})(?!\d|[:.]\d)")),
    ("max", re.compile(rf"\b[Mm]aximum(?:[ \t]+(?:value|length|size|number))?(?:[ \t]+of[ \t]+`?[A-Za-z_][A-Za-z0-9_]*`?(?=[ \t]+is))?(?:[ \t]+is|[ \t]+of|:)?[ \t]+(?P<b>{NUM})(?!\d|[:.]\d)")),
    ("min", re.compile(rf"\b(?:at[ \t]+least|no[ \t]+less[ \t]+than|greater[ \t]+than[ \t]+or[ \t]+equal[ \t]+to)[ \t]+(?P<a>{NUM})(?!\d|[:.]\d)")),
    ("min", SCIM_MIN),
    ("max", SCIM_MAX),
    ("max", re.compile(rf"\b(?:at[ \t]+most|no[ \t]+more[ \t]+than|less[ \t]+than[ \t]+or[ \t]+equal[ \t]+to|cannot[ \t]+exceed|"
                       rf"must[ \t]+not[ \t]+exceed|up[ \t]+to[ \t]+a[ \t]+maximum[ \t]+of)[ \t]+(?P<b>{NUM})(?!\d|[:.]\d)")),
]
LENGTH_AFTER = re.compile(r"^[ \t]*(?:\w+[ \t]+){0,1}(?:characters?|chars?)\b", re.I)
LENGTH_BEFORE = re.compile(r"\blength\b|\bcharacters?\b", re.I)

# ------------------------------------------------------------------ formato
FORMATS = [
    ("RFC3339", re.compile(r"\bRFC[ \t-]?3339\b")),
    ("ISO-8601", re.compile(r"\bISO[ \t-]?8601\b")),
    ("CIDR", re.compile(r"\bCIDR[ \t]+(?:notation|format|block[ \t]+format)\b")),
    ("base64", re.compile(r"\bbase[ \t-]?64(?:[ \t-]?encoded)?\b", re.I)),
    ("cron", re.compile(r"\bcron[ \t]+(?:expression|format|syntax|string)\b", re.I)),
    ("IANA-tz", re.compile(r"\bIANA[ \t]+time[ \t]?zone\b|\btz[ \t]+database\b", re.I)),
]
OCID_FMT = re.compile(r"\[OCID\]\(|\bOCIDs?\b")

DEPRECATED = re.compile(r"\*\*Deprecated\b|\(\s*Deprecated\s*\)|^\s*\**Deprecated\b|\b(?:is|are|has[ \t]+been|have[ \t]+been)"
                        r"[ \t]+deprecated\b|\bDEPRECATED\b")
EXAMPLE = re.compile(r"\bExample:[ \t]*`(?P<v>[^`]+)`")
CONFLICT = re.compile(r"\bIt[ \t]+is[ \t]+an[ \t]+error[ \t]+to[ \t]+set[ \t]+both\b|\bmutually[ \t]+exclusive\b|"
                      r"\bcannot[ \t]+be[ \t]+(?:specified|set|used)[ \t]+(?:together[ \t]+)?(?:with|along[ \t]+with)\b|"
                      r"\b[Cc]onflicts[ \t]+with\b")
WHEN = re.compile(r"^(?P<kind>Required|Applicable|Optional)(?P<only>[ \t]+only)?[ \t]+when[ \t]+(?P<cond>.+)$")
COND_EQ = re.compile(r"^(?P<field>[A-Za-z_][A-Za-z0-9_.]*)[ \t]*=[ \t]*(?P<vals>[^=]+)$")

ABBREV = ("e.g.", "i.e.", "etc.", "vs.", "Ex.", "ex.", "approx.", "No.", "Inc.")
SENT_BOUND = re.compile(r"(?<=[.!?])[ \t]+(?=\S)")


def sentence_at(text: str, pos: int) -> str:
    """A sentença do texto (uma linha) que contém a posição pos."""
    starts = [0]
    for m in SENT_BOUND.finditer(text):
        before = text[:m.start()]
        if before.endswith(ABBREV) or re.search(r"\d\.$", before):
            continue
        starts.append(m.end())
    s = 0
    for st in starts:
        if st <= pos:
            s = st
    nxt = [st for st in starts if st > pos]
    e = nxt[0] if nxt else len(text)
    out = text[s:e].strip()
    return out if len(out) >= 5 else text.strip()


def first_sentence(item) -> str:
    """A 1ª sentença da linha do item, crua ('* `nome` - (Optional) (Updatable) Texto.'): origem dos fatos
    que vêm da estrutura do item (descrição, marcadores, unidade pelo nome)."""
    raw = item.raw.strip()
    m = re.match(r"^[*-][ \t]+`[^`]+`[ \t]*-[ \t]?", raw)
    pre = len(m.group(0)) if m else 0
    marks = re.match(r"^(?:[ \t]*\([^()]*(?:\([^()]*\)[^()]*)*\))*", raw[pre:])
    start = pre + (len(marks.group(0)) if marks else 0)
    tail = raw[start:]
    if not tail.strip():
        return raw
    lead = len(tail) - len(tail.lstrip())
    return raw[:start + lead] + sentence_at(tail.lstrip(), 0)


def fact(kind, line, sentence, value=None, status="stated", reason=None, method="regex", evidence="published"):
    f = {"fact_kind": kind, "status": status, "line": line, "sentence": sentence,
         "extraction_method": method, "evidence_level": evidence}
    if status == "stated":
        f["value"] = value
    else:
        f["unknown_reason"] = reason
    return f


def _num(s: str):
    t = s.replace(",", "")
    try:
        return int(t)
    except ValueError:
        return float(t)


def typed(raw: str, tf_type):
    """Literal da doc no tipo do schema quando a conversão é trivial (bool/number); senão o texto."""
    t = raw.strip()
    if tf_type == "bool" and t.lower() in ("true", "false"):
        return t.lower() == "true"
    if tf_type == "number" and re.fullmatch(NUM, t):
        return _num(t)
    return t


def _val(m: re.Match) -> str | None:
    for g in ("bt", "sq", "dq", "num", "tok"):
        if m.group(g) is not None:
            return m.group(g).strip()
    return None


# ------------------------------------------------------------------ regras
def rule_description(item) -> list:
    body = item.body()
    if not body:
        return [fact("description", item.line, first_sentence(item), status="unknown", reason="not_documented",
                     method="parser")]
    return [fact("description", item.line, first_sentence(item), value=body, method="parser")]


def rule_markers(item, atom, page) -> list:
    out = []
    marks = item.markers
    if item.section == "arguments" and atom.get("configurable"):
        upd = [m for m in marks if m.startswith("Updatable")]
        if upd and upd[0] == "Updatable":
            out.append(fact("forces_replacement", item.line, first_sentence(item), value=False, method="parser"))
        elif upd:
            out.append(fact("forces_replacement", item.line, first_sentence(item), status="unknown", reason="ambiguous",
                            method="parser"))
        elif page.important_line is not None:
            out.append(fact("forces_replacement", item.line, first_sentence(item), value=True, method="parser",
                            evidence="derived"))
    for m in marks:
        w = WHEN.match(m)
        if w:
            cond = w.group("cond").strip()
            ce = COND_EQ.match(cond)
            val = ({"field": ce.group("field"), "values": [v.strip() for v in ce.group("vals").split("|") if v.strip()]}
                   if ce else {"condition": cond})
            if w.group("kind") == "Required":
                out.append(fact("required_when", item.line, first_sentence(item), value=val, method="parser"))
            elif w.group("kind") == "Applicable":
                out.append(fact("behavior", item.line, first_sentence(item), value={"applicable_when": val},
                                method="parser"))
            else:
                out.append(fact("behavior", item.line, first_sentence(item), value={"optional_when": val},
                                method="parser"))
        elif m.startswith("Defaults to"):
            v = m[len("Defaults to"):].strip()
            if v:
                out.append(fact("default", item.line, first_sentence(item), value=v, method="parser"))
        elif m.strip("*") == "Deprecated":
            out.append(fact("deprecation", item.line, first_sentence(item), value=True, method="parser"))
    return out


def rule_default(item, atom) -> list:
    out = []
    for n, text in item.lines():
        for trig in DEFAULT_TRIGGERS:
            for m in trig.finditer(text):
                rest = text[m.end():]
                sent = sentence_at(text, m.start())
                v = VAL_RE.match(rest)
                if v:
                    out.append(fact("default", n, sent, value=typed(_val(v), atom.get("tf_type"))))
                else:
                    out.append(fact("default", n, sent, status="unknown", reason="ambiguous"))
    return out


def _enum_inline(rest: str) -> list | None:
    seg = re.split(r"\.(?:[ \t]|$)", rest, maxsplit=1)[0]
    seg = re.sub(r"[ \t]*\([^()]*\)", "", seg)          # explicação entre parênteses de cada valor
    seg = seg.strip().rstrip(".;")
    if not seg:
        return []
    quoted = re.findall(r"`([^`]+)`|'([^']+)'|\"([^\"]+)\"", seg)
    if quoted:
        vals = [a or b or c for a, b, c in quoted]
        leftover = re.sub(r"`[^`]+`|'[^']+'|\"[^\"]+\"", "", seg)
        leftover = re.sub(r"\b(?:and|or)\b|[,;/]|\s", "", leftover)
        return vals if not leftover else None
    pieces = [p.strip() for p in re.split(r",|;|\bor\b|\band\b", seg) if p.strip()]
    if pieces and all(ENUM_TOKEN.match(p) for p in pieces):
        return pieces
    return None


def rule_enum(item, tf_type=None) -> list:
    out = []
    lines = item.lines()
    for i, (n, text) in enumerate(lines):
        for m in ENUM_TRIGGER.finditer(text):
            sent = sentence_at(text, m.start())
            rest = text[m.end():]
            vals = _enum_inline(rest)
            if vals == []:
                # lista nas linhas seguintes: '* `X`', '- X', ...
                vals = []
                for _, t2 in lines[i + 1:]:
                    b = LIST_BULLET.match(t2)
                    if not b:
                        if t2.strip():
                            break
                        continue
                    vals.append(next(g for g in b.groups() if g is not None).strip())
            target = m.group("for")
            if target and snake(target) != item.name:
                # 'Supported values for interval: ...' sob o atributo query: valores de outra coisa
                out.append(fact("allowed_values", n, sent, status="unknown", reason="ambiguous"))
            elif vals and len(set(vals)) == len(vals):
                out.append(fact("allowed_values", n, sent, value=[typed(v, tf_type) for v in vals]))
            else:
                out.append(fact("allowed_values", n, sent, status="unknown", reason="ambiguous"))
    return out


ENUM_LINE = re.compile(r"^[ \t]*[*-][ \t]+(?:`(?P<b>[A-Z][A-Z0-9_]*)`(?:[ \t]*[-:–][ \t]|[ \t]*$)"
                       r"|(?P<v>[A-Z][A-Z0-9_]*)(?:[ \t]+[-–][ \t]|[ \t]*$))")


CAN_BE = re.compile(r"\b(?:[Cc]an|[Mm]ust)[ \t]+be[ \t]+(?:either[ \t]+)?(?=[`'\"A-Z])")
CAPS_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def rule_enum_can_be(item, tf_type=None) -> list:
    """'Can be SENDER or RECEIVER.': gatilho genérico, então só vale com 2+ valores todos em CAIXA ALTA ou
    entre aspas/crases; sem isso, nada (não é marcado ambíguo, porque 'can be' quase sempre é prosa)."""
    out = []
    for n, text in item.lines():
        for m in CAN_BE.finditer(text):
            vals = _enum_inline(text[m.end():])
            if not vals or len(vals) < 2 or len(set(vals)) != len(vals):
                continue
            seg = text[m.end():]
            quoted = bool(re.match(r"[`'\"]", seg))
            if quoted or all(CAPS_TOKEN.match(v) for v in vals):
                out.append(fact("allowed_values", n, sentence_at(text, m.start()),
                                value=[typed(v, tf_type) for v in vals]))
    return out


def rule_enum_list(item) -> list:
    """Lista de valores em CAIXA ALTA logo abaixo do item ('* `NATIVE` - ...'): o conjunto de valores do
    atributo. Fonte: a linha do item, que apresenta a lista; método parser (estrutura da página)."""
    vals, first = [], None
    for n, t in item.cont:
        m = ENUM_LINE.match(t)
        if m:
            vals.append(m.group("b") or m.group("v"))
            first = first or n
        elif vals and t.strip():
            break
    # '(Required when tipo=A | B)' seguido de '* A: ...' e '* B: ...' explica cada variante, não lista valores
    cond_vals = set()
    for mk in item.markers:
        w = WHEN.match(mk)
        ce = COND_EQ.match(w.group("cond").strip()) if w else None
        if ce:
            cond_vals |= {v.strip() for v in ce.group("vals").split("|")}
    if vals and set(vals) <= cond_vals:
        return []
    if len(vals) >= 2 and len(set(vals)) == len(vals):
        return [fact("allowed_values", item.line, first_sentence(item), value=vals, method="parser")]
    return []


def rule_range(item) -> list:
    out = []
    for n, text in item.lines():
        found: dict = {}
        for kind, rx in RANGE_PATTERNS:
            for m in rx.finditer(text):
                sent = sentence_at(text, m.start())
                head = sent[:max(0, sent.find(m.group(0)))] if m.group(0) in sent else ""
                if re.search(r"\b[Ii]f\b", head) or re.search(r"\bfor[ \t]+<[^>]+>", m.group(0)):
                    continue
                after = text[m.end():]
                before = text[max(0, m.start() - 40):m.start()]
                applies = "length" if (LENGTH_AFTER.match(after) or LENGTH_BEFORE.search(before)
                                       or LENGTH_BEFORE.search(m.group(0))) else "value"
                key = (sent, applies)
                d = found.setdefault(key, {"pos": m.start()})
                if kind in ("both", "min") and m.groupdict().get("a") is not None:
                    d.setdefault("min", _num(m.group("a")))
                if kind in ("both", "max") and m.groupdict().get("b") is not None:
                    d.setdefault("max", _num(m.group("b")))
                um = re.match(rf"^[ \t]+(?P<u>{_UW})\b", after, re.I)
                if um and applies == "value":
                    d.setdefault("unit_text", um.group("u"))
        for (sent, applies), d in sorted(found.items(), key=lambda kv: kv[1]["pos"]):
            v = {k: d[k] for k in ("min", "max") if k in d}
            v["applies_to"] = applies
            if "unit_text" in d:
                v["unit_text"] = d["unit_text"]
            if "min" in v and "max" in v and v["min"] > v["max"]:
                out.append(fact("range", n, sent, status="unknown", reason="contradictory"))
            else:
                out.append(fact("range", n, sent, value=v))
    return out


def rule_unit(item, atom) -> list:
    out = []
    for n, text in item.lines():
        for rx in UNIT_PATTERNS:
            for m in rx.finditer(text):
                u = UNIT_WORDS[m.group("u").lower()]
                out.append(fact("unit", n, sentence_at(text, m.start()), value=u))
    if not out:
        nm = NAME_UNIT.search(item.name)
        if nm and nm.group("u") in NAME_UNIT_OK:
            u = UNIT_WORDS.get(nm.group("u"), None)
            if u is None and nm.group("u") in ("gbs", "tbs", "mbs", "kbs"):
                u = nm.group("u")[:2].upper()
            if u:
                out.append(fact("unit", item.line, first_sentence(item), value=u, evidence="derived"))
    return out


def rule_format(item) -> list:
    out = []
    for n, text in item.lines():
        for name, rx in FORMATS:
            m = rx.search(text)
            if m:
                out.append(fact("format", n, sentence_at(text, m.start()), value=name))
    first = sentence_at(item.head, 0) if item.head.strip() else ""
    m = OCID_FMT.search(first)
    if m:
        out.append(fact("format", item.line, first, value="OCID"))
    return out


OTHER_SUBJECT = re.compile(r"(?:`(?P<b>[A-Za-z_][A-Za-z0-9_]*)`|\b(?P<s>[a-z][a-z0-9]*(?:_[a-z0-9]+)+))[ \t,]*$")


def rule_deprecation(item) -> list:
    out = []
    for n, text in item.lines():
        m = DEPRECATED.search(text)
        if m:
            # 'x_antigo is deprecated, use <este>': o depreciado é outro campo
            sub = OTHER_SUBJECT.search(text[:m.start()])
            if sub and (sub.group("b") or sub.group("s")) not in (item.name,) and m.group(0)[:1].islower():
                continue
            out.append(fact("deprecation", n, sentence_at(text, m.start()), value=True))
    return out


def rule_example(item) -> list:
    out = []
    for n, text in item.lines():
        for m in EXAMPLE.finditer(text):
            out.append(fact("example", n, sentence_at(text, m.start()), value=m.group("v")))
    return out


def snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def rule_conflicts(item, names: set) -> list:
    out = []
    for n, text in item.lines():
        m = CONFLICT.search(text)
        if not m:
            continue
        sent = sentence_at(text, m.start())
        cands = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", sent)) | set(re.findall(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b", sent))
        # a doc do oci cita campos da API em camelCase (ocpuCount): o nome Terraform é o snake_case
        cands |= {snake(c) for c in re.findall(r"\b([a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+)\b", sent)}
        others = sorted(c for c in cands if c in names and c != item.name)
        if others:
            out.append(fact("conflicts_with", n, sent, value=others))
        else:
            out.append(fact("conflicts_with", n, sent, status="unknown", reason="ambiguous"))
    return out


def extract_item(item, atom: dict, page, sibling_names: set) -> list:
    """Todos os fatos de um item já casado com o átomo."""
    out = rule_description(item)
    out += rule_markers(item, atom, page)
    out += rule_default(item, atom)
    out += rule_enum(item, atom.get("tf_type"))
    if not any(f["fact_kind"] == "allowed_values" and f["status"] == "stated" for f in out):
        out += rule_enum_list(item)
    if not any(f["fact_kind"] == "allowed_values" and f["status"] == "stated" for f in out):
        out += rule_enum_can_be(item, atom.get("tf_type"))
    out += rule_range(item)
    out += rule_unit(item, atom)
    out += rule_format(item)
    out += rule_deprecation(item)
    out += rule_example(item)
    out += rule_conflicts(item, sibling_names)
    return out


def _canon(v):
    return repr(v) if not isinstance(v, (dict, list)) else repr(sorted(v.items()) if isinstance(v, dict) else v)


def reconcile(facts: list) -> list:
    """Por átomo e tipo de fato com valor único esperado (default, unit, forces_replacement): valores
    distintos declarados -> um único unknown (contradictory; ambiguous para unidade), com a 1ª fonte;
    repetidos iguais -> o 1º.
    Os demais tipos ficam todos, sem duplicata exata (mesmo valor e mesma linha; na descrição, mesmo texto)."""
    single = {"default", "unit", "forces_replacement"}
    out, seen = [], set()
    by_kind: dict = {}
    for f in facts:
        by_kind.setdefault(f["fact_kind"], []).append(f)
    for kind, fs in by_kind.items():
        if kind in single:
            stated = [f for f in fs if f["status"] == "stated"]
            vals = {_canon(f["value"]) for f in stated}
            if len(vals) > 1:
                first = stated[0]
                # unidades diferentes no mesmo texto costumam ser de coisas diferentes: ambíguo, não contraditório
                why = "ambiguous" if kind == "unit" else "contradictory"
                u = {k: v for k, v in first.items() if k != "value"}
                u.update(status="unknown", unknown_reason=why)
                out.append(u)
                continue
            if stated:
                # um declarado (o publicado tem precedência sobre o derivado)
                pub = [f for f in stated if f["evidence_level"] == "published"]
                out.append((pub or stated)[0])
                continue
            out.append(fs[0])
            continue
        for f in fs:
            # descrição repetida (Argument Reference e Attributes Reference com o mesmo texto): fica a 1ª
            key = (kind, f["status"], _canon(f.get("value"))) if kind == "description" and f["status"] == "stated" \
                else (kind, f["status"], _canon(f.get("value")), f["line"])
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
    return out
