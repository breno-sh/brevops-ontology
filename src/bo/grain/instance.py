"""Camada de instância: configuração (recursos e blocos declarados) → ocorrências com identidade por hash.

Formato de entrada (sintético, sem HCL): {"provider": p, "resources": [{"type": t, "name": n, "values": {...}}]}.
Bloco single = objeto; list/set = lista de objetos. Referência = {"$ref": "tipo.nome"}; valor simbólico não
resolvido = {"$unknown": motivo}. O grão de cada ocorrência sai do mesmo motor da camada de schema, com as
referências resolvidas entre ocorrências. A identidade de ocorrência é o sha256 do JSON canônico de
{grain, label, parent, endpoints, key}; a posição textual nunca entra (só como campo `$index`, quando a
evidência declara a ordem como identidade).
"""

from __future__ import annotations

import copy
import ipaddress
import re
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
    if norm == "content":
        return content_hash(v)
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


# símbolo de referência que vira ponta externa (C19 3.2.0, C19-EXTERNAL)
SYMBOL_RE = re.compile(r'^(var|data|module)\.[A-Za-z_][A-Za-z0-9_\-]*(\.[A-Za-z_*][A-Za-z0-9_\-]*|\[[0-9]+\]|'
                       r'\["[^"\s]+"\])*$')


def symbol_of(nid) -> str | None:
    """T51c (0.2.4): símbolo da ponta externa simbólica (EXT:<tipo ou vazio>#sym:<símbolo>), senão None."""
    if isinstance(nid, str) and nid.startswith(EXT) and "#sym:" in nid:
        return nid.split("#sym:", 1)[1]
    return None


class RepeatError(NormError):
    """T59c: repetição idêntica de elemento anônimo sem evidência de multiplicidade."""


def content_hash(v) -> str:
    """T59b: conteúdo canônico do item; símbolo e referência entram como marcas da configuração (não completados)."""
    def mark(x):
        if isinstance(x, dict) and "$unknown" in x:
            return "sym:" + str(x["$unknown"])
        if isinstance(x, dict) and "$ref" in x:
            return "ref:" + str(x["$ref"])
        if isinstance(x, dict):
            return {k: mark(y) for k, y in x.items()}
        if isinstance(x, list):
            return [mark(y) for y in x]
        return x
    return sha256_text(canon(mark(v)))


