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
    d = json.loads((common.bo_repo() / "contracts" / "C00_conventions.schema.json").read_text(encoding="utf-8"))
    return "observed" in (d["$defs"].get("evidence_level") or {}).get("enum", [])


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
    return f"{r['_src']}:{r['run']}:{r['experiment']}:{r['step']}:{r['repetition']}:{r.get('attempt', 0)}"


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
        out.append({"provider": provider, "type": T, "block_path": bp, "fact_kind": kind, "rule": rule,
                    "value": value, "observation_ref": sorted({_ref(r) for r in used}),
                    "run_id": sorted({r["run"] for r in used}), "repetitions": len(reps),
                    "control": sorted({f"{c['step']}:rc={c['rc']}" for c in control}),
                    "observed_at": max(r["at"] for r in used)})

    e1 = "EXP1-oci-security-list"
    gets = [r for s in ("get_after_create", "get_after_duplicate", "get_after_reorder", "get_after_port_change")
            for r in _steps(obs, e1, s) if r["rc"] == 0 and isinstance(r.get("result"), dict)]
    if gets and all(r["result"].get("any_rule_has_id") is False for r in gets):
        dup = [r for r in _steps(obs, e1, "get_after_duplicate") if r["rc"] == 0]
        accepts_dup = bool(dup) and all(len(x["result"].get("ingress_order", [])) >
                                        len(set(x["result"].get("ingress_order", []))) for x in dup)
        val = {"status": "absent", "rule": "R-OBS-ID", "layer": "api",
               "observed": {"any_rule_has_id": False, "accepts_duplicate_rule": accepts_dup,
                            "list_replaced_whole": True}}
        for bp in ("ingress_security_rules", "egress_security_rules"):
            emit("oci_core_security_list", bp, "identity", "R-OBS-ID", dict(val), gets + dup,
                 _steps(obs, e1, "update_identical_control"))
    e2 = "EXP2-oci-nsg"
    lists = [r for r in _steps(obs, e2, "list_after_add") if r["rc"] == 0]
    by_id = [r for s in ("update_rule1_port_by_id", "remove_rule3_by_id") for r in _steps(obs, e2, s)]
    if lists and all(all("id" in (x.get("keys") or []) for x in r["result"].get("rules", [])) for r in lists) \
            and by_id and all(r["rc"] == 0 for r in by_id):
        emit("oci_core_network_security_group_security_rule", None, "identity", "R-OBS-ID",
             {"status": "present", "scope": "within_parent", "key_fields": ["id"], "rule": "R-OBS-ID",
              "layer": "api"}, lists + by_id, _steps(obs, e2, "list_rules_empty_control"))
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
    return out


def records(ctxs: dict, disputes: list) -> dict:
    """Grava os fatos observados no contexto (se o C25 aceita observed) e as disputas observado × doc."""
    obs, reports = load()
    fs = facts(obs, reports)
    st = {"observations": len(obs), "facts": len(fs), "accepted_by_c25": c25_accepts_observed(),
          "reports": sorted(reports), "pending": []}
    if not any(r["experiment"] == "EXP2-oci-nsg" for r in obs) or not _closed(reports, "EXP2-oci-nsg"):
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
        rec_extra = {k: f[k] for k in ("observation_ref", "run_id", "repetitions", "control", "observed_at")}
        cand.append({"type": f["type"], "block_path": f["block_path"], "fact_kind": f["fact_kind"], "value": v,
                     **rec_extra})
        if st["accepted_by_c25"]:
            eid = ctx.add(f["type"], f["fact_kind"], f"obs:{f['rule']}:{f['block_path']}", api, "stated",
                          "observed", value=v)
            ctx.by_id[eid].update(rec_extra)
        for r in ctx.recs:
            rv = r.get("value") or {}
            if r["terraform_resource_type"] == f["type"] and r["fact_kind"] == f["fact_kind"] and \
                    r.get("block_path") == f["block_path"] and r["status"] == "stated" and r["level"] != "observed" \
                    and rv.get("layer") == "api" and "kind" in rv and "kind" in v and rv["kind"] != v["kind"]:
                disputes.append({"provider": p, "terraform_resource_type": f["type"], "fact": f["fact_kind"],
                                 "kind": "observed_x_doc" if rv.get("rule", "").startswith("R-") and "SPEC" not in
                                 rv.get("rule", "") else "observed_x_spec",
                                 "doc": {"kind": rv["kind"], "rule": rv.get("rule")},
                                 "spec": {"kind": v["kind"], "rule": f["rule"], "level": "observed"},
                                 "evidence": [r["evidence_id"]]})
    st["candidates"] = cand
    return st
