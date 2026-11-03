"""Regras de commit (C00): assunto '[ID] texto' em português simples, sem atribuição nem menção a IA,
e o conjunto de commits que pertence a um módulo (usado pelo commit_lint e pelo ownership_check)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import core
from .catalog import Catalog, module_of_subject
from .core import BoError

MAX_SUBJECT = 72
COORD = "COORD"

# (rótulo, regex). Nada de atribuição, assinatura de ferramenta ou menção a IA/modelo.
FORBIDDEN: list[tuple[str, re.Pattern]] = [
    ("co-authored-by", re.compile(r"co-?authored-?by", re.I)),
    ("menção a Claude", re.compile(r"\bclaude\b", re.I)),
    ("menção a Anthropic", re.compile(r"\banthropic\b", re.I)),
    ("menção a OpenAI/ChatGPT/GPT", re.compile(r"\b(openai|chatgpt|gpt[-\s]?\d+(\.\d+)?|gpt)\b", re.I)),
    ("menção a Copilot/Codex/Gemini", re.compile(r"\b(copilot|codex|gemini|bard|llama|mistral)\b", re.I)),
    ("nome de modelo", re.compile(r"\b(opus|sonnet|haiku|fable)\b", re.I)),
    ("menção a LLM", re.compile(r"\bllms?\b", re.I)),
    ("menção a IA", re.compile(r"\b(IA|AI|IAs)\b")),
    ("menção a inteligência artificial", re.compile(r"intelig[eê]ncia\s+artificial|artificial\s+intelligence", re.I)),
    ("assinatura 'gerado com/por'", re.compile(r"\b(generated|gerad[oa]s?)\s+(with|by|com|por|pel[oa])\b", re.I)),
    ("emoji de robô", re.compile("\U0001F916")),
    ("e-mail de bot", re.compile(r"noreply@|no-reply@", re.I)),
]

PT_WORDS = set("""
de da do das dos e em no na nos nas num numa para pra com por pelo pela pelos pelas que o a os as um uma uns
umas sem ao aos à às se não mais menos entre sobre como até já só também cada todo toda todos todas
cria adiciona acrescenta corrige retira tira apaga atualiza ajusta inicia implementa grava documenta renomeia
troca separa testa congela marca refaz liga desliga inclui exclui melhora simplifica reorganiza gera regenera
escreve lê valida confere verifica registra fixa prende solta publica prepara termina conclui usa passa falha
mergeia junta divide limpa mostra explica descreve protege bloqueia libera aceita recusa reprova aprova roda
ferramentas ferramenta testes teste módulo módulos repositório regras regra arquivo arquivos dados linter
comprovante comprovantes congelamento entrada entradas saída saídas trava travas papel papéis leitura
convenções caminhos posse estado retrato catálogo integração gates
""".split())

EN_WORDS = set("""
the and of to for with add adds added fix fixes fixed update updates updated from into this that is are use
uses used initial create creates created implement implements refactor bump rename renames delete deletes
improve improves support new on by when should make makes made wip tweak cleanup
""".split())


def _letters(text: str) -> list[str]:
    toks = []
    for t in re.split(r"\s+", text):
        t = t.strip(".,;:!?()[]{}\"'`")
        if not t or re.search(r"[/_=.\d<>@#$]", t):
            continue
        if all(unicodedata.category(c).startswith("L") or c == "-" for c in t):
            toks.append(t.lower())
    return toks


def language_score(text: str) -> tuple[int, int]:
    toks = _letters(text)
    pt = sum(t in PT_WORDS for t in toks) + (1 if re.search(r"[ãõçáéíóúâêôà]", text, re.I) else 0)
    en = sum(t in EN_WORDS for t in toks)
    return pt, en


@dataclass
class Problem:
    commit: str
    rule: str

    def __str__(self) -> str:
        return f"{self.commit}: {self.rule}"


def lint_message(msg: str, expected_id: str | None = None, known_ids: set[str] | None = None,
                 ref: str = "mensagem") -> list[Problem]:
    probs = []
    lines = msg.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    lines = [ln for ln in lines if not ln.startswith("#")]  # comentários do editor do git
    if not lines:
        return [Problem(ref, "mensagem vazia")]
    subject = lines[0].rstrip()
    mid = module_of_subject(subject)
    if mid is None:
        probs.append(Problem(ref, "assunto tem de começar com '[ID] ' (ex.: '[REPO] cria o lock.sh')"))
    elif expected_id and mid not in (expected_id,):
        probs.append(Problem(ref, f"assunto marcado [{mid}] numa branch do módulo {expected_id}"))
    elif known_ids is not None and mid not in known_ids and mid != COORD:
        probs.append(Problem(ref, f"[{mid}] não é módulo do catálogo"))
    if len(subject) > MAX_SUBJECT:
        probs.append(Problem(ref, f"assunto com {len(subject)} caracteres (máx. {MAX_SUBJECT})"))
    text = "\n".join(lines)
    for label, rx in FORBIDDEN:
        if rx.search(text):
            probs.append(Problem(ref, f"proibido: {label}"))
    body = re.sub(r"^\[[A-Z0-9-]+\]\s*", "", text)
    pt, en = language_score(body)
    if pt == 0 or en >= pt:
        probs.append(Problem(ref, f"não parece português (pt={pt}, en={en}); escreva em português simples"))
    return probs


# ---------------------------------------------------------------- commits de um módulo

def module_commits(repo: Path, cat: Catalog | None, branch: str, mid: str | None = None) -> tuple[str, list[str]]:
    """(id, commits): commits ainda não mergeados (base..branch) mais os commits '[ID] ...' alcançáveis."""
    if not core.ref_exists(repo, branch):
        raise BoError(f"branch {branch} não existe em {repo}", code=2)
    if mid is None:
        m = cat.by_branch(branch) if cat else None
        mid = m.id if m else branch.removeprefix("bo/").upper()
    base = core.base_branch()
    unmerged = core.git(repo, "rev-list", f"{base}..{branch}").split() if core.ref_exists(repo, base) else []
    out = list(unmerged)
    for line in core.git(repo, "log", branch, "--format=%H%x09%s").splitlines():
        sha, _, subj = line.partition("\t")
        if module_of_subject(subj) == mid and sha not in out:
            out.append(sha)
    return mid, out


def commit_message(repo: Path, sha: str) -> str:
    return core.git(repo, "log", "-1", "--format=%B", sha)


def is_merge(repo: Path, sha: str) -> bool:
    return len(core.git(repo, "rev-list", "--parents", "-n", "1", sha).split()) > 2
