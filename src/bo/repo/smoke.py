"""Smoke offline dos comandos de gate: cada comando resolve ANTES de rodar.

Para cada comando simples de cada gate: executável no PATH (ou caminho existente e executável),
'python -m bo.*' importável com o mesmo interpretador e a mesma flag -I do gate, pacote de
terceiro na versão do requirements.lock, script existente, alvo de make existente, variáveis
definidas, e ROBOT/Terraform na versão fixada (ontology/patterns/toolchain_pins.json e
universe/pins.json). Nada do gate é executado.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import core
from .catalog import Catalog, is_self_gate, strip_comment

BUILTINS = {"cd", "test", "[", "[[", "echo", "true", "false", "export", "exit", "set", ":", "printf", "!",
            "unset", "wait", "source", "."}
OPERATORS = {"&&", "||", ";", "|", "&", "(", ")", "{", "}", ";;", "|&"}
PY_ARG_FLAGS = {"-X", "-W", "-Q"}
PIN_FILES = {
    "robot": ("ontology/patterns/toolchain_pins.json", "ONTPAT"),
    "terraform": ("universe/pins.json", "PINS"),
}
PIN_KEYS = {"robot": ("robot", "ROBOT"), "terraform": ("terraform", "terraform_version", "terraform_core")}
VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


@dataclass
class Item:
    gate: str
    command: str
    ok: bool
    detail: str

    def line(self) -> str:
        if self.ok:
            return f"  OK   {self.command[:100]} ({self.detail})"
        return f"  FAIL {self.command[:100]}\n       -> {self.detail}"


@dataclass
class Report:
    module: str
    items: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(i.ok for i in self.items)


def split_simple(cmd: str) -> list[list[str]]:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    toks = list(lex)
    out, cur = [], []
    for t in toks:
        if t in OPERATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        out.append(cur)
    return out


def expand(tok: str, env: dict) -> str:
    def rep(m):
        name = m.group(1) or m.group(2)
        return env.get(name, m.group(0))
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)", rep, tok)


def lock_pins(repo: Path) -> dict[str, str]:
    p = Path(repo) / "requirements.lock"
    pins = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
            if m:
                pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def tool_pin(tool: str, repo: Path) -> tuple[str | None, str]:
    rel, producer = PIN_FILES[tool]
    p = Path(repo) / rel
    if not p.exists():
        return None, f"{tool} sem versão fixada: {rel} ausente (produtor {producer})"
    try:
        d = core.read_json(p)
    except (OSError, ValueError) as e:
        return None, f"{rel} ilegível: {e}"
    cands = [d] + [d.get(k) for k in ("tools", "toolchain") if isinstance(d.get(k), dict)]
    for c in cands:
        for k in PIN_KEYS[tool]:
            v = c.get(k)
            if isinstance(v, dict):
                v = v.get("version")
            if isinstance(v, str) and VERSION_RE.search(v):
                return VERSION_RE.search(v).group(1), f"pin {v} em {rel}"
    return None, f"{tool} sem versão fixada em {rel} (chaves aceitas: {', '.join(PIN_KEYS[tool])})"


def tool_version(tool: str, exe: str, env: dict) -> tuple[str | None, str]:
    args = [exe, "version", "-json"] if tool == "terraform" else [exe, "--version"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"{tool} não respondeu à consulta de versão: {e}"
    out = r.stdout + r.stderr
    if tool == "terraform":
        try:
            return json.loads(r.stdout).get("terraform_version"), "terraform version -json"
        except ValueError:
            pass
    m = VERSION_RE.search(out)
    return (m.group(1) if m else None), (out.strip().splitlines() or ["(sem saída)"])[0][:80]


class Smoker:
    def __init__(self, cat: Catalog, repo: Path, env: dict):
        self.cat, self.repo, self.env = cat, Path(repo), env
        self.pins = lock_pins(repo)
        self._spec_cache: dict[tuple, tuple] = {}

    def owner_of_pkg(self, mod: str) -> str:
        pkg = mod.split(".")[1] if mod.count(".") >= 1 else mod
        for m in self.cat.modules.values():
            for o in m.owns:
                if o.rstrip("/").endswith(f"/src/bo/{pkg}"):
                    return m.id
        return "?"

    def find_spec(self, py: str, flags: list[str], mod: str) -> tuple[bool, str]:
        key = (py, tuple(flags), mod)
        if key in self._spec_cache:
            return self._spec_cache[key]
        code = ("import importlib.util,importlib.metadata as md,sys,json\n"
                f"m={mod!r}\n"
                "try:\n s=importlib.util.find_spec(m)\nexcept Exception as e:\n"
                " print(json.dumps({'ok':False,'err':type(e).__name__+': '+str(e)}));sys.exit(0)\n"
                "top=m.split('.')[0]\nv=None\n"
                "try:\n v=md.version(top)\nexcept Exception:\n pass\n"
                "print(json.dumps({'ok':s is not None,'origin':getattr(s,'origin',None),'version':v}))")
        try:
            r = subprocess.run([py, *flags, "-B", "-c", code], capture_output=True, text=True, timeout=120,
                               env=self.env, cwd=self.env.get("BO_TMP") or None)
            res = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"ok": False, "err": r.stderr}
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            res = {"ok": False, "err": str(e)}
        if not res.get("ok"):
            if mod.startswith("bo."):
                pth_hint = ""
                if not (Path(self.env.get("BO_REPO", "")) / "src" / "bo").is_dir():
                    pth_hint = f"; {self.env.get('BO_REPO')}/src/bo não existe"
                out = (False, f"módulo {mod} não importável com '{py} {' '.join(flags)}' "
                              f"(dono do pacote: {self.owner_of_pkg(mod)}; ainda não mergeado?{pth_hint}). "
                              f"Se bo.repo também falha, rode 'make -C $BO_REPO bootstrap'. {res.get('err', '')[:120]}")
            else:
                out = (False, f"módulo {mod} não instalado em {py} ({res.get('err', '')[:120]})")
        else:
            top = mod.split(".")[0].lower().replace("_", "-")
            pin = self.pins.get(top)
            if pin and res.get("version") and res["version"] != pin:
                out = (False, f"{top} {res['version']} instalado, mas requirements.lock fixa {pin}")
            else:
                out = (True, f"{mod} resolve" + (f" ({top}=={res['version']}, fixado)" if pin else ""))
        self._spec_cache[key] = out
        return out

    def check_python(self, words: list[str]) -> tuple[bool, str]:
        py = shutil.which(words[0], path=self.env.get("PATH"))
        if not py:
            return False, f"interpretador {words[0]} não está no PATH"
        flags, i = [], 1
        while i < len(words):
            w = words[i]
            if w == "-m":
                if i + 1 >= len(words):
                    return False, "-m sem módulo"
                return self.find_spec(py, flags, words[i + 1])
            if w == "-c":
                return True, "código inline"
            if w in PY_ARG_FLAGS:
                flags += [w, words[i + 1]] if i + 1 < len(words) else [w]
                i += 2
                continue
            if w.startswith("-"):
                flags.append(w)
                i += 1
                continue
            p = Path(w)
            if not p.is_file():
                return False, f"script não existe: {w}"
            return True, f"script {p.name} existe"
        return True, "interpretador interativo"

    def check_make(self, words: list[str]) -> tuple[bool, str]:
        d, targets, i = Path("."), [], 1
        while i < len(words):
            w = words[i]
            if w == "-C" and i + 1 < len(words):
                d = Path(words[i + 1])
                i += 2
                continue
            if w.startswith("-") or "=" in w:
                i += 1
                continue
            targets.append(w)
            i += 1
        mk = next((d / n for n in ("GNUmakefile", "makefile", "Makefile") if (d / n).is_file()), None)
        if mk is None:
            return False, f"Makefile não existe em {d}"
        text = mk.read_text(encoding="utf-8", errors="replace")
        for t in targets or []:
            if not re.search(rf"^{re.escape(t)}\s*:", text, re.M):
                return False, f"alvo '{t}' não existe em {mk}"
        return True, f"alvo(s) {', '.join(targets) or '(padrão)'} existem"

    def check_versioned(self, tool: str, exe: str) -> tuple[bool, str]:
        pin, why = tool_pin(tool, self.repo)
        if pin is None:
            return False, why
        ver, raw = tool_version(tool, exe, self.env)
        if ver is None:
            return False, f"versão de {tool} ilegível ({raw})"
        if ver != pin and not ver.startswith(pin + "."):
            return False, f"{tool} {ver} no PATH, mas a versão fixada é {pin} ({why})"
        return True, f"{tool} {ver} = {why}"

    def check_simple(self, words: list[str], depth: int = 0) -> tuple[bool, str]:
        words = [expand(w, self.env) for w in words]
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        if not words:
            return True, "só atribuição"
        undefined = [w for w in words if re.search(r"\$\{?[A-Za-z_]", w)]
        if undefined:
            return False, f"variável indefinida em: {undefined[0]}"
        if any("$(" in w or "`" in w for w in words):
            return False, "substituição de comando não é verificável offline"
        cmd = words[0]
        name = Path(cmd).name
        if cmd in BUILTINS:
            return True, "builtin"
        if name in ("bash", "sh", "zsh") and depth < 3:
            if "-c" in words or any(w.startswith("-") and "c" in w[1:] for w in words[1:2]):
                idx = next(i for i, w in enumerate(words) if w == "-c" or (w.startswith("-") and "c" in w[1:]))
                inner = words[idx + 1] if idx + 1 < len(words) else ""
                res = [self.check_simple(s, depth + 1) for s in split_simple(strip_comment(inner)[0])]
                bad = [r for r in res if not r[0]]
                return (not bad), ("; ".join(r[1] for r in bad) if bad else f"{len(res)} comando(s) internos resolvem")
            script = next((w for w in words[1:] if not w.startswith("-")), None)
            if script and not Path(script).is_file():
                return False, f"script não existe: {script}"
        if "/" in cmd:
            p = Path(cmd)
            if not p.is_file():
                return False, f"executável não existe: {cmd}"
            if not os.access(p, os.X_OK):
                return False, f"sem permissão de execução: {cmd}"
            return True, f"{p.name} existe e é executável"
        exe = shutil.which(cmd, path=self.env.get("PATH"))
        if not exe:
            return False, f"'{cmd}' não está no PATH"
        if name in ("python", "python3") or re.match(r"python3(\.\d+)?$", name):
            return self.check_python(words)
        if name == "make":
            return self.check_make(words)
        if name in PIN_FILES:
            return self.check_versioned(name, exe)
        return True, f"{cmd} em {exe}"

    def smoke_module(self, mid: str) -> Report:
        mod = self.cat.get(mid)
        rep = Report(mid)
        if not mod.gates:
            rep.items.append(Item("-", "(sem gates)", False, f"módulo {mid} não tem gates no catálogo"))
        for g in mod.gates:
            cmd, _ = strip_comment(g)
            if not cmd:
                rep.items.append(Item(g, g, False, "gate vazio"))
                continue
            try:
                simples = split_simple(cmd)
            except ValueError as e:
                rep.items.append(Item(g, cmd, False, f"comando mal formado: {e}"))
                continue
            for words in simples:
                ok, why = self.check_simple(words)
                if ok and is_self_gate(cmd, mid):
                    why += "; auto-referência: o runner não reexecuta"
                rep.items.append(Item(g, " ".join(words), ok, why))
        gs = Path(self.repo) / "gates" / f"{mid}.sh"
        rep.items.append(Item("gates/<ID>.sh", f"gates/{mid}.sh", gs.is_file(),
                              "existe" if gs.is_file() else f"gates/{mid}.sh ausente (o make gate exige)"))
        return rep
