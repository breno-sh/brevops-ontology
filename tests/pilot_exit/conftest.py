"""Fixtures dos testes do PILOT-EXIT: só dados sintéticos criados aqui (nunca as retidas)."""
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def work(tmp_path):
    """Pasta nova por teste; com o ambiente da lane, TMPDIR = $BO_TMP (nunca /tmp)."""
    tmp = os.environ.get("BO_TMP")
    if tmp:
        assert str(tmp_path).startswith(str(Path(tmp).resolve())) or str(tmp_path).startswith(tmp), \
            f"teste fora de $BO_TMP: {tmp_path}"
    return tmp_path


@pytest.fixture()
def keypair(work):
    """Par RSA descartável e certificado autoassinado (CN=teste-sintetico); nada a ver com a chave D15."""
    key, cert = work / "k.pem", work / "c.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=teste-sintetico"], check=True, capture_output=True)
    return key, cert
