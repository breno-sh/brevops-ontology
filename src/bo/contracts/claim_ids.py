"""Gate: claim_id imutável; versão e evento em campos próprios.

  python -I -m bo.contracts.claim_ids

  I1  todo campo claim_id (claim_version_id, event_id) de todo schema publicado referencia a definição do C00;
  I2  todo registro que é VERSÃO de alegação (tem claim_version_id e event_id) exige os três campos;
  I3  nenhum schema tem o id mutável da v2 (bo_row_id, row_id, row_hash);
  I4  os padrões aceitam e recusam o que devem (claim_id sem @n, sem EV-, sem hash; versão = <claim_id>@n);
  I5  linhagem nos stubs (C09, complex, C20): claim_id igual entre versões, versão de claim_id, supersedes anterior e
      da mesma alegação, evento próprio por versão;
  I6  referências entre stubs: claim_id/claim_version_id citados em C11, C12, C21, C23 existem nas alegações (C09),
      e as pernas de uma composição (a∘b) também;
  I7  autoteste: mudar o claim_id de uma versão, reusar o evento ou apontar versão de outra alegação reprova.
"""

from __future__ import annotations

import copy
import json
import re
import sys

from . import _base, catalog, fileio, rules
from .spec_a import P_CLAIM_ID, P_CLAIM_VERSION_ID, P_EVENT_ID

C00_REF = {k: f"{_base.BASE_URI}{_base.C00}#/$defs/{k}" for k in ("claim_id", "claim_version_id", "event_id")}
LOCAL_REF = {k: f"#/$defs/{k}" for k in C00_REF}
MUTABLE = ("bo_row_id", "row_id", "row_hash")
ACCEPT = {"claim_id": ["CLM-EX-01", "ANC-aws-0001", "CLM-EX-01~inv", "CLM-A∘CLM-B", "FX:FX-BUCKET-01"],
          "claim_version_id": ["CLM-EX-01@1", "CLM-EX-01@12", "ANC-A-01@1~inv", "CLM-A∘CLM-B@1"],
          "event_id": ["EV-CLM-EX-01", "EV-AUDIT-0007", "EV-ARB-0002"]}
REJECT = {"claim_id": ["CLM-EX-01@1", "EV-CLM-EX-01", "a" * 64, "0123456789abcdef", "", "CLM EX", "@1"],
          "claim_version_id": ["CLM-EX-01", "CLM-EX-01@0", "CLM-EX-01@", "@1", "CLM-EX-01@1.2"],
          "event_id": ["CLM-EX-01@1", "EV-", "EV-@1", "ev-x"]}


