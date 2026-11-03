"""Mundos sintéticos além do contêiner de objetos: interface de rede, regras de firewall, atribuição de acesso,
namespace com contêineres, banco com parâmetros e cópias, faceta com vários donos.

Cada mundo devolve {"provider", "schema", "evidence", "configs"}; os provedores são sintéticos (provider_b...).
"""

from __future__ import annotations

from .fixtures import blk, c, ev_aspect, ev_element, ev_entity, res


def _ref_fm(**fields):
    return {k: {"path": p, "ref": True} for k, p in fields.items()}


# ---------------------------------------------------------------------------------------------------------
# NIC: instância com interfaces; anexação como bloco embutido ou como recurso separado

def nic_world() -> dict:
    P = "provider_b"
    schema = {
        "b_instance": res(["name"], {"network_interface": blk(["network_interface_id", "device_index"],
                                                              nesting="list")}),
        "b_nic": res(["name", "subnet_id"]),
        "b_subnet": res(["name"]),
        "b_nic_attachment": res(["instance_id", "network_interface_id", "device_index"]),
    }
    attach_common = {
        "lifecycle_controller": [c(kind="self", tag="att")],
        "owner": [c(kind="self", tag="att")],
        "effective_scope": [c(kind="self", tag="att")],
        "api_resource": [c(status="resource", label="interface attachment", service="compute",
                           resource="InterfaceAttachment", tag="att")],
    }
    ev = {
        "b_instance": ev_entity("compute instance", "instance_name", "name", service="compute", tag="vm"),
        "b_subnet": ev_entity("subnet", "subnet_name", "name", service="network", tag="sn"),
        "b_nic": dict(ev_entity("network interface", "nic_name", "name", service="network", tag="nic",
                                extra_fm=_ref_fm(subnet="subnet_id")), references={"subnet": "b_subnet"}),
        # anexação embutida: identidade = (instância pelo pai estrutural, interface); índice é atributo da associação
        "b_instance.network_interface": dict(
            attach_common,
            identity=[c(status="present", scope="within_parent", key_fields=["interface"], tag="att")],
            element_name_key=[c(status="absent", tag="att")],
            field_map={**_ref_fm(interface="network_interface_id"),
                       "device_index": {"path": "device_index", "norm": "int", "config": True}},
            references={"interface": "b_nic"}, parent_role="instance"),
        # anexação separada: id opaco da API, chave de importação = (instância, interface)
        "b_nic_attachment": dict(
            attach_common,
            identity=[c(status="present", scope="independent", key_fields=["id"], surrogate=True, tag="att")],
            import_key=[c(status="present", fields=["instance", "interface"], tag="att")],
            field_map={**_ref_fm(instance="instance_id", interface="network_interface_id"),
                       "device_index": {"path": "device_index", "norm": "int", "config": True}},
            references={"instance": "b_instance", "interface": "b_nic"}),
    }

    def base(n_nics, inline, order=None):
        nics = [("nic1", "sa", 0), ("nic2", "sb", 1)][:n_nics]
        if order:
            nics = [nics[i] for i in order]
        rs = [{"type": "b_subnet", "name": "sa", "values": {"name": "subnet-a"}},
              {"type": "b_subnet", "name": "sb", "values": {"name": "subnet-b"}}]
        for nm, sn, _ in nics:
            rs.append({"type": "b_nic", "name": nm, "values": {"name": f"if-{nm}", "subnet_id":
                                                               {"$ref": f"b_subnet.{sn}"}}})
        vm = {"name": "vm-one"}
        if inline:
            vm["network_interface"] = [{"network_interface_id": {"$ref": f"b_nic.{nm}"}, "device_index": i}
                                       for nm, _, i in nics]
        rs.append({"type": "b_instance", "name": "vm1", "values": vm})
        if not inline:
            for nm, _, i in nics:
                rs.append({"type": "b_nic_attachment", "name": f"a{nm}", "values": {
                    "instance_id": {"$ref": "b_instance.vm1"}, "network_interface_id": {"$ref": f"b_nic.{nm}"},
                    "device_index": i}})
        return {"provider": P, "resources": rs}

    unresolved = base(1, False)
    for r in unresolved["resources"]:
        if r["type"] == "b_nic_attachment":
            r["values"]["network_interface_id"] = {"$unknown": "computed"}
    return {"provider": P, "schema": schema, "evidence": ev, "configs": {
        "inline_1": base(1, True), "inline_2": base(2, True), "separate_1": base(1, False),
        "separate_2": base(2, False), "inline_2_reordered": base(2, True, order=[1, 0]),
        "separate_unresolved": unresolved}}


