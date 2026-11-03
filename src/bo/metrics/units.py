"""Unidades de análise (PREREG §3 e §5) e adaptadores dos contratos.

Denominador fixado no lado de origem, pela regra de inclusão, antes do tradutor: as funções daqui só leem a
configuração de origem (C06) e os papéis (C04); o desfecho nunca entra na contagem.

Documento JSON de política
  leitura por campo     UM campo (o atributo que carrega o documento), qualquer que seja o tamanho
  leitura por decisão   uma decisão por declaração normalizada (efeito, principal, ação, recurso, condição):
                        listas de Action, Resource e Principal são expandidas em átomos (partir a lista em
                        várias declarações dá o mesmo conjunto), NotAction/NotResource/NotPrincipal ficam como
                        conjunto (partir mudaria o significado), Condition vira JSON canônico com listas de
                        valores como conjunto, Sid e Version saem. O mesmo documento escrito como blocos
                        `statement` de `aws_iam_policy_document` (um campo por atributo de bloco) dá as mesmas
                        decisões: é o caso em que somar campos muda o denominador da leitura por campo e não
                        muda o da leitura por decisão.
  NAME e TAG            fora de todas as leituras, menos M-OPCOV-NAMETAG (um mapa de tags conta uma vez por
                        chave).
"""
from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace

NAME_TAG_ROLES = frozenset({"NAME", "TAG"})
POLICY_BLOCK_TYPES = frozenset({"aws_iam_policy_document"})
_IDX = re.compile(r"\[(\d+)\]")


class UnitError(ValueError):
    pass


class UnsupportedPolicyFormat(UnitError):
    """Documento de política num formato que a normalização não conhece: o chamador decide (nunca 1 por linha)."""


