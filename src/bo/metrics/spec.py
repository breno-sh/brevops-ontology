"""Ligação entre o pré-registro (prereg/metrics_spec.yaml) e a implementação.

Cada uma das 28 métricas tem um Binding: eixo, leitura, quantificador, pesos e incerteza (iguais aos do spec,
conferidos por `check_spec`), a tabela de desfechos (policy) e o tipo de cálculo (`kind`). O spec é texto
normativo; a biblioteca não decide nada que ele não diga. Se o spec mudar (sha diferente do congelado no
PREREG.html), `load_spec(strict=True)` reprova: emenda do pré-registro exige rever a biblioteca.

Sementes: seed = int(sha256(UTF-8('brevops-prereg-v3/' + NOME)).hexdigest(), 16) mod 2147483647 (PREREG §12).
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import policy as P

SPEC_SHA256 = "7462e43de6cddd29848b3817c0633cd7dca82085c6b955ca5eff8c95f7703f86"  # PREREG.html, arquivos irmãos
N_BOOT = 4000
N_PERM = 10000
LEVEL = 0.95
SMALL_CLUSTER = 30  # menos de 30 famílias numa célula: IC t com CR2 (R3-M5)
PROVIDERS = ("aws", "google", "azurerm", "oci")
CLAUSES = ("Definição", "População", "Direção", "Unidade", "Denominador", "Desconhecido")


def repo_root() -> Path:
    env = os.environ.get("BO_REPO")
    if env and (Path(env) / "prereg" / "metrics_spec.yaml").is_file():
        return Path(env)
    return Path(__file__).resolve().parents[3]


def spec_path() -> Path:
    return repo_root() / "prereg" / "metrics_spec.yaml"


def seed(name: str) -> int:
    return int(hashlib.sha256(("brevops-prereg-v3/" + name).encode("utf-8")).hexdigest(), 16) % 2147483647


SEED_BOOT = seed("SEED-BOOT")
SEED_PERM = seed("SEED-PERM")


def directions(providers=PROVIDERS) -> list[tuple[str, str]]:
    return [(a, b) for a in providers for b in providers if a != b]


def direction_key(a: str, b: str | None) -> str:
    return a if b is None else f"{a}->{b}"


# ------------------------------------------------------------------------------------------------- bindings
@dataclass(frozen=True)
class Binding:
    metric_id: str
    name: str
    axis: str
    reading: str
    quantifier: str
    weights: str
    uncertainty: str
    kind: str                      # proportion | complex_fraction | product | ... (core.reading_for)
    table: dict = field(hash=False, compare=False)
    unknown: frozenset = frozenset()
    directional: bool = True
    only_oci: bool = False
    correlated_with: tuple = ()


def _b(mid, name, axis, reading, quantifier, weights, uncertainty, kind, table, unknown, **kw):
    return Binding(mid, name, axis, reading, quantifier, weights, uncertainty, kind, table, frozenset(unknown), **kw)


_OP = P.operational_table()
_OPS = [  # (id, nome) das métricas operacionais por decisão que seguem M-OPCOV-DEC
    ("M-OPCOV-DEC-DIRECT", "cobertura do caminho direto par-a-par"),
    ("M-OPCOV-DEC-C1", "cobertura do controle c1 (tabela sem inferência)"),
    ("M-OPCOV-DEC-C2", "cobertura do controle c2 (taxonomia e realizações)"),
    ("M-ABL-SEEDAWS-DEC", "ablação: semente só AWS"),
    ("M-ABL-THR-ALT1-DEC", "ablação: primeiro limiar alternativo de admissão"),
    ("M-ABL-THR-ALT2-DEC", "ablação: segundo limiar alternativo de admissão"),
    ("M-ABL-RAWTYPES-DEC", "ablação: tipos Terraform crus"),
    ("M-ABL-NOGUARD-DEC", "ablação: sem guardas e sem transformações"),
    ("M-ABL-AWSRAW-DEC", "ablação conjunta: semente só AWS com tipos crus (H6)"),
    ("M-H2H-TRANS-DEC", "eixo de tradução de cada comparador (orçamento igual)"),
    ("M-TOOL-LLM-DEC", "acerto do LLM com prompt congelado (suplementar)"),
]

BINDINGS: dict[str, Binding] = {}
for _x in [
    _b("M-REPR-DEC", "representabilidade por decisão", "representability", "decision", "observed_fraction",
       "uniform", "bootstrap", "proportion", P.representability_table(), P.UNK_REPR, directional=False),
    _b("M-TRANS-DEC-EXIST", "transportabilidade existencial por decisão", "transportability", "decision",
       "existential", "uniform", "bootstrap", "proportion", P.transport_table(False), P.UNK_TRANS_SCHEMA),
    _b("M-TRANS-DEC-UNIV", "transportabilidade universal por decisão", "transportability", "decision",
       "universal", "uniform", "bootstrap", "proportion", P.transport_table(False), P.UNK_TRANS_SCHEMA),
    _b("M-TRANS-DEC-OBS", "transportabilidade no uso observado", "transportability", "decision",
       "observed_fraction", "uniform", "bootstrap", "proportion", P.transport_table(True), P.UNK_TRANS_OBS),
    _b("M-OPCOV-DEC", "cobertura operacional por decisão (principal)", "operational", "decision",
       "observed_fraction", "uniform", "bootstrap", "proportion", _OP, P.UNK_OP),
    _b("M-OPCOV-FIELD", "cobertura operacional por campo", "operational", "field", "observed_fraction",
       "uniform", "bootstrap", "proportion", _OP, P.UNK_OP),
    _b("M-OPCOV-GRAPH", "cobertura operacional por grafo", "operational", "graph", "observed_fraction",
       "uniform", "bootstrap", "proportion", P.graph_table(), P.UNK_OP),
    _b("M-OPCOV-UNIT", "cobertura operacional por unidade implantável completa", "operational",
       "complete_unit", "observed_fraction", "uniform", "bootstrap", "proportion", P.unit_table(), P.UNK_UNIT),
    _b("M-OPCOV-NAMETAG", "cobertura operacional de NAME e TAG (leitura própria)", "operational", "field",
       "observed_fraction", "uniform", "bootstrap", "proportion", _OP, P.UNK_OP),
    *[_b(i, n, "operational", "decision", "observed_fraction", "uniform", "bootstrap", "proportion", _OP,
         P.UNK_OP) for i, n in _OPS],
    _b("M-OPCOV-DEC-COMPLEX", "fração da cobertura via correspondência complexa", "operational", "decision",
       "observed_fraction", "uniform", "bootstrap", "complex_fraction", _OP, P.UNK_OP),
    _b("M-LOPO-OPCOV-DEC", "cobertura com a ontologia sem OCI (leave-one-provider-out)", "operational",
       "decision", "observed_fraction", "uniform", "bootstrap", "proportion", _OP, P.UNK_OP, only_oci=True),
    _b("M-PERS-DEC", "precisão de persistência", "persistence", "decision", "observed_fraction",
       "inverse_probability", "bootstrap", "proportion", P.persistence_table(), P.UNK_PERS),
    _b("M-OPCOV-PERS-DEC", "leitura combinada: emitida e persistida", "persistence", "decision",
       "observed_fraction", "frame", "bootstrap", "product", {}, P.UNK_OP | P.UNK_PERS,
       correlated_with=("M-OPCOV-DEC", "M-PERS-DEC")),
    _b("M-BEHAV-DEC", "observações coincidentes sob protocolo", "behavior", "decision", "observed_fraction",
       "inverse_probability", "wilson", "proportion", P.behavior_table(), P.UNK_BEHAV),
    _b("M-HOLDOUT-REPR-DEC", "hold-out de unidades: representação às cegas", "representability", "decision",
       "observed_fraction", "uniform", "bootstrap", "proportion", P.representability_table(), P.UNK_REPR,
       directional=False),
    _b("M-LOPO-REPR-DEC", "LOPO: representação da OCI sem OCI", "representability", "decision",
       "observed_fraction", "uniform", "bootstrap", "proportion", P.representability_table(), P.UNK_REPR,
       directional=False, only_oci=True),
    _b("M-CQ-ANSWER", "respostas corretas das CQs congeladas", "representability", "graph", "observed_fraction",
       "uniform", "exact", "proportion", P.cq_table(), P.UNK_CQ, directional=False),
]:
    BINDINGS[_x.metric_id] = _x

# códigos que a cláusula "Desconhecido" nomeia, por métrica, quando o nome da biblioteca difere do texto
# (TIMEOUT = "consulta que não termina" na M-CQ-ANSWER; a combinada herda os desconhecidos dos dois fatores)
SPEC_NAMED_ALIASES = {"M-CQ-ANSWER": {"TIMEOUT": "consulta que não termina"},
                      "M-OPCOV-PERS-DEC": {"UNKNOWN_SYMBOLIC_INPUT": "M-OPCOV-DEC", "UNKNOWN_INPUT": "M-OPCOV-DEC",
                                           "CONDITION_INDETERMINATE": "M-OPCOV-DEC"}}


# ------------------------------------------------------------------------------------------------- spec
class SpecError(ValueError):
    pass


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_spec(path: Path | None = None, strict: bool = True) -> dict:
    path = Path(path or spec_path())
    if strict and file_sha256(path) != SPEC_SHA256:
        raise SpecError(f"{path}: sha256 diferente do congelado no PREREG ({SPEC_SHA256[:12]}…); emenda exige "
                        "rever a biblioteca")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if doc.get("schema") != "bo.metrics_spec/1" or doc.get("contract") != "C15":
        raise SpecError(f"{path}: não é um metrics_spec C15")
    return doc


def clauses(definition: str) -> dict[str, str]:
    out = {}
    for part in definition.split(" | "):
        k, _, v = part.partition(": ")
        out[k.strip()] = v.strip()
    return out


def inclusion_rule(inclusion: str) -> tuple[str, str]:
    m = re.match(r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+): (.{5,})$", inclusion, re.S)
    if not m:
        raise SpecError(f"inclusão sem rule_id: {inclusion[:40]}")
    return m.group(1), m.group(2)


def named_unknown_codes(unknown_clause: str) -> set[str]:
    """Códigos em maiúsculas (enumerações) que a cláusula Desconhecido cita como bounded.

    Tira os trechos que a cláusula declara como falha nos dois limites ("... não transporta nos dois limites",
    "... é falha nos dois limites", "... os demais códigos ..."), para sobrar só o que fica no intervalo."""
    text = unknown_clause
    # cortes por frase: o que vem depois de ';' e diz "nos dois limites" sem "limite superior" é falha definida
    keep = []
    for sent in re.split(r";", text):
        s = sent.strip()
        if ("dois limites" in s or "nos dois" in s or "não transportam" in s or "fora da base" in s or "falha definida" in s
                or "errada nos dois" in s or "reprova" in s) and "limite superior" not in s:
            continue
        if s.startswith("est =") or s.startswith("limite superior = produto") or s.startswith("os demais"):
            continue
        keep.append(s)
    codes = set(re.findall(r"(?<![-\w])[A-Z][A-Z_]{4,}\b", " ".join(keep)))
    return {c for c in codes if c not in {"NAME", "TAG"}}


def check_spec(doc: dict) -> list[str]:
    """Toda métrica do spec tem binding com os mesmos campos; nenhum binding fora do spec; cada métrica
    tem as seis cláusulas; os códigos bounded do binding são os que a cláusula Desconhecido nomeia."""
    errs = []
    ids = [m["metric_id"] for m in doc["metrics"]]
    for mid in sorted(set(BINDINGS) - set(ids)):
        errs.append(f"{mid}: binding sem métrica no spec")
    for m in doc["metrics"]:
        mid = m["metric_id"]
        b = BINDINGS.get(mid)
        if b is None:
            errs.append(f"{mid}: métrica do spec sem implementação")
            continue
        for k in ("axis", "reading", "quantifier", "weights", "uncertainty"):
            if getattr(b, k) != m[k]:
                errs.append(f"{mid}: {k} = {getattr(b, k)} na biblioteca, {m[k]} no spec")
        cl = clauses(m["definition"])
        for c in CLAUSES:
            if not cl.get(c):
                errs.append(f"{mid}: cláusula {c} ausente")
        try:
            inclusion_rule(m["inclusion"])
        except SpecError as e:
            errs.append(f"{mid}: {e}")
        named = named_unknown_codes(cl.get("Desconhecido", ""))
        aliases = SPEC_NAMED_ALIASES.get(mid, {})
        lib = {c for c in b.unknown}
        lib_named = {c for c in lib if c not in aliases}
        if mid == "M-OPCOV-DEC-COMPLEX":
            continue  # a base exclui os desconhecidos; os limites tratam todos como simples/complexos
        if lib_named != named - set(aliases):
            errs.append(f"{mid}: desconhecidos {sorted(lib_named)} na biblioteca, {sorted(named)} no spec")
        for c, phrase in aliases.items():
            if c in lib and phrase not in cl.get("Desconhecido", ""):
                errs.append(f"{mid}: {c} sem a frase '{phrase}' na cláusula")
    return errs


def spec_by_id(doc: dict) -> dict[str, dict]:
    return {m["metric_id"]: m for m in doc["metrics"]}
