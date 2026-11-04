"""Comparação de decomposição (E2): unidades esperadas (gabarito) × unidades produzidas pelo pipeline.

Unidade: {"domain_unit", "kind", "accepted_kinds"?, "parent", "occurrence": {...}, "tf": {...}}. Duas unidades
são a mesma se domain_unit, parent e occurrence coincidem; a camada Terraform (tf) é ignorada, para que regra
embutida e regra em recurso separado contem como a mesma unidade (CMT-FW-P01).
"""
from __future__ import annotations

import json
from pathlib import Path

DISPUTES_PATH = Path(__file__).resolve().parent.parent / "disputes.json"
_KIND_FACTS = {"lifecycle_controller", "owner"}


def _load() -> list:
    if not DISPUTES_PATH.is_file():
        return []
    return [d for d in json.loads(DISPUTES_PATH.read_text(encoding="utf-8"))["disputes"] if d["fact"] in _KIND_FACTS]


def _resolved(d: dict) -> bool:
    return str(d.get("status", "")).startswith("resolvida")


def disputes() -> dict:
    """Disputas ABERTAS spec x doc do SERVICE-EVIDENCE na fatia, por tipo Terraform (só as que decidem o tipo)."""
    out = {}
    for d in _load():
        if not _resolved(d):
            out.setdefault(d["terraform_resource_type"], []).append(d)
    return out


def resolutions() -> dict:
    """Disputas resolvidas por observação (R2 do PREREG), por tipo Terraform."""
    out = {}
    for d in _load():
        if _resolved(d):
            out.setdefault(d["terraform_resource_type"], []).append(d)
    return out


def apply_disputes(units: list) -> list:
    """Unidade cujo tipo depende de fato em disputa aberta vira UNKNOWN, com o motivo; disputa resolvida por
    observação deixa o tipo do lado vencedor e registra a resolução. O gabarito retido também passa por aqui
    (a disputa é da evidência, não da fixture)."""
    disp, res = disputes(), resolutions()
    out = []
    for u in units:
        t = u.get("tf", {}).get("resource_type")
        ds = disp.get(t)
        if ds and u["kind"] != "UNKNOWN":
            u = dict(u, kind="UNKNOWN", accepted_kinds=["UNKNOWN"],
                     unknown=sorted({d["fact"] for d in ds}),
                     dispute=[{"fact": d["fact"], "doc": d["doc"], "spec": d["spec"], "evidence": d["evidence"]} for d in ds],
                     kind_without_dispute=u["kind"])
        elif res.get(t) and u["kind"] != "UNKNOWN":
            rs = res[t]
            spec_parent = all(d.get("resolved_to") == "spec" and d["spec"].get("kind") == "parent" for d in rs)
            if spec_parent and u["kind"] == "COMPONENT":
                u = dict(u, dispute_resolved=[{"fact": d["fact"], "resolved_to": d["resolved_to"],
                                               "observation_id": d["observation_id"], "resolved_at": d.get("resolved_at")} for d in rs],
                         evidence=list(u["evidence"]) + [d["observation_id"] for d in rs])
            else:
                u = dict(u, kind="UNKNOWN", accepted_kinds=["UNKNOWN"], unknown=sorted({d["fact"] for d in rs}),
                         dispute=[{"fact": d["fact"], "resolved_to": d.get("resolved_to"), "note": "resolução não casa com o tipo do gabarito"} for d in rs],
                         kind_without_dispute=u["kind"])
        out.append(u)
    return out


def _key(u: dict) -> str:
    return json.dumps([u["domain_unit"], u.get("parent"), u.get("occurrence", {})], sort_keys=True)


def normalize(units: list) -> dict:
    """Chave -> unidade; repetição da mesma chave ganha sufixo #n (a security list aceita regras idênticas
    sem id, SE-oci-xalogqqyvlj5ctiu: a ocorrência é contada, não fundida)."""
    out, seen = {}, {}
    for u in units:
        k = _key(u)
        seen[k] = seen.get(k, 0) + 1
        out[k if seen[k] == 1 else f"{k}#{seen[k]}"] = u
    return out


def compare(expected: list, actual: list) -> dict:
    e, a = normalize(apply_disputes(expected)), normalize(actual)
    missing = sorted(set(e) - set(a))
    extra = sorted(set(a) - set(e))
    wrong_kind = []
    for k in sorted(set(e) & set(a)):
        acc = e[k].get("accepted_kinds") or [e[k]["kind"]]
        if a[k]["kind"] not in acc:
            wrong_kind.append({"unit": k, "expected": acc, "actual": a[k]["kind"]})
    return {"equal": not (missing or extra or wrong_kind), "missing": missing, "extra": extra,
            "wrong_kind": wrong_kind}


def invariant(units_a: list, units_b: list) -> bool:
    """As duas embalagens dão as mesmas unidades a menos da camada Terraform?"""
    strip = lambda us: sorted((_key(u), u["kind"]) for u in us)
    return strip(units_a) == strip(units_b)