def canon(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def short_hash(s: str, n: int = 16) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


# ------------------------------------------------------------------------------------------------- Unit
@dataclass(frozen=True)
class Unit:
    """Uma unidade de análise com os rótulos de cluster e os códigos de desfecho.

    codes: desfechos que compõem a unidade (resultado/código do C23, desfecho do C12/C22, ou códigos da
    biblioteca); a classe sai de policy.classify_all com a tabela da métrica."""
    unit_id: str
    family_id: str
    repo_id: str
    source: str
    target: str | None = None
    graph_id: str | None = None
    resource_id: str | None = None
    codes: tuple = ()
    weight: float = 1.0
    pilot_exposed: bool = False
    attrs: tuple = ()          # pares (chave, valor) ordenados: domain, pair, stratum, group, complex...

    def attr(self, k, default=None):
        return dict(self.attrs).get(k, default)

    def with_codes(self, codes) -> "Unit":
        return replace(self, codes=tuple(codes))

    def with_attrs(self, **kw) -> "Unit":
        d = dict(self.attrs)
        d.update(kw)
        return replace(self, attrs=tuple(sorted(d.items())))


def mk_attrs(**kw) -> tuple:
    return tuple(sorted(kw.items()))


# ------------------------------------------------------------------------------------------------- termos
def _term_tokens(t) -> list[str]:
    """Valor de um termo C06 como lista de átomos opacos; literal lista vira os elementos."""
    if isinstance(t, dict) and "$term" in t:
        t = t["$term"]
    if isinstance(t, dict) and t.get("kind") == "literal":
        v = t.get("value")
        return [canon(x) for x in v] if isinstance(v, list) else [canon(v)]
    if isinstance(t, dict) and t.get("kind") == "expression" and t.get("op") == "hcl_tuple":
        out = []
        for x in t.get("args", []):   # tupla HCL = lista: cada elemento é um átomo
            out.extend(_term_tokens(x))
        return out
    if isinstance(t, dict) and "kind" in t:
        return ["$term:" + canon(t)]
    if isinstance(t, list):
        out = []
        for x in t:
            out.extend(_term_tokens(x))
        return out
    return [canon(t)]


def _scalar(t) -> str:
    toks = _term_tokens(t)
    if len(toks) != 1:
        raise UnitError(f"esperado escalar, veio {len(toks)} valores")
    return toks[0]


# ------------------------------------------------------------------------------------------------- política
def _principal_atoms(stmt: dict) -> list:
    if "NotPrincipal" in stmt:
        np_ = stmt["NotPrincipal"]
        items = sorted((k, x) for k, v in (np_.items() if isinstance(np_, dict) else [("*", np_)])
                       for x in _term_tokens(v))
        return [("not", canon(items))]
    p = stmt.get("Principal")
    if p is None:
        return [("none", "")]           # política de identidade: o principal é o portador
    if isinstance(p, dict) and "kind" not in p and "$term" not in p:
        return sorted({(k, x) for k, v in p.items() for x in _term_tokens(v)})
    return [("*", x) for x in _term_tokens(p)]


def _list_atoms(stmt: dict, pos: str, neg: str) -> list:
    if neg in stmt:
        return [("not", canon(sorted(set(_term_tokens(stmt[neg])))))]
    if pos not in stmt:
        return [("none", "")]
    return sorted({("is", x) for x in _term_tokens(stmt[pos])})


STATEMENT_KEYS = frozenset({"Sid", "Effect", "Principal", "NotPrincipal", "Action", "NotAction", "Resource",
                            "NotResource", "Condition"})


def _unresolved(stmt: dict) -> dict:
    """Chaves fora da gramática (ex.: chave calculada que virou símbolo): ficam na decisão, nunca somem."""
    return {k: sorted(_term_tokens(v)) for k, v in stmt.items() if k not in STATEMENT_KEYS}


def _condition(stmt: dict) -> str:
    c = stmt.get("Condition")
    extra = _unresolved(stmt)
    if not c and not extra:
        return ""
    if not c:
        return canon({"$unresolved": extra})
    if not isinstance(c, dict):
        return canon({"cond": _term_tokens(c), **({"$unresolved": extra} if extra else {})})
    out = {"$unresolved": extra} if extra else {}
    for op, kv in c.items():
        if isinstance(kv, dict) and "kind" not in kv:
            out[op] = {k: sorted(set(_term_tokens(v))) for k, v in kv.items()}
        else:
            out[op] = sorted(set(_term_tokens(kv)))
    return canon(out)


def _statements(tree) -> list[dict]:
    if not isinstance(tree, dict):
        raise UnsupportedPolicyFormat("documento de política não é objeto")
    if "Statement" in tree:
        st = tree["Statement"]
        return [st] if isinstance(st, dict) else list(st)
    if "bindings" in tree:  # política IAM do GCP: role + members (+ condition)
        out = []
        for b in tree["bindings"]:
            out.append({"Effect": "Allow", "Principal": {"member": b.get("members", [])},
                        "Action": b.get("role"), "Resource": {"kind": "self"},
                        **({"Condition": {"expr": b["condition"]}} if b.get("condition") else {})})
        return out
    raise UnsupportedPolicyFormat("formato de política sem Statement nem bindings")


def policy_decisions(tree) -> list[tuple]:
    """Declarações normalizadas (efeito, principal, ação, recurso, condição), ordenadas e sem repetição.

    Declaração vazia (só Sid/Effect) não é decisão. Chave fora da gramática entra no componente de condição
    como '$unresolved' (a decisão continua contada; o tradutor decide o desfecho)."""
    out = set()
    for st in _statements(tree):
        if not isinstance(st, dict):
            raise UnsupportedPolicyFormat("declaração que não é objeto")
        if not (set(st) - {"Sid", "Effect"}):
            continue   # declaração vazia: não configura nada (nenhum dos cinco componentes)
        e = st.get("Effect", "Allow")
        eff = canon(e) if isinstance(e, str) else _scalar(e)
        cond = _condition(st)
        for pr, ac, rs in itertools.product(_principal_atoms(st), _list_atoms(st, "Action", "NotAction"),
                                            _list_atoms(st, "Resource", "NotResource")):
            out.add((eff, canon(pr), canon(ac), canon(rs), cond))
    return sorted(out)


def _set_path(root: dict, path: str, term):
    """'statement[1].principals[0].identifiers' -> root['statement'][1]['principals'][0]['identifiers']."""
    parts = path.split(".")
    cur = root
    for i, part in enumerate(parts):
        m = re.match(r"^([A-Za-z_][\w]*)((?:\[\d+\])*)$", part)
        if not m:
            raise UnitError(f"caminho de bloco ilegível: {path}")
        name, idxs = m.group(1), [int(x) for x in _IDX.findall(m.group(2))]
        last = i == len(parts) - 1
        if not idxs:
            if last:
                cur[name] = term
            else:
                cur = cur.setdefault(name, {})
            continue
        lst = cur.setdefault(name, {})
        for j, k in enumerate(idxs):
            if j == len(idxs) - 1 and last:
                lst[k] = term
            else:
                lst = lst.setdefault(k, {})
        cur = lst


def _ordered(d):
    return [d[k] for k in sorted(d)] if isinstance(d, dict) else d


def blocks_to_policy(fields: list[dict]) -> dict:
    """Campos `statement[i].*` de aws_iam_policy_document -> árvore de política equivalente (Statement)."""
    root: dict = {}
    for f in fields:
        if not f["attr_path"].startswith("statement"):
            continue
        _set_path(root, f["attr_path"], f["term"])
    stmts = []
    for s in _ordered(root.get("statement", {})):
        st = {"Effect": s.get("effect", {"kind": "literal", "value": "Allow"})}
        for k, j in (("actions", "Action"), ("not_actions", "NotAction"), ("resources", "Resource"),
                     ("not_resources", "NotResource")):
            if k in s:
                st[j] = s[k]
        for k, j in (("principals", "Principal"), ("not_principals", "NotPrincipal")):
            if k in s:
                pr = defaultdict(list)
                for p in _ordered(s[k]):
                    typ = _scalar(p["type"])
                    pr[json.loads(typ) if typ.startswith('"') else typ].extend(_term_tokens(p["identifiers"]))
                if set(pr) == {"*"}:
                    st[j] = [{"kind": "literal", "value": json.loads(x)} if not x.startswith("$term:")
                             else json.loads(x[6:]) for x in pr["*"]]
                else:
                    st[j] = {t: [{"kind": "literal", "value": json.loads(x)} if not x.startswith("$term:")
                                 else json.loads(x[6:]) for x in ids] for t, ids in pr.items()}
        if "condition" in s:
            cond: dict = defaultdict(dict)
            for c in _ordered(s["condition"]):
                test = json.loads(_scalar(c["test"]))
                var = json.loads(_scalar(c["variable"]))
                cond[test].setdefault(var, []).extend(
                    {"kind": "literal", "value": json.loads(x)} if not x.startswith("$term:") else json.loads(x[6:])
                    for x in _term_tokens(c["values"]))
            st["Condition"] = dict(cond)
        stmts.append(st)
    return {"Statement": stmts}


def decisions_of_document(tree) -> list[tuple]:
    return policy_decisions(tree)


# ------------------------------------------------------------------------------------------------- campos e decisões
@dataclass(frozen=True)
class Field:
    """Um átomo de atributo configurado numa ocorrência de bloco (C06 symbolic_config + papel C04)."""
    field_id: str
    resource_id: str
    attr_path: str
    role: str
    family_id: str
    repo_id: str
    provider: str
    resource_type: str
    term: dict = field(hash=False, compare=False, default_factory=dict)
    is_policy_document: bool = False


def resource_id(rec: dict) -> str:
    return f"{rec['repo_id']}|{rec['file']}|{rec['resource_address']}"


def fields_from_symbolic(records, role_of=None) -> list[Field]:
    """Registros C06 symbolic_config -> campos. role_of(atom_id) -> papel C04 (padrão CONFIG).

    Termo withheld fica como campo (o valor nunca é lido); a classificação do desfecho é do tradutor."""
    out = []
    for r in records:
        atom = f"{r['provider']}:{r['resource_type']}:{_IDX.sub('', r['attr_path'])}"
        role = (role_of(atom) if role_of else None) or "CONFIG"
        rid = resource_id(r)
        is_doc = r["term"].get("kind") == "document" and r["term"].get("format") == "policy_json"
        out.append(Field(f"{rid}|{r['attr_path']}", rid, r["attr_path"], role, r["family_id"], r["repo_id"],
                         r["provider"], r["resource_type"], r["term"], is_doc))
    return sorted(out, key=lambda f: f.field_id)


def field_units(fields, nametag: bool = False) -> list[Field]:
    """Inclusão INC-FIELD-01 (nametag=False) ou INC-NAMETAG-01 (nametag=True); um mapa de tags conta uma vez
    por chave. Documento de política é um campo só."""
    out = []
    for f in fields:
        if (f.role in NAME_TAG_ROLES) != nametag:
            continue
        t = f.term
        if nametag and f.role == "TAG" and t.get("kind") == "literal" and isinstance(t.get("value"), dict):
            for k in sorted(t["value"]):
                out.append(replace(f, field_id=f"{f.field_id}[{k}]", term={"kind": "literal",
                                                                          "value": t["value"][k]}))
            continue
        out.append(f)
    return out


@dataclass(frozen=True)
class Decision:
    decision_id: str
    resource_id: str
    concept: str
    family_id: str
    repo_id: str
    provider: str
    field_ids: tuple
    statement: tuple | None = None


def decision_units(fields, concept_of=None) -> list[Decision]:
    """Inclusão INC-DEC-01 sobre campos já incluídos (NAME e TAG fora).

    concept_of(field) -> conceito do glossário (decisão); padrão: o caminho do atributo sem índices (uma
    decisão por atributo configurado). Documentos de política e blocos statement de aws_iam_policy_document
    viram uma decisão por declaração normalizada, com o mesmo id nas duas embalagens."""
    out: dict[str, Decision] = {}
    blocks = defaultdict(list)
    for f in fields:
        if f.role in NAME_TAG_ROLES:
            continue
        if f.resource_type in POLICY_BLOCK_TYPES and f.attr_path.startswith("statement"):
            blocks[f.resource_id].append(f)
            continue
        if f.is_policy_document:
            for st in decisions_of_document(f.term["tree"]):
                did = f"{f.resource_id}|policy|{short_hash(canon(st))}"
                prev = out.get(did)
                ids = tuple(sorted(set((prev.field_ids if prev else ()) + (f.field_id,))))
                out[did] = Decision(did, f.resource_id, "policy_statement", f.family_id, f.repo_id, f.provider,
                                    ids, st)
            continue
        concept = concept_of(f) if concept_of else _IDX.sub("", f.attr_path)
        did = f"{f.resource_id}|{concept}"
        prev = out.get(did)
        ids = tuple(sorted(set((prev.field_ids if prev else ()) + (f.field_id,))))
        out[did] = Decision(did, f.resource_id, concept, f.family_id, f.repo_id, f.provider, ids)
    for rid, fs in blocks.items():
        tree = blocks_to_policy([{"attr_path": f.attr_path, "term": f.term} for f in fs])
        f0 = fs[0]
        for st in decisions_of_document(tree):
            did = f"{rid}|policy|{short_hash(canon(st))}"
            out[did] = Decision(did, rid, "policy_statement", f0.family_id, f0.repo_id, f0.provider,
                                tuple(sorted(f.field_id for f in fs)), st)
    return [out[k] for k in sorted(out)]


# ------------------------------------------------------------------------------------------------- grafos
def config_graphs(records) -> dict[str, str]:
    """Componente conexo de recursos de um repositório ligados por referência (C06): resource_id -> graph_id.

    A referência liga por endereço dentro do mesmo repositório (o arquivo não importa: módulos do mesmo repo
    se enxergam pelo endereço). graph_id = hash do menor recurso do componente (estável e sem nome real)."""
    parent: dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_addr: dict[tuple, set] = defaultdict(set)
    refs = []
    for r in records:
        node = (r["repo_id"], r["resource_address"])
        find(node)
        by_addr[(r["repo_id"], r["resource_address"])].add(resource_id(r))
        for t in _refs(r["term"]):
            refs.append((node, (r["repo_id"], t)))
    for a, b in refs:
        if b in by_addr:
            union(a, b)
    out = {}
    for node in parent:
        root = find(node)
        gid = "G-" + short_hash(canon(list(root)), 12)
        for rid in by_addr.get(node, ()):
            out[rid] = gid
    return out


def _refs(t) -> list[str]:
    out = []
    if isinstance(t, dict):
        if t.get("kind") == "reference" and t.get("target_address"):
            out.append(t["target_address"])
        for v in t.values():
            out.extend(_refs(v))
    elif isinstance(t, list):
        for v in t:
            out.extend(_refs(v))
    return out


# ------------------------------------------------------------------------------------------------- adaptadores
def trace_codes(traces) -> list[str]:
    """Traços C23 -> códigos (carried, omitted ou o block_code)."""
    out = []
    for t in traces:
        r = t["result"]
        if r == "blocked":
            out.append(t["block_code"])
        elif r in ("carried", "omitted"):
            out.append(r)
        else:
            raise UnitError(f"resultado C23 desconhecido: {r}")
    return out


def final_persistence(outcomes) -> dict[str, list[str]]:
    """Desfechos C12 -> por case_id, o último desfecho de cada lado (retentativas registradas: vale a última)."""
    last: dict[tuple, tuple] = {}
    for o in outcomes:
        if o["outcome"]["axis"] != "persistence":
            continue
        k = (o["case_id"], o["side"])
        key = (o["decided_at"], o["outcome_id"])
        if k not in last or key > last[k][0]:
            last[k] = (key, o["outcome"]["value"])
    out = defaultdict(list)
    for (case, _side), (_k, v) in sorted(last.items()):
        out[case].append(v)
    return dict(out)


PAIR_PROVIDERS = {"AWSGCP": ("aws", "google"), "AWSAZ": ("aws", "azurerm"), "AWSOCI": ("aws", "oci"),
                  "GCPAZ": ("google", "azurerm"), "GCPOCI": ("google", "oci"), "AZOCI": ("azurerm", "oci")}


def pair_direction(pair: str, direction: str) -> tuple[str, str]:
    """Par C00 + direção C11 (forward = primeiro -> segundo do nome do par) -> (origem, destino)."""
    a, b = PAIR_PROVIDERS[pair]
    if direction == "forward":
        return a, b
    if direction == "inverse":
        return b, a
    raise UnitError(f"direção {direction!r}")


def pair_of(a: str, b: str) -> str:
    for k, v in PAIR_PROVIDERS.items():
        if set(v) == {a, b}:
            return k
    raise UnitError(f"par {a},{b}")


def case_units(cases, outcomes, family_of_group=None, repo_of_group=None) -> list[Unit]:
    """Casos C11 de deploy (origin = sample) + desfechos C12 -> unidades de persistência (pesos do frame).

    Caso sorteado sem desfecho fica UNKNOWN (no intervalo), nunca sai do denominador."""
    fin = final_persistence(outcomes)
    out = []
    for c in cases:
        if c.get("origin") != "sample":
            continue
        st = c["stratum"]
        fam = family_of_group(c["group_id"]) if family_of_group else c["group_id"]
        repo = repo_of_group(c["group_id"]) if repo_of_group else c["group_id"]
        src, dst = pair_direction(st["pair"], st["direction"])
        out.append(Unit(c["case_id"], fam, repo, src, dst, resource_id=c["group_id"],
                        codes=tuple(fin.get(c["case_id"], ["UNKNOWN"])), weight=float(c.get("weight", 1.0)),
                        attrs=mk_attrs(stratum="|".join(st[k] for k in ("pair", "domain", "cardinality",
                                                                        "relation", "direction")))))
    return sorted(out, key=lambda u: u.unit_id)


def probe_units(judgements, cases, family_of_group=None, probe_type_of_case=None) -> list[Unit]:
    """Julgamentos C22 (PROBE-JOIN) + casos C11 -> pares de sonda por direção do caso (destino = lado
    implantado), com o peso do caso. Julgamento de caso fora do C11 é erro (o par precisa do frame)."""
    by_case = {c["case_id"]: c for c in cases}
    out = []
    for j in judgements:
        if j["outcome"]["axis"] != "behavior":
            continue
        c = by_case.get(j["case_id"])
        if c is None:
            raise UnitError(f"{j['pair_case_id']}: caso {j['case_id']} fora do C11")
        src, dst = pair_direction(c["stratum"]["pair"], c["stratum"]["direction"])
        fam = family_of_group(c["group_id"]) if family_of_group else c["group_id"]
        out.append(Unit(j["pair_case_id"], fam, c["group_id"], src, dst, resource_id=c["group_id"],
                        codes=(j["outcome"]["value"],), weight=float(c.get("weight", 1.0)),
                        attrs=mk_attrs(probe_type=probe_type_of_case(j["case_id"]) if probe_type_of_case
                                       else "unspecified")))
    return sorted(out, key=lambda u: u.unit_id)


# ------------------------------------------------------------------------------------------------- transporte
EVIDENCE_ORDER = ("UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED",
                  "OBSERVATION_TESTED")


def transport_code(rec: dict, quantifier: str) -> str:
    """Código de transporte de uma decisão (alegação C21 + relação + avaliação do predicado/guarda).

    rec: verdict (C21), evidence_state, relation (exact|close|broad|narrow|related), kind_unknown (bool),
    repair_excluded (bool), guard (TRUE|FALSE|INDETERMINATE|None), e por quantificador:
      existential  satisfiable: TRUE|FALSE|INDETERMINATE (predicado de pertença ou domínio da função)
      universal    valid: TRUE|FALSE|INDETERMINATE (predicado verdadeiro em todo o domínio; broad dispensa)
      observed     value_status: TRUE|FALSE|INDETERMINATE|SYMBOLIC (valor observado no uso)"""
    if rec.get("repair_excluded"):
        return "REPAIR_EXCLUDED"
    v = rec.get("verdict")
    if v != "OK":
        return v if v in ("REFUTED_BY_RULE", "UNPROVEN", "CONTESTED", "AMBIGUOUS") else "UNPROVEN"
    if rec.get("kind_unknown"):
        return "KIND_UNKNOWN"
    if EVIDENCE_ORDER.index(rec.get("evidence_state", "UNRESOLVED")) < EVIDENCE_ORDER.index("DOC_SUPPORTED"):
        return "EVIDENCE_BELOW_DOC_SUPPORTED"
    rel = rec.get("relation")
    if rel == "related":
        return "RELATED_ONLY"
    g = rec.get("guard")
    if g == "FALSE":
        return "CONDITION_FALSE"
    if quantifier == "existential":
        p = rec.get("satisfiable")
    elif quantifier == "universal":
        p = "TRUE" if rel == "broad" else rec.get("valid")
    elif quantifier == "observed_fraction":
        p = rec.get("value_status")
        if p == "SYMBOLIC":
            return "UNKNOWN_SYMBOLIC_INPUT"
    else:
        raise UnitError(f"quantificador {quantifier}")
    if p == "FALSE":
        return "PREDICATE_FALSE" if rel in ("broad", "narrow") else "FUNCTION_UNDEFINED"
    if p == "INDETERMINATE" or g == "INDETERMINATE":
        return "CONDITION_INDETERMINATE"
    if p == "TRUE":
        return "TRANSPORTS"
    raise UnitError(f"avaliação ausente para {quantifier}: {p!r}")


# ------------------------------------------------------------------------------------------------- unidade completa
def complete_unit_codes(rec: dict) -> list[str]:
    """Recurso de A -> códigos da unidade implantável completa em B.

    rec: plan (C26 lowering_plan ou None), trace_codes (códigos dos valores do recurso), required_missing
    (campos obrigatórios do destino sem valor nem síntese declarada), validate (ok|failed|INFRA_ERROR)."""
    codes = list(rec.get("trace_codes", []))
    plan = rec.get("plan")
    if plan is None:
        codes.append("NO_UNIT")
    elif not plan.get("dependency_closure", {}).get("closed", False):
        codes.append("DEPENDENCY_OPEN")
    if rec.get("required_missing"):
        codes.append("UNKNOWN_INPUT")   # obrigatório do destino sem valor: falha definida na unidade completa
    v = rec.get("validate")
    if v == "failed":
        codes.append("VALIDATE_FAILED")
    elif v == "INFRA_ERROR":
        codes.append("INFRA_ERROR")
    elif v != "ok":
        raise UnitError(f"validate {v!r}")
    if not any(c not in ("carried",) for c in codes):
        codes.append("COMPLETE")
    return codes
