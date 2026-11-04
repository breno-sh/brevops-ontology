"""Gate (python -I -m bo.evidence.pinned -> bo.service_evidence.pinned): toda fonte ligada a um pin; nada sem data.

Confere em service_evidence.jsonl e protocol_support.jsonl:
  - pin.provider_version = versão do provedor em universe/pins.json; api_version só onde a ponte publicada a deu;
  - doc_source: repo e tag v<versão> do pin; o commit e a data do commit (results/SERVICE-EVIDENCE/sources.json)
    estão escritos no SOURCE.txt da cópia conferida pelo DOCS-*;
  - web_citation do schema: sha256 do arquivo = schema_sha256 do pin; uri = pacote assinado da pré-busca;
    retrieved_at com fuso -03:00;
  - todo default/as_of dentro de value tem data ISO;
  - sources.json igual ao que o build gera agora (nenhuma fonte sem pin ou sem data).
"""

from __future__ import annotations

import collections
import json
import re
import sys

from . import build, common

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?-03:00$")


def _dates(v, path, bad, eid):
    if isinstance(v, dict):
        if "as_of" in v and not (isinstance(v["as_of"], str) and DATE.match(v["as_of"])):
            bad.append(f"{eid}: {path}.as_of sem data ISO")
        if path.endswith("default") and "as_of" not in v and "c03_fact_id" in v:
            bad.append(f"{eid}: default sem as_of")
        for k, x in v.items():
            _dates(x, f"{path}.{k}", bad, eid)
    elif isinstance(v, list):
        for x in v:
            _dates(x, path, bad, eid)


def main(argv=None) -> int:
    bad, cnt = [], collections.Counter()
    pins = common.pins()
    srcdoc = build.sources_doc()
    cur = json.loads((common.results_dir() / "sources.json").read_text(encoding="utf-8"))
    if cur != srcdoc:
        bad.append("results/SERVICE-EVIDENCE/sources.json difere do que as fontes fixadas dão agora")
    for p, s in srcdoc["providers"].items():
        txt = common.real(s["docs"]["source_txt"]).read_text(encoding="utf-8")
        if s["docs"]["commit"] not in txt:
            bad.append(f"{p}: commit da tag não está no SOURCE.txt")
        if s["docs"]["commit_date"] not in txt:
            bad.append(f"{p}: data do commit não está no SOURCE.txt")
        if s["docs"]["tag"] not in txt:
            bad.append(f"{p}: tag não está no SOURCE.txt")
        if not DT.match(s["schema"]["retrieved_at"]):
            bad.append(f"{p}: schema sem data de extração")
        common.schema(p)  # sai se o sha256 do arquivo não for o do pin
    bridge_ver = {}
    with open(common.out_dir() / "service_evidence.jsonl", encoding="utf-8") as f:
        recs = [json.loads(x) for x in f]
    for r in recs:
        v = r.get("value") or {}
        if v.get("aspect") == "api_resource_bridge" and v.get("api_version"):
            bridge_ver[(r["provider"], r["terraform_resource_type"])] = v["api_version"]
    for r in recs:
        eid, p = r["evidence_id"], r["provider"]
        if r["pin"]["provider_version"] != pins[p]["version"]:
            bad.append(f"{eid}: provider_version fora do pin")
        av = r["pin"].get("api_version")
        if av is not None and bridge_ver.get((p, r.get("terraform_resource_type"))) != av:
            bad.append(f"{eid}: api_version sem ponte publicada que a dê")
        d = r.get("doc")
        if d:
            if d["repo"] != common.SRC[p]["repo"] or d["tag"] != "v" + pins[p]["version"]:
                bad.append(f"{eid}: doc fora do pin")
            cnt["doc"] += 1
        c = r.get("citation")
        if c:
            m = common.SECTION_RX.match(c.get("section", ""))
            if not m or m["sha"] != pins[p]["schema_sha256"] or c["uri"] != srcdoc["providers"][p]["schema"]["uri"]:
                bad.append(f"{eid}: citação de schema fora do pin")
            if not DT.match(c.get("retrieved_at", "")):
                bad.append(f"{eid}: citação sem data")
            cnt["schema"] += 1
        if not d and not c and r["level"] != "derived" and r["level"] != "interpreted":
            bad.append(f"{eid}: sem fonte")
        _dates(v, "value", bad, eid)
    with open(common.out_dir() / "protocol_support.jsonl", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            r = json.loads(line)
            p = r["provider"]
            if r["pin"]["provider_version"] != pins[p]["version"]:
                bad.append(f"protocol:{i}: provider_version fora do pin")
            for e in r["evidence"]:
                d = e.get("doc")
                if d and (d["repo"] != common.SRC[p]["repo"] or d["tag"] != "v" + pins[p]["version"]):
                    bad.append(f"protocol:{i}: doc fora do pin")
            cnt["protocol"] += 1
    print(f"[{common.now()}] pinned: {len(recs)} fatos; {dict(cnt)}; falhas {len(bad)}")
    for b in bad[:20]:
        print("  FALHA", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
