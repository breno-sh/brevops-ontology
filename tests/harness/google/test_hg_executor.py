"""Executor com respostas gravadas: ordem das travas, redator antes de gravar, desfechos do C12 e resíduo."""
import json
import uuid

import pytest

from bo.harness.google import common as C
from bo.harness.google import executor as X
from conftest import case_for, load_fixture, recorded

BIND_SQL = {"SYM-1a2b3c4d5e6f": "bo-hgnet", "SYM-2b3c4d5e6f70": "bo-hgdb"}
BIND_FW = {"SYM-3c4d5e6f7081": "bo-hgfw", "SYM-4d5e6f708192": "bo-hgsub"}


class Intent:
    def __init__(self, fail_on=None):
        self.log, self.fail_on = [], fail_on

    def __call__(self, stage, run_id, case_id, addresses):
        if stage == self.fail_on:
            raise OSError("disco cheio")
        self.log.append(stage)
        return True


def make(recording, *, identity=True, intent=None, **kw):
    runner = X.RecordedRunner(recorded(recording))
    order = []
    for m in ("init", "apply", "destroy"):
        f = getattr(runner, m)
        setattr(runner, m, (lambda f, m: lambda *a: (order.append("runner:" + m), f(*a))[1])(f, m))
    it = intent or Intent()

    def ident():
        order.append("identity")
        return identity

    def intent_spy(stage, *a):
        order.append("intent:" + stage)
        return it(stage, *a)
    ex = X.Executor(runner, identity_guard=ident, intent=intent_spy, run_id="t-" + uuid.uuid4().hex[:8],
                    sleep=lambda s: order.append(f"sleep:{s}"), wait_s=30, read_interval_s=15,
                    allow_disk_ephemeral=True, **kw)
    return ex, runner, order, it


def run(recording, fixture="net_sql", bindings=None, ctx=None, comparator=None, **kw):
    plan, graph = load_fixture(fixture)
    ex, runner, order, it = make(recording, **kw)
    r = ex.run_case(case_for(plan, comparator), plan, graph, bindings=BIND_SQL if bindings is None else bindings,
                    runtime_context=ctx or {"region": "us-central1"})
    return r, ex, runner, order, it


def test_persistido_ordem_redacao_e_saida_c12(work):
    r, ex, runner, order, it = run("netsql_persisted.json")
    assert r.outcome["outcome"]["value"] == "PERSISTED", r.outcome
    assert r.outcome["evidence_state_after"] == "PERSISTENCE_VERIFIED"
    assert order == ["identity", "intent:intent", "runner:init", "runner:apply", "intent:created", "sleep:30",
                     "sleep:15", "intent:removal_requested", "runner:destroy", "intent:verified_absent"]
    assert runner.calls == ["init", "apply", "read", "read", "destroy", "read"]
    assert it.log == ["intent", "created", "removal_requested", "verified_absent"]
    fields = {f["path"]: f for f in r.readback["fields"]}
    rp = fields["r1.root_password"]
    assert rp["state"] == "withheld" and "value" not in rp and rp["redaction"]["rule_id"] == "REDACT-SECRET-01"
    assert fields["r1.settings.backup_configuration.backup_retention_settings.retained_backups"]["value"] == 7
    secret = runner.env_seen["TF_VAR_lp_hg_netsql_r1_secret_root_password"]
    paths = ex.write([r], work / "c12")
    for p in list(paths.values()) + [str(work / "c12" / "run_events.jsonl")]:
        assert secret not in open(p).read()
    assert C.validate("C12", work / "c12" / "readback.jsonl") == []
    assert C.validate("C12", work / "c12" / "outcomes.jsonl") == []
    assert not (C.tmp() / "ephemeral" / ex.run_id / r.case_id).exists()


@pytest.mark.parametrize("rec,value,detail", [
    ("netsql_altered.json", "ALTERED", "retained_backups"),
    ("netsql_api400.json", "REJECTED_BY_API", "API-400"),
    ("netsql_quota.json", "INFRA_ERROR", "INFRA-QUOTA"),
    ("netsql_unclassified.json", "UNKNOWN", "UNCLASSIFIED"),
    ("netsql_unstable.json", "UNKNOWN", "leituras sucessivas"),
    ("netsql_not_read.json", "NOT_READABLE", "settings.edition"),
])
def test_desfechos(rec, value, detail):
    r, ex, runner, order, it = run(rec)
    assert r.outcome["outcome"]["value"] == value and detail in r.outcome["outcome"]["detail"], r.outcome
    assert r.outcome["evidence_state_after"] == r.outcome["evidence_state_before"]
    assert "destroy" in runner.calls and it.log[-1] == "verified_absent"


def test_bloco_set_e_referencia_conferem():
    r, *_ = run("netfw_persisted.json", fixture="net_fw", bindings=BIND_FW)
    assert r.outcome["outcome"]["value"] == "PERSISTED", r.outcome


def test_residuo_vira_erro_e_e_registrado(work):
    r, ex, runner, order, it = run("netsql_residue.json")
    assert r.residue == ["google_sql_database_instance.lp_hg_netsql_r1"] and "residue" in it.log
    with pytest.raises(X.ResidueError):
        ex.write([r], work / "c12")
    assert (work / "c12" / "outcomes.jsonl").exists()


def test_identidade_fora_da_allowlist_aborta_antes_de_tudo():
    with pytest.raises(X.IdentityRefused):
        run("netsql_persisted.json", identity=False)


