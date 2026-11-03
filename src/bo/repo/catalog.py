"""Catálogo de módulos: leitura do modulos.json (ou do retrato modules/owners.json),
expansão de caminhos (C00), casamento de caminhos, produtores e fechos de dependência."""

from __future__ import annotations

import fnmatch
import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import core
from .core import BoError

OWNERS_REL = "modules/owners.json"
STATE_REL = "modules/state.json"


@dataclass
class Module:
    id: str
    branch: str
    worktree: str
    deps: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    owns: list = field(default_factory=list)
    gates: list = field(default_factory=list)
    contracts: list = field(default_factory=list)
    wave: int | None = None
    needs_cloud: bool = False
    lock: str | None = None
    known: bool = True  # False = módulo sintético (ex. DUMMY), fora do plano


FIELDS = ("deps", "inputs", "outputs", "owns", "gates", "contracts")


def default_branch(mid: str) -> str:
    return "bo/" + mid.lower()


def default_worktree(mid: str) -> str:
    return str(core.lanes_dir() / ("bo-" + mid.lower()))


def synthetic_module(mid: str) -> Module:
    """Módulo fora do plano (ex. DUMMY do gate do REPO): posse padrão C00, sem gates."""
    pkg = mid.lower().replace("-", "_")
    return Module(
        id=mid, branch=default_branch(mid), worktree=default_worktree(mid),
        owns=[f"$BO_REPO/src/bo/{pkg}/", f"$BO_REPO/tests/{pkg}/", f"$BO_REPO/gates/{mid}.sh",
              f"$BO_REPO/results/{mid}/", f"$BO_DATA/{mid}/"],
        known=False)


class Catalog:
    def __init__(self, raw: dict, source: Path):
        self.raw = raw
        self.source = Path(source)
        self.index_sets = {k: v for k, v in raw.get("index_sets", {}).items() if isinstance(v, list)}
        self.modules: dict[str, Module] = {}
        for m in raw.get("modules", []):
            mid = m.get("stable_id") or m.get("id")
            self.modules[mid] = Module(
                id=mid, branch=m.get("branch") or default_branch(mid),
                worktree=m.get("worktree") or default_worktree(mid),
                wave=m.get("wave"), needs_cloud=bool(m.get("needs_cloud")), lock=m.get("lock"),
                **{k: list(m.get(k) or []) for k in FIELDS})
        cat = raw.get("artifact_catalog") or {}
        self.artifacts = list(cat.get("artifacts") or [])
        self.external_inputs = list(cat.get("external_inputs") or [])
        self.contracts = dict(raw.get("contracts") or {})

    # ------------------------------------------------------------ consulta
    def get(self, mid: str, allow_synthetic: bool = False) -> Module:
        if mid in self.modules:
            return self.modules[mid]
        if allow_synthetic:
            return synthetic_module(mid)
        near = [k for k in self.modules if k.lower() == mid.lower()]
        hint = f" (quis dizer {near[0]}?)" if near else ""
        raise BoError(f"módulo {mid!r} não existe em {self.source}{hint}", code=2)

    def by_branch(self, branch: str) -> Module | None:
        b = branch.removeprefix("refs/heads/")
        for m in self.modules.values():
            if m.branch == b:
                return m
        return None

    def deps_closure(self, mid: str) -> list[str]:
        seen: list[str] = []
        stack = list(self.get(mid).deps)
        while stack:
            d = stack.pop()
            if d in seen:
                continue
            seen.append(d)
            if d in self.modules:
                stack.extend(self.modules[d].deps)
        return seen

    def reverse_closure(self, start: set[str]) -> set[str]:
        """Todos os módulos que dependem (transitivamente) de algum de start."""
        rev: dict[str, set[str]] = {}
        for m in self.modules.values():
            for d in m.deps:
                rev.setdefault(d, set()).add(m.id)
        out: set[str] = set()
        stack = list(start)
        while stack:
            x = stack.pop()
            for y in rev.get(x, ()):
                if y not in out:
                    out.add(y)
                    stack.append(y)
        return out

    # ------------------------------------------------------------ caminhos
    def expand(self, pattern: str, mid: str | None = None, repo: Path | None = None) -> list[str]:
        """$BO_REPO/$BO_DATA/$BO_TMP/<ID> e {index_set} -> padrões concretos (glob * preservado)."""
        s = pattern.replace("$BO_REPO", str(repo or core.bo_repo())).replace("$BO_DATA", str(core.bo_data()))
        if mid:
            s = s.replace("$BO_TMP", str(core.bo_tmp(mid))).replace("<ID>", mid)
        keys = re.findall(r"\{([a-z_]+)\}", s)
        keys = [k for k in dict.fromkeys(keys) if k in self.index_sets]
        if not keys:
            return [s]
        out = []
        for combo in itertools.product(*(self.index_sets[k] for k in keys)):
            t = s
            for k, v in zip(keys, combo):
                t = t.replace("{" + k + "}", v)
            out.append(t)
        return out

    def producers_of(self, path: str) -> set[str]:
        """Produtores (pelo catálogo) de um caminho concreto ou padrão de entrada."""
        out = set()
        for a in self.artifacts:
            for ap in self.expand(a["path"]):
                if overlaps(path, ap):
                    out.add(a["producer"])
        return out

    def consumers_of(self, path: str) -> set[str]:
        out = set()
        for m in self.modules.values():
            for inp in m.inputs:
                for ip in self.expand(inp, m.id):
                    if overlaps(path, ip):
                        out.add(m.id)
        for a in self.artifacts:
            for ap in self.expand(a["path"]):
                if overlaps(path, ap):
                    out.update(a.get("consumers") or [])
        return out


