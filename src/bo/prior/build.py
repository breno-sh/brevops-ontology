"""Gera as saídas do PRIOR a partir das entradas somente leitura e dos downloads fixados (offline).

  python -I -m bo.prior.build            grava $BO_DATA/PRIOR/<model>/{classes.csv, properties.csv, classes.jsonl,
                                         properties.jsonl, provider_links.sssom.tsv, SOURCE.txt},
                                         $BO_DATA/PRIOR/kalinin/METHOD_NOTES.html, $BO_DATA/PRIOR/MANIFEST.sha256,
                                         $BO_REPO/results/PRIOR/inventory.json e results/PRIOR/MANIFEST.sha256
  python -I -m bo.prior.build --check    regenera em $BO_TMP e exige os mesmos bytes (regeneração idêntica)

classes.csv e properties.csv são o inventário nativo (catálogo: tipo doc) com as colunas do C14 onde o artefato as
determina; classes.jsonl e properties.jsonl são a projeção C14 3.0.0 dessas linhas (marcadores explícitos onde o
artefato não determina o campo); provider_links.sssom.tsv é C09 3.0.0. Todo texto nativo passa pelo
privacy_lint campo a campo: campo com achado é omitido e contado, nunca gravado.
"""

from __future__ import annotations

import csv
import filecmp
import io
import json
import os
import shutil
import sys
from pathlib import Path

import yaml

from bo.contracts import sssom as CS
from bo.repo import privacy as PV
from bo.semantics import sssom_io as SIO

from . import kalinin as K
from . import sources as S
from . import x_cartography, x_cloudquery, x_fix, x_owlxml, x_rdf, x_steampipe, x_tosca
from .common import ENCODING, Extract, Link, bo_data, dl, portable, sha256_file, short_hash

ONT = S.ONT
CLASS_COLS = ["class_id", "label", "definition", "parents", "model_role", "status", "evidence_state", "native_id",
              "provider", "layer", "source", "line"]
PROP_COLS = ["property_id", "label", "kind", "domain", "range", "definition", "value_marks", "unknown_marks",
             "status", "evidence_state", "native_id", "provider", "layer", "domain_source", "source", "line"]
NO_DEF = "sem definição no artefato de origem"
NOT_DECLARED = "bo:NotDeclared"
# Marca de valor por modelo para a projeção C14 (julgamento nosso no nível do modelo, não da propriedade):
# coletores de inventário leem a API (observed); modelos de implantação e catálogos descrevem o que se configura.
VALUE_MARKS = {"cpg": ["observed"], "certgraph": ["observed"], "fixinventory": ["observed"],
               "cartography": ["observed"], "steampipe": ["observed"], "cloudquery": ["observed"],
               "kalinin": ["observed"], "tosca-edmm": ["configured"], "devops-infra": ["configured"],
               "cocoon": ["configured"]}
LICENSE_URL = {"Apache-2.0": "https://spdx.org/licenses/Apache-2.0.html", "MIT": "https://spdx.org/licenses/MIT.html",
               "MPL-2.0": "https://spdx.org/licenses/MPL-2.0.html", "CC-BY-4.0": "https://spdx.org/licenses/CC-BY-4.0.html",
               "NOASSERTION": SIO.LICENSE}
ABSENCE_SUBJECT = {
    "devops-infra": ("dvi:core", {"dvi": "http://w3id.org/devops-infra/"},
                     "11 módulos publicados lidos (classes e propriedades do espaço w3id.org/devops-infra); nenhum "
                     "termo, indivíduo ou anotação liga classe a termo de provedor"),
    "cocoon": ("cocoon_onto:v1.0.1", {"cocoon_onto": "https://w3id.org/cocoon/"},
               "ontology_dev/cocoon1.0.1.ttl lido; a ontologia não liga classe a tipo de recurso de provedor (as "
               "ofertas dos provedores estão no despejo de dados data/v1_0_1.ttl, como instâncias, fora do escopo)"),
    "mosaic": ("isbn:978-83-60810-22-4", {"isbn": "urn:isbn:"},
               "só documental: nenhum artefato inspecionável encontrado (buscas no SOURCE.txt)"),
    "cso": ("doi:10.1007/978-3-319-11692-1_4", {"doi": "https://doi.org/"},
            "só documental: nenhum artefato inspecionável encontrado; o texto de Kalinin e Skvortsov diz que a CSO "
            "agrupa ofertas de AWS, Azure e Google em classes comuns, mas nenhuma correspondência é inspecionável"),
}


