"""Regras que o JSON Schema não exprime (x-bo-contract.semantic_rules), por (contrato, tipo de arquivo).

Cada regra recebe os objetos já lidos (depois do schema), o contexto do leitor e o caminho do arquivo (para os
arquivos irmãos) e devolve a lista de erros. Teorias de outros módulos são usadas como bibliotecas, não
reescritas: guardas, projeções, grupos e alternativas (bo.semantics), compromissos e CQs (bo.requirements.model),
punning (bo.ontpat.no_punning) e digest de comprovante (bo.repo.receipts)."""

from __future__ import annotations

import fnmatch
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import fileio
from .spec_a import (EVIDENCE_STATES, P_ATOM_ID, P_CLAIM_ID, P_CLAIM_VERSION_ID, P_EVENT_ID, PAIR_SIDE)

RULES: dict[tuple[str, str], callable] = {}
VERSION_RE = re.compile(r"^(?P<base>.+)@(?P<n>[1-9][0-9]*)(?P<inv>~inv)?$")
LADDER = {s: i for i, s in enumerate(EVIDENCE_STATES)}


def rule(cid: str, *kinds: str):
    def deco(fn):
        for k in kinds:
            RULES[(cid, k)] = fn
        return fn
    return deco


def run(cid: str, kind: str, objs: list, ctx: dict, path: Path) -> list[str]:
    fn = RULES.get((cid, kind))
    return fn(objs, ctx, path) if fn else []


# ------------------------------------------------------------------------------------------------ utilidades
def dup(values, what: str) -> list[str]:
    c = Counter(v for v in values if v is not None)
    d = sorted(k for k, n in c.items() if n > 1)
    return [f"{what} repetido: {', '.join(map(str, d[:10]))}"] if d else []


def version_parts(vid: str):
    m = VERSION_RE.match(vid or "")
    if not m:
        return None, None
    return m.group("base") + (m.group("inv") or ""), int(m.group("n"))


def version_of(claim_id: str, vid: str, where: str) -> list[str]:
    base, _ = version_parts(vid)
    if base != claim_id:
        return [f"{where}: claim_version_id {vid!r} não é versão de {claim_id!r} (esperado {claim_id}@n)"]
    return []


def claim_lineage(recs: list[dict], where_of) -> list[str]:
    """claim_id imutável; versão e evento em campos próprios; supersedes = versão anterior da mesma alegação."""
    errs = []
    for i, r in enumerate(recs):
        cid, vid = r.get("claim_id"), r.get("claim_version_id")
        if cid is None or vid is None:
            continue
        errs += version_of(cid, vid, where_of(i, r))
        sup = r.get("supersedes")
        if sup:
            sb, sn = version_parts(sup)
            _, n = version_parts(vid)
            if sb != cid:
                errs.append(f"{where_of(i, r)}: supersedes {sup!r} é de outra alegação (claim_id não muda entre versões)")
            elif n is not None and sn is not None and sn >= n:
                errs.append(f"{where_of(i, r)}: supersedes {sup!r} não é anterior a {vid!r}")
        if r.get("event_id") and re.match(P_CLAIM_VERSION_ID, r["event_id"]):
            errs.append(f"{where_of(i, r)}: event_id com forma de versão")
    errs += dup([r.get("claim_version_id") for r in recs], "claim_version_id")
    by = defaultdict(list)
    for r in recs:
        if r.get("claim_id"):
            by[r["claim_id"]].append(r.get("event_id"))
    for c, evs in by.items():
        if len(evs) > 1:
            errs += [f"{c}: {e}" for e in dup(evs, "event_id entre versões da mesma alegação")]
    vids = {r.get("claim_version_id") for r in recs}
    for i, r in enumerate(recs):
        sup = r.get("supersedes")
        if sup and version_parts(sup)[0] == r.get("claim_id") and sup not in vids:
            # versão anterior em outro arquivo é aceitável; dentro do mesmo arquivo a cadeia tem de fechar
            if any(version_parts(v)[0] == r.get("claim_id") and v != r.get("claim_version_id") for v in vids if v):
                errs.append(f"{where_of(i, r)}: supersedes {sup!r} não está no arquivo, mas outras versões estão")
    return errs


def sibling(path: Path, name: str) -> Path | None:
    p = path.parent / name
    return p if p.is_file() else None


def load_sibling(path: Path, name: str) -> list[dict] | None:
    p = sibling(path, name)
    if p is None:
        return None
    if name.endswith(".jsonl"):
        return [o for _, o in fileio._jsonl(p)[0]]
    return [o for _, o in fileio._json(p)[0]]


