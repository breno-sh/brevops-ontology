#!/bin/bash
# Varredura dos QUATRO provedores (aws, google, azurerm, oci), em todas as regiões lidas de cada conta.
# Lição embutida (~90 dólares queimados): nunca dizer "zero recursos" a partir de um provedor só, de regiões fixas
# ou de um tipo só. Este script roda os quatro sempre, não para no primeiro que falha, e só sai 0 se os quatro
# responderam (e, com --expect-empty, se nenhum tem resíduo inesperado nem item a investigar).
# Uso: sweep_all.sh --dry-run
#      sweep_all.sh --run MODULO [--expect-empty] [--record-baseline]     (exige BO_CLOUD_GO=1, GO do Breno)
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
providers=(aws google azurerm oci)
TZ=America/Recife date '+[%Y-%m-%dT%H:%M:%S%z] sweep_all: 4 provedores' | sed -E 's/([0-9]{2})([0-9]{2})\]/\1:\2]/'
ok=0; fail=()
for p in "${providers[@]}"; do
  if bash "$here/sweep_$p.sh" "$@"; then ok=$((ok + 1)); else fail+=("$p"); fi
done
echo "sweep_all: $ok/${#providers[@]} provedores OK (${providers[*]})${fail[*]:+; REPROVADOS: ${fail[*]}}"
[ "$ok" -eq "${#providers[@]}" ]
