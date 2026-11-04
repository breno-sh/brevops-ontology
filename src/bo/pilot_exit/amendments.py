"""E6: delta de contrato. Lista cada mudança que um módulo dos pilotos pediu e confere se virou emenda versionada.

Fonte dos pedidos: results/PILOT-*/CONTRACT_CHANGE.txt (menos o deste módulo). Item = linha que começa na coluna 0
com um rótulo 'CC-<x>' ou 'N.' (ou 'ACHADO N'). O item conta como VERSIONADO quando:
  (a) o registro de emendas do CONTRACTS (bo.contracts.amendments.AMENDMENTS) cita o arquivo do módulo e o rótulo
      entre parênteses (ex.: 'results/PILOT-NET-ORACLE/CONTRACT_CHANGE.txt (2)'); ou
  (b) o próprio pedido diz que o item foi RESOLVIDO/adotado citando versão ou commit na mesma frase.
O resto é ABERTO e conta em unversioned_changes. O avaliador não aplica emenda no que não é dele (owns): registra
o ledger e o pedido em results/PILOT-EXIT/CONTRACT_CHANGE.txt para os donos.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from . import common as C

ITEM = re.compile(r"^(CC-[A-Z0-9][A-Z0-9-]*(?=[\s(:.])|ACHADO \d+|\d+(?=\.\s))")
RESOLVED = re.compile(r"((?:CC-[A-Z0-9][A-Z0-9-]*)(?:\s*(?:,|e)\s*CC-[A-Z0-9][A-Z0-9-]*)*)\s+RESOLVID[OA]S?\b(?=(.{0,200}))", re.S)
ADOPTED = re.compile(r"itens?\s+([\d][\d ,e]*)\s+(?:foi|foram)\s+adotad[oa]s?([^\n]*(?:\n[^\n]*)?)", re.I)
VERSIONISH = re.compile(r"(\b\d+\.\d+\.\d+\b|\b[0-9a-f]{7,40}\b|emenda \d+)")


def pilot_modules(cat_modules: dict) -> list[str]:
    return sorted(m for m in cat_modules if m.startswith("PILOT-") and m != C.MODULE)


def parse(text: str) -> dict:
    items = []
    for line in text.splitlines():
        m = ITEM.match(line)
        if m and m.group(1) not in items:
            items.append(m.group(1))
    resolved = {}
    flat = text.replace("\n", " ")
    for m in RESOLVED.finditer(flat):
        if VERSIONISH.search(m.group(2)[:200]):
            for i in re.findall(r"CC-[A-Z0-9][A-Z0-9-]*", m.group(1)):
                resolved[i] = "pedido marca RESOLVIDO com versão/commit"
    for m in ADOPTED.finditer(text):
        if VERSIONISH.search(m.group(2)):
            for i in re.findall(r"\d+", m.group(1)):
                resolved[i] = "pedido marca adotado com emenda/versão"
    return {"items": items, "resolved": resolved}


def registry_citations(module: str) -> dict:
    from bo.contracts.amendments import AMENDMENTS
    cites = {}
    for a in AMENDMENTS:
        src = a.get("source", "")
        if f"{module}/CONTRACT_CHANGE.txt" not in src:
            continue
        for grp in re.findall(r"\(([^)]*)\)", src.split(f"{module}/CONTRACT_CHANGE.txt", 1)[1][:80]):
            for tok in re.split(r"\s*,\s*", grp):
                tok = tok.strip()
                m = re.match(r"(CC-[A-Z0-9][A-Z0-9-]*|ACHADO \d+|\d+)", tok)
                if m:
                    cites[m.group(1)] = f"{a['contract']} {a['from']}->{a['to']}"
    return cites


def ledger(root: Path, cat_modules: dict) -> dict:
    rows = []
    for mid in pilot_modules(cat_modules):
        p = root / "results" / mid / "CONTRACT_CHANGE.txt"
        if not p.is_file():
            continue
        txt = p.read_text(encoding="utf-8")
        pr = parse(txt)
        reg = registry_citations(mid)
        for it in pr["items"]:
            if it in reg:
                st, by = "VERSIONED", "registro de emendas: " + reg[it]
            elif it in pr["resolved"]:
                st, by = "VERSIONED", pr["resolved"][it]
            else:
                st, by = "OPEN", ""
            rows.append({"module": mid, "file": C.portable(p, root), "item": it, "status": st, "versioned_by": by})
    return {"requests": rows, "n_requests": len(rows),
            "unversioned_changes": sum(1 for r in rows if r["status"] == "OPEN")}


def stale_not_marked(root: Path) -> dict:
    sys.path.insert(0, str(root / "src"))
    from bo.repo import catalog, receipts, state
    cat = catalog.load(root)
    scan = receipts.invalidate_scan(cat, root)
    st = state.load(root, cat)
    missing = sorted(m for m in scan["stale"] if (st["modules"].get(m) or {}).get("status") != "STALE")
    return {"receipts": len(scan["receipts"]), "should_be_stale": sorted(scan["stale"]),
            "stale_not_marked": len(missing), "missing": missing}


def catalog_ok(root: Path) -> dict:
    env = dict(__import__("os").environ, BO_REPO=str(root))
    a = subprocess.run([sys.executable, "-I", "-B", "-m", "pytest", str(root / "tests/integration/core"), "-q",
                        "-p", "no:cacheprovider"], capture_output=True, text=True, env=env, cwd=str(root))
    b = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "--all-stubs"], capture_output=True,
                       text=True, env=env, cwd=str(root))
    tail = lambda r: (r.stdout.strip().splitlines() or [""])[-1][:200]
    return {"catalog_ok": a.returncode == 0 and b.returncode == 0,
            "core_integration": {"rc": a.returncode, "tail": tail(a)},
            "contracts_all_stubs": {"rc": b.returncode, "tail": tail(b)}}
