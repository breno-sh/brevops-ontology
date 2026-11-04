"""Fixtures do CORPUS-OCI: um BO_DATA sintético mínimo (HCL + SCHEMA-OCI) dentro de $BO_TMP (nunca /tmp)."""
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "CORPUS-OCI"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

R1, R2, R3 = "R-0000000000a1", "R-0000000000b2", "R-0000000000c3"
F1, F2 = "F-0000000000f1", "F-0000000000f2"
INST = "oci_core_instance.SYM-00000000000a"
INST2 = "module.SYM-00000000000m.oci_core_instance.SYM-00000000000b"
SL = "oci_core_security_list.SYM-00000000000c"
DATA = "data.oci_core_images.SYM-00000000000d"
AWS = "aws_s3_bucket.SYM-00000000000e"
GHOST = "oci_tag.SYM-00000000000f"


def atom(rt, path, blocks=(), configurable=True):
    return {"atom_id": f"oci:{rt}:{path}", "block_path": [{"block": b, "nesting_mode": "list"} for b in blocks],
            "computed": False, "configurable": configurable, "deprecated": False,
            "nesting": "list" if blocks else "none", "optional": True, "path": path, "provider": "oci",
            "provider_version": "9.11.0", "required": False, "resource_type": rt, "sensitive": False,
            "tf_type": "string"}


ATOMS = [
    atom("oci_core_instance", "shape"),
    atom("oci_core_instance", "metadata"),
    atom("oci_core_instance", "display_name"),
    atom("oci_core_instance", "state", configurable=False),
    atom("oci_core_instance", "shape_config.ocpus", ["shape_config"]),
    atom("oci_core_security_list", "ingress_security_rules.protocol", ["ingress_security_rules"]),
    atom("oci_core_security_list", "ingress_security_rules.tcp_options.min",
         ["ingress_security_rules", "tcp_options"]),
    atom("oci_core_security_list", "vcn_id"),
]

LIT = {"kind": "literal", "datatype": "string", "value": "x"}
SYM = {"kind": "symbol", "symbol_id": "SYM-0000000000aa", "name_class": "variable", "scope": "repo"}
NULL = {"kind": "literal", "datatype": "null", "value": None}
WH = {"kind": "withheld", "reason": "boot_script"}
EXPR_WH = {"kind": "expression", "op": "hcl_object", "args": [LIT, WH]}
REF = {"kind": "reference", "target_type": "oci_core_vcn", "target_address": "oci_core_vcn.SYM-0000000000bb"}


def rec(repo, fam, file, addr, rt, path, term, prov="oci"):
    return {"repo_id": repo, "family_id": fam, "file": file, "resource_address": addr, "resource_type": rt,
            "provider": prov, "attr_path": path, "term": term}


