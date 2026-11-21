#!/usr/bin/env bash
# Install system packages required by LeBench modules.
# Usage: install_deps.sh [--yes]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=detect_os.sh
source "${SCRIPT_DIR}/detect_os.sh"

ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help)
      echo "Usage: $0 [--yes]"
      exit 0
      ;;
  esac
done

lebench_detect_os

log() { printf '[lebench-deps] %s\n' "$*"; }
die() { printf '[lebench-deps] ERROR: %s\n' "$*" >&2; exit 1; }

if [[ "${LEBENCH_IS_LINUX}" -ne 1 ]]; then
  die "system dependency installer targets Linux only (detected non-Linux)"
fi

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    die "need root or sudo to install system packages"
  fi
}

confirm_install() {
  local pkgs="$1"
  log "Will install system packages: ${pkgs}"
  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    die "non-interactive shell: re-run with --yes to install packages"
  fi
  read -r -p "Continue? [y/N] " ans
  case "${ans}" in
    y|Y|yes|YES) return 0 ;;
    *) die "aborted by user" ;;
  esac
}

install_apt() {
  local pkgs=(
    python3 python3-venv python3-pip
    sysbench fio iputils-ping traceroute
    mtr-tiny smartmontools dmidecode numactl
    ca-certificates curl
  )
  # Optional / may be missing on minimal images
  local optional=(git)
  confirm_install "${pkgs[*]} ${optional[*]}"
  run_root apt-get update -y
  run_root apt-get install -y "${pkgs[@]}"
  run_root apt-get install -y "${optional[@]}" || log "optional packages skipped"
}

install_dnf() {
  local pkgs=(
    python3 python3-pip
    sysbench fio iputils traceroute
    mtr smartmontools dmidecode numactl
    ca-certificates curl
  )
  local optional=(git)
  confirm_install "${pkgs[*]} ${optional[*]}"
  if [[ "${LEBENCH_PKG_MGR}" == "dnf" ]]; then
    run_root dnf install -y "${pkgs[@]}" || true
    # Ensure python3-pip / venv equivalents
    run_root dnf install -y python3 python3-pip "${optional[@]}" || log "retry/optional skipped"
    # Some packages may need EPEL
    if ! command -v sysbench >/dev/null 2>&1; then
      log "sysbench missing — trying EPEL"
      run_root dnf install -y epel-release || true
      run_root dnf install -y sysbench fio mtr smartmontools dmidecode numactl traceroute || log "some tools still missing; doctor will report"
    fi
  else
    run_root yum install -y "${pkgs[@]}" "${optional[@]}" || log "some yum packages missing"
  fi
}

case "${LEBENCH_PKG_MGR}" in
  apt) install_apt ;;
  dnf|yum) install_dnf ;;
  *)
    die "unsupported package manager (${LEBENCH_PKG_MGR}). Install manually: python3, sysbench, fio, ping, traceroute"
    ;;
esac

log "Done. Run: lebench doctor"
