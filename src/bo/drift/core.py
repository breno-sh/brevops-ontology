"""Núcleo do DRIFT: estados por versão amostrada, eventos tipados e renomes com prova.

Tudo aqui é função pura sobre "fotos" do schema (átomo -> estado) em versões já ordenadas; a leitura dos
arquivos fica em build.py. Regras (declaradas em churn.json e no summary.json):

- Intervalo de um evento: (after, until] entre duas versões OBSERVADAS consecutivas. Versão listada sem
  átomos é lacuna: o intervalo a atravessa, nada é interpolado.
- Truncamento à esquerda: átomo já presente na primeira versão observada não ganha evento de adição.
- Mudança de contrato: um evento por campo comparado que mudou (COMPARED em common.py). ForceNew e Default
  não são observáveis no estimando (o schema JSON do plugin não os exporta): zero eventos por construção.
- Renome (sempre dentro do mesmo tipo de recurso, C13-RENAME), em ordem de precedência:
  R1 publicado: frase de guia de atualização da major que o intervalo cruza, na seção do tipo, cita os dois
     nomes; pista "renamed" basta, pista de substituição exige o mesmo tf_type; o par tem de ser único.
  R2 derivado (ponte de depreciação): o átomo antigo passou a deprecated no MESMO intervalo em que o novo
     apareceu, os dois conviveram, o antigo saiu; mesmo bloco pai, mesmo tf_type, nomes com os mesmos tokens
     (um contido no outro) e par único nos dois sentidos.
  Sem R1 nem R2, o par estrutural (saiu X, entrou Y, mesmo pai, mesmo tf_type, tokens relacionados, único)
  vai para rename_candidates como UNPROVEN e os eventos continuam remoção + adição.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field

from . import common

STATE_FIELDS = common.COMPARED   # ordem da tupla de estado
I_TF, I_REQ, I_OPT, I_COMP, I_SENS, I_DEP, I_WO, I_NEST, I_BP = range(len(STATE_FIELDS))
TYPE_ORDER = {"addition": 0, "rename": 1, "removal": 2, "contract_change": 3}


# ---------------------------------------------------------------------------------------------- estados
_INTERN: dict = {}


def state_of(atom: dict) -> tuple:
    """Tupla de estado (campos COMPARED); tf_type e block_path como JSON canônico para serem hasheáveis."""
    st = (common.dumps(atom["tf_type"]), bool(atom["required"]), bool(atom["optional"]), bool(atom["computed"]),
          bool(atom.get("sensitive", False)), bool(atom.get("deprecated", False)),
          bool(atom.get("write_only", False)), atom.get("nesting", "none"), common.dumps(atom.get("block_path", [])))
    return _INTERN.setdefault(st, st)


def field_value(st: tuple, i: int):
    v = st[i]
    return json.loads(v) if i in (I_TF, I_BP) else v


def snapshot(atoms: list[dict], provider: str) -> tuple[dict, dict]:
    """(atom_id -> estado, atom_id -> (resource_type, path)) de uma versão; reprova átomo de outro provider ou
    atom_id repetido."""
    snap, meta = {}, {}
    for a in atoms:
        aid = a["atom_id"]
        if a["provider"] != provider:
            raise ValueError(f"{aid}: provider {a['provider']} != {provider}")
        if aid in snap:
            raise ValueError(f"{aid}: repetido na mesma versão")
        if aid != f"{provider}:{a['resource_type']}:{a['path']}":
            raise ValueError(f"{aid}: atom_id != provider:resource_type:path")
        snap[aid] = state_of(a)
        meta[aid] = (a["resource_type"], a["path"])
    return snap, meta


# ---------------------------------------------------------------------------------------------- nomes
_TOKEN_NORM = {"enabled": "enable", "disabled": "disable"}


def _singular(t: str) -> str:
    """Plural inglês regular -> singular (policies -> policy, processes -> process, ids -> id)."""
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith(("sses", "xes", "zes", "ches", "shes")):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _tokens(name: str) -> frozenset:
    out = set()
    for t in name.lower().split("_"):
        if not t:
            continue
        out.add(_singular(_TOKEN_NORM.get(t, t)))
    return frozenset(out)


def lexically_related(a: str, b: str) -> bool:
    """Nomes relacionados pela última parte do caminho: mesmos tokens, tokens de um contidos nos do outro
    (name -> db_name, enable_auto_scaling -> auto_scaling_enabled, dns_zone_id -> dns_zone_ids), ou a forma
    sem sublinhados de um contida na do outro, com 4+ letras (azure_keyvault_x -> key_vault_x)."""
    if a == b:
        return False
    la, lb = a.rsplit(".", 1)[-1], b.rsplit(".", 1)[-1]
    ta, tb = _tokens(la), _tokens(lb)
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    short, long_ = sorted((la.lower().replace("_", ""), lb.lower().replace("_", "")), key=len)
    return len(short) >= 4 and short in long_


def parent(path: str) -> str:
    return path.rpartition(".")[0]


def _split_on(path: str, mention: str):
    """Ocorrências de `mention` como segmento(s) inteiro(s) do caminho: lista de (prefixo, sufixo)."""
    segs, ms = path.split("."), mention.split(".")
    out = []
    for i in range(len(segs) - len(ms) + 1):
        if segs[i:i + len(ms)] == ms:
            out.append((".".join(segs[:i]), ".".join(segs[i + len(ms):])))
    return out


def mention_pairs(x_path: str, y_path: str, m1: str, m2: str) -> bool:
    """x = pre + m1 + post e y = pre + m2 + post (mesmo contexto antes e depois): renome de atributo ou de
    bloco (os filhos levam o mesmo sufixo)."""
    a = set(_split_on(x_path, m1))
    return any(p in a for p in _split_on(y_path, m2))


# ---------------------------------------------------------------------------------------------- resultado
@dataclass
class ProviderResult:
    provider: str
    observed: list            # versões observadas, em ordem
    history: dict             # atom_id -> [estado | None por versão observada]
    meta: dict                # atom_id -> (resource_type, path)
    events: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    interval_stats: list = field(default_factory=list)


def event_id(provider: str, key: str) -> str:
    # 32 hex: token longo de hash (o privacy_lint não lê 12 dígitos seguidos dentro dele como conta)
    return f"EV-DRIFT-{provider}-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _ev(provider, etype, rt, after, until, evidence, **kw) -> dict:
    key = "|".join([etype, kw.get("atom_id", ""), kw.get("from_atom", ""), kw.get("to_atom", ""),
                    (kw.get("change") or {}).get("field", ""), after, until])
    e = {"event_id": event_id(provider, key), "provider": provider, "resource_type": rt, "event_type": etype,
         "version_interval": {"after": after, "until": until}, "evidence": evidence}
    e.update(kw)
    return e


def diff_ref(provider: str, a: str, b: str) -> dict:
    return {"level": "derived", "ref": f"DRIFT-DIFF:{provider}:{a}..{b}"}


# ---------------------------------------------------------------------------------------------- renomes
def _run_start(h: list, i: int) -> int:
    """Primeiro índice da sequência contínua de presença que contém i."""
    while i > 0 and h[i - 1] is not None:
        i -= 1
    return i


def _deprecation_start(h: list, i: int) -> int | None:
    """Índice em que o átomo (presente em i) passou a deprecated dentro da presença atual, se observado."""
    r = _run_start(h, i)
    for d in range(r + 1, i + 1):
        if h[d][I_DEP] and not h[d - 1][I_DEP]:
            return d
    return None


def find_renames(provider: str, i: int, res: ProviderResult, B: dict, rem: set, add: set, sentences: list):
    """Pares de renome no intervalo (observed[i-1], observed[i]]; B = foto de observed[i].
    Devolve (renomes {x: (y, regra, evidência)}, candidatos)."""
    obs, H, meta = res.observed, res.history, res.meta
    a_v, b_v = obs[i - 1], obs[i]
    by_rt_b = defaultdict(list)
    for aid in sorted(B):
        by_rt_b[meta[aid][0]].append(aid)
    by_rt_rem = defaultdict(list)
    for x in rem:
        by_rt_rem[meta[x][0]].append(x)

    renames: dict = {}       # x -> (y, rule, evidence)
    cands: list = []
    used_y: set = set()

    # R1: frases publicadas dos guias da major cruzada pelo intervalo
    ma, mb = common.major(a_v), common.major(b_v)
    applicable = [s for s in sentences if ma < s.major <= mb]
    if applicable:
        pub = defaultdict(lambda: defaultdict(list))   # x -> y -> [frases]
        repl: dict = {}                                 # (x, y) -> (status, frase)
        for s in applicable:
            for rt in s.resources:
                xs = by_rt_rem.get(rt)
                if not xs:
                    continue
                ys = [y for y in by_rt_b.get(rt, ()) if y not in rem]
                for m1 in s.mentions:
                    for m2 in s.mentions:
                        if m1 == m2:
                            continue
                        for x in xs:
                            xp = meta[x][1]
                            if not _split_on(xp, m1):
                                continue
                            for y in ys:
                                yp = meta[y][1]
                                if not mention_pairs(xp, yp, m1, m2):
                                    continue
                                same_t = H[x][i - 1][I_TF] == H[y][i][I_TF]
                                if s.cue == "rename" or (same_t and lexically_related(m1, m2)):
                                    pub[x][y].append(s)
                                else:
                                    # substituição publicada que não prova renome: sucessor citado, mas
                                    # tf_type diferente ou nomes sem relação (name -> id, x_name -> x_id)
                                    repl.setdefault((x, y), ("REPLACEMENT" if same_t else
                                                             "REPLACEMENT_TYPE_CHANGED", s))
        target_count = defaultdict(int)
        for x, ys in pub.items():
            for y in ys:
                target_count[y] += 1
        for x, ys in sorted(pub.items()):
            rt = meta[x][0]
            if len(ys) == 1 and target_count[next(iter(ys))] == 1:
                y, ss = next(iter(ys.items()))
                ev = [_doc(s) for s in sorted(set(ss), key=lambda s: (s.file, s.line))[:3]]
                renames[x] = (y, "R1", ev)
                used_y.add(y)
            else:
                for y, ss in sorted(ys.items()):
                    cands.append(_cand(provider, rt, x, y, a_v, b_v, "AMBIGUOUS", "R1", [_doc(ss[0])]))
        for (x, y), (status, s) in sorted(repl.items()):
            if x not in pub:
                cands.append(_cand(provider, meta[x][0], x, y, a_v, b_v, status, "R1", [_doc(s)]))

    # R2: ponte de depreciação
    bridge = defaultdict(list)
    for x in sorted(rem):
        if x in renames:
            continue
        hx = H[x]
        d = _deprecation_start(hx, i - 1)
        if d is None:
            continue
        rt, xp = meta[x]
        for y in by_rt_b.get(rt, ()):
            if y in rem or y in used_y:
                continue
            hy = H[y]
            yp = meta[y][1]
            if parent(yp) != parent(xp) or not lexically_related(xp, yp):
                continue
            if hy[d] is None or hy[d - 1] is not None or _run_start(hy, i) != d:
                continue          # o novo tem de aparecer no mesmo intervalo da depreciação e ficar até i
            if hy[i][I_DEP] or hy[i][I_TF] != hx[i - 1][I_TF]:
                continue
            bridge[x].append((y, d))
    tcount = defaultdict(int)
    for x, ys in bridge.items():
        for y, _ in ys:
            tcount[y] += 1
    for x, ys in sorted(bridge.items()):
        rt = meta[x][0]
        if len(ys) == 1 and tcount[ys[0][0]] == 1:
            y, d = ys[0]
            ref = (f"DRIFT-RULE-R2:{x}~{y.rsplit(':', 1)[-1]}:deprecated_and_added({obs[d - 1]}..{obs[d]})"
                   f":removed({a_v}..{b_v})")
            renames[x] = (y, "R2", [{"level": "derived", "ref": ref,
                                     "note": "ponte de depreciação: antigo deprecated no intervalo em que o novo "
                                             "apareceu; conviveram; antigo removido; mesmo pai e tf_type"}])
            used_y.add(y)
        else:
            for y, _ in ys:
                cands.append(_cand(provider, rt, x, y, a_v, b_v, "AMBIGUOUS", "R2", []))

    # Candidatos estruturais sem prova (UNPROVEN): saiu X, entrou Y no mesmo intervalo
    struct = defaultdict(list)
    add_by_rt = defaultdict(list)
    for y in add:
        if y not in used_y:
            add_by_rt[meta[y][0]].append(y)
    for x in sorted(rem):
        if x in renames:
            continue
        rt, xp = meta[x]
        for y in sorted(add_by_rt.get(rt, ())):
            yp = meta[y][1]
            if parent(yp) == parent(xp) and lexically_related(xp, yp) and H[y][i][I_TF] == H[x][i - 1][I_TF]:
                struct[x].append(y)
    sc = defaultdict(int)
    for ys in struct.values():
        for y in ys:
            sc[y] += 1
    for x, ys in sorted(struct.items()):
        st = "UNPROVEN" if len(ys) == 1 and sc[ys[0]] == 1 else "AMBIGUOUS"
        for y in sorted(ys):
            cands.append(_cand(provider, meta[x][0], x, y, a_v, b_v, st, "STRUCT", []))
    return renames, cands


def _doc(s) -> dict:
    return {"level": "published", "doc": {"repo": s.repo, "tag": s.tag, "file": s.file, "line": s.line,
                                          "sentence": s.text}}


def _cand(provider, rt, x, y, a, b, status, rule, evidence) -> dict:
    return {"provider": provider, "resource_type": rt, "from_atom": x, "to_atom": y,
            "version_interval": {"after": a, "until": b}, "status": status, "rule": rule,
            "evidence": evidence}


# ---------------------------------------------------------------------------------------------- análise
def analyze(provider: str, observed: list[str], snaps: list[dict], metas: list[dict],
            sentences: list | None = None) -> ProviderResult:
    """observed: versões observadas em ordem semver; snaps[i]: atom_id -> estado; metas[i]: atom_id ->
    (resource_type, path). Gera histórico, eventos, candidatos e contagens por intervalo."""
    if [common.semver_key(v) for v in observed] != sorted(common.semver_key(v) for v in observed) \
            or len(set(observed)) != len(observed):
        raise ValueError("versões observadas fora de ordem ou repetidas")
    meta: dict = {}
    for m in metas:
        for aid, rt_path in m.items():
            if meta.setdefault(aid, rt_path) != rt_path:
                raise ValueError(f"{aid}: resource_type/path mudou entre versões")
    n = len(observed)
    H = {aid: [None] * n for aid in meta}
    for i, s in enumerate(snaps):
        for aid, st in s.items():
            H[aid][i] = st
    res = ProviderResult(provider, list(observed), H, meta)
    sentences = sentences or []
    for i in range(1, n):
        a_v, b_v = observed[i - 1], observed[i]
        A, B = snaps[i - 1], snaps[i]
        rem = A.keys() - B.keys()
        add = B.keys() - A.keys()
        renames, cands = find_renames(provider, i, res, B, rem, add, sentences)
        res.candidates += cands
        to_same_interval = {y for y, _, _ in renames.values() if y in add}
        dref = diff_ref(provider, a_v, b_v)
        evs = []
        for x in rem:
            rt = meta[x][0]
            if x in renames:
                y, rule, ev = renames[x]
                evs.append(_ev(provider, "rename", rt, a_v, b_v, ev + [dref], from_atom=x, to_atom=y))
            else:
                evs.append(_ev(provider, "removal", rt, a_v, b_v, [dref], atom_id=x))
        for y in add:
            if y not in to_same_interval:
                evs.append(_ev(provider, "addition", meta[y][0], a_v, b_v, [dref], atom_id=y))
        by_field = defaultdict(int)
        blocks = set()            # blocos distintos cuja mudança de block_path se propagou aos átomos filhos
        for aid in A.keys() & B.keys():
            sa, sb = A[aid], B[aid]
            if sa is sb:
                continue
            for k, fname in enumerate(STATE_FIELDS):
                if sa[k] != sb[k]:
                    by_field[fname] += 1
                    if k == I_BP:
                        blocks.add((meta[aid][0], changed_block(field_value(sa, k), field_value(sb, k))))
                    evs.append(_ev(provider, "contract_change", meta[aid][0], a_v, b_v, [dref], atom_id=aid,
                                   change={"field": fname, "before": field_value(sa, k),
                                           "after": field_value(sb, k)}))
        evs.sort(key=_event_sort_key)
        res.events += evs
        rts_a = {meta[x][0] for x in A}
        rts_b = {meta[x][0] for x in B}
        cnt = defaultdict(int)
        for e in evs:
            cnt[e["event_type"]] += 1
        rule_cnt = defaultdict(int)
        for _, rule, _ in renames.values():
            rule_cnt[rule] += 1
        res.interval_stats.append({
            "after": a_v, "until": b_v, "atoms_after": len(A), "atoms_until": len(B),
            "events": {t: cnt.get(t, 0) for t in TYPE_ORDER},
            "contract_change_by_field": {f: by_field.get(f, 0) for f in STATE_FIELDS},
            "block_path_changes_distinct_blocks": len(blocks),
            "renames_by_rule": {"R1_published": rule_cnt.get("R1", 0), "R2_derived": rule_cnt.get("R2", 0)},
            "additions_in_new_types": sum(1 for e in evs if e["event_type"] == "addition"
                                          and e["resource_type"] not in rts_a),
            "removals_in_removed_types": sum(1 for e in evs if e["event_type"] == "removal"
                                             and e["resource_type"] not in rts_b),
            "types_added": len(rts_b - rts_a), "types_removed": len(rts_a - rts_b),
            "types_after": len(rts_a), "types_until": len(rts_b),
        })
    uniq = {}
    for c in res.candidates:
        uniq.setdefault((c["from_atom"], c["to_atom"], c["version_interval"]["until"], c["rule"], c["status"]), c)
    res.candidates = sorted(uniq.values(), key=lambda c: (common.semver_key(c["version_interval"]["until"]),
                                                          c["from_atom"], c["to_atom"], c["rule"], c["status"]))
    return res


def changed_block(before: list, after: list) -> str:
    """Caminho do bloco mais externo cuja descrição (modo, min/max) ou nome mudou."""
    names = []
    for b, a in zip(before, after):
        names.append(a.get("block", "?"))
        if b != a:
            return ".".join(names)
    longer = after if len(after) > len(before) else before
    return ".".join(x.get("block", "?") for x in longer[:min(len(before), len(after)) + 1])


def _event_sort_key(e: dict):
    a = e.get("atom_id") or e.get("from_atom")
    return (e["resource_type"], a, TYPE_ORDER[e["event_type"]], (e.get("change") or {}).get("field", ""),
            e.get("to_atom", ""))


def atom_history_records(res: ProviderResult):
    """Registros C13 atom_history em ordem de atom_id (gerador)."""
    ev_by_atom = defaultdict(list)
    for e in res.events:
        for k in ("atom_id", "from_atom", "to_atom"):
            if k in e:
                ev_by_atom[e[k]].append(e["event_id"])
    for aid in sorted(res.history):
        rt, path = res.meta[aid]
        hist, pres = [], []
        for v, st in zip(res.observed, res.history[aid]):
            if st is None:
                hist.append({"version": v, "state": "absent"})
                continue
            pres.append(v)
            item = {"version": v, "state": "present", "tf_type": field_value(st, I_TF), "required": st[I_REQ],
                    "optional": st[I_OPT], "computed": st[I_COMP], "sensitive": st[I_SENS],
                    "deprecated": st[I_DEP]}
            if st[I_WO]:
                item["write_only"] = True
            hist.append(item)
        evs = list(dict.fromkeys(ev_by_atom.get(aid, [])))
        yield {"atom_id": aid, "provider": res.provider, "resource_type": rt, "path": path, "history": hist,
               "first_seen": pres[0] if pres else None, "last_seen": pres[-1] if pres else None, "events": evs}
