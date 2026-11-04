"""bo.schema (SCHEMALIB): schema JSON do Terraform -> átomos (C01) e tipos (C02), régua do C1, extração em
sandbox, reprodução do catalogo4v2 e crosscheck contra o índice do Registry.

Emendas versionadas da biblioteca (o que muda nos bytes de saída e quem precisa de refresh): AMENDMENTS.
"""

LIBRARY_VERSION = "1.1.0"

AMENDMENTS = [
    {"version": "1.0.0", "date": "2026-11-03", "contracts": {"C01": "2.1.0", "C02": "2.0.0"},
     "change": "átomo por entrada 'attributes'; write_only opcional (só quando verdadeiro); nested_type = 1 átomo",
     "bytes": "linha de base"},
    {"version": "1.1.0", "date": "2026-11-04", "contracts": {"C01": "2.2.0", "C02": "2.0.0"},
     "origin": "CONTRACTS emenda 7, item CC-NET-1 (PILOT-NET-GLOSS); tentativa 2 do PILOT-EXIT",
     "change": "atributo coleção de objetos (type cty list/set de object, ou nested_type list/set) ganha átomos de "
               "elemento <pai>.<membro>, com block_path terminando em {block: <pai>, kind: nested_attribute, "
               "nesting_mode: list|set}; recursivo para membro que também é coleção. Flags: nested_type usa os do "
               "membro; objeto cty herda do pai (configurável -> optional, só computed -> computed; sensitive, "
               "deprecated, write_only do pai). TypeSchema.atoms não muda; os elementos ficam em TypeSchema.elements "
               "e saem em TypeSchema.all_atoms(), logo depois do pai.",
     "bytes": "átomos existentes: mesmos ids e mesmos bytes; atoms.jsonl só ganha linhas de elemento; types.jsonl "
              "(C02) e a régua do C1 não mudam (contam só .atoms)",
     "opt_in": "TypeSchema.atoms intacto; elementos só por TypeSchema.all_atoms() ou bo.schema.build --elements "
               "(padrão do build: o atoms.jsonl de antes)",
     "refresh": "FASE 2 (decisão do coordenador, 2026-11-04): SCHEMA-*, HIST-* e SCHEMA-POST trocam para all_atoms(); "
                "depois os consumidores do atoms.jsonl em cascata. Nada regenerado agora, para não invalidar a cadeia "
                "antes da tentativa 2 do PILOT-EXIT"},
]
