"""Proposta da parte 'realização' do contrato C14 (dono: CONTRACTS) a partir do padrão de descritor.

  python -I -m bo.ontpat.c14 --write   grava results/ONTPAT/C14_proposta/ (schema JSON da linha de realizations.jsonl)
  python -I -m bo.ontpat.c14 --check   extrai as realizações do ABox de exemplo (SPARQL) e valida cada linha no schema;
                                       confere também que o schema gravado é o daqui

Enquanto bo.contracts.validate não existe (ordem do plano), é este o validador do C14 do ONTPAT. Divergência
com o schema que o CONTRACTS publicar vira results/ONTPAT/CONTRACT_CHANGE.txt.
"""

from __future__ import annotations

import json
import sys

import jsonschema
import rdflib

from . import common as c

ENUM = {
    "fidelity": ["Lossless", "DeclaredLoss", "PartialTransport", "NoTransport"],
    "evidence": ["StructurallyValid", "DocSupported", "PersistenceVerified", "ObservationTested", "Unresolved"],
    "exclusivity": ["ProvenExclusive", "Ambiguous"],
}
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://w3id.org/brevops/contracts/C14/realization_row.schema.json",
    "title": "C14 realizations.jsonl (proposta do ONTPAT, padrão de descritor)",
    "type": "object",
    "additionalProperties": False,
    "required": ["realization_id", "of", "provider", "realized_by", "lifting_fidelity", "lowering_fidelity",
                 "evidence_state", "derived_from", "generated_by"],
    "properties": {
        "realization_id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]+$"},
        "of": {"type": "object", "additionalProperties": False, "required": ["descriptor_key", "kind", "describes"],
               "properties": {"descriptor_key": {"type": "string"}, "kind": {"enum": ["class", "property"]},
                              "describes": {"type": "string", "format": "iri",
                                            "description": "IRI da entidade OWL, levado por anotação (bo:describesProperty/describesClass), nunca como indivíduo"}}},
        "provider": {"type": "string"},
        "realized_by": {"type": "array", "minItems": 1, "items": {"type": "object", "additionalProperties": False,
                        "required": ["artifact_name", "schema"],
                        "properties": {"artifact_name": {"type": "string"}, "artifact_path": {"type": "string"},
                                       "schema": {"type": "string"}}}},
        "lifting_fidelity": {"enum": ENUM["fidelity"]},
        "lowering_fidelity": {"enum": ENUM["fidelity"]},
        "evidence_state": {"enum": ENUM["evidence"]},
        "exclusivity": {"enum": ENUM["exclusivity"]},
        "guards": {"type": "array", "items": {"type": "string"}},
        "alternative_to": {"type": "array", "items": {"type": "string"}},
        "losses": {"type": "array", "items": {"type": "string", "pattern": "^[A-Z][A-Z_]+$"}},
        "projections": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                        "required": ["from_field", "descriptor_key"],
                        "properties": {"from_field": {"type": "string"}, "descriptor_key": {"type": "string"}}}},
        "derived_from": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "generated_by": {"type": "string"},
        "attributed_to": {"type": "string"},
    },
    "allOf": [
        {"if": {"anyOf": [{"properties": {"lifting_fidelity": {"enum": ["DeclaredLoss", "PartialTransport"]}}, "required": ["lifting_fidelity"]},
                          {"properties": {"lowering_fidelity": {"enum": ["DeclaredLoss", "PartialTransport"]}}, "required": ["lowering_fidelity"]}]},
         "then": {"required": ["losses"], "properties": {"losses": {"minItems": 1}}}},
        {"if": {"required": ["alternative_to"], "properties": {"alternative_to": {"minItems": 1}}},
         "then": {"required": ["guards", "exclusivity"], "properties": {"guards": {"minItems": 1}}}},
    ],
}
LEIA = """Proposta do ONTPAT para a linha de realizations.jsonl do contrato C14 (o C14 é do CONTRACTS).
Gerada por bo.ontpat.c14 em 2026-11-02 (America/Recife). Cada campo é a leitura de um termo do padrão P7/P8:
  of.describes       <- bo:of -> descritor -> bo:describesProperty | bo:describesClass (anotação; sem punning)
  provider           <- bo:onProvider
  realized_by        <- bo:realizedBy (1:N artefatos, com bo:artifactName, bo:artifactPath, bo:inSchema)
  lifting_fidelity   <- bo:liftingFidelity   lowering_fidelity <- bo:loweringFidelity (por direção)
  evidence_state     <- bo:evidenceState (escada §9.2)
  guards/alternative_to/exclusivity <- bo:hasGuard/bo:guardExpression, bo:alternativeTo, bo:exclusivity
  losses             <- bo:declaresLoss/bo:lossCode   projections <- bo:hasProjection/bo:fromField
  derived_from/generated_by/attributed_to <- prov:wasDerivedFrom / prov:wasGeneratedBy / prov:wasAttributedTo
Sem injetividade: o mesmo descritor pode ter várias realizações por provedor (alternativas guardadas).
Regras condicionais: perda declarada ou parcial exige 'losses'; alternativa exige guarda e exclusividade.
"""

