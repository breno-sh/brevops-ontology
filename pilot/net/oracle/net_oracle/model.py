"""Modelo neutro de filtragem de tráfego usado pelo oráculo (independente de mapeador e de ontologia).

Conjunto de regras, regra, alvo (por anexação ou seleção), direção, estado de conexão, precedência e efeito
ficam separados, como pede o REQ-NET-01. Um valor que não se sabe (simbólico, não lido, sem evidência) nunca
vira default: vira ponto de escolha (Choice) que o avaliador explora.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

ALLOW, DENY, UNKNOWN = "ALLOW", "DENY", "UNKNOWN"
DIRECTIONS = ("ingress", "egress")
PROTOCOLS = ("tcp", "udp", "icmp", "all")


class Symbolic:
    """Valor que só se conhece depois (variável, referência não resolvida, atributo não lido)."""

    def __init__(self, label: str, code: str = "UNKNOWN_SYMBOLIC_INPUT"):
        self.label = label
        self.code = code

    def __repr__(self):  # pragma: no cover - depuração
        return f"Symbolic({self.label})"


def is_sym(v) -> bool:
    return isinstance(v, Symbolic)


@dataclass
class PortRange:
    lo: int
    hi: int

    def contains(self, p: int) -> bool:
        return self.lo <= p <= self.hi


@dataclass
class Rule:
    rule_id: str
    set_id: str
    direction: object            # "ingress" | "egress" | Symbolic
    protocol: object             # "tcp" | "udp" | "icmp" | "all" | Symbolic
    remote: object               # lista de CIDR (str), [] = nada casa, ou Symbolic; "SERVICE_TAG:x" = etiqueta
    dst_ports: object = None     # None = qualquer porta; lista de PortRange; Symbolic
    src_ports: object = None     # idem (OCI e Azure filtram porta de origem)
    local: object = None         # None = qualquer endereço local; lista de CIDR; Symbolic
    effect: object = "allow"     # "allow" | "deny" | Symbolic
    priority: object = None      # int | None | Symbolic
    state: object = None         # "stateful" | "stateless" | None (herda o padrão do conjunto) | Symbolic
    text_position: int = 0
    origin: str = ""             # endereço Terraform (ou id neutro) de onde a regra veio
    inline: bool | None = None
    selector: object = None      # None = vale para o alvo do conjunto; ("tags", [..]); ("unspecified",)
    maybe_member: str | None = None  # regra separada cujo conjunto não se resolve: pertença é escolha (código)


@dataclass
class RuleSet:
    set_id: str
    provider: str
    kind: str                    # sg | gcp_network | azure_nsg | oci_security_list | oci_nsg | neutral
    evaluation: str              # allow_only | priority_allow_deny
    rules: list = field(default_factory=list)
    default_state: object = None  # "stateful" | "stateless" | None (sem evidência) | Symbolic
    rules_unread: bool = False   # leitura parcial: pode haver regras não lidas
    attachment_unread: bool = False
    origin: str = ""


@dataclass
class Target:
    target_id: str
    ip: str | None = None
    sets: list = field(default_factory=list)          # ids de conjuntos que se aplicam por anexação
    maybe_sets: list = field(default_factory=list)    # conjuntos cuja aplicação é desconhecida (escolha)
    maybe_code: dict = field(default_factory=dict)    # set_id -> código (INCOMPLETE_READ ou UNKNOWN_SYMBOLIC_INPUT)
    tags: list = field(default_factory=list)
    network: str | None = None


@dataclass
class Packet:
    direction: str               # relativo ao alvo
    protocol: str
    remote_ip: str
    dst_port: object             # int | None (icmp) | Symbolic
    src_port: object = None      # int | None | Symbolic
    local_ip: str | None = None


@dataclass
class Flow:
    flow_id: str
    target: str
    direction: str
    protocol: str
    remote: str
    port: object = None
    state: str = "new"           # new | return
    of: str | None = None        # para retorno: o fluxo original
    reply_port: object = None    # porta efêmera do lado que iniciou (destino do pacote de retorno)
    src_port: object = 49152     # porta de origem do fluxo novo: parte do fluxo sintético, não default de provedor


@dataclass
class Network:
    provider: str
    sets: dict = field(default_factory=dict)
    targets: dict = field(default_factory=dict)
    validity: list = field(default_factory=list)      # [(value, code, why)] VALID/INVALID/UNKNOWN
    notes: list = field(default_factory=list)


def cidr_contains(cidr: str, ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def parse_ports(spec) -> object:
    """'443', '8000-8080', 443, [..], '*', None -> lista de PortRange ou None (qualquer)."""
    if spec is None or spec == "*" or spec == "all":
        return None
    if is_sym(spec):
        return spec
    if isinstance(spec, (list, tuple)):
        out = []
        for s in spec:
            r = parse_ports(s)
            if r is None:
                return None
            if is_sym(r):
                return r
            out.extend(r)
        return out
    if isinstance(spec, int):
        return [PortRange(spec, spec)]
    s = str(spec).strip()
    if "-" in s:
        a, b = s.split("-", 1)
        return [PortRange(int(a), int(b))]
    return [PortRange(int(s), int(s))]
