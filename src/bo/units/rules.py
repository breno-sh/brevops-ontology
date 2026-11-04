"""Regras declaradas do UNITS: literal de unidade -> tipo de unidade (QUDT por IRI, janela de taxa, convenção de byte).

Nada aqui é palpite: cada tabela é fechada e cada saída cita a regra (rule id) que a produziu. O que não casa com
uma regra fica UNKNOWN (há grandeza, não se sabe qual unidade) ou NOT_APPLICABLE (não há grandeza).

Tipo de unidade (N4, igual ao bo.transforms.units): (unidade, janela de taxa, convenção de byte). Uma taxa é a
unidade da quantidade MAIS a janela: 'Mbps' = (unit:MegaBIT, PT1S, SI); 'IOPS' = (unit:NUM, PT1S); nunca uma
unidade -PER- com janela (seria contar o tempo duas vezes).

Grandeza de dado: o QUDT 3.5.3 liga BYTE/BIT e prefixos a quantitykind:AmountOfData (e ByteDataVolume /
BitDataVolume), não a quantitykind:InformationEntropy; o UNITS usa AmountOfData e registra a divergência com o
registro do TRANSFORMS em results/UNITS/CONTRACT_CHANGE.txt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

NA = "NOT_APPLICABLE"
UNK = "UNKNOWN"

TIME = "quantitykind:Time"
DATA = "quantitykind:AmountOfData"
COUNT = "quantitykind:Count"
RATIO = "quantitykind:DimensionlessRatio"

# unidades usadas (todas no registro do TRANSFORMS e conferidas no QUDT fixado por bo.units.qudt)
UNIT_KIND = {
    "unit:NanoSEC": TIME, "unit:MicroSEC": TIME, "unit:MilliSEC": TIME, "unit:SEC": TIME, "unit:MIN": TIME,
    "unit:HR": TIME, "unit:DAY": TIME, "unit:WK": TIME, "unit:MO": TIME, "unit:YR": TIME,
    "unit:BIT": DATA, "unit:KiloBIT": DATA, "unit:MegaBIT": DATA, "unit:GigaBIT": DATA,
    "unit:BYTE": DATA, "unit:KiloBYTE": DATA, "unit:MegaBYTE": DATA, "unit:GigaBYTE": DATA, "unit:TeraBYTE": DATA,
    "unit:KibiBYTE": DATA, "unit:MebiBYTE": DATA, "unit:GibiBYTE": DATA, "unit:TebiBYTE": DATA,
    "unit:NUM": COUNT, "unit:FRACTION": RATIO, "unit:PERCENT": RATIO,
}
# convenção de byte por unidade. BYTE e BIT sem prefixo têm fator 1 nas duas convenções; o C05-BYTES exige SI|IEC
# e o UNITS grava SI (convenção vácua, declarada em UNITS-BYTE-00 e no CONTRACT_CHANGE).
BYTE_CONV = {
    "unit:BIT": "SI", "unit:KiloBIT": "SI", "unit:MegaBIT": "SI", "unit:GigaBIT": "SI",
    "unit:BYTE": "SI", "unit:KiloBYTE": "SI", "unit:MegaBYTE": "SI", "unit:GigaBYTE": "SI", "unit:TeraBYTE": "SI",
    "unit:KibiBYTE": "IEC", "unit:MebiBYTE": "IEC", "unit:GibiBYTE": "IEC", "unit:TebiBYTE": "IEC",
}

RULES = {
    "UNITS-KIND-01": "datatype vem do tf_type do SCHEMA-* (string, number->decimal, bool, list/set/map/object/dynamic"
                     "->árvore ou tupla); string, booleano, enum e árvore não têm grandeza (C05-KIND): NOT_APPLICABLE",
    "UNITS-ENUM-01": "string com allowed_values declarado (lista; no GCP só closed=true) vira escalar enum com a lista",
    "UNITS-DUR-01": "timeouts.{create,read,update,delete,default} (string) é duração Go (time.ParseDuration, ex. '30m'):"
                    " escalar duration, grandeza Time, unidade da faixa e da forma canônica unit:SEC, formato go_duration",
    "UNITS-DUR-02": "string com formato google.protobuf.Duration ('3.5s') publicado: duration, Time, unit:SEC",
    "UNITS-DUR-03": "string com formato ISO-8601 de duração publicado: duration, Time; unidade UNKNOWN porque "
                    "xsd:duration tem meses e mês não é número fixo de segundos (TRANSFORMS, contexto de calendário)",
    "UNITS-LIT-01": "literal de unidade publicado (fact_kind unit, ou unidade de range/default) mapeado pela tabela "
                    "fechada LITERALS para o IRI QUDT; literal fora da tabela fica UNKNOWN",
    "UNITS-BYTE-00": "BYTE/BIT sem prefixo: fator 1 em SI e IEC; grava SI (convenção vácua)",
    "UNITS-BYTE-01": "prefixo binário explícito (KiB, MiB, GiB, TiB, kibibyte...) = IEC",
    "UNITS-BYTE-02": "prefixo decimal de byte (KB, MB, GB, TB, gigabyte...) sem confirmação da convenção na frase: "
                     "grandeza AmountOfData, unidade UNKNOWN (doc de nuvem usa GB também para 2^30)",
    "UNITS-BYTE-03": "prefixo decimal de byte com o prefixo binário correspondente na mesma frase (ex. 'gigabytes "
                     "(specifically GiB)'): IEC",
    "UNITS-BIT-01": "bit e bit por segundo com prefixo (Kbps, Mbps, Gbps) = SI (IEC 80000-13; telecom não usa 2^n)",
    "UNITS-RATE-01": "taxa: a janela vai no tipo; '/s', 'ps', 'per second' = PT1S; 'per minute' = PT1M; 'per hour' = "
                     "PT1H; 'per day' = P1D; 'per N minutes' = PTNM",
    "UNITS-RATE-02": "unidade composta ('MBps per TiB', 'per vCPU', 'gigabyte-seconds'): grandeza e unidade UNKNOWN",
    "UNITS-COUNT-01": "contagem de coisa (vCPU, OCPU, ECPU, CPU, IOPS): Count, unit:NUM; IOPS com janela PT1S; a coisa "
                      "contada fica na nota da evidência (o C05 não tem campo para ela)",
    "UNITS-PCT-01": "percent, percentage, %: DimensionlessRatio, unit:PERCENT",
    "UNITS-EPOCH-01": "tempo 'since (the Unix) epoch': Time na unidade publicada, formato unix_epoch",
    "UNITS-NAME-01": "sufixo do nome do atributo numérico na tabela fechada NAME_SUFFIXES (ex. _in_seconds, _days, "
                     "_mb, _gib, _percent, _mbps, _iops)",
    "UNITS-NAID-01": "número que é identificador, código ou ordinal (porta, ASN, VLAN, prioridade, versão, código "
                     "ICMP/HTTP, protocolo, índice, ordem): sem grandeza, NOT_APPLICABLE",
    "UNITS-CONFLICT-01": "fontes de unidade discordam: mesma grandeza -> unidade UNKNOWN; grandezas diferentes -> "
                         "UNKNOWN nas duas",
    "UNITS-UNK-01": "número sem unidade publicada, sem regra de nome e sem regra de identificador: UNKNOWN",
    "UNITS-UNK-02": "o DOCS-* registrou a unidade como desconhecida (status unknown: ambiguous, contradictory, "
                    "not_documented): UNKNOWN",
    "UNITS-RANGE-01": "faixa só de range sobre o valor (of/applies_to = value; count só em número escalar), na "
                      "mesma unidade do átomo; faixas divergentes entre fatos não entram",
    "UNITS-FMT-01": "formato publicado (fact_kind format) normalizado pela tabela FORMATS; formatos divergentes não "
                    "entram",
    "UNITS-SHARED-01": "átomo repetido do DOCS-AWS (shared_block_map.jsonl, R3-shared) herda os fatos do canônico",
}


@dataclass(frozen=True)
class UT:
    """Tipo de unidade candidato. unit/qk podem ser UNK; window é xsd:duration fixa ou None."""
    qk: str
    unit: str
    window: str | None = None
    rule: str = "UNITS-LIT-01"
    note: str = ""

    @property
    def bc(self) -> str:
        return BYTE_CONV.get(self.unit, NA)

    def key(self):
        return (self.qk, self.unit, self.window)


def _t(unit, rule="UNITS-LIT-01", note=""):
    return UT(UNIT_KIND[unit], unit, None, rule, note)


TIME_WORDS = {
    "unit:NanoSEC": ["ns", "nanosecond", "nanoseconds", "nanos"],
    "unit:MicroSEC": ["us", "µs", "microsecond", "microseconds", "micros"],
    "unit:MilliSEC": ["ms", "msec", "millisecond", "milliseconds", "millis"],
    "unit:SEC": ["s", "sec", "secs", "second", "seconds"],
    "unit:MIN": ["min", "mins", "minute", "minutes", "in_min"],
    "unit:HR": ["h", "hr", "hrs", "hour", "hours"],
    "unit:DAY": ["d", "day", "days"],
    "unit:WK": ["wk", "wks", "week", "weeks"],
    "unit:MO": ["month", "months"],
    "unit:YR": ["yr", "yrs", "year", "years"],
}

# prefixos de byte: decimal (ambíguo) -> binário correspondente
SI_BYTE = {"K": "unit:KibiBYTE", "M": "unit:MebiBYTE", "G": "unit:GibiBYTE", "T": "unit:TebiBYTE"}
IEC_TOKENS = {"K": ("KiB", "kibibyte"), "M": ("MiB", "mebibyte"), "G": ("GiB", "gibibyte"), "T": ("TiB", "tebibyte")}
SI_BYTE_WORDS = {  # literal (minúsculo) -> prefixo
    "kb": "K", "kbs": "K", "kilobyte": "K", "kilobytes": "K",
    "mb": "M", "mbs": "M", "megabyte": "M", "megabytes": "M",
    "gb": "G", "gbs": "G", "gigabyte": "G", "gigabytes": "G",
    "tb": "T", "tbs": "T", "terabyte": "T", "terabytes": "T",
}
IEC_BYTE_WORDS = {
    "kib": "unit:KibiBYTE", "kibibyte": "unit:KibiBYTE", "kibibytes": "unit:KibiBYTE",
    "mib": "unit:MebiBYTE", "mebibyte": "unit:MebiBYTE", "mebibytes": "unit:MebiBYTE",
    "gib": "unit:GibiBYTE", "gibs": "unit:GibiBYTE", "gibibyte": "unit:GibiBYTE", "gibibytes": "unit:GibiBYTE",
    "tib": "unit:TebiBYTE", "tibs": "unit:TebiBYTE", "tebibyte": "unit:TebiBYTE", "tebibytes": "unit:TebiBYTE",
}
BIT_RATE = {"kbps": "unit:KiloBIT", "mbps": "unit:MegaBIT", "gbps": "unit:GigaBIT",
            "kilobit_per_second": "unit:KiloBIT", "megabit_per_second": "unit:MegaBIT",
            "gigabit_per_second": "unit:GigaBIT"}
COUNT_WORDS = {"vcpu": "vCPU", "vcpus": "vCPU", "cpu": "CPU", "cpus": "CPU", "ocpu": "OCPU", "ocpus": "OCPU",
               "ecpu": "ECPU", "ecpus": "ECPU"}
PCT_WORDS = {"percent", "percentage", "%", "pct"}
IOPS_WORDS = {"iops", "io_operation_per_second"}

TIME_LOOKUP = {w: u for u, ws in TIME_WORDS.items() for w in ws}
# literais de uma letra só valem com a caixa exata (B = byte; b sozinho não entra)
CASE_SENSITIVE = {"B": "unit:BYTE"}

_WIN_UNIT = {"second": "S", "sec": "S", "s": "S", "minute": "M", "min": "M", "hour": "H", "hr": "H", "day": "D"}
_PER_TIME = re.compile(r"(?:\bper|/)\s*(?:(\d+)\s*)?(seconds?|secs?|s|minutes?|mins?|hours?|hrs?|days?)\b", re.I)
_PER_OTHER = re.compile(r"\bper\s+(?!(?:\d+\s*)?(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b)[A-Za-z]")
_PRODUCT = re.compile(r"\b(?:giga|mega|kilo|tera)?bytes?-(?:seconds?|hours?)\b|\b(?:GB|MB)-(?:seconds?|hours?)\b", re.I)


def window_of(n: str | None, word: str) -> str:
    w = word.lower().rstrip("s") if word.lower() not in ("s",) else "s"
    u = _WIN_UNIT.get(w) or _WIN_UNIT.get(word.lower())
    k = int(n) if n else 1
    if u == "D":
        return f"P{k}D"
    return f"PT{k}{u}"


def rate_window_in(sentence: str) -> str | None:
    """Janela de taxa declarada na frase ('per second', '/s', 'per 5 minutes'); None se não há."""
    m = _PER_TIME.search(sentence or "")
    return window_of(m.group(1), m.group(2)) if m else None


def compound_in(sentence: str) -> bool:
    s = sentence or ""
    return bool(_PER_OTHER.search(s) or _PRODUCT.search(s))


def near_literal(sentence: str, literal: str, after: int = 28) -> str:
    """Trechos da frase logo depois de cada ocorrência do literal (onde mora '/s', 'per second', 'per TiB')."""
    s = sentence or ""
    out = []
    for m in re.finditer(rf"(?<![A-Za-z]){re.escape(literal)}", s, re.I):
        out.append(s[m.start():m.end() + after])
    return " | ".join(out)


def _byte_si(prefix: str, sentence: str, literal: str) -> UT:
    """Prefixo decimal de byte: IEC se a frase traz o prefixo binário correspondente; senão grandeza sem unidade."""
    toks = IEC_TOKENS[prefix]
    s = sentence or ""
    if toks[0] in s or re.search(rf"\b{toks[1]}s?\b", s, re.I):
        return _t(SI_BYTE[prefix], "UNITS-BYTE-03", f"literal '{literal}' com '{toks[0]}' na mesma frase")
    return UT(DATA, UNK, None, "UNITS-BYTE-02", f"literal '{literal}': convenção SI x IEC não declarada")


def literal_type(literal: str, sentence: str = "") -> UT | None:
    """Literal de unidade (como o DOCS-* gravou) -> tipo de unidade, com a janela lida da frase. None = fora da tabela."""
    if not isinstance(literal, str) or not literal.strip():
        return None
    lit = literal.strip()
    low = lit.lower()
    s = sentence or ""
    ut: UT | None = None
    is_time = False
    if lit in CASE_SENSITIVE:
        ut = _t(CASE_SENSITIVE[lit], "UNITS-BYTE-00", "byte sem prefixo")
    elif low in ("byte", "bytes"):
        ut = _t("unit:BYTE", "UNITS-BYTE-00", "byte sem prefixo")
    elif low in ("bit", "bits"):
        ut = _t("unit:BIT", "UNITS-BIT-01", "bit sem prefixo")
    elif low in IEC_BYTE_WORDS:
        ut = _t(IEC_BYTE_WORDS[low], "UNITS-BYTE-01", f"literal '{lit}'")
    elif low in ("mib/s", "gib/s", "kib/s", "tib/s"):
        ut = replace(_t(IEC_BYTE_WORDS[low[:-2]], "UNITS-BYTE-01", f"literal '{lit}'"), window="PT1S")
    elif lit in ("MBps", "GBps", "KBps", "TBps", "MB/s", "GB/s", "KB/s", "TB/s"):
        ut = replace(_byte_si(lit[0], s, lit), window="PT1S")
    elif low in BIT_RATE:
        # 'Mbps' com 'MBps' na frase é megabyte por segundo (B maiúsculo); a caixa da frase decide
        if re.search(rf"\b{lit[0].upper()}Bps\b", s) and not re.search(rf"\b{lit[0].upper()}bps\b", s):
            ut = replace(_byte_si(lit[0].upper(), s, lit[0].upper() + "Bps"), window="PT1S")
        else:
            ut = UT(DATA, BIT_RATE[low], "PT1S", "UNITS-BIT-01", f"literal '{lit}'")
    elif low in SI_BYTE_WORDS:
        ut = _byte_si(SI_BYTE_WORDS[low], s, lit)
    elif low in TIME_LOOKUP:
        ut = _t(TIME_LOOKUP[low], "UNITS-LIT-01", f"literal '{lit}'")
        is_time = True
    elif low in PCT_WORDS:
        ut = _t("unit:PERCENT", "UNITS-PCT-01", f"literal '{lit}'")
    elif low in IOPS_WORDS:
        ut = UT(COUNT, "unit:NUM", "PT1S", "UNITS-COUNT-01", "contagem de operação de E/S por segundo (IOPS)")
    elif low in COUNT_WORDS:
        ut = _t("unit:NUM", "UNITS-COUNT-01", f"contagem de {COUNT_WORDS[low]}")
    if ut is None:
        return None
    if is_time:
        if re.search(r"\bsince\s+(the\s+)?(unix\s+)?epoch\b", s, re.I):
            ut = replace(ut, rule="UNITS-EPOCH-01", note=ut.note + "; desde a época Unix")
        return ut
    if ut.unit == "unit:PERCENT":
        return ut
    near = near_literal(s, lit)
    if compound_in(near):
        return UT(UNK, UNK, None, "UNITS-RATE-02", f"literal '{lit}' em unidade composta")
    if ut.window is None:
        w = rate_window_in(near)
        if w:
            ut = replace(ut, window=w, rule=ut.rule, note=ut.note + f"; taxa por {w} (UNITS-RATE-01)")
    return ut


# --------------------------------------------------------------------------------------------- regra de nome
# sufixo do último segmento do nome (tokens separados por '_'), do mais longo para o mais curto
NAME_SUFFIXES: list[tuple[tuple[str, ...], str]] = []


def _add(words, lit):
    for w in words:
        NAME_SUFFIXES.append((tuple(w.split("_")), lit))


_add(["in_seconds", "seconds", "secs", "in_secs", "in_sec", "sec"], "seconds")
_add(["in_milliseconds", "milliseconds", "in_ms", "ms", "millis", "msec", "in_millis"], "milliseconds")
_add(["in_microseconds", "microseconds", "in_us"], "microseconds")
_add(["in_nanoseconds", "nanoseconds", "nanos"], "nanoseconds")
_add(["in_minutes", "minutes", "mins", "in_mins", "in_min"], "minutes")
_add(["in_hours", "hours", "hrs", "in_hrs"], "hours")
_add(["in_days", "days"], "days")
_add(["in_weeks", "weeks"], "weeks")
_add(["in_months", "months"], "months")
_add(["in_years", "years"], "years")
_add(["in_bytes", "bytes"], "bytes")
_add(["kilo_bytes", "in_kilo_bytes", "kilobytes"], "kb")
_add(["mega_bytes", "in_mega_bytes", "megabytes"], "mb")
_add(["giga_bytes", "in_giga_bytes", "gigabytes"], "gb")
_add(["tera_bytes", "in_tera_bytes", "terabytes"], "tb")
_add(["kibi_bytes", "kibibytes"], "kib")
_add(["mebi_bytes", "mebibytes"], "mib")
_add(["gibi_bytes", "gibibytes"], "gib")
_add(["tebi_bytes", "tebibytes"], "tib")
_add(["in_kbs", "in_kb", "kb", "kbs"], "kb")
_add(["in_mbs", "in_mb", "mb", "mbs"], "mb")
_add(["in_gbs", "in_gb", "gb", "gbs"], "gb")
_add(["in_tbs", "in_tb", "tb", "tbs"], "tb")
_add(["in_kib", "kib", "in_kibs"], "kib")
_add(["in_mib", "mib", "in_mibs", "mibs"], "mib")
_add(["in_gib", "gib", "in_gibs", "gibs"], "gib")
_add(["in_tib", "tib", "in_tibs", "tibs"], "tib")
_add(["in_percent", "in_percentage", "percent", "percentage", "pct"], "percent")
_add(["in_mbps", "mbps"], "mbps")
_add(["in_gbps", "gbps"], "gbps")
_add(["in_kbps", "kbps"], "kbps")
_add(["in_mibps", "mibps"], "MiB/s")
_add(["in_gibps", "gibps"], "GiB/s")
_add(["iops"], "iops")
_add(["ocpus", "ocpu_count"], "ocpu")
_add(["vcpus", "vcpu_count"], "vcpu")
_add(["ecpus", "ecpu_count"], "ecpu")
NAME_SUFFIXES.sort(key=lambda x: -len(x[0]))

_PER_OTHER_NAME = re.compile(r"_per_(?!(?:second|sec|minute|min|hour|day)$)[a-z0-9]+$")


def name_compound(attr: str) -> bool:
    """Nome '..._per_<não-tempo>' (iops_per_tb, mbps_per_tib, cost_per_gb): unidade composta (UNITS-RATE-02)."""
    return bool(_PER_OTHER_NAME.search(attr.rsplit(".", 1)[-1].lower()))


_PER_NAME = re.compile(r"(?:^|_)(?P<what>[a-z]+)_per_(?P<win>second|sec|minute|min|hour|day)$")


MONEY_SIBLINGS = {"currency_code", "currency"}


def name_type(attr: str, siblings: frozenset | set = frozenset()) -> UT | None:
    """Tipo de unidade pelo nome do atributo (último segmento). None = nenhuma regra casa.

    siblings = nomes dos outros atributos do mesmo bloco. Bloco de dinheiro (google.type.Money: units, nanos,
    currency_code) não tem grandeza de tempo nem de dado: a regra de nome não se aplica nele. 'nanos' só é
    nanossegundo ao lado de 'seconds' (google.protobuf.Duration) ou de 'hours'/'minutes' (hora do dia)."""
    name = attr.rsplit(".", 1)[-1].lower()
    if siblings & MONEY_SIBLINGS:
        return None
    if name == "nanos" and not ("seconds" in siblings or {"hours", "minutes"} <= set(siblings)):
        return None
    m = _PER_NAME.search(name)
    if m:
        what = m.group("what")
        win = window_of(None, m.group("win"))
        base = literal_type(what) if what not in ("requests", "request", "messages", "events", "operations",
                                                   "calls", "transactions", "queries", "records") else None
        if base is not None and base.qk == DATA and base.window is None:
            return replace(base, window=win, rule="UNITS-NAME-01", note=f"nome '{name}': {base.note}; taxa {win}")
        if base is None:
            return UT(COUNT, "unit:NUM", win, "UNITS-NAME-01", f"nome '{name}': contagem de {what} por {win}")
        return None
    toks = tuple(name.split("_"))
    for suf, lit in NAME_SUFFIXES:
        if len(toks) >= len(suf) and toks[-len(suf):] == suf:
            if len(toks) == len(suf) and lit in ("kb", "mb", "gb", "tb", "milliseconds", "seconds") and \
                    suf[0] in ("kb", "mb", "gb", "tb", "ms", "sec", "msec"):
                return None   # nome que é só a sigla ('ms', 'gb'): curto demais para a regra
            ut = literal_type(lit)
            if ut is None:
                return None
            return replace(ut, rule="UNITS-NAME-01", note=f"sufixo '_{'_'.join(suf)}' do nome: {ut.note}")
    return None


# ----------------------------------------------------------------------------- números sem grandeza (ids)
_NAID = re.compile(
    r"(?:^|_)(?:ports?|asn|bgp_asn|as_number|vlan|vlan_id|vlan_tag|vni|priority|rule_number|"
    r"version|revision|generation|status_code|response_code|http_code|error_code|icmp_type|icmp_code|"
    r"protocol|protocol_number|index|order|position|sequence|sequence_number|ordinal|id|serial_number)$")


def is_identifier_number(attr: str) -> bool:
    name = attr.rsplit(".", 1)[-1].lower()
    if name in ("type", "code"):   # 'type'/'code' sozinhos: só sob bloco icmp
        return "icmp" in attr.lower()
    return bool(_NAID.search(name))


# ----------------------------------------------------------------------------------------------- formatos
FORMATS = {
    "json": "json", "arn": "arn", "cidr": "cidr", "rfc3339": "rfc3339", "utc timestamp": "utc_timestamp",
    "base64": "base64", "ipv6": "ipv6", "ipv4": "ipv4", "iso8601": "iso8601", "iso-8601": "iso8601",
    "cron": "cron", "uuid": "uuid", "iso8601_duration": "iso8601_duration", "hh:mm": "hh_mm",
    "ocid": "ocid", "iana-tz": "iana_tz",
}


def format_of(value) -> str | None:
    """Valor de fact_kind format (texto ou objeto do GCP) -> formato normalizado; None = não entra."""
    if isinstance(value, str):
        return FORMATS.get(value.strip().lower())
    if isinstance(value, dict):
        a = value.get("aspect")
        if a == "timestamp" and str(value.get("standard", "")).upper() == "RFC3339":
            return "rfc3339"
        if a == "duration" and value.get("standard") == "google.protobuf.Duration":
            return "protobuf_duration"
    return None
