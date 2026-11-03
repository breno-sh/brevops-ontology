"""Perfil OWL 2 DL sobre o FECHO DE IMPORTS (S3), com o ROBOT fixado, e o laudo do PROV-O publicado.

  python -I -m bo.ontpat.profile          grava results/ONTPAT/profile/ (laudos e profile.json)
  python -I -m bo.ontpat.profile --check  confere que o gravado é o que sai agora

Também roda o HermiT (robot reason) sobre o fecho e sobre o ABox de exemplo: consistente e sem classe
insatisfatível. Os números entram em ONTPAT.html.
"""

from __future__ import annotations

import sys

from . import common as c
from . import pins, robot


def measure() -> dict:
    pdir = c.patterns_dir()
    tmp = c.tmp_dir()
    out = {"schema": "bo.ontpat.profile/1", "toolchain": {k: robot.pins()[k]["version"] for k in ("robot", "hermit", "elk", "owlapi")}}
    closure_file = tmp / "closure.ttl"
    r = robot.run(["merge", "--input", str(pdir / c.PATTERNS), "--collapse-import-closure", "true", "--output", str(closure_file)])
    if r.returncode != 0:
        raise RuntimeError("robot merge falhou: " + r.stderr[-400:])
    rep = tmp / "profile_closure.txt"
    r = robot.run(["validate-profile", "--profile", "DL", "--input", str(closure_file), "--output", str(rep)])
    out["closure"] = {"files": ["$BO_REPO/ontology/patterns/bo-patterns.ttl", "$BO_REPO/ontology/patterns/descriptor-pattern.ttl"],
                      "in_profile": r.returncode == 0, "report": rep.read_text(encoding="utf-8").strip().splitlines()[:3]}
    r = robot.run(["reason", "--reasoner", "hermit", "--input", str(closure_file), "--output", str(tmp / "closure_reasoned.ttl")])
    out["closure"]["hermit_consistent_coherent"] = r.returncode == 0
    r = robot.run(["reason", "--reasoner", "hermit", "--input", str(pdir / c.EXAMPLE), "--output", str(tmp / "example_reasoned.ttl")])
    out["example_abox_hermit_consistent_coherent"] = r.returncode == 0
    r = robot.run(["reason", "--reasoner", "ELK", "--input", str(closure_file), "--output", str(tmp / "closure_elk.ttl")])
    out["closure"]["elk_runs_but_is_not_complete_for_dl"] = {"exit": r.returncode,
        "note": "ELK ignora o que está fora do EL (uniões, inversas, cardinalidades, chaves, oneOf): saída só indicativa; "
                "decisão de consistência é do HermiT"}
    prov = c.data_dir() / "downloads" / pins.EXTERNAL["prov_o"][0]
    prep = tmp / "profile_prov-o.txt"
    r = robot.run(["validate-profile", "--profile", "DL", "--input", str(prov), "--output", str(prep)])
    lines = prep.read_text(encoding="utf-8").strip().splitlines()
    puns = sorted({ln.split("<")[1].split(">")[0] for ln in lines[1:] if ln.startswith("Cannot pun")})
    out["prov_o"] = {"file": "$BO_DATA/downloads/" + pins.EXTERNAL["prov_o"][0], "sha256": c.sha256_file(prov),
                     "in_profile": r.returncode == 0, "violations": len(lines) - 1, "punned_terms": puns,
                     "consequence": "não importado; termos usados declarados em bo-patterns.ttl (MIREOT) só como propriedade de objeto"}
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = c.results_dir() / "profile" / "profile.json"
    cur = measure()
    if "--check" in argv:
        old = c.read_json(target) if target.exists() else None
        if old != cur:
            c.emit("perfil gravado difere do medido agora")
            return 1
        c.emit(f"perfil confere: fecho OWL 2 DL={cur['closure']['in_profile']}, HermiT ok={cur['closure']['hermit_consistent_coherent']}, "
               f"PROV-O publicado em DL={cur['prov_o']['in_profile']} ({cur['prov_o']['violations']} violações)")
        return 0 if cur["closure"]["in_profile"] and cur["closure"]["hermit_consistent_coherent"] else 1
    c.write_json(target, cur)
    (c.results_dir() / "profile" / "prov-o.txt").write_text(
        (c.tmp_dir() / "profile_prov-o.txt").read_text(encoding="utf-8"), encoding="utf-8")
    (c.results_dir() / "profile" / "closure.txt").write_text(
        (c.tmp_dir() / "profile_closure.txt").read_text(encoding="utf-8"), encoding="utf-8")
    c.emit(f"escrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
