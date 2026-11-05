"""Evidência de serviço (C25, SERVICE-EVIDENCE) dos tipos da fatia, lida como o grão a pede.

Só conta a camada de API (layer = api) ou fato publicado com aspecto que diga dono, alcance ou ciclo de vida; o
que é só da camada Terraform (onde o código escreve, create/delete do provider) não decide dono nem controlador
(regra da v3: três camadas separadas). Disputa spec × doc (results/SERVICE-EVIDENCE/spec_disputes.json) vira
DISPUTED, nunca escolha silenciosa de um lado. Falta de fato vira UNKNOWN com o campo em missing_evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import common as C

FACTS = ("owner", "lifecycle_controller", "effective_scope", "identity")
# Regra de dono única (contrato do PILOT-STO-ORACLE 1.4.0, DEC-NO-API-OWNER; DIAG_T3 F6), reimplementada aqui só pelo
# contrato, sem importar o oráculo: o dono de uma configuração só é conhecido quando o SERVICE-EVIDENCE tem, para o
# tipo (ou o bloco de topo), fato de dono "stated" FORA da camada Terraform: camada de API ou identidade/pai do objeto
# remoto. Só camada Terraform (R-OWN-TOP, R-BLOCK-OWNER) ou nada documentado decide UNKNOWN. Atributo de topo é campo
# do objeto de API do próprio recurso e herda o fato do recurso.
OWNER_IDENTITY_RULES = ("R-OWN-AWS-IDENTITY", "R-OWN-AZ-PARENT", "R-OWN-GCP-PARENT", "R-OWN-DOC-PARENT")


@dataclass
class TypeEvidence:
    rtype: str
    owner_kinds: dict = field(default_factory=dict)       # kind -> [evidence_id], camada api
    owner_via: list = field(default_factory=list)         # atributos que levam ao pai
    parent_api: list = field(default_factory=list)        # tipos de API pai (R-OWN-AZ-PARENT)
    parent_tf_types: list = field(default_factory=list)   # tipos Terraform que realizam o pai
    owner_unknown: list = field(default_factory=list)
    account_scoped: bool = False                         # alcance do tipo = conta (type_scope)
    per_account_singleton: bool = False                  # cardinalidade 1 por conta
    life_kinds: dict = field(default_factory=dict)
    life_unknown: list = field(default_factory=list)
    scope_kinds: dict = field(default_factory=dict)
    type_scope: str | None = None
    identity_refs: dict = field(default_factory=dict)    # atributo -> tipo Terraform referenciado
    block_scope_parent: set = field(default_factory=set)  # caminhos de bloco com alcance = pai (api)
    disputed: dict = field(default_factory=dict)         # fato -> {doc, spec, evidence}
    owner_layers: dict = field(default_factory=dict)     # block_path ou None -> {"api": [...], "terraform": [...]}


class Evidence:
    def __init__(self, records: list[dict], disputes: list[dict], source: dict | None = None):
        self.source = source or {}
        self.types: dict[str, TypeEvidence] = {}
        for r in records:
            self._add(r)
        for d in disputes:
            te = self._te(d["terraform_resource_type"])
            te.disputed[d["fact"]] = {"doc": d.get("doc"), "spec": d.get("spec"), "evidence": d.get("evidence", [])}

    def _te(self, rtype: str) -> TypeEvidence:
        if rtype not in self.types:
            self.types[rtype] = TypeEvidence(rtype)
        return self.types[rtype]

    def _add(self, r: dict) -> None:
        te = self._te(r["terraform_resource_type"])
        fk, v, eid, bp = r["fact_kind"], r.get("value") or {}, r["evidence_id"], r.get("block_path")
        if fk == "owner" and r.get("status") == "stated":
            layer = "api" if (v.get("layer") == "api" or v.get("rule") in OWNER_IDENTITY_RULES) else (
                "terraform" if v.get("layer") == "terraform" else None)
            if layer:
                te.owner_layers.setdefault(bp or None, {"api": [], "terraform": []})[layer].append(eid)
        if bp:
            if fk == "effective_scope" and v.get("layer") == "api" and v.get("kind") == "parent":
                te.block_scope_parent.add(bp)
            return
        if r.get("status") == "unknown" or not v:
            if fk == "owner":
                te.owner_unknown.append(eid)
            elif fk == "lifecycle_controller":
                te.life_unknown.append(eid)
            return
        layer = v.get("layer")
        if fk == "owner":
            if layer == "api" and v.get("kind"):
                te.owner_kinds.setdefault(v["kind"], []).append(eid)
                te.owner_via += [x for x in (v.get("via") or []) if x not in te.owner_via]
            elif v.get("aspect") == "parent" and v.get("parent_api_type"):
                te.parent_api.append(v["parent_api_type"])
                te.parent_tf_types += [x for x in (v.get("parent_terraform_types") or []) if x not in te.parent_tf_types]
        elif fk == "lifecycle_controller":
            if layer == "api" and v.get("kind"):
                te.life_kinds.setdefault(v["kind"], []).append(eid)
        elif fk == "effective_scope":
            if v.get("aspect") == "type_scope" and v.get("scope"):
                te.type_scope = v["scope"]
                if v["scope"] == "account":
                    te.account_scoped = True
            elif layer == "api" and v.get("kind"):
                te.scope_kinds.setdefault(v["kind"], []).append(eid)
        elif fk == "identity":
            if v.get("aspect") == "reference_target" and v.get("resolved") and v.get("attribute"):
                te.identity_refs[v["attribute"]] = v["resolved"]
            if v.get("aspect") == "cardinality" and v.get("per") == "account" and v.get("max") == 1:
                te.per_account_singleton = True

    @classmethod
    def load(cls) -> "Evidence":
        p = C.data_root() / "SERVICE-EVIDENCE" / "service_evidence.jsonl"
        dp = C.repo() / "results" / "SERVICE-EVIDENCE" / "spec_disputes.json"
        types = {t for ts in C.SLICE_TYPES.values() for t in ts}
        needles = tuple(f'"terraform_resource_type":"{t}"' for t in types) + tuple(
            f'"terraform_resource_type": "{t}"' for t in types)
        recs = []
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if any(n in line for n in needles):
                    rec = json.loads(line)
                    if rec.get("terraform_resource_type") in types and rec.get("fact_kind") in FACTS:
                        recs.append(rec)
        disputes = [d for d in C.read_json(dp).get("disputes", []) if d.get("terraform_resource_type") in types]
        return cls(recs, disputes, source={"service_evidence": C.portable(p), "service_evidence_sha256": C.sha256_file(p),
                                           "spec_disputes": C.portable(dp), "spec_disputes_sha256": C.sha256_file(dp),
                                           "records": len(recs), "disputes": len(disputes)})

    def get(self, rtype: str) -> TypeEvidence:
        return self.types.get(rtype) or TypeEvidence(rtype)

    def owner(self, rtype: str, setting: bool = False) -> dict:
        """{'kind': parent|self|DISPUTED|UNKNOWN, 'via': [...], 'parent_types': [...], 'evidence': [...]} (camada de API).

        Para tipo de configuração (setting=True), ser sub-recurso de API de um pai (aspecto parent do C25, com os
        tipos Terraform que realizam o pai) é dono = pai, mesmo que a spec dê ao sub-recurso um recurso próprio:
        configuração sem identidade fora do pai. Para contêiner e namespace vale o dono explícito da API."""
        te = self.get(rtype)
        if "owner" in te.disputed:
            return {"kind": "DISPUTED", "via": te.owner_via, "parent_types": te.parent_tf_types,
                    "evidence": te.disputed["owner"]["evidence"], "dispute": te.disputed["owner"]}
        if "parent" in te.owner_kinds:
            return {"kind": "parent", "via": te.owner_via, "parent_types": te.parent_tf_types,
                    "evidence": te.owner_kinds["parent"]}
        if setting and te.parent_api and (te.parent_tf_types or te.identity_refs):
            return {"kind": "parent", "via": sorted(te.identity_refs), "parent_types": te.parent_tf_types,
                    "evidence": [], "rule": "R-OWN-AZ-PARENT"}
        if "self" in te.owner_kinds:
            return {"kind": "self", "via": [], "parent_types": [], "evidence": te.owner_kinds["self"]}
        return {"kind": "UNKNOWN", "via": [], "parent_types": [], "evidence": te.owner_unknown}

    def owner_rule(self, rtype: str, block: str | None = None) -> dict:
        """Regra de dono única: (tipo, bloco de topo ou None) -> {'class': API | TERRAFORM_ONLY | UNDOCUMENTED, ...}.
        Bloco usa os fatos do próprio caminho; tipo (e atributo de topo) usa os fatos do recurso."""
        e = self.get(rtype).owner_layers.get(block or None, {"api": [], "terraform": []})
        cls = "API" if e["api"] else ("TERRAFORM_ONLY" if e["terraform"] else "UNDOCUMENTED")
        return {"class": cls, "api_evidence": sorted(e["api"]), "terraform_evidence": sorted(e["terraform"]),
                "key": rtype if not block else f"{rtype}/{block}"}

    def lifecycle(self, rtype: str) -> dict:
        te = self.get(rtype)
        if "lifecycle_controller" in te.disputed:
            return {"kind": "DISPUTED", "evidence": te.disputed["lifecycle_controller"]["evidence"],
                    "dispute": te.disputed["lifecycle_controller"]}
        for k in ("parent", "self"):
            if k in te.life_kinds:
                return {"kind": k, "evidence": te.life_kinds[k]}
        if te.per_account_singleton and te.account_scoped:
            return {"kind": "external", "evidence": [], "rule": "R-LIFE-ACCOUNT-SINGLETON"}
        return {"kind": "UNKNOWN", "evidence": te.life_unknown}

    def disputes_of(self, rtype: str) -> dict:
        return dict(self.get(rtype).disputed)
