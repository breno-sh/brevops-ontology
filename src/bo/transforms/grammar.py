"""Conteúdo de transforms/conditions.grammar.json (C10 conditions_grammar) e as suítes de satisfatibilidade.

SAT_TESTS vão para o arquivo e são conferidos pelo validador do C10 (C10-SAT, contra bo.semantics.guards) e pelo
bo.transforms.guard_sat (contra esta implementação e o oráculo de força bruta). INCOMPATIBLE_PAIRS são guardas
satisfazíveis sozinhas cuja interseção é vazia; COMPATIBLE_PAIRS, o controle (interseção satisfazível).
"""

from __future__ import annotations


def A(term, op, value):
    return {"term": term, "op": op, "value": value}


def G(*atoms, term_types=None, kind_disjoint=None):
    g = {"all": list(atoms)}
    if term_types:
        g["term_types"] = term_types
    if kind_disjoint:
        g["kind_disjoint"] = kind_disjoint
    return g


STR = {"datatype": "string"}
INT = {"datatype": "integer"}
BOOL = {"datatype": "boolean"}
TIER = {"datatype": "enum", "enum": ["basic", "standard", "premium"]}

SAT_TESTS = [
    ("SAT-EMPTY", G(), "SAT"),
    ("SAT-EDITION-ONE", G(A("object.edition", "edition_in", ["standard"])), "SAT"),
    ("SAT-EDITION-DISJ", G(A("object.edition", "edition_in", ["standard"]),
                           A("object.edition", "edition_in", ["premium"])), "UNSAT"),
    ("SAT-KIND-OPEN", G(A("object.target", "refers_to_kind", "subnet"),
                        A("object.target", "refers_to_kind", "network_interface")), "UNKNOWN"),
    ("SAT-KIND-DISJOINT", G(A("object.target", "refers_to_kind", "subnet"),
                            A("object.target", "refers_to_kind", "network_interface"),
                            kind_disjoint=[["subnet", "network_interface"]]), "UNSAT"),
    ("SAT-KIND-SAME", G(A("object.target", "refers_to_kind", "subnet"),
                        A("object.target", "refers_to_kind", "subnet")), "SAT"),
    ("SAT-REGION-OVERLAP", G(A("object.region", "region_in", ["r-a", "r-b"]),
                             A("object.region", "region_in", ["r-b", "r-c"])), "SAT"),
    ("SAT-REGION-DISJ", G(A("object.region", "region_in", ["r-a"]), A("object.region", "region_in", ["r-b"])),
     "UNSAT"),
    ("SAT-TWO-ROLES", G(A("subject.region", "region_in", ["r-a"]), A("object.region", "region_in", ["r-b"])), "SAT"),
    ("SAT-VERSION-OVERLAP", G(A("object.provider_version", "version_range", {"min": "5.0", "max_exclusive": "6.0"}),
                              A("object.provider_version", "version_range", {"min": "5.5", "max_exclusive": "7"})),
     "SAT"),
    ("SAT-VERSION-DISJ", G(A("object.provider_version", "version_range", {"min": "4.0", "max_exclusive": "5.0"}),
                           A("object.provider_version", "version_range", {"min": "5.0", "max_exclusive": "6.0"})),
     "UNSAT"),
    ("SAT-VERSION-BELOW-ZERO", G(A("object.provider_version", "version_range", {"max_exclusive": "0"})), "UNSAT"),
    ("SAT-VERSION-IN", G(A("object.provider_version", "in", ["4.9", "5.1"]),
                         A("object.provider_version", "version_range", {"min": "5.0"}),
                         term_types={"object.provider_version": STR}), "SAT"),
    ("SAT-VERSION-IN-DISJ", G(A("object.provider_version", "in", ["4.9", "4.10"]),
                              A("object.provider_version", "version_range", {"min": "5.0"}),
                              term_types={"object.provider_version": STR}), "UNSAT"),
    ("SAT-PRESENT-ONLY", G(A("object.kms_key", "present", True)), "SAT"),
    ("SAT-ABSENT-ONLY", G(A("object.kms_key", "present", False)), "SAT"),
    ("SAT-PRESENT-CONFLICT", G(A("object.kms_key", "present", True), A("object.kms_key", "present", False)), "UNSAT"),
    ("SAT-ABSENT-WITH-VALUE", G(A("object.tier", "present", False), A("object.tier", "eq", "standard"),
                                term_types={"object.tier": TIER}), "UNSAT"),
    ("SAT-EQ-IN", G(A("object.name", "eq", "a"), A("object.name", "in", ["a", "b"]),
                    term_types={"object.name": STR}), "SAT"),
    ("SAT-EQ-IN-DISJ", G(A("object.name", "eq", "a"), A("object.name", "in", ["b", "c"]),
                         term_types={"object.name": STR}), "UNSAT"),
    ("SAT-BOOL-CONFLICT", G(A("object.enabled", "eq", True), A("object.enabled", "eq", False),
                            term_types={"object.enabled": BOOL}), "UNSAT"),
    ("SAT-ENUM-IN", G(A("object.tier", "in", ["basic", "standard"]), A("object.tier", "in", ["standard", "premium"]),
                      term_types={"object.tier": TIER}), "SAT"),
    ("SAT-INT-IN-DISJ", G(A("object.port", "in", [80, 443]), A("object.port", "eq", 22),
                          term_types={"object.port": INT}), "UNSAT"),
    ("SAT-VERSION-CLOSED-UNIVERSE", G(A("object.provider_version", "version_range", {"min": "6"}),
                                      term_types={"object.provider_version": {"datatype": "enum",
                                                                              "enum": ["4.9", "5.0"]}}), "UNSAT"),
    ("SAT-VERSION-CLOSED-UNIVERSE-OK", G(A("object.provider_version", "version_range", {"min": "5"}),
                                         term_types={"object.provider_version": {"datatype": "enum",
                                                                                 "enum": ["4.9", "5.0"]}}), "SAT"),
    ("SAT-VERSION-INTEGER-TERM", G(A("object.provider_version", "version_range", {"min": "1"}),
                                   term_types={"object.provider_version": INT}), "UNSAT"),
    ("SAT-KIND-WITH-VALUE", G(A("object.target", "refers_to_kind", "subnet"), A("object.target", "eq", "ref-a"),
                              term_types={"object.target": STR}), "UNSAT"),
    ("SAT-KIND-OPEN-WITH-VALUE", G(A("object.target", "refers_to_kind", "subnet"),
                                   A("object.target", "refers_to_kind", "vpc"), A("object.target", "eq", "ref-a"),
                                   term_types={"object.target": STR}), "UNSAT"),
    ("SAT-KIND-CLOSED-UNIVERSE", G(A("object.target", "refers_to_kind", "subnet"),
                                   term_types={"object.target": TIER}), "UNSAT"),
    ("SAT-UNSAT-DOMINATES", G(A("object.target", "refers_to_kind", "subnet"),
                              A("object.target", "refers_to_kind", "network_interface"),
                              A("object.region", "region_in", ["r-a"]), A("object.region", "region_in", ["r-b"])),
     "UNSAT"),
]

