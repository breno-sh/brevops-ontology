"""Avaliador de decisão de acesso: dado o modelo neutro (Network) e um fluxo, devolve ALLOW, DENY ou UNKNOWN.

Método (supervaluação): todo valor que não se sabe — parâmetro de provedor sem evidência na leitura, valor
simbólico, pedaço não lido — é um ponto de escolha. O avaliador percorre todas as combinações de escolhas
que a decisão de fato consulta; se todas dão a mesma decisão, ela é a resposta; se não, a resposta é UNKNOWN
com o código do ponto de escolha que dividiu (INCOMPLETE_READ > UNKNOWN_SYMBOLIC_INPUT > MISSING_EVIDENCE).
Nada é preenchido por default (REQ-LOSS-01, REQ-ABS-01).
"""
from __future__ import annotations

from .model import ALLOW, DENY, UNKNOWN, Flow, Network, Packet, Rule, RuleSet, cidr_contains, is_sym
from .semantics import param

CODE_ORDER = ("INCOMPLETE_READ", "UNKNOWN_SYMBOLIC_INPUT", "MISSING_EVIDENCE")


class _Branch(Exception):
    def __init__(self, key, values, code):
        self.key, self.values, self.code = key, values, code


class Chooser:
    def __init__(self, assignment: dict, reading: str):
        self.assignment = assignment
        self.reading = reading
        self.used: dict = {}

    def choose(self, key, values, code):
        if key in self.assignment:
            self.used[key] = code
            return self.assignment[key]
        values = list(values)
        if len(values) == 1:
            return values[0]
        raise _Branch(key, values, code)

    def p(self, provider, name, code="MISSING_EVIDENCE", key_extra=None, values=None):
        pr = param(provider, name, self.reading, values=values)
        if pr.known:
            return pr.value
        return self.choose(("param", provider, name, key_extra), pr.values, code)


def explore(fn, reading: str, limit: int = 4096):
    """Roda fn(chooser) sob toda combinação de escolhas consultada. Devolve [(resultado, {chave: código})]."""
    out, stack, n = [], [dict()], 0
    while stack:
        a = stack.pop()
        n += 1
        if n > limit:
            raise RuntimeError("explosão de escolhas no avaliador")
        ch = Chooser(a, reading)
        try:
            r = fn(ch)
        except _Branch as b:
            for v in reversed(b.values):
                na = dict(a)
                na[b.key] = v
                stack.append(na)
            # guarda o código para relatar depois
            _codes[b.key] = b.code
            continue
        out.append((r, None, a))
    return out


_codes: dict = {}


# ------------------------------------------------------------------ casamento de regra e pacote

def _rule_applies(rule: Rule, target, ch) -> bool:
    if rule.maybe_member and not ch.choose(("member", rule.rule_id, rule.set_id), [True, False], rule.maybe_member):
        return False
    sel = rule.selector
    if sel is None:
        return True
    if sel[0] == "tags":
        tags = sel[1]
        if is_sym(tags):
            return ch.choose(("sym", rule.rule_id, "target_tags"), [True, False], tags.code)
        return bool(set(tags) & set(target.tags))
    if sel[0] == "unspecified":
        prov = rule.set_id.split(":", 1)[0]
        return ch.p(prov, "target.no_selector", key_extra=rule.rule_id) == "applies"
    raise ValueError(f"seletor desconhecido {sel!r}")


def _match_cidrs(spec, ip, ch, key, provider):
    if is_sym(spec):
        return ch.choose(("sym",) + key, [True, False], spec.code)
    if ip is None:
        return ch.choose(("sym",) + key + ("local_ip",), [True, False], "UNKNOWN_SYMBOLIC_INPUT")
    for c in spec:
        if is_sym(c):
            if ch.choose(("sym",) + key + (c.label,), [True, False], c.code):
                return True
        elif c.startswith("SERVICE_TAG:"):
            if ch.p(provider, "service_tag", key_extra=(c, ip)) == "matches":
                return True
        elif cidr_contains(c, ip):
            return True
    return False


