"""Comprovantes de congelamento (C17 freeze_receipt.json), validação no consumo e invalidação.

Caminhos ficam gravados na forma portátil ($BO_REPO/..., $BO_DATA/...) para o mesmo
comprovante valer no repositório principal e em qualquer worktree.
"""

from __future__ import annotations

import glob as _glob
import shutil
import subprocess
from pathlib import Path

from . import core, state as st_mod
from .catalog import Catalog, is_file_input, matches, merged_modules, overlaps
from .core import BoError

RECEIPT_SCHEMA = "bo.freeze_receipt/1"
COORDINATOR = "coordenador"
LEDGER_NAME = "consume_ledger.json"


# ---------------------------------------------------------------- caminhos portáteis

def portable(p: str | Path, repo: Path | None = None) -> str:
    s = str(Path(p))
    r, d = str(Path(repo or core.bo_repo())), str(core.bo_data())
    if s == r or s.startswith(r + "/"):
        return "$BO_REPO" + s[len(r):]
    if s == d or s.startswith(d + "/"):
        return "$BO_DATA" + s[len(d):]
    return s


def resolve(p: str, repo: Path | None = None) -> Path:
    return Path(p.replace("$BO_REPO", str(repo or core.bo_repo())).replace("$BO_DATA", str(core.bo_data())))


def expand_existing(cat: Catalog, pattern: str, mid: str, repo: Path) -> list[Path]:
    out = []
    for pat in cat.expand(pattern, mid, repo):
        trailing = pat.endswith("/")
        for hit in sorted(_glob.glob(pat.rstrip("/") or "/")):
            hp = Path(hit)
            if trailing and not hp.is_dir():
                continue
            out.append(hp)
    return out


def entry(p: Path, repo: Path, **extra) -> dict:
    h = core.hash_path(p)
    e = {"path": portable(p, repo), "kind": h["kind"], "sha256": h["sha256"]}
    if h["kind"] == "dir":
        e["files"] = h["files"]
    e.update(extra)
    return e


# ---------------------------------------------------------------- comprovante

def receipt_digest(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k not in ("digest", "ots")}
    return core.sha256_bytes(core.canonical_json(body).encode())


def receipts_dir(repo: Path) -> Path:
    return Path(repo) / "freeze"


def list_receipts(repo: Path) -> list[Path]:
    d = receipts_dir(repo)
    return sorted(d.glob("*/freeze_receipt.json")) if d.is_dir() else []


def create(cat: Catalog, name: str, paths: list[str], owner: str, repo: Path,
           out: Path | None = None, tag: bool = True, ots: bool = True, note: str = "") -> tuple[Path, dict]:
    if not paths:
        raise BoError("nada para congelar: passe --paths")
    arts, producers = [], set()
    for p in paths:
        ap = resolve(p, repo) if p.startswith("$BO_") else Path(p).resolve()
        if not ap.exists():
            raise BoError(f"artefato a congelar não existe: {p}")
        prods = sorted(cat.producers_of(str(ap)))
        producers.update(prods)
        arts.append(entry(ap, repo, producers=prods))
    closure: list[str] = []
    for pr in sorted(producers):
        for x in [pr] + cat.deps_closure(pr):
            if x not in closure:
                closure.append(x)
    transitive, seen = [], {a["path"] for a in arts}
    for mid in closure:
        if mid not in cat.modules:
            continue
        for inp in filter(is_file_input, cat.modules[mid].inputs):
            for hit in expand_existing(cat, inp, mid, repo):
                pp = portable(hit, repo)
                if pp in seen:
                    continue
                seen.add(pp)
                transitive.append(entry(hit, repo, via=mid))
    head = core.git(repo, "rev-parse", "HEAD").strip() if core.git_ok(repo, "rev-parse", "HEAD") else None
    tag_name = f"bo-freeze-{name}"
    rec = {
        "schema": RECEIPT_SCHEMA, "contract": "C17", "contract_version": "3.0.0",
        "name": name, "owner": owner, "created_at": core.now(), "note": note,
        "git": {"commit": head, "tag": tag_name if tag else None},
        "modules": closure, "artifacts": arts, "transitive_inputs": transitive,
    }
    rec["digest"] = receipt_digest(rec)
    out = Path(out or receipts_dir(repo) / name / "freeze_receipt.json")
    if out.exists():
        raise BoError(f"comprovante já existe: {out} (congelamento é único; emenda = nome novo)")
    rec["ots"] = stamp_ots(rec["digest"], out.parent) if ots else {"status": "DISABLED", "reason": "--no-ots"}
    core.write_json(out, rec)
    if tag and head:
        if core.ref_exists(repo, "refs/tags/" + tag_name):
            raise BoError(f"tag {tag_name} já existe")
        core.git(repo, "tag", "-a", tag_name, "-m", f"congelamento {name}: digest {rec['digest']}", head)
    if owner == COORDINATOR:
        # modules/state.json é do REPO/coordenador: módulo dono do próprio comprovante (ex. SPLIT) não o toca;
        # o comprovante é achado por varredura de freeze/*/ de qualquer jeito.
        s = st_mod.load(repo, cat)
        s["freezes"][name] = {"status": "VALID", "receipt": portable(out, repo), "digest": rec["digest"],
                              "created_at": rec["created_at"], "owner": owner}
        s["events"].append({"at": rec["created_at"], "freeze": name, "status": "VALID", "reason": "congelado"})
        st_mod.save(s, repo)
    return out, rec


