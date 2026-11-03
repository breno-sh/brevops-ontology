"""Régua de atributos do C1 (v3, a do catalogo4v2.jsonl), recalculada a partir dos átomos.

Três classes disjuntas por átomo, na ordem de decisão:
  provider_populated  computed, não required, e o nome (último segmento do caminho) em
                      PROVIDER_POPULATED_NAMES: o provedor preenche, o operador não decide;
  cfg                 required ou optional (fora da classe acima): o denominador do C1;
  computed_only       computed puro (nem required nem optional);
  None                nenhum flag (não entra em denominador algum).
cfg_raw = cfg + provider_populated (o denominador antigo, publicado para a sensibilidade).

Isto é uma decisão de análise do estudo C1, e não um fato do schema: os flags crus ficam no átomo (C01);
esta régua só existe para reproduzir o catálogo e para quem quiser o mesmo denominador.
"""

from __future__ import annotations

from .core import TypeSchema

PROVIDER_POPULATED_NAMES = frozenset({"id", "arn", "owner_id", "tags_all", "region"})
CLASSES = ("cfg", "provider_populated", "computed_only")


def classify(atom: dict) -> str | None:
    name = atom["path"].rsplit(".", 1)[-1]
    if atom["computed"] and not atom["required"] and name in PROVIDER_POPULATED_NAMES:
        return "provider_populated"
    if atom["required"] or atom["optional"]:
        return "cfg"
    if atom["computed"]:
        return "computed_only"
    return None


def counts(ts: TypeSchema) -> dict:
    """As contagens do catalogo4v2 (mesmos nomes de campo) de um tipo."""
    c = {k: 0 for k in CLASSES}
    for a in ts.atoms:
        k = classify(a)
        if k:
            c[k] += 1
    return {
        "n_atributos_total": len(ts.atoms),
        "n_atributos_cfg": c["cfg"],
        "n_provider_populated": c["provider_populated"],
        "n_atributos_cfg_raw": c["cfg"] + c["provider_populated"],
        "n_computed_only": c["computed_only"],
        "n_blocos_total": len(ts.blocks),
    }


COUNT_FIELDS = ("n_atributos_total", "n_atributos_cfg", "n_provider_populated", "n_atributos_cfg_raw",
                "n_computed_only", "n_blocos_total")


def tree(ts: TypeSchema) -> dict:
    """A 'arvore' do catalogo4v2 (listas por bloco), reconstruída dos átomos e dos blocos."""
    def node():
        return {"blocos": {}, "cfg": [], "computed_only": [], "n_attr": 0, "opt": [],
                "provider_populated": [], "req": []}
    root = node()

    def at(path):
        n = root
        for seg in path:
            n = n["blocos"].setdefault(seg, node())
        return n
    for b in ts.blocks:
        at(b.path)
    for a in ts.atoms:
        segs = a["path"].split(".")
        n, name = at(segs[:-1]), segs[-1]
        n["n_attr"] += 1
        if a["required"]:
            n["req"].append(name)
        if a["optional"]:
            n["opt"].append(name)
        k = classify(a)
        if k:
            n[k].append(name)

    def norm(n):
        for k in ("cfg", "computed_only", "opt", "provider_populated", "req"):
            n[k].sort()
        n["blocos"] = {k: norm(v) for k, v in sorted(n["blocos"].items())}
        return n
    return norm(root)
