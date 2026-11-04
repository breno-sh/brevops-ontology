"""CC-8: fatos de camada de API tirados da especificação do provedor (apispec.py), ligados aos tipos Terraform.

Por tipo com casamento ÚNICO (R-BRIDGE-SPEC) com um recurso da spec:
  publicados  as operações citadas (create/delete, ou a 1ª operação de configuração da faceta), com a
              citação da spec (arquivo, ponteiro, nome da operação)
  derivados   api_bridge (R-BRIDGE-SPEC); recurso com create/delete próprios: lifecycle_controller e owner
              {kind: self, layer: api} (R-LIFE-SPEC, R-OWN-SPEC); faceta: owner e lifecycle_controller
              {kind: parent, layer: api, via: atributo de referência ao pai} (R-OWN-SPEC, R-LIFE-SPEC-PARENT)
Mais de um casamento: um registro com os candidatos (aspect spec_bridge_candidates), sem fato de camada API.
Conflito com o que veio da doc (R-OWN-API, R-LIFE-API, ponte da doc com outro recurso) não é resolvido:
os dois ficam e o conflito vai para a lista de disputas (results/SERVICE-EVIDENCE/spec_disputes.json).
"""

from __future__ import annotations

from . import apispec as A
from . import sources

PREFIX = {"aws": ("s3_", "ec2_", "vpc_"), "google": (), "azurerm": (), "oci": ()}


def singular(s: str) -> str:
    if s.endswith("ies"):
        return s[:-3] + "y"
    if s.endswith("sses") or s.endswith("xes"):
        return s[:-2]
    return s[:-1] if s.endswith("s") else s


def names_of(p: str, key, r) -> set[str]:
    n = r["resource"]
    if p == "aws":
        out = {A.snake(n)}
        if r["parent"] and not n.startswith(r["parent"]):
            out.add(A.snake(r["parent"]) + "_" + A.snake(n))
        for pl in r.get("payload") or []:  # faceta pelo membro de payload da operação (ServerSideEncryptionConfiguration)
            out.add(A.snake(r["parent"]) + "_" + A.snake(pl))
        if {"Authorize", "Revoke"} <= set(r.get("verbs") or []):  # Authorize/Revoke criam e removem REGRAS
            out |= {x + "_rule" for x in list(out)}
        return out
    if p == "google":
        return {f"{r['service']}_{singular(A.snake(n))}"}
    if p == "oci":
        return {n, singular(n)}
    return set()


def candidates(p: str, T: str, bridge: dict | None, m: dict) -> list:
    if p == "azurerm":
        if bridge and bridge.get("resource") not in (None, "UNKNOWN"):
            k = (bridge["service"], bridge["resource"])
            return [k] if k in m else []
        return []
    suf = T.split("_", 1)[1]
    keys = {suf} | {suf[len(x):] for x in PREFIX[p] if suf.startswith(x)}
    if p == "aws":
        toks = suf.split("_")
        found = []
        # do nome mais específico para o menos: nome inteiro, depois sem o 1º termo, depois sem os 2 primeiros
        for level in (keys, {"_".join(toks[1:])} if len(toks) > 1 else set(),
                      {"_".join(toks[2:])} if len(toks) > 2 else set()):
            found = sorted(k for k, r in m.items() if level and names_of(p, k, r) & level)
            if found:
                break
        if len(found) <= 1:
            return found
        # desempate por serviço: pasta/sdkId/arnNamespace/endpointPrefix = 1º termo do tipo ou cabeça da subcategoria
        hints = {A.norm(toks[0])}
        sub = (sources.typesub(p)[0].get(T) or {}).get("subcategory")
        if sub:
            hints.add(A.norm(sub["value"].split(" (")[0]))
            hints.add(A.norm(sub["value"]))
        exact_dir = [k for k in found if A.norm(k[0]) in hints]  # 1º: pasta do serviço igual à dica
        if exact_dir:
            return exact_dir
        names = A.aws_service_names()
        same = [k for k in found if names.get(k[0], set()) & hints]  # 2º: sdkId/arnNamespace/endpointPrefix
        return same if same else found
    if p == "oci":
        tok = suf.split("_", 1)[0]
        mods = [sv for sv in A.SPEC["oci"]["versions"] if suf.startswith(sv + "_")]
        if mods:  # módulo com o nome inteiro no tipo (os_management_hub, data_safe): o mais longo
            svc = max(mods, key=len)
            rest = suf[len(svc) + 1:]
        else:
            svcs = {sv for sv in A.SPEC["oci"]["versions"] if sv.replace("_", "") == tok}
            if bridge and bridge.get("service"):
                svcs |= {sv for sv in A.SPEC["oci"]["versions"]
                         if sv.replace("_", "") == bridge["service"].replace("-", "").replace("_", "")}
            if len(svcs) != 1:
                return []
            svc = svcs.pop()
            rest = suf.split("_", 1)[1] if "_" in suf else suf
        keys = {rest}
        keys |= {k + "s" for k in keys}
        if bridge and bridge.get("resource") not in (None, "UNKNOWN"):
            keys.add(A.snake(bridge["resource"]))
        return sorted(k for k, r in m.items() if k[0] == svc and names_of(p, k, r) & keys)
    return sorted(k for k, r in m.items() if names_of(p, k, r) & keys)


