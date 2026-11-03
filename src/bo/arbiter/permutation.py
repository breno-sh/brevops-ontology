"""Gate: veredito igual com provedores renomeados para rótulos opacos e nas 24 ordens (S15, R1-M7).

Uso: python -I -m bo.arbiter.permutation [--rename]

Mundo plantado (bo.arbiter.battery.world, provedores pa, pb, pc, pd, mais o glossário das âncoras). Para cada uma
das 4! = 24 ordens dos provedores, as alegações entram ordenadas pela posição do provedor do sujeito e do objeto
nessa ordem (a ordem das linhas muda). Com --rename, além disso, todo id de átomo (sujeito, objeto, campos de
projeção e de grupo, átomo das âncoras do glossário) vira um rótulo opaco por uma bijeção que depende da ordem:
o prefixo do provedor e o nome local somem. Exige, em toda ordem, a mesma parte do C21 que não depende de hora,
sha nem texto: claim_version_id -> (veredito, regras, composição usada).

Antes, confere que a execução canônica dá os vereditos plantados (não se testa invariância de um árbitro errado).
Controle (o teste não é vazio): um 'árbitro com voto' que, em cada conflito, dá OK à alegação cujo provedor de
sujeito vem primeiro (o desempate por nome de provedor que a S15 condena) tem de mudar de saída em alguma ordem.
Relatório: $BO_DATA/ARBITERLIB/permutation.json.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import sys

from . import battery as B
from . import engine
from .common import emit, now, provider_of, sha256_bytes, write_report
from .inputs import Glossary

PROVIDERS = ("pa", "pb", "pc", "pd")
DECIDED = "2026-11-03T00:00:00-03:00"


def opaque(perm_idx: int, atom: str) -> str:
    h = sha256_bytes(f"{perm_idx}|{atom}".encode("utf-8"))
    p = provider_of(atom)
    return f"q{sha256_bytes(f'{perm_idx}|{p}'.encode('utf-8'))[:5]}:x{h[:12]}"


def rename_claims(claims: list[dict], f) -> list[dict]:
    out = []
    for r in claims:
        r = copy.deepcopy(r)
        for k in ("subject_id", "object_id"):
            r[k] = f(r[k])
        for p in r.get("projection") or []:
            p["field"] = f(p["field"])
        g = r.get("group")
        if g:
            for v in g.get("variables") or []:
                v["field"] = f(v["field"])
        for a in r.get("anchors") or []:
            if isinstance(a, dict) and a.get("atom_id"):
                a["atom_id"] = f(a["atom_id"])
        out.append(r)
    return out


def glossary_world() -> tuple[list[dict], dict]:
    """Mundo + duas alegações de mesmo conceito (uma com âncoras auditadas, outra com âncora fraca)."""
    claims, expect, _ = B.world()
    s, o = "pa:anc.backup_retention", "pb:anc.backup_retention"
    base = B.C("ANC-OK", s, "exact", o, B.DAYS(1, 30), B.DAYS(1, 30), B.IDN, "equal", "lossless",
               tests=[{"input": 7, "expected": 7}], basis="shared_concept",
               subject_concept="concept:backup_retention", object_concept="concept:backup_retention",
               anchors=[{"claim_id": "ANC-BAT-01", "evidence_state": "DOC_SUPPORTED"},
                        {"claim_id": "ANC-BAT-02", "evidence_state": "DOC_SUPPORTED"}])
    weak = copy.deepcopy(base)
    weak.update(claim_id="ANC-WEAK", claim_version_id="ANC-WEAK@1", event_id="EV-ANC-WEAK",
                subject_id="pc:anc.backup_retention", object_id="pd:anc.backup_retention",
                anchors=[{"claim_id": "ANC-BAT-03", "evidence_state": "DOC_SUPPORTED"},
                         {"claim_id": "ANC-BAT-04", "evidence_state": "DOC_SUPPORTED"}])
    g = B.glossary_records({s: "DOC_SUPPORTED", o: "DOC_SUPPORTED", "pc:anc.backup_retention": "DOC_SUPPORTED",
                            "pd:anc.backup_retention": "STRUCTURALLY_VALID"})
    expect.update({"ANC-OK": "OK", "ANC-WEAK": "UNPROVEN"})
    return claims + [base, weak], {"glossary": g, "expect": expect}


def run_once(claims, gl, perm, perm_idx, rename) -> dict:
    rank = {p: i for i, p in enumerate(perm)}
    order = sorted(range(len(claims)), key=lambda i: (rank.get(provider_of(claims[i]["subject_id"]), 9),
                                                      rank.get(provider_of(claims[i]["object_id"]), 9), i))
    cs = [claims[i] for i in order]
    orig = cs
    g = copy.deepcopy(gl)
    if rename:
        cs = rename_claims(cs, lambda a: opaque(perm_idx, a))
        for a in g["claims"]:
            a["atom_id"] = opaque(perm_idx, a["atom_id"])
    res = engine.arbitrate(B.items_of(cs), glossary=Glossary(g["claims"], g["audits"]), decided_at=DECIDED,
                           arbiter_sha256="0" * 64)
    return {"map": engine.verdict_map(res["verdicts"]), "verdicts": res["verdicts"], "claims": orig}


def voting(out: dict, perm) -> dict:
    """Controle: árbitro com voto por nome de provedor (o que o árbitro de verdade não faz). O voto olha o nome
    ORIGINAL do provedor do sujeito na ordem dada; a saída dele muda com a ordem, a do árbitro não."""
    rank = {p: i for i, p in enumerate(perm)}
    subj = {r["claim_id"]: provider_of(r["subject_id"]) for r in out["claims"]}
    m = dict(out["map"])
    contested = sorted((vid for vid, v in m.items() if v[0] == "CONTESTED" and vid.split("@")[0] in subj),
                       key=lambda vid: (rank.get(subj[vid.split("@")[0]], 9), vid))
    if contested:
        win = contested[0]
        m[win] = ("OK", (), ())
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.arbiter.permutation")
    ap.add_argument("--rename", action="store_true", help="também renomeia provedores e átomos para rótulos opacos")
    a = ap.parse_args(argv)
    claims, ctx = glossary_world()
    gl, expect = ctx["glossary"], ctx["expect"]
    canon_run = run_once(claims, gl, PROVIDERS, 0, False)
    got = {vid.split("@")[0]: v[0] for vid, v in canon_run["map"].items()}
    wrong = {cid: (got.get(cid), e) for cid, e in expect.items() if got.get(cid) != e}
    diffs, ctl_changed = [], 0
    ctl_ref = voting(canon_run, PROVIDERS)
    perms = list(itertools.permutations(PROVIDERS))
    for i, perm in enumerate(perms):
        r = run_once(claims, gl, perm, i + 1, a.rename)
        if r["map"] != canon_run["map"]:
            ks = sorted(set(r["map"]) ^ set(canon_run["map"])) + \
                sorted(k for k in set(r["map"]) & set(canon_run["map"]) if r["map"][k] != canon_run["map"][k])
            diffs.append({"order": list(perm), "differs": ks[:20]})
        if voting(r, perm) != ctl_ref:
            ctl_changed += 1
    ok = not wrong and not diffs and ctl_changed > 0 and len(perms) == 24
    p = write_report("permutation", {"rename": a.rename, "orders": len(perms), "claims": len(claims),
                                     "verdict_lines": len(canon_run["map"]), "planted_wrong": wrong, "diffs": diffs,
                                     "control_voting_changed_in": ctl_changed, "pass": ok})
    for d in diffs[:5]:
        emit(f"  FALHA ordem {d['order']}: {d['differs'][:5]}")
    for cid, (g, e) in list(wrong.items())[:10]:
        emit(f"  FALHA plantado {cid}: {g} (esperado {e})")
    emit(f"[{now()}] permutation{' --rename' if a.rename else ''}: {len(perms)} ordens, {len(canon_run['map'])} "
         f"vereditos; {len(perms) - len(diffs)}/{len(perms)} iguais ao canônico; plantados {len(expect) - len(wrong)}/"
         f"{len(expect)}; controle com voto mudou em {ctl_changed}/{len(perms)}; relatório {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
