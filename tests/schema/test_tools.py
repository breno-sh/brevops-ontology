"""bo.schema.lockfile, extract (perfil do sandbox), build e crosscheck."""
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from bo.contracts import validate as V
from bo.schema import build, core, crosscheck, extract, lockfile

from conftest import schema_doc

INPUT_LOCK = Path("/Users/breno/doutorado/pesquisa-lanes/c1-37-icsa/superficie/data/tfschema4/.terraform.lock.hcl")

LOCK = """# This file is maintained automatically by "terraform init".
# Manual edits may be lost in future updates.

provider "registry.terraform.io/hashicorp/aws" {
  version     = "5.83.1"
  constraints = "5.83.1"
  hashes = [
    "h1:AAAA=",
    "zh:0011",
  ]
}

provider "registry.terraform.io/oracle/oci" {
  version = "9.1.0"
  hashes = [
    "h1:BBBB=",
  ]
}
"""


def test_lock_parse_and_render_roundtrip():
    locks = lockfile.parse(LOCK)
    aws = lockfile.find(locks, "hashicorp/aws")
    assert (aws.version, aws.constraints, aws.hashes, aws.name) == ("5.83.1", "5.83.1", ("h1:AAAA=", "zh:0011"), "aws")
    oci = lockfile.find(locks, "registry.terraform.io/oracle/oci")
    assert (oci.version, oci.constraints, oci.source) == ("9.1.0", None, "oracle/oci")
    again = lockfile.parse(lockfile.render([aws, oci]))
    assert again == locks
    with pytest.raises(KeyError):
        lockfile.find(locks, "hashicorp/google")


@pytest.mark.skipif(not INPUT_LOCK.exists(), reason="entrada do catálogo ausente")
def test_input_lock_has_catalog_versions():
    locks = lockfile.read(INPUT_LOCK)
    got = {lp.name: lp.version for lp in locks.values()}
    assert {k: got[k] for k in ("google", "azurerm", "oci")} == {"google": "8.2.0", "azurerm": "5.5.0", "oci": "9.1.0"}
    assert all(lp.hashes for lp in locks.values())


def test_versions_tf_pins_exact_version():
    lp = lockfile.find(lockfile.parse(LOCK), "hashicorp/aws")
    assert 'aws = { source = "hashicorp/aws", version = "= 5.83.1" }' in extract.versions_tf(lp)


def test_sandbox_env_has_no_credentials(work):
    env = extract.sandbox_env(work, work / "cache", Path("/usr/bin/true"))
    assert set(env) == {"PATH", "HOME", "TMPDIR", "TF_PLUGIN_CACHE_DIR", "TF_CLI_CONFIG_FILE", "TF_IN_AUTOMATION",
                        "CHECKPOINT_DISABLE", "LANG"}
    assert env["HOME"].startswith(str(work))


def test_sandbox_profile_lists_credential_dirs():
    prof = extract.sandbox_profile([Path("/x")], network=False)
    for p in (".aws", ".config/gcloud", ".azure", ".oci", ".ssh", "brevops-keys", "SPLIT/sealed"):
        assert p in prof
    assert "(deny network-outbound (remote ip))" in prof
    assert "network" not in extract.sandbox_profile([Path("/x")], network=True).split("(deny file-read*")[0]


@pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").exists(), reason="sandbox-exec só no macOS")
def test_sandbox_denies_read_write_and_ip(work, monkeypatch):
    """O perfil de verdade: ler a sonda negada falha, escrever fora da pasta falha, conectar por IP falha."""
    denied = work / "denied"
    denied.mkdir()
    (denied / "probe.txt").write_text("sonda", encoding="utf-8")
    outside = work / "outside"
    outside.mkdir()
    inside = work / "inside"
    inside.mkdir()
    monkeypatch.setattr(extract, "DENY_READ", [denied])
    prof = work / "p.sb"
    prof.write_text(extract.sandbox_profile([inside], network=False), encoding="utf-8")

    def sb(*cmd):
        return subprocess.run(["/usr/bin/sandbox-exec", "-f", str(prof), *cmd], capture_output=True).returncode

    assert sb("/bin/cat", str(denied / "probe.txt")) != 0
    assert sb("/usr/bin/touch", str(outside / "w")) != 0 and not (outside / "w").exists()
    assert sb("/usr/bin/touch", str(inside / "w")) == 0
    code = ("import socket,sys\ns=socket.socket()\ns.settimeout(2)\n"
            "try:\n s.connect(('127.0.0.1', 9))\nexcept PermissionError:\n sys.exit(7)\nexcept OSError:\n sys.exit(0)\n")
    assert sb(sys.executable, "-I", "-c", code) == 7
    # controle: fora do sandbox a mesma conexão não dá PermissionError
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", 9))
    except PermissionError:
        pytest.fail("controle sem sandbox também negado: o teste não distingue")
    except OSError:
        pass
    finally:
        s.close()


