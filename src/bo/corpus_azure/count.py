"""Contagem de uso por átomo, sem estado global: caminho de atributo -> átomo e termo -> classe.

Regras (todas registradas no summary.json):

* Recurso = bloco ``resource`` (não ``data``) do provedor, identificado por (repo_id, file, resource_address).
  Um bloco com count/for_each conta uma vez (é o que o texto configura, não as instâncias).
* Módulo = diretório do arquivo .tf dentro do repositório (repo_id, dirname(file)).
* attr_path -> caminho do átomo: ``dynamic["b"][i].content.x`` vira ``b.x``; índices ``[n]`` saem; o resultado
  precisa ser um ``path`` do atoms.jsonl do mesmo resource_type, ou um campo de um atributo de tipo objeto escrito
  como bloco (``security_rule { access = ... }`` configura o átomo ``security_rule``), conferido no tf_type. O resto não vira átomo e é contado por categoria
  (meta-argumento, metadado de dynamic, bloco retido inteiro, tipo fora do schema, atributo fora do schema).
* Classe do termo: ``withheld`` se há termo retido em qualquer nível; ``literal`` se o valor sai só do texto do
  atributo (literais, cadeias simbolizadas por privacidade, CIDR/IP, documento sem interpolação não-literal,
  funções puras sobre isso); ``symbolic`` se depende de variável, local, saída de módulo, referência, iterador de
  count/for_each/dynamic, workspace, arquivo ou função impura.
* Várias ocorrências do mesmo átomo no mesmo recurso (bloco repetido) contam um recurso; a classe do recurso é a
  mais fraca: withheld > symbolic > literal (literal só se toda ocorrência é literal).
"""
from __future__ import annotations

import posixpath
import re
from collections import defaultdict

META_TOP = frozenset({"count", "for_each", "provider", "depends_on", "lifecycle", "provisioner", "connection"})
DYN_RX = re.compile(r'dynamic\["([A-Za-z0-9_]+)"\]\[\d+\]\.')
IDX_RX = re.compile(r"\[\d+\]")
DATA_RX = re.compile(r"^(module\.SYM-[0-9a-f]+\.)*data\.")

# name_class de símbolo cujo valor não está no texto do atributo
NONGROUND_CLASSES = frozenset({"variable", "local", "module_output", "data_source", "resource_attribute",
                               "count_index", "each_key", "workspace"})
# funções cujo valor depende de outro arquivo, do ambiente ou do momento da execução
NONGROUND_FUNCS = frozenset({"file", "filebase64", "filebase64sha256", "filebase64sha512", "filemd5", "filesha1",
                             "filesha256", "filesha512", "fileexists", "fileset", "templatefile", "abspath",
                             "pathexpand", "timestamp", "plantimestamp", "uuid", "bcrypt"})

CLASSES = ("literal", "symbolic", "withheld")
RANK = {"literal": 0, "symbolic": 1, "withheld": 2}

UNMATCHED = ("meta_argument", "dynamic_meta", "withheld_block", "block_without_leaf", "type_not_in_schema",
             "attr_not_in_schema", "unparsed_path")


def is_data_address(addr: str) -> bool:
    return bool(DATA_RX.match(addr))


def module_of(file: str) -> str:
    return posixpath.dirname(file)


def atom_path(attr_path: str) -> tuple[str | None, str | None]:
    """(caminho do átomo, None) ou (None, categoria de não-átomo) — sem olhar o schema ainda."""
    head = attr_path.split(".", 1)[0].split("[", 1)[0]
    if head in META_TOP:
        return None, "meta_argument"
    p = attr_path
    while True:
        m = DYN_RX.search(p)
        if not m:
            break
        rest = p[m.end():]
        if not rest.startswith("content."):
            return None, "dynamic_meta"
        p = p[:m.start()] + m.group(1) + "." + rest[len("content."):]
    p = IDX_RX.sub("", p)
    if "[" in p or "]" in p or p.endswith(".") or ".." in p:
        return None, "unparsed_path"
    return p, None


