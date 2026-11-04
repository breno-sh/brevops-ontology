"""Gate: terraform validate offline, provider fixado, sandbox sem credenciais.

  python -I -m bo.pilot.tf_validate --slice net --plugin-cache $BO_DATA [--out DIR]

Pega o HCL renderizado que o bo.pilot.run deixou no staging e valida com o terraform fixado (universe/pins.json)
e o provider do cache assinado do SCHEMA-<provedor> (bo.pilot.net.tfval). Um diretório raiz por controle e
provedor com os planos que não colidem (aws e google: rótulos e variáveis prefixados pelo plano); o azurerm, cujo
renderizador usa rótulos por nó, vai um diretório por plano. Sai 0 só se todo plano RENDERED valida e há ao menos
um plano validado.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from bo.pilot.net import pipeline as P
from bo.pilot.net import tfval as TV

from .common import dump, out_dir, parser, repo, say


def main(argv=None) -> int:
    ap = parser("bo.pilot.tf_validate", __doc__)
    ap.add_argument("--plugin-cache", default=None, help="raiz do BO_DATA com SCHEMA-*/plugin_cache")
    a = ap.parse_args(argv)
    base = Path(a.plugin_cache) if a.plugin_cache else TV.data_root()
    out = out_dir(a)
    if not (out / "cases.jsonl").exists():
        from .common import run_pipeline
        run_pipeline(a)
    rows = [json.loads(l) for l in (out / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    groups = {}
    for r in rows:
        if r["render_status"] == "RENDERED":
            groups.setdefault((r["control"], r["direction"].split("->")[1]), []).append(r)
    results, fails, n_ok = [], [], 0
    work = P.tmp() / "tfv"
    for (ctl, prov), rs in sorted(groups.items()):
        units = [rs] if prov in ("aws", "google") else [[r] for r in rs]
        for i, unit in enumerate(units):
            root = work / ctl / prov / (f"u{i:03d}")
            if root.exists():
                shutil.rmtree(root)
            root.mkdir(parents=True)
            _assemble(root, prov, unit, out)
            try:
                res = TV.validate_dir(root, prov, repo(), base, work / ".sbx" / ctl / prov / f"u{i:03d}")
            except TV.SandboxError as e:
                res = {"ok": False, "stage": "sandbox", "detail": str(e)}
            res.update({"control": ctl, "provider": prov, "cases": [r["case_id"] for r in unit]})
            results.append(res)
            if res["ok"]:
                n_ok += len(unit)
            else:
                fails.append(res)
    rep = {"schema": "bo.pilot_net.tf_validate/1", "terraform": TV.pins(repo())["terraform"]["version"],
           "validated_plans": n_ok, "units": results, "failures": len(fails)}
    dump(out / "tf_validate.json", rep)
    say(f"tf_validate: {n_ok} plano(s) validados em {len(results)} raiz(es); falhas {len(fails)} -> "
        f"{'OK' if n_ok and not fails else 'REPROVADO'}")
    for f in fails[:6]:
        say(f"  {f['control']} {f['provider']} {f['cases'][:2]}: {f.get('stage')} "
            f"{json.dumps(f.get('diagnostics') or f.get('detail'), ensure_ascii=False)[:400]}")
    return 0 if n_ok and not fails else 1


def _assemble(root: Path, prov: str, unit: list, out: Path) -> None:
    if prov == "aws":
        from bo.harness.aws import render as R
        for f in R.TEMPLATE_FILES:
            shutil.copyfile(R.templates_dir() / f, root / f)
    elif prov == "google":
        from bo.harness.google import render as R
        from bo.harness.google.schema import Schema
        (root / "versions.tf").write_text(R.versions_tf(Schema.load(None)), encoding="utf-8")
    elif prov == "azurerm":
        from bo.harness.azurerm import _common as C
        shutil.copyfile(C.templates_dir() / "versions.tf", root / "versions.tf")
    for r in unit:
        for p in sorted((out / "hcl" / r["case_id"]).glob("*.tf")):
            name = p.name if prov != "azurerm" else "main.tf"
            shutil.copyfile(p, root / name)


if __name__ == "__main__":
    raise SystemExit(main())
