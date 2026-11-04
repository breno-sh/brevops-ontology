"""CC-8: especificação de API dos provedores como fonte PUBLICADA (dado não confiável, só parse).

Fontes fixadas (SOURCE.txt e SHA256SUMS em $BO_DATA/downloads/apispec-<provedor>/):
  aws      modelos Smithy (aws/api-models-aws, commit fixado): s3, ec2
  google   documentos Discovery v1 (revisão no próprio documento): storage, compute
  azurerm  azure-rest-api-specs (commit fixado): Microsoft.Storage 2026-09-01, Microsoft.Network 2026-03-01
  oci      oci-python-sdk (commit fixado): object_storage_client, core/virtual_network_client, lidos como TEXTO
           (expressão regular nas linhas `def`, `resource_path =` e `method =`; nunca importados)

Cada operação vira uma linha do modelo: (arquivo, ponteiro, nome, método, caminho, rótulos do caminho).
Citação (web_citation): uri = URL bruta fixada; section = "apispec <prov>/<arquivo> sha256 <h> <ponteiro>";
sentence = JSON canônico da projeção da operação; resolve() recalcula do arquivo.
Recursos e facetas (regras em rules.py):
  R-LIFE-SPEC   create e delete próprios (aws Create<N>/Delete<N>; google insert/delete; azure PUT e DELETE no
                caminho da instância; oci create_<n>/delete_<n>) -> ciclo de vida próprio na API
  R-OWN-SPEC    recurso de R-LIFE-SPEC: a configuração está no próprio objeto (self); faceta (configurada só
                por operação sobre o identificador do pai: aws Put<M> com os rótulos do Delete do pai ou nome
                com prefixo do pai; azure PUT sem DELETE com o último nome constante; oci put/update/add/remove
                cujo caminho estende o caminho do delete do pai) -> dono = pai
  R-BRIDGE-SPEC tipo Terraform <-> recurso da spec só com casamento único; ambíguo fica UNKNOWN com candidatos
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache

from . import common

RETRIEVED = "2026-11-04T08:36-03:00"
CC8 = {
    "aws": {"dir": "apispec-aws", "files": {"s3-2006-03-01.json": "s3", "ec2-2016-11-15.json": "ec2"},
            "urls": {"s3-2006-03-01.json": "https://raw.githubusercontent.com/aws/api-models-aws/"
                     "1b9ff13fe6c28ea9774a527e53cda6a3b91369dc/models/s3/service/2006-03-01/s3-2006-03-01.json",
                     "ec2-2016-11-15.json": "https://raw.githubusercontent.com/aws/api-models-aws/"
                     "1b9ff13fe6c28ea9774a527e53cda6a3b91369dc/models/ec2/service/2016-11-15/ec2-2016-11-15.json"},
            "versions": {"s3": "2006-03-01", "ec2": "2016-11-15"},
            "pin": "aws/api-models-aws@1b9ff13fe6c28ea9774a527e53cda6a3b91369dc", "date": "2026-10-30"},
    "google": {"dir": "apispec-google", "files": {"storage-v1.json": "storage", "compute-v1.json": "compute"},
               "urls": {"storage-v1.json": "https://storage.googleapis.com/$discovery/rest?version=v1",
                        "compute-v1.json": "https://compute.googleapis.com/$discovery/rest?version=v1"},
               "versions": {"storage": "v1", "compute": "v1"},
               "pin": "discovery v1 (revision no documento)", "date": "2026-11-04"},
    "azurerm": {"dir": "apispec-azurerm",
                "files": {"storage-2026-09-01-openapi.json": "Microsoft.Storage",
                          "network-2026-03-01-virtualNetwork.json": "Microsoft.Network"},
                "urls": {"storage-2026-09-01-openapi.json":
                         "https://raw.githubusercontent.com/Azure/azure-rest-api-specs/6ad5af824ebf340b4a83889dbdd70572124b57a5/"
                         "specification/storage/resource-manager/Microsoft.Storage/Storage/stable/2026-09-01/openapi.json",
                         "network-2026-03-01-virtualNetwork.json":
                         "https://raw.githubusercontent.com/Azure/azure-rest-api-specs/6ad5af824ebf340b4a83889dbdd70572124b57a5/"
                         "specification/network/resource-manager/Microsoft.Network/Network/stable/2026-03-01/"
                         "virtualNetwork.json"},
                "versions": {"Microsoft.Storage": "2026-09-01", "Microsoft.Network": "2026-03-01"},
                "pin": "Azure/azure-rest-api-specs@6ad5af824ebf340b4a83889dbdd70572124b57a5", "date": "2026-11-03"},
    "oci": {"dir": "apispec-oci", "files": {"object_storage_client.py.txt": "object_storage",
                                            "virtual_network_client.py.txt": "core"},
            "urls": {"object_storage_client.py.txt":
                     "https://raw.githubusercontent.com/oracle/oci-python-sdk/ec1d21a37357b8ab1e86fec7132bc08f3df17782/"
                     "src/oci/object_storage/object_storage_client.py",
                     "virtual_network_client.py.txt":
                     "https://raw.githubusercontent.com/oracle/oci-python-sdk/ec1d21a37357b8ab1e86fec7132bc08f3df17782/"
                     "src/oci/core/virtual_network_client.py"},
            "versions": {"object_storage": "sdk@ec1d21a", "core": "sdk@ec1d21a"},
            "pin": "oracle/oci-python-sdk@ec1d21a37357b8ab1e86fec7132bc08f3df17782", "date": "2026-11-03"},
}
CC9_DIRS = {p: f"apispec-{p}-cc9" for p in ("aws", "google", "azurerm", "oci")}
EXTRA_DIRS = {"oci": ["apispec-oci-models"]}  # modelos de dados do SDK (swagger_types), rodada final do piloto


def batch_dirs(p: str) -> list[str]:
    return [CC9_DIRS[p]] + EXTRA_DIRS.get(p, [])


def _build_spec() -> dict:
    """Junta o lote do CC-8 (pastas apispec-<prov>/) e o do CC-9 (apispec-<prov>-cc9/, FILES.json), sem
    duplicar o mesmo arquivo de origem. Arquivo = caminho relativo a $BO_DATA/downloads (fid)."""
    out = {}
    for p, c in CC8.items():
        files = {f"{c['dir']}/{f}": svc for f, svc in c["files"].items()}
        urls = {f"{c['dir']}/{f}": u for f, u in c["urls"].items()}
        sets = [{"dir": c["dir"], "pin": c["pin"], "date": c["date"]}]
        versions = dict(c["versions"])
        kinds = {}
        for bd in batch_dirs(p):
            fj = common.bo_data() / "downloads" / bd / "FILES.json"
            if not fj.exists():
                fj = common.bo_data() / "downloads" / (bd + ".staging") / "FILES.json"
            if not fj.exists():
                continue
            j = json.loads(fj.read_text(encoding="utf-8"))
            seen = set(urls.values())
            for rel, meta in sorted(j["files"].items()):
                if meta["url"] in seen:
                    continue
                fid = f"{bd}/{rel}"
                urls[fid] = meta["url"]
                if meta.get("kind") == "model":
                    kinds[fid] = "model"
                else:
                    files[fid] = meta["service"]
                    versions.setdefault(meta["service"], meta.get("version") or j["pin"])
            sets.append({"dir": bd, "pin": j["pin"], "date": j["date"]})
        out[p] = {"files": files, "urls": urls, "versions": versions, "sets": sets, "models": kinds,
                  "pin": "; ".join(x["pin"] for x in sets), "date": max(x["date"] for x in sets)}
    return out


SPEC = _build_spec()
SECTION_RX = re.compile(r"^apispec (?P<prov>[a-z]+)/(?P<file>\S+) sha256 (?P<sha>[0-9a-f]{64}) (?P<ptr>\S+)$")
DL = None
AWS_VERB = re.compile(r"^(Create|Delete|Run|Terminate|Put|Get|Update|Modify|Describe|List|Authorize|Revoke|Associate|Disassociate|"
                      r"Attach|Detach|Enable|Disable|Replace|Apply|Restore|Copy|Head)([A-Z].*)$")
OCI_VERB = re.compile(r"^(create|launch|delete|terminate|get|list|update|put|add|remove|change|restore|copy|reencrypt|rename|"
                      r"make|abort|commit|head|upload)_(.+)$")


def ddir(p: str):
    return common.bo_data() / "downloads" / f"apispec-{p}"


def path(f: str):
    """Arquivo pelo fid (pasta do lote/arquivo). Lote ainda não promovido: lê de <pasta>.staging, com o MESMO fid
    (a citação não muda quando o lote é promovido dentro da trava)."""
    p0 = common.bo_data() / "downloads" / f
    if p0.exists():
        return p0
    d, rest = f.split("/", 1)
    return common.bo_data() / "downloads" / (d + ".staging") / rest


def url(p: str, f: str) -> str:
    return SPEC[p]["urls"][f]


@lru_cache(maxsize=4096)
def sha(p: str, f: str) -> str:
    return hashlib.sha256(path(f).read_bytes()).hexdigest()


@lru_cache(maxsize=8)
def sums_ok(p: str) -> tuple:
    bad = []
    for st in SPEC[p]["sets"]:
        d = common.bo_data() / "downloads" / st["dir"]
        if not d.exists():
            d = common.bo_data() / "downloads" / (st["dir"] + ".staging")
        for line in (d / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            h, f = line.split("  ", 1)
            if hashlib.sha256((d / f).read_bytes()).hexdigest() != h:
                bad.append(f"{st['dir']}/{f}")
    return tuple(bad)


@lru_cache(maxsize=64)
def load_json(p: str, f: str):
    return json.loads(path(f).read_text(encoding="utf-8"))


@lru_cache(maxsize=512)
def load_lines(p: str, f: str):
    return tuple(path(f).read_text(encoding="utf-8").splitlines())


def snake(s: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    return s.replace("-", "_").lower()


def esc(s: str) -> str:
    return s.replace("~", "~0").replace("/", "~1")


def unesc(s: str) -> str:
    return s.replace("~1", "/").replace("~0", "~")


# ---------------------------------------------------------------- projeção de uma operação (frase da citação)

def project(p: str, f: str, ptr: str) -> dict:
    if p == "aws":
        shapes = load_json(p, f)["shapes"]
        if "/members/" in ptr:  # membro de estrutura (ex.: SecurityGroupRule.SecurityGroupRuleId)
            sh, mem = ptr[len("/shapes/"):].split("/members/")
            node = shapes[unesc(sh)]["members"][unesc(mem)]
            return {"shape": unesc(sh).split("#")[1], "member": unesc(mem), "target": node.get("target")}
        name = unesc(ptr[len("/shapes/"):])
        o = shapes[name]
        http = (o.get("traits") or {}).get("smithy.api#http") or {}
        labels = []
        if o.get("input"):
            inp = shapes.get(o["input"]["target"], {})
            labels = sorted(m for m, v in (inp.get("members") or {}).items()
                            if "smithy.api#httpLabel" in (v.get("traits") or {}))
        return {"operation": name.split("#")[1], "method": http.get("method"), "uri": http.get("uri"),
                "labels": labels}
    if p in ("google", "azurerm") and (ptr.startswith("/schemas/") or ptr.startswith("/definitions/")):
        node = load_json(p, f)
        for part in ptr.split("/")[1:]:
            node = node[unesc(part)]
        return {"field": unesc(ptr.split("/")[-1]), "type": node.get("type"), "ref": node.get("$ref"),
                "items_ref": (node.get("items") or {}).get("$ref")}
    if p == "google":
        node = load_json(p, f)
        for part in ptr.split("/")[1:]:
            node = node[unesc(part)]
        return {"id": node.get("id"), "httpMethod": node.get("httpMethod"), "path": node.get("path")}
    if p == "azurerm":
        _, _paths, path, meth = ptr.split("/", 3)
        o = load_json(p, f)["paths"][unesc(path)][meth]
        return {"operationId": o.get("operationId"), "method": meth.upper(), "path": unesc(path)}
    lines = load_lines(p, f)
    mm = re.match(r"^M(\d+)$", ptr)
    if mm:  # linha do swagger_types de um modelo do SDK
        return {"model_line": lines[int(mm.group(1)) - 1].strip()}
    m = re.match(r"^L(\d+),(\d+),(\d+)$", ptr)
    return {"lines": [lines[int(m.group(i)) - 1].strip() for i in (1, 2, 3)]}


def cite(p: str, f: str, ptr: str) -> dict:
    return {"uri": url(p, f), "retrieved_at": RETRIEVED,
            "section": f"apispec {p}/{f} sha256 {sha(p, f)} {ptr}", "sentence": common.canon(project(p, f, ptr))}


def resolve(p: str, cit: dict) -> str | None:
    m = SECTION_RX.match(cit.get("section", ""))
    if not m:
        return "section sem ponteiro de spec"
    if m["prov"] != p or (m["file"] not in SPEC[p]["files"] and m["file"] not in SPEC[p].get("models", {})):
        return "arquivo de spec fora da lista fixada"
    if m["sha"] != sha(p, m["file"]) or sums_ok(p):
        return "sha256 do arquivo de spec não confere"
    if cit.get("uri") != url(p, m["file"]):
        return "uri não é a fonte fixada"
    try:
        want = common.canon(project(p, m["file"], m["ptr"]))
    except (KeyError, IndexError, AttributeError, TypeError, ValueError):
        return "ponteiro não existe na spec"
    return None if want == cit.get("sentence") else "operação da spec difere da frase"


# ---------------------------------------------------------------- modelo de recursos por provedor

def model(p: str) -> dict:
    """{recurso: {"service", "file", "create", "delete", "config": [ptrs], "parent", "id": ..}}."""
    return {"aws": _aws, "google": _google, "azurerm": _azure, "oci": _oci}[p]()


@lru_cache(maxsize=1)
def aws_service_names() -> dict:
    """serviço (pasta) -> nomes normalizados (pasta, sdkId, arnNamespace, endpointPrefix) do traço aws.api#service."""
    out = {}
    for f, svc in SPEC["aws"]["files"].items():
        names = {norm(svc)}
        for v in load_json("aws", f)["shapes"].values():
            if v.get("type") == "service":
                t = (v.get("traits") or {}).get("aws.api#service") or {}
                names |= {norm(t.get(k, "")) for k in ("sdkId", "arnNamespace", "endpointPrefix") if t.get(k)}
        out[svc] = names
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