def via_attr(p: str, T: str, r: dict) -> list:
    top = {path for path, depth, *_ in sources.atoms(p).get(T, []) if not depth and "." not in path}
    cands = []
    for lb in r.get("parent_labels") or []:
        cands += [A.snake(lb), A.snake(lb) + "_id", A.snake(lb) + "_name"]
    pp = r.get("parent_path") or ""
    if pp:
        last = pp.rstrip("/").split("/")[-1].strip("{}")
        sn = A.snake(last)
        cands += [sn, sn.replace("_name", ""), sn.replace("_id", "") + "_id"]
    if p == "azurerm" and r.get("parent"):
        par = r["parent"].split("/")[-1]
        cands += [singular(A.snake(par)) + "_id", singular(A.snake(par)) + "_name"]
    return sorted({c for c in cands if c in top})[:1]


COVERAGE: dict = {}
BRIDGED: dict = {}  # provedor -> [(tipo, chave da spec)] dos casamentos únicos, para o blockspec


def run(ctx, bridges: dict, disputes: list) -> None:
    p = ctx.p
    cov = COVERAGE[p] = {"types": 0, "bridged": [], "ambiguous": [], "no_candidate": []}
    BRIDGED[p] = []
    m = A.model(p)
    doc_api = {}
    for r in ctx.recs:
        v = r.get("value") or {}
        if r["status"] == "stated" and not r.get("block_path") and v.get("rule") in (
                "R-OWN-API", "R-LIFE-API", "R-OWN-API-SHARED", "R-LIFE-API-SHARED"):
            doc_api.setdefault(r["terraform_resource_type"], []).append(r)
    refs = {}
    for r in ctx.recs:
        v = r.get("value") or {}
        if r["status"] == "stated" and not r.get("block_path") and v.get("aspect") == "reference_target" \
                and v.get("resolved"):
            refs.setdefault(r["terraform_resource_type"], set()).add(v["resolved"])
    cand_of = {T: candidates(p, T, bridges.get(T), m) for T in sources.types(p)}
    if p == "aws":  # 3º desempate: serviço da maioria dos casamentos únicos da mesma subcategoria (>= 3)
        import collections as _c
        by_sub = _c.defaultdict(_c.Counter)
        subcat = {T: ((sources.typesub(p)[0].get(T) or {}).get("subcategory") or {}).get("value") for T in cand_of}
        for T, cs in cand_of.items():
            if len(cs) == 1 and subcat[T]:
                by_sub[subcat[T]][cs[0][0]] += 1
        for T, cs in cand_of.items():
            if len(cs) > 1 and subcat[T] and by_sub[subcat[T]]:
                svc, n = by_sub[subcat[T]].most_common(1)[0]
                pick = [c for c in cs if c[0] == svc]
                if n >= 3 and len(pick) == 1:
                    cand_of[T] = pick
                    ctx.st["R-BRIDGE-SPEC_por_subcategoria"] += 1
    by_key, shared = {}, set()
    for T, cs in cand_of.items():
        if len(cs) == 1:
            by_key.setdefault(cs[0], []).append(T)
    for key, ts in by_key.items():
        if len(ts) < 2:
            continue
        # desempate declarado: o único tipo do grupo que não referencia outro membro fica com a ponte
        # (ou que tem atributo REFERENCE de topo chamado <recurso da spec no singular>_id, como storage_account_id)
        idattr = singular(A.snake(key[1].split("/")[-1])) + "_id"
        prim = [T for T in ts if not (refs.get(T, set()) & (set(ts) - {T}))
                and idattr not in {a for a in sources.references(p).get(T, set()) if "." not in a}]
        if len(prim) != 1 and p == "aws":
            # 2º desempate (aws): o único tipo cujo nome inteiro (sem aws_ e sem s3_/ec2_/vpc_) é o nome do recurso
            def exact(T):
                suf = T.split("_", 1)[1]
                full = {suf} | {suf[len(x):] for x in PREFIX[p] if suf.startswith(x)}
                return bool(names_of(p, key, m[key]) & full)
            ex = [T for T in (prim or ts) if exact(T)]
            if len(ex) == 1:
                prim = ex
        for T in ts:
            if not (len(prim) == 1 and T == prim[0]):
                shared.add(T)  # casamento não único: fica como candidato
        ctx.st["R-BRIDGE-SPEC_grupo"] += 1
    for T in sources.types(p):
        br = bridges.get(T)
        cands = cand_of[T]
        cov["types"] += 1
        if not cands:
            cov["no_candidate"].append(T)
            continue
        if len(cands) > 1 or T in shared:
            cov["ambiguous"].append(T)
            ctx.add(T, "api_bridge", "spec_candidates", br or {"service": "UNKNOWN", "resource": "UNKNOWN"},
                    "stated", "derived",
                    value={"aspect": "spec_bridge_candidates", "rule": "R-BRIDGE-SPEC",
                           "candidates": sorted({f"{a}:{b}" for a, b in cands}),
                           "reason": "mais de um recurso da spec" if len(set(cands)) > 1 else
                           "o recurso da spec casa com mais de um tipo; o desempate não dá este tipo como o primário"},
                    derived=sorted({_op(ctx, T, p, m[c], "config" if m[c]["parent"] else "create")
                                    for c in set(cands)}))
            ctx.st["R-BRIDGE-SPEC_ambiguo"] += 1
            continue
        key = cands[0]
        r = m[key]
        cov["bridged"].append(T)
        BRIDGED.setdefault(p, []).append((T, key))
        f = r["file"]
        ver = A.SPEC[p]["versions"][r["service"]]
        api = {"service": r["service"], "resource": r["resource"]}
        if r["create"]:
            c_id = _op(ctx, T, p, r, "create")
            d_id = _op(ctx, T, p, r, "delete")
            ops = [c_id, d_id]
        else:
            ops = [_op(ctx, T, p, r, "config")]
        bid = ctx.add(T, "api_bridge", "spec_bridge", api, "stated", "derived",
                      value={"aspect": "api_resource_bridge", "rule": "R-BRIDGE-SPEC", "service": r["service"],
                             "resource": r["resource"], "spec_file": f, "api_version": ver},
                      derived=ops, api_version=ver)
        ctx.st["R-BRIDGE-SPEC"] += 1
        if br and br.get("resource") not in (None, "UNKNOWN"):
            a, b = singular(A.snake(br["resource"].split("/")[-1])), singular(A.snake(r["resource"].split("/")[-1]))
            if a != b:
                disputes.append({"provider": p, "terraform_resource_type": T, "fact": "api_bridge",
                                 "doc": br, "spec": api, "evidence": [bid]})
        if r["create"]:
            new = {"lifecycle_controller": ("self", "R-LIFE-SPEC"), "owner": ("self", "R-OWN-SPEC")}
            via = []
        else:
            new = {"lifecycle_controller": ("parent", "R-LIFE-SPEC-PARENT"), "owner": ("parent", "R-OWN-SPEC")}
            via = via_attr(p, T, r)
        if not r["create"]:
            new["effective_scope"] = ("parent", "R-SCOPE-SPEC")
            if p == "aws" and {"Authorize", "Revoke"} <= set(r.get("verbs") or []):
                _aws_rule_identity(ctx, T, r, api, ops, bid)
        else:
            _blocks(ctx, T, r, m, api, bid)
            if p == "oci" and r.get("path"):
                _oci_identity(ctx, T, r, api, ops, bid)
        for kind, (k, rule) in new.items():
            v = {"kind": k, "rule": rule, "layer": "api", "spec_resource": f"{r['service']}:{r['resource']}"}
            if k == "parent":
                v["parent_resource"] = r["parent"]
                v["via"] = via
            eid = ctx.add(T, kind, f"spec:{rule}", api, "stated", "derived", value=v, derived=ops + [bid])
            ctx.st[rule] += 1
            for d in doc_api.get(T, []):
                if d["fact_kind"] == kind and d["value"].get("kind") != k:
                    disputes.append({"provider": p, "terraform_resource_type": T, "fact": kind,
                                     "doc": {"kind": d["value"].get("kind"), "rule": d["value"].get("rule")},
                                     "spec": {"kind": k, "rule": rule}, "evidence": [d["evidence_id"], eid]})


