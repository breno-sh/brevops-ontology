"""Testes do CORPUS-AWS: regras U1-U8 em unidade e a contagem de ponta a ponta num TerraDS sintético."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bo.corpus_aws import build, check, core

R1, R2 = "R-0000000001aa", "R-0000000002bb"
F1 = "F-00000000001f"


def lit(v, dt="string"):
    return {"kind": "literal", "datatype": dt, "value": v}


def sym(cls, n=1):
    return {"kind": "symbol", "symbol_id": f"SYM-{n:011x}a", "name_class": cls, "scope": "repo"}


def ex(op, *args):
    return {"kind": "expression", "op": op, "args": list(args)}


WH = {"kind": "withheld", "reason": "secret"}
REF = {"kind": "reference", "target_type": "aws_thing", "target_address": "aws_thing.SYM-00000000002a"}

ATOMS = [  # (tipo, caminho, configurável)
    ("aws_thing", "name", True), ("aws_thing", "size", True), ("aws_thing", "arn", False),
    ("aws_thing", "ingress", True), ("aws_thing", "environment.variables", True),
    ("aws_thing", "cfg.a", True), ("aws_thing", "cfg.b", True), ("aws_thing", "rule.match.field", True),
    ("aws_other", "tags", True),
]


# ------------------------------------------------------------------------------------------------ unidade
@pytest.mark.parametrize("path,want", [
    ("name", ("attr", ("name",))),
    ("ingress[0].from_port", ("attr", ("ingress", "from_port"))),
    ('dynamic["rule"][0].content.match[0].field', ("attr", ("rule", "match", "field"))),
    ('dynamic["rule"][0].for_each', ("dynamic_meta", ("rule",))),
    ('dynamic["rule"][0].iterator', ("dynamic_meta", ("rule",))),
    ('dynamic["environment"][0].content', ("attr", ("environment",))),
    ('a[0].dynamic["b"][1].content.c', ("attr", ("a", "b", "c"))),
    ("count", ("meta", ("count",))),
    ("lifecycle[0].ignore_changes", ("meta", ("lifecycle", "ignore_changes"))),
    ("provisioner[0]", ("meta", ("provisioner",))),
])
def test_normalize(path, want):
    assert core.normalize(path) == want


def test_normalize_rejects_garbage():
    with pytest.raises(ValueError):
        core.normalize("a..b c")


@pytest.mark.parametrize("term,want", [
    (lit("x"), "literal"),
    (sym("unknown"), "literal"),                       # texto literal simbolizado só por privacidade
    (sym("variable"), "symbolic"),
    (sym("each_key"), "symbolic"),
    (REF, "symbolic"),
    (WH, "withheld"),
    (ex("max", lit(1, "number"), lit(2, "number")), "literal"),
    (ex("max", sym("variable"), lit(2, "number")), "symbolic"),
    (ex("file", lit("p.json")), "symbolic"),            # lê arquivo: o valor não sai do texto do atributo
    (ex("hcl_provider_function", lit("provider::aws::x"), lit(1, "number")), "symbolic"),  # resolvida no plano
    (sym("path"), "symbolic"),                         # path.*: depende do lugar do módulo (4 CORPUS)
    (ex("max", sym("path"), lit(1, "number")), "symbolic"),
    (sym("module_output"), "symbolic"),
    (sym("local"), "symbolic"),
    (ex("hcl_object", lit("k"), WH), "withheld"),
    (ex("hcl_object", lit("k"), sym("local"), lit("j"), WH), "withheld"),
    ({"kind": "document", "format": "json", "tree": {"a": [1, {"kind": "symbol"}]}, "symbolized": []}, "literal"),
    ({"kind": "document", "format": "json", "tree": {"a": {"$term": sym("variable")}}, "symbolized": []},
     "symbolic"),
    ({"kind": "document", "format": "json", "tree": {"a": {"$term": WH}}, "symbolized": []}, "withheld"),
])
def test_classify_and_naive_agree(term, want):
    assert core.classify(term) == want
    marks = check.naive_class(term)
    naive = "withheld" if "w" in marks else ("symbolic" if "s" in marks else "literal")
    assert naive == want


def test_naive_path_agrees_with_core():
    for p in ["name", "ingress[3].x", 'dynamic["rule"][0].content.match[0].field', 'dynamic["r"][0].for_each',
              "count", "lifecycle[0].create_before_destroy", 'dynamic["environment"][0].content']:
        disp, segs = core.normalize(p)
        got = check.naive_path(p)
        assert (got is None) == (disp != "attr")
        if got is not None:
            assert tuple(got) == segs


def _index():
    ix = core.AtomIndex("aws")
    for t, p, c in ATOMS:
        ix.add({"atom_id": f"aws:{t}:{p}", "provider": "aws", "resource_type": t, "path": p, "configurable": c,
                "computed": not c, "required": False, "optional": c, "deprecated": False})
    return ix


def test_atom_index_match_and_single_leaf():
    ix = _index()
    assert ix.match("aws_thing", ("name",)) == ("name", "exact")
    assert ix.match("aws_thing", ("ingress", "from_port")) == ("ingress", "prefix")
    assert ix.match("aws_thing", ("foo",)) == (None, "unmatched")
    assert ix.match("aws_gone", ("x",)) == (None, "type_unknown")
    assert ix.single_leaf("aws_thing", ("environment",)) == "environment.variables"
    assert ix.single_leaf("aws_thing", ("cfg",)) is None
    with pytest.raises(ValueError):
        ix.add({"atom_id": "google:x:y", "provider": "google", "resource_type": "x", "path": "y"})


# ------------------------------------------------------------------------------------------------ ponta a ponta
def rec(rid, file, addr, rtype, path, term, provider="aws"):
    return {"repo_id": rid, "family_id": F1, "file": file, "resource_address": addr, "resource_type": rtype,
            "provider": provider, "attr_path": path, "term": term}


A1, A2 = "aws_thing.SYM-00000000001a", "module.SYM-0000000000ma.aws_thing.SYM-00000000002a"
RECS = {
    R1: [
        rec(R1, "main.tf", A1, "aws_thing", "name", lit("n")),
        rec(R1, "main.tf", A1, "aws_thing", "size", sym("variable")),
        rec(R1, "main.tf", A1, "aws_thing", "ingress[0].from_port", lit(80, "number")),
        rec(R1, "main.tf", A1, "aws_thing", "ingress[1].to_port", REF),
        rec(R1, "main.tf", A1, "aws_thing", "environment[0]", WH),
        rec(R1, "main.tf", A1, "aws_thing", "cfg[0]", WH),
        rec(R1, "main.tf", A1, "aws_thing", "count", lit(2, "number")),
        rec(R1, "main.tf", A1, "aws_thing", 'dynamic["rule"][0].for_each', sym("variable")),
        rec(R1, "main.tf", A1, "aws_thing", 'dynamic["rule"][0].content.match[0].field', sym("each_key")),
        rec(R1, "main.tf", A1, "aws_thing", "foo", lit("x")),
        rec(R1, "main.tf", A1, "aws_thing", "cfg[1].a", lit(None, "null")),   # attr = null não configura (U9)
        rec(R1, "mod/a.tf", A2, "aws_thing", "name", sym("unknown")),
        rec(R1, "mod/a.tf", A2, "aws_thing", "size", ex("max", lit(1, "number"), lit(2, "number"))),
        rec(R1, "main.tf", "data.aws_thing.SYM-00000000003a", "aws_thing", "name", lit("d")),
        rec(R1, "main.tf", "aws_gone.SYM-00000000005a", "aws_gone", "x", lit("g")),
        rec(R1, "main.tf", "google_x.SYM-00000000006a", "google_x", "name", lit("g"), provider="google"),
    ],
    R2: [
        rec(R2, "x/main.tf", A1, "aws_thing", "name",
            {"kind": "document", "format": "json", "symbolized": [],
             "tree": {"a": {"$term": sym("variable")}, "b": {"$term": WH}}}),
    ],
}
RESOURCES = [  # (repo, file, addr, tipo, provider)
    (R1, "main.tf", A1, "aws_thing", "aws"), (R1, "mod/a.tf", A2, "aws_thing", "aws"),
    (R1, "main.tf", "data.aws_thing.SYM-00000000003a", "aws_thing", "aws"),
    (R1, "mod/a.tf", "aws_other.SYM-00000000004a", "aws_other", "aws"),
    (R1, "main.tf", "aws_gone.SYM-00000000005a", "aws_gone", "aws"),
    (R1, "main.tf", "google_x.SYM-00000000006a", "google_x", "google"),
    (R2, "x/main.tf", A1, "aws_thing", "aws"),
]

EXPECTED = [
    (R1, "aws_gone", None, 1, 0, 0, 0, 0),
    (R1, "aws_other", None, 1, 0, 0, 0, 0),
    (R1, "aws_thing", None, 2, 2, 1, 0, 1),
    (R1, "aws_thing", "aws:aws_thing:environment.variables", 2, 1, 0, 0, 1),
    (R1, "aws_thing", "aws:aws_thing:ingress", 2, 1, 0, 1, 0),
    (R1, "aws_thing", "aws:aws_thing:name", 2, 2, 2, 0, 0),
    (R1, "aws_thing", "aws:aws_thing:rule.match.field", 2, 1, 0, 1, 0),
    (R1, "aws_thing", "aws:aws_thing:size", 2, 2, 1, 1, 0),
    (R2, "aws_thing", None, 1, 1, 0, 0, 1),
    (R2, "aws_thing", "aws:aws_thing:name", 1, 1, 0, 0, 1),
]


@pytest.fixture()
def fake_data(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq
    d = tmp_path / "data"
    (d / "HCL").mkdir(parents=True)
    (d / "SCHEMA-AWS").mkdir()
    with open(d / "SCHEMA-AWS" / "atoms.jsonl", "w") as f:
        for t, p, c in ATOMS:
            f.write(json.dumps({"atom_id": f"aws:{t}:{p}", "provider": "aws", "resource_type": t, "path": p,
                                "configurable": c, "computed": not c, "required": False, "optional": c,
                                "deprecated": False}) + "\n")
    n_attrs = {}
    for rid, rs in RECS.items():
        for r in rs:
            k = (rid, r["file"], r["resource_address"])
            n_attrs[k] = n_attrs.get(k, 0) + 1
    cols = {k: [] for k in ("repo_id", "family_id", "file", "resource_address", "resource_type", "provider",
                            "n_attrs", "has_count", "has_for_each", "module_depth")}
    for rid, fl, a, t, prov in RESOURCES:
        for k, v in zip(cols, (rid, F1, fl, a, t, prov, n_attrs.get((rid, fl, a), 0), False, False, 0)):
            cols[k].append(v)
    pq.write_table(pa.table(cols), d / "HCL" / "resources.parquet")
    idx = {}
    with open(d / "HCL" / "symbolic_config.jsonl", "wb") as f:
        for rid in (R2, R1):  # ordem do arquivo != ordem dos ids
            s = f.tell()
            for r in RECS[rid]:
                f.write((core.dumps(r) + "\n").encode())
            idx[rid] = [s, f.tell(), len(RECS[rid])]
    (d / "HCL" / "symbolic_config.index.json").write_text(json.dumps({"module": "HCL", "repos": idx}))
    monkeypatch.setenv("BO_DATA", str(d))
    monkeypatch.setenv("BO_TMP", str(tmp_path / "tmp"))
    return d


def _rows(path: Path):
    out = []
    for line in path.read_text().splitlines():
        u = json.loads(line)
        out.append((u["repo_id"], u["resource_type"], u.get("atom_id"), u["n_resources"], u["n_set"],
                    u["n_literal"], u["n_symbolic"], u["n_withheld"]))
    return out


def test_end_to_end_counts_and_contract(fake_data, tmp_path):
    out = tmp_path / "out1"
    assert build.main(["--workers", "1", "--out", str(out)]) == 0
    assert _rows(out / "usage.jsonl") == EXPECTED
    from bo.contracts import catalog, validate
    r = validate.validate_file(catalog.resolve("usage", out / "usage.jsonl"), out / "usage.jsonl")
    assert r.ok, r.errors
    c = json.loads((out / "counts.json").read_text())
    assert c["consistency"] == {"parquet_duplicate_resource": 0, "records_type_mismatch": 0,
                                "records_without_resource": 0, "resources_n_attrs_mismatch": 0}
    assert c["corpus"]["data_blocks_excluded"] == 1
    assert c["records"]["records_withheld_block_attributed"] == 1
    assert c["records"]["records_withheld_block_unattributed"] == 1
    assert c["records"]["records_unmatched"] == 1
    assert c["records"]["records_type_unknown"] == 1
    assert c["records"]["records_explicit_null"] == 1
    assert c["records"]["records_meta:count"] == 1 and c["records"]["records_dynamic_meta"] == 1
    tot = {json.loads(x)["atom_id"]: json.loads(x) for x in (out / "atom_totals.jsonl").read_text().splitlines()}
    assert len(tot) == len(ATOMS)
    name = tot["aws:aws_thing:name"]
    assert (name["n_repos"], name["n_families"], name["n_modules"], name["n_resources"]) == (2, 1, 3, 3)
    assert (name["type_n_repos"], name["type_n_modules"], name["type_n_resources"]) == (2, 3, 3)
    assert tot["aws:aws_thing:arn"]["n_repos"] == 0 and tot["aws:aws_other:tags"]["type_n_resources"] == 1
    # o check independente (2ª implementação em todos os repositórios) aceita a saída
    assert check.main([str(out), "--sample-mod", "1"]) == 0


def test_deterministic_across_workers(fake_data, tmp_path):
    a, b = tmp_path / "w1", tmp_path / "w2"
    assert build.main(["--workers", "1", "--out", str(a)]) == 0
    assert build.main(["--workers", "2", "--out", str(b), "--chunk-bytes", "1"]) == 0
    for n in ("usage.jsonl", "atom_totals.jsonl", "build_report.json", "counts.json"):
        assert (a / n).read_bytes() == (b / n).read_bytes(), n


def test_check_catches_tampering(fake_data, tmp_path):
    out = tmp_path / "t"
    assert build.main(["--workers", "1", "--out", str(out)]) == 0
    lines = (out / "usage.jsonl").read_text().splitlines()
    u = json.loads(lines[5])
    u["n_literal"] += 1
    u["n_set"] += 1
    lines[5] = core.dumps(u)
    (out / "usage.jsonl").write_text("\n".join(lines) + "\n")
    assert check.main([str(out), "--sample-mod", "1"]) == 1
    rep = json.loads((out / "check_report.json").read_text())
    assert rep["result"] == "FAIL" and not check.stamp_matches(out, need_validator=False)


def test_input_change_detected(fake_data, tmp_path):
    out = tmp_path / "c"
    assert build.main(["--workers", "1", "--out", str(out)]) == 0
    with open(fake_data / "SCHEMA-AWS" / "atoms.jsonl", "a") as f:
        f.write(json.dumps({"atom_id": "aws:aws_other:extra", "provider": "aws", "resource_type": "aws_other",
                            "path": "extra", "configurable": True}) + "\n")
    assert check.main([str(out), "--sample-mod", "1"]) == 1


def test_promote_refuses_without_lock(fake_data, tmp_path, monkeypatch):
    from bo.corpus_aws import promote
    monkeypatch.setenv("BO_REPO", str(tmp_path / "repo"))
    assert promote.main([]) == 3


def test_check_catches_type_row_tampering(fake_data, tmp_path):
    out = tmp_path / "tt"
    assert build.main(["--workers", "1", "--out", str(out)]) == 0
    lines = (out / "usage.jsonl").read_text().splitlines()
    i = next(k for k, ln in enumerate(lines) if "atom_id" not in ln and '"aws_thing"' in ln)
    u = json.loads(lines[i])
    u["n_set"] -= 1
    u["n_literal" if u["n_literal"] else "n_withheld"] -= 1
    lines[i] = core.dumps(u)
    (out / "usage.jsonl").write_text("\n".join(lines) + "\n")
    assert check.main([str(out), "--sample-mod", "1"]) == 1
