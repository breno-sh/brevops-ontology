"""Resolução de campos: todo campo de nó citado pelo ouro resolve num campo de API registrado ou é UNRESOLVED.

Registro = $BO_DATA/GOLD-CARTO/api_fields.jsonl, gerado dos esquemas de nó do próprio Cartography no mesmo commit
(CartographyNodeSchema.label + PropertyRef das propriedades). Estados:
  API_FIELD            existe esquema com o rótulo, a propriedade e uma PropertyRef literal vinda do registro da API
  KWARG_ONLY           a propriedade só vem de set_in_kwargs (contexto da sincronização, ex. região): não é campo de API
  NON_LITERAL_KEY      PropertyRef com chave não literal: não resolve estaticamente
  FIELD_NOT_IN_SCHEMA  há esquema com o rótulo, mas nenhum tem a propriedade
  NO_SCHEMA            nenhum esquema de nó declara o rótulo (ingestão legada, sem modelo de dados)
  NO_NODE_FIELD        static_value: não há campo de origem
Só API_FIELD sustenta STRUCTURALLY_VALID; qualquer outro estado obriga evidence_state = UNRESOLVED.

  python -I -m bo.gold_carto.resolve [GOLD-CARTO]   confere o arquivo publicado contra o registro (saída 0/1)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import MODULE_ID


class Index:
    def __init__(self, registry: list[dict]):
        self.by: dict[str, dict[str, list[dict]]] = {}
        for r in registry:
            self.by.setdefault(r["node_label"], {}).setdefault(r["property"], []).append(r)

    def resolve(self, label: str, fld: str | None) -> dict:
        out = {"node_label": label, "field": fld}
        if not fld:
            return out | {"status": "NO_NODE_FIELD"}
        if label not in self.by:
            return out | {"status": "NO_SCHEMA"}
        refs = self.by[label].get(fld)
        if not refs:
            return out | {"status": "FIELD_NOT_IN_SCHEMA", "schemas": sorted({r["schema"] for v in self.by[label].values()
                                                                             for r in v})}
        api = [r for r in refs if not r["set_in_kwargs"] and r["source_key"] is not None]
        if api:
            return out | {"status": "API_FIELD", "api_keys": sorted({r["source_key"] for r in api}),
                          "schemas": sorted({f"{r['schema_file']}:{r['line']}" for r in api})}
        if all(r["set_in_kwargs"] for r in refs):
            return out | {"status": "KWARG_ONLY", "schemas": sorted({f"{r['schema_file']}:{r['line']}" for r in refs})}
        return out | {"status": "NON_LITERAL_KEY", "schemas": sorted({f"{r['schema_file']}:{r['line']}" for r in refs})}


def load_registry(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def check(records: list[dict], index: Index) -> tuple[list[str], dict]:
    """Recalcula a resolução de cada campo citado (sem confiar no que a linha diz) e cobra a marcação."""
    errs, counts = [], {}
    for r in records:
        cid = r.get("claim_id", "?")
        try:
            other = json.loads(r.get("other") or "{}")
        except json.JSONDecodeError:
            errs.append(f"{cid}: coluna other não é JSON")
            continue
        res = other.get("resolution")
        if not isinstance(res, list) or not res:
            errs.append(f"{cid}: sem resolução de campo (other.resolution)")
            continue
        cited = set()
        for x in res:
            got = index.resolve(x.get("node_label"), x.get("field"))
            if got["status"] != x.get("status"):
                errs.append(f"{cid}: {x.get('node_label')}.{x.get('field')} declarado {x.get('status')}, "
                            f"registro diz {got['status']}")
            counts[got["status"]] = counts.get(got["status"], 0) + 1
            cited.add((x.get("node_label"), x.get("field")))
        ok_all = all(index.resolve(l, f)["status"] == "API_FIELD" for l, f in cited)
        if not ok_all and r.get("evidence_state") != "UNRESOLVED":
            errs.append(f"{cid}: campo não resolvido e evidence_state={r.get('evidence_state')} (devia ser UNRESOLVED)")
        if ok_all and r.get("evidence_state") == "UNRESOLVED":
            errs.append(f"{cid}: todos os campos resolvem mas a linha está UNRESOLVED")
        if other.get("level") == "published":
            label = r.get("subject_label", "")
            node, _, fld = label.partition(".")
            if (node, fld or None) not in cited:
                errs.append(f"{cid}: o campo do sujeito {label} não está na resolução")
    return errs, counts


def main(argv=None) -> int:
    from bo.contracts.sssom import read_tsv
    from .build import data_dir
    argv = list(sys.argv[1:] if argv is None else argv)
    mid = argv[0] if argv else MODULE_ID
    if mid != MODULE_ID:
        print(f"bo.gold_carto.resolve só resolve {MODULE_ID} (pedido: {mid})", file=sys.stderr)
        return 2
    d = data_dir()
    tsv, regp = d / "cartography.sssom.tsv", d / "api_fields.jsonl"
    for p in (tsv, regp):
        if not p.is_file():
            print(f"FAIL: {p} ausente (rode python -I -m bo.gold_carto.build)", file=sys.stderr)
            return 1
    _, recs, _ = read_tsv(tsv.read_text(encoding="utf-8"))
    errs, counts = check(recs, Index(load_registry(regp)))
    n_unres = sum(r.get("evidence_state") == "UNRESOLVED" for r in recs)
    print(f"{MODULE_ID}: {len(recs)} linhas; citações de campo por estado {json.dumps(counts, sort_keys=True)}; "
          f"{n_unres} linhas marcadas UNRESOLVED")
    for e in errs[:40]:
        print("  FAIL", e)
    if errs:
        print(f"FAIL: {len(errs)} problema(s) de resolução")
        return 1
    print("OK: todo campo resolve num campo de API registrado ou a linha está marcada UNRESOLVED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
