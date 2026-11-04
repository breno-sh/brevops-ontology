"""Regeneração idêntica do HIST-GCP, offline (chamado por gates/HIST-GCP.sh).

  python -I -m bo.hist_gcp.regen_check

Para cada versão extraída, a partir da saída crua guardada ($BO_DATA/downloads/hist-gcp/google-V/schema/):
  átomos refeitos pela biblioteca, duas vezes, em $BO_TMP -> mesmos bytes entre si e iguais ao atoms_V.jsonl.gz
  guardado (sha do JSONL e do gzip). Depois, versions.json e extraction.json refeitos a partir dos receipts e da
  lista do PINS -> iguais aos guardados, fora o generated_at. results/HIST-GCP/history_counts.json refeito -> igual.
O binário do provider não é executado de novo (foi apagado depois da extração, como manda o brief); a prova de que a
saída crua é a do binário assinado está no receipt (sha do binário, h1 = h1 do zip do SHA256SUMS assinado) e, no pin,
no schema_sha256 do pins.json, que o PINS obteve de outra extração.
"""

from __future__ import annotations

import json
import sys

from . import atoms as A
from . import common as C
from . import pipeline as P
from . import results as R


def main(argv=None) -> int:
    args = [a for a in (argv or []) if a != C.ID]
    if args:
        print(f"regen_check: argumentos desconhecidos: {args}", file=sys.stderr)
        return 2
    hist = C.history()
    xd = json.loads((C.out_dir() / "extraction.json").read_text(encoding="utf-8"))
    problems, n = [], 0
    results = {}
    for row in xd["versions"]:
        v = row["version"]
        if row["status"] != "extracted":
            results[v] = {"status": row["status"], "reason": row["reason"], "evidence": row["evidence"]}
            continue
        rec = json.loads(C.receipt_path(v).read_text(encoding="utf-8"))
        results[v] = {"status": "extracted", "receipt": rec}
        raw = C.raw_schema_dir(v) / "schema.json.gz"
        runs = []
        for i in (1, 2):
            b, _ = A.build_bytes(raw, v)
            runs.append((C.sha256_bytes(b), C.sha256_bytes(C.gzip_bytes(b, f"atoms_{v}.jsonl"))))
        if runs[0] != runs[1]:
            problems.append(f"{v}: as duas regenerações divergem")
        if runs[0] != (rec["atoms"]["jsonl_sha256"], rec["atoms"]["gz_sha256"]):
            problems.append(f"{v}: regenerado != guardado")
        if C.sha256_file(C.atoms_path(v)) != rec["atoms"]["gz_sha256"]:
            problems.append(f"{v}: atoms_{v}.jsonl.gz != receipt")
        n += 1
    gen_v = json.loads((C.out_dir() / "versions.json").read_text(encoding="utf-8"))
    vd = P.versions_doc(hist, results, gen_v["generated_at"])
    if vd != gen_v:
        problems.append("versions.json não regenera igual (fora o generated_at)")
    xd2 = P.extraction_doc(hist, C.pins(), C.terraform_binary(), C.vendor_key(), results, xd["generated_at"])
    if xd2 != xd:
        problems.append("extraction.json não regenera igual (fora o generated_at)")
    cp = C.results_dir() / "history_counts.json"
    old = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else None
    if old is None or R.counts_doc(xd, old.get("generated_at", "")) != old:
        problems.append("results/HIST-GCP/history_counts.json não regenera igual (fora o generated_at)")
    print(f"[{C.now()}] regen_check {C.ID}: {n} versões, átomos refeitos 2x da saída crua; versions.json, "
          f"extraction.json e history_counts.json refeitos -> {'PASS' if not problems else 'FAIL'}")
    for p in problems:
        print(f"  FAIL {p}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
