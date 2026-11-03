"""Auditoria da centralidade da AWS com as tabelas dos próprios fornecedores (só leitura das linhas normalizadas).

Duas leituras, ambas descritivas (censo das tabelas publicadas, não amostra: sem intervalo amostral; a incerteza que
importa é a de cobertura da tabela e a da regra de separação de menções, e ela não é quantificada aqui):

1. Linha sem contraparte, por tabela (só table_set main): fração das linhas em que a coluna de um provedor não
   nomeia serviço: vazia, ausência explícita do fornecedor ("None", "No equivalent"...) ou prosa sem nome de
   serviço (mentions.classify). O relatório separa as três causas. Nas tabelas cujo pivô não é a AWS (Google e Oracle), "sem AWS" é exatamente o que um recorte que parte do
   catálogo AWS nunca veria. A Microsoft é AWS-pivô por construção (toda linha tem AWS), então só mede "sem Azure".
2. Alcance entre provedores (p -> q): dos serviços distintos de p que aparecem em tabelas com colunas p e q, a
   fração que divide linha com ao menos um serviço de q. Tabela cujo pivô é q não entra no par (p, q): nela toda
   linha tem q por construção e o alcance seria 1 por artefato (ex.: Oracle para q = oci, Microsoft para q = aws). Se o alcance para a AWS for maior que para os outros
   destinos, as tabelas já são AWS-cêntricas; se for menor, um universo ancorado na AWS perde serviços dos outros.
"""

from __future__ import annotations

from collections import defaultdict

from . import mentions as MN

PROVIDERS = ("aws", "azure", "gcp", "oci")
TABLE_COLUMNS = {"google": ("gcp", "aws", "azure"), "microsoft": ("aws", "azure"),
                 "oracle": ("oci", "aws", "azure", "gcp")}
ROW_CHECKS = (("google", "aws"), ("google", "azure"), ("oracle", "aws"), ("oracle", "azure"), ("oracle", "gcp"),
              ("microsoft", "azure"), ("microsoft", "aws"))
NAMES = {"aws": "AWS", "azure": "Azure", "gcp": "Google Cloud", "oci": "OCI"}


def _main(rows):
    return [r for r in rows if r["table_set"] == "main"]


def row_gaps(rows: list[dict]) -> dict:
    out = {}
    for vendor, q in ROW_CHECKS:
        rs = [r for r in _main(rows) if r["vendor"] == vendor]
        gap = [r for r in rs if not r["cells"][q]["mentions"]]
        by = defaultdict(int)
        for r in gap:
            by[r["cells"][q]["status"]] += 1
        out[f"{vendor}:{q}"] = {
            "vendor": vendor, "missing": q, "n_rows": len(rs), "n_missing": len(gap),
            "fraction": round(len(gap) / len(rs), 6) if rs else None, "by_cause": dict(sorted(by.items())),
            "rows": [{"row": r["row"], "cause": r["cells"][q]["status"], "cell": r["cells"][q]["text"],
                      "other_mentions": {p: c["mentions"] for p, c in r["cells"].items() if p != q}}
                     for r in gap]}
    return out


def reach(rows: list[dict]) -> dict:
    universe = defaultdict(set)   # (p, q) -> serviços de p vistos em tabela com coluna q
    reached = defaultdict(set)
    for r in _main(rows):
        cols = TABLE_COLUMNS[r["vendor"]]
        for p in cols:
            ids = {MN.service_id(p, m) for m in r["cells"][p]["mentions"]}
            for q in cols:
                if q == p or q == r["pivot"]:
                    continue
                universe[(p, q)] |= ids
                if r["cells"][q]["mentions"]:
                    reached[(p, q)] |= ids
    out = {}
    for p in PROVIDERS:
        for q in PROVIDERS:
            if p == q or (p, q) not in universe:
                continue
            u, h = universe[(p, q)], reached[(p, q)]
            out[f"{p}->{q}"] = {"from": p, "to": q, "n_services": len(u), "n_reached": len(h),
                                "fraction": round(len(h) / len(u), 6) if u else None,
                                "unreached": sorted(u - h)}
    return out


def metric(mid: str, name: str, reading: str, k: int, n: int, frame_ref: dict, frame_desc: str, rule: str,
           text: str) -> dict:
    est = round(k / n, 6) if n else None
    return {"metric_id": mid, "name": name, "reading": reading, "axis": "representability",
            "quantifier": "observed_fraction",
            "operational_coverage": {"lower": est if n else 0.0, "upper": est if n else 1.0, "est": est, "n": n},
            "frame": {"ref": frame_ref, "description": frame_desc},
            "inclusion": {"rule_id": rule, "text": text}, "weights": {"scheme": "uniform"},
            "joint_uncertainty": {"method": "none"}}


def metrics(gaps: dict, rch: dict, frame_ref: dict) -> list[dict]:
    out = []
    for key, g in gaps.items():
        v, q = g["vendor"], g["missing"]
        out.append(metric(
            f"M-OFFTAB-ROW-{v.upper()}-NO-{q.upper()}",
            f"linhas da tabela {v} sem contraparte {NAMES[q]}", "complete_unit", g["n_missing"], g["n_rows"],
            frame_ref, f"censo das linhas main da tabela {v} em table_rows.jsonl (sem incerteza amostral)",
            f"INC-OFFTAB-ROW-{v.upper()}", f"linha main da tabela {v}; conta se a coluna {q} não nomeia serviço (vazia, ausência explícita ou prosa)"))
    for key, r in rch.items():
        p, q = r["from"], r["to"]
        out.append(metric(
            f"M-OFFTAB-REACH-{p.upper()}-{q.upper()}",
            f"serviços {NAMES[p]} que dividem linha com algum serviço {NAMES[q]}", "graph", r["n_reached"],
            r["n_services"], frame_ref,
            f"ids distintos de {p} nas tabelas main com colunas {p} e {q} e pivô diferente de {q} "
            "(censo; id = slug do rótulo)",
            f"INC-OFFTAB-REACH-{p.upper()}-{q.upper()}",
            f"serviço {p} em tabela que tem coluna {q}; conta se divide linha com menção de {q}"))
    return out


def verdict(gaps: dict, rch: dict) -> list[str]:
    """Frases de leitura, só com os números calculados (sem limiar escolhido depois)."""
    out = []
    for p in ("gcp", "azure", "oci"):
        alts = {q: rch[f"{p}->{q}"]["fraction"] for q in PROVIDERS if f"{p}->{q}" in rch}
        if "aws" in alts:
            others = {q: f for q, f in alts.items() if q != "aws"}
            rel = "maior que" if all(alts["aws"] > f for f in others.values()) else \
                "menor que" if all(alts["aws"] < f for f in others.values()) else "entre"
            out.append(f"{NAMES[p]}: alcance para AWS {alts['aws']:.3f}, {rel} o alcance para "
                       + ", ".join(f"{NAMES[q]} {f:.3f}" for q, f in sorted(others.items())))
    for key in ("google:aws", "oracle:aws"):
        g = gaps[key]
        out.append(f"{g['vendor']}: {g['n_missing']} de {g['n_rows']} linhas ({g['fraction']:.3f}) sem serviço AWS "
                   f"(invisíveis a um recorte que parte do catálogo AWS)")
    a, z = gaps["microsoft:aws"], gaps["microsoft:azure"]
    out.append(f"microsoft (pivô AWS): {z['n_missing']} de {z['n_rows']} linhas sem Azure e {a['n_missing']} "
               f"sem AWS (causas: Azure {z['by_cause']}, AWS {a['by_cause']})")
    return out
