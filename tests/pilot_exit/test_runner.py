"""Isolamento do código avaliado: sobreposição de BO_DATA e sandbox (sem escrita fora de $BO_TMP, sem rede)."""
import sys

from bo.pilot_exit import common as C, runner


def test_overlay_copia_o_proprio_e_liga_o_resto(work):
    real = work / "real"
    for d in ("PILOT-STO-E2E", "SCHEMA-AWS", "tmp", "PILOT-EXIT", "SPLIT"):
        (real / d).mkdir(parents=True)
    (real / "PILOT-STO-E2E" / "x.txt").write_text("velho")
    ov = runner.overlay(real, work / "ov", "PILOT-STO-E2E")
    assert (ov / "SCHEMA-AWS").is_symlink() and not (ov / "PILOT-STO-E2E").is_symlink()
    assert not (ov / "PILOT-EXIT").exists() and not (ov / "SPLIT").exists() and not (ov / "tmp").is_symlink()
    (ov / "PILOT-STO-E2E" / "x.txt").write_text("novo")
    assert (real / "PILOT-STO-E2E" / "x.txt").read_text() == "velho"


def test_sandbox_nega_escrita_fora_e_rede(work):
    fora = C.data() / "zz_pilot_exit_sandbox_probe.txt"
    dentro = work / "ok.txt"
    code = (f"open({str(dentro)!r},'w').write('x')\n"
            f"try:\n open({str(fora)!r},'w').write('x'); print('FORA_ESCREVEU')\nexcept OSError: print('FORA_NEGADO')\n"
            "import socket\ntry:\n socket.create_connection(('1.1.1.1',443),timeout=3); print('REDE_ABERTA')\n"
            "except OSError: print('REDE_NEGADA')\n")
    script = work / "probe.py"
    script.write_text(code)
    res = runner.run_commands([f"{sys.executable} -I {script}"], work, work / "data", "PILOT-STO-E2E", work / "logs",
                              tmp_root=work / "t")
    out = (work / "logs" / "01.out").read_text()
    assert res[0]["rc"] == 0 and "FORA_NEGADO" in out and "REDE_NEGADA" in out and dentro.exists()
    assert not fora.exists()


def test_comandos_do_catalogo_sao_os_gates_do_e2e():
    cmds = runner.catalog_gates("PILOT-STO-E2E")
    assert cmds and all(c.startswith(("python -I -m bo.pilot.", "python -I -m bo.lower.")) for c in cmds)
    assert any("--fixtures calib" in c for c in cmds)
