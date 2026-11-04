"""Nível OBSERVED (adendo de 04/11, §2): fatos tirados dos experimentos reprodutíveis do OBS-GAPS na API real.

Entradas (só leitura): $BO_DATA/OBS-GAPS/observations.jsonl (+ report.json quando sair) e $BO_DATA/OBS-GAPS-AZ/
(quando sair). Cada fato observado leva: observation_ref (as observações usadas, por run/experimento/passo/
repetição), run_id, repetitions (pares run×repetição distintos do tratamento), control (o passo de controle e o seu
resultado) e observed_at (a observação mais recente usada). Regras (rules.py):
  R-OBS-ID          regra com ou sem identidade de API (security list: nenhuma regra tem id, lista trocada inteira,
                    aceita duplicata; NSG: toda regra listada tem id e é alterada/removida pelo id)
  R-OBS-OWNER       a API recusa regra de NSG sem NSG (inexistente ou sem nsg-id) e não há comando de regra solta:
                    dono = o NSG. Contra a doc (camada de API pela doc, R-OWN-API self) vira disputa observada × doc
  R-OBS-CASCADE     regras somem com o NSG (só quando o report.json do OBS-GAPS fechar o experimento)
  R-OBS-ASSOC-LIFE  ciclo de vida da associação NSG↔NIC/subnet (OBS-GAPS-AZ, quando sair)
Exigência mínima: 2 repetições distintas do tratamento e o controle presente com rc 0; senão o fato não sai.
Os registros só entram no service_evidence.jsonl quando o C25 aceita o nível observed (emenda 10 do CONTRACTS);
antes disso vão para .staging/observed_candidates.jsonl, para teste.
"""

from __future__ import annotations

import json

from . import common

DIRS = ("OBS-GAPS", "OBS-GAPS-AZ")


def c25_accepts_observed() -> bool:
    """O C25 (emenda 10, 1.4.0) aceita level observed no próprio campo level."""
    d = json.loads((common.bo_repo() / "contracts" / "C25_service_evidence.schema.json").read_text(encoding="utf-8"))
    lv = d["$defs"]["service_evidence"]["properties"].get("level") or {}
    return "observed" in (lv.get("enum") or [])


def load() -> tuple[list[dict], dict]:
    obs, reports = [], {}
    for d in DIRS:
        base = common.bo_data() / d
        p = base / "observations.jsonl"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    r["_src"] = d
                    obs.append(r)
        rp = base / "report.json"
        if rp.exists():
            reports[d] = json.loads(rp.read_text(encoding="utf-8"))
    return obs, reports


def _ref(r: dict) -> str:
    """record_id do C25 1.4.0: <run>/<passo>/<repetição> (mais #<tentativa> quando há mais de uma)."""
    rid = f"{r['run']}/{r['step']}/{r['repetition']}"
    return rid + (f"#{r['attempt']}" if (r.get("attempt") or 1) > 1 else "")


def _steps(obs, exp, step):
    return [r for r in obs if r["experiment"] == exp and r["step"] == step]


def _reps(rs):
    return sorted({(r["run"], r["repetition"]) for r in rs})


def _closed(reports: dict, exp: str) -> bool:
    """O report.json do OBS-GAPS (obs-gaps.report/1) dá o experimento como fechado: resposta com
    repetitions_complete >= 2 e repeatable true."""
    for rep in reports.values():
        for e in (rep.get("answers") or []):
            if e.get("experiment") == exp and (e.get("repetitions_complete") or 0) >= 2 and e.get("repeatable"):
                return True
    return False


