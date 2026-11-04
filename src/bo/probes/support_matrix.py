"""Gate: tipo × provedor × SKU sem suporte validado não entra no sorteio.

  python -I -m bo.probes.support_matrix            confere (regenera em memória e compara com o gravado)
  python -I -m bo.probes.support_matrix --write    regrava deploy/probes/protocol_support.json (C22 probe_types,
                                                   validated_support preenchido), results/PROBEKIT/support_matrix.json
                                                   e o NOT_VALIDATED.json de cada _templates/ sem suporte

Validação OFFLINE do PROBEKIT (o SERVICE-EVIDENCE só documenta; C25-PS-PUB: validated é sempre false lá). Cada
caso tipo/provedor passa por:
  S1 evidência      linha do SERVICE-EVIDENCE documented_supported, com evidência publicada
  S2 requisito      mínimo documentado <= requirement.max_seconds (ex. fila <= 24 h, log <= 3 dias)
  S3 taxa (P4)      limite de taxa com janela, chave, rajada e mecanismo declarados
  S4 protocolo      P1–P3 com o TTL configurado (janela separada do TTL, com margem)
  S5 janela         janela do protocolo <= janela máxima do SAFETY (D12) e de cada tipo do template
  S6 SKU            tipo que realiza a sonda está na allowlist do SAFETY e não é Classe C
  S7 pin            versão citada pelo SERVICE-EVIDENCE = versão fixada (universe/pins.json)
  S8 template       existe; schema fixado confere nos dois lados; caso configura os atributos da sonda; caso e
                    controle só diferem neles; TTL do plano = TTL do kit; plan_guard sem achado; custo <= limite
  S9 operações      o kit tem as operações de plano de dados e o parser separa efeito de oposto nas amostras
                    canônicas (ops.SAMPLES)
validated = todos passam. unsupported = falha demonstrada (S1 documented_unsupported, S2 com mínimo documentado
acima do requisito, S5). O resto é unknown (falta evidência, SKU fora da allowlist, sem template). Só validated entra no sorteio (DEPSAMPLE lê drawable()).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from . import KIT_VERSION, MODULE_ID, PROBE_TYPES, PROVIDERS
from . import cells as C
from . import cost as K
from . import protocol as PR
from . import templates as T
from .common import (ProbeError, compare_or_write, deploy_dir, dumps, now, portable, prereg_path, read_jsonl,
                     results_dir, service_evidence_path, sha256_file, sku_table_path)

SUPPORT_JSON = "protocol_support.json"
MATRIX_JSON = "support_matrix.json"
NOT_VALIDATED = "NOT_VALIDATED.json"


def support_path() -> Path:
    return deploy_dir() / SUPPORT_JSON


def matrix_path() -> Path:
    return results_dir() / MATRIX_JSON


# ------------------------------------------------------------------------------------------------ entradas
def load_service_evidence(path: Path | None = None) -> dict[str, dict]:
    from bo.contracts import validate as V
    p = Path(path or service_evidence_path())
    r = V.validate("C25_protocol_support", p)
    if not r.ok:
        raise ProbeError(f"protocol_support.jsonl não confere com o C25: {r.errors[:2]}", "CONTRACT")
    rows = read_jsonl(p)
    out = {}
    for row in rows:
        cell = f"{row['probe_type']}/{row['provider']}"
        if cell in out:
            raise ProbeError(f"{cell}: duas linhas no SERVICE-EVIDENCE (o kit precisa de uma por caso)", "SE")
        if row.get("validated") is not False:
            raise ProbeError(f"{cell}: SERVICE-EVIDENCE com validated != false (C25-PS-PUB)", "SE")
        out[cell] = row
    return out


def inputs_info() -> list[dict]:
    from .tfschema import info
    out = [{"path": "$BO_REPO/prereg/probe_types.yaml", "sha256": sha256_file(prereg_path())},
           {"path": "$BO_DATA/SERVICE-EVIDENCE/protocol_support.jsonl", "sha256": sha256_file(service_evidence_path())},
           {"path": "$BO_REPO/deploy/safety/allowlist_skus.yaml", "sha256": sha256_file(sku_table_path())}]
    for p in PROVIDERS:
        i = info(p)
        out.append({"path": i["path"], "sha256": i["schema_sha256"]})
    return out


# ------------------------------------------------------------------------------------------------ checagem
def _chk(cid: str, ok: bool, detail: str, demonstrated: bool = False) -> dict:
    """demonstrated: a falha é prova positiva de que o protocolo não roda no provedor (=> unsupported)."""
    return {"id": cid, "ok": bool(ok), "detail": detail, "demonstrated": bool(demonstrated and not ok)}


def evaluate_cell(cell: str, se: dict | None, protos: dict, table: dict, pins: dict) -> dict:
    t, p = C.split(cell)
    proto = protos[t]
    impl = C.IMPL.get(cell)
    checks = []
    if se is None:
        checks.append(_chk("S1", False, "sem linha no SERVICE-EVIDENCE"))
        return _verdict(cell, checks, [], None)
    pub = [e for e in se["evidence"] if e.get("level") == "published"]
    checks.append(_chk("S1", se["status"] == "documented_supported" and bool(pub),
                       f"SERVICE-EVIDENCE {se['status']}; {len(pub)} evidência(s) publicada(s)",
                       demonstrated=se["status"] == "documented_unsupported"))
    mn = ((se.get("documented") or {}).get("min") or {}).get("seconds")
    mx = se["requirement"]["max_seconds"]
    if mx is None:
        checks.append(_chk("S2", True, "sem requisito de mínimo no protocolo"))
    elif mn is None:
        checks.append(_chk("S2", False, f"mínimo do provedor não documentado; requisito <= {mx} s"))
    else:
        checks.append(_chk("S2", mn <= mx, f"mínimo documentado {mn} s; requisito <= {mx} s", demonstrated=True))
    if t == "rate_limit":
        miss = PR.rate_limit_declared(se.get("documented") or {})
        checks.append(_chk("S3", not miss, "janela, chave, rajada e mecanismo declarados" if not miss else
                           f"não declarado(s) no SERVICE-EVIDENCE: {', '.join(miss)}"))
    ttl = impl.ttl_s if impl else float(mn or 0)
    coh = proto.coherence(ttl)
    checks.append(_chk("S4", not coh, f"TTL {ttl:.0f} s; " + ("; ".join(coh) if coh else "P1–P3 conferem")))
    win_h = proto.window_s / 3600.0
    se_type = se["terraform_resource_type"]
    tables = table["providers"][p]["types"]
    caps = [table["budget"]["max_window_hours"]]
    tpl_types = set()
    if impl and T.has_template(cell):
        for side in T.SIDES:
            _, insts = T.synthetic_plan(cell, side, T.synthetic_vars(cell, "b-probe", {}, "r", impl.runner_inputs))
            tpl_types |= {i.type for i in insts}
    for rt in sorted(tpl_types | {se_type}):
        if rt in tables:
            caps.append(tables[rt]["max_window_hours"])
    checks.append(_chk("S5", win_h <= min(caps), f"janela {win_h:g} h; máximo {min(caps):g} h (D12 e tipos)",
                       demonstrated=True))
    from bo.safety import skus
    in_table = skus.entry(table, p, se_type) is not None and not skus.is_class_c(table, p, se_type)
    checks.append(_chk("S6", in_table, f"{se_type} " + ("na allowlist do SAFETY" if in_table else
                                                         "fora da allowlist do SAFETY")))
    pin_v = pins[p]["version"]
    checks.append(_chk("S7", se["pin"]["provider_version"] == pin_v,
                       f"SERVICE-EVIDENCE cita {se['pin']['provider_version']}; pin {pin_v}"))
    sku, s8 = [], []
    if impl is None or not T.has_template(cell):
        s8.append("sem template no kit")
    else:
        s8, sku = template_checks(cell, se, proto, table)
    checks.append(_chk("S8", not s8, "; ".join(s8) if s8 else "template confere (schema, atributos, controle, "
                                                               "TTL, plan_guard, custo)"))
    from .ops import parser_selftest
    s9 = parser_selftest(cell)
    checks.append(_chk("S9", not s9, "operações no kit; parser separa efeito de oposto nas amostras canônicas"
                       if not s9 else "; ".join(s9)))
    return _verdict(cell, checks, sku, se)


def template_checks(cell: str, se: dict, proto, table: dict) -> tuple[list[str], list[dict]]:
    from .tfschema import resource_block
    t, p = C.split(cell)
    impl = C.IMPL[cell]
    out = []
    est = K.estimate(cell, proto, table)
    insts = est["_insts"]
    for side in T.SIDES:
        f = T.schema_findings(insts[side], lambda rt: resource_block(p, rt))
        out += [f"schema ({side}): {x}" for x in f]
    se_type, se_attrs = se["terraform_resource_type"], se["attributes"]
    probe_insts = [i for i in insts["case"] if i.type == se_type]
    if not probe_insts:
        out.append(f"caso sem recurso {se_type}")
    for a in se_attrs:
        if not any(T.has_attr_path(i.config, a) for i in probe_insts):
            out.append(f"caso não configura {se_type}.{a}")
    types_of = {i.address: i.type for i in insts["case"] + insts["control"]}
    out += [f"controle: {x}" for x in T.diff_findings(T.side_diff(insts["case"], insts["control"]), se_type,
                                                       se_attrs, types_of)]
    out += ttl_findings(cell, impl, insts["case"])
    for side in T.SIDES:
        for fd in est["sides"][side]["findings"]:
            out.append(f"plan_guard ({side}): {fd['code']} {fd['address']}")
    if not est["within_limit"]:
        out.append("custo estimado acima do limite do tipo")
    sku = []
    tables = table["providers"][p]["types"]
    for it in insts["case"]:
        ent = tables.get(it.type) or {}
        attrs = {a: T.get_path(it.config, a.replace(".0.", ".0.")) for a, r in sorted((ent.get("rules") or {}).items())
                 if r.get("sku")}
        sku.append({"address": it.address, "type": it.type, "sku": {k: v for k, v in attrs.items()}})
    return out, sku


def ttl_findings(cell: str, impl, case_insts) -> list[str]:
    from .common import duration_s
    if impl.ttl_from:
        rt, path, factor = impl.ttl_from
        vals = []
        for i in case_insts:
            if i.type == rt:
                v = T.get_path(i.config, path)
                if v is None or v is T.UNKNOWN:
                    return [f"TTL {rt}.{path} ausente ou desconhecido no plano"]
                vals.append(duration_s("PT" + str(v)[:-1].upper() + "S") if factor == "duration_s" and
                            str(v).endswith("s") else float(v) * float(factor if factor != "duration_s" else 1))
        if not vals or any(abs(v - impl.ttl_s) > 1e-9 for v in vals):
            return [f"TTL do plano {vals} s diferente do TTL do kit {impl.ttl_s:.0f} s"]
        return []
    if cell in C.ITEM_TTL_ATTRIBUTE:
        rt, path, want = C.ITEM_TTL_ATTRIBUTE[cell]
        got = [T.get_path(i.config, path) for i in case_insts if i.type == rt]
        if got != [want]:
            return [f"atributo de TTL do item {got} diferente de {want!r}"]
    return []


def _verdict(cell: str, checks: list, sku: list, se: dict | None) -> dict:
    failed = [c["id"] for c in checks if not c["ok"]]
    demo = [c["id"] for c in checks if c.get("demonstrated")]
    status = "validated" if not failed else ("unsupported" if demo else "unknown")
    t, p = C.split(cell)
    return {"cell": cell, "probe_type": t, "provider": p, "status": status, "drawable": status == "validated",
            "join_outcome_if_drawn": None if status == "validated" else "PROTOCOL_UNSUPPORTED",
            "failed": failed, "checks": checks,
            "realizing_type": se["terraform_resource_type"] if se else None,
            "attributes": se["attributes"] if se else [], "sku": sku,
            "template": portable(T.template_dir(cell)) + "/"}


# ------------------------------------------------------------------------------------------------ saídas
def build(now_iso: str | None = None) -> tuple[dict, dict, dict]:
    from bo.safety import skus
    from .tfschema import pins
    protos = PR.load()
    se = load_service_evidence()
    table = skus.load_table()
    pn = pins()
    cells = {c: evaluate_cell(c, se.get(c), protos, table, pn) for c in C.all_cells()}
    stamp = now_iso or now()
    doc = yaml.safe_load(prereg_path().read_text(encoding="utf-8"))
    out_types = []
    for pt in doc["probe_types"]:
        vs = []
        for p in PROVIDERS:
            cell = f"{pt['probe_type']}/{p}"
            v = cells[cell]
            vs.append({"provider": p, "status": v["status"], "evidence": evidence_items(cell, v, se.get(cell))})
        out_types.append({**pt, "validated_support": vs})
    support = {**{k: doc[k] for k in ("schema", "contract", "contract_version", "protocol_version")},
               "module": MODULE_ID, "generated_at": stamp, "probe_types": out_types}
    matrix = {"schema": "bo.probekit.support_matrix/1", "module": MODULE_ID, "kit_version": KIT_VERSION,
              "generated_at": stamp, "protocol": PR.source_info(), "kit_params": PR.KIT_PARAMS,
              "inputs": inputs_info(), "protocols": protocols_view(protos),
              "cells": [cells[c] for c in C.all_cells()],
              "drawable": [c for c in C.all_cells() if cells[c]["drawable"]],
              "summary": {s: sum(1 for c in cells.values() if c["status"] == s)
                          for s in ("validated", "unsupported", "unknown")},
              "note": "validação offline (fase 1, sem nuvem): a primeira execução real é do SMOKE, com o GO do "
                      "Breno; o suporte observado só sobe depois das sondas"}
    not_valid = {c: {"schema": "bo.probekit.not_validated/1", "cell": c, "status": v["status"],
                     "join_outcome_if_drawn": "PROTOCOL_UNSUPPORTED", "failed": v["failed"],
                     "reasons": [f"{k['id']}: {k['detail']}" for k in v["checks"] if not k["ok"]],
                     "generated_at": stamp}
                 for c, v in cells.items() if v["status"] != "validated"}
    return support, matrix, not_valid


def protocols_view(protos: dict) -> dict:
    """Por tipo: polling efetivo (leituras até max_wait), janela, margem e onde cada pré-condição é cumprida."""
    out = {}
    for t, p in protos.items():
        out[t] = {"polls_until_max_wait": K.n_ticks(p), "poll_interval_s": p.poll_interval_s,
                  "max_wait_s": p.max_wait_s, "window_s": p.window_s, "margin_over_ttl_s": p.margin_over_ttl_s,
                  "repetitions": p.repetitions, "tolerance": {"kind": p.tolerance_kind, "value": p.tolerance_value},
                  "needs_supervisor": p.needs_supervisor,
                  "preconditions": [{"text": txt, "enforced_by": by} for txt, by in
                                    zip(p.preconditions, PR.PRECONDITIONS.get(t, []))]}
    return out


def evidence_items(cell: str, v: dict, se: dict | None) -> list[dict]:
    items = []
    for e in (se or {}).get("evidence", []):
        if e.get("level") == "published" and "doc" in e:
            items.append({"level": "published", "doc": e["doc"]})
        elif e.get("level") == "published" and "citation" in e:
            items.append({"level": "published", "citation": e["citation"]})
        elif e.get("level") == "interpreted":
            items.append({"level": "interpreted", "model_id": e["model_id"], "note": e["note"],
                          "ref": f"$BO_DATA/SERVICE-EVIDENCE/protocol_support.jsonl#{cell}"})
    types = sorted({s["type"] for s in v["sku"]})
    attrs = {f"{s['type']}.{k}": x for s in v["sku"] for k, x in sorted(s["sku"].items())}
    sku = (", ".join(types) + " na allowlist do SAFETY; atributos de SKU "
           + (json.dumps(attrs, sort_keys=True, ensure_ascii=False) if attrs else "nenhum na tabela"))
    note = (f"validação offline do PROBEKIT {KIT_VERSION} ({v['status']}): "
            + ("S1–S9 conferem; SKU: " + sku if v["status"] == "validated" else
               "falhou " + ", ".join(v["failed"])))
    items.append({"level": "derived", "ref": f"$BO_REPO/results/PROBEKIT/support_matrix.json#{cell}", "note": note})
    return items


def write(support: dict, matrix: dict, not_valid: dict, write_mode: bool) -> list[str]:
    probs = []
    probs += compare_or_write(support_path(), support, write_mode)
    probs += compare_or_write(matrix_path(), matrix, write_mode)
    for c in C.all_cells():
        f = T.template_dir(c) / NOT_VALIDATED
        if c in not_valid:
            probs += compare_or_write(f, not_valid[c], write_mode)
        elif f.exists():
            if write_mode:
                f.unlink()
            else:
                probs.append(f"{portable(f)} sobrando: o caso está validado")
    return probs


# ------------------------------------------------------------------------------------------------ consumo
def load_support(path: Path | None = None) -> dict[str, str]:
    """{tipo/provedor: status} do protocol_support.json gravado, conferido pelo validador oficial (C22)."""
    p = Path(path or support_path())
    errs = PR.validate_contract(p)
    if errs:
        raise ProbeError(f"protocol_support.json não confere com o C22: {errs[:2]}", "CONTRACT")
    d = json.loads(p.read_text(encoding="utf-8"))
    return {f"{t['probe_type']}/{v['provider']}": v["status"] for t in d["probe_types"] for v in t["validated_support"]}


def drawable(path: Path | None = None) -> list[str]:
    """Casos que podem ser sorteados (só validated)."""
    return [c for c, s in load_support(path).items() if s == "validated"]


def invariants(support: dict, matrix: dict) -> list[str]:
    out = []
    st = {f"{t['probe_type']}/{v['provider']}": v["status"] for t in support["probe_types"]
          for v in t["validated_support"]}
    if sorted(st) != sorted(C.all_cells()):
        out.append("protocol_support.json não cobre os 24 casos tipo × provedor")
    for c in matrix["cells"]:
        allok = all(k["ok"] for k in c["checks"])
        if (c["status"] == "validated") != allok:
            out.append(f"{c['cell']}: status {c['status']} incoerente com as checagens")
        if c["drawable"] != (c["status"] == "validated") or st.get(c["cell"]) != c["status"]:
            out.append(f"{c['cell']}: sorteável sem suporte validado (ou o inverso)")
        if c["status"] == "validated" and not T.has_template(c["cell"]):
            out.append(f"{c['cell']}: validado sem template")
        if c["probe_type"] == "rate_limit" and c["status"] == "validated" and \
                not any(k["id"] == "S3" and k["ok"] for k in c["checks"]):
            out.append(f"{c['cell']}: limite de taxa validado sem janela, chave, rajada e mecanismo")
    if sorted(matrix["drawable"]) != sorted(c for c, s in st.items() if s == "validated"):
        out.append("drawable diferente dos casos validated")
    if set(matrix["drawable"]) - set(drawable_from(st)):
        out.append("drawable com caso sem suporte validado")
    return out


def drawable_from(st: dict) -> list[str]:
    return [c for c, s in st.items() if s == "validated"]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    write_mode = "--write" in argv
    try:
        support, matrix, not_valid = build()
    except ProbeError as e:
        print(f"support_matrix: RECUSA ({e.code}): {e}")
        return 1
    probs = invariants(support, matrix) + PR.precondition_problems(PR.load())
    if not probs:
        probs += write(support, matrix, not_valid, write_mode)
    if not probs:
        errs = PR.validate_contract(support_path())
        probs += [f"C22: {e}" for e in errs]
    for c in matrix["cells"]:
        mark = "SORTEÁVEL" if c["drawable"] else "fora"
        print(f"  {c['cell']:<28} {c['status']:<11} {mark:<9} {','.join(c['failed']) or '-'}")
    s = matrix["summary"]
    print(f"support_matrix: {s['validated']} validated, {s['unsupported']} unsupported, {s['unknown']} unknown; "
          f"{len(matrix['drawable'])} caso(s) sorteável(is) de 24")
    for p in probs:
        print("  PROBLEMA:", p)
    print("support_matrix:", "OK" if not probs else "REPROVADO")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
