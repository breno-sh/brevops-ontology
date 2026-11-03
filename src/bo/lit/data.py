"""Fonte única do módulo LIT: entradas bibliográficas, linhas da matriz de posicionamento e os
fatos de Kalinin & Skvortsov 2026 e do CoCoOn.

O gerador (bo.lit.build) escreve daqui lit/related.bib, lit/positioning_matrix.csv e
lit/RELATED_WORK.html; os gates (check_ids, matrix_check, cocoon_disambiguation) leem os três
arquivos gerados e o livro de resolução results/LIT/id_resolution.json (bo.lit.resolve).

Regras de redação:
- Kalinin descrito como está: artigo PUBLICADO, artefato ontológico INDISPONÍVEL.
- Paulo, Vasconcelos e Ferraz (WebMedia 2025) sempre em terceira pessoa.
- Nada de e-mail, id de conta ou valor da empresa. O PDF de Kalinin é só leitura local: daqui sai
  paráfrase com número de página, nunca trecho copiado.
- Toda afirmação sobre um trabalho declara o nível de evidência (coluna evidence_level).
"""

# Data da última edição do conteúdo (America/Recife). O gerador usa este carimbo para que a
# regeneração seja idêntica; muda só quando o conteúdo muda.
EDITED_AT = "2026-11-02T23:40:00-03:00"
RETRIEVED_ON = "2026-11-02"

# ----------------------------------------------------------------------------- bibliografia
# Cada entrada: key, type, fields (ordem de escrita). Campos próprios do LIT:
#   altid             identificadores alternativos "esquema:valor" separados por " ; "
#                     esquemas: isbn, wayback, commit (github:dono/repo@sha40), std, arxiv
#   crossref_mismatch diferença DECLARADA entre a entrada e o registro do Crossref (o check_ids
#                     reprova diferença não declarada)
#   lit_role          papel na matriz (só documentação)

