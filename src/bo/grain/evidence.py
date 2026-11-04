"""Evidência estruturada por candidato: alegações, consolidação e adaptadores.

Uma alegação (claim) é o que UMA fonte diz sobre UM campo de evidência de um candidato. A consolidação de um
campo dá KNOWN (todas as alegações afirmadas concordam), UNKNOWN (nenhuma afirmada) ou CONTRADICTORY (duas
afirmadas divergem). O motor de regras só vê o resultado consolidado; o que cada provedor diz vive nos
adaptadores (FixtureAdapter para dados sintéticos, C25Adapter para o service_evidence.jsonl do
SERVICE-EVIDENCE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import canon

FIELDS = ("identity", "import_key", "element_name_key", "lifecycle_controller", "owner",
          "effective_scope", "api_resource")
# Campos que o C19 aceita em missing_evidence (a chave de importação e a de nome contam como identidade).
C19_MISSING = ("identity", "lifecycle_controller", "owner", "effective_scope", "api_resource")
C19_OF_FIELD = {"identity": "identity", "import_key": "identity", "element_name_key": "identity",
                "lifecycle_controller": "lifecycle_controller", "owner": "owner",
                "effective_scope": "effective_scope", "api_resource": "api_resource"}

KNOWN, UNKNOWN, CONTRADICTORY = "KNOWN", "UNKNOWN", "CONTRADICTORY"
PARENT = "$parent"

_KINDS_LC = ("self", "parent", "provider", "external")
_KINDS_SCOPE = ("self", "parent", "container", "global")
_API = ("resource", "aspect", "payload")


class EvidenceError(ValueError):
    """Alegação mal formada (erro do adaptador, não evidência que falta)."""


def _norm_via(v) -> tuple[str, ...]:
    """via ausente, [] e ["$parent"] são a mesma coisa: o padrão é o pai estrutural (nó aninhado)."""
    if v is None:
        return ()
    if isinstance(v, str):
        v = [v]
    out = tuple(sorted(str(x) for x in v))
    return () if out == (PARENT,) else out


def normalize_claim(fld: str, c: dict) -> dict | None:
    """Forma comparável de uma alegação; None = a fonte diz que não sabe."""
    if not isinstance(c, dict):
        raise EvidenceError(f"{fld}: alegação não é objeto")
    st = c.get("status")
    if st == "unknown":
        return None
    if fld == "identity":
        if st not in ("present", "absent"):
            raise EvidenceError(f"identity: status {st!r}")
        if st == "absent":
            return {"status": "absent"}
        scope = c.get("scope")
        if scope not in ("independent", "within_parent", None):
            raise EvidenceError(f"identity: scope {scope!r}")
        return {"status": "present", "scope": scope, "key_fields": sorted(c.get("key_fields", [])),
                "surrogate": bool(c.get("surrogate", False)), "anonymous": bool(c.get("anonymous", False))}
    if fld in ("import_key", "element_name_key"):
        if st not in ("present", "absent"):
            raise EvidenceError(f"{fld}: status {st!r}")
        if st == "absent":
            return {"status": "absent"}
        return {"status": "present", "fields": sorted(c.get("fields", []))}
    if fld in ("lifecycle_controller", "owner"):
        k = c.get("kind")
        if k not in _KINDS_LC:
            raise EvidenceError(f"{fld}: kind {k!r}")
        return {"kind": k, "via": list(_norm_via(c.get("via")))}
    if fld == "effective_scope":
        k = c.get("kind")
        if k not in _KINDS_SCOPE:
            raise EvidenceError(f"effective_scope: kind {k!r}")
        return {"kind": k, "via": list(_norm_via(c.get("via")))}
    if fld == "api_resource":
        st2 = c.get("status")
        if st2 not in _API:
            raise EvidenceError(f"api_resource: status {st2!r}")
        out = {"status": st2, "label": c.get("label")}
        if c.get("service"):
            out["service"] = c["service"]
        if c.get("resource"):
            out["resource"] = c["resource"]
        return out
    raise EvidenceError(f"campo de evidência desconhecido: {fld}")


@dataclass(frozen=True)
class Fact:
    state: str  # KNOWN | UNKNOWN | CONTRADICTORY
    value: Any = None

    @property
    def known(self) -> bool:
        return self.state == KNOWN


def consolidate(fld: str, claims: list[dict]) -> Fact:
    for c in claims or []:
        if isinstance(c, dict) and c.get("status") == "contradictory":
            return Fact(CONTRADICTORY, None)
    stated = [n for n in (normalize_claim(fld, c) for c in claims or []) if n is not None]
    if not stated:
        return Fact(UNKNOWN, None)
    keys = {canon(s) for s in stated}
    if len(keys) > 1:
        return Fact(CONTRADICTORY, None)
    return Fact(KNOWN, stated[0])


@dataclass
class CandidateEvidence:
    """Evidência de um candidato (recurso, bloco ou grupo de atributos) já com as alegações por campo."""
    claims: dict[str, list[dict]] = field(default_factory=dict)
    # campo canônico -> {"path": caminho relativo no candidato, "norm": normalizador, "ref": bool, "config": bool}
    field_map: dict[str, dict] = field(default_factory=dict)
    # campo canônico de referência -> candidato-alvo (camada de schema)
    references: dict[str, str] = field(default_factory=dict)
    # nome canônico do pai estrutural quando ele entra na identidade (papel na tupla do vínculo)
    parent_role: str = "parent"
    # grupos de atributos ligados a um aspecto da API (T1): nome -> {"paths": [...], "evidence": {...}}
    groups: dict[str, dict] = field(default_factory=dict)
    # papéis do C04 por caminho relativo (opcional)
    roles: dict[str, str] = field(default_factory=dict)
    # tipo gêmeo de que o bloco herdou a evidência (T09) e marca de fora do domínio (T45)
    twin: str | None = None
    out_of_domain: str | None = None
    # o pai estrutural é o pai de caminho da spec (herdado do gêmeo, G2-CHILD)
    parent_is_path_parent: bool = False
    # faceta implícita (T57): {facet, label, operation, member, parent_resource, source}; só com fato da spec
    implicit_facet: dict | None = None

    def fact(self, fld: str) -> Fact:
        return consolidate(fld, self.claims.get(fld, []))

    def sources(self, flds=FIELDS) -> list[dict]:
        out, seen = [], set()
        for f in flds:
            for c in self.claims.get(f, []):
                s = c.get("source")
                if s and canon(s) not in seen:
                    seen.add(canon(s))
                    out.append(s)
        return out


def from_dict(d: dict) -> CandidateEvidence:
    claims = {f: list(d.get(f, [])) for f in FIELDS if f in d}
    return CandidateEvidence(claims=claims, field_map=dict(d.get("field_map", {})),
                             references=dict(d.get("references", {})),
                             parent_role=d.get("parent_role", "parent"),
                             groups=dict(d.get("groups", {})), roles=dict(d.get("roles", {})),
                             twin=d.get("twin"), out_of_domain=d.get("out_of_domain"),
                             parent_is_path_parent=bool(d.get("parent_is_path_parent")),
                             implicit_facet=d.get("implicit_facet"))


class FixtureAdapter:
    """Adaptador de evidência para dados sintéticos: {cid: {campo: [alegações], ...}}."""

    def __init__(self, table: dict[str, dict]):
        self.table = table

    def evidence(self, cid: str) -> CandidateEvidence:
        return from_dict(self.table.get(cid, {}))


class C25Adapter:
    """Lê service_evidence.jsonl (C25 1.0.0) e devolve a evidência neutra por candidato.

    Convenção de leitura (o C25 deixa `value` livre): `value` é a alegação do campo, como objeto
    ({"kind": ..., "via": ...}, {"status": ..., "key_fields": ...}) ou, para lifecycle_controller, owner e
    effective_scope, a string do kind. O candidato é terraform_resource_type, mais value.block_path
    (blocos separados por ponto) quando a alegação é de um bloco aninhado. status=unknown vira alegação
    desconhecida; unknown_reason=contradictory vira CONTRADICTORY. A fonte (evidence_id e nível) entra no C19.
    """

    _FACT_FIELD = {"identity": "identity", "import_key": "import_key",
                   "lifecycle_controller": "lifecycle_controller", "owner": "owner",
                   "effective_scope": "effective_scope"}

    def __init__(self, records: list[dict], extra: dict[str, dict] | None = None, candidates=None):
        self.by_cid: dict[str, dict] = {}
        self.reasons: dict[str, list] = {}
        from . import c25_aspects as A
        if any(A.is_aspect_record(r) for r in records):
            # forma por aspecto do SERVICE-EVIDENCE: tradução normativa (bo.grain.c25_aspects.TABLE)
            by_p: dict[str, list] = {}
            for r in records:
                by_p.setdefault(r.get("provider", ""), []).append(r)
            cset = set(candidates) if candidates is not None else None
            for prov in sorted(by_p):
                ev, why = A.translate(by_p[prov], cset)
                self.by_cid.update(ev)
                self.reasons.update(why)
            records = []
        for r in records:
            fk = r.get("fact_kind")
            fld = self._FACT_FIELD.get(fk)
            rt = r.get("terraform_resource_type")
            if not fld or not rt:
                continue
            val = r.get("value")
            bp = val.get("block_path") if isinstance(val, dict) else None
            cid = rt + ("." + bp if bp else "")
            src = {"level": r.get("level") or "published", "ref": r["evidence_id"]}
            if r.get("level") == "interpreted" and r.get("model_id"):
                src["model_id"] = r["model_id"]
            if r.get("status") == "unknown":
                st = "contradictory" if r.get("unknown_reason") == "contradictory" else "unknown"
                claim = {"status": st, "source": src}
            else:
                if isinstance(val, str):
                    claim = {"kind": val}
                elif isinstance(val, dict):
                    claim = {k: v for k, v in val.items()
                             if k not in ("block_path", "references", "field_map", "api_status", "label",
                                          "element_name_key", "parent_role")}
                    ent0 = self.by_cid.setdefault(cid, {})
                    ent0.setdefault("references", {}).update(val.get("references") or {})
                    ent0.setdefault("field_map", {}).update(val.get("field_map") or {})
                    if val.get("parent_role"):
                        ent0["parent_role"] = val["parent_role"]
                    if fld == "identity" and "element_name_key" in val:
                        nk = val["element_name_key"]
                        ent0.setdefault("element_name_key", []).append(
                            {"status": "absent", "source": src} if not nk else
                            {"status": "present", "fields": list(nk), "source": src})
                else:
                    raise EvidenceError(f"{r.get('evidence_id')}: value não interpretável")
                claim["source"] = src
            ent = self.by_cid.setdefault(cid, {})
            ent.setdefault(fld, []).append(claim)
            api = r.get("api_resource")
            if api and fld == "identity" and isinstance(val, dict) and val.get("api_status"):
                ent.setdefault("api_resource", []).append(
                    {"status": val["api_status"], "label": val.get("label") or api["resource"],
                     "service": api["service"], "resource": api["resource"], "source": src})
        # campo citado numa chave sem mapa explícito: nome canônico = caminho no candidato; referência se tem alvo
        for cid, ent in self.by_cid.items():
            fm, refs = ent.setdefault("field_map", {}), ent.get("references", {})
            for fld in ("identity", "import_key"):
                for cl in ent.get(fld, []):
                    for f in list(cl.get("key_fields", []) or []) + list(cl.get("fields", []) or []):
                        if f not in fm and not cl.get("surrogate"):
                            fm[f] = {"path": f, "ref": True} if f in refs else {"path": f, "norm": "str"}
        for cid, d in (extra or {}).items():
            ent = self.by_cid.setdefault(cid, {})
            for k, v in d.items():
                if k in FIELDS:
                    ent.setdefault(k, []).extend(v)
                else:
                    ent[k] = v

    def evidence(self, cid: str) -> CandidateEvidence:
        return from_dict(self.by_cid.get(cid, {}))
