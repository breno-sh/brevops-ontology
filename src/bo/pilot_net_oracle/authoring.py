"""Ferramentas de autoria das fixtures da fatia NET (calibração no repositório; retidas fora dele, seladas).

As funções aqui só montam configuração nativa e o gabarito de decomposição a partir de regras escritas à mão;
as RESPOSTAS (decisão por fluxo, veredito por tradução) são escritas à mão em cada fixture e conferidas
contra o avaliador (net_oracle) pelo build: divergência é erro de um dos dois e para o build.
Nada aqui lê mapeamento, glossário ou saída do pipeline.
"""
from __future__ import annotations

OCI_PROTO = {"tcp": "6", "udp": "17", "icmp": "1", "all": "all"}
AZ_PROTO = {"tcp": "Tcp", "udp": "Udp", "icmp": "Icmp", "all": "*"}
TARGET_IP = "10.0.1.10"


def R(direction, proto, ports, cidr, effect="allow", prio=None, stateless=None, name=None, src_ports=None,
      tags=None):
    """Regra escrita à mão. ports: (lo, hi) | None (todas) | 'sym:..'; cidr: str | lista | 'sym:..'."""
    return {"dir": direction, "proto": proto, "ports": ports, "cidr": cidr, "effect": effect, "prio": prio,
            "stateless": stateless, "name": name, "src_ports": src_ports, "tags": tags}


def F(fid, direction, proto, port, remote, target="vm1"):
    return {"flow_id": fid, "target": target, "direction": direction, "protocol": proto, "port": port,
            "remote": remote, "state": "new"}


def RET(fid, of, reply_port=49152, target="vm1"):
    return {"flow_id": fid, "target": target, "state": "return", "of": of, "reply_port": reply_port}


def E(value, why, code=None):
    d = {"value": value, "why": why}
    if code:
        d["code"] = code
    return d


def _cidr_list(c):
    return c if isinstance(c, list) else [c]


def _ports_str(p):
    if p is None:
        return "*"
    if isinstance(p, str):
        return p
    return str(p[0]) if p[0] == p[1] else f"{p[0]}-{p[1]}"


# ------------------------------------------------------------------ AWS

def aws(rules, *, separate=False, separate_type="aws_vpc_security_group", sg="web", attach=("web",),
        extra_sgs=(), sym_parent=False, vm="vm1"):
    res = []
    groups = {sg: [], **{g: [] for g in extra_sgs}}
    for r in rules:
        groups[r.get("sg", sg) if isinstance(r, dict) else sg].append(r)
    for g, rs in groups.items():
        vals = {"name": f"fx-{g}", "description": "fixture sintética"}
        if not separate:
            for d in ("ingress", "egress"):
                blocks = [_aws_block(r) for r in rs if r["dir"] == d]
                if blocks:
                    vals[d] = blocks
        res.append({"type": "aws_security_group", "name": g, "values": vals})
        if separate:
            for i, r in enumerate(rs):
                res.append(_aws_sep(r, g, i, separate_type, sym_parent))
    res.append({"type": "aws_instance", "name": vm,
                "values": {"vpc_security_group_ids": [f"ref:aws_security_group.{a}" for a in attach]}})
    return {"resources": res}


def _aws_block(r):
    lo, hi, proto = _aws_ports(r)
    b = {"from_port": lo, "to_port": hi, "protocol": proto}
    if r["cidr"] is not None:
        b["cidr_blocks"] = r["cidr"] if isinstance(r["cidr"], str) and r["cidr"].startswith("sym:") else _cidr_list(r["cidr"])
    return b


def _aws_ports(r):
    if r["proto"] == "all":
        return 0, 0, "-1"
    p = r["ports"]
    if isinstance(p, str):
        return p, p, r["proto"]
    if p is None:
        return 0, 65535, r["proto"]
    return p[0], p[1], r["proto"]


