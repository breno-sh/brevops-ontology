"""Gate de HIGIENE: python -I -m bo.requirements.vocab_independent [--dir PASTA] [--selftest]

Reprova se o texto das CQs (e também o dos requisitos e o dos compromissos, fora do aterramento por provedor)
contiver termo de provedor ou IRI (bo:, w3id, http/https). Higiene, não validade (§8 do plano): passar aqui
não prova nada sobre o significado das CQs.

O que é varrido: todo valor textual do registro, inclusive termos de vocabulário (kind, rel, attr, what) e ids
locais de fixture. O que NÃO é varrido, por ser referência e não texto: identificadores de registro e de
fixture, listas de ids (requirement_ids, commitment_ids, cases, case, answers, consumers), cabeçalho de contrato
e, nos compromissos, provider_grounding (o único lugar onde provedor é citado, de propósito, como dica de
instanciação para o CQFIX e os oráculos, com estado de evidência UNRESOLVED).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import common

PROVIDER_TERMS = [
    # provedores e prefixos de tipo
    "aws", "amazon", "gcp", "google", "azure", "azurerm", "azuread", "oci", "oracle", "microsoft",
    # serviços e recursos com nome de provedor
    "s3", "ec2", "ebs", "eni", "vpc", "iam", "arn", "rds", "aurora", "dynamodb", "elb", "alb", "nlb",
    "cloudwatch", "cloudtrail", "route53", "kms", "gcs", "gce", "gke", "bigquery", "cloud sql", "cloud storage",
    "compute engine", "backend service", "forwarding rule", "url map", "target pool", "service account",
    "entra id", "active directory", "aad", "nsg", "storage account", "resource group", "subscription",
    "management group", "application gateway", "front door", "blob", "vcn", "vnic", "security list",
    "compartment", "tenancy", "ocid", "autonomous database", "security group", "target group", "network acl",
    "nacl", "bucket",
]
_B = r"(?<![A-Za-z0-9À-ÿ])"
_E = r"(?![A-Za-z0-9À-ÿ])"
TERM_RE = re.compile(_B + "(" + "|".join(re.escape(t).replace(r"\ ", r"[\s_-]+") for t in PROVIDER_TERMS) + ")" + _E,
                     re.IGNORECASE)
IRI_RE = re.compile(r"(?<![A-Za-z0-9])bo:[A-Za-z_]|w3id\.org|https?://", re.IGNORECASE)

SKIP_KEYS = {"schema", "contract", "contract_version", "cq_id", "commitment_id", "req_id", "fixture_id",
             "requirement_ids", "commitment_ids", "cases", "case", "answers", "consumers", "provider_grounding"}


def texts(obj, path=""):
    """Gera (caminho, texto) de todo valor textual fora de SKIP_KEYS."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            yield from texts(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from texts(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def scan_record(rec: dict) -> list[tuple[str, str]]:
    hits = []
    for p, t in texts(rec):
        for m in TERM_RE.finditer(t):
            hits.append((p, f"termo de provedor '{m.group(1)}'"))
        for m in IRI_RE.finditer(t):
            hits.append((p, f"IRI '{m.group(0)}'"))
    return hits


def check(d: Path) -> tuple[list[str], dict]:
    errs, n = [], {}
    for kind, fname in common.KIND_FILE.items():
        recs = common.load_jsonl(d / fname)
        n[kind] = sum(1 for r in recs for _ in texts(r))
        for r in recs:
            rid = r.get("cq_id") or r.get("commitment_id") or r.get("req_id") or "?"
            for p, why in scan_record(r):
                errs.append(f"{fname} {rid} {p}: {why}")
    return errs, n


def selftest() -> int:
    bad = {"question": "O bucket do AWS S3 tem versionamento?", "x": [{"kind": "security_group"}],
           "y": "ver bo:Bucket e https://w3id.org/brevops", "provider_grounding": [{"note": "aws_s3_bucket"}]}
    good = {"question": "O contêiner de objetos tem versionamento? álbum, carne, sócio, penina",
            "provider_grounding": [{"note": "aws_s3_bucket"}], "case": "IAM"}
    hb, hg = scan_record(bad), scan_record(good)
    need = {"bucket", "aws", "s3", "security_group", "bo:b", "w3id.org", "https://"}
    found = {w.split("'")[1].lower() for _, w in hb}
    ok = need <= found and not hg and not any(p.startswith("provider_grounding") for p, _ in hb)
    print(f"selftest vocab_independent: {'OK' if ok else 'FALHOU'} (achados={sorted(found)}, falsos={hg})")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.requirements.vocab_independent")
    ap.add_argument("--dir", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if selftest() != 0:
        return 1
    d = Path(a.dir) if a.dir else common.out_dir()
    errs, n = check(d)
    print(f"vocab_independent (higiene): {sum(n.values())} valores textuais varridos {n}")
    if errs:
        return common.fail(errs, "vocab_independent")
    print("vocab_independent: OK (nenhum termo de provedor nem IRI)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
