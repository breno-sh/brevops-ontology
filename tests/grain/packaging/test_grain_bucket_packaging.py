"""4 embalagens sintéticas do mesmo contêiner de objetos → mesma decomposição; reordenar blocos não muda nada.

Embalagens (provedor sintético provider_a): blocos embutidos (inline); recursos separados com bloco de carga
útil transparente (separate); bloco invólucro + grupos de atributos (wrapped); mistura com regra de ciclo de
vida como recurso separado (mixed). Camada de schema: assinatura estrutural igual. Camada de instância: as
mesmas ocorrências (mesmo hash de identidade, mesmo grão, pai, chave e configuração normalizada).
"""

import json
import os
import subprocess
import sys

import pytest

from bo.grain import fixtures as F
from bo.grain import instance as I
from bo.grain import rules as R
from bo.grain import schema as S
from bo.grain.evidence import FixtureAdapter

RS = R.load()
SCH = F.bucket_schema()
AD = FixtureAdapter(F.bucket_evidence())
BLOCKS = F.schema_blocks(SCH)
RES = S.decompose_schema(S.candidates_from_tf_schema(F.P, SCH), AD, RS)


def rows(cfg):
    return I.canonical_rows(I.decompose_config(cfg, AD, BLOCKS, RS))


def test_four_packagings_same_schema_decomposition():
    sigs = {k: S.signature(RES, v) for k, v in F.BUCKET_PACKAGINGS.items()}
    assert len(sigs) == 4
    base = sigs["inline"]
    assert len(base) == 5
    for k, s in sigs.items():
        assert s == base, k
    grains = sorted(r[0] for r in base)
    assert grains == ["COMPONENT", "ENTITY", "FACET", "FACET", "FACET"]


def test_four_packagings_same_instance_decomposition():
    cfgs = F.bucket_configs()
    assert len(cfgs) == 4
    base = rows(cfgs["inline"])
    assert len(base) == 6  # contêiner, 3 facetas, 2 regras
    for k, cfg in cfgs.items():
        assert rows(cfg) == base, k
    # as embalagens são de fato diferentes na camada Terraform
    tfs = {k: sorted(n for o in I.decompose_config(c, AD, BLOCKS, RS) for n in o.tf) for k, c in cfgs.items()}
    assert len({json.dumps(v) for v in tfs.values()}) == 4


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize("pk", ["inline", "separate", "wrapped", "mixed"])
def test_reordering_blocks_changes_nothing(pk, seed):
    cfg = F.bucket_configs()[pk]
    assert rows(F.shuffled(cfg, seed)) == rows(cfg)


def test_reordering_is_not_vacuous():
    """Controle: o embaralhamento mexe na posição (os endereços posicionais dos blocos mudam) e uma
    identidade por posição mudaria; a nossa não muda."""
    cfg = F.bucket_configs()["inline"]
    pos = {}
    for seed in range(25):
        occ = I.decompose_config(F.shuffled(cfg, seed), AD, BLOCKS, RS)
        for o in occ:
            if o.label == "lifecycle rule":
                pos.setdefault(o.key["rule_name"], set()).add(o.tf[0])
    assert all(len(v) == 2 for v in pos.values()), pos


def test_comparison_is_sensitive_to_content():
    """Controle: mudar o nome de uma regra, o valor de uma faceta ou o nome do contêiner muda a decomposição."""
    base = rows(F.bucket_configs()["inline"])
    assert rows(F.bucket_configs(rules=[("r-new", "tmp/", 30), F.RULES_V[1]])["inline"]) != base
    assert rows(F.bucket_configs(versioning="Suspended")["inline"]) != base
    assert rows(F.bucket_configs(name="other-example")["inline"]) != base


def test_every_schema_atom_has_a_unit():
    _, atoms = S.to_c19(RES)
    n_attrs = sum(len(c.attrs) for c in RES.candidates.values())
    assert len(atoms) == n_attrs
    uids = {u["unit_id"] for u in S.to_c19(RES)[0]}
    assert all(a["unit_id"] in uids for a in atoms)


def test_c19_records_validate(tmp_path):
    units, atoms = S.to_c19(RES)
    pu, pa = tmp_path / "canonical_units.jsonl", tmp_path / "canonical_atoms.jsonl"
    pu.write_text("".join(json.dumps(u) + "\n" for u in units))
    pa.write_text("".join(json.dumps(a) + "\n" for a in atoms))
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "C19", str(pu), str(pa)],
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0, r.stdout + r.stderr