def _aws_sep(r, g, i, kind, sym_parent):
    lo, hi, proto = _aws_ports(r)
    parent = "sym:sg_id_not_resolved" if sym_parent else f"ref:aws_security_group.{g}"
    if kind == "aws_vpc_security_group":
        t = f"aws_vpc_security_group_{r['dir']}_rule"
        v = {"security_group_id": parent, "ip_protocol": proto, "cidr_ipv4": r["cidr"]}
        if proto != "-1":
            v.update({"from_port": lo, "to_port": hi})
    else:
        t = "aws_security_group_rule"
        v = {"type": r["dir"], "security_group_id": parent, "protocol": proto, "from_port": lo, "to_port": hi,
             "cidr_blocks": _cidr_list(r["cidr"])}
    return {"type": t, "name": r.get("name") or f"{g}_r{i + 1}", "values": v}


# ------------------------------------------------------------------ Google

def gcp(rules, *, vm_tags=("web",), vm="vm1", extra_vms=()):
    res = [{"type": "google_compute_network", "name": "net", "values": {"name": "fx-net", "auto_create_subnetworks": False}}]
    for i, r in enumerate(rules):
        v = {"name": f"fx-{r.get('name') or f'fw{i + 1}'}".replace("_", "-"), "network": "ref:google_compute_network.net",
             "direction": r["dir"].upper()}
        if r["prio"] is not None:
            v["priority"] = r["prio"]
        blk = {"protocol": r["proto"]}
        if r["proto"] in ("tcp", "udp") and r["ports"] is not None:
            blk["ports"] = [r["ports"]] if isinstance(r["ports"], str) else [_ports_str(r["ports"])]
        v[r["effect"]] = [blk]
        key = "source_ranges" if r["dir"] == "ingress" else "destination_ranges"
        v[key] = r["cidr"] if isinstance(r["cidr"], str) and r["cidr"].startswith("sym:") else _cidr_list(r["cidr"])
        tags = r.get("tags", ["web"]) if r.get("tags") is not None else ["web"]
        if tags != "none":
            v["target_tags"] = tags
        res.append({"type": "google_compute_firewall", "name": r.get("name") or f"fw{i + 1}", "values": v})
    for name, tags in ((vm, list(vm_tags)),) + tuple(extra_vms):
        res.append({"type": "google_compute_instance", "name": name,
                    "values": {"tags": tags, "network_interface": [{"network": "ref:google_compute_network.net"}]}})
    return {"resources": res}


# ------------------------------------------------------------------ Azure

def _az_rule(r, i):
    d = {"name": r.get("name") or f"rule{i + 1}", "priority": r["prio"],
         "direction": "Inbound" if r["dir"] == "ingress" else "Outbound",
         "access": "Allow" if r["effect"] == "allow" else "Deny", "protocol": AZ_PROTO[r["proto"]],
         "source_port_range": _ports_str(r["src_ports"]) if r["src_ports"] else "*",
         "destination_port_range": _ports_str(r["ports"]) if r["proto"] in ("tcp", "udp") else "*"}
    c = r["cidr"]
    c = "*" if c in ("0.0.0.0/0",) else c
    if r["dir"] == "ingress":
        d["source_address_prefix"], d["destination_address_prefix"] = c, "*"
    else:
        d["source_address_prefix"], d["destination_address_prefix"] = "*", c
    return d


