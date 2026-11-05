"""Decomposição das fixtures em unidades canônicas (E2) pela BIBLIOTECA DE GRÃO (bo.grain, camada de instância).

O tipo da unidade (ENTITY | COMPONENT | FACET | BINDING | UNKNOWN), o pai e a identidade de ocorrência saem do
bo.grain.instance.decompose_config com o mesmo adaptador de evidência do PILOT-NET-GLOSS e do bo.grain.realdata
(C25Adapter sobre o SERVICE-EVIDENCE do pin, átomos C01 do SCHEMA-*). Nada aqui decide grão: o que o GRAIN não
decide sai UNKNOWN com a evidência que falta. Este módulo só (1) diz que construção levantada (lift.py) é qual
unidade neutra do vocabulário dos compromissos (rule_set, filter_rule, attachment, selection), (2) escreve a chave
de ocorrência na forma do gabarito: elemento com nome -> {"name"}, resolvido ou não o pai; anônimo -> campos de
identidade normalizados; pai dado por atributo de nome com valor simbólico -> o símbolo (F3 do DIAG_T3), e (3)
conta a repetição de elementos distintos com a mesma chave pela evidência publicada (F4, ver _dedupe).

Fonte do TIPO, em ordem: (1) a unidade canônica C19 oficial do PILOT-NET-GLOSS ($BO_DATA/PILOT-NET-GLOSS/
canonical_units.jsonl: a mesma biblioteca aplicada no nível de esquema) da construção (tipo[.bloco]); (2) para
construção fora dos tipos da fatia do GLOSS, a camada de instância do GRAIN. A camada de instância, sozinha, devolve
UNKNOWN mesmo onde decide o tipo, porque a identidade de ocorrência da entidade de id opaco não tem valor na
configuração (achado CC-NET-E2E-2). Anexação por atributo-lista (vpc_security_group_ids, security_list_ids,
nsg_ids) e seleção por rótulo não são bloco nem recurso: sem unidade C19 nem ocorrência, saem UNKNOWN com
missing = ["grain_occurrence"].
"""

from __future__ import annotations

import copy
import json
import random

from . import lift as LF
from . import vocab as V

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


def c19_kinds() -> dict:
    import os
    from pathlib import Path
    p = Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data")) / "PILOT-NET-GLOSS" / "canonical_units.jsonl"
    if "c19" not in _cache:
        out = {}
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    u = json.loads(line)
                    cid = u["unit_id"][3:].split("-", 1)[1] if u["unit_id"].startswith("CU-") else u["unit_id"]
                    out[cid] = u
        _cache["c19"] = out
    return _cache["c19"]


def _kind_c19(go, nid, cid):
    u = c19_kinds().get(cid)
    if u is not None:
        return u["kind"], list(u.get("missing_evidence") or []) if u["kind"] == "UNKNOWN" else [], None
    return _kind(go, nid)


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
        k, miss, _ = _kind_c19(go, s.tf["address"], s.kind)
        u = {"domain_unit": "rule_set", "kind": k, "parent": None, "occurrence": {"set": s.tf["address"]},
             "tf": {"resource_type": s.kind}}
        if k == "UNKNOWN":
            u["unknown"] = miss
        u["_src"] = s.tf["address"]
        units.append(u)
    by_addr = {f"{r['type']}.{r['name']}": r for r in fx["config"]["resources"]}
    for rid, r in L.rules.items():
        if "block_path" in r.tf:
            nid = f"{r.tf['address']}/{r.tf['block_path']}#{r.tf['index']}"
            tf = {"resource_type": r.tf["resource_type"], "block_path": r.tf["block_path"]}
        else:
            nid = r.tf["address"]
            tf = {"resource_type": r.tf["resource_type"]}
        cid = f"{r.tf['resource_type']}.{r.tf['block_path']}" if "block_path" in r.tf else r.tf["resource_type"]
        k, miss, o = _kind_c19(go, nid, cid)
        parent = L.sets[r.set_id].tf["address"] if r.set_id else _parent_symbol(fx["provider"], r, by_addr, o)
        go_o = o if o is not None else go["by_nid"].get(nid)
        nk = go_o.name_key if go_o is not None else {}
        name = r.facts.get("name")
        if len(nk) == 1:
            occ = {"name": next(iter(nk.values()))}   # name_key do GRAIN (0.2.4): o nome, resolvido ou não o pai (F3)
        elif name is not None and name.known():
            occ = {"name": name.raw}           # elemento nomeado fora do GRAIN: o mesmo critério pelo lift
        elif r.set_id is None:
            occ = {"rule": r.tf["address"]}
        else:
            occ = _content_key(r)
        u = {"domain_unit": "filter_rule", "kind": k, "parent": parent, "occurrence": occ, "tf": tf, "_src": nid,
             "_mult": go_o.multiplicity if go_o is not None else None}
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
        if "block_path" in a.tf:
            k, miss = _binding_occ(go, a.tf["address"], a.tf["block_path"],
                                   L.sets[a.set_id].tf["address"] if a.set_id else None)
        else:
            k, miss, _ = _kind_c19(go, nid, a.tf["resource_type"])
        u = {"domain_unit": "attachment", "kind": k, "parent": None,
             "occurrence": {"set": set_addr, "target": ep},
             "tf": {k2: v for k2, v in a.tf.items() if k2 in ("resource_type", "block_path")}}
        if k == "UNKNOWN":
            u["unknown"] = miss
        if fx["provider"] == "google":
            continue        # na fatia do gabarito, a rede é o conjunto e o vínculo é a seleção por rótulo
        u["_src"] = f"{nid}/{a.tf.get('block_path', '')}#{a.tf.get('index', '')}->{set_addr}"
        units.append(u)
    for sel in L.selections:
        r = L.rules[sel.rule_id]
        for i, tag in enumerate(sel.labels.raw if isinstance(sel.labels.raw, list) else []):
            o = go["by_nid"].get(f"{r.tf['address']}:target_tags#{i}")
            k = o.grain if o is not None else "UNKNOWN"
            u = {"domain_unit": "selection", "kind": k, "parent": None,
                 "occurrence": {"label": tag, "rule": r.facts["name"].raw},
                 "tf": {"resource_type": r.tf["resource_type"], "block_path": "target_tags"}}
            if k == "UNKNOWN":
                u["unknown"] = list(o.missing) if o is not None else ["grain_occurrence"]
            u["_src"] = f"{r.tf['address']}:target_tags#{i}"
            units.append(u)
    return _dedupe(units, fx["provider"])


