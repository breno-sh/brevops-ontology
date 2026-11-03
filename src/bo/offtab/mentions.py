"""Regra de separação de célula em menções de serviço e identificador de cada menção.

Uma célula do Google ou da Microsoft é texto livre; a Oracle já dá listas. A regra é mecânica e não resolve sinônimo:
  1. separa em " ; " (quebra estrutural da página: <br>, item de lista);
  2. separa em ", " fora de parênteses;
  3. tira "or " / "and " do começo de um pedaço que veio de vírgula ("A, B, or C");
  4. pedaço de vírgula que começa com minúscula é continuação, não serviço novo: volta a se juntar ao anterior
     com o texto original (", optionally with Dapr ...", ", such as use1-az1", ", or a specialized ...");
  5. tira espaço e ponto final.
Antes disso a célula é classificada (classify): vazia; ausência explícita do fornecedor ("None", "No equivalent",
"No direct equivalent", "No single equivalent. ..."); prosa (tem fronteira de frase ". " + maiúscula e não nomeia
serviço, ex. "Claims no access to customer data, even by request. ..."); ou serviços. Só a última gera menções.
"A or B" e "A and B" sem vírgula NÃO são separados: viram uma menção só, marcada compound (a página pode estar
nomeando um serviço com "and" no nome, ex. "Cost Management + Billing", ou propondo alternativas). Cada menção
guarda o texto da célula de origem, então quem quiser outra regra refaz a partir do catálogo.

Identificador: <prefixo do provedor>:<slug do rótulo como escrito>. Rótulos diferentes para o mesmo serviço
("Amazon S3" e "Simple Storage Service (S3)") ficam como ids diferentes: o OFFTAB não decide sinonímia.
"""

from __future__ import annotations

import re

PREFIX = {"aws": "awssvc", "azure": "azuresvc", "gcp": "gcpsvc", "oci": "ocisvc"}
BASE = "https://w3id.org/brevops/offtab/service/"
CURIE_MAP = {v: f"{BASE}{k}/" for k, v in PREFIX.items()}
_COMPOUND = re.compile(r"\s(or|and)\s|\s\+\s|/")


def split_top_commas(s: str) -> list[str]:
    out, depth, cur = [], 0, []
    i = 0
    while i < len(s):
        c = s[i]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth = max(0, depth - 1)
        if c == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def clean(s: str) -> str:
    s = s.strip()
    while s.endswith("."):
        s = s[:-1].rstrip()
    return s


_NONE = re.compile(r"^(none|no( direct| single)? equivalent\b.*)$", re.I | re.S)
_SENTENCE = re.compile(r"\.\s+[A-Z]")
EMPTY, NONE, PROSE, SERVICES = "empty", "explicit_none", "prose", "services"


def classify(text: str) -> str:
    t = clean(text)
    if not t:
        return EMPTY
    if _NONE.match(t):
        return NONE
    if any(_SENTENCE.search(seg) for seg in t.split(" ; ")):
        return PROSE
    return SERVICES


def split_cell(text: str) -> list[str]:
    if classify(text) != SERVICES:
        return []
    out = []
    for seg in text.split(" ; "):
        cur: list[str] = []
        for k, raw in enumerate(split_top_commas(seg)):
            p = clean(raw)
            if k > 0:
                p = re.sub(r"^(or|and)\s+", "", p)
            if not p:
                continue
            if k > 0 and p[0].islower() and cur:
                cur[-1] = clean(f"{cur[-1]},{raw}")
                continue
            cur.append(p)
        out += cur
    return out


def compound(label: str) -> bool:
    return bool(_COMPOUND.search(label))


def slug(label: str) -> str:
    s = label.lower().replace("&", " and ").replace("+", " plus ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        raise ValueError(f"rótulo sem caractere útil: {label!r}")
    return s


def service_id(provider: str, label: str) -> str:
    return f"{PREFIX[provider]}:{slug(label)}"