# ---------------------------------------------------------------------------------------------------------
# Firewall: conjunto de regras; regra embutida (anônima, identidade por conteúdo) ou recurso separado

def firewall_world() -> dict:
    P = "provider_c"
    content = ["direction", "protocol", "port_range", "source"]
    norms = {"direction": "lower", "protocol": "lower", "port_range": "str", "source": "cidr"}
    schema = {
        "c_rule_set": res(["name"], {"rule": blk(["direction", "protocol", "ports", "cidr", "action"],
                                                 nesting="set")}),
        "c_rule": res(["rule_set_id", "direction", "protocol", "ports", "cidr", "action"]),
        "c_rule_from_set": res(["rule_set_id", "source_set_id", "direction", "protocol", "ports", "action"]),
    }
    paths = {"direction": "direction", "protocol": "protocol", "port_range": "ports", "source": "cidr"}

    def fm(extra=None):
        out = {k: {"path": paths[k], "norm": norms[k]} for k in content}
        out["action"] = {"path": "action", "norm": "lower", "config": True}
        out.update(extra or {})
        return out

    el = ev_element("network rule", None, None, {}, anonymous_fields=content, tag="fwr")
    el["field_map"] = fm()
    sep = ev_element("network rule", None, None, {}, anonymous_fields=content, via="rule_set",
                     ref_field="rule_set", ref_target="c_rule_set", tag="fwr")
    sep["field_map"] = fm(_ref_fm(rule_set="rule_set_id"))
    # regra cuja origem é outro conjunto: a chave tem duas referências e campos próprios; o dono é o conjunto
    content2 = ["direction", "protocol", "port_range"]
    frm = ev_element("network rule", None, None, {}, anonymous_fields=content2, via="rule_set",
                     ref_field="rule_set", ref_target="c_rule_set", tag="fwr2")
    frm["import_key"] = [c(status="present", fields=["rule_set", "source_set"] + content2, tag="fwr2")]
    frm["identity"] = [c(status="present", scope="within_parent", key_fields=content2 + ["source_set"],
                         anonymous=True, tag="fwr2")]
    frm["field_map"] = {**{k: {"path": paths[k], "norm": norms[k]} for k in content2},
                        "action": {"path": "action", "norm": "lower", "config": True},
                        **_ref_fm(rule_set="rule_set_id", source_set="source_set_id")}
    frm["references"] = {"rule_set": "c_rule_set", "source_set": "c_rule_set"}
    ev = {"c_rule_set": ev_entity("network rule set", "set_name", "name", service="network", tag="rs"),
          "c_rule_set.rule": el, "c_rule": sep, "c_rule_from_set": frm}
    rules = [("ingress", "tcp", "443", "10.0.0.0/8", "allow"), ("ingress", "tcp", "22", "192.168.1.0/24", "deny"),
             ("egress", "udp", "53", "0.0.0.0/0", "allow")]

    def inline(order=(0, 1, 2)):
        return {"provider": P, "resources": [{"type": "c_rule_set", "name": "rs1", "values": {
            "name": "set-one", "rule": [dict(zip(["direction", "protocol", "ports", "cidr", "action"], rules[i]))
                                        for i in order]}}]}

    def separate(order=(0, 1, 2)):
        rs = [{"type": "c_rule_set", "name": "rs1", "values": {"name": "set-one"}}]
        for i in order:
            d = dict(zip(["direction", "protocol", "ports", "cidr", "action"], rules[i]))
            d["rule_set_id"] = {"$ref": "c_rule_set.rs1"}
            rs.append({"type": "c_rule", "name": f"r{i}", "values": d})
        return {"provider": P, "resources": rs}

    from_set = {"provider": P, "resources": [
        {"type": "c_rule_set", "name": "rs1", "values": {"name": "set-one"}},
        {"type": "c_rule_set", "name": "rs2", "values": {"name": "set-two"}},
        {"type": "c_rule_from_set", "name": "x", "values": {
            "rule_set_id": {"$ref": "c_rule_set.rs1"}, "source_set_id": {"$ref": "c_rule_set.rs2"},
            "direction": "ingress", "protocol": "tcp", "ports": "5432", "action": "allow"}}]}
    # mesma regra (mesmo conteúdo normalizado) com CIDR escrito de outro jeito: é a mesma ocorrência
    alias = inline()
    alias["resources"][0]["values"]["rule"][0]["cidr"] = "10.1.2.3/8"
    return {"provider": P, "schema": schema, "evidence": ev, "configs": {
        "inline": inline(), "separate": separate(), "inline_reordered": inline((2, 0, 1)),
        "separate_reordered": separate((1, 2, 0)), "from_set": from_set, "inline_cidr_alias": alias}}