def stamp_ots(digest: str, outdir: Path) -> dict:
    """Carimbo OpenTimestamps do digest. Sem cliente 'ots', fica PENDING explícito (nunca silencioso)."""
    exe = shutil.which("ots")
    if not exe:
        return {"status": "PENDING", "reason": "cliente ots ausente; carimbar depois com freeze.py stamp",
                "digest": digest}
    outdir.mkdir(parents=True, exist_ok=True)
    df = outdir / "freeze_receipt.digest"
    df.write_text(digest + "\n", encoding="utf-8")
    r = subprocess.run([exe, "stamp", str(df)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return {"status": "PENDING", "reason": "ots stamp falhou: " + r.stderr.strip()[:200], "digest": digest}
    return {"status": "STAMPED", "file": df.name + ".ots", "digest": digest, "at": core.now()}


def verify(rec_path: Path, repo: Path) -> list[dict]:
    """Confere um comprovante. Devolve a lista de divergências (vazia = íntegro)."""
    rec = core.read_json(rec_path)
    probs = []
    if rec.get("schema") != RECEIPT_SCHEMA:
        return [{"path": str(rec_path), "problem": "schema desconhecido"}]
    if receipt_digest(rec) != rec.get("digest"):
        probs.append({"path": portable(rec_path, repo), "problem": "comprovante editado (digest não bate)"})
    for kind in ("artifacts", "transitive_inputs"):
        for e in rec.get(kind, []):
            cur = core.hash_path(resolve(e["path"], repo))
            if cur["sha256"] != e["sha256"]:
                d = {"path": e["path"], "problem": "hash mudou" if cur["kind"] != "missing" else "sumiu",
                     "section": kind, "receipt": rec.get("name")}
                if e.get("kind") == "dir" and cur["kind"] == "dir":
                    old, new = e.get("files", {}), cur["files"]
                    d["changed_files"] = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))[:50]
                probs.append(d)
    return probs


# ---------------------------------------------------------------- manifestos (C17 MANIFEST.sha256)

def manifest_paths(cat: Catalog, mid: str, repo: Path) -> list[Path]:
    cands = {Path(repo) / "results" / mid / "MANIFEST.sha256", core.bo_data() / mid / "MANIFEST.sha256"}
    if mid in cat.modules:
        for o in cat.modules[mid].outputs:
            if o.endswith("MANIFEST.sha256"):
                for x in cat.expand(o, mid, repo):
                    cands.add(Path(x))
    return sorted(p for p in cands if p.exists())


def manifest_candidates(rel: str, mf: Path, repo: Path) -> list[Path]:
    """Convenção C17: caminho absoluto, portátil ($BO_REPO/$BO_DATA), relativo ao manifesto
    ou relativo à raiz do repositório (como o shasum -c rodado de $BO_REPO)."""
    if rel.startswith("$BO_"):
        return [resolve(rel, repo)]
    if rel.startswith("/"):
        return [Path(rel)]
    return [mf.parent / rel, Path(repo) / rel]


