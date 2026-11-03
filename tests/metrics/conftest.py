"""Dados sintéticos com semente fixa e acesso aos stubs (nenhum dado do estudo)."""
import json
import os
from pathlib import Path

import numpy as np
import pytest

from bo.metrics.units import Unit, mk_attrs

ROOT = Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[2])
STUBS = ROOT / "contracts" / "stubs"


def jsonl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]


def synth(n_fam=40, per_fam=6, p_carried=0.6, p_unknown=0.1, dirs=(("aws", "google"),), seed=7, prefix="D",
          codes_unknown="INFRA_ERROR", codes_fail="NO_REALIZATION", attrs=None, fam_sd=0.15):
    """Decisões sintéticas: família ⊃ repositório ⊃ grafo; efeito de família na probabilidade de emissão."""
    rng = np.random.default_rng(seed)
    out = []
    for a, b in dirs:
        for f in range(n_fam):
            shift = rng.normal(0, fam_sd)
            for i in range(per_fam):
                r = rng.random()
                p = min(max(p_carried + shift, 0.01), 0.99)
                code = codes_unknown if r < p_unknown else ("carried" if r < p_unknown + (1 - p_unknown) * p
                                                            else codes_fail)
                extra = attrs(f, i, rng) if attrs else {}
                out.append(Unit(f"{prefix}-{a}-{b}-{f:03d}-{i:02d}", f"F-{f:04d}", f"R-{f:04d}-{i % 2}", a, b,
                                graph_id=f"G-{f:04d}-{i % 3}", resource_id=f"X-{f:04d}-{i}", codes=(code,),
                                attrs=mk_attrs(**extra)))
    return out


@pytest.fixture
def stubs():
    return STUBS
