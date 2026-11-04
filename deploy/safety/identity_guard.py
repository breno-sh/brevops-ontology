#!/usr/bin/env python3
"""Guarda de identidade efetiva (SAFETY). Implementação: src/bo/safety/identity.py.

  identity_guard.py check --provider P        conferência (C16 effective_identity_check); sai 1 se fora da allowlist
  identity_guard.py hash --provider P         linha "P sha256:<hex>" da sessão atual, para o Breno colar na allowlist
  identity_guard.py verify-allowlist          confere o arquivo (600, dono, fora de repositório); não imprime conteúdo
Só roda CLI de nuvem em check/hash (leitura da identidade); nesta fase, só o verify-allowlist é usado.
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if (_SRC / "bo" / "safety").is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bo.safety.identity import (IdentityRefused, check, identity_hash, load_allowlist, read_identity,  # noqa: E402,F401
                                require_fresh)


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="identity_guard")
    ap.add_argument("cmd", choices=["check", "hash", "verify-allowlist"])
    ap.add_argument("--provider", choices=["aws", "google", "azurerm", "oci"])
    a = ap.parse_args(argv)
    try:
        if a.cmd == "verify-allowlist":
            al = load_allowlist()
            print("allowlist: ok (" + ", ".join(f"{k}={len(v)}" for k, v in sorted(al.items())) + ")")
            return 0
        if not a.provider:
            ap.error("--provider obrigatório")
        if a.cmd == "hash":
            print(f"{a.provider} sha256:{identity_hash(read_identity(a.provider))}")
            return 0
        print(json.dumps(check(a.provider)))
        return 0
    except IdentityRefused as e:
        print(f"identity_guard: ABORTA: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
