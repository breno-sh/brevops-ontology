"""Guarda de plano offline das fixtures das CQs: só tipos e SKUs permitidos (§10 do plano), sem rede.

  python -I -m bo.harness.plan_guard_offline $BO_REPO/cq/fixtures     (despachante -> bo.cqfix.plan_guard_offline)

Lê cada <dir>/{provider}/main.tf (python-hcl2) e <dir>/probes.yaml. Reprova (sai 1) quando:
  - um tipo (recurso ou data) não está em ALLOWED_TYPES do realizador do provedor;
  - um tipo da Classe C do §10.1 (fora da amostra salvo OK), um tipo marcado "só offline" ou de custo
    medium/high aparece num slice implantável (deployable: true no probes.yaml);
  - um atributo de SKU_RULES tem valor fora da lista ou não literal (num slice implantável);
  - há provisioner, backend/cloud, bloco provider com credencial, ou endereço fora de todo slice.
Relatório: $BO_DATA/CQFIX/plan_guard.json. A allowlist do SAFETY (deploy/safety/allowlist_skus.yaml), quando
existir, prevalece no deploy; esta guarda vale para as fixtures.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import yaml

from . import MODULE_ID, PROVIDERS, data_root, fixtures_dir, now_iso
from . import tfparse

CLASS_C = {
    "aws": [r"^aws_opensearch", r"^aws_elasticsearch", r"^aws_msk_", r"^aws_redshift", r"^aws_organizations_"],
    "google": [r"^google_filestore", r"^google_bigtable", r"^google_alloydb", r"^google_folder",
               r"^google_organization", r"^google_org_policy", r"^google_access_context_manager",
               r"^google_cloud_identity_group", r"^google_spanner_instance$"],
    "azurerm": [r"^azurerm_firewall", r"^azurerm_application_gateway", r"^azurerm_web_application_firewall",
                r"^azurerm_cdn_frontdoor", r"^azurerm_frontdoor", r"^azurerm_management_group"],
    "oci": [r"^oci_identity_domains_", r"^oci_database_db_system$"],
}
CRED_KEYS = re.compile(r"(access_key|secret_key|^token$|credentials|client_secret|private_key|fingerprint|"
                       r"user_ocid|password|client_certificate)", re.I)


def check(root: Path) -> dict:
    probes = yaml.safe_load((root / "probes.yaml").read_text(encoding="utf-8"))
    slices = {}
    for pr in probes["probes"]:
        for a in pr["slice"]:
            slices.setdefault((pr["provider"], a), []).append(pr)
    findings, counts = [], {}
    for p in PROVIDERS:
        f = root / p / "main.tf"
        if not f.is_file():
            findings.append({"provider": p, "rule": "main.tf ausente"})
            continue
        mod = importlib.import_module(f"bo.cqfix.realize.{p}")
        allowed, skus = mod.ALLOWED_TYPES, mod.SKU_RULES
        cc = [re.compile(x) for x in CLASS_C[p]]
        text = f.read_text(encoding="utf-8")
        if re.search(r"\bprovisioner\s+\"", text):
            findings.append({"provider": p, "rule": "provisioner proibido"})
        doc = tfparse.load(f)
        for t in doc["terraform"]:
            for k in ("backend", "cloud"):
                if k in t:
                    findings.append({"provider": p, "rule": f"bloco {k} proibido nas fixtures"})
        for pv in doc["provider"]:
            for _name, body in pv.items():
                for path, _v in tfparse.walk_keys(body):
                    if CRED_KEYS.search(path.split(".")[-1]):
                        findings.append({"provider": p, "rule": "credencial em bloco provider", "path": path})
        n = 0
        for b in doc["blocks"]:
            n += 1
            prs = slices.get((p, b.address))
            if not prs:
                findings.append({"provider": p, "address": b.address, "rule": "endereço fora de todo slice"})
                continue
            if len(prs) > 1:
                findings.append({"provider": p, "address": b.address, "rule": "endereço em mais de um slice"})
            deployable = all(x["deployable"] for x in prs)
            info = allowed.get(b.type_key)
            if info is None:
                findings.append({"provider": p, "address": b.address, "rule": f"tipo {b.type_key} fora da allowlist"})
                continue
            restricted = (any(r.search(b.type) for r in cc) or "só offline" in info["category"]
                          or info["cost_class"] in ("medium", "high"))
            if restricted and deployable:
                findings.append({"provider": p, "address": b.address,
                                 "rule": f"tipo restrito ({info['category']}, {info['cost_class']}) em slice implantável"})
            for (t, path), vals in skus.items():
                if t != b.type_key or not deployable:
                    continue
                for got in tfparse.get_path(b.body, path):
                    if isinstance(got, tfparse.Expr) or got not in vals:
                        findings.append({"provider": p, "address": b.address, "rule": "SKU fora da lista",
                                         "attr": path, "got": got.text if isinstance(got, tfparse.Expr) else got,
                                         "allowed": vals})
        counts[p] = n
    return {"schema": "bo.cqfix.plan_guard/1", "module": MODULE_ID, "generated_at": now_iso(), "root": str(root),
            "blocks": counts, "findings": findings, "ok": not findings}


def main(argv=None) -> int:
    argv = [a for a in (sys.argv[1:] if argv is None else argv) if a != MODULE_ID]
    root = Path(argv[0]) if argv else fixtures_dir()
    rep = check(root)
    out = data_root() / MODULE_ID / "plan_guard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    for f in rep["findings"][:40]:
        print("REPROVA", json.dumps(f, ensure_ascii=False, default=str))
    print(f"plan_guard_offline: {sum(rep['blocks'].values())} bloco(s) em {len(rep['blocks'])} provedor(es), "
          f"{len(rep['findings'])} achado(s) -> {'OK' if rep['ok'] else 'REPROVADO'}")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
