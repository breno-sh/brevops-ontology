"""Conferência de assinatura OpenPGP do SHA256SUMS com gpgv (sem agente, sem chaveiro do usuário).

A chave pública vem do próprio Terraform Registry (signing_keys.gpg_public_keys[].ascii_armor da rota de
download). Tudo roda num diretório temporário em $BO_TMP, apagado ao fim; HOME do usuário não é lido."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config


class SigError(Exception):
    pass


def _tool(name: str) -> str:
    for d in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        p = Path(d) / name
        if p.exists():
            return str(p)
    found = shutil.which(name)
    if not found:
        raise SigError(f"{name} não encontrado")
    return found


def verify(data: Path, sig: Path, key_armor: str) -> dict:
    """Confere a assinatura destacada `sig` sobre `data`. Devolve {valid, good, expired_key, fingerprint,
    primary_fingerprint, sig_date, status}; levanta SigError se não houver VALIDSIG. `good` = GOODSIG (chave
    dentro da validade); `expired_key` = EXPKEYSIG (assinatura correta, mas a cópia da chave está vencida)."""
    tmp = Path(tempfile.mkdtemp(prefix="gpgv-", dir=config.bo_tmp()))
    try:
        home = tmp / "h"
        home.mkdir(mode=0o700)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "GNUPGHOME": str(home), "LC_ALL": "C"}
        asc = tmp / "key.asc"
        asc.write_text(key_armor, encoding="utf-8")
        kr = tmp / "key.gpg"
        r = subprocess.run([_tool("gpg"), "--batch", "--no-options", "--homedir", str(home), "--dearmor",
                            "--output", str(kr), str(asc)], capture_output=True, text=True, env=env, timeout=60)
        if r.returncode != 0 or not kr.exists():
            raise SigError(f"gpg --dearmor falhou: {r.stderr.strip()[:200]}")
        r = subprocess.run([_tool("gpgv"), "--homedir", str(home), "--status-fd", "1", "--keyring", str(kr),
                            str(sig), str(data)], capture_output=True, text=True, env=env, timeout=60)
        status = [ln for ln in r.stdout.splitlines() if ln.startswith("[GNUPG:]")]
        valid = [ln.split() for ln in status if ln.split()[1:2] == ["VALIDSIG"]]
        if r.returncode != 0 or not valid:
            raise SigError(f"assinatura inválida para {data.name}: {' | '.join(status)[:300]}")
        f = valid[0]
        kinds = {ln.split()[1] for ln in status}
        return {"valid": True, "good": "GOODSIG" in kinds, "expired_key": "EXPKEYSIG" in kinds,
                "fingerprint": f[2], "primary_fingerprint": f[11] if len(f) > 11 else f[2], "sig_date": f[3],
                "status": [" ".join(ln.split()[:2]) for ln in status]}
    finally:
        if (tmp / "h").exists():
            subprocess.run([_tool("gpgconf"), "--homedir", str(tmp / "h"), "--kill", "all"],
                           capture_output=True, env={"PATH": "/usr/bin:/bin"}, timeout=30)
        shutil.rmtree(tmp, ignore_errors=True)
