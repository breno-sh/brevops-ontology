"""Aplica a biblioteca de grão COMO ESTÁ à fatia sto e mede o que as entradas do módulo permitem.

Não conserta nada: o que a biblioteca devolve (inclusive erro) é o resultado. Três medidas:
  1. grain: bo.grain.schema.decompose_schema com bo.grain.evidence.C25Adapter sobre o service_evidence.jsonl real,
     por provedor; registra o desfecho e, por candidato e campo, o que a consolidação da biblioteca devolve;
  2. shape: quantos fatos de grão do C25 (identity, import_key, lifecycle_controller, owner, effective_scope)
     seguem a convenção de leitura do GRAIN.html e quantos vêm na forma por aspecto, na fatia e no corpus;
  3. sentences: quantos átomos da fatia têm, nas entradas do glossarista, uma sentença PUBLICADA da documentação
     do próprio átomo (a exigência do GLOSSARY_BRIEF para ancorar), por papel e por faceta.

Uso: python -I -m bo.pilot_sto_gloss.diagnose [--check]   (--check: refaz e compara com o arquivo gravado)
Saída: $BO_REPO/results/PILOT-STO-GLOSS/pilot_findings.json
"""

from __future__ import annotations

import collections
import json
import sys

from . import common as C

GRAIN_FACTS = ("identity", "import_key", "lifecycle_controller", "owner", "effective_scope")

# Faceta da fatia por tipo separado; nos tipos contêiner, por palavra do caminho. É só uma régua de diagnóstico
# para contar cobertura de sentença (não é decisão de grão nem de conceito).
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


def atoms_from_roles(roles: dict[str, dict]) -> list[dict]:
    """Átomos no formato que bo.grain.schema.candidates_from_atoms lê, refeitos do atom_id do C04.

    O C01 (SCHEMA-*/atoms.jsonl) não é entrada deste módulo nem está na lista de leitura do glossarista; o caminho
    do átomo dá os blocos (todo prefixo é bloco; a medida conta os prefixos que também são átomos), mas não o
    nesting_mode, que vai como UNKNOWN (as regras de grão não leem cardinalidade)."""
    out = []
    for aid in sorted(roles):
        prov, rt, path = aid.split(":", 2)
        parts = path.split(".")
        out.append({"atom_id": aid, "provider": prov, "resource_type": rt, "path": path,
                    "block_path": [{"block": b, "nesting_mode": "UNKNOWN"} for b in parts[:-1]]})
    return out


def prefix_collisions(roles: dict[str, dict]) -> int:
    ids = set(roles)
    n = 0
    for aid in ids:
        prov, rt, path = aid.split(":", 2)
        parts = path.split(".")
        if any(f"{prov}:{rt}:{'.'.join(parts[:i])}" in ids for i in range(1, len(parts))):
            n += 1
    return n


def grain_as_is(roles: dict[str, dict], evidence: list[dict]) -> dict:
    from bo.grain import evidence as E
    from bo.grain import rules as R
    from bo.grain import schema as S

    rs = R.load(C.repo() / "grain" / "grain_rules.yaml")
    atoms = atoms_from_roles(roles)
    out = {"library": "bo.grain.schema.decompose_schema + bo.grain.evidence.C25Adapter (sem alteração)",
           "atoms_reconstructed_from": "ROLES atom_id (C01 fora das entradas)",
           "prefix_collisions": prefix_collisions(roles), "providers": {}}
    for prov in sorted(C.SLICE):
        patoms = [a for a in atoms if a["provider"] == prov]
        precs = [r for r in evidence if r.get("provider") == prov]
        cands = S.candidates_from_atoms(patoms)
        rep = {"candidates": len(cands), "top_level": sum(1 for c in cands if c.parent is None),
               "nested_blocks": sum(1 for c in cands if c.parent is not None), "evidence_records": len(precs)}
        try:
            adapter = E.C25Adapter(precs)
        except E.EvidenceError as e:
            rep.update(outcome="ADAPTER_ERROR", error=str(e)[:200])
            out["providers"][prov] = rep
            continue
        fields = collections.Counter()
        cand_err = 0
        for c in cands:
            ev = adapter.evidence(c.cid)
            bad = False
            for f in E.FIELDS:
                try:
                    st = ev.fact(f).state
                except E.EvidenceError:
                    st = "EVIDENCE_ERROR"
                    bad = True
                fields[f"{f}:{st}"] += 1
            cand_err += bad
        rep["candidates_with_evidence_error"] = cand_err
        rep["candidates_without_any_claim"] = sum(1 for c in cands if c.cid not in adapter.by_cid)
        rep["nested_blocks_with_any_claim"] = sum(1 for c in cands if c.parent is not None and c.cid in adapter.by_cid)
        rep["field_states"] = dict(sorted(fields.items()))
        try:
            res = S.decompose_schema(cands, adapter, rs)
            units, catoms = S.to_c19(res, {a: r["role"] for a, r in roles.items()})
            rep.update(outcome="DECIDED", units=len(units), atoms=len(catoms),
                       kinds=dict(collections.Counter(u["kind"] for u in units)),
                       rules=dict(collections.Counter(u["rule_applied"] for u in units)))
        except E.EvidenceError as e:
            rep.update(outcome="EVIDENCE_ERROR", error=str(e)[:200])
        out["providers"][prov] = rep
    return out


