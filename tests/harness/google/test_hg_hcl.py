"""Emissor de HCL: escapes, alinhamento e forma canônica conferida com o terraform fmt fixado."""
import random
import shutil
import subprocess

from bo.harness.google import hcl as H

TF = shutil.which("terraform")


def fmt_ok(d, text):
    (d / "x.tf").write_text(text, encoding="utf-8")
    p = subprocess.run([TF, f"-chdir={d}", "fmt", "-check", "-diff", "-no-color"], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(d), "CHECKPOINT_DISABLE": "1"})
    return p.returncode == 0, p.stdout + p.stderr


def test_terraform_fixado_no_path():
    assert TF, "terraform não está no PATH (pin em universe/pins.json)"
    out = subprocess.run([TF, "version", "-json"], capture_output=True, text=True).stdout
    from bo.harness.google import common as C
    assert C.pins()["terraform"]["version"] in out


def test_escapes_nao_interpolam():
    assert H.quote('a${b}%{c}"\\\n') == '"a$${b}%%{c}\\"\\\\\\n"'
    assert H.quote("$x %y") == '"$x %y"'


def test_numeros_e_chaves():
    assert H.number(7) == "7" and H.number(7.0) == "7" and H.number(1.5) == "1.5"
    assert H.key("a_b") == "a_b" and H.key("a-b") == "a-b" and H.key("1a") == '"1a"' and H.key("for") == '"for"'


def test_alinhamento_quebra_em_multilinha(work):
    b = H.Body({"a": 1, "tags": {"x": 1, "yy": "b"}, "bb": 2, "ccc": [1, 2]}, [])
    text = H.document([("resource", ["x", "y"], b)])
    assert "  a = 1\n  tags = {\n    x  = 1\n    yy = \"b\"\n  }\n  bb  = 2\n  ccc = [1, 2]\n" in text
    ok, diff = fmt_ok(work, text)
    assert ok, diff


def _rand_value(rng, depth=0):
    k = rng.randrange(8 if depth < 2 else 5)
    if k == 0:
        return rng.choice(["", "a", 'q"uote', "dollar ${x}", "pct %{y}", "back\\slash", "nl\nx", "ção"])
    if k == 1:
        return rng.choice([0, 7, -3, 1.5, 1e-3, 123456789])
    if k == 2:
        return rng.choice([True, False])
    if k == 3:
        return None
    if k == 4:
        return [rng.choice(["a", "b"]) for _ in range(rng.randrange(3))]
    if k == 5:
        return {f"k{i}": _rand_value(rng, depth + 1) for i in range(rng.randrange(3))}
    if k == 6:
        return [{f"z{i}": _rand_value(rng, depth + 1) for i in range(1, rng.randrange(2, 4))}
                for _ in range(rng.randrange(1, 3))]
    return H.Template(("pre-", H.Expr("var.v"), "-pos"))


def _rand_body(rng, depth=0):
    b = H.Body.new()
    for i in range(rng.randrange(1, 6)):
        b.attrs[rng.choice(["a", "bb", "cccc", "d_long_name", "e"]) + str(i)] = _rand_value(rng)
    if depth < 2:
        for i in range(rng.randrange(3)):
            b.blocks.append((f"blk{i % 2}", _rand_body(rng, depth + 1)))
    return b


def test_forma_canonica_em_200_corpos_aleatorios(work):
    rng = random.Random(20261103)
    blocks = [("resource", ["google_x", f"r{i}"], _rand_body(rng)) for i in range(200)]
    ok, diff = fmt_ok(work, H.document(blocks, ["cabeçalho"]))
    assert ok, diff[:2000]
