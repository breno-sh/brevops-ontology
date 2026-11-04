"""Plano de lowering (C26) -> HCL pelos renderizadores dos HARNESS-* (sem inserção silenciosa) e HCL relido
(python-hcl2, parser independente do renderizador) -> configuração no formato do oráculo.

Renderizar é dos HARNESS-*: este módulo só os chama pela API pública de cada um e guarda o texto, o estado
(RENDERED | UNKNOWN_INPUT | INVALID_PLAN | ...) e os problemas. A conversão HCL -> oráculo:
  * referência ${tipo.rótulo.attr} -> "ref:tipo.rótulo"; variável ${var.x} -> "sym:x";
  * fica só o que o oráculo lê (adapters.SUPPORTED); o contexto fora da fatia que o renderizador escreve (grupo de
    recursos, rede virtual, VCN) é descartado, e o ponto de anexação vira o alvo do fluxo por uma regra declarada:
      aws      aws_network_interface_sg_attachment(var.X, sg)  -> aws_network_interface(attachment.instance = alvo,
               security_groups = [...]) + aws_instance alvo
      azurerm  interface do ponto -> azurerm_linux_virtual_machine alvo com network_interface_ids = [interface]
      oci      sub-rede do ponto -> oci_core_instance alvo com create_vnic_details.subnet_id = sub-rede
      google   a instância renderizada é o alvo
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import hcl2

REF = re.compile(r"^\$\{([a-z][a-z0-9_]*)\.([A-Za-z0-9_\-]+)(?:\.([A-Za-z0-9_.]+))?\}$")
VAR = re.compile(r"^\$\{var\.([A-Za-z0-9_\-]+)\}$")
SUPPORTED = {
    "aws": ["aws_security_group", "aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule",
            "aws_security_group_rule", "aws_instance", "aws_network_interface"],
    "google": ["google_compute_firewall", "google_compute_network", "google_compute_instance"],
    "azurerm": ["azurerm_network_security_group", "azurerm_network_security_rule",
                "azurerm_network_interface_security_group_association", "azurerm_subnet_network_security_group_association",
                "azurerm_network_interface", "azurerm_linux_virtual_machine", "azurerm_subnet"],
    "oci": ["oci_core_security_list", "oci_core_network_security_group",
            "oci_core_network_security_group_security_rule", "oci_core_subnet", "oci_core_instance"],
}


def _jsonl(rows) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def render_provider(provider: str, cases: list, work: Path) -> dict:
    """cases: [CaseOut TRANSLATED do provedor]. Devolve plan_id -> {status, problems, files{nome: texto}, root}."""
    work.mkdir(parents=True, exist_ok=True)
    inp = work / "in"
    if inp.exists():
        shutil.rmtree(inp)
    inp.mkdir()
    (inp / "lowering_plan.jsonl").write_text(_jsonl([c.plan for c in cases]), encoding="utf-8")
    (inp / "graph_ir.jsonl").write_text(_jsonl([c.graph for c in cases]), encoding="utf-8")
    out = work / "out"
    if out.exists():
        shutil.rmtree(out)
    fn = {"aws": _aws, "google": _google, "azurerm": _azure, "oci": _oci}[provider]
    return fn(inp, out, cases)


def _aws(inp, out, cases):
    from bo.harness.aws import render as R
    man = R.render_file(inp / "lowering_plan.jsonl", out, inp / "graph_ir.jsonl")
    res = {}
    for e in man["plans"]:
        files = {}
        if e.get("file"):
            files[e["file"]] = (out / e["file"]).read_text(encoding="utf-8")
        res[e["plan_id"]] = {"status": e["status"], "problems": e["missing"] + e["problems"] + e["unrendered"],
                             "files": files, "dir": str(out), "shared": [f for f in R.TEMPLATE_FILES]}
    return res


def _google(inp, out, cases):
    from bo.harness.google import render as R
    from bo.harness.google.schema import Schema
    schema = Schema.load(None)
    rules = R.load_rules()
    out.mkdir(parents=True)
    (out / "versions.tf").write_text(R.versions_tf(schema), encoding="utf-8")
    res = {}
    graphs = {c.graph["graph_id"]: c.graph for c in cases}
    for c in cases:
        r = R.render_plan(c.plan, graphs.get(c.plan["graph_id"]), schema, "object", rules)
        files = {}
        if r.status == R.RENDERED:
            name = R.file_name(r.plan_id)
            (out / name).write_text(r.hcl, encoding="utf-8")
            files[name] = r.hcl
        res[r.plan_id] = {"status": r.status, "problems": r.failures, "files": files, "dir": str(out),
                          "shared": ["versions.tf"]}
    return res


def _azure(inp, out, cases):
    from bo.harness.azurerm import render as R
    rep = R.render_file(inp / "lowering_plan.jsonl", out, inp / "graph_ir.jsonl")
    res = {}
    for row in rep["plans"]:
        files = {}
        d = None
        if row["status"] == "RENDERED":
            d = out if rep["layout"] == "single" else out / row["plan_id"]
            files = {"main.tf": (d / "main.tf").read_text(encoding="utf-8")}
        res[row["plan_id"]] = {"status": row["status"], "problems": row["issues"], "files": files,
                               "dir": str(d) if d else None, "shared": ["versions.tf"]}
    return res


def _oci(inp, out, cases):
    from bo.harness.oci import render as R
    syms = sorted({t["term"]["symbol_id"] for c in cases for t in c.graph["terms"]
                   if t["term"].get("kind") == "symbol" and t["term"].get("name_class") == "variable"})
    (inp / "bindings.json").write_text(json.dumps({
        "schema": "bo.harness.oci.bindings/1", "synthetic": True,
        "note": "bindings SINTÉTICOS do PILOT-NET-E2E: o compartment de contexto de cada caso é a chave compartment_id",
        "bindings": [{"symbol_id": s, "key": "compartment_id"} for s in syms]}, indent=1), encoding="utf-8")
    rr = R.render(inp / "lowering_plan.jsonl", out, inp / "graph_ir.jsonl", inp / "bindings.json")
    res = {}
    for p in rr.report["plans"]:
        files = {}
        if p["status"] == "RENDERED" and p.get("module"):
            mdir = out / p["module"]
            files = {f.name: f.read_text(encoding="utf-8") for f in sorted(mdir.glob("*.tf"))}
        res[p["plan_id"]] = {"status": p["status"], "problems": p["issues"], "files": files,
                             "dir": str(out / p["module"]) if p.get("module") else None, "module": p.get("module"),
                             "root": str(out)}
    return res


# --------------------------------------------------------------------------------------------- HCL -> oráculo

def parse(files: dict) -> dict:
    """{nome: texto} -> {"resources": [(tipo, rótulo, valores)], "variables": [...]} pelo python-hcl2."""
    resources, variables = [], []
    for name, text in sorted(files.items()):
        doc = hcl2.loads(text)
        for blk in doc.get("resource", []):
            for rtype, inner in blk.items():
                for label, body in inner.items():
                    resources.append((_unq(rtype), _unq(label), _clean(body)))
        for blk in doc.get("variable", []):
            variables.extend(_unq(k) for k in blk)
    return {"resources": resources, "variables": variables}


def _unq(s):
    return s[1:-1] if isinstance(s, str) and len(s) >= 2 and s[0] == s[-1] == '"' else s


def _clean(v):
    if isinstance(v, dict):
        return {_unq(k): _clean(x) for k, x in v.items() if not str(k).startswith("__")}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, str):
        s = _unq(v)
        m = VAR.match(s)
        if m:
            return f"sym:{m.group(1)}"
        m = REF.match(s)
        if m:
            return f"ref:{m.group(1)}.{m.group(2)}"
        if s.startswith("${") and s.endswith("}"):
            inner = s[2:-1]
            m2 = re.match(r"^([a-z][a-z0-9_]*)\.([A-Za-z0-9_\-]+)(?:\.[A-Za-z0-9_.]+)?$", inner)
            if m2 and not inner.startswith("var."):
                return f"ref:{m2.group(1)}.{m2.group(2)}"
            if inner.startswith("var."):
                return f"sym:{inner[4:]}"
        return s
    return v


def _flatten_blocks(v):
    """python-hcl2 devolve bloco aninhado como lista de um dicionário; atributos de lista de objeto também."""
    return v


def to_oracle(provider: str, case, parsed: dict, src_fx: dict) -> dict:
    res = parsed["resources"]
    keep = SUPPORTED[provider]
    out = []
    node_label = {}
    for rtype, label, body in res:
        if rtype in keep:
            out.append({"type": rtype, "name": label, "values": _single_blocks(provider, rtype, body)})
        node_label.setdefault(rtype, []).append((label, body))
    targets = {}
    src_targets = src_fx.get("targets", {})
    for tid, ep in case.endpoints.items():
        ip = src_targets.get(tid, {}).get("ip")
        if provider == "aws":
            sym = ep["symbol"]
            sgs = []
            for label, body in node_label.get("aws_network_interface_sg_attachment", []):
                ni = _clean(body.get("network_interface_id"))
                if isinstance(ni, str) and ni.startswith("sym:") and _sym_matches(ni, case, sym):
                    sgs.append(_clean(body.get("security_group_id")))
            out.append({"type": "aws_instance", "name": f"ctx_{tid}", "values": {}})
            out.append({"type": "aws_network_interface", "name": f"ctx_{tid}_nic",
                        "values": {"attachment": {"instance": f"ref:aws_instance.ctx_{tid}"}, "security_groups": sgs}})
            targets[tid] = {"ip": ip, "ref": f"aws_instance.ctx_{tid}"}
        elif provider == "google":
            lab = _label_of(case, ep["node"], "google_compute_instance", node_label)
            targets[tid] = {"ip": ip, "ref": f"google_compute_instance.{lab}"}
        elif provider == "azurerm":
            lab = _label_of(case, ep["node"], "azurerm_network_interface", node_label)
            out.append({"type": "azurerm_linux_virtual_machine", "name": f"ctx_{tid}",
                        "values": {"network_interface_ids": [f"ref:azurerm_network_interface.{lab}"]}})
            targets[tid] = {"ip": ip, "ref": f"azurerm_linux_virtual_machine.ctx_{tid}"}
        elif provider == "oci":
            lab = _label_of(case, ep["node"], "oci_core_subnet", node_label)
            out.append({"type": "oci_core_instance", "name": f"ctx_{tid}",
                        "values": {"create_vnic_details": {"subnet_id": f"ref:oci_core_subnet.{lab}"}}})
            targets[tid] = {"ip": ip, "ref": f"oci_core_instance.ctx_{tid}"}
    for tid, spec in src_targets.items():
        if tid not in targets:
            # alvo da origem sem ponto no destino (nenhum conjunto anexado): ponto vazio, sem conjunto
            ctx = {"aws": ("aws_instance", {}), "google": ("google_compute_instance", {"network_interface": []}),
                   "azurerm": ("azurerm_linux_virtual_machine", {"network_interface_ids": []}),
                   "oci": ("oci_core_instance", {"create_vnic_details": {}})}[provider]
            out.append({"type": ctx[0], "name": f"ctx_{tid}", "values": ctx[1]})
            targets[tid] = {"ip": spec.get("ip"), "ref": f"{ctx[0]}.ctx_{tid}"}
    return {"schema": "bo.pilot_net.fixture/1", "fixture_id": f"{case.case_id}-TARGET", "provider": provider,
            "config": {"resources": out}, "targets": targets, "flows": src_fx["flows"],
            "read": {"completeness": "complete", "not_read": [], "withheld": []}}


def _sym_matches(ni: str, case, sym_tid: str) -> bool:
    sid = next(t["term"]["symbol_id"] for t in case.graph["terms"] if t["term_id"] == sym_tid)
    return ni.endswith(sid[4:].lower()) or ni.endswith(sid[4:])


def _label_of(case, node, rtype, node_label) -> str:
    labs = [l for l, _ in node_label.get(rtype, [])]
    hits = [l for l in labs if l.endswith("_" + node) or l == node or l.endswith(node)]
    if len(hits) != 1:
        raise ValueError(f"nó {node} ({rtype}) sem rótulo único no HCL: {labs}")
    return hits[0]


# blocos que o oráculo lê como objeto único (hcl2 devolve lista de um)
_SINGLE = {"aws_network_interface": ["attachment"], "oci_core_instance": ["create_vnic_details"],
           "oci_core_security_list": [], "google_compute_instance": []}


def _single_blocks(provider, rtype, body):
    b = dict(body)
    for k in _SINGLE.get(rtype, []):
        if isinstance(b.get(k), list) and len(b[k]) == 1:
            b[k] = b[k][0]
    if rtype == "oci_core_security_list":
        for key in ("ingress_security_rules", "egress_security_rules"):
            rules = []
            for r in b.get(key) or []:
                r = dict(r)
                for opt in ("tcp_options", "udp_options"):
                    if isinstance(r.get(opt), list) and len(r[opt]) == 1:
                        r[opt] = r[opt][0]
                        for sub in ("destination_port_range", "source_port_range"):
                            if isinstance(r[opt].get(sub), list) and len(r[opt][sub]) == 1:
                                r[opt][sub] = r[opt][sub][0]
                rules.append(r)
            if rules:
                b[key] = rules
    if rtype == "google_compute_instance":
        b.pop("boot_disk", None)
    return b
