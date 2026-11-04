"""Contagem por repositório: blocos resource do google x átomos do schema fixado (C06 usage).

Função pura (sem E/S), usada pelo build em paralelo e pelos testes. As regras estão em common.PARAMS.

Classe do valor (term_class), sobre o termo C06 inteiro:
  withheld  há termo retido em qualquer nível;
  symbolic  o valor depende de algo fora do texto do atributo: referência a recurso, símbolo de variável, local,
            saída de módulo, data source, atributo de recurso, count.index, each/iterador de dynamic, workspace,
            path.* (onde o módulo está, resolvido no plano), função de provedor (provider::...), ou função que lê
            arquivo, ambiente ou relógio (NONGROUND_FUNCS);
  literal   o resto: o valor sai só do texto (literais, cadeias e endereços simbolizados pelo HCL por
            privacidade, CIDR/IP, documento sem interpolação dependente, funções puras sobre isso).
Literal null no topo (``attr = null``) não configura o átomo: para o Terraform é o mesmo que omitir.
"""

from __future__ import annotations

import collections
import posixpath
import re

from .paths import classify_path

DATA_ADDR = re.compile(r"^(module\.SYM-[0-9a-f]+\.)*data\.")
KINDS = ("literal", "symbol", "expression", "reference", "document", "withheld")
CLASS_RANK = {"literal": 0, "symbolic": 1, "withheld": 2}


def is_data(address: str) -> bool:
    return bool(DATA_ADDR.match(address))


NONGROUND_CLASSES = frozenset({"variable", "local", "module_output", "data_source", "resource_attribute",
                               "count_index", "each_key", "workspace", "path"})
# função de provedor (provider::ns::f) é resolvida pelo plugin no plano: depende de fora do texto
NONGROUND_OPS = frozenset({"hcl_provider_function"})
NONGROUND_FUNCS = frozenset({"file", "filebase64", "filebase64sha256", "filebase64sha512", "filemd5", "filesha1",
                             "filesha256", "filesha512", "fileexists", "fileset", "templatefile", "abspath",
                             "pathexpand", "timestamp", "plantimestamp", "uuid", "bcrypt"})


def _doc_terms(tree):
    """Termos embutidos na árvore de um documento: {"$term": termo} e a chave interpolada {"$key": termo, ...}."""
    stack = [tree]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            emb = False
            for kk in ("$term", "$key"):
                t = x.get(kk)
                if isinstance(t, dict) and "kind" in t:
                    emb = True
                    yield t
            if "$term" in x and emb:
                continue
            stack.extend(v for kk, v in x.items() if kk != "$key" or not emb)
        elif isinstance(x, list):
            stack.extend(x)


def term_class(term: dict) -> str:
    worst = "literal"
    stack = [term]
    while stack:
        t = stack.pop()
        k = t.get("kind")
        if k == "withheld":
            return "withheld"
        if k == "reference":
            worst = "symbolic"
        elif k == "symbol":
            if t.get("name_class") in NONGROUND_CLASSES:
                worst = "symbolic"
        elif k == "expression":
            if t.get("op") in NONGROUND_FUNCS or t.get("op") in NONGROUND_OPS:
                worst = "symbolic"
            stack.extend(a for a in t.get("args") or [] if isinstance(a, dict))
        elif k == "document":
            stack.extend(_doc_terms(t.get("tree")))
    return worst


def is_explicit_null(term: dict) -> bool:
    return term.get("kind") == "literal" and term.get("datatype") == "null"


def load_atoms(lines) -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    """resource_type -> (caminhos de átomo do C01, caminhos de bloco que contêm átomos), do provider google."""
    import json
    by: dict[str, set[str]] = collections.defaultdict(set)
    for ln in lines:
        if not ln.strip():
            continue
        a = json.loads(ln)
        if a.get("provider") != "google":
            continue
        by[a["resource_type"]].add(a["path"])
    out = {}
    for k, v in by.items():
        blocks = set()
        for p in v:
            segs = p.split(".")
            blocks.update(".".join(segs[:i]) for i in range(1, len(segs)))
        out[k] = (frozenset(v), frozenset(blocks))
    return out


def resolve(atoms, rtype: str, attr_path: str, kind: str) -> tuple[str, str | None]:
    """(categoria, caminho do átomo). Categorias: atom, atom_object, meta, withheld_block, block_as_attribute,
    unmatched_type, unmatched_path, malformed."""
    cat, path = classify_path(attr_path)
    if cat in ("meta", "malformed"):
        return cat, None
    ent = atoms.get(rtype)
    if ent is None:
        return "unmatched_type", None
    known, blocks = ent
    if cat == "path" and path in known:
        return "atom", path
    segs = path.split(".")
    start = len(segs) if cat == "block" else len(segs) - 1
    for k in range(start, 0, -1):
        pre = ".".join(segs[:k])
        if pre in known:
            return "atom_object", pre  # atributo de tipo objeto escrito como bloco/caminho
    if cat == "block":
        return ("withheld_block" if kind == "withheld" else "unmatched_path"), None
    if path in blocks:
        return "block_as_attribute", None  # bloco atribuído com sintaxe de atributo (ex.: x = []): sem átomo
    return "unmatched_path", None


