"""Leitura das fixtures: configuração nativa de cada provedor (recursos Terraform como JSON) -> modelo neutro.

Formato da configuração: {"resources": [{"type": T, "name": N, "values": {...}}]}. Referência a outro recurso é a
string "ref:T.N"; valor simbólico (variável, saída computada, referência não resolvida) é "sym:<rótulo>".
Também lê as fixtures em vocabulário independente dos compromissos C24 (provider "neutral").
"""
from __future__ import annotations

from .model import (Flow, Network, Rule, RuleSet, Symbolic, Target, is_sym, parse_ports)

SUPPORTED = {
    "aws": ["aws_security_group", "aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule",
            "aws_security_group_rule", "aws_instance", "aws_network_interface"],
    "google": ["google_compute_firewall", "google_compute_network", "google_compute_instance"],
    "azurerm": ["azurerm_network_security_group", "azurerm_network_security_rule",
                "azurerm_network_interface_security_group_association",
                "azurerm_subnet_network_security_group_association", "azurerm_network_interface",
                "azurerm_linux_virtual_machine", "azurerm_subnet"],
    "oci": ["oci_core_security_list", "oci_core_network_security_group",
            "oci_core_network_security_group_security_rule", "oci_core_subnet", "oci_core_instance"],
}


class FixtureError(ValueError):
    pass


def _v(x):
    """Converte 'sym:...' em Symbolic; mantém o resto."""
    if isinstance(x, str) and x.startswith("sym:"):
        return Symbolic(x[4:])
    return x


def _ref(x):
    if isinstance(x, str) and x.startswith("ref:"):
        return x[4:]
    if isinstance(x, str) and x.startswith("sym:"):
        return Symbolic(x[4:])
    raise FixtureError(f"referência esperada, achei {x!r}")


def _cidrs(x):
    x = _v(x)
    if x is None:
        return []
    if is_sym(x):
        return x
    if isinstance(x, str):
        x = [x]
    return [_v(c) for c in x]


def _not_read(fx):
    return {(n["of"], n["what"]) for n in fx.get("read", {}).get("not_read", [])}


def _unread(addr, nr):
    return "INCOMPLETE_READ" if (addr, "rules") in nr else False


def _proto_num(p):
    p = _v(p)
    if is_sym(p):
        return p
    p = str(p).lower()
    return {"6": "tcp", "17": "udp", "1": "icmp", "-1": "all", "all": "all", "*": "all"}.get(p, p)


# ---------------------------------------------------------------- AWS

def _aws_ports(fp, tp, proto):
    fp, tp = _v(fp), _v(tp)
    if proto in ("all", "icmp"):
        return None
    if is_sym(fp) or is_sym(tp):
        return fp if is_sym(fp) else tp
    if fp is None and tp is None:
        return None
    return parse_ports(f"{fp}-{tp}")


def _aws(fx, net, res, nr):
    sets = {}
    for r in res:
        if r["type"] == "aws_security_group":
            addr = f"aws_security_group.{r['name']}"
            sid = f"aws:{addr}"
            sets[addr] = RuleSet(sid, "aws", "sg", "allow_only", origin=addr,
                                 rules_unread=_unread(addr, nr))
            pos = 0
            for d in ("ingress", "egress"):
                for i, b in enumerate(r["values"].get(d, []) or []):
                    pos += 1
                    proto = _proto_num(b.get("protocol"))
                    rid = f"{addr}.{d}[{i}]"
                    sets[addr].rules.append(Rule(
                        rid, sid, d, proto, _cidrs(b.get("cidr_blocks")),
                        dst_ports=_aws_ports(b.get("from_port"), b.get("to_port"), proto),
                        state=Symbolic(f"{rid}.state", "INCOMPLETE_READ") if (rid, "state_tracking") in nr else None,
                        text_position=pos, origin=addr, inline=True))
    pos = 1000
    for r in res:
        t = r["type"]
        if t in ("aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule", "aws_security_group_rule"):
            v = r["values"]
            addr = f"{t}.{r['name']}"
            sg = _ref(v.get("security_group_id"))
            unresolved = is_sym(sg) or sg not in sets
            if unresolved:
                net.notes.append(f"{addr}: security_group_id não resolvido (pertença UNKNOWN)")
            if t == "aws_security_group_rule":
                d = v.get("type")
                proto = _proto_num(v.get("protocol"))
                cid = _cidrs(v.get("cidr_blocks"))
            else:
                d = "ingress" if t.endswith("ingress_rule") else "egress"
                proto = _proto_num(v.get("ip_protocol"))
                cid = _cidrs(v.get("cidr_ipv4"))
            pos += 1
            for parent in (list(sets) if unresolved else [sg]):
                sets[parent].rules.append(Rule(f"{addr}@{parent}" if unresolved else addr, sets[parent].set_id, d, proto, cid,
                                               dst_ports=_aws_ports(v.get("from_port"), v.get("to_port"), proto),
                                               text_position=pos, origin=addr, inline=False,
                                               maybe_member="UNKNOWN_SYMBOLIC_INPUT" if unresolved else None))
    for s in sets.values():
        net.sets[s.set_id] = s
    return {a: s.set_id for a, s in sets.items()}


