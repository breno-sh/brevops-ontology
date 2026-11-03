"""Testes do PREREG: cálculo de poder, gates de estimandos e de termo antigo, sementes, pilotos, contratos e
determinismo. Cada gate é testado também no sentido de reprovar (arranjo quebrado de propósito), para que um
verde não prove outra coisa.

Rodar: python -I -B -m pytest tests/prereg -q -p no:cacheprovider   (temporário em $BO_TMP, nunca /tmp)
"""

from __future__ import annotations

import copy
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(REPO / "src"))

from bo.prereg import build, common, content as C, estimands, no_oldterm, pilot_exit, seeds  # noqa: E402

PW = common.power_module(REPO / "prereg" / "power.py")
TERM = C.OLD_TERMS[0]


@pytest.fixture
def tmp():
    base = Path(os.environ.get("BO_TMP") or "/Users/breno/doutorado/brevops-data/tmp/PREREG")
    d = base / f"t_{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def spec_doc():
    return common.yaml_load(common.FILES["metrics_spec"])


def power_doc():
    return json.loads(common.FILES["power_json"].read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------- fórmulas de poder
def test_wald_power_closed_form():
    # com crítico normal, n = ((z_a + z_b)·sigma1/delta)² dá exatamente o poder alvo
    za, zb = 1.6448536, 0.8416212
    n = ((za + zb) * math.sqrt(0.6 * 0.4) / 0.1) ** 2
    assert abs(PW["wald_power"](0.1, 0.24, n, PW["crit"](0.05, 1, 1, None), None, 1) - 0.80) < 1e-6
    # bilateral soma a outra cauda; Holm com k braços usa alfa/(2k)
    assert PW["crit"](0.05, 2, 7, None) > PW["crit"](0.05, 2, 1, None) > PW["crit"](0.05, 1, 1, None)
    # crítico t é maior que o normal e converge para ele
    assert PW["crit"](0.05, 1, 1, 10) > PW["crit"](0.05, 1, 1, 1000) > PW["crit"](0.05, 1, 1, None)


def test_design_effect_reduces_to_single_level():
    m = {"graph": 4, "repository": 4, "family": 4}
    rho = {"graph": 0.2, "repository": 0.2, "family": 0.2}
    assert abs(PW["design_effect"](m, rho) - (1 + 3 * 0.2)) < 1e-12
    m2 = {"graph": 3, "repository": 6, "family": 12}
    rho2 = {"graph": 0.3, "repository": 0.2, "family": 0.1}
    assert abs(PW["design_effect"](m2, rho2) - 2.8) < 1e-12
    with pytest.raises(ValueError):
        PW["design_effect"](m2, {"graph": 0.1, "repository": 0.2, "family": 0.3})


def test_sign_exact_against_scipy():
    from scipy.stats import binom
    n, p10, p01, a = 30, 0.30, 0.02, 0.05 / 7
    pd, q = p10 + p01, p10 / (p10 + p01)
    tot = 0.0
    for d in range(n + 1):
        crit = next((b for b in range(d + 1) if binom.sf(b - 1, d, 0.5) <= a), None)
        if crit is None:
            continue
        tot += binom.pmf(d, n, pd) * binom.sf(crit - 1, d, q)
    assert abs(PW["power_sign_exact"](n, p10, p01, a) - tot) < 1e-9


def test_at_least_against_enumeration():
    import itertools
    probs = [0.9, 0.8, 0.7, 0.05, 0.05]
    brute = 0.0
    for bits in itertools.product([0, 1], repeat=len(probs)):
        if sum(bits) >= 3:
            brute += math.prod(p if b else 1 - p for p, b in zip(probs, bits))
    assert abs(PW["at_least"](3, probs) - brute) < 1e-12


def test_paired_moments():
    mu, var = PW["paired_moments"]({"11": 0.52, "10": 0.03, "01": 0.03, "00": 0.42}, 0.95)
    assert abs(mu - (0.55 - 0.95 * 0.55)) < 1e-12
    assert var > 0
    with pytest.raises(ValueError):
        PW["paired_moments"]({"11": 0.5, "10": 0.1, "01": 0.1, "00": 0.1}, 1.0)


def test_t_distribution_against_scipy():
    from scipy.stats import t
    for df in (2, 5, 17, 60, 400):
        assert abs(PW["t_ppf"](0.975, df) - t.ppf(0.975, df)) < 1e-9
        assert abs(PW["t_cdf"](-0.7, df) - t.cdf(-0.7, df)) < 1e-12


def test_monte_carlo_confirms_clustered_power():
    """Simulação: dados binários com correlação intracluster por família (beta-binomial), analisados como a
    análise fará (IC t com gl = famílias - 1 sobre as médias das famílias). O poder simulado tem de bater com o
    analítico de power.py (n / DE, Wald sob a alternativa, crítico t) no regime dos n do pré-registro
    (27 a 90 famílias): nunca otimista além de 0,03, conservador no máximo 0,06."""
    import numpy as np
    from scipy.stats import t
    rng = np.random.default_rng(seeds.derive("SEED-POWER-SIM"))
    cases = [(0.70, 0.60, 0.10, 10, (27, 45, 90)), (0.10, 0.15, 0.20, 6, (90,)), (0.90, 0.80, 0.10, 2, (45, 90))]
    for p0, p1, rho, m, fams in cases:
        de = 1 + (m - 1) * rho
        c = {"model": "one_prop", "planning": {"p0": p0, "p1": p1}, "alpha": 0.05, "sides": 1}
        ab = (1 - rho) / rho
        for fam in fams:
            reps, rej = 4000, 0
            tc = t.ppf(0.95, fam - 1)
            for _ in range(reps):
                y = rng.binomial(m, rng.beta(p1 * ab, (1 - p1) * ab, size=fam)) / m
                h = tc * y.std(ddof=1) / math.sqrt(fam)
                rej += (y.mean() + h < p0) if p1 < p0 else (y.mean() - h > p0)
            sim, ana = rej / reps, PW["power_t"](c, fam, m, de)
            # nunca otimista (n pré-registrado pequeno demais) além de 0,03; conservador no máximo 0,06
            assert ana <= sim + 0.03 and sim - ana < 0.06, (p0, p1, fam, sim, ana)
    # o arranjo que ignora a correlação (DE = 1) superestima muito o poder
    c = {"model": "one_prop", "planning": {"p0": 0.7, "p1": 0.6}, "alpha": 0.05, "sides": 1}
    assert PW["power_t"](c, 27, 10, 1.0) > PW["power_t"](c, 27, 10, 1.9) + 0.15


# ------------------------------------------------------------------------------------------- power.json
def test_power_check_green():
    errs = PW["check"](common.FILES["power_json"], common.FILES["metrics_spec"])
    assert errs == []


def test_power_semantic_catches_missing_correlation():
    d = power_doc()
    ids = {m["metric_id"] for m in spec_doc()["metrics"]}
    assert PW["semantic"](d, ids) == []
    d1 = copy.deepcopy(d)
    d1["data"]["cluster_model"]["rho"]["repository"] = 0
    assert any("família E por repositório" in e for e in PW["semantic"](d1, ids))
    d2 = copy.deepcopy(d)
    d2["data"]["design_effect_census"] = 1.0
    assert any("efeito de desenho" in e for e in PW["semantic"](d2, ids))


def test_power_semantic_catches_underpowered_claim():
    d = power_doc()
    ids = {m["metric_id"] for m in spec_doc()["metrics"]}
    d1 = copy.deepcopy(d)
    h1 = next(c for c in d1["data"]["contrasts"] if c["contrast_id"] == "C-H1")
    h1["result"]["overall_power"] = 0.6
    assert any("C-H1: poder conjunto" in e for e in PW["semantic"](d1, ids))
    d2 = copy.deepcopy(d)
    h4 = next(c for c in d2["data"]["contrasts"] if c["contrast_id"] == "C-H4")
    h4["feasibility"]["cap"] = 50
    assert any("C-H4" in e and "acima do limite" in e for e in PW["semantic"](d2, ids))
    d3 = copy.deepcopy(d)
    d3["data"]["contrasts"] = [c for c in d3["data"]["contrasts"] if c["hypothesis"] != "H3"]
    assert any("H3 sem contraste" in e for e in PW["semantic"](d3, ids))
    d4 = copy.deepcopy(d)
    beh = next(c for c in d4["data"]["contrasts"] if c["contrast_id"] == "C-BEHAV")
    beh["alpha"] = 0.05
    assert any("descritivo não pode trazer teste" in e for e in PW["semantic"](d4, ids))
    assert any("fora do metrics_spec" in e for e in PW["semantic"](d, ids - {"M-OPCOV-DEC"}))


def test_power_check_detects_tampering(tmp):
    p = tmp / "power.json"
    d = power_doc()
    d["data"]["contrasts"][0]["result"]["n_units"] -= 1
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    assert any("difere do recalculado" in e for e in PW["check"](p, common.FILES["metrics_spec"]))


def test_power_cli_gate():
    r = subprocess.run([sys.executable, "-I", str(common.FILES["power_py"]), "--check", str(common.FILES["power_json"])],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_claimed_contrast_models_family_and_repository():
    d = power_doc()["data"]
    for c in d["contrasts"]:
        if c["status"] == "descriptive":
            continue
        if c["result"]["kind"] == "normal":
            assert c["result"]["design_effect"] > 1.3, c["contrast_id"]
            assert len(c["sensitivity"]) == 9


def test_h9_fixture_scale_is_underpowered_and_declared():
    h9 = next(c for c in power_doc()["data"]["contrasts"] if c["contrast_id"] == "C-H9")
    assert h9["result"]["power_at_fixture_scale"] < 0.1
    assert h9["result"]["n_cases_per_family"] > h9["planning"]["fixture_scale_n"]
    assert "inconclusivo" in h9["feasibility"]["rule"]


# ------------------------------------------------------------------------------------------- estimandos
def test_estimands_green():
    errs, _ = estimands.run(common.FILES["metrics_spec"], common.FILES["power_json"], common.C00_SCHEMA)
    assert errs == []


def _mut(spec, mid, fn):
    s = copy.deepcopy(spec)
    m = next(x for x in s["metrics"] if x["metric_id"] == mid)
    fn(m)
    return s


def test_estimands_catch_missing_clause():
    s = _mut(spec_doc(), "M-OPCOV-DEC", lambda m: m.update(
        definition=common.SEP.join(m["definition"].split(common.SEP)[:-1])))
    assert any(e.startswith("E-CLAUSES M-OPCOV-DEC") for e in estimands.check_spec(s))


def test_estimands_catch_unit_mismatch():
    s = _mut(spec_doc(), "M-OPCOV-FIELD", lambda m: m.update(reading="decision"))
    assert any(e.startswith("E-UNIT M-OPCOV-FIELD") for e in estimands.check_spec(s))


def test_estimands_catch_unknown_without_bounds_or_codes():
    s = _mut(spec_doc(), "M-PERS-DEC", lambda m: m.update(definition=m["definition"].replace("limite superior", "outro")))
    assert any(e.startswith("E-UNKNOWN M-PERS-DEC") for e in estimands.check_spec(s))
    s2 = _mut(spec_doc(), "M-PERS-DEC", lambda m: m.update(definition=m["definition"].replace("NOT_READABLE", "X")))
    assert any("NOT_READABLE" in e for e in estimands.check_spec(s2))


def test_estimands_catch_denominator_by_line():
    s = _mut(spec_doc(), "M-OPCOV-DEC", lambda m: m.update(
        definition=m["definition"].replace("por decisão, não por linha", "por linha")))
    assert any(e.startswith("E-DENOM M-OPCOV-DEC") for e in estimands.check_spec(s))


def test_estimands_catch_nametag_inside():
    s = _mut(spec_doc(), "M-OPCOV-GRAPH", lambda m: m.update(inclusion="INC-GRAPH-01: todos os grafos"))
    assert any(e.startswith("E-NAMETAG M-OPCOV-GRAPH") for e in estimands.check_spec(s))


def test_estimands_catch_missing_quantifier_and_reading():
    s = copy.deepcopy(spec_doc())
    s["metrics"] = [m for m in s["metrics"] if m["metric_id"] not in ("M-TRANS-DEC-UNIV", "M-OPCOV-UNIT")]
    errs = estimands.check_spec(s)
    assert any("E-QUANT" in e and "universal" in e for e in errs)
    assert any("E-LADDER" in e and "complete_unit" in e for e in errs)


def test_policy_against_c00_enums():
    c00 = json.loads(common.C00_SCHEMA.read_text(encoding="utf-8"))
    assert estimands.check_policy(c00) == []
    c2 = copy.deepcopy(c00)
    c2["$defs"]["block_code"]["enum"].append("NEW_CODE_FROM_CONTRACT")
    assert any("NEW_CODE_FROM_CONTRACT" in e for e in estimands.check_policy(c2))


def test_registry_detects_hand_edit():
    s = _mut(spec_doc(), "M-REPR-DEC", lambda m: m.update(frame="outro frame qualquer"))
    assert estimands.check_registry(s)


# ------------------------------------------------------------------------------------------- termo antigo
def test_no_oldterm_green():
    errs, info = no_oldterm.scan(no_oldterm.scope())
    assert errs == [] and info["note_present"]


def test_no_oldterm_catches_term_outside_note(tmp):
    good = common.FILES["html"].read_text(encoding="utf-8")
    bad = good.replace("<h2 id=\"escada\">", f"<p>o {TERM} voltou</p><h2 id=\"escada\">", 1)
    p = tmp / "PREREG.html"
    p.write_text(bad, encoding="utf-8")
    errs, _ = no_oldterm.scan([p])
    assert any(e.startswith("T-TEXT") for e in errs)


def test_no_oldterm_catches_yaml_key_and_code(tmp):
    y = tmp / "x.yaml"
    y.write_text(f"a:\n  max_{C.OLD_TERMS[2]}: 1\n", encoding="utf-8")
    errs, _ = no_oldterm.scan([y])
    assert any(e.startswith("T-KEY") for e in errs)
    py = tmp / "x.py"
    py.write_text(f"x = '{TERM}'\n# {no_oldterm.MARK_A}\ny = '{TERM}'\n# {no_oldterm.MARK_B}\n", encoding="utf-8")
    errs, _ = no_oldterm.scan([py])
    assert [e for e in errs if "x.py:1" in e] and not [e for e in errs if "x.py:3" in e]


def test_no_oldterm_requires_the_note(tmp):
    html_txt = common.FILES["html"].read_text(encoding="utf-8").replace('id="nota-renomeacao"', 'id="outra"')
    q = tmp / common.FILES["html"].name
    q.write_text(html_txt, encoding="utf-8")
    errs, info = no_oldterm.scan([q])
    assert any(e.startswith("T-NOTE") for e in errs) and not info["note_present"]
    # sem a nota, o termo que estava nela passa a contar como fora dela
    assert any(e.startswith("T-TEXT") for e in errs)


def test_word_boundary_does_not_flag_compounds():
    # 'arquiteto' contém a sequência, mas não é o termo
    assert not no_oldterm.TERM_RE.search("o arquiteto do sistema")
    assert no_oldterm.TERM_RE.search(f"o {TERM.upper()} da v2")


# ------------------------------------------------------------------------------------------- sementes, pilotos, sondas
def test_seeds_green_and_tamper(tmp):
    assert seeds.check(common.FILES["seeds"]) == []
    t = common.FILES["seeds"].read_text(encoding="utf-8").replace(str(seeds.derive("SEED-SPLIT")), "123", 1)
    p = tmp / "SEEDS.txt"
    p.write_text(t, encoding="utf-8")
    assert any("SEED-SPLIT" in e for e in seeds.check(p))
    assert seeds.derive("SEED-SPLIT") == seeds.derive("SEED-SPLIT") and seeds.derive("SEED-SPLIT") != seeds.derive("SEED-BOOT")


def test_pilot_exit_green_and_mutations():
    doc = common.yaml_load(common.FILES["pilot_exit"])
    assert pilot_exit.check(doc) == []
    d1 = copy.deepcopy(doc)
    d1["criteria"][3]["pass_rule"] = "cobertura >= 0.8"
    assert any("cobertura" in e for e in pilot_exit.check(d1))
    d2 = copy.deepcopy(doc)
    d2["criteria"] = d2["criteria"][:-1]
    assert any("critérios" in e for e in pilot_exit.check(d2))
    d3 = copy.deepcopy(doc)
    d3["reasoning_controls_rule"]["outcomes"] = d3["reasoning_controls_rule"]["outcomes"][:2]
    assert any("desfechos dos controles" in e for e in pilot_exit.check(d3))
    d4 = copy.deepcopy(doc)
    d4["attempts_max"] = 3
    assert any("attempts_max" in e for e in pilot_exit.check(d4))


def _dur_h(s: str) -> float:
    import re
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", s)
    d, h, mi, se = (int(x) if x else 0 for x in m.groups())
    return d * 24 + h + mi / 60 + se / 3600


def test_probe_types_protocol_window_margin_cost():
    doc = common.yaml_load(common.FILES["probe_types"])
    types = [p["probe_type"] for p in doc["probe_types"]]
    assert types == ["object_versioning", "object_lifecycle", "item_ttl", "queue_retention", "rate_limit",
                     "log_retention"]
    for p in doc["probe_types"]:
        w, m = _dur_h(p["window"]["duration"]), _dur_h(p["window"]["margin_over_ttl"])
        assert 0 < m < w, p["probe_type"]
        assert _dur_h(p["polling"]["max_wait"]) <= w and _dur_h(p["polling"]["interval"]) < w
        assert p["cost_limit"]["amount"] > 0 and p["repetitions"] >= 3
        assert all(s["status"] == "unknown" and s["evidence"] == [] for s in p["validated_support"])
        if w >= 24:
            assert any("D16" in x for x in p["preconditions"]), p["probe_type"]
    rl = next(p for p in doc["probe_types"] if p["probe_type"] == "rate_limit")
    txt = " ".join(rl["preconditions"])
    for k in ("JANELA", "CHAVE", "RAJADA", "MECANISMO"):
        assert k in txt


def test_h2h_refs_and_equal_budget():
    doc = common.yaml_load(common.FILES["h2h_fairness"])
    assert doc["cq_ref"]["sha256"] == common.sha_file(common.CQ_SPEC)
    assert doc["universe_ref"]["sha256"] == common.sha_file(common.FILES["metrics_spec"])
    b = doc["budget"]["per_comparator"]
    assert all(c["budget_hours"] == b and c["same_universe"] and c["same_cqs"] for c in doc["comparators"])
    assert len({c["comparator_id"] for c in doc["comparators"]}) == 12


# ------------------------------------------------------------------------------------------- contratos e build
@pytest.mark.parametrize("kind,key", [("results", "metrics_spec"), ("results", "power_json"),
                                      ("probes", "probe_types"), ("C28", "h2h_fairness")])
def test_contracts_validate(kind, key):
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", kind, str(common.FILES[key])],
                       capture_output=True, text=True, env={**os.environ, "BO_REPO": str(REPO)})
    assert r.returncode == 0, r.stdout + r.stderr


def test_build_is_deterministic_and_published():
    a, b = build.produce(), build.produce()
    assert a == b
    for p, txt in a.items():
        assert p.read_text(encoding="utf-8") == txt, p


def test_metric_definitions_have_no_separator_inside_clauses():
    for m in C.METRICS:
        for k in ("definition", "population", "direction", "unit", "denominator", "unknown"):
            assert common.SEP not in m[k], (m["metric_id"], k)


def test_manifest_covers_outputs():
    lines = common.MANIFEST.read_text(encoding="utf-8").splitlines()
    paths = {ln.split("  ", 1)[1] for ln in lines}
    for p in common.FILES.values():
        assert p.relative_to(common.REPO).as_posix() in paths
    for ln in lines:
        sha, rel = ln.split("  ", 1)
        assert common.sha_file(common.REPO / rel) == sha, rel
