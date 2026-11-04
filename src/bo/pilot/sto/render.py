"""Planos C26 -> HCL pelos renderizadores dos HARNESS-* (sem inserção silenciosa), conferência independente e
terraform validate offline no provider fixado, num sandbox sem credenciais (decisão D1).

Nada aqui escreve fora de $BO_TMP: os renderizadores e verificadores dos harness são chamados em processo, com
pasta de trabalho do módulo; os relatórios dos harness (que gravariam em $BO_DATA/HARNESS-*) não são usados.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import common as C

PINS = {"aws": "6.71.0", "google": "8.9.0", "azurerm": "5.12.0", "oci": "9.11.0"}
SRC = {"aws": "hashicorp/aws", "google": "hashicorp/google", "azurerm": "hashicorp/azurerm", "oci": "oracle/oci"}
CRED_PREFIXES = ("AWS_", "GOOGLE_", "GCLOUD_", "CLOUDSDK_", "ARM_", "AZURE_", "OCI_", "TF_VAR_")
OCI_KEYS = {"compartment": "compartment_id", "namespace": "objectstorage_namespace"}


def _google_tmp_here():
    """O harness do Google só aceita $BO_TMP com o nome do próprio módulo (HARNESS-GCP). Para reusar o
    renderizador sem escrever no temporário de outro módulo, a função de temporário dele é trocada, só neste
    processo, pela pasta do PILOT-STO-E2E (achado registrado em controls.json: harness não reusável como está)."""
    from bo.harness.google import common as GC
    mine = C.tmp_dir() / "harness-google"
    mine.mkdir(parents=True, exist_ok=True)
    GC.tmp = lambda: mine
    return mine


def work_dir(name: str) -> Path:
    p = C.tmp_dir() / "render" / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_inputs(d: Path, plans: list[dict], graphs: list[dict]) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    C.write_jsonl(d / "lowering_plan.jsonl", plans)
    C.write_jsonl(d / "graph_ir.jsonl", graphs)
    return d / "lowering_plan.jsonl"


def oci_bindings(d: Path, plans: list[dict]) -> Path:
    syms = set()
    for p in plans:
        for s in p["steps"]:
            for v in s["values"]:
                if v["term"]["kind"] == "symbol":
                    syms.add(v["term"]["symbol_id"])
    rows = []
    for what, key in OCI_KEYS.items():
        sid = "SYM-" + C.short_id("ctx", what)
        if sid in syms:
            rows.append({"symbol_id": sid, "key": key})
    bf = d / "bindings.json"
    C.write_json(bf, {"schema": "bo.harness.oci.bindings/1", "synthetic": True, "module": C.MODULE, "bindings": rows})
    return bf


def render(provider: str, plans: list[dict], graphs: list[dict], name: str) -> dict:
    """Renderiza todos os planos de um provedor. Devolve {plan_id: status}, a pasta de saída e o relatório."""
    d = work_dir(f"{name}/{provider}")
    for x in list(d.iterdir()):
        shutil.rmtree(x) if x.is_dir() else x.unlink()
    pf = write_inputs(d / "in", plans, graphs)
    out = d / "out"
    status = {}
    if provider == "aws":
        from bo.harness.aws import render as R
        man = R.render_file(pf, out, d / "in" / "graph_ir.jsonl")
        status = {e["plan_id"]: e["status"] for e in man["plans"]}
        detail = {e["plan_id"]: e.get("missing") or e.get("problems") or [] for e in man["plans"]}
    elif provider == "google":
        from bo.harness.google import render as R
        _google_tmp_here()
        out = _google_tmp_here() / name / "out"
        rc, rep = R.render_file(pf, out, d / "in" / "graph_ir.jsonl")
        if rc:
            raise RuntimeError(f"render google saiu {rc}: {rep.get('errors', [])[:3]}")
        status = {e["plan_id"]: e["status"] for e in rep["plans"]}
        detail = {e["plan_id"]: [f.get("code") for f in e.get("failures", [])] for e in rep["plans"]}
    elif provider == "azurerm":
        from bo.harness.azurerm import render as R
        rep = R.render_file(pf, out, d / "in" / "graph_ir.jsonl")
        status = {e["plan_id"]: e["status"] for e in rep["plans"]}
        detail = {e["plan_id"]: [i.get("code") for i in e.get("issues", [])] for e in rep["plans"]}
    elif provider == "oci":
        from bo.harness.oci import render as R
        bf = oci_bindings(d / "in", plans)
        rr = R.render(pf, out, d / "in" / "graph_ir.jsonl", bf)
        status = {e["plan_id"]: e["status"] for e in rr.report["plans"]}
        detail = {e["plan_id"]: [i.get("code") for i in e.get("issues", e.get("problems", []))]
                  if isinstance(e.get("issues", e.get("problems", [])), list) else [] for e in rr.report["plans"]}
    else:
        raise ValueError(provider)
    return {"provider": provider, "dir": d, "out": out, "plan_file": pf, "status": status, "detail": detail}


def no_silent_insert(r: dict) -> dict:
    """Conferência independente do HCL contra o plano, pelo verificador do harness do provedor (parser python-hcl2)."""
    prov, d = r["provider"], r["dir"]
    work = d / "nsi"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    problems, checked = [], 0
    if prov == "aws":
        from bo.harness.aws import no_silent_insert as N
        rep = N.check_render(r["out"])
        problems = [f"{f['kind']} {f.get('where')} {f.get('path')}" for f in rep["findings"]]
        checked = rep["counts"].get("RENDERED", 0)
    elif prov == "google":
        from bo.harness.google import no_silent_insert as N
        from bo.harness.google import render as GR
        work = _google_tmp_here() / "nsi"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        rep = N.run_plan(r["plan_file"], work, GR.Schema.load(None))
        for p in rep.get("plans", []):
            problems += [f"{p['plan_id']}: {x}" for x in p.get("problems", [])]
            checked += p["status"] == "RENDERED"
        problems += rep.get("problems", [])
    elif prov == "azurerm":
        from bo.harness.azurerm import no_silent_insert as N
        rep = N.run([r["plan_file"]], work)
        problems = list(rep.get("errors", []))
        checked = rep.get("modules_checked", 0)
        if checked == 0:
            problems = [x for x in problems if "vacuidade" not in x]
    elif prov == "oci":
        from bo.harness.oci import no_silent_insert as N
        rep = N.run_corpus([(r["plan_file"], r["plan_file"].parent / "bindings.json")], work)
        problems = list(rep.get("violations", [])) + list(rep["mutations"]["failed"])
        checked = rep.get("rendered_checked", 0)
    return {"provider": prov, "checked": checked, "problems": problems}


# ----------------------------------------------------------------------------------------------------------
# terraform validate offline
# ----------------------------------------------------------------------------------------------------------
def terraform_bin() -> str:
    p = shutil.which("terraform")
    if not p:
        raise RuntimeError("terraform não está no PATH")
    return p


def plugin_cache(provider: str, base: Path) -> dict:
    pc = base / C.SCHEMA_DIR[provider] / "plugin_cache"
    lock = pc / "terraform.lock.hcl"
    rc = pc / "terraformrc"
    if not lock.exists():
        raise RuntimeError(f"{C.portable(lock)} ausente")
    if not rc.exists():
        # SCHEMA-GCP guarda o espelho desempacotado na própria pasta (sem terraformrc): gera um no BO_TMP
        rc = C.tmp_dir() / "tf" / f"terraformrc.{provider}"
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text('provider_installation {\n  filesystem_mirror {\n    path    = "%s"\n    include = ["registry.terraform.io/%s"]\n  }\n'
                      '  direct {\n    exclude = ["registry.terraform.io/*/*"]\n  }\n}\n' % (pc, SRC[provider]), encoding="utf-8")
    return {"lock": lock, "rc": rc}


def sandbox_env(home: Path, rc: Path) -> dict:
    home.mkdir(parents=True, exist_ok=True)
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home), "TF_CLI_CONFIG_FILE": str(rc),
           "TF_IN_AUTOMATION": "1", "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1", "TMPDIR": str(home)}
    for k in env:
        assert not k.startswith(CRED_PREFIXES)
    return env


def tf_dirs(r: dict) -> list[tuple[str, Path]]:
    """(rótulo, pasta raiz) a validar para os planos RENDERED."""
    prov, out = r["provider"], r["out"]
    rendered = [p for p, s in r["status"].items() if s == "RENDERED"]
    if not rendered:
        return []
    if prov == "aws":
        from bo.harness.aws import render as R
        d = r["dir"] / "validate" / "aws_all"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for f in R.TEMPLATE_FILES:
            shutil.copyfile(out / f, d / f)
        for pid in rendered:
            shutil.copyfile(out / f"{pid}.tf", d / f"{pid}.tf")
        return [("aws:all", d)]
    def copy(label: str, src: Path) -> tuple[str, Path]:
        # valida numa cópia: a pasta de saída do harness fica intacta (o lock e o .terraform não entram nela)
        d = r["dir"] / "validate" / label.replace(":", "_")
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(src, d, ignore=shutil.ignore_patterns(".terraform", ".terraform.lock.hcl", "*.json"))
        return label, d

    if prov == "google":
        return [copy("google:all", out)]
    if prov == "azurerm":
        rep = json.loads((out / "render_report.json").read_text(encoding="utf-8"))
        if rep["layout"] == "single":
            return [copy("azurerm:" + rendered[0], out)]
        return [copy("azurerm:" + pid, out / pid) for pid in rendered]
    if prov == "oci":
        return [copy("oci:all", out)]
    return []


def validate_dir(provider: str, d: Path, base: Path) -> dict:
    pcache = plugin_cache(provider, base)
    shutil.copyfile(pcache["lock"], d / ".terraform.lock.hcl")
    home = C.tmp_dir() / "tf" / "home"
    env = sandbox_env(home, pcache["rc"])
    tf = terraform_bin()
    init = subprocess.run([tf, "init", "-backend=false", "-lockfile=readonly", "-input=false", "-no-color"],
                          cwd=d, env=env, capture_output=True, text=True, timeout=600)
    if init.returncode != 0:
        return {"ok": False, "stage": "init", "tail": init.stderr[-800:]}
    val = subprocess.run([tf, "validate", "-json", "-no-color"], cwd=d, env=env, capture_output=True, text=True,
                         timeout=600)
    try:
        js = json.loads(val.stdout)
    except ValueError:
        js = {"valid": False, "diagnostics": [{"summary": val.stdout[-300:] + val.stderr[-300:]}]}
    sel = subprocess.run([tf, "providers", "-no-color"], cwd=d, env=env, capture_output=True, text=True, timeout=120)
    pinned = f"{SRC[provider]}] {PINS[provider]}" in sel.stdout or f"{SRC[provider]}" in sel.stdout
    lockd = (d / ".terraform.lock.hcl").read_text(encoding="utf-8")
    pin_ok = f'version     = "{PINS[provider]}"' in lockd or f'version = "{PINS[provider]}"' in lockd
    shutil.rmtree(d / ".terraform", ignore_errors=True)
    return {"ok": bool(js.get("valid")) and pin_ok, "valid": js.get("valid"), "pin_ok": pin_ok, "providers_listed": pinned,
            "errors": [x.get("summary") for x in js.get("diagnostics", []) if x.get("severity") == "error"][:10],
            "warnings": len([x for x in js.get("diagnostics", []) if x.get("severity") == "warning"])}
