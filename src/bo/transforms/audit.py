"""Gate: todo item do registro tem domínio, codomínio, pré-condição, erro, perda e inversa parcial — e as
declarações são verdadeiras (python -I -m bo.transforms.audit).

Confere no transforms/transforms.yaml PUBLICADO:
  1. validador oficial do C10 (schema + regras C10-KIND, C10-CAL, C10-INV) e igualdade com o registro do código;
  2. campos: domínio/codomínio (escalar) ou portas nomeadas e tipadas (combinador); pré-condição com conteúdo;
     erro = 'nunca' ou 'CÓDIGO: quando | ...' com códigos do registro; perda = 'nenhuma' ou tipos do loss_contract;
     inversa {name, partial} com name declarado no documento (ou null com partial false);
  3. erro executável: todo código declarado aparece num exemplo que o levanta, e nenhum exemplo levanta código
     não declarado; ao menos um exemplo positivo por item;
  4. inversa executável: partial=false -> TODO exemplo positivo volta pela inversa; partial=true -> ao menos um
     volta e ao menos um não volta (ou a instância não tem inversa), prova de que a parcialidade é real.
"""

from __future__ import annotations

import subprocess
import sys

from . import common as C
from . import comparators as CMP
from . import registry as R
from .errors import ERROR_CODES, TransformError
from .examples import run_example, same_input

_PLACEHOLDER = ("todo", "tbd", "xxx", "pendente", "a definir", "placeholder")


def _apply(t, ex):
    if isinstance(t, R.Scalar):
        return R.apply_scalar(t.name, ex.value, ex.params, ex.ctx)
    return R.apply_combinator(t.name, ex.value, ex.ctx)


def _roundtrips(t, ex):
    """True/False se volta pela inversa; None se a instância não tem inversa."""
    got = _apply(t, ex)
    inv = R.invert(t.name, ex.params, ex.value, got)
    if inv is None:
        return None
    name, p = inv
    try:
        back = R.apply_scalar(name, got, p, ex.ctx) if isinstance(t, R.Scalar) else R.apply_combinator(name, p, ex.ctx)
    except TransformError:
        return False
    return same_input(t, back, ex.value)


