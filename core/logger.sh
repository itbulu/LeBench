#!/usr/bin/env bash
# core/logger.sh - per-module logging under logs/YYYYMMDD/

LZY_LOG_DATE=""
LZY_CURRENT_MODULE=""

lzy_logger_init() {
  LZY_LOG_DATE="$(lzy_today)"
  lzy_ensure_dir "${LZY_LOGS_DIR}/${LZY_LOG_DATE}"
}

lzy_log_file() {
  local module="${1:-main}"
  printf '%s/%s/%s.log' "${LZY_LOGS_DIR}" "${LZY_LOG_DATE}" "${module}"
}

lzy_log() {
  local level="$1"
  shift
  local module="${LZY_CURRENT_MODULE:-main}"
  local ts
  ts="$(date +"%Y-%m-%d %H:%M:%S")"
  local line="[${ts}] [${level}] $*"
  local file
  file="$(lzy_log_file "${module}")"
  mkdir -p "$(dirname "${file}")"
  printf '%s\n' "${line}" >>"${file}"
}

lzy_log_info() { lzy_log "INFO" "$@"; }
lzy_log_warn() { lzy_log "WARN" "$@"; }
lzy_log_error() { lzy_log "ERROR" "$@"; }

# Tee command stdout/stderr into module log while showing on console
# Usage: lzy_run_logged <module> -- <command...>
lzy_run_logged() {
  local module="$1"
  shift
  if [[ "${1:-}" == "--" ]]; then
    shift
  fi
  local file
  file="$(lzy_log_file "${module}")"
  mkdir -p "$(dirname "${file}")"
  {
    echo "===== START $(lzy_now_iso) ====="
    echo "CMD: $*"
  } >>"${file}"
  # shellcheck disable=SC2086
  "$@" 2>&1 | tee -a "${file}"
  local rc=${PIPESTATUS[0]}
  echo "===== END rc=${rc} $(lzy_now_iso) =====" >>"${file}"
  return "${rc}"
}