def azure(rules, *, separate=False, assoc=("nic",), nsg="web", extra_nsgs=(), vm="vm1"):
    res = []
    groups = {nsg: [], **{g: [] for g in extra_nsgs}}
    for r in rules:
        groups[r.get("nsg", nsg)].append(r)
    for g, rs in groups.items():
        vals = {"name": f"fx-{g}", "location": "fixture", "resource_group_name": "fx-rg"}
        if not separate:
            vals["security_rule"] = [_az_rule(r, i) for i, r in enumerate(rs)]
        res.append({"type": "azurerm_network_security_group", "name": g, "values": vals})
        if separate:
            for i, r in enumerate(rs):
                v = _az_rule(r, i)
                v.update({"network_security_group_name": f"ref:azurerm_network_security_group.{g}",
                          "resource_group_name": "fx-rg"})
                res.append({"type": "azurerm_network_security_rule", "name": r.get("name") or f"{g}_rule{i + 1}", "values": v})
    res.append({"type": "azurerm_subnet", "name": "sa", "values": {"name": "fx-sa"}})
    res.append({"type": "azurerm_network_interface", "name": "nic1",
                "values": {"ip_configuration": [{"name": "ipc", "subnet_id": "ref:azurerm_subnet.sa"}]}})
    res.append({"type": "azurerm_linux_virtual_machine", "name": vm,
                "values": {"network_interface_ids": ["ref:azurerm_network_interface.nic1"]}})
    for a in assoc:
        kind, g = (a.split(":") + [nsg])[:2]
        if kind == "nic":
            res.append({"type": "azurerm_network_interface_security_group_association", "name": f"nic_{g}",
                        "values": {"network_interface_id": "ref:azurerm_network_interface.nic1",
                                   "network_security_group_id": f"ref:azurerm_network_security_group.{g}"}})
        else:
            res.append({"type": "azurerm_subnet_network_security_group_association", "name": f"sub_{g}",
                        "values": {"subnet_id": "ref:azurerm_subnet.sa",
                                   "network_security_group_id": f"ref:azurerm_network_security_group.{g}"}})
    return {"resources": res}


# ------------------------------------------------------------------ OCI

def _oci_rule(r, nsg_parent=None):
    d = {"protocol": OCI_PROTO[r["proto"]]}
    d["source" if r["dir"] == "ingress" else "destination"] = r["cidr"]
    if r["stateless"] is not None:
        d["stateless"] = r["stateless"]
    if r["proto"] in ("tcp", "udp") and (r["ports"] is not None or r["src_ports"]):
        key = "tcp_options" if r["proto"] == "tcp" else "udp_options"
        opt = {}
        if nsg_parent:
            if r["ports"] is not None:
                opt["destination_port_range"] = {"min": r["ports"][0], "max": r["ports"][1]}
        elif r["ports"] is not None:
            opt.update({"min": r["ports"][0], "max": r["ports"][1]})
        if r["src_ports"]:
            opt["source_port_range"] = {"min": r["src_ports"][0], "max": r["src_ports"][1]}
            if not nsg_parent and r["ports"] is None:
                opt = {"source_port_range": opt["source_port_range"]}
        d[key] = opt
    if nsg_parent:
        d.update({"network_security_group_id": nsg_parent, "direction": r["dir"].upper(),
                  ("source_type" if r["dir"] == "ingress" else "destination_type"): "CIDR_BLOCK"})
    return d


def oci(rules, *, kind="sl", sl="web", nsg="web", vm="vm1", both=False, sym_parent=False):
    res = []
    sl_rules = [r for r in rules if (r.get("set") or kind) == "sl"]
    nsg_rules = [r for r in rules if (r.get("set") or kind) == "nsg"]
    use_sl, use_nsg = kind == "sl" or both, kind == "nsg" or both
    if use_sl:
        res.append({"type": "oci_core_security_list", "name": sl, "values": {
            "compartment_id": "ref:oci_identity_compartment.fx", "vcn_id": "ref:oci_core_vcn.fx",
            "ingress_security_rules": [_oci_rule(r) for r in sl_rules if r["dir"] == "ingress"],
            "egress_security_rules": [_oci_rule(r) for r in sl_rules if r["dir"] == "egress"]}})
    if use_nsg:
        res.append({"type": "oci_core_network_security_group", "name": nsg, "values": {
            "compartment_id": "ref:oci_identity_compartment.fx", "vcn_id": "ref:oci_core_vcn.fx"}})
        parent = "sym:nsg_id_not_resolved" if sym_parent else f"ref:oci_core_network_security_group.{nsg}"
        for i, r in enumerate(nsg_rules):
            res.append({"type": "oci_core_network_security_group_security_rule", "name": r.get("name") or f"{nsg}_r{i + 1}",
                        "values": _oci_rule(r, parent)})
    res.append({"type": "oci_core_subnet", "name": "sa", "values": {
        "security_list_ids": [f"ref:oci_core_security_list.{sl}"] if use_sl else []}})
    vnic = {"subnet_id": "ref:oci_core_subnet.sa"}
    if use_nsg:
        vnic["nsg_ids"] = [f"ref:oci_core_network_security_group.{nsg}"]
    res.append({"type": "oci_core_instance", "name": vm, "values": {"create_vnic_details": vnic}})
    return {"resources": res}