def _aws_targets(fx, net, res, nr, setmap):
    by = {f"{r['type']}.{r['name']}": r for r in res}
    for tid, spec in fx.get("targets", {}).items():
        inst = by.get(spec["ref"])
        if inst is None:
            raise FixtureError(f"alvo {tid}: {spec['ref']} não existe")
        t = Target(tid, ip=spec.get("ip"))
        groups = inst["values"].get("vpc_security_group_ids", []) or []
        groups = [groups] if isinstance(groups, str) else list(groups)
        for r in res:
            if r["type"] == "aws_network_interface":
                att = r["values"].get("attachment") or {}
                if att.get("instance") == f"ref:{spec['ref']}":
                    groups += r["values"].get("security_groups", []) or []
        for g in groups:
            g = _ref(g)
            if is_sym(g):
                t.maybe_sets.extend(setmap.values())
                t.maybe_code.update({x: "UNKNOWN_SYMBOLIC_INPUT" for x in setmap.values()})
            else:
                t.sets.append(setmap.get(g, f"aws:{g}"))
        if (spec["ref"], "attachment") in nr:
            t.maybe_sets.extend(s for s in setmap.values() if s not in t.sets)
        net.targets[tid] = t


# ---------------------------------------------------------------- Google

def _gcp(fx, net, res, nr):
    for r in res:
        if r["type"] == "google_compute_network":
            addr = f"google_compute_network.{r['name']}"
            net.sets[f"google:{addr}"] = RuleSet(f"google:{addr}", "google", "gcp_network", "priority_allow_deny",
                                                origin=addr, rules_unread=_unread(addr, nr))
    pos = 0
    for r in res:
        if r["type"] != "google_compute_firewall":
            continue
        v = r["values"]
        addr = f"google_compute_firewall.{r['name']}"
        nw = _ref(v.get("network"))
        sid = f"google:{nw}" if not is_sym(nw) else None
        if sid not in net.sets:
            net.notes.append(f"{addr}: rede não resolvida")
            for s in net.sets.values():
                s.rules_unread = s.rules_unread or "UNKNOWN_SYMBOLIC_INPUT"
            continue
        d = _v(v.get("direction"))
        d = d.lower() if isinstance(d, str) else (d if is_sym(d) else Symbolic(f"{addr}.direction", "MISSING_EVIDENCE"))
        pri = _v(v.get("priority"))
        lo, hi = 0, 65535
        if isinstance(pri, int) and not (lo <= pri <= hi):
            net.validity.append(("INVALID", "INCONSISTENT", f"{addr}: prioridade {pri} fora de 0-65535"))
        if d == "ingress":
            remote, local = _cidrs(v.get("source_ranges")), (None if v.get("destination_ranges") is None else _cidrs(v.get("destination_ranges")))
        elif d == "egress":
            remote, local = _cidrs(v.get("destination_ranges")), (None if v.get("source_ranges") is None else _cidrs(v.get("source_ranges")))
        else:
            remote, local = Symbolic(f"{addr}.ranges"), None
        tags = v.get("target_tags")
        sel = ("tags", _v(tags) if is_sym(_v(tags)) else list(tags)) if tags is not None else ("unspecified",)
        blocks = [("allow", b) for b in (v.get("allow") or [])] + [("deny", b) for b in (v.get("deny") or [])]
        if v.get("allow") and v.get("deny"):
            net.validity.append(("UNKNOWN", "MISSING_EVIDENCE", f"{addr}: allow e deny no mesmo recurso"))
        for i, (eff, b) in enumerate(blocks):
            pos += 1
            proto = _proto_num(b.get("protocol"))
            ports = None if proto not in ("tcp", "udp") else parse_ports([_v(x) for x in b["ports"]]) if b.get("ports") else None
            rid = f"{addr}.{eff}[{i}]"
            net.sets[sid].rules.append(Rule(rid, sid, d, proto, remote, dst_ports=ports, local=local, effect=eff,
                                            priority=pri, text_position=pos, origin=addr, inline=False, selector=sel))


