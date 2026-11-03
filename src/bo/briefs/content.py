"""O que cada papel lê, o que é proibido, quem consome cada brief e o que o lint exige.

Fonte única dos três artefatos derivados: briefs/read_allowlists.json (o bo-lane lê 'roles.<papel>.read'),
o texto 'O QUE VOCÊ PODE LER' de cada brief e as checagens de bo.briefs.lint e bo.briefs.allowlists.
"""

from __future__ import annotations

import re

# ------------------------------------------------------------------------------------- listas de leitura
# Modelos aceitos pelo bo-lane (tools/bo-lane, bo.repo.lane.expand_template): $OWNS, $INPUTS e caminhos com
# $WT (a worktree da lane) ou $BO_DATA. A lane soma a isso, sempre: $BO_DATA/<ID>, $BO_TMP, locks/, o diretório
# comum do git, a cadeia de ferramentas e o brief e os gates do próprio módulo no plano.
INFRA = ["$WT/src/", "$WT/tools/", "$WT/contracts/", "$WT/modules/", "$WT/freeze/", "$WT/Makefile",
         "$WT/pyproject.toml", "$WT/requirements.lock", "$WT/CONVENTIONS.html", "$WT/.bo/", "$WT/.claude/",
         "$WT/.git"]
PACKAGE = ["$OWNS", "$INPUTS"]

BRIEF_OF = {"glossarist": "GLOSSARY_BRIEF.txt", "mapper": "MAPPER_BRIEF.txt", "hunter": "NONEHUNT_BRIEF.txt",
            "auditor": "AUDITOR_BRIEF.txt", "evaluator": "VALIDATOR_BRIEF.txt"}


def _own(role):
    return ["$WT/briefs/" + BRIEF_OF[role]]


ROLE_READ = {
    "glossarist": PACKAGE + _own("glossarist") + INFRA + ["$WT/grain/", "$WT/ontology/patterns/naming_rules.yaml",
                                     "$WT/semantics/SEMANTICS.html"],
    "mapper": PACKAGE + _own("mapper") + INFRA + ["$WT/semantics/", "$WT/transforms/", "$WT/arbiter/RULES.html"],
    "hunter": PACKAGE + _own("hunter") + INFRA + ["$WT/semantics/", "$WT/transforms/", "$WT/arbiter/RULES.html"],
    "auditor": PACKAGE + _own("auditor") + INFRA + ["$WT/semantics/", "$WT/grain/", "$WT/ontology/patterns/naming_rules.yaml",
                                  "$WT/domain/domain_contracts.yaml", "$BO_DATA/SPLIT/training_projection/",
                                  "$BO_DATA/DOCS-*/docs_facts.jsonl", "$BO_DATA/SCHEMA-*/atoms.jsonl"],
    "evaluator": PACKAGE + _own("evaluator") + INFRA + ["$WT/semantics/", "$WT/transforms/", "$WT/prereg/"],
}

WHY_READ = {
    "$OWNS": "o que é seu (código, testes, gate, resultados, dados do módulo)",
    "$INPUTS": "as entradas que o seu módulo declara no catálogo (inclui este brief)",
    "$WT/src/": "código do repositório (bibliotecas congeladas: bo.semantics, bo.contracts, bo.transforms...)",
    "$WT/tools/": "ferramentas comuns (gate_smoke, consume_check, provenance, lock...)",
    "$WT/contracts/": "JSON Schema, stubs e regras dos contratos C00-C29",
    "$WT/modules/": "retrato do catálogo e estado (STALE/CURRENT)",
    "$WT/freeze/": "comprovantes de congelamento (só hashes)",
    "$WT/semantics/": "teoria das correspondências, tabela de composição e contraexemplos (SEMANTICS)",
    "$WT/semantics/SEMANTICS.html": "teoria das correspondências (por que âncora é alegação)",
    "$WT/transforms/": "registro FECHADO de transformações, combinadores e gramática de guarda (C10)",
    "$WT/arbiter/RULES.html": "regras congeladas do árbitro (o que ele confere na sua saída)",
    "$WT/grain/": "procedimento de grão canônico (mecânico, provisório até o GRAIN-REPRO)",
    "$WT/ontology/patterns/naming_rules.yaml": "regras de nome: tokens de provedor proibidos em rótulo e definição",
    "$WT/domain/domain_contracts.yaml": "contratos de domínio: identidade, dono, alcance, unidades de decisão",
    "$BO_DATA/SPLIT/training_projection/": "projeção de TREINO (o que pode ser citado); nunca a de teste",
    "$BO_DATA/DOCS-*/docs_facts.jsonl": "fatos de documentação por atributo, com nível (publicado/derivado/interpretado)",
    "$BO_DATA/SCHEMA-*/atoms.jsonl": "átomos dos schemas fixados (para conferir que o átomo citado existe)",
    "$WT/prereg/": "pré-registro: métricas, critérios e consequências escritos antes dos dados",
}
for _r, _f in BRIEF_OF.items():
    WHY_READ["$WT/briefs/" + _f] = "este brief (também quando o catálogo não o lista como entrada do módulo)"
