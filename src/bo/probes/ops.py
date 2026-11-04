"""Operações de plano de dados por caso validado e os parsers das respostas.

Cada caso (tipo/provedor) declara:
  act      o que a repetição faz (gravar a mesma chave W vezes; criar N objetos/itens/mensagens sintéticos)
  observe  a leitura que conta (versões da chave; quantos dos N ainda existem), sem consumir nada
Uma operação é CLI (argv) ou REST (método, URL, corpo); os {marcadores} vêm de:
  alvos da implantação  bucket, account, container, table, queue_url, topic, subscription, project, database,
                        region (entregues pelo PROBE-* em memória; nunca gravados)
  do runner             key, prefix, i, pk, n, expire_epoch, expire_iso, payload_file, now_utc, since_utc
O parser só devolve contagens ({"versions": n} ou {"present": n}); a resposta crua nunca sai da memória.
Formatos de resposta: os da saída JSON documentada de cada CLI/API; o SMOKE confere na primeira execução real
(respostas gravadas em tests/probes/recorded/ seguem esses formatos, com valores sintéticos).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .common import ProbeError


class ParseError(ValueError):
    code = "PARSE"


@dataclass(frozen=True)
class Op:
    kind: str                    # cli | http
    argv: tuple = ()             # cli
    method: str = "GET"          # http
    url: str = ""                # http
    body: dict | None = None     # http (marcadores em strings)
    per_item: bool = False       # a operação roda uma vez por item i = 1..N
    repeat: str = ""             # "writes": a ação roda W vezes com a mesma chave
    parse: object = None         # resposta crua -> contagem (observe)
    ok_status: tuple = (200,)    # http: status de sucesso (observe por item: 404 também é resposta válida)

    def render(self, ctx: dict) -> dict:
        def sub(x):
            if isinstance(x, str):
                try:
                    return x.format(**ctx)
                except KeyError as e:
                    raise ProbeError(f"marcador {e} sem valor na operação", "OP") from None
            if isinstance(x, dict):
                return {k: sub(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [sub(v) for v in x]
            return x
        if self.kind == "cli":
            return {"kind": "cli", "argv": [sub(a) for a in self.argv]}
        return {"kind": "http", "method": self.method, "url": sub(self.url), "body": sub(self.body)}


# ------------------------------------------------------------------------------------------------ parsers
def _stdout_json(raw: dict):
    if not isinstance(raw, dict) or raw.get("rc") != 0:
        raise ParseError("comando saiu com erro")
    try:
        return json.loads(raw.get("stdout") or "null")
    except json.JSONDecodeError:
        raise ParseError("saída não é JSON") from None


def _http_json(raw: dict, ok=(200,)):
    if not isinstance(raw, dict) or raw.get("status") not in ok:
        raise ParseError(f"status HTTP {raw.get('status') if isinstance(raw, dict) else '?'}")
    return raw.get("body")


def _key_count(items, key: str, field_name: str) -> int:
    if not isinstance(items, list):
        raise ParseError("lista esperada")
    return sum(1 for x in items if isinstance(x, dict) and x.get(field_name) == key)


def p_aws_versions(raw, ctx):
    d = _stdout_json(raw) or {}
    if not isinstance(d, dict):
        raise ParseError("objeto esperado")
    return {"versions": _key_count(d.get("Versions") or [], ctx["key"], "Key")}


def p_gcs_versions(raw, ctx):
    d = _stdout_json(raw)
    return {"versions": _key_count(d if d is not None else [], ctx["key"], "name")}


def p_az_versions(raw, ctx):
    """az storage blob list --include v: uma entrada por versão (com versionId) quando o versionamento está ligado;
    sem versionamento, o blob atual vem com versionId nulo e conta como 1 (a versão única)."""
    d = _stdout_json(raw)
    return {"versions": _key_count(d if d is not None else [], ctx["key"], "name")}


def p_oci_versions(raw, ctx):
    d = _stdout_json(raw) or {}
    data = d.get("data") if isinstance(d, dict) else None
    items = data.get("items") if isinstance(data, dict) else data
    return {"versions": _key_count(items if items is not None else [], ctx["key"], "name")}


def p_aws_keycount(raw, ctx):
    d = _stdout_json(raw) or {}
    if not isinstance(d, dict):
        raise ParseError("objeto esperado")
    if "KeyCount" in d:
        return {"present": int(d["KeyCount"])}
    return {"present": len(d.get("Contents") or [])}


GCS_NO_MATCH = "matched no objects"


def p_gcs_list(raw, ctx):
    """gcloud storage objects list sai 1 com "One or more URLs matched no objects" quando o prefixo esvaziou: é
    contagem zero (o efeito), não leitura perdida. Qualquer outro erro continua leitura perdida."""
    if isinstance(raw, dict) and raw.get("rc") == 1 and GCS_NO_MATCH in (raw.get("stderr_tail") or ""):
        return {"present": 0}
    d = _stdout_json(raw)
    if d is None:
        return {"present": 0}
    if not isinstance(d, list):
        raise ParseError("lista esperada")
    return {"present": sum(1 for x in d if isinstance(x, dict) and str(x.get("name", "")).startswith(ctx["prefix"]))}


def p_dynamo_count(raw, ctx):
    d = _stdout_json(raw) or {}
    if not isinstance(d, dict) or "Count" not in d:
        raise ParseError("Count ausente")
    return {"present": int(d["Count"])}


def p_firestore_items(raw_list, ctx):
    """Uma resposta por item: 200 = presente, 404 = ausente; qualquer outro status é leitura perdida."""
    if not isinstance(raw_list, list) or len(raw_list) != ctx["n"]:
        raise ParseError("uma resposta por item esperada")
    present = 0
    for r in raw_list:
        st = r.get("status") if isinstance(r, dict) else None
        if st == 200:
            present += 1
        elif st != 404:
            raise ParseError(f"status HTTP {st}")
    return {"present": present}


def p_sqs_attrs(raw, ctx):
    d = _stdout_json(raw) or {}
    a = d.get("Attributes") if isinstance(d, dict) else None
    if not isinstance(a, dict) or "ApproximateNumberOfMessages" not in a:
        raise ParseError("atributos de contagem ausentes")
    keys = ("ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed")
    return {"present": sum(int(a.get(k, 0)) for k in keys)}


def p_monitoring_undelivered(raw, ctx):
    """Cloud Monitoring timeSeries.list de pubsub subscription/num_undelivered_messages: ponto mais recente.
    Série ausente = métrica ainda não publicada (atraso): leitura perdida, não zero."""
    body = _http_json(raw) or {}
    ts = body.get("timeSeries") if isinstance(body, dict) else None
    if not ts:
        raise ParseError("série ausente (atraso da métrica)")
    pts = [p for s in ts for p in (s.get("points") or [])]
    if not pts:
        raise ParseError("série sem pontos")
    last = max(pts, key=lambda p: (p.get("interval") or {}).get("endTime", ""))
    v = (last.get("value") or {}).get("int64Value")
    if v is None:
        raise ParseError("ponto sem int64Value")
    return {"present": int(v)}


# ------------------------------------------------------------------------------------------------ casos
KEY = "bo-probe/{role}/r{rep}/obj"
PREFIX = "bo-probe/{role}/r{rep}/"

OPS: dict[str, dict[str, Op]] = {
    "object_versioning/aws": {
        "act": Op("cli", ("aws", "s3api", "put-object", "--bucket", "{bucket}", "--key", "{key}", "--body",
                          "{payload_file}", "--output", "json"), repeat="writes"),
        "observe": Op("cli", ("aws", "s3api", "list-object-versions", "--bucket", "{bucket}", "--prefix", "{key}",
                              "--output", "json"), parse=p_aws_versions)},
    "object_versioning/google": {
        "act": Op("cli", ("gcloud", "storage", "cp", "{payload_file}", "gs://{bucket}/{key}"), repeat="writes"),
        "observe": Op("cli", ("gcloud", "storage", "objects", "list", "gs://{bucket}/{key}", "--all-versions",
                              "--format=json"), parse=p_gcs_versions)},
    "object_versioning/azurerm": {
        "act": Op("cli", ("az", "storage", "blob", "upload", "--account-name", "{account}", "--container-name",
                          "{container}", "--name", "{key}", "--file", "{payload_file}", "--overwrite", "true",
                          "--auth-mode", "key", "--output", "json"), repeat="writes"),
        "observe": Op("cli", ("az", "storage", "blob", "list", "--account-name", "{account}", "--container-name",
                              "{container}", "--prefix", "{key}", "--include", "v", "--auth-mode", "key",
                              "--output", "json"), parse=p_az_versions)},
    "object_versioning/oci": {
        "act": Op("cli", ("oci", "os", "object", "put", "--bucket-name", "{bucket}", "--name", "{key}", "--file",
                          "{payload_file}", "--force"), repeat="writes"),
        "observe": Op("cli", ("oci", "os", "object", "list-object-versions", "--bucket-name", "{bucket}",
                              "--prefix", "{key}", "--all"), parse=p_oci_versions)},
    "object_lifecycle/aws": {
        "act": Op("cli", ("aws", "s3api", "put-object", "--bucket", "{bucket}", "--key", "{prefix}obj-{i}",
                          "--body", "{payload_file}", "--output", "json"), per_item=True),
        "observe": Op("cli", ("aws", "s3api", "list-objects-v2", "--bucket", "{bucket}", "--prefix", "{prefix}",
                              "--output", "json"), parse=p_aws_keycount)},
    "object_lifecycle/google": {
        "act": Op("cli", ("gcloud", "storage", "cp", "{payload_file}", "gs://{bucket}/{prefix}obj-{i}"),
                  per_item=True),
        "observe": Op("cli", ("gcloud", "storage", "objects", "list", "gs://{bucket}/{prefix}**", "--format=json"),
                      parse=p_gcs_list)},
    "item_ttl/aws": {
        "act": Op("cli", ("aws", "dynamodb", "put-item", "--table-name", "{table}", "--item",
                          '{{"pk":{{"S":"{pk}"}},"sk":{{"S":"i{i}"}},"bo_expire_at":{{"N":"{expire_epoch}"}}}}',
                          "--output", "json"), per_item=True),
        "observe": Op("cli", ("aws", "dynamodb", "query", "--table-name", "{table}", "--key-condition-expression",
                              "pk = :p", "--expression-attribute-values", '{{":p":{{"S":"{pk}"}}}}', "--select",
                              "COUNT", "--consistent-read", "--output", "json"), parse=p_dynamo_count)},
    "item_ttl/google": {
        "act": Op("http", method="PATCH",
                  url="https://firestore.googleapis.com/v1/projects/{project}/databases/{database}/documents/"
                      "bo-probe/{pk}-i{i}",
                  body={"fields": {"bo_expire_at": {"timestampValue": "{expire_iso}"}}}, per_item=True),
        "observe": Op("http", method="GET",
                      url="https://firestore.googleapis.com/v1/projects/{project}/databases/{database}/documents/"
                          "bo-probe/{pk}-i{i}?mask.fieldPaths=bo_expire_at",
                      per_item=True, parse=p_firestore_items, ok_status=(200, 404))},
    "queue_retention/aws": {
        "act": Op("cli", ("aws", "sqs", "send-message", "--queue-url", "{queue_url}", "--message-body",
                          "bo-probe-synthetic", "--output", "json"), per_item=True),
        "observe": Op("cli", ("aws", "sqs", "get-queue-attributes", "--queue-url", "{queue_url}",
                              "--attribute-names", "ApproximateNumberOfMessages",
                              "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed",
                              "--output", "json"), parse=p_sqs_attrs)},
    "queue_retention/google": {
        "act": Op("cli", ("gcloud", "pubsub", "topics", "publish", "{topic}", "--message", "bo-probe-synthetic",
                          "--format=json"), per_item=True),
        "observe": Op("http", method="GET",
                      url="https://monitoring.googleapis.com/v3/projects/{project}/timeSeries?filter=metric.type%3D"
                          "%22pubsub.googleapis.com%2Fsubscription%2Fnum_undelivered_messages%22%20AND%20"
                          "resource.labels.subscription_id%3D%22{subscription}%22&interval.startTime={since_utc}"
                          "&interval.endTime={now_utc}",
                      parse=p_monitoring_undelivered)},
}

# filas: uma fila (aws) ou um tópico com assinatura (google) por repetição e por lado, porque a leitura conta a fila
# inteira; os alvos dessas chegam como lista (um por repetição).
PER_REP_TARGETS = {"queue_retention/aws", "queue_retention/google"}


# amostras canônicas (formato documentado de cada saída, valores sintéticos): efeito e efeito oposto de uma
# repetição com N = 3. O support_matrix (S9) passa cada uma pelo parser e pelo estado do tipo; parser que não
# separa efeito de oposto deixa o caso fora do sorteio.
def _c(obj):
    return {"rc": 0, "stdout": json.dumps(obj)}


_K = "bo-probe/case/r1/obj"
_P = "bo-probe/case/r1/"
SAMPLES = {
    "object_versioning/aws": (_c({"Versions": [{"Key": _K, "VersionId": f"v{i}"} for i in range(3)]}),
                              _c({"Versions": [{"Key": _K, "VersionId": "null"}]})),
    "object_versioning/google": (_c([{"name": _K, "generation": str(i)} for i in range(3)]),
                                 _c([{"name": _K, "generation": "1"}])),
    "object_versioning/azurerm": (_c([{"name": _K, "versionId": f"t{i}"} for i in range(3)]),
                                  _c([{"name": _K, "versionId": None}])),
    "object_versioning/oci": (_c({"data": [{"name": _K, "version-id": f"v{i}"} for i in range(3)]}),
                              _c({"data": [{"name": _K, "version-id": "v0"}]})),
    "object_lifecycle/aws": (_c({"KeyCount": 0}), _c({"KeyCount": 3, "Contents": [{}, {}, {}]})),
    "object_lifecycle/google": ({"rc": 1, "stdout": "", "stderr_tail": "ERROR: One or more URLs matched no objects."},
                                _c([{"name": f"{_P}obj-{i}"} for i in (1, 2, 3)])),
    "item_ttl/aws": (_c({"Count": 0, "ScannedCount": 0}), _c({"Count": 3, "ScannedCount": 3})),
    "item_ttl/google": ([{"status": 404}] * 3, [{"status": 200, "body": {}}] * 3),
    "queue_retention/aws": (_c({"Attributes": {"ApproximateNumberOfMessages": "0"}}),
                            _c({"Attributes": {"ApproximateNumberOfMessages": "3"}})),
    "queue_retention/google": ({"status": 200, "body": {"timeSeries": [{"points": [{"value": {"int64Value": "0"}}]}]}},
                               {"status": 200, "body": {"timeSeries": [{"points": [{"value": {"int64Value": "3"}}]}]}}),
}


def parser_selftest(cell: str) -> list[str]:
    """Problemas do parser do caso nas amostras canônicas (vazio = separa efeito de oposto)."""
    from .kinds import EFFECT, OPPOSITE, Kind
    if cell not in OPS or cell not in SAMPLES:
        return ["sem operações ou sem amostras canônicas"]
    t = cell.split("/")[0]
    kind = Kind(t, "exact", 0, 3)
    ctx = runner_ctx(cell, "case", 1, {"n": 3})
    out = []
    for raw, want in zip(SAMPLES[cell], (EFFECT, OPPOSITE)):
        try:
            got = kind.state(OPS[cell]["observe"].parse(raw, ctx))
        except (ParseError, ValueError) as e:
            out.append(f"amostra {want}: parser recusou ({e})")
            continue
        if got != want:
            out.append(f"amostra {want}: parser deu {got}")
    return out


def ops_for(cell: str) -> dict[str, Op]:
    if cell not in OPS:
        raise ProbeError(f"{cell}: sem operações de plano de dados no kit (caso não validado)", "PROTOCOL_UNSUPPORTED")
    return OPS[cell]


def runner_ctx(cell: str, role: str, rep: int, base: dict) -> dict:
    """Marcadores de uma repetição (os alvos da implantação chegam em base, em memória)."""
    tg = base.get(role)
    if isinstance(tg, list):
        if rep > len(tg):
            raise ProbeError(f"{cell}: sem alvo da repetição {rep} do {role}", "OP")
        tg = tg[rep - 1]
    ctx = {k: v for k, v in base.items() if k not in ("case", "control")}
    ctx.update(tg or {})
    ctx.update({"role": role, "rep": rep, "key": KEY.format(role=role, rep=rep),
                "prefix": PREFIX.format(role=role, rep=rep), "pk": f"{role}-r{rep}"})
    return ctx
