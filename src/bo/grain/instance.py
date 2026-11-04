"""Camada de instância: configuração (recursos e blocos declarados) → ocorrências com identidade por hash.

Formato de entrada (sintético, sem HCL): {"provider": p, "resources": [{"type": t, "name": n, "values": {...}}]}.
Bloco single = objeto; list/set = lista de objetos. Referência = {"$ref": "tipo.nome"}; valor simbólico não
resolvido = {"$unknown": motivo}. O grão de cada ocorrência sai do mesmo motor da camada de schema, com as
referências resolvidas entre ocorrências. A identidade de ocorrência é o sha256 do JSON canônico de
{grain, label, parent, endpoints, key}; a posição textual nunca entra (só como campo `$index`, quando a
evidência declara a ordem como identidade).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from . import rules as R
from .common import canon, sha256_text
from . import schema as S
from .engine import EXT, SEL, Node, decide_graph
from .evidence import PARENT, CandidateEvidence, from_dict


class NormError(ValueError):
    pass


def _sym(v) -> bool:
    return isinstance(v, dict) and ("$unknown" in v or "$ref" in v)


def normalize(norm: str, v):
    if v is None or _sym(v):
        raise NormError("valor ausente ou simbólico")
    if norm == "str":
        return str(v).strip()
    if norm == "lower":
        return str(v).strip().lower()
    if norm in ("int", "ordinal"):
        return int(v)
    if norm == "bool":
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "enabled", "on", "yes"):
                return True
            if s in ("false", "disabled", "off", "no", "suspended"):
                return False
            raise NormError(f"bool não interpretável: {v!r}")
        return bool(v)
    if norm == "cidr":
        return str(ipaddress.ip_network(str(v).strip(), strict=False))
    if norm.startswith("set_of_"):
        inner = norm[len("set_of_"):]
        vals = v if isinstance(v, (list, tuple, set)) else [v]
        return sorted({canon(normalize(inner, x)) for x in vals})
    raise NormError(f"normalizador desconhecido: {norm}")


def _get(values: dict, path: str, index):
    if path == "$index":
        return index
    if path == "$element":
        return values.get("$element") if isinstance(values, dict) else None
    cur = values
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


@dataclass
class Occurrence:
    occ_id: str | None
    grain: str
    label: str
    parent: str | None
    endpoints: dict
    key: dict
    config: dict
    rule: str
    missing: list
    tf: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    refs: dict = field(default_factory=dict)      # referências simples (fora da identidade): campo -> ocorrência

    def row(self):
        return (self.occ_id, self.grain, self.label, self.parent, tuple(sorted(self.endpoints.items())),
                canon(self.key), canon(self.config), canon(self.refs), self.rule, tuple(self.missing))


def path_el(m: dict) -> bool:
    return m.get("path") == "$element"


def build_nodes(config: dict, adapter, schema_blocks: dict) -> tuple[dict, dict, dict]:
    """schema_blocks: cid -> conjunto de nomes de bloco filhos (para saber o que é bloco e o que é atributo)."""
    provider = config["provider"]
    raw: dict[str, dict] = {}
    evs: dict[str, CandidateEvidence] = {}

    def ev_of(cid):
        if cid not in evs:
            evs[cid] = adapter.evidence(cid)
        return evs[cid]

    has = getattr(adapter, "has", None)

    def walk(cid, rtype, nid, values, parent_nid, block_path, index):
        ev = ev_of(cid)
        if ev.out_of_domain:
            return                                       # T45: configuração do Terraform, fora do domínio
        if ev.implicit_facet and parent_nid is not None:
            # T57: faceta implícita entre o pai e os blocos membros (uma por ocorrência do pai)
            imp = ev.implicit_facet
            pcid = raw[parent_nid]["cid"]
            fcid, fnid = f"{pcid}:{imp['facet']}", f"{parent_nid}:{imp['facet']}"
            if fcid not in evs:
                evs[fcid] = from_dict(S.implicit_facet_evidence(imp))
                evs[fcid].implicit_facet = dict(imp, implicit=True)
            if fnid not in raw:
                raw[fnid] = dict(cid=fcid, rt=rtype, values={}, parent=parent_nid, block_path=raw[parent_nid][
                    "block_path"], index=None, group=imp["facet"])
            parent_nid = fnid
        raw[nid] = dict(cid=cid, rt=rtype, values=values, parent=parent_nid, block_path=block_path, index=index,
                        group=None)
        # T58: ligação por atributo-lista ou seleção: um nó por elemento (a posição não entra na identidade)
        for attr, link in sorted(ev.links.items()):
            v = values.get(attr) if isinstance(values, dict) else None
            if not isinstance(v, list):
                continue
            lcid = f"{cid}:{attr}"
            if lcid not in evs:
                extra = adapter.evidence(lcid) if has and has(lcid) else None
                evs[lcid] = from_dict(S.link_evidence(cid, attr, link, extra))
            for i, el in enumerate(v):
                raw[f"{nid}:{attr}#{i}"] = dict(cid=lcid, rt=rtype, values={"$element": el, "$attr": attr,
                                                                           "$kind": link.get("kind")},
                                                parent=nid, block_path=block_path, index=i, group=attr)
        for g, spec in sorted(ev.groups.items()):
            if any(_get(values, p, None) is not None for p in spec.get("paths", [])):
                gcid = f"{cid}:{g}"
                if gcid not in evs:
                    evs[gcid] = from_dict(spec.get("evidence", {}))
                raw[f"{nid}:{g}"] = dict(cid=gcid, rt=rtype, values=values, parent=nid, block_path=block_path,
                                         index=None, group=g)
        kids = set(schema_blocks.get(cid, ()))
        if isinstance(values, dict) and has:
            # T2 sem o schema do chamador: atributo com lista de objetos e evidência própria é bloco repetido
            kids |= {k for k, x in values.items() if isinstance(x, list) and x and all(isinstance(y, dict) for y in x)
                     and has(f"{cid}.{k}")}
        for b in sorted(kids):
            v = values.get(b)
            if v is None:
                continue
            items = v if isinstance(v, list) else [v]
            for i, item in enumerate(items):
                walk(f"{cid}.{b}", rtype, f"{nid}/{b}#{i}", item or {}, nid, block_path + (b,), i)

    for r in config["resources"]:
        walk(r["type"], r["type"], f"{r['type']}.{r['name']}", r.get("values", {}), None, (), None)

    def payload(cid):
        ev = ev_of(cid)
        api, idf = ev.fact("api_resource"), ev.fact("identity")
        return api.known and api.value["status"] == "payload" and idf.known and idf.value["status"] == "absent"

    def ref_target(nid, f):
        info = raw[nid]
        ev = ev_of(info["cid"])
        m = ev.field_map.get(f, {})
        v = _get(info["values"], m.get("path", f), info["index"])
        if v is None and m.get("namespace") and info["parent"] is not None:
            # T52b na instância: o bloco herda do pai o contêiner de namespace (o nome do pai o qualifica)
            pinfo = raw[info["parent"]]
            v = _get(pinfo["values"], m.get("path", f), pinfo["index"])
        if isinstance(v, dict) and "$ref" in v and v["$ref"] in raw:
            return v["$ref"]
        if isinstance(v, dict) and "$ref" in v:
            return EXT + v["$ref"]                       # T51: ocorrência referenciada fora da configuração
        tgt = ev.references.get(f)
        if path_el(m) and m.get("selector") and isinstance(v, (str, int)) and tgt and tgt.startswith(SEL):
            # T60: nó SELECTOR com identidade = predicado normalizado (chave do seletor, valor)
            return f"{tgt}={str(v).strip()}"
        if tgt and isinstance(v, (str, int)) and not isinstance(v, bool) and not m.get("by_name"):
            return f"{EXT}{tgt}#{v}"                     # referência por id literal a objeto fora da configuração
        if m.get("by_name") and isinstance(v, str):
            # referência por nome a um elemento irmão dentro do mesmo recurso (sem endereço Terraform)
            tcid, root = ev.references.get(f), nid.split("/")[0].split(":")[0]
            tev = ev_of(tcid) if tcid else None
            nk = tev.fact("element_name_key") if tev else None
            if not nk or not nk.known or nk.value["status"] != "present" or len(nk.value["fields"]) != 1:
                return None
            kpath = tev.field_map.get(nk.value["fields"][0], {}).get("path")
            hits = [x for x, r in raw.items() if r["cid"] == tcid and x.startswith(root + "/")
                    and _get(r["values"], kpath, r["index"]) == v]
            return hits[0] if len(hits) == 1 else None
        return None

    transparent: dict[str, str | None] = {}
    for nid in sorted(raw, key=lambda x: (x.count("/") + x.count(":"), x)):
        info = raw[nid]
        if not payload(info["cid"]):
            continue
        if info["parent"] is not None:
            p = info["parent"]
            transparent[nid] = transparent.get(p) if p in transparent else p
        else:
            ev = ev_of(info["cid"])
            imp = ev.fact("import_key")
            refs = [f for f in (imp.value.get("fields", []) if imp.known else []) if ev.field_map.get(f, {}).get("ref")]
            transparent[nid] = ref_target(nid, refs[0]) if len(refs) == 1 else None

    def eff(nid):
        while nid in transparent:
            nid = transparent[nid]
            if nid is None:
                return None
        return nid

    nodes: dict[str, Node] = {}
    for nid, info in sorted(raw.items()):
        if nid in transparent:
            continue
        ev = ev_of(info["cid"])
        rts = {}
        for f, m in ev.field_map.items():
            if m.get("ref"):
                t = ref_target(nid, f)
                rts[f] = eff(t) if t else None
        p = eff(info["parent"]) if info["parent"] else None
        nodes[nid] = Node(nid=nid, provider=provider, cid=info["cid"], resource_type=info["rt"],
                          block_path=info["block_path"], group=info["group"], parent=p, ev=ev, ref_targets=rts,
                          values=info)
    return nodes, transparent, raw


def decompose_config(config: dict, adapter, schema_blocks: dict, rs: R.RuleSet) -> list[Occurrence]:
    nodes, transparent, raw = build_nodes(config, adapter, schema_blocks)
    decs = decide_graph(list(nodes.values()), rs)
    memo: dict[str, str | None] = {}
    keys: dict[str, dict] = {}

    def field_val(nid, f):
        info = raw[nid]
        m = nodes[nid].ev.field_map.get(f) if nid in nodes else None
        if m is None:
            raise NormError(f"campo {f} sem mapa")
        return normalize(m.get("norm", "str"), _get(info["values"], m.get("path", f), info["index"]))

    def ident(nid, stack=()):
        if nid in memo:
            return memo[nid]
        if nid.startswith(EXT):
            # T51 na instância: ocorrência externa referenciada, identidade = o endereço ou o valor citado
            memo[nid] = sha256_text(canon({"external": nid[len(EXT):]}))
            return memo[nid]
        if nid.startswith(SEL):
            k, _, val = nid[len(SEL):].partition("=")
            memo[nid] = sha256_text(canon({"selector": k, "value": val}))
            return memo[nid]
        if nid in stack:
            return None
        d = decs[nid]
        if d.grain == "UNKNOWN":
            memo[nid] = None
            return None
        st = stack + (nid,)
        key, parent, endpoints = {}, None, {}
        try:
            own = [f for f in d.identity.own if f != "$id"]
            try:
                if "$id" in d.identity.own:
                    raise NormError("identidade só por id opaco: sem valor na configuração")
                for f in own:
                    key[f] = field_val(nid, f)
            except NormError as e0:
                if nid not in raw or raw[nid]["parent"] is not None:
                    raise                 # bloco: o endereço é posicional e não serve de identidade (reordenação)
                # T59: recurso de topo de id opaco (ou chave sem valor na configuração): antes da criação não há
                # id; a ocorrência declarada é identificada pelo endereço do recurso (símbolo por configuração)
                key = {"$address": nid}
                d.notes.append(f"identidade de ocorrência simbólica (endereço): {e0}")
            if d.grain in ("COMPONENT", "FACET"):
                parent = ident(d.parent, st)
                if parent is None:
                    raise NormError("pai sem identidade")
                for f, t in d.identity.refs.items():
                    if f != PARENT and t != d.parent:
                        it = ident(t, st)
                        if it is None:
                            raise NormError("referência sem identidade")
                        key[f] = it
            if d.grain == "BINDING":
                for role, t in d.endpoints.items():
                    it = ident(t, st)
                    if it is None:
                        raise NormError("ponta do vínculo sem identidade")
                    endpoints[role] = it
        except NormError as e:
            d.notes.append(f"identidade de ocorrência indeterminada: {e}")
            memo[nid] = None
            return None
        body = {"grain": d.grain, "label": d.label, "parent": parent, "endpoints": endpoints, "key": key}
        h = sha256_text(canon(body))
        memo[nid] = h
        keys[nid] = key
        return h

    def config_of(nid):
        out = {}
        members = [nid] + sorted(x for x in raw if x in transparent and _eff(x, transparent) == nid)
        for m in members:
            ev = nodes[m].ev if m in nodes else _ev(raw[m]["cid"], adapter)
            info = raw[m]
            for f, spec in sorted(ev.field_map.items()):
                if spec.get("config"):
                    v = _get(info["values"], spec.get("path", f), info["index"])
                    if v is None:
                        continue
                    try:
                        out[f] = normalize(spec.get("norm", "str"), v)
                    except NormError:
                        out[f] = {"symbolic": True}
        return out

    occ_by: dict = {}
    out: list[Occurrence] = []
    for nid in sorted(nodes):
        d = decs[nid]
        h = ident(nid)
        o = Occurrence(occ_id=h, grain=d.grain if h or d.grain == "UNKNOWN" else "UNKNOWN", label=d.label,
                       parent=memo.get(d.parent) if d.parent else None,
                       endpoints={r: memo.get(t) for r, t in d.endpoints.items()}, key=keys.get(nid, {}),
                       config=config_of(nid), rule=d.rule if h or d.grain == "UNKNOWN" else "GRAIN-G0-IDENTITY",
                       missing=list(d.missing) if (h or d.grain == "UNKNOWN") else ["identity"], tf=[nid],
                       notes=list(d.notes))
        n = nodes[nid]
        for f, t in sorted(n.ref_targets.items()):
            if f not in d.identity.refs and n.ev.field_map.get(f, {}).get("ref"):
                o.refs[f] = ident(t) if t else None
        if o.occ_id and o.occ_id in occ_by:
            prev = occ_by[o.occ_id]
            if canon(prev.config) == canon(o.config):
                prev.tf.append(nid)
                continue
            for x in (prev, o):
                x.grain, x.rule, x.missing = "UNKNOWN", "GRAIN-G0-DUPLICATE", ["identity"]
        if o.occ_id:
            occ_by[o.occ_id] = o
        out.append(o)
    return out


def _eff(nid, transparent):
    while nid in transparent:
        nid = transparent[nid]
        if nid is None:
            return None
    return nid


def _ev(cid, adapter):
    if ":" in cid:
        base, g = cid.split(":", 1)
        return from_dict(adapter.evidence(base).groups.get(g, {}).get("evidence", {}))
    return adapter.evidence(cid)


def canonical_rows(occs: list[Occurrence]) -> list:
    """Forma comparável (sem camada Terraform): o que tem de ser igual entre embalagens."""
    return sorted((o.row() for o in occs), key=lambda r: canon([str(x) for x in r]))
