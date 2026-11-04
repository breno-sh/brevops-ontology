"""Gera as respostas gravadas SINTÉTICAS dos testes offline (tests/harness/oci/fixtures/recordings/).

  python -I tests/harness/oci/make_recordings.py          regrava
  python -I tests/harness/oci/make_recordings.py --check  confere que os arquivos são a regeneração exata

Nenhuma gravação veio de nuvem (nuvem é proibida nesta fase): o state é montado no formato de
`terraform show -json` a partir dos valores do plano de exemplo (deploy/fixtures/oci/_templates/examples), com
OCIDs e contexto como marcadores (@OCID:<tipo>:<n>, @CTX:<chave>) que o RecordedRunner expande só em memória, e com
os desvios de cada cenário escritos aqui, à vista. Cada gravação guarda o sha256 do main.tf do módulo renderizado:
se o renderizador mudar o HCL, a gravação deixa de valer.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC_DIR = HERE / "fixtures" / "recordings"
os.environ.setdefault("BO_REPO", str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parents[2] / "src"))

from bo.harness.oci import render as R  # noqa: E402
from bo.harness.oci import schema as S  # noqa: E402
from bo.harness.oci import templates_dir, tmp_root  # noqa: E402

EX = templates_dir() / "examples"
BINDINGS = R.load_bindings(EX / "bindings.json")
BLOCKS = {t: set(S.table().block("resource", t).blocks) for t in S.table().types("resource")}
NOTE = "gravação sintética (sem nuvem): state no formato de terraform show -json montado do plano de exemplo"


def rendered() -> dict:
    out = tmp_root() / "make_recordings_render"
    rr = R.render(EX / "lowering_plan.jsonl", out, bindings_path=EX / "bindings.json")
    return {p["plan_id"]: (p, rr.report["files"][f"{p['module']}/main.tf"]) for p in rr.report["plans"]}


def _ocid_token(rtype: str, label: str) -> str:
    return f"@OCID:{rtype}:{sum(ord(c) for c in label)}"


def _set_path(d: dict, toks: list, value) -> None:
    cur = d
    for i, (kind, name, idx) in enumerate(toks):
        last = i == len(toks) - 1
        if kind == "block":
            lst = cur.setdefault(name, [])
            while len(lst) <= idx:
                lst.append({})
            cur = lst[idx]
        elif kind == "attr":
            if last:
                cur[name] = value
            else:
                cur = cur.setdefault(name, {})
        else:
            if last:
                cur[name] = value
            else:
                cur = cur.setdefault(name, {})


def _tokens(hcl_path: str) -> list:
    out = []
    parts = hcl_path.split(".")
    seen_attr = False
    for p in parts:
        if "[" in p and not seen_attr:
            name, idx = p[:-1].split("[")
            out.append(("block", name, int(idx)))
        elif not seen_attr:
            out.append(("attr", p, 0))
            seen_attr = True
        else:
            out.append(("key", p, 0))
    return out


def state_for(plan_report: dict, plan: dict, lifecycle: dict | None = None) -> dict:
    """State 'como planejado' do módulo, com campos computados plausíveis do provider."""
    vidx = {v["field"]: v for s in plan["steps"] for v in s["values"]}
    labels = {v: int(k) for k, v in plan_report["labels"].items()}
    steps = {s["order"]: s for s in plan["steps"]}
    res = {}
    for w in plan_report["written"]:
        key = (w["resource_type"], w["label"])
        r = res.setdefault(key, {"id": _ocid_token(*key)})
        v = vidx[w["field"]] if w["field"] in vidx else None
        step = steps[labels[w["label"]]]
        v = next(x for x in step["values"] if x["field"] == w["field"])
        t = v["term"]
        if t["kind"] == "list":
            exprs = w["expr"][1:-1].split(", ") if w["expr"] != "[]" else []
            val = [_value(it, e, w["source"]) for it, e in zip(t["items"], exprs)]
        else:
            val = _value(t, w["expr"], w["source"])
        m = re.fullmatch(r"([a-z_]+)\[([0-9]+)\]", w["hcl_path"])
        if m and m.group(1) not in BLOCKS.get(w["resource_type"], ()):
            lst = r.setdefault(m.group(1), [])        # forma antiga do C26-LIST: elemento da lista
            while len(lst) <= int(m.group(2)):
                lst.append(None)
            lst[int(m.group(2))] = val
            continue
        _set_path(r, _tokens(w["hcl_path"]), val)
    # inserção declarada do harness (HI-OCI-01): a tag de execução volta no state como o provider a guarda
    for ins in plan_report.get("insertions", []):
        r = res.setdefault((ins["resource_type"], ins["label"]), {"id": _ocid_token(ins["resource_type"], ins["label"])})
        _set_path(r, _tokens(ins["hcl_path"]), "@CTX:" + ins["source"].split(":", 1)[1])
    # referência a atributo que não é id: copia o valor do alvo
    for r in res.values():
        _resolve_refs(r, res)
    resources = []
    for (rtype, label), vals in sorted(res.items(), key=lambda kv: labels[kv[0][1]]):
        vals = dict(vals)
        vals["time_created"] = "2026-11-03 10:00:00.000 +0000 UTC"
        if rtype in ("oci_core_vcn", "oci_core_security_list", "oci_core_network_security_group", "oci_core_subnet"):
            vals["state"] = (lifecycle or {}).get(label, "AVAILABLE")
        if rtype == "oci_core_security_list":
            for rule in vals.get("ingress_security_rules", []):
                rule.setdefault("description", "")
                rule.setdefault("source_type", "CIDR_BLOCK")
        if rtype == "oci_objectstorage_bucket":
            vals.setdefault("storage_tier", "Standard")
            vals["etag"] = "syn-etag-1"
        resources.append({"address": f"module.{plan_report['module']}.{rtype}.{label}", "mode": "managed",
                          "type": rtype, "name": label, "provider_name": "registry.terraform.io/oracle/oci",
                          "schema_version": 0, "values": vals, "sensitive_values": {}})
    return {"format_version": "1.0", "terraform_version": "1.15.8",
            "values": {"root_module": {"child_modules": [
                {"address": f"module.{plan_report['module']}", "resources": resources}]}}}


def _value(t: dict, expr: str, source: str):
    if t["kind"] == "literal":
        return t["value"]
    if t["kind"] == "symbol":
        return "@CTX:" + BINDINGS[t["symbol_id"]] if t["symbol_id"] in BINDINGS else "@CTX:" + source.split(":", 1)[1]
    if t["kind"] == "reference":
        parts = expr.split(".")
        tgt = (parts[0], parts[1])
        val = _ocid_token(*tgt) if parts[2] == "id" else None
        return val if val is not None else ("@REF", tgt, parts[2])
    raise ValueError(f"termo {t['kind']} sem gravação sintética")


def _resolve_refs(obj, res):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, tuple) and v and v[0] == "@REF":
                obj[k] = res[v[1]][v[2]]
            else:
                _resolve_refs(v, res)
    elif isinstance(obj, list):
        for x in obj:
            _resolve_refs(x, res)


def _rec(plan_id, sha, polls, apply=None, destroy=None, after=None, expects=None, scenario=""):
    return {"schema": "bo.harness.oci.recording/1", "synthetic": True, "note": NOTE, "scenario": scenario,
            "plan_id": plan_id, "module_sha256": sha, "identity": "sandbox-synthetic",
            "expects_vars": expects or [], "apply": apply or {"ok": True}, "polls": polls,
            "destroy": destroy or {"ok": True}, "state_list_after_destroy": after or []}


def build_all() -> dict:
    rend = rendered()
    plans = {p["plan_id"]: p for p in R.load_jsonl(EX / "lowering_plan.jsonl")}
    net_rep, net_sha = rend["LP-OCI-NET-0001"]
    sto_rep, sto_sha = rend["LP-OCI-STO-0001"]
    net, sto = plans["LP-OCI-NET-0001"], plans["LP-OCI-STO-0001"]
    net_vars = sorted(v["name"] for v in net_rep["variables"]) + ["bo_region"]
    sto_vars = sorted(v["name"] for v in sto_rep["variables"]) + ["bo_region"]

    ok_net = state_for(net_rep, net)
    # o state devolve o conjunto de regras de entrada em outra ordem (set não tem ordem)
    sl = ok_net["values"]["root_module"]["child_modules"][0]["resources"][1]["values"]
    sl["ingress_security_rules"].reverse()
    provisioning = state_for(net_rep, net, lifecycle={"r1": "PROVISIONING"})
    altered = copy.deepcopy(ok_net)
    sl2 = altered["values"]["root_module"]["child_modules"][0]["resources"][1]["values"]
    for rule in sl2["ingress_security_rules"]:
        if rule["protocol"] == "17":
            rule["stateless"] = False           # a API devolveu a regra UDP como stateful
    lst_rep, lst_sha = rend["LP-OCI-NET-0002"]
    idx_rep, idx_sha = rend["LP-OCI-NET-0003"]
    lst, idx = plans["LP-OCI-NET-0002"], plans["LP-OCI-NET-0003"]
    lst_vars = sorted(v["name"] for v in lst_rep["variables"]) + ["bo_region"]
    idx_vars = sorted(v["name"] for v in idx_rep["variables"]) + ["bo_region"]
    ok_lst = state_for(lst_rep, lst)
    # security_list_ids é set no oci 9.11.0: o state devolve em outra ordem e continua igual ao plano
    sub = ok_lst["values"]["root_module"]["child_modules"][0]["resources"][3]["values"]
    sub["security_list_ids"].reverse()
    lst_altered = copy.deepcopy(ok_lst)
    lst_altered["values"]["root_module"]["child_modules"][0]["resources"][3]["values"]["security_list_ids"].pop()
    ok_idx = state_for(idx_rep, idx)
    ok_sto = state_for(sto_rep, sto)
    leaky = copy.deepcopy(ok_sto)
    b = leaky["values"]["root_module"]["child_modules"][0]["resources"][0]["values"]
    b["bucket_url"] = "https://objectstorage.syn-region-1.example.invalid/n/@CTX:objectstorage_namespace/b/x"
    b["kms_key_id"] = "@OCID:oci_kms_key:9"
    return {
        "net_persisted.json": _rec("LP-OCI-NET-0001", net_sha, [provisioning, ok_net], expects=net_vars,
                                   scenario="VCN em PROVISIONING na 1ª leitura; regras de entrada em outra ordem"),
        "net_altered.json": _rec("LP-OCI-NET-0001", net_sha, [altered], expects=net_vars,
                                 scenario="regra UDP volta stateful: ALTERED"),
        "net_timeout.json": _rec("LP-OCI-NET-0001", net_sha, [provisioning], expects=net_vars,
                                 scenario="VCN não sai de PROVISIONING: INFRA_ERROR por espera"),
        "net_throttled.json": _rec("LP-OCI-NET-0001", net_sha, [], apply={"ok": False, "status": 429,
                                                                          "code": "TooManyRequests"},
                                   expects=net_vars, scenario="limite de taxa no apply: INFRA_ERROR"),
        "list_persisted.json": _rec("LP-OCI-NET-0002", lst_sha, [ok_lst], expects=lst_vars,
                                    scenario="sub-rede com security_list_ids = termo list; o set volta em outra ordem"),
        "list_altered.json": _rec("LP-OCI-NET-0002", lst_sha, [lst_altered], expects=lst_vars,
                                  scenario="a sub-rede volta com uma security list a menos: ALTERED"),
        "list_indexed_persisted.json": _rec("LP-OCI-NET-0003", idx_sha, [ok_idx], expects=idx_vars,
                                            scenario="forma antiga do C26-LIST (security_list_ids.0, .1): PERSISTED"),
        "sto_persisted.json": _rec("LP-OCI-STO-0001", sto_sha, [leaky], expects=sto_vars,
                                   scenario="bucket e política conferem; campos não planejados com namespace e OCID "
                                            "de chave não podem vazar"),
        "sto_rejected.json": _rec("LP-OCI-STO-0001", sto_sha, [], apply={"ok": False, "status": 400,
                                                                         "code": "InvalidParameter"},
                                  expects=sto_vars, scenario="API recusa a configuração: REJECTED_BY_API"),
        "sto_residue.json": _rec("LP-OCI-STO-0001", sto_sha, [ok_sto], expects=sto_vars,
                                 after=["module.lp_oci_sto_0001.oci_objectstorage_bucket.r1"],
                                 scenario="destroy deixa o bucket no state: resíduo"),
    }


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    recs = build_all()
    if "--check" in argv:
        bad = [n for n, o in recs.items() if not (REC_DIR / n).exists() or (REC_DIR / n).read_text() != dump(o)]
        extra = sorted(p.name for p in REC_DIR.glob("*.json") if p.name not in recs)
        if bad or extra:
            print(f"make_recordings --check: diferem {bad}, sobram {extra}")
            return 1
        print(f"make_recordings --check: {len(recs)} gravação(ões) idênticas à regeneração")
        return 0
    REC_DIR.mkdir(parents=True, exist_ok=True)
    for n, o in recs.items():
        (REC_DIR / n).write_text(dump(o), encoding="utf-8")
    print(f"make_recordings: {len(recs)} gravação(ões) em {REC_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
