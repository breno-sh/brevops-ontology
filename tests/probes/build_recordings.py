"""Gera as respostas gravadas SINTÉTICAS de tests/probes/recorded/ (rode uma vez; os JSON ficam versionados).

  python -I tests/probes/build_recordings.py

Cada resposta segue o formato de saída JSON documentado da CLI/API do caso (aws s3api, gcloud storage, az storage,
oci os, aws dynamodb, aws sqs, Firestore REST, Cloud Monitoring REST), com valores inventados: nenhum nome de
recurso, conta, projeto ou conteúdo real. Os instantes (at_s) são os do polling do protocolo congelado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "recorded"
SRC = Path(__file__).resolve().parents[2] / "src"


def ticks(interval: float, max_wait: float) -> list[float]:
    n = int(max_wait // interval)
    t = [i * interval for i in range(1, n + 1)]
    if not t or t[-1] < max_wait:
        t.append(max_wait)
    return t


def cli(obj) -> dict:
    return {"rc": 0, "stdout": json.dumps(obj)}


FAIL = {"rc": 254, "stdout": ""}


def aws_versions(key: str, n: int) -> dict:
    vs = [{"Key": key, "VersionId": f"v{i}", "IsLatest": i == n, "Size": 1024} for i in range(1, n + 1)]
    return cli({"Versions": vs, "Name": "bo-synthetic"})


def gcs_versions(key: str, n: int) -> dict:
    return cli([{"name": key, "generation": str(1000 + i), "size": 1024} for i in range(1, n + 1)])


def az_versions(key: str, n: int) -> dict:
    return cli([{"name": key, "versionId": f"2026-11-04T12:0{i}:00.0000000Z", "isCurrentVersion": i == n}
                for i in range(1, n + 1)])


def az_versions_or_plain(key: str, n: int) -> dict:
    """Com 1 versão (controle sem versionamento) o blob atual vem com versionId nulo."""
    if n == 1:
        return cli([{"name": key, "versionId": None, "isCurrentVersion": None}])
    return az_versions(key, n)


NO_MATCH = {"rc": 1, "stdout": "", "stderr_tail": "ERROR: (gcloud.storage.objects.list) One or more URLs matched no "
                                                  "objects."}


def oci_versions(key: str, n: int) -> dict:
    return cli({"data": {"items": [{"name": key, "version-id": f"v{i}", "size": 1024} for i in range(1, n + 1)]},
                "prefixes": []})


def dynamo_count(n: int) -> dict:
    return cli({"Count": n, "ScannedCount": n, "ConsumedCapacity": None})


def sqs_attrs(n: int) -> dict:
    return cli({"Attributes": {"ApproximateNumberOfMessages": str(n), "ApproximateNumberOfMessagesNotVisible": "0",
                               "ApproximateNumberOfMessagesDelayed": "0"}})


def monitoring(n: int | None) -> dict:
    if n is None:
        return {"status": 200, "body": {}}
    return {"status": 200, "body": {"timeSeries": [{"metric": {"type": "pubsub.googleapis.com/subscription/"
                                                                       "num_undelivered_messages"},
                                                    "points": [{"interval": {"endTime": "2026-11-04T12:00:00Z"},
                                                                "value": {"int64Value": str(n)}}]}]}}


def firestore(present: list[bool]) -> list[dict]:
    return [{"status": 200, "body": {"name": "synthetic"}} if p else {"status": 404, "body": None} for p in present]


def s3_keycount(n: int) -> dict:
    return cli({"KeyCount": n, "Contents": [{"Key": f"k{i}", "Size": 1024} for i in range(n)]})


def gcs_list(prefix: str, n: int) -> dict:
    return cli([{"name": f"{prefix}obj-{i}", "size": 1024} for i in range(1, n + 1)])


def key(role, rep):
    return f"bo-probe/{role}/r{rep}/obj"


def prefix(role, rep):
    return f"bo-probe/{role}/r{rep}/"


def seq(times, fn) -> list[dict]:
    return [{"at_s": t, "raw": fn(i, t)} for i, t in enumerate(times)]


def rec(cell, calls, note):
    return {"schema": "bo.probe_recording/1", "cell": cell, "synthetic": True, "note": note, "calls": calls}


def build() -> dict[str, dict]:
    out = {}
    # ------------------------------------------------ object_versioning/aws: listagem eventual e uma leitura perdida
    T = ticks(60, 1800)
    calls = {}
    for r in (1, 2, 3):
        calls[f"case/{r}"] = {"act": [cli({"VersionId": "v"})]}
    # r1: lista 1 versão, depois 3, 3 -> observado em 120 s (confirmado em 180 s)
    calls["case/1"]["observe"] = seq(T[:3], lambda i, t: aws_versions(key("case", 1), 1 if i == 0 else 3))
    # r2: leitura perdida (3 tentativas falham), depois 3, 3 -> observado
    calls["case/2"]["observe"] = [{"at_s": 60, "raw": FAIL}, {"at_s": 60, "raw": FAIL}, {"at_s": 60, "raw": FAIL}] + \
        seq(T[1:3], lambda i, t: aws_versions(key("case", 2), 3))
    # r3: 3, 1 (oscila), 3, 3 -> observado em 180 s com uma oscilação
    calls["case/3"]["observe"] = seq(T[:4], lambda i, t: aws_versions(key("case", 3), [3, 1, 3, 3][i]))
    for r in (1, 2, 3):
        calls[f"control/{r}"] = {"act": [cli({"VersionId": "null"})],
                                 "observe": seq(T, lambda i, t, r=r: aws_versions(key("control", r), 1))}
    out["object_versioning_aws.json"] = rec("object_versioning/aws", calls,
                                            "consistência eventual, leitura perdida e oscilação; controle com 1 versão")

    # ------------------------------------------------ item_ttl/aws: expiração, oscilação, censura
    T = ticks(7200, 259200)
    calls = {}
    for r in (1, 2, 3):
        calls[f"case/{r}"] = {"act": [[cli({}), cli({}), cli({})]]}
    # r1: some depois de 4 h (3,2,0,0)
    calls["case/1"]["observe"] = seq(T[:4], lambda i, t: dynamo_count([3, 2, 0, 0][i]))
    # r2: 3,0,1 (volta: leitura eventual),0,0 -> uma oscilação, observado
    calls["case/2"]["observe"] = seq(T[:5], lambda i, t: dynamo_count([3, 0, 1, 0, 0][i]))
    # r3: nunca some na janela de 72 h -> censura
    calls["case/3"]["observe"] = seq(T, lambda i, t: dynamo_count(3))
    for r in (1, 2, 3):
        calls[f"control/{r}"] = {"act": [[cli({}), cli({}), cli({})]], "observe": seq(T, lambda i, t: dynamo_count(3))}
    out["item_ttl_aws.json"] = rec("item_ttl/aws", calls, "expiração com oscilação e uma repetição censurada")

    # ------------------------------------------------ queue_retention/aws: controle negativo falho
    T = ticks(3600, 172800)
    calls = {}
    for r in (1, 2, 3):
        calls[f"case/{r}"] = {"act": [[cli({"MessageId": "m"})] * 3],
                              "observe": seq(T[:3], lambda i, t: sqs_attrs([3, 0, 0][i]))}
    for r in (1, 2):
        calls[f"control/{r}"] = {"act": [[cli({"MessageId": "m"})] * 3], "observe": seq(T, lambda i, t: sqs_attrs(3))}
    # controle 3: as mensagens somem com retenção maior que a janela -> controle negativo falho
    calls["control/3"] = {"act": [[cli({"MessageId": "m"})] * 3],
                          "observe": seq(T[:6], lambda i, t: sqs_attrs([3, 3, 3, 3, 0, 0][i]))}
    out["queue_retention_aws.json"] = rec("queue_retention/aws", calls, "controle negativo dá o mesmo efeito do caso")

    # ------------------------------------------------ object_versioning/google: ação falha e leitura final perdida
    T = ticks(60, 1800)
    calls = {"case/1": {"act": [cli([])], "observe": seq(T[:2], lambda i, t: gcs_versions(key("case", 1), 3))},
             # r2: nunca mostra as 3 versões e a leitura final se perde -> erro (não censura)
             "case/2": {"act": [cli([])], "observe": seq(T[:-1], lambda i, t: gcs_versions(key("case", 2), 1))
                        + [{"at_s": T[-1], "raw": FAIL}] * 3},
             # r3: a ação falha nas 3 tentativas -> erro sem leitura
             "case/3": {"act": [FAIL, FAIL, FAIL]}}
    for r in (1, 2, 3):
        calls[f"control/{r}"] = {"act": [cli([])], "observe": seq(T, lambda i, t, r=r: gcs_versions(key("control", r), 1))}
    out["object_versioning_google.json"] = rec("object_versioning/google", calls,
                                               "erro de ação e leitura final perdida viram errors")

    # ------------------------------------------------ item_ttl/google: Firestore REST por item
    T = ticks(7200, 259200)
    calls = {}
    for r in (1, 2, 3):
        calls[f"case/{r}"] = {"act": [[{"status": 200, "body": {}}] * 3],
                              "observe": seq(T[:4], lambda i, t: firestore([[True] * 3, [True, False, False],
                                                                           [False] * 3, [False] * 3][i]))}
        calls[f"control/{r}"] = {"act": [[{"status": 200, "body": {}}] * 3],
                                 "observe": seq(T, lambda i, t: firestore([True] * 3))}
    out["item_ttl_google.json"] = rec("item_ttl/google", calls, "200 presente, 404 ausente, por documento")

    # ------------------------------------------------ queue_retention/google: métrica com atraso
    T = ticks(3600, 172800)
    calls = {}
    for r in (1, 2, 3):
        # primeira leitura sem série (atraso da métrica: leitura perdida), depois 3, 0, 0
        calls[f"case/{r}"] = {"act": [[cli({"messageIds": ["1"]})] * 3],
                              "observe": [{"at_s": 3600, "raw": monitoring(None)}] * 3 +
                              seq(T[1:4], lambda i, t: monitoring([3, 0, 0][i]))}
        calls[f"control/{r}"] = {"act": [[cli({"messageIds": ["1"]})] * 3],
                                 "observe": seq(T, lambda i, t: monitoring(3))}
    out["queue_retention_google.json"] = rec("queue_retention/google", calls, "série ausente = leitura perdida")

    # ------------------------------------------------ versionamento azurerm e oci: corrida inteira
    T = ticks(60, 1800)
    for cell, fn, fname in (("object_versioning/azurerm", az_versions_or_plain, "object_versioning_azurerm.json"),
                            ("object_versioning/oci", oci_versions, "object_versioning_oci.json")):
        calls = {}
        for r in (1, 2, 3):
            calls[f"case/{r}"] = {"act": [cli({})], "observe": seq(T[:3], lambda i, t, r=r, fn=fn:
                                                                   fn(key("case", r), 1 if i == 0 else 3))}
            calls[f"control/{r}"] = {"act": [cli({})], "observe": seq(T, lambda i, t, r=r, fn=fn:
                                                                      fn(key("control", r), 1))}
        out[fname] = rec(cell, calls, "versões aparecem na segunda leitura; controle com versão única")

    # ------------------------------------------------ ciclo de vida aws e google: 72 h, leitura a cada 6 h
    T = ticks(21600, 259200)
    for cell, fn, fname in (("object_lifecycle/aws", lambda role, rep, n: s3_keycount(n), "object_lifecycle_aws.json"),
                            ("object_lifecycle/google", lambda role, rep, n: gcs_list(prefix(role, rep), n) if n
                             else NO_MATCH, "object_lifecycle_google.json")):
        calls = {}
        for r in (1, 2, 3):
            # expira entre 24 h e 36 h (regra de 1 dia + atraso assíncrono do provedor)
            calls[f"case/{r}"] = {"act": [[cli({})] * 3],
                                  "observe": seq(T[:7], lambda i, t, r=r, fn=fn:
                                                 fn("case", r, [3, 3, 3, 3, 1, 0, 0][i]))}
            calls[f"control/{r}"] = {"act": [[cli({})] * 3],
                                     "observe": seq(T, lambda i, t, r=r, fn=fn: fn("control", r, 3))}
        out[fname] = rec(cell, calls, "expiração assíncrona depois de 1 dia; controle sem regra continua com os 3")

    # ------------------------------------------------ parsers soltos (azurerm, oci, lifecycle)
    out["parsers.json"] = {"schema": "bo.probe_recording/1", "synthetic": True, "cell": "*", "calls": {},
                           "parsers": {
                               "object_versioning/azurerm": [[az_versions(key("case", 1), 3), {"versions": 3}],
                                                             [cli([{"name": key("case", 1), "versionId": None,
                                                                    "isCurrentVersion": None}]), {"versions": 1}],
                                                             [cli([{"name": "bo-probe/case/r1/objx"}]),
                                                              {"versions": 0}]],
                               "object_versioning/oci": [[oci_versions(key("case", 1), 2), {"versions": 2}],
                                                         [cli({"data": []}), {"versions": 0}]],
                               "object_lifecycle/aws": [[s3_keycount(2), {"present": 2}],
                                                        [cli({"Name": "bo-synthetic"}), {"present": 0}]],
                               "object_lifecycle/google": [[gcs_list(prefix("case", 1), 3), {"present": 3}],
                                                           [cli([]), {"present": 0}],
                                                           [{"rc": 1, "stdout": "", "stderr_tail":
                                                             "ERROR: (gcloud.storage.objects.list) One or more URLs "
                                                             "matched no objects."}, {"present": 0}]],
                               "object_versioning/aws": [[aws_versions(key("case", 1), 3), {"versions": 3}],
                                                         [aws_versions("bo-probe/case/r1/obj-outra", 2),
                                                          {"versions": 0}]],
                           },
                           "parse_errors": {
                               "object_versioning/aws": [FAIL, {"rc": 0, "stdout": "não é json"}],
                               "item_ttl/aws": [cli({"ScannedCount": 1})],
                               "queue_retention/aws": [cli({"Attributes": {}})],
                               "queue_retention/google": [monitoring(None), {"status": 503, "body": None}],
                               "object_lifecycle/google": [{"rc": 1, "stdout": "", "stderr_tail":
                                                            "ERROR: (gcloud.storage.objects.list) 403 Forbidden"}],
                           }}
    return out


def main() -> int:
    HERE.mkdir(parents=True, exist_ok=True)
    for name, doc in build().items():
        (HERE / name).write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("gravado", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
