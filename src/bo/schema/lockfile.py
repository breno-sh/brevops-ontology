"""Leitura do .terraform.lock.hcl (só o formato que o 'terraform init' grava).

O lock é a fonte da versão de cada provider (nunca uma constante digitada) e dos hashes que o
'terraform init' confere no pacote baixado. Aqui só se lê e se recorta: o recorte de um provider
vira o lock da pasta de extração, e o init reprova se o pacote não bater com algum hash dele.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_BLOCK = re.compile(r'^provider\s+"([^"]+)"\s*\{\n(.*?)^\}', re.M | re.S)
_VERSION = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.M)
_CONSTRAINTS = re.compile(r'^\s*constraints\s*=\s*"([^"]+)"', re.M)
_HASHES = re.compile(r'^\s*hashes\s*=\s*\[(.*?)\]', re.M | re.S)
_HASH = re.compile(r'"((?:h1|zh):[^"]+)"')


@dataclass(frozen=True)
class LockedProvider:
    address: str            # registry.terraform.io/hashicorp/aws
    version: str
    constraints: str | None
    hashes: tuple = field(default_factory=tuple)

    @property
    def source(self) -> str:
        """hashicorp/aws (o endereço sem o host do registro)."""
        return "/".join(self.address.split("/")[-2:])

    @property
    def name(self) -> str:
        return self.address.split("/")[-1]

    def render(self) -> str:
        """O bloco no formato do terraform init (um lock de um provider só)."""
        lines = [f'provider "{self.address}" {{', f'  version     = "{self.version}"']
        if self.constraints:
            lines.append(f'  constraints = "{self.constraints}"')
        lines.append("  hashes = [")
        lines += [f'    "{h}",' for h in self.hashes]
        lines += ["  ]", "}"]
        return "\n".join(lines) + "\n"


def parse(text: str) -> dict[str, LockedProvider]:
    """{endereço: LockedProvider} de um .terraform.lock.hcl."""
    out = {}
    for addr, body in _BLOCK.findall(text):
        m = _VERSION.search(body)
        if not m:
            raise ValueError(f"lock: provider {addr} sem version")
        c = _CONSTRAINTS.search(body)
        h = _HASHES.search(body)
        hashes = tuple(_HASH.findall(h.group(1))) if h else ()
        out[addr] = LockedProvider(addr, m.group(1), c.group(1) if c else None, hashes)
    return out


def read(path: Path | str) -> dict[str, LockedProvider]:
    return parse(Path(path).read_text(encoding="utf-8"))


def find(locks: dict[str, LockedProvider], source: str) -> LockedProvider:
    """O provider de 'hashicorp/aws' (ou do endereço completo) no lock; KeyError se não houver."""
    for addr, lp in locks.items():
        if addr == source or lp.source == source:
            return lp
    raise KeyError(f"lock sem o provider {source} (tem: {', '.join(sorted(locks)) or 'nenhum'})")


HEADER = ("# This file is maintained automatically by \"terraform init\".\n"
          "# Manual edits may be lost in future updates.\n\n")


def render(providers: list[LockedProvider]) -> str:
    return HEADER + "\n".join(p.render() for p in providers)
