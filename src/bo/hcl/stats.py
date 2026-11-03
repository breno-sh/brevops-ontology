"""Gate: taxa de leitura do parser e coerência das saídas.

  python -I -m bo.hcl.stats --min-parse-rate 0.95

Confere, a partir de $BO_DATA/HCL:
  - parse_rate = arquivos lidos / arquivos .tf no arquivo >= mínimo;
  - a extração cobriu o TerraDS inteiro (repositórios = linhas de Repositories no sqlite; sem --limit);
  - resources.parquet tem resources_emitted linhas; o índice soma records registros e cobre o jsonl inteiro;
  - termos por tipo somam records; parse_stats.json e o parquet foram gerados do mesmo tar (sha256).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import source
from .common import out_dir, now, sha256_file


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.hcl.stats")
    ap.add_argument("--min-parse-rate", type=float, required=True)
    ap.add_argument("--data", default=None)
    a = ap.parse_args(argv)
    d = out_dir() if a.data is None else __import__("pathlib").Path(a.data)
    errs = []
    st = json.load(open(d / "parse_stats.json", encoding="utf-8"))
    rate = st["files_ok"] / st["files_total"] if st["files_total"] else 0.0
    if abs(rate - st["parse_rate"]) > 1e-6:
        errs.append("parse_rate gravado não confere com files_ok/files_total")
    if rate < a.min_parse_rate:
        errs.append(f"parse_rate {rate:.4f} < {a.min_parse_rate}")
    if st.get("limit") is not None:
        errs.append(f"extração com --limit {st['limit']}: não cobre o TerraDS")
    n_repos = source.sqlite_conn().execute("select count(*) from Repositories").fetchone()[0]
    if st["repos"] != n_repos:
        errs.append(f"repositórios lidos {st['repos']} != {n_repos} no sqlite")
    if st["inputs"]["tar_sha256"] != sha256_file(source.TAR):
        errs.append("tar do TerraDS mudou depois da extração")
    import pyarrow.parquet as pq
    n_rows = pq.ParquetFile(d / "resources.parquet").metadata.num_rows
    if n_rows != st["resources_emitted"]:
        errs.append(f"resources.parquet {n_rows} linhas != resources_emitted {st['resources_emitted']}")
    idx = json.load(open(d / "symbolic_config.index.json", encoding="utf-8"))["repos"]
    n_rec = sum(v[2] for v in idx.values())
    if n_rec != st["records"]:
        errs.append(f"índice soma {n_rec} registros != records {st['records']}")
    end = max((v[1] for v in idx.values()), default=0)
    size = (d / "symbolic_config.jsonl").stat().st_size
    if end != size:
        errs.append(f"índice termina em {end} != tamanho do jsonl {size}")
    if sum(st["terms_by_kind"].values()) != st["records"]:
        errs.append("terms_by_kind não soma records")
    if sum(st["blocks_by_provider"].values()) != st["resources_emitted"]:
        errs.append("blocks_by_provider não soma resources_emitted")
    print(f"[{now()}] bo.hcl.stats: {st['files_ok']}/{st['files_total']} arquivos lidos "
          f"(parse_rate {rate:.4f}, mínimo {a.min_parse_rate}); {st['repos']} repositórios; "
          f"{st['resources_emitted']} recursos; {st['records']} registros; falhas {st['failures']}")
    for e in errs:
        print("  FAIL " + e)
    print("RESULTADO: " + ("OK" if not errs else f"REPROVADO ({len(errs)})"))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
