"""Grão da fatia sto pela biblioteca de grão, como está (GLOSSARY_BRIEF G5: mecânico, sem reclassificar).

Entrada: átomos C01 dos tipos da fatia ($BO_DATA/SCHEMA-*/atoms.jsonl), service_evidence.jsonl (C25) e papéis
(C04). Caminho: bo.grain.schema.candidates_from_atoms -> bo.grain.evidence.C25Adapter (tradução por aspecto do
GRAIN 0.1.1) -> bo.grain.schema.decompose_schema -> bo.grain.schema.to_c19. UNKNOWN fica UNKNOWN, com o
missing_evidence e os motivos que a biblioteca devolve.
"""

from __future__ import annotations

import collections

from . import common as C

SCHEMA_DIR = {"aws": "SCHEMA-AWS", "google": "SCHEMA-GCP", "azurerm": "SCHEMA-AZURE", "oci": "SCHEMA-OCI"}
CONTAINER = {"aws": "aws_s3_bucket", "google": "google_storage_bucket", "azurerm": "azurerm_storage_container",
             "oci": "oci_objectstorage_bucket"}


def load_atoms(provider: str) -> list[dict]:
    types = set(C.SLICE[provider])
    out = []
    for a in C.iter_jsonl(C.data_root() / SCHEMA_DIR[provider] / "atoms.jsonl"):
        if a.get("resource_type") in types:
            out.append(a)
    return out


def run(roles: dict[str, dict] | None = None, evidence: list[dict] | None = None, atoms_by_provider=None) -> dict:
    from bo.grain import rules as R
    from bo.grain import schema as S
    from bo.grain.evidence import C25Adapter

    rs = R.load(C.repo() / "grain" / "grain_rules.yaml")
    roles = roles if roles is not None else C.slice_roles()
    evidence = evidence if evidence is not None else C.slice_evidence()
    atom_roles = {a: r["role"] for a, r in roles.items()}
    units, atoms, report = [], [], {}
    for prov in sorted(C.SLICE):
        patoms = atoms_by_provider[prov] if atoms_by_provider is not None else load_atoms(prov)
        cands = S.candidates_from_atoms(patoms)
        recs = [r for r in evidence if r.get("provider") == prov]
        ad = C25Adapter(recs, candidates={c.cid for c in cands})
        res = S.decompose_schema(cands, ad, rs)
        u, a = S.to_c19(res, atom_roles)
        units += u
        atoms += a
        decs = res.decisions

        def brief(cid):
            d = decs.get(cid)
            if d is None:
                return None
            return {"grain": d.grain, "rule": d.rule, "missing": list(d.missing),
                    "identity_class": d.identity.cls, "reasons": sorted(set(ad.reasons.get(cid, [])))}

        report[prov] = {
            "atoms": len(patoms), "candidates": len(cands), "evidence_records": len(recs),
            "grains": dict(sorted(collections.Counter(d.grain for d in decs.values()).items())),
            "rules": dict(sorted(collections.Counter(d.rule for d in decs.values()).items())),
            "missing": dict(sorted(collections.Counter(m for d in decs.values() for m in d.missing).items())),
            "container": {"type": CONTAINER.get(prov), **(brief(CONTAINER.get(prov)) or {"grain": "ABSENT"})},
            "top_level": {t: brief(t) for t in sorted(C.SLICE[prov])},
            "units": len(u), "canonical_atoms": len(a),
        }
    return {"units": units, "atoms": atoms, "report": report}
