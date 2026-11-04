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
OCI_SVC = {"objectstorage": "objectstorage", "core": "iaas"}  # serviço do nome do tipo oci_<serviço>_ -> spec


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
    if p == "oci":
        svc = OCI_SVC.get(suf.split("_", 1)[0])
        if not svc:
            return []
        keys = {suf.split("_", 1)[1] if "_" in suf else suf}
        keys |= {k + "s" for k in keys}
        if bridge and bridge.get("resource") not in (None, "UNKNOWN") and bridge.get("service") == svc:
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


def run(ctx, bridges: dict, disputes: list) -> None:
    p = ctx.p
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
        for T in ts:
            if not (len(prim) == 1 and T == prim[0]):
                shared.add(T)  # casamento não único: fica como candidato
        ctx.st["R-BRIDGE-SPEC_grupo"] += 1
    for T in sources.types(p):
        br = bridges.get(T)
        cands = cand_of[T]
        if not cands:
            continue
        if len(cands) > 1 or T in shared:
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
    proj = A.project(p, r["file"], ptr)
    kind = "owner" if role == "config" else "lifecycle_controller"
    return ctx.add(T, kind, f"specop:{r['file']}:{ptr}", {"service": r["service"], "resource": r["resource"]},
                   "stated", "published",
                   value={"aspect": "spec_operation", "rule": "R-SPEC-OP", "role": role,
                          "operation": proj.get("operation") or proj.get("id") or proj.get("operationId")
                          or proj["lines"][0]},
                   cit=A.cite(p, r["file"], ptr))
