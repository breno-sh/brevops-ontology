"""Gate de higiene (# higiene: não é evidência de validade): nenhuma regra cita provedor, prefixo de tipo ou
sufixo de nome.

Uso: python -I -m bo.grain.lint ARQ_DE_REGRAS [--no-selftest]

Confere, no texto inteiro (comentários inclusive) e no YAML carregado:
  L1. o arquivo carrega pelo bo.grain.rules (vocabulário fechado de predicados: condição que não está na
      lista reprova, então nenhuma regra pode olhar para nome ou tipo);
  L2. nenhum nome de provedor ou de nuvem (lista abaixo, por palavra, sem diferenciar maiúsculas) e nenhum
      provedor sintético (provider_<letra>);
  L3. nenhum prefixo de tipo Terraform (aws_, google_, azurerm_, ..., e os sintéticos de uma letra, a_ ... z_);
  L4. nenhuma construção de casamento por nome: chave suffix/prefix/endswith/startswith/regex/glob/pattern/
      name/type/resource_type; valor com curinga (*), âncora de regex, ou começando/terminando em '_';
      sufixo de embalagem colado a um identificador (x_attachment, x_association, x_versioning, ...).
Não vacuidade: antes de aprovar o arquivo dado, o lint roda sobre mutantes do próprio arquivo (um por
categoria) e cada mutante tem de reprovar.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from . import rules as R
from .common import stamp

PROVIDER_WORDS = ["aws", "amazon", "ec2", "s3", "rds", "gcp", "gcloud", "google", "gke", "azure", "azurerm",
                  "azuread", "microsoft", "oci", "oracle", "alibaba", "alicloud", "aliyun", "ibm",
                  "digitalocean", "linode", "hetzner", "cloudflare", "vultr", "openstack", "vsphere", "hashicorp"]
TYPE_PREFIXES = ["aws", "google", "azurerm", "azuread", "azapi", "oci", "alicloud", "ibm", "digitalocean",
                 "cloudflare", "kubernetes", "helm", "openstack", "vsphere"]
FORBIDDEN_KEYS = {"suffix", "prefix", "endswith", "startswith", "ends_with", "starts_with", "regex", "regexp",
                  "glob", "pattern", "name", "name_in", "names", "type", "type_in", "types", "resource_type",
                  "resource_type_in", "name_suffix", "name_prefix", "type_prefix", "type_suffix", "match_name",
                  "name_matches", "type_matches", "tf_type"}
PACKAGING_SUFFIXES = ["attachment", "attachments", "association", "associations", "binding", "bindings", "member",
                      "members", "policy", "policies", "rule", "rules", "configuration", "config", "versioning",
                      "setting", "settings", "assignment", "assignments", "iam", "acl", "link", "links"]

_RE_PROVIDER = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(PROVIDER_WORDS) + r")(?![A-Za-z0-9])", re.I)
_RE_SYNTH = re.compile(r"(?<![A-Za-z0-9])provider_[a-z](?![A-Za-z0-9])")
_RE_PREFIX = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(TYPE_PREFIXES) + r"|[a-z])_[a-z0-9]")
_RE_SUFFIX = re.compile(r"[A-Za-z0-9]_(" + "|".join(PACKAGING_SUFFIXES) + r")(?![A-Za-z0-9_])")
_RE_WILD = re.compile(r"\*|\^\w|\w\$|\.\*|\\[dwsb]")


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield ("key", f"{path}.{k}", str(k))
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield ("val", path, obj)


def lint_text(text: str) -> list[str]:
    errs: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        for rx, cat in ((_RE_PROVIDER, "L2 provedor"), (_RE_SYNTH, "L2 provedor sintético"),
                        (_RE_PREFIX, "L3 prefixo de tipo"), (_RE_SUFFIX, "L4 sufixo de embalagem")):
            m = rx.search(line)
            if m:
                errs.append(f"{cat} na linha {i}: '{m.group(0)}'")
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return errs + [f"L1 YAML inválido: {e}"]
    try:
        R.parse(doc)
    except (R.RulesError, KeyError, TypeError) as e:
        errs.append(f"L1 regras não carregam no vocabulário fechado: {e}")
    for kind, path, s in _walk(doc):
        if kind == "key" and s.lower() in FORBIDDEN_KEYS:
            errs.append(f"L4 chave de casamento por nome/tipo: {path}")
        if kind == "val":
            if path.endswith(".text") or ".when" in path or path.endswith(".meaning") or path.startswith(".layers") \
                    or ".procedure" in path or path.startswith(".predicates") or ".evidence." in path:
                continue  # texto explicativo: só as regras L2/L3/L4 de linha valem para ele
            st = s.strip()
            if st.startswith("_") or st.endswith("_") or _RE_WILD.search(st):
                errs.append(f"L4 valor com curinga ou pedaço de nome: {path} = '{st[:40]}'")
    return errs


MUTANTS = [
    ("provedor no texto", lambda t: t.replace("text: identidade e ciclo de vida independentes",
                                              "text: como no AWS, identidade e ciclo de vida independentes", 1)),
    ("provedor sintético", lambda t: t.replace("schema: bo.grain.rules/1", "schema: bo.grain.rules/1  # provider_a", 1)),
    ("prefixo de tipo", lambda t: t.replace("    match: {identity_class_in: [INDEPENDENT]}",
                                            "    match: {identity_class_in: [INDEPENDENT]}  # google_storage_bucket",
                                            1)),
    ("prefixo sintético", lambda t: t.replace("schema: bo.grain.rules/1", "schema: bo.grain.rules/1  # a_bucket", 1)),
    ("predicado de sufixo", lambda t: t.replace("    match: {identity_class_in: [BORROWED]}",
                                                "    match: {identity_class_in: [BORROWED], name_suffix: [versioning]}",
                                                1)),
    ("sufixo de embalagem", lambda t: t.replace("schema: bo.grain.rules/1", "schema: bo.grain.rules/1  # x_attachment", 1)),
    ("curinga", lambda t: t.replace("    multi_owner: {resolve_to: binding_over_owners,",
                                    "    multi_owner: {resolve_to: '*', ", 1)),
    ("chave de tipo", lambda t: t.replace("    match: {identity_class_in: [INDEPENDENT]}",
                                          "    match: {identity_class_in: [INDEPENDENT]}\n    resource_type: [bucket]",
                                          1)),
]


def selftest(text: str) -> list[str]:
    fails = []
    for name, f in MUTANTS:
        m = f(text)
        if m == text:
            fails.append(f"mutante '{name}' não aplicou (o arquivo mudou; atualize o lint)")
        elif not lint_text(m):
            fails.append(f"mutante '{name}' passou no lint (o lint não pega a categoria)")
    return fails


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_self = "--no-selftest" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print("uso: python -I -m bo.grain.lint ARQ_DE_REGRAS [--no-selftest]", file=sys.stderr)
        return 2
    p = Path(args[0])
    if not p.is_file():
        print(f"lint: arquivo ausente: {p}", file=sys.stderr)
        return 2
    text = p.read_text(encoding="utf-8")
    errs = lint_text(text)
    st = [] if no_self else selftest(text)
    print(stamp(f"lint (# higiene) {p}: {len(errs)} problema(s); "
                f"{'selftest pulado' if no_self else f'{len(MUTANTS) - len(st)}/{len(MUTANTS)} mutante(s) reprovados'}"))
    for e in errs + st:
        print("  ", e)
    ok = not errs and not st
    print("RESULTADO:", "OK" if ok else "REPROVADO")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