# --------------------------------------------------------------------------------------------- extratores
def _ls(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern))


def run_model(model: str) -> Extract:
    if model == "cpg":
        root = dl("cpg") / "clouditor__cloud-property-graph"
        p = root / "owl2java/resources/urn_webprotege_ontology_e4316a28-d966-4499-bd93-6be721055117.owx"
        b = "http://graph.clouditor.io/"
        ns = {"cpg": b + "classes/", "cpgprop": b + "properties/", "cpgi_aws": b + "individuals/aws/",
              "cpgi_azure": b + "individuals/azure/", "cpgi_k8s": b + "individuals/k8s/",
              "cpgi_docker": b + "individuals/docker/", "cpgi_lib": b + "individuals/libraries/",
              "cpgi": b + "individuals/"}
        ind = {b + "individuals/aws/": "aws", b + "individuals/azure/": "azurerm",
               b + "individuals/k8s/": "other:kubernetes", b + "individuals/docker/": "other:docker",
               b + "individuals/libraries/": "other:libraries"}
        ex = x_owlxml.extract(model, p, portable(p), ns, ind)
        for extra in ("cloudpg/src/main/java/io/clouditor/graph/passes/Azure.kt",
                      "cloudpg/src/main/java/io/clouditor/graph/passes/KubernetesPass.kt"):
            ex.files.append((portable(root / extra), root / extra))
        ex.notes.append("os passes Azure.kt e KubernetesPass.kt instanciam classes da ontologia a partir de recursos "
                        "Azure e Kubernetes em código; esses vínculos não são declarativos e não foram extraídos "
                        "(só os ClassAssertion publicados na ontologia viram vínculo)")
        return ex
    if model == "certgraph":
        p = Path(f"{ONT}/downloads/certgraph/ontology-merged.owx")
        b = "https://ontology.cybersecuritycertcluster.eu/"
        ns = {"cg": b + "classes/", "cgprop": b + "properties/", "cgi_aws": b + "individuals/aws/",
              "cgi_azure": b + "individuals/azure/", "cgi_k8s": b + "individuals/k8s/",
              "cgi_docker": b + "individuals/docker/", "cgi_lib": b + "individuals/libraries/",
              "cgi": b + "individuals/"}
        ind = {b + "individuals/aws/": "aws", b + "individuals/azure/": "azurerm",
               b + "individuals/k8s/": "other:kubernetes", b + "individuals/docker/": "other:docker",
               b + "individuals/libraries/": "other:libraries"}
        return x_owlxml.extract(model, p, str(p), ns, ind)
    if model == "devops-infra":
        local_dir = Path(f"{ONT}/bakeoff/downloads/devops-infra")
        files = [(str(local_dir / f"{m}.rdf"), local_dir / f"{m}.rdf") for m in ("core", "database", "network",
                                                                                 "server")]
        root = dl(model) / "oeg-upm__devops-infra/ontology"
        for p in _ls(root, "*/ontology.xml"):
            files.append((portable(p), p))
        ns = {f"dvi_{m.replace('-', '_')}": f"http://w3id.org/devops-infra/{m}#" for m in (
            "core", "database", "network", "server", "certificate", "data-center", "hardware", "organisation",
            "product", "software", "workflow")}
        return x_rdf.extract(model, files, ns)
    if model == "fixinventory":
        d = Path(f"{ONT}/bakeoff/downloads/fixinventory")
        base = d / "fixlib/fixlib/baseresources.py"
        plug = []
        for plugdir, sub in (("aws", "fix_plugin_aws/resource"), ("gcp", "fix_plugin_gcp/resources"),
                             ("azure", "fix_plugin_azure/resource")):
            for p in _ls(d / "plugins" / plugdir / sub, "*.py"):
                plug.append((str(p), p, plugdir))
        ex = x_fix.extract(model, (str(base), base), plug)
        ex.files.append((str(d / "SOURCE.txt"), d / "SOURCE.txt"))
        return ex
    if model == "cartography":
        root = dl(model) / "cartography-cncf__cartography"
        ex = x_cartography.extract(model, root, portable(root) + "/")
        return ex
    if model == "steampipe":
        files = []
        for plug, prov in (("aws", "aws"), ("gcp", "google"), ("azure", "azurerm"), ("oci", "oci")):
            for p in _ls(dl(model) / f"turbot__steampipe-plugin-{plug}" / plug, "table_*.go"):
                files.append((portable(p), p, prov))
        return x_steampipe.extract(model, files)
    if model == "cloudquery":
        files = []
        for plug, prov in (("aws", "aws"), ("gcp", "google"), ("azure", "azurerm"), ("oracle", "oci")):
            for p in _ls(dl(model) / f"cloudquery__cloudquery/plugins/source/{plug}/docs/tables", "*.md"):
                if p.name != "README.md":
                    files.append((portable(p), p, prov))
        return x_cloudquery.extract(model, files)
    if model == "cocoon":
        p = dl(model) / "miranda-zhang__cloud-computing-schema/ontology_dev/cocoon1.0.1.ttl"
        return x_rdf.extract(model, [(portable(p), p)], {"cocoon": "https://w3id.org/cocoon/v1.0.1#"})
    if model == "tosca-edmm":
        root = dl(model)
        tos = [(portable(p), p) for p in _ls(root / "oasis-open__tosca-community-contributions/profiles", "**/*.yaml")]
        ed = root / "UST-EDMM__edmm/docs/types.yml"
        ex = x_tosca.extract(model, tos, (portable(ed), ed))
        spec = Path(f"{ONT}/downloads/tosca20/TOSCA-v2.0-os.html")
        txt = spec.read_text(encoding="utf-8", errors="replace")
        ex.files.append((str(spec), spec))
        ex.counts["tosca20_spec_normative_type_names"] = txt.count("tosca.nodes.")
        ex.notes.append("a especificação TOSCA 2.0 lida não define tipos normativos (0 ocorrências de "
                        "'tosca.nodes.'); os tipos vêm dos perfis da comunidade")
        return ex
    if model == "kalinin":
        pdf = Path(f"{ONT}/downloads/kalinin2026/pdfs/kalinin2026.pdf")
        notes = Path(f"{ONT}/downloads/kalinin2026/FICHAMENTO_KALININ2026.txt")
        return K.extract(model, str(pdf), pdf, str(notes), notes)
    if model in ("mosaic", "cso"):
        return Extract(model=model)
    raise KeyError(model)


