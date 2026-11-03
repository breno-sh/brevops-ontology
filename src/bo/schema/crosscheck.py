"""Tipos de recurso de um schema extraído x índice de documentação do Terraform Registry da mesma versão.

  python -I -m bo.schema.crosscheck --provider aws [--types ARQ] [--index ARQ] [--fetch]
                                    [--schema DIR] [--docs DIR] [--beta-schema DIR] [--no-evidence] [--out ARQ]

--types   types.jsonl (C02) do produtor; padrão $BO_DATA/<SCHEMA-X>/types.jsonl. A versão é a dos registros.
--index   resposta de GET https://registry.terraform.io/v1/providers/<ns>/<nome>/<versão> (campo 'docs');
          padrão $BO_DATA/downloads/registry-docs/<provedor>-<versão>/index.json; --fetch baixa se faltar.
--schema  pasta do bo.schema.extract do MESMO provedor e versão (schema.json.gz, schema.json.sha256, receipt.json);
          padrão $BO_DATA/downloads/tfschema/<provedor>-<versão>/. Dá os data sources do schema.
--docs    website/docs/ do repositório do provider na tag da versão, com MANIFEST.json (sha256 por arquivo) na
          pasta-mãe; padrão $BO_DATA/downloads/prefetch/<provedor>/<versão>/docs. Dá o título de cada página.
--beta-schema  (só google) pasta do bo.schema.extract do google-beta da MESMA versão; padrão
          $BO_DATA/downloads/tfschema/google-beta-<versão>/ quando existe.
Evidência (schema, docs, beta) só vale conferida: sha256 da saída do terraform = schema.json.sha256 = recibo;
recibo do bo.schema.extract com -lockfile=readonly; pacote do provider no cache de plugin com o sha256 do
recibo e o h1 recalculado dentro dos hashes do lock (o init conferiu a assinatura do release contra eles);
cada página lida bate com o sha256 do MANIFEST.json. Evidência ausente: as causas que dependem dela não se
aplicam (a diferença fica sem causa). Evidência presente que não confere: sai 1, sem relatório de PASS.

Índice = páginas category 'resources', language 'hcl'; o slug vira <provedor>_<slug>. Título de uma página =
primeira linha que casa TITLE (ex.: '# Resource: aws_lb', '# Data Source: oci_x', '# google_y').
Critério: toda diferença tipo<->página tem uma causa de CAUSES (regra mecânica, conferível pela evidência
listada no relatório), e nenhuma fica sem causa. Sai 0 só assim; sai 1 se sobrar diferença sem causa.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import core

REGISTRY = {"aws": "hashicorp/aws", "google": "hashicorp/google", "azurerm": "hashicorp/azurerm", "oci": "oracle/oci"}
PRODUCER = {"aws": "SCHEMA-AWS", "azurerm": "SCHEMA-AZURE", "google": "SCHEMA-GCP", "oci": "SCHEMA-OCI"}
BETA = {"google": "registry.terraform.io/hashicorp/google-beta"}
IAM_SUFFIXES = ("_iam_binding", "_iam_member", "_iam_policy", "_iam_audit_config")
TITLE = re.compile(r"^#\s+(?:(Resource|Data Source|Ephemeral Resource|List Resource|Action):\s*)?"
                   r"`?([a-z][a-z0-9_]*)`?\s*$", re.M)

#: causa -> regra mecânica (o lado da diferença entre colchetes)
CAUSES = {
    "alias_bloco_identico": "[tipo] sem página, com block_sha256 igual ao de um tipo documentado (alias, ex.: aws_alb = aws_lb)",
    "familia_iam": "[tipo] <x>_iam_binding/_member/_policy/_audit_config coberto pela página <x>_iam; "
                   "[página] <x>_iam que cobre ao menos um tipo da família",
    "so_beta": "[página] (só google) cujo tipo, ou um tipo da família <x>_iam, existe no schema do google-beta da "
               "MESMA versão extraído de binário assinado conferido; nunca pelo aviso 'beta' da doc",
    "nome_divergente": "[página e tipo] o título da página nomeia exatamente um tipo de recurso do schema que não tem "
                       "página pelo slug: os dois formam um par (igualdade de nome, sem semelhança)",
    "data_source_publicado_como_recurso": "[página] título 'Data Source: X' com X em data_source_schemas do schema",
    "pagina_sem_tipo_no_schema": "[página] o título nomeia X, e X não é recurso nem data source do schema da versão "
                                 "(nem do google-beta, quando conferido)",
    "tipo_sem_documentacao": "[tipo] nenhuma página do índice com o slug dele e nenhum título de página de recurso "
                             "(em todas as páginas do índice com arquivo em --docs) que o nomeie",
}


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


class EvidenceError(SystemExit):
    """Evidência presente que não confere (sha256, recibo, versão): o crosscheck não decide nada."""


def read_types(path: Path) -> tuple[str, dict[str, str]]:
    types, versions = {}, set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                t = json.loads(line)
                types[t["resource_type"]] = t["block_sha256"]
                versions.add(t["provider_version"])
    if len(versions) != 1:
        raise SystemExit(f"crosscheck: {path} com {len(versions)} versões ({sorted(versions)})")
    return versions.pop(), types


def index_path(provider: str, version: str) -> Path:
    return bo_data() / "downloads" / "registry-docs" / f"{provider}-{version}" / "index.json"


def fetch(provider: str, version: str, dest: Path) -> None:
    url = f"https://registry.terraform.io/v1/providers/{REGISTRY[provider]}/{version}"
    import time
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:      # noqa: S310 (URL fixa do registro)
                data = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    json.loads(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    (dest.parent / "SOURCE.txt").write_text(
        f"GET {url}\nÍndice de documentação do Terraform Registry (campo 'docs').\n"
        "Baixado por python -I -m bo.schema.crosscheck --fetch. Dado não confiável: só lido como JSON.\n",
        encoding="utf-8")


def _name(provider: str, slug: str) -> str:
    pref = provider + "_"
    return slug if slug.startswith(pref) else pref + slug


def documented(index: dict, provider: str, version: str) -> set[str]:
    if index.get("version") not in (None, version):
        raise SystemExit(f"crosscheck: índice da versão {index.get('version')}, tipos da {version}")
    return {_name(provider, d["slug"]) for d in index.get("docs") or []
            if d.get("category") == "resources" and d.get("language") == "hcl"}


# ------------------------------------------------------------------------------------------------ evidência
def h1_of_dir(d: Path) -> str:
    """Hash 'h1:' do terraform (dirhash Hash1) de um pacote desempacotado no cache de plugin."""
    lines = sorted((p.relative_to(d).as_posix(), _sha_file(p)) for p in d.rglob("*") if p.is_file())
    blob = "".join(f"{h}  {rel}\n" for rel, h in lines).encode()
    return "h1:" + base64.b64encode(hashlib.sha256(blob).digest()).decode()


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def plugin_caches(extra: Path | None = None) -> list[Path]:
    """Onde procurar o pacote: --plugin-cache, o cache padrão do bo.schema.extract e o plugin_cache/ de cada
    SCHEMA-*. O lugar não prova nada; a prova é o sha256 do binário e o h1 do pacote."""
    out = [extra] if extra else []
    out.append(bo_data() / "downloads" / "terraform-registry" / "plugin-cache")
    out += [bo_data() / m / "plugin_cache" for m in sorted(set(PRODUCER.values()))]
    return out


def verified_schema(d: Path, address: str, version: str, cache: Path | None = None) -> tuple[dict, dict]:
    """(provider_schema, prova) de uma pasta do bo.schema.extract; EvidenceError se algo não confere."""
    def bad(msg):
        raise EvidenceError(f"crosscheck: evidência {d} não confere: {msg}")
    rc = d / "receipt.json"
    if not rc.exists():
        bad("sem receipt.json do bo.schema.extract")
    r = json.loads(rc.read_text(encoding="utf-8"))
    if r.get("schema") != "bo.schema_extract/1":
        bad(f"recibo {r.get('schema')!r}")
    if r["provider"]["address"] != address or r["provider"]["version"] != version:
        bad(f"recibo de {r['provider']['address']} {r['provider']['version']}, esperado {address} {version}")
    if "readonly" not in (r.get("lock") or {}).get("mode", ""):
        bad("extração sem -lockfile=readonly")
    raw = gzip.open(d / "schema.json.gz", "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    want = (d / "schema.json.sha256").read_text(encoding="utf-8").split()[0]
    if not (sha == want == r["schema_json"]["sha256"]):
        bad("sha256 da saída do terraform diverge do schema.json.sha256 ou do recibo")
    pb = r["provider_binary"]
    pkgs = [c / address / version / pb["os_arch"] for c in plugin_caches(cache)]
    pkg = next((p for p in pkgs if (p / pb["file"]).exists()), None)
    if pkg is None:
        bad(f"pacote do provider ausente dos caches de plugin ({', '.join(str(p) for p in pkgs)})")
    binf = pkg / pb["file"]
    if _sha_file(binf) != pb["sha256"]:
        bad("sha256 do binário no cache diverge do recibo")
    h1 = h1_of_dir(pkg)
    if h1 not in r["lock"]["hashes"]:
        bad("h1 do pacote fora dos hashes do lock")
    ps = core.providers(json.loads(raw)).get(core.short_name(address))
    if ps is None:
        bad(f"schema sem {address}")
    return ps, {"pasta": str(d), "pacote": str(pkg), "schema_sha256": sha, "binario_sha256": pb["sha256"], "h1": h1,
                "terraform": r.get("terraform", {}).get("version")}


@dataclass
class Evidence:
    data_sources: set
    resources: set
    titles: dict = field(default_factory=dict)        # nome da página (índice resources/hcl) -> (tipo, nome)
    resource_titles: dict = field(default_factory=dict)  # nome nomeado por título de recurso -> [páginas]
    beta_types: set | None = None
    proof: dict = field(default_factory=dict)


def parse_title(text: str) -> tuple[str, str] | None:
    m = TITLE.search(text)
    return (m.group(1) or "Resource", m.group(2)) if m else None


def read_docs(docs: Path, index: dict, provider: str, version: str) -> tuple[dict, dict, dict]:
    """(títulos das páginas de recurso, títulos de recurso de todas as páginas, prova). Confere o MANIFEST.json."""
    man = docs.parent / "MANIFEST.json"
    if not man.exists():
        raise EvidenceError(f"crosscheck: {docs} sem MANIFEST.json na pasta-mãe")
    m = json.loads(man.read_text(encoding="utf-8"))
    addr = f"registry.terraform.io/{REGISTRY[provider]}"
    if m.get("provider") != addr or m.get("version") != version:
        raise EvidenceError(f"crosscheck: MANIFEST.json de {m.get('provider')} {m.get('version')}")
    shas = {f["path"]: f["sha256"] for f in m.get("files") or []}
    page_titles, res_titles, n = {}, {}, 0
    for d in index.get("docs") or []:
        if d.get("language") != "hcl" or not str(d.get("path", "")).startswith("website/docs/"):
            continue
        rel = d["path"][len("website/"):]                     # docs/r/x.html.markdown
        f = docs.parent / rel
        if rel not in shas or not f.exists():
            continue
        data = f.read_bytes()
        if hashlib.sha256(data).hexdigest() != shas[rel]:
            raise EvidenceError(f"crosscheck: {rel} diverge do sha256 do MANIFEST.json")
        n += 1
        t = parse_title(data.decode("utf-8", errors="replace"))
        if d.get("category") == "resources":
            page_titles[_name(provider, d["slug"])] = t
        if t and t[0] != "Data Source":
            res_titles.setdefault(t[1], []).append(_name(provider, d["slug"]))
    return page_titles, res_titles, {"docs": str(docs), "manifest_sha256": _sha_file(man), "paginas_lidas": n}


# ------------------------------------------------------------------------------------------------ comparação
def compare(types: dict[str, str], docs: set[str], ev: Evidence | None = None) -> dict:
    """Sem evidência: só alias e família IAM (o comportamento de antes). Com evidência: as causas de CAUSES."""
    tset = set(types)
    no_doc, no_type = sorted(tset - docs), sorted(docs - tset)
    doc_sha = {types[t]: t for t in sorted(tset & docs)}
    explained, rest = [], []
    for t in no_doc:
        if types[t] in doc_sha:
            explained.append({"tipo": t, "causa": "alias_bloco_identico", "documentado_como": doc_sha[types[t]]})
            continue
        fam = next((t[: -len(s)] + "_iam" for s in IAM_SUFFIXES if t.endswith(s)), None)
        if fam and fam in docs:
            explained.append({"tipo": t, "causa": "familia_iam", "documentado_como": fam})
            continue
        rest.append(t)
    covered_pages = {e["documentado_como"] for e in explained if e["causa"] == "familia_iam"}
    pages_left = [p for p in no_type if p not in covered_pages]
    if ev is not None:
        rest, pages_left = _with_evidence(rest, pages_left, ev, explained)
    rep = {"tipos_schema": len(tset), "paginas_indice": len(docs), "iguais": len(tset & docs),
           "explicadas": explained, "tipos_sem_pagina": rest, "paginas_sem_tipo": pages_left,
           "veredito": "PASS" if not rest and not pages_left else "FAIL"}
    if ev is not None:      # sem evidência, as chaves (e os bytes) são as de antes: há consumidores que os fixam
        rep["por_causa"] = por_causa(explained)
    return rep


def por_causa(explained: list) -> dict:
    causes = {}
    for e in explained:
        causes[e["causa"]] = causes.get(e["causa"], 0) + 1
    return dict(sorted(causes.items()))


def _family(page: str) -> list[str]:
    return [page + s[len("_iam"):] for s in IAM_SUFFIXES] if page.endswith("_iam") else []


def _with_evidence(types_left: list, pages_left: list, ev: Evidence, explained: list) -> tuple[list, list]:
    tl = set(types_left)
    pages_out = []
    paired = set()
    for p in pages_left:
        if ev.beta_types is not None:
            hit = sorted(x for x in [p, *_family(p)] if x in ev.beta_types)
            if hit:
                explained.append({"pagina": p, "causa": "so_beta", "tipos_google_beta": hit})
                continue
        t = ev.titles.get(p)
        if t is None:
            pages_out.append(p)                  # sem arquivo conferido ou sem título: sem causa
            continue
        kind, named = t
        if kind == "Data Source":
            if named in ev.data_sources:
                explained.append({"pagina": p, "causa": "data_source_publicado_como_recurso", "titulo_nomeia": named})
                continue
        elif named in tl and named not in paired:
            paired.add(named)
            explained.append({"pagina": p, "causa": "nome_divergente", "titulo_nomeia": named})
            explained.append({"tipo": named, "causa": "nome_divergente", "documentado_como": p})
            continue
        if named not in ev.resources and named not in ev.data_sources and \
                not (ev.beta_types and named in ev.beta_types):
            explained.append({"pagina": p, "causa": "pagina_sem_tipo_no_schema", "titulo_nomeia": named,
                              "titulo_tipo": kind})
            continue
        pages_out.append(p)
    types_out = []
    for t in sorted(tl - paired):
        if t not in ev.resource_titles:
            explained.append({"tipo": t, "causa": "tipo_sem_documentacao"})
        else:
            types_out.append(t)                  # algum título de recurso o nomeia: não é "sem documentação"
    return types_out, pages_out


def gather(provider: str, version: str, types: dict, index: dict, schema_dir: Path | None, docs: Path | None,
           beta_dir: Path | None, cache: Path | None = None) -> Evidence | None:
    """Evidência conferida, ou None se faltar o schema ou as docs (as causas de evidência não se aplicam)."""
    if not (schema_dir and (schema_dir / "receipt.json").exists() and docs and docs.is_dir()):
        return None
    addr = f"registry.terraform.io/{REGISTRY[provider]}"
    ps, sproof = verified_schema(schema_dir, addr, version, cache)
    res = set(ps.get("resource_schemas") or {})
    if res != set(types):
        raise EvidenceError(f"crosscheck: o schema de {schema_dir} não tem os mesmos tipos do types.jsonl")
    page_titles, res_titles, dproof = read_docs(docs, index, provider, version)
    ev = Evidence(set(ps.get("data_source_schemas") or {}), res, page_titles, res_titles,
                  proof={"schema": sproof, "docs": dproof})
    if beta_dir and provider in BETA and (beta_dir / "receipt.json").exists():
        bps, bproof = verified_schema(beta_dir, BETA[provider], version, cache)
        ev.beta_types = set(bps.get("resource_schemas") or {})
        ev.proof["beta"] = bproof
    return ev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.schema.crosscheck", description=__doc__.split("\n")[0])
    ap.add_argument("--provider", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--types", type=Path)
    ap.add_argument("--index", type=Path)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--schema", type=Path)
    ap.add_argument("--docs", type=Path)
    ap.add_argument("--beta-schema", type=Path)
    ap.add_argument("--plugin-cache", type=Path)
    ap.add_argument("--no-evidence", action="store_true", help="só alias e família IAM (o critério antigo)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    tpath = a.types or bo_data() / PRODUCER[a.provider] / "types.jsonl"
    if not tpath.exists():
        print(f"crosscheck: {tpath} não existe (o {PRODUCER[a.provider]} grava o types.jsonl)", file=sys.stderr)
        return 2
    version, types = read_types(tpath)
    ipath = a.index or index_path(a.provider, version)
    if not ipath.exists():
        if not a.fetch:
            print(f"crosscheck: índice {ipath} ausente (use --fetch)", file=sys.stderr)
            return 2
        fetch(a.provider, version, ipath)
    index = json.loads(ipath.read_text(encoding="utf-8"))
    ev = None
    if not a.no_evidence:
        tf = bo_data() / "downloads" / "tfschema"
        try:
            ev = gather(a.provider, version, types, index,
                        a.schema or tf / f"{a.provider}-{version}",
                        a.docs or bo_data() / "downloads" / "prefetch" / a.provider / version / "docs",
                        a.beta_schema or (tf / f"google-beta-{version}" if a.provider in BETA else None),
                        a.plugin_cache)
        except EvidenceError as e:
            print(str(e), file=sys.stderr)
            return 1
    rep = compare(types, documented(index, a.provider, version), ev)
    from bo.repo.core import now
    rep = {"generated_at": now(), "provider": a.provider, "provider_version": version, "types": str(tpath),
           "index": str(ipath), "causas": CAUSES,
           "evidencia": ev.proof if ev else "ausente (só alias_bloco_identico e familia_iam se aplicam)", **rep}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"crosscheck {a.provider} {version}: {rep['tipos_schema']} tipos, {rep['paginas_indice']} páginas, "
          f"{rep['iguais']} iguais, explicadas {por_causa(rep['explicadas']) or '{}'}, sem causa: "
          f"{len(rep['tipos_sem_pagina'])} tipo(s), {len(rep['paginas_sem_tipo'])} página(s) "
          f"[evidência {'conferida' if ev else 'ausente'}] -> {rep['veredito']}")
    for t in rep["tipos_sem_pagina"][:20]:
        print(f"  tipo sem causa: {t}")
    for p in rep["paginas_sem_tipo"][:20]:
        print(f"  página sem causa: {p}")
    return 0 if rep["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
