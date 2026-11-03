"""Gates do módulo chamados como o catálogo os chama: no_silent_insert e regeneração do índice do schema."""
import subprocess
import sys

from bo.harness.google import common as C
from bo.harness.google import no_silent_insert as N


def test_no_silent_insert_passa_e_pega_todos_os_controles():
    assert N.main([]) == 0
    import json
    rep = json.loads((C.module_data() / "no_silent_insert.json").read_text())
    assert rep["verdict"] == "PASS" and rep["plans_checked"] >= 5 and rep["leaves_checked"] > 0
    assert all(x["caught"] for x in rep["negative_controls"]) and len(rep["negative_controls"]) >= 10


def test_indice_do_schema_regenera_identico():
    p = subprocess.run([sys.executable, "-I", "-m", "bo.harness.google.schema_index", "--check"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


def test_indice_bate_com_o_pin():
    import json
    d = json.loads((C.templates() / "schema_index.json").read_text())
    pin = C.provider_pin()
    assert (d["version"], d["schema_sha256"]) == (pin["version"], pin["schema_sha256"])


def test_rodada_offline_com_todas_as_gravacoes():
    from bo.harness.google import offline_run
    assert offline_run.main([]) == 0
    import json
    rep = json.loads((C.module_data() / "offline_run" / "offline_run_report.json").read_text())
    assert rep["verdict"] == "PASS" and rep["recordings"] >= 9 and not rep["c12_errors"]
    assert {c["outcome"] for c in rep["checks"]} >= {"PERSISTED", "ALTERED", "REJECTED_BY_API", "INFRA_ERROR",
                                                     "NOT_READABLE", "UNKNOWN"}