INSTANCE = {"aws": "aws_instance", "google": "google_compute_instance", "azurerm": "azurerm_linux_virtual_machine",
            "oci": "oci_core_instance"}


def targets(provider, vms=("vm1",)):
    return {v: {"ref": f"{INSTANCE[provider]}.{v}", "ip": TARGET_IP if i == 0 else f"10.0.1.{11 + i}"}
            for i, v in enumerate(vms)}


# ------------------------------------------------------------------ gabarito de decomposição

def _occ(**kw):
    return {k: v for k, v in kw.items() if v is not None}


def decomposition(provider: str, config: dict) -> list:
    """Unidades esperadas (C19: ENTITY | COMPONENT | FACET | BINDING | UNKNOWN), escritas por tipo de recurso.

    Fonte: CMT-FW-P01 (conjunto = ENTITY; regra = COMPONENT do conjunto, com identidade de ocorrência, igual
    embutida ou separada) e as linhas de dono/identidade do SERVICE-EVIDENCE citadas em evidence.
    """
    res = config["resources"]
    out = []
    norm_port = lambda lo, hi: None if lo is None else f"{lo}-{hi}"
    for r in res:
        t, n, v = r["type"], r["name"], r["values"]
        a = f"{t}.{n}"
        if t == "aws_security_group":
            out.append({"domain_unit": "rule_set", "kind": "ENTITY", "parent": None, "occurrence": {"set": a},
                        "tf": {"resource_type": t}, "evidence": ["C24:CMT-FW-P01", "SE-aws-rouky47ej4w3me2k"]})
            for d in ("ingress", "egress"):
                for i, b in enumerate(v.get(d, []) or []):
                    out.append(_aws_rule_unit(a, d, b["protocol"], b.get("from_port"), b.get("to_port"),
                                              b.get("cidr_blocks"), {"resource_type": t, "block_path": d}))
        elif t in ("aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule", "aws_security_group_rule"):
            parent = v["security_group_id"]
            d = v.get("type") or ("ingress" if "ingress" in t else "egress")
            proto = v.get("ip_protocol") or v.get("protocol")
            cid = v.get("cidr_blocks") or ([v["cidr_ipv4"]] if v.get("cidr_ipv4") else None)
            if parent.startswith("sym:"):
                out.append({"domain_unit": "filter_rule", "kind": "COMPONENT", "parent": "UNKNOWN",
                            "occurrence": {"rule": a}, "tf": {"resource_type": t},
                            "evidence": ["C24:CMT-FW-P01", "C24:CMT-NIC-U02"], "unknown": ["owner"]})
                continue
            out.append(_aws_rule_unit(parent[4:], d, proto, v.get("from_port", 0 if proto == "-1" else None),
                                      v.get("to_port", 0 if proto == "-1" else None), cid, {"resource_type": t}))
        elif t == "aws_instance":
            for g in v.get("vpc_security_group_ids", []):
                out.append({"domain_unit": "attachment", "kind": "BINDING", "parent": None,
                            "occurrence": {"set": g[4:], "target": a}, "tf": {"resource_type": t, "block_path": "vpc_security_group_ids"},
                            "evidence": ["C24:CMT-FW-P05"]})
        elif t == "google_compute_network":
            out.append({"domain_unit": "rule_set", "kind": "ENTITY", "parent": None, "occurrence": {"set": a},
                        "tf": {"resource_type": t}, "evidence": ["C24:CMT-FW-P01"]})
        elif t == "google_compute_firewall":
            out.append({"domain_unit": "filter_rule", "kind": "COMPONENT", "accepted_kinds": ["COMPONENT", "ENTITY"],
                        "parent": v["network"][4:], "occurrence": {"name": v["name"]}, "tf": {"resource_type": t},
                        "evidence": ["C24:CMT-FW-P01", "SE-google-mhidfw4xa7sokciu", "SE-google-mjuxwfic7ez6bfii"],
                        "note": "o compromisso pede COMPONENT do conjunto; o dono publicado é o projeto e a identidade é projects/{project}/global/firewalls/{name}: ENTITY ligada à rede também é aceita"})
            if v.get("target_tags"):
                for tag in v["target_tags"]:
                    out.append({"domain_unit": "selection", "kind": "BINDING", "parent": None,
                                "occurrence": {"rule": v["name"], "label": tag}, "tf": {"resource_type": t, "block_path": "target_tags"},
                                "evidence": ["C24:CMT-FW-P05"]})
        elif t == "azurerm_network_security_group":
            out.append({"domain_unit": "rule_set", "kind": "ENTITY", "parent": None, "occurrence": {"set": a},
                        "tf": {"resource_type": t}, "evidence": ["C24:CMT-FW-P01", "SE-azurerm-zvfleucvpmt7gzna"]})
            for b in v.get("security_rule", []) or []:
                out.append({"domain_unit": "filter_rule", "kind": "COMPONENT", "parent": a, "occurrence": {"name": b["name"]},
                            "tf": {"resource_type": t, "block_path": "security_rule"},
                            "evidence": ["C24:CMT-FW-P01", "SE-azurerm-qvepgdtxoh7qzmyl", "SE-azurerm-xexh22d7kybt736y"]})
        elif t == "azurerm_network_security_rule":
            out.append({"domain_unit": "filter_rule", "kind": "COMPONENT", "parent": v["network_security_group_name"][4:],
                        "occurrence": {"name": v["name"]}, "tf": {"resource_type": t},
                        "evidence": ["C24:CMT-FW-P01", "SE-azurerm-qvepgdtxoh7qzmyl", "SE-azurerm-xexh22d7kybt736y"]})
        elif t in ("azurerm_network_interface_security_group_association", "azurerm_subnet_network_security_group_association"):
            end = v.get("network_interface_id") or v.get("subnet_id")
            out.append({"domain_unit": "attachment", "kind": "BINDING", "parent": None,
                        "occurrence": {"set": v["network_security_group_id"][4:], "target": end[4:]},
                        "tf": {"resource_type": t}, "evidence": ["C24:CMT-FW-P05"]})
        elif t in ("oci_core_security_list", "oci_core_network_security_group"):
            out.append({"domain_unit": "rule_set", "kind": "ENTITY", "parent": None, "occurrence": {"set": a},
                        "tf": {"resource_type": t},
                        "evidence": ["C24:CMT-FW-P01", "SE-oci-lq2gnnmrobz7ft7h" if "security_list" in t else "SE-oci-gm5xlnh42tjbc5ou"]})
            for key, d in (("ingress_security_rules", "ingress"), ("egress_security_rules", "egress")):
                for b in v.get(key, []) or []:
                    out.append(_oci_rule_unit(a, d, b, {"resource_type": t, "block_path": key}))
        elif t == "oci_core_network_security_group_security_rule":
            parent = v["network_security_group_id"]
            if parent.startswith("sym:"):
                out.append({"domain_unit": "filter_rule", "kind": "COMPONENT", "parent": "UNKNOWN",
                            "occurrence": {"rule": a}, "tf": {"resource_type": t},
                            "evidence": ["C24:CMT-FW-P01", "C24:CMT-NIC-U02"], "unknown": ["owner"]})
                continue
            out.append(_oci_rule_unit(parent[4:], v["direction"].lower(), v, {"resource_type": t}))
        elif t == "oci_core_subnet":
            for s in v.get("security_list_ids", []):
                out.append({"domain_unit": "attachment", "kind": "BINDING", "parent": None,
                            "occurrence": {"set": s[4:], "target": a}, "tf": {"resource_type": t, "block_path": "security_list_ids"},
                            "evidence": ["C24:CMT-FW-P05"]})
        elif t == "oci_core_instance":
            for g in (v.get("create_vnic_details") or {}).get("nsg_ids", []):
                out.append({"domain_unit": "attachment", "kind": "BINDING", "parent": None,
                            "occurrence": {"set": g[4:], "target": a}, "tf": {"resource_type": t, "block_path": "create_vnic_details.nsg_ids"},
                            "evidence": ["C24:CMT-FW-P05"]})
    return out


