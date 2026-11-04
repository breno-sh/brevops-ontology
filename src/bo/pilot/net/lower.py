"""Construtores do plano por provedor de destino (lowering procedural, separado da camada lógica).

Cada construtor escreve: contexto mínimo fora da fatia (rede/contêiner e ponto de anexação, com valores de
contexto SINTETIZADOS e marcados, nunca traduzidos), o conjunto, as regras e a anexação. A realização do destino é
FIXA e igual nos três controles (escolha tipada registrada no plano): o que muda entre controles é só o que se sabe
para preencher os campos.

  aws      aws_security_group + aws_security_group_rule (type, protocol, from_port, to_port, cidr_blocks) +
           aws_network_interface_sg_attachment (interface do ponto = entrada simbólica do contexto)
  google   google_compute_network + google_compute_firewall por regra (target_tags do grupo) +
           google_compute_instance como ponto (campos de contexto simbólicos, rótulos do grupo)
  azurerm  grupo de recursos, rede e sub-rede de contexto + NSG + azurerm_network_security_rule por regra +
           interface de rede como ponto + associação interface<->NSG
  oci      VCN de contexto + security list com regras embutidas + sub-rede por ponto (security_list_ids)
"""

from __future__ import annotations

from . import carry as CY
from . import vocab as V

AZ_LOCATION = "brazilsouth"          # contexto sintético declarado (mesmo dos moldes do HARNESS-AZURE)
OCI_VCN_CIDR = "10.0.0.0/16"


def _src_fact(tr, prop):
    r = tr.get("src_rule")
    if tr.get("compiled") or tr.get("synth") or r is None:
        return None
    if prop in ("protocol", "dst_ports"):
        return tr["match"][prop]
    return r.facts.get(prop)


