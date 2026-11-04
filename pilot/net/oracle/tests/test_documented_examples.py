"""G1: o avaliador reproduz os exemplos documentados de cada provedor (frases da doc fixada via SERVICE-EVIDENCE)."""
import pytest

import net_oracle as no
from conftest import ORACLE, load

EX = load(ORACLE / "documented_examples.json")["examples"]


def test_todo_provedor_tem_exemplo():
    assert {e["provider"] for e in EX} == {"aws", "google", "azurerm", "oci"}


@pytest.mark.parametrize("ex", EX, ids=[e["example_id"] for e in EX])
def test_exemplo(ex):
    r = no.evaluate_fixture(ex["fixture"])
    got = {k: v["value"] for k, v in r["decisions"].items()}
    assert got == {k: v["value"] for k, v in ex["expected"]["decisions"].items()}, ex["quote"]
    assert r["validity"]["value"] == ex["expected"]["validity"]["value"]
