"""Adaptador C25 por aspecto: tradução normativa dos fatos do SERVICE-EVIDENCE (value.aspect) em alegações.

O SERVICE-EVIDENCE grava os fatos de grão por aspecto (identity/resource_identity_schema, import_key/
import_formats, owner/identity_scope, lifecycle_controller/destroy_effect, ...). Esta tabela diz, aspecto a
aspecto, que alegação neutra cada fato vira. É normativa (o GRAIN-REPRO a segue; ela está em GRAIN.html,
gerada de TABLE abaixo). Princípios:
  * nada é inventado: aspecto sem tradução vira alegação UNKNOWN com o motivo, e fato com status unknown
    vira alegação UNKNOWN com o unknown_reason;
  * dono da IDENTIDADE (owner/identity_scope, owner/parent, owner/parent_attribute) não é dono da
    CONFIGURAÇÃO: esses aspectos só alimentam o escopo da identidade, nunca o campo owner;
  * destroy_effect "suspend" num recurso separado é indício de faceta do pai (ciclo de vida = pai, ligação com
    a API = aspecto); "not_deleted" e "state_only" dizem que o destroy não apaga, não quem apaga;
  * bloco aninhado só tem alegações se o SERVICE-EVIDENCE emitiu fato com block_path; sem elas, UNKNOWN (G0),
    nunca FACET por omissão;
  * nenhuma heurística de nome (block_schema.facet_word não é lido).
A fonte de cada alegação é {level: derived, ref: evidence_id, note: "<regra>: <aspecto>"}.
"""

from __future__ import annotations

from collections import defaultdict

GRAIN_FACTS = ("identity", "import_key", "lifecycle_controller", "owner", "effective_scope", "api_bridge")

# campos de identidade que nomeiam o escopo do provedor (conta, região, projeto, assinatura): não são unidades
PROVIDER_SCOPE_FIELDS = {
    "aws": {"account_id", "region"},
    "google": {"project", "project_id"},
    "azurerm": {"subscription_id"},
    "oci": set(),
}
# escopos de contenção que são do provedor (não há unidade Terraform para eles na decomposição)
PROVIDER_SCOPE_KINDS = {"account", "region", "project", "organization", "folder", "subscription", "tenancy",
                        "billing_account", "extension_scope"}

