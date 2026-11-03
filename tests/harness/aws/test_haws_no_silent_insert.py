"""Gate de inserção silenciosa: render limpo sem achados; cada mutação plantada é pega."""
import json
import shutil

import pytest

from bo.harness.aws import no_silent_insert as nsi


def test_clean_render_has_no_findings(rendered):
    out, _ = rendered
    rep = nsi.check_render(out)
    assert rep["findings"] == []
    assert rep["counts"]["RENDERED"] == 4 and rep["counts"]["UNKNOWN_INPUT"] == 3


@pytest.mark.parametrize("mut", nsi.MUTATIONS, ids=[m[0].split()[0] for m in nsi.MUTATIONS])
def test_each_mutation_is_caught(rendered, work, mut):
    out, _ = rendered
    d = work / "m"
    shutil.copytree(out, d)
    name, fname, old, new = mut
    nsi._edit(d / fname, old, new)
    assert nsi.check_render(d)["findings"], name


def test_extra_file_is_caught(rendered, work):
    out, _ = rendered
    d = work / "m"
    shutil.copytree(out, d)
    (d / "override.tf").write_text('resource "aws_vpc" "x" {\n}\n')
    assert any(f["where"] == "override.tf" for f in nsi.check_render(d)["findings"])


def test_gate_main_passes_and_writes_report(work):
    rep = work / "nsi.json"
    assert nsi.main(["--report", str(rep)]) == 0
    d = json.loads(rep.read_text())
    assert d["verdict"] == "PASS" and d["totals"]["mutations_caught"] == d["totals"]["mutations"] == len(nsi.MUTATIONS)
