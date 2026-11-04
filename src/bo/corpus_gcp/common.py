"""Caminhos, parâmetros fixados e escrita canônica do CORPUS-GCP."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

MODULE = "CORPUS-GCP"
PROVIDER = "google"
TZ = ZoneInfo("America/Recife")

# Regras de contagem (vão para summary.json e build_report.json). term_class e explicit_null foram corrigidos na
# caça de defeitos pela semântica do C06 e do Terraform (cadeia simbolizada por privacidade não é dependência;
# attr = null é omitir), antes de qualquer consumidor; nada aqui mira um número.
PARAMS = {
    "provider": PROVIDER,
    "unit_resource": "bloco resource gerenciado (repo_id, file, resource_address) do resources.parquet; data fica fora",
    "unit_module": "diretório do arquivo .tf dentro do repositório (repo_id, dirname(file))",
    "term_class": "withheld = termo retido em qualquer nível; simbólico = depende de referência, variável, local, "
                  "saída de módulo, data source, atributo de recurso, count.index, each/iterador de dynamic, "
                  "workspace ou função de arquivo/ambiente/relógio; literal = o resto (sai só do texto, inclusive "
                  "cadeia, CIDR e IP simbolizados por privacidade)",
    "explicit_null": "literal null no topo não configura o átomo (Terraform: igual a omitir)",
    "precedence": "por recurso e átomo, com várias ocorrências (blocos repetidos/dynamic): withheld > simbólico > literal",
    "type_row": "linha sem atom_id por (repo, tipo): n_resources = blocos do tipo; n_set = blocos com >= 1 átomo",
    "atom_rows": "só átomos com n_set >= 1 no repositório; os não configurados ficam implícitos na linha do tipo",
    "object_attr": "caminho sob um atributo de tipo objeto (escrito como bloco) conta para esse átomo",
    "meta": "count, for_each, provider, depends_on, lifecycle, provisioner, connection e for_each/iterator/labels "
            "de dynamic não são átomos",
    "workers": 6,
}

META_TOP = frozenset({"count", "for_each", "provider", "depends_on", "lifecycle", "provisioner", "connection"})
META_DYNAMIC = frozenset({"for_each", "iterator", "labels"})


def bo_data() -> Path:
    return Path(os.environ.get("BO_DATA", "/Users/breno/doutorado/brevops-data"))


def bo_repo() -> Path:
    return Path(os.environ.get("BO_REPO", "/Users/breno/doutorado/brevops-ontology"))


def out_dir() -> Path:
    return bo_data() / MODULE


def staging_dir() -> Path:
    return out_dir() / ".staging"


def tmp_dir() -> Path:
    p = Path(os.environ.get("BO_TMP") or (bo_data() / "tmp" / MODULE))
    p.mkdir(parents=True, exist_ok=True)
    return p


def results_dir() -> Path:
    return bo_repo() / "results" / MODULE


def hcl_dir() -> Path:
    return bo_data() / "HCL"


def atoms_path() -> Path:
    return bo_data() / "SCHEMA-GCP" / "atoms.jsonl"


def inputs() -> dict[str, Path]:
    """Entradas declaradas no catálogo, mais o índice do HCL (lido para ir direto aos repositórios)."""
    h = hcl_dir()
    return {"$BO_DATA/HCL/resources.parquet": h / "resources.parquet",
            "$BO_DATA/HCL/symbolic_config.jsonl": h / "symbolic_config.jsonl",
            "$BO_DATA/HCL/symbolic_config.index.json": h / "symbolic_config.index.json",
            "$BO_DATA/SCHEMA-GCP/atoms.jsonl": atoms_path()}


def now() -> str:
    return _dt.datetime.now(TZ).replace(microsecond=0).isoformat()


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def portable(p: Path) -> str:
    s = str(p)
    for root, name in ((str(bo_data()), "$BO_DATA"), (str(bo_repo()), "$BO_REPO")):
        if s == root or s.startswith(root + "/"):
            return name + s[len(root):]
    return s