# ---------------------------------------------------------------------------------------------------------
# IAM: atribuição <principal, conjunto de permissões, escopo>

def iam_world() -> dict:
    P = "provider_d"
    schema = {"d_principal": res(["name"]), "d_role": res(["name"]), "d_project": res(["name"]),
              "d_assignment": res(["project_id", "role_id", "principal_id", "condition"])}
    ev = {
        "d_principal": ev_entity("principal", "principal_name", "name", service="iam", tag="pr"),
        "d_role": ev_entity("permission set", "role_name", "name", service="iam", tag="ro"),
        "d_project": ev_entity("scope", "project_name", "name", service="rm", tag="pj"),
        "d_assignment": {
            "identity": [c(status="absent", tag="as")],
            "import_key": [c(status="present", fields=["scope", "permission_set", "principal"], tag="as")],
            "lifecycle_controller": [c(kind="self", tag="as")],
            "owner": [c(kind="self", tag="as")],
            "effective_scope": [c(kind="container", via="scope", tag="as")],
            "api_resource": [c(status="resource", label="access assignment", service="iam", resource="Assignment",
                               tag="as")],
            "field_map": {**_ref_fm(scope="project_id", permission_set="role_id", principal="principal_id"),
                          "condition": {"path": "condition", "norm": "str", "config": True}},
            "references": {"scope": "d_project", "permission_set": "d_role", "principal": "d_principal"},
        },
    }
    cfg = {"provider": P, "resources": [
        {"type": "d_principal", "name": "p1", "values": {"name": "alice-example"}},
        {"type": "d_role", "name": "ps1", "values": {"name": "reader"}},
        {"type": "d_project", "name": "s1", "values": {"name": "proj-example"}},
        {"type": "d_assignment", "name": "a1", "values": {"project_id": {"$ref": "d_project.s1"},
                                                         "role_id": {"$ref": "d_role.ps1"},
                                                         "principal_id": {"$ref": "d_principal.p1"}}}]}
    return {"provider": P, "schema": schema, "evidence": ev, "configs": {"assignment": cfg}}


# ---------------------------------------------------------------------------------------------------------
# Namespace de armazenamento com contêineres (contêiner = componente do namespace) e configuração do namespace

