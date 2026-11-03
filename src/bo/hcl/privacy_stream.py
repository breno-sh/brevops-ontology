"""Varredura de privacidade em fluxo e em paralelo, com as MESMAS regras do privacy_lint (bo.repo.privacy).

  python -I -m bo.hcl.privacy_stream CAMINHO [CAMINHO ...]

Existe porque o privacy_lint --strict reprova, sem ler, arquivo acima de 50 MB (privacy.TEXT_LIMIT) e o
symbolic_config.jsonl do TerraDS inteiro tem gigabytes. Isto NÃO substitui o gate do catálogo (que continua
reprovando por tamanho): é a evidência de conteúdo que acompanha o pedido de mudança
(results/HCL/CONTRACT_CHANGE.txt). Arquivo grande é lido em pedaços alinhados em fim de linha; binário é
varrido pelas sequências imprimíveis, como no modo estrito. O valor achado nunca é impresso.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
from pathlib import Path

from bo.repo import privacy

from .common import now

CHUNK = 48 * 1024 * 1024


def _chunks(path: Path):
    size = path.stat().st_size
    with open(path, "rb") as f:
        start = 0
        while start < size:
            f.seek(min(start + CHUNK, size))
            f.readline()
            end = min(f.tell(), size)
            yield start, end
            start = end


def _scan(args):
    path, start, end, lists = args
    with open(path, "rb") as f:
        f.seek(start)
        b = f.read(end - start)
    found = privacy.scan_bytes(b, str(path), lists, strict=True)
    return str(path), start, b.count(b"\n"), [(x.rule, x.line, x.hint) for x in found]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("uso: python -I -m bo.hcl.privacy_stream CAMINHO ...", file=sys.stderr)
        return 2
    lists, notes = privacy.load_lists()
    jobs, n_files, n_bytes, missing = [], 0, 0, []
    for root in map(Path, argv):
        if not root.exists():
            missing.append(str(root))
            continue
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for p in files:
            if "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            n_files += 1
            n_bytes += p.stat().st_size
            for s, e in _chunks(p):
                jobs.append((p, s, e, lists))
    res = []
    with mp.get_context("spawn").Pool(min(14, max(1, os.cpu_count() - 2))) as pool:
        res = pool.map(_scan, jobs, chunksize=1)
    res.sort(key=lambda r: (r[0], r[1]))
    findings, base, last = [], {}, None
    for path, start, nl, fs in res:
        if path != last:
            base[path], last = 0, path
        for rule, line, hint in fs:
            findings.append(f"{path}:{base[path] + line}: {rule} ({hint})")
        base[path] += nl
    print(f"[{now()}] privacy_stream: {n_files} arquivo(s), {n_bytes} bytes, {len(jobs)} pedaço(s); "
          f"regras de bo.repo.privacy ({len(privacy.RULES)} + 12 dígitos + listas privadas)")
    for x in notes:
        print(f"  nota: {x}")
    for m in missing:
        print(f"  ACHADO caminho ausente: {m}")
    for f in findings[:50]:
        print(f"  ACHADO {f}")
    bad = len(findings) + len(missing)
    print("RESULTADO: " + ("OK" if not bad else f"REPROVADO ({bad} achado(s))"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