def _gcp_targets(fx, net, res, nr):
    by = {f"{r['type']}.{r['name']}": r for r in res}
    for tid, spec in fx.get("targets", {}).items():
        inst = by[spec["ref"]]
        v = inst["values"]
        t = Target(tid, ip=spec.get("ip"), tags=list(v.get("tags") or []))
        for ni in v.get("network_interface", []) or []:
            nw = _ref(ni.get("network"))
            if is_sym(nw):
                t.maybe_sets.extend(net.sets)
                t.maybe_code.update({x: "UNKNOWN_SYMBOLIC_INPUT" for x in net.sets})
            else:
                t.sets.append(f"google:{nw}")
        net.targets[tid] = t


# ---------------------------------------------------------------- Azure

_AZ_DIR = {"inbound": "ingress", "outbound": "egress"}


def _az_prefixes(single, multi):
    vals = multi if multi else ([single] if single is not None else [])
    out = []
    for x in vals:
        x = _v(x)
        if is_sym(x):
            out.append(x)
        elif x == "*" or x == "0.0.0.0/0" or x == "Any":
            out.append("0.0.0.0/0")
        elif "/" in x or x.replace(".", "").isdigit():
            out.append(x if "/" in x else x + "/32")
        else:
            out.append(f"SERVICE_TAG:{x}")
    return out


def _az_rule(b, sid, rid, pos, inline):
    d = _AZ_DIR.get(str(b.get("direction", "")).lower(), Symbolic(f"{rid}.direction"))
    src = _az_prefixes(b.get("source_address_prefix"), b.get("source_address_prefixes"))
    dst = _az_prefixes(b.get("destination_address_prefix"), b.get("destination_address_prefixes"))
    def _pp(x):
        return parse_ports([_v(i) for i in x] if isinstance(x, list) else _v(x))
    sp = _pp(b.get("source_port_ranges") or b.get("source_port_range"))
    dp = _pp(b.get("destination_port_ranges") or b.get("destination_port_range"))
    remote, local = (src, dst) if d == "ingress" else (dst, src)
    local = None if local == ["0.0.0.0/0"] else local
    return Rule(rid, sid, d, _proto_num(b.get("protocol")), remote, dst_ports=dp, src_ports=sp, local=local,
                effect=str(b.get("access")).lower(), priority=_v(b.get("priority")), text_position=pos,
                origin=rid, inline=inline)


def _azure(fx, net, res, nr):
    pos = 0
    for r in res:
        if r["type"] == "azurerm_network_security_group":
            addr = f"azurerm_network_security_group.{r['name']}"
            sid = f"azurerm:{addr}"
            rs = RuleSet(sid, "azurerm", "azure_nsg", "priority_allow_deny", origin=addr,
                         rules_unread=_unread(addr, nr))
            for i, b in enumerate(r["values"].get("security_rule", []) or []):
                pos += 1
                rs.rules.append(_az_rule(b, sid, f"{addr}.security_rule[{i}]", pos, True))
            net.sets[sid] = rs
    for r in res:
        if r["type"] == "azurerm_network_security_rule":
            addr = f"azurerm_network_security_rule.{r['name']}"
            g = _ref(r["values"].get("network_security_group_name"))
            sid = f"azurerm:{g}" if not is_sym(g) else None
            pos += 1
            if sid in net.sets:
                net.sets[sid].rules.append(_az_rule(r["values"], sid, addr, pos, False))
                continue
            net.notes.append(f"{addr}: NSG não resolvido (pertença UNKNOWN)")
            for c in net.sets:
                ru = _az_rule(r["values"], c, f"{addr}@{c}", pos, False)
                ru.maybe_member = "UNKNOWN_SYMBOLIC_INPUT"
                net.sets[c].rules.append(ru)
    for rs in net.sets.values():
        seen = {}
        for ru in rs.rules:
            p = ru.priority
            if isinstance(p, int) and not (100 <= p <= 4096):
                net.validity.append(("INVALID", "INCONSISTENT", f"{ru.rule_id}: prioridade {p} fora de 100-4096"))
            if isinstance(p, int):
                for other_dir, other in seen.get(p, []):
                    if other_dir == ru.direction:
                        net.validity.append(("INVALID", "INCONSISTENT", f"{ru.rule_id} e {other}: prioridade {p} repetida na mesma direção"))
                    else:
                        from .semantics import param
                        uq = param("azurerm", "priority.unique")
                        if not uq.known:
                            net.validity.append(("UNKNOWN", "MISSING_EVIDENCE", f"{ru.rule_id} e {other}: prioridade {p} repetida em direções diferentes (unicidade sem evidência)"))
                        elif uq.value != "direction":
                            net.validity.append(("INVALID", "INCONSISTENT", f"{ru.rule_id} e {other}: prioridade {p} repetida no NSG"))
                seen.setdefault(p, []).append((ru.direction, ru.rule_id))


