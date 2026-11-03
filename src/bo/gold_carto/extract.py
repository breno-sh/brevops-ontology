"""Leitura estática do Cartography: tarball conferido por sha256, ast.parse e um avaliador restrito.

Nada do Cartography é importado ou executado. O avaliador entende só o subconjunto que os arquivos de mapeamento
usam (constantes, dicionários com **, listas com *, nomes, chamadas aos construtores de specs.py, funções
auxiliares de um único return e compreensões de lista sobre literais). Qualquer outra forma levanta Unevaluable
com arquivo e linha: falha alta, nunca silêncio.
"""

from __future__ import annotations

import ast
import hashlib
import io
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from . import PROVIDERS, SOURCE_COMMIT, TARBALL, TARBALL_SHA256

MAPPING_PKG = "cartography.models.ontology.mapping"
SPECS = f"{MAPPING_PKG}.specs"
OPAQUE_PREFIXES = ("cartography.models.core", "typing", "dataclasses", "logging", "enum", "__future__")

# campos de cada construtor (ordem do dataclass em specs.py) e os que o avaliador precisa avaliar
CTORS = {
    "OntologyFieldMapping": ("ontology_field", "node_field", "required", "special_handling", "extra", "indexed"),
    "OntologyNodeMapping": ("node_label", "fields", "eligible_for_source"),
    "OntologyMapping": ("module_name", "nodes"),
    "ExtraNodeLabel": ("label",),
}
CTOR_DEFAULTS = {
    "OntologyFieldMapping": {"required": False, "special_handling": None, "extra": {}, "indexed": True},
    "OntologyNodeMapping": {"eligible_for_source": True},
    "OntologyMapping": {},
    "ExtraNodeLabel": {},
}


class Unevaluable(ValueError):
    pass


class Source:
    """Tarball do commit fixado, lido em memória depois de conferir o sha256."""

    def __init__(self, path: Path):
        data = Path(path).read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != TARBALL_SHA256:
            raise ValueError(f"tarball {path.name}: sha256 {got[:12]}... != fixado {TARBALL_SHA256[:12]}...")
        if Path(path).name != TARBALL:
            raise ValueError(f"tarball inesperado: {path.name}")
        self.sha256 = got
        self.files: dict[str, bytes] = {}
        top = f"cartography-{SOURCE_COMMIT}/"
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile() or not m.name.startswith(top):
                    continue
                rel = m.name[len(top):]
                if rel.endswith(".py") and rel.startswith("cartography/models/") or rel == "LICENSE":
                    self.files[rel] = tf.extractfile(m).read()

    def text(self, rel: str) -> str:
        return self.files[rel].decode("utf-8")

    def rel_of(self, dotted: str) -> str | None:
        base = dotted.replace(".", "/")
        for cand in (base + ".py", base + "/__init__.py"):
            if cand in self.files:
                return cand
        return None

    def py_files(self, prefix: str) -> list[str]:
        return sorted(r for r in self.files if r.startswith(prefix) and r.endswith(".py"))


@dataclass(frozen=True)
class Ctor:
    name: str


@dataclass(frozen=True)
class Opaque:
    what: str


@dataclass
class Function:
    env: "ModuleEnv"
    node: ast.FunctionDef


@dataclass
class ClassRef:
    env: "ModuleEnv"
    node: ast.ClassDef

    def label(self) -> str | None:
        for st in self.node.body:
            if (isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.target.id == "label"
                    and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str)):
                return st.value.value
        return None


