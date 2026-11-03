"""Leitura (sem executar nada) de composições e XRDs Crossplane: patches com linha, transformações e condição.

Cobre o modo Resources (spec.resources/spec.patchSets) e o passo de patch-and-transform do modo Pipeline
(function-patch-and-transform e a variante condicional: input.kind == Resources). Passos de outras funções
(KCL, go-templating, auto-ready...) são contados como não lidos, nunca interpretados.
"""
from __future__ import annotations

import re

import yaml

PT_FUNCTION = re.compile(r"patch-and-transform")
XR_SIDE = {"FromCompositeFieldPath": "to_mr", "CombineFromComposite": "to_mr",
           "ToCompositeFieldPath": "to_xr", "CombineToComposite": "to_xr"}
ENV_TYPES = {"FromEnvironmentFieldPath", "ToEnvironmentFieldPath", "CombineFromEnvironment",
             "CombineToEnvironment"}


class _LineLoader(yaml.SafeLoader):
    """SafeLoader que anota cada mapa com a linha (1-based) em que começa: chave '__line__'."""


def _construct_mapping(loader, node, deep=False):
    m = yaml.SafeLoader.construct_mapping(loader, node, deep=True)
    m["__line__"] = node.start_mark.line + 1
    return m


_LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_docs(text: str) -> list:
    return [d for d in yaml.load_all(text, Loader=_LineLoader) if isinstance(d, dict)]


def strip_lines(x):
    if isinstance(x, dict):
        return {k: strip_lines(v) for k, v in x.items() if k != "__line__"}
    if isinstance(x, list):
        return [strip_lines(v) for v in x]
    return x


def split_api_version(av: str) -> tuple[str, str]:
    if "/" in (av or ""):
        g, v = av.rsplit("/", 1)
        return g, v
    return "", av or ""


# ----------------------------------------------------------------------------------------------- XRD
def parse_xrd(doc: dict) -> dict | None:
    if doc.get("kind") != "CompositeResourceDefinition":
        return None
    spec = doc.get("spec") or {}
    group = spec.get("group")
    kind = (spec.get("names") or {}).get("kind")
    versions = {}
    for v in spec.get("versions") or []:
        sch = ((v.get("schema") or {}).get("openAPIV3Schema")) or {}
        versions[v.get("name")] = strip_lines(sch)
    return {"group": group, "kind": kind, "versions": versions,
            "claim_kind": (spec.get("claimNames") or {}).get("kind")}


# ----------------------------------------------------------------------------------------- composição
def _patch_sets(container: dict) -> dict:
    out = {}
    for ps in container.get("patchSets") or []:
        out[ps.get("name")] = ps.get("patches") or []
    return out


def _expand(patches: list, sets: dict, trail=()):
    """Expande PatchSet (recursivo), devolvendo (patch, nome_do_patchset | None)."""
    for p in patches or []:
        if (p.get("type") or "") == "PatchSet":
            name = p.get("patchSetName")
            if name in trail or name not in sets:
                yield {"__unresolved_patchset__": name, "__line__": p.get("__line__")}, name
                continue
            for q, _ in _expand(sets[name], sets, trail + (name,)):
                yield q, name
        else:
            yield p, (trail[-1] if trail else None)


def _patch_record(p: dict, ps_name):
    if "__unresolved_patchset__" in p:
        return {"type": "PatchSet", "status": "patchset_ausente", "patch_set": p["__unresolved_patchset__"],
                "line": p.get("__line__")}
    ptype = p.get("type") or "FromCompositeFieldPath"
    rec = {"type": ptype, "line": p.get("__line__"), "patch_set": ps_name,
           "transforms": strip_lines(p.get("transforms") or []),
           "policy": strip_lines(p.get("policy")) if p.get("policy") is not None else None}
    if ptype in ("FromCompositeFieldPath", "ToCompositeFieldPath", "FromEnvironmentFieldPath",
                 "ToEnvironmentFieldPath"):
        frm = p.get("fromFieldPath")
        rec["from_field_path"] = frm
        rec["to_field_path"] = p.get("toFieldPath") or frm   # sem toFieldPath = mesmo caminho (doc. Crossplane)
    elif ptype in ("CombineFromComposite", "CombineToComposite", "CombineFromEnvironment",
                   "CombineToEnvironment"):
        comb = strip_lines(p.get("combine") or {})
        rec["combine"] = comb
        rec["from_field_paths"] = [v.get("fromFieldPath") for v in comb.get("variables") or []]
        rec["to_field_path"] = p.get("toFieldPath")
    rec["status"] = "ok" if ptype in XR_SIDE else ("ambiente" if ptype in ENV_TYPES else "tipo_desconhecido")
    return rec