ENTRIES = [
    # --- concorrente direto
    {"key": "kalinin2026unified", "type": "article", "fields": [
        ("author", "Kalinin, Nikolai A. and Skvortsov, Nikolay A."),
        ("title", "Toward a Unified Cloud Resource Ontology for Multicloud Security"),
        ("journal", "Pattern Recognition and Image Analysis"),
        ("volume", "36"), ("number", "2"), ("pages", "558--567"), ("year", "2026"),
        ("publisher", "Pleiades Publishing"),
        ("doi", "10.1134/S1054661826700367"),
        ("note", "Edição especial com artigos selecionados da DAMDID/RCDL-2025. Artigo publicado; "
                 "o artefato ontológico não está disponível (sem link, IRI ou repositório)."),
    ]},
    # --- grafos e ontologias de recursos de nuvem
    {"key": "banse2021cpg", "type": "inproceedings", "fields": [
        ("author", "Banse, Christian and Kunz, Immanuel and Schneider, Angelika and Weiss, Konrad"),
        ("title", "Cloud Property Graph: Connecting Cloud Security Assessments with Static Code Analysis"),
        ("booktitle", "2021 IEEE 14th International Conference on Cloud Computing (CLOUD)"),
        ("pages", "13--19"), ("year", "2021"), ("publisher", "IEEE"),
        ("doi", "10.1109/CLOUD53861.2021.00014"),
    ]},
    {"key": "clouditor2023cpgrepo", "type": "software", "fields": [
        ("author", "{Clouditor project}"),
        ("title", "cloud-property-graph (repositório do Cloud Property Graph)"),
        ("year", "2023"), ("url", "https://github.com/clouditor/cloud-property-graph"),
        ("altid", "commit:github:clouditor/cloud-property-graph@6c7bc074386531bd18ff83e9a2656c1f266839cc"),
        ("note", "Licença Apache-2.0. Último commit em 2023-02-03 (consultado em 2026-11-02)."),
    ]},
    {"key": "banse2023semantic", "type": "inproceedings", "fields": [
        ("author", "Banse, Christian and Kunz, Immanuel and Haas, Nico and Schneider, Angelika"),
        ("title", "A Semantic Evidence-based Approach to Continuous Cloud Service Certification"),
        ("booktitle", "Proceedings of the 38th ACM/SIGAPP Symposium on Applied Computing (SAC)"),
        ("pages", "24--33"), ("year", "2023"), ("publisher", "ACM"),
        ("doi", "10.1145/3555776.3577600"),
    ]},
    {"key": "schoberl2024certgraph", "type": "inproceedings", "fields": [
        ("author", "Schöberl, Stefan and Banse, Christian and Geist, Verena and Kunz, Immanuel and Pinzger, Martin"),
        ("title", "CertGraph: Towards a Comprehensive Knowledge Graph for Cloud Security Certifications"),
        ("booktitle", "Proceedings of the ACM/IEEE 27th International Conference on Model Driven "
                      "Engineering Languages and Systems (MODELS Companion)"),
        ("pages", "76--77"), ("year", "2024"), ("publisher", "ACM"),
        ("doi", "10.1145/3652620.3687795"),
    ]},
    {"key": "corcho2021devopsinfra", "type": "inproceedings", "fields": [
        ("author", "Corcho, Oscar and Chaves-Fraga, David and Toledo, Jhon and Arenas-Guerrero, Julián and "
                   "Badenes-Olmedo, Carlos and Wang, Mingxue and Peng, Hu and Burrett, Nicholas and "
                   "Mora, José and Zhang, Puchao"),
        ("title", "A High-Level Ontology Network for ICT Infrastructures"),
        ("booktitle", "The Semantic Web -- ISWC 2021"), ("series", "Lecture Notes in Computer Science"),
        ("volume", "12922"), ("pages", "446--462"), ("year", "2021"), ("publisher", "Springer"),
        ("doi", "10.1007/978-3-030-88361-4_26"),
        ("altid", "commit:github:oeg-upm/devops-infra@3ac3129a81d24c1239bd91c02f705576a0dab22d ; "
                  "wayback:http://web.archive.org/web/20260214010110/https://oeg-upm.github.io/devops-infra/index.html"),
        ("note", "Rede de ontologias DevOps-Infra; artefato em https://w3id.org/devops-infra/ "
                 "(repositório sem licença declarada no GitHub; último commit em 2023-02-06)."),
    ]},
    {"key": "cartography2026ontology", "type": "software", "fields": [
        ("author", "{Cartography contributors (CNCF)}"),
        ("title", "Cartography: ontology module (semantic labels, abstract nodes, OntologyFieldMapping)"),
        ("year", "2026"), ("url", "https://github.com/cartography-cncf/cartography"),
        ("altid", "commit:github:cartography-cncf/cartography@e978c291082a2b65442ff79ffa4201cce5b11683 ; "
                  "wayback:http://web.archive.org/web/20260520135208/https://github.com/cartography-cncf/cartography/discussions/1579"),
        ("note", "Commit = último que tocou cartography/models/ontology em 2026-10-29. RFC \"Ontology Support in "
                 "Cartography\", discussão 1579, aberta em 2025-05-21. Licença Apache-2.0. Software, sem DOI."),
    ]},
    {"key": "fixinventory2025", "type": "software", "fields": [
        ("author", "{Some Engineering}"),
        ("title", "Fix Inventory (base kinds)"),
        ("year", "2025"), ("url", "https://github.com/someengineering/fixinventory"),
        ("altid", "commit:github:someengineering/fixinventory@211833381fdd07690bc789d30ffc2bd84a67744e"),
        ("note", "Último commit do ramo main em 2025-03-28 (consultado em 2026-11-02). Licença Apache-2.0. "
                 "A revisão R4 cita o prefixo 2118338, que não existe no repositório; o commit é 2118333."),
    ]},
    {"key": "cloudquery2026", "type": "software", "fields": [
        ("author", "{CloudQuery}"),
        ("title", "CloudQuery: data pipelines for cloud configuration and security data"),
        ("year", "2026"), ("url", "https://github.com/cloudquery/cloudquery"),
        ("altid", "commit:github:cloudquery/cloudquery@6f152b61c747d3417e2b4e98438ed6256ceb0fa4 ; "
                  "wayback:http://web.archive.org/web/20260804230727/https://www.cloudquery.io/"),
        ("note", "Licença MPL-2.0. É o coletor de inventário que Kalinin e Skvortsov usam."),
    ]},
    {"key": "steampipeaws2026", "type": "software", "fields": [
        ("author", "{Turbot}"),
        ("title", "steampipe-plugin-aws: SQL tables over AWS resources"),
        ("year", "2026"), ("url", "https://github.com/turbot/steampipe-plugin-aws"),
        ("version", "1.34.1"),
        ("altid", "commit:github:turbot/steampipe-plugin-aws@bb6992d4748caab938e2c691be977d6610fc1fab ; "
                  "wayback:http://web.archive.org/web/20260909064952/https://steampipe.io/"),
        ("note", "Licença Apache-2.0. Um plugin por provedor; sem camada neutra."),
    ]},
    # --- ontologias de serviços de nuvem anteriores (comparadores citados por Kalinin)
    {"key": "moscato2011mosaic", "type": "inproceedings", "fields": [
        ("author", "Moscato, Francesco and Aversa, Rocco and Di Martino, Beniamino and Fortiş, Teodor-Florin and Munteanu, Victor"),
        ("title", "An Analysis of mOSAIC Ontology for Cloud Resources Annotation"),
        ("booktitle", "Proceedings of the Federated Conference on Computer Science and Information Systems (FedCSIS 2011)"),
        ("pages", "973--980"), ("year", "2011"), ("address", "Szczecin, Poland"), ("publisher", "IEEE"),
        ("isbn", "978-83-60810-22-4"),
        ("altid", "isbn:978-83-60810-22-4 ; "
                  "wayback:http://web.archive.org/web/20240620031012/https://annals-csis.org/proceedings/2011/pliks/154.pdf"),
        ("note", "Sem DOI: os anais da FedCSIS 2011 não têm DOI por artigo. ISBN e páginas conferidos no "
                 "cabeçalho do próprio artigo (artigo 154 dos anais). O índice dos anais mostra o ISBN "
                 "978-83-60810-34-4, que reprova no dígito verificador; vale o do artigo."),
    ]},
    {"key": "dimartino2013mosaic", "type": "incollection", "fields": [
        ("author", "Di Martino, Beniamino and Cretella, Giuseppina"),
        ("title", "Semantic Technology for Supporting Software Portability and Interoperability in the "
                  "Cloud -- Contributions from the mOSAIC Project"),
        ("booktitle", "Cloud Computing and Big Data"), ("series", "Advances in Parallel Computing"),
        ("year", "2013"), ("publisher", "IOS Press"),
        ("doi", "10.3233/978-1-61499-322-3-66"),
        ("crossref_mismatch", "authors: o Crossref grava nome e sobrenome juntos no campo family "
                              "(\"Di Martino Beniamino\", \"Cretella Giuseppina\")"),
    ]},
    {"key": "dimartino2014openstack", "type": "inproceedings", "fields": [
        ("author", "Di Martino, Beniamino and Cretella, Giuseppina and Esposito, Antonio and Carta, Graziella"),
        ("title", "Semantic Representation of Cloud Services: A Case Study for Openstack"),
        ("booktitle", "Internet and Distributed Computing Systems (IDCS 2014)"),
        ("series", "Lecture Notes in Computer Science"), ("volume", "8729"),
        ("pages", "39--50"), ("year", "2014"), ("publisher", "Springer"),
        ("doi", "10.1007/978-3-319-11692-1_4"),
        ("note", "É a referência [6] de Kalinin e Skvortsov para a \"Cloud Services Ontology\"."),
    ]},
    {"key": "dimartino2015owl", "type": "article", "fields": [
        ("author", "Di Martino, Beniamino and Cretella, Giuseppina and Esposito, Antonio and Carta, Graziella"),
        ("title", "An OWL Ontology to Support Cloud Portability and Interoperability"),
        ("journal", "International Journal of Web and Grid Services"),
        ("volume", "11"), ("number", "3"), ("pages", "303"), ("year", "2015"), ("publisher", "Inderscience"),
        ("doi", "10.1504/IJWGS.2015.070972"),
        ("crossref_mismatch", "authors: o Crossref grava o primeiro autor como family=\"Martino\", given=\"Beniamino Di\""),
    ]},
    {"key": "dimartino2025cloudontoviz", "type": "article", "fields": [
        ("author", "Di Martino, Beniamino and Esposito, Antonio and Fiorentino, Francesco"),
        ("title", "CloudOntoViz"),
        ("journal", "International Journal on Semantic Web and Information Systems"),
        ("volume", "21"), ("number", "1"), ("pages", "1--24"), ("year", "2025"), ("publisher", "IGI Global"),
        ("doi", "10.4018/ijswis.392474"),
    ]},
    {"key": "zhang2012cocoon", "type": "inproceedings", "fields": [
        ("author", "Zhang, Miranda and Ranjan, Rajiv and Haller, Armin and Georgakopoulos, Dimitrios and "
                   "Menzel, Michael and Nepal, Surya"),
        ("title", "An Ontology-based System for Cloud Infrastructure Services' Discovery"),
        ("booktitle", "8th International Conference on Collaborative Computing: Networking, Applications and "
                      "Worksharing (CollaborateCom 2012)"),
        ("pages", "524--530"), ("year", "2012"), ("address", "Pittsburgh, PA, USA"), ("publisher", "IEEE"),
        ("isbn", "978-1-4673-2740-4"),
        ("doi", "10.4108/icst.collaboratecom.2012.250650"),
        ("altid", "wayback:http://web.archive.org/web/20240810052221/https://ieeexplore.ieee.org/document/6450944"),
        ("crossref_mismatch", "authors: o registro ICST no Crossref lista 5 autores (Nepal primeiro, sem Menzel) "
                              "e não tem páginas; a lista de 6 autores e as páginas 524--530 vêm do IEEE Xplore "
                              "(documento 6450944), que é a forma citada por Kalinin e Skvortsov"),
        ("note", "CoCoOn, versão de 2012 (descoberta de serviços IaaS, base do CloudRecommender). "
                 "É a referência [16] de Kalinin e Skvortsov."),
    ]},
    {"key": "zhang2019cocoon", "type": "inproceedings", "fields": [
        ("author", "Zhang, Qian and Haller, Armin and Wang, Qing"),
        ("title", "CoCoOn: Cloud Computing Ontology for IaaS Price and Performance Comparison"),
        ("booktitle", "The Semantic Web -- ISWC 2019 (Resources Track)"),
        ("series", "Lecture Notes in Computer Science"), ("volume", "11779"),
        ("pages", "325--341"), ("year", "2019"), ("publisher", "Springer"),
        ("doi", "10.1007/978-3-030-30796-7_21"),
        ("altid", "commit:github:miranda-zhang/cloud-computing-schema@32e9cc70ec3729a8002272d9eeac4de5478ab4ee"),
        ("note", "CoCoOn, versão de 2019 (ISWC Resources). É a entrada citada pela revisão R4. Artefato em "
                 "https://w3id.org/cocoon/ (redireciona para o repositório, licença MIT)."),
    ]},
    # --- implantação e padrões de modelo de nuvem
    {"key": "binz2014tosca", "type": "incollection", "fields": [
        ("author", "Binz, Tobias and Breitenbücher, Uwe and Kopp, Oliver and Leymann, Frank"),
        ("title", "TOSCA: Portable Automated Deployment and Management of Cloud Applications"),
        ("booktitle", "Advanced Web Services"), ("pages", "527--549"), ("year", "2014"),
        ("publisher", "Springer"),
        ("doi", "10.1007/978-1-4614-7535-4_22"),
    ]},
    {"key": "oasis2025tosca", "type": "techreport", "fields": [
        ("author", "{OASIS TOSCA Technical Committee}"),
        ("title", "TOSCA Version 2.0"),
        ("institution", "OASIS"), ("type", "OASIS Standard"), ("year", "2025"),
        ("url", "https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html"),
        ("altid", "std:OASIS TOSCA Version 2.0 (OASIS Standard, 2025-07-22) ; "
                  "wayback:http://web.archive.org/web/20261024113947/https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html"),
        ("note", "Substitui TOSCA 1.0 e o Simple Profile in YAML 1.3."),
    ]},
    {"key": "oasis2020toscayaml", "type": "techreport", "fields": [
        ("author", "{OASIS TOSCA Technical Committee}"),
        ("title", "TOSCA Simple Profile in YAML Version 1.3"),
        ("institution", "OASIS"), ("type", "OASIS Standard"), ("year", "2020"),
        ("url", "https://docs.oasis-open.org/tosca/TOSCA-Simple-Profile-YAML/v1.3/os/TOSCA-Simple-Profile-YAML-v1.3-os.html"),
        ("altid", "std:OASIS TOSCA Simple Profile in YAML 1.3 ; "
                  "wayback:http://web.archive.org/web/20261009103055/https://docs.oasis-open.org/tosca/TOSCA-Simple-Profile-YAML/v1.3/os/TOSCA-Simple-Profile-YAML-v1.3-os.html"),
    ]},
    {"key": "wurster2020edmm", "type": "article", "fields": [
        ("author", "Wurster, Michael and Breitenbücher, Uwe and Falkenthal, Michael and Krieger, Christoph and "
                   "Leymann, Frank and Saatkamp, Karoline and Soldani, Jacopo"),
        ("title", "The Essential Deployment Metamodel: A Systematic Review of Deployment Automation Technologies"),
        ("journal", "SICS Software-Intensive Cyber-Physical Systems"),
        ("volume", "35"), ("number", "1--2"), ("pages", "63--75"), ("year", "2020"), ("publisher", "Springer"),
        ("doi", "10.1007/s00450-019-00412-x"),
        ("note", "EDMM. Publicado online em 2019; volume impresso de 2020."),
    ]},
    {"key": "dmtf2016cimi", "type": "techreport", "fields": [
        ("author", "{Distributed Management Task Force}"),
        ("title", "Cloud Infrastructure Management Interface (CIMI) Model and RESTful HTTP-based Protocol"),
        ("institution", "DMTF"), ("type", "DMTF Standard"), ("number", "DSP0263"), ("version", "2.0.0"),
        ("year", "2016"),
        ("url", "https://www.dmtf.org/sites/default/files/standards/documents/DSP0263_2.0.0.pdf"),
        ("altid", "std:DMTF DSP0263 2.0.0 (2016-07-27) ; "
                  "wayback:http://web.archive.org/web/20261011095918/https://www.dmtf.org/sites/default/files/standards/documents/DSP0263_2.0.0.pdf"),
    ]},
    {"key": "ocsf2026schema", "type": "software", "fields": [
        ("author", "{OCSF project}"),
        ("title", "Open Cybersecurity Schema Framework (OCSF) schema"),
        ("year", "2026"), ("version", "1.9.0"), ("url", "https://github.com/ocsf/ocsf-schema"),
        ("altid", "commit:github:ocsf/ocsf-schema@14d7761ffcfdd3c7f68c8df9ddd58aae2765a92e ; "
                  "wayback:http://web.archive.org/web/20261016043138/https://schema.ocsf.io/"),
        ("note", "Licença Apache-2.0. Última release 1.9.0 (2026-08-03); commit do ramo main em 2026-10-30."),
    ]},
    # --- padrões de mapeamento, evidência e engenharia de ontologias
    {"key": "matentzoglu2022sssom", "type": "article", "fields": [
        ("author", "Matentzoglu, Nicolas and Balhoff, James P. and Bello, Susan M. and others"),
        ("title", "A Simple Standard for Sharing Ontological Mappings (SSSOM)"),
        ("journal", "Database"), ("volume", "2022"), ("pages", "baac035"), ("year", "2022"),
        ("publisher", "Oxford University Press"),
        ("doi", "10.1093/database/baac035"),
        ("altid", "commit:github:mapping-commons/sssom@9287d104437ad702fa4e74b1ea2b42a879b877ae"),
    ]},
    {"key": "david2011alignapi", "type": "article", "fields": [
        ("author", "David, Jérôme and Euzenat, Jérôme and Scharffe, François and Trojahn dos Santos, Cássia"),
        ("title", "The Alignment API 4.0"),
        ("journal", "Semantic Web"), ("volume", "2"), ("number", "1"), ("pages", "3--10"), ("year", "2011"),
        ("publisher", "IOS Press"),
        ("doi", "10.3233/SW-2011-0028"),
        ("note", "Referência do EDOAL (Expressive and Declarative Ontology Alignment Language)."),
    ]},
    {"key": "edoal2020spec", "type": "misc", "fields": [
        ("author", "{Alignment API project (INRIA)}"),
        ("title", "EDOAL: Expressive and Declarative Ontology Alignment Language"),
        ("year", "2020"), ("url", "https://moex.gitlabpages.inria.fr/alignapi/edoal.html"),
        ("altid", "wayback:http://web.archive.org/web/20200219205706/http://alignapi.gforge.inria.fr:80/edoal.html"),
        ("note", "Página da especificação; o endereço atual não tem cópia arquivada, a cópia é do endereço anterior (gforge)."),
    ]},
    {"key": "giglio2019eco", "type": "article", "fields": [
        ("author", "Giglio, Michelle and Tauber, Rebecca and Nadendla, Suvarna and others"),
        ("title", "ECO, the Evidence & Conclusion Ontology: Community Standard for Evidence Information"),
        ("journal", "Nucleic Acids Research"), ("volume", "47"), ("number", "D1"), ("pages", "D1186--D1194"),
        ("year", "2019"), ("publisher", "Oxford University Press"),
        ("doi", "10.1093/nar/gky1036"),
        ("altid", "commit:github:evidenceontology/evidenceontology@6bbc0730de4f3d04a5a1347946cd231e40fde4bd"),
    ]},
    {"key": "matentzoglu2022odk", "type": "article", "fields": [
        ("author", "Matentzoglu, Nicolas and Goutte-Gattat, Damien and Tan, Shawn Zheng Kai and others"),
        ("title", "Ontology Development Kit: A Toolkit for Building, Maintaining and Standardizing Biomedical Ontologies"),
        ("journal", "Database"), ("volume", "2022"), ("pages", "baac087"), ("year", "2022"),
        ("publisher", "Oxford University Press"),
        ("doi", "10.1093/database/baac087"),
    ]},
    # --- validade da evidência de schema, deriva e precedentes de venue
    {"key": "qiu2024zodiac", "type": "inproceedings", "fields": [
        ("author", "Qiu, Yiming and Kon, Patrick Tser Jern and Beckett, Ryan and Chen, Ang"),
        ("title", "Unearthing Semantic Checks for Cloud Infrastructure-as-Code Programs"),
        ("booktitle", "Proceedings of the ACM SIGOPS 30th Symposium on Operating Systems Principles (SOSP)"),
        ("pages", "574--589"), ("year", "2024"), ("publisher", "ACM"),
        ("doi", "10.1145/3694715.3695974"),
        ("note", "Zodiac."),
    ]},
    {"key": "gupta2026terramod", "type": "inproceedings", "fields": [
        ("author", "Gupta, Pranjal and Aggarwal, Pooja and Paulovicks, Brent and Mohapatra, Prateeti and Lee, Rong and Sheinin, Vadim"),
        ("title", "Automating Terraform Code Migration through Provider Evolution Knowledge"),
        ("booktitle", "Proceedings of the IEEE/ACM 48th International Conference on Software Engineering (ICSE Companion)"),
        ("pages", "211--215"), ("year", "2026"), ("publisher", "ACM"),
        ("doi", "10.1145/3786582.3786841"),
        ("note", "TerraMod."),
    ]},
    {"key": "ulhaque2022kgsecconfig", "type": "inproceedings", "fields": [
        ("author", "Ul Haque, Mubin and Kholoosi, M. Mehdi and Babar, M. Ali"),
        ("title", "KGSecConfig: A Knowledge Graph Based Approach for Secured Container Orchestrator Configuration"),
        ("booktitle", "2022 IEEE International Conference on Software Analysis, Evolution and Reengineering (SANER)"),
        ("pages", "420--431"), ("year", "2022"), ("publisher", "IEEE"),
        ("doi", "10.1109/SANER53432.2022.00057"),
    ]},
    {"key": "kosinska2023cnont", "type": "article", "fields": [
        ("author", "Kosińska, Joanna and Brotoń, Grzegorz and Tobiasz, Maciej"),
        ("title", "Knowledge Representation of the State of a Cloud-Native Application"),
        ("journal", "International Journal on Software Tools for Technology Transfer"),
        ("volume", "26"), ("number", "1"), ("pages", "21--32"), ("year", "2023"), ("publisher", "Springer"),
        ("doi", "10.1007/s10009-023-00705-2"),
        ("note", "CNOnt. Publicado online em 2023; volume 26 (2024)."),
    ]},
    {"key": "haller2020oneontology", "type": "article", "fields": [
        ("author", "Haller, Armin and Polleres, Axel"),
        ("title", "Are We Better Off with Just One Ontology on the Web?"),
        ("journal", "Semantic Web"), ("volume", "11"), ("number", "1"), ("pages", "87--99"), ("year", "2020"),
        ("publisher", "IOS Press"),
        ("doi", "10.3233/SW-190379"),
    ]},
    # --- ontologias de fundamentação
    {"key": "arp2015bfo", "type": "book", "fields": [
        ("author", "Arp, Robert and Smith, Barry and Spear, Andrew D."),
        ("title", "Building Ontologies with Basic Formal Ontology"),
        ("publisher", "The MIT Press"), ("year", "2015"),
        ("isbn", "978-0-262-52781-1"),
        ("doi", "10.7551/mitpress/9780262527811.001.0001"),
        ("altid", "isbn:978-0-262-52781-1"),
    ]},
    {"key": "iso2021bfo", "type": "techreport", "fields": [
        ("author", "{ISO/IEC JTC 1}"),
        ("title", "Information Technology -- Top-Level Ontologies (TLO) -- Part 2: Basic Formal Ontology (BFO)"),
        ("institution", "ISO/IEC"), ("number", "ISO/IEC 21838-2:2021"), ("year", "2021"),
        ("url", "https://www.iso.org/standard/74572.html"),
        ("altid", "std:ISO/IEC 21838-2:2021 ; "
                  "wayback:http://web.archive.org/web/20261025074801/https://www.iso.org/standard/74572.html ; "
                  "commit:github:BFO-ontology/BFO-2020@bd1fb61c5fa4e358fc9690f0d214b1ac63fae594"),
    ]},
    {"key": "borgo2022dolce", "type": "article", "fields": [
        ("author", "Borgo, Stefano and Ferrario, Roberta and Gangemi, Aldo and Guarino, Nicola and Masolo, Claudio "
                   "and Porello, Daniele and Sanfilippo, Emilio M. and Vieu, Laure"),
        ("title", "DOLCE: A Descriptive Ontology for Linguistic and Cognitive Engineering"),
        ("journal", "Applied Ontology"), ("volume", "17"), ("number", "1"), ("pages", "45--69"), ("year", "2022"),
        ("publisher", "IOS Press"),
        ("doi", "10.3233/AO-210259"),
    ]},
    {"key": "guizzardi2022ufo", "type": "article", "fields": [
        ("author", "Guizzardi, Giancarlo and Botti Benevides, Alessander and Fonseca, Claudenir M. and Porello, Daniele "
                   "and Almeida, João Paulo A. and Prince Sales, Tiago"),
        ("title", "UFO: Unified Foundational Ontology"),
        ("journal", "Applied Ontology"), ("volume", "17"), ("number", "1"), ("pages", "167--210"), ("year", "2022"),
        ("publisher", "IOS Press"),
        ("doi", "10.3233/AO-210256"),
    ]},
    {"key": "gufo2026", "type": "software", "fields": [
        ("author", "{NEMO (UFES)}"),
        ("title", "gUFO: A Lightweight Implementation of the Unified Foundational Ontology"),
        ("year", "2026"), ("url", "http://purl.org/nemo/gufo"),
        ("altid", "commit:github:nemo-ufes/gufo@fa89632534a72dd0ce82f62051cc52b5417150dd ; "
                  "wayback:http://web.archive.org/web/20261014083059/https://nemo-ufes.github.io/gufo/"),
        ("note", "Licença CC-BY-4.0."),
    ]},
    # --- trabalho anterior de coautoria (citado em terceira pessoa)
    {"key": "paulo2025webmedia", "type": "inproceedings", "fields": [
        ("author", "Paulo, Weslley and Vasconcelos, Breno and Ferraz, Carlos"),
        ("title", "Automating Cloud Infrastructure Provisioning with Semantically-Enriched Large Language Models"),
        ("booktitle", "Proceedings of the 31st Brazilian Symposium on Multimedia and the Web (WebMedia 2025)"),
        ("pages", "77--85"), ("year", "2025"), ("publisher", "Sociedade Brasileira de Computação (SBC)"),
        ("doi", "10.5753/webmedia.2025.16102"),
    ]},
    # --- outros relacionados apontados pela revisão R4
    {"key": "kumara2020smells", "type": "inproceedings", "fields": [
        ("author", "Kumara, Indika and Vasileiou, Zoe and Meditskos, Georgios and Tamburri, Damian A. and "
                   "Van Den Heuvel, Willem-Jan and Karakostas, Anastasios and Vrochidis, Stefanos and Kompatsiaris, Ioannis"),
        ("title", "Towards Semantic Detection of Smells in Cloud Infrastructure Code"),
        ("booktitle", "Proceedings of the 10th International Conference on Web Intelligence, Mining and Semantics (WIMS)"),
        ("year", "2020"), ("publisher", "ACM"),
        ("doi", "10.1145/3405962.3405979"),
        ("altid", "arxiv:2007.02135"),
        ("note", "A R4 cita só o preprint arXiv 2007.02135; o arXiv aponta este DOI da versão publicada."),
    ]},
    {"key": "vasileiou2025sodalite", "type": "article", "fields": [
        ("author", "Vasileiou, Zoe and Kumara, Indika and Meditskos, Georgios and Tokmakov, Kamil and others"),
        ("title", "A Knowledge-Based Approach for Guided Development of Infrastructure as Code"),
        ("journal", "Software and Systems Modeling"), ("volume", "25"), ("number", "2"), ("pages", "515--548"),
        ("year", "2025"), ("publisher", "Springer"),
        ("doi", "10.1007/s10270-025-01294-1"),
    ]},
    {"key": "challita2018fclouds", "type": "inproceedings", "fields": [
        ("author", "Challita, Stephanie and Zalila, Faiez and Merle, Philippe"),
        ("title", "Specifying Semantic Interoperability between Heterogeneous Cloud Resources with the FCLOUDS Formal Language"),
        ("booktitle", "2018 IEEE 11th International Conference on Cloud Computing (CLOUD)"),
        ("pages", "367--374"), ("year", "2018"), ("publisher", "IEEE"),
        ("doi", "10.1109/CLOUD.2018.00053"),
    ]},
    {"key": "chiari2024doml", "type": "article", "fields": [
        ("author", "Chiari, Michele and Xiang, Bin and Canzoneri, Sergio and others"),
        ("title", "DOML: A New Modeling Approach to Infrastructure-as-Code"),
        ("journal", "Information Systems"), ("volume", "125"), ("pages", "102422"), ("year", "2024"),
        ("publisher", "Elsevier"),
        ("doi", "10.1016/j.is.2024.102422"),
    ]},
    {"key": "hamdan2024semantic", "type": "article", "fields": [
        ("author", "Hamdan, Norazian M. and Admodisastro, Novia and Osman, Hafeez Bin and Bin Muhammad, Muhammad Sufri"),
        ("title", "Semantic Interoperability in Multi-Cloud Platforms: A Reference Architecture Utilizing an Ontology-Based Approach"),
        ("journal", "International Journal on Advanced Science, Engineering and Information Technology"),
        ("volume", "14"), ("number", "6"), ("pages", "1967--1975"), ("year", "2024"),
        ("doi", "10.18517/ijaseit.14.6.19861"),
    ]},
    {"key": "ketonen2024migration", "type": "inproceedings", "fields": [
        ("author", "Ketonen, Teemu and Smolander, Kari"),
        ("title", "Strategies and Challenges in Cloud-to-Cloud Migration Using Infrastructure as Code"),
        ("booktitle", "Product-Focused Software Process Improvement (PROFES 2024), Industry, Workshop and Doctoral Symposium Papers"),
        ("series", "Lecture Notes in Computer Science"), ("pages", "3--18"), ("year", "2024"), ("publisher", "Springer"),
        ("doi", "10.1007/978-3-031-78392-0_1"),
    ]},
    {"key": "agbaegbu2021survey", "type": "article", "fields": [
        ("author", "Agbaegbu, Josiah and Arogundade, Oluwasefunmi Tale and Misra, Sanjay and Damaševičius, Robertas"),
        ("title", "Ontologies in Cloud Computing -- Review and Future Directions"),
        ("journal", "Future Internet"), ("volume", "13"), ("number", "12"), ("pages", "302"), ("year", "2021"),
        ("publisher", "MDPI"),
        ("doi", "10.3390/fi13120302"),
    ]},
]