@dataclass
class ModuleEnv:
    ev: "Evaluator"
    dotted: str
    rel: str
    tree: ast.Module
    assigns: dict = field(default_factory=dict)
    imports: dict = field(default_factory=dict)
    funcs: dict = field(default_factory=dict)
    classes: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    busy: set = field(default_factory=set)

    def __post_init__(self):
        pkg = self.dotted if self.rel.endswith("__init__.py") else self.dotted.rsplit(".", 1)[0]
        for st in self.tree.body:
            if isinstance(st, ast.ImportFrom):
                mod = st.module or ""
                if st.level:
                    parts = pkg.split(".")
                    mod = ".".join(parts[:len(parts) - (st.level - 1)] + ([mod] if mod else []))
                for a in st.names:
                    self.imports[a.asname or a.name] = (mod, a.name)
            elif isinstance(st, ast.Assign):
                for t in st.targets:
                    if isinstance(t, ast.Name):
                        self.assigns[t.id] = st.value
            elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
                self.assigns[st.target.id] = st.value
            elif isinstance(st, ast.FunctionDef):
                self.funcs[st.name] = st
            elif isinstance(st, ast.ClassDef):
                self.classes[st.name] = st

    def where(self, node) -> str:
        return f"{self.rel}:{getattr(node, 'lineno', '?')}"

    def get(self, name: str, at=None):
        if name in self.values:
            return self.values[name]
        if name in self.busy:
            raise Unevaluable(f"{self.where(at)}: definição cíclica de {name}")
        self.busy.add(name)
        try:
            if name in self.assigns:
                v = self.ev.eval(self.assigns[name], self, {})
            elif name in self.funcs:
                v = Function(self, self.funcs[name])
            elif name in self.classes:
                v = ClassRef(self, self.classes[name])
            elif name in self.imports:
                mod, orig = self.imports[name]
                v = self.ev.imported(mod, orig, self, at)
            else:
                raise Unevaluable(f"{self.where(at)}: nome {name} não definido no módulo")
        finally:
            self.busy.discard(name)
        self.values[name] = v
        return v


