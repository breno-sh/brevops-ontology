"""Conferência independente com o provider fixado: terraform validate offline concorda com cada estado."""
from bo.harness.aws import tf_validate


def test_terraform_validate_agrees_with_renderer(rendered, work):
    out, _ = rendered
    rep = tf_validate.validate_render(out, work / "tfv")
    by = {p["plan_id"]: p for p in rep["plans"]}
    assert rep["agree"], [(p["plan_id"], p["diagnostics"]) for p in rep["plans"] if not p["agree"]]
    assert all(by[k]["terraform_valid"] for k in ("LP-AWS-NET-01", "LP-AWS-STO-01", "LP-AWS-DB-02", "LP-AWS-SEC-02"))
    assert by["LP-AWS-DB-01"]["terraform_missing"] == ["instance_class"]
    assert not (work / "tfv").exists()


def test_sandbox_env_has_no_credentials(work):
    env = tf_validate.sandbox_env(work)
    assert not any(k.startswith(("AWS_", "GOOGLE_", "ARM_", "OCI_")) for k in env)
    assert env["HOME"].startswith(str(work))
