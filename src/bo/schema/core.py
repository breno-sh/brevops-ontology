"""Schema JSON do Terraform -> átomos (C01) e tipos (C02). A biblioteca única de todos os produtores.

Entrada: a saída de 'terraform providers schema -json' (format_version 1.x), crua ou em .gz.

Regras (as mesmas para os 4 provedores e para qualquer versão):
  * átomo = cada entrada de 'attributes' de cada bloco, em toda a profundidade; o caminho é o dos nomes de
    bloco até ele ('rule.expiration.days'); block_path traz, por bloco, nesting_mode e min_items/max_items
    quando o schema os declara; nesting = modo do último bloco ('none' no topo).
  * blocos ('block_types') não são átomos: são contados em counts.blocks e descritos no block_path.
  * atributo com 'nested_type' (protocolo 6) é UM átomo; tf_type é o tipo cty equivalente
    (single -> ["object", {...}(, [opcionais])], list/set/map -> [modo, objeto]); os filhos não viram átomos,
    para que counts.attributes seja o número de entradas 'attributes' do schema (a régua do catálogo).
  * flags required/optional/computed/sensitive/deprecated são os do schema, sem reinterpretação;
    configurable = required ou optional. write_only (C01 2.1.0) só é gravado quando o schema o marca: o átomo
    sem ele sai com os mesmos bytes de antes da emenda. A régua do C1 (cfg/provider_populated/computed_only) mora em
    bo.schema.ruler, separada: ela é uma decisão de análise, não um fato do schema.
  * block_sha256 = sha256 do JSON canônico do bloco (chaves ordenadas, separadores ',' ':', UTF-8).
  * max_depth = profundidade máxima de bloco aninhado (bloco de topo = 1; tipo sem blocos = 0).
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

#: endereço do registro -> nome curto do provedor (C00). Outros: o último segmento do endereço.
PROVIDER_SHORT = {
    "registry.terraform.io/hashicorp/aws": "aws",
    "registry.terraform.io/hashicorp/google": "google",
    "registry.terraform.io/hashicorp/azurerm": "azurerm",
    "registry.terraform.io/oracle/oci": "oci",
}

FLAGS = ("required", "optional", "computed", "sensitive", "deprecated")


class SchemaError(ValueError):
    """Schema que viola uma regra do C01/C02 (ex.: required e computed juntos) ou fora do formato."""


def short_name(address: str) -> str:
    return PROVIDER_SHORT.get(address, address.rsplit("/", 1)[-1])


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(obj) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def load(path: Path | str) -> dict:
    """O documento do 'providers schema -json' (aceita .json e .json.gz)."""
    p = Path(path)
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rb") as f:
        doc = json.loads(f.read())
    fv = str(doc.get("format_version", ""))
    if not fv.startswith("1."):
        raise SchemaError(f"{p}: format_version {fv!r} não suportado (esperado 1.x)")
    if not isinstance(doc.get("provider_schemas"), dict):
        raise SchemaError(f"{p}: sem provider_schemas")
    return doc


def providers(doc: dict) -> dict[str, dict]:
    """{nome curto: provider_schema}. Dois endereços com o mesmo nome curto reprovam."""
    out = {}
    for addr, ps in sorted(doc["provider_schemas"].items()):
        s = short_name(addr)
        if s in out:
            raise SchemaError(f"dois endereços para o provedor {s}")
        out[s] = ps
    return out


def nested_type_to_cty(nt: dict):
    """Tipo cty equivalente a um atributo 'nested_type' (protocolo 6)."""
    attrs, optional = {}, []
    for name, a in sorted((nt.get("attributes") or {}).items()):
        attrs[name] = attr_cty(a)
        if a.get("optional"):
            optional.append(name)
    # codificação JSON do cty: atributos opcionais do objeto vão num terceiro elemento
    obj = ["object", attrs, optional] if optional else ["object", attrs]
    mode = nt.get("nesting_mode", "single")
    if mode == "single":
        return obj
    if mode in ("list", "set", "map"):
        return [mode, obj]
    raise SchemaError(f"nested_type com nesting_mode {mode!r} desconhecido")


def attr_cty(a: dict):
    if "type" in a:
        return a["type"]
    if "nested_type" in a:
        return nested_type_to_cty(a["nested_type"])
    raise SchemaError("atributo sem 'type' nem 'nested_type'")


@dataclass(frozen=True)
class BlockRef:
    """Um bloco aninhado: caminho (nomes, ele incluído) e o modo de aninhamento dele."""
    path: tuple
    nesting_mode: str

    @property
    def depth(self) -> int:
        return len(self.path)


@dataclass
class TypeSchema:
    provider: str
    provider_version: str
    resource_type: str
    block: dict
    atoms: list = field(default_factory=list)       # dicts C01: uma entrada 'attributes' do schema cada
    blocks: list = field(default_factory=list)      # BlockRef, em pré-ordem (nomes ordenados)
    elements: dict = field(default_factory=dict)    # atom_id do pai -> átomos de elemento de coleção (C01 2.2.0)

    @property
    def type_id(self) -> str:
        return f"{self.provider}:{self.resource_type}"

    def all_atoms(self) -> list:
        """Átomos do schema e, logo depois de cada coleção de objetos, os átomos de elemento dela (C01 2.2.0).
        As contagens (C02, régua do C1) continuam sobre .atoms; .elements só acrescenta linhas ao atoms.jsonl."""
        out = []
        for a in self.atoms:
            out.append(a)
            out += self.elements.get(a["atom_id"], [])
        return out


def _block_entry(name: str, bt: dict) -> dict:
    mode = bt.get("nesting_mode")
    if mode not in ("single", "list", "set", "map", "group"):
        raise SchemaError(f"bloco {name}: nesting_mode {mode!r} desconhecido")
    e = {"block": name, "nesting_mode": mode}
    for k in ("min_items", "max_items"):
        if k in bt:
            e[k] = int(bt[k])
    return e


def _walk(block: dict, path: tuple, bpath: tuple) -> Iterator[tuple]:
    """('attr', path, block_path, attr) e ('block', path, block_path, None), em pré-ordem com nomes ordenados."""
    for name, a in sorted((block.get("attributes") or {}).items()):
        yield "attr", path + (name,), bpath, a
    for name, bt in sorted((block.get("block_types") or {}).items()):
        e = _block_entry(name, bt)
        np, nb = path + (name,), bpath + (e,)
        yield "block", np, nb, None
        yield from _walk(bt.get("block") or {}, np, nb)


def make_atom(provider: str, version: str, rtype: str, path: tuple, bpath: tuple, a: dict) -> dict:
    fl = {k: bool(a.get(k)) for k in FLAGS}
    where = f"{provider}:{rtype}:{'.'.join(path)}"
    if fl["required"] and fl["optional"]:
        raise SchemaError(f"{where}: required e optional ao mesmo tempo")
    if fl["required"] and fl["computed"]:
        raise SchemaError(f"{where}: required e computed ao mesmo tempo")
    wo = bool(a.get("write_only"))
    if wo and (fl["computed"] or not (fl["required"] or fl["optional"])):
        raise SchemaError(f"{where}: write_only exige configurable e não computed (C01-WRITEONLY)")
    p = ".".join(path)
    atom = {
        "atom_id": f"{provider}:{rtype}:{p}",
        "provider": provider,
        "provider_version": version,
        "resource_type": rtype,
        "path": p,
        "block_path": [dict(e) for e in bpath],
        "tf_type": attr_cty(a),
        "nesting": bpath[-1]["nesting_mode"] if bpath else "none",
        **fl,
        "configurable": fl["required"] or fl["optional"],
    }
    if wo:      # campo opcional do C01 2.1.0: só aparece quando verdadeiro (átomo sem ele = bytes de antes)
        atom["write_only"] = True
    return atom


# ------------------------------------------------------------------------------- elementos de coleção (C01 2.2.0)
def collection_of_objects(a: dict) -> tuple[str, dict, bool] | None:
    """(modo list|set, {membro: definição}, membros têm flags próprios) se o atributo é coleção de objetos.

    nested_type com nesting_mode list/set: os membros são atributos com flags próprios (protocolo 6).
    type cty ["list"|"set", ["object", {...}(, opcionais)]]: os membros só têm tipo (sem flags)."""
    nt = a.get("nested_type")
    if nt is not None:
        mode = nt.get("nesting_mode")
        return (mode, dict(nt.get("attributes") or {}), True) if mode in ("list", "set") else None
    t = a.get("type")
    if (isinstance(t, list) and len(t) == 2 and t[0] in ("list", "set") and isinstance(t[1], list)
            and len(t[1]) >= 2 and t[1][0] == "object" and isinstance(t[1][1], dict)):
        return t[0], {m: {"type": mt} for m, mt in t[1][1].items()}, False
    return None


def element_flags(parent: dict, member: dict, own_flags: bool) -> dict:
    """Flags do membro de um elemento de coleção (regra declarada da biblioteca, emenda 1.1.0):
      * nested_type: os flags do próprio membro (o schema os declara);
      * objeto cty (sem flags no schema): pai configurável -> optional (o schema não diz se o membro é
        obrigatório dentro do elemento; o stub C01 2.2.0 do CONTRACTS usa optional), não computed;
        pai só computed -> computed. sensitive, deprecated e write_only vêm do pai."""
    if own_flags:
        a = dict(member)
        for k in ("sensitive", "deprecated"):
            a[k] = bool(member.get(k)) or bool(parent.get(k))
        return a
    a = {"type": member["type"]}
    if parent.get("required") or parent.get("optional"):
        a["optional"] = True
        if parent.get("write_only"):
            a["write_only"] = True
    else:
        a["computed"] = True
    for k in ("sensitive", "deprecated"):
        if parent.get(k):
            a[k] = True
    return a


def _elements(provider, version, rtype, path, bpath, a) -> list:
    """Átomos de elemento de um atributo coleção de objetos, recursivo (membro que também é coleção)."""
    c = collection_of_objects(a)
    if c is None:
        return []
    mode, members, own = c
    nb = bpath + ({"block": path[-1], "kind": "nested_attribute", "nesting_mode": mode},)
    out = []
    for name, m in sorted(members.items()):
        child = element_flags(a, m, own)
        out.append(make_atom(provider, version, rtype, path + (name,), nb, child))
        out += _elements(provider, version, rtype, path + (name,), nb, child)
    return out


def is_element(atom: dict) -> bool:
    """Átomo de elemento de coleção (C01 2.2.0): algum passo do block_path é nested_attribute."""
    return any(b.get("kind") == "nested_attribute" for b in atom["block_path"])


def type_schema(provider: str, version: str, rtype: str, block: dict) -> TypeSchema:
    ts = TypeSchema(provider, version, rtype, block)
    for kind, path, bpath, a in _walk(block, (), ()):
        if kind == "attr":
            atom = make_atom(provider, version, rtype, path, bpath, a)
            ts.atoms.append(atom)
            el = _elements(provider, version, rtype, path, bpath, a)
            if el:
                ts.elements[atom["atom_id"]] = el
        else:
            ts.blocks.append(BlockRef(path, bpath[-1]["nesting_mode"]))
    return ts


def type_record(ts: TypeSchema) -> dict:
    """A linha C02 do tipo: contagens sobre os átomos e os blocos, profundidade e sha256 do bloco."""
    at = ts.atoms
    req = sum(a["required"] for a in at)
    opt = sum(a["optional"] for a in at)
    return {
        "type_id": ts.type_id,
        "provider": ts.provider,
        "provider_version": ts.provider_version,
        "resource_type": ts.resource_type,
        "counts": {
            "attributes": len(at),
            "blocks": len(ts.blocks),
            "required": req,
            "optional": opt,
            "computed": sum(a["computed"] for a in at),
            "configurable": sum(a["configurable"] for a in at),
            "sensitive": sum(a["sensitive"] for a in at),
            "deprecated": sum(a["deprecated"] for a in at),
        },
        "max_depth": max((b.depth for b in ts.blocks), default=0),
        "block_sha256": canonical_sha256(ts.block),
    }


def iter_types(provider_schema: dict, provider: str, version: str) -> Iterator[TypeSchema]:
    """Um TypeSchema por tipo de recurso (resource_schemas), em ordem de nome."""
    for rtype, s in sorted((provider_schema.get("resource_schemas") or {}).items()):
        yield type_schema(provider, version, rtype, s.get("block") or {})


def write_jsonl(path: Path, records) -> int:
    n = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n