class Evaluator:
    def __init__(self, src: Source):
        self.src = src
        self.mods: dict[str, ModuleEnv] = {}

    def module(self, dotted: str) -> ModuleEnv:
        if dotted not in self.mods:
            rel = self.src.rel_of(dotted)
            if rel is None:
                raise Unevaluable(f"módulo {dotted} fora do tarball")
            self.mods[dotted] = ModuleEnv(self, dotted, rel, ast.parse(self.src.text(rel), filename=rel))
        return self.mods[dotted]

    def imported(self, mod: str, orig: str, env: ModuleEnv, at):
        if mod == SPECS and orig in CTORS:
            return Ctor(orig)
        if mod == "cartography.models.core.nodes" and orig == "ExtraNodeLabel":
            return Ctor(orig)
        if mod.startswith(OPAQUE_PREFIXES) or not mod.startswith("cartography"):
            return Opaque(f"{mod}.{orig}")
        target = self.module(mod)
        if orig in target.assigns or orig in target.funcs or orig in target.classes or orig in target.imports:
            return target.get(orig, at)
        sub = self.src.rel_of(f"{mod}.{orig}")
        if sub is not None:
            return self.module(f"{mod}.{orig}")
        raise Unevaluable(f"{env.where(at)}: {orig} não existe em {mod}")

    # ------------------------------------------------------------------ expressões
    def eval(self, node, env: ModuleEnv, local: dict):
        E = lambda n: self.eval(n, env, local)  # noqa: E731
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in local:
                return local[node.id]
            if node.id in ("True", "False", "None"):
                return {"True": True, "False": False, "None": None}[node.id]
            return env.get(node.id, node)
        if isinstance(node, ast.Dict):
            out = {}
            for k, v in zip(node.keys, node.values):
                if k is None:
                    sub = E(v)
                    if not isinstance(sub, dict):
                        raise Unevaluable(f"{env.where(node)}: ** sobre algo que não é dicionário")
                    out.update(sub)
                else:
                    out[E(k)] = E(v)
            return out
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            out = []
            for e in node.elts:
                if isinstance(e, ast.Starred):
                    out.extend(E(e.value))
                else:
                    out.append(E(e))
            return out if isinstance(node, ast.List) else tuple(out) if isinstance(node, ast.Tuple) else frozenset(out)
        if isinstance(node, ast.ListComp):
            if len(node.generators) != 1 or not isinstance(node.generators[0].target, ast.Name):
                raise Unevaluable(f"{env.where(node)}: compreensão fora do subconjunto")
            g = node.generators[0]
            out = []
            for item in E(g.iter):
                loc = dict(local)
                loc[g.target.id] = item
                if all(self.eval(c, env, loc) for c in g.ifs):
                    out.append(self.eval(node.elt, env, loc))
            return out
        if isinstance(node, ast.Call):
            return self.call(node, env, local)
        if isinstance(node, ast.Subscript):
            base, idx = E(node.value), E(node.slice)
            try:
                return base[idx]
            except Exception as e:  # noqa: BLE001
                raise Unevaluable(f"{env.where(node)}: subscrito não avaliável: {e}") from None
        raise Unevaluable(f"{env.where(node)}: expressão {type(node).__name__} fora do subconjunto")

    def call(self, node: ast.Call, env: ModuleEnv, local: dict):
        f = self.eval(node.func, env, local)
        if isinstance(f, Ctor):
            names = CTORS[f.name]
            out = dict(CTOR_DEFAULTS[f.name])
            for i, a in enumerate(node.args):
                if i < len(names):
                    out[names[i]] = self.eval(a, env, local)
            for kw in node.keywords:
                if kw.arg is None:
                    raise Unevaluable(f"{env.where(node)}: **kwargs em {f.name}")
                if kw.arg in names:
                    out[kw.arg] = self.eval(kw.value, env, local)
                elif f.name != "ExtraNodeLabel":
                    raise Unevaluable(f"{env.where(node)}: {f.name} sem o campo {kw.arg}")
            out["_ctor"] = f.name
            out["_file"] = env.rel
            out["_line"] = node.lineno
            return out
        if isinstance(f, Function):
            fn = f.node
            body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
            if len(body) != 1 or not isinstance(body[0], ast.Return) or fn.args.vararg or fn.args.kwarg:
                raise Unevaluable(f"{f.env.where(fn)}: função {fn.name} fora do subconjunto (um único return)")
            params = [a.arg for a in fn.args.args]
            defaults = fn.args.defaults
            loc = {}
            for p, d in zip(params[len(params) - len(defaults):], defaults):
                loc[p] = self.eval(d, f.env, {})
            for p, a in zip(params, node.args):
                loc[p] = self.eval(a, env, local)
            for kw in node.keywords:
                if kw.arg not in params:
                    raise Unevaluable(f"{env.where(node)}: argumento {kw.arg} desconhecido em {fn.name}")
                loc[kw.arg] = self.eval(kw.value, env, local)
            missing = [p for p in params if p not in loc]
            if missing:
                raise Unevaluable(f"{env.where(node)}: {fn.name} sem argumentos {missing}")
            res = self.eval(body[0].value, f.env, loc)
            if isinstance(res, dict):
                res = dict(res, _site_file=env.rel, _site_line=node.lineno, _via=fn.name)
            return res
        raise Unevaluable(f"{env.where(node)}: chamada a {ast.unparse(node.func)} fora do subconjunto")


# ---------------------------------------------------------------------------------------- mapeamentos
def _category_labels(ev: Evaluator) -> dict:
    init = ev.module(MAPPING_PKG)
    labels = {}
    for cat, v in init.get("SEMANTIC_LABEL_BY_CATEGORY").items():
        labels[cat] = v["label"]
    for cat, cls in init.get("ONTOLOGY_MODELS").items():
        if isinstance(cls, ClassRef) and cls.label():
            labels[cat] = cls.label()
    return labels