def _op(ctx, T: str, p: str, r: dict, role: str) -> str:
    ptr = r[role] if role != "config" else r["config"][0]
    kind_role = role
    proj = A.project(p, r["file"], ptr)
    kind = "owner" if role in ("config", "update") else "lifecycle_controller"
    return ctx.add(T, kind, f"specop:{r['file']}:{ptr}", {"service": r["service"], "resource": r["resource"]},
                   "stated", "published",
                   value={"aspect": "spec_operation", "rule": "R-SPEC-OP", "role": role,
                          "operation": proj.get("operation") or proj.get("id") or proj.get("operationId")
                          or proj["lines"][0]},
                   cit=A.cite(p, r["file"], ptr))


def _oci_identity(ctx, T: str, r: dict, api: dict, ops: list, bid: str) -> None:
    """R-ID-SPEC (oci): os parâmetros do caminho do delete_<n> são a chave; o último é o próprio objeto (…Id ->
    atributo id; …Name -> name ou <coisa>), os outros só entram se houver atributo de topo com o mesmo nome."""
    p = ctx.p
    top = {path for path, depth, *_ in sources.atoms(p).get(T, []) if not depth and "." not in path}
    params = [x.strip("{}") for x in r["path"].split("/") if x.startswith("{")]
    if not params:
        return
    keys, unmapped = [], []
    for i, prm in enumerate(params):
        sn = A.snake(prm)
        base = sn[:-5] if sn.endswith("_name") else (sn[:-3] if sn.endswith("_id") else sn)
        last = i == len(params) - 1
        opts = (["id"] if sn.endswith("_id") else ["name", base]) if last else [base, sn, base + "_id"]
        hit = next((o for o in opts if o in top), None)
        (keys if hit else unmapped).append(hit or prm)
    if unmapped:
        ctx.st["R-ID-SPEC_sem_atributo"] += 1
        return
    refs = sources.references(p).get(T, set())
    scope = "within_parent" if any(k in refs for k in keys[:-1]) else "independent"
    ctx.add(T, "identity", "spec_identity", api, "stated", "derived",
            value={"status": "present", "scope": scope, "key_fields": keys, "rule": "R-ID-SPEC", "layer": "api",
                   "spec_path": r["path"]},
            derived=ops + [bid])
    ctx.st["R-ID-SPEC"] += 1


