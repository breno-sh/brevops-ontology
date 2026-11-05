"""Diagnóstico: as sondas são Python válido e não importam nada do avaliador (rodam só com o código congelado)."""
from bo.pilot_exit import diag


def test_sondas_compilam_e_so_usam_codigo_congelado():
    for src in (diag.NET_PROBE, diag.STO_PROBE):
        compile(src, "probe", "exec")
        assert "pilot_exit" not in src
