"""Compromissos do REQUIREMENTS (C24) com o GRAIN como consumidor, como casos de teste do procedimento.

Cada compromisso vira uma checagem nos mundos sintéticos (bo.grain.worlds, bo.grain.fixtures). Os que
dependem de outra camada (decisão de acesso, precedência, raciocínio OWL) ficam fora do alcance do grão, com
o módulo que decide. Fonte dos ids e das afirmações: $BO_REPO/requirements/commitments.jsonl.
"""

from __future__ import annotations

import copy
import json

from . import battery as B
from . import fixtures as F
from . import instance as I
from . import rules as R
from . import schema as S
from .common import load_jsonl, repo
from .evidence import FixtureAdapter


def _ctx():
    rs = R.load()
    W = B.all_worlds()
    cache = {}

    def dec(w, ev=None):
        if ev is None:
            if w not in cache:
                cache[w] = B.run_schema(W[w], rs)
            return cache[w]
        return B.run_schema(W[w], rs, ev)

    def occs(w, cfg):
        return I.decompose_config(W[w]["configs"][cfg], FixtureAdapter(W[w]["evidence"]),
                                  F.schema_blocks(W[w]["schema"]), rs)
    return rs, W, dec, occs


def _rows(o):
    return I.canonical_rows(o)


def checks() -> dict:
    rs, W, dec, occs = _ctx()
    out = {}

    def put(cid, ok, how):
        out[cid] = {"ok": bool(ok), "how": how}

    d = dec("bucket").decisions
    bcfg = F.bucket_configs()
    put("CMT-BKT-P01", all(d[c].grain == "FACET" and d[c].owner["targets"] == ["a_bucket"] for c in
                           ("a_bucket.versioning", "a_bucket_versioning"))
        and len({json.dumps(_rows(I.decompose_config(c, FixtureAdapter(W["bucket"]["evidence"]),
                                                     F.schema_blocks(W["bucket"]["schema"]), rs)))
                 for c in bcfg.values()}) == 1,
        "faceta de versionamento embutida e separada: mesmo dono, mesmas ocorrências nas 4 embalagens")
    n = dec("namespace").decisions
    put("CMT-BKT-P02", n["e_account.versioning"].grain == "FACET" and
        n["e_account.versioning"].scope == {"kind": "container", "target": "e_account"},
        "faceta do namespace com alcance = contêineres do namespace, dono = namespace")
    put("CMT-BKT-P03", n["e_container"].grain == "COMPONENT" and n["e_container"].parent == "e_account" and
        n["e_container"].lifecycle["kind"] == "parent", "contêiner é componente do namespace (G2)")
    res = dec("namespace")
    units, _ = S.to_c19(res)
    bad = copy.deepcopy([u for u in units if u["unit_id"].endswith("e_account.versioning")])
    bad[0]["owner"] = {"kind": "parent", "ref": "CU-provider_e-e_container"}
    put("CMT-BKT-N03", bool(S.verify_units(bad, res)) and not S.verify_units(units, res),
        "unidade declarada com dono divergente da evidência é rejeitada por verify_units")
    o = [x for x in occs("namespace", "unresolved") if x.label == "retention"]
    put("CMT-BKT-U02", len(o) == 1 and o[0].grain == "UNKNOWN" and "owner" in o[0].missing,
        "configuração separada com referência ao contêiner não resolvida: UNKNOWN com owner")
    put("CMT-LC-U01", n["e_orphan_setting"].grain == "UNKNOWN" and
        n["e_orphan_setting"].missing == ["lifecycle_controller"], "sem controlador de ciclo de vida: UNKNOWN")
    cnt = {}
    for cfg in ("inline_1", "inline_2", "separate_1", "separate_2"):
        oc = occs("nic", cfg)
        cnt[cfg] = (sum(o.label in ("compute instance", "network interface") for o in oc),
                    sum(o.label == "interface attachment" and o.grain == "BINDING" for o in oc))
    put("CMT-NIC-P01", cnt["inline_2"] == cnt["separate_2"] == (3, 2), f"contagens {cnt}")
    put("CMT-NIC-P02", cnt["inline_1"] == cnt["separate_1"] == (2, 1), f"contagens {cnt}")
    put("CMT-NIC-P03", all(set(_rows(occs("nic", f"{p}_1"))) < set(_rows(occs("nic", f"{p}_2")))
                           for p in ("inline", "separate")), "1 → 2 interfaces só acrescenta")
    put("CMT-NIC-P04", all(_rows(occs("nic", f"inline_{k}")) == _rows(occs("nic", f"separate_{k}")) for k in (1, 2)),
        "embutida == separada (sem a camada Terraform)")
    put("CMT-NIC-P05", _rows(occs("nic", "inline_2")) == _rows(occs("nic", "inline_2_reordered")),
        "blocos reordenados: mesmas identidades de ocorrência")
    put("CMT-NIC-N03", sum(o.label == "compute instance" for o in occs("nic", "inline_2")) == 1,
        "interface não conta como instância")
    o = [x for x in occs("nic", "separate_unresolved") if x.label == "interface attachment"]
    put("CMT-NIC-U02", len(o) == 1 and o[0].grain == "UNKNOWN", "referência simbólica não vira anexação")
    f = dec("firewall").decisions
    put("CMT-FW-P01", f["c_rule_set.rule"].grain == f["c_rule"].grain == "COMPONENT" and
        len({json.dumps(_rows(occs("firewall", k))) for k in ("inline", "separate", "inline_reordered",
                                                               "separate_reordered")}) == 1,
        "regra embutida (anônima, por conteúdo) == regra separada; reordenar não muda")
    put("CMT-FW-P06", _rows(occs("firewall", "inline")) == _rows(occs("firewall", "inline_reordered")),
        "parte do grão: a ordem textual não muda as unidades (a decisão de acesso é do PILOT-NET)")
    a = dec("iam").decisions["d_assignment"]
    put("CMT-IAM-P01", a.grain == "BINDING" and set(a.endpoints) == {"scope", "permission_set", "principal"},
        "atribuição = vínculo de três pontas, distinto delas")
    put("CMT-LC-N01", all(dec("iam").decisions[c].lifecycle["kind"] == "self" for c in
                          ("d_principal", "d_role", "d_project")),
        "as pontas do vínculo têm ciclo de vida próprio: apagar o vínculo não as encerra")
    put("CMT-LC-P01", n["e_container"].lifecycle == {"kind": "parent", "target": "e_account"},
        "controlador do componente = o pai (o fim desce do pai, ONTPAT P4)")
    db = dec("db").decisions
    put("CMT-DB-P03", db["f_param_group"].grain == "ENTITY", "conjunto de parâmetros compartilhado é entidade")
    put("CMT-DB-P04", db["f_db_instance.backup"].grain == "FACET" and db["f_snapshot"].grain == "ENTITY",
        "retenção = faceta; cópia manual = entidade com ciclo de vida próprio")
    lb_e, lb_s = occs("lb", "embedded"), occs("lb", "separate")
    root = [o.occ_id for o in lb_e if o.label == "load balancer"]

    def below(oc, r):
        kids, frontier = set(), {r}
        while frontier:
            nxt = {o.occ_id for o in oc if o.parent in frontier} | \
                  {v for o in oc if o.occ_id in (kids | {r}) for v in o.refs.values() if v}
            nxt -= kids | {r}
            kids |= nxt
            frontier = nxt
        return kids
    put("CMT-LB-P02", len(root) == 1 and len(below(lb_e, root[0])) == 9 == len(below(lb_s, root[0])),
        "nove unidades abaixo do balanceador (frontend, 2 listeners, 2 regras, 2 pools, sonda, certificado)")
    put("CMT-LB-P03", _rows(lb_e) == _rows(lb_s) and all(o.refs.get("pool") for o in lb_e if o.label == "routing rule"),
        "embutido == separado, inclusive as referências regra → pool (por nome no embutido)")
    return out


