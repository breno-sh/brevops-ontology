"""Extrator do Fix Inventory: classes Python lidas por AST (nunca importadas nem executadas).

Classe = `class X(...)` com `kind: ClassVar[str] = "..."`. Neutra = definida em fixlib/baseresources.py; de provedor
= plugins/{aws,gcp,azure}. Propriedade = atributo anotado (não ClassVar, sem '_' inicial) do corpo da classe, com a
descrição de `field(metadata={"description": ...})`. Vínculos publicados:
  (a) classe: kind do provedor -> kinds base mais próximos na herança (os mais específicos; 'resource' só quando é o
      único), construção python:inheritance;
  (b) propriedade: entrada do dicionário `mapping` do kind do provedor cuja chave é atributo herdado de um kind base
      e cujo valor começa por S("Campo", ...) -> o caminho da resposta da API alimenta a propriedade base
      (construção fix:mapping). Valores que não partem de S(...) não viram vínculo e são contados.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .common import Cls, Extract, Link, Prop, clean, local

PLUGIN_PROVIDER = {"aws": "aws", "gcp": "google", "azure": "azurerm"}


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def _is_classvar(ann) -> bool:
    s = ast.unparse(ann)
    return s.startswith("ClassVar")


def _field_desc(value) -> str:
    if isinstance(value, ast.Call):
        for kw in value.keywords:
            if kw.arg == "metadata" and isinstance(kw.value, ast.Dict):
                for k, v in zip(kw.value.keys, kw.value.values):
                    if _const(k) == "description" and isinstance(_const(v), str):
                        return _const(v)
    return ""


def _s_path(value) -> list | None:
    """Caminho do primeiro S("a", "b") à esquerda de uma cadeia S(...) >> ... ; None se não começar por S."""
    node = value
    while isinstance(node, ast.BinOp):
        node = node.left
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "S":
        args = [_const(a) for a in node.args]
        if args and all(isinstance(a, str) for a in args):
            return args
    return None


class _C:
    def __init__(self, name, file_label, provider, node, kind, consts):
        self.name, self.file, self.provider, self.node, self.kind = name, file_label, provider, node, kind
        self.bases = [ast.unparse(b).split(".")[-1] for b in node.bases]
        self.display = self.desc = ""
        self.attrs: dict[str, tuple[str, str, int]] = {}
        self.mapping: dict[str, tuple[list | None, int]] = {}
        for st in node.body:
            if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                n = st.target.id
                if n == "_kind_display" and st.value is not None:
                    self.display = _const(st.value) or ""
                elif n == "_kind_description" and st.value is not None:
                    self.desc = _const(st.value) or ""
                elif n == "mapping" and isinstance(st.value, ast.Dict):
                    for k, v in zip(st.value.keys, st.value.values):
                        if isinstance(_const(k), str):
                            self.mapping[_const(k)] = (_s_path(v), k.lineno)
                elif not n.startswith("_") and not _is_classvar(st.annotation):
                    self.attrs[n] = (ast.unparse(st.annotation).replace(" ", ""), _field_desc(st.value), st.lineno)


def _load(path: Path, label: str, provider: str) -> list[_C]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=label)
    consts = {}
    for st in tree.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            if isinstance(_const(st.value), str):
                consts[st.targets[0].id] = _const(st.value)
    out = []
    for st in ast.walk(tree):
        if not isinstance(st, ast.ClassDef):
            continue
        kind = None
        for b in st.body:
            if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name) and b.target.id == "kind":
                kind = _const(b.value) if b.value is not None else None
        out.append(_C(st.name, label, provider, st, kind, consts))
    return out


def extract(model: str, base_file: tuple[str, Path], plugin_files: list[tuple[str, Path, str]]) -> Extract:
    ex = Extract(model=model, files=[base_file] + [(lb, p) for lb, p, _ in plugin_files])
    base = _load(base_file[1], base_file[0], "")
    plugins = []
    for lb, p, plug in plugin_files:
        plugins += _load(p, lb, PLUGIN_PROVIDER[plug])
    by_file, by_prov = {}, {}
    for c in base + plugins:
        by_file.setdefault(c.file, {})[c.name] = c
        by_prov.setdefault(c.provider, {}).setdefault(c.name, c)
    base_names = {c.name: c for c in base}

    def resolve(c: _C, bname: str) -> _C | None:
        return by_file[c.file].get(bname) or by_prov.get(c.provider, {}).get(bname) or base_names.get(bname)

    def anc_kinded(c: _C, seen=None) -> list[_C]:
        seen = seen or set()
        out = []
        for b in c.bases:
            r = resolve(c, b)
            if r is None or id(r) in seen:
                continue
            seen.add(id(r))
            if r.kind:
                out.append(r)
            out += anc_kinded(r, seen)
        return out

    def nearest_base(c: _C) -> list[_C]:
        found, stack, seen = [], [c], set()
        while stack:
            x = stack.pop()
            for b in x.bases:
                r = resolve(x, b)
                if r is None or id(r) in seen:
                    continue
                seen.add(id(r))
                if r.provider == "" and r.kind:
                    found.append(r)
                else:
                    stack.append(r)
        # mais específicos: descarta base que é ancestral de outra base encontrada
        anc_of = {id(f): {id(a) for a in anc_kinded(f)} for f in found}
        keep = [f for f in found if not any(id(f) in anc_of[id(g)] for g in found if g is not f)]
        uniq = {f.kind: f for f in keep}
        return [uniq[k] for k in sorted(uniq)]

    kinded = [c for c in base + plugins if c.kind]
    idx, dup_kinds = {}, 0
    for c in kinded:
        if c.kind in idx:
            dup_kinds += 1
        idx.setdefault(c.kind, c)
    for c in kinded:
        if idx[c.kind] is not c:
            continue
        parents = sorted({f"fix:{local(a.kind)}" for a in (resolve(c, b) for b in c.bases) if a is not None and a.kind}
                         | {f"fix:{local(a.kind)}" for a in _first_kinded(c, resolve)})
        ex.classes.append(Cls(id=f"fix:{local(c.kind)}", native=c.kind, label=c.display or c.kind,
                              definition=clean(c.desc), parents=sorted(set(parents)), provider=c.provider,
                              source=c.file, line=c.node.lineno))
        for a, (ann, desc, ln) in sorted(c.attrs.items()):
            ex.props.append(Prop(id=f"fixp:{local(c.kind)}.{local(a)}", native=f"{c.kind}.{a}", label=a,
                                 kind="datatype", domain=[f"fix:{local(c.kind)}"], domain_kind="class_member",
                                 range=f"py:{local(ann)}", definition=clean(desc), provider=c.provider,
                                 source=c.file, line=ln))
    root_res = next((c for c in base if c.kind == "resource"), None)
    for c in kinded:
        if c.provider and idx[c.kind] is c and root_res is not None and any(a is root_res for a in anc_kinded(c)):
            ex.provider_terms.setdefault(c.provider, []).append(f"fix:{local(c.kind)}")
    ex.provider_unit = "kinds de recurso de provedor (herdam de BaseResource)"
    n_map = n_map_s = 0
    for c in kinded:
        if not c.provider or idx[c.kind] is not c:
            continue
        nb = nearest_base(c)
        for b in nb:
            ex.links.append(Link(subject=f"fix:{local(c.kind)}", object=f"fix:{local(b.kind)}",
                                 native_relation="python:inheritance", link_kind="provider_class_to_model_class",
                                 level="class", provider=c.provider, source=c.file, line=c.node.lineno,
                                 sentence=f"class {c.name}({', '.join(c.bases)}) -> base {b.name} (kind {b.kind})",
                                 subject_label=c.display or c.kind, object_label=b.display or b.kind))
        base_attr = {}
        for a in anc_kinded(c):
            if a.provider == "":
                for k in a.attrs:
                    base_attr.setdefault(k, a)
        for key, (path, ln) in sorted(c.mapping.items()):
            if key not in base_attr:
                continue
            n_map += 1
            if path is None:
                continue
            n_map_s += 1
            owner = base_attr[key]
            ex.links.append(Link(subject=f"fixapi_{c.provider}:{local(c.kind)}/{local('.'.join(path))}",
                                 object=f"fixp:{local(owner.kind)}.{local(key)}", native_relation="fix:mapping",
                                 link_kind="provider_field_to_model_property", level="property",
                                 provider=c.provider, source=c.file, line=ln,
                                 sentence=f"{c.name}.mapping[{key!r}] = S({', '.join(repr(x) for x in path)}) ...",
                                 subject_label=".".join(path), object_label=f"{owner.kind}.{key}"))
    ex.prefixes = {"fix": "https://github.com/someengineering/fixinventory#kind/",
                   "fixp": "https://github.com/someengineering/fixinventory#property/",
                   "py": "https://docs.python.org/3/library/typing.html#",
                   **{f"fixapi_{p}": f"https://github.com/someengineering/fixinventory#api/{p}/"
                      for p in PLUGIN_PROVIDER.values()}}
    ex.counts = {"kinds": len(ex.classes), "kinds_base": sum(1 for c in ex.classes if not c.provider),
                 "attributes": len(ex.props), "mapping_entries_on_base_properties": n_map,
                 "mapping_entries_from_S_path": n_map_s,
                 "mapping_entries_not_S_path": n_map - n_map_s,
                 "kinds_declared_twice_first_kept": dup_kinds}
    return ex


def _first_kinded(c, resolve) -> list:
    """Ancestrais com kind mais próximos (atravessa mixins sem kind)."""
    out, stack, seen = [], [c], set()
    while stack:
        x = stack.pop()
        for b in x.bases:
            r = resolve(x, b)
            if r is None or id(r) in seen:
                continue
            seen.add(id(r))
            if r.kind:
                out.append(r)
            else:
                stack.append(r)
    return out
