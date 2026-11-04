"""bo.corpus_oci.swap: sem a trava do módulo, nada troca."""
from bo.corpus_oci import build, swap


def test_swap_requires_lock(data_root):
    stg = data_root / "CORPUS-OCI" / ".staging"
    build.run("oci", stg)
    assert swap.main([]) == 3
    assert not (data_root / "CORPUS-OCI" / "usage.jsonl").exists()


def test_swap_with_lock(data_root):
    stg = data_root / "CORPUS-OCI" / ".staging"
    build.run("oci", stg)
    lk = data_root / "locks" / "merge-base"
    lk.mkdir(parents=True)
    (lk / "owner").write_text("owner=CORPUS-OCI@1\npid=1\n")
    assert swap.main([]) == 0
    assert (data_root / "CORPUS-OCI" / "usage.jsonl").is_file() and not stg.exists()


def test_swap_refuses_bad_staging(data_root):
    stg = data_root / "CORPUS-OCI" / ".staging"
    build.run("oci", stg)
    (stg / "usage.jsonl").write_text((stg / "usage.jsonl").read_text().splitlines()[0] + "\n")
    lk = data_root / "locks" / "merge-base"
    lk.mkdir(parents=True)
    (lk / "owner").write_text("owner=CORPUS-OCI@1\n")
    assert swap.main([]) == 1
    assert not (data_root / "CORPUS-OCI" / "usage.jsonl").exists()
