"""Tradução de um caso (fixture de origem x direção x controle) -> IR de grafo (C26), plano de lowering (C26),
traço por valor (C23) e perdas declaradas.

Princípios (os mesmos nos três controles; só muda o que o Knowledge do controle sabe):
  P1  valor lido de átomo só atravessa por alegação OK (carry.carry); sem ela: UNPROVEN, e nada é inventado;
  P2  valor sem átomo de origem (sentido pelo bloco, efeito pelo bloco, efeito da lista de permissão, decisão sem
      regra, prioridade sintetizada) só desce se o controle o SABE (c2: realização; c3: axioma), pelo codec do
      destino, marcado como sintetizado e com os axiomas que o justificam no traço;
  P3  completo ou nada: um conjunto só é emitido se toda regra dele é emitida inteira. Regra de efeito permitir
      cuja entrada é desconhecida (simbólica, não lida) pode ser omitida com perda UNKNOWN_INPUT declarada (o
      destino fica mais fechado, nunca mais aberto); regra de negação ou de efeito desconhecido nunca é omitida;
  P4  nunca DENY -> ALLOW: destino só-permissão recebe negação só pela compilação do conjunto efetivo (c3, exige
      ordem de precedência e desempate conhecidos); senão o caso é UNSUPPORTED;
  P5  campo obrigatório do destino sem valor -> UNKNOWN_INPUT; o caso sai UNSUPPORTED (com o traço), sem HCL.
A política de perda (códigos do plano) é fixa e única: loss_policy.py.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass, field

from . import carry as CY
from . import vocab as V
from .lift import Lifted, is_sym

SYM_NS = "net-e2e"
MAXP = {"google": 65535, "azurerm": 4096}
MINP = {"google": 0, "azurerm": 100}


def sym_id(*parts) -> str:
    """SYM-<16 hex> estável; sal até não haver 12 dígitos seguidos (o privacy_lint reprova sequência assim)."""
    import re
    salt = 0
    while True:
        h = hashlib.sha256(json.dumps([SYM_NS, *parts, salt]).encode()).hexdigest()[:16]
        if not re.search(r"[0-9]{12}", h):
            return "SYM-" + h
        salt += 1


def lit(v) -> dict:
    if isinstance(v, bool):
        return {"kind": "literal", "datatype": "bool", "value": v}
    if isinstance(v, (int, float)):
        return {"kind": "literal", "datatype": "number", "value": v}
    if isinstance(v, list):
        return {"kind": "literal", "datatype": "list", "value": v}
    if isinstance(v, dict):
        return {"kind": "literal", "datatype": "map", "value": v}
    if v is None:
        return {"kind": "literal", "datatype": "null", "value": None}
    return {"kind": "literal", "datatype": "string", "value": str(v)}


@dataclass
class CaseOut:
    case_id: str
    fixture_id: str
    direction: str
    control: str
    status: str = "TRANSLATED"            # TRANSLATED | UNSUPPORTED | REFUSED
    reasons: list = field(default_factory=list)
    traces: list = field(default_factory=list)
    graph: dict | None = None
    plan: dict | None = None
    losses: list = field(default_factory=list)      # [{code, field, detail}] (também nos passos)
    endpoints: dict = field(default_factory=dict)   # alvo abstrato -> {"node": nó, "kind": ...}
    consequences: list = field(default_factory=list)  # consequências usadas que só o controle sabia
    n_flows: int = 0


class Blocked(Exception):
    def __init__(self, code, detail, status="UNSUPPORTED"):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


# --------------------------------------------------------------------------------------------- construção do plano

class Plan:
    def __init__(self, case_id, source, target):
        self.case_id, self.source, self.target = case_id, source, target
        self.terms, self.resources, self.components, self.references = [], [], [], []
        self.steps, self.contexts = [], []
        self.nr = self.nc = 0

    def term(self, t) -> str:
        tid = f"t{len(self.terms) + 1}"
        self.terms.append({"term_id": tid, "term": t})
        return tid

    def node(self, cls, component_of=None, occurrence=None) -> str:
        if component_of:
            self.nc += 1
            nid = f"c{self.nc}"
            self.components.append({"node_id": nid, "of": component_of, "class_iri": cls,
                                    "occurrence_key": occurrence or [nid]})
        else:
            self.nr += 1
            nid = f"r{self.nr}"
            self.resources.append({"node_id": nid, "class_iri": cls})
        return nid

    def ref(self, frm, to, prop, kind="reference"):
        self.references.append({"from": frm, "to": to, "property_iri": prop, "kind": kind})

    def step(self, node_id, rtype, values, *, name=None, name_field=None, depends=(), losses=(), choices=(),
             unknowns=(), action="create") -> int:
        order = len(self.steps) + 1
        st = {"order": order, "action": action, "node_id": node_id, "resource_type": rtype,
              "typed_choices": list(choices), "values": values, "losses": list(losses),
              "symbolic_unknowns": list(unknowns), "depends_on": sorted(set(depends))}
        if name is not None:
            st["derived_name"] = name if name_field is None else dict(name, field=name_field)
        self.steps.append(st)
        return order

    def order_of(self, node_id) -> int:
        return next(s["order"] for s in self.steps if s["node_id"] == node_id)

    def graph(self) -> dict:
        return {"graph_id": f"GIR-{self.case_id[5:]}", "case_id": self.case_id, "source_provider": self.source,
                "terms": self.terms, "resources": self.resources, "components": self.components,
                "references": self.references, "preconditions": [], "contexts": self.contexts}

    def lowering(self) -> dict:
        nodes = {r["node_id"] for r in self.resources} | {c["node_id"] for c in self.components}
        missing = sorted({s["node_id"] for s in self.steps} - nodes)
        for s in self.steps:
            for v in s["values"]:
                t = v["term"]
                if t.get("kind") == "reference" and t.get("target_node") and t["target_node"] not in nodes:
                    missing.append(t["target_node"])
        return {"plan_id": f"LP-{self.case_id[5:]}", "graph_id": f"GIR-{self.case_id[5:]}",
                "target_provider": self.target, "steps": self.steps,
                "dependency_closure": {"closed": not missing, "missing": sorted(set(missing))}}


def val(field_, term, origin="carried"):
    return {"field": field_, "term": term, "origin": origin, "marked": origin != "carried"}


def refterm(plan: Plan, node_id: str, rtype: str, attribute="id") -> dict:
    return {"kind": "reference", "target_type": rtype, "target_address": f"{rtype}.{sym_id(plan.case_id, node_id)}",
            "attribute": attribute, "target_node": node_id}


def name_of(plan: Plan, node_id: str, stem: str, literal_name: bool = False) -> dict:
    """Nome derivado: termo símbolo por nó (o executor liga um nome sintético) ou literal (renderizador que só
    aceita literal em nome); o mesmo símbolo identifica o nó nas referências."""
    if literal_name:
        tid = plan.term(lit(f"{stem}-{node_id}"))
        return {"template": "bo-{" + tid + "}", "from_terms": [tid]}
    tid = plan.term({"kind": "symbol", "symbol_id": sym_id(plan.case_id, node_id), "name_class": "resource_attribute",
                     "scope": "repo"})
    return {"template": stem + "-{" + tid + "}", "from_terms": [tid]}


# --------------------------------------------------------------------------------------------- caso

class Translator:
    def __init__(self, L: Lifted, K, cs, direction: str, control: str, case_id: str):
        self.L, self.K, self.cs, self.direction, self.control = L, K, cs, direction, control
        self.src, self.tgt = direction.split("->")
        self.out = CaseOut(case_id, L.fixture_id, direction, control)
        self.ntr = 0
        self.loss_codes: list = []
        self.consumed: dict = {}      # (indivíduo, átomo) -> como o valor foi usado sem saída própria

    # ---------------------------------------------------------------- traço C23
    def trace(self, *, atom, raw, result, code=None, out_atom=None, out_value=None, claim_id=None, prop=None,
              fn=None, axioms=(), meta=(), individual=None, classes=(), detail=None, rule=None, guard=None,
              realization=None):
        self.ntr += 1
        t = {"trace_id": f"TR-{self.out.case_id[5:]}-{self.ntr:04d}", "case_id": self.out.case_id,
             "input": {"atom_id": atom, "term": _term_of(raw)}, "justifying_axioms": list(axioms),
             "consulted_metadata": list(meta), "control": {"c1_table": "c1", "c2_taxonomy": "c2", "c3_full": "c3"}[self.control],
             "result": result}
        if claim_id:
            t["claim_id"] = claim_id.split(",")[0]
        if individual:
            t["individual"] = f"ex:{self.L.fixture_id.lower().replace('-', '_')}__{individual}"
        if classes:
            t["inferred_classes"] = sorted(classes)
        if prop:
            t["property"] = prop
        if realization:
            t["realization_id"] = realization
        if fn and isinstance(fn, dict) and fn.get("name"):
            t["transform"] = {"name": fn["name"].split("+")[0] if "+" in fn["name"] else fn["name"],
                              "params": fn.get("params") or {}}
        if result == "carried":
            t["output"] = {"atom_id": out_atom, "term": _term_of(out_value)}
        if result == "blocked":
            t["block_code"] = code
            if code in ("CONDITION_FALSE", "CONDITION_INDETERMINATE"):
                t["guard_evaluated"] = {"guard": {"all": []}, "result": "FALSE" if code == "CONDITION_FALSE"
                                        else "INDETERMINATE"}
        if rule:
            t["rule"] = rule
        if detail:
            t["detail"] = detail[:300] if len(detail) >= 3 else detail + "..."
        self.out.traces.append(t)
        return t

    def knows(self, ind, prop):
        return self.K.value(ind, prop)

    # ---------------------------------------------------------------- execução
    def run(self) -> CaseOut:
        try:
            self._prechecks()
            groups = self._groups()
            plan = Plan(self.out.case_id, self.src, self.tgt)
            builder = BUILDERS[self.tgt](self, plan)
            builder.context()
            for gi, g in enumerate(groups):
                rules = self._target_rules(g, gi)
                builder.rule_set(gi, g, rules)
            builder.endpoints(groups)
            self.out.graph = plan.graph()
            self.out.plan = plan.lowering()
            self.out.losses = [dict(l) for l in self.loss_codes]
        except Blocked as b:
            self.out.status = b.status
            self.out.reasons.append({"code": b.code, "detail": b.detail})
            self.out.graph = self.out.plan = None
        self._account()
        return self.out

    def _account(self):
        """Traço por valor completo (E1): todo valor de átomo da origem sem registro ganha um — nome e
        identificador não atravessam (o destino recebe nome derivado); o resto, sem realização usada, ou, se a
        unidade foi bloqueada, o código do bloqueio."""
        pre = f"ex:{self.L.fixture_id.lower().replace('-', '_')}__"
        seen = {(t.get("individual", "")[len(pre):], t["input"]["atom_id"]) for t in self.out.traces}
        blocked = self.out.reasons[0] if self.out.reasons else None
        items = []
        for s in self.L.sets.values():
            if s.name is not None and s.name.atom:
                items.append((s.name.atom, s.name.raw, s.sid, "name"))
        for r in self.L.rules.values():
            for a, raw in r.atoms.items():
                items.append((a, raw, r.rid, "name" if a.endswith(":name") or a.endswith(".name") else "value"))
        for atom, raw, ind, kind in items:
            if (ind, atom) in seen or raw is None:
                continue
            seen.add((ind, atom))
            if blocked:
                self.trace(atom=atom, raw=raw, result="blocked", code=blocked["code"], individual=ind,
                           detail=f"unidade bloqueada antes deste valor: {blocked['detail']}")
            elif (ind, atom) in self.consumed:
                axs, why = self.consumed[(ind, atom)]
                self.trace(atom=atom, raw=raw, result="omitted", individual=ind, axioms=axs,
                           meta=["valor usado na decisão do lowering, sem campo próprio no destino"], detail=why)
            elif kind == "name":
                self.trace(atom=atom, raw=raw, result="blocked", code="NO_REALIZATION", individual=ind, rule="T-NAME",
                           detail="nome da origem não atravessa: o destino recebe nome derivado (C26 derived_name)")
            else:
                self.trace(atom=atom, raw=raw, result="blocked", code="NO_REALIZATION", individual=ind,
                           detail="valor sem realização usada no destino nesta direção")

    def loss(self, code, fld, detail, step_losses=None):
        d = {"code": code, "field": fld, "detail": detail}
        if d not in self.loss_codes:
            self.loss_codes.append(d)
        if step_losses is not None and d not in step_losses:
            step_losses.append(d)

    def _prechecks(self):
        L, K = self.L, self.K
        if L.unsupported:
            raise Blocked("NO_UNIT", f"recursos fora da fatia e do contexto: {', '.join(L.unsupported)}")
        if not K.consistent:
            self.trace(atom=f"{self.src}:{next(iter(L.sets.values())).kind}:name", raw=None, result="blocked",
                       code="SHACL_VIOLATION", detail="; ".join(K.violations.get("*", [])),
                       axioms=["AX-NET-09"])
            raise Blocked("SHACL_VIOLATION", "ABox inconsistente: configuração de origem recusada", "REFUSED")
        for sid, msgs in K.violations.items():
            if sid in L.sets:
                s = L.sets[sid]
                self.trace(atom=f"{self.src}:{s.kind}:name", raw=s.name.raw if s.name else None, result="blocked",
                           code="SHACL_VIOLATION", detail="; ".join(msgs), axioms=["AX-NET-06"],
                           individual=sid, classes=self.K.types.get(sid, ()))
                self.out.consequences.append({"kind": "source_rejected", "individual": sid, "axioms": ["AX-NET-06"]})
                raise Blocked("SHACL_VIOLATION", f"conjunto de origem inválido: {'; '.join(msgs)}", "REFUSED")
        if not L.sets:
            raise Blocked("NO_UNIT", "nenhum conjunto de regras na origem")

    # ---------------------------------------------------------------- aplicabilidade por ponto de anexação
    def _groups(self) -> list:
        L = self.L
        per_ep = {}
        for tid, e in L.endpoints.items():
            atts = [a for a in L.attachments if a.endpoint == tid]
            if e.attach_unread:
                raise Blocked("UNKNOWN_INPUT", f"anexação do alvo {tid} não lida")
            for a in atts:
                if a.status != "known":
                    self.trace(atom=f"{self.src}:{a.tf['resource_type']}:{a.tf.get('block_path', 'id')}", raw="sym:",
                               result="blocked", code="UNKNOWN_SYMBOLIC_INPUT",
                               detail=f"anexação do alvo {tid} simbólica ou a conjunto ausente")
                    raise Blocked("UNKNOWN_SYMBOLIC_INPUT", f"anexação do alvo {tid} não resolvida")
            sets = sorted({a.set_id for a in atts})
            rules = []
            for sid in sets:
                for r in L.rules_of(sid):
                    if self.src == "google":
                        if not self._selected(r, e):
                            continue
                    rules.append(r.rid)
            per_ep[tid] = (tuple(sets), tuple(rules))
        sig = {}
        for tid, (sets, rules) in sorted(per_ep.items()):
            sig.setdefault((sets, rules), []).append(tid)
        groups = []
        for (sets, rules), eps in sig.items():
            if not sets:
                groups.append({"sets": [], "rules": [], "endpoints": eps})
                continue
            if len(sets) > 1:
                ok = all(self.knows(s, "precedence") == "order_independent" for s in sets)
                if not ok:
                    raise Blocked("AMBIGUOUS_TARGET", f"alvo com {len(sets)} conjuntos: combinação sem semântica "
                                                      "conhecida no controle")
                self.out.consequences.append({"kind": "merge_permission_lists", "sets": list(sets),
                                              "axioms": ["AX-NET-02"]})
            groups.append({"sets": list(sets), "rules": list(rules), "endpoints": eps})
        # conjuntos sem nenhum alvo: traduz também (unidade completa sem anexação)
        attached = {s for g in groups for s in g["sets"]}
        for sid in L.sets:
            if sid not in attached:
                groups.append({"sets": [sid], "rules": [r.rid for r in L.rules_of(sid)], "endpoints": ()})
        for sid, s in L.sets.items():
            if s.symbolic_member:
                raise Blocked("UNKNOWN_SYMBOLIC_INPUT", "regra com conjunto não resolvido: pertença desconhecida")
        return groups

    def _selected(self, r, e) -> bool:
        """Seleção por rótulo (GCP target_tags): realização de vínculo (c2+)."""
        sel = [s for s in self.L.selections if s.rule_id == r.rid]
        if not sel:
            if not self.K.structural:
                raise Blocked("NO_REALIZATION", "regra sem seletor: alcance 'toda a rede' é realização (c2+)")
            return True
        s = sel[0]
        self.consumed[(r.rid, s.labels.atom)] = ([], "seleção por rótulo resolvida em anexação aos pontos com o "
                                                     "rótulo (realização do vínculo)")
        if not self.K.structural:
            self.trace(atom=s.labels.atom, raw=s.labels.raw, result="blocked", code="NO_REALIZATION",
                       detail="seleção por rótulo vira anexação só pela realização do vínculo (c2+)")
            raise Blocked("NO_REALIZATION", "seleção por rótulo sem realização no controle")
        if s.labels.status != "known":
            raise Blocked("UNKNOWN_SYMBOLIC_INPUT", "rótulos de seleção simbólicos")
        return bool(set(s.labels.value) & set(e.tags))

    # ---------------------------------------------------------------- regras de destino do grupo
    def _target_rules(self, g, gi) -> list:
        L = self.L
        rules = [L.rules[r] for r in g["rules"]]
        sets = [L.sets[s] for s in g["sets"]]
        out = []
        unread = any(s.unread for s in sets)
        if unread:
            self.loss("UNKNOWN_INPUT", "rules", "conjunto de origem lido pela metade: regra não lida não é traduzida")
        effects = {}
        for r in rules:
            e = self._effect(r)
            effects[r.rid] = e
        known = {k: v for k, v in effects.items() if v}
        allow_only_tgt = self.tgt in ("aws", "oci")
        if any(v is None for v in effects.values()):
            bad = [k for k, v in effects.items() if v is None]
            r = L.rules[bad[0]]
            self.trace(atom=_rule_atom(r), raw=None, result="blocked", code="UNKNOWN_INPUT", individual=r.rid,
                       prop="bo:hasEffect", detail="efeito da regra desconhecido no controle: não há como emitir")
            raise Blocked("UNKNOWN_INPUT", "efeito de regra desconhecido no controle")
        has_deny = any(v == "deny" for v in known.values())
        # ordem e decisão sem regra do conjunto de origem (por grupo)
        prec = {self.knows(s.sid, "precedence") for s in sets}
        if allow_only_tgt and has_deny:
            out = self._compile_effective(g, rules, effects, sets)
            self.loss("DENY_COMPILED", "rules", "destino só-permissão: negação compilada fora (conjunto efetivo)")
        else:
            for r in rules:
                for tr in self._expand(r, effects[r.rid]):
                    out.append(tr)
        # prioridades no destino por precedência
        if self.tgt in ("google", "azurerm"):
            self._priorities(out, sets, rules, prec)
        # decisão sem regra que case
        nm = {self.knows(s.sid, "no_match") for s in sets}
        if self.tgt in ("google", "azurerm"):
            if nm == {"deny"} and not unread:
                for d in ("ingress", "egress"):
                    out.append({"synth": "catch_all", "direction": d, "effect": "deny", "protocol": "all",
                                "dst_ports": None, "remote": ["0.0.0.0/0"], "local": None, "src_ports": None,
                                "priority": MAXP[self.tgt] - (1 if d == "ingress" and self.tgt == "azurerm" else 0),
                                "src_rule": None, "fields": {}, "why": ["AX-NET-03"]})
                self.out.consequences.append({"kind": "catch_all_deny", "sets": g["sets"], "axioms": ["AX-NET-03"]})
            else:
                self.loss("DEFAULT_NO_EVIDENCE", "default_rule",
                          "padrão do destino para fluxo sem regra sem evidência; decisão sem regra da origem "
                          + ("não conhecida no controle" if nm != {"deny"} else "conhecida, mas conjunto lido pela metade"))
        else:
            if nm != {"deny"}:
                self.loss("UNKNOWN_INPUT", "default_rule", "decisão da origem para fluxo sem regra não conhecida no "
                                                           "controle; o destino nega por padrão")
            if self.tgt == "oci":
                self.loss("DEFAULT_NO_EVIDENCE", "default_rule", "o destino só exprime permissão; o padrão de negar "
                                                                 "sem regra não tem evidência publicada no SERVICE-EVIDENCE")
        # estado de conexão
        if self.tgt in ("aws", "google", "azurerm"):
            self.loss("STATE_NOT_EXPRESSIBLE", "state", "estado de conexão do destino sem evidência: retorno UNKNOWN")
        return out

    def _effect(self, r):
        """Efeito neutro da regra no controle; registra a consequência quando só o axioma a dá."""
        f = r.facts.get("effect")
        if f is not None and f.known() and f.origin == "atom":
            v = self.knows(r.rid, "effect") if self.K.structural else None
            return v or ("atom:" + str(f.raw))
        if f is not None and f.known() and f.origin == "structure":
            return f.value if self.K.structural else None
        effs = {m.get("effect").value for m in r.matches if m.get("effect") is not None and m["effect"].known()}
        if len(effs) == 1 and self.K.structural:
            return effs.pop()
        v = self.knows(r.rid, "effect")
        if v in ("allow", "deny"):
            self.out.consequences.append({"kind": "effect_entailed", "individual": r.rid, "value": v,
                                          "axioms": self.K.justification(r.rid, "effect")})
            return v
        return None

    def _expand(self, r, effect) -> list:
        """Uma regra de origem -> ocorrências de destino (uma por combinação de protocolo, faixa e alcance quando o
        destino exige escalar). A separação em ocorrências é estrutural (projeção por ocorrência)."""
        out = []
        eff = effect[5:] if isinstance(effect, str) and effect.startswith("atom:") else effect
        for mi, m in enumerate(r.matches):
            out.append({"src_rule": r, "match": m, "match_index": mi, "effect": eff, "effect_raw": effect,
                        "direction": None, "priority": None, "fields": {}})
        return out

    def _priorities(self, out, sets, rules, prec):
        """Prioridade no destino por precedência: carregada por alegação quando o átomo existe; senão sintetizada
        só se o controle conhece a ordem da origem (c3: AX-NET-02 ou AX-NET-04/05)."""
        for o in out:
            o.setdefault("priority_src", None)
        if prec == {"order_independent"}:
            base = 1000 if self.tgt == "google" else 100
            i = 0
            for o in out:
                if o.get("synth"):
                    continue
                o["priority"] = base if self.tgt == "google" else base + i
                o["priority_why"] = ["AX-NET-02", "AX-NET-01"]
                i += 1
            self.out.consequences.append({"kind": "priority_synthesized", "order": "order_independent",
                                          "axioms": ["AX-NET-02"]})
            return
        if prec == {"lower_value_first"}:
            # ordem da origem: (prioridade, negar antes de permitir no empate se o desempate é conhecido)
            tie = {self.knows(s.sid, "tie_break") for s in sets}
            items = []
            for o in out:
                if o.get("synth"):
                    continue
                p = o["src_rule"].facts.get("priority")
                pv = p.value if p is not None and p.known() else None
                if pv is None:
                    pv = 1000 if self.src == "google" and p is not None and p.status == "absent" else None
                if pv is None:
                    raise Blocked("UNKNOWN_INPUT", "prioridade de origem desconhecida")
                items.append((pv, o))
            pvals = [p for p, _ in items]
            ties = len(pvals) != len(set(pvals))
            if ties and tie != {"deny_over_allow"} and self.src != "azurerm":
                raise Blocked("UNKNOWN_INPUT", "empate de prioridade sem desempate conhecido")
            items.sort(key=lambda x: (x[0], 0 if x[1]["effect"] == "deny" else 1))
            self._rank = {id(o): (p, k) for k, (p, o) in enumerate(items)}
            for o in out:
                o["priority_order"] = self._rank.get(id(o))
            return
        # sem ordem conhecida: a prioridade só atravessa se o átomo atravessar (no lowering)
        for o in out:
            o["priority_order"] = None

    # ---------------------------------------------------------------- conjunto efetivo (c3)
    def _compile_effective(self, g, rules, effects, sets) -> list:
        prec = {self.knows(s.sid, "precedence") for s in sets}
        if prec != {"lower_value_first"}:
            raise Blocked("UNKNOWN_INPUT", "negação na origem e destino só-permissão: compilar exige a ordem de "
                                           "precedência, desconhecida no controle")
        tie = {self.knows(s.sid, "tie_break") for s in sets}
        boxes = []
        for r in rules:
            p = r.facts.get("priority")
            pv = p.value if p is not None and p.known() else (1000 if self.src == "google" and p is not None
                                                              and p.status == "absent" else None)
            if pv is None:
                raise Blocked("UNKNOWN_INPUT", "prioridade de origem desconhecida: não há como compilar")
            d = r.facts.get("direction")
            dv = self.knows(r.rid, "direction") or (d.value if d is not None and d.known() else None)
            if dv is None:
                raise Blocked("UNKNOWN_INPUT", "sentido desconhecido: não há como compilar")
            if r.facts.get("local") is not None and r.facts["local"].status not in ("absent",):
                raise Blocked("UNKNOWN_INPUT", "filtro de endereço local não exprimível no destino")
            sp = r.facts.get("src_ports")
            if sp is not None and sp.status == "known" and sp.value is not None:
                if effects[r.rid] == "deny":
                    raise Blocked("OUT_OF_SUBSET", "negação com porta de origem: omitir abriria tráfego")
                self.loss("SRC_PORT_DROPPED", "src_ports", "regra que depende de porta de origem omitida")
                continue
            rem = r.facts.get("remote")
            if rem is None or not rem.known():
                raise Blocked("UNKNOWN_SYMBOLIC_INPUT", "alcance remoto simbólico: não há como compilar")
            for m in r.matches:
                if not m["protocol"].known() or m["dst_ports"].status == "symbolic":
                    raise Blocked("UNKNOWN_SYMBOLIC_INPUT", "protocolo ou portas simbólicos")
                eff = m.get("effect").value if m.get("effect") is not None else effects[r.rid]
                for c in rem.value:
                    if c.startswith("SERVICE_TAG:"):
                        raise Blocked("OUT_OF_SUBSET", f"etiqueta de serviço {c} não exprimível no destino")
                    boxes.append({"prio": pv, "eff": eff, "dir": dv, "proto": m["protocol"].value,
                                  "ports": m["dst_ports"].value, "cidr": c, "rule": r})
        ties = {}
        for b in boxes:
            ties.setdefault(b["prio"], set()).add(b["eff"])
        if any(len(v) > 1 for v in ties.values()) and tie != {"deny_over_allow"} and self.src != "azurerm":
            raise Blocked("UNKNOWN_INPUT", "empate de prioridade sem desempate conhecido")
        boxes.sort(key=lambda b: (b["prio"], 0 if b["eff"] == "deny" else 1))
        allowed = []      # lista de caixas (dir, proto, ports, cidr) permitidas no conjunto efetivo
        denied = []
        for b in boxes:
            me = (b["dir"], b["proto"], _pr(b["ports"]), b["cidr"])
            if b["eff"] == "deny":
                denied.append(me)
                continue
            box = [me]
            for d in denied:
                box = [x for y in box for x in _sub(y, d)]
            allowed.extend((x, b["rule"]) for x in box)
            # o que esta permissão cobre também não é decidido por regra posterior: para quem vem depois, conta
            # como já decidido (sai do espaço restante), como a negação
            denied.append(me)
        for b in boxes:
            for a in b["rule"].atoms:
                self.consumed[(b["rule"].rid, a)] = (["AX-NET-04", "AX-NET-05", "AX-NET-10"],
                                                    "compilado no conjunto efetivo do destino só-permissão")
        self.out.consequences.append({"kind": "effective_set_compiled", "sets": g["sets"],
                                      "axioms": ["AX-NET-04"] + (["AX-NET-05"] if tie == {"deny_over_allow"} else [])})
        out = []
        for (d, proto, ports, cidr), r in allowed:
            out.append({"src_rule": r, "compiled": True, "direction": d, "effect": "allow", "protocol": proto,
                        "dst_ports": None if ports == (0, 65535) and proto in ("all", "icmp") else [ports],
                        "remote": [cidr], "fields": {}, "why": ["AX-NET-04", "AX-NET-05", "AX-NET-10"]})
        return out


# --------------------------------------------------------------------------------------------- caixas (compilação)

def _pr(ports):
    if ports is None:
        return (0, 65535)
    if len(ports) != 1:
        raise Blocked("OUT_OF_SUBSET", "lista de faixas de porta na compilação")
    return tuple(ports[0])


def _sub(a, b):
    """a \\ b sobre caixas (sentido, protocolo, (lo, hi), CIDR): lista de caixas disjuntas que cobrem a parte de a
    fora de b. Protocolo sem porta (icmp, all) vale para a faixa inteira. CIDRs ou se aninham ou são disjuntos."""
    da, pa, (la, ha), ca = a
    db, pb, (lb, hb), cb = b
    if da != db:
        return [a]
    if pb != "all" and pa != pb:
        if pa == "all":
            raise Blocked("OUT_OF_SUBSET", "permissão de todo protocolo menos um: não exprimível como lista finita")
        return [a]
    if pa in ("all", "icmp"):
        la, ha = 0, 65535
    if pb in ("all", "icmp"):
        lb, hb = 0, 65535
    na, nb = ipaddress.ip_network(ca, strict=False), ipaddress.ip_network(cb, strict=False)
    if not na.overlaps(nb) or hb < la or lb > ha:
        return [a]
    out = []
    if na == nb or nb.supernet_of(na):
        inter = ca
    else:
        out += [(da, pa, (la, ha), str(x)) for x in sorted(na.address_exclude(nb))]
        inter = cb
    if la < lb:
        out.append((da, pa, (la, lb - 1), inter))
    if ha > hb:
        out.append((da, pa, (hb + 1, ha), inter))
    return out


def _rule_atom(r) -> str:
    rt = r.tf["resource_type"]
    path = r.tf.get("block_path") or ("type" if rt == "aws_security_group_rule" else "id")
    return f"{r.provider}:{rt}:{path}"


def _term_of(raw):
    if isinstance(raw, str) and raw.startswith("sym:"):
        return {"kind": "symbol", "symbol_id": sym_id("input", raw), "name_class": "unknown", "scope": "repo"}
    if isinstance(raw, tuple):
        raw = list(raw)
    return lit(raw)


from .lower import BUILDERS  # noqa: E402  (construtores por provedor de destino)