def _match_ports(spec, port, ch, key):
    if spec is None:
        return True
    if is_sym(spec):
        return ch.choose(("sym",) + key, [True, False], spec.code)
    if port is None:
        return True
    if is_sym(port):
        return ch.choose(("sym", "port") + key, [True, False], port.code)
    return any(r.contains(port) for r in spec)


def _matches(rule: Rule, pkt: Packet, ch, provider: str) -> bool:
    d = rule.direction
    if is_sym(d):
        d = ch.choose(("sym", rule.rule_id, "direction"), ["ingress", "egress"], d.code)
    if d != pkt.direction:
        return False
    pr = rule.protocol
    if is_sym(pr):
        if not ch.choose(("sym", rule.rule_id, "protocol"), [True, False], pr.code):
            return False
    elif pr != "all" and pr != pkt.protocol:
        return False
    if not _match_cidrs(rule.remote, pkt.remote_ip, ch, (rule.rule_id, "remote"), provider):
        return False
    if rule.local is not None and not _match_cidrs(rule.local, pkt.local_ip, ch, (rule.rule_id, "local"), provider):
        return False
    if pkt.protocol in ("tcp", "udp") or (pr == "all"):
        if pkt.protocol in ("tcp", "udp"):
            if not _match_ports(rule.dst_ports, pkt.dst_port, ch, (rule.rule_id, "dst_ports")):
                return False
            if not _match_ports(rule.src_ports, pkt.src_port, ch, (rule.rule_id, "src_ports")):
                return False
    return True


def _effect(rule: Rule, ch, rs: RuleSet | None = None):
    e = rule.effect
    if is_sym(e):
        return ch.choose(("sym", rule.rule_id, "effect"), ["allow", "deny"], e.code)
    if rs is not None and rs.evaluation == "allow_only" and rs.provider in ("aws", "oci"):
        # o efeito 'só permissão' é derivação deste oráculo; fora da leitura, cada regra pode ser qualquer efeito
        if not param(rs.provider, "evaluation", ch.reading).known:
            return ch.choose(("param", rs.provider, "evaluation", rule.rule_id), ["allow", "deny"], "MISSING_EVIDENCE")
    return e


def _priority(rule: Rule, rs: RuleSet, ch):
    p = rule.priority
    if is_sym(p):
        return ch.choose(("sym", rule.rule_id, "priority"), ["top", "bottom"], p.code)
    if p is None:
        pd = param(rs.provider, "priority.default", ch.reading)
        if pd.known:
            return pd.value
        return ch.choose(("sym", rule.rule_id, "priority"), ["top", "bottom"], "MISSING_EVIDENCE")
    return p


def _rule_state(rule: Rule, rs: RuleSet, ch):
    """Estado de conexão de UMA regra: o da regra, senão o padrão do conjunto, senão escolha."""
    s = rule.state
    if is_sym(s):
        return ch.choose(("sym", rule.rule_id, "state"), ["stateful", "stateless"], s.code)
    if rs.kind == "oci_nsg":
        st = param("oci", "state.nsg_rule", ch.reading)
        if not st.known:
            return ch.choose(("param", "oci", "state.nsg_rule", rule.rule_id), ["stateful", "stateless"], "MISSING_EVIDENCE")
    if s in ("stateful", "stateless"):
        return s
    ds = rs.default_state
    if is_sym(ds):
        return ch.choose(("sym", rs.set_id, "default_state"), ["stateful", "stateless"], ds.code)
    if ds in ("stateful", "stateless"):
        return ds
    # estado de conjunto sem evidência: uma só escolha por conjunto (vale para todas as regras dele)
    return ch.p(rs.provider, "state.default", key_extra=rs.set_id)


def _no_match(rs: RuleSet, direction: str, ch):
    prov = rs.provider
    if rs.evaluation == "allow_only":
        v = ch.p(prov, "allow_only.no_match", key_extra=rs.set_id)
    else:
        pr = param(prov, f"priority.no_match.{direction}", ch.reading)
        if pr.level != "absent":
            v = ch.p(prov, f"priority.no_match.{direction}", key_extra=rs.set_id)
        else:
            v = ch.p(prov, "priority.no_match", key_extra=(rs.set_id, direction), values=["allow", "deny"])
    return ALLOW if v == "allow" else DENY


