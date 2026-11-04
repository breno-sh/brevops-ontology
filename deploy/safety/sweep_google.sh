#!/bin/bash
# Varredura google (só relato): todas as regiões lidas da conta, todos os tipos; nada é apagado.
# Uso: sweep_google.sh --dry-run | --run MODULO [--record-baseline] [--expect-empty] [--batch B] [--fixture ARQ]
# Implementação: src/bo/safety/sweep.py. Sem BO_CLOUD_GO=1 (GO do Breno) só o --dry-run e o --fixture rodam.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../../src"
[ -d "$here/src/bo/safety" ] && src="$here/src"   # pacote copiado para a VM do supervisor (bundle.sh)
py="${BO_PYTHON:-$(command -v python || command -v python3)}"
exec "$py" -I -B -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from bo.safety.sweep import main; sys.exit(main(sys.argv[1:]))' "$src" --provider google "$@"
