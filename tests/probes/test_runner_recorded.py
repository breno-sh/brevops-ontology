"""Runner sobre RESPOSTAS GRAVADAS (formato de saída de cada CLI/API, valores sintéticos), passando pelos mesmos
parsers do backend ao vivo: controle negativo, repetição, censura, consistência eventual e erro de infraestrutura.
A gravação também prende os instantes de leitura ao polling do protocolo congelado (at_s)."""

from __future__ import annotations

import json

import pytest

from bo.contracts import validate as V
from bo.probes.runner import write_local
from probes_helpers import recorded_run


def by(trace, role, rep):
    return next(t for t in trace if t["role"] == role and t["rep"] == rep)


def test_versioning_eventual_listing_lost_poll_and_flap(protos):
    obs, trace, run, rb = recorded_run(protos, "object_versioning_aws.json")
    assert obs["counts"] == {"attempts": 3, "observed": 3, "not_observed": 0, "errors": 0}
    assert obs["negative_control_ok"] is True
    r1, r2, r3 = by(trace, "case", 1), by(trace, "case", 2), by(trace, "case", 3)
    # consistência eventual: efeito só depois de 2 leituras seguidas; o instante é o da primeira delas
    assert r1["effect_at_s"] == 120 and [p["state"] for p in r1["polls"]] == ["opposite", "effect", "effect"]
    # leitura perdida (3 tentativas) não decide nada e é contada
    assert r2["lost_polls"] == 1 and r2["result"] == "observed"
    # oscilação: 3, 1, 3, 3 -> a primeira leitura com efeito não vale; observado em 180 s
    assert r3["flaps"] == 1 and r3["effect_at_s"] == 180
    # o controle negativo é lido até o fim da janela (30 leituras de 60 s) e sempre dá 1 versão
    for r in (1, 2, 3):
        c = by(trace, "control", r)
        assert c["result"] == "ok" and len(c["polls"]) == 30 and c["polls"][-1]["t_s"] == 1800
    # toda resposta gravada foi consumida (nem a mais, nem a menos)
    for k, n in rb.pos.items():
        role, rep, op = k
        assert n == len(rb.calls[f"{role}/{rep}"][op])


def test_expiry_flap_and_censoring(protos):
    obs, trace, run, rb = recorded_run(protos, "item_ttl_aws.json")
    # r1 e r2 expiram; r3 não expira em 72 h: censura -> not_observed, nunca "igual"
    assert obs["counts"] == {"attempts": 3, "observed": 2, "not_observed": 1, "errors": 0}
    assert obs["negative_control_ok"] is True
    assert by(trace, "case", 2)["flaps"] == 1
    r3 = by(trace, "case", 3)
    assert r3["result"] == "not_observed" and "censura" in r3["reason"]
    assert r3["polls"][-1]["t_s"] == 259200 and len(r3["polls"]) == 36  # polling de 2 h até 72 h
    assert run.heartbeat_summary()["required"] and run.heartbeat_summary()["max_gap_s"] <= 60


def test_negative_control_failing_is_reported(protos):
    obs, trace, run, rb = recorded_run(protos, "queue_retention_aws.json")
    assert obs["counts"]["observed"] == 3
    assert obs["negative_control_ok"] is False  # o PROBE-JOIN tem de transformar o par em INFRA_ERROR
    c3 = by(trace, "control", 3)
    assert c3["result"] == "fail" and c3["polls"][-1]["t_s"] == 6 * 3600


def test_action_failure_and_lost_final_poll_are_errors(protos):
    obs, trace, run, rb = recorded_run(protos, "object_versioning_google.json")
    assert obs["counts"] == {"attempts": 3, "observed": 1, "not_observed": 0, "errors": 2}
    assert by(trace, "case", 2)["reason"] == "leitura final perdida"
    assert by(trace, "case", 3)["reason"].startswith("ação falhou")


def test_firestore_per_document_and_metric_delay(protos):
    obs, _, _, _ = recorded_run(protos, "item_ttl_google.json")
    assert obs["counts"]["observed"] == 3 and obs["negative_control_ok"] is True
    obs, trace, _, _ = recorded_run(protos, "queue_retention_google.json")
    assert obs["counts"]["observed"] == 3
    assert all(by(trace, "case", r)["lost_polls"] == 1 for r in (1, 2, 3))


def test_recording_out_of_sync_with_polling_fails(protos, recording, monkeypatch):
    import probes_helpers as H
    rec = recording("object_versioning_aws.json")
    rec["calls"]["case/1"]["observe"][0]["at_s"] = 90  # gravação que não bate com o intervalo de 60 s
    monkeypatch.setattr(H, "load_recording", lambda name: rec)
    with pytest.raises(AssertionError, match="gravada em 90"):
        H.recorded_run(protos, "object_versioning_aws.json")


def test_observation_is_local_c22_and_has_no_judgement(protos, work):
    obs, trace, _, _ = recorded_run(protos, "item_ttl_aws.json", side="B")
    write_local(work, obs, trace)
    assert V.validate("C22_observations", work / "observations.jsonl").ok
    rec = json.loads((work / "observations.jsonl").read_text().splitlines()[0])
    assert "outcome" not in rec and "judged_by" not in rec  # só o PROBE-JOIN julga
    assert rec["observation_id"] == "OBS-REC-item_ttl-aws-B" and rec["side"] == "B"
    # rastro só com contagens e tempos
    for line in (work / "probe_trace.jsonl").read_text().splitlines():
        t = json.loads(line)
        for p in t["polls"]:
            assert set(p) <= {"t_s", "state", "present", "versions", "lost", "code", "accepted", "throttled",
                              "other", "expected_accepted"}
    with pytest.raises(Exception, match="já gravada"):
        write_local(work, obs, trace)