for _k in INFRA:
    WHY_READ.setdefault(_k, "infraestrutura do repositório (Makefile, convenções, lane, git)")

# ----------------------------------------------------------------------------------- partição de teste
# Nunca legível por papel restrito antes do UNSEAL; depois dele, só por módulo que dependa do UNSEAL.
TEST_PARTITION = ["$BO_DATA/SPLIT/sealed/", "$BO_DATA/SPLIT/holdout_units.json.enc", "$BO_DATA/UNSEAL/"]

# Material de avaliação: nenhum papel de construção (glossarista, mapeador, caçador, auditor) lê.
EVAL_DATA = r"^\$BO_DATA/(GOLD-|PILOT-(NET|STO)-ORACLE|JUDGE|DEP-|PROBE|DEPSAMPLE|DISPUTE-SAMPLE|GOLDEVAL|HOLDOUT|UNSEAL|MATRIX|PAIRWISE|TRANSLATOR)"
EVAL_REPO = r"^\$WT/(pilot/|results/(GOLD|JUDGE|GOLDEVAL|PROBE|DEP|MATRIX|HOLDOUT|PILOT-EXIT))"

# Saídas de outros papéis que cada papel NÃO lê (separação de papéis, §9.1). O dado do próprio módulo é exceção.
ROLE_FORBID = {
    "glossarist": [EVAL_DATA, EVAL_REPO, r"^\$BO_DATA/(MAP-|PILOT-(NET|STO)-MAP|CAND|RECONCILE|RELIAB|NONEHUNT-|GLOSSARY-AUDIT)"],
    "mapper": [EVAL_DATA, EVAL_REPO, r"^\$BO_DATA/(MAP-|PILOT-(NET|STO)-MAP|GLOSSARY-|PILOT-(NET|STO)-GLOSS/(glossary|claims)|RELIAB|NONEHUNT-|RECONCILE)"],
    "hunter": [EVAL_DATA, EVAL_REPO, r"^\$BO_DATA/(MAP-|PILOT-(NET|STO)-MAP|GLOSSARY-|CAND|RELIAB|NONEHUNT-)"],
    "auditor": [EVAL_DATA, EVAL_REPO, r"^\$BO_DATA/(MAP-|PILOT-(NET|STO)-MAP|CAND|RECONCILE|RELIAB|NONEHUNT-)"],
    "evaluator": [],
}

# Módulos que o coordenador lança como avaliador (o padrão do bo-lane não deduz este papel pelo ID).
EVALUATOR_MODULES = ["PILOT-EXIT"]
# Consumidores que o padrão do bo-lane põe como builder mas que precisam do papel do brief (ex.: o segundo
# mapeador cego): o coordenador lança com --role explícito.
LAUNCH_ROLE_OVERRIDE = {"RELIAB": "mapper", "PILOT-EXIT": "evaluator"}

# --------------------------------------------------------------------------- caminhos de avaliação no texto
# Nenhum brief cita caminho de avaliação (nem para proibir): a proibição é dita por nome, sem endereço.
EVAL_PATH_PATTERNS = [
    r"SPLIT/sealed", r"holdout_units", r"\.json\.enc", r"UNSEAL/", r"test_partition", r"ORACLE/sealed",
    r"expected_answers", r"fixtures_calib", r"pilot/(net|sto)/", r"gold_audited", r"\$BO_DATA/GOLD",
    r"GOLD-(AUDIT|CARTO|LIBCLOUD|XPLANE|MODS)", r"GOLDEVAL", r"\$BO_DATA/(JUDGE|DEPSAMPLE|DISPUTE-SAMPLE|PROBE-JOIN|HOLDOUT)",
    r"DEP-(AWS|GCP|AZURE|OCI)-[AB]", r"brevops-keys", r"pair_judgements", r"readback\.jsonl", r"outcomes\.jsonl",
]

