"""Regras estruturais de uma realização (Fx/NA) contra a fixture abstrata. Usadas pelo fixture_check e pelo
desenvolvimento (mensagens em português; lista vazia = confere)."""
from __future__ import annotations

import re

from .model import COST_CLASSES, EVIDENCE_LEVELS, MECHANISMS, NA, Fx

ADDR = re.compile(r"^(data\.)?[a-z][a-z0-9_]*\.[a-z0-9_]+$")
PREFIXES = ("probe:", "implicit:", "external:", "absent:")


def _addr_of(target: str) -> str:
    return target.split("#", 1)[0]


def _probe_key_exists(inputs: dict, key: str) -> bool:
    cur = inputs
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def lint(q: dict, variant: str, fid: str, r) -> list[str]:
    errs = []
    f = q["fixtures"][variant]["fixture"]
    w = f"{fid}"
    if isinstance(r, NA):
        if len(r.reason.strip()) < 15:
            errs.append(f"{w}: NOT_APPLICABLE sem motivo")
        if not r.evidence:
            errs.append(f"{w}: NOT_APPLICABLE sem evidência")
        return errs
    if not isinstance(r, Fx):
        return [f"{w}: realização de tipo {type(r).__name__}"]
    slug_prefix = re.sub(r"[^a-z0-9]+", "_", fid.lower()).strip("_") + "_"
    addrs = [x.address for x in r.resources]
    if len(set(addrs)) != len(addrs):
        errs.append(f"{w}: endereço repetido no slice")
    for x in r.resources:
        if not x.label.startswith(slug_prefix):
            errs.append(f"{w}: rótulo {x.label} não começa com {slug_prefix}")
    for vd in r.variables:
        if not vd.name.startswith(slug_prefix):
            errs.append(f"{w}: variável {vd.name} não começa com {slug_prefix}")
        if vd.has_default:
            errs.append(f"{w}: variável simbólica {vd.name} com default")
    ents = [e["id"] for e in f["entities"]]
    if sorted(r.entity_map) != sorted(ents):
        miss = sorted(set(ents) - set(r.entity_map))
        extra = sorted(set(r.entity_map) - set(ents))
        errs.append(f"{w}: entity_map difere das entidades da fixture (faltam {miss}, sobram {extra})")
    mapped_addrs, bare_mapped = set(), set()
    inputs = (r.probe or {}).get("inputs", {})
    for lid, tgt in r.entity_map.items():
        if tgt.startswith("probe:"):
            if not _probe_key_exists(inputs, tgt[6:]):
                errs.append(f"{w}: {lid} -> {tgt}, mas probe.inputs não tem {tgt[6:]}")
        elif tgt.startswith(PREFIXES):
            if len(tgt.split(":", 1)[1].strip()) < 5:
                errs.append(f"{w}: {lid} -> {tgt} sem descrição")
        else:
            a = _addr_of(tgt)
            if a not in addrs:
                errs.append(f"{w}: {lid} -> {tgt}: endereço fora do slice")
            mapped_addrs.add(a)
            if "#" not in tgt:
                bare_mapped.add(a)
    for k, why in r.synthesized.items():
        a = _addr_of(k)
        if a not in addrs:
            errs.append(f"{w}: sintetizado {k} fora do slice")
        if len(str(why).strip()) < 10:
            errs.append(f"{w}: sintetizado {k} sem motivo")
        if "#" not in k and a in bare_mapped:
            errs.append(f"{w}: {a} é ao mesmo tempo indivíduo da fixture e recurso sintetizado")
    synth_addrs = {k for k in r.synthesized if "#" not in k}
    for a in addrs:
        if a not in mapped_addrs and a not in synth_addrs:
            errs.append(f"{w}: {a} no slice sem entidade nem motivo de síntese")
    nr = sorted((n["of"], n["what"]) for n in f["read"]["not_read"])
    got = sorted((i["of"], i["what"]) for i in r.incompleteness)
    if nr != got:
        errs.append(f"{w}: incompleteness {got} não cobre exatamente o not_read da fixture {nr}")
    for i in r.incompleteness:
        if i.get("mechanism") not in MECHANISMS:
            errs.append(f"{w}: mecanismo inválido {i.get('mechanism')!r}")
        if len(str(i.get("detail", "")).strip()) < 15:
            errs.append(f"{w}: incompletude sem detalhe")
        if i.get("address") and _addr_of(i["address"]) not in addrs:
            errs.append(f"{w}: incompletude aponta para {i['address']} fora do slice")
        if i.get("mechanism") == "SYMBOLIC_INPUT" and not r.variables:
            errs.append(f"{w}: SYMBOLIC_INPUT sem variável simbólica declarada")
    if variant != "incomplete":
        if r.variables:
            errs.append(f"{w}: fixture de leitura completa com variável simbólica {[v.name for v in r.variables]}")
        if r.incompleteness:
            errs.append(f"{w}: fixture de leitura completa com incompletude")
    if r.evidence_level not in EVIDENCE_LEVELS:
        errs.append(f"{w}: evidence_level inválido")
    if r.cost_class not in COST_CLASSES:
        errs.append(f"{w}: cost_class inválido")
    if not r.deployable and len(r.deploy_note.strip()) < 15:
        errs.append(f"{w}: não implantável sem motivo")
    if (r.probe or {}).get("kind", "static") not in ("static", "readback", "two_phase", "translation"):
        errs.append(f"{w}: probe.kind inválido")
    return errs
