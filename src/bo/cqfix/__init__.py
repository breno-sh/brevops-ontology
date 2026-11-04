"""CQFIX: fixtures conforme, não conforme e incompleta das CQs, por provedor (contratos C24 e C11).

Entradas (só leitura): $BO_REPO/requirements/cq_spec.jsonl (29 CQs além do CIS, REQUIREMENTS) e
$BO_REPO/cq/cis_cross_provider.csv (CQSRC; os 8 conceitos CIS presentes nos 4 benchmarks).
Saídas: $BO_REPO/cq/fixtures/{provider}/main.tf, expected_answers.json e probes.yaml, mais a
especificação C24 das CQs CIS em results/CQFIX/cq_spec_cis.jsonl.

A resposta esperada de cada fixture é copiada da especificação (cq_spec ou cq_spec_cis), nunca calculada
por mapeador ou ontologia. Cada provedor instancia a situação abstrata com tipos do provider Terraform
fixado (universe/pins.json); o que não existe no provedor vira NOT_APPLICABLE com evidência conferível
(ausência no schema fixado) ou citação marcada como INTERPRETED.
"""
from __future__ import annotations

import os
from pathlib import Path

MODULE_ID = "CQFIX"
PROVIDERS = ("aws", "google", "azurerm", "oci")
VARIANTS = ("conforming", "nonconforming", "incomplete")
VARIANT_LETTER = {"conforming": "C", "nonconforming": "N", "incomplete": "I"}
PROVIDER_SCHEMA_DIR = {"aws": "SCHEMA-AWS", "google": "SCHEMA-GCP", "azurerm": "SCHEMA-AZURE", "oci": "SCHEMA-OCI"}
TZ = "America/Recife"


def repo_root() -> Path:
    env = os.environ.get("BO_REPO")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def data_root() -> Path:
    return Path(os.environ.get("BO_DATA") or "/Users/breno/doutorado/brevops-data")


def tmp_root() -> Path:
    p = Path(os.environ.get("BO_TMP") or (data_root() / "tmp" / MODULE_ID))
    p.mkdir(parents=True, exist_ok=True)
    return p


def fixtures_dir() -> Path:
    return repo_root() / "cq" / "fixtures"


def results_dir() -> Path:
    return repo_root() / "results" / MODULE_ID


def now_iso() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(TZ)).replace(microsecond=0).isoformat()
