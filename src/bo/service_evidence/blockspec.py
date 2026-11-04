"""CC-12: ponte de API no nível de BLOCO, pelo campo ou sub-recurso da spec que o bloco configura.

Para cada tipo com casamento único na spec (specfacts.BRIDGED) e cada bloco/coleção dele:
  google  bloco de recurso próprio -> campo do corpo do insert (Discovery schemas: versioning, encryption,
          lifecycle.rule, retentionPolicy); a configuração vai pelo patch/update do pai
  azure   bloco <x>_properties de recurso próprio -> sub-recurso <x>Services do pai (PUT sem DELETE, nome
          constante); sub-blocos dele -> campos do corpo desse PUT; demais blocos -> campos do corpo do pai
  aws     bloco de recurso próprio -> membro de lista do payload de uma faceta do pai (ex.: aws_s3_bucket
          .lifecycle_rule -> BucketLifecycleConfiguration.Rules); bloco de tipo-faceta -> membro do payload
          (ex.: aws_s3_bucket_acl.access_control_policy.grant -> AccessControlPolicy.Grants)
Fatos (todos DERIVADOS de fato PUBLICADO da spec, campo ou membro citado por ponteiro):
  api_bridge do bloco (R-BRIDGE-SPEC-BLOCK), dono, ciclo e alcance = pai na camada api (R-OWN-SPEC-BLOCK),
  identidade do item de lista pela spec (R-ID-SPEC: membro ID/id -> chave; sem -> ausente),
  spec_facet_member (R-FACET-SPEC) quando a API só aceita os blocos como membros de um objeto-faceta único do
  pai, gravado por UMA operação sobre o pai (sem create/delete próprios do bloco),
  twin_type de bloco (R-TWIN-SPEC) quando a forma embutida e a separada caem no mesmo membro da spec.
Sem casamento do campo: nada (o bloco segue com os fatos que já tinha).
"""

from __future__ import annotations

from . import apispec as A
from . import sources


def _top(p, T):
    return {path for path, depth, *_ in sources.atoms(p).get(T, []) if not depth and "." not in path}


def _block_attrs(p, T, bp):
    pre = bp + "."
    return {path[len(pre):] for path, *_ in sources.atoms(p).get(T, [])
            if path.startswith(pre) and "." not in path[len(pre):]}


def _blocks_of(ctx, T):
    """block_path de blocos e coleções do tipo (registros block_schema já emitidos)."""
    return sorted({r["block_path"] for r in ctx.recs if r["terraform_resource_type"] == T and r.get("block_path")
                   and (r.get("value") or {}).get("aspect") == "block_schema"})


def _field_rec(ctx, T, p, f, ptr, api):
    proj = A.project(p, f, ptr)
    return ctx.add(T, "identity", f"specfield:{f}:{ptr}", api, "stated", "published",
                   value={"aspect": "spec_field", "rule": "R-SPEC-OP",
                          "field": proj.get("field") or proj.get("member")},
                   cit=A.cite(p, f, ptr))


def _emit(ctx, T, bp, api_block, der, extra, scope_kind="parent"):
    p = ctx.p
    ctx.add(T, "api_bridge", f"specblock:{bp}", api_block, "stated", "derived",
            value={"aspect": "api_resource_bridge", "rule": "R-BRIDGE-SPEC-BLOCK", "block_path": bp,
                   "service": api_block["service"], "resource": api_block["resource"], **extra},
            derived=der)
    for kind in ("owner", "lifecycle_controller", "effective_scope"):
        ctx.add(T, kind, f"specblock:{bp}:{kind}", api_block, "stated", "derived",
                value={"kind": scope_kind, "rule": "R-OWN-SPEC-BLOCK", "layer": "api", "block_path": bp},
                derived=der)
    ctx.st["R-BRIDGE-SPEC-BLOCK"] += 1
    _ = p


