"""Gera as linhas C09 do PILOT-NET-MAP a partir do pacote e das decisões (determinístico: mesma entrada, mesmos
bytes). Nada aqui decide veredito: o árbitro congelado julga depois.

Por par (orientação canônica) e por faixa: emparelha os membros dos dois lados com a guarda do contexto (sentido e
efeito), escreve a alegação pela política da faixa (os três campos separados), acrescenta os grupos de portas
(início e fim numéricos <-> faixa em texto, pelo combinador do registro), o efeito fixo do AZOCI e, por fim, a
linha de ausência tipada de todo átomo canônico dos dois lados que nenhuma alegação que transporta alcança.
"""

from __future__ import annotations

import json
from fractions import Fraction

from bo.semantics.claims import Claim
from bo.semantics.obligations import computed_vdr
from bo.semantics.valuetypes import ValueType

from . import decisions as D
from .bundle import Bundle
from .common import MODEL_ID, MODULE, NO_TERM, PAIRS, PRED, TRANSPORTING, UNGLOSSED, provider_of, type_of

KINDS_ORDER = {"claim": 0, "group": 1, "fixed": 2, "absence": 3}
SAMPLE_TEXT = "exemplo"


# ------------------------------------------------------------------------------------------- realizações
def atom_of(shape_id: str, path: str) -> str:
    s = D.SHAPES[shape_id]
    return f"{s['prov']}:{s['rtype']}:{s['prefix']}{path}"


def field_of(atom: str) -> str:
    """'prov:tipo:caminho' -> 'prov:tipo.caminho' (forma de campo das variáveis de grupo e das projeções)."""
    p, t, path = atom.split(":", 2)
    return f"{p}:{t}.{path}"


def resolved_shapes(b: Bundle) -> dict:
    """Formas com o efeito resolvido pelo pacote: efeito "unknown" vira fixo quando uma âncora publicada de tipo
    ou de bloco (C20 implication) diz o efeito do tipo/bloco daquela forma (ex.: regra só de permitir)."""
    out = {}
    for sid, sh in D.SHAPES.items():
        sh = dict(sh)
        if sh.get("eff") == "unknown":
            refs = [f"{sh['prov']}:{sh['rtype']}"]
            if sh.get("prefix"):
                refs.insert(0, f"{sh['prov']}:{sh['rtype']}:{sh['prefix'].rstrip('.')}")
            vals = sorted({x["value"] for r in refs for x in b.implied("concept:rule_effect", r)} & {"allow", "deny"})
            if len(vals) == 1:
                sh["eff"] = vals[0]
                sh["eff_source"] = sorted({x["claim_id"] for r in refs for x in b.implied("concept:rule_effect", r)})
        out[sid] = sh
    return out


def realizations(b: Bundle) -> tuple[dict, list[dict]]:
    """{faixa: [real]}, [membro declarado que o pacote não tem]."""
    out, missing = {}, []
    shapes = resolved_shapes(b)
    for sl in D.SLOTS:
        lst = []
        for m in sl["members"]:
            shape_id, path = m[0], m[1]
            atom = atom_of(shape_id, path)
            if atom not in b.canonical:
                missing.append({"slot": sl["slot"], "atom": atom})
                continue
            lst.append({"atom": atom, "shape_id": shape_id, "shape": shapes[shape_id], "path": path,
                        "dir_override": m[2] if len(m) > 2 else None, "slot": sl["slot"]})
        out[sl["slot"]] = lst
    return out, missing


# ------------------------------------------------------------------------------------------------- guardas
def _term_type(b: Bundle, shape: dict, path: str) -> dict:
    t = b.types.get(f"{shape['prov']}:{shape['rtype']}:{path}")
    if t and t.get("datatype") == "enum" and t.get("enum"):
        return {"datatype": "enum", "enum": list(t["enum"])}
    return {"datatype": "string"}


class Skip(Exception):
    """Emparelhamento que a guarda não consegue escrever sem inventar valor."""


def _dir_of(r: dict):
    sh = r["shape"]
    if r["dir_override"]:
        return r["dir_override"]
    return sh.get("dir") if sh.get("dir") in ("in", "out") else (sh.get("dir"))


def _own_dir_guard(b, r, role, atoms, tt):
    """Membro que fixa o próprio sentido numa forma com sentido por atributo (ex.: cidr_blocks só em ingress)."""
    sh = r["shape"]
    if r["dir_override"] and sh.get("dir") == "attr":
        vals = sh.get("dir_vals") or {}
        if r["dir_override"] not in vals:
            raise Skip(f"{r['atom']}: sentido {r['dir_override']} sem valor documentado em {sh['dir_term']}")
        term = f"{role}.{sh['dir_term']}"
        atoms.append({"term": term, "op": "eq", "value": vals[r["dir_override"]]})
        tt[term] = _term_type(b, sh, sh["dir_term"])