# --------------------------------------------------------------------------------------------- privacidade
class Scrub:
    def __init__(self):
        self.lists = PV.load_lists()[0]
        self.n = 0
        self.rules: dict[str, int] = {}

    def __call__(self, s: str) -> str:
        if not s:
            return s
        f = PV.scan_text(s, "campo", self.lists)
        if not f:
            return s
        self.n += 1
        for x in f:
            self.rules[x.rule] = self.rules.get(x.rule, 0) + 1
        return "[omitido: o texto nativo tem padrão barrado pelo privacy_lint (" + ",".join(sorted({x.rule for x in f})) + ")]"


# --------------------------------------------------------------------------------------------- escrita
def _csv(rows: list[list], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _layer(prov: str) -> str:
    return "neutral" if not prov else ("provider" if not prov.startswith("other:") else "other_platform")


def _domain(p) -> dict:
    dom = p.domain or []
    if not dom:
        return {"kind": "single", "class": NOT_DECLARED}
    if len(dom) == 1:
        if p.domain_kind == "restriction":
            return {"kind": "local_restriction", "class": dom[0], "restriction": "some"}
        return {"kind": "single", "class": dom[0]}
    return {"kind": "union", "classes": list(dom)}


def tables(ex: Extract, scrub: Scrub) -> tuple[str, str, list, list, dict]:
    marks = VALUE_MARKS.get(ex.model, ["observed"])
    seen, crow, cj, dup_c = set(), [], [], 0
    for c in ex.classes:
        if c.id in seen:
            dup_c += 1
            continue
        seen.add(c.id)
        parents = [{"iri": p, "kind": "nested"} for p in c.parents if p != c.id]
        lab, de = scrub(c.label), scrub(c.definition)
        crow.append([c.id, lab, de, json.dumps(parents, ensure_ascii=False), "Other", "active", c.evidence,
                     scrub(c.native), c.provider, _layer(c.provider), c.source, c.line])
        cj.append({"class_id": c.id, "label": lab if len(lab) >= 2 else f"rótulo {lab}",
                   "definition": de if len(de) >= 10 else NO_DEF, "parents": parents, "model_role": "Other",
                   "status": "active", "evidence_state": c.evidence})
    seen, prow, pj, dup_p = set(), [], [], 0
    for p in ex.props:
        if p.id in seen:
            dup_p += 1
            continue
        seen.add(p.id)
        dom = _domain(p)
        lab, de = scrub(p.label), scrub(p.definition)
        rng = p.range or NOT_DECLARED
        prow.append([p.id, lab, p.kind, json.dumps(dom, ensure_ascii=False), rng, de, json.dumps(marks),
                     json.dumps(["unknown"]), "active", p.evidence, scrub(p.native), p.provider, _layer(p.provider),
                     p.domain_kind, p.source, p.line])
        pj.append({"property_id": p.id, "label": lab if len(lab) >= 2 else f"rótulo {lab}", "kind": p.kind,
                   "domain": dom, "range": rng if "|" not in rng else "bo:NotSingleRange",
                   "definition": de if len(de) >= 10 else NO_DEF, "value_marks": marks, "unknown_marks": ["unknown"],
                   "status": "active", "evidence_state": p.evidence})
    return (_csv(crow, CLASS_COLS), _csv(prow, PROP_COLS), cj, pj,
            {"duplicate_class_ids_dropped": dup_c, "duplicate_property_ids_dropped": dup_p})


def link_records(ex: Extract, m: dict, scrub: Scrub) -> tuple[list[dict], dict]:
    links = list(ex.links)
    pre = dict(ex.prefixes)
    if not links:
        subj, extra, why = ABSENCE_SUBJECT[ex.model]
        pre.update(extra)
        links = [Link(subject=subj, object="sssom:NoTermFound", native_relation="sssom:NoTermFound",
                      link_kind="absence", level="absence", provider="", source="SOURCE.txt", line=0,
                      sentence=why, subject_label=m["title"], object_label="nenhum termo de provedor")]
    pre["sssom"] = "https://w3id.org/sssom/"
    recs, seen = [], {}
    for ln in links:
        key = (ln.subject, ln.object, ln.native_relation)
        if key in seen:
            r = seen[key]
            r["proof"]["evidence"].append({"source": f"{ln.source}:{ln.line}", "sentence": scrub(ln.sentence),
                                           "date": S.EDITED_AT[:10]})
            continue
        rel, reading = ENCODING[ln.native_relation]
        cid = f"PRIOR.{ex.model}.{short_hash(ln.subject, ln.object, ln.native_relation)}"
        pred = {"exact": "skos:exactMatch", "close": "skos:closeMatch", "broad": "skos:broadMatch",
                "narrow": "skos:narrowMatch", "related": "skos:relatedMatch"}[rel]
        note = scrub(ln.note)
        r = {"subject_id": ln.subject, "predicate_id": pred, "object_id": ln.object,
             "mapping_justification": "semapv:ManualMappingCuration",
             "claim_id": cid, "claim_version_id": f"{cid}@1", "event_id": f"EV-{cid}-1",
             "semantic_relation": rel,
             "value_domain_relation": {"relation": "unknown", "orientation": "subject_to_object"},
             "transport_fidelity": "none", "guard": {"all": []}, "loss_contract": [],
             "proof": {"type": "absence_by_inspection" if ln.level == "absence" else "published_by_model",
                       "evidence": [{"source": f"{ln.source}:{ln.line}", "sentence": scrub(ln.sentence),
                                     "date": S.EDITED_AT[:10]}], "tests": []},
             "evidence_state": ln.evidence, "subject_concept": "bo:UNGLOSSED", "object_concept": "bo:UNGLOSSED",
             "subject_label": scrub(ln.subject_label), "object_label": scrub(ln.object_label),
             "subject_source": m.get("repo") or m.get("reference") or "",
             "object_source": m.get("repo") or m.get("reference") or "",
             "mapping_provider": m.get("repo") or m.get("reference") or "",
             "mapping_tool": "bo.prior.build", "mapping_date": S.EDITED_AT[:10],
             "see_also": f"{ln.source}:{ln.line}",
             "curation_rule": f"bo:prior/{ln.native_relation}/{ln.tier}/{ln.link_kind}/{ln.level}",
             "curation_rule_text": reading,
             "comment": ("UNPROVEN: vínculo publicado pelo modelo, transcrito sem prova nossa; "
                         if ln.level != "absence" else "UNPROVEN: ausência por inspeção, não exaustiva; ")
             + f"provedor={ln.provider or 'n/a'}" + (f"; {note}" if note else "")}
        seen[key] = r
        recs.append(r)
    for r in recs:
        r["proof"]["evidence"].sort(key=lambda e: e["source"])
    recs.sort(key=lambda r: (r["subject_id"], r["object_id"], r["claim_id"]))
    return recs, pre


def sssom_text(recs: list[dict], prefixes: dict, model: str, license_id: str) -> str:
    base = dict(SIO.PREFIXES)
    for k in ("pa", "pb", "pc", "pd", "pz"):
        base.pop(k, None)
    base.update(prefixes)
    base["semapv"] = SIO.PREFIXES["semapv"]
    used = set()
    for r in recs:
        for k in ("subject_id", "object_id", "predicate_id", "mapping_justification", "subject_concept",
                  "object_concept"):
            v = r[k]
            if not v.startswith(("http://", "https://")):
                used.add(v.split(":", 1)[0])
    curie = {k: v for k, v in sorted(base.items()) if k in used or k in ("bo", "bosx", "skos", "semapv")}
    t = CS.write_tsv(recs, f"https://w3id.org/brevops/prior/{model}/provider_links", curie)
    head, body = [], []
    for ln in t.splitlines(keepends=True):
        (head if ln.startswith("#") else body).append(ln)
    meta = yaml.safe_load("".join(x[2:] if x.startswith("# ") else x[1:] for x in head))
    meta["license"] = LICENSE_URL[license_id]
    h = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True, default_flow_style=False)
    return "".join(f"# {x}\n" for x in h.splitlines()) + "".join(body)


