"""Depois da troca: grava o summary.json (C17, proveniência pelo tools/provenance.py) e o manifesto.

  python -I -m bo.corpus_oci.finalize --brief ARQ

Os números do summary saem do build_report.json publicado, não de memória.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from . import build, manifest

BRIEF = "/Users/breno/doutorado/pesquisa/superficie/reports/brevops_ontology/execucao/briefs/CORPUS-OCI.txt"
MODEL = "claude-opus-5-5"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.corpus_oci.finalize")
    ap.add_argument("--brief", default=BRIEF)
    a = ap.parse_args(argv)
    pub = build.bo_data() / build.MODULE
    rep = json.loads((pub / "build_report.json").read_text(encoding="utf-8"))
    c, ua, tc = rep["counts"], rep["unattributed_records"], rep["term_class_records"]
    atoms = [json.loads(x) for x in (pub / "atom_totals.jsonl").read_text(encoding="utf-8").splitlines()]
    pv = sorted({json.loads(ln)["provider_version"] for ln in open(build.inputs()["atoms"], encoding="utf-8")})
    top = sorted((x for x in atoms if x["n_set"]), key=lambda x: (-x["n_families"], -x["n_repos"], x["atom_id"]))[:5]
    conf = [x for x in atoms if x["configurable"]]
    stamp = datetime.now(ZoneInfo("America/Recife")).isoformat(timespec="seconds")
    note = (
        f"[{stamp}] Uso real do oci no TerraDS, sem split. {c['repos_with_managed']} repositórios, "
        f"{c['families_with_managed']} famílias, {c['modules_with_managed']} módulos e {c['managed_blocks']} "
        f"recursos gerenciados ({c['data_blocks']} blocos data fora). {c['managed_records']} valores lidos pelas "
        f"faixas do symbolic_config.index.json (= n_attrs do parquet, conferido); {c['attributed_records']} viram átomo; não atribuídos: "
        + ", ".join(f"{k} {v}" for k, v in ua.items())
        + f". Classes dos valores: literal {tc['literal']}, symbolic {tc['symbolic']}, withheld {tc['withheld']}. "
        f"Átomos configurados: {c['atoms_configured']} de {c['schema_atoms']} "
        f"({sum(1 for x in conf if x['n_set'])} de {len(conf)} configuráveis); em 2+ famílias: "
        f"{c['atoms_configured_in_2plus_families']}. Tipos no corpus: {c['types_in_corpus']}, "
        f"{c['types_in_corpus_not_in_schema']} fora do schema {','.join(pv)}. {c['usage_records']} registros usage "
        f"({c['usage_records_with_atom']} por átomo). Mais difundidos (famílias): "
        + "; ".join(f"{x['atom_id']} {x['n_families']}" for x in top)
        + ". Definições em build_report.json (definitions) e na docstring de bo.corpus_oci.counting. "
        "Contagem por repositório, módulo e recurso em atom_totals.jsonl e type_totals.jsonl."
    )
    params = {
        "provider": build.PROVIDER, "provider_version": ",".join(pv),
        "resource_unit": "bloco resource (sem data), chave (repo_id, file, resource_address)",
        "module_unit": "(repo_id, dirname(file))",
        "atom_resolution": "sem [n]; dynamic content desdobrado; caminho exato ou maior prefixo atributo",
        "class_precedence": "withheld>symbolic>literal",
        "zero_rows": "átomo não configurado num (repo, tipo) não tem registro; denominador no registro do tipo",
        "hcl_branch_data": "bo/hcl, dados em $BO_DATA/HCL (sha nas entradas)",
    }
    cmd = [sys.executable, "-I", str(manifest.repo() / "tools" / "provenance.py"), "record", build.MODULE,
           "--brief", a.brief, "--model", MODEL, "--note", note,
           "--source", "https://doi.org/10.5281/zenodo.20339474|CC-BY-4.0 (dataset); licença por repositório em "
                       "$BO_DATA/HCL/licenses.json|só contagens agregadas por id sintético, via configuração "
                       "simbólica do HCL"]
    for k, v in params.items():
        cmd += ["--param", f"{k}={v}"]
    for p in build.inputs().values():
        cmd += ["--input", build.portable(p)]
    r = subprocess.run(cmd, text=True)
    if r.returncode != 0:
        return r.returncode
    return manifest.main(["write"])


if __name__ == "__main__":
    sys.exit(main())