def run(ctx, bridges_unused=None) -> None:
    p = ctx.p
    m = A.model(p)
    members = {}  # (svc, faceta, membro) -> [(tipo, bloco, embutido?)]
    upd_cache = {}
    for T, key in [x for x in __import__("bo.service_evidence.specfacts", fromlist=["BRIDGED"]).BRIDGED.get(p, [])]:
        r = m[key]
        f = r["file"]
        bps = _blocks_of(ctx, T)
        if not bps:
            continue
        if p in ("google", "azurerm") and r["create"]:
            upd = r.get("update")
            if upd and (T, upd) not in upd_cache:
                from .specfacts import _op
                upd_cache[(T, upd)] = _op(ctx, T, p, r, "update")
            uid = upd_cache.get((T, upd)) if upd else None
            for bp in bps:
                segs = bp.split(".")
                base_r, base_schema, path, rel = r, r.get("schema"), segs, None
                if p == "azurerm" and segs[0].endswith("_properties"):
                    child = m.get((r["service"], f"{r['resource']}/{segs[0][:-11]}Services"))
                    if not child or child.get("parent") != r["resource"]:
                        continue
                    base_r, base_schema, path = child, child.get("schema"), segs[1:]
                    if not path:  # o próprio bloco <x>_properties = sub-recurso faceta do pai
                        from .specfacts import _op
                        cid = _op(ctx, T, p, child, "config")
                        _emit(ctx, T, bp, {"service": child["service"], "resource": child["resource"]}, [cid],
                              {"spec_file": child["file"], "configured_by": "PUT do sub-recurso"})
                        continue
                ptrs = A.find_field(p, base_r["file"], base_schema, path) if path else None
                if not ptrs:
                    continue
                fids = [_field_rec(ctx, T, p, base_r["file"], x, {"service": base_r["service"],
                                                                     "resource": base_r["resource"]})
                        for x in ptrs]
                names = [A.unesc(x.split("/")[-1]) for x in ptrs]
                api_b = {"service": base_r["service"], "resource": f"{base_r['resource']}.{'.'.join(names)}"}
                op_id = uid if base_r is r else None
                if base_r is not r:
                    from .specfacts import _op
                    op_id = _op(ctx, T, p, base_r, "config")
                der = fids + ([op_id] if op_id else [])
                _emit(ctx, T, bp, api_b, der, {"spec_file": base_r["file"], "field": ".".join(names)})
                last = A.project(p, base_r["file"], ptrs[-1])
                if last.get("type") == "array":
                    item = A.field_children(p, base_r["file"], ptrs[-1])
                    battrs = _block_attrs(p, T, bp)
                    key = next((k for k in ("id", "name") if k in item and k in battrs), None)
                    if key is None and any(k in item for k in ("id", "name")):
                        key = "UNMAPPED"
                    _identity(ctx, T, bp, api_b, der, key)
                    if len(names) > 1 and op_id:
                        _facet_member(ctx, T, bp, api_b, der, facet=names[0],
                                      facet_resource=f"{base_r['service']}:{base_r['resource']}.{names[0]}",
                                      operation=A.project(p, base_r["file"], base_r.get("update") or
                                                          base_r["config"][0]), member=names[-1])
        elif p == "aws":
            facets = [(k, fr) for k, fr in m.items() if k[0] == r["service"] and fr.get("parent") ==
                      (r["resource"] if r["create"] else None)] if r["create"] else [(key, r)]
            for bp in bps:
                segs = bp.split(".")
                for fk, fr in facets:
                    req = (A.load_json(p, fr["file"])["shapes"][A.unesc(fr["config"][0][len("/shapes/"):])]
                           .get("input") or {}).get("target")
                    if not req:
                        continue
                    if r["create"]:  # embutido: <termos da faceta>_<membro>, ex.: lifecycle_rule
                        if len(segs) != 1 or "_" not in bp:
                            continue
                        head, last = bp.rsplit("_", 1)
                        if not set(head.split("_")) <= set(A.snake(fr["resource"]).split("_")):
                            continue
                        mp = None
                        for pl in fr.get("payload") or []:
                            mp = A.aws_member_path(fr["file"], req, [A.snake(pl), last])
                            if mp:
                                break
                    else:  # tipo-faceta: caminho do bloco a partir do request (ou do payload)
                        mp = A.aws_member_path(fr["file"], req, segs)
                        if not mp:
                            for pl in fr.get("payload") or []:
                                mp = A.aws_member_path(fr["file"], req, [A.snake(pl)] + segs)
                                if mp:
                                    break
                    if not mp:
                        continue
                    from .specfacts import _op
                    op = _op(ctx, T, p, fr, "config")
                    fids = [_field_rec(ctx, T, p, fr["file"], x, {"service": fr["service"],
                                                                  "resource": fr["resource"]}) for x, _t in mp]
                    mem_names = [A.unesc(x.split("/members/")[-1]) for x, _t in mp]
                    api_b = {"service": fr["service"], "resource": f"{fr['resource']}.{'.'.join(mem_names)}"}
                    _emit(ctx, T, bp, api_b, fids + [op], {"spec_file": fr["file"], "field": ".".join(mem_names)})
                    shapes = A.load_json(p, fr["file"])["shapes"]
                    if shapes.get(mp[-1][1], {}).get("type") == "list":
                        item = shapes.get(A.aws_item_shape(fr["file"], mp[-1][1]), {}).get("members") or {}
                        _identity(ctx, T, bp, api_b, fids + [op],
                                  "id" if ("ID" in item or "Id" in item) and "id" in _block_attrs(p, T, bp)
                                  else (None if not ("ID" in item or "Id" in item) else "UNMAPPED"))
                        if r["create"]:
                            _facet_member(ctx, T, bp, api_b, fids + [op], facet=fr["resource"],
                                          facet_resource=f"{fr['service']}:{fr['resource']}",
                                          operation=A.project(p, fr["file"], fr["config"][0]),
                                          member=mem_names[-1])
                        members.setdefault((fr["service"], fr["resource"], mem_names[-1]), []).append(
                            (T, bp, bool(r["create"]), fids[-1]))
                    break
    # gêmeo de bloco: a forma embutida e a separada caem no mesmo membro da spec
    for (svc, fac, mem), lst in members.items():
        emb = [x for x in lst if x[2]]
        sep = [x for x in lst if not x[2]]
        if len(sep) != 1:
            continue
        U, ubp, _e, ufid = sep[0]
        for T, bp, _e2, tfid in emb:
            ctx.add(T, "identity", f"twinblock:{bp}:{U}.{ubp}", {"service": svc, "resource": fac}, "stated",
                    "derived",
                    value={"aspect": "twin_type", "rule": "R-TWIN-SPEC", "block_path": bp, "twin": U,
                           "twin_block_path": ubp, "spec_member": f"{fac}.{mem}"},
                    derived=[tfid, ufid])
            ctx.st["R-TWIN-SPEC"] += 1


def _identity(ctx, T, bp, api_b, der, key):
    if key == "UNMAPPED":
        ctx.st["R-ID-SPEC_bloco_sem_atributo"] += 1
        return
    v = ({"status": "present", "scope": "within_parent", "key_fields": [key]} if key else {"status": "absent"})
    v.update({"rule": "R-ID-SPEC", "layer": "api", "block_path": bp})
    ctx.add(T, "identity", f"specblockid:{bp}", api_b, "stated", "derived", value=v, derived=der)
    ctx.st["R-ID-SPEC_bloco"] += 1


def _facet_member(ctx, T, bp, api_b, der, facet, facet_resource, operation, member):
    opname = operation.get("operation") or operation.get("id") or operation.get("operationId")
    ctx.add(T, "identity", f"specfacet:{bp}", api_b, "stated", "derived",
            value={"aspect": "spec_facet_member", "rule": "R-FACET-SPEC", "block_path": bp, "facet": facet,
                   "facet_resource": facet_resource, "operation": opname, "member": member,
                   "single_operation": True},
            derived=der)
    ctx.st["R-FACET-SPEC"] += 1
