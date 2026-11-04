#!/bin/bash
# Teardown google do lote: terraform destroy no canal efêmero, identidade conferida, trava cleanup-global,
# remoção só do que tem a tag da execução ou linha do manifesto próprio, estados de remoção, resíduo esperado.
# Uso: teardown_google.sh --dry-run | --apply --run MODULO [--batch B] [--workdir EFEMERO]
# Implementação: src/bo/safety/teardown.py. Sem BO_CLOUD_GO=1 (GO do Breno) só o --dry-run e o --fixture rodam.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../../src"
[ -d "$here/src/bo/safety" ] && src="$here/src"   # pacote copiado para a VM do supervisor (bundle.sh)
py="${BO_PYTHON:-$(command -v python || command -v python3)}"
exec "$py" -I -B -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from bo.safety.teardown import main; sys.exit(main(sys.argv[1:]))' "$src" --provider google "$@"
