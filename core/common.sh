#!/usr/bin/env bash
# core/common.sh - shared helpers for LZY Bench
# shellcheck disable=SC2034

set -o pipefail

# ---------------------------------------------------------------------------
# Resolve project root (directory containing benchmark.sh)
# ---------------------------------------------------------------------------
lzy_init_root() {
  local src="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
  # Prefer caller (benchmark.sh) when sourced
  if [[ -n "${LZY_ROOT:-}" && -d "${LZY_ROOT}" ]]; then
    return 0
  fi
  local dir
  dir="$(cd "$(dirname "${src}")" && pwd)"
  # If sourced from core/, go up one level
  if [[ "$(basename "${dir}")" == "core" ]]; then
    dir="$(cd "${dir}/.." && pwd)"
  fi
  LZY_ROOT="${dir}"
  export LZY_ROOT
}

lzy_init_root

# ---------------------------------------------------------------------------
# Colors (disabled when not a TTY)
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
  LZY_C_RESET=$'\033[0m'
  LZY_C_RED=$'\033[0;31m'
  LZY_C_GREEN=$'\033[0;32m'
  LZY_C_YELLOW=$'\033[0;33m'
  LZY_C_BLUE=$'\033[0;34m'
  LZY_C_CYAN=$'\033[0;36m'
  LZY_C_BOLD=$'\033[1m'
else
  LZY_C_RESET="" LZY_C_RED="" LZY_C_GREEN="" LZY_C_YELLOW=""
  LZY_C_BLUE="" LZY_C_CYAN="" LZY_C_BOLD=""
fi

lzy_die() {
  echo "${LZY_C_RED}[ERROR]${LZY_C_RESET} $*" >&2
  exit 1
}

lzy_info() {
  echo "${LZY_C_CYAN}[INFO]${LZY_C_RESET} $*"
}

lzy_ok() {
  echo "${LZY_C_GREEN}[OK]${LZY_C_RESET} $*"
}

lzy_warn() {
  echo "${LZY_C_YELLOW}[WARN]${LZY_C_RESET} $*" >&2
}

lzy_require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || return 1
}

lzy_check_root() {
  if [[ "${LZY_REQUIRE_ROOT:-1}" == "1" ]] && [[ "$(id -u)" -ne 0 ]]; then
    lzy_die "需要 root 权限运行。请使用: sudo ./benchmark.sh $*"
  fi
}

# ISO-8601 UTC timestamp
lzy_now_iso() {
  date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# Local date YYYYMMDD
lzy_today() {
  date +"%Y%m%d"
}

# Run id: YYYYMMDD-HHMMSS
lzy_new_run_id() {
  date +"%Y%m%d-%H%M%S"
}

# Escape string for JSON (basic)
lzy_json_escape() {
  local s="${1:-}"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "${s}"
}

# Write JSON file via jq if available, else raw stdin
# Usage: lzy_write_json <path> < jq-filter-or-raw >
lzy_write_json() {
  local path="$1"
  mkdir -p "$(dirname "${path}")"
  cat >"${path}"
}

# Ensure directory exists
lzy_ensure_dir() {
  mkdir -p "$1"
}

# Safe integer or string for JSON number fields
lzy_json_num_or_null() {
  local v="${1:-}"
  if [[ "${v}" =~ ^-?[0-9]+([.][0-9]+)?$ ]]; then
    printf '%s' "${v}"
  else
    printf 'null'
  fi
}

# Command output trimmed, empty -> empty string
lzy_cmd_out() {
  "$@" 2>/dev/null | head -n 200 | tr -d '\r' || true
}

# First line helper
lzy_first_line() {
  head -n 1 2>/dev/null || true
}
