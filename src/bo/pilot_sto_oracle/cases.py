"""Casos obrigatórios e famílias de tradução do oráculo STO, com a resposta esperada ANALÍTICA.

A resposta de cada fixture é escrita aqui a partir dos parâmetros (fórmula fechada, tabela de decisão),
sem chamar o avaliador; o build confere avaliador == resposta analítica antes de gravar ou selar. Duas
contas independentes: se divergirem, o build para.

Partições: 'calib' usa parâmetros fixos e nomes legíveis (reprodutível, vai para o git); 'heldout' sorteia
nomes, dias, chaves e variantes com o gerador do sistema operacional (nada reprodutível a partir do git) e
só existe cifrada em $BO_DATA/PILOT-STO-ORACLE/sealed/.
"""
from __future__ import annotations

import copy
import secrets
import string

from .realize import PROVIDERS, SHORT, aws_acl, aws_public, container, expire_current, finalize, merge, noncurrent_rule, tf

PIN = {"aws": "6.71.0", "google": "8.9.0", "azurerm": "5.12.0", "oci": "9.11.0"}
POL = ("positive", "negative", "unknown")

MANDATORY = {
    "MC-VER": {"title": "versionamento efetivo: ligado, suspenso, nunca ligado, transição recusada",
               "commitments": ["CMT-CFG-P02", "CMT-ID-P01"], "requirements": ["REQ-STO-01"], "answers": ["F1", "F5"]},
    "MC-DEC-PACK": {"title": "decomposição invariante à embalagem (bloco embutido × recurso separado × atributo)",
                    "commitments": ["CMT-BKT-P01", "CMT-BKT-U02"], "requirements": ["REQ-ENT-01", "REQ-STO-01"], "answers": ["F1"]},
    "MC-DEC-SCOPE": {"title": "dono × alcance efetivo; conta × contêiner no Azure; nível de conta na AWS; namespace OCI",
                     "commitments": ["CMT-BKT-P02", "CMT-BKT-P03", "CMT-BKT-N01", "CMT-BKT-N03", "CMT-LC-U01"],
                     "requirements": ["REQ-REL-01", "REQ-STO-01"], "answers": ["F1"]},
    "MC-LC-CUR": {"title": "ciclo de vida da versão corrente numa linha do tempo sintética, com o dia de fronteira",
                  "commitments": ["CMT-LOSS-P01"], "requirements": ["REQ-STO-01"], "answers": ["F5", "F6"]},
    "MC-LC-NONCUR": {"title": "exclusão de versões não correntes: relógio (desde não corrente × desde criação) e retenção por contagem",
                     "commitments": ["CMT-LOSS-N02"], "requirements": ["REQ-STO-01"], "answers": ["F5", "F6"]},
    "MC-LC-FILTER": {"title": "aplicabilidade da regra: estado, prefixo, contêiner no prefixo (Azure), exclusão (OCI)",
                     "commitments": [], "requirements": ["REQ-STO-01"], "answers": ["F5"]},
    "MC-PUB-LEVEL": {"title": "acesso público efetivo entre níveis (conta, contêiner, política, ACL, propriedade, organização)",
                     "commitments": ["CMT-BKT-N02", "CMT-BKT-U01"], "requirements": ["REQ-REL-01", "REQ-ABS-01"], "answers": ["F1", "S10"]},
    "MC-PUB-GRAN": {"title": "granularidade do acesso público: ler × listar × autenticado qualquer",
                    "commitments": [], "requirements": ["REQ-STO-01"], "answers": ["F5"]},
}
FAMILIES = {
    "T1-VERSIONED": "versionamento ligado com sobrescrita e exclusão; vizinho na mesma conta (Azure)",
    "T2-PUBLIC-READ": "leitura anônima sem listagem",
    "T3-EXPIRE": "expiração da versão corrente com o dia de fronteira (>= × >)",
    "T4-NONCURRENT": "exclusão de versões não correntes com relógios diferentes",
}


def _tok(n=6):
    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(n))


class Gen:
    def __init__(self, split):
        assert split in ("calib", "heldout")
        self.split = split
        self.fixtures, self.entries = [], []
        self._n = {}
        self._rnd = secrets.SystemRandom() if split == "heldout" else None

    # parâmetros: fixos na calibração, sorteados nas retidas
    def pick(self, calib, lo, hi):
        return calib if self.split == "calib" else self._rnd.randint(lo, hi)

    def choice(self, calib, options):
        return calib if self.split == "calib" else self._rnd.choice(options)

    def name(self, base):
        return base if self.split == "calib" else f"{base}_{_tok(5)}"

    def key(self, base):
        return base if self.split == "calib" else f"{_tok(4)}/{base}"

    def fid(self, p, mc, pol):
        if self.split == "heldout":
            return "FX-STO-H-" + secrets.token_hex(5).upper()
        k = (p, mc, pol)
        self._n[k] = self._n.get(k, 0) + 1
        return f"FX-STO-{SHORT[p]}-{mc[3:]}-{pol[0].upper()}{self._n[k]:02d}"

    def eid(self, a, b, fam, var):
        if self.split == "heldout":
            return "DX-H-" + secrets.token_hex(5).upper()
        k = (a, b, fam, var)
        self._n[k] = self._n.get(k, 0) + 1
        return f"DX-{SHORT[a]}-{SHORT[b]}-{fam.split('-')[0]}-{var}-{self._n[k]:02d}"

    def add(self, p, mc, pol, summary, resources, checks, *, context=None, timeline=None, read=None, invariant_group=None):
        fx = make_fx(p, self.fid(p, mc, pol), summary, resources, context=context, timeline=timeline, read=read)
        fx["split"], fx["case"], fx["polarity"] = self.split, mc, pol
        if invariant_group:
            fx["invariant_group"] = invariant_group if self.split == "calib" else f"{invariant_group}-{_tok(4)}"
        self.fixtures.append({"fixture": fx, "checks": checks, **({"edge_v4": True} if getattr(self, "_edge", False) else {})})
        return fx


def make_fx(p, fid, summary, resources, *, context=None, timeline=None, read=None):
    res = finalize(p, copy.deepcopy(resources))
    fx = {"schema": "bo.pilot.sto.fixture/1", "fixture_id": fid, "provider": p, "provider_version": PIN[p],
          "summary": summary, "terraform": tf(p, res, extra_vars=_vars_in(res)), "context": context or {},
          "read": read or {"completeness": "complete", "not_read": [], "withheld": []}}
    if timeline:
        fx["timeline"] = timeline
    return fx


def _vars_in(res):
    import json
    import re
    return sorted(set(re.findall(r"\$\{var\.([a-z_]+)\}", json.dumps(res))))


def tl(container_addr, eval_day, events):
    return {"container": container_addr, "eval_day": eval_day,
            "events": sorted(events, key=lambda e: (e["day"], 0 if e["op"] == "set_versioning" else 1))}


def put(day, key):
    return {"day": day, "op": "put", "key": key}


def unk(code):
    return {"unknown": code}


def partial(*items):
    return {"completeness": "partial", "not_read": [{"of": o, "what": w} for o, w in items], "withheld": []}


def acct_attrs():
    return {}


def bucket(p, g, n, **kw):
    """contêiner com a conta Azure criada junto (salvo account_ref)."""
    if p == "azurerm" and "account_ref" not in kw:
        kw.setdefault("account_attrs", {})
    return container(p, n, **kw)