def namespace_world() -> dict:
    P = "provider_e"
    schema = {
        "e_account": res(["name"], {"versioning": blk(["enabled"])}),
        "e_container": res(["account_id", "name"]),
        "e_container_setting": res(["container_id", "retention_days"]),
        "e_orphan_setting": res(["container_id", "flag"]),
    }
    cont = ev_element("object container", "container_name", "name", {}, via="account", ref_field="account",
                      ref_target="e_account", tag="ct")
    cont["api_resource"] = [c(status="resource", label="object container", service="objstore",
                              resource="Container", tag="ct")]
    ns_ver = ev_aspect("versioning", {"versioning": ("enabled", "bool")}, tag="nsv")
    ns_ver["effective_scope"] = [c(kind="container", tag="nsv")]
    setting = ev_aspect("retention", {"retention_days": ("retention_days", "int")}, via="container",
                        ref_field="container", ref_target="e_container", tag="ret")
    setting["field_map"]["container"]["path"] = "container_id"
    orphan = ev_aspect("flag", {"flag": ("flag", "bool")}, via="container", ref_field="container",
                       ref_target="e_container", tag="orf")
    orphan["field_map"]["container"]["path"] = "container_id"
    orphan.pop("lifecycle_controller")
    ev = {"e_account": ev_entity("storage namespace", "account_name", "name", service="objstore", tag="ns"),
          "e_account.versioning": ns_ver, "e_container": cont, "e_container_setting": setting,
          "e_orphan_setting": orphan}
    cont["field_map"]["account"]["path"] = "account_id"

    def cfg(container_ref=True):
        return {"provider": P, "resources": [
            {"type": "e_account", "name": "ns1", "values": {"name": "acct-example", "versioning": {"enabled": True}}},
            {"type": "e_container", "name": "c1", "values": {"account_id": {"$ref": "e_account.ns1"},
                                                             "name": "c-one"}},
            {"type": "e_container", "name": "c2", "values": {"account_id": {"$ref": "e_account.ns1"},
                                                             "name": "c-two"}},
            {"type": "e_container_setting", "name": "s1", "values": {
                "container_id": {"$ref": "e_container.c1"} if container_ref else {"$unknown": "computed"},
                "retention_days": 7}}]}
    return {"provider": P, "schema": schema, "evidence": ev,
            "configs": {"resolved": cfg(True), "unresolved": cfg(False)}}


# ---------------------------------------------------------------------------------------------------------
# Banco: retenção de backup é faceta; grupo de parâmetros e cópia manual são entidades

def db_world() -> dict:
    P = "provider_f"
    schema = {"f_db_instance": res(["name", "param_group_id"], {"backup": blk(["retention_days"])}),
              "f_param_group": res(["name", "family"]),
              "f_snapshot": res(["name", "source_instance_id"])}
    inst = ev_entity("db instance", "instance_name", "name", service="db", tag="dbi",
                     extra_fm=_ref_fm(param_group="param_group_id"))
    inst["references"] = {"param_group": "f_param_group"}
    snap = ev_entity("db snapshot", "snapshot_name", "name", service="db", tag="snp",
                     extra_fm=_ref_fm(source="source_instance_id"))
    snap["references"] = {"source": "f_db_instance"}
    ev = {"f_db_instance": inst,
          "f_db_instance.backup": ev_aspect("backup retention", {"retention_days": ("retention_days", "int")},
                                            tag="bkr"),
          "f_param_group": ev_entity("db parameter set", "group_name", "name", service="db", tag="pg"),
          "f_snapshot": snap}
    cfg = {"provider": P, "resources": [
        {"type": "f_param_group", "name": "ps1", "values": {"name": "pg-example", "family": "x1"}},
        {"type": "f_db_instance", "name": "i1", "values": {"name": "db-one", "param_group_id":
                                                           {"$ref": "f_param_group.ps1"}, "backup":
                                                           {"retention_days": 7}}},
        {"type": "f_db_instance", "name": "i3", "values": {"name": "db-three", "param_group_id":
                                                           {"$ref": "f_param_group.ps1"}}},
        {"type": "f_snapshot", "name": "b1", "values": {"name": "snap-one", "source_instance_id":
                                                        {"$ref": "f_db_instance.i1"}}}]}
    return {"provider": P, "schema": schema, "evidence": ev, "configs": {"db": cfg}}


# ---------------------------------------------------------------------------------------------------------
# Faceta com vários donos: fica no vínculo entre eles; sem vínculo, UNKNOWN com owner

