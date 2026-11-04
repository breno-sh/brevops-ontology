"""Decomposição das fixtures em unidades canônicas (E2) pela BIBLIOTECA DE GRÃO (bo.grain, camada de instância).

O tipo da unidade (ENTITY | COMPONENT | FACET | BINDING | UNKNOWN), o pai e a identidade de ocorrência saem do
bo.grain.instance.decompose_config com o mesmo adaptador de evidência do PILOT-NET-GLOSS e do bo.grain.realdata
(C25Adapter sobre o SERVICE-EVIDENCE do pin, átomos C01 do SCHEMA-*). Nada aqui decide grão: o que o GRAIN não
decide sai UNKNOWN com a evidência que falta. Este módulo só (1) diz que construção levantada (lift.py) é qual
unidade neutra do vocabulário dos compromissos (rule_set, filter_rule, attachment, selection) e (2) escreve a chave
de ocorrência na forma do gabarito: elemento com nome -> {"name"}; anônimo -> campos de identidade normalizados.

Anexação por atributo-lista (vpc_security_group_ids, security_list_ids, nsg_ids) não é bloco nem recurso: a camada
de instância do GRAIN não a torna ocorrência; a unidade sai UNKNOWN com missing = ["grain_occurrence"].
"""

from __future__ import annotations

import copy
import json
import random

from . import lift as LF

SCHEMA_DIR = {"aws": "SCHEMA-AWS", "google": "SCHEMA-GCP", "azurerm": "SCHEMA-AZURE", "oci": "SCHEMA-OCI"}
_cache: dict = {}


def _grain_inputs(provider: str, types: set):
    from bo.grain import rules as R
    from bo.grain.evidence import C25Adapter
    from bo.grain.realdata import load_atoms, load_evidence
    key = (provider, tuple(sorted(types)))
    if key not in _cache:
        atoms = load_atoms(provider, types)
        blocks = {}
        for a in atoms:
            cid = a["resource_type"]
            for p in a["path"].split(".")[:-1]:
                blocks.setdefault(cid, set()).add(p)
                cid = f"{cid}.{p}"
        if "ev" not in _cache:
            _cache["ev"] = load_evidence()
        recs = [r for r in _cache["ev"] if r.get("provider") == provider]
        _cache[key] = (C25Adapter(recs), blocks, R.load())
    return _cache[key]


def _grain_config(fx: dict) -> dict:
    def conv(v):
        if isinstance(v, str) and v.startswith("ref:"):
            return {"$ref": v[4:]}
        if isinstance(v, str) and v.startswith("sym:"):
            return {"$unknown": v[4:]}
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return v
    return {"provider": fx["provider"],
            "resources": [{"type": r["type"], "name": r["name"], "values": conv(r["values"])}
                          for r in fx["config"]["resources"]]}


def grain_occurrences(fx: dict) -> dict:
    """endereço/nó Terraform -> Occurrence do GRAIN (ou {} se a biblioteca falhar, com o motivo)."""
    from bo.grain import instance as I
    prov = fx["provider"]
    types = {r["type"] for r in fx["config"]["resources"]}
    ad, blocks, rs = _grain_inputs(prov, types)
    occs = I.decompose_config(_grain_config(fx), ad, blocks, rs)
    out = {}
    for o in occs:
        for nid in o.tf:
            out[nid] = o
    by_id = {o.occ_id: o for o in occs if o.occ_id}
    return {"by_nid": out, "by_id": by_id}


def _content_key(r: LF.Rule) -> dict:
    f = r.facts
    m = r.matches[0] if r.matches else {}
    d = f.get("direction")
    key = {"direction": d.value if d is not None and d.known() else None}
    p = m.get("protocol")
    key["protocol"] = str(p.raw) if p is not None and p.raw is not None else None
    dp = m.get("dst_ports")
    if dp is not None and dp.known() and dp.value:
        lo, hi = dp.value[0]
        key["ports"] = f"{lo}-{hi}"
    sp = f.get("src_ports")
    if sp is not None and sp.known() and sp.value:
        lo, hi = sp.value[0]
        key["src_ports"] = f"{lo}-{hi}"
    rem = f.get("remote")
    if rem is not None and rem.raw is not None:
        # identidade = conjunto de CIDRs remotos (normalizador set_of_cidr); a OCI tem um CIDR por regra (escalar)
        if r.provider == "oci":
            key["remote"] = rem.raw
        else:
            key["remote"] = sorted(rem.raw) if isinstance(rem.raw, list) else [rem.raw]
    if r.provider == "oci":
        st = f.get("stateless")
        if st is not None and LF.is_sym(st.raw):
            key["stateless"] = st.raw          # simbólico fica simbólico na chave (nenhum valor completado)
        else:
            key["stateless"] = bool(st.raw) if st is not None and st.raw is not None else False
    return {k: v for k, v in key.items() if v is not None}


