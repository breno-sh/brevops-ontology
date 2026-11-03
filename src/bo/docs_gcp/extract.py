"""Padrões declarados sobre o texto de um item de atributo. Cada padrão tem um id (P-...) e um método (C03).

Entrada: o item (linhas com número). Saída: Item limpo (nome, flags, descrição, frases com linha) e uma lista de
achados (kind, value | unknown_reason, frase, linha, pattern_id). Nada é inferido além do que a frase diz:
  * default       'Default(s) (value) is|to|:' + valor literal (crase, aspas, true/false, número, duração '900s',
                  'empty string' -> "", CONSTANTE);
                  número com unidade vira {"quantity", "unit"}; valor não literal -> unknown ambiguous (P-DEF)
  * allowed_values 'Possible|Valid|Allowed|Accepted|Supported values are|include' + lista; 'one of|either|
                  must be|can be' + lista de >= 2 itens (crase ou CONSTANTE) (P-ENUM-*); 'include' = lista aberta
  * range         'between N and M', 'N-M characters', 'at least|minimum (value) of N', 'at most|maximum (value)
                  of N', 'must not|cannot exceed N' (P-RANGE-*); of = length | count | value pela palavra seguinte
  * unit          'in <unidade>' e '(number|amount|size|duration) of <unidade>' (P-UNIT-*)
  * format        'regular expression `re`' (P-FMT-RE), RFC 3339 (P-FMT-RFC3339), duração protobuf em segundos com
                  sufixo 's' (P-FMT-DUR), 'with format `t`' (P-FMT-ID)
  * forces_replacement 'forces a new resource|recreation', 'will cause|force ... to (be )?recreate(d)', 'requires
                  (a )?recreation', 'will recreate the', 'delete/recreate', 'forcing recreation', sem
                  'without|not|never' logo antes (P-FN)
  * deprecation   flag (Deprecated) ou frase com 'deprecated' (P-DEP-FLAG, P-DEP-TEXT)
  * conflicts_with 'conflicts with `a`', 'mutually exclusive with `a`', 'cannot be (specified|set|used) (together )?
                  with `a`', 'only one of `a`, `b` (can|may|should|must) be' (P-CONF-*)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MD_LINK = re.compile(r"\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
LEAD = re.compile(r"^\s*[*-]\s+`(?P<name>[^`]+)`\s*(?P<rest>.*)$")
FLAGS = re.compile(r"^\s*(?:-{1,2}|:)?\s*\((?P<f>[^()]*(?:\([^()]*\)[^()]*)*)\)\s*(?:-{1,2}|:)?\s*")
KNOWN_FLAGS = {"required", "optional", "computed", "output", "deprecated", "beta", "sensitive", "write-only",
               "ga", "immutable", "updatable", "default", "optional, beta", "deprecated, beta"}
NO_SPLIT_BEFORE = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "Inc.", "U.S.")


@dataclass
class Sentence:
    text: str
    line: int
    start: int
    end: int


@dataclass
class Item:
    name: str
    flags: list
    description: str
    sentences: list
    line: int


@dataclass
class Finding:
    kind: str
    pattern: str
    sentence: Sentence
    value: object = None
    unknown_reason: str | None = None
    method: str = "regex"


def clean_line(s: str) -> str:
    s = MD_LINK.sub(lambda m: m.group(1), s)
    s = s.replace("**", "").replace("<br>", " ").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def split_sentences(text: str, offsets: list) -> list:
    """Frases com a linha de origem. offsets = [(posição inicial no texto, nº da linha)] em ordem."""
    out = []
    start = 0
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z`*\"(\[])", text):
        before = text[:m.start()]
        if before.endswith(NO_SPLIT_BEFORE) or re.search(r"\b[A-Za-z]\.$", before):
            continue
        out.append((start, m.start()))
        start = m.end()
    out.append((start, len(text)))
    sents = []
    for a, b in out:
        t = text[a:b].strip()
        if not t:
            continue
        line = offsets[0][1]
        for pos, ln in offsets:
            if pos <= a:
                line = ln
            else:
                break
        sents.append(Sentence(t, line, a, b))
    return sents


def item_from_lines(lines: list) -> Item:
    """lines = [(nº, texto)] do item, a primeira com '* `nome`'."""
    m = LEAD.match(lines[0][1])
    name = m.group("name")
    first = m.group("rest")
    flags = []
    while True:
        mf = FLAGS.match(first)
        if not mf:
            break
        inner = mf.group("f")
        toks = [t.strip().lower() for t in MD_LINK.sub(lambda x: x.group(1), inner).split(",")]
        if not toks or not all(t in KNOWN_FLAGS or t.startswith(("beta", "deprecated", "optional", "required",
                                                                   "output", "computed")) for t in toks):
            break
        flags += toks
        first = first[mf.end():]
    first = re.sub(r"^\s*(?:-{1,2}|:)\s*", "", first)
    parts = [(lines[0][0], first)] + [(ln, t) for ln, t in lines[1:]]
    text, offsets = "", []
    for ln, t in parts:
        c = clean_line(t)
        if not c:
            continue
        # subitens e notas: o marcador de lista sai do texto
        c = re.sub(r"^[*-]\s+", "", c)
        # flags num subitem continuam visíveis no texto do pai (não são do pai)
        if text:
            text += " "
        offsets.append((len(text), ln))
        text += c
    if not offsets:
        offsets = [(0, lines[0][0])]
    # flags que o gerador MMv1 põe na segunda linha: '* `x` -\n  (Required)\n  texto'
    while True:
        mf = re.match(r"^\((?P<f>[^()]*)\)\s*", text)
        if not mf:
            break
        toks = [t.strip().lower() for t in mf.group("f").split(",")]
        if not all(t in KNOWN_FLAGS or t.startswith(("beta", "deprecated", "optional", "required", "output",
                                                     "computed")) for t in toks):
            break
        flags += toks
        cut = mf.end()
        text = text[cut:]
        offsets = [(max(0, p - cut), ln) for p, ln in offsets]
        # a primeira posição que ficou negativa vira 0; linhas que caíram antes do corte saem
        keep = []
        for p, ln in offsets:
            if keep and keep[-1][0] == p:
                keep[-1] = (p, ln)
            else:
                keep.append((p, ln))
        offsets = keep
    return Item(name=name, flags=flags, description=text.strip(), sentences=split_sentences(text, offsets),
                line=lines[0][0])


# ---------------------------------------------------------------- valores literais

UNIT_WORDS = ("nanoseconds|microseconds|milliseconds|seconds|minutes|hours|days|weeks|months|years|"
              "bytes|kilobytes|megabytes|gigabytes|terabytes|kib|mib|gib|tib|kb|mb|gb|tb|pb|"
              "mbps|gbps|percent|percentage|degrees|cpus|vcpus")
UNIT_CANON = {"kib": "KiB", "mib": "MiB", "gib": "GiB", "tib": "TiB", "kb": "KB", "mb": "MB", "gb": "GB",
              "tb": "TB", "pb": "PB", "mbps": "Mbps", "gbps": "Gbps", "percentage": "percent", "vcpus": "vCPUs",
              "cpus": "CPUs"}
SINGULAR = {"nanosecond": "nanoseconds", "microsecond": "microseconds", "millisecond": "milliseconds",
            "second": "seconds", "minute": "minutes", "hour": "hours", "day": "days", "week": "weeks",
            "month": "months", "year": "years", "byte": "bytes", "gigabyte": "gigabytes", "megabyte": "megabytes",
            "kilobyte": "kilobytes", "terabyte": "terabytes", "degree": "degrees"}


def canon_unit(u: str) -> str:
    lu = u.lower()
    lu = SINGULAR.get(lu, lu)
    return UNIT_CANON.get(lu, lu)


UNIT_ALT = UNIT_WORDS + "|" + "|".join(SINGULAR)
NUM = r"-?\d+(?:,\d{3})*(?:\.\d+)?"


def literal(s: str):
    """Valor literal do começo de s, ou None. Devolve (valor, texto casado)."""
    m = re.match(r"`([^`]*)`", s)
    if m:
        return _scalar(m.group(1).strip().strip('"').strip("'")), m.group(0)
    m = re.match(r'"([^"]{0,80})"', s) or re.match(r"'([^']{0,80})'", s)
    if m:
        return m.group(1), m.group(0)
    m = re.match(r"(true|false)\b", s, re.I)
    if m:
        return m.group(1).lower() == "true", m.group(0)
    m = re.match(rf"({NUM})\s*({UNIT_ALT})\b", s, re.I)
    if m:
        return {"quantity": _num(m.group(1)), "unit": canon_unit(m.group(2))}, m.group(0)
    m = re.match(r"(\d+(?:\.\d+)?s)(?![\w-])", s)
    if m:
        return m.group(1), m.group(0)
    m = re.match(rf"({NUM})(?![\w-])(?!\.\d)", s)
    if m:
        return _num(m.group(1)), m.group(0)
    m = re.match(r"(?:an?\s+)?empty\s+string\b", s, re.I)
    if m:
        return "", m.group(0)
    m = re.match(r"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{2,})\b", s)
    if m:
        return m.group(1), m.group(0)
    return None


def _num(s: str):
    s = s.replace(",", "")
    return float(s) if "." in s else int(s)


def _scalar(s: str):
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if re.fullmatch(NUM, s):
        return _num(s)
    return s


# ---------------------------------------------------------------- padrões

DEFAULT_RE = re.compile(r"\b(?:the\s+)?default(?:s|ed)?(?:\s+value)?(?:\s+(?:is|will be|to|of))?\s*(?::|=)?\s+"
                        r"(?:set\s+to\s+|to\s+)?", re.I)
DEFAULT_SKIP = re.compile(r"^(?:the\s+)?(?:provider|project|region|zone|network|service|compute|behavior|behaviour|"
                          r"setting|configuration|value|policy)\b", re.I)


def find_default(s: Sentence) -> list:
    out = []
    for m in DEFAULT_RE.finditer(s.text):
        # 'default' como adjetivo ('the default network') não é declaração de valor
        head = s.text[m.start():m.end()].lower()
        if not re.search(r"default(?:s|ed)?(?:\s+value)?\s*(?:is|will be|to|of|:|=)|defaults\s", head):
            continue
        rest = s.text[m.end():]
        lit = literal(rest)
        if lit is not None:
            out.append(Finding("default", "P-DEF", s, value=lit[0]))
        elif rest and not DEFAULT_SKIP.match(rest):
            out.append(Finding("default", "P-DEF", s, unknown_reason="ambiguous"))
    return out


ITEM = r"`[^`]+`(?:\s*\((?:Beta|beta)\))?|\"[A-Za-z0-9_.:\-/ ]{1,60}\""
CONST = r"[A-Z][A-Z0-9_]*[A-Z0-9]"
LIST_SEP = r"\s*(?:,\s*(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+|/)\s*"


def parse_list(rest: str, allow_const: bool) -> list:
    pat = ITEM + (f"|{CONST}(?![a-z])" if allow_const else "")
    m = re.match(rf"\s*(?:{pat})(?:{LIST_SEP}(?:{pat}))*", rest)
    if not m:
        return []
    items = re.findall(pat, m.group(0))
    vals = []
    for it in items:
        it = re.sub(r"\s*\((?:Beta|beta)\)$", "", it).strip()
        if it.startswith("`"):
            it = it.strip("`").strip().strip('"').strip("'")
        elif it.startswith('"'):
            it = it.strip('"')
        if it and it not in vals:
            vals.append(it)
    return vals


ENUM_HEAD = re.compile(r"\b(?P<w>possible|valid|allowed|accepted|acceptable|supported|permitted)\s+(?:values?|options?|"
                       r"inputs?)\s+(?:are|is|include|includes)\s*(?::|-)?\s*", re.I)
ENUM_ONEOF = re.compile(r"\b(?:must\s+be\s+one\s+of|can\s+be\s+one\s+of|is\s+one\s+of|one\s+of|either|must\s+be|"
                        r"can\s+be|should\s+be|may\s+be|set\s+to)\s*(?::)?\s*(?:the\s+following\s*:?\s*)?", re.I)


def find_enum(s: Sentence) -> list:
    out = []
    for m in ENUM_HEAD.finditer(s.text):
        vals = parse_list(s.text[m.end():], allow_const=True)
        if vals:
            closed = not re.search(r"include", m.group(0), re.I)
            out.append(Finding("allowed_values", "P-ENUM-HEAD", s, value={"values": vals, "closed": closed}))
    if out:
        return out
    for m in ENUM_ONEOF.finditer(s.text):
        vals = parse_list(s.text[m.end():], allow_const=True)
        if len(vals) >= 2:
            out.append(Finding("allowed_values", "P-ENUM-ONEOF", s, value={"values": vals, "closed": True}))
            break
    return out


def _of(after: str) -> str:
    a = after.lower()
    if re.match(r"\s*(?:unicode\s+)?(?:characters?|chars?|letters?|bytes? long)", a):
        return "length"
    if re.match(r"\s*(?:items?|entries|elements?|values|rules?|tags?|labels?|keys?|members?|instances?|"
                r"nodes?|replicas?|zones?|ranges?)\b", a):
        return "count"
    return "value"


def _unit_after(after: str):
    m = re.match(rf"\s*({UNIT_ALT})\b", after, re.I)
    return canon_unit(m.group(1)) if m else None


def find_range(s: Sentence) -> list:
    out = []
    t = s.text
    seen = set()

    def add(pat, lo, hi, after):
        v = {"of": _of(after)}
        if lo is not None:
            v["min"] = _num(lo)
        if hi is not None:
            v["max"] = _num(hi)
        u = _unit_after(after)
        if u and v["of"] == "value":
            v["unit"] = u
        key = (pat, lo, hi)
        if key not in seen:
            seen.add(key)
            out.append(Finding("range", pat, s, value=v))

    for m in re.finditer(rf"\bbetween\s+({NUM})\s*(?:{UNIT_ALT})?\s+and\s+({NUM})\b", t, re.I):
        add("P-RANGE-BETWEEN", m.group(1), m.group(2), t[m.end():])
    for m in re.finditer(rf"(?<![\w.-])({NUM})\s*(?:-|–|to)\s*({NUM})\s+(?=(?:unicode\s+)?(?:characters|chars)\b)",
                         t, re.I):
        add("P-RANGE-LEN", m.group(1), m.group(2), t[m.end():])
    for m in re.finditer(rf"\b(?:range|ranges)\s+(?:is\s+)?(?:from\s+)?\[?\s*({NUM})\s*(?:,|to|-|–)\s*({NUM})\s*\]?",
                         t, re.I):
        add("P-RANGE-FROMTO", m.group(1), m.group(2), t[m.end():])
    for m in re.finditer(rf"\b(?:at\s+least|no\s+less\s+than|greater\s+than\s+or\s+equal\s+to|minimum(?:\s+value)?\s+"
                         rf"(?:is|of)|min(?:imum)?\s+of)\s+({NUM})\b", t, re.I):
        add("P-RANGE-MIN", m.group(1), None, t[m.end():])
    for m in re.finditer(rf"\b(?:at\s+most|no\s+more\s+than|less\s+than\s+or\s+equal\s+to|maximum(?:\s+value)?\s+"
                         rf"(?:is|of)|max(?:imum)?\s+of|(?:must|may|can|should)\s+not\s+exceed|cannot\s+exceed|"
                         rf"can't\s+exceed|up\s+to\s+a\s+maximum\s+of)\s+({NUM})\b", t, re.I):
        add("P-RANGE-MAX", None, m.group(1), t[m.end():])
    return out


UNIT_IN = re.compile(rf"\b(?:in|in\s+units\s+of|measured\s+in|expressed\s+in|specified\s+in)\s+({UNIT_ALT})\b", re.I)
UNIT_OF = re.compile(rf"\b(?:number|amount|count|size|duration|length|period|interval|quantity)\s+of\s+({UNIT_ALT})\b",
                     re.I)
UNIT_PAREN = re.compile(rf"\((?:in\s+)?({UNIT_ALT})\)", re.I)


def find_unit(s: Sentence) -> list:
    out = []
    for pat, rx in (("P-UNIT-IN", UNIT_IN), ("P-UNIT-OF", UNIT_OF), ("P-UNIT-PAREN", UNIT_PAREN)):
        for m in rx.finditer(s.text):
            u = m.group(1)
            # 'in GB' só com sigla em maiúsculas (evita 'in mb' de outra coisa); palavras em qualquer caixa
            if u.lower() in ("kb", "mb", "gb", "tb", "pb", "kib", "mib", "gib", "tib") and not u[0].isupper():
                continue
            out.append(Finding("unit", pat, s, value=canon_unit(u)))
    return out


FMT_RE = re.compile(r"\b(?:regular\s+expression|regex|RE2(?:\s+regex)?|pattern)\s*(?::)?\s*`(?P<re>[^`]{2,})`", re.I)
FMT_RFC = re.compile(r"\bRFC\s?3339\b", re.I)
FMT_DUR = re.compile(r"\bduration\s+in\s+seconds\s+with\s+up\s+to\s+(?:nine|9)\s+fractional\s+digits", re.I)
FMT_ID = re.compile(r"\bwith\s+format\s+`(?P<t>[^`]+)`", re.I)


def find_format(s: Sentence) -> list:
    out = []
    for m in FMT_RE.finditer(s.text):
        out.append(Finding("format", "P-FMT-RE", s, value={"aspect": "regex", "pattern": m.group("re")}))
    if FMT_RFC.search(s.text):
        out.append(Finding("format", "P-FMT-RFC3339", s, value={"aspect": "timestamp", "standard": "RFC3339"}))
    if FMT_DUR.search(s.text):
        out.append(Finding("format", "P-FMT-DUR", s,
                           value={"aspect": "duration", "standard": "google.protobuf.Duration", "suffix": "s"}))
    for m in FMT_ID.finditer(s.text):
        out.append(Finding("format", "P-FMT-ID", s, value={"aspect": "identifier", "template": m.group("t")}))
    return out


FN_RE = re.compile(r"\b(?:forces?\s+(?:a\s+|the\s+)?(?:new\s+(?:resource|instance|\w+)|re-?creation|recreat\w*|"
                   r"replacement)|will\s+(?:cause|force)\s+(?:the\s+)?[\w ]{0,40}?\s+to\s+(?:be\s+)?re-?creat\w*|"
                   r"causes?\s+(?:a\s+)?re-?creation|requires?\s+(?:a\s+)?re-?creat\w*|"
                   r"(?:resource|instance)\s+(?:will\s+be|is)\s+re-?created|(?:will|would)\s+(?:delete/)?re-?create\s+the\b|"
                   r"\bdelete/re-?create\b|\bforcing\s+re-?creat\w*)", re.I)
FN_NEG = re.compile(r"\b(?:without|not|never|no\s+longer|doesn't|does\s+not|won't)\s+(?:\w+\s+){0,3}$", re.I)


def find_forcenew(s: Sentence) -> list:
    for m in FN_RE.finditer(s.text):
        if FN_NEG.search(s.text[:m.start()]):
            continue
        return [Finding("forces_replacement", "P-FN", s, value=True)]
    return []


DEP_RE = re.compile(r"\bdeprecated\b", re.I)


def find_deprecation(s: Sentence) -> list:
    if DEP_RE.search(s.text) and not re.search(r"\bnon-?deprecated\b", s.text, re.I):
        return [Finding("deprecation", "P-DEP-TEXT", s, value={"deprecated": True})]
    return []


CONF_RES = (
    ("P-CONF-WITH", re.compile(r"\bconflicts?\s+with\s+(?P<l>.*)", re.I)),
    ("P-CONF-MUTEX", re.compile(r"\bmutually\s+exclusive\s+with\s+(?P<l>.*)", re.I)),
    ("P-CONF-CANNOT", re.compile(r"\bcan(?:not|'t)\s+be\s+(?:specified|set|used|provided|configured)\s+(?:together\s+|"
                                 r"at\s+the\s+same\s+time\s+|simultaneously\s+)?(?:with|alongside|and)\s+(?P<l>.*)", re.I)),
    ("P-CONF-ONLYONE", re.compile(r"\bonly\s+one\s+of\s+(?P<l>.*?)\s+(?:can|may|should|must|is\s+allowed|"
                                  r"could)\b", re.I)),
)


def find_conflicts(s: Sentence, own: str) -> list:
    for pid, rx in CONF_RES:
        m = rx.search(s.text)
        if not m:
            continue
        names = [n for n in re.findall(r"`([A-Za-z0-9_.\[\]*]+)`", m.group("l")) if n != own]
        if pid == "P-CONF-ONLYONE":
            names = [n for n in re.findall(r"`([A-Za-z0-9_.\[\]*]+)`", m.group("l")) if n != own]
        if names:
            return [Finding("conflicts_with", pid, s, value={"attributes": sorted(set(names))})]
    return []


def findings(item: Item) -> list:
    out = []
    if any(f.startswith("deprecated") or ", deprecated" in f for f in item.flags) and item.sentences:
        out.append(Finding("deprecation", "P-DEP-FLAG", item.sentences[0], value={"deprecated": True}, method="parser"))
    own = item.name.split(".")[-1]
    for s in item.sentences:
        out += find_default(s)
        out += find_enum(s)
        out += find_range(s)
        out += find_unit(s)
        out += find_format(s)
        out += find_forcenew(s)
        if not any(f.kind == "deprecation" for f in out):
            out += find_deprecation(s)
        out += find_conflicts(s, own)
    return out