def test_identidade_recusada_nao_chama_o_runner():
    plan, graph = load_fixture("net_sql")
    ex, runner, order, it = make("netsql_persisted.json", identity=False)
    with pytest.raises(X.IdentityRefused):
        ex.run_case(case_for(plan), plan, graph, bindings=BIND_SQL, runtime_context={})
    assert runner.calls == [] and it.log == []


def test_intencao_nao_gravada_impede_o_apply():
    plan, graph = load_fixture("net_sql")
    ex, runner, order, it = make("netsql_persisted.json", intent=Intent(fail_on="intent"))
    with pytest.raises(X.IntentNotRecorded):
        ex.run_case(case_for(plan), plan, graph, bindings=BIND_SQL, runtime_context={})
    assert "apply" not in runner.calls


def test_simbolo_sem_valor_sintetico_e_unknown_input_sem_apply():
    r, ex, runner, order, it = run("netsql_persisted.json", bindings={"SYM-1a2b3c4d5e6f": "bo-hgnet"})
    assert r.outcome["outcome"]["value"] == "UNKNOWN" and "UNKNOWN_INPUT" in r.outcome["outcome"]["detail"]
    assert runner.calls == [] and "identity" not in order


def test_plano_reprovado_nao_chega_ao_runner():
    plan = C.read_jsonl(C.repo() / "contracts" / "stubs" / "C26" / "lowering_plan.jsonl")[0]
    graph = C.read_jsonl(C.repo() / "contracts" / "stubs" / "C26" / "graph_ir.jsonl")[0]
    ex, runner, order, it = make("netsql_persisted.json")
    r = ex.run_case(case_for(plan), plan, graph, bindings={}, runtime_context={})
    assert r.outcome["outcome"]["value"] == "UNKNOWN" and r.outcome["outcome"]["detail"].startswith("UNKNOWN_INPUT")
    assert runner.calls == [] and order == []


def test_simbolo_em_campo_secreto_e_recusado():
    from bo.harness.google import render as R
    plan, graph = load_fixture("net_sql")
    plan["plan_id"] = "LP-SECRET-X"
    plan["steps"][1]["values"][4]["term"] = {"kind": "symbol", "symbol_id": "SYM-0a0b0c0d0e0f",
                                             "name_class": "variable", "scope": "repo"}
    r = R.render_plan(plan, graph, R.Schema.load())
    assert "WITHHELD_LITERAL" in [f["code"] for f in r.failures]


def test_guarda_adiada_sem_contexto_nao_aplica():
    r, ex, runner, order, it = run("netsql_persisted.json", fixture="kms_pubsub", bindings={}, ctx={"region": None})
    assert r.outcome["outcome"]["value"] == "UNKNOWN" and "INDETERMINATE" in r.outcome["outcome"]["detail"]
    assert runner.calls == []


def test_canal_efemero_em_disco_so_no_modo_offline():
    plan, graph = load_fixture("net_sql")
    ex, runner, order, it = make("netsql_persisted.json")
    ex.allow_disk_ephemeral = False
    with pytest.raises(X.CloudForbidden):
        ex.run_case(case_for(plan), plan, graph, bindings=BIND_SQL, runtime_context={})
    assert "apply" not in runner.calls


def test_diretorio_do_caso_e_exclusivo():
    plan, graph = load_fixture("net_sql")
    ex, runner, order, it = make("netsql_persisted.json")
    ex.run_case(case_for(plan), plan, graph, bindings=BIND_SQL, runtime_context={})
    with pytest.raises(FileExistsError):
        ex.run_case(case_for(plan), plan, graph, bindings=BIND_SQL, runtime_context={})
    assert str(ex.root).startswith(str(C.tmp()))


def test_runner_do_terraform_recusa_nuvem_sem_autorizacao(work):
    tr = X.TerraformRunner()
    for call in (tr.apply, tr.destroy, tr.refresh_show):
        with pytest.raises(X.CloudForbidden):
            call(work, work, {})
    auth = X.CloudAuthorization("r", "go-123", work / "cloud-google", identity_checked=True)
    with pytest.raises(X.CloudForbidden):          # sem BO_CLOUD_GO e sem trava
        X.TerraformRunner(authorization=auth).apply(work, work, {})


def test_classificacao_de_erros():
    assert X.classify_error("googleapi: Error 403: PERMISSION_DENIED")[1] == "INFRA_ERROR"
    assert X.classify_error('expected tier to be one of ["a"]')[1] == "REJECTED_BY_API"
    assert X.classify_error("Error: Missing required argument")[:2] == ("TF-CONFIG", "UNKNOWN")
    assert X.classify_error("nada conhecido")[1] == "UNKNOWN"


def test_bo_tmp_alheio_e_recusado(monkeypatch):
    monkeypatch.setenv("BO_TMP", str(C.data() / "tmp" / "HARNESS-AWS"))
    with pytest.raises(SystemExit):
        C.tmp()
    monkeypatch.setenv("BO_TMP", "/tmp/HARNESS-GCP")
    with pytest.raises(SystemExit):
        C.tmp()


def test_canario_recusa_registro_com_segredo():
    from bo.harness.google.redact import GoogleRedactor, RedactionError
    from bo.harness.google.render import Schema
    rd = GoogleRedactor(Schema.load())
    rd.register_secret("segredo-de-teste-xyz")
    with pytest.raises(RedactionError):
        rd.assert_clean({"x": ["prefixo segredo-de-teste-xyz sufixo"]})
    rd.assert_clean({"x": "limpo"})
    assert json.dumps({}) == "{}"
