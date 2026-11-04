"""terraform fmt -check e validate offline das 4 fixtures (sandbox sem credenciais; nada de plan/apply).

  python -I -m bo.cqfix.tfcheck [DIR]     grava $BO_DATA/CQFIX/tf_validate.json; sai 0 se as 4 validam sem erro
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import MODULE_ID, PROVIDERS, data_root, fixtures_dir, now_iso
from . import tf


def main(argv=None) -> int:
    argv = [a for a in (sys.argv[1:] if argv is None else argv) if a != MODULE_ID]
    root = Path(argv[0]) if argv else fixtures_dir()
    rep = {"schema": "bo.cqfix.tf_validate/1", "module": MODULE_ID, "generated_at": now_iso(), "providers": {}}
    ok = True
    for p in PROVIDERS:
        f = root / p / "main.tf"
        text = f.read_text(encoding="utf-8")
        fmt_ok = tf.fmt_text(text) == text
        v = tf.validate(p, f)
        ent = {"fmt_ok": fmt_ok, "valid": bool(v.get("valid")), "errors": v.get("error_count"),
               "warnings": v.get("warning_count"),
               "diagnostics": [{"severity": d.get("severity"), "summary": d.get("summary")}
                               for d in v.get("diagnostics", [])][:20]}
        rep["providers"][p] = ent
        good = fmt_ok and ent["valid"] and not ent["errors"] and not ent["warnings"]
        ok &= good
        print(f"{p}: fmt {'OK' if fmt_ok else 'DIFERE'}, validate valid={ent['valid']} erros={ent['errors']} "
              f"avisos={ent['warnings']}")
    rep["ok"] = ok
    out = data_root() / MODULE_ID / "tf_validate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
