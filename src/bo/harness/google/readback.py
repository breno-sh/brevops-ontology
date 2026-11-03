"""Leitura de volta (C12 readback) e desfecho de persistência (C12 outcomes) a partir do state já redigido.

Regra HGCP-PERSIST-01 (só sobre os valores CARREGADOS do plano; sintetizados e defaults declarados são lidos e
gravados, mas não decidem, porque não são a alegação sob teste):
  - algum valor carregado lido difere do plano pelo comparador do caso (C11, bo.transforms.comparators) -> ALTERED;
  - senão, algum valor carregado não lido, withheld ou simbólico -> NOT_READABLE;
  - senão, todos conferem -> PERSISTED;
  - nenhum valor carregado comparável -> UNKNOWN (com o motivo).
Valor sabidamente ausente no state (absent) entra como ABSENT no comparador e só confere com ausência.
Bloco repetido de nesting 'set' compara como conjunto de objetos projetados nas chaves do plano (ordem não conta).
Valor carregado com termo withheld (segredo) é lido como withheld e fica FORA da decisão (nunca é comparável).
Atributo de tipo set compara como conjunto. Valor de referência (expressão '<endereço>.<atributo>') é resolvido no
mesmo state lido; confere se igual ou se um lado é a URL googleapis cujo caminho termina no outro (self_link x id,
a mesma supressão de diferença que o provider google faz).
Escada de evidência (C12-LADDER): só PERSISTED sobe para PERSISTENCE_VERIFIED; os outros mantêm o estado anterior.
"""

from __future__ import annotations

from bo.transforms import comparators as CMP
from bo.transforms.errors import TransformError
from bo.transforms.markers import ABSENT

from . import common as C
from .no_silent_insert import Expected, single_block
from .redact import ABSENT as S_ABSENT, NOT_READ, READ, WITHHELD, _walk, c12_path

RULE_ID = "HGCP-PERSIST-01"
PROTOCOL_VERSION = "1.0.0"
LADDER = ["UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED"]


def plan_leaves(plan: dict, graph: dict, schema) -> list[dict]:
    """[{address, kind, rtype, path, expected, origin}] — uma folha por valor do plano, já achatada."""
    exp = Expected(plan, graph, schema)
    out = []
    for st in sorted(plan["steps"], key=lambda s: s["order"]):
        addr = exp.addr(st)
        owner = exp.owner(st)
        kind = "data" if owner["action"] == "reference" else "resource"
        blk = exp.block(st)
        for v in st["values"]:
            set_block = _set_block(blk, v["field"])
            leaves: dict = {}
            val = exp.term(v["term"], st, v["field"])
            if set_block:
                leaves[v["field"]] = val
            else:
                exp.flat(blk, v["field"], val, leaves)
            for p, x in leaves.items():
                out.append({"address": addr, "kind": kind, "rtype": owner["resource_type"], "path": p,
                            "expected": x, "origin": v["origin"], "set_block": set_block,
                            "set_attr": _is_set_attr(blk, p),
                            "withheld_term": v["term"]["kind"] == "withheld"})
    return out


def _is_set_attr(blk: dict, path: str) -> bool:
    from .schema import attr_at
    attr, rest = attr_at(blk, path.split("."))
    return bool(attr) and not rest and isinstance(attr["type"], list) and attr["type"][0] == "set"


def _same_ref(exp, obs) -> bool:
    if not isinstance(exp, str) or not isinstance(obs, str):
        return False
    if exp == obs:
        return True
    a, b = (exp, obs) if len(exp) > len(obs) else (obs, exp)
    return a.startswith("https://www.googleapis.com/") and a.endswith("/" + b)


def resolve(exp, state_resources: dict):
    """('expr', 'tipo.nome.atributo') -> valor do atributo no state lido; None se não resolve."""
    if not (isinstance(exp, tuple) and exp[0] == "expr"):
        return None
    parts = exp[1].split(".")
    if parts[0] == "var" or len(parts) < 3:
        return None
    addr = ".".join(parts[:3] if parts[0] == "data" else parts[:2])
    attr = parts[3:] if parts[0] == "data" else parts[2:]
    r = state_resources.get(addr)
    cur = (r or {}).get("values")
    for a in attr:
        cur = cur.get(a) if isinstance(cur, dict) else None
    return cur


def _set_block(blk: dict, field: str) -> bool:
    node = blk
    segs = field.split(".")
    for i, s in enumerate(segs):
        if s.isdigit():
            continue
        if s in node["blocks"]:
            bt = node["blocks"][s]
            if i == len(segs) - 1:
                return bt["nesting_mode"] == "set" and not single_block(node, s)
            node = bt["block"]
        else:
            return False
    return False


def _project(obs, exp):
    """Projeta o observado nas chaves do esperado (campos computados a mais não fazem parte da alegação)."""
    if isinstance(exp, dict) and isinstance(obs, dict):
        return {k: _project(obs.get(k), v) for k, v in exp.items()}
    if isinstance(exp, list) and isinstance(obs, list) and len(exp) == len(obs):
        return [_project(o, e) for o, e in zip(obs, exp)]
    return obs


