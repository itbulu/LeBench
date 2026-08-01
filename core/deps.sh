#!/usr/bin/env bash
# core/deps.sh - dependency checks and soft requirements

# Map module -> required commands (space-separated). Optional tools checked separately.
declare -A LZY_DEPS_REQUIRED=(
  [system]="uname lscpu free lsblk ip"
  [cpu]="sysbench"
  [memory]="sysbench"
  [disk]="fio"
  [network]="ping"
  [route]="curl"
  [streaming]="curl"
  [docker]=""
  [wordpress]=""
  [score]="jq"
)

declare -A LZY_DEPS_OPTIONAL=(
  [system]="jq whois curl"
  [cpu]="jq geekbench6 geekbench5 unixbench"
  [memory]="jq"
  [disk]="jq"
  [network]="jq speedtest speedtest-cli curl"
  [route]="jq whois traceroute mtr besttrace nexttrace"
  [streaming]="jq"
  [docker]="jq docker docker-compose curl"
  [wordpress]="jq docker docker-compose curl"
)

lzy_deps_check_module() {
  local module="$1"
  local missing=()
  local req="${LZY_DEPS_REQUIRED[${module}]:-}"
  local cmd

  for cmd in ${req}; do
    if ! lzy_require_cmd "${cmd}"; then
      missing+=("${cmd}")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    lzy_warn "模块 [${module}] 缺少依赖: ${missing[*]}"
    lzy_log_warn "模块 [${module}] 缺少依赖: ${missing[*]}"
    return 1
  fi
  return 0
}

lzy_deps_list_optional() {
  local module="$1"
  local opt="${LZY_DEPS_OPTIONAL[${module}]:-}"
  local cmd
  local available=()
  local missing=()

  for cmd in ${opt}; do
    if lzy_require_cmd "${cmd}"; then
      available+=("${cmd}")
    else
      missing+=("${cmd}")
    fi
  done

  if [[ ${#available[@]} -gt 0 ]]; then
    lzy_info "模块 [${module}] 可选依赖可用: ${available[*]}"
  fi
  if [[ ${#missing[@]} -gt 0 ]]; then
    lzy_info "模块 [${module}] 可选依赖未安装: ${missing[*]}"
  fi
}

lzy_has_jq() {
  lzy_require_cmd jq
}
