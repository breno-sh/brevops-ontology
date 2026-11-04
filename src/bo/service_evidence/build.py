"""Gera as saídas do SERVICE-EVIDENCE.

  python -I -m bo.service_evidence.build           grava
  python -I -m bo.service_evidence.build --check   regera em memória e compara byte a byte (evidence_levels.json
                                                   sem o carimbo generated_at); sai 1 se diverge

Saídas:
  $BO_DATA/SERVICE-EVIDENCE/service_evidence.jsonl   C25 1.0.0, ordenado por evidence_id
  $BO_DATA/SERVICE-EVIDENCE/protocol_support.jsonl   formato bo.protocol_support/1 (protocol.SCHEMA)
  $BO_REPO/results/SERVICE-EVIDENCE/evidence_levels.json   contagens por provedor × fato × nível × status,
                                                   entradas lidas (variantes, shared_block_map), regras, lacunas
  $BO_REPO/results/SERVICE-EVIDENCE/sources.json     cada fonte com pin, commit, data e sha256
  $BO_REPO/results/SERVICE-EVIDENCE/protocol_support.schema.json
"""

from __future__ import annotations

import collections
import json
import sys

from . import common, curated, extract, protocol, rules, sources


def _protocol_atoms():
    for probe, p, T, attrs, *_ in protocol.ENTRIES:
        for a in attrs:
            sources.EXTRA_ATOMS.add(f"{p}:{T}:{a}")


def generate() -> dict:
    _protocol_atoms()
    ctxs, stats, bridges = {}, {}, {}
    for p in common.PROVIDERS:
        ctx, st, extra = extract.run(p)
        ctxs[p], stats[p], bridges[p] = ctx, st, extra["bridges"]
        stats[p]["out_of_pin_examples"] = extra["out_of_pin_examples"]
    _, cur = curated.records(ctxs, bridges)
    recs = []
    for p in common.PROVIDERS:
        stated = {(r["terraform_resource_type"], r["fact_kind"]) for r in ctxs[p].recs if r["status"] == "stated"}
        dropped = 0
        for r in ctxs[p].recs:
            if r["status"] == "unknown" and (r["terraform_resource_type"], r["fact_kind"]) in stated:
                dropped += 1
                continue
            recs.append(r)
        stats[p]["unknown_dropped_because_stated"] = dropped
    recs.sort(key=lambda r: r["evidence_id"])
    ids = [r["evidence_id"] for r in recs]
    if len(ids) != len(set(ids)):
        raise SystemExit("evidence_id repetido")
    prow, pmiss = protocol.rows()
    perr = protocol.validate(prow)
    if perr:
        raise SystemExit("protocol_support fora do formato: " + "; ".join(perr[:5]))
    return {"recs": recs, "protocol": prow, "protocol_missing": pmiss, "stats": stats, "curated": cur}


def evidence_levels(g: dict) -> dict:
    by = collections.defaultdict(lambda: collections.Counter())
    tot = collections.Counter()
    for r in g["recs"]:
        by[r["provider"]][f"{r['fact_kind']}|{r['level']}|{r['status']}"] += 1
        tot[r["level"]] += 1
        tot[f"status:{r['status']}"] += 1
    types_cov = {}
    for p in common.PROVIDERS:
        kinds = collections.defaultdict(set)
        for r in g["recs"]:
            if r["provider"] == p and r["status"] == "stated":
                kinds[r["fact_kind"]].add(r["terraform_resource_type"])
        types_cov[p] = {k: len(v) for k, v in sorted(kinds.items())}
    inputs = []
    for p in common.PROVIDERS:
        for path in sources.input_paths(p):
            inputs.append({"path": "$BO_DATA/" + str(path.relative_to(common.bo_data())),
                           "sha256": common.sha256_file(path)})
    inputs.append({"path": "$BO_REPO/universe/pins.json",
                   "sha256": common.sha256_file(common.bo_repo() / "universe" / "pins.json")})
    gaps = [{"provider": r["provider"], "terraform_resource_type": r["terraform_resource_type"],
             "fact_kind": r["fact_kind"]}
            for r in g["recs"] if r["status"] == "unknown"
            and r["terraform_resource_type"] in set(sum(curated.NET_TYPES.values(), []) +
                                                    sum(curated.STO_TYPES.values(), []))]
    st = {p: {k: v for k, v in g["stats"][p].items() if k != "counters"} for p in common.PROVIDERS}
    for p in common.PROVIDERS:
        st[p]["docs_facts_read"] = sources.docs_facts(p)[1]
        st[p]["shared_block_map"] = sources.shared_blocks(p)[1]
        st[p]["extract_counters"] = g["stats"][p]["counters"]
    return {
        "schema": "bo.service_evidence_levels/1", "module": common.MODULE, "contract": "C25",
        "contract_version": "1.0.0", "generated_at": common.now(),
        "records": len(g["recs"]), "by_level": dict(sorted(tot.items())),
        "by_provider": {p: dict(sorted(by[p].items())) for p in common.PROVIDERS},
        "types_with_stated_fact": types_cov,
        "protocol_support": {"rows": len(g["protocol"]),
                             "by_status": dict(collections.Counter(r["status"] for r in g["protocol"])),
                             "missing": g["protocol_missing"]},
        "curated": g["curated"],
        "pilot_slice_gaps": gaps,
        "level_policy": {
            "published": "a frase citada (doc_source da página fixada, ou nó do schema do binário assinado do pin "
                         "em web_citation) diz o valor; o resolver confere na fonte fixada",
            "derived": "regra declarada em value.rule sobre fatos publicados do mesmo arquivo (derived_from)",
            "interpreted": "leitura do modelo claude-opus-5-5 sobre a frase citada; value.basis diz o que foi "
                           "inferido além do texto",
            "unknown": "status unknown com unknown_reason; a citação é a publicação consultada (título da página, "
                       "ou as chaves do bloco do tipo no schema quando não há página), para refazer a busca",
        },
        "rules": rules.RULES,
        "inputs": {
            "files": inputs,
            "type_subcategory": {p: st[p]["type_subcategory_variants"] for p in common.PROVIDERS},
            "type_subcategory_reading": sources.__doc__.strip(),
            "notes": [
                f"DOCS-AWS: docs_facts.jsonl lido com {sources.docs_facts('aws')[1].get('lidos')} fatos (versão "
                "completa, com os blocos repetidos). O shared_block_map.jsonl também é lido: átomo repetido sem fato "
                "próprio usaria os do canônico (mesma frase e linha); usos nesta geração: "
                f"{g['stats']['aws']['counters'].get('via_shared_block_map', 0)}",
                "SCHEMA-GCP G3 em ABANDON: 89 páginas do índice são de tipos só do google-beta 8.9.0; aqui só entram "
                "tipos do schema fixado do google (types.jsonl), então essas páginas não geram fato",
                "SCHEMA-OCI G3 em ABANDON (defeitos da doc upstream: páginas com slug divergente, data source em r/, "
                "tipos sem página): o tipo vai à página que o DOCS-OCI ligou a ele (doc_file); tipo sem página "
                "fica UNKNOWN citando as chaves do bloco no schema (R-ABSENT-NOPAGE)",
            ],
        },
        "per_provider": st,
    }


