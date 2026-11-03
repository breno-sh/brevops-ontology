"""Baixa (se faltar) e confere os tarballs fixados: python -I -m bo.cqsrc.fetch [--verify]

Sem --verify: baixa o que falta do codeload do GitHub para $BO_DATA/downloads/steampipe-mods/<mod>/,
confere o sha256 fixado em sources.py (diferente = descarta o arquivo baixado e sai 1) e grava SOURCE.txt.
Com --verify: não usa rede; sai 1 se algum tarball falta, diverge do sha256 ou se SOURCE.txt difere.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request

from . import sources


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.cqsrc.fetch")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    bad = 0
    for mod, (_, _, _, _, pin) in sources.MODS.items():
        arc = sources.archive_path(mod)
        st = arc.parent / "SOURCE.txt"
        if not arc.exists():
            if a.verify:
                print(f"FALTA {arc}")
                bad += 1
                continue
            arc.parent.mkdir(parents=True, exist_ok=True)
            part = arc.parent / (arc.name + ".part")
            with urllib.request.urlopen(sources.codeload_url(mod), timeout=120) as r, open(part, "wb") as f:
                f.write(r.read())
            if sha256(part) != pin:
                print(f"SHA256 DIVERGE {mod}: arquivo baixado descartado")
                part.unlink()
                bad += 1
                continue
            part.rename(arc)
        got = sha256(arc)
        if got != pin:
            print(f"SHA256 DIVERGE {mod}: {got[:12]}... != fixado {pin[:12]}...")
            bad += 1
            continue
        want = sources.source_txt(mod)
        if a.verify:
            if not st.exists() or st.read_text(encoding="utf-8") != want:
                print(f"SOURCE.txt ausente ou diferente: {st}")
                bad += 1
                continue
        else:
            st.write_text(want, encoding="utf-8")
        print(f"OK {mod} {sources.MODS[mod][1]} sha256 {pin[:12]}...")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