# ----------------------------------------------------------------------------- matriz
# Colunas da positioning_matrix.csv. Valores fechados onde dá; NOT_APPLICABLE nunca é zero.
COLUMNS = [
    "row_id", "work", "bibkeys", "kind", "group", "article_status", "artifact_status", "artifact_ref",
    "providers", "model_source", "neutral_layer", "config_attributes", "typed_correspondence",
    "quantitative_eval", "translation", "deploy_validation", "what_it_does", "gap_or_limit",
    "threat_to_novelty", "what_we_must_show", "comparison_axes", "comparator_suggestion",
    "evidence_level", "evidence_detail", "source", "answers",
]

ENUMS = {
    "kind": {"artigo", "software", "padrao", "ontologia_fundacional", "levantamento"},
    "group": {"concorrente_direto", "grafo_ou_ontologia_de_nuvem", "ontologia_de_servicos_anterior",
              "implantacao_e_padrao_de_modelo", "padrao_de_mapeamento_e_evidencia", "validade_da_evidencia",
              "deriva_de_schema", "precedente_de_venue", "justificativa", "ontologia_fundacional",
              "coautoria_terceira_pessoa", "incumbente_industrial", "outros_relacionados"},
    "article_status": {"publicado", "nao_se_aplica"},
    "artifact_status": {"disponivel", "indisponivel", "nao_localizado", "nao_se_aplica"},
    "neutral_layer": {"sim", "nao", "parcial", "NOT_APPLICABLE", "UNKNOWN"},
    "config_attributes": {"sim", "nao", "parcial", "NOT_APPLICABLE", "UNKNOWN"},
    "typed_correspondence": {"sim", "nao", "parcial", "NOT_APPLICABLE", "UNKNOWN"},
    "quantitative_eval": {"sim", "nao", "parcial", "NOT_APPLICABLE", "UNKNOWN"},
    "translation": {"sim", "nao", "parcial", "NOT_APPLICABLE", "UNKNOWN"},
    "deploy_validation": {"sim", "nao", "parcial", "NOT_APPLICABLE", "UNKNOWN"},
    "threat_to_novelty": {"critico", "alto", "medio", "baixo", "nenhum"},
    "comparator_suggestion": {"comparador_artefato", "comparador_documental", "reconstrucao_de_metodo",
                              "reuso_de_padrao", "ameaca_a_validade", "citar", "fora_da_comparacao"},
    "evidence_level": {"texto_integral", "especificacao", "repositorio", "resumo", "descricao_de_terceiro",
                       "metadados"},
}
AXES = {"nativo", "representacao", "traducao", "NOT_APPLICABLE"}