def _objects(x, path=""):
    if isinstance(x, dict):
        if isinstance(x.get("properties"), dict):
            yield path, x
        for k, v in x.items():
            yield from _objects(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _objects(v, f"{path}/{i}")


def check_schemas(sch: dict) -> tuple[list[str], int]:
    errs, n = [], 0
    for cid, s in sorted(sch.items()):
        for path, o in _objects(s):
            props = o["properties"]
            for k in MUTABLE:
                if k in props:
                    errs.append(f"I3 {cid}{path}: campo mutável da v2 {k}")
            for k in C00_REF:
                if k not in props:
                    continue
                n += 1
                ref = props[k].get("$ref")
                want = LOCAL_REF[k] if cid == "C00" else C00_REF[k]
                if ref != want:
                    errs.append(f"I1 {cid}{path}/{k}: não referencia o C00 ({ref!r})")
            if "claim_version_id" in props and "event_id" in props:
                req = set(o.get("required") or [])
                miss = {"claim_id", "claim_version_id", "event_id"} - req
                if "claim_id" not in props or miss:
                    errs.append(f"I2 {cid}{path}: versão de alegação sem exigir {sorted(miss)}")
    return errs, n


def check_patterns() -> list[str]:
    errs = []
    pats = {"claim_id": P_CLAIM_ID, "claim_version_id": P_CLAIM_VERSION_ID, "event_id": P_EVENT_ID}
    for k, p in pats.items():
        for v in ACCEPT[k]:
            if not re.match(p, v):
                errs.append(f"I4 {k}: {v!r} devia ser aceito")
        for v in REJECT[k]:
            if re.match(p, v):
                errs.append(f"I4 {k}: {v!r} devia ser recusado")
    return errs


def _load(rel: str, sch: dict) -> list[dict]:
    from .validate import stub_index
    kind = stub_index()[rel]
    cid, k = kind.split(":")
    p = _base.stubs_dir() / rel
    fk = catalog.resolve(f"{cid}_{k}", p, sch)
    return [o for _, o in fileio.read(fk.format, p)[0]]


def check_lineage(sch: dict) -> tuple[list[str], dict]:
    errs, claims = [], {}
    for rel in ("C09/correspondences.sssom.tsv", "complex.sssom.tsv", "C20/claims.jsonl"):
        recs = _load(rel, sch)
        errs += [f"I5 {rel}: {e}" for e in rules.claim_lineage(recs, lambda i, r: f"[{i + 1}]")]
        for r in recs:
            claims.setdefault(r["claim_id"], set()).add(r["claim_version_id"])
    return errs, claims


def check_refs(sch: dict, claims: dict) -> list[str]:
    errs = []

    def known(cid: str) -> bool:
        return all(part in claims for part in cid.split("∘"))
    for rel in ("C11/cases.jsonl", "C12/outcomes.jsonl", "C12/readback.jsonl", "C21/verdicts.jsonl",
                "C23/translation_trace.jsonl"):
        for r in _load(rel, sch):
            c = r.get("claim_id")
            if c and not known(c):
                errs.append(f"I6 {rel}: claim_id {c} não existe nas alegações dos stubs")
            v = r.get("claim_version_id")
            if v and "∘" not in c and v not in claims.get(c, set()):
                errs.append(f"I6 {rel}: claim_version_id {v} não existe")
    return errs


def selftest(sch: dict) -> list[str]:
    errs = []
    base = _load("C20/claims.jsonl", sch)
    probes = {
        "claim_id muda entre versões": lambda r: (r[1].update({"claim_id": "ANC-aws-0099",
                                                                "claim_version_id": "ANC-aws-0099@2"})),
        "evento reusado entre versões": lambda r: r[1].update({"event_id": r[0]["event_id"]}),
        "versão de outra alegação": lambda r: r[1].update({"claim_version_id": "ANC-aws-0002@2"}),
        "supersedes não anterior": lambda r: r[1].update({"supersedes": "ANC-aws-0001@3"}),
    }
    for name, f in probes.items():
        r = copy.deepcopy(base)
        f(r)
        if not rules.claim_lineage(r, lambda i, x: f"[{i + 1}]"):
            errs.append(f"I7 autoteste: '{name}' passou e devia reprovar")
    if rules.claim_lineage(base, lambda i, x: f"[{i + 1}]"):
        errs.append("I7 autoteste: controle (stub sem mutação) reprovou")
    return errs


def main(argv=None) -> int:
    sch = catalog.schemas()
    e1, n = check_schemas(sch)
    e2 = check_patterns()
    e3, claims = check_lineage(sch)
    e4 = check_refs(sch, claims)
    e5 = selftest(sch)
    errs = e1 + e2 + e3 + e4 + e5
    rep = {"at": _base.now(), "fields_checked": n, "claims_in_stubs": {k: sorted(v) for k, v in claims.items()},
           "patterns": {"claim_id": P_CLAIM_ID, "claim_version_id": P_CLAIM_VERSION_ID, "event_id": P_EVENT_ID},
           "errors": errs}
    d = _base.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "claim_ids.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for e in errs:
        print(f"  FAIL {e}")
    print(f"[{_base.now()}] claim_ids: {n} campo(s) de id em {len(sch)} schemas; {len(claims)} alegação(ões) nos stubs; "
          f"{len(errs)} erro(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
