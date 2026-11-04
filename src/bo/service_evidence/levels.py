"""Gate (python -I -m bo.evidence.levels -> bo.service_evidence.levels): todo fato tem nível; PUBLICADO tem citação
literal que resolve na fonte fixada; DERIVADO aponta fatos do mesmo arquivo e cita regra declarada; INTERPRETADO
tem model_id; UNKNOWN tem motivo e nenhum valor.

Confere service_evidence.jsonl e as evidências do protocol_support.jsonl. Resolver:
  doc_source   a frase (depois da mesma redação) aparece no texto da página fixada a partir da linha citada
  web_citation nó do schema do binário assinado do pin, recalculado do arquivo (sha256 = schema_sha256 do pin)
Extras: ponte publicada tem serviço e recurso literais na frase; frase-chave da importação resolve na sua linha;
value.rule existe em rules.RULES. Relatório em $BO_DATA/SERVICE-EVIDENCE/levels_check.json.
"""

from __future__ import annotations

import collections
import json
import sys

from . import apispec, common, rules

LEVELS = {"published", "derived", "interpreted"}


def check_record(r: dict, ids: dict, bad: list, cnt: collections.Counter) -> None:
    eid, p, lvl = r.get("evidence_id"), r.get("provider"), r.get("level")

    def err(msg):
        bad.append(f"{eid}: {msg}")

    if lvl not in LEVELS:
        err(f"nível ausente ou inválido: {lvl!r}")
        return
    cnt[lvl] += 1
    if r.get("status") == "unknown":
        if "value" in r or not r.get("unknown_reason"):
            err("unknown com valor ou sem motivo")
    elif r.get("status") == "stated":
        v = r.get("value")
        if not isinstance(v, dict) or v.get("rule") not in rules.RULES:
            err("valor sem regra declarada (value.rule)")
    else:
        err("status inválido")
    if lvl == "published":
        doc, cit = r.get("doc"), r.get("citation")
        if not doc and not (cit and cit.get("sentence")):
            err("publicado sem citação literal")
        if doc:
            why = common.resolve_doc(p, doc)
            if why:
                err(f"doc não resolve: {why}")
            else:
                cnt["doc_resolvido"] += 1
        if cit and cit.get("section", "").startswith("apispec "):
            why = apispec.resolve(p, cit)
            if why:
                err(f"citação da spec não resolve: {why}")
            else:
                cnt["spec_resolvido"] += 1
        elif cit:
            why = common.resolve_schema(p, cit)
            if why:
                err(f"citação do schema não resolve: {why}")
            else:
                cnt["schema_resolvido"] += 1
        v = r.get("value") or {}
        if v.get("aspect") == "api_resource_bridge" and doc:
            s = doc["sentence"]
            for k in ("service", "resource"):
                if v.get(k) != "UNKNOWN" and v.get(k) not in s:
                    err(f"ponte publicada com {k} que não está na frase")
        if v.get("key_sentence") and v.get("key_line") and doc:
            kd = {k: doc[k] for k in ("repo", "tag", "file")}
            kd.update(line=v["key_line"], sentence=v["key_sentence"])
            if v.get("key_redacted"):
                kd["redacted"] = True
            if common.resolve_doc(p, kd):
                err("frase-chave da importação não resolve")
        if "model_id" in r:
            err("publicado com model_id")
    elif lvl == "derived":
        df = r.get("derived_from") or []
        if not df:
            err("derivado sem derived_from")
        for d in df:
            src = ids.get(d)
            if src is None:
                err(f"derived_from aponta id ausente {d}")
            elif src["provider"] != p:
                err("derived_from de outro provedor")
            elif src["status"] != "stated":
                err("derived_from aponta fato desconhecido")
        if "model_id" in r:
            err("derivado com model_id")
    elif lvl == "interpreted":
        if not r.get("model_id"):
            err("interpretado sem model_id")
        if r.get("doc"):
            why = common.resolve_doc(p, r["doc"])
            if why:
                err(f"âncora do interpretado não resolve: {why}")
        if r.get("status") == "stated" and not (r.get("value") or {}).get("basis"):
            err("interpretado sem basis (o que foi inferido além do texto)")


def check_protocol(rows: list, ids: dict, bad: list, cnt: collections.Counter) -> None:
    for i, r in enumerate(rows, 1):
        tag = f"protocol:{i}:{r.get('probe_type')}:{r.get('provider')}"
        ev = r.get("evidence") or []
        if not ev:
            bad.append(f"{tag}: sem evidência")
        for e in ev:
            lvl = e.get("level")
            if lvl not in LEVELS:
                bad.append(f"{tag}: evidência sem nível")
            elif lvl == "published":
                if e.get("doc"):
                    why = common.resolve_doc(r["provider"], e["doc"])
                    if why:
                        bad.append(f"{tag}: doc não resolve: {why}")
                elif e.get("citation"):
                    why = common.resolve_schema(r["provider"], e["citation"])
                    if why:
                        bad.append(f"{tag}: citação não resolve: {why}")
                else:
                    bad.append(f"{tag}: publicado sem citação")
            elif lvl == "interpreted" and not e.get("model_id"):
                bad.append(f"{tag}: interpretado sem model_id")
            elif lvl == "derived" and e.get("ref") not in ids:
                bad.append(f"{tag}: derivado sem ref válida")
            cnt[f"protocol_{lvl}"] += 1


def load(path) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _data_dir(argv):
    """--staging confere a geração ainda não promovida ($BO_DATA/SERVICE-EVIDENCE/.staging/)."""
    return common.out_dir() / ".staging" if argv and "--staging" in argv else common.out_dir()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    recs = load(_data_dir(argv) / "service_evidence.jsonl")
    rows = load(_data_dir(argv) / "protocol_support.jsonl")
    ids = {r["evidence_id"]: r for r in recs}
    bad, cnt = [], collections.Counter()
    for r in recs:
        check_record(r, ids, bad, cnt)
    check_protocol(rows, ids, bad, cnt)
    rep = {"checked_at": common.now(), "records": len(recs), "protocol_rows": len(rows), "counts": dict(cnt),
           "failures": len(bad), "first_failures": bad[:50]}
    (common.out_dir() / "levels_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n",
                                                         encoding="utf-8")
    print(f"[{rep['checked_at']}] levels: {len(recs)} fatos, {len(rows)} linhas de protocolo; "
          f"{dict(cnt)}; falhas {len(bad)}")
    for b in bad[:20]:
        print("  FALHA", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
