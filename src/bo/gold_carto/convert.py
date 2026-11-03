"""OntologyFieldMapping -> alegações C09 3.0.0.

Duas famílias de linha, separadas por basis e mapping_justification:

  PUBLICADA (basis=direct, semapv:ManualMappingCuration): campo de nó do provedor -> campo da ontologia do
  Cartography, exatamente como o arquivo de mapeamento declara. A relação sai de uma regra fixa por
  special_handling (RULES abaixo, escrita antes de olhar os números), nunca de juízo caso a caso.

  DERIVADA (basis=shared_concept, semapv:MappingChaining): dois campos de provedores diferentes que o Cartography
  manda para o MESMO campo da ontologia. É o hub átomo -> conceito <- átomo do SEMANTICS (K-HUB): a relação sai de
  bo.semantics.composition.compose(âncora_a, inversa(âncora_b)) pela tabela formal. Como as âncoras não têm prova
  (sem testes, sem DOC_SUPPORTED), a composição verdadeira (hub_claim) dá UNPROVEN; para escrever a relação
  derivada, a composição roda com K-LEGS e K-DOMAIN desligados e o resultado verdadeiro do hub vai junto na linha
  (other.hub_outcome). Onde a tabela não dá relação (ex. close∘close), a linha derivada é relatedMatch, sem
  função e sem transporte. Estado de evidência da derivada = o menor das pernas.

Toda linha é hipótese de alinhamento até o GOLD-AUDIT: o estado de evidência máximo aqui é STRUCTURALLY_VALID
(campo resolvido no registro de campos de API do próprio Cartography); campo não resolvido = UNRESOLVED.
"""

from __future__ import annotations

import hashlib
import json
import re

from bo.semantics import composition as K
from bo.semantics.claims import Claim, invert
from bo.semantics.vocab import EVIDENCE_STATES, SKOS_PREDICATE

from . import LICENSE_URI, PROVIDERS, SOURCE_COMMIT, SOURCE_COMMIT_DATE, SOURCE_REPO, SOURCE_TAG

NS = f"https://w3id.org/brevops/gold/cartography/{SOURCE_COMMIT}/"
PREFIXES = {f"carto_{p}": f"{NS}node/{p}/" for p in PROVIDERS} | {"carto_ont": f"{NS}ontology/"}
MAPPING_SET_ID = f"{NS}mapping-set/cartography.sssom.tsv"
UNGLOSSED = "bo:UNGLOSSED"
VDR_UNKNOWN = {"relation": "unknown", "orientation": "subject_to_object"}
DISABLED_FOR_DERIVATION = frozenset({"K-LEGS", "K-DOMAIN"})

# Regra fixa special_handling -> (relação, fidelidade). Escrita a partir de specs.py (semântica declarada de
# cada special_handling), não dos dados. 'mapping' sempre declara a perda de ausência (valor fora do mapa vira
# NULL, specs.py) e, se a tabela não é injetiva, a perda semântica (valores distintos colapsam).
RULES = {
    None: ("exact", "lossless", "cópia do valor (sem tratamento)"),
    "mapping": ("close", "declared_loss", "enum_map com a tabela publicada; fora da tabela vira NULL"),
    "invert_boolean": ("exact", "lossless", "negação booleana como enum_map {true:false, false:true}"),
    "to_boolean": ("close", "declared_loss", "só a presença de valor passa (não nulo -> true); sem função no núcleo"),
    "equal_boolean": ("close", "declared_loss", "só a igualdade ao valor de extra.value passa; sem função no núcleo"),
    "or_boolean": ("related", "none", "OU de vários campos: combinação N:1 sem função no núcleo"),
    "nor_boolean": ("related", "none", "NOU de vários campos: combinação N:1 sem função no núcleo"),
    "coalesce": ("exact", "lossless", "primeiro não nulo: cada campo realiza sob a guarda de ausência dos anteriores"),
    "normalize_hostname": ("exact", "lossless", "minúsculas, sem espaço e sem ponto final; sem função no núcleo"),
    "static_value": ("related", "none", "valor fixo para todo nó do rótulo (fixed_default); não há campo de origem"),
}


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", s) or "_"


def node_curie(module: str, label: str, fld: str | None) -> str:
    return f"carto_{module}:{_safe(label)}" + (f".{_safe(fld)}" if fld else "")


def ont_curie(label: str, fld: str) -> str:
    return f"carto_ont:{_safe(label)}.{_safe(fld)}"


def source_ref(rel: str, line: int) -> str:
    return f"{SOURCE_REPO}/blob/{SOURCE_COMMIT}/{rel}#L{line}"