OUT_OF_SCOPE = {
    "CMT-BKT-N01": "AXIOMS/OWL (disjunção de tipos)", "CMT-BKT-N02": "PILOT-STO-ORACLE (acesso efetivo)",
    "CMT-BKT-U01": "PILOT-STO-ORACLE (acesso efetivo)", "CMT-NIC-N01": "AXIOMS/OWL", "CMT-NIC-N02": "AXIOMS/OWL",
    "CMT-NIC-U01": "ABOX-LIFT (leitura completa)", "CMT-FW-P02": "PILOT-NET-ORACLE", "CMT-FW-P03": "PILOT-NET-ORACLE",
    "CMT-FW-P04": "PILOT-NET-ORACLE", "CMT-FW-P05": "PILOT-NET-ORACLE", "CMT-FW-N01": "TRANSLATOR",
    "CMT-FW-N02": "AXIOMS/OWL", "CMT-FW-N03": "PILOT-NET-ORACLE", "CMT-FW-U01": "PILOT-NET-ORACLE",
    "CMT-FW-U02": "PILOT-NET-ORACLE", "CMT-FW-U03": "PILOT-NET-ORACLE", "CMT-IAM-P02": "DOMAIN-CONTRACTS (unidade de decisão)",
    "CMT-IAM-P03": "DOMAIN-CONTRACTS", "CMT-IAM-P04": "DOMAIN-CONTRACTS", "CMT-IAM-P05": "DOMAIN-CONTRACTS",
    "CMT-IAM-P06": "DOMAIN-CONTRACTS", "CMT-IAM-N01": "TRANSLATOR", "CMT-IAM-N02": "DOMAIN-CONTRACTS",
    "CMT-IAM-N03": "AXIOMS/OWL", "CMT-IAM-N04": "DOMAIN-CONTRACTS", "CMT-IAM-U01": "DOMAIN-CONTRACTS",
    "CMT-IAM-U02": "DOMAIN-CONTRACTS", "CMT-IAM-U03": "DOMAIN-CONTRACTS", "CMT-LB-P01": "DOMAIN-CONTRACTS",
"CMT-LB-P04": "ONTPAT/AXIOMS", "CMT-LB-N01": "ONTPAT",
    "CMT-LB-N02": "SHACL", "CMT-LB-N03": "AXIOMS", "CMT-LB-U01": "ABOX-LIFT", "CMT-LB-U02": "ABOX-LIFT",
    "CMT-DB-P01": "DOMAIN-CONTRACTS", "CMT-DB-P02": "AXIOMS", "CMT-DB-N01": "AXIOMS/OWL", "CMT-DB-N02": "AXIOMS",
    "CMT-DB-N03": "AXIOMS", "CMT-DB-U01": "ABOX-LIFT", "CMT-DB-U02": "ABOX-LIFT",
}


def run() -> dict:
    p = repo() / "requirements" / "commitments.jsonl"
    cmts = [c for c in load_jsonl(p) if "GRAIN" in c.get("consumers", [])]
    res = checks()
    rows = []
    for c in cmts:
        k = c["commitment_id"]
        if k in res and res[k]["ok"] is not None:
            rows.append({"commitment_id": k, "status": "REPRODUCED" if res[k]["ok"] else "FAILED",
                         "how": res[k]["how"]})
        else:
            rows.append({"commitment_id": k, "status": "OUT_OF_SCOPE",
                         "decided_by": OUT_OF_SCOPE.get(k, res.get(k, {}).get("how", "não mapeado"))})
    unknown_ids = sorted(set(res) - {c["commitment_id"] for c in cmts})
    return {"schema": "bo.grain.commitment_suite/1", "source": "$BO_REPO/requirements/commitments.jsonl",
            "n_commitments": len(cmts), "reproduced": sum(r["status"] == "REPRODUCED" for r in rows),
            "failed": sum(r["status"] == "FAILED" for r in rows),
            "out_of_scope": sum(r["status"] == "OUT_OF_SCOPE" for r in rows),
            "checks_without_commitment": unknown_ids, "rows": rows}