def _conforms(fk: str, val) -> bool:
    """A forma que o C25Adapter da biblioteca aceita (GRAIN.html, seção Adaptadores)."""
    if fk in ("lifecycle_controller", "owner", "effective_scope"):
        if isinstance(val, str):
            return True
        return isinstance(val, dict) and "kind" in val
    return isinstance(val, dict) and val.get("status") in ("present", "absent")


def shape(records) -> dict:
    total = conf = with_block = unknown = 0
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
        if _conforms(fk, v):
            conf += 1
        if isinstance(v, dict):
            aspects[f"{fk}/{v.get('aspect')}"] += 1
            with_block += "block_path" in v
    return {"grain_fact_records": total, "status_unknown": unknown, "stated": total - unknown,
            "stated_in_grain_convention": conf, "with_block_path": with_block,
            "stated_by_aspect": dict(sorted(aspects.items()))}


def sentences(roles: dict[str, dict], evidence: list[dict]) -> dict:
    own = collections.defaultdict(set)   # atom_id -> níveis das sentenças do próprio átomo
    for r in evidence:
        v = r.get("value")
        if not isinstance(v, dict) or not v.get("attribute"):
            continue
        aid = f"{r['provider']}:{r['terraform_resource_type']}:{v['attribute']}"
        if aid in roles and r.get("doc"):
            own[aid].add(r.get("level"))
    by_role = collections.defaultdict(lambda: [0, 0, 0])
    by_facet = collections.defaultdict(lambda: [0, 0, 0])
    by_prov = collections.defaultdict(lambda: [0, 0, 0])
    for aid, r in roles.items():
        lv = own.get(aid, set())
        pub = "published" in lv
        anyl = bool(lv)
        for tab, key in ((by_role, r["role"]), (by_prov, aid.split(":")[0])):
            tab[key][0] += 1
            tab[key][1] += pub
            tab[key][2] += anyl
        if r["role"] == "CONFIG":
            f = facet_of(aid)
            by_facet[f][0] += 1
            by_facet[f][1] += pub
            by_facet[f][2] += anyl

    def fmt(t):
        return {k: {"atoms": v[0], "own_published_sentence": v[1], "own_sentence_any_level": v[2]}
                for k, v in sorted(t.items())}

    return {"rule": "GLOSSARY_BRIEF G2: ancorar só com sentença da documentação do PRÓPRIO átomo, na tag fixada",
            "source_in_inputs": "SERVICE-EVIDENCE value.attribute + doc (único texto de documentação nas entradas)",
            "atoms": len(roles), "by_role": fmt(by_role), "config_by_facet": fmt(by_facet),
            "by_provider": fmt(by_prov), "facet_rule": "diagnóstico: tipo separado ou palavra do caminho"}


def build() -> dict:
    roles = C.slice_roles()
    ev = C.slice_evidence()
    corpus = C.iter_jsonl(C.data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl")
    return {
        "schema": "bo.pilot_findings/1", "module": C.MODULE,
        "slice": {p: sorted(ts) for p, ts in C.SLICE.items()}, "excluded": C.EXCLUDED,
        "slice_types": len(C.slice_types()), "slice_atoms": len(roles), "slice_evidence_records": len(ev),
        "grain": grain_as_is(roles, ev),
        "c25_shape": {"slice": shape(ev), "corpus": shape(corpus)},
        "sentences": sentences(roles, ev),
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = [a for a in argv if a != C.MODULE]
    rep = build()
    path = C.results_dir() / "pilot_findings.json"
    if "--check" in argv:
        if not path.is_file():
            print(f"FALHA: {path} ausente")
            return 1
        old = json.loads(path.read_text(encoding="utf-8"))
        old.pop("generated_at", None)
        if old != rep:
            print("FALHA: pilot_findings.json não é o que as entradas dão hoje (regere sem --check)")
            return 1
        print("OK: pilot_findings.json regenerado idêntico")
        return 0
    rep["generated_at"] = C.now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(C.dump_json(rep), encoding="utf-8")
    g = rep["grain"]["providers"]
    print(f"[{rep['generated_at']}] grão como está: " + "; ".join(f"{p}={v['outcome']}" for p, v in g.items()))
    s = rep["c25_shape"]["corpus"]
    print(f"C25 no corpus: {s['stated_in_grain_convention']}/{s['stated']} fatos de grão afirmados na convenção "
          f"do GRAIN; {s['with_block_path']} com block_path")
    cf = rep["sentences"]["by_role"].get("CONFIG", {})
    print(f"sentença própria publicada: {cf.get('own_published_sentence')}/{cf.get('atoms')} átomos CONFIG da fatia")
    print(f"gravado: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