def _sentence(fm: dict) -> str:
    parts = [f"ontology_field={fm['ontology_field']!r}", f"node_field={fm['node_field']!r}"]
    if fm["required"]:
        parts.append("required=True")
    if fm["special_handling"]:
        parts.append(f"special_handling={fm['special_handling']!r}")
    if fm["via"]:
        parts.append(f"via {fm['via']}()")
    return f"{fm['node_label']} (módulo {fm['module']}): OntologyFieldMapping(" + ", ".join(parts) + ")"


def _ev_state(resolutions: list[dict]) -> str:
    return "STRUCTURALLY_VALID" if resolutions and all(r["status"] == "API_FIELD" for r in resolutions) \
        else "UNRESOLVED"


def published(fm: dict, resolve) -> list[dict]:
    """Linhas publicadas de um OntologyFieldMapping (várias só para coalesce/or/nor, uma por campo)."""
    sh = fm["special_handling"]
    if sh not in RULES:
        raise ValueError(f"special_handling desconhecido: {sh!r} em {fm['file']}:{fm['line']}")
    rel, fid, why = RULES[sh]
    extra = fm["extra"] or {}
    base_id = "-".join(["CARTO-PUB", fm["module"], _safe(fm["mapping_key"]), _safe(fm["node_label"]),
                        _safe(fm["node_field"] or "_label"), fm["category"], _safe(fm["ontology_field"])])
    obj = ont_curie(fm["ontology_label"], fm["ontology_field"])
    evidence = [{"source": source_ref(fm["file"], fm["line"]), "date": SOURCE_COMMIT_DATE,
                 "sentence": _sentence(fm)}]
    if sh in ("coalesce", "or_boolean", "nor_boolean"):
        fields = [fm["node_field"]] + [f for f in extra.get("fields", []) if f != fm["node_field"]]
    elif sh == "static_value":
        fields = [None]
    else:
        fields = [fm["node_field"]]
    out = []
    for k, fld in enumerate(fields):
        cid = base_id if len(fields) == 1 else f"{base_id}-f{k + 1}"
        res = [resolve(fm["node_label"], fld)]
        guard = {"all": []}
        loss: list[dict] = []
        fn = None
        rec = {}
        if sh in (None, "coalesce"):
            fn = {"name": "identity", "params": {}}
        if sh == "coalesce" and k > 0:
            guard = {"all": [{"term": f"subject.{_safe(p)}", "op": "present", "value": False} for p in fields[:k]]}
            res += [resolve(fm["node_label"], p) for p in fields[:k]]
        if sh == "mapping":
            table = {str(a): b for a, b in sorted((extra.get("map") or {}).items())}
            fn = {"name": "enum_map", "params": {"table": table}}
            loss.append({"kind": "absence", "detail": "valor do provedor fora da tabela vira NULL (specs.py)"})
            if len(set(json.dumps(v) for v in table.values())) < len(table):
                loss.append({"kind": "semantic", "detail": f"{len(table)} valores do provedor colapsam em "
                             f"{len(set(json.dumps(v) for v in table.values()))} valores canônicos"})
        if sh == "invert_boolean":
            fn = {"name": "enum_map", "params": {"table": {"true": False, "false": True}}}
        if sh == "to_boolean":
            loss.append({"kind": "semantic", "detail": "só a presença de valor passa (não nulo -> true)"})
        if sh == "equal_boolean":
            loss.append({"kind": "semantic", "detail": f"só a igualdade a {extra.get('value')!r} passa"})
        if sh == "normalize_hostname" and extra.get("record_types"):
            tf = extra.get("record_type_field", "type")
            term = f"subject.{_safe(tf)}"
            guard = {"all": [{"term": term, "op": "in", "value": sorted(str(x) for x in extra["record_types"])}],
                     "term_types": {term: {"datatype": "string"}}}
            res.append(resolve(fm["node_label"], tf))
        if sh in ("or_boolean", "nor_boolean"):
            rec["bo_group_id"] = _safe(f"GRP-{base_id}")
        if sh == "static_value":
            rec["fixed_default"] = {"kind": "fixed", "value": extra.get("value"),
                                    "context": {"node_label": fm["node_label"], "module": fm["module"]},
                                    "evidence": {"date": SOURCE_COMMIT_DATE, "source": evidence[0]["source"]}}
        subj = node_curie(fm["module"], fm["node_label"], fld)
        if fld is None:
            res = [{"field": None, "status": "NO_NODE_FIELD", "node_label": fm["node_label"]}]
        other = {"level": "published", "registry": fm["registry"], "category": fm["category"],
                 "mapping_key": fm["mapping_key"], "special_handling": sh, "rule": why,
                 "required": fm["required"], "eligible_for_source": fm["eligible_for_source"],
                 "indexed": fm["indexed"], "resolution": res}
        if sh in ("coalesce", "or_boolean", "nor_boolean"):
            other["combined_fields"] = fields
            other["position"] = k + 1
        if sh == "equal_boolean":
            other["extra_value"] = extra.get("value")
        rec.update({
            "subject_id": subj, "predicate_id": SKOS_PREDICATE[rel], "object_id": obj,
            "mapping_justification": "semapv:ManualMappingCuration",
            "claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
            "semantic_relation": rel, "value_domain_relation": dict(VDR_UNKNOWN), "transport_fidelity": fid,
            "guard": guard, "translation_fn": fn, "loss_contract": loss,
            "proof": {"type": "published_mapping", "evidence": evidence, "tests": []},
            "evidence_state": _ev_state(res), "basis": "direct",
            "subject_concept": UNGLOSSED, "object_concept": UNGLOSSED,
            "subject_label": f"{fm['node_label']}.{fld}" if fld else fm["node_label"],
            "object_label": f"{fm['ontology_label']}._ont_{fm['ontology_field']}",
            "subject_source": f"{SOURCE_REPO} módulo {fm['module']}", "subject_source_version": SOURCE_COMMIT,
            "object_source": f"{SOURCE_REPO} ontologia", "object_source_version": SOURCE_COMMIT,
            "author_label": "contribuidores do Cartography", "mapping_provider": SOURCE_REPO,
            "mapping_date": SOURCE_COMMIT_DATE, "publication_date": SOURCE_COMMIT_DATE,
            "mapping_tool": "bo.gold_carto.build", "license": LICENSE_URI,
            "comment": f"publicado no Cartography {SOURCE_TAG}: {why}",
            "other": json.dumps(other, ensure_ascii=False, sort_keys=True),
        })
        out.append(rec)
    return out


