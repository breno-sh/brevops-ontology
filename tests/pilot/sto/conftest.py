import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(scope="session")
def ev():
    from bo.pilot.sto import evidence as EV
    return EV.Evidence.load()


@pytest.fixture(scope="session")
def syn():
    import synth
    return synth.claimset()


@pytest.fixture(scope="session")
def ctx_syn(syn, tmp_path_factory):
    from bo.pilot.sto import pipeline as PL
    return PL.prepare(claims=syn, out_dir=tmp_path_factory.mktemp("owl_syn"))


@pytest.fixture(scope="session")
def expected():
    from bo.pilot.sto import common as C
    return C.read_json(C.repo() / "pilot" / "sto" / "expected_answers.json")
