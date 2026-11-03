"""skos_roundtrip --file: lê ESSE arquivo (bo.contracts.sssom) e testa a ida e volta das linhas dele.
Reprovam o comportamento antigo (que ignorava --file e saía 0 com o autoteste): arquivo inexistente, vazio, só
cabeçalho ou com direção invertida tem de sair != 0."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bo.semantics import common, skos_roundtrip as RT
from bo.semantics.content import examples as E

EXAMPLES = common.repo() / "results" / "SEMANTICS" / "C09_proposta" / "examples.sssom.tsv"


def run(*args):
    env = dict(os.environ, BO_REPO=str(common.repo()))
    r = subprocess.run([sys.executable, "-I", "-m", "bo.semantics.skos_roundtrip", *args], capture_output=True,
                       text=True, env=env, timeout=300)
    return r.returncode, r.stdout + r.stderr


def tmpfile(name, text):
    p = common.tmp_dir() / "rt_file_tests" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_fails():
    rc, out = run("--file", "/nao/existe.tsv")
    assert rc != 0 and "não existe" in out and "23/23" not in out


def test_empty_file_fails_with_message():
    rc, out = run("--file", str(tmpfile("vazio.sssom.tsv", "")))
    assert rc != 0 and "vazio" in out


def test_header_only_file_fails():
    head = "".join(l for l in EXAMPLES.read_text(encoding="utf-8").splitlines(keepends=True)
                   if l.startswith("#") or l.startswith("subject_id"))
    rc, out = run("--file", str(tmpfile("so_cabecalho.sssom.tsv", head)))
    assert rc != 0 and "sem nenhuma linha" in out


def test_unreadable_file_fails():
    p = tmpfile("binario.sssom.tsv", "")
    p.write_bytes(b"\xff\xfe\x00\x80")
    rc, out = run("--file", str(p))
    assert rc != 0


def test_good_file_passes_and_reads_its_rows():
    rc, out = run("--file", str(EXAMPLES))
    assert rc == 0, out
    n = sum(1 for l in EXAMPLES.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")) - 1
    assert f"{n} linha(s)" in out


def _write(recs, name):
    from bo.contracts import sssom as CS
    return tmpfile(name, CS.write_tsv(recs, "https://example.org/mapping-set/t"))


def test_inverted_orientation_in_file_fails():
    bad = copy.deepcopy(E.BROAD_ARCHIVE)
    bad["membership_predicate"]["subset"] = "object"      # leitura da v2: 'a broadMatch b' com 'a' mais amplo
    rc, out = run("--file", str(_write([bad, E.EXACT_DAYS_SECS], "invertido.sssom.tsv")))
    assert rc == 1 and "membership_orientation_matches_direction" in out


def test_relation_predicate_mismatch_in_file_fails():
    bad = copy.deepcopy(E.BROAD_ARCHIVE)
    bad["semantic_relation"] = "narrow"
    checks = {c["check"]: c["ok"] for c in RT.file_checks(_write([bad], "mismatch.sssom.tsv"))}
    assert not checks["semantic_relation_matches_predicate"]


def test_file_mode_uses_the_file_not_the_selftest():
    one = _write([E.NARROW_TLS], "um.sssom.tsv")
    res = RT.file_checks(one)
    assert res[0]["n_rows"] == 1 and all(c["ok"] for c in res)
    with pytest.raises(RT.FileError):
        RT.file_checks("/nao/existe.tsv")


def test_without_file_selftest_still_runs():
    rc, out = run()
    assert rc == 0 and "skos_roundtrip:" in out