def _c09_from_comp(comp: dict, a: dict, b: dict, cid: str, hub: dict, fallback: str | None) -> dict:
    ev = EVIDENCE_STATES[min(EVIDENCE_STATES.index(a["evidence_state"]), EVIDENCE_STATES.index(b["evidence_state"]))]
    oa, ob = json.loads(a["other"]), json.loads(b["other"])
    if fallback:
        rel, fid, fn, guard, vdr, loss = "related", "none", None, {"all": []}, dict(VDR_UNKNOWN), []
        deriv = {"table_row": fallback, "result": None, "fallback": "relatedMatch (sem função, sem transporte)"}
    else:
        rel, fid = comp["semantic_relation"], comp["transport_fidelity"]
        chain = comp["translation_fn"]
        fn = None if not chain else chain[0] if len(chain) == 1 else chain
        guard = comp["guard"]
        vdr = {"relation": comp["value_domain_relation"]["relation"], "orientation": "subject_to_object"}
        loss = [dict(x, leg=i + 1) for i, ls in enumerate(comp.get("leg_losses") or []) for x in (ls or [])]
        deriv = {"table_row": comp["proof"]["table_row"], "result": rel, "derivation": comp["proof"]["derivation"]}
    other = {"level": "derived", "category": oa["category"], "pivot": a["object_id"],
             "legs": [a["claim_id"], b["claim_id"]], "derivation": deriv,
             "disabled_rules_for_derivation": sorted(DISABLED_FOR_DERIVATION),
             "hub_outcome": {"outcome": hub.get("outcome"), "rule": hub.get("rule")},
             "resolution": oa["resolution"] + ob["resolution"]}
    return {
        "subject_id": a["subject_id"], "predicate_id": SKOS_PREDICATE[rel], "object_id": b["subject_id"],
        "mapping_justification": "semapv:MappingChaining",
        "claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
        "semantic_relation": rel, "value_domain_relation": vdr, "transport_fidelity": fid,
        "guard": guard, "translation_fn": fn, "loss_contract": loss,
        "proof": {"type": "composition", "legs": [a["claim_id"], b["claim_id"]],
                  "evidence": a["proof"]["evidence"] + b["proof"]["evidence"], "tests": [],
                  "table_row": deriv["table_row"]},
        "evidence_state": ev, "basis": "shared_concept", "anchors": [a["claim_id"], b["claim_id"]],
        "subject_concept": UNGLOSSED, "object_concept": UNGLOSSED,
        "subject_label": a["subject_label"], "object_label": b["subject_label"],
        "subject_source_version": SOURCE_COMMIT, "object_source_version": SOURCE_COMMIT,
        "mapping_provider": SOURCE_REPO, "mapping_date": SOURCE_COMMIT_DATE,
        "mapping_tool": "bo.gold_carto.build (bo.semantics.composition.compose)", "license": LICENSE_URI,
        "comment": f"derivada: os dois campos alimentam {a['object_label']} no Cartography {SOURCE_TAG}",
        "other": json.dumps(other, ensure_ascii=False, sort_keys=True),
    }