def _resources_block(container: dict, mode: str, step: str | None):
    sets = _patch_sets(container)
    for ri, r in enumerate(container.get("resources") or []):
        base = r.get("base") or {}
        group, version = split_api_version(base.get("apiVersion"))
        res = {"resource_index": ri, "resource_name": r.get("name") or f"#{ri}", "mode": mode, "step": step,
               "condition": r.get("condition"), "line": r.get("__line__"),
               "mr": {"group": group, "version": version, "kind": base.get("kind")}, "patches": []}
        for pi, (p, ps) in enumerate(_expand(r.get("patches") or [], sets)):
            rec = _patch_record(p, ps)
            rec["patch_index"] = pi
            res["patches"].append(rec)
        yield res


def parse_composition(doc: dict) -> dict | None:
    if doc.get("kind") != "Composition":
        return None
    spec = doc.get("spec") or {}
    md = doc.get("metadata") or {}
    xr_group, xr_version = split_api_version((spec.get("compositeTypeRef") or {}).get("apiVersion"))
    comp = {"name": md.get("name"), "labels": strip_lines(md.get("labels") or {}), "line": doc.get("__line__"),
            "xr": {"group": xr_group, "version": xr_version, "kind": (spec.get("compositeTypeRef") or {}).get("kind")},
            "mode": spec.get("mode") or "Resources", "resources": [], "unread_steps": []}
    if comp["mode"] == "Pipeline":
        for st in spec.get("pipeline") or []:
            fn = (st.get("functionRef") or {}).get("name") or ""
            inp = st.get("input") or {}
            if PT_FUNCTION.search(fn) and inp.get("kind") == "Resources":
                comp["resources"].extend(_resources_block(inp, "Pipeline", st.get("step")))
            else:
                comp["unread_steps"].append({"step": st.get("step"), "function": fn, "line": st.get("__line__")})
    else:
        comp["resources"].extend(_resources_block(spec, "Resources", None))
    return comp


def parse_file(text: str) -> dict:
    out = {"compositions": [], "xrds": [], "other_kinds": []}
    for d in load_docs(text):
        c = parse_composition(d)
        if c is not None:
            out["compositions"].append(c)
            continue
        x = parse_xrd(d)
        if x is not None:
            out["xrds"].append(x)
            continue
        out["other_kinds"].append(d.get("kind"))
    return out


# --------------------------------------------------------------------------------------------- caminhos
_SEG = re.compile(r"([^.\[\]]+)|\[([^\]]*)\]")


def split_path(path: str) -> list[tuple[str, str]]:
    """'spec.forProvider.tags[Name]' -> [('f','spec'),('f','forProvider'),('f','tags'),('k','Name')];
    '[0]' -> ('i','0'). Segmento entre colchetes não numérico é chave de mapa."""
    if not isinstance(path, str) or not path:
        raise ValueError(f"caminho vazio ou inválido: {path!r}")
    out = []
    pos = 0
    for m in _SEG.finditer(path):
        if m.start() != pos and path[pos:m.start()] != ".":
            raise ValueError(f"caminho mal formado: {path!r}")
        if m.group(1) is not None:
            out.append(("f", m.group(1)))
        else:
            key = m.group(2)
            out.append(("i", key) if key.isdigit() else ("k", key.strip("'\"")))
        pos = m.end()
    if pos != len(path):
        raise ValueError(f"caminho mal formado: {path!r}")
    return out


def join_path(segs) -> str:
    s = ""
    for kind, v in segs:
        if kind == "f":
            s += ("." if s else "") + v
        else:
            s += f"[{v}]"
    return s
