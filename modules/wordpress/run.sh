#!/usr/bin/env bash
# modules/wordpress/run.sh - WordPress + MariaDB + Redis via Compose
# shellcheck source=/dev/null

lzy_module_wordpress() {
  local out_partial="${LZY_RUN_DIR}/_wordpress_partial.json"
  source "${LZY_ROOT}/modules/_lib/app_common.sh"

  lzy_log_info "开始 WordPress 应用测试"
  lzy_app_json_init

  local status="ok" error=""
  local deploy_ms="null" ttfb_ms="null" total_ms="null" http_code=""
  local port="${LZY_WP_HOST_PORT:-18080}"
  local workdir="${LZY_APP_WORKDIR}/wordpress"
  local compose_src="${LZY_ROOT}/modules/wordpress/compose.yml"
  local project="lzybenchwp"

  if ! lzy_ensure_docker; then
    cat >"${out_partial}" <<EOF
{"status":"fail","error":"docker unavailable","deploy_ms":null,"ttfb_ms":null,"total_ms":null,"http_code":null}
EOF
    lzy_app_json_merge "wordpress" "${out_partial}"
    return 1
  fi

  local compose
  if ! compose="$(lzy_compose_cmd)"; then
    cat >"${out_partial}" <<EOF
{"status":"fail","error":"docker compose not available","deploy_ms":null,"ttfb_ms":null,"total_ms":null,"http_code":null}
EOF
    lzy_app_json_merge "wordpress" "${out_partial}"
    return 1
  fi

  mkdir -p "${workdir}"
  cp -f "${compose_src}" "${workdir}/compose.yml"
  export LZY_WP_HOST_PORT="${port}"

  # Tear down previous project
  lzy_info "清理旧 WordPress 栈（如有）"
  (cd "${workdir}" && ${compose} -p "${project}" down -v) >>"$(lzy_log_file wordpress)" 2>&1 || true

  lzy_info "部署 WordPress 栈（MariaDB + Redis + WP）端口 ${port}"
  local t0 t1
  t0="$(date +%s%N 2>/dev/null || date +%s)"

  if ! (cd "${workdir}" && ${compose} -p "${project}" up -d) >>"$(lzy_log_file wordpress)" 2>&1; then
    status="fail"
    error="compose up failed"
    lzy_warn "${error}"
  else
    # Wait for HTTP on host port (WP install screen counts as ready)
    if lzy_wait_http "http://127.0.0.1:${port}/" "${LZY_WP_WAIT_SEC:-240}"; then
      t1="$(date +%s%N 2>/dev/null || date +%s)"
      if [[ ${#t0} -gt 10 ]]; then
        deploy_ms=$(( (t1 - t0) / 1000000 ))
      else
        deploy_ms=$(( (t1 - t0) * 1000 ))
      fi
      lzy_ok "WordPress HTTP 就绪 ${deploy_ms}ms"

      # Timing sample (average of 3)
      local sum_ttfb=0 sum_total=0 ok_n=0 i
      for i in 1 2 3; do
        lzy_curl_timing "http://127.0.0.1:${port}/"
        http_code="${LZY_CURL_CODE}"
        if [[ "${http_code}" == 2* || "${http_code}" == 3* ]]; then
          sum_ttfb=$((sum_ttfb + LZY_CURL_TTFB))
          sum_total=$((sum_total + LZY_CURL_TOTAL))
          ok_n=$((ok_n + 1))
        fi
        sleep 0.3
      done
      if [[ ${ok_n} -gt 0 ]]; then
        ttfb_ms=$((sum_ttfb / ok_n))
        total_ms=$((sum_total / ok_n))
        lzy_info "页面 TTFB≈${ttfb_ms}ms  Total≈${total_ms}ms (code=${http_code})"
      else
        status="fail"
        error="${error};http timing failed"
      fi
    else
      status="fail"
      error="${error};wordpress http not ready"
      lzy_warn "WordPress HTTP 未在超时内就绪"
    fi
  fi

  cat >"${out_partial}" <<EOF
{
  "status": "${status}",
  "error": "$(lzy_json_escape "${error}")",
  "port": ${port},
  "deploy_ms": $(lzy_json_num_or_null "${deploy_ms}"),
  "ttfb_ms": $(lzy_json_num_or_null "${ttfb_ms}"),
  "total_ms": $(lzy_json_num_or_null "${total_ms}"),
  "http_code": $(lzy_json_num_or_null "${http_code}"),
  "stack": ["wordpress", "mariadb", "redis"],
  "compose_project": "$(lzy_json_escape "${project}")"
}
EOF
  lzy_app_json_merge "wordpress" "${out_partial}"

  if [[ "${LZY_APP_CLEANUP:-1}" == "1" ]]; then
    lzy_info "清理 WordPress Compose 栈"
    (cd "${workdir}" && ${compose} -p "${project}" down -v) >>"$(lzy_log_file wordpress)" 2>&1 || true
    if [[ "${LZY_KEEP_TEMP:-0}" != "1" ]]; then
      rm -rf "${workdir}" 2>/dev/null || true
    fi
  else
    lzy_warn "保留 WordPress 栈: http://127.0.0.1:${port}/  (LZY_APP_CLEANUP=0)"
  fi

  [[ "${status}" == "ok" ]] && return 0 || return 1
}