class Builder:
    provider = ""
    rule_atom_type = ""

    def __init__(self, T, plan):
        self.T, self.P = T, plan
        self.set_nodes = {}       # índice do grupo -> nó do conjunto
        self.tags = {}

    # ------------------------------------------------------------ contexto das guardas (C10)
    def guard_ctx(self, tr) -> dict:
        """Contexto da guarda: lado da origem (translate.subject_ctx) + 'object.<campo>' = o que o lowering já
        decidiu para a ocorrência de destino. Termo ausente fica não lido (guarda INDETERMINATE, nunca TRUE)."""
        from .translate import subject_ctx
        r = tr.get("src_rule")
        ctx = subject_ctx(r) if r is not None else {}
        for k, v in (tr.get("object") or {}).items():
            ctx[f"object.{k}"] = v
        return ctx

    def decide(self, tr, field, value):
        tr.setdefault("object", {})[field] = value

    # ------------------------------------------------------------ resolução de um campo
    def resolve(self, tr, prop, target_field, target_atom, *, required=True, neutral=None, codec=None,
                element=False, list_ok=False):
        """Valor do campo de destino. Devolve (termo, origem) ou None (omitido). Levanta Blocked quando não dá."""
        T = self.T
        from .translate import Blocked, lit
        f = _src_fact(tr, prop)
        r = tr.get("src_rule")
        ind = r.rid if r is not None else None
        if f is not None and f.origin == "atom" and f.status != "absent":
            if f.status != "known":
                code = "UNKNOWN_SYMBOLIC_INPUT" if f.status == "symbolic" else "UNKNOWN_INPUT"
                T.trace(atom=f.atom, raw=f.raw, result="blocked", code=code, individual=ind,
                        prop=V.PROPERTY_IRI.get(prop), detail=f"valor de origem {f.status}")
                raise Blocked(code, f"{prop}: valor de origem {f.status}")
            raw = f.raw
            if element is not False:
                raw = element
            o = CY.carry(T.cs, f.atom, raw, target_atom, ctx=self.guard_ctx(tr), element=element is not False)
            if o.ok:
                v = o.value
                if list_ok and not isinstance(v, list):
                    v = [v]
                T.trace(atom=f.atom, raw=raw, result="carried", out_atom=target_atom, out_value=v,
                        claim_id=o.claim_id, prop=V.PROPERTY_IRI.get(prop), fn=o.fn, individual=ind,
                        meta=[f"alegação {o.claim_id}"], detail=o.detail or None)
                return lit(v), "carried"
            if o.result == "omitted" and not required:
                T.trace(atom=f.atom, raw=raw, result="omitted", individual=ind, detail=o.detail or "omitido")
                return None
            T.trace(atom=f.atom, raw=raw, result="blocked", code=o.code or "UNPROVEN", claim_id=o.claim_id,
                    individual=ind, prop=V.PROPERTY_IRI.get(prop), detail=o.detail, rule=o.rule)
            raise Blocked(o.code or "UNPROVEN", f"{prop} -> {target_atom}: {o.detail}")
        # sem átomo de origem: valor neutro conhecido pelo controle (estrutura, axioma, compilação, síntese)
        if neutral is not None and codec is not None:
            out = codec(neutral)
            if out is None:
                raise Blocked("NO_REALIZATION", f"{prop}={neutral!r} sem realização em {self.provider}")
            why = tr.get("why") or (T.K.justification(ind, prop) if ind else [])
            if not why and ind and (ind, prop) in T.hints and T.hints[(ind, prop)][0] is not None:
                why = [f"tabela: alegação {c}" for c in T.hints[(ind, prop)][1][:3]]
            T.trace(atom=(f.atom if f is not None and f.atom else _construct_atom(tr, T)), raw=_raw_of(f, tr),
                    result="carried", out_atom=target_atom, out_value=out, prop=V.PROPERTY_IRI.get(prop),
                    individual=ind, axioms=[w for w in why if w.startswith("AX-")],
                    meta=[w for w in why if not w.startswith("AX-")] or [f"codec de realização {self.provider}"],
                    classes=T.K.types.get(ind, ()) if ind else (),
                    realization=f"RZ-{self.provider}-{prop}", detail="valor neutro conhecido no controle, descido "
                                                                     "pelo codec do destino")
            return lit(out), "synthesized"
        if not required:
            return None
        T.trace(atom=(f.atom if f is not None and f.atom else _construct_atom(tr, T)), raw=_raw_of(f, tr),
                result="blocked", code="UNKNOWN_INPUT", individual=ind, prop=V.PROPERTY_IRI.get(prop),
                rule="T-ABSENCE", detail=f"{target_field} obrigatório no destino sem valor conhecido no controle")
        raise Blocked("UNKNOWN_INPUT", f"{target_field}: obrigatório no destino sem valor conhecido no controle")

    def neutral(self, tr, prop):
        """Valor neutro que o controle conhece (estrutural c2+, entailado c3, ou da compilação/síntese)."""
        T = self.T
        if tr.get("compiled") or tr.get("synth"):
            v = tr.get(prop)
            if prop in ("dst_ports", "local", "src_ports") and v is None:
                return "ANY"
            return v
        r = tr["src_rule"]
        if prop == "effect":
            e = tr.get("effect")
            return e if e in ("allow", "deny") else None
        if prop == "direction":
            v = T.knows(r.rid, "direction") if T.K.structural else None
            return v or T.table_hint(r, "direction")
        if prop == "protocol":
            m = tr["match"]["protocol"]
            return m.value if T.K.structural and m.known() else None
        if prop == "dst_ports":
            m = tr["match"]["dst_ports"]
            if not T.K.structural:
                return None
            return ("ANY" if m.value is None else m.value) if m.status in ("known", "absent") else None
        if prop in ("remote", "local"):
            f = r.facts.get(prop)
            if not T.K.structural or f is None:
                return None
            return "ANY" if f.status == "absent" else (f.value if f.known() else None)
        if prop == "src_ports":
            f = r.facts.get(prop)
            if not T.K.structural:
                return None
            return "ANY" if f is None or f.status == "absent" or (f.known() and f.value is None) else (
                f.value if f.known() else None)
        return None

    def unexpressible(self, tr, *, src_ports: bool, local: bool, src_ports_block: bool = False) -> bool:
        """Fato CONHECIDO da origem que o destino não exprime. Regra que permite: omitida com perda declarada
        (o destino fica mais fechado), só para porta de origem (perda do catálogo); regra que nega, ou filtro de
        endereço local: bloqueio (omitir abriria tráfego ou não há perda declarável). Devolve True = omitir."""
        T = self.T
        r = tr.get("src_rule")
        if r is None or tr.get("compiled") or tr.get("synth"):
            return False
        sp, lc = r.facts.get("src_ports"), r.facts.get("local")
        eff = self.neutral(tr, "effect")
        if not local and lc is not None and lc.status not in ("absent",):
            raise_block(T, tr, "local", f"filtro de endereço local sem realização em {self.provider}", "NO_REALIZATION")
        if not src_ports and sp is not None and sp.status == "known" and sp.value is not None:
            if src_ports_block:
                raise_block(T, tr, "src_ports", f"porta de origem: realização em {self.provider} não implementada "
                                                "no piloto", "NO_REALIZATION")
            if eff != "allow":
                raise_block(T, tr, "src_ports", "negação com porta de origem: omitir abriria tráfego", "OUT_OF_SUBSET")
            T.loss("SRC_PORT_DROPPED", "src_ports", f"{self.provider} não filtra porta de origem: regra omitida")
            T.trace(atom=sp.atom or _construct_atom(tr, T), raw=sp.raw, result="blocked", code="OUT_OF_SUBSET",
                    individual=r.rid, prop="bo:ruleSourcePorts",
                    detail="porta de origem sem realização no destino: regra omitida (perda declarada)")
            for a, raw in r.atoms.items():
                if raw is not None and a != sp.atom:
                    T.trace(atom=a, raw=raw, result="blocked", code="OUT_OF_SUBSET", individual=r.rid,
                            detail="regra omitida inteira (porta de origem sem realização; perda SRC_PORT_DROPPED)")
            return True
        if not src_ports and sp is not None and sp.status in ("symbolic", "unread"):
            raise_block(T, tr, "src_ports", "porta de origem desconhecida", "UNKNOWN_SYMBOLIC_INPUT")
        return False

    def plan_priorities(self, rules, target_atom, required: bool):
        """Prioridade de cada regra de destino, decidida para o CONJUNTO inteiro (misturar valor carregado com
        valor renumerado quebraria a ordem). (1) carrega por alegação se toda regra tem átomo, toda alegação
        transporta e a ordem (com empates) se preserva; (2) senão renumera pela ordem que o controle conhece
        (c3: AX-NET-04/05 ou AX-NET-02); (3) senão, sem átomo e campo opcional: omite; senão bloqueia."""
        from .translate import Blocked
        T = self.T
        lo, hi = (100, 4094) if self.provider == "azurerm" else (0, 65534)
        real = [tr for tr in rules if not tr.get("synth")]
        if not real:
            return {}
        facts = [_src_fact(tr, "priority") for tr in real]
        res = {}
        if real and all(f is not None and f.origin == "atom" and f.status == "known" for f in facts):
            outs = [CY.carry(T.cs, f.atom, f.raw, target_atom, ctx=self.guard_ctx(tr)) for f, tr in zip(facts, real)]
            if all(o.ok for o in outs):
                src = [f.value for f in facts]
                dst = [o.value for o in outs]
                order_ok = all((a < b) == (c < d) and (a == b) == (c == d) for i, (a, c) in enumerate(zip(src, dst))
                               for (b, d) in list(zip(src, dst))[i + 1:])
                in_range = all(lo <= v <= hi for v in dst)
                uniq = len(set(dst)) == len(dst) or self.provider != "azurerm"
                if order_ok and in_range and uniq:
                    for tr, f, o in zip(real, facts, outs):
                        T.trace(atom=f.atom, raw=f.raw, result="carried", out_atom=target_atom, out_value=o.value,
                                claim_id=o.claim_id, prop="bo:rulePriority", fn=o.fn, individual=tr["src_rule"].rid,
                                meta=[f"alegação {o.claim_id}"])
                        res[id(tr)] = (o.value, "carried")
                    return res
            why_carry = next((o.detail for o in outs if not o.ok), "ordem, faixa ou unicidade não se preserva")
        else:
            why_carry = "nem toda regra tem átomo de prioridade"
        known_order = [tr for tr in real if tr.get("priority_order") is not None or tr.get("priority") is not None]
        if real and len(known_order) == len(real):
            for tr in real:
                if tr.get("priority") is not None:
                    v = tr["priority"] if self.provider == "google" else None
                    if v is None:
                        v = 100 + 10 * real.index(tr)
                    axs = tr.get("priority_why") or ["AX-NET-02"]
                else:
                    v = 100 + 10 * tr["priority_order"][1]
                    axs = ["AX-NET-04"] + (["AX-NET-05"] if self.T.src == "google" else [])
                if not lo <= v <= hi:
                    raise Blocked("TRANSFORM_OUT_OF_DOMAIN", "prioridade renumerada fora da faixa do destino")
                f = _src_fact(tr, "priority")
                T.trace(atom=f.atom if f is not None and f.atom else _construct_atom(tr, T), raw=_raw_of(f, tr),
                        result="carried", out_atom=target_atom, out_value=v, prop="bo:rulePriority",
                        individual=tr["src_rule"].rid if tr.get("src_rule") is not None else None, axioms=axs,
                        meta=["ordem de precedência da origem conhecida no controle"],
                        detail=f"renumeração que preserva a ordem ({why_carry})")
                res[id(tr)] = (v, "synthesized")
            return res
        if not required and all(f is None or f.status == "absent" for f in facts):
            return {id(tr): None for tr in real}
        for tr, f in zip(real, facts):
            if f is not None and f.status == "known":
                T.trace(atom=f.atom, raw=f.raw, result="blocked", code="UNPROVEN", individual=tr["src_rule"].rid,
                        prop="bo:rulePriority", detail=f"prioridade não atravessa: {why_carry}; ordem desconhecida no "
                                                       "controle")
        raise Blocked("UNPROVEN" if any(f is not None and f.status == "known" for f in facts) else "UNKNOWN_INPUT",
                      f"prioridade no destino: {why_carry}; ordem da origem desconhecida no controle")

    def mark_allow_only(self, tr):
        """Destino só-permissão: o efeito (permitir) e a prioridade da origem decidem que a regra entra, sem campo
        próprio; a porta de origem 'qualquer' é a ausência de filtro no destino."""
        r = tr.get("src_rule")
        if r is None or tr.get("compiled"):
            return
        T = self.T
        for prop, why, axs in (("effect", "efeito permitir realizado pela própria regra no destino só-permissão",
                                ["AX-NET-01", "AX-NET-10"]),
                               ("priority", "ordem irrelevante entre permissões no destino só-permissão",
                                ["AX-NET-02"])):
            f = r.facts.get(prop)
            if f is not None and f.atom:
                T.consumed[(r.rid, f.atom)] = (axs, why)
        sp = r.facts.get("src_ports")
        if sp is not None and sp.atom and sp.status == "known" and sp.value is None:
            T.consumed[(r.rid, sp.atom)] = ([], "porta de origem 'qualquer': o destino não filtra porta de origem")

    def mark_group(self, tr, o, main_atom):
        r = tr.get("src_rule")
        for fld in getattr(o, "inputs", []) or []:
            if r is not None and fld != main_atom:
                self.T.consumed[(r.rid, fld)] = ([], f"transportado com {main_atom} pela alegação de grupo {o.claim_id}")

    def mark_src_any(self, tr):
        r = tr.get("src_rule")
        sp = r.facts.get("src_ports") if r is not None else None
        if sp is not None and sp.atom and sp.status == "known" and sp.value is None:
            self.T.consumed[(r.rid, sp.atom)] = ([], "porta de origem 'qualquer': o destino não filtra porta de origem")

    def mark_any(self, tr, prop, why):
        r = tr.get("src_rule")
        f = r.facts.get(prop) if r is not None else None
        if f is not None and f.atom and f.status == "known":
            self.T.consumed[(r.rid, f.atom)] = ([], why)

    # ------------------------------------------------------------ referências do plano (traço C23)
    def member_ref(self, tr, field, target_atom, term):
        """Referência regra -> conjunto: leva a PERTENÇA da origem (bloco do conjunto ou campo-pai da regra
        separada); regra sintetizada (negação de fecho) leva referência sintetizada."""
        from .translate import val
        r = tr.get("src_rule")
        if r is None or tr.get("synth"):
            return val(field, term, "synthesized")
        prov, rt = r.provider, r.tf["resource_type"]
        if "block_path" in r.tf:
            atom = f"{prov}:{rt}:{r.tf['block_path']}"
        else:
            atom = f"{prov}:{rt}:{V.STANDALONE_RULES[prov][rt]['parent']}"
        raw = self.T.L.sets[r.set_id].tf["address"] if r.set_id else None
        self.T.trace(atom=atom, raw=raw, result="carried", out_atom=target_atom, out_value=term, prop="bo:ruleInSet",
                     individual=r.rid, meta=["pertença da regra ao conjunto na configuração de origem"],
                     detail="referência ao conjunto traduzido no mesmo plano")
        return val(field, term, "carried")

    def attach_ref(self, tid, field, target_atom, term):
        """Referência do ponto de anexação ao conjunto: leva a ANEXAÇÃO da origem do alvo tid."""
        from .translate import val
        atts = [a for a in self.T.L.attachments if a.endpoint == tid and a.set_id]
        if not atts:
            return val(field, term, "synthesized")
        prov = self.T.L.provider
        for a in atts:
            fld = a.tf.get("block_path") or ("network_security_group_id" if prov == "azurerm" else "id")
            self.T.trace(atom=f"{prov}:{a.tf['resource_type']}:{fld}", raw=self.T.L.sets[a.set_id].tf["address"],
                         result="carried", out_atom=target_atom, out_value=term, prop="bo:attachesRuleSet",
                         individual=a.set_id, meta=[f"anexação do alvo {tid} na configuração de origem"],
                         detail="referência do ponto de anexação ao conjunto traduzido")
        return val(field, term, "carried")

    def depends(self, *nodes):
        return [self.P.order_of(n) for n in nodes if n]


