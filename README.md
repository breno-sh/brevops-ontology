# BrevOps Ontology

A provider-neutral ontology of multi-cloud infrastructure configuration, built from evidence instead of hand-written mappings.

AWS, Azure, Google Cloud and Oracle Cloud describe the same ideas (a virtual machine, a network interface, a storage bucket, a firewall rule) with different resource types, nested blocks and field names. BrevOps Ontology reads what each provider publishes (Terraform provider schemas, provider documentation and compliance controls) and induces a shared vocabulary from it, so that one question, such as "is this bucket public?" or "does this VM have a public IP?", can be asked once and answered over any of the four clouds.

Who it is for: people who audit, compare or migrate cloud configuration across providers, and researchers working on cloud ontologies and infrastructure-as-code analysis.

## What it does

- **Grain classification.** Every configuration unit is classified as an *entity* (own identity and life cycle), a *component* (identity tied to a parent), a *facet* (configures one aspect of its owner) or a *link* (identity is a tuple of references). The class comes from schema and documentation evidence, not from how the Terraform block happens to be packaged.
- **Requirements and competency questions.** 26 requirements, 90 semantic commitments (positive, negative and unknown cases) and 29 competency questions, written before any induction, many of them grounded in CIS benchmark controls.
- **Executable fixtures.** Competency questions are realized as Terraform fixtures and checked by per-slice oracles. A safety harness can deploy free-tier fixtures to real accounts and always tears them down.
- **Mapping and verdicts.** Provider resources are mapped onto the shared patterns (OWL/Turtle, validated with SHACL), and every mapping decision keeps its provenance.
- **Comparison.** A pre-registered head-to-head protocol compares the result with existing approaches under the same universe and the same questions.

## Status

The pilot is complete on two slices, **network** (`pilot/net`) and **storage** (`pilot/sto`), and is frozen at tag `bo-freeze-FREEZE-P`. The pilot exit criteria E1 to E8 pass on the held-out sets. The next phase scales the pipeline from the pilot slices to the full provider schemas.

## Built with

- Python (3.11 or later; the pinned set in `requirements.lock` was resolved on 3.14). The core tooling uses only the standard library.
- rdflib and pySHACL for the ontology and the shapes, python-hcl2 for Terraform, pandas, statsmodels and lifelines for the metrics.
- Terraform (provider pins in `universe/pins.json`) and ROBOT (`ontology/patterns/toolchain_pins.json`).

## Getting started

```bash
git clone https://github.com/breno-sh/brevops-ontology.git
cd brevops-ontology
python -m venv .venv && . .venv/bin/activate
# sssom and lifelines are pinned for modules that do not use them yet and
# conflict with pandas 3, so the working set skips them for now.
pip install $(grep -vE '^\s*(#|$)|^(sssom|lifelines)==' requirements.lock)

# Generated data lives outside git. Point BO_DATA at any writable folder.
export BO_DATA="$PWD/../brevops-data"

make bootstrap   # writes a .pth into the venv so `python -I -m bo.*` finds src/
make test        # repository unit tests
make selftest    # self-tests of the repository tools
make help        # every target
```

Each module has its own gates, run with `make gate ID=<MODULE>` (for example `make gate ID=GRAIN`). Module tests can also be run directly, one folder at a time:

```bash
python -I -m pytest -q tests/schema
```

Some module tests read generated data from `$BO_DATA` (provider schema atoms, service evidence). On a fresh clone they fail with `dado real ausente` ("real data missing") until the module that produces that data has been run.

## Repository layout

| Path | What is there |
| --- | --- |
| `requirements/` | Requirements, semantic commitments and competency question specs |
| `prereg/` | Pre-registration: metrics, power analysis, pilot exit criteria, head-to-head fairness |
| `contracts/` | Versioned contracts between modules (JSON formats and rules) |
| `src/bo/` | One package per module: schema extraction, documentation, service evidence, grain, mapping, oracles, metrics |
| `cq/`, `pilot/` | Competency question fixtures, pilot slices, expected answers and oracles |
| `ontology/`, `shapes/` | Ontology design patterns (Turtle) and SHACL shapes |
| `deploy/` | Safety harness for real deployments: allowlists, supervisor, teardown |
| `results/` | Per-module outputs with manifests and freeze receipts |
| `tests/` | Tests, one folder per module |

Most design documents (`*.html`) and comments are written in Brazilian Portuguese. English documentation is on the roadmap.

## Roadmap

- Scale grain classification from the pilot slices to the full AWS, Azure, Google Cloud and Oracle Cloud schemas, including recursive nested blocks.
- Freeze the scale baseline and rerun the head-to-head comparison on it.
- English documentation and a short tutorial.
- Package the ontology and the classifier as a release that can be used without the research pipeline.
- Remove machine-specific default paths from the configuration.

## License

BrevOps Ontology is free software under the **GNU Affero General Public License v3.0** (see [LICENSE](LICENSE)). You can use, study, modify and share it. If you distribute it, or run a modified version as a network service, you must release your complete source under the same license.

**Commercial license.** If you want to use BrevOps Ontology in a product or service without the AGPL obligations, a separate commercial license is available from the copyright holder. Open an issue or contact [@breno-sh](https://github.com/breno-sh) on GitHub.

Third-party material and its licenses are listed in [NOTICE](NOTICE).

## Contributing

Issues and suggestions are welcome. Because the project is dual-licensed, code contributions can only be merged after the contributor agrees in writing that the copyright holder may distribute them under both the AGPL and the commercial license.

Copyright (C) 2026 Breno Vasconcelos
