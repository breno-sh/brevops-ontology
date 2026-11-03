"""Conjunto de mundos sintéticos e utilidades comuns aos gates (unknown_exit, priority, permutation)."""

from __future__ import annotations

import copy

from . import fixtures as F
from . import schema as S
from . import worlds as W
from .evidence import FixtureAdapter


def all_worlds() -> dict:
    out = {"bucket": {"provider": F.P, "schema": F.bucket_schema(), "evidence": F.bucket_evidence(),
                      "configs": F.bucket_configs()}}
    for name, fn in W.ALL.items():
        if name == "multi_owner":
            out["multi_owner"] = fn(True)
            out["multi_owner_nobinding"] = fn(False)
        else:
            out[name] = fn()
    return out


def run_schema(world: dict, rs, evidence: dict | None = None) -> S.SchemaResult:
    ev = world["evidence"] if evidence is None else evidence
    cands = S.candidates_from_tf_schema(world["provider"], world["schema"])
    return S.decompose_schema(cands, FixtureAdapter(ev), rs)


def evidence_slots(evidence: dict):
    """(cid, caminho até o dicionário de evidência) de todo candidato, inclusive grupos de atributos."""
    for cid in sorted(evidence):
        yield cid, (cid,)
        for g in sorted(evidence[cid].get("groups", {})):
            yield f"{cid}:{g}", (cid, "groups", g, "evidence")


def get_slot(evidence: dict, path: tuple) -> dict:
    cur = evidence
    for p in path:
        cur = cur[p]
    return cur


def contradiction(fld: str, claims: list) -> list:
    """Alegação afirmada que diverge das existentes (ou duas divergentes, se o campo estava vazio)."""
    tag = {"level": "derived", "ref": "FX-GRAIN-contra", "note": "alegação divergente injetada"}
    stated = [c for c in claims if c.get("status") not in ("unknown",)]
    first = stated[0] if stated else None
    if fld == "identity":
        alt = [{"status": "absent"}] if (first and first.get("status") == "present") else \
            [{"status": "present", "scope": "independent", "key_fields": ["x_contra"]}]
    elif fld in ("import_key", "element_name_key"):
        alt = [{"status": "absent"}] if (first and first.get("status") == "present") else \
            [{"status": "present", "fields": ["x_contra"]}]
    elif fld in ("lifecycle_controller", "owner"):
        alt = [{"kind": "parent" if (first and first.get("kind") == "self") else "self"}]
    elif fld == "effective_scope":
        alt = [{"kind": "global" if (first and first.get("kind") == "self") else "self"}]
    elif fld == "api_resource":
        alt = [{"status": "aspect" if (first and first.get("status") == "resource") else "resource",
                "label": "contra"}]
    else:
        raise KeyError(fld)
    out = copy.deepcopy(claims) + [dict(a, source=tag) for a in alt]
    if not stated:
        other = contradiction(fld, [dict(alt[0], source=tag)])
        out = other
    return out


def to_c25(world: dict, provider_version: str = "0.0.1") -> tuple[list[dict], dict]:
    """Converte a evidência neutra de um mundo em registros C25 (service_evidence.jsonl), na convenção de
    leitura do C25Adapter. Devolve (registros, extra): grupos de atributos não cabem no C25 e vão em extra."""
    recs, extra, k = [], {}, 0
    fk = {"identity": "identity", "import_key": "import_key", "lifecycle_controller": "lifecycle_controller",
          "owner": "owner", "effective_scope": "effective_scope"}
    for cid, ev in sorted(world["evidence"].items()):
        rt, _, bp = cid.partition(".")
        api = next((c for c in ev.get("api_resource", []) if c.get("status") != "unknown"), None)
        api_res = {"service": (api or {}).get("service") or "svc",
                   "resource": (api or {}).get("resource") or ((api or {}).get("label") or "unknown").title()
                   .replace(" ", "")}
        for fld, kind in fk.items():
            for n, cl in enumerate(ev.get(fld, [])):
                k += 1
                r = {"evidence_id": f"SE-fx-{world['provider']}-{k:04d}", "provider": world["provider"],
                     "pin": {"provider_version": provider_version}, "api_resource": api_res,
                     "terraform_resource_type": rt, "fact_kind": kind, "level": "published",
                     "citation": {"uri": "https://docs.example.org/fixture", "retrieved_at":
                                  "2026-11-03T02:00:00-03:00", "sentence": "frase sintética da fixture do GRAIN"}}
                if cl.get("status") == "unknown":
                    r["status"], r["unknown_reason"] = "unknown", "not_documented"
                else:
                    v = {kk: vv for kk, vv in cl.items() if kk != "source"}
                    if bp:
                        v["block_path"] = bp
                    if fld == "identity" and n == 0:
                        if api:
                            v["api_status"], v["label"] = api["status"], api.get("label")
                        if ev.get("element_name_key"):
                            nk = ev["element_name_key"][0]
                            v["element_name_key"] = nk.get("fields", []) if nk.get("status") == "present" else []
                        v["references"] = ev.get("references", {})
                        v["field_map"] = ev.get("field_map", {})
                        if ev.get("parent_role"):
                            v["parent_role"] = ev["parent_role"]
                    r["status"], r["value"] = "stated", v
                recs.append(r)
        if ev.get("groups"):
            extra[cid] = {"groups": ev["groups"]}
        if not ev.get("identity"):
            extra.setdefault(cid, {}).update({kk: ev[kk] for kk in ("field_map", "references", "api_resource",
                                                                   "element_name_key") if kk in ev})
    return recs, extra
