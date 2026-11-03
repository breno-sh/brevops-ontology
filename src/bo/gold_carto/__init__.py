"""GOLD-CARTO: ouro externo a partir da ontologia do Cartography (commit fixado).

O código do Cartography é DADO: é lido do tarball como texto e interpretado por um avaliador estático restrito
(ast), sem import e sem execução. Os OntologyFieldMapping de AWS, GCP e Azure viram correspondências C09 3.0.0:
âncoras publicadas (campo de nó do provedor -> campo da ontologia do Cartography) e pares derivados entre
provedores pela tabela formal de composição do SEMANTICS (hub: átomo -> conceito <- átomo).
"""

SOURCE_REPO = "https://github.com/cartography-cncf/cartography"
SOURCE_TAG = "0.144.0"
SOURCE_COMMIT = "66ead780c590c2db63947286fa8d5131f44697f8"
SOURCE_COMMIT_DATE = "2026-10-28"
TARBALL = f"cartography-{SOURCE_COMMIT}.tar.gz"
TARBALL_SHA256 = "5f97bebfc87ff400cb72a1fc6e582dc332cd56a65215fa2bab3e98dbd4136bd6"
LICENSE_URI = "https://www.apache.org/licenses/LICENSE-2.0"
PROVIDERS = ("aws", "gcp", "azure")
MODULE_ID = "GOLD-CARTO"