def _azure_targets(fx, net, res, nr):
    by = {f"{r['type']}.{r['name']}": r for r in res}
    nic_assoc, sub_assoc = {}, {}
    for r in res:
        v = r["values"]
        if r["type"] == "azurerm_network_interface_security_group_association":
            nic_assoc.setdefault(_ref(v["network_interface_id"]), []).append(_ref(v["network_security_group_id"]))
        if r["type"] == "azurerm_subnet_network_security_group_association":
            sub_assoc.setdefault(_ref(v["subnet_id"]), []).append(_ref(v["network_security_group_id"]))
    for tid, spec in fx.get("targets", {}).items():
        vm = by[spec["ref"]]
        t = Target(tid, ip=spec.get("ip"))
        for nic in vm["values"].get("network_interface_ids", []):
            nic = _ref(nic)
            for g in nic_assoc.get(nic, []):
                t.sets.append(f"azurerm:{g}")
            for ipc in by[nic]["values"].get("ip_configuration", []) or []:
                sn = _ref(ipc.get("subnet_id"))
                for g in sub_assoc.get(sn, []):
                    t.sets.append(f"azurerm:{g}")
            if (nic, "attachment") in nr:
                t.maybe_sets.extend(s for s in net.sets if s not in t.sets)
        net.targets[tid] = t


# ---------------------------------------------------------------- OCI

def _oci_range(o):
    if not o:
        return None
    return parse_ports(f"{o['min']}-{o['max']}")


def _oci_rule(b, sid, rid, d, pos, inline, nr):
    proto = _proto_num(b.get("protocol"))
    opts = b.get("tcp_options") or b.get("udp_options")
    dp = sp = None
    if opts:
        if "destination_port_range" in opts or "source_port_range" in opts:
            dp = _oci_range(opts.get("destination_port_range"))
        else:
            dp = _oci_range({"min": opts["min"], "max": opts["max"]}) if "min" in opts else None
        sp = _oci_range(opts.get("source_port_range"))
    remote = _cidrs(b.get("source") if d == "ingress" else b.get("destination"))
    st = _v(b.get("stateless", False))
    if (rid, "state_tracking") in nr:
        state = Symbolic(f"{rid}.stateless", "INCOMPLETE_READ")
    elif is_sym(st):
        state = st
    else:
        state = "stateless" if st else "stateful"
    return Rule(rid, sid, d, proto, remote, dst_ports=dp, src_ports=sp, state=state, text_position=pos,
                origin=rid, inline=inline)


