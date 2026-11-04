"""Leitura tolerante das entradas (somente leitura).

type_subcategory.jsonl: os 4 DOCS-* gravaram formatos diferentes (o CONTRACTS fixa um só no C03 3.1.0, e os
DOCS-* estão migrando). Aqui cada registro é lido pelas CHAVES, não pelo provedor: o bloco de importação é
"import" ou "import_id"; a frase é source (ou o 1º statement), a frase-chave é key_sentence (ou statement), a lista
literal de IDs/formatos é value; id_attributes, separators, methods, identity, supported, id_format,
id_is_plain_id e placeholders são copiados quando existem. A subcategoria vem como bloco {value, source} ou como
texto com source no topo. A assinatura de cada variante lida (bloco + chaves) é contada e vai para
results/SERVICE-EVIDENCE/evidence_levels.json (inputs.type_subcategory). Sem bloco de importação (formato antigo
do DOCS-GCP), o extract relê a seção Import da página fixada (regra R-IMPORT-DOC).
Nada é inventado: campo ausente fica ausente; import sem status vira desconhecido.

docs_facts.jsonl: lido em fluxo, guardando só os fatos dos átomos que alguma regra usa.
shared_block_map.jsonl (DOCS-AWS): átomos de bloco repetido cujos fatos estão no átomo canônico; se o
docs_facts não tiver o átomo repetido, os fatos do canônico (mesma frase, mesma linha) valem para ele.
"""

from __future__ import annotations

import collections
import json
from functools import lru_cache

from . import common, rules

DM = {"aws": "AWS", "google": "GCP", "azurerm": "AZURE", "oci": "OCI"}


def docs_dir(provider: str):
    return common.bo_data() / f"DOCS-{DM[provider]}"


def schema_dir(provider: str):
    return common.bo_data() / f"SCHEMA-{DM[provider]}"


def input_paths(provider: str) -> list:
    d, s = docs_dir(provider), schema_dir(provider)
    out = [d / "docs_facts.jsonl", d / "type_subcategory.jsonl", s / "atoms.jsonl", s / "types.jsonl"]
    if (d / "shared_block_map.jsonl").exists():
        out.append(d / "shared_block_map.jsonl")
    return out


@lru_cache(maxsize=4)
def types(provider: str) -> tuple[str, ...]:
    out = []
    with open(schema_dir(provider) / "types.jsonl", encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line)["resource_type"])
    return tuple(sorted(out))


@lru_cache(maxsize=4)
def atoms(provider: str) -> dict:
    """resource_type -> lista de (path, block_path_len, required, optional, computed, configurable)."""
    out = collections.defaultdict(list)
    with open(schema_dir(provider) / "atoms.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["resource_type"]].append((r["path"], len(r.get("block_path") or []), bool(r.get("required")),
                                            bool(r.get("optional")), bool(r.get("computed")),
                                            bool(r.get("configurable"))))
    return dict(out)


# ---------------------------------------------------------------- type_subcategory (4 variantes)

def _import_block(r: dict) -> tuple[str | None, dict | None]:
    for k in ("import", "import_id"):
        if isinstance(r.get(k), dict):
            return k, r[k]
    return None, None


def _variant(r: dict) -> str:
    """Assinatura da variante = nome do bloco de importação + chaves presentes (ou como vem a subcategoria)."""
    k, imp = _import_block(r)
    sub = "subcategory:" + ("text" if isinstance(r.get("subcategory"), str) else "block")
    if imp is None:
        return f"{sub};sem_import"
    keys = sorted(x for x in imp if x not in ("evidence_level", "extraction_method"))
    return f"{sub};{k}{{{','.join(keys)}}}"


def _subcat(r: dict) -> dict | None:
    s = r.get("subcategory")
    if isinstance(s, dict):
        if s.get("status") == "stated" and s.get("source"):
            return {"value": s["value"], "source": s["source"]}
        return None
    if isinstance(s, str) and r.get("status") == "stated" and isinstance(r.get("source"), dict):
        return {"value": s, "source": r["source"]}
    return None


def _doc_file(r: dict) -> str | None:
    if r.get("doc_file"):
        return r["doc_file"]
    pages = [p for p in (r.get("doc_pages") or []) if "/r/" in p or p.startswith("website/docs/r/")]
    return pages[0] if pages else None


C25_REASONS = ("not_documented", "ambiguous", "contradictory", "out_of_pin")
VALUE_KEYS = ("id_attributes", "separators", "methods", "identity", "supported", "id_format", "id_is_plain_id",
              "placeholders")


