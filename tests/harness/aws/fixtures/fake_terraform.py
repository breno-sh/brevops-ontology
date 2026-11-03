"""'terraform' falso dos testes do HARNESS-AWS: responde com uma gravação (BO_FAKE_TF_REC) e registra só NOMES
de variáveis de ambiente em BO_FAKE_TF_LOG. Nunca abre rede. Chamado pelo TerraformCLIBackend sob env -i."""
import json
import os
import sys
from pathlib import Path

rec = json.loads(Path(os.environ["BO_FAKE_TF_REC"]).read_text())
args = sys.argv[1:]
with open(os.environ["BO_FAKE_TF_LOG"], "a") as log:
    log.write(json.dumps({"args": args, "env": sorted(os.environ), "cwd_files": sorted(os.listdir("."))}) + "\n")
counter = Path(".fake_reads")


def diag_lines(step):
    for d in step.get("diagnostics", []):
        print(json.dumps({"type": "diagnostic", "diagnostic": d}))
    return 0 if step.get("ok", True) else 1


cmd = args[0]
if cmd == "init":
    sys.exit(0)
if cmd == "apply" and "-refresh-only" in args:
    sys.exit(0)
if cmd == "apply":
    sys.exit(diag_lines(rec.get("apply", {"ok": True})))
if cmd == "show":
    n = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(n + 1))
    reads = rec["reads"]
    print(json.dumps(reads[min(n, len(reads) - 1)]))
    sys.exit(0)
if cmd == "destroy":
    Path(".destroyed").write_text("1")
    sys.exit(diag_lines(rec.get("destroy", {"ok": True})))
if cmd == "state":
    key = "state_list_after_destroy" if Path(".destroyed").exists() else "state_list"
    print("\n".join(rec.get(key, [])))
    sys.exit(0)
sys.exit(2)
