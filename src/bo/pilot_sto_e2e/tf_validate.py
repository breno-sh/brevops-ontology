"""Gate G5: terraform validate offline no provider fixado, num sandbox sem credenciais.

  python -I -m bo.pilot.tf_validate --slice sto --plugin-cache $BO_DATA

Renderiza os planos do estudo (staging) e do canário (12 direções) e roda terraform init -backend=false
-lockfile=readonly + validate em cada raiz, com env -i, HOME em $BO_TMP, sem variável de credencial e o provider
vindo só do espelho local fixado em $BO_DATA/SCHEMA-*/plugin_cache (lock h1 do pin). Controle negativo: um
argumento inexistente plantado numa cópia de cada raiz tem de reprovar no validate. Sem nuvem, sem plan, sem apply.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from bo.pilot.sto import common as C
from bo.pilot.sto import pipeline as PL
from bo.pilot.sto import render as RD

from ._cli import check_slice, parser, say
from ._runs import study_and_canary


def _plant(d: Path) -> Path | None:
    tgt = d.parent / (d.name + "-neg")
    if tgt.exists():
        shutil.rmtree(tgt)
    shutil.copytree(d, tgt, ignore=shutil.ignore_patterns(".terraform"))
    for f in sorted(tgt.rglob("*.tf")):
        txt = f.read_text(encoding="utf-8")
        i = txt.find('resource "')
        if i >= 0:
            j = txt.find("{", i)
            f.write_text(txt[:j + 1] + "\n  bo_not_an_argument = 1\n" + txt[j + 1:], encoding="utf-8")
            return tgt
    return None


def main(argv=None) -> int:
    ap = parser("bo.pilot.tf_validate", __doc__)
    ap.add_argument("--plugin-cache", default=str(C.data_root()))
    a = ap.parse_args(argv)
    check_slice(a)
    base = Path(a.plugin_cache)
    leaked = sorted(k for k in os.environ if k.startswith(RD.CRED_PREFIXES))
    study, can, err = study_and_canary("tfv")
    if err:
        say("tf_validate", err)
        return 2
    rep = {"generated_at": C.now(), "terraform": RD.terraform_bin(), "plugin_cache": C.portable(base),
           "parent_env_credential_vars": len(leaked), "roots": [], "negative_controls": []}
    problems = []
    neg_done = set()
    for label, out in (("study", study), ("canary", can)):
        for prov, rr in sorted(out["render"]["renders"].items()):
            for name, d in RD.tf_dirs(rr):
                v = RD.validate_dir(prov, d, base)
                rep["roots"].append({"set": label, "provider": prov, "root": name, **v})
                if not v["ok"]:
                    problems.append(f"{label}/{name}: {v.get('stage', 'validate')} {v.get('errors') or v.get('tail', '')}")
                if prov not in neg_done:
                    nd = _plant(d)
                    if nd is not None:
                        nv = RD.validate_dir(prov, nd, base)
                        rep["negative_controls"].append({"provider": prov, "root": name, "rejected": not nv["ok"]})
                        if nv["ok"]:
                            problems.append(f"controle negativo aceito pelo validate: {prov} {name}")
                        neg_done.add(prov)
                        shutil.rmtree(nd, ignore_errors=True)
    for p in C.PROVIDERS:
        if not any(r["provider"] == p and r["ok"] for r in rep["roots"]):
            problems.append(f"nenhuma raiz validada para {p}")
        if p not in neg_done:
            problems.append(f"sem controle negativo para {p}")
    rep["problems"] = problems
    C.write_json(PL.stage_dir() / "tf_validate_report.json", rep)
    say("tf_validate", {"roots": len(rep["roots"]), "valid": sum(1 for r in rep["roots"] if r["ok"]),
                        "negative_rejected": sum(1 for x in rep["negative_controls"] if x["rejected"]),
                        "problems": problems[:5]})
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