def _dir_guard(b, ra, rb, atoms, tt):
    da, db = _dir_of(ra), _dir_of(rb)
    if da is None or db is None:
        return
    fa, fb = da in ("in", "out"), db in ("in", "out")
    if fa and fb:
        if da != db:
            raise Skip("sentidos fixos diferentes")
        return
    for fixed, other, role in ((da, rb, "object"), (db, ra, "subject")):
        if fixed in ("in", "out") and _dir_of(other) == "attr":
            sh = other["shape"]
            vals = sh.get("dir_vals") or {}
            if fixed not in vals:
                raise Skip(f"{other['atom']}: sentido {fixed} sem valor documentado em {sh['dir_term']}")
            term = f"{role}.{sh['dir_term']}"
            atoms.append({"term": term, "op": "eq", "value": vals[fixed]})
            tt[term] = _term_type(b, sh, sh["dir_term"])


def _eff_atoms(b, r, role, e) -> list:
    """Átomos de guarda que forçam o efeito e no lado r (atributo ou bloco usado)."""
    sh = r["shape"]
    if sh["eff"] == "attr":
        vals = sh.get("eff_vals") or {}
        if e not in vals:
            raise Skip(f"{r['atom']}: efeito {e} sem valor documentado em {sh['eff_term']}")
        return [({"term": f"{role}.{sh['eff_term']}", "op": "eq", "value": vals[e]},
                 (f"{role}.{sh['eff_term']}", _term_type(b, sh, sh["eff_term"])))]
    if sh["eff"] == "struct":
        blk = f"{sh['prov']}:{sh['rtype']}:{sh['eff_present'][e]}."
        if not any(a.startswith(blk) for a in list(b.canonical) + list(b.types)):
            raise Skip(f"{r['atom']}: bloco {sh['eff_present'][e]} ausente do pacote")
        return [({"term": f"{role}.{sh['eff_present'][e]}", "op": "present", "value": True}, None)]
    return []


def guards_for(b: Bundle, ra: dict, rb: dict, with_dir: bool = True) -> list[dict]:
    """Guardas (uma ou duas, exclusivas entre si) do emparelhamento a (sujeito) × b (objeto)."""
    base_atoms, tt = [], {}
    _own_dir_guard(b, ra, "subject", base_atoms, tt)
    _own_dir_guard(b, rb, "object", base_atoms, tt)
    if with_dir:
        _dir_guard(b, ra, rb, base_atoms, tt)
    ea, eb = ra["shape"].get("eff"), rb["shape"].get("eff")
    variants: list[list] = [[]]
    if "unknown" in (ea, eb):
        ea = eb = None          # efeito não documentado de um lado: nenhuma guarda de efeito se escreve
    if ea is not None and eb is not None:
        fixed = {"allow", "deny"}
        if ea in fixed and eb in fixed:
            if ea != eb:
                raise Skip("efeitos fixos diferentes")
        elif ea in fixed:
            variants = [_eff_atoms(b, rb, "object", ea)]
        elif eb in fixed:
            variants = [_eff_atoms(b, ra, "subject", eb)]
        elif {ea, eb} == {"attr", "struct"}:
            variants = []
            for e in ("allow", "deny"):
                try:
                    variants.append(_eff_atoms(b, ra, "subject", e) + _eff_atoms(b, rb, "object", e))
                except Skip:
                    continue
            if not variants:
                raise Skip("nenhum efeito escrevível dos dois lados")
    out = []
    for v in variants:
        atoms, ttv = list(base_atoms), dict(tt)
        for at, typ in v:
            atoms.append(at)
            if typ:
                ttv[typ[0]] = typ[1]
        g = {"all": sorted(atoms, key=lambda x: json.dumps(x, sort_keys=True))}
        if ttv:
            g["term_types"] = dict(sorted(ttv.items()))
        out.append(g)
    return out


