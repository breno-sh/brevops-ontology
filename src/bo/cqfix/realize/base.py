"""Base comum dos realizadores por provedor: contexto de uma fixture e registro de realizadores.

Um realizador é `f(v, c) -> Fx | NA`, registrado com @reg(REALIZERS, "CQ-XXX-NN"); v é a variante
("conforming" | "nonconforming" | "incomplete") e c o contexto (Ctx) da fixture. Rótulos Terraform
saem de <fx_slug>_<id local> (ou _x_<papel> para recurso sintetizado), nomes na nuvem de
"${var.run_id}-<fx>-<id>"; nada de nome real.
"""
from __future__ import annotations

from ..hcl import Ref, Res, Tpl, Var, VarDecl
from ..model import NA, Fx, fx_slug


def reg(table: dict, *cq_ids: str):
    def deco(fn):
        for q in cq_ids:
            if q in table:
                raise ValueError(f"realizador duplicado para {q}")
            table[q] = fn
        return fn
    return deco


class Ctx:
    def __init__(self, provider: str, q: dict, variant: str):
        self.provider = provider
        self.q = q
        self.cq_id = q["cq_id"]
        self.v = variant
        self.fixture = q["fixtures"][variant]["fixture"]
        self.fid = self.fixture["fixture_id"]
        self.slug = fx_slug(self.fid)
        self.dash = self.slug.replace("_", "-")
        self.res: list[Res] = []
        self.vars: list[VarDecl] = []
        self.emap: dict[str, str] = {}
        self.synth: dict[str, str] = {}
        self.inc: list[dict] = []
        self.probe: dict = {}
        self.dev: list[str] = []
        self.evidence: list[dict] = []

    # ---- nomes
    def lab(self, lid: str) -> str:
        return f"{self.slug}_{lid}"

    def name(self, lid: str, sep: str = "-", maxlen: int | None = None) -> Tpl:
        tail = f"{self.dash}-{lid.replace('_', '-')}".replace("-", sep)
        if maxlen:
            tail = tail[:maxlen]
        return Tpl("${var.run_id}" + sep + tail)

    # ---- recursos
    def add(self, r: Res, entity: str | None = None, synth: str | None = None) -> Res:
        if any(x.address == r.address for x in self.res):
            raise ValueError(f"{self.fid}: endereço repetido {r.address}")
        self.res.append(r)
        if entity:
            self.emap[entity] = r.address
        if synth:
            self.synth[r.address] = synth
        if not entity and not synth:
            raise ValueError(f"{self.fid}: {r.address} sem entidade nem motivo de síntese")
        return r

    def r(self, rtype: str, lid: str, attrs: dict | None = None, blocks=None, entity=None, synth=None,
          kind="resource", depends_on=None, provider=None) -> Res:
        return self.add(Res(rtype, self.lab(lid), attrs or {}, blocks or [], kind, depends_on or [], provider),
                        entity, synth)

    def x(self, rtype: str, role: str, attrs: dict | None = None, blocks=None, why: str = "", kind="resource",
          depends_on=None, provider=None) -> Res:
        """Recurso sintetizado (não é indivíduo da fixture); why é obrigatório."""
        if not why:
            raise ValueError("recurso sintetizado sem motivo")
        return self.r(rtype, f"x_{role}", attrs, blocks, synth=why, kind=kind, depends_on=depends_on,
                      provider=provider)

    def symvar(self, suffix: str, typ: str = "string", desc: str = "") -> Var:
        n = f"{self.slug}_{suffix}"
        self.vars.append(VarDecl(n, typ, desc or f"entrada simbólica da fixture {self.fid}; sem valor de propósito"))
        return Var(n)

    def map(self, lid: str, target: str):
        self.emap[lid] = target

    def missing(self, of: str, what: str, mechanism: str, detail: str, address: str | None = None):
        d = {"of": of, "what": what, "mechanism": mechanism, "detail": detail}
        if address:
            d["address"] = address
        self.inc.append(d)

    def done(self, evidence_level: str = "STRUCTURAL", deployable: bool = True, deploy_note: str = "",
             cost_class: str = "free") -> Fx:
        return Fx(resources=self.res, entity_map=dict(self.emap), variables=self.vars, incompleteness=self.inc,
                  probe=self.probe, synthesized=self.synth, deviations=self.dev,
                  evidence_level=evidence_level, evidence=self.evidence, deployable=deployable,
                  deploy_note=deploy_note, cost_class=cost_class)


def na(reason: str, *evidence: dict) -> NA:
    if not evidence:
        raise ValueError("NOT_APPLICABLE sem evidência")
    return NA(reason, list(evidence))


def ref(r: Res, attr: str = "id") -> Ref:
    return r.ref(attr)


__all__ = ["Ctx", "reg", "na", "ref", "Ref", "Res", "Tpl", "Var", "VarDecl", "Fx", "NA"]
