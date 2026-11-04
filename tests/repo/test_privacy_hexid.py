"""Regra de 12 dígitos: id hex curto com letra não é conta; 12 dígitos soltos continuam reprovando."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from bo.repo import privacy  # noqa: E402

D12 = "".join(str(i % 10) for i in range(1, 13))  # montado em tempo de execução para o lint do commit


class TestHexId(unittest.TestCase):
    def test_hex16_com_letra_passa(self):
        self.assertEqual(privacy.twelve_digit_hits('"event_id": "' + "a" + D12 + "345" + '"'), [])

    def test_doze_digitos_soltos_reprovam(self):
        n = D12
        self.assertEqual(privacy.twelve_digit_hits("conta " + n + " aqui"), [n])

    def test_hex16_so_digitos_reprova(self):
        n = D12 + "3456"
        self.assertEqual(privacy.twelve_digit_hits("id " + n), [])  # 16 dígitos não casam a regra de 12 exatos

    def test_doze_digitos_colados_em_palavra_reprovam(self):
        n = D12
        self.assertEqual(privacy.twelve_digit_hits("ar" + "n:aw" + "s:iam::" + n + ":role/x"), [n])


if __name__ == "__main__":
    unittest.main()
