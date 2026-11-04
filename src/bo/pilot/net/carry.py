"""Transporte de valor de átomo por alegação OK (igual nos três controles) e descida de valor neutro por realização.

carry():  valor cru de um átomo de origem -> átomo de destino, pela alegação escalar ou de grupo entre os dois.
          Usa bo.semantics.transport (tabela SKOS com a direção corrigida, guarda, pertença, perdas). Lista com
          projeção de escopo 'element' é transportada elemento a elemento. Sem alegação OK: UNPROVEN (ou o código do
          veredito); mais de uma alegação OK com saídas diferentes: AMBIGUOUS_TARGET.
lower():  valor NEUTRO entailado (c2: realização estrutural; c3: axioma) -> valor do destino pelo codec do vocab.
"""

from __future__ import annotations

import json

from bo.semantics.transport import transport
from bo.transforms import registry as REG

from . import vocab as V
from .claims import strip_index

VERDICT_CODE = {"REFUTED_BY_RULE": "REFUTED_BY_RULE", "UNPROVEN": "UNPROVEN", "AMBIGUOUS": "AMBIGUOUS_TARGET",
                "CONTESTED": "UNPROVEN"}


class Out:
    """Resultado de uma tentativa: carried (value) | blocked (code) | omitted."""

    def __init__(self, result, value=None, code=None, claim_id=None, detail="", fn=None, rule=None, guard=None):
        self.result, self.value, self.code, self.claim_id = result, value, code, claim_id
        self.detail, self.fn, self.rule, self.guard = detail, fn, rule, guard

    @property
    def ok(self):
        return self.result == "carried"

    def __repr__(self):  # pragma: no cover - depuração
        return f"Out({self.result}, {self.value!r}, {self.code})"


def _elementwise(claim: dict) -> bool:
    proj = claim.get("projection")
    if isinstance(proj, str) and proj:
        proj = json.loads(proj)
    return any(((p.get("occurrence") or {}).get("scope") == "element") for p in (proj or []))


def _one(ref, raw, ctx):
    t = transport(ref.claim, raw, ctx, ref.direction)
    if t["result"] == "carried":
        return Out("carried", t["value"], claim_id=ref.claim_id, fn=ref.claim.get("translation_fn"),
                   detail=t.get("detail", ""))
    if t["result"] == "omitted":
        return Out("omitted", claim_id=ref.claim_id, detail=t.get("detail", ""))
    return Out("blocked", code=t["code"], claim_id=ref.claim_id, detail=t.get("detail", ""), rule=t.get("rule"),
               guard=t.get("guard"))


def carry(cs, source_atom: str, raw, target_atom: str, ctx=None, element: bool = False) -> Out:
    """element=True: o chamador já separou a ocorrência (um elemento da lista); a alegação tem de ser por elemento."""
    if cs is None:
        return Out("blocked", code="UNPROVEN", detail="sem conjunto de alegações")
    src = strip_index(source_atom)
    refs = cs.scalar(src, target_atom)
    ok = [r for r in refs if r.ok]
    if not ok:
        g = carry_group(cs, src, raw, target_atom, ctx)
        if g is not None:
            return g
        if refs:
            v = refs[0].verdict
            return Out("blocked", code=VERDICT_CODE.get(v, "UNPROVEN"), claim_id=refs[0].claim_id,
                       detail=f"alegação {refs[0].claim_id} com veredito {v}: não transporta", rule="T-UNPROVEN")
        return Out("blocked", code="UNPROVEN", detail=f"nenhuma alegação entre {src} e {target_atom}",
                   rule="T-UNPROVEN")
    outs = []
    for ref in ok:
        if isinstance(raw, list) and not element and _elementwise(ref.claim):
            parts = [_one(ref, x, ctx) for x in raw]
            bad = [p for p in parts if not p.ok]
            if bad:
                outs.append(bad[0])
            else:
                outs.append(Out("carried", [p.value for p in parts], claim_id=ref.claim_id,
                                fn=ref.claim.get("translation_fn"), detail="por elemento (projeção por ocorrência)"))
        else:
            outs.append(_one(ref, raw, ctx))
    good = [o for o in outs if o.ok]
    if len({json.dumps(o.value, sort_keys=True, default=str) for o in good}) > 1:
        return Out("blocked", code="AMBIGUOUS_TARGET", claim_id=",".join(o.claim_id for o in good),
                   detail="mais de uma alegação OK com saídas diferentes")
    if good:
        return good[0]
    return outs[0]