def decide_set(rs: RuleSet, target, pkt: Packet, ch):
    """Decisão de UM conjunto para um pacote novo: (ALLOW|DENY, rastreado: bool)."""
    matched = [r for r in rs.rules if _rule_applies(r, target, ch) and _matches(r, pkt, ch, rs.provider)]
    phantom = None
    if rs.rules_unread:
        opts = ["none", "allow_top"] + (["deny_top"] if rs.evaluation == "priority_allow_deny" else [])
        code = rs.rules_unread if isinstance(rs.rules_unread, str) else "INCOMPLETE_READ"
        phantom = ch.choose(("unread", rs.set_id, pkt.direction, pkt.remote_ip, str(pkt.dst_port)), opts, code)
    if rs.evaluation == "allow_only":
        effs = [(r, _effect(r, ch, rs)) for r in matched]
        if any(e == "deny" for _, e in effs):
            return DENY, False  # só sob leitura em que o efeito não é evidenciado
        allows = [r for r, e in effs if e == "allow"]
        if phantom == "allow_top" and not allows:
            return ALLOW, ch.choose(("unread_state", rs.set_id), [True, False], "INCOMPLETE_READ")
        if not allows:
            return _no_match(rs, pkt.direction, ch), False
        return ALLOW, _tracked(allows, rs, ch)
    # precedência numérica com permitir e negar
    cands = [(_rank(_priority(r, rs, ch)), _effect(r, ch), r) for r in matched]
    if not cands and phantom in (None, "none"):
        return _no_match(rs, pkt.direction, ch), False
    if phantom in ("allow_top", "deny_top"):
        # regra não lida, adversária: vence sozinha, a menos que a melhor lida já esteja no limite inferior
        # da faixa publicada (aí empata; com prioridade única, como no Azure, não pode empatar e perde)
        best_real = min((c[0] for c in cands), default=None)
        rng = param(rs.provider, "priority.range", ch.reading)
        uniq = param(rs.provider, "priority.unique", ch.reading)
        lb = rng.value[0] if rng.known else None
        if best_real is not None and lb is not None and best_real <= lb:
            if not uniq.known:
                cands.append((best_real, "allow" if phantom == "allow_top" else "deny", None))
        else:
            cands.append((-10 ** 9, "allow" if phantom == "allow_top" else "deny", None))
    best = min(c[0] for c in cands)
    winners = [c for c in cands if c[0] == best]
    effects = {c[1] for c in winners}
    if len(effects) > 1:
        tb = ch.p(rs.provider, "priority.tie_break", key_extra=rs.set_id)
        eff = "deny" if tb == "deny_over_allow" else "allow"
    else:
        eff = effects.pop()
    rules = [c[2] for c in winners if c[1] == eff and c[2] is not None]
    dec = ALLOW if eff == "allow" else DENY
    if dec == DENY:
        return DENY, False
    if not rules:  # quem permitiu foi a regra não lida: estado também não lido
        return ALLOW, ch.choose(("unread_state", rs.set_id), [True, False], "INCOMPLETE_READ")
    return ALLOW, _tracked(rules, rs, ch)


def _rank(p):
    if p == "top":
        return -10 ** 8
    if p == "bottom":
        return 10 ** 9
    return p


def _tracked(rules, rs, ch) -> bool:
    states = {_rule_state(r, rs, ch) for r in rules}
    if states == {"stateful"}:
        return True
    if states == {"stateless"}:
        return False
    return ch.p(rs.provider, "overlap_stateful_stateless", key_extra=rs.set_id) == "tracked"


def _applicable_sets(net: Network, target, ch):
    sets = [net.sets[s] for s in target.sets]
    for s in target.maybe_sets:
        code = target.maybe_code.get(s, "INCOMPLETE_READ")
        if ch.choose(("maybe_attachment", s, target.target_id), [True, False], code):
            sets.append(net.sets[s])
    return sets


