"""Extrator do CloudQuery: páginas docs/tables/<tabela>.md geradas pelos plugins AWS, GCP, Azure e Oracle.

Classe = tabela (de provedor; o CloudQuery não tem camada neutra; sem pais: a relação "This table depends on [x]"
é de tabela filha para tabela mãe, não de subclasse). Propriedade = linha da tabela de colunas (nome, tipo Arrow);
a coluna _cq_parent_id de uma tabela filha ganha como imagem a tabela mãe declarada na página. Vínculo publicado:
tabela -> URL de documentação da operação da API que a página cita (construção cloudquery:api_doc). Nada além do
título, da primeira frase, das relações e das colunas é lido (exemplos de consulta ficam de fora).
"""

from __future__ import annotations

import re
from pathlib import Path

from .common import Cls, Extract, Link, Prop, clean, local

RX_TITLE = re.compile(r"^# Table: ([a-z0-9_]+)\s*$", re.M)
RX_DEP = re.compile(r"^This table depends on \[([a-z0-9_]+)\]", re.M)
RX_URL = re.compile(r"^(https?://\S+)\s*$", re.M)
RX_COL = re.compile(r"^\|([^|\n]+)\|`([^`\n]+)`\|\s*$", re.M)


def extract(model: str, files: list[tuple[str, Path, str]]) -> Extract:
    ex = Extract(model=model, files=[(lb, p) for lb, p, _ in files])
    no_url = n_child = 0
    for lb, p, prov in files:
        text = p.read_text(encoding="utf-8")
        mt = RX_TITLE.search(text)
        if not mt:
            ex.notes.append(f"{lb}: sem título '# Table:'")
            continue
        table = mt.group(1)
        head_end = text.find("\n## ", mt.end())
        head = text[mt.end(): head_end if head_end > 0 else len(text)]
        desc = next((ln.strip() for ln in head.splitlines() if ln.strip() and not ln.startswith(("http", "The "))),
                    "")
        tid = f"cq:{local(table)}"
        mothers = sorted({f"cq:{local(d)}" for d in RX_DEP.findall(text)})
        if mothers:
            n_child += 1
        ex.classes.append(Cls(id=tid, native=table, label=table, definition=clean(desc), provider=prov, source=lb,
                              line=text.count("\n", 0, mt.start()) + 1))
        mu = RX_URL.search(head)
        if mu:
            ex.links.append(Link(subject=tid, object=mu.group(1), native_relation="cloudquery:api_doc",
                                 link_kind="model_term_to_provider_api", level="class", provider=prov, source=lb,
                                 line=text.count("\n", 0, mt.end() + mu.start()) + 1,
                                 sentence=f"página da tabela {table} cita {mu.group(1)}", subject_label=table,
                                 object_label=mu.group(1)))
        else:
            no_url += 1
        cstart = text.find("## Columns")
        if cstart < 0:
            continue
        for mc in RX_COL.finditer(text, cstart):
            name = mc.group(1).strip()
            pk = name.endswith("(PK)")
            name = name.replace("(PK)", "").strip()
            if name.startswith("Name") or set(name) <= {"-", " "}:
                continue
            parent_ref = name == "_cq_parent_id" and mothers
            ex.props.append(Prop(id=f"cqcol:{local(table)}.{local(name)}", native=f"{table}.{name}", label=name,
                                 kind="object" if parent_ref else "datatype", domain=[tid], domain_kind="class_member",
                                 range="|".join(mothers) if parent_ref else f"arrow:{local(mc.group(2))}",
                                 definition=("chave primária" if pk else "")
                                 + ("referência à tabela mãe declarada na página" if parent_ref else ""),
                                 provider=prov, source=lb, line=text.count("\n", 0, mc.start()) + 1))
    ex.prefixes = {"cq": "https://hub.cloudquery.io/#table/", "cqcol": "https://hub.cloudquery.io/#column/",
                   "arrow": "https://arrow.apache.org/docs/format/Columnar.html#"}
    ex.counts = {"tables": len(ex.classes), "columns": len(ex.props), "tables_without_api_doc_url": no_url,
                 "child_tables_with_declared_mother": n_child}
    for prov in ("aws", "google", "azurerm", "oci"):
        ex.counts[f"tables_{prov}"] = sum(1 for c in ex.classes if c.provider == prov)
    return ex