def write_schema(work, with_receipt=True, version="1.0.0"):
    d = work / "provider_a-1.0.0"
    d.mkdir()
    (d / "schema.json").write_text(json.dumps(schema_doc()), encoding="utf-8")
    if with_receipt:
        (d / "receipt.json").write_text(json.dumps({"provider": {"version": version}}), encoding="utf-8")
    return d / "schema.json"


def test_build_writes_valid_contract_files_deterministically(work):
    s = write_schema(work)
    r1 = build.build(s, "provider_a", None, work / "a1.jsonl", work / "t1.jsonl")
    r2 = build.build(s, "provider_a", "1.0.0", work / "a2.jsonl", work / "t2.jsonl")
    assert r1 == r2 and (r1["types"], r1["atoms"], r1["provider_version"]) == (2, 24, "1.0.0")
    assert (work / "a1.jsonl").read_bytes() == (work / "a2.jsonl").read_bytes()
    assert (work / "t1.jsonl").read_bytes() == (work / "t2.jsonl").read_bytes()
    assert V.validate("C01_atoms", work / "a1.jsonl").ok and V.validate("C02_types", work / "t1.jsonl").ok
    assert build.main(["--schema", str(s), "--provider", "provider_a", "--atoms", str(work / "a3.jsonl"),
                       "--types", str(work / "t3.jsonl")]) == 0


def test_build_version_never_guessed(work):
    s = write_schema(work, with_receipt=False)
    with pytest.raises(SystemExit):
        build.build(s, "provider_a", None, work / "a.jsonl", work / "t.jsonl")
    shutil.rmtree(s.parent)
    s = write_schema(work, version="1.0.0")
    with pytest.raises(SystemExit):
        build.build(s, "provider_a", "9.9.9", work / "a.jsonl", work / "t.jsonl")
    with pytest.raises(SystemExit):
        build.build(s, "provider_z", "1.0.0", work / "a.jsonl", work / "t.jsonl")


def page(slug, category="resources", language="hcl"):
    return {"slug": slug, "category": category, "language": language}


def test_crosscheck_alias_and_iam_family_explained():
    types = {"aws_lb": "s1", "aws_alb": "s1", "aws_vpc": "s2",
             "google_x_iam_binding": "b", "google_x_iam_member": "m", "google_x_iam_policy": "p"}
    docs = {"aws_lb", "aws_vpc", "google_x_iam"}
    r = crosscheck.compare(types, docs)
    assert r["veredito"] == "PASS"
    assert sorted((e["tipo"], e["causa"]) for e in r["explicadas"]) == [
        ("aws_alb", "alias_bloco_identico"), ("google_x_iam_binding", "familia_iam"),
        ("google_x_iam_member", "familia_iam"), ("google_x_iam_policy", "familia_iam")]


def test_crosscheck_unexplained_fails():
    r = crosscheck.compare({"aws_a": "1", "aws_b": "2"}, {"aws_a", "aws_c"})
    assert r["veredito"] == "FAIL" and r["tipos_sem_pagina"] == ["aws_b"] and r["paginas_sem_tipo"] == ["aws_c"]


def test_crosscheck_index_filters_and_prefixes():
    idx = {"version": "5.0.0", "docs": [page("lb"), page("lb", language="python"), page("vpc", "data-sources"),
                                         page("aws_iam_role")]}
    assert crosscheck.documented(idx, "aws", "5.0.0") == {"aws_lb", "aws_iam_role"}
    with pytest.raises(SystemExit):
        crosscheck.documented(idx, "aws", "6.0.0")


def test_crosscheck_cli_offline(work):
    tpath = work / "types.jsonl"
    recs = [{"resource_type": "aws_lb", "block_sha256": "s1", "provider_version": "1.0.0"},
            {"resource_type": "aws_alb", "block_sha256": "s1", "provider_version": "1.0.0"}]
    tpath.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    idx = work / "index.json"
    idx.write_text(json.dumps({"version": "1.0.0", "docs": [page("lb")]}), encoding="utf-8")
    out = work / "cc.json"
    assert crosscheck.main(["--provider", "aws", "--types", str(tpath), "--index", str(idx), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["explicadas"][0]["documentado_como"] == "aws_lb"
    idx.write_text(json.dumps({"version": "1.0.0", "docs": [page("lb"), page("vpc")]}), encoding="utf-8")
    assert crosscheck.main(["--provider", "aws", "--types", str(tpath), "--index", str(idx)]) == 1
    assert crosscheck.main(["--provider", "aws", "--types", str(work / "nada.jsonl")]) == 2
    assert crosscheck.main(["--provider", "aws", "--types", str(tpath), "--index", str(work / "x.json")]) == 2
