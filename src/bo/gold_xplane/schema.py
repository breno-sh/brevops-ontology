"""Resolução de campos: caminho de MR no CRD do provider fixado, caminho de XR no XRD, e ponte para o atributo
Terraform (só em providers gerados do Terraform: tags tf:"..." dos tipos Go e GetTerraformResourceType).

Toda resolução devolve um dicionário com 'status' (resolved | unresolved | runtime) e o motivo; nada é inferido
por semelhança de nome."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .compose import split_path

EXTERNAL_NAME = "crossplane.io/external-name"
MR_RUNTIME_SPEC = {"writeConnectionSecretToRef", "providerConfigRef", "providerRef", "deletionPolicy",
                   "managementPolicies", "publishConnectionDetailsTo"}
XR_RUNTIME_SPEC = {"compositionRef", "compositionSelector", "compositionRevisionRef", "compositionUpdatePolicy",
                   "compositionRevisionSelector", "claimRef", "resourceRefs", "writeConnectionSecretToRef",
                   "publishConnectionDetailsTo", "environmentConfigRefs"}
_REF = re.compile(r"(Ref|Refs|Selector)$")


# --------------------------------------------------------------------------------------- schema OpenAPI
def walk_schema(schema: dict, segs) -> tuple[bool, dict | None, str]:
    """Anda no openAPIV3Schema. Devolve (achou, nó, motivo)."""
    node = schema
    for kind, v in segs:
        if node is None:
            return False, None, "nó nulo"
        if node.get("x-kubernetes-preserve-unknown-fields") and not node.get("properties"):
            return True, node, "preserve-unknown-fields (campo livre aceito pelo schema)"
        if kind == "f":
            props = node.get("properties") or {}
            if v in props:
                node = props[v]
            elif isinstance(node.get("additionalProperties"), dict):
                node = node["additionalProperties"]
            else:
                return False, None, f"campo '{v}' não existe no schema"
        elif kind == "i":
            if node.get("type") != "array":
                return False, None, f"índice [{v}] em nó que não é lista"
            node = node.get("items") or {}
        else:   # chave de mapa
            props = node.get("properties") or {}
            if v in props:
                node = props[v]
            elif isinstance(node.get("additionalProperties"), dict) or node.get("additionalProperties") is True:
                ap = node.get("additionalProperties")
                node = ap if isinstance(ap, dict) else {}
            else:
                return False, None, f"chave [{v}] em nó sem additionalProperties"
    return True, node, "ok"


def value_type(node: dict | None) -> dict | None:
    if not node:
        return None
    t = node.get("type")
    if node.get("enum"):
        return {"datatype": "enum", "enum": [str(x) for x in node["enum"]]}
    m = {"integer": "integer", "number": "decimal", "boolean": "boolean", "string": "string",
         "array": "tuple", "object": "tuple"}
    return {"datatype": m[t]} if t in m else None


# ------------------------------------------------------------------------------------------- providers
class ProviderIndex:
    """Lê $BO_DATA/downloads/crossplane/providers/<repo>@<tag>/ (index.json, CRDs, Go)."""

    def __init__(self, root: Path):
        self.root = root

    def _dir(self, repo: str, tag: str) -> Path:
        return self.root / "providers" / f"{repo.replace('/', '__')}@{tag}"

    @lru_cache(maxsize=None)
    def index(self, repo: str, tag: str) -> dict:
        return json.loads((self._dir(repo, tag) / "index.json").read_text(encoding="utf-8"))

    @lru_cache(maxsize=None)
    def crd_schema(self, repo, tag, group, version, kind):
        e = self.index(repo, tag)["kinds"].get(f"{group}/{version}/{kind}")
        if not e or not e.get("crd"):
            return None, None
        doc = next(d for d in yaml.safe_load_all((self._dir(repo, tag) / e["crd"]).read_text(encoding="utf-8"))
                   if isinstance(d, dict))
        for v in (doc.get("spec") or {}).get("versions") or []:
            if v.get("name") == version:
                return ((v.get("schema") or {}).get("openAPIV3Schema")) or {}, e["crd"]
        return None, e["crd"]

    @lru_cache(maxsize=None)
    def go(self, repo, tag, group, version, kind):
        e = self.index(repo, tag)["kinds"].get(f"{group}/{version}/{kind}") or {}
        if not e.get("go_types") or not e.get("terraformed"):
            return None
        types_txt = (self._dir(repo, tag) / e["go_types"]).read_text(encoding="utf-8")
        tf_txt = (self._dir(repo, tag) / e["terraformed"]).read_text(encoding="utf-8")
        m = re.search(rf"func \(mg \*{re.escape(kind)}\) GetTerraformResourceType\(\) string \{{\s*return \"([a-z0-9_]+)\"",
                      tf_txt)
        if not m:
            return None
        return {"tf_type": m.group(1), "structs": parse_go_structs(types_txt), "file": e["go_types"],
                "terraformed": e["terraformed"]}


_STRUCT = re.compile(r"^type (\w+) struct \{\n(.*?)^\}", re.M | re.S)
_FIELD = re.compile(r'^\s*(\w+)\s+([^\s`]+)\s+`json:"([^",]*)[^"]*"(?:\s+tf:"([^",]*)[^"]*")?')


def parse_go_structs(txt: str) -> dict:
    """{struct: {json_name: (tf_name|None, tipo_elemento)}} lido como texto (nunca compilado)."""
    out = {}
    for m in _STRUCT.finditer(txt):
        fields = {}
        for line in m.group(2).splitlines():
            f = _FIELD.match(line)
            if not f:
                continue
            _, typ, js, tf = f.groups()
            elem = re.sub(r"^(\[\]|\*|map\[string\])+", "", typ)
            fields[js] = (tf if tf not in (None, "", "-") else None, elem, typ)
        out[m.group(1)] = fields
    return out


def tf_bridge(go: dict | None, kind: str, segs) -> dict:
    """Caminho de MR (spec.forProvider/initProvider/status.atProvider...) -> atributo Terraform pelas tags."""
    if go is None:
        return {"status": "unresolved", "reason": "provider sem tipos gerados do Terraform (sem tag tf)"}
    if len(segs) < 2:
        return {"status": "unresolved", "reason": "caminho curto demais"}
    head = (segs[0][1], segs[1][1])
    root = {("spec", "forProvider"): f"{kind}Parameters", ("spec", "initProvider"): f"{kind}InitParameters",
            ("status", "atProvider"): f"{kind}Observation"}.get(head)
    if root is None:
        return {"status": "unresolved", "reason": "fora de forProvider/initProvider/atProvider"}
    cands = [s for s in go["structs"] if s == root or s.startswith(root + "_")]
    if not cands:
        return {"status": "unresolved", "reason": f"struct {root} ausente nos tipos Go"}
    struct, parts, key = cands[0], [], None
    rest = segs[2:]
    for i, (k, v) in enumerate(rest):
        if k == "i":
            continue
        if k == "k":
            key = v
            if i != len(rest) - 1:
                return {"status": "unresolved", "reason": "caminho continua depois de chave de mapa"}
            break
        fields = go["structs"].get(struct)
        if fields is None or v not in fields:
            return {"status": "unresolved", "reason": f"campo {v} ausente em {struct}"}
        tf, elem, _typ = fields[v]
        if tf is None:
            return {"status": "unresolved", "reason": f"campo {v} sem tag tf: não é atributo do recurso Terraform (referência, seletor ou argumento do provider, como region)"}
        parts.append(tf)
        struct = elem
    if not parts:
        return {"status": "unresolved", "reason": "caminho sem atributo"}
    out = {"status": "resolved", "tf_type": go["tf_type"], "tf_path": ".".join(parts), "go_file": go["file"]}
    if key is not None:
        out["map_key"] = key
    return out


def classify_mr_path(path: str) -> str:
    segs = split_path(path)
    names = [v for k, v in segs if k == "f"]
    if segs[0] == ("f", "metadata"):
        if len(segs) >= 3 and segs[1] == ("f", "annotations") and segs[2] == ("k", EXTERNAL_NAME):
            return "external_name"
        return "runtime"
    if len(names) >= 2 and names[0] == "spec" and names[1] in ("forProvider", "initProvider"):
        return "reference" if any(_REF.search(n) for n in names[2:]) else "param"
    if len(names) >= 2 and names[0] == "status" and names[1] == "atProvider":
        return "observed"
    if names and names[0] == "spec" and len(names) >= 2 and names[1] in MR_RUNTIME_SPEC:
        return "runtime"
    return "runtime" if names and names[0] in ("status", "spec") and len(names) >= 2 and names[1] in (
        "conditions", "atProvider") else "other"


def classify_xr_path(path: str) -> str:
    segs = split_path(path)
    if segs[0] == ("f", "metadata"):
        return "xr_meta"
    names = [v for k, v in segs if k == "f"]
    if len(names) >= 2 and names[0] == "spec" and names[1] in XR_RUNTIME_SPEC:
        return "xr_runtime"
    return "xr_field"
