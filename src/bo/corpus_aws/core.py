"""Biblioteca de contagem de uso (C06 usage), independente do provedor.

Regras fixadas antes de ver os números (o resumo grava a versão das regras):

U1 recurso: um bloco `resource` (Managed) de resources.parquet, identificado por (repo_id, file, resource_address).
   Bloco `data` fica fora: os átomos do SCHEMA são de recursos gerenciados e o nome do tipo de data source
   coincide com o de recurso (aws_vpc, aws_ami...). Os data sources são contados à parte no relatório.
U2 módulo: o diretório do arquivo .tf dentro do repositório (repo_id, dirname(file)). O endereço já carrega a
   cadeia module.SYM-… do HCL, mas um diretório é um módulo uma vez só.
U3 caminho: attr_path sem índices ([n]); `dynamic["b"][i].content.` vira `b.`; o caminho casa com o átomo de
   maior prefixo no tipo (atributo-como-bloco, ex.: ingress { ... } do aws_security_group é o átomo `ingress`).
U4 meta-argumento (count, for_each, provider, depends_on, lifecycle, provisioner, connection) e meta de dynamic
   (for_each, iterator, labels) não são átomos: contados à parte.
U5 bloco retido inteiro (o HCL retém `environment { ... }` sem abrir): atribuído ao átomo só quando o bloco tem
   exatamente um átomo configurável no schema (a única coisa que ele pode carregar); senão fica não atribuído e é
   relatado por (tipo, bloco).
U6 classe de um valor: retido se há termo retido em qualquer ponto do termo; senão simbólico se o valor depende
   de nome resolvido fora do atributo (var, local, módulo, data, referência a recurso, count/each, path,
   workspace, iterador de dynamic, função de provedor ou função que lê arquivo, relógio ou acaso); senão literal
   (inclui texto literal simbolizado só por privacidade, name_class 'unknown', e documento sem interpolação).
U7 classe por (recurso, átomo) com vários registros (blocos repetidos): retido > simbólico > literal.
U8 linha de tipo (sem atom_id): n_resources = blocos gerenciados do tipo no repositório; n_set = 0 por
   definição (o uso por átomo está nas linhas com atom_id). Tipo ausente do schema só tem linha de tipo.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections import Counter, defaultdict

RULES_VERSION = "U1-U8/1"

META_TOP = frozenset({"count", "for_each", "provider", "depends_on", "lifecycle", "provisioner", "connection"})
DYNAMIC_META = frozenset({"for_each", "iterator", "labels"})
SYMBOLIC_CLASSES = frozenset({"variable", "local", "module_output", "data_source", "resource_attribute",
                              "count_index", "each_key", "path", "workspace"})
# funções do Terraform cujo valor não sai do texto do atributo: leem arquivo/diretório, relógio ou acaso
IMPURE_FUNCS = frozenset({"file", "fileexists", "fileset", "filebase64", "filebase64sha256", "filebase64sha512",
                          "filemd5", "filesha1", "filesha256", "filesha512", "templatefile", "abspath",
                          "pathexpand", "timestamp", "plantimestamp", "uuid", "bcrypt"})
PROVIDER_FUNC_OP = "hcl_provider_function"

CLASSES = ("literal", "symbolic", "withheld")
_RANK = {"literal": 0, "symbolic": 1, "withheld": 2}

_TOK = re.compile(r'([A-Za-z0-9_]+)|\[(\d+)\]|\["((?:[^"\\]|\\.)*)"\]|(\.)')
_DATA_ADDR = re.compile(r"^(module\.SYM-[0-9a-f]+\.)*data\.")


# ------------------------------------------------------------------------------------------------ caminhos
def is_data_address(addr: str) -> bool:
    return bool(_DATA_ADDR.match(addr))


def module_of(file: str) -> str:
    return posixpath.dirname(file) or "."


def tokens(attr_path: str) -> list[tuple[str, str]]:
    out = []
    pos = 0
    for m in _TOK.finditer(attr_path):
        if m.start() != pos:
            raise ValueError(f"attr_path fora da gramática do C06 na posição {pos}")
        pos = m.end()
        if m.group(1) is not None:
            out.append(("n", m.group(1)))
        elif m.group(2) is not None:
            out.append(("i", m.group(2)))
        elif m.group(3) is not None:
            out.append(("k", m.group(3)))
    if pos != len(attr_path):
        raise ValueError(f"attr_path fora da gramática do C06 na posição {pos}")
    return out


def normalize(attr_path: str) -> tuple[str, tuple[str, ...]]:
    """(disposição, segmentos). disposição: 'attr' | 'meta' | 'dynamic_meta'. U3/U4."""
    items = tokens(attr_path)
    segs: list[str] = []
    j = 0
    while j < len(items):
        t, v = items[j]
        if t == "n" and v == "dynamic" and j + 1 < len(items) and items[j + 1][0] == "k":
            segs.append(items[j + 1][1])
            j += 2
            while j < len(items) and items[j][0] == "i":
                j += 1
            if j < len(items) and items[j] == ("n", "content"):
                j += 1
            elif j < len(items) and items[j][0] == "n" and items[j][1] in DYNAMIC_META:
                return "dynamic_meta", tuple(segs)
            elif j < len(items):
                return "dynamic_meta", tuple(segs)
            continue
        if t == "n":
            segs.append(v)
        j += 1
    if not segs:
        raise ValueError("attr_path sem nome")
    if segs[0] in META_TOP:
        return "meta", tuple(segs)
    return "attr", tuple(segs)


class AtomIndex:
    """Átomos (C01) de um provedor: caminho por tipo, configurável, e átomos configuráveis por prefixo de bloco."""

    def __init__(self, provider: str):
        self.provider = provider
        self.paths: dict[str, set[str]] = defaultdict(set)
        self.meta: dict[tuple[str, str], dict] = {}
        self._under: dict[tuple[str, str], list[str]] = defaultdict(list)

    @classmethod
    def load(cls, path, provider: str) -> "AtomIndex":
        ix = cls(provider)
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    ix.add(json.loads(line))
        return ix

    def add(self, a: dict) -> None:
        if a["provider"] != self.provider:
            raise ValueError(f"átomo de outro provedor: {a['provider']}")
        t, p = a["resource_type"], a["path"]
        want = f"{self.provider}:{t}:{p}"
        if a["atom_id"] != want:
            raise ValueError(f"atom_id {a['atom_id']} != {want}")
        self.paths[t].add(p)
        self.meta[(t, p)] = {"configurable": bool(a.get("configurable")), "computed": bool(a.get("computed")),
                             "required": bool(a.get("required")), "optional": bool(a.get("optional")),
                             "deprecated": bool(a.get("deprecated"))}
        if a.get("configurable"):
            segs = p.split(".")
            for k in range(1, len(segs)):
                self._under[(t, ".".join(segs[:k]))].append(p)

    def has_type(self, t: str) -> bool:
        return t in self.paths

    def atom_id(self, t: str, p: str) -> str:
        return f"{self.provider}:{t}:{p}"

    def match(self, t: str, segs: tuple[str, ...]) -> tuple[str | None, str]:
        """U3: maior prefixo que é átomo. ('caminho', 'exact'|'prefix') ou (None, 'unmatched')."""
        ps = self.paths.get(t)
        if not ps:
            return None, "type_unknown"
        for k in range(len(segs), 0, -1):
            p = ".".join(segs[:k])
            if p in ps:
                return p, ("exact" if k == len(segs) else "prefix")
        return None, "unmatched"

    def single_leaf(self, t: str, segs: tuple[str, ...]) -> str | None:
        """U5: o único átomo configurável sob o bloco, ou None."""
        under = self._under.get((t, ".".join(segs)), [])
        return under[0] if len(under) == 1 else None


# ------------------------------------------------------------------------------------------------ termos
def _doc_class(x) -> int:
    """Pior classe dentro da árvore de um documento (termos embutidos em {"$term"} e {"$key"})."""
    worst = 0
    if isinstance(x, dict):
        for k, v in x.items():
            if k in ("$term", "$key") and isinstance(v, dict) and "kind" in v:
                worst = max(worst, term_rank(v))
            else:
                worst = max(worst, _doc_class(v))
            if worst == 2:
                return 2
    elif isinstance(x, list):
        for v in x:
            worst = max(worst, _doc_class(v))
            if worst == 2:
                return 2
    return worst


def term_rank(t: dict) -> int:
    """U6 em rank: 0 literal, 1 simbólico, 2 retido."""
    k = t.get("kind")
    if k == "withheld":
        return 2
    if k == "literal":
        return 0
    if k == "reference":
        return 1
    if k == "symbol":
        return 1 if t.get("name_class") in SYMBOLIC_CLASSES else 0
    if k == "document":
        return _doc_class(t.get("tree"))
    if k == "expression":
        op = t.get("op")
        worst = 1 if (op == PROVIDER_FUNC_OP or op in IMPURE_FUNCS) else 0
        for a in t.get("args") or ():
            worst = max(worst, term_rank(a))
            if worst == 2:
                return 2
        return worst
    raise ValueError(f"termo de tipo desconhecido: {k!r}")


def classify(term: dict) -> str:
    return CLASSES[term_rank(term)]


# ------------------------------------------------------------------------------------------------ agregação
class RepoAgg:
    """Agrega um repositório: recursos (do parquet) e registros (do jsonl) -> linhas por (tipo, átomo)."""

    def __init__(self, ix: AtomIndex, repo_id: str, resources: dict):
        # resources: (file, address) -> (resource_type, n_attrs, is_data)
        self.ix = ix
        self.repo_id = repo_id
        self.resources = resources
        self.family_id: str | None = None
        self.cells: dict[tuple, int] = {}          # (file, addr, atom_path) -> rank
        self.seen_records: Counter = Counter()     # (file, addr) -> registros vistos
        self.diag: Counter = Counter()
        self.unattributed_blocks: Counter = Counter()  # (tipo, bloco) -> registros
        self.unmatched_paths: Counter = Counter()      # (tipo, caminho) -> registros
        self.unknown_types: Counter = Counter()        # tipo -> registros

    def add(self, r: dict) -> None:
        if r["repo_id"] != self.repo_id:
            raise ValueError("registro de outro repositório no intervalo do índice")
        if self.family_id is None:
            self.family_id = r["family_id"]
        elif self.family_id != r["family_id"]:
            raise ValueError("repositório com duas famílias")
        key = (r["file"], r["resource_address"])
        res = self.resources.get(key)
        if res is None:
            self.diag["records_without_resource"] += 1
            return
        if res[0] != r["resource_type"]:
            self.diag["records_type_mismatch"] += 1
            return
        self.seen_records[key] += 1
        if res[2]:
            self.diag["records_data"] += 1
            return
        self.diag["records_managed"] += 1
        t = r["resource_type"]
        disp, segs = normalize(r["attr_path"])
        if disp != "attr":
            self.diag[f"records_{disp}"] += 1
            if disp == "meta":
                self.diag[f"records_meta:{segs[0]}"] += 1
            return
        if not self.ix.has_type(t):
            self.diag["records_type_unknown"] += 1
            self.unknown_types[t] += 1
            return
        rank = term_rank(r["term"])
        p, how = self.ix.match(t, segs)
        if p is None and rank == 2 and r["term"].get("kind") == "withheld":
            leaf = self.ix.single_leaf(t, segs)
            if leaf is not None:
                p, how = leaf, "withheld_block_attributed"
            elif self.ix._under.get((t, ".".join(segs))):
                self.diag["records_withheld_block_unattributed"] += 1
                self.unattributed_blocks[(t, ".".join(segs))] += 1
                return
        if p is None:
            self.diag["records_unmatched"] += 1
            self.unmatched_paths[(t, ".".join(segs))] += 1
            return
        self.diag[f"records_{how}"] += 1
        if rank == 2 and r["term"].get("kind") != "withheld":
            self.diag["records_embedded_withheld"] += 1
        ck = (key[0], key[1], p)
        if self.cells.get(ck, -1) < rank:
            self.cells[ck] = rank

    def finish(self) -> dict:
        """Linhas do repositório e diagnósticos. Confere registros contra n_attrs do parquet."""
        for key, (_t, n_attrs, _d) in self.resources.items():
            got = self.seen_records.get(key, 0)
            if got != n_attrs:
                self.diag["resources_n_attrs_mismatch"] += 1
        per: dict[tuple, list] = {}
        mods: dict[tuple, set] = defaultdict(set)
        for (file, addr, p), rank in self.cells.items():
            t = self.resources[(file, addr)][0]
            row = per.setdefault((t, p), [0, 0, 0, 0])
            row[0] += 1
            row[1 + rank] += 1
            mods[(t, p)].add(module_of(file))
        rows = {k: (v[0], v[1], v[2], v[3], len(mods[k])) for k, v in per.items()}
        return {"repo_id": self.repo_id, "family_id": self.family_id, "rows": rows, "diag": dict(self.diag),
                "unattributed_blocks": dict(self.unattributed_blocks), "unmatched_paths": dict(self.unmatched_paths),
                "unknown_types": dict(self.unknown_types)}


def usage_row(provider: str, repo_id: str, family_id: str, rtype: str, n_resources: int,
              atom_id: str | None = None, n_set: int = 0, n_literal: int = 0, n_symbolic: int = 0,
              n_withheld: int = 0) -> dict:
    row = {"repo_id": repo_id, "family_id": family_id, "provider": provider, "resource_type": rtype,
           "n_resources": n_resources, "n_set": n_set, "n_literal": n_literal, "n_symbolic": n_symbolic,
           "n_withheld": n_withheld}
    if atom_id is not None:
        row["atom_id"] = atom_id
    return row


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