# (id, g1, g2): cada uma SAT sozinha, interseção UNSAT
INCOMPATIBLE_PAIRS = [
    ("X-REGION", G(A("object.region", "region_in", ["r-a", "r-b"])), G(A("object.region", "region_in", ["r-c"]))),
    ("X-EDITION", G(A("object.edition", "edition_in", ["standard"])), G(A("object.edition", "edition_in", ["premium"]))),
    ("X-VERSION", G(A("object.provider_version", "version_range", {"max_exclusive": "5.0"})),
     G(A("object.provider_version", "version_range", {"min": "5.0"}))),
    ("X-PRESENT", G(A("object.kms_key", "present", True)), G(A("object.kms_key", "present", False))),
    ("X-ABSENT-VALUE", G(A("object.kms_key", "present", False)),
     G(A("object.kms_key", "eq", "alias-a"), term_types={"object.kms_key": STR})),
    ("X-STRING", G(A("object.name", "in", ["a", "b"]), term_types={"object.name": STR}),
     G(A("object.name", "eq", "c"), term_types={"object.name": STR})),
    ("X-BOOL", G(A("object.enabled", "eq", True), term_types={"object.enabled": BOOL}),
     G(A("object.enabled", "eq", False), term_types={"object.enabled": BOOL})),
    ("X-INT", G(A("object.port", "in", [80, 443]), term_types={"object.port": INT}),
     G(A("object.port", "in", [22, 3389]), term_types={"object.port": INT})),
    ("X-ENUM", G(A("object.tier", "in", ["basic"]), term_types={"object.tier": TIER}),
     G(A("object.tier", "in", ["premium", "standard"]), term_types={"object.tier": TIER})),
    ("X-KIND", G(A("object.target", "refers_to_kind", "subnet"), kind_disjoint=[["subnet", "network_interface"]]),
     G(A("object.target", "refers_to_kind", "network_interface"))),
    ("X-SUBJECT", G(A("subject.region", "region_in", ["r-a"]), A("object.edition", "edition_in", ["standard"])),
     G(A("subject.region", "region_in", ["r-b"]))),
]

