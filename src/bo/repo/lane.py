"""bo-lane: uma worktree por módulo, com sandbox de leitura por papel (§7.2, §9.1).

  bo-lane new ID [--role PAPEL] [--base bo/base]   worktree + branch + $BO_DATA/ID + $BO_TMP + sandbox
  bo-lane check-sandbox ID                         prova que o papel não lê fora do pacote
  bo-lane exec ID -- CMD ...                       roda CMD sob o perfil sandbox-exec da lane
  bo-lane env ID                                   linhas 'export' (BO_ID, BO_REPO, BO_TMP, ...)
  bo-lane refresh ID                               recalcula o sandbox (caminhos criados depois)
  bo-lane rm ID [--force]                          remove worktree e tmp; a branch só some se nunca teve commit [ID]
  bo-lane list | roles

O sandbox é escrito em <worktree>/.claude/settings.json: permissions.deny com o complemento da
lista de leitura (para a ferramenta Read) e sandbox.filesystem.denyRead=[HOME] com allowRead =
lista do papel (para o Bash). O mesmo conjunto vira <worktree>/.bo/sandbox.sb (sandbox-exec), que o
check-sandbox usa para provar a negação de verdade, lendo arquivos-sonda dentro e fora do pacote.
Lista por papel: $BO_REPO/briefs/read_allowlists.json (BRIEFS) quando existir; antes, a padrão daqui.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import catalog, core
from .core import BoError

HOME = Path.home()
ROLE_ALIASES = {"glossarista": "glossarist", "mapeador": "mapper", "cacador": "hunter", "caçador": "hunter",
                "auditor": "auditor", "avaliador": "evaluator", "extrator": "extractor", "construtor": "builder",
                "validador": "evaluator"}
ROLES = {
    "builder": "infra/biblioteca: lê o repositório e o BO_DATA inteiros, menos segredos e teste selado",
    "extractor": "extração de fontes: como builder",
    "glossarist": "glossarista: só o pacote (entradas, posse, código, contratos)",
    "mapper": "mapeador: só o pacote fechado (entradas com a projeção de treino, posse, código, contratos)",
    "hunter": "caçador de NONE/erros: só o pacote",
    "auditor": "auditor: só o pacote",
    "evaluator": "avaliador: só o pacote",
}
RESTRICTED = {"glossarist", "mapper", "hunter", "auditor", "evaluator"}
ROLE_BY_PATTERN = [(r"^(MAP-|PILOT-.*-MAP$)", "mapper"), (r"^NONEHUNT-", "hunter"),
                   (r"^(GLOSSARY-AUDIT|GOLD-AUDIT)$", "auditor"),
                   (r"^(GLOSSARY-(?!AUDIT|FREEZE)|PILOT-.*-GLOSS$)", "glossarist")]
WT_INFRA = ["src/", "tools/", "contracts/", "modules/", "freeze/", "Makefile", "pyproject.toml",
            "requirements.lock", "CONVENTIONS.html", ".bo/", ".claude/", ".git"]
TOOLCHAIN = [HOME / ".local/share/mise", HOME / ".local/bin", HOME / ".gitconfig", HOME / ".config/git",
             HOME / ".claude/skills/unlazy", HOME / ".config/bo/gcp_projects.txt",
             HOME / ".config/bo/private_terms.txt", HOME / ".config/mise", HOME / ".local/state/mise",
             HOME / ".zshrc", HOME / ".zprofile", HOME / ".zshenv", HOME / ".bash_profile", HOME / ".bashrc",
             HOME / ".profile"]
SECRETS = [HOME / ".ssh", HOME / ".aws", HOME / ".config/gcloud", HOME / ".azure", HOME / ".oci",
           HOME / "brevops-keys", HOME / ".config/bo/allowlist", HOME / ".netrc", HOME / ".kube",
           HOME / ".docker/config.json", HOME / ".gnupg"]
SPECIAL = re.compile(r"[()\[\]{}*?!#\\]")


def PROBE_ROOT() -> Path:  # noqa: N802 - diretório de sondas, existe antes do cálculo do complemento
    return core.bo_tmp("_sandbox_probe")


def norm_role(r: str | None, mid: str) -> str:
    if r:
        r = ROLE_ALIASES.get(r.lower(), r.lower())
        if r not in ROLES:
            raise BoError(f"papel desconhecido: {r} (papéis: {', '.join(ROLES)})", code=2)
        return r
    for rx, role in ROLE_BY_PATTERN:
        if re.search(rx, mid):
            return role
    return "builder"


def sealed_paths() -> list[Path]:
    d = core.bo_data()
    return [d / "SPLIT" / "sealed", d / "SPLIT" / "holdout_units.json.enc"]


def plan_paths(mid: str) -> list[Path]:
    plan = Path(core.DEFAULT_PLAN_DIR)
    return [plan / "PLANO_BREVOPS_ONTOLOGY.html", core.modules_json(), plan / "execucao" / "briefs" / f"{mid}.txt",
            plan / "execucao" / "gates" / f"{mid}.md"]


# ---------------------------------------------------------------- lista de leitura

def allowlist(cat: catalog.Catalog, mod: catalog.Module, role: str, wt: Path) -> tuple[list[Path], str]:
    data, tmp = core.bo_data() / mod.id, core.bo_tmp(mod.id)
    common = [data, tmp, core.bo_data() / "locks", core.git_common_dir(core.bo_repo())] + TOOLCHAIN + plan_paths(mod.id)
    src = "padrão do REPO"
    ra = core.read_json(Path(core.bo_repo()) / "briefs" / "read_allowlists.json")
    if ra is not None:
        roles = ra.get("roles") if isinstance(ra, dict) else None
        if not isinstance(roles, dict):
            raise BoError("briefs/read_allowlists.json sem objeto 'roles' (formato em CONVENTIONS.html)")
        if role in roles:
            src = "briefs/read_allowlists.json"
            out = [Path(p) for p in common]
            for tpl in roles[role].get("read", []):
                out.extend(expand_template(cat, mod, tpl, wt))
            return dedupe(out), src
        src = f"padrão do REPO (papel {role} ausente de briefs/read_allowlists.json)"
    if role not in RESTRICTED:
        out = [wt, core.bo_data(), Path(core.DEFAULT_PLAN_DIR)] + common
        for inp in mod.inputs:
            if inp.startswith("/"):
                out.append(Path(inp))
        return dedupe(out), src
    out = [wt / x for x in WT_INFRA] + list(common)
    for tpl in ("$OWNS", "$INPUTS"):
        out.extend(expand_template(cat, mod, tpl, wt))
    return dedupe(out), src


def expand_template(cat, mod, tpl: str, wt: Path) -> list[Path]:
    if tpl == "$OWNS":
        pats = mod.owns
    elif tpl == "$INPUTS":
        pats = [i for i in mod.inputs if catalog.is_file_input(i)]
    else:
        pats = [tpl.replace("$WT", "$BO_REPO")]
    out = []
    for p in pats:
        for x in cat.expand(p, mod.id, repo=wt):
            out.extend(glob_dirs(x))
    return out


def glob_dirs(pattern: str) -> list[Path]:
    """Padrão com '*' vira os caminhos existentes; sem '*', o próprio caminho (mesmo que ainda não exista)."""
    if "*" not in pattern:
        return [Path(pattern.rstrip("/") or "/")]
    import glob as g
    return [Path(h) for h in sorted(g.glob(pattern.rstrip("/")))]


def dedupe(paths: list[Path]) -> list[Path]:
    out = []
    for p in sorted({Path(os.path.abspath(p)) for p in paths}, key=lambda x: (len(x.parts), str(x))):
        if any(is_within(p, q) for q in out):
            continue
        out.append(p)
    return sorted(out)


def is_within(p: Path, q: Path) -> bool:
    try:
        Path(p).relative_to(q)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- regras

def complement(allowed: list[Path], root: Path = HOME) -> list[Path]:
    """Tudo sob root que não está nem dentro nem a caminho de um caminho permitido."""
    deny = []

    def walk(d: Path):
        try:
            kids = sorted(d.iterdir())
        except OSError:
            return
        for k in kids:
            if any(is_within(k, a) for a in allowed):
                continue
            if any(is_within(a, k) for a in allowed) and k.is_dir() and not k.is_symlink():
                walk(k)
            else:
                deny.append(k)
    if any(is_within(a, root) for a in allowed):
        walk(root)
    else:
        deny.append(root)
    return deny


def rule_path(p: Path) -> str:
    return "/" + SPECIAL.sub("?", str(p))


def read_rule(p: Path, is_dir: bool | None = None) -> str:
    if is_dir is None:
        is_dir = p.is_dir() and not p.is_symlink()
    return f"Read({rule_path(p)}/**)" if is_dir else f"Read({rule_path(p)})"


def settings_for(allowed: list[Path], deny: list[Path], writable: list[Path], wt: Path) -> dict:
    secrets = SECRETS + sealed_paths()
    deny_rules = [read_rule(p) for p in deny]
    for s in secrets:
        deny_rules += [f"Read({rule_path(s)})", f"Read({rule_path(s)}/**)"]
    return {
        "$comment": "gerado por tools/bo-lane (REPO); não editar à mão: refaça com bo-lane new",
        "permissions": {
            "allow": sorted({r for p in allowed for r in (f"Read({rule_path(p)})", f"Read({rule_path(p)}/**)")}),
            "deny": sorted(set(deny_rules)),
            "additionalDirectories": [str(p) for p in allowed if not is_within(p, wt) and p.is_dir()],
        },
        "sandbox": {
            "enabled": True,
            "allowUnsandboxedCommands": False,
            "filesystem": {
                "denyRead": [str(HOME)] + [str(s) for s in secrets],
                "allowRead": [str(p) for p in allowed],
                "allowWrite": [str(p) for p in writable],
            },
        },
    }


def sbpl(allowed: list[Path], secrets: list[Path]) -> str:
    def q(p):
        return json.dumps(str(p))
    lines = ["(version 1)", "(allow default)", f"(deny file-read* (subpath {q(HOME)}))"]
    for p in allowed:
        lines.append(f"(allow file-read* (subpath {q(p)}))")
    # ancestrais dos caminhos permitidos: só o nó do diretório (getcwd do bash/git precisa); o conteúdo
    # dos irmãos continua negado pela regra da HOME
    anc = sorted({str(x) for p in allowed for x in Path(p).parents if is_within(x, HOME)})
    for x in anc:
        lines.append(f"(allow file-read* (literal {q(x)}))")
    lines.append("(allow file-read-metadata)")
    for s in secrets:
        lines.append(f"(deny file-read* (subpath {q(s)}))")
    return "\n".join(lines) + "\n"


def rule_regex(rule: str) -> re.Pattern | None:
    m = re.match(r"^Read\((.*)\)$", rule)
    if not m:
        return None
    pat = m.group(1)
    if pat.startswith("//"):
        pat = pat[1:]
    elif pat.startswith("~/"):
        pat = str(HOME) + pat[1:]
    else:
        return None
    rx, i = "", 0
    while i < len(pat):
        if pat.startswith("/**", i) and i + 3 == len(pat):
            rx += "(/.*)?"
            i += 3
        elif pat.startswith("**", i):
            rx += ".*"
            i += 2
        elif pat[i] == "*":
            rx += "[^/]*"
            i += 1
        elif pat[i] == "?":
            rx += "[^/]"
            i += 1
        else:
            rx += re.escape(pat[i])
            i += 1
    return re.compile("^" + rx + "$")


def simulate(settings: dict, path: Path, wt: Path) -> bool:
    """True = a ferramenta Read leria (nega se alguma regra deny casa; deny vence allow)."""
    s = str(Path(os.path.abspath(path)))
    for r in settings["permissions"]["deny"]:
        rx = rule_regex(r)
        if rx and rx.match(s):
            return False
    if is_within(Path(s), wt):
        return True
    for r in settings["permissions"]["allow"]:
        rx = rule_regex(r)
        if rx and rx.match(s):
            return True
    return False


# ---------------------------------------------------------------- comandos

def lane_info(mid: str) -> tuple[catalog.Catalog, catalog.Module, Path]:
    cat = catalog.load()
    mod = cat.get(mid, allow_synthetic=True)
    return cat, mod, Path(mod.worktree)


def env_lines(mod: catalog.Module, wt: Path, role: str) -> str:
    tmp = core.bo_tmp(mod.id)
    vals = {"BO_ID": mod.id, "BO_ROLE": role, "BO_REPO": str(wt), "BO_DATA": str(core.bo_data()),
            "BO_TMP": str(tmp), "TMPDIR": str(tmp), "BO_MODULES": str(core.modules_json()),
            "BO_BASE": core.base_branch()}
    return "".join(f"export {k}={json.dumps(v)}\n" for k, v in vals.items())


def write_sandbox(cat, mod, wt: Path, role: str) -> dict:
    allowed, src = allowlist(cat, mod, role, wt)
    deny = complement(allowed)
    writable = [wt, core.bo_data() / mod.id, core.bo_tmp(mod.id), core.bo_data() / "locks",
                core.git_common_dir(core.bo_repo()), plan_paths(mod.id)[3]]
    settings = settings_for(allowed, deny, writable, wt)
    (wt / ".claude").mkdir(exist_ok=True)
    core.write_json(wt / ".claude" / "settings.json", settings)
    (wt / ".bo").mkdir(exist_ok=True)
    (wt / ".bo" / "sandbox.sb").write_text(sbpl(allowed, SECRETS + sealed_paths()), encoding="utf-8")
    (wt / ".bo" / "lane.env").write_text(env_lines(mod, wt, role), encoding="utf-8")
    info = {"id": mod.id, "role": role, "role_source": src, "branch": mod.branch, "worktree": str(wt),
            "base": core.base_branch(), "known_module": mod.known, "created_at": core.now(),
            "allowlist": [str(p) for p in allowed], "deny_rules": len(settings["permissions"]["deny"])}
    core.write_json(wt / ".bo" / "lane.json", info)
    return info


def lane_is_empty(repo: Path, wt: Path, mod: catalog.Module, base: str) -> bool:
    """Sem commit fora da base e sem mudança rastreada: recriar não perde nada (ex. DUMMY de um gate interrompido)."""
    if not (wt / ".git").exists():
        return False
    if core.ref_exists(repo, "refs/heads/" + mod.branch) and \
            core.git(repo, "rev-list", f"{base}..{mod.branch}").split():
        return False
    return core.git(wt, "status", "--porcelain").strip() == ""


def cmd_new(mid: str, role: str | None, base: str | None) -> int:
    cat, mod, wt = lane_info(mid)
    role = norm_role(role, mid)
    repo = core.bo_repo()
    base = base or core.base_branch()
    if wt.exists():
        if not lane_is_empty(repo, wt, mod, base):
            raise BoError(f"worktree já existe e tem trabalho: {wt} (commit, ou bo-lane rm {mid} --force)")
        core.emit(f"  lane {mid} já existia sem trabalho (sem commit novo, limpa): recriada")
        cmd_rm(mid, force=False)
    if not core.ref_exists(repo, base):
        raise BoError(f"base {base} não existe em {repo}")
    if core.ref_exists(repo, "refs/heads/" + mod.branch):
        core.git(repo, "worktree", "add", "-q", str(wt), mod.branch)
        how = f"branch existente {mod.branch}"
    else:
        core.git(repo, "worktree", "add", "-q", "-b", mod.branch, str(wt), base)
        how = f"branch nova {mod.branch} a partir de {base}"
    for d in (core.bo_data() / mid, core.bo_tmp(mid), PROBE_ROOT()):
        d.mkdir(parents=True, exist_ok=True)
    info = write_sandbox(cat, mod, wt, role)
    core.emit(f"[{core.now()}] lane {mid}: {wt} ({how})")
    core.emit(f"  papel {role} ({info['role_source']}); {len(info['allowlist'])} raiz(es) de leitura; "
              f"{info['deny_rules']} regra(s) deny")
    core.emit(f"  BO_TMP={core.bo_tmp(mid)}  ->  source {wt}/.bo/lane.env")
    if not mod.known:
        core.emit(f"  nota: {mid} não está no catálogo; posse padrão C00 (src/bo/{mid.lower()}/, tests/, results/, ...)")
    return 0


def plant(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def denied_paths(settings: dict) -> list[Path]:
    out = []
    for r in settings["permissions"]["deny"]:
        m = re.match(r"^Read\(/(/.*?)(/\*\*)?\)$", r)
        if m and "?" not in m.group(1):
            out.append(Path(m.group(1)))
    return sorted(set(out))


def cmd_check(mid: str) -> int:
    cat, mod, wt = lane_info(mid)
    sp = wt / ".claude" / "settings.json"
    info = core.read_json(wt / ".bo" / "lane.json")
    if not wt.is_dir() or info is None or not sp.exists():
        raise BoError(f"lane {mid} não existe ou não tem sandbox (bo-lane new {mid} --role ...)")
    try:
        settings = json.loads(sp.read_text(encoding="utf-8"))
    except ValueError as e:
        raise BoError(f"{sp} não é JSON válido: {e}")
    role = info["role"]
    results = []

    def expect(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    fs = settings.get("sandbox", {}).get("filesystem", {})
    expect("sandbox do Bash ligado e sem escape", settings.get("sandbox", {}).get("enabled") is True and
           settings["sandbox"].get("allowUnsandboxedCommands") is False)
    expect("denyRead cobre a HOME inteira", str(HOME) in fs.get("denyRead", []))
    expect("allowRead = lista do papel", sorted(fs.get("allowRead", [])) == sorted(info["allowlist"]))
    expect("segredos e teste selado negados explicitamente",
           all(str(s) in fs.get("denyRead", []) for s in SECRETS + sealed_paths()))
    # sondas dentro do pacote
    inside = [plant(core.bo_data() / mid / ".probe_inside.txt", "dentro\n"),
              plant(core.bo_tmp(mid) / ".probe_inside.txt", "dentro\n")]
    for p in (wt / "src" / "bo" / "repo" / "core.py", core.modules_json()):
        if p.exists():
            inside.append(p)
    for inp in mod.inputs:
        hits = [h for x in cat.expand(inp, mid, repo=wt) for h in glob_dirs(x) if h.exists()]
        if hits:
            inside.append(hits[0])
            break
    # sondas fora: caminhos que já existiam quando a lane foi criada, um de cada região
    denied = [p for p in denied_paths(settings) if p.exists()]
    regions = {"outro módulo em BO_DATA": core.bo_data(), "worktree fora do pacote": wt,
               "outra lane": core.lanes_dir(), "repositório principal": Path(core.DEFAULT_BO_REPO),
               "plano (gates de outro módulo)": Path(core.DEFAULT_PLAN_DIR) / "execucao" / "gates"}
    outside, planted = [], []
    for label, root in regions.items():
        cand = [p for p in denied if is_within(p, root) and not (label == "outra lane" and is_within(p, wt))]
        cand.sort(key=lambda x: (not x.is_dir(), x.name.startswith("."), str(x)))
        if not cand:
            if role in RESTRICTED and label in ("outro módulo em BO_DATA", "worktree fora do pacote"):
                expect(f"existe sonda para '{label}'", False, f"nenhum caminho negado sob {root}")
            continue
        p = cand[0]
        if p.is_dir():
            p = plant(p / f".probe_fora_{mid}.txt", "fora\n")
            planted.append(p)
        outside.append((label, p))
    secrets = [p for p in (HOME / ".ssh", HOME / ".aws", HOME / ".config/gcloud", HOME / ".azure") if p.exists()]
    if role in RESTRICTED:
        expect("papel restrito tem sondas fora do pacote", len(outside) >= 3, f"{len(outside)} sonda(s)")
    try:
        for p in inside:
            expect(f"Read permite {p}", simulate(settings, p, wt))
        for label, p in outside:
            expect(f"Read nega ({label}) {p}", not simulate(settings, p, wt))
        for p in secrets + sealed_paths():
            expect(f"Read nega segredo/selado {p}", not simulate(settings, p, wt))
        sb = wt / ".bo" / "sandbox.sb"
        exe = shutil.which("sandbox-exec")
        expect("sandbox-exec disponível para a prova real", exe is not None)
        if exe:
            def can_read(p: Path) -> bool:
                args = ["/bin/ls", str(p)] if p.is_dir() else ["/bin/cat", str(p)]
                return subprocess.run([exe, "-f", str(sb), *args], capture_output=True).returncode == 0
            for p in inside:
                expect(f"sandbox-exec lê {p}", can_read(p))
            for label, p in outside:
                expect(f"sandbox-exec nega ({label}) {p}", not can_read(p))
            for p in secrets:
                expect(f"sandbox-exec nega segredo {p}", not can_read(p))
            new_sib = plant(PROBE_ROOT() / mid / "criado_depois.txt", "fora\n")
            planted.append(new_sib)
            expect("sandbox-exec nega caminho criado depois da lane", not can_read(new_sib))
            env = dict(os.environ, BO_REPO=str(wt))
            r = subprocess.run([exe, "-f", str(sb), sys.executable, "-I", "-B", "-c", "import bo.repo.core"],
                               capture_output=True, env=env, cwd=str(wt))
            expect("dentro do sandbox, python -I importa bo.repo da worktree", r.returncode == 0,
                   r.stderr.decode(errors="replace")[-200:])
            r = subprocess.run([exe, "-f", str(sb), "bash", "-lc", "cd \"$BO_REPO\" && python -I tools/gate_smoke.py "
                                "--help >/dev/null 2>&1; command -v python >/dev/null && git status --porcelain >/dev/null"],
                               capture_output=True, env=env, cwd=str(wt))
            expect("dentro do sandbox, bash -lc acha python e o git funciona na worktree", r.returncode == 0,
                   r.stderr.decode(errors="replace")[-200:])
    finally:
        for p in planted + inside[:2]:
            p.unlink(missing_ok=True)
        shutil.rmtree(PROBE_ROOT() / mid, ignore_errors=True)
    bad = [r for r in results if not r[1]]
    core.emit(f"[{core.now()}] check-sandbox {mid} (papel {role}): {len(results) - len(bad)}/{len(results)}")
    for name, ok, detail in results:
        core.emit(f"  [{'ok' if ok else 'FALHOU'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    gap = [k for k in sorted(core.bo_data().iterdir()) if k not in denied and not any(
        is_within(k, Path(a)) or is_within(Path(a), k) for a in info["allowlist"])] if role in RESTRICTED else []
    if gap:
        core.emit(f"  aviso: {len(gap)} caminho(s) em BO_DATA criados depois da lane não estão nas regras da "
                  f"ferramenta Read (o Bash continua negado); rode bo-lane refresh {mid}")
    return 0 if not bad else 1


def cmd_refresh(mid: str) -> int:
    cat, mod, wt = lane_info(mid)
    info = core.read_json(wt / ".bo" / "lane.json")
    if info is None:
        raise BoError(f"lane {mid} não existe")
    info2 = write_sandbox(cat, mod, wt, info["role"])
    core.emit(f"lane {mid}: sandbox recalculado ({info2['deny_rules']} regra(s) deny)")
    return 0


def cmd_rm(mid: str, force: bool) -> int:
    cat, mod, wt = lane_info(mid)
    repo = core.bo_repo()
    if wt.exists():
        args = ["worktree", "remove"] + (["--force"] if force else []) + [str(wt)]
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise BoError(f"git worktree remove falhou ({r.stderr.strip()}); commit/limpe ou use --force")
        core.emit(f"  worktree removida: {wt}")
    else:
        core.emit(f"  worktree já não existia: {wt}")
    core.git(repo, "worktree", "prune")
    br = "refs/heads/" + mod.branch
    if core.ref_exists(repo, br):
        ahead = core.git(repo, "rev-list", f"{core.base_branch()}..{mod.branch}").split()
        own = [ln for ln in core.git(repo, "log", mod.branch, "--format=%s").splitlines()
               if catalog.module_of_subject(ln) == mid]
        if not ahead and not own:
            core.git(repo, "branch", "-D", mod.branch)
            core.emit(f"  branch {mod.branch} removida (nunca teve commit [{mid}])")
        else:
            core.emit(f"  branch {mod.branch} mantida ({len(own)} commit(s) [{mid}], {len(ahead)} fora de "
                      f"{core.base_branch()}; commit_lint e ownership_check continuam usando)")
    tmp = core.bo_tmp(mid)
    if tmp.exists():
        shutil.rmtree(tmp)
        core.emit(f"  tmp removido: {tmp}")
    data = core.bo_data() / mid
    if data.is_dir() and not any(data.iterdir()):
        data.rmdir()
        core.emit(f"  {data} vazio removido")
    core.emit(f"[{core.now()}] lane {mid} removida")
    return 0


def cmd_exec(mid: str, argv: list[str]) -> int:
    _, mod, wt = lane_info(mid)
    sb = wt / ".bo" / "sandbox.sb"
    if not sb.exists():
        raise BoError(f"lane {mid} sem perfil {sb}")
    env = dict(os.environ)
    for line in (wt / ".bo" / "lane.env").read_text(encoding="utf-8").splitlines():
        k, _, v = line.removeprefix("export ").partition("=")
        env[k] = json.loads(v)
    return subprocess.run(["sandbox-exec", "-f", str(sb), *argv], env=env, cwd=str(wt)).returncode


def cmd_list() -> int:
    repo = core.bo_repo()
    out = core.git(repo, "worktree", "list", "--porcelain")
    n = 0
    for block in out.strip().split("\n\n"):
        kv = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        wt = Path(kv.get("worktree", ""))
        info = core.read_json(wt / ".bo" / "lane.json") or {}
        core.emit(f"  {wt}  {kv.get('branch', '').removeprefix('refs/heads/')}  "
                  f"{info.get('id', '-')} {info.get('role', '')}")
        n += 1
    core.emit(f"{n} worktree(s)")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    def need_id():
        if not rest or rest[0].startswith("-"):
            raise BoError(f"uso: bo-lane {cmd} ID", code=2)
        return rest[0]

    if cmd == "new":
        mid = need_id()
        role = base = None
        i = 1
        while i < len(rest):
            if rest[i] == "--role" and i + 1 < len(rest):
                role, i = rest[i + 1], i + 2
            elif rest[i] == "--base" and i + 1 < len(rest):
                base, i = rest[i + 1], i + 2
            else:
                raise BoError(f"opção desconhecida: {rest[i]}", code=2)
        return cmd_new(mid, role, base)
    if cmd == "check-sandbox":
        return cmd_check(need_id())
    if cmd == "refresh":
        return cmd_refresh(need_id())
    if cmd == "rm":
        return cmd_rm(need_id(), "--force" in rest)
    if cmd == "env":
        _, mod, wt = lane_info(need_id())
        info = core.read_json(wt / ".bo" / "lane.json") or {}
        sys.stdout.write(env_lines(mod, wt, info.get("role", "builder")))
        return 0
    if cmd == "exec":
        mid = need_id()
        if "--" not in rest:
            raise BoError("uso: bo-lane exec ID -- CMD ...", code=2)
        return cmd_exec(mid, rest[rest.index("--") + 1:])
    if cmd == "list":
        return cmd_list()
    if cmd == "roles":
        for k, v in ROLES.items():
            core.emit(f"  {k:<10} {v}")
        return 0
    raise BoError(f"comando desconhecido: {cmd}", code=2)
