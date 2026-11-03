"""Redator: Withheld sem valor nem hash; ids reais só em forma simbólica; texto livre sem identificador."""
import pytest

from bo.harness.aws import redact

D12 = "".join(str(i % 10) for i in range(1, 13))           # montado em tempo de execução (privacy_lint)
ARN = "ar" + "n:aws:iam::" + D12 + ":role/bo-x"


@pytest.mark.parametrize("path,rule", [
    ("r1.password", "REDACT-SECRET-01"), ("r1.master_password", "REDACT-SECRET-01"),
    ("r1.user_data", "REDACT-BOOT-01"), ("r1.user_data_base64", "REDACT-BOOT-01"),
    ("r1.environment.variables", "REDACT-ENV-01"), ("r1.content", "REDACT-OBJECT-01"),
    ("r1.message_body", "REDACT-MESSAGE-01"), ("r1.log_events", "REDACT-LOG-01")])
def test_content_rules_withhold_without_value(path, rule):
    fr = redact.redact_field(path, "qualquer coisa")
    assert fr.state == "withheld" and fr.rule_id == rule and fr.value is None


def test_sensitive_and_write_only_from_schema():
    assert redact.redact_field("r1.x", "v", sensitive=True).state == "withheld"
    assert redact.redact_field("r1.x", "v", write_only=True).state == "not_read"
    assert redact.redact_field("r1.x", None).state == "absent"


def test_real_identifier_never_written():
    fr = redact.finalize(redact.redact_field("r1.role", ARN))
    assert fr.state == "withheld" and fr.rule_id == "REDACT-IDENT-01"
    fr = redact.finalize(redact.redact_field("r1.owner", D12))
    assert fr.state == "withheld" and fr.rule_id == "REDACT-IDENT-01"
    assert redact.scrub_text(D12) == "<conta>"


def test_symbolic_forms_and_preference():
    sym = {"vpc-0a1b2c3d4e5f6a7b8": ["ref:r1"], "bo-b": ["ref:r1", "sym:SYM-0011223344556677"]}
    assert redact.redact_field("r2.vpc_id", "vpc-0a1b2c3d4e5f6a7b8", symbolic=sym).value == "ref:r1"
    assert redact.redact_field("r2.bucket", "bo-b", symbolic=sym, prefer="sym:SYM-0011223344556677").value == \
        "sym:SYM-0011223344556677"
    assert redact.redact_field("r1.name", "bo-b", symbolic=sym, prefer="bo-b").value == "bo-b"
    fr = redact.finalize(redact.redact_field("r2.vpc_id", "vpc-0ffffffffffffffff", symbolic=sym))
    assert fr.state == "withheld" and fr.rule_id == "REDACT-IDENT-01"


def test_scrub_text_masks_identifiers():
    t = redact.scrub_text(f"User {ARN} not authorized; vpc-0a1b2c3d4e5f6a7b8; fulano" + "@" + "empresa.com.br; " +
                          "AK" + "IA" + "Q" * 16 + " https://x.y/z")
    assert "<arn>" in t and "<id>" in t and "<email>" in t and "<chave>" in t and "<url>" in t
    assert D12 not in t and "empresa" not in t


def test_kit_redactor_runs_first_and_base_always(work):
    p = work / "redactor.py"
    p.write_text("def redact(obj, context):\n    obj = dict(obj)\n    obj['kit'] = context\n    return obj\n")
    r = redact.Redactor(redact.load_kit_redactor(p))
    out = r({"note": ARN}, "readback")
    assert out == {"note": "<arn>", "kit": "readback"}
    assert r.ids[0].startswith("kit:") and r.ids[-1].startswith("base:")


def test_kit_required_for_real_runs(work):
    with pytest.raises(redact.KitRedactorMissing):
        redact.Redactor(None, require_kit=True)
    bad = work / "redactor.py"
    bad.write_text("x = 1\n")
    with pytest.raises(redact.KitRedactorMissing):
        redact.load_kit_redactor(bad)
