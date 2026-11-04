"""Obrigações por alegação (A1, A2, A3): a referência é bo.semantics.obligations.assess; aqui só a adaptação.

O assess do SEMANTICS julga uma alegação escalar com translation_fn do núcleo. O C09 tem mais três formas, e o
árbitro as reduz à forma que o assess julga, sem afrouxar nada:
  projeção   a alegação fala da PARTE que a projeção extrai do campo (um campo, vários conceitos: F3). Tipo do
             lado = tipo da projeção; id interno do lado = '<campo>#<parte>'; etapa inicial de translation_fn
             igual ao extrator é descartada (ele já roda na projeção); entrada de teste que é o campo inteiro
             passa pelo extrator (quando o extrator aceita a entrada, ela é o campo inteiro). Várias projeções do mesmo campo: transporta a de concept = conceito da
             alegação (ARB-PROJ-PART). check_projections (P-OCC, P-EXEC, P-OVERLAP) roda sobre todas.
  grupo      regra sobre subgrafo: check_group (G-VARS, G-ARITY, G-OCC) + ARB-G-DUP, ARB-G-TYPE, ARB-G-EXEC; o
             assess roda sem translation_fn (os passos são a normalização) e a falha EXACT-NORM dele sai.
  registro   etapa que só existe no registro fechado do TRANSFORMS: tipada com check_chain (ARB-FN-TYPE) e
             testada com apply_* do registro (EXACT-TESTS); o assess roda sem a cadeia (EXACT-NORM sai) e, sem
             domínio calculável, 'sem perda' continua UNPROVEN (VDR-UNKNOWN).
Âncoras (F4): resolvidas no glossário auditado C20 (ARB-ANCHOR), nunca pelo estado que o mapeador declarou;
evidência que só cita o glossário é o caminho átomo→conceito←átomo e cai na ANCHOR-NOT-PROOF.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from bo.contracts import catalog as CCAT
from bo.contracts import validate as CVAL
from bo.semantics import guards as G
from bo.semantics import projections as PJ
from bo.semantics import transforms as ST
from bo.semantics.claims import Claim as _SClaim, check_predicate as _check_predicate
from bo.semantics.obligations import assess
from bo.semantics.valuetypes import OutOfDomain, TypeError_, ValueType
from bo.transforms import registry as TR
from bo.transforms.errors import TransformError

from .rules import verdict_of

C09_REF = "https://w3id.org/brevops/contracts/C09/correspondences.schema.json#/$defs/correspondence"
UNGLOSSED = "bo:UNGLOSSED"
ANCHOR_OK = ("DOC_SUPPORTED", "OBSERVATION_TESTED")     # as mesmas da ANCHOR-NOT-PROOF do SEMANTICS
GLOSSARY_SOURCES = ("concept:", "glossary:", "anchor:")
_SCHEMAS = None


def _validator():
    global _SCHEMAS
    if _SCHEMAS is None:
        _SCHEMAS = CCAT.schemas()
    return CVAL.validator_for(C09_REF, _SCHEMAS)


def F(rule, outcome, detail):
    return {"rule": rule, "outcome": outcome, "detail": str(detail)[:400]}


@dataclass
class Side:
    """Um lado da alegação como o árbitro o enxerga: campo, parte projetada, ocorrência e tipo."""
    field: str
    part: str = "*"
    occ: tuple = ()
    type: dict | None = None
    concept: str | None = None
    projected: bool = False

    @property
    def id(self) -> str:
        return self.field if self.part == "*" else f"{self.field}#{self.part}"

    @property
    def key(self) -> tuple:
        return (self.id, self.occ)


@dataclass
class Checked:
    item: dict
    failures: list = field(default_factory=list)
    form: str = "plain"                 # plain | projection | group | absence | invalid
    eff: dict | None = None             # alegação efetiva (ids internos por parte) para conjunto e K4
    subject: Side | None = None
    object: Side | None = None
    group_sides: list = field(default_factory=list)   # [(lado, Side)] das variáveis do grupo
    computed: dict = field(default_factory=dict)
    fn_path: str = "core"               # core | registry | unknown (só o núcleo do SEMANTICS compõe no K4)

    @property
    def rec(self) -> dict:
        return self.item["rec"]

    @property
    def cid(self) -> str:
        return str(self.rec.get("claim_id"))

    @property
    def vid(self) -> str:
        return str(self.rec.get("claim_version_id"))

    @property
    def verdict(self) -> str:
        return verdict_of(f["outcome"] for f in self.failures)

    @property
    def relation(self) -> str | None:
        return self.rec.get("semantic_relation")


# ------------------------------------------------------------------------------------------ função de tradução
def fn_names(fn) -> list[str]:
    return [i.get("name") for i in ST.chain_of(fn) if isinstance(i, dict)]


def fn_path(fn) -> tuple[str, list[str]]:
    """('core' | 'registry' | 'unknown', etapas fora dos dois). Comparador do registro não é tradução."""
    names = fn_names(fn)
    if all(n in ST.REGISTRY for n in names):
        return "core", []
    bad = []
    for n in names:
        if n in ST.REGISTRY:
            continue
        try:
            t = TR.get(n)
        except TransformError:
            bad.append(n)
            continue
        if getattr(t, "c11_name", None) or str(n).startswith("compare_"):
            bad.append(n)
    return ("unknown" if bad else "registry"), bad


def _reg_apply(chain, v, ctx=None):
    for item in ST.chain_of(chain):
        t = TR.get(item["name"])
        p = item.get("params") or {}
        if isinstance(t, TR.Scalar):
            v = TR.apply_scalar(item["name"], v, p, ctx)
        else:
            ports = [i[0] for i in t.inputs]
            out = TR.apply_combinator(item["name"], v if isinstance(v, dict) else {ports[0]: v}, ctx)
            v = out[next(iter(out))] if len(out) == 1 else out
    return v


def _same(a, b) -> bool:
    from bo.semantics.predicates import _eq
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    return _eq(a, b)


# -------------------------------------------------------------------------------------------------- projeções
def _proj_part(p: dict) -> str:
    ex = p.get("extractor") or {}
    if ex.get("component"):
        return ex["component"]
    key = (ex.get("params") or {}).get("key")
    if key is not None:
        return f"{ex.get('name')}:{key}"
    return "*" if ex.get("name") == "identity" else str(ex.get("name"))


def _proj_occ(p: dict) -> tuple:
    o = p.get("occurrence") or {}
    return (o.get("scope", "resource"),) + tuple(sorted(o.get("key_fields") or ()))


def extract(p: dict, v):
    ex = p["extractor"]
    out = ST.apply({"name": ex["name"], "params": ex.get("params")}, v)
    return out[ex["component"]] if ex.get("component") else out


def _pick(projs, fieldname, concept, fails, side):
    mine = [p for p in projs if p.get("field") == fieldname]
    if not mine:
        return None
    if len(mine) == 1:
        return mine[0]
    hit = [p for p in mine if p.get("concept") == concept]
    if len(hit) == 1:
        return hit[0]
    fails.append(F("ARB-PROJ-PART", "REFUTED_BY_RULE",
                   f"{len(mine)} projeções de {fieldname} ({side}) e {len(hit)} com concept = {concept}: parte indefinida"))
    return None


def _strip_extractor(chain, p):
    ch = ST.chain_of(chain)
    ex = p.get("extractor") or {}
    if ch and ch[0].get("name") == ex.get("name") and (ch[0].get("params") or {}) == (ex.get("params") or {}):
        ch = ch[1:]
    if not ch:
        return {"name": "identity", "params": {}}
    return ch[0] if len(ch) == 1 else ch


def _effective(rec: dict, ps, po) -> dict:
    """Alegação sobre as partes projetadas (ids internos '<campo>#<parte>')."""
    e = copy.deepcopy(rec)
    e.pop("projection", None)
    tests = list(((e.get("proof") or {}).get("tests")) or [])
    if ps is not None:
        e["subject_value_type"] = ps["type"]
        e["subject_id"] = Side(ps["field"], _proj_part(ps)).id
        if e.get("translation_fn") is not None:
            e["translation_fn"] = _strip_extractor(e["translation_fn"], ps)
        nt = []
        for t in tests:
            t = dict(t)
            if "input" in t:
                try:
                    t["input"] = extract(ps, t["input"])
                except (OutOfDomain, TypeError_, KeyError, TypeError):
                    pass
            nt.append(t)
        tests = nt
    if po is not None:
        e["object_value_type"] = po["type"]
        e["object_id"] = Side(po["field"], _proj_part(po)).id
        nt = []
        for t in tests:
            t = dict(t)
            if "expected" in t:
                try:
                    t["expected"] = extract(po, t["expected"])
                except (OutOfDomain, TypeError_, KeyError, TypeError):
                    pass
            nt.append(t)
        tests = nt
    if e.get("proof") is not None:
        e["proof"] = dict(e["proof"])
        e["proof"]["tests"] = tests
    return e


# ------------------------------------------------------------------------------------------------------ grupos
def _group_dups(g: dict) -> list[dict]:
    out = []
    writers: dict[str, list] = {}
    for i, s in enumerate(g.get("steps") or []):
        for var in (s.get("outputs") or {}).values():
            writers.setdefault(var, []).append(i)
    for var, ws in sorted(writers.items()):
        if len(ws) > 1:
            out.append(F("ARB-G-DUP", "REFUTED_BY_RULE", f"variável {var} escrita por {len(ws)} passos"))
    slots: dict[tuple, list] = {}
    for v in g.get("variables") or []:
        slots.setdefault((v.get("side"), v.get("field"), v.get("occurrence")), []).append(v.get("name"))
    for k, names in sorted(slots.items(), key=lambda kv: str(kv[0])):
        if len(names) > 1:
            out.append(F("ARB-G-DUP", "REFUTED_BY_RULE", f"{sorted(map(str, names))} ligadas ao mesmo {k}"))
    seen = set()
    from .common import canon
    for s in g.get("steps") or []:
        k = canon(s)
        if k in seen:
            out.append(F("ARB-G-DUP", "REFUTED_BY_RULE", f"passo repetido: {s.get('name')}"))
        seen.add(k)
    return out


def _components(vt) -> dict | None:
    if not isinstance(vt, dict) or vt.get("datatype") != "tuple":
        return None
    return {c.get("name"): c.get("type") for c in vt.get("components") or [] if isinstance(c, dict)}


def _exec_group(g: dict, env: dict) -> dict:
    """Passos em ordem sobre {?var: valor}; passo com entrada faltando não roda (teste parcial)."""
    env = dict(env)
    for s in g.get("steps") or []:
        name = s["name"]
        sig = PJ.SIGNATURES[name]
        args = {a: env[var] for a, var in (s.get("inputs") or {}).items() if var in env}
        if len(args) != len(sig[0]):
            continue
        fn = {"name": name, "params": s.get("params")}
        if sig[0] == ("value",):
            out = {"value": ST.apply(fn, args["value"])}
        elif len(sig[0]) == 1:
            out = ST.apply(fn, args[sig[0][0]])
        else:
            out = ST.apply(fn, args)
        if len(sig[1]) == 1 and not isinstance(out, dict):
            out = {sig[1][0]: out}
        for comp, var in (s.get("outputs") or {}).items():
            env[var] = out[comp]
    return env


def _check_group(c: Checked, g: dict, repeated: set, disabled) -> None:
    rec = c.rec
    if rec.get("translation_fn") is not None and "ARB-G-FN" not in disabled:
        c.failures.append(F("ARB-G-FN", "REFUTED_BY_RULE", "grupo com translation_fn: duas normalizações"))
    if rec.get("bo_group_id") != g.get("bo_group_id") and "ARB-G-CONSIST" not in disabled:
        c.failures.append(F("ARB-G-CONSIST", "REFUTED_BY_RULE",
                            f"coluna bo_group_id {rec.get('bo_group_id')} != grupo {g.get('bo_group_id')}"))
    try:
        r = PJ.check_group(g, disabled=disabled)
        c.failures.extend(F(x["rule"], x["outcome"], x["detail"]) for x in r["failures"])
    except (KeyError, TypeError, AttributeError) as e:
        c.failures.append(F("G-VARS", "REFUTED_BY_RULE", f"grupo ilegível: {type(e).__name__}: {e}"))
        return
    if "ARB-G-DUP" not in disabled:
        c.failures.extend(_group_dups(g))
    vars_ = [v for v in g.get("variables") or [] if isinstance(v, dict)]
    comps = {"subject": _components(rec.get("subject_value_type")),
             "object": _components(rec.get("object_value_type"))}
    vtypes = {}
    for v in vars_:
        side, name = v.get("side"), str(v.get("name", ""))
        cs = comps.get(side)
        ty = None if cs is None else cs.get(name.lstrip("?"))
        if ty is None:
            if "ARB-G-TYPE" not in disabled:
                c.failures.append(F("ARB-G-TYPE", "REFUTED_BY_RULE",
                                    f"{name} ({side}) sem componente tipado em {side}_value_type"))
        else:
            vtypes[name] = ty
        occ = ()
        for p in rec.get("projection") or []:
            if p.get("field") == v.get("field") and (p.get("occurrence") or {}).get("scope") == "block":
                occ = _proj_occ(p)
        c.group_sides.append((side, Side(str(v.get("field")), "*", occ, ty)))
        if v.get("field") in repeated and not occ and "ARB-OCC-ID" not in disabled:
            c.failures.append(F("ARB-OCC-ID", "REFUTED_BY_RULE",
                                f"{name}: {v.get('field')} está em bloco repetido e a ocorrência {v.get('occurrence')} "
                                "não é identificada por campos-chave (projeção scope=block)"))
    if "ARB-G-EXEC" in disabled:
        return
    byname = {v.get("name"): v for v in vars_}
    tests = ((rec.get("proof") or {}).get("tests")) or []
    if not tests:
        c.failures.append(F("ARB-G-EXEC", "UNPROVEN", "grupo sem teste executável"))
    for t in tests:
        inp, exp = t.get("input"), t.get("expected")
        if not isinstance(inp, dict) or not isinstance(exp, dict) or not exp:
            c.failures.append(F("ARB-G-EXEC", "REFUTED_BY_RULE", f"teste de grupo não é {{?var: valor}}: {t}"))
            continue
        wrong = [k for k in inp if (byname.get(k) or {}).get("side") != "subject"] + \
                [k for k in exp if (byname.get(k) or {}).get("side") != "object"]
        if wrong:
            c.failures.append(F("ARB-G-EXEC", "REFUTED_BY_RULE", f"teste cita variável inexistente ou do lado errado: {wrong}"))
            continue
        bad_in = [k for k, v in inp.items() if k in vtypes and not _admits(vtypes[k], v)]
        if bad_in:
            c.failures.append(F("ARB-G-EXEC", "REFUTED_BY_RULE", f"entrada fora do tipo da variável: {bad_in}"))
            continue
        try:
            env = _exec_group(g, inp)
        except (OutOfDomain, TypeError_, KeyError) as e:
            c.failures.append(F("ARB-G-EXEC", "REFUTED_BY_RULE", f"grupo falha no teste {inp}: {e}"))
            continue
        for k, want in exp.items():
            if k not in env:
                c.failures.append(F("ARB-G-EXEC", "REFUTED_BY_RULE", f"{k} não é produzida a partir de {sorted(inp)}"))
            elif not _same(env[k], want):
                c.failures.append(F("ARB-G-EXEC", "REFUTED_BY_RULE", f"{k} = {env[k]!r}, teste diz {want!r}"))
            elif k in vtypes and not _admits(vtypes[k], env[k]):
                c.failures.append(F("ARB-G-EXEC", "REFUTED_BY_RULE", f"{k} = {env[k]!r} fora do tipo da variável"))


def _admits(tdict, v) -> bool:
    try:
        return ValueType.from_dict(tdict).admits(v)
    except (TypeError_, ValueError):
        return False


# ------------------------------------------------------------------------------------------------------ âncoras
def _anchors(c: Checked, glossary, disabled) -> None:
    if "ARB-ANCHOR" in disabled:
        return
    rec = c.rec
    sc, oc = rec.get("subject_concept"), rec.get("object_concept")
    evs = ((rec.get("proof") or {}).get("evidence")) or []
    cited = [e for e in evs if isinstance(e, dict) and e.get("source") and (e.get("sentence") or e.get("observation"))]
    only_gloss = bool(cited) and all(str(e.get("source")).startswith(GLOSSARY_SOURCES) or e.get("anchor_claim_id")
                                     for e in cited)
    if rec.get("basis") != "shared_concept":
        if only_gloss and sc == oc and sc not in (None, UNGLOSSED):
            c.failures.append(F("ANCHOR-NOT-PROOF", "UNPROVEN",
                                "a evidência só cita o glossário: átomo→conceito←átomo é alegação de âncora, não prova"))
        return
    anchors = rec.get("anchors") or []
    if sc != oc or sc in (None, UNGLOSSED):
        c.failures.append(F("ARB-ANCHOR", "REFUTED_BY_RULE", f"shared_concept com conceitos {sc} e {oc}"))
        return
    if glossary is None:
        c.failures.append(F("ARB-ANCHOR", "UNPROVEN",
                            "sem glossário auditado (C20): o estado das âncoras declarado pelo mapeador não é prova"))
        return
    if len(anchors) != 2:
        c.failures.append(F("ARB-ANCHOR", "UNPROVEN", f"{len(anchors)} âncora(s); são duas (sujeito e objeto)"))
        return
    want = {rec.get("subject_id"), rec.get("object_id")}
    got = set()
    for ref in anchors:
        a, st, why = glossary.resolve(ref if isinstance(ref, dict) else {})
        if a is None:
            c.failures.append(F("ARB-ANCHOR", "UNPROVEN", f"{ref}: {why}"))
            continue
        got.add(a.get("atom_id"))
        if a.get("concept_id") != sc:
            c.failures.append(F("ARB-ANCHOR", "REFUTED_BY_RULE", f"âncora {a['claim_version_id']} é de {a.get('concept_id')}, não {sc}"))
        if a.get("atom_id") not in want:
            c.failures.append(F("ARB-ANCHOR", "REFUTED_BY_RULE", f"âncora {a['claim_version_id']} é de outro átomo"))
        if st not in ANCHOR_OK:
            c.failures.append(F("ARB-ANCHOR", "UNPROVEN", f"âncora {a['claim_version_id']} em {st} ({why}); exige DOC_SUPPORTED"))
    if got and got != want and not any(f["rule"] == "ARB-ANCHOR" and f["outcome"] == "REFUTED_BY_RULE" for f in c.failures):
        c.failures.append(F("ARB-ANCHOR", "REFUTED_BY_RULE", "as âncoras não cobrem sujeito e objeto"))


# ------------------------------------------------------------------------------------------------------ ausência
NO_TERM = "sssom:NoTermFound"
ABSENCE_PROVEN = ("ABSENCE_DEMONSTRATED", "OUT_OF_PIN", "UNSUPPORTED_BY_TRANSLATOR")


def is_absence(rec: dict) -> bool:
    return bool(rec.get("absence")) or NO_TERM in (rec.get("subject_id"), rec.get("object_id"))


def _check_absence(c: Checked, dis) -> None:
    """Ausência tipada (C09-NONE, C09 3.2.0): veredito próprio, não é related.
    ARB-ABSENCE-WF   forma: absence presente; sssom:NoTermFound no lado oposto ao de absence.side (padrão subject:
                     o átomo é o sujeito e o objeto é NoTermFound); relatedMatch/related, fidelidade none, sem
                     translation_fn.                                                                   -> REFUTED
    ARB-ABSENCE-KIND kind UNRESOLVED: a busca não decidiu; a ausência é hipótese.                   -> UNPROVEN
    ARB-ABSENCE-EV   kind provado (ABSENCE_DEMONSTRATED, OUT_OF_PIN, UNSUPPORTED_BY_TRANSLATOR) sem evidência
                     citada (absence.evidence ou proof.evidence com fonte e sentença).             -> UNPROVEN
    Sem falha, OK: a ausência está provada como ausência (e não transporta nada)."""
    rec = c.rec
    ab = rec.get("absence") or {}
    side = ab.get("side", "subject")
    atom_key, none_key = ("subject_id", "object_id") if side == "subject" else ("object_id", "subject_id")
    wf = []
    if not ab:
        wf.append("sssom:NoTermFound sem o campo absence")
    if rec.get(none_key) != NO_TERM or rec.get(atom_key) == NO_TERM:
        wf.append(f"absence.side={side}: {none_key} tem de ser sssom:NoTermFound e {atom_key} o átomo")
    if rec.get("semantic_relation") != "related" or rec.get("predicate_id") != "skos:relatedMatch":
        wf.append("ausência é skos:relatedMatch/related")
    if rec.get("transport_fidelity") not in (None, "none"):
        wf.append(f"ausência com fidelidade {rec.get('transport_fidelity')}")
    if rec.get("translation_fn") is not None:
        wf.append("ausência com translation_fn")
    if wf and "ARB-ABSENCE-WF" not in dis:
        c.failures.append(F("ARB-ABSENCE-WF", "REFUTED_BY_RULE", "; ".join(wf)))
    kind = ab.get("kind")
    if kind not in ABSENCE_PROVEN:
        if "ARB-ABSENCE-KIND" not in dis:
            c.failures.append(F("ARB-ABSENCE-KIND", "UNPROVEN",
                                f"ausência {kind}: a busca registrada não decidiu; fica como hipótese"))
        return
    evs = list(ab.get("evidence") or []) + list(((rec.get("proof") or {}).get("evidence")) or [])
    cited = [e for e in evs if isinstance(e, dict) and e.get("source") and (e.get("sentence") or e.get("observation"))]
    if not cited and "ARB-ABSENCE-EV" not in dis:
        c.failures.append(F("ARB-ABSENCE-EV", "UNPROVEN", f"ausência {kind} sem evidência citada (fonte e sentença)"))


# ------------------------------------------------------------------------------------- domínio pelo registro
def registry_vdr(eff: dict) -> str:
    """Relação de domínios de uma cadeia só do registro do TRANSFORMS, calculada por enumeração exaustiva quando o
    domínio do sujeito é finito (enum, booleano, inteiro com faixa curta): imagem = registro aplicado a cada valor;
    valor fora do domínio da função parcial conta como sem contraparte (mesmo ajuste do SEMANTICS)."""
    from bo.semantics.obligations import PARTIAL_ADJUST
    from bo.semantics.valuetypes import EnumDomain, NumDomain, relation
    try:
        ts = ValueType.from_dict(eff["subject_value_type"])
        to = ValueType.from_dict(eff["object_value_type"])
        dom = ts.domain()
    except (TypeError_, OutOfDomain, ValueError, KeyError, TypeError):
        return "unknown"
    if isinstance(dom, EnumDomain):
        vals = list(dom.values)
    elif isinstance(dom, NumDomain) and dom.count() is not None and dom.count() <= 4000:
        vals = list(dom.points())
    else:
        return "unknown"
    img, undefined = set(), 0
    for v in vals:
        try:
            img.add(_reg_apply(eff["translation_fn"], v))
        except (TransformError, KeyError, TypeError, ValueError):
            undefined += 1
    if not img:
        return "disjoint"
    try:
        r = relation(EnumDomain(frozenset(img)), to.domain())
    except (TypeError_, OutOfDomain, TypeError):
        return "unknown"
    return PARTIAL_ADJUST[r] if undefined else r


LIFT_WRAP = {"equal": "subset", "subset": "subset", "superset": "overlap", "overlap": "overlap",
             "disjoint": "disjoint", "unknown": "unknown"}


def collection_vdr(eff: dict) -> str | None:
    """wrap_list (escalar -> lista de um elemento) e unwrap_single (lista de exatamente um -> escalar), do registro do
    TRANSFORMS: a relação de domínios sobe do ELEMENTO para a lista (CC-13 do PILOT-STO-MAP). None = não é o caso.
      wrap_list     imagem = {[x] : x ∈ dom(sujeito)}. Com o elemento do sujeito ⊆ item_type do objeto, a imagem é
                    subconjunto PRÓPRIO das listas do objeto (há listas vazias e de 2+ elementos): 'subset'.
                    Elemento sobreposto -> overlap; disjunto -> disjoint; relação do elemento unknown -> unknown.
      unwrap_single definida só nas listas de um elemento: imagem = dom(item_type) pela função; a relação do elemento
                    com o objeto leva o ajuste de função parcial do SEMANTICS (equal->superset, subset->overlap).
    A relação do elemento é a do SEMANTICS (valuetypes.relation): domínio aberto (texto sem enum) dá unknown, como
    no núcleo; com domínio finito, o elemento passa pelo registro valor a valor."""
    from bo.semantics.obligations import PARTIAL_ADJUST
    from bo.semantics.valuetypes import EnumDomain, relation
    ch = ST.chain_of(eff.get("translation_fn"))
    if len(ch) != 1 or ch[0].get("name") not in ("wrap_list", "unwrap_single"):
        return None
    name = ch[0]["name"]
    try:
        ts = ValueType.from_dict(eff["subject_value_type"])
        to = ValueType.from_dict(eff["object_value_type"])
    except (TypeError_, OutOfDomain, ValueError, KeyError, TypeError):
        return "unknown"
    if name == "wrap_list":
        if to.datatype != "list" or to.item is None or ts.datatype in ("list", "set", "map"):
            return "disjoint" if to.datatype != "list" else "unknown"
        sd, it = ts.domain(), to.item
        if isinstance(sd, EnumDomain):
            img, out_of = set(), 0
            for v in sd.values:
                try:
                    y = _reg_apply(ch, v)
                except (TransformError, KeyError, TypeError, ValueError):
                    out_of += 1
                    continue
                if isinstance(y, list) and len(y) == 1 and it.admits(y[0]):
                    img.add(1)
                else:
                    out_of += 1
            if not img:
                return "disjoint"
            return "overlap" if out_of else "subset"
        try:
            return LIFT_WRAP[relation(sd, it.domain())]
        except (TypeError_, OutOfDomain, TypeError):
            return "unknown"
    if ts.datatype != "list" or ts.item is None:
        return "unknown"
    idom = ts.item.domain()
    if isinstance(idom, EnumDomain):
        img = set()
        for v in idom.values:
            try:
                img.add(_reg_apply(ch, [v]))
            except (TransformError, KeyError, TypeError, ValueError):
                pass
        if not img:
            return "disjoint"
        try:
            r = relation(EnumDomain(frozenset(img)), to.domain())
        except (TypeError_, OutOfDomain, TypeError):
            return "unknown"
    else:
        try:
            r = relation(idom, to.domain())
        except (TypeError_, OutOfDomain, TypeError):
            return "unknown"
    return PARTIAL_ADJUST[r]


def _registry_domain(c: Checked, eff: dict, dis) -> None:
    cv = collection_vdr(eff)
    vdr = cv if cv is not None else registry_vdr(eff)
    c.computed["vdr"] = vdr
    if vdr == "unknown":
        return
    c.failures = [f for f in c.failures if f["rule"] != "VDR-UNKNOWN"]
    decl = (eff.get("value_domain_relation") or {}).get("relation")
    fid = eff.get("transport_fidelity")
    if decl not in (None, "unknown", vdr) and "VDR-COMPUTED" not in dis:
        c.failures.append(F("VDR-COMPUTED", "REFUTED_BY_RULE",
                            f"declarada {decl}, calculada {vdr} pelo registro do TRANSFORMS (enumeração do domínio)"))
    if fid == "lossless" and vdr in ("superset", "overlap", "disjoint") and "FID-COHERENT" not in dis:
        c.failures.append(F("FID-COHERENT", "REFUTED_BY_RULE", f"sem perda com domínio {vdr}: há valor que não cabe"))
    if vdr == "disjoint" and fid not in (None, "none") and "FID-COHERENT" not in dis:
        c.failures.append(F("FID-COHERENT", "REFUTED_BY_RULE", "domínios disjuntos: nenhum valor atravessa"))


# ---------------------------------------------------------------------------------------------------- principal
def _assess_into(c: Checked, rec: dict, drop: tuple, disabled) -> None:
    try:
        a = assess(rec, disabled=disabled)
    except Exception as e:      # noqa: BLE001 - nada de entrada derruba o árbitro
        c.failures.append(F("ARB-MALFORMED", "REFUTED_BY_RULE", f"assess: {type(e).__name__}: {e}"))
        return
    c.computed.update(a.computed)
    c.failures.extend(F(f["rule"], f["outcome"], f["detail"]) for f in a.failures if f["rule"] not in drop)


def _registry_checks(c: Checked, rec: dict, disabled) -> None:
    chain = rec.get("translation_fn")
    st, ot = rec.get("subject_value_type"), rec.get("object_value_type")
    if st and ot and "ARB-FN-TYPE" not in disabled and all(isinstance(TR.get(n), TR.Scalar) for n in fn_names(chain)):
        try:
            TR.check_chain(chain, st, ot)
        except (TransformError, KeyError, TypeError, ValueError) as e:
            c.failures.append(F("ARB-FN-TYPE", "REFUTED_BY_RULE", f"cadeia do registro não tipa: {e}"))
    if "EXACT-TESTS" in disabled:
        return
    tests = ((rec.get("proof") or {}).get("tests")) or []
    if not tests:
        c.failures.append(F("EXACT-TESTS", "UNPROVEN", "normalização sem testes executáveis"))
    for t in tests:
        if "input" not in t or "expected" not in t:
            c.failures.append(F("EXACT-TESTS", "UNPROVEN", f"teste sem input/expected: {t}"))
            continue
        if st and not _admits(st, t["input"]):
            c.failures.append(F("EXACT-TESTS", "REFUTED_BY_RULE", f"entrada de teste fora do tipo do sujeito: {t['input']!r}"))
            continue
        try:
            y = _reg_apply(chain, t["input"], t.get("context"))
        except (TransformError, KeyError, TypeError, ValueError) as e:
            c.failures.append(F("EXACT-TESTS", "REFUTED_BY_RULE", f"normalização falha no teste {t['input']!r}: {e}"))
            continue
        if not _same(y, t["expected"]):
            c.failures.append(F("EXACT-TESTS", "REFUTED_BY_RULE", f"normalização({t['input']!r}) = {y!r}, teste diz {t['expected']!r}"))


def check(item: dict, *, glossary=None, repeated: set | None = None, group_def: dict | None = None,
          disabled=frozenset()) -> Checked:
    """Obrigações de UMA alegação. repeated: campos sabidamente em bloco repetido. group_def: definição do grupo
    tirada de outra linha (linha com bo_group_id e sem group)."""
    dis = frozenset(disabled)
    repeated = repeated or set()
    c = Checked(item)
    rec = c.rec
    if "ARB-C09-SCHEMA" not in dis:
        errs = sorted(_validator().iter_errors(rec), key=lambda e: list(e.absolute_path))
        if errs:
            c.form = "invalid"
            for e in errs[:3]:
                c.failures.append(F("ARB-C09-SCHEMA", "REFUTED_BY_RULE",
                                    f"/{'/'.join(map(str, e.absolute_path))}: {e.message}"))
            return c
    if is_absence(rec):
        c.form = "absence"
        for e in _check_predicate(_SClaim(rec)):
            c.failures.append(F("SKOS-PRED", "REFUTED_BY_RULE", e))
        try:
            G.typecheck(guard_of(c))
        except G.GuardTypeError as e:
            c.failures.append(F("GUARD-TYPE", "REFUTED_BY_RULE", str(e)))
        _check_absence(c, dis)
        return c
    g = rec.get("group") or group_def
    path, bad = fn_path(rec.get("translation_fn"))
    c.fn_path = path
    if bad and "ARB-FN-REG" not in dis:
        c.failures.append(F("ARB-FN-REG", "REFUTED_BY_RULE", f"fora do núcleo e do registro fechado: {bad}"))

    projs = rec.get("projection") or []
    if projs:
        try:
            r = PJ.check_projections(projs, {f: {"repeated": True} for f in repeated}, disabled=dis)
            c.failures.extend(F(x["rule"], x["outcome"], x["detail"]) for x in r["failures"])
        except (KeyError, TypeError, AttributeError) as e:
            c.failures.append(F("P-EXEC", "REFUTED_BY_RULE", f"projeção ilegível: {type(e).__name__}: {e}"))

    if g is not None:
        c.form = "group"
        _check_group(c, g, repeated, dis)
        r2 = dict(rec)
        r2["translation_fn"] = None
        _assess_into(c, r2, ("EXACT-NORM",), dis)
        c.subject = Side(str(rec.get("subject_id")), "*", (), None, rec.get("subject_concept"))
        c.object = Side(str(rec.get("object_id")), "*", (), None, rec.get("object_concept"))
    else:
        ps = _pick(projs, rec.get("subject_id"), rec.get("subject_concept"), c.failures, "sujeito")
        po = _pick(projs, rec.get("object_id"), rec.get("object_concept"), c.failures, "objeto")
        c.form = "projection" if (ps or po) else "plain"
        eff = _effective(rec, ps, po) if (ps or po) else copy.deepcopy(rec)
        c.subject = Side(str(rec.get("subject_id")), _proj_part(ps) if ps else "*", _proj_occ(ps) if ps else (),
                         eff.get("subject_value_type"), rec.get("subject_concept"), bool(ps))
        c.object = Side(str(rec.get("object_id")), _proj_part(po) if po else "*", _proj_occ(po) if po else (),
                        eff.get("object_value_type"), rec.get("object_concept"), bool(po))
        for side, s, p in (("sujeito", c.subject, ps), ("objeto", c.object, po)):
            if s.field in repeated and (p is None or (p.get("occurrence") or {}).get("scope") != "block") \
                    and "ARB-OCC-ID" not in dis:
                c.failures.append(F("ARB-OCC-ID", "REFUTED_BY_RULE",
                                    f"{s.field} ({side}) está em bloco repetido e a alegação não identifica a ocorrência"))
        if path == "core":
            _assess_into(c, eff, (), dis)
        else:
            e2 = dict(eff)
            e2["translation_fn"] = None
            _assess_into(c, e2, ("EXACT-NORM",), dis)
            if path == "registry":
                _registry_checks(c, eff, dis)
                _registry_domain(c, eff, dis)
        c.eff = eff
    if rec.get("semantic_relation") == "related" and "ARB-RELATED-EV" not in dis:
        evs = ((rec.get("proof") or {}).get("evidence")) or []
        cited = [e for e in evs if isinstance(e, dict) and e.get("source") and (e.get("sentence") or e.get("observation"))]
        if rec.get("evidence_state") not in ANCHOR_OK or not cited:
            c.failures.append(F("ARB-RELATED-EV", "UNPROVEN",
                                f"related em {rec.get('evidence_state')} sem citação que o sustente: hipótese de alinhamento"))
    _anchors(c, glossary, dis)
    return c


def guard_of(c: Checked) -> dict:
    g = c.rec.get("guard")
    return g if isinstance(g, dict) else G.empty()
