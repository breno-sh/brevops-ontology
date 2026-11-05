"""Abertura das fixtures RETIDAS (D15): o envelope vai para a VM Oracle pelo ssh, a VM decifra com a chave privada
(que nunca sai de lá) e o texto claro volta só pelo pipe, para a memória deste processo. Nada em claro é gravado
aqui: quem precisa de arquivo (o código congelado) recebe uma árvore temporária em $BO_TMP, apagada no fim.

Antes de usar, confere: sha do envelope = índice selado; sha do texto claro = índice; cada item do texto claro
bate com o resumo publicado no índice (STO: sha por item; NET: sha com sal); contagens iguais.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile

from . import common as C


class SealError(RuntimeError):
    pass


def decrypt(envelope: bytes, argv=C.VM_DECRYPT_ARGV, timeout: int = 300) -> bytes:
    try:
        r = subprocess.run(list(argv), input=envelope, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SealError(f"decifração falhou ({type(e).__name__})")
    if r.returncode != 0 or not r.stdout:
        raise SealError(f"decifração falhou (saída {r.returncode}): {r.stderr.decode(errors='replace')[-200:]}")
    return r.stdout


# ---------------------------------------------------------------------------------------------------- STO
def _sto_canon(obj) -> bytes:
    """canon do PILOT-STO-ORACLE (bo.pilot_sto_oracle.build.canon): indent=1, chaves ordenadas, \\n final."""
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _sto_check(idx: dict, plain: bytes) -> dict:
    try:
        b = json.loads(plain)
    except ValueError:
        raise SealError("texto claro STO não é JSON")
    if not isinstance(b, dict) or not isinstance(b.get("fixtures"), list) or not isinstance(b.get("entries"), list):
        raise SealError("texto claro STO sem fixtures/entries")
    want = {i["item_id"]: i for i in idx.get("items", [])}
    seen = {}
    for f in b["fixtures"]:
        fx = f["fixture"]
        seen[fx["fixture_id"]] = ("fixture", C.sha_bytes(_sto_canon(fx)))
    for e in b["entries"]:
        seen[e["entry_id"]] = ("direction_entry", C.sha_bytes(_sto_canon({"source": e["source"], "target": e["target"]})))
    if set(seen) != set(want):
        raise SealError(f"itens do texto claro ≠ índice ({len(set(seen) ^ set(want))} diferença(s))")
    bad = [k for k, (kind, h) in seen.items() if want[k]["kind"] != kind or want[k]["sha256"] != h]
    if bad:
        raise SealError(f"{len(bad)} item(ns) com sha diferente do índice")
    cnt = idx.get("counts", {})
    got = {"fixtures": len(b["fixtures"]), "direction_entries": len(b["entries"]),
           "checks": sum(len(f["checks"]) for f in b["fixtures"])}
    if any(cnt.get(k) != v for k, v in got.items()):
        raise SealError(f"contagens ≠ índice: {got} x {cnt}")
    return {"bundle": b, "n_items": len(seen), "counts": got}


# ---------------------------------------------------------------------------------------------------- NET
def _net_canon(obj) -> bytes:
    """canon do PILOT-NET-ORACLE (bo.pilot_net_oracle.seal.canon): compacto, chaves ordenadas."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _net_check(idx: dict, plain: bytes) -> dict:
    try:
        tf = tarfile.open(fileobj=io.BytesIO(plain), mode="r:")
        files = {m.name: tf.extractfile(m).read() for m in tf.getmembers() if m.isfile()}
    except (tarfile.TarError, AttributeError):
        raise SealError("texto claro NET não é tar")
    if "bundle.json" not in files or "SALT.txt" not in files:
        raise SealError("tar NET sem bundle.json ou SALT.txt")
    b = json.loads(files["bundle.json"])
    salt = files["SALT.txt"].decode().strip()
    items = list(b.get("fixtures", [])) + list(b.get("translations", []))
    if any(x.get("split") != "retained" for x in items):
        raise SealError("item não retido dentro do envelope")
    dig = sorted(hashlib.sha256(salt.encode() + _net_canon(x)).hexdigest() for x in items)
    if dig != sorted(idx.get("salted_digests", [])):
        raise SealError("resumos com sal ≠ índice")
    cnt = idx.get("counts", {})
    got = {"fixtures_total": len(b.get("fixtures", [])), "translations_total": len(b.get("translations", []))}
    if any(cnt.get(k) != v for k, v in got.items()):
        raise SealError(f"contagens ≠ índice: {got}")
    return {"bundle": b, "n_items": len(items), "counts": got,
            "source_names": sorted(k for k in files if k not in ("bundle.json", "SALT.txt"))}


# ---------------------------------------------------------------------------------------------------- comum
def index_of(slice_: str, root=None) -> dict:
    s = C.SLICES[slice_]
    p = C.expand(s["index"], root)
    idx = C.read_json(p)
    if not isinstance(idx, dict):
        raise SealError(f"índice selado ausente ou ilegível: {C.portable(p)}")
    if slice_ == "net":
        pub = C.read_json((root or C.repo()) / "pilot/net/oracle/sealed_index.json")
        if pub is not None and pub != idx:
            raise SealError("índice selado em $BO_DATA ≠ cópia pública em pilot/net/oracle/sealed_index.json")
    return idx


def envelope_sha(slice_: str, idx: dict) -> str:
    return idx["ciphertext_sha256"] if slice_ == "sto" else idx["envelope_sha256"]


def envelope_path(slice_: str, idx: dict, root=None):
    """O envelope ativo é o que o índice selado aponta (re-selagens trocam o arquivo); sem campo, o padrão."""
    p = idx.get("envelope") if slice_ == "net" else idx.get("sealed_file")
    return C.expand(p or C.SLICES[slice_]["envelope"], root)


def check_envelope(slice_: str, root=None) -> dict:
    """Sem decifrar: envelope existe e o sha bate com o índice."""
    idx = index_of(slice_, root)
    env = envelope_path(slice_, idx, root)
    if not env.is_file():
        raise SealError(f"envelope ausente: {C.portable(env)}")
    h = C.sha_file(env)
    if h != envelope_sha(slice_, idx):
        raise SealError(f"envelope {slice_} ≠ índice selado")
    return {"envelope": C.portable(env), "ciphertext_sha256": h, "plaintext_sha256": idx["plaintext_sha256"]}


def open_slice(slice_: str, decrypt_argv=C.VM_DECRYPT_ARGV, root=None, idx: dict | None = None,
               envelope: bytes | None = None) -> dict:
    """Decifra (pela VM) e confere. Devolve o pacote em memória e os hashes; nunca grava o texto claro."""
    idx = idx if idx is not None else index_of(slice_, root)
    if envelope is None:
        env_p = envelope_path(slice_, idx, root)
        envelope = env_p.read_bytes()
    if C.sha_bytes(envelope) != envelope_sha(slice_, idx):
        raise SealError(f"envelope {slice_} ≠ índice selado")
    plain = decrypt(envelope, decrypt_argv)
    if C.sha_bytes(plain) != idx["plaintext_sha256"]:
        raise SealError(f"texto claro {slice_} ≠ sha do índice")
    out = _sto_check(idx, plain) if slice_ == "sto" else _net_check(idx, plain)
    out.update({"slice": slice_, "ciphertext_sha256": C.sha_bytes(envelope), "plaintext_sha256": C.sha_bytes(plain),
                "plaintext_bytes": len(plain)})
    del plain
    return out
