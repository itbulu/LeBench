#!/usr/bin/env bash
# Core bootstrap: fetch/use source, venv, pip install, wrapper, doctor.
# Invoked by ../install.sh — prefer running install.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=detect_os.sh
source "${SCRIPT_DIR}/detect_os.sh"

# Defaults (overridable by env / flags via install.sh)
LEBENCH_PREFIX="${LEBENCH_PREFIX:-${HOME}/.local/share/lebench}"
LEBENCH_BIN_DIR="${LEBENCH_BIN_DIR:-${HOME}/.local/bin}"
LEBENCH_REPO_URL="${LEBENCH_REPO_URL:-https://github.com/itbulu/LeBench.git}"
LEBENCH_REF="${LEBENCH_REF:-main}"
ASSUME_YES="${ASSUME_YES:-0}"
INSTALL_DEPS="${INSTALL_DEPS:-1}"
DEPS_ONLY="${DEPS_ONLY:-0}"
NO_DEPS="${NO_DEPS:-0}"
FROM_LOCAL="${FROM_LOCAL:-0}"
UNINSTALL="${UNINSTALL:-0}"
SKIP_DOCTOR="${SKIP_DOCTOR:-0}"

log() { printf '[lebench-install] %s\n' "$*"; }
warn() { printf '[lebench-install] WARN: %s\n' "$*" >&2; }
die() { printf '[lebench-install] ERROR: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

confirm() {
  local prompt="$1"
  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    return 0
  fi
  if [[ ! -t 0 ]]; then
    die "non-interactive: pass --yes"
  fi
  read -r -p "${prompt} [y/N] " ans
  case "${ans}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

do_uninstall() {
  log "Uninstalling LeBench user install under ${LEBENCH_PREFIX}"
  rm -f "${LEBENCH_BIN_DIR}/lebench"
  rm -rf "${LEBENCH_PREFIX}"
  log "Removed venv/wrapper. System packages (sysbench/fio/...) were NOT removed."
  exit 0
}

ensure_python() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    die "python3 not found — install system deps first (omit --no-deps) or install python3 manually"
  fi
  local ver
  ver="$("${PYTHON_BIN}" -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
  # Require 3.9+
  "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)' \
    || die "Python >= 3.9 required (found ${ver})"
  export PYTHON_BIN
  log "Using ${PYTHON_BIN} (${ver})"
}

fetch_source() {
  if [[ "${FROM_LOCAL}" -eq 1 ]]; then
    SRC_DIR="${REPO_ROOT}"
    [[ -f "${SRC_DIR}/pyproject.toml" ]] || die "local repo missing pyproject.toml"
    log "Using local source: ${SRC_DIR}"
    return 0
  fi

  SRC_DIR="${LEBENCH_PREFIX}/src"
  mkdir -p "${LEBENCH_PREFIX}"
  if [[ -d "${SRC_DIR}/.git" ]]; then
    log "Updating existing clone ${SRC_DIR} @ ${LEBENCH_REF}"
    need_cmd git
    git -C "${SRC_DIR}" fetch --tags --force origin
    git -C "${SRC_DIR}" checkout "${LEBENCH_REF}"
    git -C "${SRC_DIR}" pull --ff-only origin "${LEBENCH_REF}" 2>/dev/null \
      || git -C "${SRC_DIR}" reset --hard "origin/${LEBENCH_REF}" 2>/dev/null \
      || true
  elif [[ -f "${REPO_ROOT}/pyproject.toml" && "${REPO_ROOT}" == *"/LeBench"* ]]; then
    # Running from a checkout: copy/use it unless LEBENCH_FORCE_CLONE=1
    if [[ "${LEBENCH_FORCE_CLONE:-0}" -eq 1 ]]; then
      need_cmd git
      rm -rf "${SRC_DIR}"
      git clone --depth 1 --branch "${LEBENCH_REF}" "${LEBENCH_REPO_URL}" "${SRC_DIR}" \
        || git clone --depth 1 "${LEBENCH_REPO_URL}" "${SRC_DIR}"
    else
      SRC_DIR="${REPO_ROOT}"
      log "Using current checkout: ${SRC_DIR}"
    fi
  else
    need_cmd git
    log "Cloning ${LEBENCH_REPO_URL} (${LEBENCH_REF}) → ${SRC_DIR}"
    rm -rf "${SRC_DIR}"
    if ! git clone --depth 1 --branch "${LEBENCH_REF}" "${LEBENCH_REPO_URL}" "${SRC_DIR}"; then
      warn "branch/tag ${LEBENCH_REF} clone failed; trying default branch"
      git clone --depth 1 "${LEBENCH_REPO_URL}" "${SRC_DIR}"
    fi
  fi
  [[ -f "${SRC_DIR}/pyproject.toml" ]] || die "source tree incomplete: ${SRC_DIR}"
  export SRC_DIR
}

create_venv_and_install() {
  local venv_dir="${LEBENCH_PREFIX}/venv"
  mkdir -p "${LEBENCH_PREFIX}"
  log "Creating venv: ${venv_dir}"
  "${PYTHON_BIN}" -m venv "${venv_dir}"
  # shellcheck disable=SC1091
  source "${venv_dir}/bin/activate"
  python -m pip install -U pip setuptools wheel
  log "pip install ${SRC_DIR}"
  python -m pip install "${SRC_DIR}"
  deactivate || true
}

write_wrapper() {
  mkdir -p "${LEBENCH_BIN_DIR}"
  local wrapper="${LEBENCH_BIN_DIR}/lebench"
  cat > "${wrapper}" <<EOF
#!/usr/bin/env bash
exec "${LEBENCH_PREFIX}/venv/bin/lebench" "\$@"
EOF
  chmod +x "${wrapper}"
  log "Wrapper: ${wrapper}"

  case ":${PATH}:" in
    *":${LEBENCH_BIN_DIR}:"*) ;;
    *)
      warn "${LEBENCH_BIN_DIR} is not on PATH"
      warn "Add to ~/.bashrc:  export PATH=\"${LEBENCH_BIN_DIR}:\$PATH\""
      # Best-effort append once
      local rc="${HOME}/.bashrc"
      if [[ -f "${rc}" ]] && ! grep -q 'LeBench bin' "${rc}" 2>/dev/null; then
        if confirm "Append PATH export to ${rc}?"; then
          {
            echo ""
            echo "# LeBench bin"
            echo "export PATH=\"${LEBENCH_BIN_DIR}:\$PATH\""
          } >> "${rc}"
          log "Updated ${rc} — run: source ${rc}"
        fi
      fi
      ;;
  esac
}