def carry_group(cs, source_atom: str, raw, target_atom: str, ctx=None, bindings: dict | None = None) -> Out | None:
    """Alegação de grupo (C09 group): liga as variáveis do lado de origem pelos valores dados em `bindings`
    (campo -> valor cru) e roda os passos do registro fechado; devolve a variável do campo de destino."""
    prov = source_atom.split(":", 1)[0]
    for g in cs.groups_to(target_atom, prov):
        if bindings is None or g.direction != "forward":
            continue
        side_src = "subject" if g.direction == "forward" else "object"
        env = {}
        for var in g.group["variables"]:
            if var["side"] == side_src:
                if var["field"] not in bindings:
                    break
                env[var["name"]] = bindings[var["field"]]
        else:
            if not g.ok:
                return Out("blocked", code=VERDICT_CODE.get(g.verdict, "UNPROVEN"), claim_id=g.claim_id,
                           detail=f"alegação de grupo {g.claim_id} com veredito {g.verdict}", rule="T-UNPROVEN")
            guard = g.claim.get("guard") or {"all": []}
            if isinstance(guard, str):
                guard = json.loads(guard)
            from bo.semantics import guards as G
            gv, gt = G.evaluate(guard, ctx or {})
            if gv != G.TRUE:
                code = "CONDITION_FALSE" if gv == G.FALSE else "CONDITION_INDETERMINATE"
                return Out("blocked", code=code, claim_id=g.claim_id, rule="T-GUARD", guard=gv,
                           detail=f"guarda da alegação de grupo {gv.lower()}: {gt}")
            try:
                steps = g.group["steps"]
                for st in steps:
                    ins = {k: env[v] for k, v in st["inputs"].items()}
                    if type(REG.get(st["name"])).__name__ == "Combinator":
                        res = REG.apply_combinator(st["name"], ins, ctx)
                    else:
                        res = {"value": REG.apply_scalar(st["name"], ins["value"], st.get("params"), ctx)}
                    for k, v in st["outputs"].items():
                        env[v] = res[k]
            except Exception as e:  # noqa: BLE001 - erro do registro vira bloqueio tipado
                return Out("blocked", code="TRANSFORM_OUT_OF_DOMAIN", claim_id=g.claim_id, detail=str(e)[:200],
                           rule="T-DOMAIN")
            side_dst = "object" if g.direction == "forward" else "subject"
            for var in g.group["variables"]:
                if var["side"] == side_dst and var["field"] == target_atom and var["name"] in env:
                    o = Out("carried", env[var["name"]], claim_id=g.claim_id,
                            fn={"name": "+".join(s["name"] for s in steps), "params": {}},
                            detail="alegação de grupo")
                    o.inputs = [v["field"] for v in g.group["variables"] if v["side"] == side_src]
                    return o
    return None


# --------------------------------------------------------------------------------------------- descida por codec

def lower_direction(provider: str, neutral: str):
    return V.DIRECTION_OUT.get(provider, {}).get(neutral)


def lower_protocol(provider: str, neutral: str):
    return V.proto_out(provider, neutral)


def lower_effect(provider: str, neutral: str):
    return V.EFFECT_OUT.get(provider, {}).get(neutral)


def port_text(lo: int, hi: int) -> str:
    return str(lo) if lo == hi else f"{lo}-{hi}"