# Nosso estudo (para a coluna providers e para o delta de Kalinin).
OUR_PROVIDERS = ["AWS", "Azure", "GCP", "OCI"]

KALININ = {
    "bibkey": "kalinin2026unified",
    "doi": "10.1134/S1054661826700367",
    "journal": "Pattern Recognition and Image Analysis",
    "volume": "36", "number": "2", "pages": "558--567", "year": "2026",
    "article_status": "publicado",
    "artifact_status": "indisponivel",
    "providers": ["AWS", "Azure", "GCP", "Yandex Cloud", "Cloud.ru"],
    "leave": ["Yandex Cloud", "Cloud.ru"],
    "enter": ["OCI"],
    # termos que a descrição TEM de conter (implementação que existe)
    "implements": ["OWL DL", "owlready2", "ABox", "CSPM", "SQL", "SPARQL", "SWRL", "HermiT"],
    # o que falta (e só isso)
    "missing": ["avaliação quantitativa", "artefato inspecionável"],
    # descrições erradas que não podem voltar (V1 da revisão GPT-6)
    "forbidden": ["não publicado", "nao publicado", "não foi publicado", "unpublished", "not published",
                  "sem implementação", "não implementa", "only the abstract", "só o resumo"],
}

COCOON = {
    "entries": [
        {"bibkey": "zhang2012cocoon", "cited_by": "Kalinin e Skvortsov 2026, referência [16] (p. 567)",
         "first_author_given": "Miranda", "venue_short": "CollaborateCom 2012", "year": "2012",
         "doi": "10.4108/icst.collaboratecom.2012.250650"},
        {"bibkey": "zhang2019cocoon", "cited_by": "revisão R4 (28/10/2026), item 12",
         "first_author_given": "Qian", "venue_short": "ISWC 2019 Resources", "year": "2019",
         "doi": "10.1007/978-3-030-30796-7_21"},
    ],
}