# aspecto -> (campo de alegação, regra, tradução em uma linha). Normativo; renderizado no GRAIN.html.
TABLE = [
    ("identity", "resource_identity_schema", "R-GRAIN-T01",
     "identity present; key_fields = required menos os campos de escopo do provedor; escopo within_parent se "
     "algum campo da chave é referência (T02, T21), senão independent; optional não entra"),
    ("identity", "shared_identity_key", "R-GRAIN-T02",
     "os campos são referência ao objeto compartilhado: alvo = o único par (peers ou o próprio) cujo ciclo de "
     "vida consolidado é self; se é o próprio, os campos são chave própria; nenhum ou mais de um: alvo não "
     "resolvido"),
    ("identity", "id_template", "R-GRAIN-T03",
     "sem tradução: formato do id Terraform, pode incluir atributos opcionais; não é chave natural"),
    ("identity", "api_resource_bridge", "R-GRAIN-T04",
     "api_resource {status: resource, label/resource/service da ponte}; resource UNKNOWN vira UNKNOWN"),
    ("api_bridge", "(qualquer, C25 1.1.0)", "R-GRAIN-T04",
     "como api_resource_bridge: api_resource {status: resource} com value.resource/service ou, sem eles, os do "
     "registro; UNKNOWN vira UNKNOWN"),
    ("identity", "api_reference", "R-GRAIN-T05", "sem tradução: página de referência da API, informativa"),
    ("identity", "cardinality", "R-GRAIN-T06",
     "sem tradução: singular por escopo do provedor; o escopo não é unidade da decomposição"),
    ("identity", "block_identity", "R-GRAIN-T07",
     "schema_identity present com key_fields: identity present within_parent e element_name_key = key_fields; "
     "absent sem element_name_candidates: identity absent; absent com candidatos: UNKNOWN (candidatos não "
     "confirmados)"),
    ("identity", "block_schema", "R-GRAIN-T08", "sem tradução: estrutura do bloco (facet_word não é lido)"),
    ("import_key", "import_formats", "R-GRAIN-T10",
     "supported false: import_key absent; identity.required presente: import_key present com required menos os "
     "campos de escopo do provedor; só placeholders, values ou id_format: UNKNOWN (sem atributos nomeados)"),
    ("owner", "identity_scope", "R-GRAIN-T20",
     "sem tradução para owner: diz quem é dono da IDENTIDADE (conta, região), não da configuração; marca "
     "account_id/region como campos de escopo do provedor para T01"),
    ("owner", "parent", "R-GRAIN-T21",
     "sem tradução para owner (contenção da identidade); se o scope_kind é unidade (não escopo do provedor) e "
     "a identidade não tem atributo de referência ao pai, a chave ganha uma referência não resolvida "
     "($container): a identidade fica UNRESOLVED"),
    ("owner", "parent_attribute", "R-GRAIN-T22",
     "sem tradução para owner (atributo de contenção, não dono da configuração)"),
    ("owner", "block_config_owner", "R-GRAIN-T23",
     "owner {kind: parent, via: $parent} quando via é o pai estrutural do bloco; senão UNKNOWN"),
    ("lifecycle_controller", "destroy_effect", "R-GRAIN-T30",
     "suspend: lifecycle_controller {kind: parent} e api_resource {status: aspect} (indício de faceta do pai); "
     "not_deleted e state_only: UNKNOWN (o destroy não apaga; não diz quem apaga)"),
    ("lifecycle_controller", "deletion_policy", "R-GRAIN-T31",
     "values com DELETE: lifecycle_controller {kind: self}; values vazio: UNKNOWN (política sem valores "
     "documentados)"),
    ("lifecycle_controller", "block_lifecycle", "R-GRAIN-T32",
     "lifecycle_controller {kind: parent, via: $parent} quando via é o pai estrutural do bloco; senão UNKNOWN"),
    ("effective_scope", "type_scope", "R-GRAIN-T40",
     "scope de escopo do provedor (account, project, organization, ...): {kind: global}; outro scope: {kind: "
     "parent, via: o campo de referência da chave} se a chave tem uma referência, senão {kind: self}"),
    ("effective_scope", "attribute_scope", "R-GRAIN-T41",
     "sem tradução: escopo de UM atributo, não da unidade"),
    ("effective_scope", "effective_public_access", "R-GRAIN-T42",
     "sem tradução: avaliação de acesso efetivo (oráculo do piloto), não grão"),
    ("effective_scope", "effective_public_access_prevention", "R-GRAIN-T42",
     "sem tradução: avaliação de acesso efetivo (oráculo do piloto), não grão"),
    ("(qualquer)", "(sem aspect)", "R-GRAIN-T99",
     "fato afirmado sem value.aspect: alegação direta na convenção anterior (identity/import_key como objeto; "
     "lifecycle_controller/owner/effective_scope como string do kind ou {kind, via}); é a porta para o "
     "SERVICE-EVIDENCE emitir fatos derivados de grão já traduzidos"),
    ("(qualquer)", "(status unknown)", "R-GRAIN-UNK", "alegação UNKNOWN com o unknown_reason; contradictory vira "
     "CONTRADICTORY"),
    ("(qualquer)", "(aspecto fora da tabela)", "R-GRAIN-UNK", "alegação UNKNOWN com o motivo 'sem tradução'"),
]
RULE_OF = {(f, a): r for f, a, r, _ in TABLE}


def is_aspect_record(r: dict) -> bool:
    v = r.get("value")
    if r.get("fact_kind") not in GRAIN_FACTS:
        return False
    return r.get("fact_kind") == "api_bridge" or bool(r.get("block_path")) or (isinstance(v, dict) and "aspect" in v)


def _src(r: dict, rule: str, why: str = "") -> dict:
    v = r.get("value") if isinstance(r.get("value"), dict) else {}
    note = f"{rule}: {r['fact_kind']}/{v.get('aspect', 'sem aspecto')}"
    if why:
        note += f" ({why})"
    return {"level": "derived", "ref": r["evidence_id"], "note": note}