def facts(obs: list[dict], reports: dict) -> list[dict]:
    """Fatos observados como dicionários neutros: {provider, type, block_path, fact_kind, rule, value, evidence}."""
    out = []

    def emit(T, bp, kind, rule, value, treat, control, provider="oci"):
        reps = _reps(treat)
        if len(reps) < 2 or not control or any(c["rc"] != 0 for c in control):
            return
        used = treat + control
        last = max(treat, key=lambda r: (r["at"], r["repetition"]))
        out.append({"provider": provider, "type": T, "block_path": bp, "fact_kind": kind, "rule": rule,
                    "value": dict(value, observation_refs=sorted({f"{r['_src']}:{_ref(r)}" for r in used})),
                    "observation_ref": {"path": f"$BO_DATA/{last['_src']}/observations.jsonl",
                                        "record_id": _ref(last)},
                    "run_id": last["run"], "repetitions": len(reps),
                    "control": {"description": f"passo de controle {control[0]['step']} do experimento",
                                "result": f"rc={control[0]['rc']}"},
                    "observed_at": max(r["at"] for r in used)})

    e1 = "EXP1-oci-security-list"
    gets = [r for s in ("get_after_create", "get_after_duplicate", "get_after_reorder", "get_after_port_change")
            for r in _steps(obs, e1, s) if r["rc"] == 0 and isinstance(r.get("result"), dict)]
    if gets and all(r["result"].get("any_rule_has_id") is False for r in gets):
        dup = [r for r in _steps(obs, e1, "get_after_duplicate") if r["rc"] == 0]
        accepts_dup = bool(dup) and all(len(x["result"].get("ingress_order", [])) >
                                        len(set(x["result"].get("ingress_order", []))) for x in dup)
        val = {"aspect": "item_identity", "has_id": False, "duplicates_accepted": accepts_dup, "replaced_whole": True,
               "rule": "R-OBS-ID", "layer": "api"}
        for bp in ("ingress_security_rules", "egress_security_rules"):
            emit("oci_core_security_list", bp, "identity", "R-OBS-ID", dict(val), gets + dup,
                 _steps(obs, e1, "update_identical_control"))
    e2 = "EXP2-oci-nsg"
    lists = [r for r in _steps(obs, e2, "list_after_add") if r["rc"] == 0]
    by_id = [r for s in ("update_rule1_port_by_id", "remove_rule3_by_id") for r in _steps(obs, e2, s)]
    if lists and all(all("id" in (x.get("keys") or []) for x in r["result"].get("rules", [])) for r in lists) \
            and by_id and all(r["rc"] == 0 for r in by_id):
        emit("oci_core_network_security_group_security_rule", None, "identity", "R-OBS-ID",
             {"aspect": "item_identity", "has_id": True, "requires_parent": True,
              "parent_attribute": "network_security_group_id", "parent_type": "oci_core_network_security_group",
              "id_field": "id", "rule": "R-OBS-ID", "layer": "api"},
             lists + by_id + [r for s_ in ("add_rule_to_nonexistent_nsg", "add_rule_without_nsg_id")
                              for r in _steps(obs, e2, s_)],
             _steps(obs, e2, "list_rules_empty_control"))
    refused = [r for s in ("add_rule_to_nonexistent_nsg", "add_rule_without_nsg_id") for r in _steps(obs, e2, s)]
    nocmd = _steps(obs, e2, "cli_has_standalone_rule_command")
    ok_add = _steps(obs, e2, "add_2_rules")
    if refused and all(r["rc"] != 0 for r in refused) and nocmd and \
            all((r.get("result") or {}).get("exists") is False for r in nocmd):
        emit("oci_core_network_security_group_security_rule", None, "owner", "R-OBS-OWNER",
             {"kind": "parent", "via": ["network_security_group_id"], "rule": "R-OBS-OWNER", "layer": "api"},
             refused + nocmd, ok_add)
    if _closed(reports, e2):
        gone = [r for s in ("list_rules_after_nsg_delete", "update_old_rule_id_after_nsg_delete")
                for r in _steps(obs, e2, s)]
        dele = [r for r in _steps(obs, e2, "delete_nsg_with_2_rules") if r["rc"] == 0]
        if dele and gone and all(r["rc"] != 0 for r in gone):
            emit("oci_core_network_security_group_security_rule", None, "lifecycle_controller", "R-OBS-CASCADE",
                 {"kind": "parent", "rule": "R-OBS-CASCADE", "layer": "api",
                  "observed": {"delete_parent_with_rules": "accepted", "rules_after_parent_delete": "unreachable (404)"},
                  "caveat": "a OCI devolve o mesmo 404 (NotAuthorizedOrNotFound) para não autorizado e para "
                            "inexistente; a cascata é inferida de 404 depois do delete do pai, com controle antes"},
                 dele + gone,
                 _steps(obs, e2, "list_before_nsg_delete_control"))
    # azure (OBS-GAPS-AZ): só com o report.json do lote presente
    if "OBS-GAPS-AZ" in reports:
        az = [r for r in obs if r["_src"] == "OBS-GAPS-AZ"]

        def st_(exp, step):
            return [r for r in az if r.get("experiment") == exp and r.get("step") == step]
        types_ = st_("a", "provider_resource_types") + st_("a", "cli_command_table_scan")
        no_type = bool(types_) and all(not (r.get("result") or {}).get("types_matching_associat")
                                       and not (r.get("result") or {}).get("network_commands_matching_associat")
                                       for r in types_)
        blocked = st_("b", "delete_nsg_while_associated")
        ctrl = st_("control", "delete_nsgC_unassociated")
        for T, via, before, after, exp, kind in (
                ("azurerm_network_interface_security_group_association", "network_interface_id",
                 "nsg_backrefs_before_nic_delete", "nsg_backrefs_after_nic_delete", "d", "networkInterfaces"),
                ("azurerm_subnet_network_security_group_association", "subnet_id",
                 "nsg_backrefs_before_nic_delete", "nsg_backrefs_after_subnet_delete", "d2", "subnets")):
            bef, aft = st_("d", before), st_(exp, after)
            def n(r):
                v = (r.get("result") or {}).get(kind)
                return len(v) if isinstance(v, list) else (v if isinstance(v, int) else -1)
            gone = bool(bef) and bool(aft) and all(n(r) >= 1 for r in bef) and all(n(r) == 0 for r in aft)
            if no_type and gone and blocked and all(r["rc"] != 0 for r in blocked):
                emit(T, None, "lifecycle_controller", "R-OBS-ASSOC-LIFE",
                     {"kind": "parent", "via": [via], "rule": "R-OBS-ASSOC-LIFE", "layer": "api",
                      "observed": {"own_resource_type": False, "removed_with_holder": True,
                                   "blocks_nsg_delete_while_associated": True}},
                     types_ + bef + aft + blocked, ctrl, provider="azurerm")
            rb = st_("a", "readback_nic" if "interface" in T else "readback_subnet")
            if no_type and rb and all((r.get("result") or {}).get("networkSecurityGroup") for r in rb):
                emit(T, None, "owner", "R-OBS-OWNER",
                     {"kind": "parent", "via": [via], "rule": "R-OBS-OWNER", "layer": "api",
                      "observed": {"reference_stored_on_holder": "networkSecurityGroup.id"}},
                     types_ + rb, st_("control", "nic_show_before_assoc"), provider="azurerm")
        if blocked and all(r["rc"] != 0 and "InUseNetworkSecurityGroupCannotBeDeleted" in
                           json.dumps(r.get("error") or {}) for r in blocked):
            emit("azurerm_network_security_group", None, "lifecycle_controller", "R-OBS-BLOCK-DELETE",
                 {"aspect": "delete_blocked_while_referenced", "rule": "R-OBS-BLOCK-DELETE", "layer": "api",
                  "error_code": "InUseNetworkSecurityGroupCannotBeDeleted",
                  "by": ["azurerm_network_interface_security_group_association",
                         "azurerm_subnet_network_security_group_association"], "auto_disassociation": False},
                 blocked, ctrl, provider="azurerm")
    return out


