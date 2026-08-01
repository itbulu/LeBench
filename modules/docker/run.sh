#!/usr/bin/env bash
# modules/docker/run.sh - Docker runtime + Nginx/Redis/MySQL startup benchmarks
# shellcheck source=/dev/null

lzy_module_docker() {
  local out_partial="${LZY_RUN_DIR}/_docker_partial.json"
  source "${LZY_ROOT}/modules/_lib/app_common.sh"

  lzy_log_info "开始 Docker 应用测试"
  lzy_app_json_init

  local install_ms="null" nginx_ms="null" redis_ms="null" mysql_ms="null"
  local status="ok" error="" docker_ver=""
  local prefix="lzybench-"

  local t0 t1

  if ! lzy_ensure_docker; then
    cat >"${out_partial}" <<EOF
{
  "status": "fail",
  "error": "docker unavailable",
  "install_ms": null,
  "nginx_start_ms": null,
  "redis_start_ms": null,
  "mysql_start_ms": null
}
EOF
    lzy_app_json_merge "docker" "${out_partial}"
    return 1
  fi

  docker_ver="$(docker version --format '{{.Server.Version}}' 2>/dev/null || docker --version | awk '{print $3}' | tr -d ',')"

  # Cleanup leftovers from previous runs
  lzy_app_cleanup_containers "${prefix}"

  local img_nginx="${LZY_DOCKER_IMAGE_NGINX:-nginx:alpine}"
  local img_redis="${LZY_DOCKER_IMAGE_REDIS:-redis:7-alpine}"
  local img_mysql="${LZY_DOCKER_IMAGE_MYSQL:-mysql:8.0}"

  # --- Nginx ---
  lzy_info "拉取并启动 Nginx (${img_nginx})"
  t0="$(date +%s%N 2>/dev/null || date +%s)"
  if docker pull "${img_nginx}" >>"$(lzy_log_file docker)" 2>&1 \
    && docker run -d --name "${prefix}nginx" -p 18081:80 "${img_nginx}" >>"$(lzy_log_file docker)" 2>&1 \
    && lzy_wait_http "http://127.0.0.1:18081/" "${LZY_DOCKER_WAIT_SEC:-90}"; then
    t1="$(date +%s%N 2>/dev/null || date +%s)"
    if [[ ${#t0} -gt 10 ]]; then
      nginx_ms=$(( (t1 - t0) / 1000000 ))
    else
      nginx_ms=$(( (t1 - t0) * 1000 ))
    fi
    lzy_ok "Nginx 就绪 ${nginx_ms}ms"
  else
    status="fail"
    error="${error};nginx failed"
    lzy_warn "Nginx 启动失败"
  fi

  # --- Redis ---
  lzy_info "拉取并启动 Redis (${img_redis})"
  t0="$(date +%s%N 2>/dev/null || date +%s)"
  if docker pull "${img_redis}" >>"$(lzy_log_file docker)" 2>&1 \
    && docker run -d --name "${prefix}redis" -p 16379:6379 "${img_redis}" >>"$(lzy_log_file docker)" 2>&1; then
    # wait ready via docker exec ping
    local i=0 ready=0
    while [[ ${i} -lt ${LZY_DOCKER_WAIT_SEC:-90} ]]; do
      if docker exec "${prefix}redis" redis-cli ping 2>/dev/null | grep -q PONG; then
        ready=1
        break
      fi
      sleep 1
      i=$((i + 1))
    done
    t1="$(date +%s%N 2>/dev/null || date +%s)"
    if [[ ${ready} -eq 1 ]]; then
      if [[ ${#t0} -gt 10 ]]; then redis_ms=$(( (t1 - t0) / 1000000 )); else redis_ms=$(( (t1 - t0) * 1000 )); fi
      lzy_ok "Redis 就绪 ${redis_ms}ms"
    else
      status="fail"; error="${error};redis not ready"; lzy_warn "Redis 未就绪"
    fi
  else
    status="fail"; error="${error};redis failed"; lzy_warn "Redis 启动失败"
  fi

  # --- MySQL ---
  lzy_info "拉取并启动 MySQL (${img_mysql}) — 首次可能较慢"
  t0="$(date +%s%N 2>/dev/null || date +%s)"
  if docker pull "${img_mysql}" >>"$(lzy_log_file docker)" 2>&1 \
    && docker run -d --name "${prefix}mysql" \
      -e MYSQL_ROOT_PASSWORD=lzybench \
      -e MYSQL_DATABASE=lzy \
      -p 13306:3306 \
      "${img_mysql}" >>"$(lzy_log_file docker)" 2>&1; then
    local j=0 my_ready=0
    while [[ ${j} -lt ${LZY_DOCKER_MYSQL_WAIT_SEC:-180} ]]; do
      if docker exec "${prefix}mysql" mysqladmin ping -h127.0.0.1 -uroot -plzybench --silent 2>/dev/null; then
        my_ready=1
        break
      fi
      sleep 2
      j=$((j + 2))
    done
    t1="$(date +%s%N 2>/dev/null || date +%s)"
    if [[ ${my_ready} -eq 1 ]]; then
      if [[ ${#t0} -gt 10 ]]; then mysql_ms=$(( (t1 - t0) / 1000000 )); else mysql_ms=$(( (t1 - t0) * 1000 )); fi
      lzy_ok "MySQL 就绪 ${mysql_ms}ms"
    else
      status="fail"; error="${error};mysql not ready"; lzy_warn "MySQL 未就绪"
    fi
  else
    status="fail"; error="${error};mysql failed"; lzy_warn "MySQL 启动失败"
  fi

  # --- Optional short stability loop ---
  local stab_status="skip" stab_ok=0 stab_fail=0 stab_note=""
  if [[ "${LZY_STABILITY_ENABLE:-0}" == "1" ]]; then
    lzy_info "稳定性短测（Nginx HTTP 循环）"
    stab_status="ok"
    local n="${LZY_STABILITY_ROUNDS:-20}"
    local k
    for ((k=1; k<=n; k++)); do
      local code
      code="$(curl -4 -sS -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:18081/ 2>/dev/null || echo 000)"
      if [[ "${code}" == 2* ]]; then stab_ok=$((stab_ok+1)); else stab_fail=$((stab_fail+1)); fi
    done
    stab_note="nginx http rounds=${n}"
    local stab_partial="${LZY_RUN_DIR}/_stability_partial.json"
    cat >"${stab_partial}" <<EOF
{
  "status": "${stab_status}",
  "rounds": ${n},
  "ok": ${stab_ok},
  "fail": ${stab_fail},
  "note": "$(lzy_json_escape "${stab_note}")"
}
EOF
    lzy_app_json_merge "stability" "${stab_partial}"
  fi

  cat >"${out_partial}" <<EOF
{
  "status": "${status}",
  "error": "$(lzy_json_escape "${error}")",
  "docker_version": "$(lzy_json_escape "${docker_ver}")",
  "images": {
    "nginx": "$(lzy_json_escape "${img_nginx}")",
    "redis": "$(lzy_json_escape "${img_redis}")",
    "mysql": "$(lzy_json_escape "${img_mysql}")"
  },
  "nginx_start_ms": $(lzy_json_num_or_null "${nginx_ms}"),
  "redis_start_ms": $(lzy_json_num_or_null "${redis_ms}"),
  "mysql_start_ms": $(lzy_json_num_or_null "${mysql_ms}"),
  "note": "start_ms includes image pull + container start + readiness"
}
EOF
  lzy_app_json_merge "docker" "${out_partial}"

  if [[ "${LZY_APP_CLEANUP:-1}" == "1" ]]; then
    lzy_info "清理 Docker 测试容器"
    lzy_app_cleanup_containers "${prefix}"
  else
    lzy_warn "保留容器（LZY_APP_CLEANUP=0）: ${prefix}nginx/redis/mysql"
  fi

  [[ "${status}" == "ok" ]] && return 0 || return 1
}
