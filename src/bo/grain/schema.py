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
from .engine import Decision, Node, decide_graph
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


def candidates_from_tf_schema(provider: str, resource_schemas: dict) -> list[Candidate]:
    out: list[Candidate] = []

    def walk(rt, block, path, parent, nesting):
        cid = rt + ("." + ".".join(path) if path else "")
        out.append(Candidate(cid, provider, rt, tuple(path), nesting, sorted((block.get("attributes") or {}).keys()),
                             parent))
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
        by[rt + ("." + ".".join(blocks) if blocks else "")].attrs.append(leaf)
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

    for cid in sorted(by, key=lambda x: (x.count(".") + x.count(":"), x)):
        ev = evs[cid]
        if not _is_payload(ev):
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
        if cid in transparent:
            continue
        ev = evs[cid]
        rt = {}
        for f, m in ev.field_map.items():
            if m.get("ref"):
                t = ev.references.get(f)
                rt[f] = t if t in by and t not in transparent else (transparent.get(t) if t in transparent else None)
        nodes[cid] = Node(nid=cid, provider=c.provider, cid=cid, resource_type=c.resource_type,
                          block_path=c.block_path, group=c.group, parent=eff_parent(cid), ev=ev, ref_targets=rt,
                          by_role=True)
    decisions = decide_graph(list(nodes.values()), rs)
    res = SchemaResult(provider, by, nodes, decisions, transparent)
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
            if u is None:
                res.atom_owner[aid] = (None, full)
            elif c.group is not None or unit == cid:
                res.atom_owner[aid] = (unit, a)
            elif u.resource_type == c.resource_type and c.block_path[:len(u.block_path)] == u.block_path:
                res.atom_owner[aid] = (unit, ".".join(list(c.block_path[len(u.block_path):]) + [a]))
            else:
                res.atom_owner[aid] = (unit, full)
    return res


def unit_id(provider: str, cid: str) -> str:
    return f"CU-{provider}-{cid.replace('@', ':')}"


def _evidence_items(n: Node, d: Decision) -> list:
    items = n.ev.sources()
    return items


ENDPOINT_REF = "endpoint:{role}={unit}"


def to_c19(res: SchemaResult, atom_roles: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Registros C19 (canonical_units, canonical_atoms) da decomposição de schema.

    As pontas de um vínculo vão em identity.evidence como itens derivados com ref = endpoint:<papel>=<unit_id>
    (o C19 3.0.0 não tem campo próprio para elas). atom_roles: atom_id -> papel do C04 (ROLES), opcional."""
    units, atoms = [], []
    uid = {cid: unit_id(res.provider, cid) for cid in res.nodes}
    for cid in sorted(res.nodes):
        n, d = res.nodes[cid], res.decisions[cid]
        layers = {"terraform": {"resource_type": n.resource_type}, "domain_unit": d.label if len(d.label) >= 2 else cid}
        if n.block_path:
            layers["terraform"]["block_path"] = ".".join(n.block_path)
        if d.api and d.api.get("service") and d.api.get("resource"):
            layers["api_resource"] = {"service": d.api["service"], "resource": d.api["resource"]}
        ident_ev = n.ev.sources(("identity", "import_key", "element_name_key"))
        for role, t in sorted(d.endpoints.items()):
            ident_ev.append({"level": "derived", "ref": ENDPOINT_REF.format(role=role, unit=uid[t]),
                             "note": "ponta do vínculo (identidade = tupla das pontas)"})
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


def signature(res: SchemaResult, cids=None, *, with_tf=False) -> list:
    """Assinatura estrutural neutra (sem camada Terraform e sem provedor): base das comparações de invariância.

    Cada unidade vira (grão, rótulo, caminho de rótulos do pai, dono, alcance, ciclo de vida, chave, anônimo,
    pontas do vínculo por rótulo). `cids` restringe às unidades de uma embalagem (e aos seus ancestrais)."""
    decs = res.decisions
    keep = set(decs) if cids is None else _closure(res, cids)

    def path(nid, seen=()):
        if nid is None or nid in seen:
            return ()
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
            if y and y not in keep:
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
