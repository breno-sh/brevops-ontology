"""Extrator do módulo de ontologia do Cartography, por avaliação estática de AST (nunca importa nem executa).

Classes neutras: rótulos semânticos (ExtraNodeLabel de labels.py) e os nós canônicos (label dos *Schema de
user.py, device.py, package.py, package_version.py, publicip.py). Classes de provedor: os node_label dos
OntologyNodeMapping, com o provedor do module_name. Propriedades neutras: ontology_field de cada rótulo; de
provedor: node_field de cada nó de módulo. Vínculos publicados: nó do módulo -> rótulo (OntologyNodeMapping) e
node_field -> ontology_field (OntologyFieldMapping, com special_handling transcrito na nota).
"""

from __future__ import annotations

import ast
from pathlib import Path

from .common import Cls, Extract, Link, Prop, clean, local, provider_of

CALLS = {"OntologyMapping", "OntologyNodeMapping", "OntologyFieldMapping", "ExtraNodeLabel"}


class _Mod:
    def __init__(self, path: Path, label: str):
        self.label = label
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=label)
        self.env: dict[str, ast.AST] = {}
        for st in self.tree.body:
            tgt = None
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                tgt, val = st.targets[0].id, st.value
            elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
                tgt, val = st.target.id, st.value
            if tgt:
                self.env[tgt] = val
        self.imports = {}
        for st in self.tree.body:
            if isinstance(st, ast.ImportFrom) and st.module:
                for a in st.names:
                    self.imports[a.asname or a.name] = (st.module, a.name)

    def ev(self, node, ctx=None):
        """Avalia literal, nome de módulo, chamada conhecida -> dict com '__call__' e '__line__'."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.ev(x, ctx) for x in node.elts]
        if isinstance(node, ast.Dict):
            return {self.ev(k, ctx): self.ev(v, ctx) for k, v in zip(node.keys, node.values) if k is not None}
        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.ev(self.env[node.id], ctx)
            if ctx is not None and node.id in self.imports:
                return ctx.resolve(self.imports[node.id])
            return {"__name__": node.id}
        if isinstance(node, ast.Attribute):
            return {"__attr__": ast.unparse(node)}
        if isinstance(node, ast.Call):
            fn = ast.unparse(node.func).split(".")[-1]
            if fn in CALLS:
                d = {"__call__": fn, "__line__": node.lineno, "__file__": self.label}
                for kw in node.keywords:
                    d[kw.arg] = self.ev(kw.value, ctx)
                return d
            return {"__unevaluated__": ast.unparse(node)[:80]}
        return {"__unevaluated__": ast.unparse(node)[:80]}


class _Ctx:
    def __init__(self, root: Path, prefix: str):
        self.root, self.prefix, self.mods = root, prefix, {}

    def mod(self, dotted: str) -> _Mod | None:
        rel = dotted.replace(".", "/") + ".py"
        p = self.root / rel
        if not p.is_file():
            p = self.root / dotted.replace(".", "/") / "__init__.py"
            rel = dotted.replace(".", "/") + "/__init__.py"
        if not p.is_file():
            return None
        if rel not in self.mods:
            self.mods[rel] = _Mod(p, self.prefix + rel)
        return self.mods[rel]

    def resolve(self, ref):
        module, name = ref
        m = self.mod(module)
        if m is None or name not in m.env:
            return {"__name__": name, "__module__": module}
        return m.ev(m.env[name], self)


def _schema_label(m: _Mod, cls_name: str) -> tuple[str, int] | None:
    for st in m.tree.body:
        if isinstance(st, ast.ClassDef) and st.name == cls_name:
            for b in st.body:
                if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name) and b.target.id == "label":
                    if isinstance(b.value, ast.Constant):
                        return b.value.value, b.lineno
    return None


def extract(model: str, root: Path, label_prefix: str) -> Extract:
    ctx = _Ctx(root, label_prefix)
    init = ctx.mod("cartography.models.ontology.mapping")
    labels_mod = ctx.mod("cartography.models.ontology.labels")
    ex = Extract(model=model)
    neutral: dict[str, Cls] = {}
    for name, node in labels_mod.env.items():
        v = labels_mod.ev(node, ctx)
        if isinstance(v, dict) and v.get("__call__") == "ExtraNodeLabel":
            neutral[v["label"]] = Cls(id=f"carto:{local(v['label'])}", native=v["label"], label=v["label"],
                                      definition=clean(v.get("description")), source=labels_mod.label,
                                      line=v["__line__"])
    # nós canônicos (ONTOLOGY_MODELS -> *Schema.label)
    canon_cat = {}
    om = init.env.get("ONTOLOGY_MODELS")
    if isinstance(om, ast.Dict):
        for k, v in zip(om.keys, om.values):
            if isinstance(v, ast.Name) and v.id in init.imports:
                mod, cname = init.imports[v.id]
                m = ctx.mod(mod)
                lab = _schema_label(m, cname) if m else None
                if lab:
                    canon_cat[k.value] = lab[0]
                    neutral.setdefault(lab[0], Cls(id=f"carto:{local(lab[0])}", native=lab[0], label=lab[0],
                                                   definition="", source=m.label, line=lab[1]))
    cat_label = {}
    sl = init.env.get("SEMANTIC_LABEL_BY_CATEGORY")
    if isinstance(sl, ast.Dict):
        for k, v in zip(sl.keys, sl.values):
            lv = init.ev(v, ctx)
            if isinstance(lv, dict) and lv.get("__call__") == "ExtraNodeLabel":
                cat_label[k.value] = lv["label"]
    cat_label.update(canon_cat)
    ex.classes = [neutral[k] for k in sorted(neutral)]

    prov_cls: dict[str, Cls] = {}
    neutral_fields: dict[tuple, Prop] = {}
    prov_fields: dict[tuple, Prop] = {}
    unevaluated = 0
    for table in ("SEMANTIC_LABELS_MAPPING", "ONTOLOGY_NODES_MAPPING"):
        d = init.ev(init.env[table], ctx)
        for cat, per_module in sorted(d.items()):
            olabel = cat_label.get(cat)
            if olabel is None or not isinstance(per_module, dict):
                ex.notes.append(f"{table}[{cat}]: categoria sem rótulo resolvido; ignorada")
                continue
            for _, om_ in sorted(per_module.items()):
                if not isinstance(om_, dict) or om_.get("__call__") != "OntologyMapping":
                    unevaluated += 1
                    ex.notes.append(f"não avaliado estaticamente: {table}[{cat}] {str(om_)[:90]}")
                    continue
                prov = provider_of(om_.get("module_name", ""))
                for nm in om_.get("nodes") or []:
                    if not isinstance(nm, dict) or nm.get("__call__") != "OntologyNodeMapping":
                        unevaluated += 1
                        ex.notes.append(f"não avaliado estaticamente (nó): {table}[{cat}] module_name="
                                        f"{om_.get('module_name')!r}: {str(nm.get('__unevaluated__', nm))[:70]}")
                        continue
                    nl = nm["node_label"]
                    pc = prov_cls.setdefault(nl, Cls(id=f"cartonode:{local(nl)}", native=nl, label=nl,
                                                     provider=prov, source=nm["__file__"], line=nm["__line__"]))
                    if f"carto:{local(olabel)}" not in pc.parents:
                        pc.parents.append(f"carto:{local(olabel)}")
                    ex.links.append(Link(subject=pc.id, object=f"carto:{local(olabel)}",
                                         native_relation="cartography:OntologyNodeMapping",
                                         link_kind="provider_class_to_model_class", level="class", provider=prov,
                                         source=nm["__file__"], line=nm["__line__"],
                                         sentence=f"OntologyNodeMapping(node_label={nl!r}) em {table}[{cat!r}], "
                                                  f"module_name={om_.get('module_name')!r}",
                                         subject_label=nl, object_label=olabel))
                    for fm in nm.get("fields") or []:
                        if not isinstance(fm, dict) or fm.get("__call__") != "OntologyFieldMapping":
                            unevaluated += 1
                            ex.notes.append(f"não avaliado estaticamente (campo): {table}[{cat}] nó {nl}: "
                                            f"{str(fm.get('__unevaluated__', fm))[:70]}")
                            continue
                        of, nf = fm["ontology_field"], fm.get("node_field", "")
                        np_ = neutral_fields.setdefault((olabel, of), Prop(
                            id=f"cartop:{local(olabel)}.{local(of)}", native=f"{olabel}._ont_{of}", label=of,
                            kind="datatype", domain=[f"carto:{local(olabel)}"], domain_kind="class_member",
                            source=fm["__file__"], line=fm["__line__"]))
                        sh = fm.get("special_handling")
                        note = ""
                        if sh:
                            extra = fm.get("extra") or {}
                            note = f"special_handling={sh}"
                            if isinstance(extra, dict) and extra:
                                keys = sorted(k for k in extra if isinstance(k, str))
                                note += f" extra[{','.join(keys)}]"
                        if fm.get("required"):
                            note = (note + "; " if note else "") + "required=True"
                        if not nf or (sh == "static_value"):
                            continue
                        pp = prov_fields.setdefault((nl, nf), Prop(
                            id=f"cartonodep:{local(nl)}.{local(nf)}", native=f"{nl}.{nf}", label=nf,
                            kind="datatype", domain=[pc.id], domain_kind="class_member", provider=prov,
                            source=fm["__file__"], line=fm["__line__"]))
                        ex.links.append(Link(subject=pp.id, object=np_.id,
                                             native_relation="cartography:OntologyFieldMapping",
                                             link_kind="provider_field_to_model_property", level="property",
                                             provider=prov, source=fm["__file__"], line=fm["__line__"],
                                             sentence=f"OntologyFieldMapping(ontology_field={of!r}, "
                                                      f"node_field={nf!r}) no nó {nl}",
                                             subject_label=f"{nl}.{nf}", object_label=f"{olabel}.{of}", note=note))
    ex.classes += [prov_cls[k] for k in sorted(prov_cls)]
    ex.props = [neutral_fields[k] for k in sorted(neutral_fields)] + [prov_fields[k] for k in sorted(prov_fields)]
    ex.files = [(m.label, root / m.label[len(label_prefix):]) for m in ctx.mods.values()]
    for p in sorted((root / "cartography/models/ontology/mapping/data").glob("*.py")):
        rel = str(p.relative_to(root))
        if (label_prefix + rel) not in {lb for lb, _ in ex.files}:
            ex.files.append((label_prefix + rel, p))
    ex.files.sort()
    ex.prefixes = {"carto": "https://github.com/cartography-cncf/cartography#ontology/",
                   "cartop": "https://github.com/cartography-cncf/cartography#ontology-field/",
                   "cartonode": "https://github.com/cartography-cncf/cartography#node/",
                   "cartonodep": "https://github.com/cartography-cncf/cartography#node-field/"}
    ex.counts = {"semantic_labels_and_canonical_nodes": len(neutral), "module_node_labels": len(prov_cls),
                 "ontology_fields": len(neutral_fields), "module_node_fields": len(prov_fields),
                 "unevaluated_entries": unevaluated}
    return ex
