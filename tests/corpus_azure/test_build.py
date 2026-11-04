"""Testes do CORPUS-AZURE sobre um BO_DATA sintético mínimo (HCL + SCHEMA-AZURE) em $BO_TMP (nunca /tmp).

A contagem é a biblioteca única (bo.corpus_oci.counting); aqui se testa a fiação do azurerm: leitura pelo índice,
recorte do provedor, casos do azurerm (atributo de objeto escrito como bloco, null explícito, tipo fora do schema,
data source) e o resumo.
"""
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "CORPUS-AZURE"))
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)

R1, R2 = "R-0000000000a1", "R-0000000000b2"
F1, F2 = "F-0000000000f1", "F-0000000000f2"
RG = "azurerm_resource_group.SYM-abcdef00000a"
RG2 = "module.SYM-abcdef00000c.azurerm_resource_group.SYM-abcdef00000b"
RG3 = "azurerm_resource_group.SYM-abcdef0000aa"
NSG = "azurerm_network_security_group.SYM-abcdef00000c"
DATA = "data.azurerm_client_config.SYM-abcdef00000d"
OLD = "azurerm_app_service.SYM-abcdef00000e"
AWS = "aws_s3_bucket.SYM-abcdef00000f"

LIT = {"kind": "literal", "datatype": "string", "value": "eastus"}
VAR = {"kind": "symbol", "symbol_id": "SYM-0a1b2c3d4e5f", "name_class": "variable", "scope": "repo"}
NULL = {"kind": "literal", "datatype": "null", "value": None}
RED = {"kind": "symbol", "symbol_id": "SYM-0a1b2c3d4e6f", "name_class": "unknown", "scope": "repo"}
WH = {"kind": "withheld", "reason": "secret"}


def atom(rt, path, tf_type="string", blocks=(), configurable=True):
    return {"atom_id": f"azurerm:{rt}:{path}", "block_path": [{"block": b, "nesting_mode": "list"} for b in blocks],
            "computed": False, "configurable": configurable, "deprecated": False,
            "nesting": "list" if blocks else "none", "optional": True, "path": path, "provider": "azurerm",
            "provider_version": "5.12.0", "required": False, "resource_type": rt, "sensitive": False,
            "tf_type": tf_type}


ATOMS = [
    atom("azurerm_resource_group", "name"),
    atom("azurerm_resource_group", "location"),
    atom("azurerm_resource_group", "managed_by"),
    atom("azurerm_network_security_group", "name"),
    atom("azurerm_network_security_group", "security_rule",
         ["set", ["object", {"access": "string", "priority": "number"}]]),
    atom("azurerm_network_security_group", "timeouts.create", blocks=["timeouts"]),
]


def rec(repo, fam, file, addr, rt, path, term, prov="azurerm"):
    return {"repo_id": repo, "family_id": fam, "file": file, "resource_address": addr, "resource_type": rt,
            "provider": prov, "attr_path": path, "term": term}


RECS = {
    R1: [rec(R1, F1, "main.tf", RG, "azurerm_resource_group", "name", LIT),
         rec(R1, F1, "main.tf", RG, "azurerm_resource_group", "location", VAR),
         rec(R1, F1, "main.tf", RG, "azurerm_resource_group", "managed_by", NULL),
         rec(R1, F1, "main.tf", RG, "azurerm_resource_group", "depends_on", LIT),
         rec(R1, F1, "main.tf", NSG, "azurerm_network_security_group", "name", RED),
         rec(R1, F1, "main.tf", NSG, "azurerm_network_security_group", "security_rule[0].access", LIT),
         rec(R1, F1, "main.tf", NSG, "azurerm_network_security_group", "security_rule[1].priority", VAR),
         rec(R1, F1, "main.tf", NSG, "azurerm_network_security_group", 'dynamic["timeouts"][0].content.create',
             WH),
         rec(R1, F1, "main.tf", NSG, "azurerm_network_security_group", 'dynamic["timeouts"][0].for_each', VAR),
         rec(R1, F1, "main.tf", DATA, "azurerm_client_config", "x", LIT),
         rec(R1, F1, "main.tf", OLD, "azurerm_app_service", "name", LIT),
         rec(R1, F1, "main.tf", AWS, "aws_s3_bucket", "bucket", LIT, prov="aws")],
    R2: [rec(R2, F2, "mod/a.tf", RG2, "azurerm_resource_group", "name", VAR)],
}


def parquet_rows():
    rows = []
    for repo, recs in RECS.items():
        seen = {}
        for r in recs:
            k = (r["file"], r["resource_address"])
            seen.setdefault(k, [r, 0])[1] += 1
        for (f, a), (r, n) in seen.items():
            rows.append({"repo_id": repo, "family_id": r["family_id"], "file": f, "resource_address": a,
                         "resource_type": r["resource_type"], "provider": r["provider"], "n_attrs": n,
                         "has_count": False, "has_for_each": False, "module_depth": a.count("module.")})
    # um recurso do azurerm sem nenhum registro, noutro diretório do mesmo repositório
    rows.append({"repo_id": R2, "family_id": F2, "file": "mod/b/x.tf", "resource_address": RG3,
                 "resource_type": "azurerm_resource_group", "provider": "azurerm", "n_attrs": 0,
                 "has_count": True, "has_for_each": False, "module_depth": 0})
    return rows