def multi_owner_world(with_binding=True) -> dict:
    P = "provider_g"
    schema = {"g_network": res(["name"]), "g_peering": res(["left_id", "right_id"]),
              "g_exchange_setting": res(["left_id", "right_id", "export_routes"])}
    ev = {
        "g_network": ev_entity("network", "network_name", "name", service="network", tag="net"),
        "g_peering": {
            "identity": [c(status="absent", tag="peer")],
            "import_key": [c(status="present", fields=["left", "right"], tag="peer")],
            "lifecycle_controller": [c(kind="self", tag="peer")], "owner": [c(kind="self", tag="peer")],
            "effective_scope": [c(kind="self", tag="peer")],
            "api_resource": [c(status="resource", label="network peering", service="network", resource="Peering",
                               tag="peer")],
            "field_map": _ref_fm(left="left_id", right="right_id"),
            "references": {"left": "g_network", "right": "g_network"}},
        "g_exchange_setting": {
            "identity": [c(status="absent", tag="exs")],
            "import_key": [c(status="present", fields=["left"], tag="exs")],
            "lifecycle_controller": [c(kind="parent", via="left", tag="exs")],
            "owner": [c(kind="parent", via=["left", "right"], tag="exs")],
            "effective_scope": [c(kind="parent", via="left", tag="exs")],
            "api_resource": [c(status="aspect", label="route exchange", tag="exs")],
            "field_map": {**_ref_fm(left="left_id", right="right_id"),
                          "export_routes": {"path": "export_routes", "norm": "bool", "config": True}},
            "references": {"left": "g_network", "right": "g_network"}},
    }
    if not with_binding:
        schema.pop("g_peering")
        ev.pop("g_peering")
    return {"provider": P, "schema": schema, "evidence": ev, "configs": {}}


# ---------------------------------------------------------------------------------------------------------
# Balanceador: frontend, listeners, regras, pools, sonda, certificado; tudo embutido ou tudo separado