run_doctor() {
  if [[ "${SKIP_DOCTOR}" -eq 1 ]]; then
    return 0
  fi
  log "Running lebench doctor ..."
  if [[ -x "${LEBENCH_PREFIX}/venv/bin/lebench" ]]; then
    "${LEBENCH_PREFIX}/venv/bin/lebench" --version || true
    "${LEBENCH_PREFIX}/venv/bin/lebench" doctor || true
  fi
}

print_next() {
  cat <<EOF

========================================================================
LeBench installed.
  prefix : ${LEBENCH_PREFIX}
  command: ${LEBENCH_BIN_DIR}/lebench

Try:
  export PATH="${LEBENCH_BIN_DIR}:\$PATH"
  lebench doctor
  lebench run --profile vps --intensity quick --yes --output-dir ./reports

Uninstall:
  bash install.sh --uninstall
========================================================================
EOF
}

main() {
  if [[ "${UNINSTALL}" -eq 1 ]]; then
    do_uninstall
  fi

  lebench_detect_os
  log "OS=${LEBENCH_OS_ID} ${LEBENCH_OS_VERSION} arch=${LEBENCH_ARCH} pkg=${LEBENCH_PKG_MGR}"

  if [[ "${LEBENCH_IS_LINUX}" -ne 1 ]]; then
    warn "Non-Linux host — install may work for CLI only; benchmarks target Linux VPS"
  elif ! lebench_arch_ok; then
    warn "Architecture ${LEBENCH_ARCH} is not in the verified set (x86_64/aarch64)"
  fi

  local deps_args=()
  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    deps_args+=(--yes)
  fi

  if [[ "${DEPS_ONLY}" -eq 1 ]]; then
    [[ "${NO_DEPS}" -eq 1 ]] && die "--deps-only conflicts with --no-deps"
    bash "${SCRIPT_DIR}/install_deps.sh" "${deps_args[@]+"${deps_args[@]}"}"
    exit 0
  fi

  if [[ "${INSTALL_DEPS}" -eq 1 && "${NO_DEPS}" -ne 1 && "${LEBENCH_IS_LINUX}" -eq 1 ]]; then
    bash "${SCRIPT_DIR}/install_deps.sh" "${deps_args[@]+"${deps_args[@]}"}"
  elif [[ "${NO_DEPS}" -eq 1 ]]; then
    log "Skipping system package install (--no-deps)"
  fi

  ensure_python
  fetch_source
  create_venv_and_install
  write_wrapper
  run_doctor
  print_next
}

main "$@"
