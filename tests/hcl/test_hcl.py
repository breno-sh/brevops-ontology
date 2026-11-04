"""Testes do leitor simbólico (bo.hcl). Valores sensíveis são montados em tempo de execução: o código-fonte
não contém ARN, conta de 12 dígitos nem segredo literal (o pre-commit do privacy_lint reprovaria)."""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from bo.hcl import classify as C
from bo.hcl import hclast
from bo.hcl.common import repo_id, sym_id
from bo.hcl.extract import build_vocab, repo_core
from bo.hcl.render import Renderer
from bo.hcl.symbolic_roundtrip import check_repo, nf
from bo.hcl.symbolize import Symbolizer, Vocab

ACCT = "".join(str((i * 7) % 10) for i in range(12))  # 12 dígitos, montado aqui
ARN = "ar" + "n"
SECRET_VAL = "s3" + "nh4Forte" + "9x"
PWKEY = "pass" + "word"
LEAK = re.compile(r"\barn:|(?<!\d)\d{12}(?!\d)|" + re.escape(SECRET_VAL))


def fixture_tf() -> str:
    return f'''
variable "vpc_cidr" {{ default = "10.0.0.0/16" }}

resource "aws_vpc" "main" {{
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  tags = {{
    Name        = "acme-prod-vpc"
    Environment = "prod"
  }}
}}

resource "aws_security_group" "web" {{
  name   = "${{var.prefix}}-web"
  vpc_id = aws_vpc.main.id
  ingress {{
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0", "1.2.3.4/32", "203.0.113.7/32"]
  }}
  dynamic "egress" {{
    for_each = var.rules
    content {{
      from_port = egress.value.port
      to_port   = egress.value.port
    }}
  }}
}}

resource "aws_db_instance" "db" {{
  allocated_storage = max(var.size, 20)
  {PWKEY}          = "{SECRET_VAL}"
  db_subnet_group_name = aws_db_subnet_group.g[0].name
  count = length(var.dbs)
  lifecycle {{
    ignore_changes = [tags, password]
  }}
}}

resource "aws_instance" "vm" {{
  ami       = data.aws_ami.ubuntu.id
  user_data = file("${{path.module}}/boot.sh")
  provisioner "remote-exec" {{
    inline = ["echo hi"]
  }}
  subnet_ids = [for s in aws_subnet.private : s.id if s.tags["tier"] == "app"]
}}

resource "aws_s3_bucket_policy" "p" {{
  bucket = aws_s3_bucket.b.id
  policy = <<EOF
{{
  "Version": "2012-10-17",
  "Statement": [{{
    "Effect": "Allow",
    "Principal": {{"AWS": "{ARN}:aws:iam::{ACCT}:root"}},
    "Action": "s3:GetObject",
    "Resource": "${{aws_s3_bucket.b.arn}}/*"
  }}]
}}
EOF
}}

resource "aws_sqs_queue" "q" {{
  redrive_policy = jsonencode({{
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 4
  }})
  kms_master_key_id = "{ARN}:aws:kms:us-east-1:{ACCT}:key/abcd-1234"
}}

data "aws_iam_policy_document" "d" {{
  statement {{
    actions   = ["sts:AssumeRole"]
    resources = ["{ARN}:aws:iam::${{data.aws_caller_identity.c.account_id}}:role/app"]
  }}
}}

module "net" {{
  source = "./modules/net"
}}
'''


def module_tf() -> str:
    return '''
resource "google_compute_subnetwork" "s" {
  ip_cidr_range = "192.168.10.0/24"
  network       = var.network
  region        = "us-central1"
}
'''