OBS_PATH = __import__("re").compile(r"^\$BO_DATA/OBS-GAPS(-AZ)?/\S+$")  # padrão do C25 1.5.0 (observation_ref.path)


def _side_value(rec: dict):
    v = rec.get("value") or {}
    return v.get("kind")


def records(ctxs: dict, disputes: list) -> dict:
    """Consolidação R1–R5 do PREREG (b95403a): R1 nunca sobrescreve; R2 disputa já existente entre fatos NÃO
    observados (publicado ou derivado) é resolvida a favor do lado que a observação reproduz (status
    resolvida-por-observação, sides, resolved_to, observation_id); R3 observado contra publicado sem disputa
    prévia abre disputa observed_x_published; R4 campo sem publicado é preenchido. R5: a mesma regra para todos."""
    obs, reports = load()
    fs = facts(obs, reports)
    st = {"observations": len(obs), "facts": len(fs), "accepted_by_c25": c25_accepts_observed(),
          "reports": sorted(reports), "pending": [], "emitted": 0,
          "R1_not_overwritten": 0, "R2_resolved": 0, "R3_opened": 0, "R4_filled": 0}
    if not _closed(reports, "EXP2-oci-nsg"):
        st["pending"].append("R-OBS-CASCADE: experimento EXP2 sem report.json fechado")
    if "OBS-GAPS-AZ" not in reports:
        st["pending"].append("R-OBS-ASSOC-LIFE: OBS-GAPS-AZ sem report.json")
    cand = []
    for f in fs:
        p = f["provider"]
        ctx = ctxs[p]
        api = {"service": "core" if p == "oci" else "Microsoft.Network", "resource": f["type"]}
        v = dict(f["value"])
        if f["block_path"]:
            v["block_path"] = f["block_path"]
        extra = {k: f[k] for k in ("observation_ref", "run_id", "repetitions", "control", "observed_at")}
        cand.append({"type": f["type"], "block_path": f["block_path"], "fact_kind": f["fact_kind"], "value": v,
                     **extra})
        if not st["accepted_by_c25"] or not OBS_PATH.match(extra["observation_ref"]["path"]):
            st["pending"].append(f"{f['type']} {f['rule']}: não aceito pelo C25 ainda")
            continue
        same = [r for r in ctx.recs if r["terraform_resource_type"] == f["type"] and r["fact_kind"] == f["fact_kind"]
                and r.get("block_path") == f["block_path"] and r["status"] == "stated" and r["level"] != "observed"]
        eid = ctx.add(f["type"], f["fact_kind"], f"obs:{f['rule']}:{f['block_path']}", api, "stated",
                      "observed", value=v)
        ctx.by_id[eid].update(extra)
        st["emitted"] += 1
        st["R1_not_overwritten"] += 1
        prior = [d for d in disputes if d["provider"] == p and d["terraform_resource_type"] == f["type"]
                 and d["fact"] == f["fact_kind"] and d.get("block_path") == f["block_path"]
                 and d.get("status") != "resolvida-por-observação" and "observed" not in d.get("kind", "")
                 and len(d.get("evidence") or []) == 2]
        ok = None
        for d in prior:
            sides = {sd: ctx.by_id.get(e) for sd, e in (("doc", d["evidence"][0]), ("spec", d["evidence"][1]))}
            if "kind" in v and sides["spec"] and _side_value(sides["spec"]) == v["kind"]:
                ok = (d, "spec")
            elif "kind" in v and sides["doc"] and _side_value(sides["doc"]) == v["kind"]:
                ok = (d, "doc")
            if ok:
                break
        if ok:  # R2
            d, side = ok
            d.update({"status": "resolvida-por-observação", "sides": list(d["evidence"]), "resolved_to": side,
                      "observation_id": eid, "resolved_at": extra["observed_at"]})
            st["R2_resolved"] += 1
            continue
        pub = [r for r in same if r["level"] == "published" and _contradicts(r, v)]
        if pub:  # R3
            ctx.by_id[eid]["disputes"] = sorted({r["evidence_id"] for r in pub})
            disputes.append({"provider": p, "terraform_resource_type": f["type"], "fact": f["fact_kind"],
                             **({"block_path": f["block_path"]} if f["block_path"] else {}),
                             "kind": "observed_x_published", "status": "aberta",
                             "doc": {"value": (pub[0].get("value") or {}).get("kind") or
                                     (pub[0].get("value") or {}).get("aspect"), "rule": pub[0]["value"].get("rule")},
                             "spec": {"kind": v.get("kind"), "rule": f["rule"], "level": "observed"},
                             "evidence": sorted({r["evidence_id"] for r in pub} | {eid})})
            st["R3_opened"] += 1
            continue
        st["R4_filled"] += 1  # R4: nenhum publicado afirma esse campo
    st["candidates"] = cand
    return st


def _contradicts(rec: dict, v: dict) -> bool:
    """O publicado afirma valor do MESMO campo e diferente do observado (kind, ou has_id do item_identity)."""
    rv = rec.get("value") or {}
    if "kind" in v and "kind" in rv:
        return rv["kind"] != v["kind"]
    if v.get("aspect") == "item_identity" and rv.get("aspect") == "item_identity":
        return rv.get("has_id") != v.get("has_id")
    return False
