"""Camada de schema: tipos Terraform (recursos, blocos, grupos de atributos) → unidades canônicas C19.

Entrada da camada Terraform em uma de duas formas:
  * schema no formato de `terraform providers schema -json` (resource_schemas → block → attributes/block_types);
  * átomos C01 (atoms.jsonl), agrupados por tipo e caminho de blocos.
A evidência vem de um adaptador (FixtureAdapter, C25Adapter) indexado pelo id de candidato:
`tipo`, `tipo.bloco.subbloco` ou `tipo.bloco:grupo` (grupo de atributos ligado a um aspecto da API, T1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import rules as R
from .common import sha256_text, canon
from .engine import EXT, SEL, Decision, Node, decide_graph
from .evidence import PARENT, CandidateEvidence, from_dict


@dataclass
class Candidate:
    cid: str
    provider: str
    resource_type: str
    block_path: tuple
    nesting: str
    attrs: list            # caminhos de atributo relativos ao candidato
    parent: str | None
    group: str | None = None
    virtual: bool = False  # elemento de atributo lista/conjunto de objetos: campos derivados do tipo cty (T2)
    attr_types: dict = field(default_factory=dict)    # atributo -> tipo cty (para T58)


def scalar_list(tf_type) -> bool:
    """lista ou conjunto de valores escalares (não de objetos): a forma das ligações por atributo (T58)."""
    return isinstance(tf_type, list) and len(tf_type) >= 2 and tf_type[0] in ("list", "set") and \
        isinstance(tf_type[1], str)


# R-GRAIN-LISTELEM (T60) pode ser desligada para medir a sensibilidade do resultado a ela
LISTELEM_ENABLED = True


# R-GRAIN-LISTREF (T61) pode ser desligada para medir a sensibilidade do resultado a ela
LISTREF_ENABLED = True
# átomos de atributo-lista escalar por provedor (provedor -> {atom_id: tf_type}); injetável nos testes
ATOM_TYPES: dict = {}


def scalar_list_atom(provider: str, atom_id: str):
    """tf_type do átomo do schema se ele é lista/conjunto de escalares; senão None. Lê SCHEMA-<P>/atoms.jsonl uma vez
    por provedor (só as linhas de lista/conjunto de string); sem o arquivo, None (sem citação, sem derivação)."""
    if provider not in ATOM_TYPES:
        idx = {}
        try:
            import json as _json
            from .realdata import SCHEMA_DIR, data_root
            with open(data_root() / SCHEMA_DIR[provider] / "atoms.jsonl", encoding="utf-8") as fh:
                for line in fh:
                    if '"string"]' not in line:
                        continue
                    a = _json.loads(line)
                    if scalar_list(a.get("tf_type")) and a.get("atom_id"):
                        idx[a["atom_id"]] = a["tf_type"]
        except (OSError, KeyError, ValueError):
            idx = {}
        ATOM_TYPES[provider] = idx
    return ATOM_TYPES[provider].get(atom_id)


def listref_link(atom_id: str) -> dict:
    """R-GRAIN-LISTREF (T61): atributo-lista de escalares do dono (átomo citado) cujos elementos, na configuração, são
    referências a recursos: cada elemento designa o objeto referenciado (o valor do elemento é o id dele). Só vale
    sem fato do SERVICE-EVIDENCE sobre o atributo; o alvo não ganha tipo (a ponta sai da própria referência)."""
    return {"kind": "reference", "target": None, "why": "referência na configuração (sem fato do SE no atributo)",
            "source": {"level": "derived", "ref": atom_id,
                       "note": "R-GRAIN-LISTREF: elementos do atributo-lista são referências a recursos na "
                               "configuração (átomo do schema citado)"}}


def link_evidence(holder_cid: str, attr: str, link: dict, extra, atom_id: str | None = None) -> dict:
    """Evidência derivada (T58) do candidato de ligação <holder>:<attr>, mais os fatos próprios da ligação."""
    sel = link.get("kind") == "selection" and bool(link.get("source"))     # seleção só com citação (T60)
    fld = "selector" if sel else "target"
    src = dict(link.get("source") or {"level": "derived", "ref": "T58"})
    src["note"] = (src.get("note", "") + " (T58: ligação por atributo)").strip()
    out = {"identity": [{"status": "present", "scope": "within_parent", "key_fields": [fld], "source": src}],
           "field_map": {fld: {"path": "$element", "ref": True, "selector": sel}}, "parent_role": "holder",
           "references": {}}
    if sel:
        out["references"][fld] = f"{SEL}{link.get('selector_kind') or attr}"
    elif link.get("target"):
        out["references"][fld] = link["target"]
    for k in ("lifecycle_controller", "owner", "effective_scope", "api_resource", "import_key"):
        cl = (extra.claims.get(k) if extra is not None else None) or []
        if cl:
            out[k] = list(cl)
    # R-GRAIN-LISTELEM (T60): o elemento de um atributo-lista é um valor escalar do dono: não tem configuração além
    # da própria identidade (dono = a própria associação), existe enquanto o dono o lista (ciclo de vida do dono) e
    # vale onde está (alcance próprio). DERIVADO, com citação do átomo do schema que prova que o atributo é do dono.
    # Fato do SERVICE-EVIDENCE sobre o atributo entra junto: se concorda, o campo é KNOWN; se diverge, CONTRADICTORY
    # (nunca sobrescrita).
    if LISTELEM_ENABLED and atom_id:
        d60 = {"level": "derived", "ref": atom_id,
               "note": "R-GRAIN-LISTELEM: elemento escalar do atributo do dono (átomo do schema citado)"}
        for k, claim in (("lifecycle_controller", {"kind": "parent", "via": "$parent"}), ("owner", {"kind": "self"}),
                         ("effective_scope", {"kind": "self"})):
            out[k] = list(out.get(k, [])) + [dict(claim, source=d60)]
    return out


def implicit_facet_evidence(imp: dict) -> dict:
    src = imp["source"]
    note = (f"implicit=true; operação {imp['operation']}" + (f" ({imp['member']})" if imp.get("member") else "")
            + " sobre o pai")
    cl = lambda **kw: dict(kw, source=dict(src, note=note))  # noqa: E731
    return {"identity": [cl(status="absent")], "lifecycle_controller": [cl(kind="parent")],
            "owner": [cl(kind="parent")], "effective_scope": [cl(kind="parent")],
            "api_resource": [cl(status="aspect", label=imp["label"])]}


def collection_fields(tf_type):
    """tf_type cty de lista ou conjunto de objetos -> (modo, {campo: tipo}); senão None.
    Aceita ["list"|"set", ["object", {...}]] e a forma nested_type [modo, {...}, opcionais] (C01-NESTED)."""
    if not isinstance(tf_type, list) or len(tf_type) < 2 or tf_type[0] not in ("list", "set"):
        return None
    inner = tf_type[1]
    if isinstance(inner, list) and len(inner) >= 2 and inner[0] == "object" and isinstance(inner[1], dict):
        return tf_type[0], inner[1]
    if isinstance(inner, dict):
        return tf_type[0], inner
    return None


def _add_collections(out: list, provider, rt, parent_cid, block_path, attr_types: dict):
    """T2: cada atributo lista/conjunto de objetos vira um candidato de bloco repetido, recursivamente."""
    for an, ty in sorted(attr_types.items()):
        cf = collection_fields(ty)
        if cf is None:
            continue
        mode, fields = cf
        path = list(block_path) + [an]
        cid = rt + "." + ".".join(path)
        out.append(Candidate(cid, provider, rt, tuple(path), mode,
                             sorted(f for f, ft in fields.items()), parent_cid, virtual=True))
        _add_collections(out, provider, rt, cid, path, fields)


def candidates_from_tf_schema(provider: str, resource_schemas: dict) -> list[Candidate]:
    out: list[Candidate] = []

    def walk(rt, block, path, parent, nesting):
        cid = rt + ("." + ".".join(path) if path else "")
        attrs = block.get("attributes") or {}
        out.append(Candidate(cid, provider, rt, tuple(path), nesting, sorted(attrs.keys()), parent,
                             attr_types={k: v.get("type") for k, v in attrs.items()}))
        _add_collections(out, provider, rt, cid, path, {k: v.get("type") for k, v in attrs.items()})
        for bname, bt in sorted((block.get("block_types") or {}).items()):
            walk(rt, bt.get("block") or {}, path + [bname], cid, bt.get("nesting_mode", "single"))

    for rt, sch in sorted(resource_schemas.items()):
        walk(rt, sch.get("block") or {}, [], None, "none")
    return out


def candidates_from_atoms(atoms: list[dict]) -> list[Candidate]:
    by: dict[str, Candidate] = {}
    for a in atoms:
        rt, prov = a["resource_type"], a["provider"]
        blocks = [b["block"] for b in a.get("block_path", [])]
        for i in range(len(blocks) + 1):
            p = blocks[:i]
            cid = rt + ("." + ".".join(p) if p else "")
            if cid not in by:
                parent = (rt + ("." + ".".join(p[:-1]) if p[:-1] else "")) if p else None
                nest = a["block_path"][i - 1]["nesting_mode"] if i else "none"
                by[cid] = Candidate(cid, prov, rt, tuple(p), nest, [], parent)
        leaf = a["path"].split(".")[-1]
        owner = rt + ("." + ".".join(blocks) if blocks else "")
        by[owner].attrs.append(leaf)
        by[owner].attr_types[leaf] = a.get("tf_type")
        extra: list = []
        _add_collections(extra, prov, rt, owner, blocks, {leaf: a.get("tf_type")})
        for c in extra:
            by.setdefault(c.cid, c)
    for c in by.values():
        c.attrs = sorted(set(c.attrs))
    return [by[k] for k in sorted(by)]


@dataclass
class SchemaResult:
    provider: str
    candidates: dict
    nodes: dict
    decisions: dict
    transparent: dict = field(default_factory=dict)   # cid -> cid do pai efetivo (ou None)
    atom_owner: dict = field(default_factory=dict)    # atom_id -> (unit cid, caminho na unidade)
    virtual_atoms: set = field(default_factory=set)   # sub-átomos derivados do tipo cty (não estão no C01)
    out_of_domain: dict = field(default_factory=dict) # cid -> motivo (T45: configuração do Terraform)
    out_of_domain_atoms: dict = field(default_factory=dict)  # atom_id -> motivo


def _is_payload(ev: CandidateEvidence) -> bool:
    api, idf = ev.fact("api_resource"), ev.fact("identity")
    return api.known and api.value["status"] == "payload" and idf.known and idf.value["status"] == "absent"


def decompose_schema(cands: list[Candidate], adapter, rs: R.RuleSet) -> SchemaResult:
    provider = cands[0].provider if cands else ""
    by = {c.cid: c for c in cands}
    evs: dict[str, CandidateEvidence] = {c.cid: adapter.evidence(c.cid) for c in cands}
    # T1: grupos de atributos ligados a um aspecto da API viram candidatos
    for c in list(cands):
        for g, spec in sorted(evs[c.cid].groups.items()):
            gid = f"{c.cid}:{g}"
            paths = sorted(spec.get("paths", []))
            by[gid] = Candidate(gid, c.provider, c.resource_type, c.block_path, "group", paths, c.cid, group=g)
            evs[gid] = from_dict(spec.get("evidence", {}))
            by[c.cid].attrs = [a for a in by[c.cid].attrs if a not in paths]
    # T58: ligação por atributo-lista de referências ou por seleção: candidato <dono>:<atributo>
    for c in sorted(list(by.values()), key=lambda x: x.cid):
        for attr, link in sorted((evs[c.cid].links if c.cid in evs else {}).items()):
            if attr not in c.attrs or not scalar_list(c.attr_types.get(attr)):
                continue
            lid = f"{c.cid}:{attr}"
            extra = adapter.evidence(lid) if getattr(adapter, "has", None) and adapter.has(lid) else None
            by[lid] = Candidate(lid, c.provider, c.resource_type, c.block_path, "link", [], c.cid, group=attr)
            aid = f"{c.provider}:{c.resource_type}:{'.'.join(list(c.block_path) + [attr])}"
            evs[lid] = from_dict(link_evidence(c.cid, attr, link, extra, atom_id=aid))
    # T57: faceta implícita (só com fato da spec): um candidato <pai>:<faceta> entre o pai e os blocos membros
    for c in sorted(list(by.values()), key=lambda x: x.cid):
        imp = evs[c.cid].implicit_facet if c.cid in evs else None
        if not imp or c.parent is None:
            continue
        fid = f"{c.parent}:{imp['facet']}"
        if fid not in by:
            pc = by[c.parent]
            by[fid] = Candidate(fid, c.provider, c.resource_type, pc.block_path, "implicit", [], c.parent,
                                group=imp["facet"])
            evs[fid] = from_dict(implicit_facet_evidence(imp))
            evs[fid].implicit_facet = dict(imp, implicit=True)
        c.parent = fid
    # T0: transparentes (carga útil da API do pai, sem identidade própria)
    transparent: dict[str, str | None] = {}

    def eff_parent(cid):
        c = by[cid]
        if c.parent is not None:
            p = c.parent
            return eff_parent_of(p) if p in transparent else p
        return None

    def eff_parent_of(tcid):
        return transparent[tcid]

    # T45: fora do domínio (o candidato e tudo abaixo dele)
    ood: dict[str, str] = {}
    for cid in sorted(by, key=lambda x: (x.count(".") + x.count(":"), x)):
        c = by[cid]
        if evs[cid].out_of_domain:
            ood[cid] = evs[cid].out_of_domain
        elif c.parent in ood:
            ood[cid] = ood[c.parent]
    for cid in sorted(by, key=lambda x: (x.count(".") + x.count(":"), x)):
        ev = evs[cid]
        if cid in ood or not _is_payload(ev):
            continue
        c = by[cid]
        if c.parent is not None:
            p = c.parent
            transparent[cid] = transparent.get(p, p) if p in transparent else p
        else:
            imp = ev.fact("import_key")
            refs = [f for f in (imp.value.get("fields", []) if imp.known else []) if ev.field_map.get(f, {}).get("ref")]
            tgt = ev.references.get(refs[0]) if len(refs) == 1 else None
            if tgt in by:
                transparent[cid] = tgt
    nodes: dict[str, Node] = {}
    for cid, c in sorted(by.items()):
        if cid in transparent or cid in ood:
            continue
        ev = evs[cid]
        rt = {}
        for f, m in ev.field_map.items():
            if m.get("ref"):
                t = ev.references.get(f)
                if t in transparent:
                    rt[f] = transparent.get(t)
                elif t in by:
                    rt[f] = t
                elif t and t.startswith(SEL):
                    rt[f] = t                            # T60: nó SELECTOR (predicado), não recurso
                else:
                    rt[f] = EXT + t if t else None      # T51: contêiner externo referenciado
        nodes[cid] = Node(nid=cid, provider=c.provider, cid=cid, resource_type=c.resource_type,
                          block_path=c.block_path, group=c.group, parent=eff_parent(cid), ev=ev, ref_targets=rt,
                          by_role=True)
    decisions = decide_graph(list(nodes.values()), rs)
    res = SchemaResult(provider, by, nodes, decisions, transparent, out_of_domain=ood)
    # átomos: cada atributo vai para a unidade do candidato, ou do pai efetivo se o candidato é transparente
    for cid, c in sorted(by.items()):
        unit = cid
        while unit in transparent:
            unit = transparent[unit]
            if unit is None:
                break
        u = by.get(unit) if unit else None
        for a in c.attrs:
            full = ".".join(list(c.block_path) + [a])
            aid = f"{c.provider}:{c.resource_type}:{full}"
            if cid in ood:
                res.out_of_domain_atoms[aid] = ood[cid]
                continue
            if c.virtual or any(by[x].virtual for x in _ancestors(by, cid)):
                res.virtual_atoms.add(aid)
            if u is None:
                res.atom_owner[aid] = (None, full)
            elif c.group is not None or unit == cid:
                res.atom_owner[aid] = (unit, a)
            elif u.resource_type == c.resource_type and c.block_path[:len(u.block_path)] == u.block_path:
                res.atom_owner[aid] = (unit, ".".join(list(c.block_path[len(u.block_path):]) + [a]))
            else:
                res.atom_owner[aid] = (unit, full)
    return res


def _ancestors(by, cid):
    out, p = [], by[cid].parent
    while p is not None and p in by:
        out.append(p)
        p = by[p].parent
    return out


def unit_id(provider: str, cid: str) -> str:
    return f"CU-{provider}-{cid.replace('@', ':')}"


def _evidence_items(n: Node, d: Decision) -> list:
    items = n.ev.sources()
    return items


def to_c19(res: SchemaResult, atom_roles: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Registros C19 (canonical_units, canonical_atoms) da decomposição de schema.

    As pontas de um vínculo vão no campo endpoints [{role, unit_id}] (C19 3.1.0). atom_roles: atom_id -> papel do C04 (ROLES), opcional."""
    units, atoms = [], []
    uid = _Uid(res.provider, {cid: unit_id(res.provider, cid) for cid in res.nodes})
    for cid in sorted(res.nodes):
        n, d = res.nodes[cid], res.decisions[cid]
        layers = {"terraform": {"resource_type": n.resource_type}, "domain_unit": d.label if len(d.label) >= 2 else cid}
        if n.block_path:
            layers["terraform"]["block_path"] = ".".join(n.block_path)
        if d.api and d.api.get("service") and d.api.get("resource"):
            layers["api_resource"] = {"service": d.api["service"], "resource": d.api["resource"]}
        ident_ev = n.ev.sources(("identity", "import_key", "element_name_key"))
        rec = {
            "unit_id": uid[cid], "provider": res.provider, "kind": d.grain, "layers": layers,
            "identity": {"evidence": ident_ev, "key_fields": list(d.identity.key_fields),
                         "anonymous": bool(d.identity.anonymous),
                         "occurrence_key": sorted(d.identity.own) if d.identity.anonymous else []},
            "lifecycle_controller": _ref(d.lifecycle["kind"], d.lifecycle.get("target"), uid),
            "owner": _ref(d.owner["kind"], (d.owner.get("targets") or [None])[0], uid),
            "effective_scope": _ref(d.scope["kind"], d.scope.get("target"), uid),
            "evidence": _evidence_items(n, d), "rule_applied": d.rule, "missing_evidence": list(d.missing),
        }
        if n.ev.implicit_facet and n.ev.implicit_facet.get("implicit"):
            imp = n.ev.implicit_facet
            rec["evidence"] = list(rec["evidence"]) + [{
                "level": "derived", "ref": "implicit=true",
                "note": f"faceta implícita {imp['facet']}: operação única {imp['operation']} sobre o pai "
                        f"(citação {imp['source'].get('ref')})"}]
        if d.own_api_lifecycle:
            rec["evidence"] = list(rec["evidence"]) + [{"level": "derived", "ref": "own_api_lifecycle=true",
                                                         "note": "componente com operações próprias na API (G2-CHILD)"}]
        for tc in d.cascade:
            rec["evidence"] = list(rec["evidence"]) + [{"level": "derived", "ref": f"cascade_delete_by={uid[tc]}",
                                                         "note": "apagado em cascata pelo contêiner de namespace "
                                                                 "(relação, não dono nem ciclo de vida)"}]
        if d.grain == "BINDING" and d.endpoints:
            rec["endpoints"] = [{"role": role, "unit_id": uid[t]} for role, t in sorted(d.endpoints.items())]
        units.append(rec)
    for aid in sorted(res.atom_owner):
        unit, rel = res.atom_owner[aid]
        if unit is None or unit not in uid:
            continue
        rec = {"atom_id": aid, "unit_id": uid[unit], "path_in_unit": rel}
        n = res.nodes[unit]
        role = (atom_roles or {}).get(aid) or n.ev.roles.get(rel)
        if role:
            rec["role"] = role
        atoms.append(rec)
    return units, atoms