def source_txt(model: str, m: dict, ex: Extract, out_counts: dict, scrub_n: int) -> str:
    L = [f"PRIOR / {model}: {m['title']}"]
    doc = m["status"] == "documental"
    L.append(f"status: {S.DOCUMENTAL if doc else 'artefato'}")
    L.append("referência: " + (m.get("reference") or m.get("repo")) + " ; bibkeys em $BO_REPO/lit/related.bib: "
             + ", ".join(m["bibkeys"]))
    L.append(f"licença: {m['license']} ({m['license_evidence']})")
    if not doc:
        L.append(f"repositório: {m['repo']}")
        L.append(f"commit: {m['commit']} ({m['commit_date']})")
    if m.get("pin_note"):
        L.append(f"nota de fixação: {m['pin_note']}")
    for s in m.get("searched", []):
        L.append(f"busca: {s}")
    L.append(f"formato nativo: {m['native']}")
    if ex.files:
        L.append("arquivos lidos (sha256  caminho), somente leitura, nunca executados:")
        for lb, p in sorted(ex.files):
            L.append(f"{sha256_file(p)}  {lb}")
    fm = dl(model) / "fetch_manifest.json"
    if m["fetch"]:
        man = json.loads(fm.read_text(encoding="utf-8"))
        L.append(f"download: {portable(fm)} sha256 {sha256_file(fm)}; baixado em {man['retrieved_at']} "
                 f"(America/Recife) por python -I -m bo.prior.fetch {model}; "
                 f"{sum(1 for f in man['files'] if not f.get('archive'))} arquivo(s)")
    L.append("extração: python -I -m bo.prior.build (src/bo/prior); codificação SKOS dos vínculos pela tabela fixa "
             "bo.prior.common.ENCODING; todo vínculo é PUBLICADO pelo modelo (ou afirmado no texto, se só "
             "documental) e fica UNRESOLVED (UNPROVEN): nenhuma correspondência foi provada aqui")
    if ex.classes or ex.props:
        L.append("projeção C14 (classes.jsonl, properties.jsonl): model_role Other; definição ausente vira "
                 f"'{NO_DEF}'; domínio ou imagem ausente vira {NOT_DECLARED}; value_marks "
                 f"{VALUE_MARKS[model]} é julgamento nosso no nível do modelo")
    else:
        L.append("classes.csv e properties.csv só com cabeçalho: sem artefato nem texto lido que nomeie classes; "
                 "sem projeção C14; provider_links.sssom.tsv tem só a linha de ausência (sssom:NoTermFound)")
    for k, v in sorted({**ex.counts, **out_counts}.items()):
        L.append(f"contagem: {k} = {json.dumps(v, ensure_ascii=False, sort_keys=True)}")
    L.append(f"contagem: campos_omitidos_pelo_privacy_lint = {scrub_n}")
    for n in ex.notes:
        L.append(f"nota: {n}")
    L.append(f"editado em: {S.EDITED_AT}")
    return "\n".join(L) + "\n"


