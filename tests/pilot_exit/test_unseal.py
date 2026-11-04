"""Abertura das retidas: com envelope e índice SINTÉTICOS (chave descartável), confere que o caminho certo abre e
que qualquer adulteração (envelope, texto claro, item, contagem, sal) reprova."""
import copy
import hashlib
import io
import json
import subprocess
import tarfile

import pytest

from bo.pilot_exit import unseal as U


def sto_canon(o):
    return (json.dumps(o, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode()


def net_canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def encrypt(plain, cert):
    return subprocess.run(["openssl", "cms", "-encrypt", "-binary", "-aes256", "-outform", "PEM", str(cert)],
                          input=plain, capture_output=True, check=True).stdout


def local(key, cert):
    return ["openssl", "cms", "-decrypt", "-inform", "PEM", "-inkey", str(key), "-recip", str(cert)]


def sto_bundle():
    fx = {"fixture_id": "FX-SYN-1", "provider": "pa", "case": "MC-X", "polarity": "positive", "summary": "s"}
    ent = {"entry_id": "DX-SYN-1", "direction": "aws->google", "family": "T1", "polarity": "negative",
           "source": {"a": 1}, "target": {"b": 2}}
    return {"schema": "x", "fixtures": [{"fixture": fx, "checks": [{"kind": "claim"}]}], "entries": [ent]}


def sto_index(b, env, plain):
    items = [{"item_id": "FX-SYN-1", "kind": "fixture", "sha256": sha(sto_canon(b["fixtures"][0]["fixture"]))},
             {"item_id": "DX-SYN-1", "kind": "direction_entry",
              "sha256": sha(sto_canon({"source": b["entries"][0]["source"], "target": b["entries"][0]["target"]}))}]
    return {"ciphertext_sha256": sha(env), "plaintext_sha256": sha(plain), "items": items,
            "counts": {"fixtures": 1, "direction_entries": 1, "checks": 1}}


def test_sto_abre_e_confere(keypair):
    key, cert = keypair
    b = sto_bundle()
    plain = sto_canon(b)
    env = encrypt(plain, cert)
    idx = sto_index(b, env, plain)
    out = U.open_slice("sto", decrypt_argv=local(key, cert), idx=idx, envelope=env)
    assert out["bundle"] == b and out["n_items"] == 2 and out["plaintext_sha256"] == sha(plain)


def test_sto_adulteracoes_reprovam(keypair):
    key, cert = keypair
    b = sto_bundle()
    plain = sto_canon(b)
    env = encrypt(plain, cert)
    idx = sto_index(b, env, plain)
    with pytest.raises(U.SealError):        # envelope trocado
        U.open_slice("sto", decrypt_argv=local(key, cert), idx=idx, envelope=env + b"\n")
    bad = copy.deepcopy(idx)
    bad["plaintext_sha256"] = "0" * 64      # texto claro diferente do índice
    with pytest.raises(U.SealError):
        U.open_slice("sto", decrypt_argv=local(key, cert), idx=bad, envelope=env)
    b2 = copy.deepcopy(b)
    b2["fixtures"][0]["fixture"]["summary"] = "outro"
    p2 = sto_canon(b2)
    e2 = encrypt(p2, cert)
    i2 = dict(idx, ciphertext_sha256=sha(e2), plaintext_sha256=sha(p2))
    with pytest.raises(U.SealError):        # item com sha diferente do resumo publicado
        U.open_slice("sto", decrypt_argv=local(key, cert), idx=i2, envelope=e2)
    i3 = copy.deepcopy(idx)
    i3["counts"]["checks"] = 9
    with pytest.raises(U.SealError):        # contagem diferente
        U.open_slice("sto", decrypt_argv=local(key, cert), idx=i3, envelope=env)


def test_decifra_com_chave_errada_reprova(keypair, work):
    key, cert = keypair
    other = work / "outra.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(other), "2048"], check=True, capture_output=True)
    b = sto_bundle()
    plain = sto_canon(b)
    env = encrypt(plain, cert)
    with pytest.raises(U.SealError):
        U.open_slice("sto", decrypt_argv=["openssl", "cms", "-decrypt", "-inform", "PEM", "-inkey", str(other)],
                     idx=sto_index(b, env, plain), envelope=env)


def net_tar(bundle, salt):
    buf = io.BytesIO()
    files = {"bundle.json": json.dumps(bundle).encode(), "SALT.txt": (salt + "\n").encode(), "retained.py": b"# x\n"}
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for n in sorted(files):
            ti = tarfile.TarInfo(n)
            ti.size = len(files[n])
            tf.addfile(ti, io.BytesIO(files[n]))
    return buf.getvalue()


def test_net_sal_e_contagens(keypair):
    key, cert = keypair
    salt = "ab" * 16
    b = {"fixtures": [{"fixture_id": "N1", "split": "retained"}],
         "translations": [{"case_id": "T1", "split": "retained"}]}
    plain = net_tar(b, salt)
    env = encrypt(plain, cert)
    dig = sorted(sha(salt.encode() + net_canon(x)) for x in b["fixtures"] + b["translations"])
    idx = {"envelope_sha256": sha(env), "plaintext_sha256": sha(plain), "salted_digests": dig,
           "counts": {"fixtures_total": 1, "translations_total": 1}}
    out = U.open_slice("net", decrypt_argv=local(key, cert), idx=idx, envelope=env)
    assert out["bundle"] == b and out["source_names"] == ["retained.py"]
    with pytest.raises(U.SealError):
        U.open_slice("net", decrypt_argv=local(key, cert), idx=dict(idx, salted_digests=dig[:1] + ["0" * 64]),
                     envelope=env)
    b2 = {"fixtures": [{"fixture_id": "N1", "split": "calib"}], "translations": b["translations"]}
    p2 = net_tar(b2, salt)
    e2 = encrypt(p2, cert)
    with pytest.raises(U.SealError):        # item que não é retido dentro do envelope
        U.open_slice("net", decrypt_argv=local(key, cert),
                     idx=dict(idx, envelope_sha256=sha(e2), plaintext_sha256=sha(p2)), envelope=e2)


def test_comando_da_vm_e_o_dos_oraculos():
    from bo.pilot_exit import common as C
    from bo.pilot_sto_oracle import seal_verify
    assert seal_verify.REMOTE.startswith(C.REMOTE_DECRYPT)
    assert C.VM == seal_verify.VM and C.VM_DECRYPT_ARGV[-2] == C.VM
