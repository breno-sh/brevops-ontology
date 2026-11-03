"""Gera o C04 roles.jsonl dos 4 provedores e o resumo por provedor (C15).

  python -I -m bo.roles.build           grava $BO_DATA/ROLES/roles.jsonl e results/ROLES/by_provider.json
  python -I -m bo.roles.build --check   regenera em memória e confere byte a byte (by_provider sem generated_at),
                                        e confere que todo átomo C01 dos 4 provedores tem exatamente um papel

Entradas (só leitura): $BO_DATA/SCHEMA-*/atoms.jsonl e $BO_DATA/DOCS-*/docs_facts.jsonl (pareados pelo
sufixo do nome da pasta). Dos fatos C03 só entram description e format com status stated.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import engine

TZ = ZoneInfo("America/Recife")
MODULE = "ROLES"
DOC_KINDS = ("description", "format")


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def rules_path() -> Path:
    return bo_repo() / "roles" / "rules.yaml"


def out_path() -> Path:
    return bo_data() / MODULE / "roles.jsonl"


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def input_pairs() -> list[tuple[str, Path, Path | None]]:
    """(sufixo, atoms.jsonl, docs_facts.jsonl ou None) para cada $BO_DATA/SCHEMA-*/atoms.jsonl."""
    out = []
    for a in sorted(glob.glob(str(bo_data() / "SCHEMA-*" / "atoms.jsonl"))):
        suffix = Path(a).parent.name[len("SCHEMA-"):]
        d = bo_data() / f"DOCS-{suffix}" / "docs_facts.jsonl"
        out.append((suffix, Path(a), d if d.exists() else None))
    return out


def read_atoms(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_facts(p: Path | None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if p is None:
        return out
    with open(p, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("fact_kind") in DOC_KINDS:
                out[d["atom_id"]].append({k: d.get(k) for k in ("fact_id", "fact_kind", "status", "value")})
    for v in out.values():
        v.sort(key=lambda x: x["fact_id"])
    return out


def classify_all(atoms: list[dict], facts: dict[str, list[dict]], rules: engine.Rules):
    """Átomos (todos os provedores juntos) -> registros C04 ordenados por atom_id, mais os traços usados."""
    ctx = engine.Context(rules, atoms)
    recs = []
    for a in atoms:
        x = ctx.features(a, facts.get(a["atom_id"], []))
        rule, used = engine.classify(x, rules)
        rec = {"atom_id": a["atom_id"], "role": rule.role, "rule_id": rule.id}
        if used:
            rec["evidence"] = [{"level": "derived", "ref": fid} for fid in used]
        recs.append((rec, x))
    recs.sort(key=lambda t: t[0]["atom_id"])
    return recs


def serialize(recs) -> bytes:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r, _ in recs).encode("utf-8")


def load_everything():
    rules = engine.load(rules_path())
    atoms, facts, inputs = [], {}, []
    for suffix, ap, dp in input_pairs():
        atoms.extend(read_atoms(ap))
        facts.update(read_facts(dp))
        inputs.append({"suffix": suffix, "atoms": ap, "docs": dp})
    return rules, atoms, facts, inputs


def portable(p: Path) -> str:
    s = str(p)
    for var, base in (("$BO_DATA", str(bo_data())), ("$BO_REPO", str(bo_repo()))):
        if s.startswith(base + "/"):
            return var + s[len(base):]
    return s


def by_provider(recs, atoms: list[dict], rules: engine.Rules, inputs, generated_at: str) -> dict:
    prov_of = {a["atom_id"]: a["provider"] for a in atoms}
    version_of = {}
    for a in atoms:
        version_of.setdefault(a["provider"], a["provider_version"])
    provs = sorted(version_of)
    n = Counter(prov_of.values())
    role_count = {p: Counter() for p in provs}
    rule_count = {r.id: Counter() for r in rules.rules}
    by_docs = {p: Counter() for p in provs}
    tail_terms = defaultdict(Counter)
    sens_ref_like = Counter()
    with_desc = Counter()
    with_format = Counter()
    for rec, x in recs:
        p = x.provider
        role_count[p][rec["role"]] += 1
        rule_count[rec["rule_id"]][p] += 1
        if "evidence" in rec:
            by_docs[p][rec["role"]] += 1
        if x.descs:
            with_desc[p] += 1
        if x.formats:
            with_format[p] += 1
        for tail in rules.stem_tails:
            k = len(tail)
            if len(x.leaf_tokens) >= k and x.leaf_tokens[-k:] == tail:
                tail_terms["_".join(tail)][p] += 1
                break
        if x.flags["sensitive"] and x.stem_class is not None and rec["role"] == "SECRET":
            sens_ref_like[p] += 1
    metrics = []
    rules_sha = sha256_file(rules.path)
    for p in provs:
        for role in engine.ROLES:
            k = role_count[p][role]
            frac = round(k / n[p], 6) if n[p] else None
            metrics.append({
                "metric_id": f"M-ROLES-{p.upper()}-{role}",
                "name": f"fração dos átomos do {p} {version_of[p]} com papel {role}",
                "reading": "field",
                "axis": "representability",
                "quantifier": "observed_fraction",
                "operational_coverage": {"lower": frac, "upper": frac, "est": frac, "n": n[p]},
                "frame": {"description": f"todos os átomos C01 do {p} {version_of[p]} (SCHEMA)"},
                "inclusion": {"rule_id": "INC-ROLES-01", "text": f"átomo cujo papel C04 é {role}"},
                "weights": {"scheme": "uniform"},
                "joint_uncertainty": {"method": "exact"},
            })
    single = sorted(rid for rid, c in rule_count.items() if 0 < len(c) < len(provs))
    unused = sorted(rid for rid, c in rule_count.items() if not c)
    concentrated = {}
    for term, c in sorted(tail_terms.items()):
        tot = sum(c.values())
        top, k = c.most_common(1)[0]
        if tot >= 20 and k / tot >= 0.95:
            concentrated[term] = {"total": tot, "provider": top, "share": round(k / tot, 4)}
    data = {
        "rules": {"path": "$BO_REPO/roles/rules.yaml", "sha256": rules_sha, "version": rules.raw["version"],
                  "n_rules": len(rules.rules)},
        "inputs": [{"atoms": portable(i["atoms"]), "docs": portable(i["docs"]) if i["docs"] else None}
                   for i in inputs],
        "atoms": {p: n[p] for p in provs},
        "provider_version": {p: version_of[p] for p in provs},
        "roles": {p: {r: role_count[p][r] for r in engine.ROLES} for p in provs},
        "roles_decided_with_docs": {p: {r: by_docs[p][r] for r in engine.ROLES if by_docs[p][r]} for p in provs},
        "atoms_with_stated_description": {p: with_desc[p] for p in provs},
        "atoms_with_stated_format": {p: with_format[p] for p in provs},
        "rule_firings": {rid: {p: rule_count[rid][p] for p in provs} for rid in [r.id for r in rules.rules]},
        "findings": {
            "rules_firing_in_fewer_than_all_providers": single,
            "rules_never_firing": unused,
            "tail_terms_by_provider": {t: dict(sorted(c.items())) for t, c in sorted(tail_terms.items())},
            "tail_terms_concentrated_in_one_provider": concentrated,
            "sensitive_atoms_with_id_or_name_tail": dict(sorted(sens_ref_like.items())),
        },
    }
    return {
        "schema": "bo.result/1",
        "contract": "C15",
        "contract_version": "3.1.0",
        "module": MODULE,
        "generated_at": generated_at,
        "metrics": metrics,
        "notes": ("Papel C04 por regra declarada em roles/rules.yaml, primeira que casa, a mesma lista para os 4 "
                  "provedores. Frações observadas sobre todos os átomos do SCHEMA (sem amostragem, sem meta). "
                  "rule_firings e findings descrevem onde cada regra disparou; regra que dispara em menos de 4 "
                  "provedores é achado, não erro."),
        "data": data,
    }


def build():
    rules, atoms, facts, inputs = load_everything()
    recs = classify_all(atoms, facts, rules)
    return rules, atoms, recs, inputs


def completeness(recs, atoms) -> list[str]:
    ids = [r["atom_id"] for r, _ in recs]
    probs = []
    if len(ids) != len(set(ids)):
        probs.append(f"{len(ids) - len(set(ids))} atom_id repetido(s)")
    missing = {a["atom_id"] for a in atoms} - set(ids)
    if missing:
        probs.append(f"{len(missing)} átomo(s) sem papel")
    return probs


def _strip_time(d: dict) -> dict:
    d = dict(d)
    d.pop("generated_at", None)
    return d


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    rules, atoms, recs, inputs = build()
    probs = completeness(recs, atoms)
    if probs:
        print("ROLES: " + "; ".join(probs))
        return 1
    blob = serialize(recs)
    bp_path = results_dir() / "by_provider.json"
    if check:
        bad = []
        if not out_path().exists() or out_path().read_bytes() != blob:
            bad.append("roles.jsonl difere da regeneração")
        if not bp_path.exists():
            bad.append("by_provider.json ausente")
        else:
            old = json.loads(bp_path.read_text(encoding="utf-8"))
            new = by_provider(recs, atoms, rules, inputs, old.get("generated_at", ""))
            if _strip_time(old) != _strip_time(new):
                bad.append("by_provider.json difere da regeneração")
        if bad:
            print("ROLES --check: " + "; ".join(bad))
            return 1
        print(f"ROLES --check: {len(recs)} papéis regenerados idênticos; by_provider confere")
        return 0
    out_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path().with_suffix(".jsonl.tmp")
    tmp.write_bytes(blob)
    tmp.replace(out_path())
    results_dir().mkdir(parents=True, exist_ok=True)
    doc = by_provider(recs, atoms, rules, inputs, now())
    bp_path.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    c = Counter(r["role"] for r, _ in recs)
    print(f"[{now()}] roles.jsonl: {len(recs)} átomos; " + ", ".join(f"{k}={c[k]}" for k in engine.ROLES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