# ---------------------------------------------------------------------------------------------- utilidades
def sample(t: dict | None, other: dict | None = None, hint: str = ""):
    """Valor de teste admitido pelo sujeito e, quando o objeto declara domínio, também por ele. Endereços usam os
    blocos reservados para documentação (RFC 5737 e RFC 3849); o resto, um texto neutro."""
    COLL = ("list", "set", "map")
    if t is not None and t.get("datatype") in COLL:
        item = sample(dict(t["item_type"], _path=t.get("_path", "")),
                      (other or {}).get("item_type") if (other or {}).get("datatype") in COLL else other, hint)
        return {str(item): item} if t["datatype"] == "map" else [item]
    if t is None or (t.get("datatype") == "string" and not t.get("enum")):
        if other and other.get("datatype") == "enum" and other.get("enum") and (t is None or not t.get("enum")):
            return other["enum"][0]
        if hint == "address":
            return "2001:db8::/32" if "ipv6" in (t or {}).get("_path", "") else "192.0.2.0/24"
        return SAMPLE_TEXT
    dt = t.get("datatype")
    if dt == "enum":
        enum = t.get("enum") or []
        oth = set((other or {}).get("enum") or [])
        common = [v for v in enum if v in oth]
        return (common or enum)[0]
    if dt in ("integer", "decimal"):
        r, ro = t.get("range") or {}, (other or {}).get("range") or {}
        lo = max([x for x in (r.get("min"), ro.get("min")) if x is not None], default=1)
        hi = min([x for x in (r.get("max"), ro.get("max")) if x is not None], default=lo)
        return lo if lo <= hi else r.get("min", 1)
    if dt == "boolean":
        return True
    if dt == "duration":
        return "PT60S"
    return SAMPLE_TEXT


def is_coll(t: dict | None) -> bool:
    return bool(t) and t.get("datatype") in ("list", "set", "map")


def vdr_of(rec: dict) -> str:
    """Relação de domínio calculada pela biblioteca do SEMANTICS (só quando os dois lados têm domínio fechado)."""
    ts, to = rec.get("subject_value_type"), rec.get("object_value_type")
    if not ts or not to or rec.get("translation_fn") is None:
        return "unknown"
    closed = lambda t: bool(t.get("enum") or t.get("range"))
    if not (closed(ts) or closed(to)):
        return "unknown"
    try:
        return computed_vdr(Claim(rec), ValueType.from_dict(ts), ValueType.from_dict(to))
    except Exception:       # noqa: BLE001 - tipo que a biblioteca não aceita: relação não calculável
        return "unknown"


def evidence_for(b: Bundle, atoms: list[str]) -> tuple[str, list[dict]]:
    """DOC_SUPPORTED só com sentença publicada para cada átomo envolvido; a citação vai na prova."""
    evs, all_have = [], True
    for a in atoms:
        mine = b.evidence.get(a) or []
        if not mine:
            all_have = False
        for e in mine[:2]:
            x = {k: e[k] for k in ("source", "sentence", "date")}
            if x not in evs:
                evs.append(x)
    return ("DOC_SUPPORTED" if all_have and evs else "STRUCTURALLY_VALID"), evs


def _block_keys(b: Bundle, shape: dict) -> list[str]:
    pre = f"{shape['prov']}:{shape['rtype']}:{shape['prefix']}"
    return sorted({a[len(pre):].split(".")[0] for a in b.canonical if a.startswith(pre)})


def projection_for(b: Bundle, r: dict) -> dict | None:
    """Campo em bloco repetido: projeção com chave de ocorrência pelo conteúdo do elemento (o elemento é anônimo;
    nunca pela posição). Só com tipo no pacote: projeção sem tipo não se escreve."""
    sh = r["shape"]
    t = b.types.get(r["atom"])
    if not sh.get("block") or t is None:
        return None
    pid = "PRJ-NET-" + r["atom"].replace(":", "-").replace(".", "-").replace("_", "-")
    s = sample(t)
    return {"projection_id": pid, "field": r["atom"], "occurrence": {"scope": "block", "key_fields": _block_keys(b, sh)},
            "extractor": {"name": "identity"}, "concept": b.concept(r["atom"]), "type": t,
            "tests": [{"input": s, "expected": s}]}


def _base(pair: str, s: str, o: str, rel: str, b: Bundle) -> dict:
    return {"basis": "direct", "creator_id": MODULE, "mapping_justification": "semapv:UnspecifiedMatching",
            "mapping_tool": MODEL_ID, "mapping_date": D.MAPPING_DATE, "subject_id": s, "object_id": o,
            "predicate_id": PRED[rel], "semantic_relation": rel,
            "subject_concept": b.concept(s) if ":" in s and s.count(":") >= 2 else UNGLOSSED,
            "object_concept": b.concept(o) if ":" in o and o.count(":") >= 2 else UNGLOSSED,
            "guard": {"all": []}, "loss_contract": [], "_pair": pair}


