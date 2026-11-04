"""Gera (ou confere byte a byte, com --check) os artefatos do BRIEFS.

  python -I -m bo.briefs.build            grava briefs/*.txt, briefs/read_allowlists.json, briefs/MANIFEST.sha256,
                                          results/BRIEFS/examples/* e results/BRIEFS/examples_report.json
  python -I -m bo.briefs.build --check    regenera num diretório temporário ($BO_TMP) e compara com o que está no
                                          repositório; sai 1 se algum byte diferir

Os briefs saem dos modelos (templates/) e dos exemplos executados (examples.check): todo veredito, transporte e
ida e volta citado no texto vem da execução, não é digitado. Nada aqui depende do relógio: a data de congelamento
é constante (common.FROZEN_AT), para a regeneração ser idêntica.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

from . import common, content
from . import examples as E

PH = re.compile(r"\{\{([A-Z_]+)(?::([A-Z_0-9]+))?\}\}")

CONSUMERS = {
    "glossarist": "PILOT-STO-GLOSS, PILOT-NET-GLOSS, GLOSSARY-CMP, GLOSSARY-NET, GLOSSARY-STO, GLOSSARY-DB, "
                  "GLOSSARY-SEC, GLOSSARY-OPS",
    "mapper": "PILOT-STO-MAP, PILOT-NET-MAP, MAP-{pair}-{domain} (36: 6 pares × 6 domínios) e RELIAB "
              "(lançado com --role mapper)",
    "hunter": "NONEHUNT-AWS, NONEHUNT-GCP, NONEHUNT-AZURE, NONEHUNT-OCI",
    "auditor": "GLOSSARY-AUDIT",
    "evaluator": "PILOT-EXIT (lançado com --role evaluator) e todo módulo que o coordenador lançar como avaliador",
}
TITLE = {"glossarist": "GLOSSARISTA", "mapper": "MAPEADOR", "hunter": "CAÇADOR DE NONE",
         "auditor": "AUDITOR DO GLOSSÁRIO", "evaluator": "AVALIADOR"}
NORMATIVE = ["semantics/SEMANTICS.html", "transforms/transforms.yaml", "grain/GRAIN.html",
             "ontology/patterns/ONTPAT.html", "prereg/PREREG.html", "contracts"]

EXAMPLES = {
    "EXACT_SAT": (E.EXACT_SAT, "C09"), "BROAD": (E.BROAD, "C09"), "NARROW": (E.NARROW, "C09"),
    "CLOSE": (E.CLOSE, "C09"), "RELATED": (E.RELATED, "C09"), "NONE_ROW": (E.NONE_ROW, "C09"),
    "ALT_STD": (E.ALT_STD, "C09"), "ALT_PREM": (E.ALT_PREM, "C09"), "GROUP": (E.GROUP, "C09-group"),
    "PROJECTION": (E.PROJECTION, "C09"), "UNPROVEN_NO_PRED": (E.UNPROVEN_NO_PRED, "C09"),
    "REFUTED_V2": (E.REFUTED_V2, "C09"), "UNPROVEN_ANCHOR": (E.UNPROVEN_ANCHOR, "C09"),
    "UNPROVEN_READBACK": (E.UNPROVEN_READBACK, "C09"), "DISPUTE": (E.dispute_example(), "C09"),
    "GLOSSARY_CONCEPT": (E.GLOSSARY_CONCEPT, "C20 concept"), "GLOSSARY_CONCEPT_NA": (E.GLOSSARY_CONCEPT_NA, "C20 concept"),
    "ANCHOR_PA": (E.ANCHOR_PA, "C20 anchor_claim"), "ANCHOR_PB": (E.ANCHOR_PB, "C20 anchor_claim"),
    "ANCHOR_PA_AUDITED": (E.ANCHOR_PA_AUDITED, "C20 anchor_claim"),
    "AUDIT_PASS": (E.AUDIT_PASS, "C20 audit"), "AUDIT_INDIRECT": (E.AUDIT_INDIRECT, "C20 audit"),
    "DECISION_BROADER": (E.DECISION_BROADER, "C20 decision"),
    "DECISION_SAME_KIND": (E.DECISION_SAME_KIND, "C20 decision"),
    "DECISION_VALUE_TYPE": (E.DECISION_VALUE_TYPE, "C20 decision"),
    "DECISION_NARROWER": (E.DECISION_NARROWER, "C20 decision"),
}


class BuildError(Exception):
    pass


# --------------------------------------------------------------------------------------- blocos de texto
def ex_block(key: str, rep: dict) -> str:
    rec, kind = EXAMPLES[key]
    line = "  EX| " + common.canon(rec)
    if kind == "C09-group":
        g = E.group_check(rec)
        runs = "; ".join(f"{common.canon(x['input'])} → {common.canon(x['got'])}" for x in g["runs"])
        tail = (f"  EX= grupo: veredito {g['verdict']} (bo.semantics.projections.check_group); execução: {runs}. A "
                f"linha leva translation_fn null porque a tradução está nos passos do grupo")
    elif kind.startswith("C09"):
        a = E.assess(rec)
        rules = ", ".join(a["rules"]) or "nenhuma"
        tail = f"  EX= veredito {a['verdict']} (bo.semantics.obligations; regras que falham: {rules})"
    else:
        tail = f"  EX= {kind}"
    return line + "\n" + tail


def tr_text(key: str, rep: dict) -> str:
    def fmt(lst):
        out = []
        for x in lst:
            out.append(f"{json.dumps(x['in'], ensure_ascii=False)} → "
                       + (json.dumps(x["out"], ensure_ascii=False) if x["result"] == "carried" else x["code"]))
        return ", ".join(out)
    t = {"BROAD": rep["broad_transport"], "NARROW": rep["narrow_transport"], "EXACT_SAT": rep["exact_transport"]}[key]
    s = f"A→B: {fmt(t['forward'])}"
    if t["inverse"]:
        s += f" | B→A: {fmt(t['inverse'])}"
    return s


def inv_text(rep: dict) -> str:
    i = rep["broad_inverse"]
    return (f"{i['subject_id']} {i['predicate_id']} {i['object_id']} (semantic_relation {i['semantic_relation']}, "
            f"basis inverse)")


def rt_text(rep: dict) -> str:
    fw = rep["broad_transport"]["forward"]
    back = rep["broad_roundtrip_values"]["A_B_A"]
    return "; ".join(f"{x['in']} → {x['out']} → {b}" for x, b in zip(fw, back))


def skos_text(rep: dict) -> str:
    a, b = E.BROAD["subject_id"], E.BROAD["object_id"]
    s = rep["skos_closure"]
    yes = lambda v: "sim" if v else "NÃO"  # noqa: E731
    return (f"infere {a} skos:broader {b} (b mais geral): {yes(s['a_broader_b'])}; infere {b} skos:narrowMatch {a}: "
            f"{yes(s['b_narrowMatch_a'])}; não infere {b} skos:broadMatch {a}: {yes(s['not_b_broadMatch_a'])}; "
            f"não infere {a} skos:narrowMatch {b}: {yes(s['not_a_narrowMatch_b'])}")


def hub_text(rep: dict) -> str:
    h = rep["hub"]
    return (f"as duas âncoras DOC_SUPPORTED com citação → {h['supported']['outcome']} como "
            f"{h['supported']['relation']}; uma âncora só STRUCTURALLY_VALID e sem citação → {h['weak']['outcome']}")


def tsv_text(rep: dict) -> str:
    t = rep["tsv_roundtrip"]
    return (f"{len(E.GOOD_ROWS)} linhas, {len(t['columns'])} colunas, iguais na volta: "
            f"{'sim' if t['equal'] else 'NÃO'}; colunas perdidas: {', '.join(t['lost_columns']) or 'nenhuma'}; "
            f"prefixos declarados: {', '.join(t['prefixes_declared'])}")


def registry() -> dict:
    t = yaml.safe_load((common.repo() / "transforms" / "transforms.yaml").read_text(encoding="utf-8"))
    sc = [x["name"] for x in t["scalar"]]
    tu = [x["name"] for x in t["combinators"] if not x["name"].startswith("compare_")]
    return {"version": str(t.get("contract_version")), "scalar": sc, "tuple": tu}


def read_list(role: str) -> str:
    out = []
    for tpl in content.ROLE_READ[role]:
        out.append(f"  {tpl:<42} {content.WHY_READ[tpl]}")
    return "\n".join(out)


def normative_line() -> str:
    from bo.repo import core as RC
    parts = []
    for rel in NORMATIVE:
        h = RC.hash_path(common.repo() / rel)
        if not h.get("sha256"):
            raise BuildError(f"fonte normativa ausente: {rel}")
        parts.append(f"{rel}{'/' if h['kind'] == 'dir' else ''} {h['sha256'][:16]}")
    return "; ".join(parts)


def contract_versions() -> str:
    out = []
    for cid, f in (("C09", "C09_correspondences.schema.json"), ("C20", "C20_glossary.schema.json")):
        s = json.loads((common.repo() / "contracts" / f).read_text(encoding="utf-8"))
        out.append(f"{cid} {s['x-bo-contract']['version']}")
    return ", ".join(out)


def parse_role_template(text: str) -> dict:
    parts, cur, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^@@([A-Z_]+)$", line)
        if m:
            if cur:
                parts[cur] = "\n".join(buf).strip("\n")
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    if cur:
        parts[cur] = "\n".join(buf).strip("\n")
    need = {"INTRO", "BODY", "FORBID", "DISPATCH_EXAMPLE", "DISPATCH_CMDS", "PROV_PARAMS", "PROV_RECORD"}
    miss = need - set(parts)
    if miss:
        raise BuildError(f"modelo sem seção: {sorted(miss)}")
    return parts


def render(text: str, values: dict, rep: dict) -> str:
    def sub(m):
        name, arg = m.group(1), m.group(2)
        if name == "EX":
            if arg not in EXAMPLES:
                raise BuildError(f"exemplo desconhecido: {arg}")
            return ex_block(arg, rep)
        if name == "TR":
            return tr_text(arg, rep)
        if name == "INV":
            return inv_text(rep)
        if name == "RT":
            return rt_text(rep)
        if name == "SKOS":
            return skos_text(rep)
        if arg is None and name in values:
            return values[name]
        raise BuildError(f"marcador sem valor: {m.group(0)}")
    out = PH.sub(sub, text)
    left = PH.findall(out)
    if left:
        raise BuildError(f"marcadores não resolvidos: {left}")
    return out


def brief_text(role: str, rep: dict, reg: dict, norm: str, cver: str) -> str:
    tdir = common.templates_dir()
    parts = parse_role_template((tdir / f"{role}.txt").read_text(encoding="utf-8"))
    fname = common.BRIEF_FILES[role]
    values = {
        "ROLE": role, "BRIEF_FILE": fname, "VERSION": common.BRIEF_VERSION, "READ_LIST": read_list(role),
        "FORBID_ROLE": parts["FORBID"], "DISPATCH_EXAMPLE": parts["DISPATCH_EXAMPLE"],
        "DISPATCH_CMDS": parts["DISPATCH_CMDS"], "PROV_PARAMS": parts["PROV_PARAMS"],
        "PROV_RECORD": parts["PROV_RECORD"], "HUB": hub_text(rep), "REGISTRY_VERSION": reg["version"],
        "REGISTRY_SCALAR": ", ".join(reg["scalar"]), "REGISTRY_TUPLE": ", ".join(reg["tuple"]),
        "PREFIXES": ", ".join(f"{k}: {v}" for k, v in {**E.PROVIDER_PREFIXES, **{
            k: v for k, v in E.PREFIXES.items() if k not in ("pa", "pb", "pc")}}.items()),
        "TSV_ROUNDTRIP": tsv_text(rep),
    }
    header = "\n".join([
        f"BRIEF DO {TITLE[role]} — BrevOps Ontology (briefs/{fname})",
        f"Versão {common.BRIEF_VERSION} · congelado em {common.FROZEN_AT} (America/Recife) · produtor: módulo BRIEFS",
        f"Contratos: {cver} (versões lidas dos schemas em contracts/)",
        f"Fontes normativas (sha256, 16 primeiros): {norm}",
        f"Quem usa: {CONSUMERS[role]}; papel {role} ({common.ROLE_PT[role]}) no bo-lane.",
        "Precedência: este brief de papel complementa o brief de lançamento do seu módulo; em conflito vale o mais",
        "restritivo, e o conflito vai para o relatório. Mudar este texto depois do FREEZE0 é emenda (versão nova, motivo",
        "e tools/invalidate.py check --apply nos consumidores).",
        "Linhas 'EX|' são exemplos SINTÉTICOS (provedores pa, pb, pc em example.org; evidência 'fixture:'); a linha",
        "'EX=' logo abaixo diz o que o código devolve para ela. Não são fatos sobre nenhum provedor real e não são",
        "resposta de nenhuma célula do estudo: não os copie, raciocine com eles.",
        "Histórico: 1.0.0 (2026-11-03) primeira versão congelada; 1.1.0 (2026-11-03) emenda 3 do CONTRACTS (C09",
        "3.1.0 e C20 3.1.0): ausência tipada no campo absence, contestação no campo disputes, decisions.jsonl com",
        "validador e o kind narrower.",
    ])
    body = render("\n\n".join([parts["INTRO"], (tdir / "core.txt").read_text(encoding="utf-8").rstrip("\n"),
                               "PAPEL: " + common.ROLE_PT[role].upper() + "\n" + parts["BODY"],
                               (tdir / "footer.txt").read_text(encoding="utf-8").rstrip("\n")]), values, rep)
    return header + "\n\n" + body + "\n"


def allowlists_doc() -> dict:
    roles = {}
    for role in common.ROLES:
        roles[role] = {"brief": f"briefs/{common.BRIEF_FILES[role]}", "read": list(content.ROLE_READ[role]),
                       "forbid_patterns": list(content.ROLE_FORBID[role])}
    return {"schema": "bo.read_allowlists/1", "module": common.MODULE, "version": common.BRIEF_VERSION,
            "frozen_at": common.FROZEN_AT,
            "note": "o bo-lane lê roles.<papel>.read; $OWNS e $INPUTS vêm do catálogo do módulo, $WT é a worktree da "
                    "lane; a lane soma $BO_DATA/<ID>, $BO_TMP, locks, o git comum, a cadeia de ferramentas e o brief e "
                    "os gates do módulo. A partição de teste nunca entra em lista nenhuma.",
            "test_partition": list(content.TEST_PARTITION),
            "launch_role_override": dict(content.LAUNCH_ROLE_OVERRIDE),
            "evaluator_modules": list(content.EVALUATOR_MODULES),
            "roles": roles}


def generate(root: Path) -> dict:
    """Escreve tudo sob root (o repositório ou uma cópia temporária). Devolve o relatório dos exemplos."""
    rep = E.check()
    if rep["problems"]:
        raise BuildError("exemplos não se comportam como o brief diz: " + "; ".join(rep["problems"]))
    reg, norm, cver = registry(), normative_line(), contract_versions()
    bdir = root / "briefs"
    bdir.mkdir(parents=True, exist_ok=True)
    files = {}
    for role in common.ROLES:
        p = bdir / common.BRIEF_FILES[role]
        p.write_text(brief_text(role, rep, reg, norm, cver), encoding="utf-8")
        files[p.name] = p
    al = bdir / "read_allowlists.json"
    al.write_text(common.pretty(allowlists_doc()), encoding="utf-8")
    files[al.name] = al
    man = "".join(f"{common.sha256_file(files[n])}  briefs/{n}\n" for n in sorted(files))
    (bdir / "MANIFEST.sha256").write_text(man, encoding="utf-8")
    rdir = root / "results" / common.MODULE
    exdir = rdir / "examples"
    if exdir.exists():
        shutil.rmtree(exdir)
    vrep = E.validate_files(exdir)
    bad = {k: v for k, v in vrep.items() if v["rc"] != 0}
    if bad:
        raise BuildError(f"exemplo reprovado no validador do contrato: {bad}")
    report = {"schema": "bo.briefs_examples/1", "module": common.MODULE, "version": common.BRIEF_VERSION,
              "cases": rep["cases"], "broad_transport": rep["broad_transport"],
              "broad_roundtrip_values": rep["broad_roundtrip_values"], "broad_inverse": rep["broad_inverse"],
              "narrow_transport": rep["narrow_transport"], "exact_transport": rep["exact_transport"],
              "close_inverse": rep["close_inverse"], "related_transport": rep["related_transport"],
              "skos_closure": rep["skos_closure"], "group": rep["group"], "projections": rep["projections"], "tsv_roundtrip": rep["tsv_roundtrip"], "hub": rep["hub"],
              "contract_validation": {k: {"kind": v["kind"], "rc": v["rc"]} for k, v in vrep.items()}}
    (rdir / "examples_report.json").write_text(common.pretty(report), encoding="utf-8")
    # manifesto dos resultados (C17): tudo em results/BRIEFS menos o próprio manifesto e o summary.json (que o
    # tools/provenance.py grava com hora). CONTRACT_CHANGE.txt é lido do repositório quando root é uma cópia.
    src_cc = common.repo() / "results" / common.MODULE / "CONTRACT_CHANGE.txt"
    if src_cc.is_file() and (rdir / "CONTRACT_CHANGE.txt") != src_cc:
        shutil.copyfile(src_cc, rdir / "CONTRACT_CHANGE.txt")
    rel = sorted(p.relative_to(root).as_posix() for p in rdir.rglob("*")
                 if p.is_file() and p.name not in ("MANIFEST.sha256", "summary.json"))
    (rdir / "MANIFEST.sha256").write_text("".join(f"{common.sha256_file(root / r)}  {r}\n" for r in rel),
                                          encoding="utf-8")
    return report


GENERATED = ["briefs/" + f for f in sorted(common.BRIEF_FILES.values())] + \
            ["briefs/read_allowlists.json", "briefs/MANIFEST.sha256", "results/BRIEFS/examples_report.json",
             "results/BRIEFS/MANIFEST.sha256"]


def generated_files(root: Path) -> list[str]:
    ex = sorted(p.relative_to(root).as_posix() for p in (root / "results" / "BRIEFS" / "examples").glob("*"))
    return GENERATED + ex


def check() -> list[str]:
    tmp = common.tmp_dir() / "regen"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    generate(tmp)
    diffs = []
    repo = common.repo()
    for rel in sorted(set(generated_files(tmp)) | set(generated_files(repo))):
        a, b = repo / rel, tmp / rel
        if not a.exists() or not b.exists() or a.read_bytes() != b.read_bytes():
            diffs.append(rel)
    return diffs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.briefs.build")
    ap.add_argument("--check", action="store_true", help="regenera no BO_TMP e compara byte a byte")
    a = ap.parse_args(argv)
    try:
        if a.check:
            diffs = check()
            for d in diffs:
                common.emit(f"  DIFERE {d}")
            common.emit(f"[{common.now()}] bo.briefs.build --check: "
                        f"{'regeneração idêntica' if not diffs else str(len(diffs)) + ' arquivo(s) diferem'}")
            return 0 if not diffs else 1
        rep = generate(common.repo())
        common.emit(f"[{common.now()}] bo.briefs.build: {len(common.BRIEF_FILES)} briefs, read_allowlists.json, "
                    f"MANIFEST.sha256; {len(rep['cases'])} exemplos executados")
        return 0
    except BuildError as e:
        common.emit(f"[{common.now()}] bo.briefs.build: ERRO: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