def corpus():
    """(linhas do parquet, registros) do corpus sintético; n_attrs = nº de registros de cada recurso."""
    recs = [
        # R1: duas instâncias (uma em módulo), uma security list, um data source, um aws, um tipo fora do schema
        rec(R1, F1, "main.tf", INST, "oci_core_instance", "shape", LIT),
        rec(R1, F1, "main.tf", INST, "oci_core_instance", "metadata.user_data", WH),
        rec(R1, F1, "main.tf", INST, "oci_core_instance", "metadata.ssh_authorized_keys", SYM),
        rec(R1, F1, "main.tf", INST, "oci_core_instance", "shape_config[0].ocpus", LIT),
        rec(R1, F1, "main.tf", INST, "oci_core_instance", "count", LIT),
        rec(R1, F1, "mod/vm.tf", INST2, "oci_core_instance", "shape", SYM),
        rec(R1, F1, "mod/vm.tf", INST2, "oci_core_instance", "dynamic[\"shape_config\"][0].for_each", SYM),
        rec(R1, F1, "mod/vm.tf", INST2, "oci_core_instance", "dynamic[\"shape_config\"][0].content.ocpus", LIT),
        rec(R1, F1, "mod/vm.tf", INST2, "oci_core_instance", "removed_attr", LIT),
        rec(R1, F1, "net.tf", SL, "oci_core_security_list", "ingress_security_rules[0].protocol", LIT),
        rec(R1, F1, "net.tf", SL, "oci_core_security_list", "ingress_security_rules[1].protocol", REF),
        rec(R1, F1, "net.tf", SL, "oci_core_security_list",
            "ingress_security_rules[0].dynamic[\"tcp_options\"][0].content.min", LIT),
        rec(R1, F1, "net.tf", SL, "oci_core_security_list", "ingress_security_rules", EXPR_WH),
        rec(R1, F1, "data.tf", DATA, "oci_core_images", "shape", LIT),
        rec(R1, F1, "aws.tf", AWS, "aws_s3_bucket", "bucket", LIT, prov="aws"),
        rec(R1, F1, "tag.tf", GHOST, "oci_tag", "name", LIT),
        # R2 (outra família): uma instância com metadata em expressão que contém retido
        rec(R2, F2, "a/b.tf", INST, "oci_core_instance", "metadata", EXPR_WH),
        rec(R2, F2, "a/b.tf", INST, "oci_core_instance", "display_name", SYM),
        rec(R2, F2, "a/b.tf", INST, "oci_core_instance", "shape", NULL),
    ]
    by_res = {}
    for r in recs:
        k = (r["repo_id"], r["family_id"], r["file"], r["resource_address"], r["resource_type"], r["provider"])
        by_res[k] = by_res.get(k, 0) + 1
    rows = [{"repo_id": k[0], "family_id": k[1], "file": k[2], "resource_address": k[3], "resource_type": k[4],
             "provider": k[5], "n_attrs": n, "has_count": False, "has_for_each": False,
             "module_depth": 1 if k[3].startswith("module.") else 0} for k, n in by_res.items()]
    # R2: uma security list vazia (sem registro); R3: só um recurso vazio e nenhum registro (fora do índice)
    rows.append({"repo_id": R2, "family_id": F2, "file": "a/c.tf", "resource_address": SL,
                 "resource_type": "oci_core_security_list", "provider": "oci", "n_attrs": 0, "has_count": False,
                 "has_for_each": False, "module_depth": 0})
    rows.append({"repo_id": R3, "family_id": F2, "file": "x.tf", "resource_address": SL,
                 "resource_type": "oci_core_security_list", "provider": "oci", "n_attrs": 0, "has_count": False,
                 "has_for_each": False, "module_depth": 0})
    return rows, recs


def write_data(root: Path, rows, recs, atoms=ATOMS):
    import pyarrow as pa
    import pyarrow.parquet as pq

    (root / "HCL").mkdir(parents=True)
    (root / "SCHEMA-OCI").mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), root / "HCL" / "resources.parquet")
    idx = {}
    with open(root / "HCL" / "symbolic_config.jsonl", "wb") as f:
        for repo in sorted({r["repo_id"] for r in recs}):
            start = f.tell()
            mine = [r for r in recs if r["repo_id"] == repo]
            for r in mine:
                f.write((json.dumps(r, sort_keys=True) + "\n").encode())
            idx[repo] = [start, f.tell(), len(mine)]
    (root / "HCL" / "symbolic_config.index.json").write_text(json.dumps({"module": "HCL", "repos": idx}))
    with open(root / "SCHEMA-OCI" / "atoms.jsonl", "w") as f:
        for a in atoms:
            f.write(json.dumps(a) + "\n")


@pytest.fixture
def data_root(monkeypatch):
    root = Path(os.environ["BO_TMP"]) / "pytest" / uuid.uuid4().hex[:12]
    rows, recs = corpus()
    write_data(root, rows, recs)
    monkeypatch.setenv("BO_DATA", str(root))
    yield root
    shutil.rmtree(root, ignore_errors=True)