def _construct_atom(tr, T) -> str:
    r = tr.get("src_rule")
    if r is None:
        s = next(iter(T.L.sets.values()))
        return f"{T.src}:{s.kind}:name"
    from .translate import _rule_atom
    return _rule_atom(r)


def _raw_of(f, tr):
    if f is not None and f.raw is not None:
        return f.raw
    r = tr.get("src_rule")
    return {"compiled": True} if tr.get("compiled") else {"synthesized": tr.get("synth") or "estrutura"} if r is None \
        else {"construct": r.tf.get("rule_address", r.tf.get("address"))}


def _ports_tuple(neutral):
    if neutral in (None, "ANY"):
        return None
    if len(neutral) != 1:
        return "MULTI"
    return tuple(neutral[0])


# --------------------------------------------------------------------------------------------- AWS

class AwsBuilder(Builder):
    provider = "aws"

    def context(self):
        self.P.contexts.append({"key": "region", "value": None, "state": "symbolic"})

    def rule_set(self, gi, g, rules):
        P, T = self.P, self.T
        from .translate import lit, name_of, refterm, val
        sn = P.node("bo:FilterRuleSet")
        self.set_nodes[gi] = sn
        P.step(sn, "aws_security_group", [], name=name_of(P, sn, "bo-sg"),
               choices=[{"choice_id": f"CH-AWS-RULE-{gi}", "options": ["aws_security_group_rule",
                                                                       "aws_vpc_security_group_ingress_rule"],
                         "selected": "aws_security_group_rule",
                         "reason": "realização fixa nos três controles: sentido como átomo (type) e alcance em lista"}])
        for k, tr in enumerate(rules):
            eff = self.neutral(tr, "effect")
            if eff != "allow":
                raise_block(T, tr, "effect", "destino só-permissão: regra que não permite não tem realização")
            self.mark_allow_only(tr)
            if self.unexpressible(tr, src_ports=False, local=False):
                continue
            cn = P.node("bo:FilterRule", component_of=sn, occurrence=[f"g{gi}", f"r{k}"])
            P.ref(cn, sn, "bo:ruleInSet", "attachment")
            losses = []
            vals = [self.member_ref(tr, "security_group_id", "aws:aws_security_group_rule:security_group_id",
                                    refterm(P, sn, "aws_security_group"))]
            t, o = self.resolve(tr, "direction", "type", "aws:aws_security_group_rule:type",
                                neutral=self.neutral(tr, "direction"), codec=lambda d: d)
            vals.append(val("type", t, o))
            self.decide(tr, "type", t["value"])
            pt, po = self.resolve(tr, "protocol", "protocol", "aws:aws_security_group_rule:protocol",
                                  neutral=self.neutral(tr, "protocol"), codec=lambda p: V.proto_out("aws", p))
            vals.append(val("protocol", pt, po))
            proto_val = pt["value"]
            if proto_val in ("-1", "icmp") or self.neutral(tr, "dst_ports") == "ANY" and proto_val in ("-1",):
                vals += [val("from_port", lit(0), "synthesized"), val("to_port", lit(0), "synthesized")]
            else:
                self._ports(tr, vals)
            self._remote(tr, vals)
            P.step(cn, "aws_security_group_rule", vals, depends=self.depends(sn), losses=losses)

    def _ports(self, tr, vals):
        from .translate import lit, val
        f = _src_fact(tr, "dst_ports")
        if f is not None and f.origin == "atom" and f.status == "known":
            r = tr["src_rule"]
            bind = {a: v for a, v in r.atoms.items()}
            for tf in ("from_port", "to_port"):
                tatom = f"aws:aws_security_group_rule:{tf}"
                o = None
                src_atom = f.atom
                if r.provider in ("google", "azurerm"):
                    elems = f.raw if isinstance(f.raw, list) else [f.raw]
                    if len(elems) != 1:
                        raise_block(self.T, tr, "dst_ports", "lista de faixas: uma regra por faixa exige projeção")
                    o = CY.carry_group(self.T.cs, f.atom, elems[0], tatom, ctx=self.guard_ctx(tr), bindings={f.atom: elems[0]})
                else:
                    src_atom = f.atom if tf == "from_port" else f.atom.rsplit(".", 1)[0] + (
                        ".max" if r.provider == "oci" else ".to_port")
                    if r.provider == "aws":
                        src_atom = f.atom.replace("from_port", tf)
                    raw = r.atoms.get(src_atom)
                    o = CY.carry(self.T.cs, src_atom, raw, tatom, ctx=self.guard_ctx(tr))
                if o is None or not o.ok:
                    code = (o.code if o else "UNPROVEN") or "UNPROVEN"
                    self.T.trace(atom=f.atom, raw=f.raw, result="blocked", code=code, individual=r.rid,
                                 prop="bo:rulePortRangeStart", claim_id=o.claim_id if o else None,
                                 detail=(o.detail if o else "nenhuma alegação de porta"))
                    from .translate import Blocked
                    raise Blocked(code, f"porta {tf}: {(o.detail if o else 'sem alegação')}")
                self.T.trace(atom=src_atom if r.provider not in ("google", "azurerm") else f.atom, raw=f.raw,
                             result="carried", out_atom=tatom, out_value=o.value,
                             claim_id=o.claim_id, prop="bo:rulePortRangeStart" if tf == "from_port" else "bo:rulePortRangeEnd",
                             fn=o.fn, individual=r.rid, meta=[f"alegação {o.claim_id}"])
                self.mark_group(tr, o, f.atom)
                vals.append(val(tf, lit(o.value)))
            return
        n = self.neutral(tr, "dst_ports")
        pt = _ports_tuple(n)
        if n is None:
            raise_block(self.T, tr, "dst_ports", "portas obrigatórias no destino sem valor conhecido")
        if pt == "MULTI":
            raise_block(self.T, tr, "dst_ports", "várias faixas numa regra só-permissão de faixa única")
        lo, hi = pt if pt else (0, 65535)
        vals += [val("from_port", lit(lo), "synthesized"), val("to_port", lit(hi), "synthesized")]
        self.T.trace(atom=_construct_atom(tr, self.T), raw=_raw_of(None, tr), result="carried",
                     out_atom="aws:aws_security_group_rule:from_port", out_value=lo, prop="bo:rulePortRangeStart",
                     axioms=[w for w in (tr.get("why") or []) if w.startswith("AX-")],
                     meta=["codec de realização aws (faixa neutra)"], detail="faixa neutra descida pelo codec")

    def _remote(self, tr, vals):
        from .translate import lit, val
        f = _src_fact(tr, "remote")
        if f is not None:
            t, o = self.resolve(tr, "remote", "cidr_blocks", "aws:aws_security_group_rule:cidr_blocks",
                                list_ok=True)
            vals.append(val("cidr_blocks", t, o))
            return
        n = tr.get("remote")
        vals.append(val("cidr_blocks", lit(list(n)), "synthesized"))

    def endpoints(self, groups):
        P = self.P
        from .translate import lit, refterm, val
        for gi, g in enumerate(groups):
            for tid in g["endpoints"]:
                an = P.node("bo:RuleSetAttachment")
                sn = self.set_nodes[gi]
                P.ref(an, sn, "bo:attachesRuleSet", "attachment")
                sym = P.term({"kind": "symbol", "symbol_id": _sym(P, f"nic-{tid}"), "name_class": "resource_attribute",
                              "scope": "repo"})
                P.step(an, "aws_network_interface_sg_attachment",
                       [self.attach_ref(tid, "security_group_id", "aws:aws_network_interface_sg_attachment:security_group_id",
                                        refterm(P, sn, "aws_security_group")),
                        val("network_interface_id", P.terms[int(sym[1:]) - 1]["term"], "synthesized")],
                       depends=self.depends(sn),
                       unknowns=[{"term_id": sym, "reason": "interface do ponto de anexação: contexto do caso, fora "
                                                            "da fatia (ligada pelo executor)"}])
                self.T.out.endpoints[tid] = {"node": an, "kind": "aws_nic_symbol", "symbol": sym, "set_node": sn}