COMPATIBLE_PAIRS = [
    ("C-REGION", G(A("object.region", "region_in", ["r-a", "r-b"])), G(A("object.region", "region_in", ["r-b", "r-c"]))),
    ("C-VERSION", G(A("object.provider_version", "version_range", {"max_exclusive": "5.1"})),
     G(A("object.provider_version", "version_range", {"min": "5.0"}))),
    ("C-OTHER-TERM", G(A("object.edition", "edition_in", ["standard"])), G(A("object.region", "region_in", ["r-a"]))),
    ("C-ENUM", G(A("object.tier", "in", ["basic", "standard"]), term_types={"object.tier": TIER}),
     G(A("object.tier", "eq", "standard"), term_types={"object.tier": TIER})),
    ("C-PRESENT", G(A("object.kms_key", "present", True)),
     G(A("object.kms_key", "eq", "alias-a"), term_types={"object.kms_key": STR})),
]

# composição a->b, b->c: o nó do meio (object da primeira = subject da segunda) com exigências incompatíveis
COMPOSITIONS = [
    ("K-MIDDLE-CONFLICT", G(A("object.region", "region_in", ["r-a"])), G(A("subject.region", "region_in", ["r-b"])),
     "UNSAT"),
    ("K-MIDDLE-OK", G(A("object.region", "region_in", ["r-a", "r-b"])), G(A("subject.region", "region_in", ["r-b"]),
                                                                          A("object.edition", "edition_in", ["x"])),
     "SAT"),
    ("K-ENDS-INDEPENDENT", G(A("subject.edition", "edition_in", ["s"])), G(A("object.edition", "edition_in", ["p"])),
     "SAT"),
]

OPERATOR_DOC = {
    "eq": "<papel>.<caminho> = valor; o termo declara o tipo em term_types (string | enum | boolean | integer) e o "
          "valor é desse tipo (e do enum, se declarado)",
    "in": "<papel>.<caminho> ∈ lista não vazia de valores do tipo declarado em term_types",
    "present": "true: o termo tem valor; false: sabidamente ausente (leitura completa); não lido é INDETERMINATE",
    "refers_to_kind": "o termo é referência para unidade do tipo nomeado; dois tipos no mesmo termo só são "
                      "incompatíveis se kind_disjoint declara o par (sem isso, UNKNOWN: mundo aberto)",
    "region_in": "<papel>.region ∈ lista não vazia de regiões",
    "edition_in": "<papel>.edition ∈ lista não vazia de edições (SKU, nível)",
    "version_range": "<papel>.provider_version em [min, max_exclusive), versões n(.n){0,3} comparadas numericamente "
                     "por componente; ao menos um limite; min < max_exclusive",
}


def document() -> dict:
    return {
        "schema": "bo.conditions_grammar/1", "contract": "C10", "contract_version": "3.0.0",
        "form": ("guarda = {all: [átomo...], term_types?: {termo: {datatype, enum?}}, kind_disjoint?: [[k1, k2]...]}; "
                 "átomo = ⟨term, op, value⟩, term = '<papel>.<caminho>'; conjunção pura, sem negação nem "
                 "disjunção; cada átomo restringe só o próprio termo, por isso a decisão é termo a termo"),
        "roles": ["subject", "object"],
        "operators": dict(OPERATOR_DOC),
        "satisfiability": ("SAT (com testemunha que o evaluate dá TRUE) | UNSAT (termo e porquê) | UNKNOWN; por "
                           "termo: present true e false juntos = UNSAT; present false com restrição de valor = UNSAT; "
                           "valores permitidos (eq, in, region_in, edition_in) ∩ universo fechado (boolean, enum) ∩ "
                           "faixa de versão vazios = UNSAT; faixa de versão vazia = UNSAT; tipos de referência "
                           "declarados disjuntos = UNSAT; dois tipos de referência sem disjunção declarada = UNKNOWN; "
                           "UNSAT de um termo domina UNKNOWN de outro; decidível (polinomial: no pior caso quadrático no tamanho das listas "
                           "de valores de um termo)"),
        "evaluation": ("TRUE | FALSE | INDETERMINATE: termo fora do contexto, NOT_READ ou simbólico é INDETERMINATE "
                       "(nunca FALSE); ABSENT torna FALSE todo operador de valor e decide present; FALSE domina "
                       "INDETERMINATE"),
        "composition": ("a->b com b->c: papéis renomeados (n0 = sujeito, n1 = meio, n2 = objeto), conjunção das "
                        "duas guardas, satisfatibilidade sobre n0, n1 e n2 (UNSAT = composição vazia), e a guarda "
                        "composta é a eliminação existencial de n1 (exata: os átomos são por termo)"),
        "schema_ref": "contracts/C10_transforms.schema.json#/$defs/guard",
        "sat_tests": [{"test_id": i, "guard": g, "expected": e} for i, g, e in SAT_TESTS],
    }
