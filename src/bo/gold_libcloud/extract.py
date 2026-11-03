"""Extração: de cada driver de compute, storage, DNS e load balancer, que campo da API alimenta cada campo
normalizado do Libcloud. Só ast; nada do Libcloud é importado.

Campo normalizado = parâmetro do __init__ de uma classe pública de libcloud/<domínio>/base.py que tem o
parâmetro 'extra' (as classes de recurso; autenticação e drivers não têm), menos 'driver'. O dicionário
'extra' é aberto chave a chave, mas as chaves de extra são do driver, não normalizadas: vão para o
registro de campos (extra_fields.jsonl), não para o SSSOM.

Cada argumento de cada construção vira uma 'alimentação' (feed) com um destes tipos:
  api       ao menos uma origem é campo da API (raiz + caminho não vazio)
  input     só parâmetro repassado inteiro (entrada do usuário ou objeto do chamador, ex. create_node(name))
  constant  só literal/constante do código (ex. country='US', state=NodeState.RUNNING)
  context   só objeto do próprio Libcloud (container=container, zone=zone, self.x)
  opaque    nenhuma das anteriores: chamada que o interpretador não segue -> UNRESOLVED
  absent    o argumento não é passado nessa construção
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from . import flow
from .flow import NOCONST, O, Sym, V, const_eval

DOMAINS = ("compute", "storage", "dns", "loadbalancer")
SKIP_PARAMS = {"self", "driver"}

# Provedor do projeto (§1: AWS, GCP, Azure, OCI) por módulo de driver. Tabela escrita à mão a partir do
# nome do módulo e das classes; tudo o que não está aqui é 'other'. Classes de API compatível que herdam
# do driver AWS (Eucalyptus, Nimbus, Outscale) são 'other' quando o método é delas.
PROJECT_PROVIDER = {
    ("compute", "ec2"): "aws", ("storage", "s3"): "aws", ("dns", "route53"): "aws",
    ("loadbalancer", "elb"): "aws", ("loadbalancer", "alb"): "aws",
    ("compute", "gce"): "gcp", ("storage", "google_storage"): "gcp", ("dns", "google"): "gcp",
    ("loadbalancer", "gce"): "gcp",
    ("compute", "azure_arm"): "azure", ("compute", "azure"): "azure", ("storage", "azure_blobs"): "azure",
}
NOT_PROJECT_CLASS_PREFIX = ("Euc", "Nimbus", "Outscale")


def project_provider(domain: str, stem: str, cls: str) -> str:
    p = PROJECT_PROVIDER.get((domain, stem), "other")
    if p == "aws" and cls.startswith(NOT_PROJECT_CLASS_PREFIX):
        return "other"
    return p


@dataclass
class Normalized:
    domain: str
    cls: str
    params: list           # parâmetros do __init__ sem self, na ordem
    fields: list           # params - driver
    line: int


def normalized_classes(pkg: Path) -> dict[str, Normalized]:
    out = {}
    for d in DOMAINS:
        p = pkg / d / "base.py"
        if not p.is_file():
            continue
        t = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for n in t.body:
            if not isinstance(n, ast.ClassDef) or n.name.startswith("_"):
                continue
            init = next((m for m in n.body if isinstance(m, ast.FunctionDef) and m.name == "__init__"), None)
            if init is None:
                continue
            params = [a.arg for a in init.args.args][1:]
            if "extra" not in params:
                continue
            out[f"{d}.{n.name}"] = Normalized(d, n.name, params, [x for x in params if x not in SKIP_PARAMS],
                                              n.lineno)
    return out


def sym_values(pkg: Path) -> dict[str, object]:
    """Constantes de classe de libcloud/<domínio>/types.py (NodeState.RUNNING -> 'running')."""
    out = {}
    for d in DOMAINS:
        p = pkg / d / "types.py"
        if not p.is_file():
            continue
        t = ast.parse(p.read_text(encoding="utf-8"))
        for n in t.body:
            if isinstance(n, ast.ClassDef):
                for s in n.body:
                    if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
                        v = const_eval(s.value)
                        if isinstance(v, (str, int)) and not isinstance(v, Sym):
                            out[f"{n.name}.{s.targets[0].id}"] = v
    return out


class Registry:
    """Módulos .py do pacote, analisados sob demanda (para seguir imports de classes e bases)."""

    def __init__(self, pkg: Path, norm: dict[str, Normalized]):
        self.pkg, self.norm, self.mods = pkg, norm, {}
        self.base_names = {}   # (modname, clsname) -> chave normalizada, para as próprias bases
        for k, n in norm.items():
            self.base_names[(f"libcloud.{n.domain}.base", n.cls)] = k

    def module(self, modname: str) -> "Module | None":
        if modname in self.mods:
            return self.mods[modname]
        if not modname.startswith("libcloud."):
            self.mods[modname] = None
            return None
        rel = Path(*modname.split(".")[1:])
        p = self.pkg / rel.with_suffix(".py")
        if not p.is_file():
            p = self.pkg / rel / "__init__.py"
        m = Module(self, modname, p) if p.is_file() and modname.startswith("libcloud.") else None
        self.mods[modname] = m
        return m


class Module:
    def __init__(self, reg: Registry, modname: str, path: Path):
        self.reg, self.modname, self.path = reg, modname, path
        self.rel = path.relative_to(reg.pkg.parent).as_posix()
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        self.consts, self.functions, self.classes, self.imports = {}, {}, {}, {}
        self.tables: dict[str, object] = {}
        for n in self.tree.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                v = const_eval(n.value, self.consts)
                if v is not NOCONST and not isinstance(v, Sym):
                    self.consts[n.targets[0].id] = v
            elif isinstance(n, ast.FunctionDef):
                self.functions[n.name] = n
            elif isinstance(n, ast.ClassDef):
                self.classes[n.name] = n
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                for a in n.names:
                    self.imports[a.asname or a.name] = (n.module, a.name)
        self._target_cache: dict[str, object] = {}
        self._mro_cache: dict[str, list] = {}
        self.callsites: list = []     # (chamador, chamado, {parâmetro: V}) das análises de profundidade 0

    def api_params(self) -> set:
        """Parâmetros que recebem dado da API: ponto fixo a partir das respostas (connection.request).
        Um parâmetro (classe, função, nome) é da API se algum chamador no mesmo arquivo passa um valor com
        origem em resposta ou em outro parâmetro da API. O resto é entrada (do usuário ou do chamador)."""
        api: set = set()
        changed = True
        while changed:
            changed = False
            for caller, callee, bind in self.callsites:
                for p, v in bind.items():
                    key = (*callee, p)
                    if key in api:
                        continue
                    if any(o.kind == "field" and (o.root.startswith("response") or (*caller, o.root) in api)
                           for o in v.all_origins()):
                        api.add(key)
                        changed = True
        return api

    # ---------------------------------------------------------------- classes
    def resolve_class(self, name: str) -> tuple["Module", str] | None:
        if name in self.classes:
            return self, name
        if name in self.imports:
            mod, nm = self.imports[name]
            m = self.reg.module(mod)
            if m is not None and m is not self:
                return m.resolve_class(nm)
        return None

    def bases_of(self, cls: str) -> list[tuple["Module", str]]:
        node = self.classes.get(cls)
        if node is None:
            return []
        out = []
        for b in node.bases:
            d = flow.dotted(b)
            if not d:
                continue
            nm = d.split(".")[-1]
            r = self.resolve_class(nm)
            if r is not None:
                out.append(r)
        return out

    def mro(self, cls: str, seen=None) -> list[tuple["Module", str]]:
        if seen is None:
            if cls not in self._mro_cache:
                self._mro_cache[cls] = self.mro(cls, set())
            return self._mro_cache[cls]
        if (self.modname, cls) in seen:
            return []
        seen.add((self.modname, cls))
        out = [(self, cls)]
        for m, c in self.bases_of(cls):
            out += m.mro(c, seen)
        return out

    def method(self, cls: str | None, name: str):
        if cls is None:
            return None
        for m, c in self.mro(cls):
            node = m.classes.get(c)
            for s in node.body if node is not None else []:
                if isinstance(s, ast.FunctionDef) and s.name == name:
                    if m is not self:
                        return None   # método herdado de outro arquivo: não seguido (constantes de outro módulo)
                    return c, s
        return None

    def class_const(self, cls: str | None, attr: str):
        if cls is None:
            return NOCONST
        for m, c in self.mro(cls):
            node = m.classes.get(c)
            for s in node.body if node is not None else []:
                if isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == attr for t in s.targets):
                    return const_eval(s.value, m.consts)
        return NOCONST

    def normalized_base(self, cls: str) -> str | None:
        """Chave normalizada se cls é (ou herda de) uma classe normalizada."""
        for m, c in self.mro(cls):
            k = self.reg.base_names.get((m.modname, c))
            if k is not None:
                return k
        return None

    def init_params(self, cls: str) -> list[str] | None:
        """Parâmetros do primeiro __init__ na cadeia (sem self)."""
        for m, c in self.mro(cls):
            k = self.reg.base_names.get((m.modname, c))
            if k is not None:
                return self.reg.norm[k].params
            node = m.classes.get(c)
            init = next((s for s in node.body if isinstance(s, ast.FunctionDef) and s.name == "__init__"), None)
            if init is not None:
                return [a.arg for a in init.args.args][1:]
        return None

    def plain_class_attrs(self, f: ast.AST):
        """(parâmetros do __init__, {atributo: parâmetro}) para classe auxiliar (não normalizada) cujo __init__
        faz self.<a> = <parâmetro>; None se não é classe resolvida ou não tem __init__ assim."""
        name = flow.dotted(f).split(".")[-1] if flow.dotted(f) else ""
        if not name or not name[:1].isupper():
            return None
        key = "plain:" + name
        if key in self._target_cache:
            return self._target_cache[key]
        res = None
        r = self.resolve_class(name)
        if r is not None and r[0].normalized_base(r[1]) is None:
            m, c = r
            for mm, cc in m.mro(c):
                node = mm.classes.get(cc)
                init = next((s for s in node.body if isinstance(s, ast.FunctionDef) and s.name == "__init__"), None)
                if init is None:
                    continue
                params = [a.arg for a in init.args.args][1:]
                amap = {}
                for s in ast.walk(init):
                    if (isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Attribute)
                            and isinstance(s.targets[0].value, ast.Name) and s.targets[0].value.id == "self"
                            and isinstance(s.value, ast.Name) and s.value.id in params):
                        amap[s.targets[0].attr] = s.value.id
                res = (params, amap) if amap else None
                break
        self._target_cache[key] = res
        return res

    def target_of(self, f: ast.AST):
        """(chave normalizada, parâmetros do construtor chamado) se a chamada constrói um recurso normalizado."""
        name = flow.dotted(f).split(".")[-1] if flow.dotted(f) else ""
        if not name or not name[:1].isupper():
            return None
        if name in self._target_cache:
            return self._target_cache[name]
        res = None
        r = self.resolve_class(name)
        if r is not None:
            m, c = r
            k = m.normalized_base(c)
            if k is not None:
                res = (k, m.init_params(c) or self.reg.norm[k].params, f"{m.modname}.{c}")
        self._target_cache[name] = res
        return res


@dataclass
class Feed:
    site: str              # rel_path:line da construção
    line: int
    module: str            # rel_path
    domain: str            # domínio do driver (pasta)
    stem: str
    cls: str               # classe que contém a função ('_module' se função do módulo)
    func: str
    target: str            # chave normalizada (compute.Node)
    built_as: str          # classe efetivamente chamada
    field: str             # campo normalizado ('extra.<k>' para chave de extra)
    value: V
    provider: str


@dataclass
class Extraction:
    feeds: list = field(default_factory=list)
    absent: list = field(default_factory=list)       # (site, target, field)
    sites: int = 0
    functions: int = 0
    failures: list = field(default_factory=list)     # (module, func, erro)
    modules: list = field(default_factory=list)
    tables: dict = field(default_factory=dict)       # (module, nome) -> tabela
    api_params: dict = field(default_factory=dict)   # module -> {(classe, função, parâmetro)}


def driver_modules(pkg: Path) -> list[tuple[str, str, str]]:
    out = []
    for d in DOMAINS:
        for p in sorted((pkg / d / "drivers").glob("*.py")):
            if p.name == "__init__.py":
                continue
            out.append((d, p.stem, f"libcloud.{d}.drivers.{p.stem}"))
    return out


def iter_functions(mod: Module):
    for n in mod.tree.body:
        if isinstance(n, ast.FunctionDef):
            yield None, n
        elif isinstance(n, ast.ClassDef):
            for s in n.body:
                if isinstance(s, ast.FunctionDef):
                    yield n.name, s


def extract(pkg: Path) -> tuple[Extraction, dict[str, Normalized]]:
    norm = normalized_classes(pkg)
    reg = Registry(pkg, norm)
    ex = Extraction()
    for domain, stem, modname in driver_modules(pkg):
        mod = reg.module(modname)
        if mod is None:
            continue
        ex.modules.append(mod.rel)
        for cls, fn in iter_functions(mod):
            ex.functions += 1
            sites: dict[int, dict] = {}

            def sink(call, tgt, pos, kw, interp, sites=sites):
                key = id(call)
                params = tgt[1]
                bound = {}
                for p, v in zip(params, pos):
                    bound[p] = v
                bound.update({k: v for k, v in kw.items() if k in params})
                cur = sites.setdefault(key, {"call": call, "tgt": tgt, "bound": {}})
                for p, v in bound.items():
                    cur["bound"][p] = flow.join(cur["bound"][p], v) if p in cur["bound"] else v

            try:
                flow.Interp(mod, cls, fn, sink=sink).run()
            except RecursionError as e:
                ex.failures.append((mod.rel, f"{cls}.{fn.name}", type(e).__name__))
                continue
            for s in sorted(sites.values(), key=lambda s: (s["call"].lineno, s["call"].col_offset)):
                ex.sites += 1
                k, _, built = s["tgt"]
                nz = norm[k]
                site = f"{mod.rel}:{s['call'].lineno}"
                owner = cls or "_module"
                prov = project_provider(domain, stem, owner)
                for f in nz.fields:
                    v = s["bound"].get(f)
                    if v is None:
                        ex.absent.append((site, k, f))
                        continue
                    if f == "extra" and v.keys is not None:
                        for ek in sorted(k for k in v.keys if k != flow.ITEM):
                            ex.feeds.append(Feed(site, s["call"].lineno, mod.rel, domain, stem, owner, fn.name, k,
                                                 built, f"extra.{ek}", v.keys[ek], prov))
                        if not v.o - {o for o in v.o if o.kind == "const"}:
                            continue
                        v = V(v.o)
                    ex.feeds.append(Feed(site, s["call"].lineno, mod.rel, domain, stem, owner, fn.name, k, built,
                                         f, v, prov))
        ex.api_params[mod.rel] = mod.api_params()
        for name, t in mod.tables.items():
            ex.tables[(mod.rel, name)] = t
    return ex, norm