def _sym(P, local):
    from .translate import sym_id
    return sym_id(P.case_id, local)


def raise_block(T, tr, prop, detail, code="NO_REALIZATION"):
    from .translate import Blocked
    r = tr.get("src_rule")
    T.trace(atom=_construct_atom(tr, T), raw=_raw_of(None, tr), result="blocked", code=code,
            individual=r.rid if r is not None else None, prop=V.PROPERTY_IRI.get(prop), detail=detail)
    raise Blocked(code, detail)


# --------------------------------------------------------------------------------------------- Google

class GoogleBuilder(Builder):
    provider = "google"

    def context(self):
        from .translate import name_of
        P = self.P
        self.net = P.node("bo:FilterRuleSet")
        P.step(self.net, "google_compute_network", [], name=name_of(P, self.net, "bo-net"), name_field="name")
        P.contexts.append({"key": "region", "value": None, "state": "symbolic"})

    def rule_set(self, gi, g, rules):
        P, T = self.P, self.T
        from .translate import lit, name_of, refterm, val
        tag = f"bo-g{gi}"
        self.tags[gi] = tag
        self.set_nodes[gi] = self.net
        self._prio = self.plan_priorities(rules, "google:google_compute_firewall:priority", required=False)
        for k, tr in enumerate(rules):
            if self.unexpressible(tr, src_ports=False, local=True):
                continue
            cn = P.node("bo:FilterRule", component_of=self.net, occurrence=[f"g{gi}", f"r{k}"])
            P.ref(cn, self.net, "bo:ruleInSet", "attachment")
            vals = [self.member_ref(tr, "network", "google:google_compute_firewall:network",
                                    refterm(P, self.net, "google_compute_network", "id"))]
            t, o = self.resolve(tr, "direction", "direction", "google:google_compute_firewall:direction",
                                neutral=self.neutral(tr, "direction"), codec=lambda d: CY.lower_direction("google", d))
            vals.append(val("direction", t, o))
            self.decide(tr, "direction", t["value"])
            d = t["value"].lower()
            pr = self._priority(tr)
            if pr is not None:
                vals.append(val("priority", lit(pr[0]), pr[1]))
            eff = self.neutral(tr, "effect")
            if eff not in ("allow", "deny"):
                raise_block(T, tr, "effect", "efeito desconhecido: bloco allow{}/deny{} sem escolha", "UNKNOWN_INPUT")
            blk = eff
            from bo.semantics.vocab import ABSENT
            self.decide(tr, blk, {"present": True})
            self.decide(tr, "deny" if blk == "allow" else "allow", ABSENT)
            fe = _src_fact(tr, "effect")
            if fe is not None and fe.origin == "atom" and fe.status == "known":
                T.trace(atom=fe.atom, raw=fe.raw, result="carried", out_atom=f"google:google_compute_firewall:{blk}",
                        out_value=blk, prop="bo:hasEffect", individual=tr["src_rule"].rid,
                        meta=["codec de realização do efeito (valor publicado do atributo) -> bloco allow{}/deny{}"],
                        realization="RZ-google-effect", detail="efeito descido pela escolha do bloco no destino")
            pt, po = self.resolve(tr, "protocol", f"{blk}.0.protocol", f"google:google_compute_firewall:{blk}.protocol",
                                  neutral=self.neutral(tr, "protocol"), codec=lambda p: V.proto_out("google", p))
            vals.append(val(f"{blk}.0.protocol", pt, po))
            if pt["value"] not in ("tcp", "udp"):
                self.mark_any(tr, "dst_ports", "protocolo sem porta: a faixa de portas da origem não se aplica")
                if tr.get("match") is not None and tr["match"]["dst_ports"].atom and tr["src_rule"] is not None:
                    T.consumed[(tr["src_rule"].rid, tr["match"]["dst_ports"].atom)] = (
                        [], "protocolo sem porta: a faixa de portas da origem não se aplica")
            if pt["value"] in ("tcp", "udp"):
                f = _src_fact(tr, "dst_ports")
                if f is not None and f.origin == "atom" and f.status == "known" and tr["src_rule"].provider in ("aws", "oci"):
                    vals.append(self._ports_group(tr, f, blk))
                else:
                    n = self.neutral(tr, "dst_ports")
                    res = self.resolve(tr, "dst_ports", f"{blk}.0.ports", f"google:google_compute_firewall:{blk}.ports",
                                       required=False, neutral=None if n == "ANY" else n,
                                       codec=lambda ps: [CY.port_text(a, b) for a, b in ps], list_ok=True)
                    if res is not None:
                        vals.append(val(f"{blk}.0.ports", res[0], res[1]))
            rf = "source_ranges" if d == "ingress" else "destination_ranges"
            lf = "destination_ranges" if d == "ingress" else "source_ranges"
            f = _src_fact(tr, "remote")
            if f is not None:
                t2, o2 = self.resolve(tr, "remote", rf, f"google:google_compute_firewall:{rf}", list_ok=True)
                vals.append(val(rf, t2, o2))
            else:
                vals.append(val(rf, lit(list(tr["remote"])), "synthesized"))
            fl = _src_fact(tr, "local")
            if fl is not None and fl.status != "absent":
                t3, o3 = self.resolve(tr, "local", lf, f"google:google_compute_firewall:{lf}", list_ok=True)
                vals.append(val(lf, t3, o3))
            elif fl is not None and fl.atom and fl.raw is not None:
                self.mark_any(tr, "local", "endereço local 'qualquer': sem filtro local no destino")
                if tr["src_rule"].facts.get("local") is not None:
                    self.T.consumed[(tr["src_rule"].rid, fl.atom)] = ([], "endereço local 'qualquer': sem filtro local no destino")
            self.mark_src_any(tr)
            vals.append(val("target_tags", lit([tag]), "synthesized"))
            P.step(cn, "google_compute_firewall", vals, name=name_of(P, cn, "bo-fw"), name_field="name",
                   depends=self.depends(self.net))

    def _priority(self, tr):
        if tr.get("synth") == "catch_all":
            return tr["priority"], "synthesized"
        return self._prio.get(id(tr))

    def _ports_group(self, tr, f, blk):
        from .translate import Blocked, lit, val
        T, r = self.T, tr["src_rule"]
        tatom = f"google:google_compute_firewall:{blk}.ports"
        binds = dict(r.atoms)
        o = CY.carry_group(T.cs, f.atom, None, tatom, ctx=self.guard_ctx(tr), bindings=binds)
        if o is None or not o.ok:
            code = (o.code if o else "UNPROVEN") or "UNPROVEN"
            T.trace(atom=f.atom, raw=f.raw, result="blocked", code=code, individual=r.rid, prop="bo:ruleDestinationPorts",
                    claim_id=o.claim_id if o else None, detail=(o.detail if o else "nenhuma alegação de grupo de portas"))
            raise Blocked(code, "portas: sem alegação de grupo OK")
        v = o.value if isinstance(o.value, list) else [o.value]
        T.trace(atom=f.atom, raw=f.raw, result="carried", out_atom=tatom, out_value=v, claim_id=o.claim_id,
                prop="bo:ruleDestinationPorts", fn=o.fn, individual=r.rid, meta=[f"alegação {o.claim_id}"])
        self.mark_group(tr, o, f.atom)
        return val(f"{blk}.0.ports", lit(v))

    def endpoints(self, groups):
        P = self.P
        from .translate import lit, name_of, refterm, val
        for gi, g in enumerate(groups):
            for tid in g["endpoints"]:
                en = P.node("bo:NetworkEndpoint")
                P.ref(en, self.net, "bo:inNetwork")
                mt = P.term({"kind": "symbol", "symbol_id": _sym(P, f"mt-{tid}"), "name_class": "variable", "scope": "repo"})
                im = P.term({"kind": "symbol", "symbol_id": _sym(P, f"img-{tid}"), "name_class": "variable", "scope": "repo"})
                P.step(en, "google_compute_instance",
                       [val("machine_type", P.terms[int(mt[1:]) - 1]["term"], "synthesized"),
                        val("boot_disk.0.initialize_params.0.image", P.terms[int(im[1:]) - 1]["term"], "synthesized"),
                        self.attach_ref(tid, "network_interface.0.network",
                                        "google:google_compute_instance:network_interface.network",
                                        refterm(P, self.net, "google_compute_network", "id")),
                        val("tags", lit([self.tags[gi]]), "synthesized")],
                       name=name_of(P, en, "bo-vm"), name_field="name", depends=self.depends(self.net),
                       unknowns=[{"term_id": mt, "reason": "tipo de máquina: contexto do ponto, fora da fatia"},
                                 {"term_id": im, "reason": "imagem: contexto do ponto, fora da fatia"}])
                self.T.out.endpoints[tid] = {"node": en, "kind": "gcp_instance"}


