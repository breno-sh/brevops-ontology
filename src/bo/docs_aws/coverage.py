"""Gate do DOCS-AWS: % de átomos com descrição, valores válidos e unidade (relatado, sem meta).

  python -I -m bo.docs.coverage DOCS-AWS        (pelo despachante do coordenador)
  python -I -m bo.docs_aws.coverage [DOCS-AWS]

Recalcula as métricas a partir do que está gravado ($BO_DATA/DOCS-AWS/docs_facts.jsonl, type_subcategory.jsonl,
shared_block_map.jsonl e os átomos do schema fixado) e confere com $BO_REPO/results/DOCS-AWS/coverage.json, que
também passa pelo validador único (C15). Sai 0 quando tudo confere e o relatório foi impresso; 1 quando o
coverage.json diverge do recálculo ou não valida. Não há limiar: a cobertura é relatada, não cobrada.
"""

from __future__ import annotations

import json
import subprocess
import sys

from bo.docs_aws import build


def _jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def recompute() -> tuple[dict, dict]:
    on_disk = json.loads((build.results_dir() / "coverage.json").read_text(encoding="utf-8"))
    facts = _jsonl(build.out_dir() / "docs_facts.jsonl")
    types = _jsonl(build.out_dir() / "type_subcategory.jsonl")
    shared = _jsonl(build.out_dir() / "shared_block_map.jsonl")
    tdict, _, _ = build.load_types()
    atoms = {a["atom_id"]: a["configurable"] for ts, _ix in tdict.values() for a in ts.atoms}
    fresh = build.coverage_doc(facts, types, atoms, on_disk["data"]["parse"], on_disk["generated_at"], shared)
    return on_disk, fresh


def main(argv=None) -> int:
    from bo.repo import core
    argv = list(sys.argv[1:] if argv is None else argv)
    argv = [a for a in argv if a != build.MODULE]
    on_disk, fresh = recompute()
    problems = []
    if on_disk["metrics"] != fresh["metrics"]:
        a = {m["metric_id"]: m["operational_coverage"] for m in on_disk["metrics"]}
        b = {m["metric_id"]: m["operational_coverage"] for m in fresh["metrics"]}
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        problems.append(f"métricas divergem do recálculo: {diff[:6]}")
    for k in ("atoms_total", "atoms_configurable", "facts_total", "atoms_with_stated", "atoms_with_stated_direct"):
        if on_disk["data"].get(k) != fresh["data"].get(k):
            problems.append(f"data.{k} diverge do recálculo")
    v = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "result",
                        str(build.results_dir() / "coverage.json")], capture_output=True, text=True)
    if v.returncode != 0:
        problems.append("coverage.json não valida no C15: " + (v.stdout + v.stderr).strip()[-300:])
    d = fresh["data"]
    core.emit(f"[{core.now()}] DOCS-AWS cobertura da documentação, aws {d['provider_version']} ({d['tag']})")
    core.emit(f"  átomos: {d['atoms_total']} ({d['atoms_configurable']} configuráveis); fatos: {d['facts_total']}")
    for m in fresh["metrics"]:
        oc = m["operational_coverage"]
        core.emit(f"  {m['metric_id']:<36} {100 * (oc['est'] or 0):6.2f}%  (n={oc['n']})")
    for p in problems:
        core.emit(f"  FALHA {p}")
    core.emit("RESULTADO: " + ("OK (relatado, sem meta)" if not problems else f"REPROVADO ({len(problems)})"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
