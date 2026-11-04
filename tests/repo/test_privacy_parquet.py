"""privacy_lint em .parquet: varre valores decodificados, não os bytes comprimidos."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from bo.repo import privacy  # noqa: E402

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover
    pa = None


@unittest.skipIf(pa is None, "pyarrow ausente")
class TestPrivacyParquet(unittest.TestCase):
    def _write(self, d, rows):
        f = Path(d) / "t.parquet"
        pq.write_table(pa.table({"v": rows, "n": list(range(len(rows)))}), f, compression="zstd")
        return f

    def test_valor_limpo_passa(self):
        with tempfile.TemporaryDirectory() as d:
            f = self._write(d, ["aws_s3_bucket", "google_storage_bucket"] * 1000)
            found, n, _ = privacy.scan_paths([f], strict=True, lists={})
            self.assertEqual(n, 1)
            self.assertEqual(found, [])

    def test_valor_sujo_reprova_com_linha(self):
        with tempfile.TemporaryDirectory() as d:
            f = self._write(d, ["ok", "fulano" + "@" + "exemplo.com.br", "ok"])
            found, _, _ = privacy.scan_paths([f], strict=True, lists={})
            self.assertTrue(found)
            self.assertEqual(found[0].line, 2)


if __name__ == "__main__":
    unittest.main()