@lru_cache(maxsize=1)
def _aws():
    out = {}
    for f, svc in SPEC["aws"]["files"].items():
        shapes = load_json("aws", f)["shapes"]
        ops = {}
        for k, v in shapes.items():
            if v.get("type") == "operation":
                m = AWS_VERB.match(k.split("#")[1])
                if m:
                    ops.setdefault(m.group(2), {})[m.group(1)] = "/shapes/" + esc(k)
        labels = lambda ptr: tuple(project("aws", f, ptr)["labels"])  # noqa: E731
        # Run<N>s/Terminate<N>s (ec2: RunInstances/TerminateInstances) contam como create/delete do substantivo no
        # singular quando não há Create/Delete para ele
        for n in [x for x in ops if x.endswith("s") and "Run" in ops[x] and "Terminate" in ops[x]]:
            sg = ops.setdefault(n[:-1], {})
            if "Create" not in sg and "Delete" not in sg:
                sg["Create"], sg["Delete"] = ops[n]["Run"], ops[n]["Terminate"]
        own = {n: o for n, o in ops.items() if "Create" in o and "Delete" in o}
        own_by_labels = {}
        for n, o in own.items():
            lb = labels(o["Delete"])
            if lb:
                own_by_labels.setdefault(lb, []).append(n)
        for n, o in own.items():
            out[(svc, n)] = {"service": svc, "resource": n, "file": f, "create": o["Create"], "delete": o["Delete"],
                             "parent": None, "config": [], "update": o.get("Modify") or o.get("Update")}
        for n, o in ops.items():
            if n in own:
                continue
            cfg = [o[v] for v in ("Put", "Authorize", "Revoke", "Update", "Modify") if v in o]
            if not cfg:
                continue
            par = None
            lb = labels(cfg[0])
            cands = own_by_labels.get(lb, []) if lb else []
            if len(cands) > 1:  # mesmo rótulo: o pai é o recurso cujo Delete está no caminho-base da faceta
                base = (project("aws", f, cfg[0])["uri"] or "").split("?")[0]
                cands = [x for x in cands if project("aws", f, own[x]["Delete"])["uri"] == base]
            if len(cands) == 1:
                par = cands[0]
            else:
                pre = sorted((x for x in own if n.startswith(x) and n != x), key=len, reverse=True)
                par = pre[0] if pre else None
            if par:
                o0 = shapes[unesc(cfg[0][len("/shapes/"):])]
                inp = shapes.get((o0.get("input") or {}).get("target", ""), {})
                payload = [m for m, v in (inp.get("members") or {}).items()
                           if "smithy.api#httpPayload" in (v.get("traits") or {})]
                out[(svc, n)] = {"service": svc, "resource": n, "file": f, "create": None, "delete": None,
                                 "parent": par, "config": cfg, "parent_labels": list(lb), "payload": payload,
                                 "verbs": sorted(v for v in ("Put", "Authorize", "Revoke", "Update", "Modify")
                                                 if v in o)}
    return out