Q = """PREFIX bo: <https://w3id.org/brevops/ontology#> PREFIX prov: <http://www.w3.org/ns/prov#>
SELECT ?r WHERE { ?r a bo:Realization }"""


def rows(g: rdflib.Graph) -> list[dict]:
    B, P = c.BO, rdflib.Namespace("http://www.w3.org/ns/prov#")
    loc = lambda x: str(x).split("#")[-1]  # noqa: E731
    out = []
    for (r,) in sorted(g.query(Q)):
        d = g.value(r, B.of)
        kind = "class" if (d, rdflib.RDF.type, B.ClassDescriptor) in g else "property"
        target = g.value(d, B.describesClass if kind == "class" else B.describesProperty)
        row = {"realization_id": loc(r),
               "of": {"descriptor_key": str(g.value(d, B.descriptorKey)), "kind": kind, "describes": str(target)},
               "provider": loc(g.value(r, B.onProvider)),
               "realized_by": [], "lifting_fidelity": loc(g.value(r, B.liftingFidelity)),
               "lowering_fidelity": loc(g.value(r, B.loweringFidelity)), "evidence_state": loc(g.value(r, B.evidenceState)),
               "derived_from": sorted(loc(x) for x in g.objects(r, P.wasDerivedFrom)),
               "generated_by": loc(g.value(r, P.wasGeneratedBy))}
        for a in sorted(g.objects(r, B.realizedBy)):
            art = {"artifact_name": str(g.value(a, B.artifactName)), "schema": loc(g.value(a, B.inSchema))}
            if g.value(a, B.artifactPath) is not None:
                art["artifact_path"] = str(g.value(a, B.artifactPath))
            row["realized_by"].append(art)
        if g.value(r, B.exclusivity) is not None:
            row["exclusivity"] = loc(g.value(r, B.exclusivity))
        guards = sorted(str(g.value(x, B.guardExpression)) for x in g.objects(r, B.hasGuard))
        alts = sorted({loc(x) for x in g.objects(r, B.alternativeTo)} | {loc(x) for x in g.subjects(B.alternativeTo, r)})
        losses = sorted(str(g.value(x, B.lossCode)) for x in g.objects(r, B.declaresLoss))
        projs = [{"from_field": str(g.value(x, B.fromField)), "descriptor_key": str(g.value(g.value(x, B.of), B.descriptorKey))}
                 for x in sorted(g.objects(r, B.hasProjection))]
        for k, v in (("guards", guards), ("alternative_to", alts), ("losses", losses), ("projections", projs)):
            if v:
                row[k] = v
        if g.value(r, P.wasAttributedTo) is not None:
            row["attributed_to"] = loc(g.value(r, P.wasAttributedTo))
        out.append(row)
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    d = c.results_dir() / "C14_proposta"
    if "--write" in argv:
        c.write_json(d / "realization_row.schema.json", SCHEMA)
        (d / "LEIA.txt").write_text(LEIA, encoding="utf-8")
        ex = rows(c.parse(c.patterns_dir() / c.EXAMPLE))
        (d / "realizations.example.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in ex), encoding="utf-8")
        c.emit(f"escrito {d}")
        return 0
    bad = []
    if c.read_json(d / "realization_row.schema.json") != SCHEMA or (d / "LEIA.txt").read_text(encoding="utf-8") != LEIA:
        bad.append("C14_proposta gravada difere da gerada")
    g = c.parse(c.patterns_dir() / c.EXAMPLE)
    rs = rows(g)
    stored = (d / "realizations.example.jsonl").read_text(encoding="utf-8")
    if stored != "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rs):
        bad.append("realizations.example.jsonl difere da extração do ABox de exemplo")
    v = jsonschema.Draft202012Validator(SCHEMA)
    for r in rs:
        for e in v.iter_errors(r):
            bad.append(f"{r['realization_id']}: {e.message}")
    neg = dict(rs[0], lowering_fidelity="DeclaredLoss")
    neg.pop("losses", None)
    if not list(v.iter_errors(neg)):
        bad.append("controle: linha com perda declarada sem 'losses' passou no schema")
    for b in bad:
        c.emit("C14: " + b)
    if not bad:
        c.emit(f"C14 (realização, proposta ONTPAT): {len(rs)} linhas extraídas do ABox de exemplo validam no schema; controle negativo reprovado")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
