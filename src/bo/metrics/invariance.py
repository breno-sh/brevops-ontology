"""Testes de invariância (PREREG §5): determinísticos, não estatísticos.

Renomear provedores, permutar a identidade dos provedores, trocar a embalagem (documento JSON inline x blocos
statement separados) e reordenar registros tem de dar a mesma saída, byte a byte, depois de desfazer a
renomeação. Qualquer diferença é defeito.

`canonical_bytes` serializa com chaves ordenadas; números em ponto flutuante com 12 algarismos significativos
(só o ajuste da logística muda a coluna de referência dos efeitos fixos com o nome do nível; as proporções e o
bootstrap são exatos e não dependem disso).
"""
from __future__ import annotations

import itertools
import json
import random
from dataclasses import replace

from .spec import PROVIDERS
from .units import Unit


class InvarianceError(AssertionError):
    pass


class NotExplodable(ValueError):
    """Documento sem forma equivalente em blocos statement (ex.: chave calculada)."""


def _round(x):
    if isinstance(x, float):
        return float(f"{x:.12g}")
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


def canonical_bytes(obj) -> bytes:
    return json.dumps(_round(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def rename_units(units, mapping: dict) -> list[Unit]:
    out = []
    for u in units:
        out.append(replace(u, source=mapping.get(u.source, u.source),
                           target=mapping.get(u.target, u.target) if u.target is not None else None))
    return out


def _relabel_str(s: str, mapping: dict) -> str:
    for sep in ("->", "<->"):
        if sep in s:
            parts = s.split(sep)
            if all(p in mapping for p in parts):
                return sep.join(mapping[p] for p in parts)
    return mapping.get(s, s)


def relabel(obj, mapping: dict):
    """Aplica o mapeamento de nomes de provedor a chaves e valores de texto (células 'a->b', 'a', 'a<->b')."""
    if isinstance(obj, dict):
        return {_relabel_str(k, mapping) if isinstance(k, str) else k: relabel(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [relabel(v, mapping) for v in obj]
    if isinstance(obj, str):
        return _relabel_str(obj, mapping)
    return obj


def opaque_names(providers=PROVIDERS) -> dict:
    return {p: f"prov{i}" for i, p in enumerate(sorted(providers), start=1)}


def check_rename(fn, units, mapping: dict | None = None) -> bytes:
    """fn(units) -> objeto serializável. Compara fn(units) com relabel(fn(renomeadas), inverso)."""
    mapping = mapping or opaque_names()
    inv = {v: k for k, v in mapping.items()}
    if len(inv) != len(mapping):
        raise InvarianceError("mapeamento não é bijetor")
    a = canonical_bytes(fn(list(units)))
    b = canonical_bytes(relabel(fn(rename_units(units, mapping)), inv))
    if a != b:
        raise InvarianceError(f"renomeação muda a saída ({_first_diff(a, b)})")
    return a


def check_permutations(fn, units, providers=PROVIDERS, limit: int | None = None) -> int:
    """Toda permutação da identidade dos provedores (24 com 4), ou as `limit` primeiras em ordem lexicográfica."""
    n = 0
    for perm in itertools.permutations(sorted(providers)):
        mapping = dict(zip(sorted(providers), perm))
        if mapping == {p: p for p in providers}:
            continue
        check_rename(fn, units, mapping)
        n += 1
        if limit and n >= limit:
            break
    return n


def check_reorder(fn, units, seed: int = 0, rounds: int = 3) -> bytes:
    a = canonical_bytes(fn(list(units)))
    rng = random.Random(seed)
    for _ in range(rounds):
        xs = list(units)
        rng.shuffle(xs)
        b = canonical_bytes(fn(xs))
        if a != b:
            raise InvarianceError(f"reordenar registros muda a saída ({_first_diff(a, b)})")
    return a


def _first_diff(a: bytes, b: bytes) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"byte {i}: …{a[max(0, i - 30):i + 30]!r} x …{b[max(0, i - 30):i + 30]!r}"
    return f"tamanhos {len(a)} x {len(b)}"


# ------------------------------------------------------------------------------------------------- embalagem
def _lit(v):
    return {"datatype": "list" if isinstance(v, list) else "string", "kind": "literal", "value": v}


def _vals(v):
    if isinstance(v, dict) and "$term" in v:
        return v["$term"]
    if isinstance(v, list) and any(isinstance(x, dict) for x in v):
        args = [x.get("$term", x) if isinstance(x, dict) else {"datatype": "string", "kind": "literal", "value": x}
                for x in v]
        return {"args": args, "kind": "expression", "op": "hcl_tuple"}
    return _lit(v if isinstance(v, list) else [v])


def policy_to_block_records(rec: dict) -> list[dict]:
    """Registro C06 com documento policy_json (Statement) -> os mesmos fatos como campos de blocos statement
    de aws_iam_policy_document (um registro por atributo de bloco). Mesmo repositório, arquivo e endereço:
    os ids de decisão coincidem e a contagem de campos cresce."""
    tree = rec["term"]["tree"]
    sts = tree["Statement"] if isinstance(tree["Statement"], list) else [tree["Statement"]]
    base = {k: rec[k] for k in ("family_id", "file", "provider", "repo_id", "resource_address")}
    base["resource_type"] = "aws_iam_policy_document"
    out = []

    def add(path, term):
        out.append({**base, "attr_path": path, "term": term})

    from .units import STATEMENT_KEYS
    for i, st in enumerate(sts):
        p = f"statement[{i}]"
        extra = set(st) - STATEMENT_KEYS
        if extra:
            raise NotExplodable(f"chave fora da gramática ({len(extra)}): sem forma de bloco")
        if "Effect" in st:
            e = st["Effect"]
            add(f"{p}.effect", e["$term"] if isinstance(e, dict) and "$term" in e else
                {"datatype": "string", "kind": "literal", "value": e})
        for j, h in (("Action", "actions"), ("NotAction", "not_actions"), ("Resource", "resources"),
                     ("NotResource", "not_resources")):
            if j in st:
                add(f"{p}.{h}", _vals(st[j]))
        for j, h in (("Principal", "principals"), ("NotPrincipal", "not_principals")):
            if j not in st:
                continue
            pr = st[j]
            items = [("*", pr)] if not isinstance(pr, dict) or "$term" in pr else sorted(pr.items())
            for k, (typ, ids) in enumerate(items):
                add(f"{p}.{h}[{k}].type", {"datatype": "string", "kind": "literal", "value": typ})
                add(f"{p}.{h}[{k}].identifiers", _vals(ids))
        k = 0
        for test, kv in sorted((st.get("Condition") or {}).items()):
            for var, vals in sorted(kv.items()):
                add(f"{p}.condition[{k}].test", {"datatype": "string", "kind": "literal", "value": test})
                add(f"{p}.condition[{k}].variable", {"datatype": "string", "kind": "literal", "value": var})
                add(f"{p}.condition[{k}].values", _vals(vals))
                k += 1
    return out


def policy_variants(tree: dict, seed: int = 0) -> dict[str, dict]:
    """Variantes que não mudam o significado: reserializar, reordenar chaves, partir listas de Action e
    Resource em declarações de um elemento, declaração única como objeto, escalar x lista de um."""
    rng = random.Random(seed)
    sts = tree["Statement"] if isinstance(tree["Statement"], list) else [tree["Statement"]]

    def shuffled(d):
        if isinstance(d, dict):
            ks = list(d)
            rng.shuffle(ks)
            return {k: shuffled(d[k]) for k in ks}
        if isinstance(d, list):
            return [shuffled(x) for x in d]
        return d

    split = []
    for st in sts:
        acts = st.get("Action")
        res = st.get("Resource")
        al = acts if isinstance(acts, list) else [acts] if acts is not None else [None]
        rl = res if isinstance(res, list) else [res] if res is not None else [None]
        for a in al:
            for r in rl:
                s2 = {k: v for k, v in st.items() if k not in ("Action", "Resource", "Sid")}
                if a is not None:
                    s2["Action"] = a
                if r is not None:
                    s2["Resource"] = [r]
                split.append(s2)
    out = {"reserialized": json.loads(json.dumps(tree, indent=3)),
           "keys_reordered": shuffled(tree),
           "lists_split": {"Version": tree.get("Version", "2012-10-17"), "Statement": split},
           "statements_reversed": {**tree, "Statement": list(reversed(sts))}}
    if len(sts) == 1:
        out["single_statement_object"] = {**tree, "Statement": sts[0]}
    return out
