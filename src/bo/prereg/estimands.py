"""Gate: cada métrica declara população, direção, unidade, denominador e tratamento do desconhecido.

  python -I -m bo.prereg.estimands [--spec ARQ] [--power ARQ]

Confere, sobre o metrics_spec.yaml publicado (não sobre o conteúdo em memória):
  E-CLAUSES   a definição de toda métrica tem as seis cláusulas rotuladas, nessa ordem, cada uma com texto
  E-UNIT      a cláusula Unidade bate com a leitura do C15 (field, decision, graph, complete_unit)
  E-UNKNOWN   a cláusula Desconhecido fala dos dois limites e nomeia os códigos do eixo
  E-DENOM     leitura por decisão: denominador fixado antes do tradutor, JSON de política por decisão e não por
              linha, NAME e TAG fora
  E-NAMETAG   NAME/TAG fora de toda leitura operacional, menos a própria (M-OPCOV-NAMETAG)
  E-DIRECTION a cláusula Direção declara a direção A→B ou se declara não direcional
  E-LADDER    os cinco eixos presentes; a cobertura operacional nas quatro leituras; uma métrica principal
              (M-OPCOV-DEC, decisão, eixo operacional)
  E-QUANT     transportabilidade declarada com os três quantificadores (existencial, universal, uso)
  E-POLICY    a tabela de desconhecido classifica todo valor das enumerações do C00 (block_code e os dois
              desfechos) exatamente uma vez, com o C00 lido de contracts/
  E-OTHER     estimandos fora do C15 com os mesmos seis atributos
  E-POWER     todo contraste de power.json cita só métricas do spec e estimandos registrados
  E-REGISTRY  o spec publicado tem exatamente as métricas do conteúdo (mesmos ids e mesma definição)
Relatório em $BO_DATA/PREREG/estimands_check.json. Sai 0 só sem erro.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import common, content as C

UNIT_OF_READING = {"field": "campo", "decision": "decisão", "graph": "grafo",
                   "complete_unit": "unidade implantável completa"}
AXES = ["representability", "transportability", "operational", "persistence", "behavior"]
READINGS = ["field", "decision", "graph", "complete_unit"]


def check_spec(spec: dict) -> list[str]:
    errs: list[str] = []
    ms = spec.get("metrics") or []
    if not ms:
        return ["E-CLAUSES: metrics_spec sem métricas"]
    for m in ms:
        mid = m.get("metric_id", "?")
        text = m.get("definition", "")
        parts = [p.partition(": ") for p in text.split(common.SEP)]
        labels = [p[0].strip() for p in parts]
        if labels != common.CLAUSES:
            errs.append(f"E-CLAUSES {mid}: cláusulas {labels} != {common.CLAUSES}")
            continue
        cl = {p[0].strip(): p[2].strip() for p in parts}
        for lab in common.CLAUSES:
            if len(cl[lab]) < 5:
                errs.append(f"E-CLAUSES {mid}: cláusula {lab} vazia ou curta")
        want_unit = UNIT_OF_READING.get(m.get("reading"))
        if cl["Unidade"] != want_unit:
            errs.append(f"E-UNIT {mid}: Unidade '{cl['Unidade']}' não bate com reading {m.get('reading')} ({want_unit})")
        unk = cl["Desconhecido"]
        if "limite inferior" not in unk or "limite superior" not in unk:
            errs.append(f"E-UNKNOWN {mid}: Desconhecido sem os dois limites")
        for code in C.AXIS_UNKNOWN_CODES.get(m.get("axis"), []):
            if code not in unk:
                errs.append(f"E-UNKNOWN {mid}: Desconhecido não nomeia {code} (eixo {m.get('axis')})")
        den = cl["Denominador"]
        if m.get("reading") == "decision":
            if m.get("axis") == "behavior":
                need = ["um por decisão"]                       # um par de sonda por decisão sondada
            elif m.get("axis") == "persistence" and mid != "M-OPCOV-PERS-DEC":
                need = ["por decisão, não por linha"]           # casos sorteados: o frame fixa o denominador
            elif mid == "M-OPCOV-DEC-COMPLEX":
                need = ["por decisão, não por linha", "NAME e TAG fora"]  # base = emitidas no limite inferior
            else:
                need = ["antes de rodar o tradutor", "por decisão, não por linha", "NAME e TAG fora"]
            for n in need:
                if n not in den:
                    errs.append(f"E-DENOM {mid}: Denominador sem '{n}'")
        if m.get("axis") == "operational":
            inc = m.get("inclusion", "")
            if mid == "M-OPCOV-NAMETAG":
                if "só papéis NAME e TAG" not in inc:
                    errs.append(f"E-NAMETAG {mid}: leitura própria sem restringir a NAME e TAG")
            elif "NAME e TAG" not in inc or "fora" not in inc:
                errs.append(f"E-NAMETAG {mid}: inclusão não tira NAME e TAG")
        dirc = cl["Direção"]
        if not ("A→B" in dirc or "não direcional" in dirc or "direção" in dirc):
            errs.append(f"E-DIRECTION {mid}: Direção não declara A→B nem 'não direcional'")
    axes = {m.get("axis") for m in ms}
    for a in AXES:
        if a not in axes:
            errs.append(f"E-LADDER: eixo {a} sem métrica")
    op_readings = {m.get("reading") for m in ms if m.get("axis") == "operational"}
    for r in READINGS:
        if r not in op_readings:
            errs.append(f"E-LADDER: cobertura operacional sem a leitura {r}")
    prim = [m for m in ms if m.get("metric_id") == "M-OPCOV-DEC"]
    if len(prim) != 1 or prim[0].get("reading") != "decision" or prim[0].get("axis") != "operational":
        errs.append("E-LADDER: métrica principal M-OPCOV-DEC ausente ou fora de (decisão, operacional)")
    q = {m.get("quantifier") for m in ms if m.get("axis") == "transportability"}
    for qq in ("existential", "universal", "observed_fraction"):
        if qq not in q:
            errs.append(f"E-QUANT: transportabilidade sem o quantificador {qq}")
    return errs


def check_policy(c00: dict) -> list[str]:
    errs = []
    defs = c00["$defs"]
    enums = {
        "block_code": defs["block_code"]["enum"],
        "outcome_persistence": defs["outcome_persistence"]["properties"]["value"]["enum"],
        "outcome_behavior": defs["outcome_behavior"]["properties"]["value"]["enum"],
    }
    for k, vals in enums.items():
        pol = C.BOUND_POLICY.get(k, {})
        for v in vals:
            if v not in pol:
                errs.append(f"E-POLICY {k}: valor {v} do C00 sem classe na política do desconhecido")
            elif pol[v] not in C.BOUND_CLASSES:
                errs.append(f"E-POLICY {k}: {v} com classe inválida {pol[v]}")
        for v in pol:
            if v not in vals:
                errs.append(f"E-POLICY {k}: {v} na política mas não no C00")
    # todo código que conta como 'bounded' tem de aparecer na cláusula de algum eixo
    named = {c for cs in C.AXIS_UNKNOWN_CODES.values() for c in cs}
    for k in enums:
        for v, cls in C.BOUND_POLICY[k].items():
            if cls == "bounded" and v not in named:
                errs.append(f"E-POLICY {k}: {v} é 'bounded' mas nenhum eixo o nomeia")
    return errs


def check_other() -> list[str]:
    errs = []
    keys = ["definition", "population", "direction", "unit", "denominator", "unknown"]
    for x in C.OTHER_ESTIMANDS:
        for k in keys:
            if len(str(x.get(k) or "")) < 5:
                errs.append(f"E-OTHER {x.get('estimand_id')}: sem {k}")
        if not ("limite" in x["unknown"] or "censura" in x["unknown"] or "mínimo e máximo" in x["unknown"]
                or "dois limites" in x["unknown"]):
            errs.append(f"E-OTHER {x['estimand_id']}: desconhecido sem limites ou censura")
    return errs


def check_power(power: dict, spec: dict) -> list[str]:
    errs = []
    ids = {m["metric_id"] for m in spec["metrics"]}
    est = {x["estimand_id"] for x in C.OTHER_ESTIMANDS}
    for c in power["data"]["contrasts"]:
        for mid in c.get("metrics", []):
            if mid not in ids:
                errs.append(f"E-POWER {c['contrast_id']}: métrica {mid} fora do spec")
        for eid in c.get("estimands", []):
            if eid not in est:
                errs.append(f"E-POWER {c['contrast_id']}: estimando {eid} não registrado")
        if not c.get("metrics") and not c.get("estimands"):
            errs.append(f"E-POWER {c['contrast_id']}: contraste sem estimando")
    for x in C.OTHER_ESTIMANDS:
        if x["contrast"] and x["contrast"] not in {c["contrast_id"] for c in power["data"]["contrasts"]}:
            errs.append(f"E-POWER {x['estimand_id']}: contraste {x['contrast']} não existe em power.json")
    return errs


def check_registry(spec: dict) -> list[str]:
    from . import build
    want = build.metrics_spec()["metrics"]
    got = spec["metrics"]
    if [m["metric_id"] for m in got] != [m["metric_id"] for m in want]:
        return ["E-REGISTRY: ids do spec publicado diferem do conteúdo"]
    return [f"E-REGISTRY {g['metric_id']}: spec publicado difere do conteúdo" for g, w in zip(got, want) if g != w]


def run(spec_path: Path, power_path: Path, c00_path: Path) -> tuple[list[str], dict]:
    spec = common.yaml_load(spec_path)
    power = json.loads(power_path.read_text(encoding="utf-8"))
    c00 = json.loads(c00_path.read_text(encoding="utf-8"))
    groups = {
        "spec": check_spec(spec), "policy": check_policy(c00), "other": check_other(),
        "power": check_power(power, spec), "registry": check_registry(spec),
    }
    errs = [e for g in groups.values() for e in g]
    rep = {"module": "PREREG", "check": "estimands",
           "at": dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="seconds"),
           "spec": common.portable(spec_path) if spec_path.resolve().is_relative_to(common.REPO.resolve()) else str(spec_path),
           "n_metrics": len(spec["metrics"]), "n_other_estimands": len(C.OTHER_ESTIMANDS),
           "errors": errs, "ok": not errs}
    return errs, rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="confere os estimandos do pré-registro")
    ap.add_argument("--spec", default=str(common.FILES["metrics_spec"]))
    ap.add_argument("--power", default=str(common.FILES["power_json"]))
    ap.add_argument("--c00", default=str(common.C00_SCHEMA))
    ap.add_argument("--no-report", action="store_true")
    a = ap.parse_args(argv)
    errs, rep = run(Path(a.spec), Path(a.power), Path(a.c00))
    if not a.no_report:
        common.OUT_DATA.mkdir(parents=True, exist_ok=True)
        (common.OUT_DATA / "estimands_check.json").write_text(common.json_dump(rep), encoding="utf-8")
    for x in errs:
        print("FAIL", x)
    if errs:
        print(f"RESULTADO: REPROVADO ({len(errs)})")
        return 1
    print(f"RESULTADO: OK ({rep['n_metrics']} métricas e {rep['n_other_estimands']} estimandos declaram população, "
          "direção, unidade, denominador e desconhecido)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
