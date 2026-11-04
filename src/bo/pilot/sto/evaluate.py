"""Avaliação do piloto sto pelo oráculo offline (só calibração; as retidas ficam cifradas e não são lidas).

  judge_runs()       cada tradução que desceu é julgada pelo oráculo (judge) com as perdas declaradas pelo plano
  negatives()        respostas do pipeline às alegações-contraexemplo das fixtures e conferência das configurações
                     candidatas negativas das entradas de direção: nenhuma pode ser aceita
  grain()            decomposição = gabarito nos casos obrigatórios; invariância a reordenação e à embalagem
  wilson()           intervalo de Wilson (95%) para as frações relatadas no C15
"""

from __future__ import annotations

import copy
import math
import random

from . import common as C
from . import lift as L
from . import oracle_io
from . import pipeline as PL

ACCEPTING = ("ACCEPT", "ACCEPT_WITH_DECLARED_LOSS")
NEGATIVE_VARIANTS = ("negative", "negative_silent")


def wilson(k: int, n: int, z: float = 1.959964) -> dict:
    if n == 0:
        return {"lower": 0.0, "upper": 1.0, "est": None, "n": 0}
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"lower": round(max(0.0, c - h), 6), "upper": round(min(1.0, c + h), 6), "est": round(p, 6), "n": n}


def judge_runs(res: dict) -> dict:
    O = oracle_io.load()
    out = {}
    for ctl, runs in res["runs"].items():
        rows = []
        for r, e in zip(runs, res["entries"]):
            row = {"entry_id": e["entry_id"], "direction": e["direction"], "family": e["family"],
                   "variant": e["variant"], "status": r.status}
            if r.status == "LOWERED":
                j = O.judge(e["source"], r.target, r.translation.effects, r.container_map)
                row.update({"verdict": j["verdict"], "code": j.get("code"), "declared": r.translation.effects,
                            "divergences": j["divergences"], "spurious_declared": j["spurious_declared"],
                            "unknown_codes": j["unknown_codes"]})
            else:
                row.update({"verdict": "NOT_TRANSPORTED", "block_code": r.block[0], "block_rule": r.block[1]})
            rows.append(row)
        out[ctl] = rows
    return out


def negatives(ctx, res: dict) -> dict:
    """Contraexemplos: alegações negativas das fixtures (respostas do pipeline) e configurações-alvo negativas."""
    exp = C.read_json(C.repo() / "pilot" / "sto" / "expected_answers.json")
    out = {ctl: {"fixture_claims": [], "candidates": []} for ctl in res["runs"]}
    for fid, f in sorted(exp["fixtures"].items()):
        fx = C.read_json(C.repo() / f["file"])
        for chk in f["checks"]:
            if chk["kind"] != "claim" or chk["expect"].get("verdict") != "REJECT":
                continue
            for ctl in res["runs"]:
                a = PL.pipeline_answer(ctx, fx, chk["claim"], ctl)
                out[ctl]["fixture_claims"].append({"fixture_id": fid, "case": f["case"], "about": chk["claim"]["about"],
                                                   "answer": a["answer"], "code": a.get("code")})
    for ctl, runs in res["runs"].items():
        for r, e in zip(runs, res["entries"]):
            if e["variant"] not in NEGATIVE_VARIANTS:
                continue
            v = PL.verify_candidate(ctx, r, e["target"])
            out[ctl]["candidates"].append({"entry_id": e["entry_id"], "variant": e["variant"], "answer": v["answer"]})
    return out


# ----------------------------------------------------------------------------------------------------------
# grão
# ----------------------------------------------------------------------------------------------------------
def neutral(dec: dict) -> dict:
    return {k: {kk: vv for kk, vv in v.items() if kk not in ("realized_by", "rules")} for k, v in dec.items()}


def shuffled(fx: dict, seed: int) -> dict:
    """Mesma configuração com a ordem dos recursos, das chaves e dos blocos repetidos permutada."""
    rnd = random.Random(seed)
    g = copy.deepcopy(fx)

    def perm_dict(d):
        ks = list(d)
        rnd.shuffle(ks)
        return {k: d[k] for k in ks}

    def walk(x):
        if isinstance(x, dict):
            return perm_dict({k: walk(v) for k, v in x.items()})
        if isinstance(x, list) and x and all(isinstance(i, dict) for i in x):
            xs = [walk(i) for i in x]
            if all(any(k in i for k in ("id", "name")) for i in xs):
                rnd.shuffle(xs)          # bloco com identidade própria (regra com id/nome): a ordem não importa
            return xs
        return x

    res = (g.get("terraform") or {}).get("resource") or {}
    g["terraform"]["resource"] = perm_dict({t: perm_dict({n: walk(b) for n, b in insts.items()}) for t, insts in res.items()})
    return g


def _inline_lifecycle(rule: dict) -> dict:
    out = {}
    if "id" in rule:
        out["id"] = rule["id"]
    if "status" in rule:
        out["enabled"] = rule["status"] == "Enabled"
    f = (rule.get("filter") or [{}])[0] if isinstance(rule.get("filter"), list) else {}
    if "prefix" in f:
        out["prefix"] = f["prefix"]
    for k, kk in (("expiration", "days"), ("noncurrent_version_expiration", "noncurrent_days")):
        b = rule.get(k)
        if isinstance(b, list) and b and kk in b[0]:
            out[k] = [{"days": b[0][kk]}]
    return out