CLOUD = ("aws", "google", "azurerm", "oci")
NA_REASON = {"steampipe": "sem camada neutra: toda tabela é de um provedor",
             "cloudquery": "sem camada neutra: toda tabela é de um provedor",
             "devops-infra": "não declara termo de provedor",
             "cocoon": "a ontologia não declara termo de provedor (ofertas só no despejo de dados)",
             "mosaic": "só documental: sem artefato", "cso": "só documental: sem artefato",
             "kalinin": "só documental: sem artefato (as classes vêm de exemplos do texto, não de um inventário)"}


CAVEAT = {"cartography": "; ATENÇÃO: a população só tem os nós que aparecem nos mapeamentos do módulo de ontologia, "
                          "então 1,0 é por construção e não mede cobertura dos módulos do Cartography",
          "cpg": "; população = indivíduos de provedor declarados na ontologia (serviços e produtos, não tipos Terraform)",
          "certgraph": "; população = indivíduos de provedor declarados na ontologia (serviços e produtos, não tipos "
                       "Terraform)"}


def metric(model: str, ex: Extract, recs: list[dict], frame_path: Path, frame_rel: str) -> dict | None:
    """Fração dos termos de provedor (aws, google, azurerm, oci) do artefato com vínculo publicado a um termo neutro
    do próprio modelo. Censo do artefato (sem amostragem): lower = upper = est."""
    if model in NA_REASON:
        return None
    if ex.provider_terms:
        pop = {t for p in CLOUD for t in ex.provider_terms.get(p, [])}
        unit = ex.provider_unit
    else:
        pop = {c.id for c in ex.classes if c.provider in CLOUD}
        unit = "classes (tipos, nós) de provedor"
    # a raiz não conta: classe neutra sem pai que tem filhas neutras (fix:resource, Root dos perfis TOSCA); rótulo
    # plano sem pai e sem filha neutra (Cartography) conta
    has_child = {p for c in ex.classes if not c.provider for p in c.parents}
    neutral = {c.id for c in ex.classes if not c.provider and (c.parents or c.id not in has_child)}
    linked = {r["subject_id"] for r in recs if r["subject_id"] in pop and r["object_id"] in neutral
              and r["curation_rule"].endswith("/class")}
    n = len(pop)
    est = round(len(linked) / n, 6) if n else None
    return {"metric_id": f"M-PRIOR-LINKED-{model.upper().replace('-', '_')}",
            "name": f"{model}: fração dos {unit} com vínculo publicado a termo neutro do modelo abaixo da raiz",
            "reading": "complete_unit", "axis": "representability", "quantifier": "observed_fraction",
            "operational_coverage": {"lower": est if n else 0.0, "upper": est if n else 1.0, "est": est, "n": n},
            "frame": {"ref": {"path": frame_rel, "sha256": sha256_file(frame_path)},
                      "description": f"{unit} (aws, google, azurerm, oci) declarados no artefato fixado do modelo "
                                     f"{model}; numerador: {len(linked)} com vínculo de classe a termo neutro"
                                     + CAVEAT.get(model, "")},
            "inclusion": {"rule_id": "INC-PRIOR-01",
                          "text": "termo cujo provedor é aws, google, azurerm ou oci; vínculo de nível classe "
                                  "publicado pelo próprio modelo a classe neutra que não seja raiz (raiz = sem pai e "
                                  "com filhas neutras); outras plataformas fora"},
            "weights": {"scheme": "uniform"}, "joint_uncertainty": {"method": "none"}}