def _ref(kind, target, uid) -> dict:
    out = {"kind": kind}
    if target is not None and target in uid:
        out["ref"] = uid[target]
    return out


class _Uid(dict):
    """unit_id dos candidatos, e o unit_id que o contêiner externo teria na decomposição completa (T51)."""

    def __init__(self, provider, m):
        super().__init__(m)
        self.provider = provider

    def __contains__(self, k):
        return dict.__contains__(self, k) or (isinstance(k, str) and k.startswith((EXT, SEL)))

    def __getitem__(self, k):
        if isinstance(k, str) and k.startswith(EXT) and not dict.__contains__(self, k):
            return unit_id(self.provider, k[len(EXT):])
        if isinstance(k, str) and k.startswith(SEL) and not dict.__contains__(self, k):
            return unit_id(self.provider, "selector:" + k[len(SEL):].replace("=", ":"))
        return dict.__getitem__(self, k)


def signature(res: SchemaResult, cids=None, *, with_tf=False) -> list:
    """Assinatura estrutural neutra (sem camada Terraform e sem provedor): base das comparações de invariância.

    Cada unidade vira (grão, rótulo, caminho de rótulos do pai, dono, alcance, ciclo de vida, chave, anônimo,
    pontas do vínculo por rótulo). `cids` restringe às unidades de uma embalagem (e aos seus ancestrais)."""
    decs = res.decisions
    keep = set(decs) if cids is None else _closure(res, cids)

    def path(nid, seen=()):
        if nid is None or nid in seen:
            return ()
        if nid.startswith(EXT):
            return ("EXTERNAL:" + nid[len(EXT):],)
        if nid.startswith(SEL):
            return ("SELECTOR:" + nid[len(SEL):],)
        d = decs[nid]
        return path(d.parent, seen + (nid,)) + (d.label,)

    out = []
    for nid in sorted(keep):
        d = decs[nid]
        row = (d.grain, path(nid), d.lifecycle["kind"], path(d.lifecycle.get("target")),
               d.owner["kind"], tuple(path(t) for t in d.owner.get("targets", [])), d.scope["kind"],
               path(d.scope.get("target")), tuple(sorted(f for f in d.identity.key_fields
                                                        if not n_is_ref(res, nid, f))),
               bool(d.identity.anonymous), tuple(sorted((r, path(t)) for r, t in d.endpoints.items())),
               d.rule, tuple(d.missing))
        if with_tf:
            row = row + (nid,)
        out.append(row)
    return sorted(out)