def _oci(fx, net, res, nr):
    pos = 0
    for r in res:
        if r["type"] == "oci_core_security_list":
            addr = f"oci_core_security_list.{r['name']}"
            sid = f"oci:{addr}"
            rs = RuleSet(sid, "oci", "oci_security_list", "allow_only", origin=addr,
                         rules_unread=_unread(addr, nr))
            for d, key in (("ingress", "ingress_security_rules"), ("egress", "egress_security_rules")):
                for i, b in enumerate(r["values"].get(key, []) or []):
                    pos += 1
                    rs.rules.append(_oci_rule(b, sid, f"{addr}.{key}[{i}]", d, pos, True, nr))
            net.sets[sid] = rs
        if r["type"] == "oci_core_network_security_group":
            addr = f"oci_core_network_security_group.{r['name']}"
            net.sets[f"oci:{addr}"] = RuleSet(f"oci:{addr}", "oci", "oci_nsg", "allow_only", origin=addr,
                                             rules_unread=_unread(addr, nr))
    for r in res:
        if r["type"] == "oci_core_network_security_group_security_rule":
            v = r["values"]
            addr = f"oci_core_network_security_group_security_rule.{r['name']}"
            g = _ref(v.get("network_security_group_id"))
            sid = f"oci:{g}" if not is_sym(g) else None
            cands = [sid] if sid in net.sets else [k for k, s_ in net.sets.items() if s_.kind == "oci_nsg"]
            if sid not in net.sets:
                net.notes.append(f"{addr}: NSG não resolvido (pertença UNKNOWN)")
            pos += 1
            d = str(v.get("direction", "")).lower()
            for c in cands:
                ru = _oci_rule(v, c, addr if c == sid else f"{addr}@{c}", d, pos, False, nr)
                if c != sid:
                    ru.maybe_member = "UNKNOWN_SYMBOLIC_INPUT"
                net.sets[c].rules.append(ru)


def _oci_targets(fx, net, res, nr):
    by = {f"{r['type']}.{r['name']}": r for r in res}
    for tid, spec in fx.get("targets", {}).items():
        inst = by[spec["ref"]]["values"]
        t = Target(tid, ip=spec.get("ip"))
        vnic = inst.get("create_vnic_details", {}) or {}
        sn = _ref(vnic.get("subnet_id"))
        if not is_sym(sn):
            for sl in by[sn]["values"].get("security_list_ids", []) or []:
                sl = _ref(sl)
                if is_sym(sl):
                    t.maybe_sets.extend(net.sets)
                    t.maybe_code.update({x: "UNKNOWN_SYMBOLIC_INPUT" for x in net.sets})
                else:
                    t.sets.append(f"oci:{sl}")
        for g in vnic.get("nsg_ids", []) or []:
            g = _ref(g)
            if is_sym(g):
                t.maybe_sets.extend(net.sets)
                t.maybe_code.update({x: "UNKNOWN_SYMBOLIC_INPUT" for x in net.sets})
            else:
                t.sets.append(f"oci:{g}")
        if (spec["ref"], "attachment") in nr:
            t.maybe_sets.extend(s for s in net.sets if s not in t.sets)
        net.targets[tid] = t


# ---------------------------------------------------------------- neutro (compromissos C24)

def _neutral(fx):
    ents = {e["id"]: e for e in fx["entities"]}
    attrs: dict = {}
    for a in fx.get("attributes", []):
        attrs.setdefault(a["of"], {}).setdefault(a["attr"], []).append(a["value"])
    nr = _not_read(fx)
    net = Network("neutral")
    one = lambda i, k, d=None: (attrs.get(i, {}).get(k) or [d])[0]
    for i, e in ents.items():
        if e["kind"] == "rule_set":
            ev = one(i, "evaluation", "allow_only")
            ev = "priority_allow_deny" if ev == "priority_allow_deny" else "allow_only"
            ds = one(i, "default_state_tracking")
            net.sets[i] = RuleSet(i, "neutral", "neutral", ev, default_state=ds,
                                  rules_unread=_unread(i, nr), origin=i)
    for i, e in ents.items():
        states = set(attrs.get(i, {}).get("state_tracking", []))
        if e["kind"] == "filter_rule" and len(states) > 1:
            net.validity.append(("INVALID", "INCONSISTENT", f"{i}: estados de conexão {sorted(states)}"))
        if len(set([e["kind"]] + list(e.get("also_kinds", [])))) > 1:
            net.validity.append(("INVALID", "INCONSISTENT", f"{i}: tipos disjuntos"))
    pos = 0
    for rel in fx.get("relations", []):
        if rel["rel"] != "rule_in" or ents[rel["from"]]["kind"] != "filter_rule":
            continue
        r = rel["from"]
        pos += 1
        d = one(r, "direction")
        states = attrs.get(r, {}).get("state_tracking", [])
        # no vocabulário dos compromissos, estado não lido = não declarado: cai no padrão do conjunto, que
        # sem evidência é escolha MISSING_EVIDENCE (CMT-FW-U03)
        st = None if (r, "state_tracking") in nr else (states[0] if states else None)
        remote = one(r, "source_cidr") if d == "ingress" else one(r, "dest_cidr")
        port = one(r, "port")
        net.sets[rel["to"]].rules.append(Rule(
            r, rel["to"], d, one(r, "protocol", "all"), [remote] if remote else [],
            dst_ports=parse_ports(port) if port is not None else None, effect=one(r, "effect", "allow"),
            priority=one(r, "priority"), state=st,
            text_position=one(r, "text_position", pos), origin=r,
            inline=one(r, "declared_inline")))
    # alvo implícito: o fluxo atinge o alvo dos conjuntos (anexação ou rótulo, quando houver)
    t = Target("t", tags=[])
    t.sets = list(net.sets)
    net.targets["t"] = t
    flows = []
    for i, e in ents.items():
        if e["kind"] == "flow":
            d = one(i, "direction")
            remote = one(i, "source_cidr") if d == "ingress" else one(i, "dest_cidr")
            remote = remote.split("/")[0] if remote else None
            flows.append(Flow(i, "t", d, one(i, "protocol"), remote, port=one(i, "port")))
    return net, flows


