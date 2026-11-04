"""Gera $BO_DATA/UNITS/value_space.jsonl (C05) a partir de SCHEMA-*/atoms.jsonl e DOCS-*/docs_facts.jsonl.

  python -I -m bo.units.build            gera value_space.jsonl, build_report.json e iri_status (via qudt)
  python -I -m bo.units.build --check    regenera em $BO_TMP e confere byte a byte com o gravado

Um registro por átomo do schema (os 4 provedores). Determinístico: ordem por atom_id, JSON canônico, sem carimbo
de hora dentro do value_space (o carimbo vai no build_report.json).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from bo.transforms import units as tu
from bo.transforms.errors import TransformError

from . import rules as R
from .rules import NA, UNK, UT

PROVIDERS = [("AWS", "aws"), ("GCP", "google"), ("AZURE", "azurerm"), ("OCI", "oci")]
KEEP = {"unit", "range", "allowed_values", "format", "default"}
MAX_EVIDENCE_REFS = 3


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", Path(__file__).resolve().parents[3]))


def out_dir() -> Path:
    return bo_data() / "UNITS"


def inputs() -> list[Path]:
    d = bo_data()
    out = []
    for P, _ in PROVIDERS:
        out += [d / f"SCHEMA-{P}" / "atoms.jsonl", d / f"DOCS-{P}" / "docs_facts.jsonl"]
    sb = d / "DOCS-AWS" / "shared_block_map.jsonl"
    if sb.exists():
        out.append(sb)
    return out


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ leitura
def load_facts(P: str) -> dict[str, list[dict]]:
    facts: dict[str, list[dict]] = defaultdict(list)
    with open(bo_data() / f"DOCS-{P}" / "docs_facts.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["fact_kind"] not in KEEP:
                continue
            facts[r["atom_id"]].append({
                "k": r["fact_kind"], "id": r["fact_id"], "st": r["status"], "lv": r["evidence_level"],
                "v": r.get("value"), "s": (r.get("source") or {}).get("sentence", ""), "ur": r.get("unknown_reason"),
            })
    return facts


def load_shared_map(facts: dict[str, list[dict]], stats: Counter) -> None:
    """DOCS-AWS: repetições (R3-shared) que ainda não têm fato próprio herdam os fatos do canônico."""
    p = bo_data() / "DOCS-AWS" / "shared_block_map.jsonl"
    if not p.exists():
        stats["shared_map_absent"] += 1
        return
    stats["shared_map_repeats_inherited"] += 0
    with open(p, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            canon = [c for c in r.get("canonical") or [] if c in facts]
            if not canon:
                continue
            src = canon[0]
            for rep in r.get("repeats") or []:
                stats["shared_map_repeats_seen"] += 1
                if rep in facts:
                    stats["shared_map_repeats_with_own_facts"] += 1
                    continue
                facts[rep] = [dict(x, inh=src) for x in facts[src]]
                stats["shared_map_repeats_inherited"] += 1


# ----------------------------------------------------------------------------------------------- datatype
SCALAR = {"string": "string", "number": "decimal", "bool": "boolean"}


def datatype_of(tf) -> dict:
    if isinstance(tf, str):
        if tf in SCALAR:
            return {"kind": "scalar", "scalar": SCALAR[tf]}
        if tf == "dynamic":
            return {"kind": "tree", "format": "json_document"}
        raise ValueError(f"tf_type desconhecido: {tf!r}")
    head, inner = tf[0], tf[1]
    if head in ("list", "set"):
        d = {"kind": "tree", "format": "list"}
        if isinstance(inner, str) and inner in SCALAR:
            d["value_scalar"] = SCALAR[inner]
        return d
    if head == "map":
        d = {"kind": "tree", "format": "map", "key_scalar": "string"}
        if isinstance(inner, str) and inner in SCALAR:
            d["value_scalar"] = SCALAR[inner]
        return d
    if head == "object":
        comps = inner if isinstance(inner, dict) else {}
        if len(comps) >= 2 and all(isinstance(t, str) and t in SCALAR for t in comps.values()) and \
                all(_comp_name_ok(n) for n in comps):
            return {"kind": "tuple", "components": [{"name": n, "scalar": SCALAR[comps[n]]} for n in sorted(comps)]}
        return {"kind": "tree", "format": "map", "key_scalar": "string"}
    raise ValueError(f"tf_type desconhecido: {tf!r}")


def _comp_name_ok(n: str) -> bool:
    import re
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", n))


TIMEOUT_OPS = {"create", "read", "update", "delete", "default"}


def is_timeout(atom: dict) -> bool:
    bp = atom.get("block_path") or []
    parts = atom["path"].split(".")
    return (len(parts) == 2 and parts[0] == "timeouts" and parts[1] in TIMEOUT_OPS and len(bp) == 1
            and bp[0].get("block") == "timeouts" and atom.get("tf_type") == "string")


# --------------------------------------------------------------------------------------------- evidência
def ev_fact(f: dict, note: str | None = None) -> dict:
    e = {"level": f["lv"] if f["lv"] in ("published", "derived") else "derived", "ref": f["id"]}
    n = note or ""
    if f.get("inh"):
        e["level"] = "derived"
        n = (n + "; " if n else "") + f"UNITS-SHARED-01 herdado de {f['inh']}"
    if n:
        e["note"] = n if len(n) >= 3 else n + "   "
    return e


def ev_rule(rule: str, note: str | None = None) -> dict:
    e = {"level": "derived", "ref": rule}
    if note:
        e["note"] = note
    return e


# ------------------------------------------------------------------------------------------------- unidade
def unit_candidates(fs: list[dict]) -> tuple[list[tuple[UT, dict]], list[dict], list[tuple[UT, dict]]]:
    """(candidatos de fato unit stated, fatos unit unknown, candidatos fracos de range/default)."""
    strong, unknown, weak = [], [], []
    for f in fs:
        if f["k"] == "unit":
            if f["st"] != "stated":
                unknown.append(f)
                continue
            v = f["v"]
            lit = None
            if isinstance(v, str):
                lit = v
            elif isinstance(v, dict):
                lit = v.get("literal") or v.get("unit")
                ut = R.literal_type(v.get("unit") or "", f["s"]) if v.get("unit") else None
                ut2 = R.literal_type(v.get("literal") or "", f["s"]) if v.get("literal") else None
                # literal com caixa (GiB) vence o nome normalizado quando ele é mais específico
                if ut2 is not None and (ut is None or ut.unit == UNK or ut2.rule in ("UNITS-BYTE-01", "UNITS-BYTE-03")):
                    ut = ut2
                strong.append((ut if ut is not None else UT(UNK, UNK, None, "UNITS-LIT-01",
                                                              f"literal '{lit}' fora da tabela"), f))
                continue
            ut = R.literal_type(lit, f["s"]) if lit else None
            strong.append((ut if ut is not None else UT(UNK, UNK, None, "UNITS-LIT-01",
                                                          f"literal '{lit}' fora da tabela"), f))
        elif f["k"] == "range" and f["st"] == "stated" and isinstance(f["v"], dict):
            u = f["v"].get("unit") or f["v"].get("unit_text")
            if u:
                ut = R.literal_type(u, f["s"])
                if ut is not None:
                    weak.append((ut, f))
        elif f["k"] == "default" and f["st"] == "stated" and isinstance(f["v"], dict) and "unit" in f["v"]:
            ut = R.literal_type(f["v"]["unit"], f["s"])
            if ut is not None:
                weak.append((ut, f))
    return strong, unknown, weak


def resolve(cands: list[UT]) -> UT:
    """Concilia candidatos: iguais -> o tipo; janela de uma fonte completa a outra da mesma grandeza que não tem
    janela; ambíguo + concreto da mesma grandeza e janela -> concreto; mesma grandeza -> unidade UNKNOWN;
    grandezas diferentes -> UNKNOWN."""
    keys = {c.key() for c in cands}
    if len(keys) == 1:
        return cands[0]
    wins = {c.window for c in cands} - {None}
    if len(wins) == 1 and len({c.qk for c in cands}) == 1 and any(c.window is None for c in cands):
        w = next(iter(wins))
        cands = [c if c.window else replace(c, window=w, note=c.note + f"; janela {w} de outra fonte")
                 for c in cands]
        keys = {c.key() for c in cands}
        if len(keys) == 1:
            return replace(cands[0], note=cands[0].note + "; resolvido")
    concrete = [c for c in cands if c.unit != UNK]
    amb = [c for c in cands if c.unit == UNK and c.qk != UNK]
    ck = {c.key() for c in concrete}
    if len(ck) == 1 and concrete and all(a.qk == concrete[0].qk and a.window == concrete[0].window for a in amb) \
            and len(concrete) + len(amb) == len(cands):
        c = concrete[0]
        return replace(c, note=c.note + "; literal ambíguo resolvido pela outra fonte")
    qks = {c.qk for c in cands}
    wins = {c.window for c in cands}
    desc = ", ".join(sorted({f"{c.unit}{'/' + c.window if c.window else ''}" for c in cands}))
    if len(qks) == 1 and UNK not in qks:
        return UT(qks.pop(), UNK, wins.pop() if len(wins) == 1 else None, "UNITS-CONFLICT-01",
                  f"fontes discordam na unidade: {desc}")
    return UT(UNK, UNK, None, "UNITS-CONFLICT-01", f"fontes discordam na grandeza: {desc}")


# ------------------------------------------------------------------------------------------------- faixa
def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def range_of(fs: list[dict], unit: str, numeric_scalar: bool, stats: Counter, explicit_unit_only: bool = False):
    rs = []
    for f in fs:
        if f["k"] != "range" or f["st"] != "stated" or not isinstance(f["v"], dict):
            continue
        v = f["v"]
        of = v.get("of") or v.get("applies_to")
        if not (of == "value" or (of == "count" and numeric_scalar)):
            stats["range_not_value_skipped"] += 1
            continue
        lo, hi = v.get("min"), v.get("max")
        if (lo is not None and not _num(lo)) or (hi is not None and not _num(hi)) or (lo is None and hi is None):
            stats["range_malformed_skipped"] += 1
            continue
        ru = v.get("unit") or v.get("unit_text")
        if explicit_unit_only and not ru:
            stats["range_dropped_unit_sources_disagree"] += 1
            continue
        if ru:
            rut = R.literal_type(ru, f["s"])
            if rut is None or rut.unit == UNK or unit in (UNK, NA):
                stats["range_unit_unresolved_skipped"] += 1
                continue
            if rut.unit != unit:
                try:
                    lo = None if lo is None else tu.convert(lo, rut.unit, unit)
                    hi = None if hi is None else tu.convert(hi, rut.unit, unit)
                except (TransformError, ValueError, ZeroDivisionError):
                    stats["range_unit_conversion_failed"] += 1
                    continue
                if any(isinstance(x, Fraction) for x in (lo, hi)):
                    stats["range_unit_conversion_inexact_skipped"] += 1
                    continue
                stats["range_converted"] += 1
        r = {}
        if lo is not None:
            r["min"] = lo
        if hi is not None:
            r["max"] = hi
        if v.get("min_exclusive") is True:
            r["min_exclusive"] = True
        if v.get("max_exclusive") is True:
            r["max_exclusive"] = True
        rs.append((r, f))
    if not rs:
        return None, []
    distinct = {json.dumps(r, sort_keys=True) for r, _ in rs}
    if len(distinct) > 1:
        stats["range_conflict_skipped"] += 1
        return None, []
    r = rs[0][0]
    if "min" in r and "max" in r and r["min"] > r["max"]:
        stats["range_inverted_skipped"] += 1
        return None, []
    return r, [f for _, f in rs]


# -------------------------------------------------------------------------------------------------- enum
def enum_of(fs: list[dict], stats: Counter):
    vals, used = [], []
    for f in fs:
        if f["k"] != "allowed_values" or f["st"] != "stated":
            continue
        v = f["v"]
        if isinstance(v, dict):
            if v.get("closed") is not True:
                stats["enum_open_list_skipped"] += 1
                continue
            v = v.get("values")
        if not isinstance(v, list) or not v:
            continue
        for x in v:
            if isinstance(x, (str, int, float, bool)) and x not in vals:
                vals.append(x)
        used.append(f)
    return vals, used


def formats_of(fs: list[dict]):
    fm, used = set(), []
    for f in fs:
        if f["k"] == "format" and f["st"] == "stated":
            x = R.format_of(f["v"])
            if x:
                fm.add(x)
                used.append(f)
    return fm, used


# ----------------------------------------------------------------------------------------------- registro
def record(atom: dict, fs: list[dict], stats: Counter, privacy_scan) -> dict:
    aid = atom["atom_id"]
    dt = datatype_of(atom["tf_type"])
    ev: list[dict] = []
    rec = {"atom_id": aid, "datatype": dt}
    fmts, fmt_facts = formats_of(fs)
    strong, unknown, weak = unit_candidates(fs)
    numeric = dt["kind"] == "scalar" and dt["scalar"] == "decimal"

    # ---- tipos especiais de string: duração e enum
    if is_timeout(atom):
        dt = rec["datatype"] = {"kind": "scalar", "scalar": "duration"}
        fmts = {"go_duration"}
        fmt_facts = []
        ut = UT(R.TIME, "unit:SEC", None, "UNITS-DUR-01", "valor é duração Go; unit:SEC é a unidade da faixa")
        ev.append(ev_rule("UNITS-DUR-01"))
        stats["duration_go_timeouts"] += 1
    elif dt == {"kind": "scalar", "scalar": "string"} and ("protobuf_duration" in fmts or "iso8601_duration" in fmts):
        dt = rec["datatype"] = {"kind": "scalar", "scalar": "duration"}
        if "protobuf_duration" in fmts:
            fmts = {"protobuf_duration"}
            ut = UT(R.TIME, "unit:SEC", None, "UNITS-DUR-02", "google.protobuf.Duration")
            stats["duration_protobuf"] += 1
        else:
            fmts = {"iso8601_duration"}
            ut = UT(R.TIME, UNK, None, "UNITS-DUR-03", "xsd:duration com meses não tem unidade única")
            stats["duration_iso8601"] += 1
        fmt_facts = [f for f in fmt_facts if R.format_of(f["v"]) in fmts]
        ev += [ev_fact(f, ut.rule) for f in fmt_facts[:MAX_EVIDENCE_REFS]]
    else:
        ut = None
        if dt == {"kind": "scalar", "scalar": "string"}:
            vals, efs = enum_of(fs, stats)
            if vals:
                dt = rec["datatype"] = {"kind": "scalar", "scalar": "enum"}
                rec["enum"] = vals
                ev += [ev_fact(f, "UNITS-ENUM-01") for f in efs[:MAX_EVIDENCE_REFS]]
                stats["enum_from_allowed_values"] += 1
        elif dt["kind"] != "scalar" or dt["scalar"] != "string":
            vals, efs = enum_of(fs, stats)
            if vals:
                stats["enum_on_non_string_dropped"] += 1
        if dt["kind"] == "tree" and dt["format"] == "json_document":
            pass
        elif dt == {"kind": "scalar", "scalar": "string"} and "json" in fmts:
            name = atom["path"].rsplit(".", 1)[-1]
            dt = rec["datatype"] = {"kind": "tree", "format": "policy_document" if name.endswith("policy") else
                                    "json_document"}
            ev += [ev_fact(f, "UNITS-FMT-01") for f in fmt_facts if R.format_of(f["v"]) == "json"][:1]
            fmts.discard("json")
            stats["string_json_to_tree"] += 1

    numeric = dt["kind"] == "scalar" and dt["scalar"] in ("decimal", "integer")

    # ---- grandeza e unidade
    if ut is None:
        if not numeric:
            if strong and any(c.qk != UNK for c, _ in strong):
                stats[f"unit_fact_on_{dt['kind']}_{dt.get('scalar', dt.get('format'))}_dropped"] += 1
            ut = UT(NA, NA, None, "UNITS-KIND-01")
            ev.insert(0, ev_rule("UNITS-KIND-01"))
        elif R.name_compound(atom["path"]):
            ut = UT(UNK, UNK, None, "UNITS-RATE-02", "nome '_per_<não-tempo>': unidade composta")
            ev.append(ev_rule("UNITS-RATE-02", ut.note))
            ev += [ev_fact(f, "UNITS-RATE-02: unidade do fato não basta para a composta") for _, f in
                   strong[:MAX_EVIDENCE_REFS]]
            stats["unit_compound_by_name"] += 1
        elif strong:
            nt = R.name_type(atom["path"], atom.get("_sib", frozenset()))
            ut = resolve([c for c, _ in strong] + ([nt] if nt is not None else []))
            if nt is not None and nt.key() != strong[0][0].key():
                ev.append(ev_rule("UNITS-NAME-01", nt.note))
                stats["unit_doc_plus_name_differ"] += 1
            notes = {id(f): (c.rule + (": " + c.note if c.note else "")) for c, f in strong}
            ev += [ev_fact(f, notes[id(f)]) for _, f in strong[:MAX_EVIDENCE_REFS]]
            stats["unit_from_doc_unit_fact"] += 1
        elif R.is_identifier_number(atom["path"]):
            ut = UT(NA, NA, None, "UNITS-NAID-01")
            ev.append(ev_rule("UNITS-NAID-01", f"nome '{atom['path'].rsplit('.', 1)[-1]}'"))
            stats["number_identifier_na"] += 1
        else:
            nt = R.name_type(atom["path"], atom.get("_sib", frozenset()))
            cands = []
            if nt is not None:
                cands.append(nt)
            if weak:
                cands += [c for c, _ in weak]
            if cands:
                ut = resolve(cands)
                if nt is not None:
                    ev.append(ev_rule("UNITS-NAME-01", nt.note))
                    stats["unit_from_name_rule"] += 1
                if weak:
                    ev += [ev_fact(f, c.rule + ": unidade da faixa/default") for c, f in weak[:MAX_EVIDENCE_REFS]]
                    if nt is None:
                        stats["unit_from_range_or_default"] += 1
            elif unknown:
                ut = UT(UNK, UNK, None, "UNITS-UNK-02")
                ev += [ev_fact(f, f"UNITS-UNK-02: {f.get('ur') or 'unknown'}") for f in unknown[:MAX_EVIDENCE_REFS]]
                stats["unit_unknown_by_docs"] += 1
            else:
                ut = UT(UNK, UNK, None, "UNITS-UNK-01")
                ev.append(ev_rule("UNITS-UNK-01"))
                stats["unit_unknown_no_evidence"] += 1
        if numeric and ut.rule == "UNITS-EPOCH-01":
            fmts = {"unix_epoch"}

    # tupla: grandeza não determinada por componente (C05 não tem grandeza por componente)
    if dt["kind"] == "tuple" and any(c["scalar"] in ("decimal", "integer", "duration") for c in dt["components"]):
        ut = UT(UNK, UNK, None, "UNITS-UNK-01", "tupla com componente numérico: grandeza por componente não é "
                                                "declarável no C05")
        ev = [e for e in ev if e.get("ref") != "UNITS-KIND-01"] + [ev_rule("UNITS-UNK-01", ut.note)]

    rec["quantity_kind"] = ut.qk
    rec["unit_qudt"] = ut.unit
    rec["rate_window"] = ut.window if ut.qk != NA else None
    bc = R.BYTE_CONV.get(ut.unit, NA)
    rec["byte_convention"] = bc

    # ---- faixa (só numérico ou duração com unidade fixa)
    if numeric or (dt.get("scalar") == "duration" and ut.unit == "unit:SEC"):
        merged = ut.rule == "UNITS-CONFLICT-01" or "resolvido" in ut.note or ut.rule == "UNITS-RATE-02"
        r, rfs = range_of(fs, ut.unit, numeric, stats, explicit_unit_only=merged)
        if r:
            rec["range"] = r
            ev += [ev_fact(f, "UNITS-RANGE-01") for f in rfs[:MAX_EVIDENCE_REFS]]
            stats["range_set"] += 1

    # ---- formato
    if len(fmts) == 1:
        rec["format"] = next(iter(fmts))
        if fmt_facts:
            ev += [ev_fact(f, "UNITS-FMT-01") for f in fmt_facts if R.format_of(f["v"]) == rec["format"]][:1]
    elif len(fmts) > 1:
        stats["format_conflict_skipped"] += 1

    if not ev:
        ev.append(ev_rule(ut.rule))
    rec["evidence"] = dedupe_ev(ev)

    # ---- privacidade: valor de enum que case com regra do privacy_lint não é gravado
    if "enum" in rec:
        line = json.dumps(rec["enum"], ensure_ascii=False)
        if privacy_scan(line):
            keep = [x for x in rec["enum"] if not privacy_scan(json.dumps(x, ensure_ascii=False))]
            stats["enum_values_redacted"] += len(rec["enum"]) - len(keep)
            if keep:
                rec["enum"] = keep
            else:
                del rec["enum"]
                rec["datatype"] = {"kind": "scalar", "scalar": "string"}
                stats["enum_dropped_by_privacy"] += 1
    return rec


def dedupe_ev(ev: list[dict]) -> list[dict]:
    seen, out = set(), []
    for e in ev:
        k = json.dumps(e, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def canon(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------------------------------------------ geração
def generate(dest: Path) -> dict:
    from bo.repo import privacy
    lists, _ = privacy.load_lists()

    def scan(text: str) -> bool:
        return bool(privacy.scan_text(text, "value_space.jsonl", lists))

    stats: Counter = Counter()
    pairs: Counter = Counter()
    per_provider: dict[str, Counter] = {}
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".jsonl.part")
    all_ids = []
    with open(tmp, "w", encoding="utf-8") as out:
        for P, prov in PROVIDERS:
            facts = load_facts(P)
            if P == "AWS":
                load_shared_map(facts, stats)
            pc: Counter = Counter()
            atoms = []
            with open(bo_data() / f"SCHEMA-{P}" / "atoms.jsonl", encoding="utf-8") as f:
                for line in f:
                    atoms.append(json.loads(line))
            atoms.sort(key=lambda a: a["atom_id"])
            sib: dict[tuple, set] = defaultdict(set)
            for a in atoms:
                parent, _, leaf = a["path"].rpartition(".")
                sib[(a["resource_type"], parent)].add(leaf)
            for a in atoms:
                parent, _, leaf = a["path"].rpartition(".")
                a["_sib"] = frozenset(sib[(a["resource_type"], parent)] - {leaf})
            for a in atoms:
                rec = record(a, facts.get(a["atom_id"], []), stats, scan)
                all_ids.append(rec["atom_id"])
                pc["atoms"] += 1
                q = rec["quantity_kind"]
                pairs[(q, rec["unit_qudt"])] += 1
                pc["qk_NOT_APPLICABLE" if q == NA else "qk_UNKNOWN" if q == UNK else "qk_known"] += 1
                u = rec["unit_qudt"]
                pc["unit_NOT_APPLICABLE" if u == NA else "unit_UNKNOWN" if u == UNK else "unit_iri"] += 1
                pc[f"qk={q}"] += 1
                if rec["rate_window"]:
                    pc["rate_window_set"] += 1
                if rec["byte_convention"] != NA:
                    pc[f"byte_{rec['byte_convention']}"] += 1
                if rec["datatype"]["kind"] == "scalar" and rec["datatype"]["scalar"] in ("decimal", "integer",
                                                                                          "duration"):
                    pc["numeric_or_duration"] += 1
                    if u not in (NA, UNK):
                        pc["numeric_with_unit_iri"] += 1
                pc[f"dt={rec['datatype']['kind']}:{rec['datatype'].get('scalar') or rec['datatype'].get('format')}"] += 1
                for k in ("enum", "range", "format"):
                    if k in rec:
                        pc[f"has_{k}"] += 1
                if any(e["level"] == "published" for e in rec["evidence"]):
                    pc["evidence_has_published"] += 1
                out.write(canon(rec) + "\n")
            per_provider[prov] = pc
    if len(all_ids) != len(set(all_ids)):
        raise SystemExit("atom_id repetido no value_space")
    os.replace(tmp, dest)
    return {"stats": dict(sorted(stats.items())), "per_provider": {k: dict(sorted(v.items()))
                                                                    for k, v in per_provider.items()},
            "pairs": pairs}


def results_dir() -> Path:
    return bo_repo() / "results" / "UNITS"


def derived_results(rep: dict) -> dict[str, str]:
    """Arquivos determinísticos de results/UNITS (sem carimbo de hora): cobertura e estado dos IRIs."""
    from . import qudt
    tot = Counter()
    for v in rep["per_provider"].values():
        tot.update(v)
    numeric = tot["numeric_or_duration"]
    cov = {
        "schema": "bo.units.coverage/1", "module": "UNITS", "contract": "C05", "contract_version": "3.0.0",
        "records": tot["atoms"],
        "totals": dict(sorted(tot.items())),
        "numeric_or_duration_with_unit_iri_share": round(tot["numeric_with_unit_iri"] / numeric, 4) if numeric else None,
        "excluding_go_timeouts": {
            "numeric_or_duration": numeric - rep["stats"].get("duration_go_timeouts", 0),
            "with_unit_iri": tot["numeric_with_unit_iri"] - rep["stats"].get("duration_go_timeouts", 0),
            "share": round((tot["numeric_with_unit_iri"] - rep["stats"].get("duration_go_timeouts", 0)) /
                           (numeric - rep["stats"].get("duration_go_timeouts", 0)), 4)
            if numeric > rep["stats"].get("duration_go_timeouts", 0) else None,
            "note": "timeouts.* (duração Go por UNITS-DUR-01) inflam a fração; esta é a conta sem eles"},
        "per_provider": rep["per_provider"], "rule_stats": rep["stats"], "rules": R.RULES,
        "note": "contagens recontadas do value_space gerado; nenhuma meta de cobertura (achado contra a hipótese é "
                "resultado)",
    }
    st = qudt.iri_status(dict(rep["pairs"]))
    div = []
    for iri, u in sorted(tu.UNITS.items()):
        loc = qudt.unit_local(iri)
        qk_loc = qudt.qk_local(u.kind)
        kinds = sorted(qudt.index()["units"].get(loc, {}).get("kinds", set()))
        div.append({"unit": iri, "transforms_kind": u.kind, "qudt_links_transforms_kind": qk_loc in kinds,
                    "units_kind": R.UNIT_KIND.get(iri), "qudt_links_units_kind":
                        qudt.qk_local(R.UNIT_KIND.get(iri, "")) in kinds})
    st = {"schema": "bo.units.iri_status/1", "module": "UNITS", **st, "transforms_registry_check": div}
    return {"coverage.json": json.dumps(cov, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            "iri_status.json": json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n"}


def now_recife() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.units.build")
    ap.add_argument("--check", action="store_true", help="regenera em $BO_TMP e compara com o gravado")
    a = ap.parse_args(argv)
    dest = out_dir() / "value_space.jsonl"
    if a.check:
        tmpd = Path(os.environ.get("BO_TMP", bo_data() / "tmp" / "UNITS")) / "regen"
        tmpd.mkdir(parents=True, exist_ok=True)
        got = tmpd / "value_space.jsonl"
        rep = generate(got)
        old = json.loads((out_dir() / "build_report.json").read_text(encoding="utf-8"))
        same = sha256(got) == sha256(dest)
        same_stats = rep["stats"] == old["stats"] and rep["per_provider"] == old["per_provider"]
        same_res = all((results_dir() / k).exists() and (results_dir() / k).read_text(encoding="utf-8") == v
                       for k, v in derived_results(rep).items())
        print(f"regeneração: value_space {'idêntico' if same else 'DIFERENTE'} "
              f"({sha256(got)[:12]}); contagens {'iguais' if same_stats else 'DIFERENTES'}; "
              f"results/UNITS/{{coverage,iri_status}}.json {'iguais' if same_res else 'DIFERENTES'}")
        got.unlink()
        return 0 if same and same_stats and same_res else 1
    rep = generate(dest)
    results_dir().mkdir(parents=True, exist_ok=True)
    for k, v in derived_results(rep).items():
        (results_dir() / k).write_text(v, encoding="utf-8")
    rep.pop("pairs")
    rep = {"schema": "bo.units.build_report/1", "module": "UNITS", "generated_at": now_recife(),
           "value_space": {"path": "$BO_DATA/UNITS/value_space.jsonl", "sha256": sha256(dest),
                           "bytes": dest.stat().st_size},
           "inputs": [{"path": "$BO_DATA/" + str(p.relative_to(bo_data())), "sha256": sha256(p)} for p in inputs()],
           "rules": R.RULES, **rep}
    (out_dir() / "build_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n",
                                                encoding="utf-8")
    tot = sum(v["atoms"] for v in rep["per_provider"].values())
    print(f"value_space.jsonl: {tot} registros, {rep['value_space']['bytes']} bytes")
    for k, v in rep["per_provider"].items():
        print(f"  {k}: " + ", ".join(f"{x}={v.get(x, 0)}" for x in ("atoms", "qk_NOT_APPLICABLE", "qk_UNKNOWN",
                                                                   "qk_known", "unit_iri", "rate_window_set")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