def repackaged(fx: dict) -> dict | None:
    """AWS: versionamento separado (aws_s3_bucket_versioning) <-> bloco embutido (versioning) no mesmo contêiner;
    ciclo de vida separado (aws_s3_bucket_lifecycle_configuration) -> blocos lifecycle_rule embutidos."""
    if fx.get("provider") != "aws":
        return None
    g = copy.deepcopy(fx)
    res = g["terraform"]["resource"]
    lc = res.get("aws_s3_bucket_lifecycle_configuration") or {}
    if len(lc) == 1 and "aws_s3_bucket_versioning" not in res:
        (n, body), = lc.items()
        tgt = L.ref_target({f"{t}.{k}": b for t, i in res.items() for k, b in i.items()}, body.get("bucket"))
        rules = body.get("rule") or []
        if tgt and rules and all(isinstance(r, dict) for r in rules):
            rt, rn = tgt.split(".", 1)
            if "lifecycle_rule" not in res[rt][rn]:
                res[rt][rn]["lifecycle_rule"] = [_inline_lifecycle(r) for r in rules]
                del res["aws_s3_bucket_lifecycle_configuration"]
                return g
    sep = res.get("aws_s3_bucket_versioning") or {}
    if len(sep) == 1:
        (n, body), = sep.items()
        tgt = L.ref_target({f"{t}.{k}": b for t, i in res.items() for k, b in i.items()}, body.get("bucket"))
        st = ((body.get("versioning_configuration") or [{}])[0]).get("status")
        if not tgt or st not in ("Enabled", "Suspended"):
            return None
        rt, rn = tgt.split(".", 1)
        if "versioning" in res[rt][rn]:
            return None
        res[rt][rn]["versioning"] = [{"enabled": st == "Enabled"}]
        del res["aws_s3_bucket_versioning"]
        return g
    for rn, b in (res.get("aws_s3_bucket") or {}).items():
        v = b.get("versioning")
        if isinstance(v, list) and len(v) == 1 and set(v[0]) == {"enabled"} and "aws_s3_bucket_versioning" not in res:
            del b["versioning"]
            res["aws_s3_bucket_versioning"] = {rn: {"bucket": "${aws_s3_bucket.%s.id}" % rn,
                                                    "versioning_configuration": [{"status": "Enabled" if v[0]["enabled"] else "Suspended"}]}}
            return g
    return None


def grain(ctx, seeds=(1, 2, 3)) -> dict:
    exp = C.read_json(C.repo() / "pilot" / "sto" / "expected_answers.json")
    mand = C.read_json(C.oracle_dir() / "MANDATORY.json")
    checks, mism = 0, []
    reorder_n, reorder_bad = 0, []
    pack_n, pack_bad = 0, []
    groups: dict = {}
    neg_n, neg_bad = 0, []
    fixtures = []
    for fid, f in sorted(exp["fixtures"].items()):
        fx = C.read_json(C.repo() / f["file"])
        fixtures.append((fid, fx))
        lf = L.lift(fx, ctx.claims, ctx.evidence)
        dec = L.decomposition(lf)
        for chk in f["checks"]:
            if chk["kind"] == "decomposition":
                checks += 1
                u = dec.get(chk["unit"])
                got = None if u is None else {k: u.get(k) for k in chk["expect"]}
                if got != chk["expect"]:
                    mism.append({"fixture_id": fid, "unit": chk["unit"], "expect": chk["expect"], "got": got})
            if chk["kind"] == "claim" and chk["claim"]["about"] in ("decomposition", "disjoint_kinds"):
                neg_n += 1
                a = PL.pipeline_answer(ctx, fx, chk["claim"], "c3_full")
                if a["answer"] != "REJECT":
                    neg_bad.append({"fixture_id": fid, "claim": chk["claim"], "answer": a})
        if f.get("invariant_group"):
            groups.setdefault(f["invariant_group"], []).append((fid, neutral(dec)))
    for e in PL.direction_entries():
        for side in ("source", "target"):
            fixtures.append((f"{e['entry_id']}:{side}", e[side]))
    for fid, fx in fixtures:
        base = neutral(L.decomposition(L.lift(fx, ctx.claims, ctx.evidence)))
        for s in seeds:
            reorder_n += 1
            got = neutral(L.decomposition(L.lift(shuffled(fx, s), ctx.claims, ctx.evidence)))
            if got != base:
                reorder_bad.append({"fixture_id": fid, "seed": s})
        rp = repackaged(fx)
        if rp is not None:
            pack_n += 1
            got = neutral(L.decomposition(L.lift(rp, ctx.claims, ctx.evidence)))
            if got != base:
                pack_bad.append({"fixture_id": fid, "diff": sorted(set(got) ^ set(base))[:6]})
    for gname, members in sorted(groups.items()):
        pack_n += 1
        first = members[0][1]
        if any(m[1] != first for m in members[1:]):
            pack_bad.append({"group": gname, "fixtures": [m[0] for m in members]})
    return {"mandatory_cases": sorted(mand["mandatory_cases"]), "decomposition_checks": checks,
            "decomposition_mismatches": mism, "negative_claims": neg_n, "negative_not_rejected": neg_bad,
            "reorder_trials": reorder_n, "reorder_failures": reorder_bad, "packaging_trials": pack_n,
            "packaging_failures": pack_bad, "invariant_groups": sorted(groups)}