@lru_cache(maxsize=1)
def _google():
    out = {}
    for f, svc in SPEC["google"]["files"].items():
        doc = load_json("google", f)

        def walk(res, prefix, ptr):
            for name, r in (res or {}).items():
                ms = r.get("methods") or {}
                base = f"{ptr}/resources/{esc(name)}"
                dotted = f"{prefix}.{name}" if prefix else name
                ins = "insert" if "insert" in ms else ("create" if "create" in ms else None)
                if ins and "delete" in ms:
                    upd = next((f"{base}/methods/{m}" for m in ("patch", "update") if m in ms), None)
                    out[(svc, dotted)] = {"service": svc, "resource": dotted, "leaf": name, "file": f,
                                        "create": f"{base}/methods/{ins}", "delete": f"{base}/methods/delete",
                                        "parent": None, "config": [], "update": upd,
                                        "schema": ((ms[ins].get("request") or {}).get("$ref"))}
                walk(r.get("resources"), dotted, base)
        walk(doc.get("resources"), "", "")
    return out


ARM_TAIL = re.compile(r"/providers/(?P<ns>[A-Za-z]+\.[A-Za-z]+)/(?P<rest>[^?]+)$")


@lru_cache(maxsize=1)
def _azure():
    out = {}
    for f, ns in SPEC["azurerm"]["files"].items():
        paths = load_json("azurerm", f)["paths"]
        for path, ops in paths.items():
            m = ARM_TAIL.search(path)
            if not m or m["ns"] != ns or "put" not in ops:
                continue
            segs = m["rest"].split("/")
            if len(segs) % 2:
                continue
            types, names = segs[0::2], segs[1::2]
            key = (ns, "/".join(types))
            ptr_put = f"/paths/{esc(path)}/put"
            body = next((x.get("schema", {}).get("$ref") for x in ops["put"].get("parameters") or []
                         if x.get("in") == "body"), None)
            body = body.split("/")[-1] if body and body.startswith("#/definitions/") else None
            if "delete" in ops:
                out[key] = {"service": ns, "resource": "/".join(types), "file": f, "create": ptr_put, "schema": body,
                            "delete": f"/paths/{esc(path)}/delete", "parent": None, "config": [],
                            "update": f"/paths/{esc(path)}/patch" if "patch" in ops else ptr_put}
            elif not names[-1].startswith("{") and len(types) > 1:
                out[key] = {"service": ns, "resource": "/".join(types), "file": f, "create": None, "delete": None,
                            "parent": "/".join(types[:-1]), "config": [ptr_put], "constant_name": names[-1],
                            "schema": body}
    return out