def verify_manifest(mf: Path, repo: Path | None = None) -> list[dict]:
    probs = []
    repo = Path(repo or core.bo_repo())
    for n, line in enumerate(mf.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            probs.append({"path": f"{mf}:{n}", "problem": "linha mal formada"})
            continue
        sha, rel = parts[0], parts[1].lstrip("*")
        cands = manifest_candidates(rel, mf, repo)
        f = next((c for c in cands if c.is_file()), cands[0])
        if not f.is_file():
            probs.append({"path": f"{mf}:{n}", "problem": f"arquivo listado não existe: {rel}"})
        elif core.sha256_file(f) != sha:
            probs.append({"path": f"{mf}:{n}", "problem": f"hash não bate: {rel}"})
    return probs


# ---------------------------------------------------------------- consumo

def _relevant(entry_path: str, input_patterns: list[str]) -> bool:
    return any(overlaps(entry_path, ip) for ip in input_patterns)


def consume_check(cat: Catalog, mid: str, repo: Path, record: bool = True, reset: bool = False) -> dict:
    mod = cat.get(mid)
    rep = {"module": mid, "at": core.now(), "checks": [], "ok": True}

    def add(name, ok, detail="", level="FAIL"):
        rep["checks"].append({"check": name, "status": "OK" if ok else level, "detail": detail})
        if not ok and level == "FAIL":
            rep["ok"] = False

    # 1. estado declarado
    s = st_mod.load(repo, cat)
    closure = cat.deps_closure(mid)
    stale = [x for x in [mid] + closure if st_mod.status_of(s, x) == "STALE"]
    add("estado", not stale, "STALE: " + ", ".join(stale) if stale else "nenhum STALE no fecho")
    broken = [n for n, f in s.get("freezes", {}).items() if f.get("status") == "BROKEN"]
    # 2. dependências mergeadas
    merged = merged_modules(repo)
    missing = [d for d in mod.deps if d not in merged]
    add("deps_mergeadas", not missing,
        ("não mergeadas em " + core.base_branch() + ": " + ", ".join(missing)) if missing
        else f"{len(mod.deps)} dep(s) mergeada(s)")
    # 3. padrões de entrada (deste módulo) e entradas existentes
    file_inputs = [i for i in mod.inputs if is_file_input(i)]
    ext = [i for i in mod.inputs if not is_file_input(i)]
    if ext:
        add("entradas_nao_arquivo", True, f"{len(ext)} referência(s) externa(s) sem arquivo (não conferível por hash): "
            + "; ".join(e[:60] for e in ext))
    pats = []
    for inp in file_inputs:
        pats.extend(cat.expand(inp, mid, repo))
    hits: list[Path] = []
    absent = []
    for inp in file_inputs:
        h = expand_existing(cat, inp, mid, repo)
        if not h:
            prods = sorted(cat.producers_of(cat.expand(inp, mid, repo)[0]))
            absent.append(f"{inp} (produtor: {', '.join(prods) or 'externo'})")
        hits.extend(h)
    add("entradas_existem", not absent, "ausentes: " + "; ".join(absent) if absent else f"{len(hits)} caminho(s)")
    # 4. comprovantes de congelamento
    rec_probs, covered, n_rec = [], set(), 0
    for rp in list_receipts(repo):
        rec = core.read_json(rp)
        name = rec.get("name", rp.parent.name)
        entries = rec.get("artifacts", []) + rec.get("transitive_inputs", [])
        relevant_rec = any(x in closure for x in rec.get("modules", [])) or \
            any(_relevant(e["path"], pats) for e in entries)
        for p in verify(rp, repo):
            if p["problem"].startswith("comprovante editado") or relevant_rec or _relevant(p["path"], pats):
                rec_probs.append(f"{name}: {p['path']} ({p['problem']})")
        if relevant_rec and name in broken:
            rec_probs.append(f"{name}: congelamento marcado BROKEN em state.json")
        for e in entries:
            if _relevant(e["path"], pats):
                covered.add(e["path"])
                n_rec += 1
    add("comprovantes", not rec_probs, "; ".join(rec_probs[:20]) if rec_probs
        else f"{len(list_receipts(repo))} comprovante(s); {n_rec} entrada(s) cobertas conferidas")
    # 5. manifestos transitivos das deps (MANIFEST.sha256 e summary.json)
    man_probs, n_man = [], 0
    for d in closure:
        for mf in manifest_paths(cat, d, repo):
            n_man += 1
            man_probs.extend(f"{d}: {p['path']} ({p['problem']})" for p in verify_manifest(mf, repo))
        summ = core.read_json(Path(repo) / "results" / d / "summary.json") or {}
        for inp in ((summ.get("agent_provenance") or {}).get("inputs") or []):
            if isinstance(inp, dict) and inp.get("sha256") and inp.get("path"):
                cur = core.hash_path(resolve(inp["path"], repo))
                if cur["sha256"] != inp["sha256"]:
                    man_probs.append(f"{d}: entrada {inp['path']} mudou depois que {d} a consumiu")
    add("manifestos_transitivos", not man_probs,
        "; ".join(man_probs[:20]) if man_probs else f"{n_man} manifesto(s) no fecho de {len(closure)} dep(s)")
    # 6. livro de consumo (primeiro consumo registra; depois tem de bater)
    ledger_p = core.bo_data() / mid / LEDGER_NAME
    ledger = {} if reset else (core.read_json(ledger_p) or {})
    ledger.setdefault("module", mid)
    ledger.setdefault("entries", {})
    led_probs, new = [], 0
    for h in hits:
        pp = portable(h, repo)
        cur = core.hash_path(h)["sha256"]
        old = ledger["entries"].get(pp)
        if old is None:
            ledger["entries"][pp] = {"sha256": cur, "first_seen": core.now(),
                                     "covered_by_receipt": any(overlaps(pp, c) for c in covered)}
            new += 1
        elif old["sha256"] != cur:
            led_probs.append(f"{pp} mudou desde o primeiro consumo ({old['first_seen']})")
    add("livro_de_consumo", not led_probs, "; ".join(led_probs[:20]) if led_probs
        else f"{len(hits)} entrada(s); {new} " + ("registrada(s) agora (primeiro consumo)" if record
                                                     else "nova(s), não gravada(s) (--no-record)"))
    if record and rep["ok"]:
        ledger["updated_at"] = core.now()
        core.write_json(ledger_p, ledger)
    rep["ledger"] = str(ledger_p)
    return rep


# ---------------------------------------------------------------- invalidação

def dependents_of(cat: Catalog, path: str) -> set[str]:
    direct = cat.consumers_of(path)
    return direct | cat.reverse_closure(direct)


def invalidate_scan(cat: Catalog, repo: Path) -> dict:
    """Confere todos os comprovantes; devolve artefatos mudados e dependentes transitivos."""
    out = {"at": core.now(), "receipts": [], "stale": {}}
    for rp in list_receipts(repo):
        rec = core.read_json(rp)
        probs = verify(rp, repo)
        out["receipts"].append({"name": rec.get("name"), "path": portable(rp, repo), "problems": probs})
        for p in probs:
            src = p["path"]
            for d in sorted(dependents_of(cat, str(resolve(src, repo)))):
                out["stale"].setdefault(d, []).append(f"{rec.get('name')}:{src}")
    return out


def apply_stale(cat: Catalog, repo: Path, stale: dict, broken: list[str], reason: str) -> list[str]:
    s = st_mod.load(repo, cat)
    changed = []
    for mid, srcs in sorted(stale.items()):
        if st_mod.mark(s, mid, "STALE", reason, source="; ".join(sorted(set(srcs)))[:500]):
            changed.append(mid)
    for b in broken:
        if b in s["freezes"]:
            s["freezes"][b]["status"] = "BROKEN"
            s["events"].append({"at": core.now(), "freeze": b, "status": "BROKEN", "reason": reason})
    st_mod.save(s, repo)
    return changed


def is_under(path: str, owned: str) -> bool:
    return matches(path, owned)
