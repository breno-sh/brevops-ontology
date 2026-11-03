"""Registro declarativo dos 12 modelos anteriores do PRIOR (índice {model} do modulos.json).

Cada modelo diz: de onde vem o artefato (commit, licença), o que é entrada local somente leitura, o que se baixa
(sempre fixado por commit, para $BO_DATA/downloads/prior-<model>/, nunca executado) e, quando não há artefato,
a marca 'só documental' com a referência. Os bibkeys apontam para $BO_REPO/lit/related.bib (módulo LIT).

Nada aqui é inferido: commit, licença e data foram conferidos na API do GitHub em 2026-11-03 (America/Recife);
onde o commit difere do fixado pelo LIT, o motivo está em `pin_note`.
"""

from __future__ import annotations

ONT = "/Users/breno/doutorado/pesquisa/superficie/reports/ontologia_neutra"
DOCUMENTAL = "só documental"

# Fuso e data de edição do conteúdo deste registro (carimbo fixo: a regeneração tem de dar os mesmos bytes).
EDITED_AT = "2026-11-03T02:10:00-03:00"

MODELS: dict[str, dict] = {
    "cpg": {
        "title": "Cloud Property Graph (Clouditor)",
        "bibkeys": ["banse2021cpg", "clouditor2023cpgrepo"],
        "status": "artifact",
        "license": "Apache-2.0",
        "license_evidence": "LICENSE na raiz do repositório no commit; API do GitHub: spdx Apache-2.0",
        "repo": "https://github.com/clouditor/cloud-property-graph",
        "commit": "6c7bc074386531bd18ff83e9a2656c1f266839cc",
        "commit_date": "2023-02-03",
        "inputs": [],
        "fetch": [{"kind": "raw", "repo": "clouditor/cloud-property-graph",
                   "commit": "6c7bc074386531bd18ff83e9a2656c1f266839cc",
                   "paths": ["LICENSE", "README.md", "build-ontology.sh", "owl2java/README.md",
                             "owl2java/resources/urn_webprotege_ontology_e4316a28-d966-4499-bd93-6be721055117.owx",
                             "cloudpg/src/main/java/io/clouditor/graph/passes/Azure.kt",
                             "cloudpg/src/main/java/io/clouditor/graph/passes/CloudResourceDiscoveryPass.kt",
                             "cloudpg/src/main/java/io/clouditor/graph/passes/KubernetesPass.kt"]}],
        "native": "OWL/XML (WebProtégé) da ontologia de recursos de nuvem do Clouditor, usada para gerar as classes "
                  "Kotlin; os passes Azure.kt e KubernetesPass.kt criam nós dessas classes a partir de recursos.",
    },
    "certgraph": {
        "title": "CertGraph (ontologia do Cybersecurity Certification Hub, sucessora da do Clouditor/EMERALD)",
        "bibkeys": ["schoberl2024certgraph", "banse2023semantic"],
        "status": "artifact",
        "license": "Apache-2.0",
        "license_evidence": "LICENSE do repositório Cybersecurity-Certification-Hub/security-metrics no commit",
        "repo": "https://github.com/Cybersecurity-Certification-Hub/security-metrics",
        "commit": "2bdcb9254723385db41fa49e376fe8e756d81b55",
        "commit_date": "2026-10-14",
        "pin_note": "commit identificado pelo blob git do arquivo local (cd0c9f8f…) = blob de "
                    "ontology/v1/ontology-merged.owx em 2bdcb925; o main já avançou (b3fca1cf, 2026-10-29), "
                    "mas a entrada congelada do plano é o arquivo baixado em 28/10.",
        "blob_check": {"path": "ontology/v1/ontology-merged.owx",
                       "git_blob": "cd0c9f8f838922ccf529c294ed9c89b2a07c0a30",
                       "local": f"{ONT}/downloads/certgraph/ontology-merged.owx"},
        "inputs": [f"{ONT}/downloads/certgraph/"],
        "fetch": [{"kind": "raw", "repo": "Cybersecurity-Certification-Hub/security-metrics",
                   "commit": "2bdcb9254723385db41fa49e376fe8e756d81b55", "paths": ["LICENSE"]}],
        "native": "OWL/XML (ontology-merged.owx): classes, data e object properties, SubClassOf.",
    },
    "devops-infra": {
        "title": "DevOps-Infra (OEG-UPM), rede de ontologias de infraestrutura de TIC",
        "bibkeys": ["corcho2021devopsinfra"],
        "status": "artifact",
        "license": "CC-BY-4.0",
        "license_evidence": "o repositório não declara licença no GitHub; cada ontology.xml declara "
                            "dcterms:license https://creativecommons.org/licenses/by/4.0",
        "repo": "https://github.com/oeg-upm/devops-infra",
        "commit": "3ac3129a81d24c1239bd91c02f705576a0dab22d",
        "commit_date": "2023-02-06",
        "pin_note": "os 4 módulos da entrada local (core, database, network, server) têm o mesmo blob git que "
                    "ontology/<m>/ontology.xml no commit; os outros 7 publicados são baixados no mesmo commit; "
                    "os 4 do catálogo (service, resource-req, network-security-load-balancing, hws) não "
                    "estão publicados (registro de 28/10 em bakeoff/downloads/devops-infra/extra4/SOURCE.txt).",
        "inputs": [f"{ONT}/bakeoff/downloads/devops-infra/"],
        "fetch": [{"kind": "raw", "repo": "oeg-upm/devops-infra",
                   "commit": "3ac3129a81d24c1239bd91c02f705576a0dab22d",
                   "paths": ["README.md"] + [f"ontology/{m}/ontology.xml" for m in (
                       "certificate", "data-center", "hardware", "organisation", "product", "software",
                       "workflow")]}],
        "native": "RDF/XML (OWL), 11 módulos publicados.",
    },
    "fixinventory": {
        "title": "Fix Inventory (base kinds e kinds por nuvem)",
        "bibkeys": ["fixinventory2025"],
        "status": "artifact",
        "license": "Apache-2.0",
        "license_evidence": "SOURCE.txt da entrada local e LICENSE do repositório no commit",
        "repo": "https://github.com/someengineering/fixinventory",
        "commit": "211833381fdd07690bc789d30ffc2bd84a67744e",
        "commit_date": "2025-03-28",
        "inputs": [f"{ONT}/bakeoff/downloads/fixinventory/"],
        "fetch": [{"kind": "raw", "repo": "someengineering/fixinventory",
                   "commit": "211833381fdd07690bc789d30ffc2bd84a67744e", "paths": ["LICENSE"]}],
        "native": "classes Python (dataclasses attrs) com kind, _kind_display, _kind_description e herança; "
                  "lidas por AST, nunca importadas.",
    },
    "cartography": {
        "title": "Cartography: módulo de ontologia (rótulos semânticos, nós abstratos, OntologyFieldMapping)",
        "bibkeys": ["cartography2026ontology"],
        "status": "artifact",
        "license": "Apache-2.0",
        "license_evidence": "LICENSE do repositório no commit",
        "repo": "https://github.com/cartography-cncf/cartography",
        "commit": "e978c291082a2b65442ff79ffa4201cce5b11683",
        "commit_date": "2026-10-29",
        "inputs": [],
        "fetch": [{"kind": "tree", "repo": "cartography-cncf/cartography",
                   "commit": "e978c291082a2b65442ff79ffa4201cce5b11683",
                   "prefix": "cartography/models/ontology/", "suffix": ".py", "extra": ["LICENSE"]}],
        "native": "módulos Python declarativos (OntologyMapping, OntologyNodeMapping, OntologyFieldMapping e "
                  "esquemas CartographyNodeSchema); lidos por AST, nunca importados.",
    },
    "steampipe": {
        "title": "Steampipe: tabelas dos plugins AWS, GCP, Azure e OCI",
        "bibkeys": ["steampipeaws2026"],
        "status": "artifact",
        "license": "Apache-2.0",
        "license_evidence": "LICENSE de cada um dos 4 repositórios no commit",
        "repo": "https://github.com/turbot/steampipe-plugin-aws (+ -gcp, -azure, -oci)",
        "commit": "aws@bb6992d4748caab938e2c691be977d6610fc1fab gcp@c9651aefd05e36b946ce80881c6100869210ba97 "
                  "azure@4d653f90a56343504988f90775b567d91b3e2dd9 oci@ac16c3883401c8a31126e97948aae89adc6d4838",
        "commit_date": "aws 2026-10-26; gcp 2026-05-21; azure 2026-10-27; oci 2026-06-01",
        "pin_note": "o LIT fixa só o plugin AWS (bb6992d4); GCP, Azure e OCI fixados no HEAD do main em 2026-11-03.",
        "inputs": [],
        "fetch": [{"kind": "tar", "repo": f"turbot/steampipe-plugin-{p}", "commit": c, "provider": prov,
                   "include": rf"^[^/]+/({p}/table_[a-z0-9_]+\.go|LICENSE)$"}
                  for p, c, prov in (("aws", "bb6992d4748caab938e2c691be977d6610fc1fab", "aws"),
                                     ("gcp", "c9651aefd05e36b946ce80881c6100869210ba97", "google"),
                                     ("azure", "4d653f90a56343504988f90775b567d91b3e2dd9", "azurerm"),
                                     ("oci", "ac16c3883401c8a31126e97948aae89adc6d4838", "oci"))],
        "native": "código Go: cada table_*.go declara a tabela (Name, Description) e as colunas "
                  "(Name, Type, Description); lido por expressão regular, nunca compilado.",
    },
    "cloudquery": {
        "title": "CloudQuery: tabelas dos plugins de origem AWS, GCP, Azure e Oracle",
        "bibkeys": ["cloudquery2026"],
        "status": "artifact",
        "license": "MPL-2.0",
        "license_evidence": "LICENSE na raiz do repositório no commit (MPL-2.0)",
        "repo": "https://github.com/cloudquery/cloudquery",
        "commit": "6d350d213594615cb9f06a622a4c6ab0768c67f4",
        "commit_date": "2024-03-04",
        "pin_note": "o LIT fixa cloudquery@6f152b61 (2026), mas nesse commit plugins/source/aws só tem views/: os "
                    "plugins pagos saíram do repositório em 19b6912c (2024-04-24) e parte das tabelas AWS já "
                    "tinha ido para o pago em 229d4e0c (2024-03-04). O commit usado é o pai de 229d4e0c, o "
                    "último com o plugin AWS aberto completo (707 páginas de tabela). Kalinin e Skvortsov usam "
                    "o CloudQuery em 2025-26, quando o plugin AWS já era fechado: a versão deles não é esta.",
        "inputs": [],
        "fetch": [{"kind": "tree", "repo": "cloudquery/cloudquery",
                   "commit": "6d350d213594615cb9f06a622a4c6ab0768c67f4",
                   "regex": r"^(plugins/source/(aws|gcp|azure|oracle)/docs/tables/[a-z0-9_]+\.md|LICENSE)$"}],
        "native": "páginas Markdown geradas pelo plugin (docs/tables/<tabela>.md): título, descrição, chave "
                  "primária, relações pai/filho e a tabela de colunas (nome, tipo).",
    },
    "mosaic": {
        "title": "mOSAIC ontology (Moscato et al. 2011)",
        "bibkeys": ["moscato2011mosaic", "dimartino2013mosaic"],
        "status": "documental",
        "license": "NOASSERTION",
        "license_evidence": "sem artefato: não há licença de artefato a declarar",
        "reference": "Moscato et al., FedCSIS 2011, pp. 973-980, ISBN 978-83-60810-22-4 (related.bib: "
                     "moscato2011mosaic); Di Martino e Cretella 2013, DOI 10.3233/978-1-61499-322-3-66",
        "searched": [
            "GitHub, organização mosaic-cloud (21 repositórios, todos de plataforma; listados em 2026-11-03): "
            "nenhum contém ontologia OWL",
            "GitHub code search 'org:mosaic-cloud extension:owl' e 'org:mosaic-cloud ontology': 0 resultados "
            "(2026-11-03)",
            "domínio mosaic-cloud.eu: hoje redireciona para um site comercial sem relação com o projeto "
            "(2026-11-03)",
        ],
        "inputs": [],
        "fetch": [],
        "native": "nenhum artefato inspecionável encontrado.",
    },
    "cso": {
        "title": "Cloud Services Ontology (Di Martino et al. 2014/2015)",
        "bibkeys": ["dimartino2014openstack", "dimartino2015owl", "dimartino2025cloudontoviz"],
        "status": "documental",
        "license": "NOASSERTION",
        "license_evidence": "sem artefato: não há licença de artefato a declarar",
        "reference": "Di Martino, Cretella, Esposito e Carta, IDCS 2014, LNCS 8729, pp. 39-50, "
                     "DOI 10.1007/978-3-319-11692-1_4 (referência [6] de Kalinin e Skvortsov); IJWGS 11(3) 2015, "
                     "DOI 10.1504/IJWGS.2015.070972",
        "searched": [
            "GitHub code search 'CloudServicesOntology' e 'mosaic_ontology cloud': 0 resultados (2026-11-03)",
            "GitHub repository search 'cloud services ontology owl di martino', 'cloud ontology portability "
            "interoperability owl', 'cloudontoviz': 0 resultados (2026-11-03)",
        ],
        "inputs": [],
        "fetch": [],
        "native": "nenhum artefato inspecionável encontrado; os artigos não são de acesso aberto e não foram lidos "
                  "aqui, então nenhuma classe é listada.",
    },
    "cocoon": {
        "title": "CoCoOn: Cloud Computing Ontology (versão de 2019, ISWC Resources)",
        "bibkeys": ["zhang2019cocoon", "zhang2012cocoon"],
        "status": "artifact",
        "license": "MIT",
        "license_evidence": "LICENSE do repositório no commit; API do GitHub: spdx MIT",
        "repo": "https://github.com/miranda-zhang/cloud-computing-schema",
        "commit": "32e9cc70ec3729a8002272d9eeac4de5478ab4ee",
        "commit_date": "2021-08-04",
        "pin_note": "o artefato é o da versão de 2019 (w3id.org/cocoon/v1.0.1). A versão de 2012 (CollaborateCom, "
                    "a que Kalinin e Skvortsov citam como [16]) não tem artefato público: para ela, só documental "
                    "(desambiguação em results/LIT/cocoon_disambiguation.json).",
        "inputs": [],
        "fetch": [{"kind": "raw", "repo": "miranda-zhang/cloud-computing-schema",
                   "commit": "32e9cc70ec3729a8002272d9eeac4de5478ab4ee",
                   "paths": ["LICENSE", "README.md", "ontology_dev/README.md", "ontology_dev/cocoon1.0.1.ttl"]}],
        "native": "Turtle (OWL): classes, propriedades, subClassOf.",
    },
    "tosca-edmm": {
        "title": "TOSCA 2.0 (perfis da comunidade OASIS) e EDMM",
        "bibkeys": ["oasis2025tosca", "oasis2020toscayaml", "binz2014tosca", "wurster2020edmm"],
        "status": "artifact",
        "license": "Apache-2.0",
        "license_evidence": "LICENSE de oasis-open/tosca-community-contributions e de UST-EDMM/edmm nos commits; "
                            "a especificação TOSCA 2.0 (entrada local) é texto OASIS, só lido",
        "repo": "https://github.com/oasis-open/tosca-community-contributions + https://github.com/UST-EDMM/edmm",
        "commit": "tosca-community-contributions@2669d67991961e6aa7919a885ebc535bdb1bd2c5 "
                  "edmm@7f550a19155a702474f512e54ff2ddb148c003dd",
        "commit_date": "tosca-community 2026-10-27; edmm 2023-02-14",
        "pin_note": "a especificação TOSCA 2.0 (entrada local) não traz tipos normativos (são perfis à parte); "
                    "as classes vêm dos perfis da comunidade e do docs/types.yml do EDMM.",
        "inputs": [f"{ONT}/downloads/tosca20/"],
        "fetch": [{"kind": "raw", "repo": "oasis-open/tosca-community-contributions",
                   "commit": "2669d67991961e6aa7919a885ebc535bdb1bd2c5",
                   "paths": ["LICENSE"] + [f"profiles/{p}" for p in (
                       "community/edmm.yaml",
                       "community/tosca/abstract/application/profile.yaml",
                       "community/tosca/abstract/base/profile.yaml",
                       "community/tosca/abstract/data/profile.yaml",
                       "community/tosca/abstract/network/profile.yaml",
                       "community/tosca/abstract/platform/profile.yaml",
                       "community/tosca/core/profile.yaml",
                       "community/tosca/technology/base/profile.yaml",
                       "org/oasis-open/simple/2.0/profile.yaml",
                       "com/ubicity/2.5/profile.yaml",
                       "com/ubicity/core/2.5/profile.yaml",
                       "com/ubicity/net/2.5/profile.yaml",
                       "com/amazon/aws/2.5/profile.yaml",
                       "com/google/cloud/2.5/profile.yaml",
                       "com/microsoft/azure/2.5/profile.yaml",
                       "io/terraform/1.0/profile.yaml")]},
                  {"kind": "raw", "repo": "UST-EDMM/edmm", "commit": "7f550a19155a702474f512e54ff2ddb148c003dd",
                   "paths": ["LICENSE", "docs/types.yml"]}],
        "native": "YAML TOSCA 2.0 (node_types, relationship_types, capability_types com derived_from) e o "
                  "types.yml do EDMM (component_types e relation_types com extends).",
    },
    "kalinin": {
        "title": "Kalinin e Skvortsov 2026, ontologia unificada de recursos de nuvem",
        "bibkeys": ["kalinin2026unified"],
        "status": "documental",
        "license": "NOASSERTION",
        "license_evidence": "sem artefato; o artigo (Pleiades Publishing) foi lido do PDF local, que não é "
                            "redistribuído nem copiado",
        "reference": "Kalinin e Skvortsov, Pattern Recognition and Image Analysis 36(2):558-567, 2026, "
                     "DOI 10.1134/S1054661826700367 (related.bib: kalinin2026unified)",
        "searched": [
            "o artigo publicado não traz link, IRI nem repositório do artefato (leitura do texto completo, "
            "2026-11-03); fichamento em ontologia_neutra/downloads/kalinin2026/FICHAMENTO_KALININ2026.txt",
        ],
        "inputs": [f"{ONT}/downloads/kalinin2026/FICHAMENTO_KALININ2026.txt",
                   f"{ONT}/downloads/kalinin2026/pdfs/kalinin2026.pdf"],
        "fetch": [],
        "native": "texto do artigo: classes, propriedades e vínculos citados nominalmente, com a página.",
    },
}

ORDER = ["cpg", "certgraph", "devops-infra", "fixinventory", "cartography", "steampipe", "cloudquery", "mosaic",
         "cso", "cocoon", "tosca-edmm", "kalinin"]
assert sorted(ORDER) == sorted(MODELS), "ORDER e MODELS divergem"
