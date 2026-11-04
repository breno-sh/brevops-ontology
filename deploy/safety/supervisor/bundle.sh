#!/bin/bash
# Monta o pacote do supervisor para a VM (não copia nada para a VM; quem instala é o Breno, D16):
#   pkg/bo_supervisor.py, pkg/src/bo/safety/*.py, pkg/deploy/safety/{allowlist_skus.json,EXPECTED_RESIDUE.json}
# A tabela vai em JSON (a VM não precisa de PyYAML). Imprime o sha256 do tar para conferir depois de copiar.
# Uso: bundle.sh DESTINO_DIR      (ex.: $BO_DATA/tmp/SAFETY/bundle)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
out="${1:?uso: bundle.sh DESTINO_DIR}"
py="${BO_PYTHON:-$(command -v python || command -v python3)}"
pkg="$out/pkg"
rm -rf "$pkg"; mkdir -p "$pkg/src/bo/safety" "$pkg/deploy/safety"
cp "$here/bo_supervisor.py" "$pkg/"
cp "$repo"/src/bo/safety/*.py "$pkg/src/bo/safety/"
cp "$repo/deploy/safety/EXPECTED_RESIDUE.json" "$pkg/deploy/safety/"
"$py" -I -c 'import json,sys,yaml; json.dump(yaml.safe_load(open(sys.argv[1])), open(sys.argv[2],"w"), sort_keys=True)' \
  "$repo/deploy/safety/allowlist_skus.yaml" "$pkg/deploy/safety/allowlist_skus.json"
for s in sweep teardown; do for p in aws google azurerm oci; do cp "$repo/deploy/safety/${s}_$p.sh" "$pkg/"; done; done
tar -C "$out" -czf "$out/bo-supervisor.tgz" pkg
shasum -a 256 "$out/bo-supervisor.tgz"
