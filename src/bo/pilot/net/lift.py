"""Lifting: configuração de uma fixture (recursos Terraform como JSON) -> indivíduos neutros (ABox) e unidades.

A leitura é estrutural e não raciocina: separa conjunto, regra, anexação, seleção e ponto de anexação, guarda o valor
CRU de cada átomo (é ele que atravessa por alegação, nos três controles) e o valor neutro pelo codec do vocab (para o
raciocínio e para a comparação). O que a construção diz sem átomo (sentido pelo bloco ingress{}, efeito pelo bloco
allow{}) entra como fato ESTRUTURAL (origin = "structure"): só os controles c2 e c3 o enxergam.

Valor simbólico ("sym:x") fica simbólico; parte não lida (read.not_read) fica marcada; referência que não resolve
vira pertença desconhecida. Nenhum valor é completado.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from . import vocab as V

SYM, UNREAD, ABSENT = "symbolic", "unread", "absent"


@dataclass
class Fact:
    value: object                 # valor neutro (ou None quando simbólico/ausente)
    raw: object = None            # valor como escrito na fixture
    status: str = "known"         # known | symbolic | unread | absent
    atom: str | None = None       # provider:tipo:caminho (sem índice) quando veio de átomo
    origin: str = "atom"          # atom | structure | entailed | synthesized
    evidence: list = field(default_factory=list)
    label: str | None = None      # rótulo do símbolo

    def known(self) -> bool:
        return self.status == "known"


@dataclass
class Rule:
    rid: str
    provider: str
    set_id: str | None
    member: str                   # known | symbolic
    tf: dict
    facts: dict = field(default_factory=dict)       # propriedade neutra -> Fact
    atoms: dict = field(default_factory=dict)       # atom_id -> (valor cru, caminho na fixture)
    matches: list = field(default_factory=list)     # [{"protocol": Fact, "dst_ports": Fact, "effect": Fact|None}]
    position: int = 0


@dataclass
class RuleSet:
    sid: str
    provider: str
    kind: str                     # tipo Terraform
    tf: dict
    name: Fact | None = None
    rules: list = field(default_factory=list)
    unread: bool = False          # leitura parcial (pode haver regra não lida)
    symbolic_member: bool = False  # alguma regra com pertença simbólica


@dataclass
class Attachment:
    set_id: str | None
    endpoint: str
    status: str                   # known | symbolic | unread
    tf: dict


@dataclass
class Selection:
    rule_id: str
    labels: Fact
    tf: dict


@dataclass
class Endpoint:
    eid: str                      # alvo abstrato do fluxo (vm1) ou endereço
    address: str
    provider: str
    ip: str | None
    tags: list = field(default_factory=list)
    network: str | None = None
    attach_unread: bool = False


@dataclass
class Lifted:
    fixture_id: str
    provider: str
    sets: dict = field(default_factory=dict)
    rules: dict = field(default_factory=dict)
    attachments: list = field(default_factory=list)
    selections: list = field(default_factory=list)
    endpoints: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)   # recursos fora da fatia e do contexto conhecido

    def rules_of(self, sid):
        return [self.rules[r] for r in self.sets[sid].rules]


# --------------------------------------------------------------------------------------------- utilidades

def is_sym(v) -> bool:
    return isinstance(v, str) and v.startswith("sym:")


def is_ref(v) -> bool:
    return isinstance(v, str) and v.startswith("ref:")


def ref_of(v):
    return v[4:] if is_ref(v) else None


def hid(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:10]


def atom_id(provider, rtype, path) -> str:
    return f"{provider}:{rtype}:{path}"


def _get(values: dict, path: str):
    cur = values
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


_KEEP = object()


def raw_fact(provider, rtype, path, raw, neutral=_KEEP, *, unread=False) -> Fact:
    """neutral=_KEEP: o valor neutro é o próprio cru; qualquer outro valor (inclusive None = 'qualquer') é o neutro."""
    a = atom_id(provider, rtype, path)
    if unread:
        return Fact(None, raw, UNREAD, a)
    if raw is None:
        return Fact(None, None, ABSENT, a)
    if is_sym(raw):
        return Fact(None, raw, SYM, a, label=raw[4:])
    if isinstance(raw, list) and any(is_sym(x) for x in raw):
        return Fact(None, raw, SYM, a, label=",".join(x[4:] for x in raw if is_sym(x)))
    return Fact(raw if neutral is _KEEP else neutral, raw, "known", a)


def ports_of(lo, hi):
    """(from, to) crus -> [(lo, hi)] ou None (qualquer) ou símbolo."""
    if is_sym(lo) or is_sym(hi):
        return SYM
    if lo is None and hi is None:
        return None
    return [(int(lo), int(hi))]


def parse_port_text(spec):
    """'443' | '8000-8080' | '*' | [..] -> [(lo, hi)] ou None."""
    if spec is None or spec == "*" or spec == []:
        return None
    if is_sym(spec):
        return SYM
    if isinstance(spec, (list, tuple)):
        out = []
        for s in spec:
            r = parse_port_text(s)
            if r is None:
                return None
            if r == SYM:
                return SYM
            out.extend(r)
        return out
    s = str(spec)
    if "-" in s:
        a, b = s.split("-", 1)
        return [(int(a), int(b))]
    return [(int(s), int(s))]


def _cidr_list(raw):
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for x in raw:
        if x in ("*", "Any", "Internet"):
            out.append("0.0.0.0/0" if x != "Internet" else f"SERVICE_TAG:{x}")
        elif "/" in str(x):
            out.append(str(x))
        elif str(x).replace(".", "").isdigit():
            out.append(f"{x}/32")
        else:
            out.append(f"SERVICE_TAG:{x}")
    return out


# --------------------------------------------------------------------------------------------- por provedor

def lift(fx: dict) -> Lifted:
    prov = fx["provider"]
    L = Lifted(fx["fixture_id"], prov)
    res = fx["config"]["resources"]
    nr = {(n["of"], n["what"]) for n in fx.get("read", {}).get("not_read", [])}
    by = {f"{r['type']}.{r['name']}": r for r in res}
    known_types = (set(V.RULE_SETS[prov]) | set(V.STANDALONE_RULES.get(prov, {})) | set(V.ENDPOINT_TYPES[prov])
                   | {t for t, _ in V.ATTACH_FIELDS[prov]} | set(V.ATTACH_RESOURCES.get(prov, {}))
                   | {"azurerm_network_interface", "azurerm_subnet", "oci_core_subnet", "aws_network_interface"})
    for r in res:
        if r["type"] not in known_types:
            L.unsupported.append(f"{r['type']}.{r['name']}")
    pos = 0
    # conjuntos
    for addr, r in by.items():
        spec = V.RULE_SETS[prov].get(r["type"])
        if spec is None:
            continue
        sid = f"set_{hid(prov, addr)}"
        s = RuleSet(sid, prov, r["type"], {"address": addr, "resource_type": r["type"]},
                    unread=(addr, "rules") in nr)
        nm = r["values"].get(spec["name"])
        if nm is not None:
            s.name = raw_fact(prov, r["type"], spec["name"], nm)
        L.sets[sid] = s
    set_by_addr = {s.tf["address"]: sid for sid, s in L.sets.items()}
    # regras embutidas
    for addr, r in by.items():
        for (stype, block), spec in V.INLINE_RULES.get(prov, {}).items():
            if r["type"] != stype:
                continue
            for i, b in enumerate(r["values"].get(block) or []):
                pos += 1
                rule = _rule(L, prov, stype, block, b, spec, set_by_addr[addr], "known",
                             {"address": addr, "resource_type": stype, "block_path": block, "index": i,
                              "rule_address": f"{addr}.{block}[{i}]"}, pos, nr)
                L.rules[rule.rid] = rule
                L.sets[set_by_addr[addr]].rules.append(rule.rid)
    # regras em recurso separado
    for addr, r in by.items():
        spec = V.STANDALONE_RULES.get(prov, {}).get(r["type"])
        if spec is None:
            continue
        pos += 1
        pv = r["values"].get(spec["parent"])
        if prov == "azurerm" and pv is not None and not is_ref(pv) and not is_sym(pv):
            # o NSG é referido pelo nome: resolve pelo nome do conjunto na mesma configuração
            hits = [sid for sid, s in L.sets.items() if s.name and s.name.raw == pv]
            parent = hits[0] if len(hits) == 1 else None
        else:
            pa = ref_of(pv)
            if pa and pa.endswith(".name"):
                pa = pa[:-5]
            if pa and pa.endswith(".id"):
                pa = pa[:-3]
            parent = set_by_addr.get(pa) if pa else None
        member = "known" if parent else "symbolic"
        rule = _rule(L, prov, r["type"], None, r["values"], spec, parent, member,
                     {"address": addr, "resource_type": r["type"], "rule_address": addr}, pos, nr)
        L.rules[rule.rid] = rule
        if parent:
            L.sets[parent].rules.append(rule.rid)
        else:
            L.notes.append(f"{addr}: conjunto da regra não resolvido (pertença simbólica)")
            for s in L.sets.values():
                s.symbolic_member = True
        if prov == "google" and r["values"].get("target_tags") is not None:
            tags = r["values"]["target_tags"]
            L.selections.append(Selection(rule.rid, raw_fact(prov, r["type"], "target_tags", tags),
                                          {"address": addr, "resource_type": r["type"], "block_path": "target_tags"}))
    _endpoints(L, fx, by, nr, set_by_addr)
    return L


def _rule(L, prov, rtype, block, b, spec, set_id, member, tf, pos, nr) -> Rule:
    prefix = f"{block}." if block else ""
    rid = f"rule_{hid(prov, tf['rule_address'])}"
    rule = Rule(rid, prov, set_id, member, tf, position=pos)
    unread_state = (tf["rule_address"], "state_tracking") in nr
    f = spec["fields"]
    for prop, path in f.items():
        raw = b.get(path)
        rule.atoms[atom_id(prov, rtype, prefix + path)] = raw
    # sentido
    if spec.get("direction"):
        ev = V.STRUCTURAL_EVIDENCE.get((prov, rtype, block, "direction")) or ["C03:" + rtype]
        rule.facts["direction"] = Fact(spec["direction"], None, "known", None, "structure", ev)
    elif "direction" in f:
        raw = b.get(f["direction"])
        neu = V.DIRECTION_IN.get(prov, {}).get(raw) if isinstance(raw, str) else None
        if prov == "aws" and isinstance(raw, str):
            neu = raw
        rule.facts["direction"] = raw_fact(prov, rtype, prefix + f["direction"], raw, neu)
    d = rule.facts["direction"].value
    # prioridade, nome, estado, efeito
    if "priority" in f:
        rule.facts["priority"] = raw_fact(prov, rtype, prefix + f["priority"], b.get(f["priority"]))
    if "name" in f:
        rule.facts["name"] = raw_fact(prov, rtype, prefix + f["name"], b.get(f["name"]))
    if "stateless" in f:
        raw = b.get(f["stateless"])
        if unread_state:
            rule.facts["stateless"] = raw_fact(prov, rtype, prefix + f["stateless"], raw, unread=True)
        else:
            rule.facts["stateless"] = raw_fact(prov, rtype, prefix + f["stateless"], raw,
                                               bool(raw) if raw is not None and not is_sym(raw) else None)
    if "effect" in f:
        raw = b.get(f["effect"])
        rule.facts["effect"] = raw_fact(prov, rtype, prefix + f["effect"], raw, V.EFFECT_IN.get(prov, {}).get(raw))
    # alcance remoto e local
    if prov == "azurerm":
        src = _first(b, f, "src_range")
        dst = _first(b, f, "dst_range")
        srcf = raw_fact(prov, rtype, prefix + src[0], src[1], _cidr_list(src[1]) if not _symish(src[1]) else None)
        dstf = raw_fact(prov, rtype, prefix + dst[0], dst[1], _cidr_list(dst[1]) if not _symish(dst[1]) else None)
        rf, lf = (srcf, dstf) if d == "ingress" else (dstf, srcf)
        rule.facts["remote"] = rf
        if lf.known() and lf.value == ["0.0.0.0/0"]:
            lf = Fact(None, lf.raw, ABSENT, lf.atom)
        rule.facts["local"] = lf
        sp = _first(b, f, "src_ports")
        dp = _first(b, f, "dst_ports")
        rule.facts["src_ports"] = raw_fact(prov, rtype, prefix + sp[0], sp[1],
                                           parse_port_text(sp[1]) if not _symish(sp[1]) else None)
        rule.matches.append({"protocol": raw_fact(prov, rtype, prefix + f["protocol"], b.get(f["protocol"]),
                                                  V.proto_in(prov, b.get(f["protocol"]))),
                             "dst_ports": raw_fact(prov, rtype, prefix + dp[0], dp[1],
                                                   parse_port_text(dp[1]) if not _symish(dp[1]) else None)})
    elif prov == "google":
        rp = f["src_range"] if d == "ingress" else f["dst_range"]
        lp = f["dst_range"] if d == "ingress" else f["src_range"]
        rule.facts["remote"] = raw_fact(prov, rtype, rp, b.get(rp), _cidr_list(b.get(rp)) if not _symish(b.get(rp)) else None)
        lv = b.get(lp)
        rule.facts["local"] = (Fact(None, None, ABSENT, atom_id(prov, rtype, lp)) if lv is None
                               else raw_fact(prov, rtype, lp, lv, _cidr_list(lv) if not _symish(lv) else None))
        for eff, blk in spec["match_blocks"].items():
            for i, m in enumerate(b.get(blk) or []):
                ev = V.STRUCTURAL_EVIDENCE[(prov, rtype, blk, "effect")]
                proto = m.get("protocol")
                ports = m.get("ports")
                rule.atoms[atom_id(prov, rtype, f"{blk}.protocol")] = proto
                rule.atoms[atom_id(prov, rtype, f"{blk}.ports")] = ports
                rule.matches.append({
                    "effect": Fact(eff, None, "known", None, "structure", ev),
                    "protocol": raw_fact(prov, rtype, f"{blk}.protocol", proto, V.proto_in(prov, proto)),
                    "dst_ports": raw_fact(prov, rtype, f"{blk}.ports", ports,
                                          parse_port_text(ports) if not _symish(ports) else None)
                    if ports is not None else Fact(None, None, ABSENT, atom_id(prov, rtype, f"{blk}.ports"))})
        effs = {m["effect"].value for m in rule.matches}
        if len(effs) == 1:
            rule.facts["effect"] = rule.matches[0]["effect"]
    elif prov == "oci":
        if "remote" in f:
            rp = f["remote"]
        else:
            rp = f["remote_in"] if d == "ingress" else f["remote_out"]
        rule.facts["remote"] = raw_fact(prov, rtype, prefix + rp, b.get(rp),
                                        _cidr_list(b.get(rp)) if not _symish(b.get(rp)) else None)
        rule.facts["local"] = Fact(None, None, ABSENT, None)
        proto = b.get(f["protocol"])
        opts_key = "tcp_options" if b.get("tcp_options") else "udp_options" if b.get("udp_options") else None
        opts = b.get(opts_key) or {}
        dpr = opts.get("destination_port_range") or ({"min": opts["min"], "max": opts["max"]} if "min" in opts else None)
        spr = opts.get("source_port_range")
        if opts_key and "destination_port_range" in opts:
            dpath = f"{prefix}{opts_key}.destination_port_range"
        else:
            dpath = f"{prefix}{opts_key or 'tcp_options'}"
        dports = None if dpr is None else ports_of(dpr.get("min"), dpr.get("max"))
        rule.atoms[atom_id(prov, rtype, dpath + ".min")] = dpr.get("min") if dpr else None
        rule.atoms[atom_id(prov, rtype, dpath + ".max")] = dpr.get("max") if dpr else None
        rule.matches.append({"protocol": raw_fact(prov, rtype, prefix + f["protocol"], proto, V.proto_in(prov, proto)),
                             "dst_ports": Fact(dports if dports != SYM else None, dpr, SYM if dports == SYM else
                                               ("known" if dpr else ABSENT), atom_id(prov, rtype, dpath + ".min"))})
        if spr:
            rule.atoms[atom_id(prov, rtype, f"{prefix}{opts_key}.source_port_range.min")] = spr.get("min")
            rule.atoms[atom_id(prov, rtype, f"{prefix}{opts_key}.source_port_range.max")] = spr.get("max")
            sp = ports_of(spr.get("min"), spr.get("max"))
            rule.facts["src_ports"] = Fact(sp if sp != SYM else None, spr, SYM if sp == SYM else "known",
                                           atom_id(prov, rtype, f"{prefix}{opts_key}.source_port_range.min"))
        else:
            rule.facts["src_ports"] = Fact(None, None, ABSENT, None)
    else:  # aws
        proto = b.get(f["protocol"])
        neu = V.proto_in(prov, proto)
        lo, hi = b.get(f["port_from"]), b.get(f["port_to"])
        ports = None if neu in ("all", "icmp") else ports_of(lo, hi)
        rule.facts["remote"] = raw_fact(prov, rtype, prefix + f["remote"], b.get(f["remote"]),
                                        _cidr_list(b.get(f["remote"])) if not _symish(b.get(f["remote"])) else None)
        rule.facts["local"] = Fact(None, None, ABSENT, None)
        rule.facts["src_ports"] = Fact(None, None, ABSENT, None)
        rule.matches.append({"protocol": raw_fact(prov, rtype, prefix + f["protocol"], proto, neu),
                             "dst_ports": Fact(ports if ports != SYM else None, [lo, hi],
                                               SYM if ports == SYM else "known",
                                               atom_id(prov, rtype, prefix + f["port_from"]))})
    return rule


def _symish(v) -> bool:
    return is_sym(v) or (isinstance(v, list) and any(is_sym(x) for x in v))


def _first(b, f, key):
    """Azure: campo singular ou plural (prefixes/ranges): devolve (caminho, valor) do que estiver presente."""
    one, many = f[key], f.get(key + "_multi")
    if many and b.get(many):
        return many, b.get(many)
    return one, b.get(one)


def _endpoints(L, fx, by, nr, set_by_addr):
    prov = L.provider
    targets = fx.get("targets", {})
    for tid, spec in targets.items():
        addr = spec["ref"]
        r = by.get(addr)
        e = Endpoint(tid, addr, prov, spec.get("ip"), attach_unread=(addr, "attachment") in nr)
        L.endpoints[tid] = e
        if r is None:
            L.notes.append(f"alvo {tid}: {addr} ausente da configuração")
            continue
        v = r["values"]
        if prov == "aws":
            groups = v.get("vpc_security_group_ids") or []
            groups = [groups] if isinstance(groups, str) else list(groups)
            for ni_addr, ni in by.items():
                if ni["type"] == "aws_network_interface" and (ni["values"].get("attachment") or {}).get("instance") == f"ref:{addr}":
                    groups += ni["values"].get("security_groups") or []
            for g in groups:
                _attach(L, set_by_addr, g, tid, {"resource_type": r["type"], "block_path": "vpc_security_group_ids",
                                                 "address": addr})
        elif prov == "google":
            e.tags = list(v.get("tags") or [])
            for ni in v.get("network_interface") or []:
                nw = ref_of(ni.get("network"))
                e.network = nw
                if nw in set_by_addr:
                    L.attachments.append(Attachment(set_by_addr[nw], tid, "known",
                                                    {"resource_type": r["type"], "block_path": "network_interface.network",
                                                     "address": addr}))
                else:
                    L.attachments.append(Attachment(None, tid, SYM, {"resource_type": r["type"], "address": addr}))
        elif prov == "azurerm":
            for nic in v.get("network_interface_ids") or []:
                nic = ref_of(nic)
                for aaddr, a in by.items():
                    if a["type"] == "azurerm_network_interface_security_group_association" and \
                            ref_of(a["values"].get("network_interface_id")) == nic:
                        _attach(L, set_by_addr, a["values"].get("network_security_group_id"), tid,
                                {"resource_type": a["type"], "address": aaddr, "via": nic})
                for ipc in (by.get(nic, {}).get("values", {}).get("ip_configuration") or []):
                    sn = ref_of(ipc.get("subnet_id"))
                    for aaddr, a in by.items():
                        if a["type"] == "azurerm_subnet_network_security_group_association" and \
                                ref_of(a["values"].get("subnet_id")) == sn:
                            _attach(L, set_by_addr, a["values"].get("network_security_group_id"), tid,
                                    {"resource_type": a["type"], "address": aaddr, "via": sn})
                if (nic, "attachment") in nr:
                    e.attach_unread = True
        elif prov == "oci":
            vnic = v.get("create_vnic_details") or {}
            sn = ref_of(vnic.get("subnet_id"))
            if sn and sn in by:
                for sl in by[sn]["values"].get("security_list_ids") or []:
                    _attach(L, set_by_addr, sl, tid, {"resource_type": "oci_core_subnet",
                                                      "block_path": "security_list_ids", "address": sn})
            for g in vnic.get("nsg_ids") or []:
                _attach(L, set_by_addr, g, tid, {"resource_type": r["type"], "block_path": "create_vnic_details.nsg_ids",
                                                 "address": addr})


def _attach(L, set_by_addr, raw, tid, tf):
    if is_sym(raw) or raw is None:
        L.attachments.append(Attachment(None, tid, SYM, dict(tf, symbol=raw[4:] if is_sym(raw) else None)))
        return
    a = ref_of(raw)
    if a and a.endswith(".id"):
        a = a[:-3]
    sid = set_by_addr.get(a)
    if sid is None:
        L.attachments.append(Attachment(None, tid, SYM, dict(tf, missing=a)))
        L.notes.append(f"{tf['address']}: conjunto {a} referido e ausente da configuração")
    else:
        L.attachments.append(Attachment(sid, tid, "known", tf))
