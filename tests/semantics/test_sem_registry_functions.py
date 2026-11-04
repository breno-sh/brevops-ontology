"""CC-3 do PILOT-STO-MAP: função do registro fechado (enum_to_bool) na tradução não pode derrubar invert nem o
skos_roundtrip --file. Função parcial do registro é declarada não inversível: a volta é UNPROVEN (T-INVERSE)."""
import copy

import pytest

pytest.importorskip("bo.transforms.registry")

from bo.contracts import sssom as CS                      # noqa: E402
from bo.semantics import common, skos_roundtrip as RT     # noqa: E402
from bo.semantics import transforms as T                  # noqa: E402
from bo.semantics.claims import Claim, invert             # noqa: E402
from bo.semantics.content import examples as E            # noqa: E402
from bo.semantics.transport import transport              # noqa: E402

E2B = {"name": "enum_to_bool", "params": {"true": ["Enabled"], "false": ["Suspended", "Disabled"]}}


def _claim():
    c = copy.deepcopy(E.CLOSE_VERSIONING)          # status Enabled/Suspended/Disabled -> booleano, como no CC-3
    c["subject_value_type"] = E.ENUM("Enabled", "Suspended", "Disabled")
    c["translation_fn"] = E2B
    return c


def test_invert_with_registry_partial_function_does_not_raise():
    inv = invert(Claim(_claim()))
    assert inv["inverse_missing"] is True and inv["predicate_id"] == "skos:closeMatch"


def test_forward_runs_registry_function_and_inverse_is_unproven():
    c = _claim()
    assert transport(c, "Disabled")["value"] is False
    back = transport(c, True, direction="inverse")
    assert back["result"] == "blocked" and back["code"] == "UNPROVEN" and back["rule"] == "T-INVERSE"


def test_non_partial_registry_function_has_declared_inverse():
    assert T.inverse_chain_safe({"name": "bool_to_enum", "params": {"true": "Enabled", "false": "Disabled"}}) == [
        {"name": "enum_to_bool", "params": {"true": ["Enabled"], "false": ["Disabled"]}}]
    assert T.inverse_chain_safe({"name": "nao_existe_em_lugar_nenhum"}) is None


def test_file_with_enum_to_bool_passes_roundtrip():
    p = common.tmp_dir() / "rt_file_tests" / "enum_to_bool.sssom.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(CS.write_tsv([_claim(), E.BROAD_ARCHIVE], "https://example.org/mapping-set/cc3"), encoding="utf-8")
    res = RT.file_checks(p)
    assert all(c["ok"] for c in res), [c for c in res if not c["ok"]]