def _import(provider: str, r: dict, doc_file: str | None) -> dict:
    """Normaliza qualquer variante: {'status': stated|unknown|absent, 'unknown_reason', 'cite', 'key_cite', 'value'}.
    cite = source do bloco, senão o 1º statement (arquivo = doc_file); key_cite = key_sentence ou statement;
    value.values = a lista literal de IDs/formatos (value do bloco), quando há."""
    repo, tg = common.SRC[provider]["repo"], common.tag(provider)
    _k, imp = _import_block(r)
    if imp is None:
        return {"status": "absent"}
    if imp.get("supported") is False and isinstance(imp.get("source"), dict):
        # "This resource does not support import." é fato publicado (importação não suportada), não lacuna
        return {"status": "stated", "cite": dict(imp["source"]), "value": {"supported": False}}
    if imp.get("status") != "stated":
        r = imp.get("unknown_reason", "not_documented")
        return {"status": "unknown", "unknown_reason": r if r in C25_REASONS else "not_documented",
                "upstream_reason": r}
    cite = None
    if isinstance(imp.get("source"), dict):
        cite = dict(imp["source"])
    elif imp.get("statements") and doc_file:
        st = imp["statements"][0]
        cite = {"repo": repo, "tag": tg, "file": doc_file, "line": st["line"], "sentence": st["sentence"]}
    if cite is None:
        return {"status": "unknown", "unknown_reason": "not_documented"}
    val = {k: imp[k] for k in VALUE_KEYS if k in imp}
    if isinstance(imp.get("value"), list):
        val["values"] = list(imp["value"])
    out = {"status": "stated", "cite": cite, "value": val}
    kc = imp.get("key_sentence") or imp.get("statement")
    if isinstance(kc, dict):
        out["key_cite"] = dict(kc)
    return out


@lru_cache(maxsize=4)
def typesub(provider: str) -> tuple[dict, dict]:
    """(resource_type -> registro normalizado, contagem de variantes). Só recurso (kind resource ou sem kind)."""
    out, cnt = {}, collections.Counter()
    with open(docs_dir(provider) / "type_subcategory.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind", "resource") != "resource":
                continue
            v = _variant(r)
            cnt[v] += 1
            rt = r.get("resource_type") or r["type_id"].split(":", 1)[1]
            df = _doc_file(r)
            out[rt] = {"resource_type": rt, "variant": v, "doc_file": df, "subcategory": _subcat(r),
                       "import": _import(provider, r, df)}
    return out, dict(cnt)


# ---------------------------------------------------------------- docs_facts filtrado

def _interesting(provider: str, path: str, depth_top: bool, fact: dict) -> bool:
    lf = rules.leaf(path)
    if depth_top and lf in rules.TAG_ATTRS[provider]:
        return True
    if rules.TTL_LEAF.search(lf) or rules.STATE_LEAF.match(lf) or rules.EFFECT_LEAF.match(lf) \
            or rules.EFFECT_BLOCK.match(lf) or rules.PREC_LEAF.match(lf) or lf in ("deletion_policy",):
        return True
    if lf in ("compartment_id",) or lf.endswith("_id"):
        return True
    if fact.get("fact_kind") == "description":
        s = ((fact.get("source") or {}).get("sentence") or "") + " " + str(fact.get("value") or "")
        if rules.STATE_DESC.search(s) or rules.SCOPE_RX.search(s):
            return True
    return False


EXTRA_ATOMS: set[str] = set()  # protocol.py acrescenta os átomos que a tabela de suporte cita


@lru_cache(maxsize=4)
def docs_facts(provider: str) -> tuple[dict, dict]:
    """(atom_id -> [fatos], estatística). Fatos sem fonte ficam de fora (não há o que citar)."""
    out = collections.defaultdict(list)
    st = collections.Counter()
    with open(docs_dir(provider) / "docs_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            st["lidos"] += 1
            aid = r.get("atom_id") or ""
            parts = aid.split(":", 2)
            if len(parts) != 3:
                st["sem_atom_id"] += 1
                continue
            path = parts[2]
            if not (aid in EXTRA_ATOMS or _interesting(provider, path, "." not in path, r)):
                continue
            if r.get("status") != "stated" or not r.get("source"):
                st["guardado_sem_fonte"] += 1
                continue
            st["guardados"] += 1
            out[aid].append({k: r[k] for k in ("fact_id", "fact_kind", "value", "source", "as_of",
                                                "evidence_level") if k in r})
    return dict(out), dict(st)


@lru_cache(maxsize=4)
def shared_blocks(provider: str) -> tuple[dict, dict]:
    """(átomo repetido -> átomo canônico, estatística). Só DOCS-AWS publica o mapa."""
    p = docs_dir(provider) / "shared_block_map.jsonl"
    out, st = {}, collections.Counter()
    if not p.exists():
        return {}, {"arquivo": "ausente"}
    with open(p, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            st["blocos"] += 1
            can = (r.get("canonical") or [None])[0]
            for rep in r.get("repeats") or []:
                if can:
                    out[rep] = can
                    st["repetidos"] += 1
    return out, dict(st)


def facts_for(provider: str, atom_id: str, used: collections.Counter | None = None) -> tuple[list, str | None]:
    """Fatos do átomo; se não houver e ele for bloco repetido, os do canônico (devolve o canônico)."""
    df, _ = docs_facts(provider)
    if atom_id in df:
        return df[atom_id], None
    can = shared_blocks(provider)[0].get(atom_id)
    if can and can in df:
        if used is not None:
            used["via_shared_block_map"] += 1
        return df[can], can
    return [], None