# ----------------------------------------------------------------------------------------------- políticas
def claim_for(pair, slot, policy, ra, rb, guard, b: Bundle) -> dict:
    a, o = ra["atom"], rb["atom"]
    ta, to = b.types.get(a), b.types.get(o)
    rel = {"priority": "close", "address": "close", "related": "related"}.get(policy, "exact")
    r = _base(pair, a, o, rel, b)
    r["guard"] = guard
    if ta is not None:
        r["subject_value_type"] = ta
    if to is not None:
        r["object_value_type"] = to
    st, evs = evidence_for(b, [a, o])
    r["evidence_state"] = st
    notes = []
    if policy == "related":
        r.update(translation_fn=None, transport_fidelity="none",
                 value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
                 proof={"type": "related", "evidence": evs, "tests": []})
        r["comment"] = (f"faixa {slot}: seletores de par por mecanismos diferentes (grupo, etiqueta, identidade); "
                        "related não transporta")
        projs = [p for p in (projection_for(b, ra), projection_for(b, rb)) if p]
        if projs:
            r["projection"] = projs
        return r
    if policy == "direction":
        va, vb = ra["shape"].get("dir_vals") or {}, rb["shape"].get("dir_vals") or {}
        table = {va[d]: vb[d] for d in ("in", "out") if d in va and d in vb}
        if not table:
            raise Skip("sentido sem valores documentados dos dois lados")
        r["translation_fn"] = {"name": "enum_map", "params": {"table": dict(sorted(table.items()))}}
        tests = [{"input": k, "expected": v} for k, v in sorted(table.items())]
        notes.append("sentido por tabela entre os valores documentados no pacote")
    else:
        ta_s = dict(ta, _path=a) if ta else {"datatype": "string", "_path": a}
        hint = policy if policy == "address" else ""
        ca, co = is_coll(ta), is_coll(to)
        if ta is not None and to is not None and not ca and co and to["datatype"] == "list":
            item = sample(ta_s, to.get("item_type"), hint)
            r["translation_fn"] = {"name": "wrap_list", "params": {}}
            tests = [{"input": item, "expected": [item]}]
            notes.append("escalar -> lista de um elemento (wrap_list do registro)")
        elif ta is not None and to is not None and ca and not co and ta["datatype"] == "list":
            item = sample(dict(ta["item_type"], _path=a), to, hint)
            r["translation_fn"] = {"name": "unwrap_single", "params": {}}
            tests = [{"input": [item], "expected": item}]
            r["loss_contract"] = r["loss_contract"] + [{"kind": "not_expressible", "why":
                                                        "lista com mais de um elemento não cabe no escalar do destino"}]
            notes.append("lista -> escalar só com um elemento (unwrap_single do registro)")
        else:
            r["translation_fn"] = {"name": "identity", "params": {}}
            x = sample(ta_s, to, hint)
            tests = [{"input": x, "expected": x}]
    r["proof"] = {"type": "normalization", "evidence": evs, "tests": tests}
    r["value_domain_relation"] = {"relation": "unknown", "orientation": "subject_to_object"}
    vdr = vdr_of(r)
    r["value_domain_relation"]["relation"] = vdr
    if policy == "priority":
        rng = (to or {}).get("range")
        loss = []
        if rng:
            loss.append({"kind": "saturation", "min": rng["min"], "max": rng["max"],
                         "why": "a faixa do destino é mais estreita; fora dela o valor não atravessa"})
        loss.append({"kind": "semantic", "why": "ordinal com o menor prevalecendo nos dois lados, mas o desempate "
                     "difere (num lado a negação prevalece no empate; no outro a prioridade é única na coleção)"})
        r["loss_contract"] = r["loss_contract"] + loss
        r["transport_fidelity"] = "declared_loss"
        notes.append("prioridade: mesmo papel ordinal; faixas e desempate diferentes (close)")
    elif policy == "address":
        r["loss_contract"] = r["loss_contract"] + [{"kind": "semantic", "why": "cada provedor admite formas próprias além do CIDR literal "
                               "(rótulos de serviço, '*', listas, IPv4 e IPv6 separados ou juntos); só o CIDR literal "
                               "atravessa e o predicado de CIDR não se escreve na linguagem fechada"}]
        r["transport_fidelity"] = "declared_loss"
        notes.append("endereço: inclusão estrita sem predicado exprimível (sem gramática de CIDR) -> close")
    elif policy == "ref":
        terms = []
        for role, rr in (("subject", ra), ("object", rb)):
            tgt = b.ref_target.get(rr["atom"])
            if tgt:
                term = f"{role}.{rr['path']}"
                r["guard"] = dict(r["guard"])
                r["guard"]["all"] = sorted(r["guard"]["all"] + [{"term": term, "op": "refers_to_kind", "value": tgt}],
                                           key=lambda x: json.dumps(x, sort_keys=True))
                terms.append(term)
        if terms:
            r["loss_contract"] = r["loss_contract"] + [{"kind": "context_dependence", "terms": sorted(terms),
                                   "why": "a referência simbólica só atravessa se o alvo foi traduzido para o tipo da guarda"}]
        r["transport_fidelity"] = "partial"
        notes.append("referência: identidade sobre a referência simbólica, alvo re-resolvido pelo tradutor")
    else:
        if vdr in ("equal", "subset") and policy == "direction":
            r["transport_fidelity"] = "lossless"
        elif any(x["kind"] == "not_expressible" for x in r["loss_contract"]):
            r["transport_fidelity"] = "declared_loss"
        else:
            r["transport_fidelity"] = "partial"
        if vdr == "unknown":
            notes.append("vocabulário de valores não declarado no pacote: domínio unknown, transporte parcial")
    projs = [p for p in (projection_for(b, ra), projection_for(b, rb)) if p]
    if projs:
        r["projection"] = projs
    if "unknown" in (ra["shape"].get("eff"), rb["shape"].get("eff")):
        notes.append("efeito de um lado não documentado no pacote: sem guarda de efeito")
    r["comment"] = f"faixa {slot}; " + "; ".join(notes) if notes else f"faixa {slot}"
    return r


