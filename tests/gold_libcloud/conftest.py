"""Fixtures do GOLD-LIBCLOUD: BO_TMP do módulo (nunca /tmp) e a fonte fixada já baixada em $BO_DATA."""
import os
from pathlib import Path

os.environ.setdefault("BO_DATA", "/Users/breno/doutorado/brevops-data")
os.environ.setdefault("BO_TMP", str(Path(os.environ["BO_DATA"]) / "tmp" / "GOLD-LIBCLOUD"))
os.environ.setdefault("TMPDIR", os.environ["BO_TMP"])
Path(os.environ["BO_TMP"]).mkdir(parents=True, exist_ok=True)
