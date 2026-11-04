"""Decomposição sobre DADO REAL (átomos C01 do SCHEMA-* e service_evidence.jsonl do SERVICE-EVIDENCE).

Uso: python -I -m bo.grain.realdata [--slice sto] [--json ARQ]
Lê só os tipos pedidos (a fatia sto por padrão, a mesma do PILOT-STO-GLOSS), roda decompose_schema com o
adaptador C25 por aspecto e devolve, por provedor, o grão de cada candidato, a regra, o que falta e os motivos
das alegações UNKNOWN. Nunca conserta evidência: o que falta no SERVICE-EVIDENCE sai como falta.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from . import rules as R
from . import schema as S
from .common import data_root, dump_json, now, stamp
from .evidence import C25Adapter

STO_SLICE = {
    "aws": ["aws_s3_bucket", "aws_s3_bucket_versioning", "aws_s3_bucket_lifecycle_configuration",
            "aws_s3_bucket_server_side_encryption_configuration", "aws_s3_bucket_public_access_block",
            "aws_s3_account_public_access_block", "aws_s3_bucket_acl", "aws_s3_bucket_policy",
            "aws_s3_bucket_ownership_controls"],
    "google": ["google_storage_bucket", "google_storage_bucket_acl", "google_storage_bucket_access_control",
               "google_storage_bucket_iam_policy", "google_storage_bucket_iam_binding",
               "google_storage_bucket_iam_member"],
    "azurerm": ["azurerm_storage_account", "azurerm_storage_container", "azurerm_storage_management_policy",
                "azurerm_storage_account_customer_managed_key", "azurerm_storage_encryption_scope"],
    "oci": ["oci_objectstorage_bucket", "oci_objectstorage_object_lifecycle_policy",
            "oci_objectstorage_namespace_metadata"],
}
CONTAINER = {"aws": "aws_s3_bucket", "google": "google_storage_bucket", "azurerm": "azurerm_storage_container",
             "oci": "oci_objectstorage_bucket"}
SCHEMA_DIR = {"aws": "SCHEMA-AWS", "google": "SCHEMA-GCP", "azurerm": "SCHEMA-AZURE", "oci": "SCHEMA-OCI"}


def load_atoms(provider: str, types: set[str]) -> list[dict]:
    p = data_root() / SCHEMA_DIR[provider] / "atoms.jsonl"
    out = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            # filtro barato antes do json: o tipo aparece literal na linha
            if not any(f'"{t}"' in line for t in types):
                continue
            a = json.loads(line)
            if a.get("resource_type") in types:
                out.append(a)
    return out


def load_evidence(path: Path | None = None) -> list[dict]:
    p = path or data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def run(slice_types: dict | None = None, records: list[dict] | None = None, rs=None) -> dict:
    rs = rs or R.load()
    slice_types = slice_types or STO_SLICE
    records = records if records is not None else load_evidence()
    out = {"schema": "bo.grain.realdata/1", "generated_at": now(), "providers": {}}
    for prov, types in sorted(slice_types.items()):
        atoms = load_atoms(prov, set(types))
        cands = S.candidates_from_atoms(atoms)
        recs = [r for r in records if r.get("provider") == prov]
        ad = C25Adapter(recs, candidates={c.cid for c in cands})
        res = S.decompose_schema(cands, ad, rs)
        units, c19_atoms = S.to_c19(res)
        dec = {}
        for cid, d in sorted(res.decisions.items()):
            dec[cid] = {"grain": d.grain, "rule": d.rule, "missing": d.missing, "identity_class": d.identity.cls,
                        "reasons": sorted(set(ad.reasons.get(cid, [])))}
        top = {c: dec.get(c) for c in types}
        out["providers"][prov] = {
            "types": len(types), "atoms": len(atoms), "candidates": len(cands), "evidence_records": len(recs),
            "grains": dict(Counter(d["grain"] for d in dec.values())),
            "rules": dict(Counter(d["rule"] for d in dec.values())),
            "missing": dict(Counter(m for d in dec.values() for m in d["missing"])),
            "container": {"type": CONTAINER[prov], **(dec.get(CONTAINER[prov]) or {"grain": "ABSENT_FROM_SCHEMA"})},
            "top_level": top, "nested_facet_like": {c: d for c, d in dec.items() if "." in c and d["grain"] == "FACET"},
            "c19_units": len(units), "c19_atoms": len(c19_atoms), "_units": units, "_atoms": c19_atoms,
            "out_of_domain": sorted(res.out_of_domain), "out_of_domain_atoms": len(res.out_of_domain_atoms),
            "virtual_atoms": len(res.virtual_atoms), "_res": res,
        }
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rep = run()
    for prov, p in rep["providers"].items():
        c = p["container"]
        print(stamp(f"{prov}: {p['candidates']} candidato(s), {p['evidence_records']} fato(s); grãos {p['grains']}; "
                    f"contêiner {c['type']} = {c['grain']} {c.get('missing')}"))
    if "--json" in argv:
        dst = Path(argv[argv.index("--json") + 1])
        slim = {k: v for k, v in rep.items() if k != "providers"}
        slim["providers"] = {pv: {k: v for k, v in p.items() if not k.startswith("_")} for pv, p in
                             rep["providers"].items()}
        dst.write_text(dump_json(slim), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def block_pair_signature(res, cid):
    """Assinatura de um bloco/unidade para o E2 que desce ao bloco correspondente: grão, regra, classe e chave
    própria da identidade, kinds de ciclo de vida, dono e alcance, o que falta, e o grão do pai (o caminho do pai
    sai à parte, porque a embalagem embutida pode não ter o nível intermediário)."""
    d = res.decisions[cid]
    keyf = tuple(sorted(f for f in d.identity.key_fields if not res.nodes[cid].ev.field_map.get(f, {}).get("ref")))
    pg = res.decisions[d.parent].grain if d.parent in res.decisions else ("EXTERNAL" if d.parent else None)
    return {"grain": d.grain, "rule": d.rule, "identity_class": d.identity.cls, "key": keyf,
            "anonymous": d.identity.anonymous, "lifecycle": d.lifecycle["kind"], "owner": d.owner["kind"],
            "scope": d.scope["kind"], "missing": tuple(d.missing), "parent_grain": pg}


def e2_pair(res, inline: str, separate_top: str) -> dict:
    """Desce do recurso separado ao bloco que corresponde ao embutido. Correspondência só por evidência: o
    gêmeo (twin_type) do embutido aponta o tipo ou o bloco; se aponta o tipo e o tipo é FACET, o par é o bloco
    filho do tipo que tem o mesmo gêmeo declarado. Sem fato de correspondência, o par fica sem alvo (motivo)."""
    ev = res.nodes[inline].ev if inline in res.nodes else None
    twin = ev.twin if ev else None
    target, why = None, None
    if twin and twin in res.decisions:
        target = twin
    elif twin and twin.split(".")[0] == separate_top:
        why = f"gêmeo {twin} não é candidato"
    else:
        why = f"sem fato de correspondência (twin_type) do bloco {inline} para {separate_top} ou um bloco dele"
    out = {"inline": inline, "separate": target, "reason": why, "inline_sig": block_pair_signature(res, inline)}
    if target:
        out["separate_sig"] = block_pair_signature(res, target)
        out["equal"] = out["inline_sig"] == out["separate_sig"]
    return out
