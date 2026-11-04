"""Prova, uma vez, que a partição retida abre com a chave privada da VM (D15) sem trazer o texto claro.

  python -I -m bo.pilot_sto_oracle.seal_verify      envia o cifrado à VM pelo ssh, decifra LÁ dentro de um pipe e
                                                    devolve só o sha256 e o tamanho do texto claro; compara com o
                                                    SEALED_INDEX.json e grava results/PILOT-STO-ORACLE/seal_verification.json

Não é gate (depende de rede): o resultado gravado é a evidência; o gate confere o cifrado contra o índice.
"""
from __future__ import annotations

import json
import subprocess
import sys

from .build import MODULE, canon, now_iso, repo, sealed_dir, sha_file

VM = "ubuntu@136.248.69.238"
REMOTE = ("openssl cms -decrypt -inform PEM -inkey ~/brevops-keys/seal_private.pem -recip ~/brevops-keys/seal_cert.pem "
          "| tee >(wc -c >&2) | sha256sum")


def main(argv=None) -> int:
    sd = sealed_dir()
    idx = json.loads((sd / "SEALED_INDEX.json").read_text(encoding="utf-8"))
    ct = (sd / "heldout.cms.pem").read_bytes()
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", VM, f"bash -c '{REMOTE}'"],
                       input=ct, capture_output=True, timeout=120)
    remote_sha = r.stdout.decode().split()[0] if r.returncode == 0 and r.stdout else None
    size = r.stderr.decode().strip().splitlines()[-1] if r.stderr else None
    ok = remote_sha == idx["plaintext_sha256"] and sha_file(sd / "heldout.cms.pem") == idx["ciphertext_sha256"]
    rep = {"schema": "bo.pilot.sto.seal_verification/1", "module": MODULE, "checked_at": now_iso(),
           "where": "VM Oracle do Breno (D15); decifrado só num pipe remoto, nada gravado lá nem aqui",
           "ciphertext_sha256": idx["ciphertext_sha256"], "plaintext_sha256_index": idx["plaintext_sha256"],
           "plaintext_sha256_remote": remote_sha, "plaintext_bytes_remote": size,
           "recipient_fingerprint_sha256": idx["recipient_fingerprint_sha256"], "result": "MATCH" if ok else "MISMATCH"}
    out = repo() / "results" / MODULE / "seal_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(canon(rep))
    print(json.dumps(rep, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