@lru_cache(maxsize=1)
def _oci():
    out = {}
    for f, svc in SPEC["oci"]["files"].items():
        lines = load_lines("oci", f)
        ops = {}
        for i, ln in enumerate(lines):
            m = re.match(r"\s+def ([a-z_]+)\(self", ln)
            if not m:
                continue
            vm = OCI_VERB.match(m.group(1))
            if not vm:
                continue
            rp = mt = None
            for j in range(i + 1, min(i + 400, len(lines))):
                if re.match(r"\s+def ", lines[j]):
                    break
                if rp is None and re.match(r'\s+resource_path = "', lines[j]):
                    rp = j
                elif rp is not None and re.match(r'\s+method = "', lines[j]):
                    mt = j
                    break
            if rp is None or mt is None:
                continue
            path = re.search(r'"([^"]+)"', lines[rp]).group(1)
            verb = {"terminate": "delete", "launch": "create"}.get(vm.group(1), vm.group(1))  # sinônimos da OCI
            ops.setdefault(vm.group(2), {}).setdefault(verb, (f"L{i + 1},{rp + 1},{mt + 1}", path))
        # próprio: delete_<n> cujo caminho termina num identificador {param}, e create_<n> ou put_<n> (o put que
        # grava o objeto pelo próprio nome, como put_object); delete com último segmento constante é faceta
        own = {n: o for n, o in ops.items() if "delete" in o and ("create" in o or "put" in o)
               and o["delete"][1].rstrip("/").split("/")[-1].startswith("{")}
        for n, o in own.items():
            if "create" not in o:
                o = dict(o, create=o["put"])
            out[(svc, n)] = {"service": svc, "resource": n, "file": f, "create": o["create"][0],
                             "delete": o["delete"][0], "parent": None, "config": [], "path": o["delete"][1],
                             "update": (o.get("update") or (None,))[0]}
        for n, o in ops.items():
            if n in own:
                continue
            cfg = [o[v] for v in ("put", "update", "add", "remove") if v in o]
            if not cfg:
                continue
            par = [x for x, ox in own.items() if cfg[0][1].startswith(ox["delete"][1] + "/")]
            if len(par) == 1:
                out[(svc, n)] = {"service": svc, "resource": n, "file": f, "create": None, "delete": None,
                                 "parent": par[0], "config": [c[0] for c in cfg], "path": cfg[0][1],
                                 "parent_path": own[par[0]]["delete"][1]}
    return out