def _ground(t) -> bool:  # noqa: C901
    """True se o termo (sem retidos) sai só do texto: ver a docstring do módulo."""
    if isinstance(t, list):
        return all(_ground(x) for x in t)
    if not isinstance(t, dict):
        return True
    k = t.get("kind")
    if k == "literal":
        return True
    if k == "symbol":
        return t.get("name_class") not in NONGROUND_CLASSES
    if k == "reference":
        return False
    if k == "expression":
        op = t.get("op")
        if op in NONGROUND_FUNCS:
            return False
        return all(_ground(a) for a in t.get("args") or [])
    if k == "document":
        return _doc_ground(t.get("tree"))
    if k is None and "$term" in t:
        return _ground(t["$term"])
    return all(_ground(v) for v in t.values())


def _doc_ground(x) -> bool:
    if isinstance(x, dict):
        if set(x) == {"$term"}:
            return _ground(x["$term"])
        return all(_doc_ground(v) for v in x.values())
    if isinstance(x, list):
        return all(_doc_ground(v) for v in x)
    return True


def _has_withheld(t) -> bool:
    if isinstance(t, dict):
        if t.get("kind") == "withheld":
            return True
        return any(_has_withheld(v) for v in t.values())
    if isinstance(t, list):
        return any(_has_withheld(v) for v in t)
    return False


def classify(term: dict) -> str:
    if _has_withheld(term):
        return "withheld"
    return "literal" if _ground(term) else "symbolic"


def weakest(a: str | None, b: str) -> str:
    return b if a is None or RANK[b] > RANK[a] else a


def _unwrap(tt):
    while isinstance(tt, list) and len(tt) == 2 and tt[0] in ("list", "set"):
        tt = tt[1]
    return tt


def _object_fields(tt):
    tt = _unwrap(tt)
    if isinstance(tt, list) and len(tt) >= 2 and tt[0] == "object" and isinstance(tt[1], dict):
        return tt[1]
    return None


def _navigates(tt, rest: list) -> bool:
    for k in rest:
        f = _object_fields(tt)
        if f is None or k not in f:
            return False
        tt = f[k]
    return True


class AtomIndex:
    """paths por resource_type e prefixos de bloco (para separar bloco retido de atributo desconhecido)."""

    def __init__(self, atoms):
        self.paths: dict[str, set] = defaultdict(set)
        self.prefixes: dict[str, set] = defaultdict(set)
        self.ids: dict[tuple, str] = {}
        self.objtype: dict[tuple, object] = {}  # atributo de tipo objeto (ou coleção de objetos)
        for a in atoms:
            rt, p = a["resource_type"], a["path"]
            self.paths[rt].add(p)
            self.ids[(rt, p)] = a["atom_id"]
            if _object_fields(a.get("tf_type")) is not None:
                self.objtype[(rt, p)] = a["tf_type"]
            parts = p.split(".")
            for i in range(1, len(parts)):
                self.prefixes[rt].add(".".join(parts[:i]))
        self.paths = dict(self.paths)
        self.prefixes = dict(self.prefixes)

    def resolve(self, rtype: str, attr_path: str, term: dict) -> tuple[str | None, str | None]:
        """(atom_id, None), (atom_id, "object_attr") ou (None, categoria de não-átomo)."""
        p, cat = atom_path(attr_path)
        if cat:
            return None, cat
        if rtype not in self.paths:
            return None, "type_not_in_schema"
        if p in self.paths[rtype]:
            return self.ids[(rtype, p)], None
        parts = p.split(".")
        for i in range(len(parts) - 1, 0, -1):
            head = ".".join(parts[:i])
            tt = self.objtype.get((rtype, head))
            if tt is not None:
                # atributo de objeto escrito como bloco ("attributes as blocks", ex.: security_rule { ... }):
                # o átomo é o atributo; o campo tem de existir no tipo do objeto
                if _navigates(tt, parts[i:]):
                    return self.ids[(rtype, head)], "object_attr"
                return None, "attr_not_in_schema"
        if p in self.prefixes.get(rtype, ()):
            return None, "withheld_block" if isinstance(term, dict) and term.get("kind") == "withheld" \
                else "block_without_leaf"
        return None, "attr_not_in_schema"