def _after(ctx) -> None:
    from . import blockspec
    blockspec.run(ctx)


def _camel(b: str) -> str:
    return "".join(x[:1].upper() + x[1:] for x in b.split("_"))


def _blocks(ctx, T: str, r: dict, m: dict, api: dict, bid: str) -> None:
    """Blocos/coleções de topo de um tipo cujo recurso tem create/delete próprios na spec.
    Há faceta <Recurso><Bloco> na spec (ex.: SecurityGroup + Ingress): o bloco é essa faceta (ponte, dono, ciclo e
    alcance = pai, R-OWN-SPEC / R-LIFE-SPEC-PARENT / R-SCOPE-SPEC). Não há, mas o recurso tem operação de update
    própria: o bloco é configurado por ela (R-OWN-SPEC-BLOCK, dono/ciclo/alcance = pai, camada api)."""
    from .grainfacts import _collections
    p = ctx.p
    for B in sorted(_collections(p, T)):
        fk = (r["service"], r["resource"] + _camel(B)) if p == "aws" else None
        fr = m.get(fk) if fk else None
        if fr and fr.get("parent") == r["resource"]:
            op = _op(ctx, T, p, fr, "config")
            ctx.add(T, "api_bridge", f"spec_block:{B}", {"service": fr["service"], "resource": fr["resource"]},
                    "stated", "derived",
                    value={"aspect": "api_resource_bridge", "rule": "R-BRIDGE-SPEC", "block_path": B,
                           "service": fr["service"], "resource": fr["resource"], "spec_file": fr["file"]},
                    derived=[op, bid])
            rules_ = (("owner", "R-OWN-SPEC"), ("lifecycle_controller", "R-LIFE-SPEC-PARENT"),
                      ("effective_scope", "R-SCOPE-SPEC"))
            der, extra = [op, bid], {"spec_resource": f"{fr['service']}:{fr['resource']}"}
            ctx.st["R-OWN-SPEC_bloco_faceta"] += 1
        elif r.get("update"):
            op = _op(ctx, T, p, r, "update")
            rules_ = (("owner", "R-OWN-SPEC-BLOCK"), ("lifecycle_controller", "R-OWN-SPEC-BLOCK"),
                      ("effective_scope", "R-OWN-SPEC-BLOCK"))
            der, extra = [op, bid], {"configured_by": "update do pai"}
            ctx.st["R-OWN-SPEC-BLOCK"] += 1
        else:
            continue
        for kind, rule in rules_:
            ctx.add(T, kind, f"spec_block:{B}:{rule}", api, "stated", "derived",
                    value={"kind": "parent", "rule": rule, "layer": "api", "block_path": B, **extra},
                    derived=der)