def translate(records: list[dict], candidates: set[str] | None = None) -> tuple[dict, dict]:
    """records: C25 de UM provedor (todos os tipos, para os pares de T02). candidates: ids de candidato da
    decomposição (alvos de referência só valem se existem). Devolve ({cid: evidência-dict}, {cid: [motivos]})."""
    by_cid: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("fact_kind") not in GRAIN_FACTS or not r.get("terraform_resource_type"):
            continue
        v = r.get("value")
        # C25 1.1.0: block_path no registro; antes, em value.block_path (as duas formas são lidas)
        bp = r.get("block_path") or (v.get("block_path") if isinstance(v, dict) else None)
        by_cid[r["terraform_resource_type"] + ("." + bp if bp else "")].append(r)
    out: dict[str, dict] = {}
    reasons: dict[str, list] = defaultdict(list)
    provider = next((r["provider"] for r in records), "")
    scope_fields = set(PROVIDER_SCOPE_FIELDS.get(provider, set()))

    def put(cid, fld, claim):
        out.setdefault(cid, {}).setdefault(fld, []).append(claim)

    def unknown(cid, fld, r, why):
        reasons[cid].append(f"{fld}: {why}")
        put(cid, fld, {"status": "unknown", "source": _src(r, RULE_OF.get((r["fact_kind"], (r.get("value") if isinstance(
            r.get("value"), dict) else {}).get("aspect")), "R-GRAIN-UNK"), why)})

    # 1ª passada: tudo que não depende de outro candidato
    pending_ids, shared, containers, scopes = {}, {}, {}, {}
    for cid, rs in sorted(by_cid.items()):
        nested = "." in cid
        parent_cid = cid.rsplit(".", 1)[0] if nested else None
        loc_scope = set(scope_fields)
        for r in rs:
            v = r.get("value") if isinstance(r.get("value"), dict) else {}
            if v.get("aspect") == "identity_scope":
                if v.get("account"):
                    loc_scope.add("account_id")
                if v.get("region"):
                    loc_scope.add("region")
        for r in rs:
            fld, v = r["fact_kind"], r.get("value")
            if r.get("status") == "unknown":
                st = "contradictory" if r.get("unknown_reason") == "contradictory" else "unknown"
                reasons[cid].append(f"{fld}: {r.get('unknown_reason')}")
                put(cid, fld, {"status": st, "source": _src(r, "R-GRAIN-UNK", r.get("unknown_reason") or "")})
                continue
            if fld == "api_bridge":
                # C25 1.1.0: fato próprio da ponte API ↔ tipo (T04b), mesma tradução de api_resource_bridge
                res_ = (v or {}).get("resource") if isinstance(v, dict) else None
                res_ = res_ or (r.get("api_resource") or {}).get("resource")
                if res_ in (None, "", "UNKNOWN"):
                    unknown(cid, "api_resource", r, "ponte sem recurso de API")
                else:
                    svc = (v.get("service") if isinstance(v, dict) else None) or (r.get("api_resource") or {}).get(
                        "service") or "UNKNOWN"
                    put(cid, "api_resource", {"status": "resource", "label": res_, "service": svc, "resource": res_,
                                              "source": _src(r, "R-GRAIN-T04")})
                continue
            if not isinstance(v, dict) or "aspect" not in v:
                # fato sem aspecto: alegação direta na convenção anterior (T99)
                claim = {"kind": v} if isinstance(v, str) else {k: x for k, x in (v or {}).items()
                                                                 if k not in ("block_path", "references",
                                                                              "field_map", "parent_role")}
                if isinstance(v, dict):
                    ent = out.setdefault(cid, {})
                    ent.setdefault("references", {}).update(v.get("references") or {})
                    ent.setdefault("field_map", {}).update(v.get("field_map") or {})
                    if v.get("parent_role"):
                        ent["parent_role"] = v["parent_role"]
                claim["source"] = _src(r, "R-GRAIN-T99", "alegação direta")
                put(cid, fld, claim)
                continue
            a = v["aspect"]
            rule = RULE_OF.get((fld, a))
            if rule is None:
                unknown(cid, fld, r, f"aspecto {a} sem tradução na tabela")
            elif a == "resource_identity_schema":
                key = [f for f in v.get("required", []) if f not in loc_scope]
                pending_ids[cid] = (r, key)
            elif a == "shared_identity_key":
                shared[cid] = (r, [f for f in v.get("fields", []) if f not in loc_scope], list(v.get("peers", [])))
            elif a == "api_resource_bridge":
                if v.get("resource") in (None, "", "UNKNOWN"):
                    unknown(cid, "api_resource", r, "ponte sem recurso de API")
                else:
                    put(cid, "api_resource", {"status": "resource", "label": v["resource"], "service": v.get("service")
                                              or "UNKNOWN", "resource": v["resource"], "source": _src(r, rule)})
            elif a == "block_identity":
                si, kf, cands = v.get("schema_identity"), list(v.get("key_fields") or []), v.get("element_name_candidates")
                if si == "present" and kf:
                    put(cid, "identity", {"status": "present", "scope": "within_parent", "key_fields": kf,
                                          "source": _src(r, rule)})
                    put(cid, "element_name_key", {"status": "present", "fields": kf, "source": _src(r, rule)})
                elif si == "absent" and not cands:
                    put(cid, "identity", {"status": "absent", "source": _src(r, rule)})
                else:
                    unknown(cid, "identity", r, "candidatos a nome não confirmados")
            elif a == "import_formats":
                if v.get("supported") is False:
                    put(cid, "import_key", {"status": "absent", "source": _src(r, rule)})
                elif isinstance(v.get("identity"), dict) and v["identity"].get("required") is not None:
                    pending_ids.setdefault(cid + "#import", (r, [f for f in v["identity"]["required"]
                                                                 if f not in loc_scope]))
                else:
                    unknown(cid, "import_key", r, "formato de importação sem atributos nomeados")
            elif a == "parent":
                sk, types = v.get("scope_kind"), v.get("parent_terraform_types") or []
                if sk not in PROVIDER_SCOPE_KINDS:
                    containers[cid] = (r, types)
                reasons[cid].append("owner: owner/parent é contenção da identidade, não dono da configuração")
                put(cid, "owner", {"status": "unknown", "source": _src(r, rule, "contenção da identidade")})
            elif a in ("block_config_owner", "block_lifecycle"):
                tgt = "owner" if a == "block_config_owner" else "lifecycle_controller"
                if nested and v.get("via") == parent_cid and v.get("kind") == "parent":
                    put(cid, tgt, {"kind": "parent", "via": "$parent", "source": _src(r, rule)})
                else:
                    unknown(cid, tgt, r, "via não é o pai estrutural")
            elif a == "destroy_effect":
                eff = v.get("effect")
                if eff == "suspend":
                    put(cid, "lifecycle_controller", {"kind": "parent", "source": _src(r, rule, "suspend")})
                    put(cid, "api_resource", {"status": "aspect", "label": None, "source": _src(r, rule, "suspend")})
                else:
                    unknown(cid, "lifecycle_controller", r, f"destroy_effect {eff}: não diz quem apaga")
            elif a == "deletion_policy":
                vals = [str(x).upper() for x in v.get("values") or []]
                if "DELETE" in vals:
                    put(cid, "lifecycle_controller", {"kind": "self", "source": _src(r, rule)})
                else:
                    unknown(cid, "lifecycle_controller", r, "política de remoção sem valores documentados")
            elif a == "type_scope":
                scopes[cid] = (r, v.get("scope"))
            else:
                unknown(cid, fld, r, f"aspecto {a}: sem tradução ({rule})")

    # ciclo de vida consolidado por candidato (para achar a raiz dos pares de T02)
    from .evidence import consolidate

    def lc_self(cid):
        f = consolidate("lifecycle_controller", out.get(cid, {}).get("lifecycle_controller", []))
        return f.known and f.value["kind"] == "self"

    refs_of: dict[str, dict] = defaultdict(dict)   # cid -> {campo: alvo ou None}
    for cid, (r, fields, peers) in sorted(shared.items()):
        roots = [p for p in sorted(set(peers) | {cid}) if lc_self(p)]
        if roots == [cid]:
            continue                                   # é a raiz: a chave é própria
        tgt = roots[0] if len(roots) == 1 else None
        if tgt is not None and candidates is not None and tgt not in candidates:
            tgt = None
        for f in fields:
            refs_of[cid][f] = tgt
        if tgt is None:
            reasons[cid].append(f"identity: chave compartilhada {fields} sem raiz única com ciclo de vida self "
                                f"entre os pares ({len(roots)} raiz(es))")
    for cid, (r, types) in sorted(containers.items()):
        refs_of[cid]["$container"] = None
        reasons[cid].append(f"identity: contido em {r['value'].get('scope_kind')} ({types or 'sem tipo Terraform'}) "
                            "sem atributo de referência ao contêiner na identidade")
    # 2ª passada: identidade e chave de importação com as referências
    for key, (r, fields) in sorted(pending_ids.items()):
        cid = key.split("#")[0]
        rfs = refs_of.get(cid, {})
        kf = list(fields) + ([f for f in rfs if f not in fields])
        if key.endswith("#import"):
            put(cid, "import_key", {"status": "present", "fields": kf, "source": _src(r, RULE_OF[("import_key",
                                                                                                   "import_formats")])})
        else:
            put(cid, "identity", {"status": "present", "scope": "within_parent" if rfs else "independent",
                                  "key_fields": kf, "source": _src(r, RULE_OF[("identity", "resource_identity_schema")])})
    for cid, rfs in refs_of.items():
        ent = out.setdefault(cid, {})
        fm = ent.setdefault("field_map", {})
        for f, t in rfs.items():
            fm[f] = {"path": f, "ref": True}
            if t is not None:
                ent.setdefault("references", {})[f] = t
    for cid, (r, scope) in sorted(scopes.items()):
        rule = RULE_OF[("effective_scope", "type_scope")]
        if scope in PROVIDER_SCOPE_KINDS:
            put(cid, "effective_scope", {"kind": "global", "source": _src(r, rule)})
        else:
            rf = [f for f in refs_of.get(cid, {}) if not f.startswith("$")]
            put(cid, "effective_scope", {"kind": "parent", "via": rf[0], "source": _src(r, rule)} if len(rf) == 1
                else {"kind": "self", "source": _src(r, rule)})
    # campos citados nas chaves sem mapa: nome canônico = caminho
    for cid, ent in out.items():
        fm = ent.setdefault("field_map", {})
        for fld in ("identity", "import_key", "element_name_key"):
            for cl in ent.get(fld, []):
                for f in list(cl.get("key_fields", []) or []) + list(cl.get("fields", []) or []):
                    fm.setdefault(f, {"path": f, "norm": "str"})
    return out, dict(reasons)