# ---------------------------------------------------------------- campos do corpo (blocos -> campo da spec)

def lower_camel(seg: str) -> str:
    t = seg.split("_")
    return t[0] + "".join(x[:1].upper() + x[1:] for x in t[1:])


def field_children(p: str, f: str, ptr: str) -> dict:
    """{nome: ponteiro} dos campos do nó (objeto, array de objetos, $ref no mesmo arquivo; azure achata
    properties com x-ms-client-flatten)."""
    doc = load_json(p, f)
    node = doc
    for part in ptr.split("/")[1:]:
        node = node[unesc(part)]
    out = {}

    def add(n, base):
        if n.get("items"):
            it = n["items"]
            if it.get("$ref"):
                return add_ref(it["$ref"])
            if it.get("properties"):
                for k in it["properties"]:
                    out.setdefault(k, f"{base}/items/properties/{esc(k)}")
            return None
        if n.get("$ref"):
            return add_ref(n["$ref"])
        for k, v in (n.get("properties") or {}).items():
            if p == "azurerm" and k == "properties" and v.get("x-ms-client-flatten") and v.get("$ref"):
                add_ref(v["$ref"])
            else:
                out.setdefault(k, f"{base}/properties/{esc(k)}")
        return None

    def add_ref(ref):
        name = ref.split("/")[-1]
        root = "schemas" if p == "google" else "definitions"
        if name in doc.get(root, {}):
            add(doc[root][name], f"/{root}/{esc(name)}")

    add(node, ptr)
    return out