def field_mappings(src: Source) -> dict:
    """Todos os OntologyFieldMapping, com registro (semantic_label | ontology_node), categoria, rótulo da classe
    da ontologia, módulo, rótulo do nó, arquivo e linha. Devolve também as contagens por módulo (fora de escopo
    inclusive)."""
    ev = Evaluator(src)
    init = ev.module(MAPPING_PKG)
    cat_label = _category_labels(ev)
    rows, per_module = [], {}
    for registry, var in (("ontology_node", "ONTOLOGY_NODES_MAPPING"), ("semantic_label", "SEMANTIC_LABELS_MAPPING")):
        for cat, by_module in init.get(var).items():
            if cat not in cat_label:
                raise Unevaluable(f"categoria {cat} sem rótulo de ontologia")
            for key, om in by_module.items():
                mod = om["module_name"]
                for nm in om["nodes"]:
                    for fm in nm["fields"]:
                        per_module.setdefault(mod, 0)
                        per_module[mod] += 1
                        rows.append({
                            "registry": registry, "category": cat, "ontology_label": cat_label[cat],
                            "module": mod, "mapping_key": key, "node_label": nm["node_label"],
                            "eligible_for_source": nm["eligible_for_source"],
                            "ontology_field": fm["ontology_field"], "node_field": fm["node_field"],
                            "required": fm["required"], "special_handling": fm["special_handling"],
                            "extra": _plain(fm["extra"]), "indexed": fm["indexed"],
                            "file": fm.get("_site_file", fm["_file"]), "line": fm.get("_site_line", fm["_line"]),
                            "via": fm.get("_via"),
                        })
    rows.sort(key=lambda r: (r["module"], r["category"], r["node_label"], r["ontology_field"], r["node_field"],
                             r["mapping_key"], r["file"], r["line"]))
    return {"rows": rows, "per_module": dict(sorted(per_module.items())), "category_labels": cat_label,
            "in_scope": [r for r in rows if r["module"] in PROVIDERS]}


def _plain(v):
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, frozenset):
        return sorted(_plain(x) for x in v)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    raise Unevaluable(f"valor não literal em extra: {type(v).__name__}")


# --------------------------------------------------------------------------- registro de campos de API
def _call_name(n) -> str | None:
    if isinstance(n, ast.Call):
        return n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else None
    return None


def api_field_registry(src: Source) -> list[dict]:
    """Esquemas de nó do Cartography (CartographyNodeSchema com label) e as PropertyRef das propriedades.

    A chave da PropertyRef é o nome do campo no registro que a ingestão do Cartography entrega ao carregador
    (resposta da API depois da transformação do Cartography); set_in_kwargs marca valor vindo do contexto da
    sincronização, não do registro da API."""
    classes: dict[str, list] = {}
    parsed = {}
    for rel in src.py_files("cartography/models/"):
        if rel.startswith("cartography/models/ontology/mapping/"):
            continue
        tree = ast.parse(src.text(rel), filename=rel)
        parsed[rel] = tree
        for st in tree.body:
            if isinstance(st, ast.ClassDef):
                classes.setdefault(st.name, []).append((rel, st))

    def props_of(rel: str, cname: str, seen=frozenset()) -> dict:
        cands = classes.get(cname) or []
        same = [c for c in cands if c[0] == rel] or cands
        out = {}
        for crel, cdef in same:
            if (crel, cname) in seen:
                continue
            for b in cdef.bases:
                if isinstance(b, ast.Name) and b.id not in ("CartographyNodeProperties",):
                    for k, v in props_of(crel, b.id, seen | {(crel, cname)}).items():
                        out.setdefault(k, v)
            for st in cdef.body:
                if (isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)
                        and _call_name(st.value) == "PropertyRef"):
                    a0 = st.value.args[0] if st.value.args else None
                    key = a0.value if isinstance(a0, ast.Constant) and isinstance(a0.value, str) else None
                    kw = {k.arg: k.value for k in st.value.keywords}
                    sik = kw.get("set_in_kwargs")
                    out[st.target.id] = {"source_key": key, "set_in_kwargs": bool(
                        isinstance(sik, ast.Constant) and sik.value is True), "file": crel, "line": st.lineno}
        return out

    reg = []
    for rel, tree in parsed.items():
        for st in tree.body:
            if not isinstance(st, ast.ClassDef):
                continue
            label, props_cls = None, None
            for b in st.body:
                if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                    if b.target.id == "label" and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                        label = b.value.value
                    if b.target.id == "properties" and isinstance(b.annotation, ast.Name):
                        props_cls = b.annotation.id
            if not label or not props_cls:
                continue
            for prop, info in sorted(props_of(rel, props_cls).items()):
                reg.append({"node_label": label, "schema": st.name, "schema_file": rel, "property": prop, **info})
    reg.sort(key=lambda r: (r["node_label"], r["schema_file"], r["schema"], r["property"]))
    return reg
