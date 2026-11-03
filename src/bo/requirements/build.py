"""Materializa o C24: python -I -m bo.requirements.build [--check]

Escreve, a partir de content/ (e só dele):
  $BO_REPO/requirements/{requirements,commitments,cq_spec}.jsonl, REQUIREMENTS.html, REQUIREMENTS.sha256
  $BO_REPO/results/REQUIREMENTS/C24_proposta/{requirements,commitments,cq_spec}.schema.json
  $BO_REPO/results/REQUIREMENTS/MANIFEST.sha256
Antes de gravar, valida tudo (schema proposto + regras semânticas); conteúdo inválido não é gravado.
--check não grava nada: sai 1 se algum arquivo publicado difere do que o conteúdo produz (regeneração idêntica).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import common, model, render, schemas, validate

# Hora em que o conteúdo foi escrito (America/Recife). Muda só quando o conteúdo muda; a saída é determinística.
AUTHORED_AT = "2026-11-02T22:28:00-03:00"


PROPOSTA = """Proposta do produtor para o C24 1.0.0 ({at}, America/Recife)

O REQUIREMENTS é o primeiro produtor do C24 e o CONTRACTS (dono de contracts/C24_requirements.schema.json e do
bo.contracts.validate) ainda não existe: ele depende de SEMANTICS, que depende deste módulo. Estes três JSON
Schema (draft 2020-12, um registro por linha de JSONL) descrevem o formato que o REQUIREMENTS publica:

  requirements.schema.json  bo.requirement/1   requisito (area, priority, statement, rationale, answers, consumers)
  commitments.schema.json   bo.commitment/1    compromisso {{positive|negative|unknown}}, check {{kind, assertion}},
                                               fixtures, expected_answer {{value, why, code?}}, protects, layer,
                                               upper_axes, provider_grounding
  cq_spec.schema.json       bo.cq_spec/1       CQ com family, question, criterion, answer_form, fixtures
                                               {{conforming, nonconforming, incomplete}} e closed_world

Regras que o schema não exprime e que o validador do produtor (python -I -m bo.requirements.validate) confere:
polaridade x checagem; resposta definida exige leitura completa declarada; UNKNOWN exige leitura parcial com
o que falta; termos de fixture só do vocabulário de requisitos (src/bo/requirements/terms.py); referências
cruzadas (requisito, compromisso); ids únicos; conforme != não conforme. Sugestão ao CONTRACTS: adotar estes
schemas como C24 1.0.0 e chamar estas regras como validação semântica, ou registrar emenda versionada.
"""

BLOQUEIO = """Bloqueio de gate: bo.contracts.validate ({at}, America/Recife)

Os gates G1 (python -I -m bo.contracts.validate commitments ...), G6 (make gate, que roda o gate_smoke antes)
e G7 (gate_smoke) exigem o módulo bo.contracts.validate. O dono é o CONTRACTS, cujas dependências são REPO e
SEMANTICS; SEMANTICS depende de REQUIREMENTS e ONTPAT, e ONTPAT depende de REQUIREMENTS. O validador, portanto,
só pode existir depois deste módulo: é um ciclo de ordem no plano, não um defeito do conteúdo.

Enquanto isso, gates/REQUIREMENTS.sh roda o validador do produtor (bo.requirements.validate) com o schema
proposto em C24_proposta/ e, assim que bo.contracts.validate existir, passa a rodá-lo também, sem mudança.
Correção sugerida ao coordenador: tirar G1 dos gates do REQUIREMENTS e pôr no CONTRACTS (validar os C24 já
publicados) ou no SEMANTIC-REGRESSION; ou reexecutar os gates do REQUIREMENTS depois do merge do CONTRACTS.
"""


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def produce() -> dict[str, bytes]:
    reqs, cmts, cqs = common.collect()
    errs = schemas_and_rules(reqs, cmts, cqs)
    if errs:
        common.fail(errs, "build (conteúdo inválido, nada gravado)")
        raise SystemExit(1)
    files: dict[str, bytes] = {}
    files["requirements/requirements.jsonl"] = common.dump_jsonl(reqs).encode()
    files["requirements/commitments.jsonl"] = common.dump_jsonl(cmts).encode()
    files["requirements/cq_spec.jsonl"] = common.dump_jsonl(cqs).encode()
    content_sha = sha(b"".join(files[k] for k in sorted(files)))
    files["requirements/REQUIREMENTS.html"] = render.render(reqs, cmts, cqs, AUTHORED_AT, content_sha).encode()
    files["requirements/REQUIREMENTS.sha256"] = "".join(
        f"{sha(files[p])}  {p}\n" for p in sorted(files)).encode()
    for kind, sch in schemas.BY_KIND.items():
        files[f"results/REQUIREMENTS/C24_proposta/{kind}.schema.json"] = (
            json.dumps(sch, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode()
    files["results/REQUIREMENTS/C24_proposta/LEIA.txt"] = PROPOSTA.format(at=AUTHORED_AT).encode()
    files["results/REQUIREMENTS/BLOQUEIO_VALIDADOR.txt"] = BLOQUEIO.format(at=AUTHORED_AT).encode()
    man = sorted(p for p in files)
    files["results/REQUIREMENTS/MANIFEST.sha256"] = "".join(f"{sha(files[p])}  {p}\n" for p in man).encode()
    return files


def schemas_and_rules(reqs, cmts, cqs) -> list[str]:
    errs = []
    errs += validate.schema_errors("requirements", reqs)
    errs += validate.schema_errors("commitments", cmts)
    errs += validate.schema_errors("cq_spec", cqs)
    errs += model.validate_requirements(reqs)
    rid = {r["req_id"] for r in reqs}
    errs += model.validate_commitments(cmts, rid)
    errs += model.validate_cq_spec(cqs, rid, {c["commitment_id"] for c in cmts})
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.requirements.build")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = common.repo()
    files = produce()
    if a.check:
        diff = [p for p, b in files.items() if not (root / p).is_file() or (root / p).read_bytes() != b]
        if diff:
            print("build --check: REPROVADO; difere do conteúdo:", *diff, sep="\n  ", file=sys.stderr)
            return 1
        print(f"build --check: OK ({len(files)} arquivos idênticos ao que o conteúdo produz)")
        return 0
    for p, b in files.items():
        dst = root / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b)
    print(f"build: {len(files)} arquivos gravados em {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