def find_field(p: str, f: str, schema: str, path: list) -> list | None:
    """Ponteiros do caminho de campos que o bloco Terraform configura (cada segmento: lowerCamel do nome; ou
    o 1º termo e depois o resto, como lifecycle_rule -> lifecycle.rule). None se algum segmento não casa."""
    root = "schemas" if p == "google" else "definitions"
    if not schema or schema not in load_json(p, f).get(root, {}):
        return None
    cur, ptrs = f"/{root}/{esc(schema)}", []
    for seg in path:
        kids = field_children(p, f, cur)
        lc = lower_camel(seg)
        for cand in (lc, lc + "s"):
            if cand in kids:
                cur = kids[cand]
                ptrs.append(cur)
                break
        else:
            cand = None
        if cand:
            continue
        # um nível intermediário ÚNICO (ex.: management policy: rule -> policy.rules)
        mids = [(k, kp, ip) for k, kp in kids.items() for c2, ip in field_children(p, f, kp).items()
                if c2 in (lc, lc + "s")]
        if len(mids) == 1:
            ptrs += [mids[0][1], mids[0][2]]
            cur = mids[0][2]
            continue
        toks = seg.split("_")
        if len(toks) > 1 and toks[0] in kids:
            inner = field_children(p, f, kids[toks[0]])
            rest = lower_camel("_".join(toks[1:]))
            if rest in inner:
                ptrs += [kids[toks[0]], inner[rest]]
                cur = inner[rest]
                continue
        return None
    return ptrs


