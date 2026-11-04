"""Código congelado: num repositório git SINTÉTICO, o sha do código do E2E na base tem de ser o da entrega."""
import json
import subprocess

from bo.pilot_exit import frozen as F


def g(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)


def repo_with_delivery(root):
    root.mkdir(parents=True, exist_ok=True)
    g(root, "init", "-q", "-b", "bo/base")
    g(root, "config", "user.email", "t@example.org")
    g(root, "config", "user.name", "t")
    (root / "src/bo/pilot/sto").mkdir(parents=True)
    (root / "src/bo/pilot/sto/run.py").write_text("X = 1\n")
    (root / "src/bo/pilot_sto_e2e").mkdir(parents=True)
    (root / "src/bo/pilot_sto_e2e/__init__.py").write_text("")
    g(root, "add", "-A")
    g(root, "commit", "-q", "-m", "[PILOT-STO-E2E] entrega")
    return root


def test_codigo_igual_ao_da_entrega(work):
    r = repo_with_delivery(work / "r")
    (r / "outro.txt").write_text("y")
    g(r, "add", "-A")
    g(r, "commit", "-q", "-m", "[OUTRO] mexe em outra coisa")
    i = F.identify("sto", r)
    assert i["match"] and i["files"] == 2 and len(i["code_sha256"]) == 64


def test_codigo_mudado_depois_da_entrega_para(work):
    r = repo_with_delivery(work / "r")
    (r / "src/bo/pilot/sto/run.py").write_text("X = 2\n")
    g(r, "commit", "-qam", "[COORD] ajuste")
    i = F.identify("sto", r)
    assert not i["match"] and "mudou depois da entrega" in i["problems"][0]


def test_manifesto_do_produtor_diferente_para(work):
    r = repo_with_delivery(work / "r")
    (r / "results/PILOT-STO-E2E").mkdir(parents=True)
    (r / "results/PILOT-STO-E2E/MANIFEST.sha256").write_text("0" * 64 + "  src/bo/pilot/sto/run.py\n")
    (r / "results/PILOT-STO-E2E/summary.json").write_text(json.dumps(
        {"agent_provenance": {"params": {"code_sha256": "f" * 64}}}))
    g(r, "add", "-A")
    g(r, "commit", "-q", "-m", "[PILOT-STO-E2E] resultados")
    i = F.identify("sto", r)
    assert not i["match"] and len(i["problems"]) == 2


def test_sem_entrega_e_erro(work):
    r = work / "r"
    r.mkdir()
    g(r, "init", "-q", "-b", "bo/base")
    g(r, "config", "user.email", "t@example.org")
    g(r, "config", "user.name", "t")
    (r / "a").write_text("a")
    g(r, "add", "-A")
    g(r, "commit", "-q", "-m", "[REPO] base")
    try:
        F.identify("net", r)
    except F.FrozenError as e:
        assert "ainda não está" in str(e)
    else:
        raise AssertionError("devia recusar")


def test_export_e_copia_inteira(work):
    r = repo_with_delivery(work / "r")
    d = F.export(r, "bo/base", work / "x")
    assert (d / "src/bo/pilot/sto/run.py").read_text() == "X = 1\n" and not (d / ".git").exists()
