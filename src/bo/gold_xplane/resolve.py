"""Gate de resolução do GOLD-XPLANE: todo campo resolve num campo registrado do schema fixado ou é marcado
unresolved, e o arquivo SSSOM é coerente com isso.

  python -I -m bo.gold_xplane.resolve GOLD-XPLANE

Confere, recalculando a partir de $BO_DATA/downloads/crossplane/ (sem rede):
  R1  todo ponto final do patches.jsonl tem resolução do lado XR e do lado MR com status em
      {resolved, runtime, unresolved} e motivo; o recálculo dá o mesmo resultado (nada editado à mão);
  R2  todo campo 'resolved' de MR existe no CRD do provider fixado (nova caminhada no schema);
  R3  toda linha SSSOM nasce de pontos finais extraídos (id do lado = campo do MR ou do XR deles);
  R4  linha com um lado unresolved tem evidence_state UNRESOLVED; linha STRUCTURALLY_VALID tem os dois lados
      resolvidos; nenhuma linha DOC_SUPPORTED ou acima (patch não é sentença publicada);
  R5  lado com id de atributo Terraform (provider:recurso:caminho) tem ponte resolvida pelas tags tf do provider;
  R6  nenhuma linha exactMatch; toda evidência tem level=derived; curation_rule declara o nível DERIVADO.
Sai 0 se tudo confere; 1 com a lista de falhas.
"""
from __future__ import annotations

import json
import re
import sys

from bo.contracts import sssom as CSSSOM

from . import build
from .compose import split_path
from .paths import ID, data_dir, downloads_dir, now_iso
from .schema import ProviderIndex, walk_schema

ATOM = re.compile(r"^(aws|google|azurerm|oci):[a-z][a-z0-9_]*:[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")
STATUSES = {"resolved", "runtime", "unresolved"}


def check() -> tuple[list[str], dict]:
    fails = []
    root = downloads_dir()
    _ex, eps, _rows, _ = build.compute(root)
    fresh = [json.loads(json.dumps(build._ep_record(e), ensure_ascii=False, sort_keys=True)) for e in eps]
    stored_txt = (data_dir() / "patches.jsonl").read_text(encoding="utf-8")
    stored = [json.loads(l) for l in stored_txt.splitlines() if l.strip()]
    if stored != fresh:
        fails.append("R1 patches.jsonl difere do recálculo a partir dos downloads")
    pi = ProviderIndex(root)
    n_fields = {"resolved": 0, "runtime": 0, "unresolved": 0}
    mr_ids, xr_ids = {}, {}
    for i, e in enumerate(stored):
        sides = [("mr", e["mr_resolution"])] + [("xr:" + p, r) for p, r in e["xr_resolutions"].items()]
        for side, r in sides:
            if r.get("status") not in STATUSES or not r.get("reason"):
                fails.append(f"R1 ponto {i} lado {side}: status/motivo ausente ({r.get('status')!r})")
                continue
            n_fields[r["status"]] += 1
        r = e["mr_resolution"]
        if r.get("status") == "resolved":
            repo, tag = r["pin"].rsplit("@", 1)
            m = e["mr"]
            sch, _ = pi.crd_schema(repo, tag, m["group"], m["version"], m["kind"])
            ok = sch is not None and walk_schema(sch, split_path(e["mr_path"]))[0]
            if not ok:
                fails.append(f"R2 ponto {i}: {m['kind']} {e['mr_path']} marcado resolved mas não está no CRD")
    for e in eps:
        mid, _ = build.mr_id(e)
        mr_ids.setdefault(mid, []).append(e)
        for p in e["xr_paths"]:
            xr_ids.setdefault(build.xr_id(e, p), []).append((e, p))
    meta, rows, _cols = CSSSOM.read_tsv((data_dir() / "crossplane.sssom.tsv").read_text(encoding="utf-8"))
    for r in rows:
        cid = r["claim_id"]
        sides_ok = []
        ids = [r["subject_id"], r["object_id"]]
        g = r.get("group")
        if g:
            ids = [v["field"] for v in g["variables"]]
        for sid in ids:
            if sid in mr_ids:
                es = mr_ids[sid]
                sides_ok.append(all(build.resolved_side(e["mr_resolution"]) for e in es))
                if ATOM.match(sid) and not all((e["mr_resolution"].get("bridge") or {}).get("status") == "resolved"
                                               for e in es):
                    fails.append(f"R5 {cid}: {sid} tem forma de atributo Terraform sem ponte resolvida")
            elif sid in xr_ids:
                sides_ok.append(all(build.resolved_side(e["xr_resolutions"][p], xr=True) for e, p in xr_ids[sid]))
            else:
                fails.append(f"R3 {cid}: lado {sid} não vem de nenhum ponto final extraído")
                sides_ok.append(False)
        st = r["evidence_state"]
        if st not in ("STRUCTURALLY_VALID", "UNRESOLVED"):
            fails.append(f"R4 {cid}: evidence_state {st} (patch não sustenta DOC_SUPPORTED ou acima)")
        if not all(sides_ok) and st != "UNRESOLVED":
            fails.append(f"R4 {cid}: lado unresolved mas evidence_state {st}")
        if all(sides_ok) and st == "UNRESOLVED":
            fails.append(f"R4 {cid}: os dois lados resolvem mas evidence_state UNRESOLVED")
        if r["predicate_id"] == "skos:exactMatch":
            fails.append(f"R6 {cid}: exactMatch a partir de patch")
        evs = (r.get("proof") or {}).get("evidence") or []
        if not evs or any(x.get("level") != "derived" for x in evs):
            fails.append(f"R6 {cid}: evidência sem level=derived")
        if r.get("curation_rule") != build.LEVEL_RULE:
            fails.append(f"R6 {cid}: curation_rule sem o nível DERIVADO")
    res = json.loads((data_dir() / "resolution.json").read_text(encoding="utf-8"))
    if res != build.resolution_report(eps, _rows):
        fails.append("R1 resolution.json difere do recálculo")
    summary = {"endpoints": len(stored), "fields": n_fields, "rows": len(rows),
               "rows_unresolved": sum(1 for r in rows if r["evidence_state"] == "UNRESOLVED")}
    return fails, summary


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] != ID:
        print(f"uso: python -I -m bo.gold_xplane.resolve {ID}", file=sys.stderr)
        return 2
    fails, s = check()
    print(f"[{now_iso()}] {ID} resolve: {s['endpoints']} pontos finais; campos resolved={s['fields']['resolved']} "
          f"runtime={s['fields']['runtime']} unresolved={s['fields']['unresolved']}; {s['rows']} linhas SSSOM, "
          f"{s['rows_unresolved']} UNRESOLVED")
    for f in fails[:50]:
        print("  FALHA", f)
    print("RESULTADO:", "OK" if not fails else f"FALHA ({len(fails)})")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