def _aws_rule_unit(parent, d, proto, lo, hi, cidrs, tf):
    return {"domain_unit": "filter_rule", "kind": "COMPONENT", "parent": parent,
            "occurrence": _occ(direction=d, protocol=str(proto), ports=None if lo is None else f"{lo}-{hi}",
                               remote=sorted(cidrs) if isinstance(cidrs, list) else cidrs),
            "tf": tf, "evidence": ["C24:CMT-FW-P01", "SE-aws-jyr4g6yuka5h7son"]}


def _oci_rule_unit(parent, d, b, tf):
    opts = b.get("tcp_options") or b.get("udp_options") or {}
    if "destination_port_range" in opts:
        ports = f"{opts['destination_port_range']['min']}-{opts['destination_port_range']['max']}"
    elif "min" in opts:
        ports = f"{opts['min']}-{opts['max']}"
    else:
        ports = None
    sp = opts.get("source_port_range")
    return {"domain_unit": "filter_rule", "kind": "COMPONENT", "parent": parent,
            "occurrence": _occ(direction=d, protocol=str(b["protocol"]), ports=ports,
                               src_ports=f"{sp['min']}-{sp['max']}" if sp else None,
                               remote=b.get("source") if d == "ingress" else b.get("destination"),
                               stateless=bool(b.get("stateless", False))),
            "tf": tf, "evidence": ["C24:CMT-FW-P01", "SE-oci-bp7mulbmn76camow"]}


