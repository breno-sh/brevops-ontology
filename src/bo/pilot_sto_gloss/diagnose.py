"""Medidas do piloto sto sobre as entradas atuais (sem consertar nada): o que a biblioteca de grão decide e o que
a documentação permite ancorar.

  grain     por provedor: grãos, regras, campos que faltam, decisão do contêiner e os motivos que o adaptador C25
            devolve (bo.pilot_sto_gloss.decompose, que é a biblioteca como está);
  c25_shape fatos de grão afirmados por aspecto e com block_path, na fatia;
  sentences átomos da fatia com fato de descrição com fonte nos DOCS-* (exigência do GLOSSARY_BRIEF para ancorar),
            por papel e por faceta (régua de diagnóstico: tipo separado ou palavra do caminho).

Uso: python -I -m bo.pilot_sto_gloss.diagnose [--check]
Saída: $BO_REPO/results/PILOT-STO-GLOSS/pilot_findings.json
"""

from __future__ import annotations

import collections
import json
import sys

from . import common as C
from . import decompose as DEC

GRAIN_FACTS = ("identity", "import_key", "lifecycle_controller", "owner", "effective_scope")

FACET_BY_TYPE = {
    "aws_s3_bucket_versioning": "versioning",
    "aws_s3_bucket_lifecycle_configuration": "lifecycle",
    "aws_s3_bucket_server_side_encryption_configuration": "encryption",
    "aws_s3_bucket_public_access_block": "public_access",
    "aws_s3_account_public_access_block": "public_access",
    "aws_s3_bucket_acl": "public_access",
    "aws_s3_bucket_policy": "public_access",
    "aws_s3_bucket_ownership_controls": "public_access",
    "google_storage_bucket_acl": "public_access",
    "google_storage_bucket_access_control": "public_access",
    "google_storage_bucket_iam_policy": "public_access",
    "google_storage_bucket_iam_binding": "public_access",
    "google_storage_bucket_iam_member": "public_access",
    "azurerm_storage_management_policy": "lifecycle",
    "azurerm_storage_account_customer_managed_key": "encryption",
    "azurerm_storage_encryption_scope": "encryption",
    "oci_objectstorage_object_lifecycle_policy": "lifecycle",
}
FACET_WORDS = (
    ("versioning", ("version",)),
    ("lifecycle", ("lifecycle", "expiration", "transition", "noncurrent", "delete_after", "tier")),
    ("encryption", ("encrypt", "kms", "sse", "key_vault", "customer_managed_key", "cmk")),
    ("public_access", ("public", "acl", "access_type", "policy", "iam", "uniform_bucket", "nested_items")),
)


def facet_of(atom_id: str) -> str:
    _, rt, path = atom_id.split(":", 2)
    if rt in FACET_BY_TYPE:
        return FACET_BY_TYPE[rt]
    low = path.lower()
    for facet, words in FACET_WORDS:
        if any(w in low for w in words):
            return facet
    return "other"


def shape(records) -> dict:
    total = unknown = with_block = 0
    aspects = collections.Counter()
    for r in records:
        fk = r.get("fact_kind")
        if fk not in GRAIN_FACTS:
            continue
        total += 1
        if r.get("status") == "unknown":
            unknown += 1
            continue
        v = r.get("value")
        if isinstance(v, dict):
            aspects[f"{fk}/{v.get('aspect')}"] += 1
        with_block += bool(r.get("block_path") or (isinstance(v, dict) and v.get("block_path")))
    return {"grain_fact_records": total, "status_unknown": unknown, "stated": total - unknown,
            "with_block_path": with_block, "stated_by_aspect": dict(sorted(aspects.items()))}


def sentences(roles: dict[str, dict]) -> dict:
    from .build import doc_descriptions

    descs = doc_descriptions(set(roles))
    tabs = {"by_role": collections.defaultdict(lambda: [0, 0]), "config_by_facet": collections.defaultdict(lambda: [0, 0]),
            "by_provider": collections.defaultdict(lambda: [0, 0])}
    for aid, r in roles.items():
        has = aid in descs
        keys = [("by_role", r["role"]), ("by_provider", aid.split(":")[0])]
        if r["role"] == "CONFIG":
            keys.append(("config_by_facet", facet_of(aid)))
        for t, k in keys:
            tabs[t][k][0] += 1
            tabs[t][k][1] += has
    return {"rule": "GLOSSARY_BRIEF G2: ancorar só com sentença da documentação do PRÓPRIO átomo, na tag fixada",
            "source": "DOCS-*/docs_facts.jsonl, fact_kind description, status stated, com source",
            "atoms": len(roles),
            **{t: {k: {"atoms": v[0], "with_own_description": v[1]} for k, v in sorted(tab.items())}
               for t, tab in tabs.items()}}


def build() -> dict:
    roles = C.slice_roles()
    ev = C.slice_evidence()
    dec = DEC.run(roles, ev)
    return {"schema": "bo.pilot_findings/2", "module": C.MODULE,
            "slice": {p: sorted(ts) for p, ts in C.SLICE.items()}, "excluded": C.EXCLUDED,
            "slice_types": len(C.slice_types()), "slice_atoms": len(roles), "slice_evidence_records": len(ev),
            "grain": dec["report"], "c25_shape": shape(ev), "sentences": sentences(roles)}


def main(argv=None) -> int:
    argv = [a for a in (sys.argv[1:] if argv is None else argv) if a != C.MODULE]
    rep = build()
    path = C.results_dir() / "pilot_findings.json"
    if "--check" in argv:
        if not path.is_file():
            print(f"FALHA: {path} ausente")
            return 1
        old = json.loads(path.read_text(encoding="utf-8"))
        old.pop("generated_at", None)
        if old != json.loads(json.dumps(rep)):
            print("FALHA: pilot_findings.json não é o que as entradas dão hoje (regere sem --check)")
            return 1
        print("OK: pilot_findings.json regenerado idêntico")
        return 0
    rep["generated_at"] = C.now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(C.dump_json(rep), encoding="utf-8")
    for p, r in rep["grain"].items():
        c = r["container"]
        print(f"[{rep['generated_at']}] {p}: {r['candidates']} candidatos, grãos {r['grains']}; contêiner "
              f"{c['type']} = {c['grain']} (falta {c.get('missing')})")
    cf = rep["sentences"]["by_role"].get("CONFIG", {})
    print(f"descrição própria com fonte: {cf.get('with_own_description')}/{cf.get('atoms')} átomos CONFIG")
    print(f"gravado: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
