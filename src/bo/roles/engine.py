"""Motor de regras do ROLES: carrega roles/rules.yaml e classifica um átomo pela primeira regra que casa.

O código não conhece provedor nenhum: o provedor só entra como dado (o campo provider do átomo, usado para
tirar o prefixo "<provider>_" do resource_type e para agrupar os tipos do mesmo provedor). Toda palavra que
decide um papel está em rules.yaml.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROLES = ("CONFIG", "IDENTIFIER", "NAME", "TAG", "REFERENCE", "TIMESTAMP", "SECRET")
KINDS = ("string", "number", "bool", "dynamic", "coll_string", "coll_other", "map_string", "map_other", "object")
STEM_CLASSES = ("empty", "own", "self", "type", "other")
CONDITIONS = ("flag", "kind_in", "leaf_in", "leaf_not_in", "tail_in", "first_token_in", "block_in", "block_tail_in",
              "type_head_in", "stem", "leaf_is_type", "leaf_is_own", "doc_format_in", "doc_format_not_in",
              "doc_desc", "doc_desc_names_leaf")
FLAGS = ("sensitive", "write_only", "configurable", "top_level")
DERIVED_LEXICONS = ("id_tails", "name_tails", "id_or_name_tails")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokens(s: str) -> list[str]:
    """Palavras de um nome: separa por _ e por camelCase, minúsculas."""
    return [t for t in _CAMEL.sub("_", s).lower().split("_") if t]


def kind(tf_type) -> str:
    """Tipo cty -> classe neutra (KINDS)."""
    if isinstance(tf_type, str):
        return tf_type if tf_type in ("string", "number", "bool", "dynamic") else "object"
    if isinstance(tf_type, list) and tf_type:
        head = tf_type[0]
        inner = tf_type[1] if len(tf_type) > 1 else None
        if head in ("list", "set"):
            return "coll_string" if inner == "string" else "coll_other"
        if head == "map":
            return "map_string" if inner == "string" else "map_other"
    return "object"


def strip_provider(resource_type: str, provider: str) -> str:
    p = provider + "_"
    return resource_type[len(p):] if resource_type.startswith(p) else resource_type


def own_suffixes(type_tokens: list[str]) -> set[str]:
    """Sufixos de palavras do nome do tipo: o substantivo do próprio tipo (bucket_policy -> policy, bucket_policy)."""
    return {"_".join(type_tokens[i:]) for i in range(len(type_tokens))}


def type_forms(type_tokens: list[str]) -> set[str]:
    """Formas pelas quais outro atributo cita este tipo: inteiro; sem a 1ª palavra; (3+) sem uma do meio."""
    n = len(type_tokens)
    out = {"_".join(type_tokens)}
    if n >= 2:
        out.add("_".join(type_tokens[1:]))
    if n >= 3:
        for i in range(1, n - 1):
            out.add("_".join(type_tokens[:i] + type_tokens[i + 1:]))
    return out


def singular(s: str) -> str:
    return s[:-1] if len(s) > 3 and s.endswith("s") and not s.endswith("ss") else s


@dataclass
class Rule:
    id: str
    role: str
    text: str
    when: dict


@dataclass
class Rules:
    path: Path
    raw: dict
    rules: list[Rule]
    lex: dict[str, set[str]]
    tails: dict[str, list[list[str]]]  # léxico -> termos como listas de palavras (para tail_in)
    format_classes: dict[str, set[str]]
    patterns: dict[str, re.Pattern]
    wo_suffix: str
    stem_tails: list[list[str]] = field(default_factory=list)


def load(path: Path) -> Rules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    norm = raw["normalize"]
    lex = {k: set(v) for k, v in raw["lexicons"].items()}
    for k in DERIVED_LEXICONS:
        if k in lex:
            raise ValueError(f"léxico {k} é derivado de normalize e não pode ser declarado")
    lex["id_tails"] = set(norm["id_tails"])
    lex["name_tails"] = set(norm["name_tails"])
    lex["id_or_name_tails"] = lex["id_tails"] | lex["name_tails"]
    tails = {k: sorted((t.split("_") for t in v), key=lambda x: -len(x)) for k, v in lex.items()}
    rules = [Rule(r["id"], r["role"], r["text"], r.get("when") or {}) for r in raw["rules"]]
    fc = {k: set(v) for k, v in raw["format_classes"].items()}
    pats = {k: re.compile(v, re.I) for k, v in raw["patterns"].items()}
    out = Rules(path, raw, rules, lex, tails, fc, pats, norm["write_only_suffix"])
    out.stem_tails = tails["id_or_name_tails"]
    problems = validate(out)
    if problems:
        raise ValueError("rules.yaml inválido: " + "; ".join(problems))
    return out


def validate(r: Rules) -> list[str]:
    """Coerência interna: papéis, condições e léxicos citados existem; ids únicos; última regra é o padrão."""
    probs = []
    seen = set()
    for rule in r.rules:
        if rule.id in seen:
            probs.append(f"{rule.id} repetida")
        seen.add(rule.id)
        if not re.fullmatch(r"ROLE-[A-Z0-9][A-Z0-9\-]*", rule.id):
            probs.append(f"{rule.id}: id fora do padrão C04")
        if rule.role not in ROLES:
            probs.append(f"{rule.id}: papel {rule.role} fora do C04")
        for c, v in rule.when.items():
            if c not in CONDITIONS:
                probs.append(f"{rule.id}: condição desconhecida {c}")
            elif c == "flag":
                for f in v:
                    if f not in FLAGS:
                        probs.append(f"{rule.id}: flag desconhecida {f}")
            elif c == "kind_in":
                for k in v:
                    if k not in KINDS:
                        probs.append(f"{rule.id}: kind desconhecido {k}")
            elif c == "stem":
                for k in v:
                    if k not in STEM_CLASSES:
                        probs.append(f"{rule.id}: classe de radical desconhecida {k}")
            elif c in ("doc_format_in", "doc_format_not_in"):
                if v not in r.format_classes:
                    probs.append(f"{rule.id}: classe de formato desconhecida {v}")
            elif c in ("doc_desc", "doc_desc_names_leaf"):
                if v not in r.patterns:
                    probs.append(f"{rule.id}: padrão desconhecido {v}")
            elif c in ("leaf_is_type", "leaf_is_own"):
                if v is not True:
                    probs.append(f"{rule.id}: {c} só aceita true")
            elif v not in r.lex:
                probs.append(f"{rule.id}: léxico desconhecido {v}")
    if not r.rules or r.rules[-1].when:
        probs.append("a última regra tem de ser o padrão (when vazio)")
    return probs


@dataclass
class Atom:
    """Os traços de um átomo que as regras podem ler (nenhum deles é o nome do provedor)."""
    atom_id: str
    provider: str
    leaf: str
    leaf_tokens: list[str]
    kind: str
    flags: dict[str, bool]
    block: str | None
    block_tokens: list[str]
    type_head: str
    own: set[str]
    stem_class: str | None
    leaf_is_type: bool
    leaf_is_own: bool
    formats: list[tuple[str, str]]  # (valor normalizado, fact_id)
    descs: list[tuple[str, str]]    # (texto, fact_id)


class Context:
    """Índices por provedor (nomes de tipo), montados a partir dos átomos."""

    def __init__(self, rules: Rules, atoms: list[dict]):
        self.rules = rules
        self.types: dict[str, dict[str, list[str]]] = {}
        self.forms: dict[str, set[str]] = {}
        self.exact: dict[str, set[str]] = {}
        for a in atoms:
            prov = a["provider"]
            rt = a["resource_type"]
            t = self.types.setdefault(prov, {})
            if rt not in t:
                t[rt] = tokens(strip_provider(rt, prov))
        for prov, t in self.types.items():
            fs = set()
            for toks in t.values():
                fs |= type_forms(toks)
            self.forms[prov] = fs
            self.exact[prov] = {"_".join(toks) for toks in t.values()}

    def base_leaf(self, leaf: str, a: dict) -> str:
        suf = self.rules.wo_suffix
        if a.get("write_only") and suf and leaf.endswith(suf) and len(leaf) > len(suf):
            return leaf[: -len(suf)]
        return leaf

    def features(self, a: dict, facts: list[dict]) -> Atom:
        r = self.rules
        prov = a["provider"]
        raw_leaf = a["path"].rpartition(".")[2]
        leaf = self.base_leaf(raw_leaf, a)
        ltoks = tokens(leaf)
        type_toks = self.types[prov][a["resource_type"]]
        own = own_suffixes(type_toks)
        forms = self.forms[prov]
        full = "_".join(type_toks)
        exact = self.exact[prov]

        def own_ok(s: str) -> bool:
            # sufixo do próprio tipo que não é exatamente o nome de OUTRO tipo (assignment_vault -> vault não é próprio)
            return s in own and (s == full or s not in exact)

        # radical: tira a cauda de id/nome mais longa
        stem_class = None
        for tail in r.stem_tails:
            k = len(tail)
            if len(ltoks) >= k and ltoks[-k:] == tail:
                stem = "_".join(ltoks[:-k])
                if not stem:
                    stem_class = "empty"
                elif own_ok(stem):
                    stem_class = "own"
                elif stem in r.lex.get("self_stems", set()):
                    stem_class = "self"
                elif stem in forms or singular(stem) in forms:
                    stem_class = "type"
                else:
                    stem_class = "other"
                break
        lj = "_".join(ltoks)
        leaf_is_type = (lj in forms or singular(lj) in forms) and not own_ok(lj) and not own_ok(singular(lj))
        bp = a.get("block_path") or []
        block = bp[-1]["block"] if bp else None
        formats, descs = [], []
        for f in facts:
            if f.get("status") != "stated":
                continue
            v = f.get("value")
            if f["fact_kind"] == "format":
                if isinstance(v, str):
                    formats.append((v, f["fact_id"]))
                elif isinstance(v, dict) and isinstance(v.get("aspect"), str):
                    formats.append(("aspect:" + v["aspect"], f["fact_id"]))
            elif f["fact_kind"] == "description" and isinstance(v, str):
                descs.append((v, f["fact_id"]))
        flags = {
            "sensitive": bool(a["sensitive"]),
            "write_only": bool(a.get("write_only", False)),
            "configurable": bool(a["configurable"]),
            "top_level": not bp,
        }
        return Atom(a["atom_id"], prov, leaf, ltoks, kind(a["tf_type"]), flags, block,
                    tokens(block) if block else [], type_toks[-1] if type_toks else "", own, stem_class,
                    leaf_is_type, own_ok(lj), formats, descs)


_NL_CACHE: dict[tuple[str, tuple[str, ...]], re.Pattern] = {}


def names_leaf_pattern(id_words: str, leaf_tokens: list[str]) -> re.Pattern:
    """"<id> of|for [the] [até 2 palavras] <folha>" ou "<folha> [1 palavra] <id>"; folha em palavras, plural opcional."""
    key = (id_words, tuple(leaf_tokens))
    if key not in _NL_CACHE:
        toks = list(leaf_tokens)
        if not toks:
            _NL_CACHE[key] = re.compile(r"(?!)")
            return _NL_CACHE[key]
        toks[-1] = re.escape(singular(toks[-1])) + "(?:s|es)?"
        noun = r"[ _-]?".join(re.escape(t) if i < len(toks) - 1 else t for i, t in enumerate(toks))
        noun = r"\b" + noun + r"\b"
        src = (rf"\b{id_words}\)?\s+(?:of|for)\s+(?:(?:the|an?|this|that)\s+)?(?:[\w'-]+\s+){{0,2}}?{noun}"
               rf"|{noun}\s+(?:[\w'-]+\s+)?{id_words}\b")
        _NL_CACHE[key] = re.compile(src, re.I)
    return _NL_CACHE[key]


def _tail_in(toks: list[str], terms: list[list[str]]) -> bool:
    return any(len(toks) >= len(t) and toks[-len(t):] == t for t in terms)


def check(cond: str, arg, x: Atom, r: Rules) -> tuple[bool, list[str]]:
    """Uma condição; devolve (casou, fact_ids que a sustentam)."""
    if cond == "flag":
        return all(x.flags[k] == bool(v) for k, v in arg.items()), []
    if cond == "kind_in":
        return x.kind in arg, []
    if cond == "leaf_in":
        return "_".join(x.leaf_tokens) in r.lex[arg], []
    if cond == "leaf_not_in":
        return "_".join(x.leaf_tokens) not in r.lex[arg], []
    if cond == "tail_in":
        return _tail_in(x.leaf_tokens, r.tails[arg]), []
    if cond == "first_token_in":
        return len(x.leaf_tokens) >= 2 and x.leaf_tokens[0] in r.lex[arg], []
    if cond == "block_in":
        return x.block is not None and "_".join(x.block_tokens) in r.lex[arg], []
    if cond == "block_tail_in":
        return x.block is not None and _tail_in(x.block_tokens, r.tails[arg]), []
    if cond == "type_head_in":
        return x.type_head in r.lex[arg], []
    if cond == "stem":
        return x.stem_class in arg, []
    if cond == "leaf_is_type":
        return x.leaf_is_type, []
    if cond == "leaf_is_own":
        return x.leaf_is_own, []
    if cond == "doc_format_in":
        ids = [fid for v, fid in x.formats if v in r.format_classes[arg]]
        return bool(ids), ids
    if cond == "doc_format_not_in":
        return not any(v in r.format_classes[arg] for v, _ in x.formats), []
    if cond == "doc_desc":
        pat = r.patterns[arg]
        ids = [fid for v, fid in x.descs if pat.search(v)]
        return bool(ids), ids
    if cond == "doc_desc_names_leaf":
        pat = names_leaf_pattern(r.raw["patterns"][arg], x.leaf_tokens)
        ids = [fid for v, fid in x.descs if pat.search(v)]
        return bool(ids), ids
    raise ValueError(f"condição desconhecida {cond}")


def classify(x: Atom, r: Rules) -> tuple[Rule, list[str]]:
    """Primeira regra cujas condições todas casam; devolve a regra e os fact_id usados."""
    for rule in r.rules:
        used: list[str] = []
        ok = True
        for cond, arg in rule.when.items():
            hit, ids = check(cond, arg, x, r)
            if not hit:
                ok = False
                break
            used.extend(ids)
        if ok:
            return rule, sorted(set(used))
    raise AssertionError("sem regra padrão")