def derived(pub: list[dict]) -> tuple[list[dict], dict]:
    """Pares entre provedores (aws<gcp<azure) com o mesmo campo da ontologia como pivô."""
    order = {p: i for i, p in enumerate(PROVIDERS)}
    by_pivot: dict[str, list[dict]] = {}
    stats = {"pairs_considered": 0, "skipped_fixed_value": 0, "skipped_same_provider": 0, "composed": 0,
             "fallback_related": 0, "empty_guard": 0, "by_table_row": {}, "hub_outcomes": {}}
    for r in pub:
        by_pivot.setdefault(r["object_id"], []).append(r)
    out = []
    for pivot in sorted(by_pivot):
        rows = sorted(by_pivot[pivot], key=lambda r: r["claim_id"])
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                pa, pb = a["subject_id"].split(":", 1)[0][6:], b["subject_id"].split(":", 1)[0][6:]
                if pa == pb:
                    stats["skipped_same_provider"] += 1
                    continue
                if order[pa] > order[pb]:
                    a2, b2 = b, a
                else:
                    a2, b2 = a, b
                stats["pairs_considered"] += 1
                if "fixed_default" in a2 or "fixed_default" in b2:
                    stats["skipped_fixed_value"] += 1
                    continue
                A, B = Claim(_core(a2)), Claim(_core(b2))
                hub = K.hub_claim(A, B)
                ho = f"{hub.get('outcome')}:{hub.get('rule')}"
                stats["hub_outcomes"][ho] = stats["hub_outcomes"].get(ho, 0) + 1
                comp = K.compose(A, inverse_leg(B), disabled=DISABLED_FOR_DERIVATION)
                h = hashlib.sha256(f"{a2['claim_id']}|{b2['claim_id']}".encode()).hexdigest()[:12]
                cid = f"CARTO-DER-{pa_of(a2)}-{pa_of(b2)}-{h}"
                if comp["outcome"] == "COMPOSED":
                    row = _c09_from_comp(comp["claim"], a2, b2, cid, hub, None)
                    stats["composed"] += 1
                elif comp["outcome"] == "UNPROVEN" and comp["rule"] == "K-TABLE":
                    row = _c09_from_comp({}, a2, b2, cid, hub, f"{A.relation}∘{inverse_leg(B).relation}")
                    stats["fallback_related"] += 1
                elif comp["outcome"] == "EMPTY":
                    stats["empty_guard"] += 1
                    continue
                else:
                    raise ValueError(f"composição inesperada {comp['outcome']}/{comp['rule']} em {cid}")
                tr = json.loads(row["other"])["derivation"]["table_row"]
                stats["by_table_row"][tr] = stats["by_table_row"].get(tr, 0) + 1
                out.append(row)
    stats["by_table_row"] = dict(sorted(stats["by_table_row"].items()))
    stats["hub_outcomes"] = dict(sorted(stats["hub_outcomes"].items()))
    out.sort(key=lambda r: r["claim_id"])
    return out, stats


def inverse_leg(b: Claim) -> Claim:
    """Inversa da âncora b com fidelidade por regra fixa (invert não copia a fidelidade e, sem domínios
    declarados, não há como recalculá-la): sem inversa executável (enum_map não injetiva) -> none; com inversa
    (identity, enum_map injetiva) ou sem função nos dois sentidos -> a fidelidade da ida."""
    inv = invert(b)
    rec = dict(inv.rec)
    rec["transport_fidelity"] = "none" if rec.get("inverse_missing") else b["transport_fidelity"]
    rec.pop("inverse_missing", None)
    return Claim(rec)


def pa_of(r: dict) -> str:
    return r["subject_id"].split(":", 1)[0][len("carto_"):]


def _core(r: dict) -> dict:
    """Só os campos da teoria (o que compose/invert leem)."""
    from bo.semantics.claims import FIELDS
    return {k: v for k, v in r.items() if k in FIELDS or k == "fixed_default"}