def _aws_rule_identity(ctx, T: str, r: dict, api: dict, ops: list, bid: str) -> None:
    """Regra criada por Authorize e removida por Revoke: a spec dá a ela identidade própria se a estrutura
    <Pai>Rule tem membro <Pai>RuleId (ex.: SecurityGroupRule.SecurityGroupRuleId, o sgr-). Atributo Terraform
    de mesmo nome em snake_case é a chave (R-ID-SPEC)."""
    p = ctx.p
    sh = f"com.amazonaws.{r['service']}#{r['parent']}Rule"
    shapes = A.load_json(p, r["file"])["shapes"]
    mem = f"{r['parent']}RuleId"
    if mem not in (shapes.get(sh, {}).get("members") or {}):
        return
    top = {path for path, depth, *_ in sources.atoms(p).get(T, []) if not depth and "." not in path}
    attr = A.snake(mem)
    if attr not in top:
        return
    ptr = f"/shapes/{A.esc(sh)}/members/{A.esc(mem)}"
    mid = ctx.add(T, "identity", f"specmember:{r['file']}:{ptr}", api, "stated", "published",
                  value={"aspect": "spec_member", "rule": "R-SPEC-OP", "shape": sh.split("#")[1], "member": mem},
                  cit=A.cite(p, r["file"], ptr))
    ctx.add(T, "identity", "spec_identity", api, "stated", "derived",
            value={"status": "present", "scope": "independent", "key_fields": [attr], "rule": "R-ID-SPEC",
                   "layer": "api", "spec_member": f"{sh.split('#')[1]}.{mem}"},
            derived=ops + [bid, mid])
    ctx.st["R-ID-SPEC"] += 1
