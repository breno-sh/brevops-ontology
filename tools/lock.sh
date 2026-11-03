#!/bin/bash
# Travas do BrevOps (§7.4): mkdir atômico em $BO_DATA/locks/<nome>, com dono e hora.
#
#   lock.sh acquire NOME [--owner DONO] [--wait SEG]   pega a trava (espera até SEG; padrão 0)
#   lock.sh release NOME [--owner DONO] [--force]      solta (só o dono, salvo --force)
#   lock.sh status [NOME]                              mostra quem segura
#   lock.sh with NOME [--owner DONO] [--wait SEG] -- CMD ...   roda CMD com a trava e solta no fim
#   lock.sh selftest
#
# Nomes: merge-base, freeze, cleanup-global, cloud-<provedor>, probe-<provedor>, cpu-heavy-1/2 ...
# Trava órfã (processo morto) é só relatada; nunca é quebrada sozinha.
set -u
BO_DATA="${BO_DATA:-/Users/breno/doutorado/brevops-data}"
LOCKS="$BO_DATA/locks"
now() { TZ=America/Recife date '+%Y-%m-%dT%H:%M:%S%z' | sed -E 's/([0-9]{2})([0-9]{2})$/\1:\2/'; }
die() { echo "lock.sh: $*" >&2; exit 2; }

valid_name() { [[ "$1" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "nome de trava inválido: '$1' (use [a-z0-9-])"; }

default_owner() { echo "${BO_ID:-${USER:-anon}}@$$"; }

acquire() {
  local name="$1"; shift; valid_name "$name"
  local owner wait=0
  owner="$(default_owner)"
  while [ $# -gt 0 ]; do case "$1" in
    --owner) owner="$2"; shift 2;; --wait) wait="$2"; shift 2;; *) die "opção desconhecida: $1";; esac; done
  mkdir -p "$LOCKS"
  local d="$LOCKS/$name" start=$SECONDS
  while :; do
    if mkdir "$d" 2>/dev/null; then
      printf 'owner=%s\npid=%s\nhost=%s\nat=%s\n' "$owner" "$PPID" "$(hostname -s)" "$(now)" > "$d/owner"
      echo "trava $name: pega por $owner"
      return 0
    fi
    if [ $((SECONDS - start)) -ge "$wait" ]; then
      echo "trava $name: ocupada" >&2; show "$name" >&2; return 1
    fi
    sleep 2
  done
}

release() {
  local name="$1"; shift; valid_name "$name"
  local owner="" force=0
  while [ $# -gt 0 ]; do case "$1" in
    --owner) owner="$2"; shift 2;; --force) force=1; shift;; *) die "opção desconhecida: $1";; esac; done
  local d="$LOCKS/$name"
  [ -d "$d" ] || { echo "trava $name: já estava livre"; return 0; }
  local cur; cur="$(sed -n 's/^owner=//p' "$d/owner" 2>/dev/null)"
  if [ "$force" -ne 1 ] && [ -n "$owner" ] && [ "$cur" != "$owner" ]; then
    echo "trava $name: pertence a '$cur', não a '$owner' (use --force só se tiver certeza)" >&2; return 1
  fi
  rm -f "$d/owner" && rmdir "$d" || { echo "trava $name: não consegui remover $d" >&2; return 1; }
  echo "trava $name: solta"
}

show() {
  local name="$1" d="$LOCKS/$1"
  [ -d "$d" ] || { echo "  $name: livre"; return 0; }
  local pid host; pid="$(sed -n 's/^pid=//p' "$d/owner" 2>/dev/null)"; host="$(sed -n 's/^host=//p' "$d/owner" 2>/dev/null)"
  local orphan=""
  if [ -n "$pid" ] && [ "$host" = "$(hostname -s)" ] && ! kill -0 "$pid" 2>/dev/null; then orphan=" (ÓRFÃ? processo $pid não existe)"; fi
  echo "  $name: $(tr '\n' ' ' < "$d/owner" 2>/dev/null)$orphan"
}

status() {
  mkdir -p "$LOCKS"
  if [ $# -gt 0 ]; then valid_name "$1"; show "$1"; return 0; fi
  local any=0
  for d in "$LOCKS"/*/; do [ -d "$d" ] || continue; any=1; show "$(basename "$d")"; done
  [ $any -eq 1 ] || echo "  nenhuma trava ocupada em $LOCKS"
}

with_lock() {
  local name="$1"; shift; local args=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do args+=("$1"); shift; done
  [ "${1:-}" = "--" ] || die "uso: lock.sh with NOME [--owner D] [--wait S] -- CMD ..."
  shift
  local owner; owner="$(default_owner)"
  local i; for ((i=0; i<${#args[@]}; i++)); do [ "${args[$i]}" = "--owner" ] && owner="${args[$((i+1))]}"; done
  acquire "$name" --owner "$owner" "${args[@]}" || return 1
  trap 'release "$name" --owner "$owner" >/dev/null' EXIT INT TERM
  "$@"; local rc=$?
  release "$name" --owner "$owner" >/dev/null; trap - EXIT INT TERM
  return $rc
}

selftest() {
  local tmp ok=0 bad=0
  tmp="$BO_DATA/tmp/REPO/lock-selftest-$$"; mkdir -p "$tmp"
  local self="$0"
  t() { if "$@" >/dev/null 2>&1; then ok=$((ok+1)); echo "  [ok] $label"; else bad=$((bad+1)); echo "  [FALHOU] $label"; fi; }
  n() { if "$@" >/dev/null 2>&1; then bad=$((bad+1)); echo "  [FALHOU] $label"; else ok=$((ok+1)); echo "  [ok] $label"; fi; }
  export BO_DATA="$tmp"
  label="pega trava livre";               t "$self" acquire teste --owner A
  label="segunda tentativa reprova";      n "$self" acquire teste --owner B
  label="dono e hora gravados";           t grep -q '^owner=A' "$tmp/locks/teste/owner"
  label="outro dono não solta";           n "$self" release teste --owner B
  label="dono solta";                     t "$self" release teste --owner A
  label="trava livre de novo";            t test ! -d "$tmp/locks/teste"
  label="with roda o comando e solta";    t "$self" with teste --owner C -- true
  label="with propaga a falha";           n "$self" with teste --owner C -- false
  label="with solta mesmo com falha";     t test ! -d "$tmp/locks/teste"
  label="nome inválido reprova";          n "$self" acquire "../fora"
  "$self" acquire teste --owner D >/dev/null 2>&1
  ( sleep 3; "$self" release teste --owner D >/dev/null 2>&1 ) &
  label="--wait espera a trava ser solta"; t "$self" acquire teste --owner E --wait 20
  wait
  "$self" release teste --owner E >/dev/null 2>&1
  rm -rf "$tmp"
  echo "lock.sh selftest: $ok/$((ok+bad)) expectativas cumpridas"
  [ $bad -eq 0 ]
}

cmd="${1:-status}"; [ $# -gt 0 ] && shift
case "$cmd" in
  acquire) [ $# -ge 1 ] || die "uso: lock.sh acquire NOME"; acquire "$@";;
  release) [ $# -ge 1 ] || die "uso: lock.sh release NOME"; release "$@";;
  status) status "$@";;
  with) [ $# -ge 1 ] || die "uso: lock.sh with NOME -- CMD"; with_lock "$@";;
  selftest|--selftest) selftest;;
  -h|--help|help) sed -n '2,12p' "$0";;
  *) die "comando desconhecido: $cmd";;
esac
