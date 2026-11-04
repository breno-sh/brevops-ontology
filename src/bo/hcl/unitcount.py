"""Contagem na unidade da tabela de referência e decomposição das diferenças (para o crosscheck).

  python -I -m bo.hcl.unitcount

A tabela Resources do TerraDS tem uma linha por (módulo, Managed|Data, tipo, nome): nenhuma duplicata
(conferido: 0 grupos repetidos). Um módulo é um diretório. Então a unidade comparável é o tipo.nome ÚNICO
por diretório de módulo, e não o bloco (dois arquivos do mesmo diretório que declaram o mesmo recurso
contam uma vez). Esta passada relê o TerraDS (parser igual ao da extração), conta nessa unidade e, por
(repositório, diretório, tipo), decompõe a diferença para o sqlite:
  falta_em_dir_com_arquivo_recusado  o diretório tem arquivo que o python-hcl2 recusou (cobertura do parser)
  falta_outro                        falta sem arquivo recusado no diretório
  sobra                              nós contamos mais
Grava $BO_DATA/HCL/unit_counts.json (agregado por tipo; nenhum nome, nenhum id de repositório).
"""

from __future__ import annotations

import collections
import multiprocessing as mp
import posixpath
import sys

from . import source
from .common import PARAMS, PROVIDERS, now, out_dir, sha256_file, write_json
from .extract import parse_files


def _work(args):
    tid, data = args
    st = collections.Counter()
    files, _ = source.repo_files(tid, data, st)
    units, refused = set(), set()
    for rel, body in parse_files(files, st):
        d = posixpath.dirname(rel) or "."
        if body is None:
            refused.add(d)
            continue
        for b in body.blocks:
            if b.type in ("resource", "data") and len(b.labels) == 2:
                t = b.labels[0]
                if "_" in t and t.split("_", 1)[0] in PROVIDERS:
                    units.add((d, ("Managed" if b.type == "resource" else "Data") + ":" + t, b.labels[1]))
    per = collections.Counter((d, k) for d, k, _ in units)
    return tid, dict(per), refused


def main(argv=None) -> int:
    con = source.sqlite_conn()
    theirs = collections.defaultdict(dict)  # repo -> {(dir, tipo): n}
    q = ("select m.RepositoryId, m.Path, r.ResourceType || ':' || r.Type, count(*) from Resources r "
         "join Modules m on m.Id = r.ModuleId group by 1, 2, 3")
    for rid, path, k, n in con.execute(q):
        t = k.split(":", 1)[1]
        if "_" in t and t.split("_", 1)[0] in PROVIDERS:
            theirs[str(rid)][(path, k)] = n
    ours_t = collections.Counter()
    dec = collections.defaultdict(collections.Counter)
    seen = set()
    with mp.get_context("spawn").Pool(PARAMS["workers"]) as pool:
        for tid, per, refused in pool.imap_unordered(_work, source.iter_repos(), chunksize=16):
            seen.add(tid)
            th = theirs.get(tid, {})
            for (d, k), a in per.items():
                ours_t[k] += a
            for key in set(per) | set(th):
                a, b = per.get(key, 0), th.get(key, 0)
                k = key[1]
                if a < b:
                    dec[k]["falta_em_dir_com_arquivo_recusado" if key[0] in refused else "falta_outro"] += b - a
                elif a > b:
                    dec[k]["sobra"] += a - b
    for rid, th in theirs.items():  # repositório do sqlite que não está no tar (não deve haver)
        if rid not in seen:
            for (d, k), b in th.items():
                dec[k]["falta_repo_ausente_no_tar"] += b
    theirs_t = collections.Counter()
    for th in theirs.values():
        for (d, k), b in th.items():
            theirs_t[k] += b
    write_json(out_dir() / "unit_counts.json", {
        "at": now(), "unit": "(diretório de módulo, Managed|Data, tipo, nome) único; = linha da tabela Resources",
        "tar_sha256": sha256_file(source.TAR), "repos": len(seen),
        "ours": dict(sorted(ours_t.items())), "sqlite": dict(sorted(theirs_t.items())),
        "decomposition": {k: dict(v) for k, v in sorted(dec.items())}})
    print(f"[{now()}] unitcount: {len(seen)} repositórios; {sum(ours_t.values())} unidades nossas, "
          f"{sum(theirs_t.values())} no sqlite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