def lb_world() -> dict:
    P = "provider_h"
    schema = {
        "h_lb": res(["name"], {
            "frontend": blk(["name", "address"], nesting="list"),
            "listener": blk(["name", "port", "certificate_id"], {
                "rule": blk(["name", "path", "pool_name"], nesting="list")}, nesting="list"),
            "pool": blk(["name"], {"probe": blk(["path", "interval"])}, nesting="list")}),
        "h_listener": res(["lb_id", "name", "port", "certificate_id"]),
        "h_rule": res(["listener_id", "name", "path", "pool_id"]),
        "h_pool": res(["lb_id", "name"]),
        "h_probe": res(["pool_id", "path", "interval"]),
        "h_frontend": res(["lb_id", "name", "address"]),
        "h_certificate": res(["name"]),
    }

    def comp(label, cfg, ref_field=None, ref_target=None, ref_path=None, extra_refs=None, tag="lbc"):
        e = ev_element(label, "item_name", "name", cfg, via=ref_field, ref_field=ref_field, ref_target=ref_target,
                       tag=tag)
        e["api_resource"] = [c(status="resource", label=label, service="lb", resource=label.title()
                               .replace(" ", ""), tag=tag)]
        if ref_field:
            e["field_map"][ref_field]["path"] = ref_path
        for f, (path, tgt) in (extra_refs or {}).items():
            e["field_map"][f] = {"path": path, "ref": True}
            e.setdefault("references", {})[f] = tgt
        return e

    probe_cfg = {"probe_path": ("path", "str"), "interval": ("interval", "int")}
    ev = {
        "h_lb": ev_entity("load balancer", "lb_name", "name", service="lb", tag="lb"),
        "h_certificate": ev_entity("certificate", "cert_name", "name", service="cert", tag="crt"),
        "h_lb.frontend": comp("frontend", {"address": ("address", "str")}, tag="fe"),
        "h_lb.listener": comp("listener", {"port": ("port", "int")}, extra_refs={"certificate": ("certificate_id",
                                                                                                "h_certificate")},
                              tag="li"),
        "h_lb.listener.rule": comp("routing rule", {"route_path": ("path", "str")},
                                   extra_refs={"pool": ("pool_name", "h_lb.pool")}, tag="ru"),
        "h_lb.pool": comp("pool", {}, tag="po"),
        "h_lb.pool.probe": ev_aspect("health probe", probe_cfg, tag="hp"),
        "h_frontend": comp("frontend", {"address": ("address", "str")}, "lb", "h_lb", "lb_id", tag="fe"),
        "h_listener": comp("listener", {"port": ("port", "int")}, "lb", "h_lb", "lb_id",
                           extra_refs={"certificate": ("certificate_id", "h_certificate")}, tag="li"),
        "h_rule": comp("routing rule", {"route_path": ("path", "str")}, "listener", "h_listener", "listener_id",
                       extra_refs={"pool": ("pool_id", "h_pool")}, tag="ru"),
        "h_pool": comp("pool", {}, "lb", "h_lb", "lb_id", tag="po"),
        "h_probe": ev_aspect("health probe", probe_cfg, via="pool", ref_field="pool", ref_target="h_pool", tag="hp"),
    }
    ev["h_probe"]["field_map"]["pool"]["path"] = "pool_id"
    ev["h_lb.listener.rule"]["field_map"]["pool"]["by_name"] = True
    lis = [("l-https", 443, ["r-api", "r-web"]), ("l-http", 80, [])]
    rules = {"r-api": ("/api", "p-api"), "r-web": ("/", "p-web")}
    cert = {"type": "h_certificate", "name": "cert1", "values": {"name": "cert-example"}}

    def embedded():
        return {"provider": P, "resources": [cert, {"type": "h_lb", "name": "lb1", "values": {
            "name": "lb-one", "frontend": [{"name": "fe-1", "address": "10.0.0.10"}],
            "listener": [{"name": n, "port": p, "certificate_id": {"$ref": "h_certificate.cert1"} if p == 443 else None,
                          "rule": [{"name": r, "path": rules[r][0], "pool_name": rules[r][1]} for r in rs]}
                         for n, p, rs in lis],
            "pool": [{"name": "p-api", "probe": {"path": "/health", "interval": 10}}, {"name": "p-web"}]}}]}

    def separate():
        lb = {"$ref": "h_lb.lb1"}
        rs = [cert, {"type": "h_lb", "name": "lb1", "values": {"name": "lb-one"}},
              {"type": "h_frontend", "name": "fe", "values": {"lb_id": lb, "name": "fe-1", "address": "10.0.0.10"}},
              {"type": "h_pool", "name": "pa", "values": {"lb_id": lb, "name": "p-api"}},
              {"type": "h_pool", "name": "pw", "values": {"lb_id": lb, "name": "p-web"}},
              {"type": "h_probe", "name": "hp", "values": {"pool_id": {"$ref": "h_pool.pa"}, "path": "/health",
                                                          "interval": 10}}]
        for n, p, rr in lis:
            v = {"lb_id": lb, "name": n, "port": p}
            if p == 443:
                v["certificate_id"] = {"$ref": "h_certificate.cert1"}
            rs.append({"type": "h_listener", "name": n.replace("-", "_"), "values": v})
            for r in rr:
                rs.append({"type": "h_rule", "name": r.replace("-", "_"), "values": {
                    "listener_id": {"$ref": f"h_listener.{n.replace('-', '_')}"}, "name": r, "path": rules[r][0],
                    "pool_id": {"$ref": "h_pool.pa" if rules[r][1] == "p-api" else "h_pool.pw"}}})
        return {"provider": P, "resources": rs}
    return {"provider": P, "schema": schema, "evidence": ev,
            "configs": {"embedded": embedded(), "separate": separate()},
            "packagings": {"embedded": ["h_lb", "h_lb.frontend", "h_lb.listener", "h_lb.listener.rule", "h_lb.pool",
                                        "h_lb.pool.probe", "h_certificate"],
                           "separate": ["h_lb", "h_frontend", "h_listener", "h_rule", "h_pool", "h_probe",
                                        "h_certificate"]}}


ALL = {"nic": nic_world, "lb": lb_world, "firewall": firewall_world, "iam": iam_world, "namespace": namespace_world,
       "db": db_world, "multi_owner": multi_owner_world}