def group_for(pair, kind, rp, rt, subject_is_pair: bool, guard, b: Bundle) -> dict:
    """Grupo N:1 (início, fim -> texto, join_port_range) ou 1:N (texto -> início, fim, split_port_range)."""
    (ps, f_from, f_to), (ts_, f_txt) = rp, rt
    a_from, a_to, a_txt = atom_of(ps, f_from), atom_of(ps, f_to), atom_of(ts_, f_txt)
    for x in (a_from, a_to, a_txt):
        if b.types.get(x) is None:
            raise Skip(f"{x}: sem tipo no pacote (componente do grupo não se tipa)")
    if is_coll(b.types[a_txt]):
        raise Skip(f"{a_txt}: faixa em lista; o grupo precisaria de join_port_range seguido de wrap_list com variável "
                   "intermediária, e a G-VARS exige campo para toda variável")
    sp, st = D.SHAPES[ps], D.SHAPES[ts_]
    side_p, side_t = ("subject", "object") if subject_is_pair else ("object", "subject")
    tup = {"datatype": "tuple", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE",
           "components": [{"name": "from_port", "type": b.types[a_from]}, {"name": "to_port", "type": b.types[a_to]}]}
    txt = {"datatype": "tuple", "quantity_kind": "NOT_APPLICABLE", "unit": "NOT_APPLICABLE",
           "components": [{"name": "ports", "type": b.types[a_txt]}]}
    pid, tid = f"{sp['prov']}:{sp['rtype']}", f"{st['prov']}:{st['rtype']}"
    s_id, o_id = (pid, tid) if subject_is_pair else (tid, pid)
    variables = [{"name": "?from_port", "side": side_p, "field": field_of(a_from), "occurrence": "?p"},
                 {"name": "?to_port", "side": side_p, "field": field_of(a_to), "occurrence": "?p"},
                 {"name": "?ports", "side": side_t, "field": field_of(a_txt), "occurrence": "?t"}]
    if subject_is_pair:
        steps = [{"name": "join_port_range", "inputs": {"from_port": "?from_port", "to_port": "?to_port"},
                  "outputs": {"ports": "?ports"}}]
        tests = [{"input": {"?from_port": 80, "?to_port": 90}, "expected": {"?ports": "80-90"}},
                 {"input": {"?from_port": 443, "?to_port": 443}, "expected": {"?ports": "443"}}]
        loss, card = [], "N:1"
    else:
        steps = [{"name": "split_port_range", "inputs": {"ports": "?ports"},
                  "outputs": {"from_port": "?from_port", "to_port": "?to_port"}}]
        tests = [{"input": {"?ports": "80-90"}, "expected": {"?from_port": 80, "?to_port": 90}},
                 {"input": {"?ports": "443"}, "expected": {"?from_port": 443, "?to_port": 443}}]
        loss = [{"kind": "not_expressible", "why": "'p-p' volta 'p' e zeros à esquerda somem (perda do registro)"}]
        card = "1:N"
    occ = sorted({"?p", "?t"})
    gid = None  # preenchido na numeração
    r = _base(pair, s_id, o_id, "exact", b)
    r.update(subject_concept=UNGLOSSED, object_concept=UNGLOSSED, guard=guard, translation_fn=None,
             subject_value_type=tup if subject_is_pair else txt, object_value_type=txt if subject_is_pair else tup,
             loss_contract=loss, transport_fidelity="declared_loss" if loss else "partial",
             value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"})
    st_ev, evs = evidence_for(b, [a_from, a_to, a_txt])
    r["evidence_state"] = st_ev
    r["proof"] = {"type": "group_execution", "evidence": evs, "tests": tests}
    r["group"] = {"bo_group_id": gid, "cardinality": card, "joins": [], "occurrence_vars": occ,
                  "variables": variables, "steps": steps}
    r["comment"] = (f"grupo de portas {kind}: início e fim numéricos <-> faixa em texto; o pacote não documenta "
                    "os valores de protocolo, então a sobrecarga ICMP de início/fim não entra na guarda")
    r["_covers"] = [a_from, a_to, a_txt]
    return r


def fixed_effect_for(pair, ra, oshape_id, b: Bundle) -> dict:
    sh = D.SHAPES[oshape_id]
    a = atom_of(ra[0], ra[1])
    ta = b.types.get(a)
    if ta is None or ta.get("datatype") != "enum":
        raise Skip(f"{a}: efeito sem enum no pacote")
    allow = D.SHAPES[ra[0]]["eff_vals"]["allow"]
    others = [v for v in ta["enum"] if v != allow]
    pins = sorted({(s.get("pin") or {}).get("provider_version") for s in b.se_by_type.get(f"{sh['prov']}:{sh['rtype']}", [])
                   if (s.get("pin") or {}).get("provider_version")})
    if not pins:
        raise Skip(f"{sh['rtype']}: versão fixada do provider ausente no pacote")
    r = _base(pair, a, f"{sh['prov']}:{sh['rtype']}", "narrow", b)
    r["object_concept"] = UNGLOSSED
    r.update(subject_value_type=ta,
             object_value_type={"datatype": "enum", "enum": [allow], "quantity_kind": "NOT_APPLICABLE",
                                "unit": "NOT_APPLICABLE"},
             translation_fn={"name": "identity", "params": {}},
             fixed_default={"kind": "fixed", "value": allow,
                            "context": {"all": [{"term": "object.provider_version", "op": "version_range",
                                                 "value": {"min": pins[0]}}]},
                            "evidence": {"date": D.MAPPING_DATE,
                                         "source": f"bundle:slice_notes.jsonl#{D.EFFECT_NOTES[sh['prov']]}"}},
             membership_predicate={"subset": "object", "expr": {"op": "in", "values": [allow]},
                                   "tests": {"members": [allow], "non_members": others}},
             transport_fidelity="partial")
    r["value_domain_relation"] = {"relation": "unknown", "orientation": "subject_to_object"}
    r["value_domain_relation"]["relation"] = vdr_of(r)
    _, evs = evidence_for(b, [a])
    # o lado de efeito fixo não tem sentença publicada (C25: effect unknown); a nota do glossarista não é documentação
    r["evidence_state"] = "STRUCTURALLY_VALID"
    r["proof"] = {"type": "membership", "evidence": evs, "tests": [{"input": allow, "expected": allow}]}
    r["comment"] = ("efeito: o destino só tem regras que permitem (sem atributo); valor fixo no vocabulário do sujeito; "
                    "o C25 marca o efeito do destino como unknown, por isso STRUCTURALLY_VALID")
    r["_covers"] = [a]
    return r


# ----------------------------------------------------------------------------------------------- ausência
def _rule_match(rule, atom: str, other: str) -> bool:
    prov, pat, oth = rule[0], rule[1], rule[2]
    if prov not in ("*", provider_of(atom)) or oth not in ("*", other):
        return False
    rtype_path = atom.split(":", 1)[1]
    if pat.startswith("*:"):
        p = pat[2:]
        path = atom.split(":", 2)[2]
        return path.startswith(p) if p.endswith(".") else path == p or path.endswith("." + p)
    return rtype_path == pat


def absence_for(pair, atom: str, other: str, b: Bundle, related_ids: list[str], skipped: list[str],
                eff_fixed: dict | None = None) -> dict:
    kind, why = None, None
    if atom.endswith(":access") and atom.startswith("azurerm:") and (eff_fixed or {}).get(other):
        kind = "UNRESOLVED"
        why = (f"o outro lado só tem regra de permitir (âncoras publicadas {', '.join(eff_fixed[other])}), sem "
               "atributo; o fixed_default não se exprime com o lado sem atributo como sujeito do par")
    for rule in ([] if kind else D.ABSENCE_RULES):
        if _rule_match(rule, atom, other):
            kind, why = rule[3], rule[4]
            break
    if kind is None and related_ids:
        kind = "UNSUPPORTED_BY_TRANSLATOR"
        why = f"só há relação related com o outro lado ({', '.join(sorted(related_ids))}); related não transporta"
    if kind is None and skipped:
        kind = "UNRESOLVED"
        why = "emparelhamento que não se escreve com o que o pacote declara: " + "; ".join(sorted(set(skipped)))[:400]
    role = (b.canonical.get(atom) or {}).get("role")
    path = atom.split(":", 2)[2]
    if kind is None and (role in D.IDENTITY_ROLES or path.split(".")[-1] in D.COMPUTED_PATHS):
        same = [x for x in b.provider_atoms(other) if (b.canonical[x].get("role") == role and role)]
        kind = "UNSUPPORTED_BY_TRANSLATOR" if same else "ABSENCE_DEMONSTRATED"
        why = ("atributo atribuído pela API; o outro lado tem o próprio, que não se traduz por valor" if same
               else "atributo atribuído pela API sem análogo no outro lado")
    if kind is None and b.types.get(atom) is None and atom not in b.types and "." in path:
        kind = "UNRESOLVED"
        why = "campo de bloco embutido sem tipo no pacote; nenhuma alegação do outro lado o alcança"
    if kind is None:
        kind = "ABSENCE_DEMONSTRATED"
        why = "nenhum átomo canônico do outro lado realiza esta decisão"
    types = b.types_by_provider.get(other, [])
    searched = [f"átomos canônicos de {other} no pacote ({len(b.provider_atoms(other))} átomos; tipos: {', '.join(types)})",
                f"vizinhos por referência e anexação dos tipos de {other} na fatia"]
    ev = [{"source": f"bundle:canonical_atoms.jsonl#{other}", "sentence": why, "date": D.MAPPING_DATE}]
    obj_side = provider_of(atom) != PAIRS[pair][0]
    r = _base(pair, NO_TERM, atom, "related", b) if obj_side else _base(pair, atom, NO_TERM, "related", b)
    absence = {"kind": kind, "searched": searched, "evidence": ev}
    if obj_side:
        absence["side"] = "object"
    r.update(translation_fn=None, transport_fidelity="none",
             value_domain_relation={"relation": "unknown", "orientation": "subject_to_object"},
             evidence_state="STRUCTURALLY_VALID", proof={"type": "absence", "evidence": ev, "tests": []},
             absence=absence)
    if obj_side:
        r.update(subject_concept=UNGLOSSED, object_concept=b.concept(atom))
    else:
        r.update(object_concept=UNGLOSSED)
    t = b.types.get(atom)
    if t is not None:
        r["object_value_type" if obj_side else "subject_value_type"] = t
    shape = next((sh for sh in D.SHAPES.values() if sh.get("block") and
                  atom.startswith(f"{sh['prov']}:{sh['rtype']}:{sh['prefix']}")), None)
    if shape is not None:
        p = projection_for(b, {"atom": atom, "shape": shape})
        if p:
            r["projection"] = [p]
    r["comment"] = (f"ausência no par {pair}, lado {'objeto' if obj_side else 'sujeito'} (sem contraparte em "
                    f"{other})")
    return r


# -------------------------------------------------------------------------------------------------- geração
def generate(b: Bundle) -> tuple[list[dict], dict]:
    reals, missing = realizations(b)
    by_pair: dict[str, list[dict]] = {p: [] for p in PAIRS}
    skipped: dict[tuple, list] = {}
    stats = {"missing_members": missing, "skipped_pairings": 0}
    slot_cfg = {s["slot"]: s for s in D.SLOTS}
    set_level = {"set_name", "set_tags", "set_network", "attach_set", "attach_nic"}
    shapes = resolved_shapes(b)
    stats["effect_resolved"] = {sid: sh["eff_source"] for sid, sh in shapes.items() if sh.get("eff_source")}
    eff_fixed: dict[str, list[str]] = {}
    for sh in shapes.values():
        if sh.get("eff_source") and sh["eff"] == "allow":
            eff_fixed.setdefault(sh["prov"], [])
            eff_fixed[sh["prov"]] = sorted(set(eff_fixed[sh["prov"]]) | set(sh["eff_source"]))
    for pair, (P, Q) in PAIRS.items():
        for slot, lst in reals.items():
            pol = slot_cfg[slot]["policy"]
            for ra in [r for r in lst if r["shape"]["prov"] == P]:
                for rb in [r for r in lst if r["shape"]["prov"] == Q]:
                    try:
                        if slot in set_level:
                            gs = [{"all": []}]
                        else:
                            gs = guards_for(b, ra, rb, with_dir=(pol != "direction"))
                        for g in gs:
                            by_pair[pair].append({"_kind": "claim", **claim_for(pair, slot, pol, ra, rb, g, b)})
                    except Skip as e:
                        stats["skipped_pairings"] += 1
                        for x in (ra["atom"], rb["atom"]):
                            skipped.setdefault((pair, x), []).append(str(e))
        # grupos de portas
        for kind, pairs_list in (("dst", D.PORT_PAIRS), ("src", D.SRC_PORT_PAIRS)):
            for rp in pairs_list:
                for rt in D.PORT_TEXT[kind]:
                    pp, tp = D.SHAPES[rp[0]]["prov"], D.SHAPES[rt[0]]["prov"]
                    if {pp, tp} != {P, Q}:
                        continue
                    subj_pair = pp == P
                    ra = {"atom": atom_of(rp[0], rp[1]), "shape": shapes[rp[0]], "dir_override": None}
                    rb = {"atom": atom_of(rt[0], rt[1]), "shape": shapes[rt[0]], "dir_override": None}
                    try:
                        gs = guards_for(b, ra, rb) if subj_pair else guards_for(b, rb, ra)
                        for g in gs:
                            by_pair[pair].append({"_kind": "group", **group_for(pair, kind, rp, rt, subj_pair, g, b)})
                    except Skip as e:
                        stats["skipped_pairings"] += 1
                        for x in (ra["atom"], rb["atom"], atom_of(rp[0], rp[2])):
                            skipped.setdefault((pair, x), []).append(str(e))
        # efeito fixo (só onde o lado com atributo é o sujeito)
        seen_rt = set()
        for (zs, zp, os_) in D.FIXED_EFFECT:
            if D.SHAPES[zs]["prov"] != P or D.SHAPES[os_]["prov"] != Q or D.SHAPES[os_]["rtype"] in seen_rt:
                continue
            seen_rt.add(D.SHAPES[os_]["rtype"])
            try:
                by_pair[pair].append({"_kind": "fixed", **fixed_effect_for(pair, (zs, zp), os_, b)})
            except Skip as e:
                stats["skipped_pairings"] += 1
                skipped.setdefault((pair, atom_of(zs, zp)), []).append(str(e))
    # ausências
    for pair, (P, Q) in PAIRS.items():
        rows = by_pair[pair]
        covered, related = set(), {}
        for r in rows:
            if r["semantic_relation"] in TRANSPORTING:
                covered |= set(r.get("_covers") or [r["subject_id"], r["object_id"]])
            elif r["semantic_relation"] == "related":
                for x in (r["subject_id"], r["object_id"]):
                    related.setdefault(x, []).append(r)
        for prov, other in ((P, Q), (Q, P)):
            for atom in b.provider_atoms(prov):
                if atom in covered:
                    continue
                rel_ids = [x["subject_id"] + " ~ " + x["object_id"] for x in related.get(atom, [])]
                rows.append({"_kind": "absence", **absence_for(pair, atom, other, b, rel_ids,
                                                                 skipped.get((pair, atom), []), eff_fixed)})
    # numeração determinística
    out = []
    for pair in PAIRS:
        rows = sorted(by_pair[pair], key=lambda r: (KINDS_ORDER[r["_kind"]], r["subject_id"], r["object_id"],
                                                    json.dumps(r.get("guard"), sort_keys=True)))
        for i, r in enumerate(rows, 1):
            cid = f"CLM-{pair}-NET-{i:04d}"
            r = {k: v for k, v in r.items() if not k.startswith("_") and v is not None}
            r["claim_id"], r["claim_version_id"], r["event_id"] = cid, f"{cid}@1", f"EV-{cid}-1"
            if r.get("group") is not None:
                gid = f"GRP-{pair}-NET-{i:04d}"
                r["group"] = dict(r["group"], bo_group_id=gid)
                r["bo_group_id"] = gid
            out.append(r)
    stats["skipped_by_atom"] = {f"{p}|{a}": sorted(set(v)) for (p, a), v in sorted(skipped.items())}
    return out, stats


def decisions_log(b: Bundle, records: list[dict]) -> list[dict]:
    """Candidatos do glossarista (shared_concept, hipótese) e o que o mapeador fez com cada um."""
    by_pair_atoms = {}
    for r in records:
        if r["semantic_relation"] in TRANSPORTING:
            pair = r["claim_id"].split("-")[1]
            by_pair_atoms.setdefault((pair, r["subject_id"], r["object_id"]), []).append(r["claim_id"])
    out = []
    for c in sorted(b.candidates, key=lambda x: x["candidate_id"]):
        s = [n["ref"] for n in c["subject"]["nodes"] if n.get("kind") == "atom"]
        o = [n["ref"] for n in c["object"]["nodes"] if n.get("kind") == "atom"]
        hits = sorted({cid for x in s for y in o for cid in by_pair_atoms.get((c["pair"], x, y), [])})
        out.append({"candidate_id": c["candidate_id"], "pair": c["pair"], "concept": c.get("concept"),
                    "subject": s, "object": o, "taken_as_direct": hits,
                    "decision": "alegação direta com citação própria" if hits else
                    "não tomada como alegação (ver ausências e faixas do par)"})
    return out