def repo_usage(provider: str, repo_id: str, resources: list, records, index: AtomIndex) -> dict:
    """Uso de um repositório.

    resources: [(file, resource_address, resource_type, family_id)] do provedor (sem data), do resources.parquet.
    records: iterável de registros C06 symbolic_config do repositório (qualquer provedor; filtra aqui).
    Devolve linhas usage (C06), módulos por átomo e contadores de auditoria.
    """
    res_key = {(f, a): (rt, fam) for f, a, rt, fam in resources}
    fams = {fam for _, _, _, fam in resources}
    if len(fams) > 1:
        raise ValueError(f"{repo_id}: mais de uma família no mesmo repositório")
    fam = next(iter(fams)) if fams else None
    n_res_type: dict[str, int] = defaultdict(int)
    for _, _, rt, _ in resources:
        n_res_type[rt] += 1
    per_res: dict[tuple, dict] = defaultdict(dict)  # (file, addr) -> atom_id -> classe mais fraca
    audit = defaultdict(int)
    unmatched_paths: set = set()
    for r in records:
        if r.get("provider") != provider:
            continue
        audit["records_provider"] += 1
        if is_data_address(r["resource_address"]):
            audit["records_data_source"] += 1
            continue
        key = (r["file"], r["resource_address"])
        if key not in res_key:
            audit["records_orphan"] += 1
            continue
        rt = res_key[key][0]
        if rt != r["resource_type"]:
            audit["records_type_mismatch"] += 1
            continue
        aid, cat = index.resolve(rt, r["attr_path"], r["term"])
        if aid is not None and cat == "object_attr":
            audit["records_matched_object_attr"] += 1
            cat = None
        if cat:
            audit["unmatched:" + cat] += 1
            if cat == "attr_not_in_schema":
                unmatched_paths.add((rt, atom_path(r["attr_path"])[0]))
            continue
        audit["records_matched"] += 1
        d = per_res[key]
        d[aid] = weakest(d.get(aid), classify(r["term"]))
    rows = {}
    modules: dict[str, set] = defaultdict(set)
    type_any: dict[str, dict] = defaultdict(lambda: {"n_set": 0, "literal": 0, "symbolic": 0, "withheld": 0})
    for key, atoms in per_res.items():
        rt = res_key[key][0]
        worst = None
        for aid, cls in atoms.items():
            row = rows.get(aid)
            if row is None:
                row = rows[aid] = {"repo_id": repo_id, "family_id": fam, "provider": provider, "resource_type": rt,
                                   "atom_id": aid, "n_resources": n_res_type[rt], "n_set": 0, "n_literal": 0,
                                   "n_symbolic": 0, "n_withheld": 0}
            row["n_set"] += 1
            row["n_" + cls] += 1
            modules[aid].add(module_of(key[0]))
            worst = weakest(worst, cls)
        ta = type_any[rt]
        ta["n_set"] += 1
        ta[worst] += 1
    out = []
    for rt in sorted(n_res_type):
        ta = type_any.get(rt, {"n_set": 0, "literal": 0, "symbolic": 0, "withheld": 0})
        out.append({"repo_id": repo_id, "family_id": fam, "provider": provider, "resource_type": rt,
                    "n_resources": n_res_type[rt], "n_set": ta["n_set"], "n_literal": ta["literal"],
                    "n_symbolic": ta["symbolic"], "n_withheld": ta["withheld"]})
        out.extend(rows[a] for a in sorted(a for a in rows if rows[a]["resource_type"] == rt))
    mods_per_type: dict[str, set] = defaultdict(set)
    for f, _, rt, _ in resources:
        mods_per_type[rt].add(module_of(f))
    return {"rows": out, "atom_modules": {a: len(m) for a, m in modules.items()},
            "type_modules": {rt: len(m) for rt, m in mods_per_type.items()},
            "n_modules": len({module_of(f) for f, _, _, _ in resources}),
            "audit": dict(audit), "unmatched_paths": sorted(unmatched_paths)}