def sources_doc() -> dict:
    out = {"schema": "bo.service_evidence_sources/1", "module": common.MODULE, "providers": {}}
    for p in common.PROVIDERS:
        src = common.SRC[p]
        m = common.schema_meta(p)
        out["providers"][p] = {
            "pin": {"provider_version": common.version(p), "source": m["source"],
                    "shasums_sha256": common.pins()[p]["shasums_sha256"]},
            "docs": {"repo": src["repo"], "tag": common.tag(p), "commit": src["commit"],
                     "commit_date": src["commit_date"], "root": src["docs_root"],
                     "source_txt": src["source_txt"],
                     "source_txt_sha256": common.sha256_file(common.real(src["source_txt"]))},
            "schema": {"uri": m["uri"], "sha256": m["sha256"], "retrieved_at": m["retrieved_at"],
                       "path": src["prefetch"].format(v=common.version(p)) + "/providers-schema.json"},
        }
    return out


def render(g: dict) -> dict[str, str]:
    lines = "".join(common.canon(r) + "\n" for r in g["recs"])
    prot = "".join(common.canon(r) + "\n" for r in g["protocol"])
    lv = json.dumps(evidence_levels(g), ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    srcs = json.dumps(sources_doc(), ensure_ascii=False, indent=1) + "\n"
    sch = json.dumps(protocol.SCHEMA, ensure_ascii=False, indent=1) + "\n"
    return {
        str(common.out_dir() / "service_evidence.jsonl"): lines,
        str(common.out_dir() / "protocol_support.jsonl"): prot,
        str(common.results_dir() / "evidence_levels.json"): lv,
        str(common.results_dir() / "sources.json"): srcs,
        str(common.results_dir() / "protocol_support.schema.json"): sch,
    }


def _strip_stamp(text: str) -> str:
    try:
        d = json.loads(text)
    except ValueError:
        return text
    if isinstance(d, dict):
        d.pop("generated_at", None)
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    g = generate()
    files = render(g)
    if "--check" in argv:
        bad = []
        for path, text in files.items():
            try:
                cur = open(path, encoding="utf-8").read()
            except OSError:
                bad.append(f"{path}: ausente")
                continue
            if path.endswith("evidence_levels.json"):
                if _strip_stamp(cur) != _strip_stamp(text):
                    bad.append(f"{path}: difere")
            elif cur != text:
                bad.append(f"{path}: difere")
        if bad:
            print("regeneração NÃO idêntica: " + "; ".join(bad))
            return 1
        print(f"regeneração idêntica: {len(files)} arquivos, {len(g['recs'])} fatos, {len(g['protocol'])} linhas "
              f"de protocolo")
        return 0
    common.out_dir().mkdir(parents=True, exist_ok=True)
    common.results_dir().mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"[{common.now()}] gravado: {len(g['recs'])} fatos C25, {len(g['protocol'])} linhas de protocolo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