def _combine(net: Network, decisions, ch, key):
    vals = {d for d in decisions}
    if len(vals) == 1:
        return vals.pop()
    comb = ch.p(net.provider, "combination", key_extra=key)
    if comb == "single_set":
        raise ValueError("combinação single_set com mais de um conjunto")
    if comb == "all_must_allow":
        return ALLOW if all(d == ALLOW for d in decisions) else DENY
    return ALLOW if any(d == ALLOW for d in decisions) else DENY


def decide_packet(net: Network, target, pkt: Packet, ch):
    sets = _applicable_sets(net, target, ch)
    if not sets:
        v = ch.p(net.provider, "no_set_applies", key_extra=target.target_id, values=["allow", "deny"])
        return (ALLOW if v == "allow" else DENY), {}
    per = {s.set_id: decide_set(s, target, pkt, ch) for s in sets}
    dec = _combine(net, [d for d, _ in per.values()], ch, ("new", target.target_id))
    return dec, per


def _packet_of(net, flow: Flow, target) -> Packet:
    return Packet(direction=flow.direction, protocol=flow.protocol, remote_ip=flow.remote,
                  dst_port=flow.port, src_port=flow.src_port, local_ip=target.ip)


def decide_flow(net: Network, flows: dict, flow: Flow, ch):
    target = net.targets[flow.target]
    if flow.state == "new":
        return decide_packet(net, target, _packet_of(net, flow, target), ch)[0]
    orig = flows[flow.of]
    o_pkt = _packet_of(net, orig, target)
    o_dec, per = decide_packet(net, target, o_pkt, ch)
    if o_dec == DENY:
        return DENY  # sem conexão permitida, não há retorno
    back = "egress" if orig.direction == "ingress" else "ingress"
    reply = Packet(direction=back, protocol=orig.protocol, remote_ip=orig.remote,
                   dst_port=flow.reply_port, src_port=orig.port, local_ip=target.ip)
    rets = []
    for sid, (d, tracked) in per.items():
        rs = net.sets[sid]
        if d == ALLOW and tracked:
            rets.append(ALLOW)
        else:
            rets.append(decide_set(rs, target, reply, ch)[0])
    if not per:
        return decide_packet(net, target, reply, ch)[0]
    return _combine(net, rets, ch, ("return", target.target_id))


def evaluate(net: Network, flows: list, reading: str = "default") -> dict:
    """{flow_id: {"value": ALLOW|DENY|UNKNOWN, "code": ..., "splits": [...]}} para cada fluxo."""
    fmap = {f.flow_id: f for f in flows}
    out = {}
    for f in flows:
        res = explore(lambda ch, f=f: decide_flow(net, fmap, f, ch), reading)
        vals = {r for r, _, _ in res}
        if len(vals) == 1:
            out[f.flow_id] = {"value": vals.pop(), "code": None, "splits": []}
            continue
        keys = set()
        for _, _, a in res:
            keys.update(a)
        piv = _pivotal_codes(res)
        split_codes = [c for c in CODE_ORDER if c in piv]
        if not split_codes:
            split_codes = [c for c in CODE_ORDER if any(_codes.get(k) == c for k in keys)] or ["MISSING_EVIDENCE"]
        out[f.flow_id] = {"value": UNKNOWN, "code": split_codes[0],
                          "splits": sorted({_fmt(k) for k in keys})}
    return out


def _pivotal_codes(res) -> set:
    """Códigos das escolhas pivô: duas execuções com decisões diferentes que só discordam nessa escolha."""
    out = set()
    for i in range(len(res)):
        for j in range(i + 1, len(res)):
            (ri, _, ai), (rj, _, aj) = res[i], res[j]
            if ri == rj:
                continue
            diff = [k for k in set(ai) & set(aj) if ai[k] != aj[k]]
            if len(diff) == 1:
                out.add(_codes.get(diff[0], "MISSING_EVIDENCE"))
    return out


def _fmt(k) -> str:
    return ":".join(str(x) for x in k if x is not None)
