"""Gate: python -I -m bo.briefs.allowlists [--file ARQ]

1. Todo papel restrito do bo-lane (glossarist, mapper, hunter, auditor, evaluator) tem lista de leitura com
   $OWNS, $INPUTS e a infraestrutura, e o brief do papel existe.
2. Nenhum modelo da lista nomeia, contém ou está dentro da partição de teste nem de segredo.
3. Para todo módulo do catálogo que cai num papel restrito (padrão do bo-lane, troca declarada ou consumidor de
   um brief), a lista EXPANDIDA pelo próprio bo-lane (bo.repo.lane.allowlist) não alcança a partição de teste
   (exceto módulo que dependa do UNSEAL), não alcança segredo, respeita os proibidos do papel (saídas de outros
   papéis e material de avaliação) e inclui o brief do papel.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import common, content

SECRET_TEMPLATES = ["~/.ssh", "~/.aws", "~/.config/gcloud", "~/.azure", "~/.oci", "~/brevops-keys",
                    "~/.config/bo/allowlist"]


def _rx(tpl: str) -> re.Pattern:
    out = ""
    for part in re.split(r"(\*)", tpl.rstrip("/")):
        out += "[^/]*" if part == "*" else re.escape(part)
    return re.compile("^" + out + "$")


def covers(tpl: str, path: str) -> bool:
    """O modelo tpl (com '*' que não cruza '/') é igual a path, um ancestral dele ou está dentro dele."""
    p, t = path.rstrip("/"), tpl.rstrip("/")
    rx = _rx(t)
    parts = p.split("/")
    for i in range(1, len(parts) + 1):          # tpl casa path ou um ancestral de path
        if rx.match("/".join(parts[:i])):
            return True
    return t.startswith(p + "/")                  # tpl está dentro de path


def literal_checks(doc: dict) -> list[str]:
    from bo.repo import lane
    probs = []
    roles = doc.get("roles")
    if doc.get("schema") != "bo.read_allowlists/1" or not isinstance(roles, dict):
        return ["read_allowlists.json fora do formato (schema bo.read_allowlists/1 com objeto roles)"]
    for role in sorted(lane.RESTRICTED):
        r = roles.get(role)
        if not isinstance(r, dict) or not r.get("read"):
            probs.append(f"papel {role} sem lista de leitura")
            continue
        read = r["read"]
        for need in ["$OWNS", "$INPUTS"] + content.INFRA:
            if need not in read:
                probs.append(f"{role}: falta {need} na lista")
        brief = common.repo() / r.get("brief", "")
        if not r.get("brief") or not brief.is_file():
            probs.append(f"{role}: brief {r.get('brief')!r} não existe")
        for tpl in read:
            if tpl not in ("$OWNS", "$INPUTS") and not re.match(r"^\$(WT|BO_DATA)/\S+$", tpl):
                probs.append(f"{role}: modelo {tpl!r} não é $OWNS, $INPUTS, $WT/... nem $BO_DATA/...")
            for tp in content.TEST_PARTITION + SECRET_TEMPLATES:
                if covers(tpl, tp):
                    probs.append(f"{role}: {tpl} alcança {tp}")
            if tpl.rstrip("/") in ("$WT", "$BO_DATA", "$BO_DATA/SPLIT"):
                probs.append(f"{role}: {tpl} libera a árvore inteira")
    extra = set(roles) - set(lane.ROLES)
    if extra:
        probs.append(f"papéis desconhecidos do bo-lane: {sorted(extra)}")
    for tp in content.TEST_PARTITION:
        if tp not in (doc.get("test_partition") or []):
            probs.append(f"test_partition não declara {tp}")
    return probs


def _portable(p: Path, wt: Path) -> str:
    from bo.repo import core
    s = str(p)
    for base, name in ((wt, "$WT"), (core.bo_data(), "$BO_DATA")):
        b = str(base)
        if s == b or s.startswith(b + "/"):
            return name + s[len(b):]
    return s


def module_roles(cat) -> dict:
    """Módulo -> papel restrito com que ele roda (padrão do bo-lane, troca declarada ou brief que consome)."""
    from bo.repo import lane
    by_brief = {f"$BO_REPO/briefs/{f}": r for r, f in common.BRIEF_FILES.items()}
    out = {}
    for mid, m in cat.modules.items():
        role = content.LAUNCH_ROLE_OVERRIDE.get(mid) or lane.norm_role(None, mid)
        consumed = {by_brief[i] for i in m.inputs if i in by_brief}
        if mid in content.EVALUATOR_MODULES:
            role = "evaluator"
        if role in lane.RESTRICTED or consumed:
            out[mid] = {"role": role, "consumes": sorted(consumed)}
    return out


def expansion_checks(cat) -> tuple[list[str], dict]:
    from bo.repo import core, lane
    probs, seen = [], {}
    unseal_dependents = cat.reverse_closure({"UNSEAL"}) if "UNSEAL" in cat.modules else set()
    data = core.bo_data()
    test_paths = [Path(t.replace("$BO_DATA", str(data))) for t in content.TEST_PARTITION]
    secrets = list(lane.SECRETS) + lane.sealed_paths()
    for mid, info in sorted(module_roles(cat).items()):
        role = info["role"]
        mod = cat.get(mid)
        if info["consumes"] and info["consumes"] != [role]:
            probs.append(f"{mid}: roda como {role}, mas consome o brief de {info['consumes']}")
        if role not in lane.RESTRICTED:
            probs.append(f"{mid}: consome brief de papel restrito e roda como {role} (lance com --role)")
            continue
        wt = Path(mod.worktree)
        allowed, src = lane.allowlist(cat, mod, role, wt)
        if src != "briefs/read_allowlists.json":
            probs.append(f"{mid}: o bo-lane não usou briefs/read_allowlists.json ({src})")
        own_roots = [Path(x.rstrip("/")) for o in mod.owns for x in cat.expand(o, mid, repo=wt)] + [data / mid]
        binds = bool(info["consumes"]) or mid in content.LAUNCH_ROLE_OVERRIDE or mid in content.EVALUATOR_MODULES
        for a in allowed:
            a = Path(a)
            for t in test_paths:
                if (lane.is_within(a, t) or lane.is_within(t, a)) and mid not in unseal_dependents:
                    probs.append(f"{mid} ({role}): {_portable(a, wt)} alcança a partição de teste")
            for s in secrets:
                if lane.is_within(a, s) or lane.is_within(s, a):
                    probs.append(f"{mid} ({role}): {a} alcança segredo {s}")
            if a in (wt, data, Path.home()):
                probs.append(f"{mid} ({role}): {_portable(a, wt)} libera a árvore inteira")
            if not binds or any(lane.is_within(a, o) for o in own_roots):
                continue   # a separação de papéis do brief vale para quem o segue; o owns é do módulo
            port = _portable(a, wt)
            for rx in content.ROLE_FORBID[role]:
                if re.search(rx, port):
                    probs.append(f"{mid} ({role}): {port} é proibido ao papel ({rx[:40]}...)")
        brief = wt / "briefs" / common.BRIEF_FILES[role]
        if binds and not any(lane.is_within(brief, Path(a)) for a in allowed):
            probs.append(f"{mid} ({role}): o próprio brief {common.BRIEF_FILES[role]} não está na lista")
        seen[mid] = {"role": role, "roots": len(allowed)}
    roles_seen = {v["role"] for v in seen.values()}
    for role in common.ROLES:
        if role not in roles_seen:
            probs.append(f"nenhum módulo do catálogo exercitou o papel {role}")
    return probs, seen


def main(argv=None) -> int:
    from bo.repo import catalog
    ap = argparse.ArgumentParser(prog="bo.briefs.allowlists")
    ap.add_argument("--file", default=None, help="outro read_allowlists.json (só checagens literais)")
    a = ap.parse_args(argv)
    path = Path(a.file) if a.file else common.briefs_dir() / "read_allowlists.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        common.emit(f"[{common.now()}] bo.briefs.allowlists: {path} ilegível ({e}) -> FAIL")
        return 1
    probs = literal_checks(doc)
    seen = {}
    if a.file is None:
        p2, seen = expansion_checks(catalog.load())
        probs += p2
        by_role = {}
        for v in seen.values():
            by_role[v["role"]] = by_role.get(v["role"], 0) + 1
        common.write_report("allowlists_report", {"gate": "bo.briefs.allowlists", "ok": not probs,
                                                  "problems": probs, "modules_by_role": by_role, "modules": seen})
        common.emit("  módulos conferidos por papel: " + ", ".join(f"{k} {v}" for k, v in sorted(by_role.items())))
    for p in probs:
        common.emit(f"    - {p}")
    common.emit(f"[{common.now()}] bo.briefs.allowlists: {len(probs)} problema(s) -> {'PASS' if not probs else 'FAIL'}")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
