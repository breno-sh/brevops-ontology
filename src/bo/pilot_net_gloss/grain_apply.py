"""Aplicação mecânica da biblioteca de grão (bo.grain) aos tipos da fatia net.

Nada de regra local: candidatos saem dos átomos (C05/C04 da UNITS e da ROLES, mesmo atom_id do C01), a evidência
sai do service_evidence.jsonl pelo C25Adapter da biblioteca e as regras são as de grain/grain_rules.yaml.

Única intervenção, sempre no sentido conservador: uma alegação que a convenção de leitura do C25Adapter não
interpreta (normalize_claim levanta EvidenceError, porque o SERVICE-EVIDENCE grava `value` por aspecto e não na
forma {status, key_fields, ...} que o GRAIN.html descreve) vira alegação desconhecida (status unknown, com a mesma
fonte). Isso só pode tirar evidência, nunca acrescentar; cada troca fica no livro grain_unreadable.jsonl e a
mudança de contrato proposta está em results/PILOT-NET-GLOSS/CONTRACT_CHANGE.txt.
"""

from __future__ import annotations

import copy

from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.evidence import FIELDS, C25Adapter, EvidenceError, FixtureAdapter, normalize_claim

from . import slice as SL


def atoms_c01_like(atom_ids: list[str]) -> list[dict]:
    """Forma mínima do C01 que o candidates_from_atoms lê: o caminho de blocos sai dos pontos do atom_id
    (no C01, ponto separa blocos). O modo de aninhamento não entra em nenhuma decisão do motor."""
    out = []
    for aid in sorted(atom_ids):
        prov, rt, path = aid.split(":", 2)
        parts = path.split(".")
        out.append({"atom_id": aid, "provider": prov, "resource_type": rt, "path": path,
                    "block_path": [{"block": b, "nesting_mode": "unknown"} for b in parts[:-1]]})
    return out


def sanitized_table(records: list[dict]) -> tuple[dict, list[dict]]:
    ad = C25Adapter(records)
    table = copy.deepcopy(ad.by_cid)
    ledger = []
    for cid in sorted(table):
        ent = table[cid]
        for fld in FIELDS:
            new = []
            for c in ent.get(fld, []):
                try:
                    if not (isinstance(c, dict) and c.get("status") == "contradictory"):
                        normalize_claim(fld, c)
                    new.append(c)
                except EvidenceError as e:
                    src = c.get("source") if isinstance(c, dict) else None
                    new.append({"status": "unknown", "source": src} if src else {"status": "unknown"})
                    ledger.append({"candidate": cid, "field": fld, "evidence_id": (src or {}).get("ref"),
                                   "reason": f"convenção de leitura do C25Adapter não interpreta: {e}",
                                   "value_keys": sorted(k for k in c if k != "source") if isinstance(c, dict) else []})
            if fld in ent:
                ent[fld] = new
    return table, ledger


def decompose(se_records: list[dict], atom_ids: list[str], atom_roles: dict,
              schema_atoms: list[dict] | None = None) -> dict:
    """schema_atoms: átomos C01 reais da fatia (com o modo de aninhamento); sem eles, a forma mínima de atoms_c01_like."""
    rs = R.load()
    recs = [r for r in se_records if r.get("terraform_resource_type") in set(SL.all_types())]
    table, ledger = sanitized_table(recs)
    adapter = FixtureAdapter(table)
    units, atoms = [], []
    by_prov: dict[str, list[str]] = {}
    for aid in atom_ids:
        by_prov.setdefault(aid.split(":", 1)[0], []).append(aid)
    for prov in SL.PROVIDERS:
        src = ([a for a in schema_atoms if a.get("provider") == prov] if schema_atoms
               else atoms_c01_like(by_prov.get(prov, [])))
        cands = S.candidates_from_atoms(src)
        res = S.decompose_schema(cands, adapter, rs)
        u, a = S.to_c19(res, atom_roles)
        units += u
        atoms += a
    return {"units": units, "atoms": atoms, "ledger": ledger, "rules_version": rs.version}
