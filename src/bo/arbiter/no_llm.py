"""Gate de HIGIENE (não é evidência de validade): o árbitro não importa cliente de LLM nem de rede.

Uso: python -I -m bo.arbiter.no_llm

Três partes:
  estática   AST de todo .py congelado (arbiter/ARBITER.sha256, ou o fecho de importação se o manifesto ainda não
             existe): import, from-import, importlib.import_module('x') e __import__('x') com texto constante;
             reprova raiz de cliente de LLM ou de rede.
  dinâmica   num interpretador limpo, instala ANTES de importar o árbitro um importador que recusa as raízes de
             LLM e desliga o socket; julga o mundo plantado; reprova se algo tentou importar LLM, abriu socket
             ou se uma raiz de LLM aparece em sys.modules. Módulos de rede da biblioteca padrão carregados por
             bibliotecas de terceiros (o rdflib carrega urllib.request) são relatados; o que conta é nenhum
             socket aberto e nenhuma importação de rede no código congelado (parte estática).
  controle   o detector estático tem de achar as importações de um texto sintético proibido (não é vazio).
Relatório: $BO_DATA/ARBITERLIB/no_llm.json.
"""

from __future__ import annotations

import ast
import sys

from .common import emit, now, repo, write_report

LLM_ROOTS = ("anthropic", "openai", "google.generativeai", "google.genai", "google.ai", "vertexai", "mistralai",
             "cohere", "ollama", "langchain", "langchain_core", "langchain_community", "langchain_openai",
             "langchain_anthropic", "llama_index", "llama_cpp", "litellm", "transformers", "huggingface_hub", "vllm",
             "groq", "together", "replicate", "dspy", "guidance", "instructor", "claude_agent_sdk", "boto3", "botocore")
NET_ROOTS = ("requests", "httpx", "aiohttp", "urllib3", "urllib.request", "http.client", "websocket", "websockets",
             "grpc")
FORBIDDEN = LLM_ROOTS + NET_ROOTS


def forbidden(mod: str) -> str | None:
    for r in FORBIDDEN:
        if mod == r or mod.startswith(r + "."):
            return r
    return None


def scan_source(text: str, where: str) -> list[dict]:
    hits = []
    tree = ast.parse(text, filename=where)
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Call):
            f = node.func
            fname = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if fname in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                names = [node.args[0].value]
        for n in names:
            r = forbidden(n)
            if r:
                hits.append({"file": where, "line": getattr(node, "lineno", 0), "import": n, "root": r})
    return hits


def frozen_py() -> list[str]:
    p = repo() / "arbiter" / "ARBITER.sha256"
    if p.exists():
        files = [ln.split("  ", 1)[1] for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        from .freeze import code_files
        files = code_files()
    return sorted(f for f in files if f.endswith(".py"))


_DYN = r"""
import importlib.abc, json, socket, sys
from bo.arbiter.no_llm import LLM_ROOTS, NET_ROOTS
tried, opened = [], []
def bad(n):
    return any(n == r or n.startswith(r + ".") for r in LLM_ROOTS)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if bad(name):
            tried.append(name)
            raise ImportError("no_llm: " + name)
        return None
sys.meta_path.insert(0, Block())
real = socket.socket
class NoNet(real):
    def __init__(self, *a, **k):
        opened.append(1)
        raise OSError("no_llm: rede desligada")
socket.socket = NoNet
from bo.arbiter import battery as B, engine
claims, _, _ = B.world()
res = engine.arbitrate(B.items_of(claims), decided_at="2026-11-03T00:00:00-03:00", arbiter_sha256="0" * 64)
print(json.dumps({"verdicts": len(res["verdicts"]), "blocked_imports": tried, "sockets": len(opened),
                  "llm_in_sys_modules": sorted(m for m in sys.modules if bad(m)),
                  "net_stdlib_loaded_by_libraries": sorted(m for m in sys.modules
                      if any(m == r or m.startswith(r + ".") for r in NET_ROOTS))}))
"""


def dynamic() -> dict:
    """Interpretador limpo: o bloqueio de LLM e o socket desligado entram ANTES de importar o árbitro."""
    import json
    import os
    import subprocess
    out = subprocess.run([sys.executable, "-I", "-B", "-c", _DYN], capture_output=True, text=True,
                         env=dict(os.environ, BO_REPO=str(repo())), check=False)
    if out.returncode != 0:
        return {"verdicts": 0, "error": out.stderr.strip()[-600:], "blocked_imports": ["?"], "sockets": 0,
                "llm_in_sys_modules": []}
    return json.loads(out.stdout.strip().splitlines()[-1])


CONTROL = "import openai\nfrom langchain.llms import Base\nimport importlib\nimportlib.import_module('anthropic')\n" \
          "import requests\n"


def main(argv=None) -> int:
    files = frozen_py()
    hits = []
    for rel in files:
        hits += scan_source((repo() / rel).read_text(encoding="utf-8"), rel)
    ctl = scan_source(CONTROL, "<controle>")
    dyn = dynamic()
    ok_ctl = {h["root"] for h in ctl} >= {"openai", "langchain", "anthropic", "requests"}
    ok = not hits and ok_ctl and not dyn["blocked_imports"] and not dyn["sockets"] and \
        not dyn["llm_in_sys_modules"] and dyn["verdicts"] > 0
    for h in hits:
        emit(f"  FALHA {h['file']}:{h['line']}: importa {h['import']}")
    p = write_report("no_llm", {"label": "higiene", "files_scanned": len(files), "hits": hits, "control_hits": ctl,
                                "control_ok": ok_ctl, "dynamic": dyn, "forbidden_roots": list(FORBIDDEN), "pass": ok})
    emit(f"[{now()}] no_llm (# higiene): {len(files)} arquivo(s) congelado(s), {len(hits)} importação(ões) proibida(s); "
         f"julgamento com importador bloqueado e sem rede: {dyn['verdicts']} veredito(s), {len(dyn['blocked_imports'])} "
         f"tentativa(s); controle {'acha' if ok_ctl else 'NÃO acha'} as 4 raízes; relatório {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