def R(**kw):
    return kw


ROWS = [
    R(row_id="kalinin2026", work="Kalinin & Skvortsov 2026 (ontologia unificada de recursos de nuvem)",
      bibkeys="kalinin2026unified", kind="artigo", group="concorrente_direto",
      article_status="publicado", artifact_status="indisponivel", artifact_ref="NOT_APPLICABLE",
      providers="AWS;Azure;GCP;Yandex Cloud;Cloud.ru", model_source="schemas dos providers Terraform + documentação Terraform e API",
      neutral_layer="sim", config_attributes="sim", typed_correspondence="nao", quantitative_eval="nao",
      translation="nao", deploy_validation="nao",
      what_it_does="Ontologia OWL DL implementada com owlready2, construída de baixo para cima a partir dos schemas "
                   "dos providers Terraform: tipo de recurso vira classe candidata, parâmetro vira propriedade "
                   "candidata; generalização em 6 passos (casamento de propriedades por nome, faixa e interpretação "
                   "de especialista; clusterização parecida com FCA; classe abstrata por cluster; CloudResource no "
                   "topo; ids viram object properties; o resto fica local ao provedor) e 4 camadas. ABox a partir do "
                   "inventário coletado pelo CloudQuery; consultas CSPM em SQL/SPARQL; cadeias de ataque em SWRL "
                   "com HermiT; 5 perguntas de competência de segurança.",
      gap_or_limit="O que falta é avaliação quantitativa (nenhum número de classes, propriedades, cobertura, precisão "
                   "dos alinhamentos ou resultado de teste das 5 CQs) e artefato inspecionável (sem link, IRI ou repositório no "
                   "artigo). Alinhamento por julgamento, sem tipo de equivalência nem 1:N; camada atômica = tipo "
                   "Terraform; sem deriva de schema.",
      threat_to_novelty="critico",
      what_we_must_show="Ontologia a partir de schemas Terraform multi-provedor não é novidade. Temos de medir o que "
                        "eles não medem (invariância do grão, semântica executável, cobertura operacional nas direções "
                        "A→B) e comparar contra uma família de reconstruções do método, relatando a faixa. Frente ao "
                        "nosso estudo (AWS, Azure, GCP, OCI) saem Yandex Cloud e Cloud.ru e entra OCI.",
      comparison_axes="representacao;nativo", comparator_suggestion="reconstrucao_de_metodo",
      evidence_level="texto_integral",
      evidence_detail="PDF lido (uso local): provedores p. 558-559 e 561; 5 CQs e ontologia de topo adiada p. 561; método em 6 passos e camadas p. 561-562; OWL DL e "
                      "owlready2 p. 563; CloudQuery e views SQL p. 563; CSPM em SPARQL p. 564; HermiT e SWRL p. 565; "
                      "protótipo e limitações p. 566; nenhum link de artefato no texto. Busca no GitHub em 2026-11-02 "
                      "sem resultado. Fichamento FICHAMENTO_KALININ2026.txt.",
      source="doi:10.1134/S1054661826700367", answers="R4-W1;V1;F8"),
    R(row_id="cartography", work="Cartography (CNCF), módulo de ontologia",
      bibkeys="cartography2026ontology", kind="software", group="grafo_ou_ontologia_de_nuvem",
      article_status="nao_se_aplica", artifact_status="disponivel",
      artifact_ref="github:cartography-cncf/cartography@e978c291082a2b65442ff79ffa4201cce5b11683",
      providers="AWS;Azure;GCP;Scaleway;outros", model_source="código dos coletores (APIs dos provedores)",
      neutral_layer="sim", config_attributes="parcial", typed_correspondence="nao", quantitative_eval="nao",
      translation="nao", deploy_validation="nao",
      what_it_does="Rótulos semânticos e nós abstratos entre provedores (computeinstance, loadbalancers, "
                   "encryptionkeys, databases, object_storage, vpcs, subnets, firewalls e outros; 42 arquivos de "
                   "mapeamento em cartography/models/ontology/mapping/data) com OntologyFieldMapping e mapas de "
                   "valores para normalizar vocabulários de provedor.",
      gap_or_limit="Valor sem mapeamento vira NULL, sem motivo tipado; sem prova de equivalência; mantido e adotado "
                   "na indústria.",
      threat_to_novelty="critico",
      what_we_must_show="Mostrar numa tarefa compartilhada (mesmo grafo factual, mesmas CQs) o que perdas tipadas e "
                        "evidência mudam; não basta afirmar.",
      comparison_axes="nativo;representacao", comparator_suggestion="comparador_artefato",
      evidence_level="repositorio",
      evidence_detail="Listagem de cartography/models/ontology/mapping/data no ramo master via API do GitHub em "
                      "2026-11-02 (42 módulos .py além de __init__.py); RFC na discussão 1579 (2025-05-21); leitura de campos e de "
                      "NULL segundo a R4 (28/10/2026).",
      source="commit:github:cartography-cncf/cartography@e978c291082a2b65442ff79ffa4201cce5b11683",
      answers="R4-W1;S12"),
    R(row_id="fix", work="Fix Inventory (base kinds)", bibkeys="fixinventory2025", kind="software",
      group="grafo_ou_ontologia_de_nuvem", article_status="nao_se_aplica", artifact_status="disponivel",
      artifact_ref="github:someengineering/fixinventory@211833381fdd07690bc789d30ffc2bd84a67744e",
      providers="AWS;Azure;GCP;Kubernetes", model_source="código dos coletores (APIs dos provedores)",
      neutral_layer="sim", config_attributes="parcial", typed_correspondence="nao", quantitative_eval="nao",
      translation="nao", deploy_validation="nao",
      what_it_does="Classes neutras (base kinds) com subclasses por provedor num grafo de inventário.",
      gap_or_limit="Kinds sem mapeamento são omitidos; repositório sem commit desde 2025-03-28.",
      threat_to_novelty="alto",
      what_we_must_show="Comparação de representação no mesmo grafo factual, com orçamento igual de adaptação.",
      comparison_axes="representacao", comparator_suggestion="comparador_artefato",
      evidence_level="repositorio",
      evidence_detail="Commit e data do último commit via API do GitHub em 2026-11-02; omissão de kinds segundo a R4. "
                      "O prefixo 2118338 citado na R4 não existe; o commit certo é 2118333.",
      source="commit:github:someengineering/fixinventory@211833381fdd07690bc789d30ffc2bd84a67744e",
      answers="R4-W1"),
    R(row_id="cpg", work="Cloud Property Graph (Banse et al. 2021)", bibkeys="banse2021cpg;clouditor2023cpgrepo",
      kind="artigo", group="grafo_ou_ontologia_de_nuvem", article_status="publicado", artifact_status="disponivel",
      artifact_ref="github:clouditor/cloud-property-graph@6c7bc074386531bd18ff83e9a2656c1f266839cc",
      providers="UNKNOWN", model_source="ontologia própria + código (code property graph)",
      neutral_layer="parcial", config_attributes="parcial", typed_correspondence="nao", quantitative_eval="UNKNOWN",
      translation="nao", deploy_validation="nao",
      what_it_does="Liga avaliação de segurança da nuvem à análise estática de código num grafo de propriedades "
                    "gerado de uma ontologia (build-ontology.sh e owl2java no repositório).",
      gap_or_limit="Foco em segurança de aplicação+nuvem, não em portabilidade de configuração.",
      threat_to_novelty="medio",
      what_we_must_show="Comparação nativa na tarefa deles quando aplicável; representação no mesmo grafo factual.",
      comparison_axes="nativo;representacao", comparator_suggestion="comparador_artefato",
      evidence_level="repositorio",
      evidence_detail="Raiz do repositório listada via API do GitHub em 2026-11-02; metadados do artigo no Crossref "
                      "(sem resumo). Provedores e avaliação não conferidos aqui; ficam para o PRIOR.",
      source="doi:10.1109/CLOUD53861.2021.00014", answers="R4-W1"),
    R(row_id="certgraph", work="CertGraph e ontologia de evidência do Clouditor (Banse et al. 2023; Schöberl et al. 2024)",
      bibkeys="schoberl2024certgraph;banse2023semantic", kind="artigo", group="grafo_ou_ontologia_de_nuvem",
      article_status="publicado", artifact_status="nao_localizado", artifact_ref="NOT_APPLICABLE",
      providers="AWS;Azure", model_source="ontologia própria mantida (Clouditor)",
      neutral_layer="sim", config_attributes="parcial", typed_correspondence="nao", quantitative_eval="UNKNOWN",
      translation="nao", deploy_validation="nao",
      what_it_does="Ontologia OWL de recursos de nuvem usada como evidência para certificação contínua (SAC 2023) e "
                   "grafo de conhecimento de certificações de segurança (MODELS Companion 2024).",
      gap_or_limit="Artefato do CertGraph não localizado por busca no GitHub; a ontologia do Clouditor vive no "
                   "código (api/ontology em clouditor/clouditor).",
      threat_to_novelty="medio",
      what_we_must_show="Explicar por que não estender esta ontologia (Haller & Polleres) e comparar representação.",
      comparison_axes="representacao", comparator_suggestion="comparador_documental",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Metadados no Crossref (sem resumo); descrição segundo a R4 (28/10/2026); busca por certgraph no "
                      "GitHub em 2026-11-02 sem repositório do projeto; diretório api/ontology listado em "
                      "clouditor/clouditor. A R4 junta CPG e CertGraph sob os DOIs de 2021 e 2023; aqui são linhas "
                      "separadas e o CertGraph tem o DOI de 2024.",
      source="doi:10.1145/3652620.3687795", answers="R4-W1"),
    R(row_id="devopsinfra", work="DevOps-Infra (Corcho et al., ISWC 2021)", bibkeys="corcho2021devopsinfra",
      kind="artigo", group="grafo_ou_ontologia_de_nuvem", article_status="publicado", artifact_status="disponivel",
      artifact_ref="github:oeg-upm/devops-infra@3ac3129a81d24c1239bd91c02f705576a0dab22d",
      providers="NOT_APPLICABLE", model_source="modelagem de cima para baixo (rede de ontologias)",
      neutral_layer="sim", config_attributes="nao", typed_correspondence="NOT_APPLICABLE", quantitative_eval="UNKNOWN",
      translation="nao", deploy_validation="nao",
      what_it_does="Rede de ontologias de alto nível para infraestrutura de TIC (ambientes, serviços, plataformas de "
                   "implantação, estados de ciclo de vida).",
      gap_or_limit="Segundo Kalinin e Skvortsov (p. 560), não captura recursos e parâmetros de configuração "
                   "específicos de provedor.",
      threat_to_novelty="medio",
      what_we_must_show="Comparação de representação no nível de classe; no nível de atributo é NOT_APPLICABLE, não zero.",
      comparison_axes="representacao", comparator_suggestion="comparador_artefato",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Descrição segundo Kalinin e Skvortsov (p. 560, texto integral); artefato em w3id.org/devops-infra "
                      "e repositório oeg-upm/devops-infra conferidos em 2026-11-02.",
      source="doi:10.1007/978-3-030-88361-4_26", answers="R4-W1;S12"),
    R(row_id="mosaic", work="mOSAIC (Moscato et al. 2011)", bibkeys="moscato2011mosaic;dimartino2013mosaic",
      kind="artigo", group="ontologia_de_servicos_anterior", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="vários (anotação de serviços de nuvem de 2011)",
      model_source="análise de padrões e propostas de nuvem, refinada com indivíduos de nuvens reais",
      neutral_layer="sim", config_attributes="nao", typed_correspondence="nao", quantitative_eval="UNKNOWN",
      translation="nao", deploy_validation="nao",
      what_it_does="Ontologia comum para anotar e negociar serviços de nuvem numa plataforma aberta, para seleção e "
                   "portabilidade em federações de nuvens.",
      gap_or_limit="Nível de serviço, não de configuração; ontologia não localizada como artefato (a organização "
                   "mosaic-cloud no GitHub tem 21 repositórios de plataforma, sem ontologia).",
      threat_to_novelty="baixo",
      what_we_must_show="Comparação documental; o que não se aplica é NOT_APPLICABLE, não zero.",
      comparison_axes="nativo", comparator_suggestion="comparador_documental",
      evidence_level="resumo",
      evidence_detail="Resumo no índice dos anais FedCSIS 2011 (annals-csis.org, artigo 154), cabeçalho do artigo "
                      "(ISBN e páginas) e descrição de Kalinin e Skvortsov (p. 559-560); repositórios de mosaic-cloud "
                      "listados em 2026-11-02.",
      source="isbn:978-83-60810-22-4", answers="S12"),
    R(row_id="cloud_services_ontology", work="Cloud Services Ontology (Di Martino et al. 2014/2015; CloudOntoViz 2025)",
      bibkeys="dimartino2014openstack;dimartino2015owl;dimartino2025cloudontoviz", kind="artigo",
      group="ontologia_de_servicos_anterior", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="AWS;Azure;Google;OpenStack;outros",
      model_source="categorias de serviço típicas entre provedores (modelagem manual)",
      neutral_layer="sim", config_attributes="nao", typed_correspondence="nao", quantitative_eval="UNKNOWN",
      translation="parcial", deploy_validation="nao",
      what_it_does="Ontologia OWL que agrupa ofertas de vários provedores em classes independentes de provedor, com "
                   "ênfase em PaaS e SaaS, para portabilidade e interoperabilidade; CloudOntoViz (2025) simplifica a "
                   "hierarquia da ontologia de referência.",
      gap_or_limit="Nível de categoria de serviço; Kalinin e Skvortsov citam o trabalho de 2014 (OpenStack) mas "
                   "descrevem o conteúdo do artigo de 2015 (ontologia OWL para portabilidade).",
      threat_to_novelty="medio",
      what_we_must_show="Comparação documental, a menos que o PRIOR localize o artefato.",
      comparison_axes="nativo", comparator_suggestion="comparador_documental",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Descrição segundo Kalinin e Skvortsov (p. 560, referência [6]); resumo do CloudOntoViz no "
                      "Crossref; busca no GitHub em 2026-11-02 sem artefato.",
      source="doi:10.1504/IJWGS.2015.070972", answers="S12"),
    R(row_id="cocoon2012", work="CoCoOn 2012 (Zhang, Ranjan, Haller et al., CollaborateCom)", bibkeys="zhang2012cocoon",
      kind="artigo", group="ontologia_de_servicos_anterior", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="Amazon EC2;Microsoft Azure;GoGrid;Rackspace;outros",
      model_source="modelagem manual de serviços IaaS", neutral_layer="sim", config_attributes="parcial",
      typed_correspondence="nao", quantitative_eval="UNKNOWN", translation="nao", deploy_validation="nao",
      what_it_does="Ontologia OWL de serviços IaaS (computação, rede, armazenamento) com propriedades funcionais e não "
                   "funcionais, povoada com ofertas reais, para descoberta e seleção (CloudRecommender).",
      gap_or_limit="Seleção de oferta, não configuração implantada; versão de 2012 sem artefato localizado.",
      threat_to_novelty="baixo",
      what_we_must_show="Comparação documental; ver a desambiguação com a versão de 2019.",
      comparison_axes="nativo", comparator_suggestion="comparador_documental",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Descrição segundo Kalinin e Skvortsov (p. 560, referência [16]); metadados no Crossref (registro "
                      "ICST) e no IEEE Xplore arquivado (documento 6450944).",
      source="doi:10.4108/icst.collaboratecom.2012.250650", answers="S12"),
    R(row_id="cocoon2019", work="CoCoOn 2019 (Zhang, Haller, Wang, ISWC Resources)", bibkeys="zhang2019cocoon",
      kind="artigo", group="precedente_de_venue", article_status="publicado", artifact_status="disponivel",
      artifact_ref="github:miranda-zhang/cloud-computing-schema@32e9cc70ec3729a8002272d9eeac4de5478ab4ee",
      providers="vários provedores IaaS (preço e desempenho)", model_source="modelagem manual + dados de preço e desempenho",
      neutral_layer="sim", config_attributes="parcial", typed_correspondence="nao", quantitative_eval="UNKNOWN",
      translation="nao", deploy_validation="nao",
      what_it_does="Ontologia de computação em nuvem para comparar preço e desempenho de IaaS, publicada como recurso "
                   "com w3id e dados abertos.",
      gap_or_limit="Escopo de comparação de oferta; mostra o que a trilha de recursos do ISWC aceitou (w3id, dados "
                   "abertos, caso de uso).",
      threat_to_novelty="baixo",
      what_we_must_show="Comparação de representação no nível de classe onde houver correspondência; resto "
                        "NOT_APPLICABLE.",
      comparison_axes="representacao", comparator_suggestion="comparador_artefato",
      evidence_level="repositorio",
      evidence_detail="w3id.org/cocoon/ redireciona para miranda-zhang/cloud-computing-schema (MIT, último commit "
                      "2021-08-04), conferido em 2026-11-02; metadados no Crossref; leitura de venue segundo a R4.",
      source="doi:10.1007/978-3-030-30796-7_21", answers="S12"),
    R(row_id="tosca_edmm", work="TOSCA (OASIS) e EDMM (Wurster et al.)",
      bibkeys="oasis2025tosca;oasis2020toscayaml;binz2014tosca;wurster2020edmm", kind="padrao",
      group="implantacao_e_padrao_de_modelo", article_status="nao_se_aplica", artifact_status="disponivel",
      artifact_ref="https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html", providers="NOT_APPLICABLE",
      model_source="padrão (topologia e orquestração) e metamodelo derivado da revisão de tecnologias de implantação",
      neutral_layer="sim", config_attributes="nao", typed_correspondence="nao", quantitative_eval="NOT_APPLICABLE",
      translation="sim", deploy_validation="NOT_APPLICABLE",
      what_it_does="Modelo neutro de topologia (nós, relações, tipos) com orquestração; o EDMM extrai o núcleo comum "
                   "das tecnologias de implantação e permite transformar para elas.",
      gap_or_limit="Neutro no nível de topologia; atributos de configuração de provedor ficam em tipos estendidos.",
      threat_to_novelty="medio",
      what_we_must_show="Comparação de tradução com orçamento igual de adaptação; sem adaptador escrito, é "
                        "NOT_APPLICABLE.",
      comparison_axes="traducao;representacao", comparator_suggestion="comparador_documental",
      evidence_level="especificacao",
      evidence_detail="Página do TOSCA 2.0 lida em 2026-11-02 (OASIS Standard de 2025-07-22, substitui TOSCA 1.0 e o "
                      "Simple Profile YAML 1.3); EDMM por metadados no Crossref e conhecimento de área.",
      source="doi:10.1007/s00450-019-00412-x", answers="S12"),
    R(row_id="cimi", work="DMTF CIMI (DSP0263)", bibkeys="dmtf2016cimi", kind="padrao",
      group="implantacao_e_padrao_de_modelo", article_status="nao_se_aplica", artifact_status="disponivel",
      artifact_ref="https://www.dmtf.org/sites/default/files/standards/documents/DSP0263_2.0.0.pdf",
      providers="NOT_APPLICABLE", model_source="padrão de interface e modelo de recursos IaaS",
      neutral_layer="sim", config_attributes="parcial", typed_correspondence="nao", quantitative_eval="NOT_APPLICABLE",
      translation="nao", deploy_validation="nao",
      what_it_does="Modelo e protocolo REST neutros para gerenciar infraestrutura (máquinas, volumes, redes).",
      gap_or_limit="Padrão de 2016; a adoção pelos 4 provedores do estudo não foi verificada aqui.",
      threat_to_novelty="baixo",
      what_we_must_show="Citar como modelo neutro anterior; comparação documental.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="especificacao",
      evidence_detail="Capa do DSP0263 2.0.0 lida em 2026-11-02 (2016-07-27, substitui 1.1.0, Normative).",
      source="std:DMTF DSP0263 2.0.0 (2016-07-27)", answers="S12"),
    R(row_id="ocsf", work="OCSF (Open Cybersecurity Schema Framework)", bibkeys="ocsf2026schema", kind="padrao",
      group="implantacao_e_padrao_de_modelo", article_status="nao_se_aplica", artifact_status="disponivel",
      artifact_ref="github:ocsf/ocsf-schema@14d7761ffcfdd3c7f68c8df9ddd58aae2765a92e", providers="NOT_APPLICABLE",
      model_source="schema comunitário de eventos e objetos de segurança", neutral_layer="sim",
      config_attributes="parcial", typed_correspondence="nao", quantitative_eval="NOT_APPLICABLE",
      translation="nao", deploy_validation="nao",
      what_it_does="Schema neutro de eventos e objetos de segurança (inclui objetos de recurso de nuvem) para "
                   "normalizar achados entre fornecedores.",
      gap_or_limit="Voltado a eventos e achados, não à configuração implantável.",
      threat_to_novelty="baixo",
      what_we_must_show="Citar; avaliar reuso de vocabulário onde o domínio SEC cruzar.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="repositorio",
      evidence_detail="Commit e release via API do GitHub em 2026-11-02; escopo por conhecimento de área, a confirmar.",
      source="commit:github:ocsf/ocsf-schema@14d7761ffcfdd3c7f68c8df9ddd58aae2765a92e", answers="S12"),
    R(row_id="sssom", work="SSSOM (Matentzoglu et al. 2022)", bibkeys="matentzoglu2022sssom", kind="padrao",
      group="padrao_de_mapeamento_e_evidencia", article_status="publicado", artifact_status="disponivel",
      artifact_ref="github:mapping-commons/sssom@9287d104437ad702fa4e74b1ea2b42a879b877ae", providers="NOT_APPLICABLE",
      model_source="padrão comunitário", neutral_layer="NOT_APPLICABLE", config_attributes="NOT_APPLICABLE",
      typed_correspondence="sim", quantitative_eval="NOT_APPLICABLE", translation="NOT_APPLICABLE",
      deploy_validation="NOT_APPLICABLE",
      what_it_does="Padrão de conjuntos de mapeamento: predicado SKOS por mapeamento, justificativa, autor e revisor, "
                   "confiança, ferramenta e versão.",
      gap_or_limit="Não define semântica operacional de transporte de valor.",
      threat_to_novelty="alto",
      what_we_must_show="Usar SSSOM em vez de formato próprio; metadado de mapeamento não é contribuição. Direção: "
                        "\"a skos:broadMatch b\" quer dizer b mais amplo.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="reuso_de_padrao",
      evidence_level="metadados",
      evidence_detail="Metadados no Crossref; conteúdo do padrão por conhecimento de área e pela R4; repositório "
                      "conferido em 2026-11-02.",
      source="doi:10.1093/database/baac035", answers="R1-M6"),
    R(row_id="edoal", work="EDOAL / Alignment API 4.0 (David et al. 2011)", bibkeys="david2011alignapi;edoal2020spec",
      kind="padrao", group="padrao_de_mapeamento_e_evidencia", article_status="publicado", artifact_status="disponivel",
      artifact_ref="https://moex.gitlabpages.inria.fr/alignapi/edoal.html", providers="NOT_APPLICABLE",
      model_source="linguagem de alinhamento", neutral_layer="NOT_APPLICABLE", config_attributes="NOT_APPLICABLE",
      typed_correspondence="sim", quantitative_eval="NOT_APPLICABLE", translation="parcial",
      deploy_validation="NOT_APPLICABLE",
      what_it_does="Linguagem de correspondências complexas (construtores de classe e propriedade, transformações de "
                   "valor) sobre a Alignment API.",
      gap_or_limit="Expressa correspondência complexa; não prova que ela vale.",
      threat_to_novelty="medio",
      what_we_must_show="Correspondência complexa em EDOAL com exportar e reimportar, em vez de formato próprio.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="reuso_de_padrao",
      evidence_level="metadados",
      evidence_detail="Metadados no Crossref; página da especificação acessível em 2026-11-02 (cópia arquivada do "
                      "endereço gforge anterior).",
      source="doi:10.3233/SW-2011-0028", answers="R1-M6"),
    R(row_id="eco_odk", work="ECO (Giglio et al. 2019) e ODK (Matentzoglu et al. 2022)",
      bibkeys="giglio2019eco;matentzoglu2022odk", kind="padrao", group="padrao_de_mapeamento_e_evidencia",
      article_status="publicado", artifact_status="disponivel",
      artifact_ref="github:evidenceontology/evidenceontology@6bbc0730de4f3d04a5a1347946cd231e40fde4bd",
      providers="NOT_APPLICABLE", model_source="ontologia comunitária e kit de engenharia",
      neutral_layer="NOT_APPLICABLE", config_attributes="NOT_APPLICABLE", typed_correspondence="NOT_APPLICABLE",
      quantitative_eval="NOT_APPLICABLE", translation="NOT_APPLICABLE", deploy_validation="NOT_APPLICABLE",
      what_it_does="Códigos de evidência por asserção (ECO) e pipeline de release congelada, versionada e checada em "
                   "CI (ODK/ROBOT).",
      gap_or_limit="Prática estabelecida, não resultado.",
      threat_to_novelty="alto",
      what_we_must_show="Proveniência por axioma e manifesto com gate são higiene; só contam se uma ablação mostrar que "
                        "mudam o resultado.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="reuso_de_padrao",
      evidence_level="metadados",
      evidence_detail="Metadados no Crossref; leitura de \"higiene, não ciência\" segundo a R4; release do ECO de "
                      "2026-07-10 conferida no GitHub.",
      source="doi:10.1093/nar/gky1036", answers="R4-W1"),
    R(row_id="zodiac", work="Zodiac (Qiu et al., SOSP 2024)", bibkeys="qiu2024zodiac", kind="artigo",
      group="validade_da_evidencia", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="Azure", model_source="mineração de checagens semânticas validadas por implantação",
      neutral_layer="nao", config_attributes="sim", typed_correspondence="NOT_APPLICABLE", quantitative_eval="sim",
      translation="nao", deploy_validation="sim",
      what_it_does="Mostra que programas Terraform válidos no schema ainda violam a semântica da nuvem; minera e valida "
                   "por implantação mais de 500 checagens para o azurerm.",
      gap_or_limit="Um provedor; não é ontologia.",
      threat_to_novelty="alto",
      what_we_must_show="Caminho existente no schema é evidência fraca; a persistência tem de ser verificada por "
                        "implantação e relatada com limites.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="ameaca_a_validade",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Metadados no Crossref; números segundo a R4 (OpenAlex). Artefato não procurado nesta etapa.",
      source="doi:10.1145/3694715.3695974", answers="R4-W1"),
    R(row_id="terramod", work="TerraMod (Gupta et al., ICSE Companion 2026)", bibkeys="gupta2026terramod", kind="artigo",
      group="deriva_de_schema", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="vários (providers Terraform)",
      model_source="schemas, changelogs e depreciações dos providers", neutral_layer="nao", config_attributes="sim",
      typed_correspondence="NOT_APPLICABLE", quantitative_eval="UNKNOWN", translation="parcial", deploy_validation="UNKNOWN",
      what_it_does="Transforma a evolução dos providers (schemas, changelogs, depreciações) em conhecimento para migração "
                   "de código Terraform com LLM.",
      gap_or_limit="Migração entre versões do mesmo provedor, não entre provedores.",
      threat_to_novelty="baixo",
      what_we_must_show="Pins fixos são retrato de alvo móvel: deriva de schema entra como ameaça à validade e hold-out "
                        "temporal.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="ameaca_a_validade",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Metadados no Crossref (pp. 211-215); descrição segundo a R4.",
      source="doi:10.1145/3786582.3786841", answers="R4-W1"),
    R(row_id="kgsecconfig", work="KGSecConfig (Ul Haque et al., SANER 2022)", bibkeys="ulhaque2022kgsecconfig",
      kind="artigo", group="precedente_de_venue", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="Kubernetes (orquestradores de contêiner)",
      model_source="grafo de conhecimento de configuração", neutral_layer="nao", config_attributes="sim",
      typed_correspondence="NOT_APPLICABLE", quantitative_eval="sim", translation="nao", deploy_validation="UNKNOWN",
      what_it_does="Grafo de conhecimento de configuração para detectar má configuração de orquestradores de contêiner.",
      gap_or_limit="Aceito pela tarefa avaliada, não pelo grafo em si.",
      threat_to_novelty="medio",
      what_we_must_show="A barra de venue de engenharia de software é uma tarefa com avaliação, não o artefato.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Metadados no Crossref (pp. 420-431); leitura de venue segundo a R4.",
      source="doi:10.1109/SANER53432.2022.00057", answers="R4-W1"),
    R(row_id="cnont", work="CNOnt (Kosińska et al., STTT 2023)", bibkeys="kosinska2023cnont", kind="artigo",
      group="precedente_de_venue", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="Kubernetes (aplicação cloud-native)",
      model_source="metodologia de engenharia de ontologia", neutral_layer="parcial", config_attributes="parcial",
      typed_correspondence="NOT_APPLICABLE", quantitative_eval="UNKNOWN", translation="nao", deploy_validation="nao",
      what_it_does="Ontologia OWL do estado implantado de aplicações cloud-native, com metodologia e caso de uso.",
      gap_or_limit="Camada de cluster, não de provedor de nuvem.",
      threat_to_novelty="medio",
      what_we_must_show="Metodologia mais caso de uso é o mínimo do venue.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="resumo",
      evidence_detail="Resumo no Crossref; leitura de venue segundo a R4.",
      source="doi:10.1007/s10009-023-00705-2", answers="R4-W1"),
    R(row_id="haller_polleres", work="Haller & Polleres 2020 (uma só ontologia na Web?)", bibkeys="haller2020oneontology",
      kind="artigo", group="justificativa", article_status="publicado", artifact_status="nao_se_aplica",
      artifact_ref="NOT_APPLICABLE", providers="NOT_APPLICABLE", model_source="NOT_APPLICABLE",
      neutral_layer="NOT_APPLICABLE", config_attributes="NOT_APPLICABLE", typed_correspondence="NOT_APPLICABLE",
      quantitative_eval="NOT_APPLICABLE", translation="NOT_APPLICABLE", deploy_validation="NOT_APPLICABLE",
      what_it_does="Discute quando vale criar mais uma ontologia em vez de estender as existentes.",
      gap_or_limit="Argumento, não artefato.",
      threat_to_novelty="nenhum",
      what_we_must_show="Justificar por que não estender CertGraph ou Cartography.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="metadados",
      evidence_detail="Metadados no Crossref; uso sugerido pela R4 (pontos menores).",
      source="doi:10.3233/SW-190379", answers="R4-W1"),
    R(row_id="foundational", work="Ontologias de fundamentação: BFO, DOLCE, UFO/gUFO",
      bibkeys="arp2015bfo;iso2021bfo;borgo2022dolce;guizzardi2022ufo;gufo2026", kind="ontologia_fundacional",
      group="ontologia_fundacional", article_status="publicado", artifact_status="disponivel",
      artifact_ref="github:nemo-ufes/gufo@fa89632534a72dd0ce82f62051cc52b5417150dd", providers="NOT_APPLICABLE",
      model_source="NOT_APPLICABLE", neutral_layer="NOT_APPLICABLE", config_attributes="NOT_APPLICABLE",
      typed_correspondence="NOT_APPLICABLE", quantitative_eval="NOT_APPLICABLE", translation="NOT_APPLICABLE",
      deploy_validation="NOT_APPLICABLE",
      what_it_does="Ontologias de topo: BFO (ISO/IEC 21838-2:2021), DOLCE e UFO, esta com a implementação leve gUFO em "
                   "OWL; base de distinções como rigidez e papéis (OntoClean).",
      gap_or_limit="Kalinin e Skvortsov adiam deliberadamente a escolha da ontologia de topo (p. 561).",
      threat_to_novelty="nenhum",
      what_we_must_show="Declarar a escolha (ou a não escolha) e o que ela muda nos axiomas de rigidez.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="metadados",
      evidence_detail="Metadados no Crossref (DOLCE, UFO, livro BFO); norma ISO arquivada; repositórios BFO-2020 e "
                      "gUFO conferidos em 2026-11-02.",
      source="doi:10.3233/AO-210256", answers="R1-M6"),
    R(row_id="webmedia2025", work="Paulo, Vasconcelos e Ferraz (WebMedia 2025)", bibkeys="paulo2025webmedia",
      kind="artigo", group="coautoria_terceira_pessoa", article_status="publicado", artifact_status="nao_localizado",
      artifact_ref="NOT_APPLICABLE", providers="vários (geração de Terraform no IaC-Eval)",
      model_source="ontologias OWL de conceitos de infraestrutura usadas como contexto de LLM", neutral_layer="parcial",
      config_attributes="UNKNOWN", typed_correspondence="nao", quantitative_eval="sim", translation="nao",
      deploy_validation="UNKNOWN",
      what_it_does="Paulo, Vasconcelos e Ferraz modelam conceitos de infraestrutura em ontologias OWL e usam essa "
                   "representação como contexto estruturado para a geração de Terraform por LLM.",
      gap_or_limit="A ontologia serve de contexto para geração; não é avaliada como modelo neutro nem como caminho de "
                   "tradução entre provedores.",
      threat_to_novelty="alto",
      what_we_must_show="Citar em terceira pessoa e diferenciar; não reaproveitar dados nem números desse trabalho.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="resumo",
      evidence_detail="Resumo no Crossref; uso do IaC-Eval segundo a R4.",
      source="doi:10.5753/webmedia.2025.16102", answers="R4-W6"),
    R(row_id="cloudquery_steampipe", work="CloudQuery e Steampipe (inventário tabular por provedor)",
      bibkeys="cloudquery2026;steampipeaws2026", kind="software", group="incumbente_industrial",
      article_status="nao_se_aplica", artifact_status="disponivel",
      artifact_ref="github:cloudquery/cloudquery@6f152b61c747d3417e2b4e98438ed6256ceb0fa4",
      providers="AWS;Azure;GCP;OCI;outros", model_source="APIs dos provedores (tabelas por provedor)",
      neutral_layer="nao", config_attributes="sim", typed_correspondence="nao", quantitative_eval="NOT_APPLICABLE",
      translation="nao", deploy_validation="nao",
      what_it_does="Coletam inventário e configuração em tabelas SQL por provedor; o CloudQuery é o coletor usado por "
                   "Kalinin e Skvortsov.",
      gap_or_limit="Sem camada neutra: a harmonização fica com quem consulta.",
      threat_to_novelty="baixo",
      what_we_must_show="São os incumbentes da pergunta \"e daí?\": a comparação de tarefa nativa usa os schemas deles.",
      comparison_axes="nativo", comparator_suggestion="comparador_artefato",
      evidence_level="repositorio",
      evidence_detail="Descrições e commits via API do GitHub em 2026-11-02; uso do CloudQuery por Kalinin e Skvortsov "
                      "(p. 563, texto integral).",
      source="commit:github:cloudquery/cloudquery@6f152b61c747d3417e2b4e98438ed6256ceb0fa4", answers="S12"),
    R(row_id="iac_semantics_others", work="Outros: SODALITE (Kumara 2020; Vasileiou 2025), FCLOUDS, DOML, Hamdan 2024, "
                                        "Ketonen & Smolander 2024, Agbaegbu 2021",
      bibkeys="kumara2020smells;vasileiou2025sodalite;challita2018fclouds;chiari2024doml;hamdan2024semantic;"
              "ketonen2024migration;agbaegbu2021survey",
      kind="levantamento", group="outros_relacionados", article_status="publicado", artifact_status="nao_se_aplica",
      artifact_ref="NOT_APPLICABLE", providers="vários", model_source="vários", neutral_layer="parcial",
      config_attributes="parcial", typed_correspondence="nao", quantitative_eval="parcial", translation="parcial",
      deploy_validation="nao",
      what_it_does="Grafos OWL de modelos de implantação consultados por SPARQL (SODALITE); modelos formais por provedor "
                   "com milhares de atributos (FCLOUDS); linguagem de modelagem de IaC (DOML); arquitetura de "
                   "referência que reivindica a mesma lacuna (Hamdan); estratégias de migração entre nuvens com IaC "
                   "(Ketonen e Smolander); levantamento de ontologias de nuvem (Agbaegbu).",
      gap_or_limit="Cada um ocupa uma ideia estrutural (camadas, núcleo neutro, módulos de provedor, alinhamento).",
      threat_to_novelty="medio",
      what_we_must_show="No agregado, mostram que núcleo neutro com módulos de provedor não é novo em espécie.",
      comparison_axes="NOT_APPLICABLE", comparator_suggestion="citar",
      evidence_level="descricao_de_terceiro",
      evidence_detail="Metadados no Crossref; descrições segundo a R4 (itens 9-12); o DOI da versão publicada do "
                      "preprint de Kumara vem do próprio registro no arXiv.",
      source="doi:10.1145/3405962.3405979", answers="R4-W1"),
]
