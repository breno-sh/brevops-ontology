"""Fidelidade do leiaute: o pacote montado com a calibração PÚBLICA, materializado numa cópia do repositório,
reproduz byte a byte pilot/sto e pilot/net do git. Assim o código congelado lê as retidas exatamente como lê a
calibração (nenhum formato inventado pelo avaliador)."""
import filecmp
import subprocess

from bo.pilot_exit import common as C, materialize as M


def _copy(dest):
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["bash", "-c", f"git -C '{C.repo()}' archive HEAD pilot | tar -x -C '{dest}'"], check=True)


def _diff(a, b):
    out = []
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__"])

    def walk(c, rel=""):
        out.extend(rel + x for x in c.left_only + c.right_only + c.diff_files)
        for k, sub in c.subdirs.items():
            walk(sub, rel + k + "/")
    walk(cmp)
    return out


def test_sto_calibracao_reproduz_git(work):
    from bo.pilot_sto_oracle import cases
    _copy(work)
    g = cases.generate("calib")
    M.materialize("sto", {"fixtures": g.fixtures, "entries": g.entries}, work)
    assert _diff(str(C.repo() / "pilot/sto"), str(work / "pilot/sto")) == []


def test_net_calibracao_reproduz_git(work):
    from bo.pilot_net_oracle import calib
    _copy(work)
    M.materialize("net", {"fixtures": calib.fixtures(), "translations": calib.translations()}, work)
    assert _diff(str(C.repo() / "pilot/net"), str(work / "pilot/net")) == []


def test_sto_pacote_menor_troca_tudo(work):
    from bo.pilot_sto_oracle import cases
    _copy(work)
    g = cases.generate("calib")
    M.materialize("sto", {"fixtures": g.fixtures[:3], "entries": g.entries[:2]}, work)
    files = sorted(p.name for p in (work / "pilot/sto/fixtures_calib").rglob("*.json"))
    assert len(files) == 5


def test_manifesto_do_oraculo_confere_na_copia(work):
    from bo.pilot_sto_oracle import cases
    _copy(work)
    g = cases.generate("calib")
    M.materialize("sto", {"fixtures": g.fixtures[:4], "entries": g.entries[:3]}, work)
    r = subprocess.run(["shasum", "-a", "256", "-c", "pilot/sto/ORACLE.sha256", "--quiet"], cwd=work,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-300:]
