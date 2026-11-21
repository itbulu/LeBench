#!/usr/bin/env bash
# LeBench one-click installer (auditable).
#
# Recommended (review then run):
#   curl -fsSL -o install.sh https://raw.githubusercontent.com/<ORG>/LeBench/main/install.sh
#   less install.sh
#   bash install.sh --yes
#
# From a git checkout:
#   bash install.sh --local --yes
#
# Not the only install path — see README / docs/install.md.
set -euo pipefail

ASSUME_YES=0
INSTALL_DEPS=1
DEPS_ONLY=0
NO_DEPS=0
FROM_LOCAL=0
UNINSTALL=0
SKIP_DOCTOR=0
LEBENCH_PREFIX="${LEBENCH_PREFIX:-${HOME}/.local/share/lebench}"
LEBENCH_BIN_DIR="${LEBENCH_BIN_DIR:-${HOME}/.local/bin}"
# 推送到 GitHub 后，请改成你的仓库地址，或安装时用 --repo / LEBENCH_REPO_URL 覆盖
LEBENCH_REPO_URL="${LEBENCH_REPO_URL:-https://github.com/YOUR_GITHUB_USER/LeBench.git}"
LEBENCH_REF="${LEBENCH_REF:-main}"

usage() {
  cat <<'EOF'
LeBench installer

Usage:
  bash install.sh [options]

Options:
  --yes, -y           Non-interactive; install system deps without prompt
  --no-deps           Do not install apt/dnf packages
  --deps-only         Only install system packages, then exit
  --local             Install from this source tree (do not clone)
  --prefix DIR        Install prefix (default: ~/.local/share/lebench)
  --bin-dir DIR       Wrapper directory (default: ~/.local/bin)
  --repo URL          Git clone URL
  --ref REF           Git branch/tag (default: main)
  --uninstall         Remove user venv + wrapper (keeps system packages)
  --skip-doctor       Do not run lebench doctor at the end
  -h, --help          Show help

Examples:
  bash install.sh --yes
  bash install.sh --local --yes
  bash install.sh --deps-only --yes
  LEBENCH_REPO_URL=https://github.com/YOU/LeBench.git bash install.sh --yes
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1 ;;
    --no-deps) NO_DEPS=1; INSTALL_DEPS=0 ;;
    --deps-only) DEPS_ONLY=1 ;;
    --local) FROM_LOCAL=1 ;;
    --prefix) LEBENCH_PREFIX="${2:?}"; shift ;;
    --bin-dir) LEBENCH_BIN_DIR="${2:?}"; shift ;;
    --repo) LEBENCH_REPO_URL="${2:?}"; shift ;;
    --ref) LEBENCH_REF="${2:?}"; shift ;;
    --uninstall) UNINSTALL=1 ;;
    --skip-doctor) SKIP_DOCTOR=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

export ASSUME_YES INSTALL_DEPS DEPS_ONLY NO_DEPS FROM_LOCAL UNINSTALL SKIP_DOCTOR
export LEBENCH_PREFIX LEBENCH_BIN_DIR LEBENCH_REPO_URL LEBENCH_REF

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${HERE}/scripts/bootstrap.sh" ]]; then
  exec bash "${HERE}/scripts/bootstrap.sh"
fi

# Standalone (curl'd install.sh only): ensure git, clone into prefix/src, run bootstrap --local
echo "[lebench-install] standalone mode — preparing clone under ${LEBENCH_PREFIX}/src"
if ! command -v git >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    if [[ "$(id -u)" -eq 0 ]]; then
      apt-get update -y && apt-get install -y git ca-certificates
    elif command -v sudo >/dev/null 2>&1; then
      sudo apt-get update -y && sudo apt-get install -y git ca-certificates
    fi
  fi
fi
command -v git >/dev/null 2>&1 || {
  echo "[lebench-install] ERROR: git is required" >&2
  exit 1
}

mkdir -p "${LEBENCH_PREFIX}"
SRC="${LEBENCH_PREFIX}/src"
if [[ -d "${SRC}/.git" ]]; then
  git -C "${SRC}" fetch --tags --force origin || true
  git -C "${SRC}" checkout "${LEBENCH_REF}" 2>/dev/null || true
  git -C "${SRC}" pull --ff-only 2>/dev/null || true
else
  rm -rf "${SRC}"
  if ! git clone --depth 1 --branch "${LEBENCH_REF}" "${LEBENCH_REPO_URL}" "${SRC}"; then
    git clone --depth 1 "${LEBENCH_REPO_URL}" "${SRC}"
  fi
fi

export FROM_LOCAL=1
exec bash "${SRC}/scripts/bootstrap.sh"