def semver_key(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


W = lambda kind: (lambda i, r: f"{kind}[{i + 1}]")  # noqa: E731


# ---------------------------------------------------------------------------------------------------- C00
def _module_ids(m: dict, where: str) -> list[str]:
    errs = []
    mid = m.get("id")
    if mid != m.get("stable_id"):
        errs.append(f"{where}: id {mid!r} != stable_id {m.get('stable_id')!r}")
    low = str(mid).lower()
    if m.get("branch") != f"bo/{low}":
        errs.append(f"{where}: branch {m.get('branch')!r} != bo/{low}")
    if not str(m.get("worktree", "")).endswith(f"/bo-{low}"):
        errs.append(f"{where}: worktree não termina em /bo-{low}")
    if m.get("tmp_dir") != f"$BO_DATA/tmp/{mid}":
        errs.append(f"{where}: tmp_dir {m.get('tmp_dir')!r} != $BO_DATA/tmp/{mid} (nunca /tmp)")
    return errs


@rule("C00", "module")
def r_module(objs, ctx, path):
    return _module_ids(objs[0], "module")


@rule("C00", "module_catalog")
def r_catalog(objs, ctx, path):
    from . import catalog as K
    cat = objs[0]
    mods = cat.get("modules") or []
    errs = []
    ids = [m.get("id") for m in mods]
    errs += dup(ids, "id de módulo")
    byid = {m.get("id"): m for m in mods}
    idx = set((cat.get("index_sets") or {}).keys())
    for m in mods:
        w = f"módulo {m.get('id')}"
        errs += _module_ids(m, w)
        for d in m.get("deps") or []:
            if d not in byid:
                errs.append(f"{w}: dep inexistente {d}")
        for fld in ("inputs", "outputs", "owns"):
            for p in m.get(fld) or []:
                for x in re.findall(r"\{([A-Za-z_]+)\}", p):
                    if x not in idx:
                        errs.append(f"{w}: {fld} usa índice {{{x}}} não declarado em index_sets")
    waves, state = {}, {}

    def wave(i):
        if i in waves:
            return waves[i]
        if state.get(i) == "visiting":
            raise ValueError(i)
        state[i] = "visiting"
        ds = [d for d in byid[i].get("deps") or [] if d in byid]
        waves[i] = 0 if not ds else 1 + max(wave(d) for d in ds)
        state[i] = "done"
        return waves[i]
    try:
        for i in byid:
            if wave(i) != byid[i].get("wave"):
                errs.append(f"módulo {i}: wave {byid[i].get('wave')} != calculada {wave(i)}")
    except ValueError as e:
        errs.append(f"ciclo de dependências passando por {e}")
    try:
        pub = K.schemas()
        for cid, c in (cat.get("contracts") or {}).items():
            if cid in pub:
                from .amendments import accepted
                v = pub[cid]["x-bo-contract"]["version"]
                if c.get("version") not in accepted(cid, v) or c.get("name") != K.NAMES[cid]:
                    errs.append(f"contracts.{cid}: {c.get('name')} {c.get('version')} != publicado {K.NAMES[cid]} {v}")
    except FileNotFoundError:
        pass
    return errs


# ---------------------------------------------------------------------------------------------------- C01
@rule("C01", "atoms")
def r_atoms(objs, ctx, path):
    errs = []
    for i, a in enumerate(objs):
        w = f"atoms[{i + 1}] {a.get('atom_id')}"
        if a["atom_id"] != f"{a['provider']}:{a['resource_type']}:{a['path']}":
            errs.append(f"{w}: atom_id != provider:resource_type:path")
        if a["required"] and a["optional"]:
            errs.append(f"{w}: required e optional ao mesmo tempo")
        if a["required"] and a["computed"]:
            errs.append(f"{w}: required e computed ao mesmo tempo")
        if a["configurable"] != (a["required"] or a["optional"]):
            errs.append(f"{w}: configurable != (required ou optional)")
        segs = a["path"].split(".")
        blocks = [b["block"] for b in a["block_path"]]
        if blocks != segs[:len(blocks)] or len(blocks) >= len(segs):
            errs.append(f"{w}: block_path {blocks} não é prefixo próprio de {a['path']}")
        if a.get("write_only") and (not a["configurable"] or a["computed"]):
            errs.append(f"{w}: write_only exige configurable e não computed")
        last = a["block_path"][-1]["nesting_mode"] if a["block_path"] else "none"
        if a["nesting"] != last:
            errs.append(f"{w}: nesting {a['nesting']} != modo do último bloco ({last})")
    errs += dup([(a["atom_id"], a["provider_version"]) for a in objs], "(atom_id, provider_version)")
    return errs


@rule("C02", "types")
def r_types(objs, ctx, path):
    errs = []
    for i, t in enumerate(objs):
        w = f"types[{i + 1}] {t.get('type_id')}"
        if t["type_id"] != f"{t['provider']}:{t['resource_type']}":
            errs.append(f"{w}: type_id != provider:resource_type")
        c = t["counts"]
        if c["configurable"] != c["required"] + c["optional"]:
            errs.append(f"{w}: configurable != required + optional")
        if c["configurable"] > c["attributes"]:
            errs.append(f"{w}: configurable > attributes")
    errs += dup([(t["type_id"], t["provider_version"]) for t in objs], "(type_id, provider_version)")
    return errs


@rule("C03", "docs_facts")
def r_docs(objs, ctx, path):
    errs = dup([f["fact_id"] for f in objs], "fact_id")
    for i, f in enumerate(objs):
        at = f.get("applies_to")
        if not at:
            continue
        pre = f["atom_id"].rsplit(":", 1)[0] + ":"
        if f["atom_id"] in at:
            errs.append(f"docs_facts[{i + 1}]: applies_to repete o próprio atom_id")
        bad = [a for a in at if not a.startswith(pre)]
        if bad:
            errs.append(f"docs_facts[{i + 1}]: applies_to fora de {pre}: {bad[:3]}")
    return errs


SUB_GUID = re.compile(r"/subscriptions/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-")


@rule("C03", "type_subcategory")
def r_type_facts(objs, ctx, path):
    errs = dup([(t.get("kind", "resource"), t["type_id"]) for t in objs], "(kind, type_id)")
    for i, t in enumerate(objs):
        w = f"type_subcategory[{i + 1}] {t['type_id']}"
        if t["type_id"] != f"{t['provider']}:{t['resource_type']}":
            errs.append(f"{w}: type_id != provider:resource_type")
        for s_ in _walk_values(t):
            if SUB_GUID.search(s_):
                errs.append(f"{w}: GUID de assinatura em claro (use /subscriptions/{{subscriptionId}})")
                break
        if t.get("alias_of") and t["alias_of"]["type_id"] == t["type_id"]:
            errs.append(f"{w}: apelido de si mesmo")
    return errs


@rule("C04", "roles")
def r_roles(objs, ctx, path):
    return dup([r["atom_id"] for r in objs], "atom_id")


# ---------------------------------------------------------------------------------------------------- C05
def _is_bytes(unit: str) -> bool:
    return bool(re.search(r"(BYTE|BIT)", unit or ""))


def _is_rate(qk: str, unit: str) -> bool:
    return bool(re.search(r"(Rate|Frequency)", qk or "")) or "-PER-" in (unit or "")


@rule("C05", "value_space")
def r_value_space(objs, ctx, path):
    errs = []
    for i, v in enumerate(objs):
        w = f"value_space[{i + 1}] {v.get('atom_id')}"
        qk, un, dt = v["quantity_kind"], v["unit_qudt"], v["datatype"]
        is_dur = dt["kind"] == "scalar" and dt.get("scalar") == "duration"
        if (qk == "NOT_APPLICABLE") != (un == "NOT_APPLICABLE") and not (is_dur and un == "NOT_APPLICABLE"):
            errs.append(f"{w}: NOT_APPLICABLE só nos dois (grandeza e unidade) ou em nenhum (exceto duração)")
        if qk == "UNKNOWN" and un != "UNKNOWN":
            errs.append(f"{w}: grandeza UNKNOWN com unidade {un} (unidade conhecida implica grandeza)")
        numeric = (dt["kind"] == "scalar" and dt["scalar"] in ("integer", "decimal", "duration")) or \
            (dt["kind"] == "tree" and dt.get("value_scalar") in ("integer", "decimal", "duration"))
        if not numeric and dt["kind"] != "tuple" and qk != "NOT_APPLICABLE":
            errs.append(f"{w}: {dt['kind']}/{dt.get('scalar', '')} não tem grandeza: use NOT_APPLICABLE (≠ UNKNOWN)")
        bare = un.rsplit(":", 1)[-1].rsplit("/", 1)[-1] in ("BYTE", "BIT")
        if _is_bytes(un) and v["byte_convention"] not in ("SI", "IEC") and not bare:
            errs.append(f"{w}: unidade de informação {un} sem byte_convention SI/IEC")
        if "allowed_values" in v and not numeric:
            errs.append(f"{w}: allowed_values em tipo não numérico")
        if "counted" in v and not str(qk).endswith("Count"):
            errs.append(f"{w}: counted só com grandeza Count")
        cands = v.get("unit_candidates") or []
        if cands and len({_is_bytes(c) for c in cands}) > 1:
            errs.append(f"{w}: unit_candidates de grandezas diferentes")
        if not _is_bytes(un) and qk not in ("UNKNOWN",) and v["byte_convention"] in ("SI", "IEC"):
            errs.append(f"{w}: byte_convention {v['byte_convention']} sem unidade de informação")
        if _is_rate(qk, un) and not v["rate_window"]:
            errs.append(f"{w}: taxa sem rate_window (a janela é parte do tipo)")
        is_enum = dt["kind"] == "scalar" and dt["scalar"] == "enum"
        if is_enum and not v.get("enum"):
            errs.append(f"{w}: escalar enum sem lista enum")
        if not is_enum and "enum" in v:
            errs.append(f"{w}: lista enum em tipo que não é enum")
        if "range" in v and not numeric:
            errs.append(f"{w}: range em tipo não numérico")
        r = v.get("range") or {}
        if "min" in r and "max" in r and r["min"] > r["max"]:
            errs.append(f"{w}: range com min > max")
    errs += dup([v["atom_id"] for v in objs], "atom_id")
    return errs


# ---------------------------------------------------------------------------------------------------- C06
LEAK = [("arn", re.compile(r"\barn:[a-z-]+:")), ("ocid", re.compile(r"\bocid1\.")),
        ("conta de 12 dígitos", re.compile(r"(?<!\d)\d{12}(?!\d)")),
        ("e-mail", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"))]


def _walk_values(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _walk_values(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk_values(v)
    elif isinstance(x, str):
        yield x


def term_leaks(term: dict, where: str) -> list[str]:
    errs = []
    if term.get("kind") == "document":
        for s in _walk_values(term.get("tree")):
            for name, rx in LEAK:
                if rx.search(s):
                    errs.append(f"{where}: documento com {name} em claro (simbolize como principal/identificador)")
    if term.get("kind") == "literal":
        for s in _walk_values(term.get("value")):
            for name, rx in LEAK:
                if rx.search(s):
                    errs.append(f"{where}: literal com {name} em claro")
    for a in (term.get("args") or []) + (term.get("items") or []):
        errs += term_leaks(a, where)
    return errs


@rule("C06", "symbolic_config")
def r_symbolic(objs, ctx, path):
    errs = []
    for i, s in enumerate(objs):
        errs += term_leaks(s["term"], f"symbolic_config[{i + 1}]")
        addr = re.sub(r"^(module\.SYM-[0-9a-f]+\.)*(data\.)?", "", s["resource_address"]).split("[")[0]
        if addr.split(".")[0] != s["resource_type"]:
            errs.append(f"symbolic_config[{i + 1}]: endereço não é do tipo {s['resource_type']}")
    return errs


@rule("C06", "usage")
def r_usage(objs, ctx, path):
    errs = []
    for i, u in enumerate(objs):
        if u["n_literal"] + u["n_symbolic"] + u["n_withheld"] != u["n_set"]:
            errs.append(f"usage[{i + 1}]: n_literal + n_symbolic + n_withheld != n_set")
        if u["n_set"] > u["n_resources"]:
            errs.append(f"usage[{i + 1}]: n_set > n_resources")
    errs += dup([(u["repo_id"], u["family_id"], u["resource_type"], u.get("atom_id")) for u in objs],
                "(repo_id, family_id, resource_type, atom_id)")
    return errs


@rule("C06", "resources")
def r_resources(objs, ctx, path):
    errs = []
    want = {"repo_id": "string", "family_id": "string", "file": "string", "resource_address": "string",
            "resource_type": "string", "provider": "string", "n_attrs": "int64", "has_count": "bool",
            "has_for_each": "bool", "module_depth": "int64"}
    got = ctx.get("arrow_types", {})
    for k, t in want.items():
        if got.get(k) != t:
            errs.append(f"coluna {k}: tipo {got.get(k)} != {t}")
    for k in set(got) - set(want):
        errs.append(f"coluna não declarada: {k}")
    errs += dup([r["resource_address"] + "@" + r["repo_id"] + "/" + r["file"] for r in objs], "recurso")
    return errs


# ---------------------------------------------------------------------------------------------------- C07
@rule("C07", "universe")
def r_universe(objs, ctx, path):
    u = objs[0]
    ids = [x["unit_id"] for x in u["units"]]
    errs = dup(ids, "unit_id")
    if set(u["pilot_exposed"]) != set(ids):
        falta = sorted(set(ids) - set(u["pilot_exposed"]))
        sobra = sorted(set(u["pilot_exposed"]) - set(ids))
        errs.append(f"pilot_exposed != unidades (faltam {falta[:5]}, sobram {sobra[:5]})")
    return errs


# ---------------------------------------------------------------------------------------------------- C08
def _subgraph(sg: dict, where: str) -> list[str]:
    errs = []
    nodes = [n["node_id"] for n in sg["nodes"]]
    errs += [f"{where}: {e}" for e in dup(nodes, "node_id")]
    ns = set(nodes)
    for e in sg["edges"]:
        for end in ("from", "to"):
            if e[end] not in ns:
                errs.append(f"{where}: aresta {e['kind']} aponta para nó inexistente {e[end]}")
    for n in sg["cross_facets"]:
        if n not in ns:
            errs.append(f"{where}: faceta cruzada {n} não é nó")
    for n in sg["nodes"]:
        if n["kind"] == "atom" and not re.match(P_ATOM_ID, n["ref"]):
            errs.append(f"{where}: nó {n['node_id']} kind atom com ref que não é atom_id")
    return errs


def _pair_sides(pair: str) -> tuple:
    for a in PAIR_SIDE:
        if pair.startswith(a) and pair[len(a):] in PAIR_SIDE:
            return PAIR_SIDE[a], PAIR_SIDE[pair[len(a):]]
    return None, None


@rule("C08", "candidates")
def r_candidates(objs, ctx, path):
    errs = []
    for i, c in enumerate(objs):
        w = f"candidates[{i + 1}] {c['candidate_id']}"
        errs += _subgraph(c["subject"], w + " subject") + _subgraph(c["object"], w + " object")
        a, b = _pair_sides(c["pair"])
        if (c["subject_provider"], c["object_provider"]) not in ((a, b), (b, a)):
            errs.append(f"{w}: provedores {c['subject_provider']}/{c['object_provider']} não são do par {c['pair']}")
    return errs + dup([c["candidate_id"] for c in objs], "candidate_id")


# ---------------------------------------------------------------------------------------------------- C09
def _fn_names() -> set:
    from bo.semantics import projections as P
    from bo.semantics import transforms as T
    from . import _base
    names = set(T.REGISTRY) | set(P.SIGNATURES)
    reg = _base.repo() / "transforms" / "transforms.yaml"
    if reg.is_file():
        try:
            doc = fileio._yaml(reg)[0][0][1]
            names |= {t.get("name") for t in (doc.get("scalar") or []) + (doc.get("combinators") or [])}
        except fileio.FormatError:
            pass
    return names


def _curie_prefix(v: str) -> str | None:
    if not isinstance(v, str) or v.startswith("http://") or v.startswith("https://"):
        return None
    p, sep, _ = v.partition(":")
    return p if sep else None


def check_correspondences(recs: list[dict], meta: dict | None, columns: list | None, notes: list | None = None) -> list[str]:
    from bo.semantics import guards as G
    from bo.semantics import projections as P
    from bo.semantics.claims import Claim, check_predicate
    from .spec_b import SSSOM_SLOTS
    from .sssom import CORE
    errs = []
    where = lambda i, r: f"linha {i + 1} {r.get('claim_id', '?')}"  # noqa: E731
    if meta is not None:
        cm = meta.get("curie_map") or {}
        for k in ("curie_map", "mapping_set_id", "license"):
            if not meta.get(k):
                errs.append(f"cabeçalho SSSOM sem {k}")
        declared = {d.get("slot_name") for d in meta.get("extension_definitions") or []}
        for c in columns or []:
            if c not in CORE and c not in SSSOM_SLOTS and c not in declared:
                errs.append(f"coluna {c} sem extension_definitions (seria descartada em silêncio)")
        for i, r in enumerate(recs):
            for k in ("subject_id", "object_id", "predicate_id", "mapping_justification", "subject_concept",
                      "object_concept"):
                p = _curie_prefix(r.get(k))
                if p and p not in cm:
                    errs.append(f"{where(i, r)}: prefixo {p}: de {k} fora do curie_map")
    names = _fn_names()
    for i, r in enumerate(recs):
        w = where(i, r)
        errs += [f"{w}: {e}" for e in check_predicate(Claim(r))]
        try:
            G.typecheck(r.get("guard") or G.empty())
        except G.GuardTypeError as e:
            errs.append(f"{w}: guarda fora da gramática: {e}")
        fn = r.get("translation_fn")
        for f in (fn if isinstance(fn, list) else [fn] if fn else []):
            if f.get("name") not in names:
                errs.append(f"{w}: translation_fn {f.get('name')!r} fora do núcleo/registro")
        g = r.get("group")
        if g is not None:
            if g.get("bo_group_id") != r.get("bo_group_id"):
                errs.append(f"{w}: bo_group_id da coluna != do grupo")
            res = P.check_group(g)
            errs += [f"{w}: grupo {f['rule']}: {f['detail']}" for f in res["failures"]]
        projs = r.get("projection")
        if projs:
            fields = {p["field"]: {"repeated": (p.get("occurrence") or {}).get("scope") == "block"} for p in projs}
            res = P.check_projections(projs, fields)
            for f in res["failures"]:
                if f["outcome"] == "REFUTED_BY_RULE":
                    errs.append(f"{w}: projeção {f['rule']}: {f['detail']}")
                elif notes is not None:
                    notes.append(f"{w}: projeção {f['rule']} ({f['outcome']}): {f['detail']}")
            errs += [f"{w}: {e}" for e in dup([p["projection_id"] for p in projs], "projection_id")]
    errs += _absences(recs, where, meta)
    errs += claim_lineage(recs, where)
    # alternativas guardadas (A-EXCL)
    byid = {r.get("claim_id"): r for r in recs}
    seen = set()
    for i, r in enumerate(recs):
        alts = r.get("alternative_to")
        if not alts or r["claim_id"] in seen:
            continue
        group_ids = {r["claim_id"], *alts}
        w = where(i, r)
        members = [byid.get(a) for a in sorted(group_ids)]
        if any(m is None for m in members):
            errs.append(f"{w}: alternative_to cita alegação fora do arquivo: "
                        f"{sorted(a for a in group_ids if a not in byid)}")
            continue
        for m in members:
            seen.add(m["claim_id"])
            if set(m.get("alternative_to") or []) != group_ids - {m["claim_id"]}:
                errs.append(f"{w}: alternativas não são mútuas ({m['claim_id']} lista {m.get('alternative_to')})")
            if m.get("subject_id") != r.get("subject_id"):
                errs.append(f"{w}: alternativa {m['claim_id']} realiza outro subject_id")
            if not (m.get("guard") or {}).get("all"):
                errs.append(f"{w}: alternativa {m['claim_id']} sem guarda")
        if len({m.get("exclusivity") for m in members}) > 1:
            errs.append(f"{w}: exclusividade diferente entre alternativas")
        res = P.check_alternatives([{"realization_id": m["claim_id"], "guard": m.get("guard"),
                                     "exclusivity": m.get("exclusivity")} for m in members])
        errs += [f"{w}: {f['rule']}: {f['detail']}" for f in res["failures"]]
    return errs


NO_TERM = "sssom:NoTermFound"
LEGACY_NONE = re.compile(r"^bo:NONE_(ABSENCE_DEMONSTRATED|OUT_OF_PIN|UNSUPPORTED_BY_TRANSLATOR|UNRESOLVED)$")


def _absences(recs: list[dict], where, meta: dict | None) -> list[str]:
    errs = []
    ids = {r.get("claim_id") for r in recs}
    for i, r in enumerate(recs):
        w = where(i, r)
        ab = r.get("absence")
        side = (ab or {}).get("side", "subject")
        s_none, o_none = r.get("subject_id") == NO_TERM, r.get("object_id") == NO_TERM
        none = s_none or o_none
        legacy = LEGACY_NONE.match(str(r.get("curation_rule") or ""))
        if s_none and o_none:
            errs.append(f"{w}: sssom:NoTermFound nos dois lados")
        if none and not (ab or legacy):
            errs.append(f"{w}: sssom:NoTermFound sem ausência tipada (absence ou curation_rule bo:NONE_<tipo>)")
        if s_none and not (ab and side == "object"):
            errs.append(f"{w}: subject_id sssom:NoTermFound só com absence.side = object")
        if ab and side == "subject" and not o_none:
            errs.append(f"{w}: absence do lado sujeito exige object_id sssom:NoTermFound")
        if ab and side == "object" and not s_none:
            errs.append(f"{w}: absence do lado objeto exige subject_id sssom:NoTermFound")
        if ab and legacy and legacy.group(1) != ab["kind"]:
            errs.append(f"{w}: curation_rule {legacy.group(0)} diverge de absence.kind {ab['kind']}")
        if none:
            if r.get("predicate_id") != "skos:relatedMatch" or r.get("semantic_relation") != "related":
                errs.append(f"{w}: ausência tem de ser skos:relatedMatch / related")
            if r.get("transport_fidelity") != "none" or r.get("translation_fn"):
                errs.append(f"{w}: ausência não transporta (fidelidade none, sem translation_fn)")
        for d in r.get("disputes") or []:
            if d == r.get("claim_id"):
                errs.append(f"{w}: disputes cita a própria alegação")
    return errs


@rule("C09", "correspondences", "correspondences_jsonl")
def r_correspondences(objs, ctx, path):
    return check_correspondences(objs, ctx.get("meta") if "meta" in ctx else None, ctx.get("columns"),
                                 ctx.setdefault("notes", []))


@rule("C09", "edoal")
def r_edoal(objs, ctx, path):
    from bo.semantics import guards as G
    from bo.semantics.edoal import ALIGN
    from bo.semantics.claims import Claim, check_predicate
    errs = []
    g = ctx["graph"]
    from rdflib.namespace import RDF
    for cell in g.subjects(RDF.type, ALIGN.Cell):
        m = g.value(cell, ALIGN.measure)
        try:
            if m is None or not 0.0 <= float(m) <= 1.0:
                errs.append(f"célula {cell}: measure ausente ou fora de [0, 1]")
        except ValueError:
            errs.append(f"célula {cell}: measure não numérica")
        for k in (ALIGN.entity1, ALIGN.entity2, ALIGN.relation):
            if g.value(cell, k) is None:
                errs.append(f"célula {cell}: sem {k.split('#')[-1]}")
    for i, r in enumerate(ctx["records"]):
        w = f"célula {i + 1} {r.get('claim_id', '?')}"
        for k, pat in (("claim_id", P_CLAIM_ID), ("claim_version_id", P_CLAIM_VERSION_ID), ("event_id", P_EVENT_ID)):
            if not isinstance(r.get(k), str) or not re.match(pat, r[k]):
                errs.append(f"{w}: anotação {k} ausente ou fora do formato")
        errs += [f"{w}: {e}" for e in check_predicate(Claim(r))]
        try:
            G.typecheck(r.get("guard") or G.empty())
        except G.GuardTypeError as e:
            errs.append(f"{w}: guarda fora da gramática: {e}")
    errs += claim_lineage(ctx["records"], lambda i, r: f"célula {i + 1}")
    return errs


# ---------------------------------------------------------------------------------------------------- C10
def _has_calendar(dur: str) -> bool:
    if not isinstance(dur, str) or not dur.startswith("P"):
        return False
    date = dur[1:].split("T")[0]
    return "Y" in date or "M" in date


@rule("C10", "transforms")
def r_transforms(objs, ctx, path):
    d = objs[0]
    errs = []
    allt = d["scalar"] + d["combinators"]
    names = [t["name"] for t in allt]
    errs += dup(names, "nome de transformação")
    for t in d["scalar"]:
        w = f"scalar {t['name']}"
        if t["domain"]["quantity_kind"] != t["codomain"]["quantity_kind"]:
            errs.append(f"{w}: grandeza de entrada {t['domain']['quantity_kind']} != saída "
                        f"{t['codomain']['quantity_kind']} (escalar preserva a grandeza; use combinador)")
        if t["domain"]["datatype"] in ("tuple",) or t["codomain"]["datatype"] in ("tuple",):
            errs.append(f"{w}: tupla em transformação escalar (é combinador)")
        dur = "duration" in (t["domain"]["datatype"], t["codomain"]["datatype"])
        if dur and t.get("duration_calendar") is None:
            errs.append(f"{w}: duração sem duration_calendar (forbidden | with_context)")
        if t.get("duration_calendar") == "with_context" and "calendar" not in (t.get("context_required") or []):
            errs.append(f"{w}: mês/ano aceito sem context_required ∋ calendar")
    for t in allt:
        inv = (t.get("inverse") or {}).get("name")
        if inv and inv not in names:
            errs.append(f"{t['name']}: inversa {inv} não declarada")
    return errs


@rule("C10", "conditions_grammar")
def r_grammar(objs, ctx, path):
    from bo.semantics import guards as G
    errs = []
    d = objs[0]
    outs = set()
    for t in d["sat_tests"]:
        try:
            got, _ = G.satisfiable(t["guard"])
        except G.GuardTypeError as e:
            errs.append(f"{t['test_id']}: guarda fora da gramática: {e}")
            continue
        outs.add(t["expected"])
        if got != t["expected"]:
            errs.append(f"{t['test_id']}: satisfiable = {got}, esperado {t['expected']}")
    for need in ("SAT", "UNSAT"):
        if need not in outs:
            errs.append(f"sat_tests sem caso {need}")
    errs += dup([t["test_id"] for t in d["sat_tests"]], "test_id")
    return errs


@rule("C10", "composition_table")
def r_composition(objs, ctx, path):
    from .spec_b import FIDELITIES, SEMANTIC_RELATIONS, VDR
    d = objs[0]
    errs = []
    sr = [(r["r1"], r["r2"]) for r in d["semantic_relation"]]
    if set(sr) != {(a, b) for a in SEMANTIC_RELATIONS for b in SEMANTIC_RELATIONS} or len(sr) != 25:
        errs.append("semantic_relation não cobre os 25 pares (r1, r2) uma vez cada")
    vr = [(r["r1"], r["r2"]) for r in d["value_domain_relation"]["rows"]]
    if set(vr) != {(a, b) for a in VDR[:5] for b in VDR[:5]} or len(vr) != 25:
        errs.append("value_domain_relation não cobre os 25 pares JEPD uma vez cada")
    for r in d["value_domain_relation"]["rows"]:
        exp = r["possible"][0] if len(r["possible"]) == 1 else "unknown"
        if r["result"] != exp:
            errs.append(f"value_domain_relation ({r['r1']}, {r['r2']}): result {r['result']} != {exp} (de possible)")
    fr = [(r["f1"], r["f2"]) for r in d["transport_fidelity"]["rows"]]
    if set(fr) != {(a, b) for a in FIDELITIES for b in FIDELITIES} or len(fr) != 16:
        errs.append("transport_fidelity não cobre os 16 pares (f1, f2) uma vez cada")
    return errs


@rule("C10", "guard")
def r_guard(objs, ctx, path):
    from bo.semantics import guards as G
    try:
        G.typecheck(objs[0])
    except G.GuardTypeError as e:
        return [f"guarda fora da gramática: {e}"]
    return []


# ---------------------------------------------------------------------------------------------------- C11
@rule("C11", "cases")
def r_cases(objs, ctx, path):
    errs = []
    for i, c in enumerate(objs):
        errs += version_of(c["claim_id"], c["claim_version_id"], f"cases[{i + 1}]")
    return errs + dup([c["case_id"] for c in objs], "case_id")


# ---------------------------------------------------------------------------------------------------- C12
@rule("C12", "readback")
def r_readback(objs, ctx, path):
    errs = dup([r["readback_id"] for r in objs], "readback_id")
    for i, r in enumerate(objs):
        errs += [f"readback[{i + 1}]: {e}" for e in dup([(f.get("node_id"), f["path"]) for f in r["fields"]],
                                                         "(node_id, campo)")]
    return errs


@rule("C12", "outcomes")
def r_outcomes(objs, ctx, path):
    errs = dup([o["outcome_id"] for o in objs], "outcome_id")
    rb = load_sibling(path, "readback.jsonl")
    rb_ids = {r["readback_id"] for r in rb} if rb else None
    for i, o in enumerate(objs):
        w = f"outcomes[{i + 1}] {o['outcome_id']}"
        b, a = LADDER[o["evidence_state_before"]], LADDER[o["evidence_state_after"]]
        val = o["outcome"]["value"]
        if a > b and val != "PERSISTED":
            errs.append(f"{w}: evidência sobe ({o['evidence_state_before']} -> {o['evidence_state_after']}) sem PERSISTED")
        if val in ("PERSISTED", "ALTERED") and not o.get("readback_id"):
            errs.append(f"{w}: {val} sem readback_id")
        if rb_ids is not None and o.get("readback_id") and o["readback_id"] not in rb_ids:
            errs.append(f"{w}: readback_id {o['readback_id']} não está no readback.jsonl irmão")
    return errs


# ---------------------------------------------------------------------------------------------------- C13
@rule("C13", "events")
def r_events(objs, ctx, path):
    errs = dup([e["event_id"] for e in objs], "event_id")
    for i, e in enumerate(objs):
        w = f"events[{i + 1}] {e['event_id']}"
        vi = e["version_interval"]
        if semver_key(vi["after"]) >= semver_key(vi["until"]):
            errs.append(f"{w}: intervalo vazio: after {vi['after']} >= until {vi['until']}")
        pre = f"{e['provider']}:{e['resource_type']}:"
        for k in ("atom_id", "from_atom", "to_atom"):
            if k in e and not e[k].startswith(pre):
                errs.append(f"{w}: {k} não é de {pre}")
        if e["event_type"] == "rename" and e.get("from_atom") == e.get("to_atom"):
            errs.append(f"{w}: renome com from_atom = to_atom")
    return errs


def _versions_doc(doc: dict, where: str = "") -> list[str]:
    vs = [v["version"] for v in doc["versions"]]
    errs = [where + e for e in dup(vs, "versão")]
    if [semver_key(v) for v in vs] != sorted(semver_key(v) for v in vs):
        errs.append(f"{where}versões fora de ordem crescente")
    return errs


@rule("C13", "versions")
def r_versions(objs, ctx, path):
    return _versions_doc(objs[0])


@rule("C13", "history_versions")
def r_history(objs, ctx, path):
    d = objs[0]
    errs = dup([p["provider"] for p in d["providers"]], "provider")
    pins = load_sibling(path, "pins.json")
    pin_by = {p["provider"]: p for p in pins[0]["providers"]} if pins else None
    for p in d["providers"]:
        w = f"{p['provider']}: "
        vd = p["versions_doc"]
        errs += _versions_doc(vd, w)
        if vd["provider"] != p["provider"]:
            errs.append(f"{w}versions_doc é de {vd['provider']}")
        last = vd["versions"][-1]
        if last["version"] != p["pin"]:
            errs.append(f"{w}C13-HIST-PIN: última versão {last['version']} != pin {p['pin']}")
        if pin_by is not None:
            q = pin_by.get(p["provider"])
            if q is None:
                errs.append(f"{w}C13-HIST-PIN: provider fora do pins.json irmão")
            else:
                if q["version"] != p["pin"]:
                    errs.append(f"{w}C13-HIST-PIN: pin {p['pin']} != pins.json {q['version']}")
                if q.get("source") != p["source"]:
                    errs.append(f"{w}C13-HIST-PIN: source diferente do pins.json")
                if last.get("schema_sha256") and q.get("schema_sha256") and last["schema_sha256"] != q["schema_sha256"]:
                    errs.append(f"{w}C13-HIST-PIN: schema_sha256 da última versão != pins.json")
        a = [(v["version"], v["released_at"]) for v in vd["versions"]]
        b = [(s_["version"], s_["released_at"]) for s_ in p["selection"]]
        if a != b:
            errs.append(f"{w}C13-HIST-SEL: selection e versions_doc não listam as mesmas versões/datas na mesma ordem")
        if semver_key(p["left_truncation"]["index_first_version"]) > semver_key(vd["versions"][0]["version"]):
            errs.append(f"{w}left_truncation.index_first_version posterior à primeira versão selecionada")
    return errs


@rule("C13", "atom_history")
def r_atom_history(objs, ctx, path):
    errs = dup([a["atom_id"] for a in objs], "atom_id")
    for i, a in enumerate(objs):
        w = f"atom_history[{i + 1}] {a['atom_id']}: "
        if a["atom_id"] != f"{a['provider']}:{a['resource_type']}:{a['path']}":
            errs.append(w + "atom_id != provider:resource_type:path")
        vs = [h["version"] for h in a["history"]]
        if len(set(vs)) != len(vs) or [semver_key(v) for v in vs] != sorted(semver_key(v) for v in vs):
            errs.append(w + "history fora de ordem semver ou com versão repetida")
        pres = [h["version"] for h in a["history"] if h["state"] == "present"]
        if a["first_seen"] != (pres[0] if pres else None) or a["last_seen"] != (pres[-1] if pres else None):
            errs.append(w + f"first_seen/last_seen != primeira/última versão presente ({pres[:1]}, {pres[-1:]})")
        for h in a["history"]:
            if h.get("required") and h.get("optional"):
                errs.append(w + f"{h['version']}: required e optional ao mesmo tempo")
    return errs


@rule("C13", "pins")
def r_pins(objs, ctx, path):
    return dup([p["provider"] for p in objs[0]["providers"]], "provider")


# ---------------------------------------------------------------------------------------------------- C14
@rule("C14", "classes")
def r_classes(objs, ctx, path):
    errs = dup([c["class_id"] for c in objs], "class_id")
    for i, c in enumerate(objs):
        errs += [f"classes[{i + 1}]: {e}" for e in dup([p["iri"] for p in c["parents"]], "pai")]
        if any(p["iri"] == c["class_id"] for p in c["parents"]):
            errs.append(f"classes[{i + 1}]: classe é pai de si mesma")
    return errs


@rule("C14", "properties")
def r_properties(objs, ctx, path):
    return dup([p["property_id"] for p in objs], "property_id")


@rule("C14", "realizations")
def r_realizations(objs, ctx, path):
    from bo.semantics import projections as P
    errs = dup([r["realization_id"] for r in objs], "realization_id")
    byid = {r["realization_id"]: r for r in objs}
    seen = set()
    for r in objs:
        alts = r.get("alternative_to")
        if not alts or r["realization_id"] in seen:
            continue
        ids = {r["realization_id"], *alts}
        w = f"realização {r['realization_id']}"
        if any(a not in byid for a in ids):
            errs.append(f"{w}: alternative_to cita realização fora do arquivo")
            continue
        ms = [byid[a] for a in sorted(ids)]
        for m in ms:
            seen.add(m["realization_id"])
            if set(m.get("alternative_to") or []) != ids - {m["realization_id"]}:
                errs.append(f"{w}: alternativas não são mútuas ({m['realization_id']})")
            if m["of"]["descriptor_key"] != r["of"]["descriptor_key"] or m["provider"] != r["provider"]:
                errs.append(f"{w}: alternativa {m['realization_id']} de outro descritor ou provedor")
        if len({m.get("exclusivity") for m in ms}) > 1:
            errs.append(f"{w}: exclusividade diferente entre alternativas")
        typed = all(all(isinstance(g, dict) for g in m.get("guards") or []) for m in ms)
        if typed:
            from bo.semantics import guards as G
            reals = [{"realization_id": m["realization_id"],
                      "guard": G.conj(*(m.get("guards") or [G.empty()])), "exclusivity": m.get("exclusivity")}
                     for m in ms]
            res = P.check_alternatives(reals)
            errs += [f"{w}: {f['rule']}: {f['detail']}" for f in res["failures"]]
    return errs


@rule("C14", "ttl")
def r_ttl(objs, ctx, path):
    from rdflib.namespace import RDFS
    from bo.ontpat import no_punning as NP
    g = ctx["graph"]
    errs = []
    rep = NP.report(g)
    for k in ("class_and_individual", "property_and_individual", "class_and_property"):
        for x in rep[k][:10]:
            errs.append(f"punning ({k}): {x}")
    for x in rep["metamodelling"][:10]:
        errs.append(f"metamodelagem: {x}")
    doms = defaultdict(set)
    for s, o in g.subject_objects(RDFS.domain):
        doms[s].add(o)
    for p, ds in sorted(doms.items()):
        if len(ds) > 1:
            errs.append(f"{p}: {len(ds)} rdfs:domain (seriam conjunção; use owl:unionOf ou restrição local)")
    return errs


# ---------------------------------------------------------------------------------------------------- C15
def _metrics(ms: list, where: str) -> list[str]:
    errs = dup([m["metric_id"] for m in ms], "metric_id")
    ids = {m["metric_id"] for m in ms}
    for m in ms:
        c = m["operational_coverage"]
        w = f"{where} {m['metric_id']}"
        if "n_known" in c and c["n_known"] > c["n"]:
            errs.append(f"{w}: n_known > n")
        if c["est"] is None:
            if c["n"] != 0 and c.get("n_known") != 0:
                errs.append(f"{w}: est nulo com n = {c['n']} e n_known != 0")
            if c["lower"] > c["upper"]:
                errs.append(f"{w}: lower > upper")
        elif c.get("n_known") == 0:
            errs.append(f"{w}: est numérico com n_known = 0 (indefinido)")
        elif not (c["lower"] <= c["est"] <= c["upper"]):
            errs.append(f"{w}: fora de lower <= est <= upper")
        for x in m["joint_uncertainty"].get("correlated_with") or []:
            if x not in ids:
                errs.append(f"{w}: correlated_with {x} não está no documento")
    return errs


@rule("C15", "result")
def r_result(objs, ctx, path):
    return _metrics(objs[0]["metrics"], "metrics")


@rule("C15", "summary_results")
def r_summary_results(objs, ctx, path):
    return r_summary(objs, ctx, path)


@rule("C15", "metrics_spec")
def r_metrics_spec(objs, ctx, path):
    return dup([m["metric_id"] for m in objs[0]["metrics"]], "metric_id")


# ---------------------------------------------------------------------------------------------------- C16
@rule("C16", "intent_manifest")
def r_intent(objs, ctx, path):
    errs = dup([i["intent_id"] for i in objs], "intent_id")
    for i, x in enumerate(objs):
        if x["purge_deadline"] <= x["recorded_at"]:
            errs.append(f"intent[{i + 1}]: purge_deadline não é posterior a recorded_at")
    return errs


@rule("C16", "run_manifest")
def r_run(objs, ctx, path):
    from .spec_c import STAGES
    errs = dup([r["run_id"] for r in objs], "run_id")
    intents = load_sibling(path, "intent_manifest.jsonl")
    iids = {i["intent_id"] for i in intents} if intents else None
    by = defaultdict(list)
    for r in objs:
        by[r["intent_id"]].append(r)
        if iids is not None and r["intent_id"] not in iids:
            errs.append(f"{r['run_id']}: intent_id {r['intent_id']} sem intenção registrada antes")
        chk = r.get("effective_identity_check")
        if r["stage"] in ("created", "confirmed") and chk and not chk["matches_allowlist"]:
            errs.append(f"{r['run_id']}: {r['stage']} com identidade fora da allowlist")
    rank = {s: i for i, s in enumerate(STAGES)}
    for iid, rs in by.items():
        seq = sorted(rs, key=lambda r: r["at"])
        st = [rank[r["stage"]] for r in seq]
        if st != sorted(st) or len(set(st)) != len(st):
            errs.append(f"{iid}: estágios fora de ordem ou repetidos: {[r['stage'] for r in seq]}")
    return errs


# ---------------------------------------------------------------------------------------------------- C17
@rule("C17", "manifest")
def r_manifest(objs, ctx, path):
    errs, paths = [], []
    for n, line in enumerate(ctx["lines"], 1):
        m = fileio.SHA_LINE.match(line)
        if not m:
            errs.append(f"linha {n}: não é '<sha256>  <caminho>'")
            continue
        p = m.group(2)
        if re.search(r"(\.\.\.|…|<|>)", p):
            errs.append(f"linha {n}: caminho com reticências ou modelo")
        paths.append(p)
    return errs + dup(paths, "caminho")


@rule("C17", "summary")
def r_summary(objs, ctx, path):
    s = objs[0]
    errs = []
    if "fable" in str(s["agent_provenance"].get("model_id", "")).lower():
        errs.append("agent_provenance.model_id é Fable (o projeto usa Opus)")
    if "results" in s:
        errs += _metrics(s["results"], "results")
    return errs


@rule("C17", "freeze_receipt")
def r_receipt(objs, ctx, path):
    from bo.repo import receipts
    r = objs[0]
    errs = []
    if receipts.receipt_digest(r) != r["digest"]:
        errs.append("digest não confere com o JSON canônico (comprovante editado)")
    if r["ots"].get("digest") and r["ots"]["digest"] != r["digest"]:
        errs.append("ots.digest != digest")
    if r["git"]["tag"] != f"bo-freeze-{r['name']}":
        errs.append("git.tag != bo-freeze-<name>")
    return errs + dup([a["path"] for a in r["artifacts"]], "artefato")


# ---------------------------------------------------------------------------------------------------- C18
@rule("C18", "numbers")
def r_numbers(objs, ctx, path):
    from .spec_c import CATEGORY_PREFIX
    errs = []
    for name, m in objs[0]["macros"].items():
        if not name.startswith(CATEGORY_PREFIX[m["category"]]):
            errs.append(f"\\{name}: categoria {m['category']} pede prefixo {CATEGORY_PREFIX[m['category']]}")
    tex = sibling(path, path.stem + ".tex")
    if tex is not None:
        errs += _tex_vs_json(fileio._tex(tex)[1]["lines"], objs[0])
    return errs


def _tex_vs_json(lines: list, doc: dict) -> list[str]:
    errs, got = [], {}
    for n, l in enumerate(lines, 1):
        if not l.strip() or l.lstrip().startswith("%"):
            continue
        m = fileio.MACRO.match(l.strip())
        if not m:
            errs.append(f"numbers.tex linha {n}: não é \\newcommand{{\\Nome}}{{valor}}")
            continue
        if m.group(1) in got:
            errs.append(f"numbers.tex: \\{m.group(1)} repetida")
        got[m.group(1)] = m.group(2)
    want = {k: v["display"] for k, v in doc["macros"].items()}
    for k in sorted(set(want) | set(got)):
        if want.get(k) != got.get(k):
            errs.append(f"\\{k}: numbers.tex {got.get(k)!r} != numbers.json {want.get(k)!r}")
    return errs


@rule("C18", "numbers_tex")
def r_numbers_tex(objs, ctx, path):
    js = sibling(path, path.stem + ".json")
    errs = []
    for n, l in enumerate(ctx["lines"], 1):
        if l.strip() and not l.lstrip().startswith("%") and not fileio.MACRO.match(l.strip()):
            errs.append(f"linha {n}: não é \\newcommand{{\\Nome}}{{valor}}")
    if js is not None and not errs:
        errs += _tex_vs_json(ctx["lines"], fileio._json(js)[0][0][1])
    return errs


# ---------------------------------------------------------------------------------------------------- C19
@rule("C19", "canonical_units")
def r_units(objs, ctx, path):
    errs = dup([u["unit_id"] for u in objs], "unit_id")
    for i, u in enumerate(objs):
        w = f"canonical_units[{i + 1}] {u['unit_id']}"
        ep = u.get("endpoints")
        if ep:
            if u["kind"] not in ("BINDING", "UNKNOWN"):
                errs.append(f"{w}: endpoints em {u['kind']} (só BINDING ou UNKNOWN)")
            errs += [f"{w}: {e}" for e in dup([e["role"] for e in ep], "papel de ponta")]
            if any(e["unit_id"] == u["unit_id"] for e in ep):
                errs.append(f"{w}: a unidade é ponta de si mesma")
        o = u["owner"]
        if o.get("refs"):
            if o.get("ref") and o["ref"] not in o["refs"]:
                errs.append(f"{w}: owner.ref fora de owner.refs")
            if u["unit_id"] in o["refs"]:
                errs.append(f"{w}: a unidade é dona de si em owner.refs")
    return errs


@rule("C19", "canonical_atoms")
def r_canon_atoms(objs, ctx, path):
    errs = dup([a["atom_id"] for a in objs], "atom_id (em mais de uma unidade)")
    us = load_sibling(path, "canonical_units.jsonl")
    if us is not None:
        ids = {u["unit_id"] for u in us}
        for i, a in enumerate(objs):
            if a["unit_id"] not in ids:
                errs.append(f"canonical_atoms[{i + 1}]: unit_id {a['unit_id']} não está em canonical_units.jsonl")
    return errs


# ---------------------------------------------------------------------------------------------------- C20
@rule("C20", "glossary")
def r_glossary(objs, ctx, path):
    errs = dup([c["concept_id"] for c in objs], "concept_id")
    for i, c in enumerate(objs):
        if c["quantity_kind"] == "UNKNOWN" and c.get("unit") not in (None, "UNKNOWN"):
            errs.append(f"glossary[{i + 1}]: grandeza UNKNOWN com unidade conhecida")
    return errs


@rule("C20", "claims")
def r_claims(objs, ctx, path):
    errs = claim_lineage(objs, W("claims"))
    for i, c in enumerate(objs):
        w = f"claims[{i + 1}]"
        k = c.get("anchor_kind", "atom")
        ref = c.get("block_id") if k == "block" else c.get("type_id") if k == "type" else None
        imp = c.get("implication") or {}
        for alt in imp.get("alternatives") or []:
            if alt["ref"] == ref:
                errs.append(f"{w}: alternativa é o próprio {k} da âncora")
            if alt["value"] == imp.get("value"):
                errs.append(f"{w}: alternativa {alt['ref']} implica o mesmo valor (a escolha não decide nada)")
        if k == "block" and ref and c.get("type_id"):
            errs.append(f"{w}: âncora em bloco com type_id")
    return errs


@rule("C20", "decisions")
def r_decisions(objs, ctx, path):
    errs = dup([d["decision_id"] for d in objs], "decision_id")
    gl = load_sibling(path, "glossary.jsonl")
    known = {c["concept_id"] for c in gl} if gl is not None else None
    edges = defaultdict(set)
    for i, d in enumerate(objs):
        w = f"decisions[{i + 1}] {d['decision_id']}"
        rel = d.get("related_concept")
        if rel and rel == d["concept_id"]:
            errs.append(f"{w}: conceito relacionado a si mesmo")
        if known is not None:
            for c in (d["concept_id"], rel):
                if c and c not in known and c != "bo:UNGLOSSED":
                    errs.append(f"{w}: {c} não está no glossary.jsonl irmão")
        if d["kind"] == "broader" and rel:
            edges[d["concept_id"]].add(rel)
        elif d["kind"] == "narrower" and rel:
            edges[rel].add(d["concept_id"])
    state = {}

    def visit(n, stack):
        state[n] = 1
        for m in edges.get(n, ()):
            if state.get(m) == 1:
                errs.append(f"C20-DEC-ACYCLIC: ciclo na hierarquia: {' -> '.join(stack + [n, m])}")
            elif m not in state:
                visit(m, stack + [n])
        state[n] = 2
    for n in sorted(edges):
        if n not in state:
            visit(n, [])
    return errs


@rule("C20", "glossary_audit")
def r_audit(objs, ctx, path):
    errs = dup([a["audit_id"] for a in objs], "audit_id")
    cl = load_sibling(path, "claims.jsonl")
    for i, a in enumerate(objs):
        errs += version_of(a["claim_id"], a["claim_version_id"], f"glossary_audit[{i + 1}]")
        if cl is not None and a["claim_version_id"] not in {c["claim_version_id"] for c in cl}:
            errs.append(f"glossary_audit[{i + 1}]: versão {a['claim_version_id']} não está em claims.jsonl")
    return errs


# ---------------------------------------------------------------------------------------------------- C21
@rule("C21", "verdicts")
def r_verdicts(objs, ctx, path):
    errs = dup([(v["claim_version_id"], v["cycle"]) for v in objs], "(claim_version_id, cycle)")
    for i, v in enumerate(objs):
        errs += version_of(v["claim_id"], v["claim_version_id"], f"verdicts[{i + 1}]")
    return errs


# ---------------------------------------------------------------------------------------------------- C22
@rule("C22", "observations")
def r_observations(objs, ctx, path):
    errs = dup([o["observation_id"] for o in objs], "observation_id")
    for i, o in enumerate(objs):
        c = o["counts"]
        if c["observed"] + c.get("observed_out_of_tolerance", 0) + c["not_observed"] + c["errors"] != c["attempts"]:
            errs.append(f"observations[{i + 1}]: observed + observed_out_of_tolerance + not_observed + errors != attempts")
    return errs


@rule("C22", "pair_judgements")
def r_judgements(objs, ctx, path):
    errs = dup([j["judgement_id"] for j in objs], "judgement_id")
    obs = load_sibling(path, "observations.jsonl")
    if obs is not None:
        by = {o["observation_id"]: o for o in obs}
        for i, j in enumerate(objs):
            w = f"pair_judgements[{i + 1}]"
            for side in ("A", "B"):
                o = by.get(j["observations"][side])
                if o is None:
                    errs.append(f"{w}: observação {side} {j['observations'][side]} não está em observations.jsonl")
                    continue
                if o["side"] != side or o["pair_case_id"] != j["pair_case_id"] or \
                        o["protocol_version"] != j["protocol_version"]:
                    errs.append(f"{w}: observação {side} de outro lado, par ou protocolo")
    return errs


@rule("C22", "probe_types")
def r_probe_types(objs, ctx, path):
    return dup([p["probe_type"] for p in objs[0]["probe_types"]], "probe_type")


# ---------------------------------------------------------------------------------------------------- C23
@rule("C23", "translation_trace")
def r_trace(objs, ctx, path):
    errs = dup([t["trace_id"] for t in objs], "trace_id")
    for i, t in enumerate(objs):
        w = f"translation_trace[{i + 1}] {t['trace_id']}"
        ge = (t.get("guard_evaluated") or {}).get("result")
        code = t.get("block_code")
        if code == "CONDITION_FALSE" and ge != "FALSE":
            errs.append(f"{w}: CONDITION_FALSE com guarda avaliada {ge}")
        if code == "CONDITION_INDETERMINATE" and ge != "INDETERMINATE":
            errs.append(f"{w}: CONDITION_INDETERMINATE com guarda avaliada {ge}")
        if t["result"] == "carried" and ge not in (None, "TRUE"):
            errs.append(f"{w}: carregado com guarda {ge}")
        both = set(t["justifying_axioms"]) & set(t["consulted_metadata"])
        if both:
            errs.append(f"{w}: mesmos itens em justifying_axioms e consulted_metadata: {sorted(both)[:5]}")
    return errs


# ---------------------------------------------------------------------------------------------------- C24
def _c24(kind: str):
    def fn(objs, ctx, path):
        from bo.requirements import model
        req = load_sibling(path, "requirements.jsonl") if kind != "requirements" else None
        cmt = load_sibling(path, "commitments.jsonl") if kind == "cq_spec" else None
        rids = {r.get("req_id") for r in req} if req is not None else None
        cids = {c.get("commitment_id") for c in cmt} if cmt is not None else None
        if kind == "requirements":
            return model.validate_requirements(objs)
        if kind == "commitments":
            return model.validate_commitments(objs, rids)
        return model.validate_cq_spec(objs, rids, cids)
    return fn


for _k in ("requirements", "commitments", "cq_spec"):
    RULES[("C24", _k)] = _c24(_k)

C11_REQUIRED = ("case_id", "group_id", "claim_id", "claim_version_id", "stratum", "frame_ref", "weight", "origin",
                "side", "lowering_plan", "values", "comparator", "cost_class")
P_CMT = re.compile(r"^CMT-[A-Z]{2,8}-[PNU]\d{2}$")


@rule("C24", "pilot_expected_answers")
def r_pilot(objs, ctx, path):
    d = objs[0]
    errs = []
    net = d["schema"].startswith("bo.pilot_net")
    entries = d["translations"] if net else d["directions"]
    seeds = [(k, e["c11_case_seed"], e["direction"]) for k, e in entries.items()]
    errs += dup([s["case_id"] for _, s, _ in seeds], "case_id da semente C11")
    for k, s, direction in seeds:
        w = f"{k}"
        pend = set(s["pending"])
        both = (pend & set(s)) | ({"stratum.relation"} & pend if "relation" in s["stratum_partial"] else set())
        if both:
            errs.append(f"{w}: {sorted(both)} na semente e em pending ao mesmo tempo")
        have = set(s) | {p.split(".")[0] for p in pend}
        if "stratum_partial" in s and ("relation" in s["stratum_partial"] or "stratum.relation" in pend):
            have.add("stratum")
        falta = [f for f in C11_REQUIRED if f not in have]
        if falta:
            errs.append(f"{w}: semente + pending não cobrem {falta} do C11")
        a, b = direction.split("->")
        if a == b:
            errs.append(f"{w}: direção {direction} de um provedor para ele mesmo")
        pa, pb = _pair_sides(s["stratum_partial"]["pair"])
        if {a, b} != {pa, pb}:
            errs.append(f"{w}: par {s['stratum_partial']['pair']} não é o da direção {direction}")
    cmt = load_sibling(path, "commitments.jsonl")
    cids = {c["commitment_id"] for c in cmt} if cmt is not None else None
    if net:
        for k, f in d["fixtures"].items():
            for c in f["commitment_ids"]:
                if not P_CMT.match(c) or (cids is not None and c not in cids):
                    errs.append(f"{k}: compromisso {c} fora do formato ou inexistente")
        if not str(d.get("retained_index", "")).startswith(("$BO_REPO/", "$BO_DATA/")):
            errs.append("retained_index não é caminho portátil (as retidas só por índice selado)")
    return errs


# ---------------------------------------------------------------------------------------------------- C25
@rule("C25", "service_evidence")
def r_service(objs, ctx, path):
    ids = [e["evidence_id"] for e in objs]
    errs = dup(ids, "evidence_id")
    for i, e in enumerate(objs):
        if e.get("block_path") and not e.get("terraform_resource_type"):
            errs.append(f"service_evidence[{i + 1}]: block_path sem terraform_resource_type")
        for d in e.get("derived_from") or []:
            if d not in ids or d == e["evidence_id"]:
                errs.append(f"service_evidence[{i + 1}]: derived_from {d} não é outro fato do arquivo")
    return errs


# ---------------------------------------------------------------------------------------------------- C26
@rule("C25", "protocol_support")
def r_protocol(objs, ctx, path):
    errs = dup([(p["probe_type"], p["provider"], p["terraform_resource_type"]) for p in objs],
               "(probe_type, provider, terraform_resource_type)")
    for i, p in enumerate(objs):
        if p["status"].startswith("documented_") and not any(e["level"] == "published" for e in p["evidence"]):
            errs.append(f"protocol_support[{i + 1}]: {p['status']} sem evidência published")
    return errs


@rule("C26", "graph_ir")
def r_graph(objs, ctx, path):
    errs = dup([g["graph_id"] for g in objs], "graph_id")
    for i, g in enumerate(objs):
        w = f"graph_ir[{i + 1}] {g['graph_id']}"
        nodes = [r["node_id"] for r in g["resources"]] + [c["node_id"] for c in g["components"]]
        errs += [f"{w}: {e}" for e in dup(nodes, "node_id")]
        errs += [f"{w}: {e}" for e in dup([t["term_id"] for t in g["terms"]], "term_id")]
        ns, rs = set(nodes), {r["node_id"] for r in g["resources"]}
        for c in g["components"]:
            if c["of"] not in rs:
                errs.append(f"{w}: componente {c['node_id']} de recurso inexistente {c['of']}")
        for r in g["references"]:
            for end in ("from", "to"):
                if r[end] not in ns:
                    errs.append(f"{w}: referência aponta para nó inexistente {r[end]}")
        for p in g["preconditions"]:
            for n in p["applies_to"]:
                if n not in ns:
                    errs.append(f"{w}: pré-condição {p['precondition_id']} sobre nó inexistente {n}")
    return errs


@rule("C26", "lowering_plan")
def r_plan(objs, ctx, path):
    errs = dup([p["plan_id"] for p in objs], "plan_id")
    gir = load_sibling(path, "graph_ir.jsonl")
    gby = {g["graph_id"]: g for g in gir} if gir is not None else None
    for i, p in enumerate(objs):
        w = f"lowering_plan[{i + 1}] {p['plan_id']}"
        orders = [s["order"] for s in p["steps"]]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            errs.append(f"{w}: ordens {orders} não são 1..n sem repetição")
        for s in p["steps"]:
            for d in s["depends_on"]:
                if d >= s["order"]:
                    errs.append(f"{w}: passo {s['order']} depende de {d}, que não é anterior")
            for v in s["values"]:
                if RUN_TAG.match(v["field"]):
                    errs.append(f"{w}: passo {s['order']} traz tag de execução {v['field']} (é do harness, não do plano)")
            prev = _ancestors(p["steps"], s)
            for v in s["values"]:
                if re.search(r"\.[0-9]+$", v["field"]) and (v.get("term") or {}).get("kind") == "reference":
                    ctx.setdefault("notes", []).append(
                        f"{w}: passo {s['order']} indexa {v['field']} com referência; prefira termo list (C26-LIST)")
            for v, tn in ((v, t.get("target_node")) for v in s["values"] for t in _refs(v.get("term") or {})):
                if tn and tn not in prev:
                    errs.append(f"{w}: passo {s['order']} referencia {tn}, que não é criado por passo de que ele depende")
            for ch in s["typed_choices"]:
                if ch["selected"] is not None and ch["selected"] not in ch["options"]:
                    errs.append(f"{w}: escolha {ch['choice_id']} selecionou fora das opções")
        if gby is not None:
            g = gby.get(p["graph_id"])
            if g is None:
                errs.append(f"{w}: graph_id {p['graph_id']} não está em graph_ir.jsonl")
                continue
            terms = {t["term_id"] for t in g["terms"]}
            nodes = {r["node_id"] for r in g["resources"]} | {c["node_id"] for c in g["components"]}
            for s in p["steps"]:
                if s["node_id"] not in nodes:
                    errs.append(f"{w}: passo {s['order']} sobre nó {s['node_id']} fora do grafo")
                used = list((s.get("derived_name") or {}).get("from_terms") or []) + \
                    [u["term_id"] for u in s["symbolic_unknowns"]]
                for t in used:
                    if t not in terms:
                        errs.append(f"{w}: passo {s['order']} cita termo {t} fora do grafo")
    return errs


# ---------------------------------------------------------------------------------------------------- C27
def _refs(term: dict):
    """Termos reference de um termo, inclusive dentro de list/expression."""
    if term.get("kind") == "reference":
        yield term
    for t in (term.get("items") or []) + (term.get("args") or []):
        yield from _refs(t)


RUN_TAG = re.compile(r"^(tags|labels|freeform_tags|defined_tags|tags_all)\.bo_")


def _ancestors(steps: list, step: dict) -> set:
    """Nós criados pelos passos de que este passo depende (fecho transitivo de depends_on)."""
    by = {s["order"]: s for s in steps}
    seen, todo = set(), list(step["depends_on"])
    while todo:
        o = todo.pop()
        if o in seen or o not in by:
            continue
        seen.add(o)
        todo += by[o]["depends_on"]
    return {by[o]["node_id"] for o in seen}


@rule("C27", "families")
def r_families(objs, ctx, path):
    errs = dup([f["family_id"] for f in objs], "family_id")
    errs += dup([m for f in objs for m in f["members"]], "repositório em mais de uma família")
    sp = sibling(path, "split.json")
    if sp is not None:
        s = fileio._json(sp)[0][0][1]
        for part in ("train", "dev"):
            n = sum(1 for f in objs if f["partition"] == part)
            want = ((s.get("partitions") or {}).get(part) or {}).get("n_families")
            if want != n:
                errs.append(f"{part}: {n} família(s) em families.jsonl != {want} em split.json")
    return errs


@rule("C27", "split")
def r_split(objs, ctx, path):
    return []


# ---------------------------------------------------------------------------------------------------- C28
@rule("C28", "comparators")
def r_comparators(objs, ctx, path):
    cs = objs[0]["comparators"]
    errs = dup([c["comparator_id"] for c in cs], "comparator_id")
    for c in cs:
        w = c["comparator_id"]
        for m in c["metrics"]:
            if m["axis"] not in c["axes"] and m["value"] != "NOT_APPLICABLE":
                errs.append(f"{w}: métrica {m['name']} no eixo {m['axis']} fora de axes tem de ser NOT_APPLICABLE "
                            f"(nunca 0), veio {m['value']!r}")
            if c["artifact"] in ("no", "doc_only") and m["axis"] == "translation" and \
                    isinstance(m["value"], (int, float)):
                errs.append(f"{w}: sem artefato, número no eixo de tradução")
        if c["artifact"] in ("no", "doc_only") and "translation" in c["axes"]:
            errs.append(f"{w}: sem artefato não pode ter o eixo de tradução")
    return errs


@rule("C28", "h2h_fairness")
def r_fairness(objs, ctx, path):
    d = objs[0]
    errs = dup([c["comparator_id"] for c in d["comparators"]], "comparator_id")
    for c in d["comparators"]:
        if c["budget_hours"] != d["budget"]["per_comparator"]:
            errs.append(f"{c['comparator_id']}: orçamento {c['budget_hours']} != {d['budget']['per_comparator']}")
        if not (c["same_universe"] and c["same_cqs"]):
            errs.append(f"{c['comparator_id']}: fora do mesmo universo ou das mesmas CQs")
    return errs


# ---------------------------------------------------------------------------------------------------- C29
@rule("C29", "domain_contracts")
def r_domains(objs, ctx, path):
    ds = objs[0]["domains"]
    errs = dup([d["domain"] for d in ds], "domain")
    fdir = path.parent / "fragments"
    frags = {}
    if fdir.is_dir():
        for f in sorted(fdir.glob("*.json")):
            try:
                o = fileio._json(f)[0][0][1]
                frags[o.get("fragment_id")] = o
            except fileio.FormatError as e:
                errs.append(f"fragments/{f.name}: {e}")
    want_kind = {"network_fragment": "network", "lb": "lb_graph", "db": "db_graph"}
    for d in ds:
        refs = [("network_fragment", d.get("network_fragment"))] + list((d.get("graphs") or {}).items())
        for k, ref in refs:
            if ref is None:
                continue
            f = frags.get(ref)
            if f is None:
                errs.append(f"{d['domain']}: fragmento {ref} ({k}) não está em fragments/")
            elif f.get("domain") != d["domain"] or f.get("kind") != want_kind[k]:
                errs.append(f"{d['domain']}: fragmento {ref} é {f.get('domain')}/{f.get('kind')}, esperado "
                            f"{d['domain']}/{want_kind[k]}")
    return errs


@rule("C29", "fragment")
def r_fragment(objs, ctx, path):
    f = objs[0]
    errs = dup([n["node_id"] for n in f["nodes"]], "node_id")
    ns = {n["node_id"] for n in f["nodes"]}
    for e in f["edges"]:
        for end in ("from", "to"):
            if e[end] not in ns:
                errs.append(f"aresta {e['kind']} aponta para nó inexistente {e[end]}")
    if not fnmatch.fnmatchcase(path.name, "*.json"):
        errs.append("fragmento fora de fragments/*.json")
    return errs