def _set_match(exp: list, obs) -> bool:
    """Bloco 'set': emparelhamento um a um; cada objeto do plano confere, nas SUAS chaves, com um observado."""
    if not isinstance(obs, list) or not isinstance(exp, list) or len(obs) != len(exp):
        return False
    free = list(range(len(obs)))
    for e in exp:
        hit = next((i for i in free if isinstance(obs[i], dict)
                    and CMP.value_equal(e, _project(obs[i], e))), None)
        if hit is None:
            return False
        free.remove(hit)
    return True


def judge_leaf(leaf: dict, field: dict, comparator: dict, state_resources: dict | None = None) -> str:
    """'match' | 'mismatch' | 'unreadable' | 'symbolic' para uma folha carregada."""
    exp = leaf["expected"]
    if field["state"] in (NOT_READ, WITHHELD):
        return "unreadable"
    obs = ABSENT if field["state"] == S_ABSENT else field["value"]
    if isinstance(exp, tuple):              # referência: resolvida no mesmo state; variável: não comparável
        target = resolve(exp, state_resources or {})
        if target is None:
            return "symbolic"
        return "match" if _same_ref(target, obs) else "mismatch"
    try:
        if leaf.get("set_attr") and isinstance(exp, list) and isinstance(obs, list):
            return "match" if CMP.compare({"name": "set_equal"}, exp, obs) else "mismatch"
        if leaf["set_block"]:
            if obs is ABSENT:
                return "match" if exp in ([], None) else "mismatch"
            return "match" if _set_match(exp, obs) else "mismatch"
        e = ABSENT if exp is None else exp
        return "match" if CMP.compare(comparator, e, obs) else "mismatch"
    except TransformError as err:
        return "unreadable" if err.code in ("UNKNOWN_INPUT", "UNKNOWN_SYMBOLIC_INPUT") else "mismatch"


def build_readback(case: dict, leaves: list[dict], state_resources: dict, redactor, rb_id: str) -> dict:
    """Um readback por caso. Com mais de um recurso no plano, o caminho ganha o nó como prefixo ('r2.network'),
    porque o C12 não tem campo de endereço e exige caminho único no registro (ver CONTRACT_CHANGE.txt)."""
    fields = []
    multi = len({lf["address"] for lf in leaves}) > 1
    for lf in leaves:
        res = state_resources.get(lf["address"])
        f = redactor.field(lf["kind"], lf["rtype"], lf["path"], res)
        if multi:
            f["path"] = lf["address"].rsplit("_", 1)[-1] + "." + f["path"]
        if lf["set_block"] and f["state"] == READ and isinstance(f["value"], dict):
            f["value"] = [f["value"]]
        fields.append(f)
    rb = {"readback_id": rb_id, "case_id": case["case_id"], "group_id": case["group_id"],
          "claim_id": case["claim_id"], "side": case["side"] if case["side"] != "both" else "object",
          "provider": C.PROVIDER, "read_at": C.now(), "protocol_version": PROTOCOL_VERSION, "fields": fields}
    redactor.assert_clean(rb)
    return rb


def decide(case: dict, leaves: list[dict], readback: dict, state_resources: dict | None = None) -> tuple[str, str]:
    """(valor do desfecho, detalhe) pela regra HGCP-PERSIST-01."""
    by_path = {}
    for lf, f in zip(leaves, readback["fields"]):
        by_path[(lf["address"], lf["path"])] = (lf, f)
    verdicts = {"match": [], "mismatch": [], "unreadable": [], "symbolic": []}
    for lf, f in by_path.values():
        if lf["origin"] != "carried" or lf["withheld_term"]:
            continue
        verdicts[judge_leaf(lf, f, case["comparator"], state_resources)].append(f["path"])
    n = sum(len(v) for v in verdicts.values())
    if n == 0:
        return "UNKNOWN", "o plano não carrega nenhum valor sob teste"
    if verdicts["mismatch"]:
        return "ALTERED", "difere do plano: " + ", ".join(verdicts["mismatch"][:5])
    if verdicts["unreadable"] or verdicts["symbolic"]:
        return "NOT_READABLE", "sem leitura comparável: " + ", ".join((verdicts["unreadable"]
                                                                       + verdicts["symbolic"])[:5])
    return "PERSISTED", f"{len(verdicts['match'])} valor(es) carregado(s) conferem"


def ladder(before: str, value: str) -> str:
    if value == "PERSISTED" and LADDER.index(before) < LADDER.index("PERSISTENCE_VERIFIED"):
        return "PERSISTENCE_VERIFIED"
    return before


def outcome_record(case: dict, value: str, detail: str, out_id: str, before: str, rb_id: str | None) -> dict:
    rec = {"outcome_id": out_id, "case_id": case["case_id"], "group_id": case["group_id"],
           "claim_id": case["claim_id"], "side": case["side"] if case["side"] != "both" else "object",
           "outcome": {"axis": "persistence", "value": value, "detail": detail[:300]},
           "evidence_state_before": before, "evidence_state_after": ladder(before, value),
           "rule_id": RULE_ID, "decided_at": C.now()}
    if rb_id is not None:
        rec["readback_id"] = rb_id
    return rec