def _parent_symbol(provider: str, r, by_addr: dict, o) -> str:
    """Pai de regra em recurso separado que o lift não ligou a um conjunto da configuração (F3 do DIAG_T3).

    Fonte 1: o pai simbólico da ocorrência do GRAIN (T51c, 0.2.4: campo de referência com valor simbólico é ponta
    externa identificada só pelo símbolo; pai simbólico = o símbolo). Fonte 2, só onde o GRAIN não modela o campo
    como pai (google_compute_firewall.network: para o GRAIN a regra é ENTITY; o conjunto vem do compromisso
    CMT-FW-P01): o campo de pai do vocabulário com valor simbólico, reconhecido pelo MESMO padrão de símbolo do
    GRAIN (bo.grain.instance.SYMBOL_RE). Fora isso (nome literal fora da configuração, referência não resolvida,
    rótulo que não é símbolo, como em NETC-C01-AWS-SYM): "UNKNOWN"."""
    from bo.grain.instance import SYMBOL_RE
    by_grain = (lambda x: x.parent_symbol if x is not None else None)(o)
    if by_grain:
        return by_grain
    spec = V.STANDALONE_RULES.get(provider, {}).get(r.tf["resource_type"])
    res = by_addr.get(r.tf["address"])
    if spec is None or res is None or (o is not None and o.parent):
        return "UNKNOWN"
    pv = res["values"].get(spec["parent"])
    return pv[4:] if LF.is_sym(pv) and SYMBOL_RE.match(pv[4:]) else "UNKNOWN"


def _binding_occ(go, holder: str, block_path: str, set_addr: str | None):
    """Vínculo por atributo-lista (GRAIN 0.1.9): ocorrência '<dono>[/bloco#i]:<atributo>#j' cuja ponta é o conjunto."""
    attr = block_path.split(".")[-1]
    set_occ = go["by_nid"].get(set_addr).occ_id if set_addr and go["by_nid"].get(set_addr) else None
    hits = [o for nid, o in go["by_nid"].items() if nid.startswith(holder) and f":{attr}#" in nid]
    for o in hits:
        if set_occ and set_occ in (o.endpoints or {}).values():
            return o.grain, list(o.missing)
    if len(hits) == 1:
        return hits[0].grain, list(hits[0].missing)
    return "UNKNOWN", ["grain_occurrence"]


def _dedupe(units, provider: str):
    """Funde só o MESMO elemento Terraform emitido duas vezes (mesma origem `_src`). Elementos distintos com a
    mesma chave são REPETIÇÃO (F4 do DIAG_T3), decidida pela multiplicidade da ocorrência do GRAIN (T59c, 0.2.4,
    lida do SERVICE-EVIDENCE pelo próprio GRAIN): accepted -> multiconjunto; rejected ou idempotent -> funde, com a
    nota; sem evidência (ou elemento sem multiplicidade no GRAIN) -> cada repetição sai UNKNOWN (missing
    item_identity), nunca fundida em silêncio. Ordem: a da primeira ocorrência de cada chave."""
    groups: dict = {}
    for u in units:
        k = json.dumps([u["domain_unit"], u["parent"], u["occurrence"]], sort_keys=True)
        g = groups.setdefault(k, {})
        g.setdefault(u.get("_src") or id(u), u)
    out = []
    for g in groups.values():
        us = list(g.values())
        if len(us) == 1:
            out.append(us[0])
            continue
        ms = [u.get("_mult") or {} for u in us]
        kinds = {m.get("evidence") for m in ms}
        acc = kinds.pop() if len(kinds) == 1 else None
        ev = sorted({(m.get("source") or {}).get("ref") for m in ms} - {None})
        rep = {"count": len(us), "evidence": ev, "rule": "R-GRAIN-T59C"}
        if acc in ("rejected", "idempotent"):
            out.append(dict(us[0], repetition=dict(rep, policy="merged", duplicates=acc)))
        elif acc == "accepted":
            out.extend(dict(u, repetition=dict(rep, policy="multiset")) for u in us)
        else:
            for u in us:
                miss = sorted(set(u.get("unknown") or []) | {"item_identity"})
                out.append(dict(u, kind="UNKNOWN", unknown=miss, repetition=dict(rep, policy="unknown"),
                                kind_without_repetition=u["kind"]))
    for u in out:
        u.pop("_src", None)
        u.pop("_mult", None)
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