# ---------------------------------------------------------------- casamento

def _parts(p: str) -> list[str]:
    return [x for x in p.split("/") if x]


def matches(path: str, pattern: str) -> bool:
    """path está coberto por pattern? Padrão terminado em / cobre a subárvore; '*' não cruza '/'."""
    pp, qq = _parts(path), _parts(pattern)
    if pattern.endswith("/"):
        return len(pp) >= len(qq) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(pp, qq))
    return len(pp) == len(qq) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(pp, qq))


def overlaps(a: str, b: str) -> bool:
    """Dois padrões se sobrepõem (um cobre o outro ou partes dele)?"""
    pa, pb = _parts(a), _parts(b)
    n = min(len(pa), len(pb))
    if not all(fnmatch.fnmatchcase(x, y) or fnmatch.fnmatchcase(y, x) for x, y in zip(pa[:n], pb[:n])):
        return False
    if len(pa) == len(pb):
        return True
    shorter = a if len(pa) < len(pb) else b
    return shorter.endswith("/")


# ---------------------------------------------------------------- carga

def load(repo: Path | None = None, prefer_snapshot: bool = False) -> Catalog:
    """Lê o modulos.json do plano; sem ele, o retrato modules/owners.json do repositório."""
    repo = Path(repo or core.bo_repo())
    src = core.modules_json()
    snap = repo / OWNERS_REL
    if not prefer_snapshot and src.exists():
        return Catalog(core.read_json(src), src)
    if snap.exists():
        return Catalog(core.read_json(snap), snap)
    raise BoError(f"nem {src} nem {snap} existem; defina BO_MODULES", code=2)


def is_file_input(inp: str) -> bool:
    """Entrada que é caminho ($BO_REPO, $BO_DATA ou absoluto). 'ext:...' é referência externa, não arquivo."""
    return inp.startswith("$BO_") or inp.startswith("/")


def _mask(obj):
    """O retrato vai para o git (repositório público no futuro): valores em dinheiro do plano saem mascarados."""
    from .privacy import RULES
    money = dict(RULES)["money"]
    if isinstance(obj, str):
        return money.sub("[valor omitido]", obj)
    if isinstance(obj, list):
        return [_mask(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _mask(v) for k, v in obj.items()}
    return obj


def snapshot(cat: Catalog) -> dict:
    """Retrato versionado do plano: o que as ferramentas precisam para funcionar sem o plano."""
    mods = []
    for m in cat.raw.get("modules", []):
        mods.append({k: m.get(k) for k in ("stable_id", "wave", "branch", "worktree", "needs_cloud", "lock",
                                            "deps", "inputs", "outputs", "owns", "gates", "contracts")})
    art = cat.raw.get("artifact_catalog") or {}
    return {
        "schema": "bo.owners/1",
        "source": str(cat.source),
        "source_sha256": core.sha256_file(cat.source),
        "source_generated_at": cat.raw.get("generated_at"),
        "plan_version": cat.raw.get("plan_version"),
        "env": cat.raw.get("env"),
        "index_sets": cat.raw.get("index_sets"),
        "contracts": cat.raw.get("contracts"),
        "masked": "valores em dinheiro do plano substituídos por [valor omitido] (privacy_lint)",
        "modules": _mask(mods),
        "artifact_catalog": _mask({"artifacts": art.get("artifacts", []),
                                   "external_inputs": art.get("external_inputs", [])}),
    }


# ---------------------------------------------------------------- gates

def strip_comment(cmd: str) -> tuple[str, str]:
    """Separa 'comando  # comentário' respeitando aspas. Devolve (comando, comentário)."""
    q = None
    for i, ch in enumerate(cmd):
        if q:
            if ch == q:
                q = None
            elif ch == "\\" and q == '"':
                continue
        elif ch in "'\"":
            q = ch
        elif ch == "#" and (i == 0 or cmd[i - 1].isspace()):
            return cmd[:i].rstrip(), cmd[i + 1:].strip()
    return cmd.strip(), ""


SELF_GATE_RE = re.compile(r"^make\s+-C\s+\S+\s+gate\s+ID=(\S+)\s*$")


def is_self_gate(cmd: str, mid: str) -> bool:
    m = SELF_GATE_RE.match(strip_comment(cmd)[0])
    return bool(m and m.group(1) == mid)


# ---------------------------------------------------------------- merge

SUBJECT_RE = re.compile(r"^\[([A-Z0-9][A-Z0-9-]*)\]\s")


def module_of_subject(subject: str) -> str | None:
    m = SUBJECT_RE.match(subject)
    return m.group(1) if m else None


def merged_modules(repo: Path, base: str | None = None) -> set[str]:
    """Módulos com pelo menos um commit '[ID] ...' na base."""
    base = base or core.base_branch()
    if not core.ref_exists(repo, base):
        return set()
    out = set()
    for s in core.git(repo, "log", base, "--format=%s").splitlines():
        mid = module_of_subject(s)
        if mid:
            out.add(mid)
    return out