def check_item(item: dict, names: set, code_item) -> list[str]:
    errs = []
    n = item.get("name", "?")
    for f in ("precondition", "error", "loss", "inverse"):
        if f not in item:
            errs.append(f"{n}: sem {f}")
    if item.get("kind") == "scalar":
        for f in ("domain", "codomain"):
            d = item.get(f) or {}
            if d.get("datatype") not in R.DATATYPES or not d.get("quantity_kind"):
                errs.append(f"{n}: {f} sem datatype/quantity_kind válidos: {d}")
    else:
        for f in ("inputs", "outputs"):
            ports = item.get(f) or []
            if not ports or any(p.get("datatype") not in R.DATATYPES or not p.get("name") for p in ports):
                errs.append(f"{n}: {f} sem portas nomeadas e tipadas")
    pre = item.get("precondition", "")
    if len(pre) < 6 or any(w in pre.lower() for w in _PLACEHOLDER):
        errs.append(f"{n}: pré-condição vazia ou de marcador: {pre!r}")
    for code, when in R.parse_error_field(item.get("error", "")):
        if code not in ERROR_CODES:
            errs.append(f"{n}: código de erro fora do registro: {code!r}")
        if len(when) < 3:
            errs.append(f"{n}: erro {code} sem dizer quando")
    for k in R.parse_loss_field(item.get("loss", "")):
        if k not in R.LOSS_KINDS:
            errs.append(f"{n}: tipo de perda fora do loss_contract: {k!r}")
    inv = item.get("inverse") or {}
    if set(inv) != {"name", "partial"}:
        errs.append(f"{n}: inversa sem name/partial")
    elif inv["name"] is None and inv["partial"]:
        errs.append(f"{n}: sem inversa mas partial=true")
    elif inv["name"] is not None and inv["name"] not in names:
        errs.append(f"{n}: inversa {inv['name']} não declarada")
    # ------------------------------------------------------------------ declarações executáveis
    t = code_item
    exs = list(t.examples)
    declared = {c for c, _ in t.errors}
    raised = {ex.err for ex in exs if ex.err}
    for c in sorted(declared - raised):
        errs.append(f"{n}: erro {c} declarado sem exemplo que o levante")
    for c in sorted(raised - declared):
        errs.append(f"{n}: exemplo levanta {c}, não declarado no campo error")
    pos = [ex for ex in exs if ex.err is None]
    if not pos:
        errs.append(f"{n}: nenhum exemplo positivo")
    for i, ex in enumerate(exs):
        ok, why = run_example(t, ex)
        if not ok:
            errs.append(f"{n}[{i}]: {why}")
    if isinstance(t, R.Scalar) and any(v.get("part_of") in ("domain", "domain_keys_image_values")
                                       for v in t.params.values()):
        for i, ex in enumerate(exs):
            try:
                dom = R.finite_domain(t.name, ex.params)
            except TransformError:
                continue
            if dom is None:
                errs.append(f"{n}: declara domínio finito nos params e finite_domain dá None")
                continue
            inside = not isinstance(ex.value, dict) and ex.value in dom
            if (ex.err is None) != inside and ex.err != "DECLARATION_ERROR":
                errs.append(f"{n}[{i}]: exemplo {'positivo fora' if ex.err is None else 'de erro dentro'} do domínio "
                            f"finito {sorted(map(str, dom))}")
    if t.inverse is not None:
        rts = [_roundtrips(t, ex) for ex in pos]
        if not t.partial:
            bad = [i for i, r in enumerate(rts) if r is not True]
            if bad:
                errs.append(f"{n}: inversa total (partial=false) não volta nos exemplos positivos {bad}")
        else:
            if True not in rts:
                errs.append(f"{n}: inversa parcial sem nenhum exemplo de ida e volta")
            if not any(r is not True for r in rts):
                errs.append(f"{n}: partial=true sem exemplo que mostre a parcialidade")
    return errs


def main(argv=None) -> int:
    path = C.transforms_yaml()
    errs = []
    if not path.is_file():
        print(f"REPROVADO: {path} não existe", file=sys.stderr)
        return 1
    r = subprocess.run([sys.executable, "-I", "-m", "bo.contracts.validate", "transforms", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        errs.append("validador do C10 reprovou: " + (r.stdout + r.stderr).strip()[-800:])
    doc = C.load_yaml(path)
    if doc != R.document():
        errs.append("transforms.yaml publicado difere do registro do código (rode python -I -m bo.transforms.build)")
    items = (doc.get("scalar") or []) + (doc.get("combinators") or [])
    names = {i.get("name") for i in items}
    if names != set(R.REGISTRY):
        errs.append(f"nomes do documento ≠ registro: {sorted(names ^ set(R.REGISTRY))}")
    per = {}
    for it in items:
        e = check_item(it, names, R.REGISTRY.get(it.get("name")))
        per[it["name"]] = {"errors": e, "examples": len(R.REGISTRY[it["name"]].examples)}
        errs += e
    n_ex = sum(len(t.examples) for t in R.REGISTRY.values())
    rep = C.report("audit", {"ok": not errs, "items": len(items), "scalar": len(doc.get("scalar") or []),
                             "combinators": len(doc.get("combinators") or []), "examples": n_ex,
                             "errors": errs, "per_item": per})
    if errs:
        for e in errs:
            print(f"REPROVADO: {e}", file=sys.stderr)
        return 1
    C.say(f"audit: {len(items)} itens ({len(doc['scalar'])} escalares, {len(doc['combinators'])} combinadores), "
          f"{n_ex} exemplos executados; todo item com domínio, codomínio, pré-condição, erro, perda e inversa "
          f"conferidos -> OK ({rep})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
