"""Tipos e utilitários comuns aos extratores do PRIOR.

Um extrator lê o artefato de um modelo (entrada somente leitura ou download fixado) e devolve um `Extract`:
classes, propriedades e vínculos publicados pelo próprio modelo entre os seus termos e os do provedor. O extrator
não interpreta: só transcreve o que o artefato declara, com arquivo:linha. A codificação dos vínculos em SKOS segue
uma tabela fixa por construção nativa (ENCODING), igual para todos os modelos.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

PROVIDERS = ("aws", "google", "azurerm", "oci")

# Construção nativa -> (semantic_relation, leitura). 'broad': o sujeito (termo do provedor) é mais estreito que o
# objeto (termo neutro do modelo): "a skos:broadMatch b" = b mais amplo. 'close': o modelo diz que os campos
# correspondem, sem dizer se a correspondência é exata. 'related': o termo do modelo é preenchido por aquela
# operação da API, sem identidade de conceito.
ENCODING = {
    "owl:ClassAssertion": ("broad", "o indivíduo do provedor é declarado instância da classe do modelo"),
    "rdfs:subClassOf": ("broad", "a classe do provedor é declarada subclasse da classe do modelo"),
    "python:inheritance": ("broad", "o kind do provedor herda (direta ou transitivamente) do kind base"),
    "fix:mapping": ("close", "o kind do provedor preenche a propriedade herdada do kind base a partir deste caminho "
                             "da resposta da API"),
    "cartography:OntologyNodeMapping": ("broad", "o nó do módulo recebe o rótulo semântico da ontologia"),
    "cartography:OntologyFieldMapping": ("close", "o campo do nó do módulo alimenta o campo da ontologia"),
    "tosca:derived_from": ("broad", "o tipo do perfil do provedor deriva do tipo do perfil neutro"),
    "edmm:extends": ("broad", "o tipo de componente do provedor estende o tipo genérico"),
    "steampipe:hydrate_tag": ("related", "a tabela é preenchida pela ação de API declarada na etiqueta do List/Get"),
    "cloudquery:api_doc": ("related", "a página da tabela aponta para a documentação da operação da API"),
    "text:subclass": ("broad", "o texto do artigo diz que a classe atômica é subclasse da classe neutra"),
    "text:property_alignment": ("close", "o texto do artigo diz que os atributos são alinhados à propriedade "
                                         "generalizada"),
    "text:atomic_class": ("close", "o texto do artigo diz que o tipo Terraform gera a classe atômica"),
    "text:abstracts_over": ("broad", "o texto do artigo diz que a classe neutra abstrai aquele serviço do provedor"),
    "text:id_to_object_property": ("related","o texto do artigo diz que o atributo identificador vira a object "
                                              "property"),
    "sssom:NoTermFound": ("related", "ausência declarada: o modelo não publica vínculo com termos de provedor"),
}

TIERS = ("PUBLISHED", "DERIVED")


@dataclass
class Cls:
    id: str
    native: str
    label: str
    definition: str = ""
    parents: list = field(default_factory=list)
    provider: str = ""          # aws|google|azurerm|oci|other:<nome>|'' (neutro)
    source: str = ""
    line: int = 0
    evidence: str = "STRUCTURALLY_VALID"


@dataclass
class Prop:
    id: str
    native: str
    label: str
    kind: str                    # object|datatype|annotation
    domain: list = field(default_factory=list)
    domain_kind: str = ""        # declared|restriction|class_member|''
    range: str = ""
    definition: str = ""
    provider: str = ""
    source: str = ""
    line: int = 0
    evidence: str = "STRUCTURALLY_VALID"


@dataclass
class Link:
    subject: str
    object: str
    native_relation: str
    link_kind: str               # provider_class_to_model_class | provider_field_to_model_property |
    #                              model_term_to_provider_api | absence
    level: str                   # class|property|absence
    provider: str
    source: str
    line: int
    sentence: str
    subject_label: str = ""
    object_label: str = ""
    tier: str = "PUBLISHED"
    note: str = ""
    evidence: str = "UNRESOLVED"


@dataclass
class Extract:
    model: str
    classes: list = field(default_factory=list)
    props: list = field(default_factory=list)
    links: list = field(default_factory=list)
    prefixes: dict = field(default_factory=dict)
    files: list = field(default_factory=list)      # (rótulo portátil, Path) lidos
    notes: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    provider_terms: dict = field(default_factory=dict)   # população da métrica, quando não é "classes de provedor"
    provider_unit: str = ""


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def dl(model: str) -> Path:
    return bo_data() / "downloads" / f"prior-{model}"


def portable(p: Path) -> str:
    s = str(p)
    d = str(bo_data())
    return "$BO_DATA" + s[len(d):] if s.startswith(d + "/") else s


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def short_hash(*parts: str, n: int = 10) -> str:
    """Identificador curto e estável em base32 minúsculo (a-z, 2-7): com 10 caracteres não forma 12 dígitos
    seguidos, que o privacy_lint barra como possível id de conta."""
    d = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return base64.b32encode(d).decode("ascii").lower()[:n]


_CURIE_LOCAL = re.compile(r"[^A-Za-z0-9_.\-/#~]")


def local(s: str) -> str:
    """Parte local de CURIE: sem espaço nem caractere que quebre o TSV/CSV; mantém o nome legível."""
    return _CURIE_LOCAL.sub("_", s.strip())


def provider_of(token: str) -> str:
    t = token.lower()
    if t in ("aws", "amazon", "com.amazon.aws"):
        return "aws"
    if t in ("gcp", "google", "googlecloud", "com.google.cloud"):
        return "google"
    if t in ("azure", "azurerm", "microsoft", "com.microsoft.azure"):
        return "azurerm"
    if t in ("oci", "oracle"):
        return "oci"
    return f"other:{t}" if t else ""


def line_of(text: str, needle: str, start: int = 0) -> int:
    i = text.find(needle, start)
    return text.count("\n", 0, i) + 1 if i >= 0 else 0


def clean(s: str | None, n: int = 600) -> str:
    """Texto nativo em uma linha (para CSV/TSV), truncado com marca explícita."""
    if not s:
        return ""
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"
