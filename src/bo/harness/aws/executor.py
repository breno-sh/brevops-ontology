"""Executor do harness: apply -> espera -> leitura -> destroy, com o redator antes de qualquer gravação.

  python -I -m bo.harness.aws.executor --offline-demo [--out DIR]
      roda os casos de fixture com respostas GRAVADAS (sem rede, sem credencial) e grava C12/C16 de exemplo

Ordem por caso (execute):
  0. pré-condições sem efeito: render RENDERED (senão UNKNOWN com 'UNKNOWN_INPUT: ...'), todo símbolo ligado,
     região do contexto do grafo (se conhecida) igual à da execução;
  1. com a CLI real: redator do kit (SAFETY) e allowlist de contas obrigatórios; identidade efetiva pelo kit
     (allowlist privada); sem casar, INFRA_ERROR e nada é criado;
  2. intenção gravada (C16 intent_manifest + estágio 'intent') ANTES do apply;
  3. diretório efêmero exclusivo (sob $BO_TMP ou a raiz efêmera do kit) com os modelos e só este plano;
     segredos gerados na hora, só em memória (TF_VAR_*), nunca gravados;
  4. init + apply; erro do provedor é classificado por regra (REJECTED_BY_API x INFRA_ERROR x UNKNOWN);
  5. espera: lê de volta até duas leituras seguidas iguais (consistência eventual) ou fim da janela;
  6. leitura: cada campo do plano vira read/absent/not_read/withheld, pelo redator; ids reais só como
     'ref:<nó>' ou 'sym:<SYM>' quando batem com o que o plano criou; caminho no C12 = '<node_id>.<campo>';
  7. desfecho C12 pela regra HAWS-JUDGE-01 com o comparador do caso (bo.transforms.comparators);
  8. destroy SEMPRE (finally), state vazio conferido; estágios removal_requested -> absent ou removal_pending;
  9. diretório efêmero apagado; gravação só pelo Sink (redator -> privacy_lint -> validador do contrato).
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import MODULE_ID, PROVIDER, pins, redact, render
from . import schema as sch
from .backends import Backend, RecordedBackend, TerraformCLIBackend

TZ = ZoneInfo("America/Recife")
PROTOCOL_VERSION = "1.0.0"
LADDER = ["UNRESOLVED", "STRUCTURALLY_VALID", "DOC_SUPPORTED", "PERSISTENCE_VERIFIED", "OBSERVATION_TESTED"]

RULES = {
    "HAWS-RENDER-01": "render diferente de RENDERED: o caso falha UNKNOWN_INPUT (ou plano inválido) sem tocar nuvem",
    "HAWS-BIND-01": "símbolo do plano sem valor ligado na execução: UNKNOWN_INPUT, nada é criado",
    "HAWS-REGION-01": "região conhecida no contexto do grafo difere da região da execução: UNKNOWN_INPUT",
    "HAWS-IDENT-01": "identidade efetiva fora da allowlist: INFRA_ERROR, nada é criado",
    "HAWS-APPLY-01": "erro no apply classificado por padrão do diagnóstico (rejeição da API x infraestrutura)",
    "HAWS-WAIT-01": "leitura não estabilizou na janela: UNKNOWN",
    "HAWS-JUDGE-01": "campos carregados (origin=carried, termo não withheld): todos lidos e iguais = PERSISTED; "
                     "algum lido e diferente = ALTERED; algum não legível e nenhum diferente = NOT_READABLE; "
                     "sintetizados, defaults declarados e segredos não entram no julgamento",
}

INFRA_PAT = re.compile(r"Throttl|RequestLimitExceeded|LimitExceeded|QuotaExceeded|ServiceUnavailable|InternalError|"
                       r"InternalFailure|StatusCode: 5\d\d|timeout|timed out|connection reset|no such host|"
                       r"ExpiredToken|NoCredentialProviders|InsufficientInstanceCapacity|AccessDenied|"
                       r"UnauthorizedOperation|init falhou", re.I)
REJECT_PAT = re.compile(r"StatusCode: 4\d\d|InvalidParameter|ValidationException|ValidationError|"
                        r"InvalidParameterCombination|InvalidParameterValue|MalformedPolicyDocument|InvalidRequest|"
                        r"InvalidInput|is not a valid|not supported|Unsupported", re.I)


def now() -> datetime:
    return datetime.now(TZ).replace(microsecond=0)


def iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


# ------------------------------------------------------------------------------------------ kit e config
class SafetyKit:
    """Interface do kit de segurança (SAFETY). identity_check() devolve {identity_sha256, checked_at,
    matches_allowlist}; intent_fields(tipo) devolve {tag_supported, ttl_supported, [ttl_hours], purge_hours,
    max_residual_cost_usd}; redactor() devolve redact.Redactor; credential_env() as variáveis de credencial."""

    name = "abstract"

    def identity_check(self) -> dict:
        raise NotImplementedError

    def intent_fields(self, resource_type: str) -> dict:
        raise NotImplementedError

    def redactor(self) -> redact.Redactor:
        raise NotImplementedError

    def credential_env(self) -> dict:
        return {}

    def allowed_account_ids(self) -> list:
        """Contas sandbox permitidas (canal privado; só em memória, vira TF_VAR e nunca é gravado)."""
        raise NotImplementedError

    def ephemeral_root(self) -> Path:
        return pins.tmp_root() / "ephemeral"


class OfflineKit(SafetyKit):
    """Kit só para respostas gravadas: identidade sintética (hash de um rótulo fixo), suporte a tag pelo schema
    fixado (atributo 'tags' configurável), TTL não suportado, prazos e custos sintéticos declarados."""

    name = "offline"

    def __init__(self, schema: sch.ProviderSchema, matches: bool = True):
        import hashlib
        self.schema = schema
        self.matches = matches
        self._id = hashlib.sha256(b"identidade-sintetica-offline").hexdigest()

    def identity_check(self):
        return {"identity_sha256": self._id, "checked_at": iso(now()), "matches_allowlist": self.matches}

    def intent_fields(self, rtype):
        tags = self.schema.has(rtype) and "tags" in self.schema.resource(rtype).attributes
        return {"tag_supported": bool(tags), "ttl_supported": False, "purge_hours": 24,
                "max_residual_cost_usd": 0.5}

    def redactor(self):
        return redact.Redactor(redact.load_kit_redactor())

    def allowed_account_ids(self):
        return []


@dataclass
class RunConfig:
    run_id: str
    batch_id: str
    region: str
    case: dict                       # registro C11
    module: str = MODULE_ID
    side: str = "object"
    evidence_state_before: str = "DOC_SUPPORTED"
    bindings: dict = field(default_factory=dict)   # SYM-... -> valor (só em memória)
    wait_timeout_s: float = 600
    poll_interval_s: float = 10


# ------------------------------------------------------------------------------------------ gravação
class SinkError(RuntimeError):
    pass


class Sink:
    """Única porta de gravação: redator (kit + base) -> privacy_lint -> validador do contrato -> arquivo."""

    def __init__(self, out_dir: Path, redactor: redact.Redactor):
        out_dir = Path(out_dir).resolve()
        allowed = [pins.data_root().resolve() / MODULE_ID, pins.tmp_root().resolve()]
        extra = [pins.data_root().resolve() / m for m in _producer_modules()]
        if not any(out_dir == a or a in out_dir.parents for a in allowed + extra):
            raise SinkError(f"gravação fora de $BO_DATA/<módulo> e de $BO_TMP: {out_dir}")
        out_dir.mkdir(parents=True, exist_ok=True)
        self.dir = out_dir
        self.red = redactor
        self.written: dict[str, int] = {}

    def append(self, fname: str, kind: str, records: list[dict]):
        if not records:
            return
        recs = [self.red(r, f"{kind}") for r in records]
        text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)
        finds = redact.privacy_findings(text, fname)
        if finds:
            raise SinkError(f"privacy_lint reprovou {fname} antes da gravação: " +
                            ", ".join(sorted({f.rule for f in finds})))
        dest = self.dir / fname
        tmp = self.dir / f".{fname}.novo"
        prev = dest.read_text(encoding="utf-8") if dest.exists() else ""
        tmp.write_text(prev + text, encoding="utf-8")
        from bo.contracts import validate as v
        vdir = self.dir / ".valida"
        shutil.rmtree(vdir, ignore_errors=True)
        vdir.mkdir()
        for sib in self.dir.glob("*.jsonl"):
            shutil.copyfile(sib, vdir / sib.name)
        tmp_named = vdir / fname
        shutil.copyfile(tmp, tmp_named)
        res = v.validate(kind, tmp_named)
        shutil.rmtree(tmp_named.parent, ignore_errors=True)
        if not res.ok:
            tmp.unlink()
            raise SinkError(f"{fname} reprova no contrato {kind}: " + "; ".join(res.errors[:3]))
        tmp.replace(dest)
        self.written[fname] = self.written.get(fname, 0) + len(recs)


def _producer_modules() -> list[str]:
    return ["SMOKE-AWS", "DEP-AWS-A", "DEP-AWS-B", "PROBE-AWS", "PILOT-NET-E2E", "PILOT-STO-E2E"]


# ------------------------------------------------------------------------------------------ execução
@dataclass
class ExecResult:
    case_id: str
    outcome: dict
    readback: dict | None
    intents: list
    runs: list
    calls: list
    notes: list = field(default_factory=list)


def _outcome_record(cfg: RunConfig, value: str, detail: str | None, rule: str, readback_id: str | None) -> dict:
    o = {"axis": "persistence", "value": value}
    if detail:
        o["detail"] = detail
    before = cfg.evidence_state_before
    after = "PERSISTENCE_VERIFIED" if value == "PERSISTED" and \
        LADDER.index(before) < LADDER.index("PERSISTENCE_VERIFIED") else before
    rec = {"outcome_id": f"OUT-{cfg.run_id[4:]}-{cfg.case['case_id'][5:]}", "case_id": cfg.case["case_id"],
           "group_id": cfg.case["group_id"], "claim_id": cfg.case["claim_id"], "side": cfg.side, "outcome": o,
           "evidence_state_before": before, "evidence_state_after": after, "rule_id": rule,
           "decided_at": iso(now())}
    if readback_id and value in ("PERSISTED", "ALTERED", "NOT_READABLE"):
        rec["readback_id"] = readback_id
    return rec


def classify(diags: list) -> tuple[str, str]:
    text = " ".join(f"{d.get('summary', '')} {d.get('detail', '')}" for d in diags if d.get("severity") == "error")
    if INFRA_PAT.search(text):
        return "INFRA_ERROR", text
    if REJECT_PAT.search(text):
        return "REJECTED_BY_API", text
    return "UNKNOWN", text


def _resources_in_state(show: dict) -> dict:
    out = {}

    def walk(mod):
        for r in mod.get("resources", []) or []:
            if r.get("mode", "managed") == "managed":
                out[r["address"]] = r
        for c in mod.get("child_modules", []) or []:
            walk(c)
    walk(((show or {}).get("values") or {}).get("root_module") or {})
    return out


_MISSING = object()


def _get(values: dict, path: list[str]):
    cur = values
    for seg in path:
        if isinstance(cur, list):
            if not cur:
                return _MISSING
            cur = cur[0]
        if not isinstance(cur, dict) or seg not in cur:
            return _MISSING
        cur = cur[seg]
    return cur


def _attr_meta(block: sch.Block, path: list[str]) -> tuple[bool, bool]:
    cur = block
    for i, seg in enumerate(path):
        if seg in cur.attributes:
            a = cur.attributes[seg]
            return a.sensitive, a.write_only
        if seg in cur.blocks:
            cur = cur.blocks[seg].block
            continue
        break
    return False, False


def build_readback(cfg: RunConfig, plan: dict, entry: dict, show: dict, schema: sch.ProviderSchema,
                   rb_id: str) -> tuple[dict, list]:
    """Readback C12 (já redigido) e a lista de comparações em memória (sem gravar valores reais)."""
    res = _resources_in_state(show)
    addr_of = {r["node_id"]: r["address"] for r in entry["resources"]}
    sym: dict[str, list] = {}
    for node, addr in addr_of.items():
        r = res.get(addr)
        for attr in ("id", "arn"):
            if r and isinstance((r.get("values") or {}).get(attr), str):
                sym.setdefault(r["values"][attr], []).append(f"ref:{node}" if attr == "id" else f"ref:{node}.arn")
    for sid, val in sorted(cfg.bindings.items()):
        if isinstance(val, str):
            sym.setdefault(val, []).append(f"sym:{sid}")
    nodes = {s["node_id"]: s for s in plan["steps"]}
    refs = entry["record"].get("references", [])
    fields, comps = [], []
    unrendered = {(u["address"], u["field"]) for u in entry["unrendered"]}
    for step in sorted(plan["steps"], key=lambda s: s["order"]):
        addr = addr_of.get(step["node_id"])
        r = res.get(addr) if addr else None
        block = schema.resource(step["resource_type"]) if schema.has(step["resource_type"]) else sch.Block()
        for v in step["values"]:
            path = f"{step['node_id']}.{v['field']}"
            if (addr, v["field"]) in unrendered:
                continue
            sens_schema, wo = _attr_meta(block, v["field"].split("."))
            sens_state = bool(_get((r or {}).get("sensitive_values") or {}, v["field"].split(".")) is True)
            if r is None:
                fr = redact.FieldRedaction("not_read")
                raw = _MISSING
            else:
                raw = _get(r.get("values") or {}, v["field"].split("."))
                prefer = _expected({"term": v["term"], "field": v["field"], "step": step}, nodes, refs)
                fr = redact.finalize(redact.redact_field(path, None if raw is _MISSING else raw,
                                                         sensitive=sens_schema or sens_state
                                                         or v["term"]["kind"] == "withheld",
                                                         write_only=wo, symbolic=sym, prefer=prefer))
                if raw is _MISSING and fr.state == "absent":
                    fr = redact.FieldRedaction("not_read")
            f = {"path": path, "state": fr.state}
            if fr.state == "read":
                f["value"] = fr.value
            if fr.state == "withheld":
                f["redaction"] = {"rule_id": fr.rule_id, "at_source": True}
            fields.append(f)
            comps.append({"path": path, "field": v["field"], "origin": v["origin"], "term": v["term"], "state": fr.state,
                          "read": fr.value if fr.state == "read" else None, "step": step})
    rb = {"readback_id": rb_id, "case_id": cfg.case["case_id"], "group_id": cfg.case["group_id"],
          "claim_id": cfg.case["claim_id"], "side": cfg.side, "provider": PROVIDER, "read_at": iso(now()),
          "protocol_version": PROTOCOL_VERSION, "fields": fields}
    return rb, comps


def _expected(c: dict, plan_nodes: dict, refs: list):
    t = c["term"]
    k = t["kind"]
    if k == "literal":
        return t["value"]
    if k == "symbol":
        return f"sym:{t['symbol_id']}"
    if k == "reference":
        for ref in refs:
            if ref["from_step"] == c["step"]["order"] and ref["field"] == c["field"]:
                node = next(s["node_id"] for s in plan_nodes.values() if s["order"] == ref["to_step"])
                return f"ref:{node}" if ref["attribute"] == "id" else f"ref:{node}.{ref['attribute']}"
        return None
    if k == "document":
        return t["tree"]
    return None


def judge(cfg: RunConfig, comps: list, plan: dict, refs: list) -> tuple[str, str | None]:
    from bo.transforms import comparators as CMP
    from bo.transforms.errors import TransformError
    nodes = {s["node_id"]: s for s in plan["steps"]}
    carried = [c for c in comps if c["origin"] == "carried" and c["term"]["kind"] != "withheld"]
    if not carried:
        return "UNKNOWN", "nenhum valor carregado (origin=carried) para julgar persistência"
    diff, unread = [], []
    for c in carried:
        exp = _expected(c, nodes, refs)
        if c["state"] in ("not_read", "withheld"):
            unread.append(c["path"])
            continue
        if c["state"] == "absent":
            if exp is not None:
                diff.append(c["path"])
            continue
        got = c["read"]
        if c["term"]["kind"] == "document" and isinstance(got, str):
            try:
                got = json.loads(got)
            except json.JSONDecodeError:
                pass
        try:
            same = CMP.compare(cfg.case["comparator"], exp, got) if c["term"]["kind"] == "literal" else exp == got
        except TransformError as e:
            return "UNKNOWN", f"comparador {cfg.case['comparator']['name']} fora do domínio em {c['path']}: {e}"
        if not same:
            diff.append(c["path"])
    if diff:
        return "ALTERED", "difere: " + ", ".join(diff)
    if unread:
        return "NOT_READABLE", "não legível: " + ", ".join(unread)
    return "PERSISTED", None


def execute(render_dir: Path, plan_id: str, cfg: RunConfig, backend: Backend, kit: SafetyKit, sink: Sink,
            graph: dict | None = None, sleep=None, clock=None) -> ExecResult:
    import time
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    render_dir = Path(render_dir)
    man = json.loads((render_dir / "render_manifest.json").read_text(encoding="utf-8"))
    entry = next((e for e in man["plans"] if e["plan_id"] == plan_id), None)
    if entry is None:
        raise KeyError(f"{plan_id} não está no render_manifest.json")
    plan = next(p for p in render.read_jsonl(Path(man["input"]["plan"])) if p["plan_id"] == plan_id)
    schema = sch.load(None)
    res = ExecResult(cfg.case["case_id"], {}, None, [], [], [])

    def finish(value, detail, rule, rb=None):
        res.outcome = _outcome_record(cfg, value, detail, rule, rb)
        sink.append("outcomes.jsonl", "outcomes", [res.outcome])
        return res

    # 0. pré-condições sem efeito colateral
    if entry["status"] != "RENDERED":
        why = "; ".join(f"{m.get('field') or ''} {m['reason']}".strip() for m in entry["missing"] + entry["problems"])
        tag = "UNKNOWN_INPUT" if entry["status"] == "UNKNOWN_INPUT" else "INVALID_PLAN"
        return finish("UNKNOWN", f"{tag}: {why}", "HAWS-RENDER-01")
    unbound = [v["symbol_id"] for v in entry["variables"] if v["kind"] == "symbol" and v["symbol_id"] not in cfg.bindings]
    if unbound:
        return finish("UNKNOWN", f"UNKNOWN_INPUT: símbolo(s) sem valor na execução: {', '.join(unbound)}",
                      "HAWS-BIND-01")
    for c in (graph or {}).get("contexts", []):
        if c["key"] == "region" and c["state"] == "known" and c.get("value") != cfg.region:
            return finish("UNKNOWN", "UNKNOWN_INPUT: região do contexto do grafo difere da região da execução",
                          "HAWS-REGION-01")
    # 1. execução real exige o kit completo: redator do SAFETY e allowlist de contas não vazia
    if isinstance(backend, TerraformCLIBackend):
        if sink.red.kit_fn is None:
            return finish("INFRA_ERROR", "execução real sem o redator do kit de segurança; nada foi criado",
                          "HAWS-IDENT-01")
        if not kit.allowed_account_ids():
            return finish("INFRA_ERROR", "allowlist de contas vazia; nada foi criado", "HAWS-IDENT-01")
    # identidade efetiva
    ident = kit.identity_check()
    if not ident.get("matches_allowlist"):
        return finish("INFRA_ERROR", "identidade efetiva fora da allowlist; nada foi criado", "HAWS-IDENT-01")
    # 2. intenção antes de criar
    t0 = now()
    for r in entry["resources"]:
        f = kit.intent_fields(r["resource_type"])
        intent = {"intent_id": f"INT-{cfg.run_id[4:]}-{r['node_id']}", "module": cfg.module, "provider": PROVIDER,
                  "batch_id": cfg.batch_id, "case_id": cfg.case["case_id"], "resource_type": r["resource_type"],
                  "logical_name": _logical_name(cfg, r["node_id"]), "recorded_at": iso(t0),
                  "effective_identity_check": ident,
                  "purge_deadline": iso(t0 + timedelta(hours=f["purge_hours"])),
                  "max_residual_cost": {"amount": f["max_residual_cost_usd"], "currency": "USD"},
                  "tag_supported": f["tag_supported"], "ttl_supported": f["ttl_supported"]}
        if f["tag_supported"]:
            intent["tags"] = {"bo-run": cfg.run_id, "bo-case": cfg.case["case_id"]}
        if f["ttl_supported"]:
            intent["ttl_hours"] = int(f["ttl_hours"])
        res.intents.append(intent)
    sink.append("intent_manifest.jsonl", "intent_manifest", res.intents)
    seq = [0]

    def stage(name, note=None, with_ident=False):
        rows = []
        for it in res.intents:
            seq[0] += 1
            row = {"run_id": f"{cfg.run_id}-{seq[0]:03d}", "intent_id": it["intent_id"], "stage": name,
                   "at": iso(now()), "visibility": "public"}
            if with_ident:
                row["effective_identity_check"] = kit.identity_check()
            if note:
                row["note"] = note
            rows.append(row)
        res.runs += rows
        sink.append("run_manifest.jsonl", "run_manifest", rows)

    stage("intent")
    # 3. diretório efêmero
    eroot = Path(kit.ephemeral_root())
    work = eroot / f"{cfg.run_id}-{plan_id}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, mode=0o700)
    tfvars = {"bo_region": cfg.region, "bo_run_id": cfg.run_id, "bo_case_id": cfg.case["case_id"],
              "bo_allowed_account_ids": list(kit.allowed_account_ids())}
    for v in entry["variables"]:
        tfvars[v["name"]] = secrets.token_urlsafe(24) if v["kind"] == "secret" else cfg.bindings[v["symbol_id"]]
    rb_id = f"RB-{cfg.run_id[4:]}-{cfg.case['case_id'][5:]}"
    applied = False
    try:
        for f in render.TEMPLATE_FILES + (entry["file"],):
            shutil.copyfile(render_dir / f, work / f)
        # 4. init + apply
        st = backend.init(work)
        if not st.ok:
            v, txt = classify(st.diagnostics or [{"severity": "error", "summary": "init falhou"}])
            return finish("INFRA_ERROR", redact.scrub_text(f"init: {txt}")[:400], "HAWS-APPLY-01")
        stage("creating")
        applied = True
        st = backend.apply(work, tfvars)
        if not st.ok:
            v, txt = classify(st.diagnostics)
            return finish(v, redact.scrub_text(f"apply: {txt}")[:400] or "apply falhou sem diagnóstico",
                          "HAWS-APPLY-01")
        stage("created", with_ident=True)
        # 5. espera por duas leituras iguais
        deadline = clock() + cfg.wait_timeout_s
        last, stable, show = None, False, {}
        while True:
            show = backend.read(work, tfvars)
            if "$error" in show:
                v, txt = classify(show["$error"])
                return finish("INFRA_ERROR" if v != "REJECTED_BY_API" else "NOT_READABLE",
                              redact.scrub_text(f"leitura: {txt}")[:400], "HAWS-WAIT-01")
            rb, comps = build_readback(cfg, plan, entry, show, schema, rb_id)
            snap = json.dumps(rb["fields"], sort_keys=True)
            if snap == last:
                stable = True
                break
            last = snap
            if clock() >= deadline:
                break
            sleep(cfg.poll_interval_s)
        stage("confirmed", with_ident=True)
        # 6. leitura gravada (redigida)
        res.readback = rb
        sink.append("readback.jsonl", "readback", [rb])
        if not stable:
            return finish("UNKNOWN", "leitura não estabilizou na janela de espera", "HAWS-WAIT-01", rb_id)
        # 7. desfecho
        value, detail = judge(cfg, comps, plan, entry["record"].get("references", []))
        return finish(value, detail, "HAWS-JUDGE-01", rb_id)
    finally:
        # 8. destroy sempre que algo pode ter sido criado
        if not applied:
            stage("absent", note="nada foi criado (parou antes do apply)")
        else:
            stage("removal_requested")
            d = backend.destroy(work, tfvars)
            left = backend.state_list(work)
            if d.ok and not left:
                stage("absent", note="terraform destroy ok e state vazio")
            else:
                stage("removal_pending", note=redact.scrub_text(
                    f"destroy ok={d.ok}; {len(left)} endereço(s) no state; teardown do kit deve reconciliar"))
                res.notes.append("resíduo pendente: teardown e varredura do kit (SAFETY) obrigatórios")
        res.calls = list(getattr(backend, "calls", []))
        tfvars.clear()
        shutil.rmtree(work, ignore_errors=True)


def _logical_name(cfg: RunConfig, node: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"bo-{cfg.case['case_id'][5:]}-{node}".lower()).strip("-")
    return base[:43].rstrip("-")


# ------------------------------------------------------------------------------------------ demonstração offline
def fixtures_dir() -> Path:
    return pins.repo_root() / "tests" / "harness" / "aws" / "fixtures"


def demo_case(plan: dict, graph: dict) -> dict:
    cid = graph["case_id"]
    return {"case_id": cid, "group_id": "G-" + cid[5:], "claim_id": "CLM-HAWS-" + cid[-6:].replace("-", ""),
            "claim_version_id": "CLM-HAWS-" + cid[-6:].replace("-", "") + "@1", "comparator": {"name": "exact"},
            "cost_class": "low", "origin": "sample", "side": "object",
            "lowering_plan": {"graph_id": plan["graph_id"], "plan_id": plan["plan_id"]}}


def offline_demo(out: Path) -> dict:
    """Roda os casos com gravação em fixtures/recorded/<plan_id>*.json. Devolve o resumo por caso."""
    fx = fixtures_dir()
    rdir = pins.tmp_root() / "demo_render"
    render.render_file(fx / "plans" / "lowering_plan.jsonl", rdir)
    plans = {p["plan_id"]: p for p in render.read_jsonl(fx / "plans" / "lowering_plan.jsonl")}
    graphs = {g["graph_id"]: g for g in render.read_jsonl(fx / "plans" / "graph_ir.jsonl")}
    schema = sch.load(None)
    kit = OfflineKit(schema)
    if out.exists():
        shutil.rmtree(out)
    sink = Sink(out, kit.redactor())
    summary = []
    for rec_path in sorted((fx / "recorded").glob("*.json")):
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        plan = plans[rec["plan_id"]]
        graph = graphs[plan["graph_id"]]
        case = demo_case(plan, graph)
        case["case_id"] = rec.get("case_id", case["case_id"])
        cfg = RunConfig(run_id=rec["run_id"], batch_id="B-HAWS-OFFLINE", region=rec.get("region", "sa-east-1"),
                        case=case, bindings=rec.get("bindings", {}), wait_timeout_s=60, poll_interval_s=5)
        t = [0.0]
        r = execute(rdir, plan["plan_id"], cfg, RecordedBackend(rec), kit, sink, graph,
                    sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
        summary.append({"recording": rec_path.name, "plan_id": plan["plan_id"], "case_id": cfg.case["case_id"],
                        "outcome": r.outcome["outcome"]["value"], "expect": rec.get("expect"),
                        "calls": r.calls, "runs": len(r.runs), "intents": len(r.intents)})
    shutil.rmtree(rdir, ignore_errors=True)
    return {"written": sink.written, "cases": summary, "redactor": kit.redactor().ids}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bo.harness.aws.executor")
    ap.add_argument("--offline-demo", action="store_true", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else pins.data_root() / MODULE_ID / "offline_run"
    rep = offline_demo(out)
    bad = [c for c in rep["cases"] if c["expect"] and c["expect"] != c["outcome"]]
    for c in rep["cases"]:
        print(f"  {c['recording']:34} {c['plan_id']:14} {c['outcome']:16} esperado={c['expect']} "
              f"chamadas={','.join(c['calls']) or '-'}")
    print(f"executor offline: {len(rep['cases'])} caso(s), {len(bad)} fora do esperado; gravado {rep['written']} "
          f"em {out} (redator: {', '.join(rep['redactor'])})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
