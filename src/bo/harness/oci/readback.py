"""Leitura de volta (C12 readback) e desfecho de persistência (C12 outcomes) a partir do state do Terraform.

A leitura é a projeção do state (formato de `terraform show -json`) nos campos que o plano escreveu, com a redação na
origem do redact.Redactor. Cada campo do C12 tem caminho `<tipo>.<rótulo>.<caminho com ocorrências>` (prefixo
`data.` para data source). Ocorrência de bloco em modo set não tem ordem no state: a ocorrência planejada i é
casada com o elemento do state que mais concorda com os valores literais planejados dela (empate: menor índice; cada
elemento serve a uma ocorrência só).

Desfecho (só os campos carried decidem; synthesized e default_declared são lidos e relatados):
  ALTERED        algum carried lido não confere pelo comparador
  NOT_READABLE   algum carried não pôde ser lido (withheld, not_read, ausente do state)
  UNKNOWN        algum carried não se compara (expressão, comparador fora do domínio do valor)
  PERSISTED      todos os carried lidos conferem
O comparador do caso (C11) vale para os carried literais e documentos; referência e binding se comparam por igualdade
exata do endereço redigido ('ref:...', 'bind:...').
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from bo.transforms import comparators as CMP
from bo.transforms.errors import TransformError
from bo.transforms.markers import ABSENT

from . import schema as S
from .redact import Redactor, is_withheld_leaf

EVIDENCE_ORDER = ["UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED"]
RULE_ID = "HARNESS-OCI-PERSIST-01"


class _NotComparable:
    def __init__(self, why: str):
        self.why = why


@dataclass
class FieldRead:
    path: str
    origin: str
    state: str                  # read | absent | not_read | withheld
    node_id: str | None = None  # nó do plano (C12 3.1.0)
    value: object = None        # redigido; só quando state == read
    rule_id: str | None = None
    expected: object = None     # redigido; nunca gravado em C12 (fica no relatório interno de comparação)
    structural: bool = False
    match: bool | None = None
    compare_error: str | None = None

    def c12(self) -> dict:
        d = {"path": self.path, "state": self.state}
        if self.node_id:
            d["node_id"] = self.node_id
        if self.state == "read":
            d["value"] = self.value
        if self.state == "withheld":
            d["redaction"] = {"rule_id": self.rule_id, "at_source": True}
        return d


def state_resources(state: dict, module: str) -> list[dict]:
    root = (state.get("values") or {}).get("root_module") or {}
    for cm in root.get("child_modules") or []:
        if cm.get("address") == f"module.{module}":
            return list(cm.get("resources") or [])
    return []


def all_resources(state: dict) -> list[dict]:
    root = (state.get("values") or {}).get("root_module") or {}
    out = list(root.get("resources") or [])
    for cm in root.get("child_modules") or []:
        out += list(cm.get("resources") or [])
    return out


def _value_term_index(plan: dict) -> dict:
    return {(s["order"], v["field"]): v for s in plan["steps"] for v in s["values"]}


def _expected(written: dict, vterm: dict, red: Redactor, by_addr: dict):
    """Valor esperado já na forma redigida, ou _NotComparable."""
    t = vterm["term"]
    k = t["kind"]
    if k == "literal":
        return t["value"] if t["value"] is not None else ABSENT
    if k == "symbol":
        src = written["source"]
        return f"bind:{src.split(':', 1)[1]}" if src.startswith("binding:") else _NotComparable("símbolo sem binding")
    if k == "reference":
        parts = written["expr"].split(".")
        is_data = parts[0] == "data"
        if is_data:
            parts = parts[1:]
        rtype, label, attr = parts[0], parts[1], parts[2:]
        tgt = by_addr.get(("data." if is_data else "") + f"{rtype}.{label}")
        if tgt is None:
            return _NotComparable("alvo da referência ausente do state")
        v = tgt.get("values") or {}
        for a in attr:
            v = v.get(a) if isinstance(v, dict) else None
        st, rv = red.value(v)
        return rv if st == "ok" else _NotComparable("alvo da referência retido")
    if k == "document":
        return {"$document": t["tree"], "format": t["format"]}
    if k == "withheld":
        return _NotComparable("valor retido: não se compara")
    return _NotComparable(f"termo {k} não se compara antes de avaliado")


def _walk(values, toks, block: S.Block, occ_choice):
    """Desce no state seguindo os tokens. occ_choice(path_prefix, name, index, candidates) -> índice do elemento."""
    cur, blk, prefix = values, block, []
    for t in toks:
        if t.kind == "block":
            bt = blk.blocks[t.name]
            v = cur.get(t.name) if isinstance(cur, dict) else None
            if v is None:
                return None, False
            if isinstance(v, list):
                if bt.mode == "set":
                    i = occ_choice(tuple(prefix), t.name, t.index, v)
                else:
                    i = t.index
                if i is None or i >= len(v):
                    return None, False
                cur = v[i]
            elif isinstance(v, dict) and t.index == 0:
                cur = v
            else:
                return None, False
            prefix.append((t.name, t.index))
            blk = bt.block
        else:
            if not isinstance(cur, dict) or t.name not in cur:
                return None, False
            cur = cur[t.name]
    return cur, True


def _literal_leaves_under(writtens: list[dict], vidx: dict, order: int, prefix_tokens: tuple, name: str, index: int):
    """Valores literais planejados dentro da ocorrência (prefix + (name, index)); caminhos relativos."""
    out = {}
    for w in writtens:
        toks = w["_toks"]
        bpath = [(t.name, t.index) for t in toks if t.kind == "block"]
        want = list(prefix_tokens) + [(name, index)]
        if bpath[:len(want)] != want:
            continue
        v = vidx.get((order, w["field"]))
        if v is None and w["origin"] == "derived_name":
            v = {"term": {"kind": "literal", "value": w["derived_value"]}}
        if v is not None and v["term"]["kind"] == "literal":
            rel = toks[len(want):] if all(t.kind == "block" for t in toks[:len(want)]) else None
            if rel is not None:
                out[tuple((t.kind, t.name, t.index) for t in rel)] = v["term"]["value"]
    return out


def _get_rel(elem, rel):
    cur = elem
    for kind, name, idx in rel:
        if kind == "block":
            v = cur.get(name) if isinstance(cur, dict) else None
            if isinstance(v, list):
                if idx >= len(v):
                    return None
                cur = v[idx]
            else:
                cur = v
        else:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(name)
    return cur


def project(state: dict, report_plan: dict, plan: dict, red: Redactor, table: S.SchemaTable | None = None) -> list:
    """Projeta o state nos campos escritos pelo render. Devolve [FieldRead], na ordem dos passos e campos."""
    table = table or S.table()
    module = report_plan["module"]
    resources = state_resources(state, module)
    red.index_state(all_resources(state))
    by_addr = {(("data." if r.get("mode") == "data" else "") + f"{r['type']}.{r['name']}"): r for r in resources}
    vidx = _value_term_index(plan)
    labels = {int(k): v for k, v in report_plan["labels"].items()}
    order_of = {v: k for k, v in labels.items()}
    writtens = []
    for w in report_plan["written"]:
        blk = table.block(w["kind"], w["resource_type"])
        toks, _attr = S.resolve(blk, w["field"])
        writtens.append(dict(w, _toks=toks, _order=order_of[w["label"]], _attr=_attr, _block=blk))
    chosen: dict = {}
    out = []
    for w in writtens:
        order = w["_order"]
        addr = ("data." if w["kind"] == "data" else "") + f"{w['resource_type']}.{w['label']}"
        path = f"{addr}.{w['hcl_path']}"
        if w["origin"] == "derived_name":
            vterm = {"term": {"kind": "literal", "datatype": "string", "value": w["derived_value"]},
                     "origin": "derived_name"}
        else:
            vterm = vidx[(order, w["field"])]
        fr = FieldRead(path, w["origin"], "not_read", node_id=w.get("node_id") or None,
                       structural=vterm["term"]["kind"] in ("reference", "symbol"))
        attr: S.Attr = w["_attr"]
        res = by_addr.get(addr)
        exp = _expected(w, vterm, red, by_addr)
        fr.expected = None if isinstance(exp, _NotComparable) else exp
        if isinstance(exp, _NotComparable):
            fr.compare_error = exp.why
        if attr.write_only:
            fr.state, fr.rule_id = "not_read", "REDACT-WRITEONLY-01"
            out.append(fr)
            continue
        if res is None:
            fr.state = "not_read"
            fr.compare_error = fr.compare_error or "recurso ausente do state"
            out.append(fr)
            continue
        if attr.sensitive or _sensitive_marked(res, w["_toks"]):
            fr.state, fr.rule_id = "withheld", "REDACT-SENSITIVE-01"
            out.append(fr)
            continue
        if is_withheld_leaf(w["resource_type"], w["field"]):
            fr.state, fr.rule_id = "withheld", "REDACT-WITHHELD-01"
            out.append(fr)
            continue

        def occ_choice(prefix, name, index, cands, _w=w, _order=order):
            key = (addr, prefix, name)
            taken = chosen.setdefault(key, {})
            if index in taken:
                return taken[index]
            planned = _literal_leaves_under(writtens_of(addr), vidx, _order, prefix, name, index)
            used = set(taken.values())
            best, best_score = None, -1
            for i, c in enumerate(cands):
                if i in used:
                    continue
                score = sum(1 for rel, val in planned.items() if CMP.value_equal(_get_rel(c, rel), val))
                if score > best_score:
                    best, best_score = i, score
            taken[index] = best
            return best

        def writtens_of(a):
            return [x for x in writtens if (("data." if x["kind"] == "data" else "") +
                                            f"{x['resource_type']}.{x['label']}") == a]

        raw, found = _walk(res.get("values") or {}, w["_toks"], w["_block"], occ_choice)
        if not found or raw is None:
            fr.state = "absent"
            fr.value = None
            out.append(fr)
            continue
        st, rv = red.value(raw)
        if st == "withheld":
            fr.state, fr.rule_id = "withheld", rv
            out.append(fr)
            continue
        fr.state, fr.value = "read", rv
        out.append(fr)
    return out


def _sensitive_marked(res: dict, toks) -> bool:
    sv = res.get("sensitive_values") or {}
    cur = sv
    for t in toks:
        if isinstance(cur, bool):
            return cur
        if not isinstance(cur, dict) or t.name not in cur:
            return False
        cur = cur[t.name]
        if t.kind == "block" and isinstance(cur, list):
            cur = cur[t.index] if t.index < len(cur) else {}
    return cur is True


def compare_fields(fields: list, comparator: dict) -> None:
    """Preenche match/compare_error de cada campo lido (em memória)."""
    for f in fields:
        if f.state != "read":
            continue
        if f.compare_error is not None:
            continue
        exp, obs = f.expected, f.value
        try:
            if isinstance(exp, dict) and "$document" in exp:
                if not isinstance(obs, str):
                    f.match = False
                    continue
                try:
                    parsed = json.loads(obs)
                except ValueError:
                    f.compare_error = "documento lido não é JSON"
                    continue
                f.match = CMP.value_equal(exp["$document"], parsed)
            elif f.structural:
                f.match = CMP.compare_exact(exp, obs)
            else:
                f.match = CMP.compare(comparator, exp, obs)
        except TransformError as e:
            f.compare_error = f"{e.code}: comparador {comparator.get('name')}"


def decide(fields: list) -> tuple[str, str]:
    carried = [f for f in fields if f.origin == "carried"]
    if not carried:
        return "UNKNOWN", "NO_CARRIED_FIELD: o plano não carrega nenhum valor da origem"
    altered = [f for f in carried if f.state == "read" and f.match is False]
    unreadable = [f for f in carried if f.state in ("withheld", "not_read", "absent") and
                  not (f.state == "absent" and f.expected is ABSENT)]
    absent_ok = [f for f in carried if f.state == "absent" and f.expected is ABSENT]
    uncomparable = [f for f in carried if f.state == "read" and f.match is None]
    n = len(carried)
    if altered:
        return "ALTERED", f"{len(altered)} de {n} campo(s) carried não conferem"
    if unreadable:
        return "NOT_READABLE", f"{len(unreadable)} de {n} campo(s) carried sem leitura"
    if uncomparable:
        return "UNKNOWN", f"{len(uncomparable)} de {n} campo(s) carried sem comparação"
    return "PERSISTED", f"{n} de {n} campo(s) carried conferem" + (f" ({len(absent_ok)} nulo(s))" if absent_ok else "")


def evidence_after(before: str, outcome: str) -> str:
    """C12-LADDER: só PERSISTED sobe, e só até PERSISTENCE_VERIFIED; nada desce."""
    if outcome == "PERSISTED" and EVIDENCE_ORDER.index(before) < EVIDENCE_ORDER.index("PERSISTENCE_VERIFIED"):
        return "PERSISTENCE_VERIFIED"
    return before


def unready(state: dict, module: str) -> list[str]:
    """Endereços de recursos com lifecycle ainda não pronto. Recurso sem 'state' no schema conta como pronto."""
    ready = {"AVAILABLE", "ACTIVE", "RUNNING", "PROVISIONED", "ENABLED", "SUCCEEDED"}
    out = []
    for r in state_resources(state, module):
        st = (r.get("values") or {}).get("state")
        if isinstance(st, str) and st and st.upper() not in ready:
            out.append(f"{r['type']}.{r['name']}:{st.upper()}")
    return out


FAILED_STATES = {"FAILED", "TERMINATED", "DELETED", "TERMINATING", "DELETING"}