def build(out_data: Path, out_results: Path) -> dict:
    out_data.mkdir(parents=True, exist_ok=True)
    out_results.mkdir(parents=True, exist_ok=True)
    metrics, not_applicable = [], {}
    inventory = {"schema": "bo.prior.inventory/1", "module": "PRIOR", "edited_at": S.EDITED_AT,
                 "encoding": {k: {"semantic_relation": v[0], "reading": v[1]} for k, v in sorted(ENCODING.items())},
                 "note": "todo vínculo é publicado pelo modelo (ou afirmado no texto, se só documental), transcrito "
                         "sem prova nossa: evidence_state UNRESOLVED (UNPROVEN); 'a skos:broadMatch b' = b mais amplo",
                 "models": {}}
    written = []
    for model in S.ORDER:
        m = S.MODELS[model]
        ex = run_model(model)
        scrub = Scrub()
        ccsv, pcsv, cj, pj, dups = tables(ex, scrub)
        recs, pre = link_records(ex, m, scrub)
        d = out_data / model
        d.mkdir(parents=True, exist_ok=True)
        (d / "classes.csv").write_text(ccsv, encoding="utf-8")
        (d / "properties.csv").write_text(pcsv, encoding="utf-8")
        files = ["classes.csv", "properties.csv", "provider_links.sssom.tsv", "SOURCE.txt"]
        if cj:
            (d / "classes.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n"
                                                     for x in cj), encoding="utf-8")
            files.append("classes.jsonl")
        if pj:
            (d / "properties.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n"
                                                        for x in pj), encoding="utf-8")
            files.append("properties.jsonl")
        (d / "provider_links.sssom.tsv").write_text(sssom_text(recs, pre, model, m["license"]), encoding="utf-8")
        by_rel, by_kind, by_prov = {}, {}, {}
        for r in recs:
            by_rel[r["semantic_relation"]] = by_rel.get(r["semantic_relation"], 0) + 1
            k = r["curation_rule"].split("/")[-2]
            by_kind[k] = by_kind.get(k, 0) + 1
            pv = r["comment"].split("provedor=", 1)[1].split(";", 1)[0]
            by_prov[pv] = by_prov.get(pv, 0) + 1
        oc = {"out_classes": len(cj), "out_properties": len(pj), "out_links": len(recs),
              "out_links_by_relation": dict(sorted(by_rel.items())), "out_links_by_kind": dict(sorted(by_kind.items())),
              "out_links_by_provider": dict(sorted(by_prov.items())), **dups}
        (d / "SOURCE.txt").write_text(source_txt(model, m, ex, oc, scrub.n), encoding="utf-8")
        if model == "kalinin":
            pdf = Path(f"{ONT}/downloads/kalinin2026/pdfs/kalinin2026.pdf")
            notes = Path(f"{ONT}/downloads/kalinin2026/FICHAMENTO_KALININ2026.txt")
            (d / "METHOD_NOTES.html").write_text(K.method_notes_html(S.EDITED_AT, sha256_file(pdf),
                                                                     sha256_file(notes)), encoding="utf-8")
            files.append("METHOD_NOTES.html")
        written += [d / f for f in sorted(files)]
        frame = d / ("provider_links.sssom.tsv" if ex.provider_unit.startswith("indiv") else "classes.csv")
        mt = metric(model, ex, recs, frame, f"$BO_DATA/PRIOR/{model}/{frame.name}")
        if mt:
            metrics.append(mt)
        else:
            not_applicable[model] = NA_REASON[model]
        prov_classes = {}
        for c in ex.classes:
            prov_classes[c.provider or "neutral"] = prov_classes.get(c.provider or "neutral", 0) + 1
        inventory["models"][model] = {
            "status": S.DOCUMENTAL if m["status"] == "documental" else "artefato", "license": m["license"],
            "commit": m.get("commit"), "classes": len(cj), "properties": len(pj), "links": len(recs),
            "classes_by_provider": dict(sorted(prov_classes.items())), **oc,
            "privacy_omitted_fields": scrub.n, "privacy_rules": dict(sorted(scrub.rules.items())),
            "extractor_counts": ex.counts}
    man = "".join(f"{sha256_file(p)}  $BO_DATA/PRIOR/{p.relative_to(out_data)}\n" for p in written)
    (out_data / "MANIFEST.sha256").write_text(man, encoding="utf-8")
    met = out_results / "metrics.json"
    met.write_text(json.dumps({"schema": "bo.prior.metrics/1", "module": "PRIOR", "edited_at": S.EDITED_AT,
                               "results": metrics, "not_applicable": not_applicable,
                               "note": "NOT_APPLICABLE não é zero: o modelo fica fora do denominador"},
                              ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    inv = out_results / "inventory.json"
    inv.write_text(json.dumps(inventory, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out_results / "MANIFEST.sha256").write_text(f"{sha256_file(inv)}  results/PRIOR/inventory.json\n"
                                                  f"{sha256_file(met)}  results/PRIOR/metrics.json\n",
                                                  encoding="utf-8")
    return inventory


def _repo() -> Path:
    return Path(os.environ.get("BO_REPO") or Path(__file__).resolve().parents[3])


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    data, res = bo_data() / "PRIOR", _repo() / "results" / "PRIOR"
    if argv[:1] == ["--check"]:
        tmp = Path(os.environ.get("BO_TMP") or bo_data() / "tmp" / "PRIOR") / "build_check"
        shutil.rmtree(tmp, ignore_errors=True)
        build(tmp / "data", tmp / "results")
        bad = []
        for sub, ref in (("data", data), ("results", res)):
            for p in sorted((tmp / sub).rglob("*")):
                if p.is_file():
                    q = ref / p.relative_to(tmp / sub)
                    if not q.is_file() or not filecmp.cmp(p, q, shallow=False):
                        bad.append(str(q))
        n = sum(1 for p in (tmp / "data").rglob("*") if p.is_file()) + 2
        for b in bad:
            print(f"FAIL regenerado difere: {b}")
        print(("OK" if not bad else "REPROVADO") + f": {n} arquivo(s) regenerados e comparados byte a byte")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1 if bad else 0
    inv = build(data, res)
    for k, v in inv["models"].items():
        print(f"{k:13s} {v['status']:14s} classes={v['classes']:6d} props={v['properties']:6d} "
              f"links={v['links']:6d} omitidos={v['privacy_omitted_fields']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