def n_is_ref(res: SchemaResult, nid, f) -> bool:
    return bool(res.nodes[nid].ev.field_map.get(f, {}).get("ref"))


def _closure(res: SchemaResult, cids) -> set:
    keep = set()
    stack = [c for c in cids if c in res.decisions]
    while stack:
        x = stack.pop()
        if x in keep:
            continue
        keep.add(x)
        d = res.decisions[x]
        for y in [d.parent, d.lifecycle.get("target"), d.scope.get("target"), *d.owner.get("targets", []),
                  *d.endpoints.values()]:
            if y and y not in keep and y in res.decisions:
                stack.append(y)
    return keep


def digest(obj) -> str:
    return sha256_text(canon(obj))


def verify_units(claimed: list[dict], res: SchemaResult) -> list[str]:
    """Confere unidades C19 declaradas (por outro produtor ou à mão) contra a evidência: grão, regra, dono,
    alcance e ciclo de vida têm de ser os que o procedimento deriva. Devolve as divergências."""
    mine, _ = to_c19(res)
    by = {u["unit_id"]: u for u in mine}
    errs = []
    for u in claimed:
        ref = by.get(u.get("unit_id"))
        if ref is None:
            errs.append(f"{u.get('unit_id')}: unidade sem candidato na decomposição")
            continue
        for k in ("kind", "rule_applied", "owner", "effective_scope", "lifecycle_controller", "missing_evidence"):
            if canon(u.get(k)) != canon(ref.get(k)):
                errs.append(f"{u['unit_id']}: {k} declarado {u.get(k)!r} diverge da evidência {ref.get(k)!r}")
    return errs


def atoms_from_tf_schema(provider: str, resource_schemas: dict, provider_version: str = "0.0.1") -> list[dict]:
    """Átomos no formato C01 a partir de um schema (para fixtures e para conferir o caminho por átomos)."""
    out = []

    def walk(rt, block, bpath):
        for a in sorted((block.get("attributes") or {})):
            path = ".".join([b["block"] for b in bpath] + [a])
            out.append({"atom_id": f"{provider}:{rt}:{path}", "provider": provider, "provider_version":
                        provider_version, "resource_type": rt, "path": path, "block_path": list(bpath),
                        "tf_type": "string", "nesting": bpath[-1]["nesting_mode"] if bpath else "none",
                        "required": False, "optional": True, "computed": False, "sensitive": False,
                        "deprecated": False, "configurable": True})
        for b, spec in sorted((block.get("block_types") or {}).items()):
            walk(rt, spec.get("block") or {}, bpath + [{"block": b, "nesting_mode": spec.get("nesting_mode",
                                                                                             "single")}])

    for rt, sch in sorted(resource_schemas.items()):
        walk(rt, sch.get("block") or {}, [])
    return out