def count_repo(repo_id: str, family_id: str, resources, records, atoms) -> dict:
    """resources: [(file, resource_address, resource_type, n_attrs)] do google neste repositório (gerenciados e
    data; data fica fora da contagem). records: dicts C06 symbolic_config do google neste repositório.

    Devolve {"rows": [usage...], "atoms": {atom_id: [n_set, n_lit, n_sym, n_wh, n_mod, registros por KINDS...]},
    "types": {tipo: [n_res, n_mod, n_set, n_mod_set, tipo_no_schema]}, "cov": Counter, "check": Counter,
    "unmatched": [(tipo, caminho)]} (caminhos de tipo conhecido que nenhum átomo cobre)."""
    cov: collections.Counter = collections.Counter()
    chk: collections.Counter = collections.Counter()
    managed: dict[tuple[str, str], str] = {}
    n_attrs: dict[tuple[str, str], int] = {}
    data_keys: set[tuple[str, str]] = set()
    for file, addr, rtype, na in resources:
        key = (file, addr)
        if is_data(addr):
            data_keys.add(key)
            continue
        managed[key] = rtype
        n_attrs[key] = na
    # (file, addr) -> atom path -> classe ; e kinds por registro
    per_res: dict[tuple[str, str], dict[str, str]] = collections.defaultdict(dict)
    rec_kinds: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    seen_records: collections.Counter = collections.Counter()
    unmatched: set[tuple[str, str]] = set()
    for r in records:
        key = (r["file"], r["resource_address"])
        seen_records[key] += 1
        kind = r["term"]["kind"]
        if key in data_keys:
            cov["data_source_records"] += 1
            continue
        rtype = managed.get(key)
        if rtype is None:
            chk["records_without_resource_row"] += 1
            continue
        if rtype != r["resource_type"]:
            chk["records_type_mismatch"] += 1
            continue
        cat, apath = resolve(atoms, rtype, r["attr_path"], kind)
        if cat not in ("atom", "atom_object"):
            cov[f"records:{cat}"] += 1
            if cat == "unmatched_path":
                cov[f"unmatched_path_kind:{kind}"] += 1
                cp = classify_path(r["attr_path"])[1]
                unmatched.add((rtype, cp))
            continue
        if is_explicit_null(r["term"]):
            cov["records:explicit_null"] += 1
            continue
        cov[f"records:{cat}"] += 1
        c = term_class(r["term"])
        prev = per_res[key].get(apath)
        if prev is None or CLASS_RANK[c] > CLASS_RANK[prev]:
            per_res[key][apath] = c
        rec_kinds[(rtype, apath)][kind] += 1
    for key, na in n_attrs.items():
        if seen_records[key] != na:
            chk["resources_n_attrs_mismatch"] += 1
    for key in data_keys:
        cov["data_source_blocks"] += 1
    # agregação por (tipo) e (tipo, átomo)
    by_type: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for key, rtype in managed.items():
        by_type[rtype].append(key)
    rows, atoms_out, types_out = [], {}, {}
    for rtype in sorted(by_type):
        keys = by_type[rtype]
        n_res = len(keys)
        mods_type = {posixpath.dirname(f) for f, _ in keys}
        acc: dict[str, list] = {}
        t_cls = collections.Counter()
        t_mods = set()
        for key in keys:
            m = per_res.get(key)
            if not m:
                continue
            worst = "literal"
            for apath, c in m.items():
                a = acc.setdefault(apath, [0, 0, 0, 0, set()])
                a[0] += 1
                a[1 + CLASS_RANK[c]] += 1
                a[4].add(posixpath.dirname(key[0]))
                if CLASS_RANK[c] > CLASS_RANK[worst]:
                    worst = c
            t_cls[worst] += 1
            t_mods.add(posixpath.dirname(key[0]))
        known = rtype in atoms
        cov["resources_managed"] += n_res
        cov["resources_schema_type" if known else "resources_unknown_type"] += n_res
        n_set_t = sum(t_cls.values())
        rows.append({"repo_id": repo_id, "family_id": family_id, "provider": "google", "resource_type": rtype,
                     "n_resources": n_res, "n_set": n_set_t, "n_literal": t_cls["literal"],
                     "n_symbolic": t_cls["symbolic"], "n_withheld": t_cls["withheld"]})
        types_out[rtype] = [n_res, len(mods_type), n_set_t, len(t_mods), known]
        for apath in sorted(acc):
            n_set, n_lit, n_sym, n_wh, mods = acc[apath]
            atom_id = f"google:{rtype}:{apath}"
            rows.append({"repo_id": repo_id, "family_id": family_id, "provider": "google", "resource_type": rtype,
                         "atom_id": atom_id, "n_resources": n_res, "n_set": n_set, "n_literal": n_lit,
                         "n_symbolic": n_sym, "n_withheld": n_wh})
            k = rec_kinds[(rtype, apath)]
            atoms_out[atom_id] = [n_set, n_lit, n_sym, n_wh, len(mods)] + [k[x] for x in KINDS]
    cov["modules_managed"] += len({posixpath.dirname(f) for f, _ in managed})
    return {"rows": rows, "atoms": atoms_out, "types": types_out, "cov": cov, "check": chk,
            "unmatched": sorted(unmatched)}
