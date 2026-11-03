"""Extrator do Steampipe: tabelas e colunas dos plugins AWS, GCP, Azure e OCI, por expressão regular sobre o Go
(nunca compilado). Cada table_*.go declara `&plugin.Table{Name, Description, List/Get, Columns}`.

Classe = tabela (todas de provedor: o Steampipe não tem camada neutra). Propriedade = coluna declarada no arquivo
(as colunas comuns injetadas por awsRegionalColumns/commonColumns etc. vêm de outro arquivo e não são listadas;
o nome do envoltório é contado). Vínculo publicado: tabela -> ação de API da etiqueta Tags do List (ou do Get,
na falta do List), construção steampipe:hydrate_tag.
"""

from __future__ import annotations

import re
from pathlib import Path

from .common import Cls, Extract, Link, Prop, clean, local

RX_TABLE = re.compile(r"&plugin\.Table\{")
RX_NAME = re.compile(r'\bName:\s*"([^"]+)"')
RX_DESC = re.compile(r'\bDescription:\s*"((?:[^"\\]|\\.)*)"')
RX_TYPE = re.compile(r"\bType:\s*proto\.ColumnType_([A-Z_]+)")
RX_COLS = re.compile(r"\bColumns:\s*([A-Za-z_][A-Za-z0-9_]*)?\(?\s*\[\]\*plugin\.Column\{")
RX_TAG = re.compile(r'Tags:\s*map\[string\]string\{([^{}]*)\}')
RX_KV = re.compile(r'"(service|action)":\s*"([^"]+)"')


def _block(text: str, start: int) -> str:
    """Trecho a partir de start até fechar a chave aberta em start (start aponta para '{')."""
    depth, i, n = 0, start, len(text)
    in_str = None
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"`":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return text[start:]


def _lineno(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _cfg_tag(text: str, tstart: int, which: str):
    m = re.compile(rf"\b{which}:\s*&plugin\.{which}Config\{{").search(text, tstart)
    if not m:
        return None
    blk = _block(text, m.end() - 1)
    t = RX_TAG.search(blk)
    if not t:
        return None
    kv = dict(RX_KV.findall(t.group(1)))
    if "service" not in kv or "action" not in kv:
        return None
    return kv["service"], kv["action"], _lineno(text, m.start() + t.start())


def extract(model: str, files: list[tuple[str, Path, str]]) -> Extract:
    ex = Extract(model=model, files=[(lb, p) for lb, p, _ in files])
    wrappers, no_tag = {}, 0
    for lb, p, prov in files:
        text = p.read_text(encoding="utf-8")
        mt = RX_TABLE.search(text)
        if not mt:
            ex.notes.append(f"{lb}: sem &plugin.Table")
            continue
        head = text[mt.end(): mt.end() + 4000]
        nm = RX_NAME.search(head)
        if not nm:
            ex.notes.append(f"{lb}: tabela sem Name literal")
            continue
        table = nm.group(1)
        dm = RX_DESC.search(head)
        tid = f"sp:{local(table)}"
        ex.classes.append(Cls(id=tid, native=table, label=table, definition=clean(dm.group(1) if dm else ""),
                              provider=prov, source=lb, line=_lineno(text, mt.end() + nm.start())))
        tag = _cfg_tag(text, mt.end(), "List") or _cfg_tag(text, mt.end(), "Get")
        if tag:
            svc, act, ln = tag
            ex.links.append(Link(subject=tid, object=f"api_{prov}:{local(svc)}.{local(act)}",
                                 native_relation="steampipe:hydrate_tag", link_kind="model_term_to_provider_api",
                                 level="class", provider=prov, source=lb, line=ln,
                                 sentence=f'Tags: {{"service": "{svc}", "action": "{act}"}}',
                                 subject_label=table, object_label=f"{svc} {act}"))
        else:
            no_tag += 1
        mc = RX_COLS.search(text, mt.end())
        if not mc:
            ex.notes.append(f"{lb}: Columns não literal")
            continue
        wrappers[mc.group(1) or "(nenhum)"] = wrappers.get(mc.group(1) or "(nenhum)", 0) + 1
        cols_blk_start = mc.end() - 1
        blk = _block(text, cols_blk_start)
        # cada coluna é um literal { Name: ..., ... } no primeiro nível do bloco
        depth, i, entries = 0, 0, []
        while i < len(blk):
            ch = blk[i]
            if ch == "{":
                depth += 1
                if depth == 2:
                    entries.append(i)
            elif ch == "}":
                depth -= 1
            elif ch in "\"`":
                j = blk.find(ch, i + 1)
                while ch == '"' and j > 0 and blk[j - 1] == "\\":
                    j = blk.find(ch, j + 1)
                i = j if j > 0 else len(blk)
            i += 1
        seen = set()
        for e in entries:
            eb = _block(blk, e)
            cn = RX_NAME.search(eb)
            if not cn or cn.group(1) in seen:
                continue
            seen.add(cn.group(1))
            ty = RX_TYPE.search(eb)
            de = RX_DESC.search(eb)
            ex.props.append(Prop(id=f"spcol:{local(table)}.{local(cn.group(1))}", native=f"{table}.{cn.group(1)}",
                                 label=cn.group(1), kind="datatype", domain=[tid], domain_kind="class_member",
                                 range=f"spt:{ty.group(1)}" if ty else "", definition=clean(de.group(1) if de else ""),
                                 provider=prov, source=lb,
                                 line=_lineno(text, cols_blk_start + e + (cn.start() if cn else 0))))
    ex.prefixes = {"sp": "https://hub.steampipe.io/plugins/turbot/#table/",
                   "spcol": "https://hub.steampipe.io/plugins/turbot/#column/",
                   "spt": "https://github.com/turbot/steampipe-plugin-sdk/grpc/proto#ColumnType_",
                   **{f"api_{p}": f"https://w3id.org/brevops/prior/api/{p}/" for p in ("aws", "google", "azurerm",
                                                                                       "oci")}}
    ex.counts = {"tables": len(ex.classes), "columns_declared_in_table_file": len(ex.props),
                 "tables_without_api_tag": no_tag, "column_wrappers": dict(sorted(wrappers.items()))}
    for prov in ("aws", "google", "azurerm", "oci"):
        ex.counts[f"tables_{prov}"] = sum(1 for c in ex.classes if c.provider == prov)
    return ex