def _kind(go, nid):
    o = go["by_nid"].get(nid)
    if o is None:
        return "UNKNOWN", ["grain_occurrence"], None
    return o.grain, list(o.missing), o


def decompose(fx: dict) -> list:
    L = LF.lift(fx)
    go = grain_occurrences(fx)
    units = []
    for sid, s in L.sets.items():
        k, miss, _ = _kind(go, s.tf["address"])
        u = {"domain_unit": "rule_set", "kind": k, "parent": None, "occurrence": {"set": s.tf["address"]},
             "tf": {"resource_type": s.kind}}
        if k == "UNKNOWN":
            u["unknown"] = miss
        units.append(u)
    for rid, r in L.rules.items():
        if "block_path" in r.tf:
            nid = f"{r.tf['address']}/{r.tf['block_path']}#{r.tf['index']}"
            tf = {"resource_type": r.tf["resource_type"], "block_path": r.tf["block_path"]}
        else:
            nid = r.tf["address"]
            tf = {"resource_type": r.tf["resource_type"]}
        k, miss, o = _kind(go, nid)
        parent = L.sets[r.set_id].tf["address"] if r.set_id else "UNKNOWN"
        name = r.facts.get("name")
        if r.set_id is None:
            occ = {"rule": r.tf["address"]}
        elif name is not None and name.known():
            occ = {"name": name.raw}
        else:
            occ = _content_key(r)
        u = {"domain_unit": "filter_rule", "kind": k, "parent": parent, "occurrence": occ, "tf": tf}
        if k == "UNKNOWN":
            u["unknown"] = miss
        units.append(u)
    for a in L.attachments:
        if a.set_id is None and not a.tf.get("symbol"):
            continue
        set_addr = L.sets[a.set_id].tf["address"] if a.set_id else a.tf["symbol"]
        ep = a.tf.get("via") or L.endpoints[a.endpoint].address
        if a.tf["resource_type"] in ("oci_core_subnet",):
            ep = a.tf["address"]
        nid = a.tf["address"]
        k, miss, _ = _kind(go, nid)
        if "block_path" in a.tf:
            k, miss = "UNKNOWN", ["grain_occurrence"]
        u = {"domain_unit": "attachment", "kind": k, "parent": None,
             "occurrence": {"set": set_addr, "target": ep},
             "tf": {k2: v for k2, v in a.tf.items() if k2 in ("resource_type", "block_path")}}
        if k == "UNKNOWN":
            u["unknown"] = miss
        if fx["provider"] == "google":
            continue        # na fatia do gabarito, a rede é o conjunto e o vínculo é a seleção por rótulo
        units.append(u)
    for sel in L.selections:
        r = L.rules[sel.rule_id]
        for tag in sel.labels.raw if isinstance(sel.labels.raw, list) else []:
            units.append({"domain_unit": "selection", "kind": "UNKNOWN", "parent": None,
                          "occurrence": {"label": tag, "rule": r.facts["name"].raw},
                          "tf": {"resource_type": r.tf["resource_type"], "block_path": "target_tags"},
                          "unknown": ["grain_occurrence"]})
    return _dedupe(units)


def _dedupe(units):
    seen, out = set(), []
    for u in units:
        k = json.dumps([u["domain_unit"], u["parent"], u["occurrence"]], sort_keys=True)
        if k in seen:
            continue
        seen.add(k)
        out.append(u)
    return out


def shuffled(fx: dict, seed: int) -> dict:
    """Mesma configuração com recursos e blocos em outra ordem (invariância a reordenação)."""
    rnd = random.Random(seed)
    g = copy.deepcopy(fx)
    rs = g["config"]["resources"]
    rnd.shuffle(rs)
    for r in rs:
        for k, v in r["values"].items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                rnd.shuffle(v)
    return g