# --------------------------------------------------------------------------------------------- Azure

class AzureBuilder(Builder):
    provider = "azurerm"

    def context(self):
        from .translate import lit, name_of, refterm, val
        P = self.P
        self.rg = P.node("bo:NetworkEndpoint")
        P.step(self.rg, "azurerm_resource_group", [val("location", lit(AZ_LOCATION), "synthesized")],
               name=name_of(P, self.rg, "bo-rg"), name_field="name")
        self.vnet = P.node("bo:NetworkEndpoint")
        P.step(self.vnet, "azurerm_virtual_network",
               [val("resource_group_name", refterm(P, self.rg, "azurerm_resource_group", "name"), "synthesized"),
                val("location", refterm(P, self.rg, "azurerm_resource_group", "location"), "synthesized"),
                val("address_space", lit(["10.20.0.0/16"]), "synthesized")],
               name=name_of(P, self.vnet, "bo-vnet"), name_field="name", depends=self.depends(self.rg))
        self.snet = P.node("bo:NetworkEndpoint")
        P.step(self.snet, "azurerm_subnet",
               [val("resource_group_name", refterm(P, self.rg, "azurerm_resource_group", "name"), "synthesized"),
                val("virtual_network_name", refterm(P, self.vnet, "azurerm_virtual_network", "name"), "synthesized"),
                val("address_prefixes", lit(["10.20.1.0/24"]), "synthesized")],
               name=name_of(P, self.snet, "bo-snet"), name_field="name", depends=self.depends(self.rg, self.vnet))
        for n, k in ((self.vnet, "inNetwork"), (self.snet, "inNetwork")):
            P.ref(n, self.rg, "bo:inResourceGroup")
        P.ref(self.snet, self.vnet, "bo:inNetwork")
        P.contexts.append({"key": "region", "value": AZ_LOCATION, "state": "known"})

    def rule_set(self, gi, g, rules):
        P, T = self.P, self.T
        from .translate import lit, name_of, refterm, val
        sn = P.node("bo:FilterRuleSet")
        self.set_nodes[gi] = sn
        P.ref(sn, self.rg, "bo:inResourceGroup")
        P.step(sn, "azurerm_network_security_group",
               [val("resource_group_name", refterm(P, self.rg, "azurerm_resource_group", "name"), "synthesized"),
                val("location", refterm(P, self.rg, "azurerm_resource_group", "location"), "synthesized")],
               name=name_of(P, sn, "bo-nsg"), name_field="name", depends=self.depends(self.rg))
        used = set()
        self._prio = self.plan_priorities(rules, "azurerm:azurerm_network_security_rule:priority", required=True)
        for k, tr in enumerate(rules):
            cn = P.node("bo:FilterRule", component_of=sn, occurrence=[f"g{gi}", f"r{k}"])
            P.ref(cn, sn, "bo:ruleInSet", "attachment")
            P.ref(cn, self.rg, "bo:inResourceGroup")
            vals = [val("resource_group_name", refterm(P, self.rg, "azurerm_resource_group", "name"), "synthesized"),
                    self.member_ref(tr, "network_security_group_name",
                                    "azurerm:azurerm_network_security_rule:network_security_group_name",
                                    refterm(P, sn, "azurerm_network_security_group", "name"))]
            A = "azurerm:azurerm_network_security_rule:"
            eff = self.neutral(tr, "effect")
            f = _src_fact(tr, "effect")
            if f is not None and f.origin == "atom":
                ta, oa = self.resolve(tr, "effect", "access", A + "access")
            else:
                ta, oa = self.resolve(tr, "effect", "access", A + "access", neutral=eff,
                                      codec=lambda e: CY.lower_effect("azurerm", e))
            self.decide(tr, "access", ta["value"])
            t, o = self.resolve(tr, "direction", "direction", A + "direction", neutral=self.neutral(tr, "direction"),
                                codec=lambda d: CY.lower_direction("azurerm", d))
            vals.append(val("direction", t, o))
            self.decide(tr, "direction", t["value"])
            vals.append(val("access", ta, oa))
            pr = self._priority(tr, used)
            vals.append(val("priority", lit(pr[0]), pr[1]))
            pt, po = self.resolve(tr, "protocol", "protocol", A + "protocol", neutral=self.neutral(tr, "protocol"),
                                  codec=lambda p: V.proto_out("azurerm", p))
            vals.append(val("protocol", pt, po))
            self._ports(tr, vals, A)
            self._ranges(tr, vals, A, t_dir=vals[2]["term"]["value"])
            P.step(cn, "azurerm_network_security_rule", vals, name=name_of(P, cn, "bo-rule"), name_field="name",
                   depends=self.depends(self.rg, sn))

    def _priority(self, tr, used):
        if tr.get("synth") == "catch_all":
            return tr["priority"], "synthesized"
        return self._prio[id(tr)]

    def _ports(self, tr, vals, A):
        from .translate import lit, val
        f = _src_fact(tr, "dst_ports")
        T = self.T
        if f is not None and f.origin == "atom" and f.status == "known" and tr["src_rule"].provider in ("aws", "oci"):
            r = tr["src_rule"]
            o = CY.carry_group(T.cs, f.atom, None, A + "destination_port_range", ctx=self.guard_ctx(tr),
                               bindings=dict(r.atoms))
            if o is None or not o.ok:
                code = (o.code if o else "UNPROVEN") or "UNPROVEN"
                T.trace(atom=f.atom, raw=f.raw, result="blocked", code=code, individual=r.rid,
                        prop="bo:ruleDestinationPorts", claim_id=o.claim_id if o else None,
                        detail=o.detail if o else "nenhuma alegação de grupo de portas")
                from .translate import Blocked
                raise Blocked(code, "portas: sem alegação de grupo OK")
            T.trace(atom=f.atom, raw=f.raw, result="carried", out_atom=A + "destination_port_range", out_value=o.value,
                    claim_id=o.claim_id, prop="bo:ruleDestinationPorts", fn=o.fn, individual=r.rid,
                    meta=[f"alegação {o.claim_id}"])
            self.mark_group(tr, o, f.atom)
            vals.append(val("destination_port_range", lit(o.value)))
        elif f is not None and f.origin == "atom" and f.status != "absent":
            t, o = self.resolve(tr, "dst_ports", "destination_port_ranges", A + "destination_port_ranges", list_ok=True)
            vals.append(val("destination_port_ranges", t, o))
        else:
            n = self.neutral(tr, "dst_ports")
            t, o = self.resolve(tr, "dst_ports", "destination_port_range", A + "destination_port_range",
                                neutral=n, codec=lambda ps: "*" if ps == "ANY" else (
                                    CY.port_text(*ps[0]) if len(ps) == 1 else None))
            vals.append(val("destination_port_range", t, o))
        n = self.neutral(tr, "src_ports") if tr.get("src_rule") is not None else "ANY"
        fsp = _src_fact(tr, "src_ports")
        if fsp is not None and fsp.origin == "atom" and fsp.status == "known" and fsp.raw is not None:
            t, o = self.resolve(tr, "src_ports", "source_port_range", A + "source_port_range")
        else:
            res = self.resolve(tr, "src_ports", "source_port_range", A + "source_port_range", neutral=n, required=False,
                               codec=lambda ps: "*" if ps == "ANY" else (CY.port_text(*ps[0]) if len(ps) == 1 else None))
            if res is None:
                return
            t, o = res
        vals.append(val("source_port_range", t, o))

    def _ranges(self, tr, vals, A, t_dir):
        from .translate import lit, val
        ingress = t_dir == "Inbound"
        rf, lf = ("source_address_prefix", "destination_address_prefix") if ingress else (
            "destination_address_prefix", "source_address_prefix")
        f = _src_fact(tr, "remote")
        if f is not None:
            many = isinstance(f.raw, list) and len(f.raw) != 1
            fld = rf + ("es" if many else "")
            if isinstance(f.raw, list) and len(f.raw) == 1:
                t, o = self.resolve(tr, "remote", fld, A + fld, element=f.raw[0])
            else:
                t, o = self.resolve(tr, "remote", fld, A + fld, list_ok=many)
            vals.append(val(fld, t, o))
        else:
            rem = tr["remote"]
            if len(rem) == 1:
                vals.append(val(rf, lit("*" if rem[0] == "0.0.0.0/0" else rem[0]), "synthesized"))
            else:
                vals.append(val(rf + "es", lit(list(rem)), "synthesized"))
        fl = _src_fact(tr, "local")
        if fl is not None and fl.status not in ("absent",) and fl.origin == "atom":
            t, o = self.resolve(tr, "local", lf, A + lf, element=fl.raw[0] if isinstance(fl.raw, list) and len(fl.raw) == 1 else False)
            vals.append(val(lf, t, o))
        else:
            n = self.neutral(tr, "local") if tr.get("src_rule") is not None else "ANY"
            t, o = self.resolve(tr, "local", lf, A + lf, neutral=n, codec=lambda x: "*" if x == "ANY" else None)
            vals.append(val(lf, t, o))

    def endpoints(self, groups):
        P = self.P
        from .translate import lit, name_of, refterm, val
        for gi, g in enumerate(groups):
            for tid in g["endpoints"]:
                nic = P.node("bo:NetworkEndpoint")
                P.ref(nic, self.rg, "bo:inResourceGroup")
                P.ref(nic, self.snet, "bo:inSubnet")
                P.step(nic, "azurerm_network_interface",
                       [val("resource_group_name", refterm(P, self.rg, "azurerm_resource_group", "name"), "synthesized"),
                        val("location", refterm(P, self.rg, "azurerm_resource_group", "location"), "synthesized"),
                        val("ip_configuration.name", lit("ipc"), "synthesized"),
                        val("ip_configuration.subnet_id", refterm(P, self.snet, "azurerm_subnet", "id"), "synthesized"),
                        val("ip_configuration.private_ip_address_allocation", lit("Dynamic"), "synthesized")],
                       name=name_of(P, nic, "bo-nic"), name_field="name", depends=self.depends(self.rg, self.snet))
                an = P.node("bo:RuleSetAttachment")
                sn = self.set_nodes[gi]
                P.ref(an, sn, "bo:attachesRuleSet", "attachment")
                P.ref(an, nic, "bo:attachesEndpoint", "attachment")
                P.step(an, "azurerm_network_interface_security_group_association",
                       [val("network_interface_id", refterm(P, nic, "azurerm_network_interface", "id"), "synthesized"),
                        self.attach_ref(tid, "network_security_group_id",
                                        "azurerm:azurerm_network_interface_security_group_association:"
                                        "network_security_group_id",
                                        refterm(P, sn, "azurerm_network_security_group", "id"))],
                       depends=self.depends(nic, sn))
                self.T.out.endpoints[tid] = {"node": nic, "kind": "azure_nic", "assoc": an, "set_node": sn}