def aws_member_path(f: str, shape: str, path: list) -> list | None:
    """aws: caminho de membros de estrutura que o bloco configura (snake do membro = segmento, ou o singular:
    Rules -> rule, Grants -> grant). Devolve [(ponteiro do membro, alvo)]."""
    shapes = load_json("aws", f)["shapes"]
    cur, out = shape, []
    for seg in path:
        st = shapes.get(cur, {})
        if st.get("type") == "list":
            cur = st["member"]["target"]
            st = shapes.get(cur, {})
        hit = None
        for mname, mv in (st.get("members") or {}).items():
            sn = snake(mname)
            if seg in (sn, sn[:-1] if sn.endswith("s") else sn):
                hit = (mname, mv["target"])
                break
        if not hit:
            return None
        out.append((f"/shapes/{esc(cur)}/members/{esc(hit[0])}", hit[1]))
        cur = hit[1]
    return out


def aws_item_shape(f: str, target: str) -> str:
    shapes = load_json("aws", f)["shapes"]
    st = shapes.get(target, {})
    return st["member"]["target"] if st.get("type") == "list" else target


def oci_model_field(svc: str, model: str, key: str, details: bool = False):
    """(fid, ponteiro M<linha>, tipo) do campo no swagger_types de models/<model>.py do módulo; com details, também
    launch_<model>_details.py e create_<model>_details.py (corpo da criação). None se não há."""
    names = [model] + ([f"launch_{model}_details", f"create_{model}_details"] if details else [])
    for nm in names:
        for fid in SPEC["oci"].get("models", {}):
            if fid.endswith(f"/src/oci/{svc}/models/{nm}.py"):
                for i, ln in enumerate(load_lines("oci", fid)):
                    mm = re.match(r"\s+'([a-z0-9_]+)': '([^']+)',?$", ln)
                    if mm and mm.group(1) == key:
                        return fid, f"M{i + 1}", mm.group(2)
    return None
