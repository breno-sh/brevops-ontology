"""Gate: taxa sem janela declarada reprova.

  python -I -m bo.units.rate_window [value_space.jsonl]

A janela (PT1S, PT5M, ...) é parte do tipo (N4). Um registro é TAXA quando qualquer sinal independente diz que é:
  (a) a grandeza ou a unidade gravada é de taxa (…Rate, Frequency, unidade -PER-);
  (b) o nome do atributo numérico termina em sufixo de taxa (_per_second, _per_minute, _rps, _qps, _tps, _iops,
      _mbps, _gbps, _kbps, _mibps ...);
  (c) a frase publicada do fato de unidade citado na evidência traz taxa ('per second', '/s', 'MiB/s', 'Mbps',
      'IOPS', 'per 5 minutes').
Reprova: taxa com grandeza conhecida e sem rate_window; taxa numérica marcada NOT_APPLICABLE; unidade -PER- com
janela (tempo contado duas vezes); janela que não é xsd:duration fixa e positiva; janela em registro sem grandeza;
tipo (unidade, janela, convenção) que o registro do TRANSFORMS não aceita.
Taxa com grandeza UNKNOWN passa: não há tipo afirmado (é o UNKNOWN honesto, contado no relatório).
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from bo.transforms import units as tu
from bo.transforms.errors import TransformError

from .build import PROVIDERS, bo_data, out_dir
from .rules import BYTE_CONV

RATE_QK = re.compile(r"(Rate|Frequency)")
RATE_NAME = re.compile(r"(?:_per_(?:second|sec|minute|min|hour|day)|(?:^|_)(?:rps|qps|tps|iops|bps|kbps|mbps|gbps|"
                       r"mibps|gibps|kibps))$")
RATE_SENTENCE = re.compile(r"\bper\s+(?:\d+\s+)?(?:seconds?|secs?|minutes?|mins?|hours?|days?)\b|/s\b|/sec\b|"
                           r"\b[KMGT]i?B/s\b|\b[KMGT]?[Bb]ps\b|\bIOPS\b")
NUMERIC = ("integer", "decimal", "duration")


def unit_sentences(ids: set[str]) -> dict[str, str]:
    out = {}
    for P, _ in PROVIDERS:
        p = bo_data() / f"DOCS-{P}" / "docs_facts.jsonl"
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if '"unit"' not in line:
                    continue
                r = json.loads(line)
                if r["fact_kind"] == "unit" and r["fact_id"] in ids:
                    out[r["fact_id"]] = (r.get("source") or {}).get("sentence", "")
    return out


def signals(r: dict, sentences: dict[str, str]) -> list[str]:
    s = []
    if RATE_QK.search(r["quantity_kind"]) or "-PER-" in r["unit_qudt"]:
        s.append("grandeza/unidade de taxa")
    dt = r["datatype"]
    numeric = dt["kind"] == "scalar" and dt["scalar"] in NUMERIC
    if numeric and RATE_NAME.search(r["atom_id"].rsplit(".", 1)[-1].rsplit(":", 1)[-1].lower()):
        s.append("nome com sufixo de taxa")
    for e in r["evidence"]:
        sent = sentences.get(e.get("ref", ""))
        if sent and RATE_SENTENCE.search(sent):
            s.append(f"frase publicada com taxa ({e['ref']})")
            break
    return s


def check_record(r: dict, sentences: dict[str, str]) -> tuple[list[str], bool]:
    errs = []
    qk, un, w, bc = r["quantity_kind"], r["unit_qudt"], r["rate_window"], r["byte_convention"]
    dt = r["datatype"]
    numeric = dt["kind"] == "scalar" and dt["scalar"] in NUMERIC
    sig = signals(r, sentences)
    is_rate = bool(sig)
    if w is not None:
        try:
            tu.fixed_window_seconds(w)
        except TransformError as e:
            errs.append(f"janela {w!r} inválida: {e}")
        if qk in ("NOT_APPLICABLE", "UNKNOWN"):
            errs.append(f"janela {w} sem grandeza declarada ({qk})")
        if "-PER-" in un:
            errs.append(f"unidade {un} já é taxa e ainda tem janela {w} (tempo contado duas vezes)")
    if is_rate and w is None:
        if qk == "NOT_APPLICABLE" and numeric:
            errs.append(f"taxa numérica marcada NOT_APPLICABLE ({'; '.join(sig)})")
        elif qk not in ("NOT_APPLICABLE", "UNKNOWN"):
            errs.append(f"taxa sem rate_window: {qk} {un} ({'; '.join(sig)})")
    if un not in ("NOT_APPLICABLE", "UNKNOWN"):
        try:
            reg = tu.UNITS[un]
            conv = bc if reg.byte_convention is not None else None
            if reg.byte_convention is None and bc != BYTE_CONV.get(un, "NOT_APPLICABLE"):
                errs.append(f"convenção {bc} diferente da declarada para {un}")
            tu.UnitType(un, w, conv).checked()
        except (TransformError, KeyError) as e:
            errs.append(f"tipo ({un}, {w}, {bc}) recusado pelo registro do TRANSFORMS: {e}")
    return errs, is_rate


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    path = Path(argv[0]) if argv else out_dir() / "value_space.jsonl"
    if not path.exists():
        print(f"REPROVADO: {path} não existe")
        return 1
    recs = [json.loads(x) for x in open(path, encoding="utf-8")]
    ids = {e["ref"] for r in recs for e in r["evidence"] if e.get("ref", "").startswith("DF-")}
    sentences = unit_sentences(ids)
    c, errs = Counter(), []
    for i, r in enumerate(recs, 1):
        e, is_rate = check_record(r, sentences)
        c["records"] += 1
        if is_rate:
            c["rate_signal"] += 1
            c["rate_with_window" if r["rate_window"] else ("rate_unknown_type" if r["quantity_kind"] == "UNKNOWN"
                                                         else "rate_without_window")] += 1
        if r["rate_window"]:
            c[f"window={r['rate_window']}"] += 1
        errs += [f"{path.name}:{i} {r['atom_id']}: {x}" for x in e]
    for e in errs[:40]:
        print("  " + e)
    wins = ", ".join(f"{k[7:]}={v}" for k, v in sorted(c.items()) if k.startswith("window="))
    print(f"rate_window: {c['records']} registros; {c['rate_signal']} com sinal de taxa: {c['rate_with_window']} com "
          f"janela, {c['rate_unknown_type']} com tipo UNKNOWN; janelas: {wins}; {len(errs)} erro(s)")
    if c["records"] == 0:
        print("REPROVADO: value_space vazio")
        return 1
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