# --------------------------------------------------------------------------------------------- OCI

class OciBuilder(Builder):
    provider = "oci"

    def context(self):
        from .translate import lit, name_of, val
        P = self.P
        self.comp = P.term({"kind": "symbol", "symbol_id": _sym(P, "compartment"), "name_class": "variable",
                            "scope": "repo"})
        self.vcn = P.node("bo:NetworkEndpoint")
        P.step(self.vcn, "oci_core_vcn", [val("compartment_id", P.terms[int(self.comp[1:]) - 1]["term"], "synthesized"),
                                          val("cidr_blocks", lit([OCI_VCN_CIDR]), "synthesized")],
               name=name_of(P, self.vcn, "vcn", literal_name=True), name_field="display_name")
        P.contexts.append({"key": "synthetic_account", "value": None, "state": "symbolic"})

    def rule_set(self, gi, g, rules):
        P, T = self.P, self.T
        from .translate import lit, name_of, refterm, val
        sn = P.node("bo:FilterRuleSet")
        self.set_nodes[gi] = sn
        P.ref(sn, self.vcn, "bo:inNetwork")
        vals = [val("compartment_id", P.terms[int(self.comp[1:]) - 1]["term"], "synthesized"),
                val("vcn_id", refterm(P, self.vcn, "oci_core_vcn", "id"), "synthesized")]
        idx = {"ingress": 0, "egress": 0}
        choices = []
        for k, tr in enumerate(rules):
            eff = self.neutral(tr, "effect")
            if eff != "allow":
                raise_block(T, tr, "effect", "destino só-permissão: regra que não permite não tem realização")
            d = self.neutral(tr, "direction")
            if d not in ("ingress", "egress"):
                raise_block(T, tr, "direction", "sentido escolhe o bloco (ingress/egress_security_rules): "
                                                "desconhecido no controle", "UNKNOWN_INPUT")
            self.unexpressible(tr, src_ports=False, local=False, src_ports_block=True)
            self.mark_allow_only(tr)
            blk = "ingress_security_rules" if d == "ingress" else "egress_security_rules"
            fd = _src_fact(tr, "direction")
            if fd is not None and fd.atom and fd.status == "known":
                T.trace(atom=fd.atom, raw=fd.raw, result="carried", out_atom=f"oci:oci_core_security_list:{blk}",
                        out_value=d, prop="bo:hasDirection", individual=tr["src_rule"].rid,
                        meta=["codec de realização do sentido -> bloco ingress/egress_security_rules"],
                        realization="RZ-oci-direction", detail="sentido descido pela escolha do bloco no destino")
            fl = _src_fact(tr, "local")
            if fl is not None and fl.atom and fl.raw is not None and fl.status == "absent":
                T.consumed[(tr["src_rule"].rid, fl.atom)] = ([], "endereço local 'qualquer': sem filtro local no destino")
            remote = "source" if d == "ingress" else "destination"
            cn = P.node("bo:FilterRule", component_of=sn, occurrence=[f"g{gi}", f"r{k}"])
            P.ref(cn, sn, "bo:ruleInSet", "attachment")
            S = f"oci:oci_core_security_list:{blk}."
            fr = _src_fact(tr, "remote")
            elems = (fr.raw if isinstance(fr.raw, list) else [fr.raw]) if fr is not None and fr.status == "known" else (
                tr.get("remote") or [None])
            if fr is not None and fr.status != "known":
                self.resolve(tr, "remote", remote, S + remote)
            if fr is not None and len(elems) > 1 and not T.K.structural:
                raise_block(T, tr, "remote", "várias faixas numa regra de faixa única: separar em ocorrências é "
                                             "realização (c2+)")
            for e in elems:
                i = idx[d]
                idx[d] += 1
                base = f"{blk}.{i}."
                pt, po = self.resolve(tr, "protocol", base + "protocol", S + "protocol",
                                      neutral=self.neutral(tr, "protocol"), codec=lambda p: V.proto_out("oci", p))
                vals.append(val(base + "protocol", pt, po))
                if fr is not None:
                    t, o = self.resolve(tr, "remote", base + remote, S + remote,
                                        element=e if isinstance(fr.raw, list) else False)
                else:
                    t, o = lit(e), "synthesized"
                vals.append(val(base + remote, t, o))
                vals.append(val(base + "stateless", lit(False), "synthesized"))
                if k == 0 and i == 0:
                    choices.append({"choice_id": f"CH-OCI-STATE-{gi}", "options": ["stateful", "stateless"],
                                    "selected": "stateful",
                                    "reason": "estado da origem sem evidência no controle: escolha declarada no destino "
                                              "(perda UNKNOWN_INPUT)"})
                T.loss("UNKNOWN_INPUT", "stateless", "estado de conexão escolhido no destino (origem sem evidência)")
                if pt["value"] in ("6", "17"):
                    opt = "tcp_options" if pt["value"] == "6" else "udp_options"
                    self._ports(tr, vals, base + opt, S + opt)
        P.step(sn, "oci_core_security_list", vals, name=name_of(P, sn, "sl", literal_name=True),
               name_field="display_name", depends=self.depends(self.vcn), choices=choices)

    def _ports(self, tr, vals, base, S):
        from .translate import Blocked, lit, val
        T = self.T
        f = _src_fact(tr, "dst_ports")
        if f is not None and f.origin == "atom" and f.status == "known":
            r = tr["src_rule"]
            for mm in ("min", "max"):
                tatom = f"{S}.{mm}"
                src = f.atom
                if r.provider == "aws":
                    src = f.atom.replace("from_port", "from_port" if mm == "min" else "to_port")
                    o = CY.carry(T.cs, src, r.atoms.get(src), tatom, ctx=self.guard_ctx(tr))
                else:
                    elems = f.raw if isinstance(f.raw, list) else [f.raw]
                    if len(elems) != 1:
                        raise_block(T, tr, "dst_ports", "lista de faixas numa regra de faixa única")
                    o = CY.carry_group(T.cs, f.atom, elems[0], tatom, ctx=self.guard_ctx(tr), bindings={f.atom: elems[0]})
                if o is None or not o.ok:
                    code = (o.code if o else "UNPROVEN") or "UNPROVEN"
                    T.trace(atom=f.atom, raw=f.raw, result="blocked", code=code, individual=r.rid,
                            prop="bo:rulePortRangeStart", claim_id=o.claim_id if o else None,
                            detail=o.detail if o else "nenhuma alegação de porta")
                    raise Blocked(code, "portas: sem alegação OK")
                T.trace(atom=src if r.provider == "aws" else f.atom, raw=f.raw, result="carried", out_atom=tatom,
                        out_value=o.value, claim_id=o.claim_id,
                        prop="bo:rulePortRangeStart" if mm == "min" else "bo:rulePortRangeEnd", fn=o.fn,
                        individual=r.rid, meta=[f"alegação {o.claim_id}"])
                self.mark_group(tr, o, f.atom)
                vals.append(val(f"{base}.{mm}", lit(o.value)))
            return
        n = self.neutral(tr, "dst_ports")
        if n is None:
            raise_block(T, tr, "dst_ports", "portas desconhecidas no controle", "UNKNOWN_INPUT")
        if n == "ANY":
            return
        pt = _ports_tuple(n)
        if pt == "MULTI":
            raise_block(T, tr, "dst_ports", "várias faixas numa regra de faixa única")
        vals += [val(f"{base}.min", lit(pt[0]), "synthesized"), val(f"{base}.max", lit(pt[1]), "synthesized")]

    def endpoints(self, groups):
        P = self.P
        from .translate import lit, name_of, refterm, val
        k = 0
        for gi, g in enumerate(groups):
            for tid in g["endpoints"]:
                k += 1
                sub = P.node("bo:NetworkEndpoint")
                sn = self.set_nodes[gi]
                P.ref(sub, self.vcn, "bo:inNetwork")
                P.ref(sub, sn, "bo:attachesRuleSet", "attachment")
                P.step(sub, "oci_core_subnet",
                       [val("compartment_id", P.terms[int(self.comp[1:]) - 1]["term"], "synthesized"),
                        val("vcn_id", refterm(P, self.vcn, "oci_core_vcn", "id"), "synthesized"),
                        val("cidr_block", lit(f"10.0.{k}.0/24"), "synthesized"),
                        self.attach_ref(tid, "security_list_ids", "oci:oci_core_subnet:security_list_ids",
                                        {"kind": "list", "items": [refterm(P, sn, "oci_core_security_list", "id")]})],
                       name=name_of(P, sub, f"subnet{k}", literal_name=True), name_field="display_name",
                       depends=self.depends(self.vcn, sn))
                self.T.out.endpoints[tid] = {"node": sub, "kind": "oci_subnet", "set_node": sn}


BUILDERS = {"aws": AwsBuilder, "google": GoogleBuilder, "azurerm": AzureBuilder, "oci": OciBuilder}