def applies_neutral(fx) -> dict:
    """applies(rs) sob leitura completa: alvos por anexação ou por seleção de rótulo (CMT-FW-P05)."""
    ents = {e["id"]: e for e in fx["entities"]}
    out = {i: set() for i, e in ents.items() if e["kind"] == "rule_set"}
    rels = fx.get("relations", [])
    for r in rels:
        if r["rel"] == "attached_to" and r["from"] in out:
            out[r["from"]].add(r["to"])
        if r["rel"] == "targets_label" and r["from"] in out:
            out[r["from"]] |= {x["from"] for x in rels if x["rel"] == "has_label" and x["to"] == r["to"]}
    return out


# ---------------------------------------------------------------- entrada

def build(fx: dict):
    """fixture -> (Network, [Flow])."""
    prov = fx.get("provider")
    if prov == "neutral":
        return _neutral(fx)
    if prov not in SUPPORTED:
        raise FixtureError(f"provedor fora da fatia: {prov}")
    res = fx["config"]["resources"]
    for r in res:
        if r["type"] not in SUPPORTED[prov]:
            raise FixtureError(f"tipo fora da fatia {prov}: {r['type']}")
    nr = _not_read(fx)
    net = Network(prov)
    if prov == "aws":
        setmap = _aws(fx, net, res, nr)
        _aws_targets(fx, net, res, nr, setmap)
    elif prov == "google":
        _gcp(fx, net, res, nr)
        _gcp_targets(fx, net, res, nr)
    elif prov == "azurerm":
        _azure(fx, net, res, nr)
        _azure_targets(fx, net, res, nr)
    else:
        _oci(fx, net, res, nr)
        _oci_targets(fx, net, res, nr)
    _unresolved_sets(net)
    flows = [flow_from(f) for f in fx.get("flows", [])]
    return net, flows


_EVAL = {"aws": ("sg", "allow_only"), "google": ("gcp_network", "priority_allow_deny"),
         "azurerm": ("azure_nsg", "priority_allow_deny"), "oci": ("oci_security_list", "allow_only")}


def _unresolved_sets(net):
    """Conjunto referenciado pelo alvo mas ausente da configuração: regras desconhecidas (simbólico)."""
    for t in net.targets.values():
        for sid in t.sets + t.maybe_sets:
            if sid not in net.sets:
                kind, ev = _EVAL[net.provider]
                net.sets[sid] = RuleSet(sid, net.provider, kind, ev, rules_unread="UNKNOWN_SYMBOLIC_INPUT", origin=sid)
                net.notes.append(f"{sid}: referenciado e ausente da configuração")


def flow_from(f: dict) -> Flow:
    return Flow(f["flow_id"], f["target"], f.get("direction", ""), f.get("protocol", ""), f.get("remote", ""),
                port=_v(f.get("port")), state=f.get("state", "new"), of=f.get("of"),
                reply_port=_v(f.get("reply_port")), src_port=_v(f.get("src_port", 49152)))


def resolve_return_direction(flows: list) -> None:
    fm = {f.flow_id: f for f in flows}
    for f in flows:
        if f.state == "return":
            o = fm[f.of]
            f.direction = "egress" if o.direction == "ingress" else "ingress"
            f.protocol, f.remote = o.protocol, o.remote
