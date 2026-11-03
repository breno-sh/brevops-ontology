"""Extrai os controles CIS (Foundations) de um mod de compliance do Steampipe, lido como dado.

Para cada pasta `cis_vNNN/` do mod: lê os .pp/.sp com o leitor mínimo (hcl_lite), resolve a árvore
benchmark -> seção -> subseção -> controle a partir do benchmark raiz `cis_vNNN`, herda as tags pelas
cadeias `merge(local.x, {...})` e devolve um registro por controle, com a linha de origem.
Família fora de escopo (cis_controls_v8_*, cis_compute_service_*) é ignorada e relatada pelo chamador.
"""

from __future__ import annotations

import re
import tarfile
from dataclasses import dataclass
from pathlib import Path

from .hcl_lite import Block, Expr, HclError, parse

FOUNDATIONS_DIR = re.compile(r"^cis_v(\d{3})$")
ITEM_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(.*\S)\s*$")


class ExtractError(ValueError):
    pass


@dataclass(frozen=True)
class Control:
    provider: str
    benchmark_id: str
    cis_version: str
    benchmark_title: str
    control_id: str
    cis_item_id: str
    section_id: str
    section_title: str
    subsection_id: str
    subsection_title: str
    title: str
    cis_level: str
    cis_type: str
    service: str
    query: str
    source_file: str  # relativo à raiz do mod
    source_line: int
    parent_id: str = ""  # benchmark imediatamente acima (pode ser mais fundo que a subseção)
    parent_title: str = ""
    title_item_id: str = ""  # número que abre o título (pode divergir da tag cis_item_id: é dado da fonte)
    anomaly: str = ""


def _string(e: Expr | None, what: str) -> str:
    if e is None:
        return ""
    if e.kind != "string":
        raise ExtractError(f"{what}: esperado texto, achado {e.kind}")
    return str(e.value)


def _refs(e: Expr | None) -> list[str]:
    if e is None:
        return []
    if e.kind != "list" or any(x.kind != "ref" for x in e.value):
        raise ExtractError("children: esperado lista de referências")
    return [str(x.value) for x in e.value]


def _merge_parts(e: Expr | None) -> tuple[str | None, dict[str, str]]:
    """merge(local.x, {k = "v"}) -> ("x", {k: v}); objeto literal -> (None, {...})."""
    if e is None:
        return None, {}
    if e.kind == "object":
        return None, {k: _string(v, f"tag {k}") for k, v in e.value.items() if v.kind == "string"}
    if e.kind == "call" and e.value[0] == "merge":
        base, own = None, {}
        for a in e.value[1]:
            if a.kind == "ref" and a.value.startswith("local."):
                if base is not None:
                    raise ExtractError("merge com mais de um local")
                base = a.value[len("local."):]
            elif a.kind == "object":
                own.update({k: _string(v, f"tag {k}") for k, v in a.value.items() if v.kind == "string"})
            else:
                raise ExtractError(f"argumento de merge não suportado: {a.kind}")
        return base, own
    raise ExtractError(f"tags: expressão não suportada ({e.kind})")


def _resolve(name: str | None, locals_: dict[str, Expr], seen: tuple[str, ...] = ()) -> dict[str, str]:
    if name is None or name not in locals_:
        return {}  # local da raiz do mod (ex. aws_compliance_common_tags): sem tags cis_*
    if name in seen:
        raise ExtractError(f"ciclo de locals: {' -> '.join(seen + (name,))}")
    base, own = _merge_parts(locals_[name])
    out = _resolve(base, locals_, seen + (name,))
    out.update(own)
    return out


def _split_title(title: str) -> tuple[str, str]:
    m = ITEM_PREFIX.match(title)
    if not m:
        return "", title.strip()
    return m.group(1), m.group(2)


def version_label(dirname: str) -> str:
    m = FOUNDATIONS_DIR.match(dirname)
    if not m:
        raise ExtractError(f"pasta fora do padrão cis_vNNN: {dirname}")
    d = m.group(1)
    return f"v{int(d[0])}.{int(d[1])}.{int(d[2])}"