# ------------------------------------------------------------------ montagem

def fixture(fid, split, case, polarity, provider, config, flows, decisions, *, summary, commitments, check,
            read=None, tgts=None, validity=None, vms=("vm1",), invariant_with=None):
    fx = {"schema": "bo.pilot_net.fixture/1", "fixture_id": fid, "split": split, "case": case,
          "polarity": polarity, "provider": provider, "summary": summary, "commitment_ids": list(commitments),
          "check": check, "config": config, "targets": tgts or targets(provider, vms),
          "read": read or {"completeness": "complete", "not_read": [], "withheld": []},
          "flows": flows,
          "expected": {"decisions": decisions, "validity": validity or {"value": "VALID"},
                       "decomposition": decomposition(provider, config)}}
    if invariant_with:
        fx["expected"]["decomposition_invariant_with"] = invariant_with
    return fx


def translation(cid, split, direction, polarity, source, target_cfg, declared_losses, verdict, *, why,
                counts=None, commitments=("CMT-FW-N01",), vms=("vm1",), tgts=None):
    """Caso de tradução: a fixture de origem (id) e uma configuração-alvo candidata, com o veredito esperado."""
    src_prov, tgt_prov = direction.split("->")
    return {"schema": "bo.pilot_net.translation_case/1", "case_id": cid, "split": split, "case": "NET-C10",
            "direction": direction, "polarity": polarity, "source_fixture": source,
            "target": {"provider": tgt_prov, "config": target_cfg, "targets": tgts or targets(tgt_prov, vms)},
            "declared_losses": declared_losses, "commitment_ids": list(commitments),
            "expected": {"verdict": verdict, "why": why, **(counts or {})}}
