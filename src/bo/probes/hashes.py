"""Manifestos do PROBEKIT (C17, formato do shasum -a 256).

  python -I -m bo.probes.hashes [--write]

  deploy/probes/PROBEKIT.sha256      protocol_support.json e todo arquivo de */*/_templates/, com caminho relativo
                                     à raiz do repositório (shasum -a 256 -c rodado de $BO_REPO)
  results/PROBEKIT/MANIFEST.sha256   código (src/bo/probes), testes e gravações (tests/probes), gates/PROBEKIT.sh e
                                     relatórios de results/PROBEKIT (menos summary.json, conferido pelo provenance)
"""

from __future__ import annotations

import sys
from pathlib import Path

from .common import deploy_dir, repo, results_dir, sha256_file, write_atomic

KIT_MANIFEST = "PROBEKIT.sha256"


def _files(root: Path, pattern: str = "**/*") -> list[Path]:
    return sorted(p for p in root.glob(pattern) if p.is_file() and "__pycache__" not in p.parts
                  and not p.name.startswith(".") and p.suffix != ".pyc")


def kit_lines() -> list[str]:
    r = repo()
    files = [deploy_dir() / "protocol_support.json"] + _files(deploy_dir(), "*/*/_templates/*")
    return [f"{sha256_file(f)}  {f.relative_to(r)}" for f in files]


def manifest_lines() -> list[str]:
    r = repo()
    files = (_files(r / "src" / "bo" / "probes") + _files(r / "tests" / "probes") + [r / "gates" / "PROBEKIT.sh"]
             + [f for f in _files(results_dir()) if f.name not in ("MANIFEST.sha256", "summary.json")])
    return [f"{sha256_file(f)}  $BO_REPO/{f.relative_to(r)}" for f in files if f.exists()]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    targets = {deploy_dir() / KIT_MANIFEST: kit_lines(), results_dir() / "MANIFEST.sha256": manifest_lines()}
    probs = []
    for path, lines in targets.items():
        text = "\n".join(lines) + "\n"
        if "--write" in argv:
            write_atomic(path, text)
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            probs.append(f"{path.name} difere do regenerado (rode com --write)")
        print(f"  {path.name}: {len(lines)} arquivo(s)")
    for p in probs:
        print("  PROBLEMA:", p)
    print("hashes:", "OK" if not probs else "REPROVADO")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
