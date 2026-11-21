#!/usr/bin/env bash
# Detect OS family, package manager, architecture.
# Sourced by other install scripts. Safe to source multiple times.

if [[ -n "${LEBENCH_DETECT_OS_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
LEBENCH_DETECT_OS_LOADED=1

lebench_detect_os() {
  LEBENCH_OS_ID="unknown"
  LEBENCH_OS_VERSION=""
  LEBENCH_OS_LIKE=""
  LEBENCH_PKG_MGR="unknown"
  LEBENCH_ARCH="$(uname -m 2>/dev/null || echo unknown)"
  LEBENCH_IS_LINUX=0

  if [[ "$(uname -s 2>/dev/null)" == "Linux" ]]; then
    LEBENCH_IS_LINUX=1
  fi

  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    LEBENCH_OS_ID="${ID:-unknown}"
    LEBENCH_OS_VERSION="${VERSION_ID:-}"
    LEBENCH_OS_LIKE="${ID_LIKE:-}"
  fi

  case "${LEBENCH_OS_ID}" in
    ubuntu|debian)
      LEBENCH_PKG_MGR="apt"
      ;;
    rocky|almalinux|centos|rhel|fedora)
      if command -v dnf >/dev/null 2>&1; then
        LEBENCH_PKG_MGR="dnf"
      else
        LEBENCH_PKG_MGR="yum"
      fi
      ;;
    *)
      case " ${LEBENCH_OS_LIKE} " in
        *"debian"*|*"ubuntu"*)
          LEBENCH_PKG_MGR="apt"
          ;;
        *"rhel"*|*"fedora"*|*"centos"*)
          if command -v dnf >/dev/null 2>&1; then
            LEBENCH_PKG_MGR="dnf"
          else
            LEBENCH_PKG_MGR="yum"
          fi
          ;;
      esac
      ;;
  esac

  export LEBENCH_OS_ID LEBENCH_OS_VERSION LEBENCH_OS_LIKE LEBENCH_PKG_MGR LEBENCH_ARCH LEBENCH_IS_LINUX
}

lebench_arch_ok() {
  case "${LEBENCH_ARCH}" in
    x86_64|amd64|aarch64|arm64) return 0 ;;
    *) return 1 ;;
  esac
}
