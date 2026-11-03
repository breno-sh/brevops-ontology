"""Item da página -> caminho de átomo no schema fixado (C01), por tipo documentado na página.

Regras (em ordem; o método vai para o relatório de resolução):
  1. tipos da página: títulos '# google_x' que existem no schema; se nenhum, google_<nome do arquivo> e, para
     páginas *_iam, google_<nome>_policy|_binding|_member|_audit_config que existem.
  2. contexto de topo de args/attrs = raiz (); da seção Timeouts = ('timeouts',).
  3. contexto de âncora nested_x: caminho = caminho do contexto do item que tem o link (#nested_x) + nome do item,
     se esse caminho é bloco do schema, átomo de tipo objeto ou subcampo dele (LINK). Repete até o ponto fixo; um contexto pode ter vários caminhos
     (a mesma estrutura documentada uma vez para dois blocos).
  4. contexto sem caminho por link: âncora nested_<caminho com '_'> igual a um único bloco ou átomo objeto
     (ANCHOR_PATH); senão, nome entre crases em 'The `x` block' com índices removidos; se é caminho de
     bloco, usa (NAME_PATH); senão, blocos cujo último nome é x: um só -> usa (NAME_UNIQUE); vários -> AMBIGUOUS.
  5. caminho do item = caminho do contexto (ou do item pai, se subitem) + nome do item sem índices ('.0', '.*',
     '[0]'); 'a/b' vale para a e para b. Subitem de item que não é bloco é texto do pai (sem caminho).
  6. caminho que é átomo -> ATOM; que é bloco -> BLOCK (bloco não é átomo no C01); dentro de átomo de tipo objeto
     -> OBJECT_FIELD (subcampo não é átomo no C01); senão NOT_IN_SCHEMA.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .mdparse import Page

IAM_SUFFIXES = ("_policy", "_binding", "_member", "_audit_config")


def page_types(pg: Page, stem: str, schema_types: set) -> list:
    ts = []
    for t, _ in pg.types:
        if t in schema_types and t not in ts:
            ts.append(t)
    if ts:
        return ts
    cand = "google_" + stem
    if cand in schema_types:
        return [cand]
    if stem.endswith("_iam"):
        return [cand + s for s in IAM_SUFFIXES if cand + s in schema_types]
    return []


def split_name(name: str) -> list:
    """'network_interface.0.access_config.*.nat_ip' -> ['network_interface', 'access_config', 'nat_ip']."""
    name = re.sub(r"\[[^\]]*\]", "", name)
    return [p for p in name.split(".") if p and p != "*" and not p.isdigit()]


@dataclass
class TypeIndex:
    atoms: set
    blocks: set
    by_last: dict

    objattrs: set

    @classmethod
    def of(cls, ts) -> "TypeIndex":
        atoms = {a["path"] for a in ts.atoms}
        blocks = {".".join(b.path) for b in ts.blocks}
        # átomo de tipo objeto (ex.: list(object) computado): os subcampos documentados não são átomos no C01
        objattrs = {a["path"] for a in ts.atoms if "object" in json.dumps(a["tf_type"])}
        by_last: dict = {}
        for b in sorted(blocks | objattrs):
            by_last.setdefault(b.rsplit(".", 1)[-1], []).append(b)
        return cls(atoms, blocks, by_last, objattrs)

    def container(self, p: str) -> bool:
        return p in self.blocks or p in self.objattrs

    def classify(self, p: str) -> str:
        if p in self.atoms:
            return "ATOM"
        if p in self.blocks:
            return "BLOCK"
        parts = p.split(".")
        if any(".".join(parts[:k]) in self.objattrs for k in range(1, len(parts))):
            return "OBJECT_FIELD"
        return "NOT_IN_SCHEMA"


def context_paths(pg: Page, idx: TypeIndex) -> tuple[dict, dict]:
    """{ctx: [caminhos (tuplas)]} e {ctx: método}."""
    paths: dict = {}
    how: dict = {}
    for c in pg.contexts:
        if c.anchor is None and c.name is None:
            paths[c.idx] = [("timeouts",)] if c.section == "timeouts" else [()]
            how[c.idx] = "TOP"
    by_anchor: dict = {}
    for c in pg.contexts:
        if c.anchor:
            by_anchor.setdefault(c.anchor, []).append(c.idx)
    changed = True
    while changed:
        changed = False
        for b in pg.bullets:
            if not b.links or b.ctx not in paths or b.parent is not None:
                continue
            for base in paths[b.ctx]:
                for nm in b.name.split("/"):
                    p = base + tuple(split_name(nm))
                    if not (idx.container(".".join(p)) or idx.classify(".".join(p)) == "OBJECT_FIELD"):
                        continue
                    for a in b.links:
                        for ci in by_anchor.get(a, []):
                            cur = paths.setdefault(ci, [])
                            if p not in cur:
                                cur.append(p)
                                how[ci] = "LINK"
                                changed = True
    by_joined: dict = {}
    for b in sorted(idx.blocks | idx.objattrs):
        by_joined.setdefault(b.replace(".", "_"), []).append(b)
    for c in pg.contexts:
        if c.idx in paths or c.name is None:
            continue
        if c.anchor and c.anchor.startswith("nested_") and len(by_joined.get(c.anchor[7:], [])) == 1:
            paths[c.idx], how[c.idx] = [tuple(by_joined[c.anchor[7:]][0].split("."))], "ANCHOR_PATH"
            continue
        nm = ".".join(split_name(c.name))
        if idx.container(nm):
            paths[c.idx], how[c.idx] = [tuple(nm.split("."))], "NAME_PATH"
            continue
        cands = idx.by_last.get(nm.rsplit(".", 1)[-1], [])
        if len(cands) == 1:
            paths[c.idx], how[c.idx] = [tuple(cands[0].split("."))], "NAME_UNIQUE"
        elif len(cands) > 1:
            paths[c.idx], how[c.idx] = [], "AMBIGUOUS"
        else:
            paths[c.idx], how[c.idx] = [], "NO_BLOCK"
    return paths, how


def bullet_paths(pg: Page, idx: TypeIndex) -> tuple[list, dict]:
    """Para cada item: [(caminho, classe)] e o método do contexto. classe = ATOM | BLOCK | NOT_IN_SCHEMA."""
    cpaths, how = context_paths(pg, idx)
    res: list = []
    for i, b in enumerate(pg.bullets):
        if b.parent is not None:
            # subitem: só vale como item se o pai é bloco; senão é texto do pai (lista de valores, notas)
            bases = [tuple(p.split(".")) for p, cls in res[b.parent] if cls == "BLOCK" or p in idx.objattrs]
        else:
            bases = cpaths.get(b.ctx, [])
        out = []
        for base in bases:
            for nm in b.name.split("/"):
                p = ".".join(base + tuple(split_name(nm)))
                cls = idx.classify(p)
                if (p, cls) not in out:
                    out.append((p, cls))
        res.append(out)
    return res, how