# Vocabulário de nuvem que não pode aparecer nos EXEMPLOS (o texto normativo pode citar o nome do provider
# Terraform, mas nunca um par real de atributos: seria a resposta de uma célula do estudo).
REAL_VOCAB = ["aws", "amazon", "gcp", "google", "azure", "azurerm", "microsoft", "oci", "oracle", "ec2", "s3",
              "vpc", "vnet", "vcn", "arn", "ocid", "gke", "eks", "aks", "lambda", "dynamodb", "cosmosdb",
              "bigquery", "cloudwatch", "stackdriver", "nsg", "elb", "alb", "bucket", "glacier", "coldline",
              "nearline", "security_group", "firewall", "ingress", "egress", "cidr", "versioning", "kms"]

# ------------------------------------------------------------------------------------------ lint por brief
COMMON_REQUIRED = {
    "três campos": [r"semantic_relation", r"value_domain_relation", r"transport_fidelity"],
    "direção SKOS": [r"a skos:broadMatch b", r"b é o mais amplo", r"a skos:narrowMatch b", r"b é o mais estreito"],
    "UNPROVEN": [r"\bUNPROVEN\b", r"sem prova"],
    "separação de papéis": [r"[Qq]uem define conceito não mapeia", r"átomo→conceito←átomo", r"ALEGAÇÃO"],
    "proibidos": [r"^PROIBIDO", r"[Nn]uvem"],
    "lista de leitura": [r"^O QUE VOCÊ PODE LER"],
    "proveniência": [r"^PROVENIÊNCIA A PREENCHER", r"model_id", r"claude-opus-5-5", r"brief_sha256",
                     r"tools/provenance\.py record", r"--param", r"entradas"],
    "despachante e pacote próprio": [r"despachante", r"main\(argv\) -> int", r"src/bo/<seu pacote>/"],
    "escada de evidência": [r"STRUCTURALLY_VALID", r"DOC_SUPPORTED", r"PERSISTENCE_VERIFIED",
                            r"OBSERVATION_TESTED", r"UNRESOLVED"],
}
ROLE_REQUIRED = {
    "glossarist": {
        "alegação auditada": [r"ancorar .*dois provedores.* é uma ALEGAÇÃO", r"GLOSSARY-AUDIT",
                              r"counterexample_search", r"extraction_method", r"evidence_level"],
        "não mapeia": [r"nunca átomo↔átomo", r"bo:UNGLOSSED"],
        "rótulo neutro e grandeza": [r"NOT_APPLICABLE", r"UNKNOWN", r"QUDT", r"token de provedor"],
        "treino": [r"projeção de treino"],
        "C20": [r"python -I -m bo\.contracts\.validate glossary", r"claims\.jsonl", r"decisions\.jsonl"],
    },
    "mapper": {
        "guarda": [r"\bguard\b", r"edition_in", r"version_range", r"CONDITION_INDETERMINATE"],
        "projeção por ocorrência": [r"projection", r"key_fields", r"nunca (pela )?posição"],
        "predicado de pertença": [r"membership_predicate", r"subset", r"members", r"non_members"],
        "ida e volta": [r"[Ii]da e volta", r"OUT_OF_SUBSET", r"skos:narrowMatch"],
        "escrita C09": [r"bo\.contracts\.sssom", r"write_tsv", r"bo\.semantics\.sssom_io\.write_tsv"],
        "ausência tipada": [r"sssom:NoTermFound", r"bo:NONE_"],
        "registro fechado": [r"transforms\.yaml", r"registry_only"],
        "grupo": [r"bo_group_id", r"variáveis nomeadas"],
    },
    "hunter": {
        "adversarial": [r"descobertas adversariais", r"não é amostra", r"nunca extrapol"],
        "alvo existe": [r"schema fixado", r"bo\.nonehunt\.check"],
        "escrita C09": [r"bo\.contracts\.sssom", r"disputes\.jsonl", r"see_also"],
        "não mapeou": [r"[Qq]uem caça erro não mapeou"],
    },
    "auditor": {
        "auditoria átomo→conceito": [r"[Aa]udit[ae] cada alegação átomo→conceito", r"indirect_anchor",
                                     r"same_quantity_distinction", r"counterexample", r"no_test_in_train"],
        "hipótese de alinhamento": [r"hipótese de alinhamento"],
        "publicado × interpretado": [r"published", r"interpreted", r"model_id"],
        "não escreveu glossário": [r"não escreveu"],
        "C20": [r"glossary_audit\.jsonl", r"supersedes"],
    },
    "evaluator": {
        "código congelado": [r"código congelado", r"sha"],
        "sem ajuste": [r"[Nn]ão ajuste", r"resultado nulo"],
        "limites": [r"NOT_READABLE", r"INFRA_ERROR", r"limite inferior", r"limite superior"],
        "não implementou": [r"não implementou"],
    },
}

SECTION_RX = re.compile(r"^([A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ,/()×→←\-]+)$", re.M)
