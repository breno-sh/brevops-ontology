"""Aplicação mecânica da biblioteca de grão (bo.grain, regras 0.1.1) aos tipos da fatia net.

Nada de regra local nem de adaptador próprio: é o mesmo caminho do bo.grain.realdata (átomos C01 do SCHEMA-*,
C25Adapter por aspecto com os candidatos do provedor, decompose_schema, to_c19), mais os papéis do C04 nos
átomos. O que falta no SERVICE-EVIDENCE sai como falta; os motivos das alegações UNKNOWN vêm do próprio
adaptador (ad.reasons) e vão para grain_unknown_reasons.jsonl.
"""

from __future__ import annotations

from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.evidence import C25Adapter

from . import slice as SL


def decompose(se_records: list[dict], schema_atoms: list[dict], atom_roles: dict) -> dict:
    rs = R.load()
    units, atoms, reasons, adapter_errors = [], [], [], []
    for prov in SL.PROVIDERS:
        types = set(SL.SLICE_TYPES[prov])
        patoms = [a for a in schema_atoms if a.get("provider") == prov and a.get("resource_type") in types]
        cands = S.candidates_from_atoms(patoms)
        recs = [r for r in se_records if r.get("provider") == prov]
        ad = C25Adapter(recs, candidates={c.cid for c in cands})
        res = S.decompose_schema(cands, ad, rs)
        u, a = S.to_c19(res, atom_roles)
        units += u
        atoms += a
        for cid in sorted(res.decisions):
            for why in sorted(set(ad.reasons.get(cid, []))):
                reasons.append({"provider": prov, "candidate": cid, "reason": why})
    return {"units": units, "atoms": atoms, "ledger": reasons, "rules_version": rs.version}


def by_unit(units: list[dict]) -> dict:
    return {u["unit_id"]: u for u in units}