def _get(values: dict, path: str, index):
    if path == "$index":
        return index
    if path == "$element":
        return values.get("$element") if isinstance(values, dict) else None
    if path == "$content":
        # T59b: conteúdo configurado do item (blocos internos incluídos)
        return {k: x for k, x in values.items() if not k.startswith("$")} if isinstance(values, dict) else None
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
    # 0.2.4 (DIAG_T3): o que o adaptador de decomposição lê sem refazer a regra
    parent_symbol: str | None = None              # T51c: pai simbólico (o símbolo), quando o pai é ponta externa
    endpoint_symbols: dict = field(default_factory=dict)   # T51c: papel -> símbolo das pontas simbólicas
    name_key: dict = field(default_factory=dict)  # chave de nome do elemento (campos próprios), resolvido ou não o pai
    multiplicity: dict | None = None              # T59c: {index, count, evidence, rule} da repetição idêntica

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
        links = dict(ev.links)
        if S.LISTREF_ENABLED and isinstance(values, dict):
            # T61 (R-GRAIN-LISTREF): sem fato do SE no atributo, lista de escalares do dono (átomo do schema) com
            # referências a recursos na configuração; elemento literal ou simbólico não cria a ligação
            for attr, v in sorted(values.items()):
                if attr in links or not isinstance(v, list) or not any(
                        isinstance(x, dict) and "$ref" in x for x in v):
                    continue
                aid = f"{provider}:{rtype}:{'.'.join(list(block_path) + [attr])}"
                if S.scalar_list_atom(provider, aid):
                    links[attr] = S.listref_link(aid)
        for attr, link in sorted(links.items()):
            v = values.get(attr) if isinstance(values, dict) else None
            if not isinstance(v, list):
                continue
            lcid = f"{cid}:{attr}"
            if lcid not in evs:
                extra = adapter.evidence(lcid) if has and has(lcid) else None
                aid = f"{provider}:{rtype}:{'.'.join(list(block_path) + [attr])}"
                evs[lcid] = from_dict(S.link_evidence(cid, attr, link, extra, atom_id=aid))
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

    # T03 (0.2.4): id composto sem alvo tipado no esquema; o ÚNICO campo da chave cujo valor na configuração é
    # referência a um recurso é o pai (evidência derivada da configuração, citada com o fato do id composto)
    node_ev: dict[str, CandidateEvidence] = {}
    for nid, info in raw.items():
        tp = ev_of(info["cid"]).template_parent
        vals = info["values"] if isinstance(info["values"], dict) else {}
        if not tp:
            continue
        hits = [f for f in tp["fields"] if isinstance(vals.get(f), dict) and "$ref" in vals[f]]
        if len(hits) != 1:
            continue
        f = hits[0]
        ev2 = copy.deepcopy(ev_of(info["cid"]))
        ev2.template_parent = None
        ev2.field_map[f] = {"path": f, "ref": True, "template": True}
        ev2.references[f] = str(vals[f]["$ref"]).split(".")[0]
        src = dict(tp["source"], note=tp["source"].get("note", "") + f" (campo {f})")
        if ev2.fact("identity").state == "UNKNOWN":
            ev2.claims.setdefault("identity", []).append({"status": "present", "scope": "within_parent",
                                                          "key_fields": list(tp["fields"]), "source": src})
        if ev2.fact("lifecycle_controller").state == "UNKNOWN":
            # sem ciclo de vida afirmado: ciclo de vida, dono e alcance pelo pai (o que ainda é UNKNOWN)
            for fld in ("lifecycle_controller", "owner", "effective_scope"):
                if ev2.fact(fld).state == "UNKNOWN":
                    ev2.claims.setdefault(fld, []).append({"kind": "parent", "via": f, "source": src})
        node_ev[nid] = ev2

    def ev_node(nid):
        return node_ev.get(nid) or ev_of(raw[nid]["cid"])

    def payload(cid):
        ev = ev_of(cid)
        api, idf = ev.fact("api_resource"), ev.fact("identity")
        return api.known and api.value["status"] == "payload" and idf.known and idf.value["status"] == "absent"

    def ref_target(nid, f):
        info = raw[nid]
        ev = ev_node(nid)
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
        if isinstance(v, dict) and "$unknown" in v and not (tgt or "").startswith(SEL) and not m.get("by_name") \
                and not m.get("selector") and SYMBOL_RE.match(str(v["$unknown"])):
            # T51b (0.2.1, C19 3.2.0): referência tipada com valor simbólico (variável, data source ou saída de
            # módulo) vira ponta externa do tipo do alvo, identificada pelo símbolo; T51c (0.2.4, DIAG_T3 F3/F5): o
            # mesmo sem alvo tipado (o campo é referência pela evidência, o tipo fica em aberto); valor computado ou
            # outro desconhecido não (segue sem alvo)
            return f"{EXT}{tgt or ''}#sym:{v['$unknown']}"
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
        ev = ev_node(nid)
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

    def own_absent(nid, own):
        """T59b: todo campo da chave própria está ausente da configuração (não simbólico): id do provedor."""
        info = raw[nid]
        ev = nodes[nid].ev
        for f in own:
            m = ev.field_map.get(f, {})
            if f == "$content" or _get(info["values"], m.get("path", f), info["index"]) is not None:
                return False
        return True

    def repeat_group(nid, c):
        """Irmãos (mesmo candidato e pai) de conteúdo igual, na ordem dos nós: a posição de nid nesse grupo é o índice
        de multiplicidade; o conjunto de índices não depende da posição (os iguais são intercambiáveis)."""
        info = raw[nid]
        return [x for x in sorted(raw) if raw[x]["cid"] == info["cid"] and raw[x]["parent"] == info["parent"]
                and content_hash(_get(raw[x]["values"], "$content", None)) == c]

    repeated: set = set()
    mult: dict = {}

    def multiplicity(nid, d, key):
        """T59c (0.2.4, DIAG_T3 F4): repetição idêntica de elemento anônimo. Aceita pela evidência: multiconjunto
        ($dup = índice); inválida ou idempotente: uma ocorrência (as declarações se fundem, com nota); sem
        evidência: UNKNOWN (GRAIN-G0-REPEAT). Elemento sem repetição: $dup 0 na chave por conteúdo, como antes."""
        if not (d.identity.anonymous or "$content" in key):
            return
        c = key.get("$content") or content_hash(_get(raw[nid]["values"], "$content", None))
        group = repeat_group(nid, c)
        if len(group) <= 1:
            if "$content" in key:
                key["$dup"] = 0
            return
        m = nodes[nid].ev.multiplicity or {}
        kind = m.get("duplicates")
        mult[nid] = {"index": group.index(nid), "count": len(group), "evidence": kind or "UNKNOWN",
                     "rule": "R-GRAIN-T59C", "source": m.get("source")}
        if kind == "accepted":
            key["$dup"] = group.index(nid)
        elif kind in ("rejected", "idempotent"):
            if "$content" in key:
                key["$dup"] = 0
        else:
            repeated.add(nid)
            raise RepeatError(f"repetição idêntica ({len(group)} declarações) sem evidência de multiplicidade (T59c)")

    def ident(nid, stack=()):
        if nid in memo:
            return memo[nid]
        if nid.startswith(EXT):
            # T51 na instância: ocorrência externa referenciada, identidade = o endereço ou o valor citado; T51c
            # (0.2.4): a ponta simbólica é identificada só pelo símbolo (o tipo, quando há, não entra)
            sym = symbol_of(nid)
            memo[nid] = sha256_text(canon({"external_symbol": sym} if sym else {"external": nid[len(EXT):]}))
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
                if nid in raw and raw[nid]["parent"] is not None:
                    if not (d.grain == "COMPONENT" and own_absent(nid, own)):
                        raise             # bloco: o endereço é posicional e não serve de identidade (reordenação)
                    # T59b (0.2.0): item sem id na configuração (id atribuído pelo provedor depois da criação): a
                    # ocorrência é (pai, caminho, conteúdo, índice de multiplicidade), independente da posição
                    key = {"$content": content_hash(_get(raw[nid]["values"], "$content", None))}
                    d.notes.append(f"identidade de ocorrência por conteúdo (T59b): {e0}")
                else:
                    # T59: recurso de topo de id opaco (ou chave sem valor na configuração): antes da criação não
                    # há id; a ocorrência declarada é identificada pelo endereço do recurso (símbolo)
                    key = {"$address": nid}
                    d.notes.append(f"identidade de ocorrência simbólica (endereço): {e0}")
            multiplicity(nid, d, key)
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

    def name_key(nid, d):
        """Chave de nome do elemento (campos próprios da identidade nomeada), independente do pai (DIAG_T3 F3)."""
        out = {}
        if d.identity.anonymous:
            return out
        for f in d.identity.own:
            if f.startswith("$"):
                continue
            try:
                out[f] = field_val(nid, f)
            except NormError:
                return {}
        return out

    occ_by: dict = {}
    out: list[Occurrence] = []
    for nid in sorted(nodes):
        d = decs[nid]
        h = ident(nid)
        rep = nid in repeated
        rule = "GRAIN-G0-REPEAT" if rep else (d.rule if h or d.grain == "UNKNOWN" else "GRAIN-G0-IDENTITY")
        o = Occurrence(occ_id=h, grain=d.grain if h or d.grain == "UNKNOWN" else "UNKNOWN", label=d.label,
                       parent=memo.get(d.parent) if d.parent else None,
                       endpoints={r: memo.get(t) for r, t in d.endpoints.items()}, key=keys.get(nid, {}),
                       config=config_of(nid), rule=rule,
                       missing=list(d.missing) if (h or d.grain == "UNKNOWN") and not rep else ["identity"], tf=[nid],
                       notes=list(d.notes), parent_symbol=symbol_of(d.parent),
                       endpoint_symbols={r: symbol_of(t) for r, t in d.endpoints.items() if symbol_of(t)},
                       name_key=name_key(nid, d), multiplicity=dict(mult[nid]) if nid in mult else None)
        n = nodes[nid]
        for f, t in sorted(n.ref_targets.items()):
            if f not in d.identity.refs and n.ev.field_map.get(f, {}).get("ref"):
                o.refs[f] = ident(t) if t else None
        if o.occ_id and o.occ_id in occ_by:
            prev = occ_by[o.occ_id]
            if canon(prev.config) == canon(o.config):
                prev.tf.append(nid)
                ev_kind = (o.multiplicity or {}).get("evidence")
                prev.notes.append(f"repetição idêntica fundida em uma ocorrência: evidência {ev_kind} (R-GRAIN-T59C)"
                                  if ev_kind in ("rejected", "idempotent") else
                                  f"mesma identidade declarada mais de uma vez ({nid}): declarações fundidas")
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