@pytest.fixture()
def data(monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq
    root = Path(os.environ["BO_TMP"]) / f"test-{uuid.uuid4().hex[:8]}"
    (root / "HCL").mkdir(parents=True)
    (root / "SCHEMA-AZURE").mkdir()
    pq.write_table(pa.Table.from_pylist(parquet_rows()), root / "HCL" / "resources.parquet")
    idx, off = {}, 0
    with open(root / "HCL" / "symbolic_config.jsonl", "wb") as f:
        for repo in sorted(RECS):
            b = b"".join(json.dumps(r, sort_keys=True, separators=(",", ":")).encode() + b"\n" for r in RECS[repo])
            f.write(b)
            idx[repo] = [off, off + len(b), len(RECS[repo])]
            off += len(b)
    (root / "HCL" / "symbolic_config.index.json").write_text(json.dumps({"module": "HCL", "repos": idx}))
    with open(root / "SCHEMA-AZURE" / "atoms.jsonl", "w") as f:
        for a in ATOMS:
            f.write(json.dumps(a) + "\n")
    monkeypatch.setenv("BO_DATA", str(root))
    yield root
    shutil.rmtree(root, ignore_errors=True)


def load(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines()]


def test_build_counts(data):
    from bo.corpus_azure.build import build
    out = data / "out"
    rep = build(out)
    usage = load(out / "usage.jsonl")
    rows = {(u["repo_id"], u["resource_type"], u.get("atom_id")): u for u in usage}
    name = rows[(R1, "azurerm_resource_group", "azurerm:azurerm_resource_group:name")]
    assert (name["n_resources"], name["n_set"], name["n_literal"]) == (1, 1, 1)
    loc = rows[(R1, "azurerm_resource_group", "azurerm:azurerm_resource_group:location")]
    assert (loc["n_set"], loc["n_symbolic"]) == (1, 1)
    # null explícito não configura o átomo
    assert (R1, "azurerm_resource_group", "azurerm:azurerm_resource_group:managed_by") not in rows
    # cadeia constante simbolizada só por privacidade continua literal (regra comum dos 4 CORPUS)
    nm = rows[(R1, "azurerm_network_security_group", "azurerm:azurerm_network_security_group:name")]
    assert (nm["n_set"], nm["n_literal"]) == (1, 1)
    # atributo de objeto escrito como bloco: um recurso, a classe mais fraca das ocorrências
    sr = rows[(R1, "azurerm_network_security_group", "azurerm:azurerm_network_security_group:security_rule")]
    assert (sr["n_set"], sr["n_literal"], sr["n_symbolic"]) == (1, 0, 1)
    to = rows[(R1, "azurerm_network_security_group", "azurerm:azurerm_network_security_group:timeouts.create")]
    assert (to["n_set"], to["n_withheld"]) == (1, 1)
    # tipo fora do schema: só a linha de tipo, n_set 0; data source e aws fora
    old = rows[(R1, "azurerm_app_service", None)]
    assert (old["n_resources"], old["n_set"]) == (1, 0)
    assert not any(k[1] in ("azurerm_client_config", "aws_s3_bucket") for k in rows)
    # recurso sem registro conta no denominador
    rg2 = rows[(R2, "azurerm_resource_group", None)]
    assert (rg2["n_resources"], rg2["n_set"]) == (2, 1)
    for u in usage:
        assert u["n_literal"] + u["n_symbolic"] + u["n_withheld"] == u["n_set"] <= u["n_resources"]
        assert u["provider"] == "azurerm" and not any("split" in k or "partition" in k for k in u)
    c = rep["corpus"]
    assert (c["n_repos"], c["n_families"], c["n_modules"], c["n_resources"], c["n_data_blocks_skipped"]) == \
        (2, 2, 3, 5, 1)
    u = rep["records"]["unattributed_by_cause"]
    assert (u["meta_argument"], u["dynamic_meta"], u["explicit_null"], u["type_not_in_schema"]) == (1, 1, 1, 1)
    assert rep["types"]["n_types_used_not_in_schema"] == 1
    tot = {a["atom_id"]: a for a in load(out / "atom_totals.jsonl")}
    assert len(tot) == len(ATOMS)
    n = tot["azurerm:azurerm_resource_group:name"]
    assert (n["n_repos"], n["n_families"], n["n_modules"], n["n_set"], n["type_n_resources"]) == (2, 2, 2, 2, 3)


def test_build_is_deterministic_and_sample_matches(data):
    from bo.corpus_azure.build import build, sample_pick
    a, b = data / "a", data / "b"
    build(a)
    build(b)
    for f in ("usage.jsonl", "atom_totals.jsonl", "type_totals.jsonl"):
        assert (a / f).read_bytes() == (b / f).read_bytes()
    s = data / "s"
    build(s, sample_mod=1)
    assert (s / "usage.jsonl").read_bytes() == (a / "usage.jsonl").read_bytes()
    assert sample_pick(R1, 1)


def test_contract_validator_accepts_output(data):
    from bo.corpus_azure.build import build
    build(data / "v")
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "usage", str(data / "v" / "usage.jsonl")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-400:] + r.stderr[-400:]
