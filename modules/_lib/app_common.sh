#!/usr/bin/env bash
# modules/_lib/app_common.sh - shared helpers for Docker / WordPress tests

LZY_APP_WORKDIR="${LZY_APP_WORKDIR:-/tmp/lzy-bench-app}"

lzy_docker_bin() {
  if lzy_require_cmd docker; then
    command -v docker
    return 0
  fi
  return 1
}

lzy_compose_cmd() {
  # Prefer "docker compose" plugin; fallback docker-compose
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi
  if lzy_require_cmd docker-compose; then
    echo "docker-compose"
    return 0
  fi
  return 1
}

lzy_ensure_docker() {
  if lzy_docker_bin >/dev/null; then
    if ! docker info >/dev/null 2>&1; then
      lzy_warn "Docker 已安装但 daemon 未就绪，尝试启动..."
      systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
      sleep 2
    fi
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    lzy_warn "Docker daemon 不可用"
    return 1
  fi

  if [[ "${LZY_DOCKER_AUTO_INSTALL:-1}" != "1" ]]; then
    lzy_warn "未安装 Docker，且 LZY_DOCKER_AUTO_INSTALL=0"
    return 1
  fi

  lzy_info "自动安装 Docker..."
  if ! lzy_require_cmd curl; then
    lzy_warn "需要 curl 才能安装 Docker"
    return 1
  fi
  if curl -fsSL https://get.docker.com | sh >>"$(lzy_log_file "${LZY_CURRENT_MODULE:-docker}")" 2>&1; then
    systemctl enable --now docker 2>/dev/null || service docker start 2>/dev/null || true
    sleep 2
    if docker info >/dev/null 2>&1; then
      lzy_ok "Docker 安装成功"
      return 0
    fi
  fi
  lzy_warn "Docker 安装失败"
  return 1
}

lzy_ms_since() {
  # args: start_epoch_seconds -> milliseconds (approx)
  local start="$1"
  local now
  now="$(date +%s)"
  echo $(( (now - start) * 1000 ))
}

lzy_time_ms() {
  # Run command, print elapsed ms to stdout on last line via variable
  # Usage: lzy_time_ms varname -- cmd...
  local __var="$1"
  shift
  [[ "${1:-}" == "--" ]] && shift
  local start end
  start="$(date +%s%N 2>/dev/null || date +%s)"
  "$@"
  local rc=$?
  end="$(date +%s%N 2>/dev/null || date +%s)"
  if [[ "${start}" == *N* || "${end}" == *N* ]]; then
    # fallback seconds
    start="$(date +%s)"
    # already ran — can't remeasure; use 0
    printf -v "${__var}" '%s' "0"
  else
    # nanoseconds available
    if [[ ${#start} -gt 10 ]]; then
      printf -v "${__var}" '%s' "$(( (end - start) / 1000000 ))"
    else
      printf -v "${__var}" '%s' "$(( (end - start) * 1000 ))"
    fi
  fi
  return "${rc}"
}

lzy_wait_http() {
  # url max_wait_sec
  local url="$1"
  local max="${2:-120}"
  local i=0 code
  while [[ ${i} -lt ${max} ]]; do
    code="$(curl -4 -sS -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 3 "${url}" 2>/dev/null || echo 000)"
    if [[ "${code}" == 2* || "${code}" == 3* ]]; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

lzy_wait_tcp() {
  local host="$1" port="$2" max="${3:-60}"
  local i=0
  while [[ ${i} -lt ${max} ]]; do
    if (echo >/dev/tcp/"${host}"/"${port}") >/dev/null 2>&1; then
      return 0
    fi
    # fallback nc
    if lzy_require_cmd nc && nc -z -w 1 "${host}" "${port}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

lzy_curl_timing() {
  # Sets globals: LZY_CURL_TTFB LZY_CURL_TOTAL LZY_CURL_CODE
  local url="$1"
  local out
  out="$(curl -4 -sS -o /tmp/lzy-app-body.txt -w '%{http_code} %{time_starttransfer} %{time_total}' \
    --connect-timeout 10 --max-time 30 "${url}" 2>/dev/null || echo '000 0 0')"
  LZY_CURL_CODE="$(echo "${out}" | awk '{print $1}')"
  local ttfb_s total_s
  ttfb_s="$(echo "${out}" | awk '{print $2}')"
  total_s="$(echo "${out}" | awk '{print $3}')"
  LZY_CURL_TTFB="$(awk -v t="${ttfb_s}" 'BEGIN{printf "%.0f", t*1000}')"
  LZY_CURL_TOTAL="$(awk -v t="${total_s}" 'BEGIN{printf "%.0f", t*1000}')"
}

lzy_app_json_init() {
  local out="${LZY_RUN_DIR}/application.json"
  if [[ -f "${out}" ]]; then
    return 0
  fi
  cat >"${out}" <<EOF
{
  "module": "application",
  "status": "pending",
  "timestamp": "$(lzy_now_iso)",
  "docker": { "status": "skip" },
  "wordpress": { "status": "skip" },
  "stability": { "status": "skip" }
}
EOF
}

lzy_app_json_merge() {
  # Merge a JSON object file into application.json under key $1
  # Usage: lzy_app_json_merge docker /path/to/partial.json
  local key="$1"
  local partial="$2"
  local out="${LZY_RUN_DIR}/application.json"
  local ts
  ts="$(lzy_now_iso)"
  lzy_app_json_init

  if lzy_has_jq; then
    local tmp
    tmp="$(mktemp)"
    jq --arg key "${key}" --arg ts "${ts}" --slurpfile p "${partial}" '
      .[$key] = $p[0] |
      .timestamp = $ts |
      .status = (
        if (.docker.status == "ok" or .wordpress.status == "ok") then "ok"
        elif (.docker.status == "fail" or .wordpress.status == "fail") then "fail"
        else (.status // "pending") end
      )
    ' "${out}" >"${tmp}" 2>/dev/null && mv "${tmp}" "${out}" || {
      rm -f "${tmp}"
      lzy_warn "jq merge 失败，回退写入 sidecar"
      cp -f "${partial}" "${LZY_RUN_DIR}/application_${key}.json"
    }
  else
    cp -f "${partial}" "${LZY_RUN_DIR}/application_${key}.json"
    lzy_warn "无 jq，已写入 application_${key}.json；评分可能不完整"
  fi
}

lzy_app_cleanup_containers() {
  # Remove containers by name prefix
  local prefix="${1:-lzybench-}"
  if ! lzy_docker_bin >/dev/null; then
    return 0
  fi
  local ids
  ids="$(docker ps -aq --filter "name=${prefix}" 2>/dev/null || true)"
  if [[ -n "${ids}" ]]; then
    # shellcheck disable=SC2086
    docker rm -f ${ids} >>"$(lzy_log_file "${LZY_CURRENT_MODULE:-docker}")" 2>&1 || true
  fi
}