def read_mod(archive: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Lê do tarball (sem extrair) os .pp/.sp das pastas cis_vNNN/ da raiz do mod.

    Devolve ({pasta: {caminho_relativo: texto}}, pastas cis_* fora de escopo). Só arquivos regulares; nome
    absoluto, com '..' ou fora do prefixo único do tarball reprova.
    """
    keep: dict[str, dict[str, str]] = {}
    skipped: set[str] = set()
    prefix = None
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            name = m.name
            if name.startswith("/") or ".." in Path(name).parts:
                raise ExtractError(f"membro suspeito no tarball: {name!r}")
            top = name.split("/", 1)[0]
            if prefix is None:
                prefix = top
            elif top != prefix:
                raise ExtractError(f"tarball com mais de uma raiz: {prefix!r} e {top!r}")
            rel = name.split("/", 1)[1] if "/" in name else ""
            parts = rel.split("/")
            if len(parts) < 2 or not parts[0].startswith("cis_"):
                continue
            if not FOUNDATIONS_DIR.match(parts[0]):
                skipped.add(parts[0])
                continue
            if len(parts) != 2 or not m.isfile() or not rel.endswith((".pp", ".sp")):
                continue
            f = tf.extractfile(m)
            keep.setdefault(parts[0], {})[rel] = f.read().decode("utf-8")
    return dict(sorted(keep.items())), sorted(skipped)


def extract_version(provider: str, bench_id: str, files: dict[str, str]) -> list[Control]:
    blocks: list[Block] = []
    if not files:
        raise ExtractError(f"{bench_id}: nenhum .pp/.sp")
    for rel in sorted(files):
        try:
            blocks += parse(files[rel], rel)
        except HclError as e:
            raise ExtractError(str(e)) from e
    locals_: dict[str, Expr] = {}
    benches: dict[str, Block] = {}
    controls: dict[str, Block] = {}
    for b in blocks:
        if b.type == "locals":
            for k, v in b.attrs.items():
                if k in locals_:
                    raise ExtractError(f"local repetido: {k}")
                locals_[k] = v
        elif b.type == "benchmark":
            benches[b.labels[0]] = b
        elif b.type == "control":
            if b.labels[0] in controls:
                raise ExtractError(f"controle repetido: {b.labels[0]}")
            controls[b.labels[0]] = b
        else:
            raise ExtractError(f"{b.file}:{b.line}: bloco inesperado {b.type}")
    if bench_id not in benches:
        raise ExtractError(f"{bench_id}: benchmark raiz ausente")
    root = benches[bench_id]
    rbase, rown = _merge_parts(root.attrs.get("tags"))
    root_tags = _resolve(rbase, locals_) | rown
    cis_version = root_tags.get("cis_version") or version_label(bench_id)
    if cis_version != version_label(bench_id):
        raise ExtractError(f"{bench_id}: cis_version {cis_version} não bate com a pasta")
    root_title = _string(root.attrs.get("title"), "title")

    out: list[Control] = []
    seen: set[str] = set()
    emitted: set[str] = set()

    def walk(ref: str, path: list[tuple[str, str]]):
        kind, _, name = ref.partition(".")
        if kind == "benchmark":
            if name not in benches:
                raise ExtractError(f"{bench_id}: benchmark {name} referido e não definido")
            b = benches[name]
            bbase, bown = _merge_parts(b.attrs.get("tags"))
            if "cis_item_id" in bown:
                # Item CIS realizado como benchmark cujos filhos são checagens de fora da pasta CIS
                # (ex. Azure 5.5 "SKU Basic"): o item é o benchmark; os filhos viram a lista de consultas.
                emit(b, bbase, bown, path, "+".join(c.partition(".")[2] for c in _refs(b.attrs.get("children"))),
                     "item CIS realizado como benchmark com checagens externas")
                return
            sid, stitle = _split_title(_string(b.attrs.get("title"), "title"))
            for child in _refs(b.attrs.get("children")):
                walk(child, path + [(sid, stitle)])
            return
        if kind != "control":
            raise ExtractError(f"{bench_id}: filho de tipo inesperado {ref}")
        if name not in controls:
            raise ExtractError(f"{bench_id}: controle {name} referido e não definido na pasta")
        if name in seen:
            raise ExtractError(f"{bench_id}: controle {name} aparece duas vezes na árvore")
        seen.add(name)
        c = controls[name]
        base, own = _merge_parts(c.attrs.get("tags"))
        q = c.attrs.get("query")
        query = str(q.value) if q is not None and q.kind == "ref" else ""
        emit(c, base, own, path, query.removeprefix("query."), "")

    def emit(c: Block, base, own, path, query: str, note: str):
        tags = _resolve(base, locals_)
        tags.update(own)
        name = c.labels[0]
        item_from_title, title = _split_title(_string(c.attrs.get("title"), "title"))
        item = tags.get("cis_item_id", "")
        anomalies = [note] if note else []
        if item and item_from_title and item != item_from_title:
            anomalies.append(f"tag cis_item_id={item} difere do número do título={item_from_title}")
        if not item:
            anomalies.append("sem tag cis_item_id; usado o número do título")
        item = item or item_from_title
        if name in emitted:
            raise ExtractError(f"{bench_id}: item {name} aparece duas vezes na árvore")
        emitted.add(name)
        sec = path[0] if path else ("", "")
        sub = path[1] if len(path) > 1 else ("", "")
        out.append(Control(
            provider=provider, benchmark_id=bench_id, cis_version=cis_version, benchmark_title=root_title,
            control_id=name, cis_item_id=item, section_id=sec[0], section_title=sec[1],
            subsection_id=sub[0], subsection_title=sub[1],
            title=title, cis_level=tags.get("cis_level", ""), cis_type=tags.get("cis_type", ""),
            service=tags.get("service", ""), query=query,
            source_file=c.file, source_line=c.line,
            parent_id=path[-1][0] if path else "", parent_title=path[-1][1] if path else "",
            title_item_id=item_from_title,
            anomaly="; ".join(anomalies),
        ))

    for child in _refs(root.attrs.get("children")):
        walk(child, [])
    orphans = sorted(set(controls) - seen)
    if orphans:
        raise ExtractError(f"{bench_id}: controles definidos fora da árvore: {orphans[:5]}")
    return out