# ======================================================================== casos de um provedor
def mc_ver(g):
    seqs = {
        "aws": [(["Enabled", "Suspended"], "SUSPENDED"), (["Enabled", "Suspended", "Enabled"], "ENABLED"),
                (["Disabled"], "DISABLED"), (["Suspended"], "SUSPENDED")],
        "google": [([True, False], "SUSPENDED"), ([True], "ENABLED"), ([False], "DISABLED"), ([True, False, True], "ENABLED")],
        "azurerm": [([True, False], "SUSPENDED"), ([True], "ENABLED"), ([False], "DISABLED")],
        "oci": [(["Enabled", "Suspended"], "SUSPENDED"), (["Disabled", "Enabled"], "ENABLED"), (["Disabled"], "DISABLED"),
                (["Enabled", "Suspended", "Enabled"], "ENABLED")],
    }
    invalid = {"aws": ["Enabled", "Disabled"], "oci": ["Enabled", "Disabled"]}
    for p in PROVIDERS:
        n = g.name("data")
        seq, want = g.choice(seqs[p][0], seqs[p])
        step = g.pick(10, 1, 40)
        r, c = bucket(p, g, n, versioning=seq[-1])
        evs = [{"day": i * step, "op": "set_versioning", "value": v} for i, v in enumerate(seq)]
        T = len(seq) * step
        g.add(p, "MC-VER", "positive", f"versionamento {seq} → {want}", r, [{"kind": "versioning", "container": c, "expect": want}],
              timeline=tl(c, T, evs))
        # negativo: 'suspenso = desligado' e transição que a API recusa
        r2, c2 = bucket(p, g, n, versioning=seqs[p][0][0][-1])
        evs2 = [{"day": i * step, "op": "set_versioning", "value": v} for i, v in enumerate(seqs[p][0][0])]
        g.add(p, "MC-VER", "negative", "alegação 'suspenso = nunca versionado' tem de ser rejeitada", r2,
              [{"kind": "versioning", "container": c2, "expect": "SUSPENDED"},
               {"kind": "claim", "claim": {"about": "versioning", "container": c2, "value": "DISABLED"},
                "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}],
              timeline=tl(c2, 2 * step, evs2))
        if p in invalid:
            seq3 = invalid[p]
            r3, c3 = bucket(p, g, n, versioning=seq3[-1])
            g.add(p, "MC-VER", "negative", "voltar a 'Disabled' depois de habilitado: a API recusa", r3,
                  [{"kind": "versioning", "container": c3, "expect": "INVALID_TRANSITION"},
                   {"kind": "claim", "claim": {"about": "versioning", "container": c3, "value": "DISABLED"},
                    "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}],
                  timeline=tl(c3, step, [{"day": i * step, "op": "set_versioning", "value": v} for i, v in enumerate(seq3)]))
        # desconhecido
        if p == "aws":
            r4, c4 = container(p, n)
            r4["aws_s3_bucket_versioning"] = {n: {"bucket": "${var.bucket_id}", "versioning_configuration": [{"status": "Enabled"}]}}
            g.add(p, "MC-VER", "unknown", "versionamento separado com referência não resolvida", r4,
                  [{"kind": "versioning", "container": c4, "expect": unk("MISSING_EVIDENCE")}])
            r5, c5 = container(p, n, versioning=True, aws_form="inline")
            r5["aws_s3_bucket_versioning"] = {n: {"bucket": f"${{{c5}.id}}", "versioning_configuration": [{"status": "Suspended"}]}}
            g.add(p, "MC-VER", "unknown", "versionamento embutido e separado no mesmo contêiner", r5,
                  [{"kind": "versioning", "container": c5, "expect": unk("UNRESOLVED")}])
            r6, c6 = container(p, n, objlock=True)
            g.add(p, "MC-VER", "positive", "Object Lock liga o versionamento", r6, [{"kind": "versioning", "container": c6, "expect": "ENABLED"}])
        elif p == "azurerm":
            r4, c4 = container(p, n, account_ref="${var.storage_account_id}")
            g.add(p, "MC-VER", "unknown", "contêiner cuja conta não foi lida", r4,
                  [{"kind": "versioning", "container": c4, "expect": unk("INCOMPLETE_READ")}])
        else:
            r4, c4 = bucket(p, g, n, versioning=True)
            g.add(p, "MC-VER", "unknown", "versionamento do contêiner não lido", r4,
                  [{"kind": "versioning", "container": c4, "expect": unk("INCOMPLETE_READ")}], read=partial((c4, "versioning")))


def _facet(owner, scope, lc="parent", missing=()):
    return {"kind": "FACET", "owner": owner, "effective_scope": scope, "lifecycle_controller": lc, "missing_evidence": list(missing)}


def mc_dec_pack(g):
    n = g.name("data")
    # AWS: embutido × separado
    grp = "INV-AWS-VERSIONING"
    for form in ("inline", "separate"):
        r, c = container("aws", n, versioning=True, aws_form=form)
        cu = f"container:{c}"
        g.add("aws", "MC-DEC-PACK", "positive", f"versionamento {form}", r,
              [{"kind": "decomposition", "unit": cu, "expect": {"kind": "ENTITY", "owner": "self", "missing_evidence": []}},
               {"kind": "decomposition", "unit": f"setting:versioning@{cu}", "expect": _facet(cu, [cu])},
               {"kind": "versioning", "container": c, "expect": "ENABLED"}], invariant_group=grp)
    for p in ("google", "oci"):
        r, c = bucket(p, g, n, versioning=True)
        cu = f"container:{c}"
        g.add(p, "MC-DEC-PACK", "positive", "versionamento embutido/atributo do contêiner", r,
              [{"kind": "decomposition", "unit": cu, "expect": {"kind": "ENTITY", "owner": "self", "missing_evidence": []}},
               {"kind": "decomposition", "unit": f"setting:versioning@{cu}", "expect": _facet(cu, [cu])}])
    a = g.name("acct")
    r, c = container("azurerm", n, versioning=True, account=a, account_attrs={})
    nu = f"namespace:azurerm_storage_account.{a}"
    g.add("azurerm", "MC-DEC-PACK", "positive", "versionamento na conta: faceta da conta, não do contêiner", r,
          [{"kind": "decomposition", "unit": nu, "expect": {"kind": "ENTITY"}},
           {"kind": "decomposition", "unit": f"container:{c}", "expect": {"kind": "ENTITY", "owner": "self", "lifecycle_controller": "self",
                                                                          "namespace": nu, "missing_evidence": []}},
           {"kind": "decomposition", "unit": f"setting:versioning@{nu}", "expect": _facet(nu, [f"container:{c}"])}])
    # negativos
    r, c = container("aws", n, versioning=True)
    cu = f"container:{c}"
    g.add("aws", "MC-DEC-PACK", "negative", "recurso separado de versionamento alegado como entidade", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:versioning@{cu}", "value": {"kind": "ENTITY"}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    r, c = bucket("google", g, n, versioning=True)
    g.add("google", "MC-DEC-PACK", "negative", "bloco embutido alegado com dono diferente do contêiner", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:versioning@container:{c}", "value": {"owner": "self"}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    r, c = container("azurerm", n, versioning=True, account=a, account_attrs={})
    g.add("azurerm", "MC-DEC-PACK", "negative", "versionamento da conta registrado como faceta de um contêiner (CMT-BKT-N03)", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:versioning@container:{c}", "value": {"kind": "FACET"}},
            "expect": {"verdict": "REJECT", "code": "NO_SUCH_UNIT"}}])
    r, c = bucket("oci", g, n, versioning=True)
    g.add("oci", "MC-DEC-PACK", "negative", "contêiner OCI alegado componente do namespace", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"container:{c}", "value": {"kind": "COMPONENT"}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    # desconhecidos
    r, c = container("aws", n)
    vn = g.name("ver")
    r["aws_s3_bucket_versioning"] = {vn: {"bucket": "${var.bucket_id}", "versioning_configuration": [{"status": "Enabled"}]}}
    g.add("aws", "MC-DEC-PACK", "unknown", "versionamento separado sem referência resolvida (CMT-BKT-U02)", r,
          [{"kind": "decomposition", "unit": f"setting:versioning@UNRESOLVED:aws_s3_bucket_versioning.{vn}",
            "expect": {"kind": "UNKNOWN", "owner": "UNKNOWN", "missing_evidence": ["owner"]}},
           {"kind": "versioning", "container": c, "expect": unk("MISSING_EVIDENCE")}])
    r, c = bucket("google", g, n)
    mn = g.name("grant")
    r["google_storage_bucket_iam_member"] = {mn: {"bucket": "${var.bucket_name}", "role": "roles/storage.objectViewer", "member": "allUsers"}}
    g.add("google", "MC-DEC-PACK", "unknown", "concessão IAM com contêiner não resolvido", r,
          [{"kind": "decomposition", "unit": f"setting:access_grant@UNRESOLVED:google_storage_bucket_iam_member.{mn}",
            "expect": {"kind": "UNKNOWN", "missing_evidence": ["owner"]}},
           {"kind": "public", "container": c, "axis": "anonymous_read", "expect": unk("MISSING_EVIDENCE")}])
    r, c = container("azurerm", n, versioning=True, account_ref="${var.storage_account_id}")
    g.add("azurerm", "MC-DEC-PACK", "unknown", "contêiner cuja conta não foi lida: namespace e configuração da conta UNKNOWN", r,
          [{"kind": "decomposition", "unit": f"container:{c}",
            "expect": {"kind": "ENTITY", "namespace": "UNKNOWN", "missing_evidence": ["namespace"]}},
           {"kind": "versioning", "container": c, "expect": unk("INCOMPLETE_READ")}])
    r, c = container("azurerm", n, versioning=True, account=a, account_attrs={})
    g.add("azurerm", "MC-DEC-PACK", "negative", "contêiner Azure alegado componente da conta: a evidência dá controlador self", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"container:{c}", "value": {"kind": "COMPONENT"}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])


def mc_dec_scope(g):
    a, n1, n2 = g.name("acct"), g.name("logs"), g.name("media")
    r1, c1 = container("azurerm", n1, versioning=True, account=a, account_attrs={})
    r2, c2 = container("azurerm", n2, account=a)
    nu = f"namespace:azurerm_storage_account.{a}"
    scope = sorted([f"container:{c1}", f"container:{c2}"])
    pref = g.key("archive/")
    lc = expire_current("azurerm", n1, 30, prefix=pref, acct=a, cname=n1.replace("_", "-"))
    g.add("azurerm", "MC-DEC-SCOPE", "positive", "conta com dois contêineres: versionamento alcança os dois; política com prefixo só um",
          merge(r1, r2, lc),
          [{"kind": "decomposition", "unit": f"setting:versioning@{nu}", "expect": _facet(nu, scope)},
           {"kind": "decomposition", "unit": f"setting:lifecycle@{nu}", "expect": _facet(nu, [f"container:{c1}"])},
           {"kind": "versioning", "container": c2, "expect": "ENABLED"}])
    g.add("azurerm", "MC-DEC-SCOPE", "negative", "indivíduo conta e contêiner ao mesmo tempo (CMT-BKT-N01)", merge(r1, r2),
          [{"kind": "claim", "claim": {"about": "disjoint_kinds", "kinds": ["storage_namespace", "object_container"]},
            "expect": {"verdict": "REJECT", "code": "INCONSISTENT"}}])
    g.add("azurerm", "MC-DEC-SCOPE", "negative", "versionamento da conta alegado faceta do primeiro contêiner", merge(r1, r2),
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:versioning@container:{c1}", "value": {"kind": "FACET"}},
            "expect": {"verdict": "REJECT", "code": "NO_SUCH_UNIT"}},
           {"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:versioning@{nu}", "value": {"effective_scope": [f"container:{c1}"]}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    r3, c3 = container("azurerm", n2, account_ref="${var.storage_account_id}")
    g.add("azurerm", "MC-DEC-SCOPE", "unknown", "segundo contêiner de conta não lida: fora do alcance conhecido", merge(r1, r3),
          [{"kind": "decomposition", "unit": f"setting:versioning@{nu}", "expect": _facet(nu, [f"container:{c1}"])},
           {"kind": "versioning", "container": c3, "expect": unk("INCOMPLETE_READ")}])
    # AWS: bloqueio de nível de conta
    b1, b2 = g.name("logs"), g.name("media")
    ra, ca = container("aws", b1)
    rb, cb = container("aws", b2)
    acc = {"aws_s3_account_public_access_block": {"this": {"block_public_acls": True, "block_public_policy": True,
                                                           "ignore_public_acls": True, "restrict_public_buckets": True}}}
    known = sorted([f"container:{ca}", f"container:{cb}"])
    g.add("aws", "MC-DEC-SCOPE", "positive", "bloqueio de conta alcança todo contêiner da conta", merge(ra, rb, acc),
          [{"kind": "decomposition", "unit": "setting:public_access_block@account:context",
            "expect": {"kind": "FACET", "owner": "account:context", "effective_scope": {"all_in": "account:context", "known": known},
                       "lifecycle_controller": "external"}}])
    g.add("aws", "MC-DEC-SCOPE", "negative", "bloqueio de conta alegado faceta de um contêiner", merge(ra, rb, acc),
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:public_access_block@container:{ca}", "value": {"kind": "FACET"}},
            "expect": {"verdict": "REJECT", "code": "NO_SUCH_UNIT"}}])
    # Google: configuração embutida no contêiner tem alcance do próprio contêiner
    nb = g.name("logs")
    r, c = bucket("google", g, nb)
    r = merge(r, expire_current("google", nb, 30))
    cu = f"container:{c}"
    g.add("google", "MC-DEC-SCOPE", "positive", "ciclo de vida do contêiner: faceta com alcance próprio", r,
          [{"kind": "decomposition", "unit": f"setting:lifecycle@{cu}", "expect": _facet(cu, [cu])}])
    # OCI: dono e controlador da política separada estão em disputa (doc self x spec parent): UNKNOWN, sem escolha
    r, c = bucket("oci", g, nb)
    r = merge(r, expire_current("oci", nb, 30))
    cu = f"container:{c}"
    pol = f"oci_objectstorage_object_lifecycle_policy.{nb}"
    g.add("oci", "MC-DEC-SCOPE", "unknown", "política de ciclo de vida separada: dono, ciclo de vida e alcance em disputa spec x doc", r,
          [{"kind": "decomposition", "unit": f"setting:lifecycle@DISPUTED:{pol}",
            "expect": {"kind": "UNKNOWN", "owner": "UNKNOWN", "lifecycle_controller": "UNKNOWN", "effective_scope": "UNKNOWN",
                       "disputed": ["effective_scope", "lifecycle_controller", "owner"]}}])
    g.add("oci", "MC-DEC-SCOPE", "negative", "disputa resolvida por escolha (faceta do contêiner) tem de ser rejeitada", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:lifecycle@{cu}", "value": {"kind": "FACET"}},
            "expect": {"verdict": "REJECT", "code": "NO_SUCH_UNIT"}}])
    nb = g.name("logs")
    r, c = bucket("oci", g, nb)
    r["oci_objectstorage_namespace_metadata"] = {"this": {"namespace": "${var.namespace}",
                                                          "default_s3compartment_id": "${var.compartment_id}"}}
    g.add("oci", "MC-DEC-SCOPE", "unknown", "metadados do namespace: dono, alcance e ciclo de vida sem evidência", r,
          [{"kind": "decomposition", "unit": "setting:namespace_defaults@namespace:context",
            "expect": {"kind": "UNKNOWN", "owner": "UNKNOWN", "effective_scope": "UNKNOWN",
                       "missing_evidence": ["owner", "effective_scope", "lifecycle_controller"]}}])
    g.add("oci", "MC-DEC-SCOPE", "negative", "metadados do namespace alegados faceta do contêiner", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": "setting:namespace_defaults@namespace:context",
                                       "value": {"kind": "FACET"}}, "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])


def mc_lc_cur(g):
    for p in PROVIDERS:
        E = g.pick(30, 5, 90)
        T = E + g.pick(10, 2, 30)
        n = g.name("data")
        ka, kb, kc = g.key("old.bin"), g.key("edge.bin"), g.key("young.bin")
        evs = [put(0, ka), put(T - E, kb), put(T - E + 1, kc)]
        extra = {"account": g.name("acct")} if p == "azurerm" else {}
        r, c = bucket(p, g, n, **extra)
        lc = expire_current(p, n, E, acct=extra.get("account"), cname=n.replace("_", "-"))
        g.add(p, "MC-LC-CUR", "positive", f"expira a corrente com idade >= {E} (não versionado); fronteira no dia {T}", merge(r, lc),
              [{"kind": "version_state", "version": f"{ka}#1", "expect": "DELETED"},
               {"kind": "version_state", "version": f"{kb}#1", "expect": "DELETED"},
               {"kind": "version_state", "version": f"{kc}#1", "expect": "CURRENT"}], timeline=tl(c, T, evs))
        # versionado: a corrente vira não corrente (OCI: sem evidência)
        rv, cv = bucket(p, g, n, versioning=True, **extra)
        lcv = expire_current(p, n, E, acct=extra.get("account"), cname=n.replace("_", "-"))
        if p == "oci":
            g.add(p, "MC-LC-CUR", "unknown", "DELETE na corrente em contêiner versionado: doc fixada não decide", merge(rv, lcv),
                  [{"kind": "key_unknown", "key": ka, "expect": unk("MISSING_EVIDENCE")},
                   {"kind": "version_state", "version": f"{kc}#1", "expect": "CURRENT"}], timeline=tl(cv, T, evs))
        else:
            g.add(p, "MC-LC-CUR", "positive", "versionado: expirar a corrente a torna não corrente", merge(rv, lcv),
                  [{"kind": "version_state", "version": f"{ka}#1", "expect": "NONCURRENT"},
                   {"kind": "version_state", "version": f"{kc}#1", "expect": "CURRENT"}], timeline=tl(cv, T, evs))
        # negativo: fronteira (Azure '>' copiado literalmente; demais: alegar que o objeto da fronteira sobrevive)
        if p == "azurerm":
            lit = expire_current(p, n, E + 1, acct=extra.get("account"), cname=n.replace("_", "-"))
            g.add(p, "MC-LC-CUR", "negative", f"limite copiado literalmente (> {E}): o objeto da fronteira não é apagado", merge(r, lit),
                  [{"kind": "version_state", "version": f"{kb}#1", "expect": "CURRENT"},
                   {"kind": "claim", "claim": {"about": "version_state", "key": kb, "version": f"{kb}#1", "value": "DELETED"},
                    "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], timeline=tl(c, T, evs))
        else:
            g.add(p, "MC-LC-CUR", "negative", "alegação de que o objeto com idade igual ao limite sobrevive", merge(r, lc),
                  [{"kind": "claim", "claim": {"about": "version_state", "key": kb, "version": f"{kb}#1", "value": "CURRENT"},
                    "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], timeline=tl(c, T, evs))
        # desconhecido: ciclo de vida não lido
        if p == "azurerm":
            acct_addr = f"azurerm_storage_account.{extra['account']}"
            g.add(p, "MC-LC-CUR", "unknown", "política de gestão da conta não lida", merge(r, lc),
                  [{"kind": "timeline", "expect": unk("INCOMPLETE_READ")}], timeline=tl(c, T, evs), read=partial((acct_addr, "management_policy")))
        elif p != "oci":
            g.add(p, "MC-LC-CUR", "unknown", "ciclo de vida do contêiner não lido", merge(r, lc),
                  [{"kind": "timeline", "expect": unk("INCOMPLETE_READ")}], timeline=tl(c, T, evs), read=partial((c, "lifecycle")))


def t4_events(E, keys):
    """Linha do tempo T4 (ver docstring do módulo): T = E + 5; E >= 27."""
    T = E + 5
    x, y, z, w, v = keys
    return T, [put(0, x), put(2, x), put(0, y), put(T - 15, y), put(T - 25, z), put(T - 5, z),
               put(T - (E - 1), w), put(T - (E - 1) + 2, w), put(T - E, v), put(T - E + 2, v)]


CLOCK = {"aws": "noncurrent", "google": "noncurrent", "azurerm": "creation", "oci": "creation"}


def t4_expect(clock, keys):
    x, y, z, w, v = keys
    dead = {x} if clock == "noncurrent" else {x, y, v}
    return {f"{k}#1": ("DELETED" if k in dead else "NONCURRENT") for k in keys}


def mc_lc_noncur(g):
    for p in PROVIDERS:
        E = g.pick(30, 27, 60)
        keys = tuple(g.key(b) for b in ("x.log", "y.log", "z.log", "w.log", "v.log"))
        T, evs = t4_events(E, keys)
        n = g.name("data")
        extra = {"account": g.name("acct")} if p == "azurerm" else {}
        r, c = bucket(p, g, n, versioning=True, **extra)
        lc = noncurrent_rule(p, n, E, acct=extra.get("account"))
        exp = t4_expect(CLOCK[p], keys)
        g.add(p, "MC-LC-NONCUR", "positive", f"não correntes com idade mínima {E} no relógio {CLOCK[p]}", merge(r, lc),
              [{"kind": "version_state", "version": vid, "expect": st} for vid, st in sorted(exp.items())], timeline=tl(c, T, evs))
        y = keys[1]
        wrong = "NONCURRENT" if exp[f"{y}#1"] == "DELETED" else "DELETED"
        g.add(p, "MC-LC-NONCUR", "negative", "alegação feita com o relógio do outro provedor", merge(r, lc),
              [{"kind": "claim", "claim": {"about": "version_state", "key": y, "version": f"{y}#1", "value": wrong},
                "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], timeline=tl(c, T, evs))
        if p == "oci":
            lc2 = copy.deepcopy(lc)
            for pol in lc2["oci_objectstorage_object_lifecycle_policy"].values():
                for rr in pol["rules"]:
                    rr.pop("target")
            g.add(p, "MC-LC-NONCUR", "unknown", "regra sem alvo: padrão não documentado", merge(r, lc2),
                  [{"kind": "timeline", "expect": unk("MISSING_EVIDENCE")}], timeline=tl(c, T, evs))
        elif p == "azurerm":
            r3, c3 = container(p, n, account_ref="${var.storage_account_id}")
            g.add(p, "MC-LC-NONCUR", "unknown", "contêiner de conta não lida: versionamento e política desconhecidos", r3,
                  [{"kind": "timeline", "expect": unk("INCOMPLETE_READ")}], timeline=tl(c3, T, evs))
        elif p == "aws":
            r3 = copy.deepcopy(merge(r, lc))
            r3["aws_s3_bucket"][n]["lifecycle_rule"] = [{"id": "inline", "enabled": True, "expiration": [{"days": E}]}]
            g.add(p, "MC-LC-NONCUR", "unknown", "lifecycle_rule embutido misturado com o recurso separado", r3,
                  [{"kind": "timeline", "expect": unk("UNRESOLVED")}], timeline=tl(c, T, evs))
        else:
            g.add(p, "MC-LC-NONCUR", "unknown", "ciclo de vida não lido", merge(r, lc),
                  [{"kind": "timeline", "expect": unk("INCOMPLETE_READ")}], timeline=tl(c, T, evs), read=partial((c, "lifecycle")))
    # retenção por contagem: S3 newer_noncurrent_versions K ≡ GCS num_newer_versions K+1
    K = g.pick(1, 1, 3)
    vers = K + 2
    q = g.key("q.dat")
    evs = [put(i, q) for i in range(vers + 1)]
    T = vers + g.pick(5, 2, 10)
    dead = {f"{q}#{i}" for i in range(1, vers - K + 1)}
    exp = {f"{q}#{i}": ("DELETED" if f"{q}#{i}" in dead else "NONCURRENT") for i in range(1, vers + 1)}
    exp[f"{q}#{vers + 1}"] = "CURRENT"
    n = g.name("data")
    r, c = container("aws", n, versioning=True)
    lc = {"aws_s3_bucket_lifecycle_configuration": {n: {"bucket": f"${{{c}.id}}", "rule": [
        {"id": "keep", "status": "Enabled", "filter": [{"prefix": ""}],
         "noncurrent_version_expiration": [{"noncurrent_days": 1, "newer_noncurrent_versions": K}]}]}}}
    g.add("aws", "MC-LC-NONCUR", "positive", f"retém as {K} não correntes mais novas", merge(r, lc),
          [{"kind": "version_state", "version": vid, "expect": st} for vid, st in sorted(exp.items())], timeline=tl(c, T, evs))
    r, c = container("google", n, versioning=True)
    r["google_storage_bucket"][n]["lifecycle_rule"] = [{"action": [{"type": "Delete"}],
                                                        "condition": [{"num_newer_versions": K + 1, "with_state": "ARCHIVED"}]}]
    g.add("google", "MC-LC-NONCUR", "positive", f"apaga quem tem >= {K + 1} versões mais novas", r,
          [{"kind": "version_state", "version": vid, "expect": st} for vid, st in sorted(exp.items())], timeline=tl(c, T, evs))


def mc_lc_filter(g):
    E = g.pick(10, 3, 40)
    T = E + g.pick(5, 1, 20)
    pre = g.choice("logs/", ["logs/", "tmp/", "cache/"])
    kin, kout = f"{pre}{g.key('a.txt')}", g.key("keep/b.txt")
    evs = [put(0, kin), put(0, kout)]
    for p in PROVIDERS:
        n = g.name("data")
        extra = {"account": g.name("acct")} if p == "azurerm" else {}
        r, c = bucket(p, g, n, **extra)
        lc = expire_current(p, n, E, prefix=pre, acct=extra.get("account"), cname=n.replace("_", "-"))
        g.add(p, "MC-LC-FILTER", "positive", f"só o prefixo {pre} expira", merge(r, lc),
              [{"kind": "version_state", "version": f"{kin}#1", "expect": "DELETED"},
               {"kind": "version_state", "version": f"{kout}#1", "expect": "CURRENT"}], timeline=tl(c, T, evs))
        g.add(p, "MC-LC-FILTER", "negative", "alegação de que a regra com prefixo alcança o resto", merge(r, lc),
              [{"kind": "claim", "claim": {"about": "version_state", "key": kout, "version": f"{kout}#1", "value": "DELETED"},
                "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], timeline=tl(c, T, evs))
        if p in ("aws", "azurerm", "oci"):
            lcd = expire_current(p, n, E, prefix=pre, acct=extra.get("account"), cname=n.replace("_", "-"), enabled=False)
            g.add(p, "MC-LC-FILTER", "positive", "regra desligada não age", merge(r, lcd),
                  [{"kind": "version_state", "version": f"{kin}#1", "expect": "CURRENT"}], timeline=tl(c, T, evs))
    # Azure: prefixo nomeia o contêiner; o outro contêiner da conta não é alcançado
    a, n1, n2 = g.name("acct"), g.name("logs"), g.name("media")
    r1, c1 = container("azurerm", n1, account=a, account_attrs={})
    r2, c2 = container("azurerm", n2, account=a)
    lc = expire_current("azurerm", n1, E, prefix=pre, acct=a, cname=n1.replace("_", "-"))
    k2 = f"{pre}{g.key('c.txt')}"
    g.add("azurerm", "MC-LC-FILTER", "negative", "objeto de outro contêiner da conta alegado expirado pela regra do primeiro",
          merge(r1, r2, lc),
          [{"kind": "version_state", "version": f"{k2}#1", "expect": "CURRENT"},
           {"kind": "claim", "claim": {"about": "version_state", "key": k2, "version": f"{k2}#1", "value": "DELETED"},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], timeline=tl(c2, T, [put(0, k2)]))
    # OCI: exclusão vence inclusão; prefixos e padrões juntos sem evidência
    n = g.name("data")
    r, c = container("oci", n)
    lc = expire_current("oci", n, E, prefix=pre)
    rule = lc["oci_objectstorage_object_lifecycle_policy"][n]["rules"][0]
    rule["object_name_filter"] = [{"inclusion_prefixes": [pre], "exclusion_patterns": [f"{pre}*.txt"]}]
    kx = f"{pre}{g.key('d.bin')}"
    g.add("oci", "MC-LC-FILTER", "positive", "exclusão vence inclusão", merge(r, lc),
          [{"kind": "version_state", "version": f"{kin}#1", "expect": "CURRENT"},
           {"kind": "version_state", "version": f"{kx}#1", "expect": "DELETED"}], timeline=tl(c, T, evs + [put(0, kx)]))
    lc2 = copy.deepcopy(lc)
    lc2["oci_objectstorage_object_lifecycle_policy"][n]["rules"][0]["object_name_filter"] = [
        {"inclusion_prefixes": [pre], "inclusion_patterns": ["*.bin"]}]
    g.add("oci", "MC-LC-FILTER", "unknown", "prefixos e padrões de inclusão juntos", merge(r, lc2),
          [{"kind": "timeline", "expect": unk("MISSING_EVIDENCE")}], timeline=tl(c, T, evs))
    n = g.name("data")
    r, c = container("aws", n)
    lc = expire_current("aws", n, E, prefix=pre)
    g.add("aws", "MC-LC-FILTER", "unknown", "regras do contêiner não lidas", merge(r, lc),
          [{"kind": "timeline", "expect": unk("INCOMPLETE_READ")}], timeline=tl(c, T, evs), read=partial((c, "lifecycle")))
    r, c = container("google", n)
    r["google_storage_bucket"][n]["lifecycle_rule"] = [{"action": [{"type": "Delete"}],
                                                        "condition": [{"age": E, "matches_suffix": [".txt"]}]}]
    g.add("google", "MC-LC-FILTER", "unknown", "condição por sufixo fora do modelo do oráculo", r,
          [{"kind": "timeline", "expect": unk("UNSUPPORTED_BY_ORACLE")}], timeline=tl(c, T, evs))
    a = g.name("acct")
    r, c = container("azurerm", n, account=a, account_attrs={})
    lc = expire_current("azurerm", n, E, prefix=pre, acct=a, cname=n.replace("_", "-"))
    g.add("azurerm", "MC-LC-FILTER", "unknown", "política de gestão não lida", merge(r, lc),
          [{"kind": "timeline", "expect": unk("INCOMPLETE_READ")}], timeline=tl(c, T, evs),
          read=partial((f"azurerm_storage_account.{a}", "management_policy")))


ACC_NONE = {"account_public_access_block": {"status": "none_configured"}}


def mc_pub_level(g):
    n = g.name("site")
    # AWS
    r, c = container("aws", n)
    r = merge(r, aws_public(n, "none"), aws_acl(n, "public-read"))
    g.add("aws", "MC-PUB-LEVEL", "positive", "ACL public-read com os bloqueios desligados (exemplo publicado)", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": True},
           {"kind": "public", "container": c, "axis": "anonymous_list", "expect": True}], context=ACC_NONE)
    blocked = {"account_public_access_block": {"status": "declared", "block_public_acls": True, "block_public_policy": True,
                                               "ignore_public_acls": True, "restrict_public_buckets": True}}
    g.add("aws", "MC-PUB-LEVEL", "positive", "bloqueio da conta ignora a ACL pública", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": False},
           {"kind": "apply_rejection", "container": c, "expect": ["acl"]}], context=blocked)
    g.add("aws", "MC-PUB-LEVEL", "negative", "contêiner permite e a conta bloqueia: alegação de público (CMT-BKT-N02)", r,
          [{"kind": "claim", "claim": {"about": "public_access", "container": c, "axis": "anonymous_read", "value": True},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], context=blocked)
    rp, cp = container("aws", n)
    rp = merge(rp, aws_public(n, "read"))
    g.add("aws", "MC-PUB-LEVEL", "positive", "política pública com os bloqueios desligados", rp,
          [{"kind": "public", "container": cp, "axis": "anonymous_read", "expect": True}], context=ACC_NONE)
    g.add("aws", "MC-PUB-LEVEL", "unknown", "bloqueio de conta não lido (CMT-BKT-U01)", rp,
          [{"kind": "public", "container": cp, "axis": "anonymous_read", "expect": unk("INCOMPLETE_READ")}],
          context={"account_public_access_block": {"status": "not_read"}})
    ro, co = container("aws", n)
    ro = merge(ro, aws_public(n, "read", pab={"block_public_policy": True}, depends=False))
    g.add("aws", "MC-PUB-LEVEL", "unknown", "bloqueio do contêiner e política pública sem ordem declarada", ro,
          [{"kind": "public", "container": co, "axis": "anonymous_read", "expect": unk("ORDER_DEPENDENT")}], context=ACC_NONE)
    ro2, co2 = container("aws", n)
    ro2 = merge(ro2, aws_public(n, "read", pab={"block_public_policy": True}, depends=True))
    g.add("aws", "MC-PUB-LEVEL", "positive", "bloqueio do contêiner aplicado antes da política (depends_on): PUT recusado", ro2,
          [{"kind": "public", "container": co2, "axis": "anonymous_read", "expect": False},
           {"kind": "apply_rejection", "container": co2, "expect": ["policy"]}], context=ACC_NONE)
    rn, cn = container("aws", n)
    rn = merge(rn, aws_public(n, "none"), aws_acl(n, "public-read", ownership=None))
    g.add("aws", "MC-PUB-LEVEL", "unknown", "ACL pública sem controle de propriedade declarado", rn,
          [{"kind": "public", "container": cn, "axis": "anonymous_read", "expect": unk("MISSING_EVIDENCE")}], context=ACC_NONE)
    re_, ce = container("aws", n)
    re_ = merge(re_, aws_public(n, "none"), aws_acl(n, "public-read", ownership="BucketOwnerEnforced"))
    g.add("aws", "MC-PUB-LEVEL", "positive", "BucketOwnerEnforced: ACL não afeta permissões", re_,
          [{"kind": "public", "container": ce, "axis": "anonymous_read", "expect": False}], context=ACC_NONE)
    # Google
    r, c = container("google", n, access="read_list")
    g.add("google", "MC-PUB-LEVEL", "positive", "allUsers objectViewer com prevenção herdada e organização sem imposição", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": True},
           {"kind": "public", "container": c, "axis": "anonymous_list", "expect": True}],
          context={"org_policy_public_access_prevention": False})
    re_ = copy.deepcopy(r)
    re_["google_storage_bucket"][n]["public_access_prevention"] = "enforced"
    g.add("google", "MC-PUB-LEVEL", "positive", "prevenção imposta no contêiner", re_,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": False}], context={"org_policy_public_access_prevention": False})
    g.add("google", "MC-PUB-LEVEL", "positive", "prevenção herdada e imposta pela organização", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": False}], context={"org_policy_public_access_prevention": True})
    g.add("google", "MC-PUB-LEVEL", "negative", "prevenção imposta: alegação de público", re_,
          [{"kind": "claim", "claim": {"about": "public_access", "container": c, "axis": "anonymous_read", "value": True},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], context={"org_policy_public_access_prevention": False})
    g.add("google", "MC-PUB-LEVEL", "unknown", "prevenção herdada com a política da organização não lida", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": unk("INCOMPLETE_READ")}])
    ra = copy.deepcopy(r)
    ra.pop("google_storage_bucket_iam_member")
    ra["google_storage_bucket"][n]["uniform_bucket_level_access"] = False
    ra["google_storage_bucket_acl"] = {n: {"bucket": f"${{{c}.name}}", "role_entity": ["READER:allUsers"], "default_acl": "publicRead"}}
    g.add("google", "MC-PUB-LEVEL", "positive", "ACL legada pública sem acesso uniforme", ra,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": True}], context={"org_policy_public_access_prevention": False})
    ru = copy.deepcopy(ra)
    ru["google_storage_bucket"][n]["uniform_bucket_level_access"] = True
    g.add("google", "MC-PUB-LEVEL", "negative", "acesso uniforme ligado: ACL legada alegada efetiva", ru,
          [{"kind": "claim", "claim": {"about": "public_access", "container": c, "axis": "anonymous_read", "value": True},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], context={"org_policy_public_access_prevention": False})
    # Azure
    a = g.name("acct")
    r, c = container("azurerm", n, access="read_list", account=a, account_attrs={})
    g.add("azurerm", "MC-PUB-LEVEL", "positive", "conta permite e contêiner 'container'", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": True},
           {"kind": "public", "container": c, "axis": "anonymous_list", "expect": True}])
    rb = copy.deepcopy(r)
    rb["azurerm_storage_account"][a]["allow_nested_items_to_be_public"] = False
    g.add("azurerm", "MC-PUB-LEVEL", "positive", "conta não permite: o nível do contêiner não tem efeito", rb,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": False}])
    g.add("azurerm", "MC-PUB-LEVEL", "negative", "conta bloqueia, contêiner permite: alegação de público (CMT-BKT-N02)", rb,
          [{"kind": "claim", "claim": {"about": "public_access", "container": c, "axis": "anonymous_read", "value": True},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    rk, ck = container("azurerm", n, access="read_list", account_ref="${var.storage_account_id}")
    g.add("azurerm", "MC-PUB-LEVEL", "unknown", "conta não lida (CMT-BKT-U01)", rk,
          [{"kind": "public", "container": ck, "axis": "anonymous_read", "expect": unk("INCOMPLETE_READ")}])
    # OCI
    r, c = container("oci", n, access="read_list")
    g.add("oci", "MC-PUB-LEVEL", "positive", "ObjectRead: leitura e listagem anônimas", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": True},
           {"kind": "public", "container": c, "axis": "anonymous_list", "expect": True}])
    r0, c0 = container("oci", n)
    g.add("oci", "MC-PUB-LEVEL", "negative", "padrão NoPublicAccess: alegação de público", r0,
          [{"kind": "public", "container": c0, "axis": "anonymous_read", "expect": False},
           {"kind": "claim", "claim": {"about": "public_access", "container": c0, "axis": "anonymous_read", "value": True},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    g.add("oci", "MC-PUB-LEVEL", "unknown", "concessões do contêiner não lidas", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": unk("INCOMPLETE_READ")}], read=partial((c, "public_access")))


def mc_pub_gran(g):
    ctx = {"aws": ACC_NONE, "google": {"org_policy_public_access_prevention": False}, "azurerm": {}, "oci": {}}
    for p in PROVIDERS:
        n = g.name("site")
        r, c = bucket(p, g, n, access="read")
        g.add(p, "MC-PUB-GRAN", "positive", "leitura anônima sem listagem", r,
              [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": True},
               {"kind": "public", "container": c, "axis": "anonymous_list", "expect": False},
               {"kind": "public", "container": c, "axis": "authenticated_read", "expect": False}], context=ctx[p])
        g.add(p, "MC-PUB-GRAN", "negative", "alegação de listagem anônima onde só há leitura", r,
              [{"kind": "claim", "claim": {"about": "public_access", "container": c, "axis": "anonymous_list", "value": True},
                "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], context=ctx[p])
    n = g.name("site")
    r, c = container("google", n)
    r["google_storage_bucket_iam_member"] = {n: {"bucket": f"${{{c}.name}}", "role": "roles/storage.objectViewer",
                                                 "member": "allAuthenticatedUsers"}}
    g.add("google", "MC-PUB-GRAN", "positive", "allAuthenticatedUsers: leitura por qualquer autenticado, não anônima", r,
          [{"kind": "public", "container": c, "axis": "authenticated_read", "expect": True},
           {"kind": "public", "container": c, "axis": "anonymous_read", "expect": False}], context=ctx["google"])
    rc = copy.deepcopy(r)
    rc["google_storage_bucket_iam_member"][n]["member"] = "allUsers"
    rc["google_storage_bucket_iam_member"][n]["condition"] = [{"title": "until", "expression": "request.time < timestamp(\"2030-01-01T00:00:00Z\")"}]
    g.add("google", "MC-PUB-GRAN", "unknown", "concessão pública condicionada", rc,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": unk("CONDITION_INDETERMINATE")}], context=ctx["google"])
    r, c = container("aws", n)
    r = merge(r, aws_public(n, "read", policy_condition=True))
    g.add("aws", "MC-PUB-GRAN", "unknown", "política pública condicionada", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": unk("CONDITION_INDETERMINATE")}], context=ACC_NONE)
    r, c = container("aws", n)
    r = merge(r, aws_public(n, "none"), aws_acl(n, "authenticated-read"))
    g.add("aws", "MC-PUB-GRAN", "positive", "ACL authenticated-read: qualquer autenticado", r,
          [{"kind": "public", "container": c, "axis": "authenticated_read", "expect": True},
           {"kind": "public", "container": c, "axis": "anonymous_read", "expect": False}], context=ACC_NONE)
    a = g.name("acct")
    r, c = container("azurerm", n, access="read", account=a, account_attrs={})
    g.add("azurerm", "MC-PUB-GRAN", "unknown", "configuração de público da conta não lida", r,
          [{"kind": "public", "container": c, "axis": "anonymous_read", "expect": unk("INCOMPLETE_READ")}],
          read=partial((f"azurerm_storage_account.{a}", "allow_nested_items_to_be_public")))
    r, c = container("oci", n, access="read")
    g.add("oci", "MC-PUB-GRAN", "unknown", "concessões do contêiner não lidas", r,
          [{"kind": "public", "container": c, "axis": "anonymous_list", "expect": unk("INCOMPLETE_READ")}], read=partial((c, "public_access")))


MC_BUILDERS = (mc_ver, mc_dec_pack, mc_dec_scope, mc_lc_cur, mc_lc_noncur, mc_lc_filter, mc_pub_level, mc_pub_gran)


# ======================================================================== bordas novas (ciclo v4, só retidas)
def _shuffled(g, xs):
    xs = list(xs)
    g._rnd.shuffle(xs)
    return xs


def mc_edge_v4(g):
    """Casos de borda do ciclo v4, só na partição retida (a calibração não muda): regra de ciclo de vida
    embutida x separada na AWS, facetas embutidas do Google, facetas de conta do Azure com política de prefixos em
    ordem sorteada, contêineres Azure de mesmo nome em contas diferentes."""
    assert g.split == "heldout"
    # 1. AWS: lifecycle_rule embutido x aws_s3_bucket_lifecycle_configuration: mesmo efeito e mesma decomposição
    E = g.pick(30, 3, 80)
    T = E + g.pick(5, 2, 25)
    pre = g.choice("logs/", ["logs/", "tmp/", "archive/", "cache/"])
    ka, kb, kc = f"{pre}{g.key('a.bin')}", f"{pre}{g.key('b.bin')}", g.key("keep.bin")
    evs = [put(0, ka), put(T - E, kb), put(T - E + 1, ka.replace("a.bin", "c.bin")), put(0, kc)]
    kc2 = ka.replace("a.bin", "c.bin")
    grp = "INV-AWS-LIFECYCLE"
    n = g.name("data")
    for form in _shuffled(g, ["inline", "separate"]):
        r, c = container("aws", n)
        if form == "inline":
            r["aws_s3_bucket"][n]["lifecycle_rule"] = [{"id": "expire", "enabled": True, "prefix": pre, "expiration": [{"days": E}]}]
            unit_by = f"{c}/lifecycle_rule"
        else:
            r = merge(r, expire_current("aws", n, E, prefix=pre))
        cu = f"container:{c}"
        g.add("aws", "MC-DEC-PACK", "positive", f"regra de ciclo de vida {form}: mesma faceta e mesmo efeito", r,
              [{"kind": "decomposition", "unit": f"setting:lifecycle@{cu}", "expect": _facet(cu, [cu])},
               {"kind": "version_state", "version": f"{ka}#1", "expect": "DELETED"},
               {"kind": "version_state", "version": f"{kb}#1", "expect": "DELETED"},
               {"kind": "version_state", "version": f"{kc2}#1", "expect": "CURRENT"},
               {"kind": "version_state", "version": f"{kc}#1", "expect": "CURRENT"}],
              timeline=tl(c, T, evs), invariant_group=grp)
    r, c = container("aws", n)
    r["aws_s3_bucket"][n]["lifecycle_rule"] = [{"id": "expire", "enabled": True, "prefix": pre, "expiration": [{"days": E}]}]
    g.add("aws", "MC-DEC-PACK", "negative", "regra embutida alegada entidade própria", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:lifecycle@container:{c}", "value": {"kind": "ENTITY"}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    r2 = merge(copy.deepcopy(r), expire_current("aws", n, E + 1, prefix=pre))
    g.add("aws", "MC-LC-CUR", "unknown", "regra embutida e recurso separado no mesmo contêiner: a doc proíbe misturar", r2,
          [{"kind": "timeline", "expect": unk("UNRESOLVED")}], timeline=tl(c, T, evs))
    # 2. Google: facetas embutidas (versionamento, ciclo de vida, prevenção) e concessão separada
    n = g.name("site")
    r, c = container("google", n, versioning=True, access="read")
    r["google_storage_bucket"][n]["public_access_prevention"] = g.choice("inherited", ["inherited", "enforced"])
    r["google_storage_bucket"][n]["lifecycle_rule"] = _shuffled(g, [
        {"action": [{"type": "Delete"}], "condition": [{"age": E, "with_state": "LIVE"}]},
        {"action": [{"type": "Delete"}], "condition": [{"days_since_noncurrent_time": E, "with_state": "ARCHIVED"}]}])
    cu = f"container:{c}"
    g.add("google", "MC-DEC-SCOPE", "positive", "facetas embutidas do Google e concessão separada: todas com alcance do contêiner", r,
          [{"kind": "decomposition", "unit": f"setting:versioning@{cu}", "expect": _facet(cu, [cu])},
           {"kind": "decomposition", "unit": f"setting:lifecycle@{cu}", "expect": _facet(cu, [cu])},
           {"kind": "decomposition", "unit": f"setting:public_access_block@{cu}", "expect": _facet(cu, [cu])},
           {"kind": "decomposition", "unit": f"setting:access_grant@{cu}", "expect": _facet(cu, [cu])}],
          context={"org_policy_public_access_prevention": False})
    g.add("google", "MC-DEC-SCOPE", "negative", "faceta embutida alegada de outro dono", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:lifecycle@{cu}", "value": {"owner": "self"}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}], context={"org_policy_public_access_prevention": False})
    # 3. Azure: facetas de conta; política com prefixos de dois contêineres em ordem sorteada, terceiro fora
    a = g.name("acct")
    names = [g.name(x) for x in ("logs", "media", "backup")]
    parts, cs = [], []
    for i, nm in enumerate(names):
        rr, cc = container("azurerm", nm, versioning=True if i == 0 else None, account=a, account_attrs={} if i == 0 else None)
        parts.append(rr)
        cs.append(cc)
    rr = merge(*parts)
    rr["azurerm_storage_account"][a]["allow_nested_items_to_be_public"] = g.choice(False, [False, True])
    hit = _shuffled(g, [names[0], names[1]])
    rr["azurerm_storage_management_policy"] = {f"{a}_policy": {"storage_account_id": f"${{azurerm_storage_account.{a}.id}}", "rule": _shuffled(g, [
        {"name": f"r{i}", "enabled": True, "filters": [{"blob_types": ["blockBlob"], "prefix_match": [f"{nm.replace('_', '-')}/{pre}"]}],
         "actions": [{"base_blob": [{"delete_after_days_since_modification_greater_than": E - 1}]}]} for i, nm in enumerate(hit)])}}
    nu = f"namespace:azurerm_storage_account.{a}"
    allc = sorted(f"container:{x}" for x in cs)
    g.add("azurerm", "MC-DEC-SCOPE", "positive", "conta com três contêineres: versionamento e público alcançam todos; política só os prefixados", rr,
          [{"kind": "decomposition", "unit": f"setting:versioning@{nu}", "expect": _facet(nu, allc)},
           {"kind": "decomposition", "unit": f"setting:public_access_block@{nu}", "expect": _facet(nu, allc)},
           {"kind": "decomposition", "unit": f"setting:lifecycle@{nu}", "expect": _facet(nu, sorted(f"container:{x}" for x in cs[:2]))},
           {"kind": "versioning", "container": cs[2], "expect": "ENABLED"}])
    g.add("azurerm", "MC-DEC-SCOPE", "negative", "política de prefixos alegada com alcance na conta inteira", rr,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:lifecycle@{nu}", "value": {"effective_scope": allc}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    k3 = f"{pre}{g.key('z.bin')}"
    g.add("azurerm", "MC-LC-FILTER", "positive", "terceiro contêiner da conta fora dos prefixos: nada expira", rr,
          [{"kind": "version_state", "version": f"{k3}#1", "expect": "CURRENT"}],
          timeline=tl(cs[2], T, [put(0, k3)]))
    # 4. Azure: contêineres de mesmo nome em contas diferentes são entidades distintas (namespace diferente)
    same = g.name("shared").replace("_", "-")
    a1, a2 = g.name("acct"), g.name("acct")
    r1, c1 = container("azurerm", "c_one", account=a1, account_attrs={}, cname=same)
    r2_, c2 = container("azurerm", "c_two", account=a2, account_attrs={}, cname=same)
    g.add("azurerm", "MC-DEC-PACK", "positive", "mesmo nome de contêiner em contas diferentes: duas entidades", merge(r1, r2_),
          [{"kind": "decomposition", "unit": f"container:{c1}", "expect": {"kind": "ENTITY", "namespace": f"namespace:azurerm_storage_account.{a1}"}},
           {"kind": "decomposition", "unit": f"container:{c2}", "expect": {"kind": "ENTITY", "namespace": f"namespace:azurerm_storage_account.{a2}"}}])
    g.add("azurerm", "MC-DEC-PACK", "negative", "contêiner alegado no namespace da outra conta", merge(r1, r2_),
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"container:{c1}", "value": {"namespace": f"namespace:azurerm_storage_account.{a2}"}},
            "expect": {"verdict": "REJECT", "code": "CONTRADICTS_ORACLE"}}])
    # 5. Google sem bloco de versionamento: padrão (DISABLED) e nenhuma faceta de versionamento
    n = g.name("plain")
    r, c = container("google", n)
    g.add("google", "MC-VER", "positive", "sem bloco de versionamento: nunca versionado, marcado como padrão", r,
          [{"kind": "versioning", "container": c, "expect": "DISABLED"}])
    g.add("google", "MC-DEC-PACK", "negative", "faceta de versionamento alegada sem bloco declarado", r,
          [{"kind": "claim", "claim": {"about": "decomposition", "unit": f"setting:versioning@container:{c}", "value": {"kind": "FACET"}},
            "expect": {"verdict": "REJECT", "code": "NO_SUCH_UNIT"}}])


# ======================================================================== famílias por direção
def _side(g, p, role, *, versioning=None, access=None, lc=None, read=None, ctx=None, bystander=False, account_ref=None):
    """Monta o lado de uma direção: devolve (fixture, contêiner)."""
    n = g.name(role)
    extra = {}
    if p == "azurerm":
        extra = {"account": g.name(role + "_acct")}
        if account_ref:
            extra["account_ref"] = account_ref
        else:
            extra["account_attrs"] = {}
    r, c = container(p, n, versioning=versioning, access=access, **extra)
    if lc:
        kind, E = lc
        part = (expire_current if kind == "expire" else noncurrent_rule)(p, n, E, acct=extra.get("account"))
        if kind == "expire" and p == "azurerm":
            part = expire_current(p, n, E, acct=extra.get("account"), cname=n.replace("_", "-"))
        r = merge(r, part)
    context = dict(ctx or {})
    if bystander and p == "azurerm":
        nb = g.name("neighbor")
        rb, cb = container(p, nb, account=extra["account"])
        r = merge(r, rb)
        context["bystanders"] = [{"container": cb, "before": {"versioning": "DISABLED"}}]
    fx = make_fx(p, "", "", r, context=context, read=read)
    return fx, c


PUB_CTX = {"aws": ACC_NONE, "google": {"org_policy_public_access_prevention": False}, "azurerm": {}, "oci": {}}
UNREAD_PUBLIC = {
    "aws": ({"account_public_access_block": {"status": "not_read"}}, None),
    "google": ({}, None),
    "azurerm": ({}, "allow"),
    "oci": ({}, "public"),
}


def _entry(g, a, b, fam, var, src, sc, tgt, tc, expect, losses=(), note=""):
    src, tgt = copy.deepcopy(src), copy.deepcopy(tgt)
    eid = g.eid(a, b, fam, var)
    src["fixture_id"], tgt["fixture_id"] = eid + "-S", eid + "-T"
    g.entries.append({"entry_id": eid, "split": g.split, "direction": f"{a}->{b}", "family": fam, "variant": var,
                      "polarity": {"acceptable": "positive", "acceptable_declared": "positive", "negative": "negative",
                                   "negative_silent": "negative", "unknown": "unknown"}[var],
                      "note": note, "source": src, "target": tgt, "container_map": {sc: tc},
                      "declared_losses": list(losses), "expect": expect})


def dir_t1(g, a, b):
    k1, k2 = g.key("doc.txt"), g.key("gone.txt")
    d = g.pick(3, 1, 10)
    T = d + g.pick(3, 1, 10)
    src, sc = _side(g, a, "src", versioning=True)
    events = [put(0, k1), put(1, k2), put(d, k1), {"day": d + 1, "op": "delete", "key": k2}]
    T = max(T, d + 1)
    src["timeline"] = tl(sc, T, events)

    def tgt_with(**kw):
        t, tc = _side(g, b, "dst", **kw)
        t["timeline"] = tl(tc, T, events)
        return t, tc

    t, tc = tgt_with(versioning=True)
    _entry(g, a, b, "T1-VERSIONED", "acceptable", src, sc, t, tc, {"verdict": "ACCEPT"})
    t, tc = tgt_with(versioning=False)
    _entry(g, a, b, "T1-VERSIONED", "negative", src, sc, t, tc, {"verdict": "REJECT", "code": "EARLY_DELETION"},
           note="alvo sem versionamento perde as versões sobrescritas e excluídas")
    t, tc = tgt_with(versioning=True, read=None)
    t["read"] = partial((tc, "versioning")) if b != "azurerm" else partial((azure_acct_of(t, tc), "blob_properties"))
    _entry(g, a, b, "T1-VERSIONED", "unknown", src, sc, t, tc, {"verdict": "UNKNOWN", "code": "INCOMPLETE_READ"})
    if b == "azurerm":
        t, tc = tgt_with(versioning=True, bystander=True)
        _entry(g, a, b, "T1-VERSIONED", "acceptable_declared", src, sc, t, tc, {"verdict": "ACCEPT_WITH_DECLARED_LOSS"},
               losses=["SCOPE_WIDENED"], note="versionamento da conta alcança o vizinho; perda de alcance declarada")
        _entry(g, a, b, "T1-VERSIONED", "negative_silent", src, sc, t, tc, {"verdict": "REJECT", "code": "SILENT_LOSS"},
               note="o mesmo alvo sem declarar o alcance alargado")


def azure_acct_of(fx, c):
    import re
    m = re.match(r"^\$\{azurerm_storage_account\.([^.]+)\.id\}$", fx["terraform"]["resource"]["azurerm_storage_container"][c.split(".", 1)[1]]["storage_account_id"])
    return f"azurerm_storage_account.{m.group(1)}"


def dir_t2(g, a, b):
    src, sc = _side(g, a, "src", access="read", ctx=PUB_CTX[a])
    t, tc = _side(g, b, "dst", access="read", ctx=PUB_CTX[b])
    _entry(g, a, b, "T2-PUBLIC-READ", "acceptable", src, sc, t, tc, {"verdict": "ACCEPT"})
    t, tc = _side(g, b, "dst", access="read_list", ctx=PUB_CTX[b])
    _entry(g, a, b, "T2-PUBLIC-READ", "negative", src, sc, t, tc, {"verdict": "REJECT", "code": "PUBLIC_WIDENED"},
           note="alvo que também lista: mais público que a origem")
    t, tc = _side(g, b, "dst", access=None, ctx=PUB_CTX[b])
    _entry(g, a, b, "T2-PUBLIC-READ", "acceptable_declared", src, sc, t, tc, {"verdict": "ACCEPT_WITH_DECLARED_LOSS"},
           losses=["ACCESS_NARROWED"], note="alvo privado com a perda de acesso declarada")
    ctx, what = UNREAD_PUBLIC[b]
    t, tc = _side(g, b, "dst", access="read", ctx=ctx if b in ("aws", "google") else PUB_CTX[b])
    if what == "allow":
        t["read"] = partial((azure_acct_of(t, tc), "allow_nested_items_to_be_public"))
    elif what == "public":
        t["read"] = partial((tc, "public_access"))
    if b == "google":
        t["context"] = {}
    _entry(g, a, b, "T2-PUBLIC-READ", "unknown", src, sc, t, tc, {"verdict": "UNKNOWN", "code": "INCOMPLETE_READ"},
           note="nível superior do alvo não lido")


def dir_t3(g, a, b):
    E = g.pick(30, 5, 90)
    T = E + g.pick(10, 2, 30)
    ka, kb, kc = g.key("old.bin"), g.key("edge.bin"), g.key("young.bin")
    events = [put(0, ka), put(T - E, kb), put(T - E + 1, kc)]
    src, sc = _side(g, a, "src", lc=("expire", E))
    src["timeline"] = tl(sc, T, events)

    def tgt(Et, **kw):
        t, tc = _side(g, b, "dst", lc=("expire", Et), **kw)
        t["timeline"] = tl(tc, T, events)
        return t, tc

    t, tc = tgt(E)
    _entry(g, a, b, "T3-EXPIRE", "acceptable", src, sc, t, tc, {"verdict": "ACCEPT"}, note="limite convertido (>= E ≡ > E-1)")
    t, tc = tgt(E + 1)
    _entry(g, a, b, "T3-EXPIRE", "acceptable_declared", src, sc, t, tc, {"verdict": "ACCEPT_WITH_DECLARED_LOSS"},
           losses=["RETAINED_LONGER"], note="um dia a mais declarado")
    t, tc = tgt(E - 1)
    _entry(g, a, b, "T3-EXPIRE", "negative", src, sc, t, tc, {"verdict": "REJECT", "code": "EARLY_DELETION"},
           note="um dia antes apaga o objeto que a origem mantém")
    if b == "azurerm":
        # cópia literal do número de '>=' para '>' (de '>' para '>=' coincide com o negativo de um dia antes)
        t, tc = tgt(E + 1)
        _entry(g, a, b, "T3-EXPIRE", "negative_silent", src, sc, t, tc, {"verdict": "REJECT", "code": "SILENT_LOSS"},
               note="número copiado literalmente de '>=' para '>': um dia a mais sem declarar")
    t, tc = tgt(E)
    t["read"] = partial((tc, "lifecycle")) if b != "azurerm" else partial((azure_acct_of(t, tc), "management_policy"))
    _entry(g, a, b, "T3-EXPIRE", "unknown", src, sc, t, tc, {"verdict": "UNKNOWN", "code": "INCOMPLETE_READ"})


def dir_t4(g, a, b):
    E = g.pick(30, 27, 60)
    keys = tuple(g.key(x) for x in ("x.log", "y.log", "z.log", "w.log", "v.log"))
    T, events = t4_events(E, keys)
    src, sc = _side(g, a, "src", versioning=True, lc=("noncurrent", E))
    src["timeline"] = tl(sc, T, events)

    def tgt(Et=None, **kw):
        t, tc = _side(g, b, "dst", versioning=True, lc=("noncurrent", Et) if Et else None, **kw)
        t["timeline"] = tl(tc, T, events)
        return t, tc

    ca, cb = CLOCK[a], CLOCK[b]
    if ca == cb:
        t, tc = tgt(E)
        _entry(g, a, b, "T4-NONCURRENT", "acceptable", src, sc, t, tc, {"verdict": "ACCEPT"}, note="mesmo relógio, limite convertido")
        t, tc = tgt(15 if ca == "noncurrent" else E - 1)
        _entry(g, a, b, "T4-NONCURRENT", "negative", src, sc, t, tc, {"verdict": "REJECT", "code": "EARLY_DELETION"})
    elif ca == "noncurrent":
        t, tc = tgt(E)
        _entry(g, a, b, "T4-NONCURRENT", "negative", src, sc, t, tc, {"verdict": "REJECT", "code": "EARLY_DELETION"},
               note="mesmo número no relógio da criação apaga antes")
        t, tc = tgt(None)
        _entry(g, a, b, "T4-NONCURRENT", "acceptable_declared", src, sc, t, tc, {"verdict": "ACCEPT_WITH_DECLARED_LOSS"},
               losses=["RETAINED_LONGER"], note="sem relógio 'desde não corrente' no alvo: não apagar e declarar")
    else:
        t, tc = tgt(E)
        _entry(g, a, b, "T4-NONCURRENT", "acceptable_declared", src, sc, t, tc, {"verdict": "ACCEPT_WITH_DECLARED_LOSS"},
               losses=["RETAINED_LONGER"], note="relógio 'desde não corrente' nunca apaga antes do 'desde a criação'")
        _entry(g, a, b, "T4-NONCURRENT", "negative_silent", src, sc, t, tc, {"verdict": "REJECT", "code": "SILENT_LOSS"},
               note="o mesmo alvo sem declarar a retenção maior")
        t, tc = tgt(1)
        _entry(g, a, b, "T4-NONCURRENT", "negative", src, sc, t, tc, {"verdict": "REJECT", "code": "EARLY_DELETION"})
    t, tc = tgt(E)
    t["read"] = partial((tc, "lifecycle")) if b != "azurerm" else partial((azure_acct_of(t, tc), "management_policy"))
    _entry(g, a, b, "T4-NONCURRENT", "unknown", src, sc, t, tc, {"verdict": "UNKNOWN", "code": "INCOMPLETE_READ"})


DIR_BUILDERS = (dir_t1, dir_t2, dir_t3, dir_t4)
DIRECTIONS = [(a, b) for a in PROVIDERS for b in PROVIDERS if a != b]


def generate(split):
    g = Gen(split)
    for f in MC_BUILDERS:
        f(g)
    if split == "heldout":
        g._edge = True
        mc_edge_v4(g)
        g._edge = False
    for a, b in DIRECTIONS:
        for f in DIR_BUILDERS:
            f(g, a, b)
    return g
