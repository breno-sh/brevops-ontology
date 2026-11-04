"""E1–E8 aplicados com as regras do prereg/pilot_exit.yaml tal como estão, sobre evidência SINTÉTICA."""
import copy
from pathlib import Path

import pytest
import yaml

from bo.pilot_exit import criteria as CR, rules
from bo.pilot_exit.common import DIRECTIONS, repo

CRIT = yaml.safe_load((repo() / "prereg" / "pilot_exit.yaml").read_text(encoding="utf-8"))["criteria"]


def good_slice():
    return {"directions": {d: "OUTPUT" for d in DIRECTIONS}, "values_without_trace": 0, "silent_insertions": 0,
            "grain": {"mismatches": 0, "invariance_failures": 0},
            "claims": {"incomplete": 0, "unproven_misjudged": 0, "off_table_compositions": 0, "skos_roundtrip_ok": True},
            "oracle": {"silent_losses": 0, "negatives_carried": 0, "items": 10, "correct": 3},
            "controls": {"same_input": True, "consequences_counted": True}}


def good():
    return {"slices": {"sto": good_slice(), "net": good_slice()},
            "addendum": {"written_before_scale": True},
            "amendments": {"unversioned_changes": 0, "stale_not_marked": 0, "catalog_ok": True},
            "effort": {"steps_without_effort": 0, "schedule_recomputed": True},
            "attempts": {"attempts": 1, "expansion_blocked": False, "plan_returned_v4": False, "breno_notified": False}}


def test_oito_criterios_do_yaml():
    assert [c["id"] for c in CRIT] == [f"E{i}" for i in range(1, 9)]
    for c in CRIT:
        rules.names(c["pass_rule"])   # toda regra é legível pela gramática


def test_tudo_bom_passa_e_acerto_baixo_nao_decide():
    out = CR.evaluate(CRIT, good())
    assert all(v["pass"] for v in out.values())   # fração de acerto 3/10 não é limiar


@pytest.mark.parametrize("path,value,crit", [
    (("slices", "sto", "directions", "aws->oci"), "MISSING", "E1"),
    (("slices", "net", "values_without_trace"), 1, "E1"),
    (("slices", "sto", "silent_insertions"), 2, "E1"),
    (("slices", "net", "grain", "mismatches"), 1, "E2"),
    (("slices", "sto", "grain", "invariance_failures"), 1, "E2"),
    (("slices", "sto", "claims", "unproven_misjudged"), 1, "E3"),
    (("slices", "net", "claims", "skos_roundtrip_ok"), False, "E3"),
    (("slices", "sto", "oracle", "silent_losses"), 1, "E4"),
    (("slices", "net", "oracle", "negatives_carried"), 1, "E4"),
    (("slices", "net", "controls", "same_input"), False, "E5"),
    (("addendum", "written_before_scale"), False, "E5"),
    (("amendments", "unversioned_changes"), 3, "E6"),
    (("amendments", "catalog_ok"), False, "E6"),
    (("effort", "steps_without_effort"), 1, "E7"),
    (("attempts", "attempts"), 3, "E8"),
])
def test_cada_falha_reprova_so_o_seu_criterio(path, value, crit):
    ev = good()
    d = ev
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = value
    out = CR.evaluate(CRIT, ev)
    assert not out[crit]["pass"]
    assert all(v["pass"] for k, v in out.items() if k != crit)


def test_medida_ausente_reprova_nunca_passa():
    ev = good()
    del ev["slices"]["sto"]["oracle"]["silent_losses"]
    out = CR.evaluate(CRIT, ev)
    assert not out["E4"]["pass"] and "MISSING_MEASURE" in out["E4"]["per_slice"]["sto"]["error"]
    ev = good()
    ev["slices"] = {}
    out = CR.evaluate(CRIT, ev)
    assert not out["E1"]["pass"] and not out["E5"]["pass"]


def test_unsupported_declarado_cobre_direcao():
    ev = good()
    ev["slices"]["net"]["directions"]["oci->aws"] = "UNSUPPORTED"
    assert CR.evaluate(CRIT, ev)["E1"]["pass"]


def test_e8_terceira_tentativa_so_passa_bloqueada():
    ev = good()
    ev["attempts"] = {"attempts": 3, "expansion_blocked": True, "plan_returned_v4": True, "breno_notified": True}
    assert CR.evaluate(CRIT, ev)["E8"]["pass"]


def test_gramatica_recusa_codigo():
    with pytest.raises(rules.RuleError):
        rules.evaluate("__import__('os')", {})
    with pytest.raises(rules.RuleError):
        rules.evaluate("a.b == 1", {"a": 1})
