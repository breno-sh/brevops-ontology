"""terraform init/validate offline, num sandbox sem credenciais (decisão D1), para conferir o renderizador.

  python -I -m bo.harness.aws.tf_validate RENDER_DIR [--json SAIDA]

Para cada plano do render_manifest.json com arquivo .tf, roda 'terraform validate' com só os modelos e aquele
plano. Ambiente: env -i, HOME e TF_PLUGIN_CACHE_DIR temporários em $BO_TMP, sem ~/.aws nem variável de
credencial, provider vindo só do mirror local com o zip assinado (-plugin-dir), -backend=false. Nada de plan
ou apply. Confere: plano RENDERED valida; plano UNKNOWN_INPUT com campo obrigatório faltando é recusado pelo
próprio Terraform com 'Missing required argument' (ou bloco faltando) nesses campos.
Sai 0 quando todo plano concorda com o estado que o renderizador deu.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import pins
from .render import TEMPLATE_FILES

CRED_HINTS = ("AWS_", "GOOGLE_", "ARM_", "OCI_", "TF_VAR_")


def terraform_bin() -> str:
    p = shutil.which("terraform")
    if not p:
        raise pins.PinError("terraform não está no PATH")
    return p


def sandbox_env(work: Path) -> dict:
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / ".terraformrc").write_text("", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(pins.socket_dir()), "TF_IN_AUTOMATION": "1",
           "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1", "TF_CLI_CONFIG_FILE": str(home / ".terraformrc")}
    assert not any(k.startswith(CRED_HINTS) for k in env)
    return env


def _run(args, cwd: Path, env: dict, timeout=600):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def validate_render(render_dir: Path, work: Path | None = None) -> dict:
    render_dir = Path(render_dir)
    man = json.loads((render_dir / "render_manifest.json").read_text(encoding="utf-8"))
    pin = pins.load_pin()
    mirror = pins.mirror_dir(pin)
    if not mirror.exists():
        raise pins.PinError(f"mirror do provider ausente: {mirror}")
    tf = terraform_bin()
    work = Path(work) if work else pins.tmp_root() / "tf_validate"
    if work.exists():
        shutil.rmtree(work)
    root = work / "root"
    root.mkdir(parents=True)
    env = sandbox_env(work)
    for f in TEMPLATE_FILES:
        shutil.copyfile(render_dir / f, root / f)
    r = _run([tf, "init", "-backend=false", "-input=false", "-no-color", f"-plugin-dir={mirror}"], root, env)
    if r.returncode != 0:
        raise RuntimeError("terraform init offline falhou: " + (r.stdout + r.stderr)[-600:])
    results = []
    for e in man["plans"]:
        if not e.get("file"):
            continue
        for old in root.glob("LP-*.tf"):
            old.unlink()
        shutil.copyfile(render_dir / e["file"], root / e["file"])
        v = _run([tf, "validate", "-json", "-no-color"], root, env)
        try:
            out = json.loads(v.stdout)
        except json.JSONDecodeError:
            out = {"valid": False, "diagnostics": [{"summary": "saída não JSON", "detail": v.stderr[-300:]}]}
        diags = out.get("diagnostics") or []
        missing_tf = sorted({_diag_field(d) for d in diags if _is_missing(d)} - {None})
        want_missing = sorted({m["field"] for m in e["missing"]
                               if m["field"] and "obrigatório" in m["reason"]})
        if e["status"] == "RENDERED":
            agree = bool(out.get("valid"))
        else:
            agree = (not out.get("valid")) and set(want_missing) <= set(missing_tf) if want_missing \
                else True
        results.append({"plan_id": e["plan_id"], "status": e["status"], "terraform_valid": bool(out.get("valid")),
                        "terraform_missing": missing_tf, "renderer_missing_required": want_missing,
                        "agree": agree,
                        "diagnostics": [d.get("summary", "") for d in diags][:10]})
    shutil.rmtree(work, ignore_errors=True)
    return {"terraform_version": pin.terraform_version, "provider_version": pin.provider_version,
            "plans": results, "agree": all(x["agree"] for x in results) and bool(results)}


def _is_missing(d: dict) -> bool:
    s = d.get("summary", "")
    return s.startswith("Missing required argument") or s.startswith("Insufficient ")


def _diag_field(d: dict) -> str | None:
    s, det = d.get("summary", ""), d.get("detail", "")
    if s.startswith("Missing required argument"):
        # 'The argument "instance_class" is required, but no definition was found.'
        if '"' in det:
            return det.split('"')[1]
    if s.startswith("Insufficient ") and s.endswith(" blocks"):
        return s[len("Insufficient "):-len(" blocks")]
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.aws.tf_validate")
    ap.add_argument("render_dir")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    try:
        rep = validate_render(Path(a.render_dir))
    except (pins.PinError, RuntimeError) as e:
        print(f"tf_validate: {e}", file=sys.stderr)
        return 2
    for p in rep["plans"]:
        print(f"  {p['plan_id']:16} {p['status']:14} terraform_valid={p['terraform_valid']!s:5} "
              f"faltam(tf)={p['terraform_missing']} faltam(render)={p['renderer_missing_required']} "
              f"{'concorda' if p['agree'] else 'DISCORDA'}")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"tf_validate: {sum(p['agree'] for p in rep['plans'])}/{len(rep['plans'])} plano(s) concordam "
          f"(terraform {rep['terraform_version']}, aws {rep['provider_version']}, offline, sem credenciais)")
    return 0 if rep["agree"] else 1


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
