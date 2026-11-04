"""Contagem de uso por átomo sobre a configuração simbólica do HCL (C06), para um provedor.

Biblioteca sem estado global: o provedor e os caminhos entram como argumentos. Nada aqui lê o HCL bruto nem
executa Terraform; a entrada é o que o HCL gravou (resources.parquet, symbolic_config.jsonl e o índice por
repositório) e o atoms.jsonl do SCHEMA-<provedor> (C01).

Definições (fixadas antes de olhar o resultado; o summary.json repete):

* Recurso: linha de resources.parquet do provedor que NÃO é data source (endereço sem o segmento ``data.``).
  Chave: (repo_id, file, resource_address), única por construção no HCL. Data sources são leitura, não
  configuração: ficam fora do usage e entram só na contagem do relatório.
* Módulo: diretório do arquivo .tf dentro do repositório, ``(repo_id, dirname(file))`` — a unidade de módulo
  do TerraDS. O caminho é o já simbolizado pelo HCL; só a igualdade importa, nunca o texto.
* Caminho → átomo: tira os índices ``[n]``, reescreve ``dynamic["b"][n].content.`` como ``b.``; se o
  resultado é caminho de átomo do tipo, é esse átomo; senão, o MAIOR prefixo próprio que é átomo de atributo
  (subchave de mapa ou objeto, ex. ``metadata.user_data`` → ``metadata``). O que sobra não vira átomo e é
  contado por causa: meta-argumento do Terraform, meta de bloco dynamic, bloco atribuído como atributo,
  atributo fora do schema, tipo fora do schema.
* Classe de um termo: ``withheld`` se o termo contém, em qualquer profundidade, um termo retido; ``literal``
  se é literal, ou documento sem nenhum identificador simbolizado e sem termo embutido; senão ``symbolic``
  (símbolo, expressão, referência, documento simbolizado).
* Classe de (recurso, átomo) com várias ocorrências (blocos repetidos, subchaves): withheld > symbolic >
  literal. Literal quer dizer valor inteiro conhecido.
* usage por (repo, família, tipo, átomo): n_resources = recursos do tipo no repositório; n_set = recursos
  que configuram o átomo; n_literal + n_symbolic + n_withheld = n_set (C06-USAGE). Átomo ausente de um
  (repo, tipo) = n_set 0; o denominador sai do registro do tipo.
* Registro do tipo (sem atom_id), um por (repo, tipo): n_resources = recursos do tipo; n_set = recursos com
  pelo menos um átomo configurado; a classe do recurso combina todos os seus átomos pela mesma precedência.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

CLASSES = ("literal", "symbolic", "withheld")
_RANK = {"literal": 0, "symbolic": 1, "withheld": 2}

# Meta-argumentos do Terraform no nível do bloco resource (nunca atributo de provider).
META_TOP = frozenset({"count", "for_each", "provider", "depends_on", "lifecycle", "provisioner", "connection"})
DYN_META = frozenset({"for_each", "iterator", "labels", "content"})

_IDX = re.compile(r"\[\d+\]")
_DYN_CONTENT = re.compile(r'dynamic\["([A-Za-z0-9_]+)"\]\[\d+\]\.content\.')
_DYN_ANY = re.compile(r'dynamic\["[A-Za-z0-9_]+"\]')
_DATA = re.compile(r"(^|\.)data\.[a-z]")
_LEAD = re.compile(r"[A-Za-z0-9_]+")

UNATTRIBUTED = ("meta_argument", "dynamic_meta", "block_as_attribute", "attr_not_in_schema",
                "type_not_in_schema")


def worse(a: str | None, b: str) -> str:
    """Classe combinada pela precedência withheld > symbolic > literal."""
    return b if a is None or _RANK[b] > _RANK[a] else a


def is_data_address(addr: str) -> bool:
    return bool(_DATA.search(addr))


def module_key(file: str) -> str:
    return posixpath.dirname(file) or "."


def _contains_withheld(node) -> bool:
    if isinstance(node, dict):
        if node.get("kind") == "withheld":
            return True
        return any(_contains_withheld(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_withheld(v) for v in node)
    return False


def _contains_term(node) -> bool:
    if isinstance(node, dict):
        if "$term" in node:
            return True
        return any(_contains_term(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_term(v) for v in node)
    return False


def term_class(term: dict) -> str:
    """literal | symbolic | withheld de um termo C00 (ver docstring do módulo)."""
    kind = term.get("kind")
    if kind == "withheld" or _contains_withheld(term.get("args")) or _contains_withheld(term.get("tree")):
        return "withheld"
    if kind == "literal":
        return "literal"
    if kind == "document" and not term.get("symbolized") and not _contains_term(term.get("tree")):
        return "literal"
    if kind in ("symbol", "expression", "reference", "document"):
        return "symbolic"
    raise ValueError(f"termo de tipo desconhecido: {kind!r}")


def normalize_path(attr_path: str) -> str:
    """Caminho do HCL → caminho de blocos do C01 (sem índices, dynamic desdobrado)."""
    return _IDX.sub("", _DYN_CONTENT.sub(r"\1.", attr_path))


@dataclass
class AtomIndex:
    """Átomos de um provedor: caminho por tipo, e os caminhos de bloco (para reconhecer bloco-como-atributo)."""

    provider: str
    paths: dict = field(default_factory=dict)       # tipo -> {caminho: atom_id}
    blocks: dict = field(default_factory=dict)      # tipo -> {caminho de bloco}
    configurable: dict = field(default_factory=dict)  # atom_id -> bool
    n_atoms: int = 0

    @classmethod
    def load(cls, path: str, provider: str) -> "AtomIndex":
        ix = cls(provider)
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if not ln.strip():
                    continue
                a = json.loads(ln)
                if a["provider"] != provider:
                    raise ValueError(f"átomo de outro provedor em {path}: {a['atom_id']}")
                rt = a["resource_type"]
                ix.paths.setdefault(rt, {})[a["path"]] = a["atom_id"]
                bl = ix.blocks.setdefault(rt, set())
                bp = [b["block"] for b in a.get("block_path") or []]
                for i in range(1, len(bp) + 1):
                    bl.add(".".join(bp[:i]))
                ix.configurable[a["atom_id"]] = bool(a.get("configurable"))
                ix.n_atoms += 1
        return ix

    def resolve(self, rtype: str, attr_path: str) -> tuple[str | None, str | None]:
        """(atom_id, None) ou (None, causa) para um attr_path do C06."""
        paths = self.paths.get(rtype)
        if paths is None:
            return None, "type_not_in_schema"
        p = normalize_path(attr_path)
        if p in paths:
            return paths[p], None
        m = _LEAD.match(p)
        if m and m.group(0) in META_TOP:
            return None, "meta_argument"
        if _DYN_ANY.search(p):
            return None, "dynamic_meta"
        if p in self.blocks.get(rtype, ()):
            return None, "block_as_attribute"
        parts = p.split(".")
        for i in range(len(parts) - 1, 0, -1):
            pre = ".".join(parts[:i])
            if pre in paths:
                return paths[pre], None
            if pre in self.blocks.get(rtype, ()):
                break  # prefixo é bloco: o resto é atributo do bloco que o schema não tem
        return None, "attr_not_in_schema"


@dataclass
class Tally:
    """Acumulador da contagem de um provedor (memória proporcional aos recursos do provedor)."""

    provider: str
    atoms: AtomIndex
    # (repo, file, addr) -> (family, type)
    resources: dict = field(default_factory=dict)
    # (repo, file, addr) -> {atom_id: classe}
    set_atoms: dict = field(default_factory=lambda: defaultdict(dict))
    stats: Counter = field(default_factory=Counter)
    unattributed: Counter = field(default_factory=Counter)  # (causa, tipo, caminho normalizado) -> n
    n_attrs_declared: int = 0

    def add_resource(self, row: dict) -> bool:
        """Registra uma linha de resources.parquet; devolve False se ela fica fora (outro provedor, data)."""
        if row["provider"] != self.provider:
            return False
        if is_data_address(row["resource_address"]):
            self.stats["data_blocks"] += 1
            self.stats["data_attrs_declared"] += int(row["n_attrs"])
            return False
        key = (row["repo_id"], row["file"], row["resource_address"])
        if key in self.resources:
            raise ValueError("recurso repetido em resources.parquet (chave repo, file, endereço)")
        self.resources[key] = (row["family_id"], row["resource_type"])
        self.n_attrs_declared += int(row["n_attrs"])
        self.stats["managed_blocks"] += 1
        return True

    def add_record(self, rec: dict) -> None:
        """Um registro do symbolic_config.jsonl (de qualquer provedor; os de fora são ignorados)."""
        if rec["provider"] != self.provider:
            return
        if is_data_address(rec["resource_address"]):
            self.stats["data_records"] += 1
            return
        key = (rec["repo_id"], rec["file"], rec["resource_address"])
        res = self.resources.get(key)
        if res is None:
            raise ValueError("registro sem linha correspondente em resources.parquet")
        if res[1] != rec["resource_type"] or res[0] != rec["family_id"]:
            raise ValueError("registro diverge do recurso (tipo ou família)")
        self.stats["managed_records"] += 1
        cls = term_class(rec["term"])
        self.stats[f"term_class:{cls}"] += 1
        atom, cause = self.atoms.resolve(rec["resource_type"], rec["attr_path"])
        if atom is None:
            self.stats[f"unattributed:{cause}"] += 1
            self.unattributed[(cause, rec["resource_type"], normalize_path(rec["attr_path"]))] += 1
            return
        self.stats["attributed_records"] += 1
        cur = self.set_atoms[key]
        cur[atom] = worse(cur.get(atom), cls)

    # ------------------------------------------------------------------------------------------ saídas
    def usage_records(self) -> list[dict]:
        """Registros C06 usage, ordenados (repo, tipo, atom_id; o do tipo, sem atom_id, primeiro)."""
        by_rt = defaultdict(list)  # (repo, family, type) -> [chaves de recurso]
        for key, (fam, rt) in self.resources.items():
            by_rt[(key[0], fam, rt)].append(key)
        out = []
        for (repo, fam, rt) in sorted(by_rt):
            keys = by_rt[(repo, fam, rt)]
            per_atom = defaultdict(Counter)
            whole = Counter()
            for k in keys:
                sa = self.set_atoms.get(k)
                if not sa:
                    continue
                agg = None
                for atom, cls in sa.items():
                    per_atom[atom][cls] += 1
                    agg = worse(agg, cls)
                whole[agg] += 1
            base = {"repo_id": repo, "family_id": fam, "provider": self.provider, "resource_type": rt,
                    "n_resources": len(keys)}
            out.append({**base, **_counts(whole)})
            for atom in sorted(per_atom):
                out.append({**base, "atom_id": atom, **_counts(per_atom[atom])})
        return out

    def atom_totals(self) -> list[dict]:
        """Por átomo do schema (todos, inclusive os nunca configurados): repositórios, famílias, módulos e
        recursos que o configuram, contra o denominador do tipo."""
        type_res = defaultdict(int)
        type_repos = defaultdict(set)
        type_fams = defaultdict(set)
        type_mods = defaultdict(set)
        for key, (fam, rt) in self.resources.items():
            type_res[rt] += 1
            type_repos[rt].add(key[0])
            type_fams[rt].add(fam)
            type_mods[rt].add((key[0], module_key(key[1])))
        a_repos = defaultdict(set)
        a_fams = defaultdict(set)
        a_mods = defaultdict(set)
        a_cls = defaultdict(Counter)
        for key, sa in self.set_atoms.items():
            fam = self.resources[key][0]
            for atom, cls in sa.items():
                a_repos[atom].add(key[0])
                a_fams[atom].add(fam)
                a_mods[atom].add((key[0], module_key(key[1])))
                a_cls[atom][cls] += 1
        out = []
        for rt in sorted(self.atoms.paths):
            for path, atom in sorted(self.atoms.paths[rt].items(), key=lambda kv: kv[1]):
                c = a_cls.get(atom, Counter())
                out.append({
                    "atom_id": atom, "resource_type": rt, "configurable": self.atoms.configurable[atom],
                    "n_repos": len(a_repos.get(atom, ())), "n_families": len(a_fams.get(atom, ())),
                    "n_modules": len(a_mods.get(atom, ())), **_counts(c),
                    "type_n_resources": type_res.get(rt, 0), "type_n_repos": len(type_repos.get(rt, ())),
                    "type_n_families": len(type_fams.get(rt, ())), "type_n_modules": len(type_mods.get(rt, ())),
                })
        return out

    def type_totals(self) -> list[dict]:
        """Por tipo presente no corpus (inclusive fora do schema): recursos, repositórios, famílias, módulos."""
        agg = defaultdict(lambda: [0, set(), set(), set(), 0])
        for key, (fam, rt) in self.resources.items():
            a = agg[rt]
            a[0] += 1
            a[1].add(key[0])
            a[2].add(fam)
            a[3].add((key[0], module_key(key[1])))
            if self.set_atoms.get(key):
                a[4] += 1
        return [{"resource_type": rt, "in_schema": rt in self.atoms.paths, "n_resources": a[0],
                 "n_repos": len(a[1]), "n_families": len(a[2]), "n_modules": len(a[3]),
                 "n_resources_with_atom": a[4]}
                for rt, a in sorted(agg.items())]


def _counts(c: Counter) -> dict:
    n = {f"n_{k}": int(c.get(k, 0)) for k in CLASSES}
    return {"n_set": sum(n.values()), **n}


def dumps(obj) -> str:
    """JSON canônico (chaves ordenadas, sem espaços, UTF-8): regeneração byte a byte."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