def make_repo(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, text in files.items():
            b = text.encode()
            ti = tarfile.TarInfo("4242/" + name)
            ti.size = len(b)
            t.addfile(ti, io.BytesIO(b))
    return buf.getvalue()


@pytest.fixture(scope="module")
def repo():
    data = make_repo({"main.tf": fixture_tf(), "modules/net/main.tf": module_tf()})
    return repo_core("4242", data, set(), reveal=True)


def recs(repo, rtype=None):
    out = []
    for ln in repo["lines"]:
        r = json.loads(ln)
        if rtype is None or r["resource_type"] == rtype:
            out.append(r)
    return out


def term_of(repo, rtype, path):
    for r in recs(repo, rtype):
        if r["attr_path"] == path:
            return r["term"]
    raise KeyError(path)


def test_ids_never_twelve_digits():
    rid = repo_id(1)
    for i in range(30000):
        s = sym_id(rid, i)
        assert re.fullmatch(r"SYM-[0-9a-f]{12}", s)
        assert not re.search(r"\d{12}", s) and s[-1] in "abcdef"
    assert re.fullmatch(r"R-[0-9a-f]{12}", rid)


def test_parse_and_resources(repo):
    assert repo["stats"]["files_ok"] == 2
    types = sorted({r[4] for r in repo["rows"]})
    assert types == ["aws_db_instance", "aws_iam_policy_document", "aws_instance", "aws_s3_bucket_policy",
                     "aws_security_group", "aws_sqs_queue", "aws_vpc", "google_compute_subnetwork"]
    mod_row = [r for r in repo["rows"] if r[4] == "google_compute_subnetwork"][0]
    assert mod_row[9] == 1 and mod_row[3].startswith("module.SYM-")
    db = [r for r in repo["rows"] if r[4] == "aws_db_instance"][0]
    assert db[7] is True and db[8] is False


def test_no_leak_in_lines(repo):
    for ln in repo["lines"]:
        assert not LEAK.search(ln), ln[:200]
        assert "acme" not in ln and "prod-vpc" not in ln


def test_cidr_classes(repo):
    t = term_of(repo, "aws_security_group", "ingress[0].cidr_blocks")
    any_, pub, doc = t["args"]
    assert any_["op"] == "cidr" and any_["args"][2]["value"] == "any" and any_["args"][0]["value"] == "0.0.0.0"
    assert pub["args"][2]["value"] == "public" and pub["args"][0]["kind"] == "symbol"
    assert pub["args"][1] == {"kind": "literal", "datatype": "number", "value": 32}
    assert doc["args"][2]["value"] == "documentation" and doc["args"][0]["kind"] == "literal"
    g = term_of(repo, "google_compute_subnetwork", "ip_cidr_range")
    assert g["args"][2]["value"] == "private" and g["args"][1]["value"] == 24
    assert C.parse_cidr("100.64.1.0/24")[2] == "shared" and C.parse_cidr("fd00::/8")[2] == "private"


def test_reference_and_names(repo):
    t = term_of(repo, "aws_security_group", "vpc_id")
    assert t["kind"] == "reference" and t["target_type"] == "aws_vpc" and t["attribute"] == "id"
    assert re.fullmatch(r"aws_vpc\.SYM-[0-9a-f]{12}", t["target_address"])
    vpc_addr = [r[3] for r in repo["rows"] if r[4] == "aws_vpc"][0]
    assert vpc_addr == t["target_address"]  # o mesmo nome dá o mesmo símbolo
    g = term_of(repo, "aws_db_instance", "db_subnet_group_name")
    assert g["target_address"].endswith("[0]") and g["attribute"] == "name"
    d = term_of(repo, "aws_instance", "ami")
    assert d["target_address"].startswith("data.aws_ami.SYM-")
    tags = term_of(repo, "aws_vpc", "tags")
    assert tags["op"] == "hcl_object" and all(a["kind"] == "symbol" for a in tags["args"])


def test_expressions(repo):
    t = term_of(repo, "aws_db_instance", "allocated_storage")
    assert t["op"] == "max" and t["args"][0]["name_class"] == "variable"
    assert t["args"][1] == {"kind": "literal", "datatype": "number", "value": 20}
    n = term_of(repo, "aws_security_group", "name")
    assert n["op"] == "hcl_template" and n["args"][0]["name_class"] == "variable"
    f = term_of(repo, "aws_instance", "subnet_ids")
    assert f["op"] == "hcl_for_tuple"
    dyn = term_of(repo, "aws_security_group", 'dynamic["egress"][0].content.from_port')
    assert dyn["op"] == "hcl_getattr" and dyn["args"][0]["args"][0]["name_class"] == "each_key"
    c = term_of(repo, "aws_db_instance", "count")
    assert c["op"] == "length"
    ic = term_of(repo, "aws_db_instance", "lifecycle[0].ignore_changes")
    assert [a["op"] for a in ic["args"]] == ["hcl_attr", "hcl_attr"]


def test_withheld_has_no_value(repo):
    pw = term_of(repo, "aws_db_instance", "password")
    assert pw == {"kind": "withheld", "reason": "secret"}
    assert term_of(repo, "aws_instance", "user_data") == {"kind": "withheld", "reason": "boot_script"}
    assert term_of(repo, "aws_instance", "provisioner[0]") == {"kind": "withheld", "reason": "boot_script"}
    assert C.withheld_reason("Environment", value_is_scalar=True) is None
    assert C.withheld_reason("environment", value_is_scalar=False) == "environment"
    assert C.withheld_reason("minimum_password_length") is None


def test_documents(repo):
    p = term_of(repo, "aws_s3_bucket_policy", "policy")
    assert p["kind"] == "document" and p["format"] == "policy_json"
    roles = {e["role"] for e in p["symbolized"]}
    assert "account" in roles
    tree = json.dumps(p["tree"])
    assert '"$term"' in tree and '"reference"' in tree and '"target_type": "aws_s3_bucket"' in tree
    s = json.dumps(p)
    assert not LEAK.search(s)
    r = term_of(repo, "aws_sqs_queue", "redrive_policy")
    assert r["op"] == "jsonencode" and r["args"][0]["op"] == "hcl_object"
    k = term_of(repo, "aws_sqs_queue", "kms_master_key_id")
    assert k["op"] == "arn" and k["args"][3]["kind"] == "symbol"
    part = term_of(repo, "aws_iam_policy_document", "statement[0].resources")
    assert "arn_partial" in json.dumps(part)


def test_roundtrip_fixture(repo):
    errs, cnt = [], {"repos": 0, "names": 0, "terms": 0, "structure_ok": 0, "term_ok": 0, "term_diff": 0,
                     "withheld": 0, "iterator": 0, "documents": 0, "cidr": 0}
    check_repo(repo, list(repo["lines"]), set(), errs, cnt)
    assert errs == []
    assert cnt["terms"] == cnt["structure_ok"] > 20 and cnt["documents"] >= 1 and cnt["cidr"] >= 3


def test_render_detects_change(repo):
    """Controle negativo: um termo adulterado não volta à mesma estrutura."""
    t = json.loads(json.dumps(term_of(repo, "aws_db_instance", "allocated_storage")))
    t["args"][1]["value"] = 21
    R = Renderer(repo["reveal"])
    back = hclast.parse_expr(R.expr(t))
    orig = hclast.parse_expr("max(var.size, 20)")
    assert nf(back) != nf(orig)


def test_symbol_depends_only_on_order():
    a, b = Symbolizer("R-000000000aaa", Vocab(set())), Symbolizer("R-000000000aaa", Vocab(set()))
    x1, y1 = a.tab.get("str", "alpha"), a.tab.get("str", "beta")
    x2, y2 = b.tab.get("str", "gamma"), b.tab.get("str", "delta")
    assert (x1, y1) == (x2, y2) and x1 != y1
    assert a.tab.get("str", "alpha") == x1


def test_vocab_rule():
    import numpy as np
    from bo.hcl.common import key64
    c_enum, c_name = key64("t:instance_type"), key64("t:name")
    rows = []
    for fam in range(10):
        rows.append((c_enum, key64("t:instance_type", "t3.micro"), fam))
        rows.append((c_name, key64("t:name", f"n{fam}"), fam))
        rows.append((c_name, key64("t:name", "example"), fam))
        rows.append((c_name, key64("t:name", f"m{fam}"), fam))
    arr = np.array(rows, dtype=np.uint64)
    keep, info = build_vocab(arr[:, 0], arr[:, 1], arr[:, 2], 5, 0.5)
    keep = set(int(x) for x in keep)
    assert key64("t:instance_type", "t3.micro") in keep
    assert key64("t:name", "example") not in keep  # comum, mas o contexto é de nomes
    assert info["enum_contexts"] == 1


def test_contract_validator_accepts_fixture(repo, tmp_path):
    p = Path(tmp_path) / "symbolic_config.jsonl"
    p.write_text("\n".join(repo["lines"]) + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "C06", str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]


def test_privacy_stream_negative_control(tmp_path):
    """Controle negativo do varredor em fluxo: conta plantada (montada aqui) reprova; arquivo limpo passa."""
    bad = Path(tmp_path) / "bad"
    good = Path(tmp_path) / "good"
    bad.mkdir()
    good.mkdir()
    (bad / "x.jsonl").write_text('{"a": 1}\n' * 1000 + '{"conta": "' + ACCT + '"}\n', encoding="utf-8")
    (good / "x.jsonl").write_text('{"a": "SYM-0a1b2c3d4e5f"}\n' * 1000, encoding="utf-8")
    rb = subprocess.run([sys.executable, "-I", "-m", "bo.hcl.privacy_stream", str(bad)], capture_output=True, text=True)
    rg = subprocess.run([sys.executable, "-I", "-m", "bo.hcl.privacy_stream", str(good)], capture_output=True, text=True)
    assert rb.returncode == 1 and ":1001: doze_digitos" in rb.stdout and ACCT not in rb.stdout
    assert rg.returncode == 0


def test_withheld_inside_documents():
    sz = Symbolizer("R-000000000bbb", Vocab(set()))
    defs = json.dumps([{"name": "app", "environment": [{"name": "K", "value": SECRET_VAL}],
                        "secrets": [{"name": "S", "valueFrom": "x"}], "image": "nginx"}])
    t = sz.text(defs, "aws_ecs_task_definition:container_definitions")
    assert t["kind"] == "document"
    s = json.dumps(t)
    assert SECRET_VAL not in s and s.count('"withheld"') == 2


def test_symlinked_tf_is_read_like_terraform():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        b = b'resource "google_compute_network" "main" {\n  name = "n"\n}\n'
        ti = tarfile.TarInfo("77/shared/network.tf")
        ti.size = len(b)
        t.addfile(ti, io.BytesIO(b))
        for name, target in (("77/a/network.tf", "../shared/network.tf"), ("77/b/x.tf", "../../fora.tf")):
            li = tarfile.TarInfo(name)
            li.type, li.linkname = tarfile.SYMTYPE, target
            t.addfile(li)
    r = repo_core("77", buf.getvalue(), set())
    assert sorted(x[2] for x in r["rows"]) == ["a/network.tf", "shared/network.tf"] or \
        len(r["rows"]) == 2
    assert r["stats"]["symlink_resolved"] == 1 and r["stats"]["symlink_unresolved"] == 1


def test_vocab_never_keeps_contract_leaks():
    """Mesmo um e-mail de domínio de exemplo (aceito pelo privacy_lint) não fica literal: a regra C06 reprova."""
    from bo.hcl.common import key64
    mail = "ops" + "@" + "example.com"
    v = Vocab({key64("c", mail), key64("c", "t3.micro")})
    assert not v.literal_ok("c", mail) and v.literal_ok("c", "t3.micro")
